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
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from assemble_workflow import assemble_template, write_workflow

LOGGER = logging.getLogger(__name__)


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    definitions = parser.add_mutually_exclusive_group(required=True)
    definitions.add_argument(
        "--yaml", type=Path, help="path to a complete workflow YAML"
    )
    definitions.add_argument(
        "--template",
        type=Path,
        help="workflow template path relative to this Skill workflows directory",
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
        help="workflow-orchestrator directory; defaults to installed sibling Skill",
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


def resolve_workflow(args):
    if args.template is not None:
        template_root = (Path(__file__).absolute().parents[1] / "workflows").resolve()
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
        *command,
    ]


def launch(args):
    workflow = resolve_workflow(args)
    # Keep the invocation path before resolving: source installations use Skill symlinks.
    harness = (
        args.harness_skill
        or Path(__file__).absolute().parents[2] / "workflow-orchestrator"
    )
    orchestrator = (harness / "scripts/orchestrator.py").resolve(strict=True)
    if not orchestrator.is_file():
        raise ValueError("workflow-orchestrator CLI not found; specify --harness-skill")
    definition = assemble_template(workflow) if args.template is not None else None
    prompt = args.prompt
    if args.prompt_file:
        prompt = args.prompt_file.read_text(encoding="utf-8")
    work = args.work_dir.resolve()
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
    if definition is not None:
        workflow = work / f"{work.name}.yaml"
        if workflow.exists():
            raise ValueError(f"workflow already exists; resume with --yaml {workflow}")
        write_workflow(definition, workflow)
    command = [
        sys.executable,
        str(orchestrator),
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
    parser = argument_parser()
    args = parser.parse_args()
    try:
        exit_code = launch(args)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.error(str(error))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
