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

"""Launch the unchanged workflow-orchestrator CLI, in tmux by default."""

import argparse
import hashlib
import logging
import os
import json
import uuid
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from assemble_workflow import load_yaml, validate_dsl_perf_tail, write_template
from workspace import load_context
from runtime_tools import prepare as prepare_runtime_tools

sys.dont_write_bytecode = True
LOGGER = logging.getLogger(__name__)
SCHEDULING_LOGGER = logging.getLogger(__name__ + ".scheduling")


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    definitions = parser.add_mutually_exclusive_group(required=True)
    definitions.add_argument(
        "--yaml", type=Path, help="path to a complete workflow YAML"
    )
    definitions.add_argument(
        "--template",
        type=Path,
        help="workflow template path relative to the plugin orchestrations/workflows directory",
    )
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--provider", required=True)
    prompts = parser.add_mutually_exclusive_group()
    prompts.add_argument(
        "--prompt", help="original task text; required by harness on first run"
    )
    prompts.add_argument(
        "--prompt-file", type=Path, help="UTF-8 task text, passed unchanged as --prompt"
    )
    parser.add_argument(
        "--harness-skill",
        type=Path,
        help="workflow-orchestrator directory; defaults to the repository harness",
    )
    parser.add_argument(
        "--env-script",
        type=Path,
        help="confirmed environment activation script; source before launch and reuse on recovery",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="stream output and return harness exit code directly",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="forward the public harness simulation flag",
    )
    return parser


def resolve_workflow(args, plugin_root=None):
    if args.template is not None:
        template_root = (plugin_root or Path(__file__).resolve().parents[1]) / "orchestrations/workflows"
        workflow = (template_root / args.template).resolve(strict=True)
        if not workflow.is_relative_to(template_root):
            raise ValueError(
                "--template must stay inside workflows; use --yaml for external files"
            )
    else:
        workflow = args.yaml.resolve(strict=True)
    if not workflow.is_file():
        raise ValueError("workflow must be a file")
    return workflow


def launch_background(command, work, tmux):
    session = "ops-direct-invoke-" + hashlib.sha256(str(work).encode()).hexdigest()[:12]
    log = work / "orchestrator.log"
    # Only process launch and output capture; retries and workflow state belong to harness.
    shell_command = (
        shlex.join(command) + " >> " + shlex.quote(str(log)) + " 2>&1; "
        'launch_exit=$?; printf "\\nexit status: %s\\n" "$launch_exit" >> '
        + shlex.quote(str(log))
        + '; exit "$launch_exit"'
    )
    result = subprocess.run(
        [tmux, "new-session", "-d", "-s", session, "-c", str(work), shell_command],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "tmux failed to start workflow")
    LOGGER.info("session: %s\nlog: %s", session, log)
    LOGGER.info(
        "Check completion with: %s", shlex.join([tmux, "has-session", "-t", session])
    )
    return 0


def with_environment(command, work, env_script):
    if env_script is not None:
        # Positional arguments keep paths and prompt text out of shell evaluation.
        command = [
            "bash",
            "-c",
            'set -e; workflow_env_script=$1; shift; workflow_launch=("$@"); '
            'set --; source "$workflow_env_script"; exec "${workflow_launch[@]}"',
            "workflow-environment",
            str(env_script),
            *command,
        ]
    # tmux may have a long-lived server with an unrelated environment. Set these
    # in the actual child command, not just in the tmux client's environment.
    return [
        "env",
        f"WORK_DIR={work}",
        f"USER_PROMPT={work / '.workflow/user_prompt.md'}",
        f"PYTHON={os.environ.get('PYTHON') or sys.executable}",
        *command,
    ]


def resolve_launch_inputs(args):
    prompt = args.prompt
    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8")
    env_script = args.env_script.resolve(strict=True) if args.env_script else None
    if env_script is not None and not env_script.is_file():
        raise ValueError("--env-script must be a file")
    tmux = None
    if not args.foreground:
        executable = shutil.which("tmux")
        if executable is None:
            raise ValueError(
                "tmux is required for background execution; use --foreground to run directly"
            )
        tmux = str(Path(executable).resolve(strict=True))
    return prompt, env_script, tmux


