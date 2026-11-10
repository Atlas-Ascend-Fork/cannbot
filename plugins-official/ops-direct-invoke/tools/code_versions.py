#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------
"""Local Git checkpoints for DSL runs. JSON output; no shell, remote or harness writes.

See ../docs/code-versions.md for the executor/verifier protocol.
"""

import argparse
from contextlib import contextmanager
import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time
import uuid


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(repo, *args, check=True):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(
            ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")
        ):
            env.pop(key)
    env["GIT_LITERAL_PATHSPECS"] = "1"
    executable = shutil.which("git")
    require(executable is not None, "git executable not found")
    result = subprocess.run(
        [
            str(Path(executable).resolve()),
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.excludesFile=/dev/null",
            "-c",
            "commit.gpgsign=false",
            "-C",
            str(repo),
            *args,
        ],
        capture_output=True,
        env=env,
    )
    if check and result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace").strip())
    return result


def output(repo, *args):
    return git(repo, *args).stdout.decode("utf-8").strip()


def atomic_json(path, value):
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temp, path)


def identifier(value):
    require(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value),
        "invalid node/attempt ID",
    )
    return value


def relative(value):
    path = PurePosixPath(value)
    require(
        value
        and "\\" not in value
        and ":" not in value
        and not path.is_absolute()
        and all(p.lower() not in ("..", ".", ".git") for p in value.split("/")),
        "paths must be literal, relative, and contained in CODE_DIR",
    )
    return path.as_posix()


