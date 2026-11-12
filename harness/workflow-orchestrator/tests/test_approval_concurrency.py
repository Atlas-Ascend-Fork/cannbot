# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

"""Exercise asynchronous approval through real scheduler and fixture CLI processes."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# A local CLI fixture, not a model call. Its slow task only finishes when the
# test releases it; verifiers invoke the real verdict callback as a child process.
FIXTURE_CLI = """
import json
import os
import subprocess
import sys
import time
from pathlib import Path

agent = sys.argv[sys.argv.index("--agent") + 1]
tid, phase = agent.rsplit("-", 1)
artifacts = Path("artifacts")
artifacts.mkdir(exist_ok=True)
if phase == "verify":
    subprocess.run(
        [sys.executable, os.environ["FIXTURE_VERDICT"], "--work-dir",
         str(Path.cwd()), "--task-id", tid],
        check=True,
    )
else:
    with (artifacts / (tid + "-executions.txt")).open("a") as output:
        output.write("execute\\n")
    (artifacts / (tid + "-prompt.txt")).write_text(sys.argv[-1])
    if tid == "slow":
        (artifacts / "slow-started").touch()
        deadline = time.monotonic() + 60
        while not (artifacts / "release-slow").exists():
            if time.monotonic() >= deadline:
                raise SystemExit("test did not release slow task")
            time.sleep(0.05)
        (artifacts / "slow-finished").touch()
print(json.dumps({"fixture_agent": agent}))
"""


def node(tid, **overrides):
    result = {
        "id": tid,
        "task_type": "normal",
        "title": "Task " + tid,
        "goal": ["finish the task"],
        "approach": ["do the work"],
        "acceptance": ["true"],
        "out_of_scope": ["nothing"],
        "depends_on": [],
        "executor": tid + "-execute",
        "verifier": tid + "-verify",
        "max_retries": 0,
        "on_exhaust": "exit",
    }
    result.update(overrides)
    return result


class ConcurrentApprovalTest(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory(prefix="wo-approval-concurrent-")
        self.addCleanup(temp_dir.cleanup)
        self.work_dir = Path(temp_dir.name)
        self.artifacts = self.work_dir / "artifacts"
        self.artifacts.mkdir()
        self._launch_fixture()
        self.addCleanup(self._finish_process)
        self._wait_for(
            lambda tasks: tasks["gate"]["status"] == "awaiting_approval"
            and tasks["slow"]["status"] == "running",
            "gate waiting while independent slow task is running",
        )
        self.assertTrue((self.artifacts / "slow-started").is_file())
        self.assertEqual(self._tasks()["after"]["status"], "pending")
        # Let the scheduler finish its dispatch round before an external decision
        # arrives. Keep the slow child blocked throughout this observation.
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            self.assertIsNone(self.proc.poll(), self.log_path.read_text())
            self.assertEqual(self._tasks()["gate"]["status"], "awaiting_approval")
            self.assertEqual(self._tasks()["after"]["status"], "pending")
            time.sleep(0.05)

    def test_approve_unlocks_downstream_before_slow_task_finishes(self):
        self._decide("approve")
        self._wait_for(
            lambda tasks: tasks["after"]["status"] == "pass",
            "approved downstream must finish without releasing slow task",
        )
        self.assertEqual(self._tasks()["gate"]["status"], "pass")
        self._assert_slow_still_running()
        self._release_and_finish(0)

    def test_redo_runs_with_feedback_before_slow_task_finishes(self):
        feedback = "recheck independent approval output"
        self._decide("redo", feedback)

        def redone(tasks):
            executions = (self.artifacts / "gate-executions.txt").read_text()
            return tasks["gate"][
                "status"
            ] == "awaiting_approval" and executions.splitlines() == [
                "execute",
                "execute",
            ]

        self._wait_for(redone, "redo must rerun gate without releasing slow task")
        self.assertIn(feedback, (self.artifacts / "gate-prompt.txt").read_text())
        self._assert_slow_still_running()
        self.assertEqual(self._tasks()["after"]["status"], "pending")
        self._decide("approve")
        self._wait_for(
            lambda tasks: tasks["after"]["status"] == "pass",
            "second approval must release the redone gate",
        )
        self._assert_slow_still_running()
        self._release_and_finish(0)

    def test_fail_is_recorded_before_slow_task_finishes(self):
        self._decide("fail", "stop this branch")
        self._wait_for(
            lambda tasks: tasks["gate"]["status"] == "fail"
            and tasks["gate"].get("exhausted"),
            "terminal rejection must be harvested while slow task is running",
        )
        self._assert_slow_still_running()
        self.assertEqual(self._tasks()["after"]["status"], "pending")
        self.assertFalse((self.artifacts / "after-executions.txt").exists())
        self._release_and_finish(1)
        self.assertIn("after", self.log_path.read_text())

    def _launch_fixture(self):
        cli_dir = self.work_dir / "fixture-bin"
        cli_dir.mkdir()
        cli = cli_dir / "opencode"
        cli.write_text("#!" + sys.executable + "\n" + FIXTURE_CLI)
        cli.chmod(0o700)
        env = os.environ.copy()
        env["PATH"] = str(cli_dir) + os.pathsep + env.get("PATH", "")
        env["FIXTURE_VERDICT"] = str(SCRIPTS / "verdict_pass.py")
        workflow = self.work_dir / "workflow.yaml"
        workflow.write_text(
            yaml.safe_dump(
                {
                    "workflow": "concurrent-approval",
                    "max_parallel": 2,
                    "nodes": [
                        node("gate", require_approval=True, on_exhaust="continue"),
                        node("slow"),
                        node("after", depends_on=["gate"]),
                    ],
                },
                sort_keys=False,
            )
        )
        self.log_path = self.work_dir / "orchestrator.log"
        with self.log_path.open("w") as output:
            self.proc = subprocess.Popen(
                [
                    sys.executable,
                    str(SCRIPTS / "orchestrator.py"),
                    "--yaml",
                    str(workflow),
                    "--work-dir",
                    str(self.work_dir),
                    "--provider",
                    "opencode",
                    "--prompt",
                    "test asynchronous approvals",
                ],
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
            )

    def _tasks(self):
        path = self.work_dir / ".workflow" / "status.json"
        return json.loads(path.read_text())["tasks"]

    def _wait_for(self, predicate, description):
        deadline = time.monotonic() + 10
        tasks = {}
        while time.monotonic() < deadline:
            try:
                tasks = self._tasks()
            except (OSError, json.JSONDecodeError):
                pass
            else:
                if predicate(tasks):
                    return
            self.assertIsNone(self.proc.poll(), self.log_path.read_text())
            time.sleep(0.05)
        self.fail(description + "; last persisted tasks: " + json.dumps(tasks))

    def _decide(self, decision, comment=None):
        command = [
            sys.executable,
            str(SCRIPTS / "approve_task.py"),
            "--work-dir",
            str(self.work_dir),
            "--task-id",
            "gate",
            "--decision",
            decision,
        ]
        if comment is not None:
            command += ["--comment", comment]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def _assert_slow_still_running(self):
        self.assertEqual(self._tasks()["slow"]["status"], "running")
        self.assertFalse((self.artifacts / "slow-finished").exists())

    def _release_and_finish(self, expected_code):
        (self.artifacts / "release-slow").touch()
        result = self.proc.wait(timeout=15)
        self.assertEqual(result, expected_code, self.log_path.read_text())
        self.assertEqual(self._tasks()["slow"]["status"], "pass")

    def _finish_process(self):
        (self.artifacts / "release-slow").touch()
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
