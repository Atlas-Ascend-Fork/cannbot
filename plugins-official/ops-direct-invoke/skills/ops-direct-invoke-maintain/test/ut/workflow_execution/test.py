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
"""Check our launcher and generated input, trusting harness execution semantics."""

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).absolute().parents[1]))
from support import (
    SCRIPTS,
    WORKFLOWS,
    available_workflows,
    generate_workflow,
    load_yaml,
    run_tests,
    run_workflow,
)


class WorkflowExecutionTests(unittest.TestCase):
    def test_selected_environment_survives_launch_and_recovery(self):
        for background in (False, True):
            with (
                self.subTest(background=background),
                tempfile.TemporaryDirectory() as tmp,
            ):
                self.check_selected_environment(Path(tmp), background)

    def prepare_selected_environment(self, folder):
        harness = folder / "harness"
        (harness / "scripts").mkdir(parents=True)
        (harness / "scripts/orchestrator.py").write_text(
            "import json, os, pathlib, sys\n"
            "keys = ('WORK_DIR', 'USER_PROMPT', 'PYTHON', 'ASCEND_HOME_PATH', 'CONDA_PREFIX')\n"
            "pathlib.Path('received.json').write_text(json.dumps({\n"
            "    'env': {key: os.environ.get(key) for key in keys}, 'args': sys.argv[1:]}))\n"
            "print('fixture launch')\n"
        )
        work = folder / "work with spaces"
        work.mkdir()
        (work / "workflow.yaml").write_text("workflow: fixture\nnodes: []\n")
        selected = {
            "PYTHON": str(folder / "selected conda/bin/python"),
            "CONDA_PREFIX": str(folder / "selected conda"),
            "ASCEND_HOME_PATH": str(folder / "selected CANN"),
        }
        env_script = folder / "activate '$(false).sh"
        env_script.write_text(
            "\n".join(
                f"export {key}={shlex.quote(value)}" for key, value in selected.items()
            )
            + "\nset -- activation-internal-argument\n"
        )
        return harness, work, env_script, selected

    def check_selected_environment(self, folder, background):
        harness, work, env_script, selected = self.prepare_selected_environment(folder)
        workflow = work / "workflow.yaml"
        log = work / "orchestrator.log"
        log.write_text("previous run evidence\n")
        state = work / ".workflow" / "status.json"
        state.parent.mkdir()
        state.write_text('{"existing": "must not be changed by launcher"}\n')
        before = {p: p.read_bytes() for p in (state, workflow, env_script)}
        env = os.environ.copy()
        env.update({key: "wrong-parent-value" for key in selected})
        if background:
            tmux = folder / "tmux"
            tmux.write_text(
                f"#!{sys.executable}\n"
                "import os, subprocess, sys\n"
                "assert sys.argv[1] == 'new-session'\n"
                # Simulate an existing server that did not inherit the client environment.
                "env = os.environ.copy()\n"
                "for key in ('WORK_DIR', 'USER_PROMPT', 'PYTHON', 'ASCEND_HOME_PATH', 'CONDA_PREFIX'):\n"
                "    env.pop(key, None)\n"
                "subprocess.run(sys.argv[-1], shell=True, env=env,\n"
                "               cwd=sys.argv[sys.argv.index('-c') + 1], check=True)\n"
            )
            tmux.chmod(0o755)
            env["PATH"] = str(folder) + os.pathsep + env.get("PATH", "")
        command = [
            sys.executable,
            str(SCRIPTS / "run_workflow.py"),
            "--yaml",
            str(workflow),
            "--work-dir",
            str(work),
            "--provider",
            "fixture-provider",
            "--harness-skill",
            str(harness),
            "--env-script",
            str(env_script),
        ]
        if not background:
            command.append("--foreground")
        self.check_launch_and_recovery(command, env, work, selected, before)
        self.assertTrue(log.read_text().startswith("previous run evidence\n"))
        if background:
            self.assertEqual(log.read_text().count("fixture launch"), 2)
            self.assertEqual(log.read_text().count("exit status: 0"), 2)

    def check_launch_and_recovery(self, command, env, work, selected, before):
        # The recovery invocation omits prompt and retains all existing inputs and state.
        prompt = '需求 "quoted" $WORK_DIR $(false) `false`\nsecond line'
        for extra in (["--prompt", prompt], []):
            result = subprocess.run(
                command + extra,
                cwd=work.parent,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            received = json.loads((work / "received.json").read_text())
            self.assertEqual(
                received["env"],
                {
                    **selected,
                    "WORK_DIR": str(work),
                    "USER_PROMPT": str(work / ".workflow/user_prompt.md"),
                },
            )
            self.assertEqual(
                received["args"],
                [
                    "--yaml",
                    str(work / "workflow.yaml"),
                    "--work-dir",
                    str(work),
                    "--provider",
                    "fixture-provider",
                    *extra,
                ],
            )
            for path, content in before.items():
                self.assertEqual(path.read_bytes(), content)

    def test_environment_activation_failure_does_not_launch_harness(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            harness = folder / "harness"
            (harness / "scripts").mkdir(parents=True)
            marker = folder / "unexpected-launch"
            (harness / "scripts/orchestrator.py").write_text(
                f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
            )
            workflow = folder / "workflow.yaml"
            workflow.write_text("workflow: fixture\nnodes: []\n")
            env_script = folder / "activate.sh"
            env_script.write_text("false\nexport PYTHON=should-not-continue\n")
            command = [
                sys.executable,
                str(SCRIPTS / "run_workflow.py"),
                "--yaml",
                str(workflow),
                "--work-dir",
                str(folder / "run"),
                "--provider",
                "fixture-provider",
                "--harness-skill",
                str(harness),
                "--foreground",
                "--env-script",
            ]
            for path in (env_script, folder / "missing.sh", folder):
                with self.subTest(path=path):
                    result = subprocess.run(
                        command + [str(path)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(marker.exists())

    def test_every_template_assembles_and_runs_through_public_cli(self):
        for entry in available_workflows():
            with self.subTest(template=entry["file"]):
                self.check_template(entry)

    def check_template(self, entry):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = WORKFLOWS / entry["file"]
            sources = {source: source.read_bytes()}
            for node in load_yaml(source)["nodes"]:
                if "yaml" in node:
                    task = source.parent / node["yaml"]
                    sources[task] = task.read_bytes()
            generated = generate_workflow(self, entry, folder)
            definition = load_yaml(generated)
            self.assertEqual(len(definition["nodes"]), len(load_yaml(source)["nodes"]))
            self.assertNotIn("use_when", definition)
            for node in definition["nodes"]:
                self.assertNotIn("yaml", node)
                self.assertNotIn("variables", node)
            before = generated.read_bytes()
            run_workflow(self, "--yaml", generated, folder / "run")
            self.assertEqual(generated.read_bytes(), before)
            for path, content in sources.items():
                self.assertEqual(path.read_bytes(), content)

    def test_launcher_passes_arguments_and_preserves_existing_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            harness = folder / "harness with spaces"
            (harness / "scripts").mkdir(parents=True)
            (harness / "scripts/orchestrator.py").write_text(
                "import json, pathlib, sys\n"
                'pathlib.Path("received.json").write_text(json.dumps(sys.argv[1:]))\n'
                "sys.exit(7)\n"
            )
            work = folder / "workflow1"
            prompt = folder / "prompt.txt"
            prompt.write_text(
                '原始需求\n"quoted" $WORK_DIR $(false) `false`', encoding="utf-8"
            )
            template = available_workflows()[0]["file"]
            command = [
                sys.executable,
                str(SCRIPTS / "run_workflow.py"),
                "--work-dir",
                str(work),
                "--provider",
                "fixture-provider",
                "--harness-skill",
                str(harness),
                "--foreground",
                "--dry-run",
                "--prompt-file",
                str(prompt),
            ]
            result = subprocess.run(
                command + ["--template", template],
                cwd=folder,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 7, result.stderr)
            generated = work / "workflow1.yaml"
            before = generated.read_bytes()
            self.assertEqual(
                json.loads((work / "received.json").read_text()),
                [
                    "--yaml",
                    str(generated),
                    "--work-dir",
                    str(work),
                    "--provider",
                    "fixture-provider",
                    "--prompt",
                    prompt.read_text(encoding="utf-8"),
                    "--dry-run",
                ],
            )
            result = subprocess.run(
                command + ["--template", template],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("resume with --yaml", result.stderr)
            result = subprocess.run(
                command + ["--yaml", str(generated)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 7, result.stderr)
            self.assertEqual(generated.read_bytes(), before)


if __name__ == "__main__":
    run_tests()