class Versions:
    def __init__(self, work, lock_timeout=30):
        self.work = Path(work).resolve()
        self.meta = self.work / "versioning"
        self.state_path = self.meta / "state.json"
        self.state = None
        self.lock_timeout = lock_timeout

    @staticmethod
    def check_restore_obstructions(repo, target):
        # Git read-tree handles tracked additions/deletions and refuses obstructing files.
        # Ignored assets are explicitly checked because Git can overwrite ignored files.
        ignored = git(
            repo, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"
        ).stdout
        target_files = git(
            repo, "ls-tree", "-r", "--name-only", "-z", target
        ).stdout.split(b"\0")
        for path in filter(None, ignored.split(b"\0")):
            require(
                not any(
                    path == p or path.startswith(p + b"/") or p.startswith(path + b"/")
                    for p in target_files
                    if p
                ),
                "ignored file obstructs restore",
            )

    @staticmethod
    def head(repo, expected=None):
        sha = output(repo, "rev-parse", "HEAD")
        if expected is not None:
            require(
                sha == expected, "HEAD drift: expected " + expected + ", got " + sha
            )
        return sha

    @staticmethod
    def changed(repo, base="HEAD"):
        paths = set()
        for args in [
            ("diff", "--name-only", "-z", "--no-renames", base),
            ("diff", "--cached", "--name-only", "-z", "--no-renames", base),
            ("ls-files", "--others", "--exclude-standard", "-z"),
        ]:
            paths.update(
                p.decode("utf-8") for p in git(repo, *args).stdout.split(b"\0") if p
            )
        return sorted(paths)

    @staticmethod
    def clean(repo):
        require(
            not git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout,
            "dirty checkout; preserve/checkpoint existing changes first",
        )

    @staticmethod
    def result_path(path):
        parts = path.parts
        return (
            len(parts) >= 4
            and parts[0] == "operators"
            and parts[2:4] == ("test", "testcase_output")
        )

    @staticmethod
    def result_dirs(repo):
        return sorted(repo.glob("operators/*/test/testcase_output"))

    @staticmethod
    def no_operation(repo):
        for name in (
            "MERGE_HEAD",
            "CHERRY_PICK_HEAD",
            "REVERT_HEAD",
            "rebase-merge",
            "rebase-apply",
        ):
            path = Path(output(repo, "rev-parse", "--git-path", name))
            require(
                not (path if path.is_absolute() else repo / path).exists(),
                "unfinished Git operation: " + name,
            )

    def recover_checkpoint(self, record, node, attempt, expected):
        require(expected == record["sha"], "recovery HEAD differs from checkpoint")
        record.setdefault("recoveries", []).append(
            {"base": record["base"], "sha": record["sha"], "state": record["state"]}
        )
        record["base"] = expected
        record.pop("merge_head", None)
        record["state"] = "editing"
        self.state["accepted"].pop(node, None)
        self.state["events"].append(
            {"kind": "recover", "node": node, "attempt": attempt, "sha": expected}
        )
        self.save()

    def begin_dependencies(self, name, repo, deps, integrating):
        inherited = self.state["repos"][name].get("dependencies", {})
        supplied = dict(value.split("=", 1) for value in deps)
        require(len(supplied) == len(deps), "duplicate dependency")
        dependencies = self.dependencies(
            [f"{n}={s}" for n, s in {**inherited, **supplied}.items()]
        )
        if not integrating:
            for sha in dependencies.values():
                require(
                    git(
                        repo, "merge-base", "--is-ancestor", sha, "HEAD", check=False
                    ).returncode
                    == 0,
                    "dependency not in checkout; integrate it before begin",
                )
        return dependencies

    def initialize_repository(self):
        repo = self.work / "code"
        require(
            not repo.exists(),
            "code directory already exists; refusing to adopt/migrate it",
        )
        repo.mkdir()
        git(repo, "init", "-b", "dsl-main")
        git(repo, "config", "user.name", "DSL workflow")
        git(repo, "config", "user.email", "dsl-workflow@localhost")
        git(repo, "config", "core.autocrlf", "false")
        (repo / ".gitignore").write_text(
            "__pycache__/\n*.pyc\n/operators/*/test/testcase_output/\n",
            encoding="utf-8",
        )
        git(repo, "add", "--", ".gitignore")
        git(repo, "commit", "-m", "Initialize DSL code history")
        self.state = {
            "format": 1,
            "work_dir": str(self.work),
            "repos": {"main": {"path": str(repo), "branch": "dsl-main"}},
            "nodes": {},
            "attempts": {},
            "history": {},
            "accepted": {},
            "events": [],
        }
        self.remember(repo)
        self.save()

    @contextmanager
    def locked(self):
        self.meta.mkdir(parents=True, exist_ok=True)
        lock = self.meta / "operation.lock"
        deadline = time.monotonic() + self.lock_timeout
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise ValueError(
                        "version operation locked; inspect owner before recovering stale lock"
                    ) from None
                time.sleep(0.05)
        os.write(fd, json.dumps({"pid": os.getpid()}).encode())
        os.close(fd)
        try:
            if self.state_path.exists():
                self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
                require(
                    self.state["work_dir"] == str(self.work),
                    "run moved; explicit recovery required",
                )
            yield
        finally:
            lock.unlink()

    def save(self):
        atomic_json(self.state_path, self.state)

    def repo(self, node):
        require(self.state is not None, "run init first")
        name = self.state["nodes"].get(node, "main")
        require(name in self.state["repos"], "unknown checkout")
        repo = Path(self.state["repos"][name]["path"])
        require(
            repo.resolve() == repo and repo.is_relative_to(self.work),
            "checkout path changed",
        )
        require(
            Path(output(repo, "rev-parse", "--show-toplevel")).resolve() == repo,
            "not the registered repository root",
        )
        require(
            output(repo, "branch", "--show-current")
            == self.state["repos"][name]["branch"],
            "registered branch changed",
        )
        return name, repo

    def registered(self, sha):
        require(
            re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha or "") is not None
            and sha in self.state["history"],
            "target must be a registered full commit SHA",
        )
        return sha

    def remember(self, repo):
        sha = self.head(repo)
        # Persistent refs retain failed attempts and bundle every registered checkpoint.
        git(repo, "update-ref", "refs/checkpoints/" + sha, sha)
        self.state["history"][sha] = output(repo, "rev-parse", "HEAD^{tree}")
        return sha

    def code_inventory(self, repo):
        """Only bytecode may be ignored; nested policies cannot hide source files."""
        ignored = git(
            repo, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"
        ).stdout
        for raw in filter(None, ignored.split(b"\0")):
            path = PurePosixPath(raw.decode("utf-8"))
            require(
                path.suffix == ".pyc"
                or "__pycache__" in path.parts
                or self.result_path(path),
                "unknown ignored asset in code checkout: " + str(path),
            )

    def archive_results(self, repo, evidence):
        root = self.meta / "artifacts" / evidence["id"]
        for source in self.result_dirs(repo):
            require(
                source.resolve().is_relative_to(repo) and not source.is_symlink(),
                "unsafe result path",
            )
            require(
                not any(
                    p.is_symlink() for p in source.parents if p.is_relative_to(repo)
                ),
                "symlink parent in test results",
            )
            require(
                all(not p.is_symlink() for p in source.rglob("*")),
                "symlink in test results",
            )
            require(
                not git(
                    repo, "ls-files", "--", source.relative_to(repo).as_posix()
                ).stdout,
                "test output overlaps tracked files",
            )
            destination = root / source.relative_to(repo)
            require(
                destination.resolve().is_relative_to(self.meta)
                and not destination.exists(),
                "artifact destination already exists or escapes run",
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
        evidence["artifacts"] = (
            {
                str(p.relative_to(self.meta)): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in root.rglob("*")
                if p.is_file()
            }
            if root.exists()
            else {}
        )

    def check_artifacts(self, evidence):
        for name, digest in evidence.get("artifacts", {}).items():
            path = self.meta / name
            require(
                path.is_file()
                and hashlib.sha256(path.read_bytes()).hexdigest() == digest,
                "test artifact missing or changed: " + name,
            )

    def idle(self, name, except_key=None):
        require(
            not any(
                a["repo"] == name and a["state"] in ("editing", "conflict", "testing")
                for key, a in self.state["attempts"].items()
                if key != except_key
            ),
            "checkout has an active attempt; resume it instead of starting another",
        )

    def inputs(self, extras=()):
        paths = (
            list((self.work / "design").rglob("*"))
            if not extras and (self.work / "design").exists()
            else []
        )
        for extra in extras:
            path = Path(extra).resolve()
            require(
                path.is_relative_to(self.work) and path.exists(),
                "input outside run or missing",
            )
            paths.extend(path.rglob("*") if path.is_dir() else [path])
        result = {}
        for path in sorted(set(paths)):
            require(not path.is_symlink(), "symlink in frozen inputs")
            if path.is_file():
                result[str(path.relative_to(self.work))] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        return result

    def init(self, node=None, base=None):
        if self.state is None:
            require(node is None, "initialize the run before a Unit")
            self.initialize_repository()
        if node:
            identifier(node)
            self.registered(base)
            if node not in self.state["nodes"]:
                root = self.work / "code"
                path = self.work / "code-worktrees" / node
                require(not path.exists(), "Unit path already exists")
                git(root, "worktree", "add", "-b", "dsl-" + node, str(path), base)
                self.state["repos"][node] = {
                    "path": str(path),
                    "branch": "dsl-" + node,
                    "base": base,
                }
                self.state["nodes"][node] = node
                self.save()
            else:
                require(
                    self.state["repos"][node]["base"] == base,
                    "Unit base changed; do not silently reset",
                )
        return self.status(node or "main")

    def dependencies(self, values):
        deps = {}
        for value in values:
            node, sha = value.split("=", 1)
            require(node not in deps, "duplicate dependency")
            self.registered(sha)
            require(
                node in self.state["accepted"]
                and self.state["accepted"][node]["sha"] == sha,
                "dependency not accepted at requested SHA: " + node,
            )
            self.accepted_valid(node, set())
            deps[node] = sha
        return deps

    def accepted_valid(self, node, seen):
        require(node not in seen, "dependency cycle")
        seen = seen | {node}
        accepted = self.state["accepted"][node]
        attempt = self.state["attempts"][accepted["attempt"]]
        evidence = next(
            e for e in attempt["evidence"] if e["id"] == accepted["evidence"]
        )
        log = self.meta / (evidence["id"] + ".log")
        require(
            log.exists()
            and hashlib.sha256(log.read_bytes()).hexdigest() == evidence["log_sha256"],
            "accepted evidence log missing or changed",
        )
        self.check_artifacts(evidence)
        name, repo = self.repo(node)
        self.idle(name)
        self.head(repo, accepted["sha"])
        self.clean(repo)
        self.code_inventory(repo)
        self.no_operation(repo)
        require(
            attempt["inputs"] == self.inputs(attempt["extra_inputs"]),
            "frozen inputs changed",
        )
        for dep, sha in attempt["dependencies"].items():
            require(
                self.state["accepted"].get(dep, {}).get("sha") == sha,
                "dependency evidence invalidated",
            )
            self.accepted_valid(dep, seen)

    def begin(
        self, node, attempt, expected, allow, deps=(), inputs=(), integrating=False
    ):
        identifier(node)
        identifier(attempt)
        key = node + "/" + attempt
        name, repo = self.repo(node)
        self.head(repo, expected)
        self.registered(expected)
        allowed = [relative(p) for p in allow]
        require(allowed, "explicit allowed paths required")
        require(
            all(p != ".gitignore" and not p.startswith("design/") for p in allowed),
            "repository policy/frozen inputs cannot be edited",
        )
        dependencies = self.begin_dependencies(name, repo, deps, integrating)
        if key in self.state["attempts"]:
            old = self.state["attempts"][key]
            require(
                old["state"] in ("editing", "conflict")
                and old["base"] == expected
                and old["allow"] == allowed
                and old["dependencies"] == dependencies,
                "attempt already used or resume parameters differ",
            )
            return old
        self.no_operation(repo)
        self.clean(repo)
        self.idle(name)
        self.state["accepted"].pop(node, None)
        self.state["nodes"].setdefault(node, name)
        record = {
            "node": node,
            "attempt": attempt,
            "repo": name,
            "base": expected,
            "sha": None,
            "state": "editing",
            "allow": allowed,
            "dependencies": dependencies,
            "extra_inputs": list(inputs),
            "inputs": self.inputs(inputs),
            "evidence": [],
        }
        self.state["attempts"][key] = record
        self.save()
        return record

    def attempt(self, node, attempt):
        key = node + "/" + attempt
        require(key in self.state["attempts"], "unknown attempt")
        return self.state["attempts"][key]

    def check_paths(self, repo, record):
        self.code_inventory(repo)
        paths = self.changed(repo, record["base"])
        for path in paths:
            relative(path)
            require(
                PurePosixPath(path).name
                not in (".gitignore", ".gitattributes", ".gitmodules"),
                "code changes cannot alter Git policy: " + path,
            )
            require(
                not self.result_path(PurePosixPath(path)),
                "test outputs are not source files",
            )
            require(
                any(path == p or path.startswith(p + "/") for p in record["allow"]),
                "change outside allowed paths: " + path,
            )
            target = repo / path
            require(
                target.resolve().is_relative_to(repo) and not target.is_symlink(),
                "symlink/path escape: " + path,
            )
            require(
                not any(
                    p.is_symlink()
                    for p in target.parents
                    if p != repo and p.is_relative_to(repo)
                ),
                "symlink parent: " + path,
            )
        return paths

    def checkpoint(self, node, attempt, expected, recover=False):
        record = self.attempt(node, attempt)
        _, repo = self.repo(node)
        self.head(repo, expected)
        if recover and record["state"] in (
            "testing",
            "invalid",
            "verified",
            "checkpointed",
        ):
            self.recover_checkpoint(record, node, attempt, expected)
        require(record["state"] in ("editing", "conflict"), "attempt is not editable")
        require(
            expected == record.get("merge_head", record["base"]), "attempt HEAD drift"
        )
        require(
            record["inputs"] == self.inputs(record["extra_inputs"]),
            "frozen inputs changed",
        )
        paths = self.check_paths(repo, record)
        if record["state"] != "conflict":
            self.no_operation(repo)
        if paths:
            git(repo, "add", "--all", "--", *paths)
        for entry in git(repo, "ls-files", "--stage", "-z").stdout.split(b"\0"):
            if entry:
                require(
                    entry.split(b" ", 1)[0] not in (b"120000", b"160000"),
                    "symlinks and embedded repositories are not managed code",
                )
        require(
            not git(repo, "ls-files", "--unmerged").stdout, "unresolved merge entries"
        )
        staged = git(repo, "diff", "--cached", "--name-only", "-z").stdout
        if staged or record["state"] == "conflict":
            git(repo, "commit", "-m", f"DSL {node} attempt {attempt}")
        if record.get("remaining"):
            record["state"] = "editing"
            self.remember(repo)
            self.save()
            self.merge_remaining(repo, record)
        self.clean(repo)
        self.no_operation(repo)
        record["sha"] = self.remember(repo)
        record["state"] = "checkpointed"
        self.state["repos"][record["repo"]]["dependencies"] = record["dependencies"]
        self.save()
        return record

    def integrate(self, node, attempt, expected, allow, deps):
        record = self.begin(node, attempt, expected, allow, deps, integrating=True)
        _, repo = self.repo(node)
        require(
            record["state"] == "editing", "resolve the pending conflict via checkpoint"
        )
        record["remaining"] = list(record["dependencies"].items())
        self.save()
        self.merge_remaining(repo, record)
        return self.checkpoint(node, attempt, self.head(repo))

    def merge_remaining(self, repo, record):
        while record["remaining"]:
            dep, sha = record["remaining"][0]
            if (
                git(
                    repo, "merge-base", "--is-ancestor", sha, "HEAD", check=False
                ).returncode
                == 0
            ):
                record["remaining"].pop(0)
                continue
            result = git(repo, "merge", "--no-ff", "--no-commit", sha, check=False)
            record["merge_head"] = self.head(repo)
            if result.returncode:
                merge_path = Path(output(repo, "rev-parse", "--git-path", "MERGE_HEAD"))
                merge_path = (
                    merge_path if merge_path.is_absolute() else repo / merge_path
                )
                record["state"] = "conflict" if merge_path.exists() else "editing"
                record["merge_error"] = result.stderr.decode("utf-8", "replace")
                self.save()
                raise ValueError(
                    "integration stopped; preserve checkout and resolve allowed conflicts, then checkpoint"
                )
            # Validate staged merge changes before creating a commit, including clean merges.
            record["state"] = "conflict"
            self.save()
            self.check_paths(repo, record)
            git(repo, "commit", "-m", "Integrate " + dep + " at " + sha)
            record["state"] = "editing"
            record["remaining"].pop(0)
            self.remember(repo)
            self.save()
        record["merge_head"] = self.head(repo)

    def bundle(self, destination):
        path = Path(destination).resolve()
        _, repo = self.repo("main")
        self.clean(repo)
        self.no_operation(repo)
        self.idle("main")
        require(
            not path.is_relative_to(repo) and not path.exists(),
            "bundle destination must be new and outside code",
        )
        manifest = path.with_suffix(path.suffix + ".json")
        require(not manifest.exists(), "bundle manifest already exists")
        git(repo, "bundle", "create", str(path), "--all")
        git(repo, "bundle", "verify", str(path))
        atomic_json(
            manifest,
            {
                "head": self.head(repo),
                "history": self.state["history"],
                "files": output(repo, "ls-tree", "-r", "HEAD"),
                "bundle_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "state": self.state,
            },
        )
        return {"bundle": str(path), "manifest": str(manifest)}

    def verify_start(self, node, attempt, expected, command):
        record = self.attempt(node, attempt)
        name, repo = self.repo(node)
        self.idle(name)
        require(
            record["state"] in ("checkpointed", "verified"),
            "checkpoint before verification",
        )
        require(record["sha"] == expected, "evidence SHA differs from attempt")
        self.head(repo, expected)
        self.clean(repo)
        self.code_inventory(repo)
        self.no_operation(repo)
        require(
            record["inputs"] == self.inputs(record["extra_inputs"]),
            "frozen inputs changed",
        )
        self.dependencies([f"{n}={s}" for n, s in record["dependencies"].items()])
        require(command, "verification command required after --")
        require(
            not self.result_dirs(repo),
            "existing test results: preserve/move them before running again",
        )
        record["state"] = "testing"
        evidence = {
            "id": uuid.uuid4().hex,
            "sha": expected,
            "command": command,
            "code_dir": str(repo),
            "inputs": record["inputs"],
            "exit_code": None,
            "valid": False,
        }
        record["evidence"].append(evidence)
        self.save()
        return repo, evidence

    def verify_finish(self, node, attempt, evidence_id, returncode):
        record = self.attempt(node, attempt)
        _, repo = self.repo(node)
        evidence = next(e for e in record["evidence"] if e["id"] == evidence_id)
        evidence["exit_code"] = returncode
        try:
            self.archive_results(repo, evidence)
            self.head(repo, evidence["sha"])
            self.clean(repo)
            self.code_inventory(repo)
            self.no_operation(repo)
            require(
                record["inputs"] == self.inputs(record["extra_inputs"]),
                "frozen inputs changed",
            )
            self.dependencies([f"{n}={s}" for n, s in record["dependencies"].items()])
            evidence["valid"] = True
        except (ValueError, OSError) as error:
            evidence["error"] = str(error)
        record["state"] = "verified" if evidence["valid"] else "invalid"
        self.save()
        return evidence

    def accept(self, node, attempt, expected, evidence_id):
        record = self.attempt(node, attempt)
        name, repo = self.repo(node)
        self.idle(name)
        self.head(repo, expected)
        self.clean(repo)
        self.code_inventory(repo)
        self.no_operation(repo)
        require(
            record["sha"] == expected and record["state"] == "verified",
            "unverified attempt",
        )
        require(
            record["inputs"] == self.inputs(record["extra_inputs"]),
            "frozen inputs changed",
        )
        self.dependencies([f"{n}={s}" for n, s in record["dependencies"].items()])
        evidence = next((e for e in record["evidence"] if e["id"] == evidence_id), None)
        require(
            evidence and evidence["valid"] and evidence["exit_code"] == 0,
            "no successful evidence",
        )
        log = self.meta / (evidence_id + ".log")
        require(
            log.exists()
            and hashlib.sha256(log.read_bytes()).hexdigest() == evidence["log_sha256"],
            "evidence log missing or changed",
        )
        self.check_artifacts(evidence)
        self.state["accepted"][node] = {
            "sha": expected,
            "attempt": node + "/" + attempt,
            "evidence": evidence_id,
        }
        self.save()
        return self.state["accepted"][node]

    def restore(self, node, target, expected, reason):
        require(reason and reason.strip(), "restore reason required")
        self.registered(target)
        name, repo = self.repo(node)
        self.idle(name)
        self.head(repo, expected)
        self.registered(expected)
        self.clean(repo)
        self.no_operation(repo)
        self.check_restore_obstructions(repo, target)
        event = {
            "kind": "restore",
            "node": node,
            "from": expected,
            "target": target,
            "reason": reason,
            "state": "pending",
        }
        self.state["events"].append(event)
        self.save()
        git(repo, "read-tree", "--reset", "-u", target)
        git(repo, "commit", "--allow-empty", "-m", "Restore " + target + ": " + reason)
        self.clean(repo)
        require(
            output(repo, "rev-parse", "HEAD^{tree}") == self.state["history"][target],
            "restored tree differs from target",
        )
        event.update(state="complete", sha=self.remember(repo))
        target_attempts = [
            a for a in self.state["attempts"].values() if a["sha"] == target
        ]
        self.state["repos"][name]["dependencies"] = (
            target_attempts[-1]["dependencies"] if target_attempts else {}
        )
        for key, accepted in list(self.state["accepted"].items()):
            if self.state["attempts"][accepted["attempt"]]["repo"] == name:
                del self.state["accepted"][key]
        self.save()
        return event

    def status(self, node):
        name, repo = self.repo(node)
        result = {
            "CODE_DIR": str(repo),
            "head": self.head(repo),
            "repo": name,
            "changes": self.changed(repo),
            "attempts": self.state["attempts"],
            "accepted": self.state["accepted"],
        }
        result["stale_accepted"] = []
        for key in self.state["accepted"]:
            try:
                self.accepted_valid(key, set())
            except ValueError:
                result["stale_accepted"].append(key)
        return result


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument(
        "action",
        choices=[
            "init",
            "begin",
            "checkpoint",
            "verify",
            "integrate",
            "restore",
            "status",
        ],
    )
    parser.add_argument("--node", default="main")
    parser.add_argument("--attempt")
    parser.add_argument("--base")
    parser.add_argument("--expected-head")
    parser.add_argument("--allow", action="append", default=[])
    parser.add_argument("--dependency", action="append", default=[])
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--target")
    parser.add_argument("--reason")
    parser.add_argument("--accept", metavar="EVIDENCE_ID")
    parser.add_argument(
        "--recover",
        action="store_true",
        help="explicitly recover an interrupted/invalid checkpoint after stopping its process",
    )
    parser.add_argument(
        "--bundle", help="status: export a new bundle and manifest outside code"
    )
    parser.add_argument(
        "--lock-timeout",
        type=float,
        default=30,
        help="seconds to wait for another Git operation",
    )
    # Split explicitly: argparse REMAINDER would swallow options after the action.
    argv = sys.argv[1:]
    split = argv.index("--") if "--" in argv else len(argv)
    args = parser.parse_args(argv[:split])
    command_start = split + 1
    command = argv[command_start:]
    return args, command


def dispatch(manager, args, command):
    if args.action not in ("init", "status"):
        require(args.expected_head, "--expected-head required")
    if args.action in ("begin", "checkpoint", "verify", "integrate"):
        require(args.attempt, "--attempt required")
    if args.action == "init":
        result = manager.init(None if args.node == "main" else args.node, args.base)
    elif args.action == "status":
        result = (
            manager.bundle(args.bundle) if args.bundle else manager.status(args.node)
        )
    elif args.action == "begin":
        result = manager.begin(
            args.node,
            args.attempt,
            args.expected_head,
            args.allow,
            args.dependency,
            args.input,
        )
    elif args.action == "checkpoint":
        result = manager.checkpoint(
            args.node, args.attempt, args.expected_head, args.recover
        )
    elif args.action == "integrate":
        result = manager.integrate(
            args.node,
            args.attempt,
            args.expected_head,
            args.allow,
            args.dependency,
        )
    elif args.action == "restore":
        result = manager.restore(
            args.node, args.target, args.expected_head, args.reason
        )
    elif args.accept:
        result = manager.accept(
            args.node, args.attempt, args.expected_head, args.accept
        )
    else:
        return manager.verify_start(
            args.node, args.attempt, args.expected_head, command
        )
    return result


def run_verification(manager, args, command, repo, evidence):
    log = manager.meta / (evidence["id"] + ".log")
    env = os.environ.copy()
    env.update(CODE_DIR=str(repo), WORK_DIR=str(manager.work), PYTHONPATH=str(repo))
    env["PYTHONPYCACHEPREFIX"] = str(
        manager.meta / "cache" / evidence["id"] / "pycache"
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault(
        "CANNBOTDSL_CACHE_DIR",
        str(manager.meta / "cache" / evidence["sha"] / "compiled"),
    )
    try:
        with log.open("wb") as stream:
            completed = subprocess.run(
                command,
                cwd=repo,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
        returncode = completed.returncode
    except OSError as error:
        log.write_text(str(error), encoding="utf-8")
        returncode = 127
    with manager.locked():
        result = manager.verify_finish(
            args.node, args.attempt, evidence["id"], returncode
        )
        result["log_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
        result["log"] = str(log)
        manager.save()
    return result, returncode


def emit_json(value, stream):
    """Emit one JSON record without changing the process-wide logging setup."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    reporter = logging.Logger("code_versions.output", level=logging.INFO)
    reporter.addHandler(handler)
    reporter.info("%s", json.dumps(value, ensure_ascii=False))


def main():
    args, command = parse_arguments()
    manager = Versions(args.work_dir, max(0, args.lock_timeout))
    try:
        with manager.locked():
            result = dispatch(manager, args, command)
        returncode = 0
        if args.action == "verify" and not args.accept:
            result, returncode = run_verification(manager, args, command, *result)
            returncode = 0 if result["valid"] and returncode == 0 else 1
        emit_json(result, sys.stdout)
        return returncode
    except (ValueError, OSError, KeyError, StopIteration) as error:
        emit_json({"error": str(error)}, sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
