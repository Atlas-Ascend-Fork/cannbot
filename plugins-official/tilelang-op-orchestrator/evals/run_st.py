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
"""Run the shared ST framework against this TileLang plugin, never its old copy."""

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys


PLUGIN = Path(__file__).resolve().parent.parent
NAME = "tilelang-op-orchestrator"
DISCOVERY = """
import json
import logging
from pathlib import Path
import sys
from conftest import get_team_path, get_teams_with_evals, load_team_evals
expected = Path(sys.argv[1]).resolve()
assert get_teams_with_evals() == [expected.name], "unexpected ST targets"
actual = get_team_path(expected.name).resolve()
assert actual == expected, (actual, expected)
evals = load_team_evals(expected.name).get("evals", [])
assert [item.get("id") for item in evals] == list(range(1, 9)), "expected all 8 original evals"
logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.info("%s", json.dumps({"plugin": str(actual), "eval_ids": [item.get("id") for item in evals]}))
"""


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", type=Path, required=True,
                        help="cannbot-skills/tests/system directory")
    parser.add_argument("--output", type=Path, required=True,
                        help="new directory for isolated configuration, sandboxes and reports")
    parser.add_argument("--phase", choices=("collect", "basic", "eval", "all"), default="all")
    parser.add_argument("--model", help="configured OpenCode provider/model for text evals")
    parser.add_argument("--client", default="opencode",
                        help="OpenCode-compatible executable, e.g. opencode or cannbot")
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=1)
    parser.add_argument("--eval-id", type=int, choices=range(1, 9), action="append",
                        help="rerun selected original eval IDs (repeatable)")
    return parser.parse_args()


def revision(directory):
    git = shutil.which("git")
    if not git:
        raise ValueError("Git executable not found")
    result = subprocess.run([str(Path(git).resolve()), "-C", str(directory), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def prepare_framework(args):
    source = args.framework.expanduser().resolve()
    if not (source / "scripts" / "test_team_evals.py").is_file():
        raise ValueError("--framework must point to cannbot-skills/tests/system")
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    framework = output / "framework" / "tests" / "system"
    for directory in ("scripts", "config"):
        shutil.copytree(source / directory, framework / directory,
                        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    shutil.copy2(PLUGIN / "evals" / "st_adapter.py",
                 framework / "scripts" / "tilelang_st_adapter.py")
    skills = PLUGIN.parents[1] / "vendor" / "cannbot-skills"
    config = {
        "skill_dirs": [str(skills / "ops")],
        "skill_whitelist": [],
        "team_dirs": [str(PLUGIN.parent)],
        "team_whitelist": [NAME],
    }
    (framework / "config" / "st-test.config").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "plugin": str(PLUGIN), "plugin_revision": revision(PLUGIN),
        "evals_sha256": hashlib.sha256((PLUGIN / "evals" / "evals.json").read_bytes()).hexdigest(),
        "framework_source": str(source), "framework_revision": revision(source),
        "skills_revision": revision(skills), "model": args.model,
        "phase": args.phase, "client": args.client, "eval_ids": args.eval_id, "config": config,
    }
    (output / "inputs.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return output, framework / "scripts"


def run_command(command, scripts, output, label, env):
    logging.info("Running %s; log: %s", label, output / (label + ".log"))
    with (output / (label + ".log")).open("w", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=scripts, env=env,
                                stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise ValueError(f"{label} failed with exit {result.returncode}; see {output / (label + '.log')}")


def configure_client(client, output, env):
    executable = shutil.which(client)
    if not executable:
        raise ValueError(f"ST client not found: {client}")
    directory = output / "bin"
    directory.mkdir()
    runtime_names = ("LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH",
                     "ASCEND_HOME_PATH", "ASCEND_TOOLKIT_HOME", "ASCEND_OPP_PATH",
                     "ASCEND_AICPU_PATH", "ASCEND_AICPU_KERNEL_PATH")
    runtime = {name: env[name] for name in runtime_names if name in env}
    launcher = directory / "opencode"
    launcher.write_text(
        f"#!{sys.executable}\nimport os, sys\nos.environ.update({runtime!r})\n"
        f"os.execv({str(Path(executable).resolve())!r}, "
        f"[{str(Path(executable).resolve())!r}, *sys.argv[1:]])\n", encoding="utf-8")
    launcher.chmod(0o755)
    env["PATH"] = str(directory) + os.pathsep + env.get("PATH", "")


def run_pytest(phase, args, scripts, output, env):
    filename = "test_team_basic.py" if phase == "basic" else "test_team_evals.py"
    command = [sys.executable, "-m", "pytest", "-p", "tilelang_st_adapter",
               filename, "--team", NAME, "-q"]
    if phase != "basic":
        for eval_id in sorted(set(args.eval_id or [])):
            command.extend(["--eval-id", str(eval_id)])
    if phase == "collect":
        command.append("--collect-only")
    else:
        command.extend(["--json-report", "--json-report-file=" + str(output / (phase + ".json")),
                        "--junitxml=" + str(output / (phase + ".xml")),
                        "--html=" + str(output / (phase + ".html")), "--self-contained-html"])
        if args.workers > 1:
            command.extend(["-n", str(args.workers)])
    run_command(command, scripts, output, phase, env)
    if phase != "collect":
        report = json.loads((output / (phase + ".json")).read_text(encoding="utf-8"))
        expected = 20 if phase == "basic" else len(set(args.eval_id or range(1, 9)))
        summary = report.get("summary", {})
        if summary.get("passed") != expected or summary.get("total") != expected:
            raise ValueError(f"{phase}: expected {expected} passes without skips; received {summary}")


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        output, scripts = prepare_framework(args)
        env = dict(os.environ)
        env.pop("REPORT_ONLY", None)
        env["TILELANG_ST_PLUGIN"] = str(PLUGIN)
        env["TILELANG_ST_SKILLS"] = str(PLUGIN.parents[1] / "vendor" / "cannbot-skills")
        if args.model:
            env["EVAL_MODEL"] = args.model
        if args.phase in ("eval", "all"):
            configure_client(args.client, output, env)
        run_command([sys.executable, "-c", DISCOVERY, str(PLUGIN)],
                    scripts, output, "discovery", env)
        phases = ("basic", "eval") if args.phase == "all" else (args.phase,)
        for phase in phases:
            run_pytest(phase, args, scripts, output, env)
        logging.info("ST %s passed; reports: %s", args.phase, output)
    except (OSError, ValueError) as error:
        logging.error("ST failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
