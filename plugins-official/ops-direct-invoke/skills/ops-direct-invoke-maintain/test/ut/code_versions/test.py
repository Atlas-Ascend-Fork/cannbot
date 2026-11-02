# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------
"""Real Git integration tests; no model, network or accelerator required."""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from version_fixtures import run_code_versions
from support import run_tests


class CodeVersionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name) / "run"
        self.work.mkdir()
        self.code = self.work / "code"
        self.initial = self.call("init")["head"]

    def call(self, action, *args, ok=True):
        result = run_code_versions(self.work, action, *args)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def git(self, *args, repo=None):
        result = subprocess.run(
            [
                str(Path(shutil.which("git")).resolve()),
                "-C",
                str(repo or self.code),
                *args,
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def begin(self, node, attempt, base, *extra):
        return self.call(
            "begin",
            "--node",
            node,
            "--attempt",
            attempt,
            "--expected-head",
            base,
            "--allow",
            "operators",
            *extra,
        )

    def checkpoint(self, node, attempt, base):
        return self.call(
            "checkpoint", "--node", node, "--attempt", attempt, "--expected-head", base
        )["sha"]

    def version_check(self, node, attempt, sha, *args, ok=True):
        return self.call(
            "verify",
            "--node",
            node,
            "--attempt",
            attempt,
            "--expected-head",
            sha,
            *args,
            ok=ok,
        )

    def verify(self, node, attempt, sha, command=None, accept=True):
        result = self.version_check(
            node,
            attempt,
            sha,
            "--",
            sys.executable,
            "-c",
            command or 'print("verified")',
        )
        if accept:
            self.version_check(node, attempt, sha, "--accept", result["id"])
        return result

    def write(self, file, data, repo=None):
        path = (repo or self.code) / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())

    def change(self, node, attempt, base, file, data, repo=None):
        self.begin(node, attempt, base)
        self.write(file, data, repo)
        sha = self.checkpoint(node, attempt, base)
        self.verify(node, attempt, sha)
        return sha

    def test_roundtrip_add_delete_rename_binary_and_bundle(self):
        first = self.change("seed", "a1", self.initial, "operators/a.py", "a=1\n")
        self.begin("seed", "a2", first)
        (self.code / "operators/a.py").rename(self.code / "operators/renamed.py")
        self.write("operators/b.bin", b"\x00\xff\x01")
        second = self.checkpoint("seed", "a2", first)
        report = self.work / ".workflow/reports/original.log"
        report.parent.mkdir(parents=True)
        report.write_text("keep")
        result = self.call(
            "restore",
            "--node",
            "seed",
            "--expected-head",
            second,
            "--target",
            first,
            "--reason",
            "discard attempt",
        )
        self.assertEqual(
            self.git("rev-parse", result["sha"] + "^{tree}"),
            self.git("rev-parse", first + "^{tree}"),
        )
        self.assertTrue((self.code / "operators/a.py").exists())
        self.assertFalse((self.code / "operators/b.bin").exists())
        self.assertEqual(report.read_text(), "keep")
        bundle = self.work / "history.bundle"
        self.call("status", "--bundle", bundle)
        clone = self.work / "restored"
        self.git("clone", str(bundle), str(clone))
        self.assertEqual(self.git("rev-parse", "HEAD", repo=clone), result["sha"])
        self.assertEqual(self.git("cat-file", "-t", second, repo=clone), "commit")

    def test_failed_attempt_no_change_dirty_and_scope(self):
        self.begin("unit", "a1", self.initial)
        self.write("operators/a.py", "broken")
        sha = self.checkpoint("unit", "a1", self.initial)
        self.version_check(
            "unit",
            "a1",
            sha,
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(3)",
            ok=False,
        )
        self.begin("unit", "a2", sha)
        self.assertEqual(self.checkpoint("unit", "a2", sha), sha)
        self.begin("unit", "a3", sha)
        self.version_check(
            "unit", "a2", sha, "--", sys.executable, "-c", "pass", ok=False
        )
        self.write("outside.txt", "unowned")
        self.call(
            "checkpoint",
            "--node",
            "unit",
            "--attempt",
            "a3",
            "--expected-head",
            sha,
            ok=False,
        )
        self.call(
            "restore",
            "--node",
            "unit",
            "--expected-head",
            sha,
            "--target",
            self.initial,
            "--reason",
            "must not discard dirty state",
            ok=False,
        )
        self.assertEqual((self.code / "outside.txt").read_text(), "unowned")

    def prepare_parallel_units(self):
        units = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                node: pool.submit(
                    self.call, "init", "--node", node, "--base", self.initial
                )
                for node in ["u1", "u2"]
            }
            paths = {
                node: Path(future.result()["CODE_DIR"])
                for node, future in futures.items()
            }
        # Both editors may hold an attempt concurrently; only Git mutations serialize.
        for node in ["u1", "u2"]:
            self.begin(node, "a1", self.initial)
            self.write(
                f"operators/{node}.py", "def run(x): return x + 1\n", paths[node]
            )
        for node in ["u1", "u2"]:
            sha = self.checkpoint(node, "a1", self.initial)
            self.verify(node, "a1", sha)
            units[node] = sha
        self.assertFalse((self.code / "operators").exists())
        self.assertFalse((self.work / "code-worktrees/u1/operators/u2.py").exists())
        deps = [arg for n, s in units.items() for arg in ["--dependency", n + "=" + s]]
        return units, deps

    def check_integration_recovery(self, accepted_sha, combined, units, deps):
        self.begin("fix", "bad", accepted_sha)
        self.write("operators/u1.py", "def run(x): return x - 100\n")
        bad = self.checkpoint("fix", "bad", accepted_sha)
        self.version_check(
            "fix", "bad", bad, "--", sys.executable, "-c", combined, ok=False
        )
        restored = self.call(
            "restore",
            "--node",
            "fix",
            "--expected-head",
            bad,
            "--target",
            accepted_sha,
            "--reason",
            "failed simulated operator",
        )["sha"]
        self.begin("fix", "restored", restored)
        self.checkpoint("fix", "restored", restored)
        self.verify("fix", "restored", restored, combined)
        self.call(
            "restore",
            "--node",
            "u1",
            "--expected-head",
            units.get("u1"),
            "--target",
            self.initial,
            "--reason",
            "replace published Unit",
        )
        self.assertIn("fix", self.call("status")["stale_accepted"])
        self.call(
            "integrate",
            "--node",
            "fix",
            "--attempt",
            "merge3",
            "--expected-head",
            restored,
            "--allow",
            "operators",
            *deps,
            ok=False,
        )

    def test_parallel_dependency_integration_and_stale_evidence(self):
        units, deps = self.prepare_parallel_units()
        result = self.call(
            "integrate",
            "--node",
            "fix",
            "--attempt",
            "merge1",
            "--expected-head",
            self.initial,
            "--allow",
            "operators",
            *deps,
        )
        combined = "from operators.u1 import run as a; from operators.u2 import run as b; assert b(a(3)) == 5"
        self.verify("fix", "merge1", result["sha"], combined)
        again = self.call(
            "integrate",
            "--node",
            "fix",
            "--attempt",
            "merge2",
            "--expected-head",
            result["sha"],
            "--allow",
            "operators",
            *deps,
        )
        self.assertEqual(again["sha"], result["sha"])
        self.verify("fix", "merge2", again["sha"], combined)
        self.check_integration_recovery(again["sha"], combined, units, deps)

    def check_interrupted_dependency_edit(self, path2, merged, sha1):
        self.begin("u2", "a1", merged)
        self.write("operators/u2.py", "from operators.u1 import value\n", path2)
        # Resume does not discard an interrupted editor's changes.
        self.begin("u2", "a1", merged)
        self.git("config", "user.name", "", repo=path2)
        self.call(
            "checkpoint",
            "--node",
            "u2",
            "--attempt",
            "a1",
            "--expected-head",
            merged,
            ok=False,
        )
        self.assertEqual(self.git("rev-parse", "HEAD", repo=path2), merged)
        self.git("config", "user.name", "DSL workflow", repo=path2)
        sha2 = self.checkpoint("u2", "a1", merged)
        self.verify(
            "u2", "a1", sha2, "from operators.u2 import value; assert value == 42"
        )
        self.assertEqual(
            self.call("status", "--node", "u2")["attempts"]["u2/a1"]["dependencies"],
            {"u1": sha1},
        )

    def test_dependency_checkout_and_interrupted_edit_commit_failure(self):
        path1 = Path(
            self.call("init", "--node", "u1", "--base", self.initial)["CODE_DIR"]
        )
        sha1 = self.change(
            "u1", "a1", self.initial, "operators/u1.py", "value=42\n", path1
        )
        path2 = Path(
            self.call("init", "--node", "u2", "--base", self.initial)["CODE_DIR"]
        )
        self.call(
            "begin",
            "--node",
            "u2",
            "--attempt",
            "a1",
            "--expected-head",
            self.initial,
            "--allow",
            "operators/u2.py",
            "--dependency",
            "u1=" + sha1,
            ok=False,
        )
        merged = self.call(
            "integrate",
            "--node",
            "u2",
            "--attempt",
            "deps",
            "--expected-head",
            self.initial,
            "--allow",
            "operators/u1.py",
            "--dependency",
            "u1=" + sha1,
        )["sha"]
        self.check_interrupted_dependency_edit(path2, merged, sha1)

    def test_lock_and_ignored_obstruction_preserve_files(self):
        lock = self.work / "versioning/operation.lock"
        lock.write_text('{"pid": 0}')
        self.call("status", "--lock-timeout", "0", ok=False)
        lock.unlink()
        sha = self.change("seed", "a1", self.initial, "operators/a.py", "original")
        self.call(
            "restore",
            "--node",
            "seed",
            "--expected-head",
            sha,
            "--target",
            self.initial,
            "--reason",
            "test",
        )
        self.write("operators/a.py", "unknown")
        # Even ignored files must not be overwritten by a historical tree.
        (self.code / ".git/info/exclude").write_text("operators/a.py\n")
        current = self.git("rev-parse", "HEAD")
        self.call(
            "restore",
            "--node",
            "seed",
            "--expected-head",
            current,
            "--target",
            sha,
            "--reason",
            "block",
            ok=False,
        )
        self.assertEqual((self.code / "operators/a.py").read_text(), "unknown")

    def test_merge_conflict_resolves_without_losing_later_dependency(self):
        base = self.change(
            "seed", "a1", self.initial, "operators/shared.py", "original\n"
        )
        units = {}
        for node in ["u1", "u2", "u3"]:
            path = Path(self.call("init", "--node", node, "--base", base)["CODE_DIR"])
            file = "operators/shared.py" if node != "u3" else "operators/third.py"
            units[node] = self.change(node, "a1", base, file, node + "\n", path)
        deps = [arg for n, s in units.items() for arg in ["--dependency", n + "=" + s]]
        self.call(
            "integrate",
            "--node",
            "fix",
            "--attempt",
            "merge",
            "--expected-head",
            base,
            "--allow",
            "operators",
            *deps,
            ok=False,
        )
        self.write("operators/shared.py", "resolved\n")
        sha = self.checkpoint("fix", "merge", self.git("rev-parse", "HEAD"))
        self.assertTrue((self.code / "operators/third.py").exists())
        self.verify("fix", "merge", sha)

    def test_verification_mutation_and_explicit_recovery(self):
        self.begin("unit", "a1", self.initial)
        self.write("operators/a.py", "original")
        sha = self.checkpoint("unit", "a1", self.initial)
        result = self.version_check(
            "unit",
            "a1",
            sha,
            "--",
            sys.executable,
            "-c",
            'from pathlib import Path; Path("operators/a.py").write_text("changed")',
            ok=False,
        )
        evidence = json.loads(result.stdout)
        self.assertFalse(evidence["valid"])
        self.version_check("unit", "a1", sha, "--accept", evidence["id"], ok=False)
        saved = self.call(
            "checkpoint",
            "--node",
            "unit",
            "--attempt",
            "a1",
            "--expected-head",
            sha,
            "--recover",
        )
        self.assertNotEqual(saved["sha"], sha)
        self.verify("unit", "a1", saved["sha"])

    def test_head_drift_missing_commit_frozen_input_and_log_tampering(self):
        spec = self.work / "design/spec.yaml"
        spec.parent.mkdir()
        spec.write_text("frozen")
        self.begin("unit", "a1", self.initial)
        sha = self.checkpoint("unit", "a1", self.initial)
        evidence = self.verify("unit", "a1", sha, accept=False)
        Path(evidence["log"]).write_text("tampered")
        self.version_check("unit", "a1", sha, "--accept", evidence["id"], ok=False)
        spec.write_text("changed")
        self.version_check(
            "unit", "a1", sha, "--", sys.executable, "-c", "pass", ok=False
        )
        self.call(
            "restore",
            "--expected-head",
            sha,
            "--target",
            "0" * 40,
            "--reason",
            "missing",
            ok=False,
        )
        self.call(
            "restore",
            "--expected-head",
            "0" * 40,
            "--target",
            sha,
            "--reason",
            "drift",
            ok=False,
        )

    def test_native_runner_output_archived_and_bound_to_evidence(self):
        self.begin("unit", "a1", self.initial)
        self.write(
            "operators/add/test/test_add.py",
            "from pathlib import Path\n"
            'p=Path(__file__).parent/"testcase_output"/"tdd"/"result.csv"\n'
            "p.parent.mkdir(parents=True,exist_ok=True)\n"
            'p.write_text("case,status\\n1,passed\\n")\n',
        )
        sha = self.checkpoint("unit", "a1", self.initial)
        evidence = self.version_check(
            "unit", "a1", sha, "--", sys.executable, "operators/add/test/test_add.py"
        )
        self.assertFalse((self.code / "operators/add/test/testcase_output").exists())
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(len(evidence["artifacts"]), 1)
        self.version_check("unit", "a1", sha, "--accept", evidence["id"])
        artifact = self.work / "versioning" / next(iter(evidence["artifacts"]))
        artifact.write_text("tampered")
        self.version_check("unit", "a1", sha, "--accept", evidence["id"], ok=False)


if __name__ == "__main__":
    run_tests()
