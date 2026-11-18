#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Create CCU drafts and bind only an explicitly reviewed environment report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
CLI = importlib.import_module("validate_aicpu_artifacts")
TEMPLATES = Path(__file__).resolve().parents[1] / "templates"


def git(root, *args):
    executable = shutil.which("git")
    if executable is None:
        raise ValueError("git executable was not found")
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(
        [executable, "-c", "core.fsmonitor=false", "-C", str(root), *args],
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
    )
    return result.stdout.rstrip("\n")


def add_untracked_fingerprint(root, relative, fingerprint):
    path = root / relative
    fingerprint.update(relative.encode())
    if path.is_symlink():
        fingerprint.update(os.readlink(path).encode())
        return
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            fingerprint.update(block)


def repository(root, supplied_identity=None, exclude=None):
    root = Path(root).resolve(strict=True)
    if Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise ValueError("repository path must be its Git worktree root")
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    head = git(root, "rev-parse", "HEAD")
    scope = ["--", ".", ":(exclude)" + exclude] if exclude else []
    status = git(root, "status", "--porcelain=v1", "--untracked-files=all", *scope)
    patch = git(
        root, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", *scope
    )
    untracked = git(
        root, "ls-files", "--others", "--exclude-standard", "-z", *scope
    ).split("\0")
    fingerprint = hashlib.sha256(
        (branch + "\n" + head + "\n" + status + "\n" + patch).encode()
    )
    for relative in sorted(path for path in untracked if path):
        add_untracked_fingerprint(root, relative, fingerprint)
    worktree = "DIRTY" if status else "CLEAN"
    if status and not supplied_identity:
        raise ValueError(
            str(root) + ": dirty worktree requires a confirmed "
            "--source-identity/--hcomm-source-identity and recoverable snapshot; "
            "no clean identity inferred"
        )
    identity = supplied_identity or f"{root}@{branch}:{head}:CLEAN"
    if not identity.strip() or head not in identity or worktree not in identity:
        raise ValueError(
            "supplied identity must include the current full HEAD and worktree state"
        )
    return dict(
        root=str(root),
        branch=branch,
        head=head,
        worktree=worktree,
        identity=identity,
        status=status,
        fingerprint=fingerprint.hexdigest(),
    )


def within(path, root):
    return path.is_relative_to(root)


def validate_destinations(task, evidence, repositories, task_id):
    source = Path(repositories["hccl"]["root"])
    if not within(task, source):
        raise ValueError("resolved task directory escapes source repository")
    roots = [source, Path(repositories["hcomm"]["root"]), task]
    overlap = any(within(evidence, root) or within(root, evidence) for root in roots)
    if task_id not in evidence.parts or overlap:
        raise ValueError(
            "evidence-root must be scoped by task-id and outside both source repositories"
        )
    if task.exists() or evidence.exists():
        raise ValueError(
            "task/evidence destination already exists; initialization never overwrites"
        )


def initialization_inputs(args):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.task_id):
        raise ValueError("task-id must be a safe directory component")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", args.op_type):
        raise ValueError("op-type must be a source operator directory name")
    requirement = Path(args.requirement_file).read_text(encoding="utf-8").strip()
    if not requirement:
        raise ValueError("requirement must be nonempty")
    excluded = f"src/ops/{args.op_type}/docs/{args.task_id}"
    repositories = {
        "hccl": repository(args.source_repo, args.source_identity, exclude=excluded),
        "hcomm": repository(args.hcomm_repo, args.hcomm_source_identity),
    }
    source = Path(repositories["hccl"]["root"])
    if not (source / "src/ops" / args.op_type).is_dir():
        raise ValueError("operator directory is absent")
    task = (source / "src/ops" / args.op_type / "docs" / args.task_id).resolve()
    evidence = Path(args.evidence_root).resolve()
    validate_destinations(task, evidence, repositories, args.task_id)
    return requirement, repositories, task, evidence


def initial_index(args, requirement, repositories, evidence, now):
    source, hcomm = repositories["hccl"], repositories["hcomm"]
    index = json.loads((TEMPLATES / "ccu-task-index-template.json").read_text())
    index.update(
        task_id=args.task_id,
        requirement=requirement,
        source_repo=source["root"],
        source_branch=source["branch"],
        source_head=source["head"],
        source_worktree=source["worktree"],
        source_identity=source["identity"],
        hcomm_repo=hcomm["root"],
        hcomm_source_identity=hcomm["identity"],
        external_evidence_roots=[str(evidence)],
        created_at=now,
        updated_at=now,
        artifacts={},
        source_identity_exclusion=f"src/ops/{args.op_type}/docs/{args.task_id}",
        initial_repository_fingerprints=dict(
            hccl=source["fingerprint"], hcomm=hcomm["fingerprint"]
        ),
    )
    return index


def environment_draft(task_id, repositories, now):
    source = repositories["hccl"]
    header = dict(
        schema_version=1,
        artifact="ENVIRONMENT",
        engine="CCU",
        owner="hcclbot",
        task_id=task_id,
        status="BLOCKED",
        source_identity=source["identity"],
        checks_pass=False,
        created_at=now,
    )
    fields = "".join(
        key + ": " + json.dumps(value, ensure_ascii=False) + "\n"
        for key, value in header.items()
    )
    text = "---\n" + fields + "---\n\n"
    text += "# 环境检查草稿\n\n待 HCCLBot 按 hccl-env-check 核对 CANN、工具、库身份与实际环境后填写结论。\n\n"
    text += "以下仅为只读 Git 元数据，不是环境通过证据：\n\n```json\n"
    text += json.dumps(repositories, ensure_ascii=False, indent=2) + "\n```\n"
    return text