def resolve_harness(args, context):
    # Installed workspaces pass the dependency path from their installation record.
    harness = (
        (Path(context["skills"]["workflow-orchestrator"]) if context else args.harness_skill)
        or Path(__file__).resolve().parents[3] / "harness/workflow-orchestrator"
    )
    orchestrator = (harness / "scripts/orchestrator.py").resolve(strict=True)
    if not orchestrator.is_file():
        raise ValueError("workflow-orchestrator CLI not found; specify --harness-skill")
    return harness, orchestrator


def prepare_workflow(args, workflow, work):
    if args.template is not None:
        template = workflow
        workflow = work / f"{work.name}.yaml"
        if workflow.exists():
            raise ValueError(f"workflow already exists; resume with --yaml {workflow}")
        write_template(template, workflow)
    # Observe the final input only; never infer, restore or override a user's cap.
    definition = load_yaml(workflow)
    cap = definition.get("max_parallel") if isinstance(definition, dict) else None
    SCHEDULING_LOGGER.info(
        "scheduling: top-level max_parallel=%s; %s",
        cap if cap is not None else "not declared (harness default)",
        "independent branches are serialized" if cap == 1
        else "actual concurrency depends on dependencies and resources",
    )
    # New complete inputs must obey the same tail contract; recovery keeps frozen inputs.
    if not (work / ".workflow/status.json").exists():
        validate_dsl_perf_tail(definition)
    return workflow


def preflight_runtime_tools(workflow, work, env_script):
    tool_root = prepare_runtime_tools(workflow, work)
    if tool_root is None:
        return
    # Select the task interpreter after environment activation, without shell expansion.
    bootstrap = (
        "import os, subprocess, sys; "
        "interpreter=os.environ.get('PYTHON') or sys.executable; "
        "sys.stdout.write('tool interpreter: '+interpreter+'\\n'); sys.stdout.flush(); "
        "sys.exit(subprocess.run([interpreter, *sys.argv[1:]]).returncode)"
    )
    preflight_command = with_environment([
        sys.executable, "-c", bootstrap,
        str(tool_root / "bootstrap.py"),
        "--preflight", str(tool_root),
    ], work, env_script)
    result = subprocess.run(preflight_command, cwd=work, capture_output=True, text=True)
    launch_record = tool_root / f"launch-preflight-{uuid.uuid4().hex}.json"
    launch_record.write_text(json.dumps({
        "status": "fail" if result.returncode else "pass",
        "env_script": str(env_script) if env_script else None,
        "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
    }, ensure_ascii=False, indent=2))
    if result.returncode:
        raise ValueError(f"runtime tools preflight failed before harness launch; evidence: {launch_record}: "
                         + (result.stderr or result.stdout).strip())
    LOGGER.info("%s", result.stdout.strip())


def launch(args):
    work = args.work_dir.resolve()
    context = load_context(work) if (work / "context.json").exists() else None
    if context is None and not args.dry_run:
        raise ValueError("prepare context.json with tools/workspace.py before starting a real workflow")
    root = Path(context["plugin_root"]) if context else None
    workflow = resolve_workflow(args, root)
    harness, orchestrator = resolve_harness(args, context)
    prompt, env_script, tmux = resolve_launch_inputs(args)
    workflow = prepare_workflow(args, workflow, work)
    preflight_runtime_tools(workflow, work, env_script)
    command = [
        sys.executable,
        *([str(root / "tools/harness_entry.py"), str(harness)] if context else [str(orchestrator)]),
        "--yaml",
        str(workflow),
        "--work-dir",
        str(work),
        "--provider",
        args.provider,
    ]
    if prompt is not None:
        command += ["--prompt", prompt]
    if args.dry_run:
        command.append("--dry-run")
    command = with_environment(command, work, env_script)
    work.mkdir(parents=True, exist_ok=True)
    if args.foreground:
        return subprocess.run(command, cwd=work).returncode
    return launch_background(command, work, tmux)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    SCHEDULING_LOGGER.addHandler(logging.StreamHandler(sys.stderr))
    SCHEDULING_LOGGER.propagate = False
    parser = argument_parser()
    args = parser.parse_args()
    try:
        exit_code = launch(args)
    except (OSError, ValueError, KeyError, yaml.YAMLError) as error:
        parser.error(str(error))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