def write_initial_artifacts(task, evidence, index, text):
    # All input validation finishes before either destination is created.
    evidence.mkdir(parents=True, exist_ok=False)
    try:
        task.mkdir(parents=True, exist_ok=False)
    except Exception:
        evidence.rmdir()
        raise
    (task / "environment.md").write_text(text, encoding="utf-8")
    (task / "task-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def initialize(args):
    requirement, repositories, task, evidence = initialization_inputs(args)
    now = datetime.now(timezone.utc).isoformat()
    index = initial_index(args, requirement, repositories, evidence, now)
    text = environment_draft(args.task_id, repositories, now)
    # A draft cannot certify the user's environment; the normal gate rejects it.
    index["artifacts"]["ENVIRONMENT"] = dict(
        path="environment.md",
        owner="hcclbot",
        status="BLOCKED",
        source_identity=repositories["hccl"]["identity"],
        valid=False,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
    write_initial_artifacts(task, evidence, index, text)
    return dict(
        created=True,
        environment_ready=False,
        task_dir=str(task),
        evidence_root=str(evidence),
        next_action="review environment.md, then bind-environment and run the unchanged ENV_READY gate",
    )


def validate_initial_repositories(index):
    source = repository(
        index["source_repo"],
        index["source_identity"],
        index["source_identity_exclusion"],
    )
    fields = {
        "source_head": "head",
        "source_branch": "branch",
        "source_worktree": "worktree",
    }
    for key, field in fields.items():
        if index.get(key) != source.get(field):
            raise ValueError("source metadata changed since initialization")
    hcomm = repository(index["hcomm_repo"], index["hcomm_source_identity"])
    fingerprints = dict(hccl=source["fingerprint"], hcomm=hcomm["fingerprint"])
    if index["initial_repository_fingerprints"] != fingerprints:
        raise ValueError(
            "repository contents changed since initialization; recreate drafts with confirmed identities"
        )


def reviewed_environment(task, index):
    # Load local workflow code only after the bytecode write guard is installed.
    validator_type = importlib.import_module("validate_aicpu_artifacts").Validator
    gate = validator_type(task, engine="CCU")
    report = task / "environment.md"
    content = report.read_bytes()
    header = gate.parse_frontmatter(report, content.decode("utf-8"))
    if not header or gate.problems:
        raise ValueError("invalid environment frontmatter")
    expected = dict(
        schema_version=1,
        artifact="ENVIRONMENT",
        engine="CCU",
        owner="hcclbot",
        task_id=index["task_id"],
        status="PASS",
        source_identity=index["source_identity"],
        checks_pass=True,
    )
    if any(header.get(key) != value for key, value in expected.items()):
        raise ValueError(
            "environment must already be reviewed PASS, checks_pass=true, with matching owner/task/source"
        )
    return report, content


def replace_index(path, before, index):
    temporary = path.with_name("task-index.json.binding")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
        if path.read_bytes() != before:
            raise ValueError("index changed while binding")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def bind_environment(task):
    task = Path(task).resolve()
    path = task / "task-index.json"
    before = path.read_bytes()
    index = json.loads(before)
    if (
        index.get("engine") != "CCU"
        or index.get("calls")
        or index.get("current_state") != "ENV_READY"
    ):
        raise ValueError("binding is for a new CCU task before role calls only")
    if set(index.get("artifacts", {})) != {"ENVIRONMENT"}:
        raise ValueError(
            "initial binding cannot change a task with downstream artifacts"
        )
    validate_initial_repositories(index)
    report, content = reviewed_environment(task, index)
    if path.read_bytes() != before or report.read_bytes() != content:
        raise ValueError("input changed while binding")
    index["artifacts"]["ENVIRONMENT"].update(
        status="PASS", valid=True, sha256=hashlib.sha256(content).hexdigest()
    )
    index["updated_at"] = datetime.now(timezone.utc).isoformat()
    # Only bind the owner's existing conclusion; reports, calls and state stay intact.
    replace_index(path, before, index)
    return dict(
        bound=True,
        task_dir=str(task),
        next_action="run validate_ccu_artifacts.py --target-state ENV_READY",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    for flag in [
        "source-repo",
        "hcomm-repo",
        "op-type",
        "task-id",
        "requirement-file",
        "evidence-root",
    ]:
        init.add_argument("--" + flag, required=True)
    init.add_argument("--source-identity")
    init.add_argument("--hcomm-source-identity")
    bind = commands.add_parser("bind-environment")
    bind.add_argument("--task-dir", required=True)
    args = parser.parse_args()
    try:
        result = (
            initialize(args)
            if args.command == "init"
            else bind_environment(args.task_dir)
        )
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
    ) as exc:
        CLI.emit_json(dict(ok=False, error=str(exc)))
        return 1
    CLI.emit_json(result, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
