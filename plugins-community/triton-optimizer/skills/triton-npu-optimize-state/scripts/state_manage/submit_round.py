# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, cast

from round.check import (
    check_round,
    cleanup_dir_pt_files,
    cleanup_workspace_triton_cache,
    is_terminal_round_directory,
    ordinary_optimize_pt_cleanup_mode,
)
from shared.managed_integrity import validate_integrity
from shared.json_io import load_json_object
from shared.cli import build_check_payload, build_workflow_failure_payload
from shared.results import build_check_result
from state_manage.state_machine import complete_round
from shared.env import read_bool_env

_MIN_SPEEDUP_ENV = "HELIX_OPTIMIZE_MIN_SPEEDUP"
_SUBMIT_ROUND_RUN_TEST_ENV = "HELIX_OPTIMIZE_SUBMIT_ROUND_RUN_TEST"


def build_parser(*, prog_name: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog_name or Path(__file__).name)
    subparsers = parser.add_subparsers(dest="command", required=True)

    round_parser = subparsers.add_parser("submit-round")
    round_parser.add_argument("--round-dir", required=True)
    round_parser.add_argument("--test-file", default=None)
    round_parser.add_argument("--current-round", type=int, default=None)
    round_parser.add_argument("--final-round", type=int, default=None)
    round_parser.add_argument(
        "--optimize-target",
        choices=("kernel", "operator"),
        default=None,
    )
    return parser


def _resolve_min_speedup() -> float | None:
    raw_env = os.environ.get(_MIN_SPEEDUP_ENV)
    if raw_env is not None:
        text = raw_env.strip()
        if not text:
            raise ValueError(f"{_MIN_SPEEDUP_ENV} is set but empty")
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"{_MIN_SPEEDUP_ENV} must be a float, got {raw_env!r}") from exc
        if value <= 0:
            raise ValueError(f"{_MIN_SPEEDUP_ENV} must be greater than 0")
        return value
    return None


def _resolve_submit_round_run_test() -> bool:
    return read_bool_env(_SUBMIT_ROUND_RUN_TEST_ENV)


def _baseline_integrity_issue(state: dict[str, Any]) -> str | None:
    message = (
        "managed baseline integrity is missing; restart or resume optimize "
        "before enabling submit-round correctness rechecks"
    )
    baseline = state.get("baseline")
    if not isinstance(baseline, dict):
        return message
    if not isinstance(cast(dict[str, Any], baseline).get("integrity"), dict):
        return message
    return None


def _recheck_command(
    execution: dict[str, Any], integrity: dict[str, Any], round_dir: Path
) -> list[str]:
    test_file = Path(str(integrity["test_file"]))
    candidate = _resolve_round_operator_for_gate(round_dir)
    command = [
        sys.executable,
        str(_run_eval_cli_path()),
        "run-test-optimize",
        "--test-file",
        str(test_file),
        "--operator-file",
        str(candidate),
    ]
    remote = execution.get("remote")
    remote_workdir = execution.get("remote_workdir")
    _validate_execution_value(remote, "remote")
    _validate_execution_value(remote_workdir, "remote_workdir")
    if remote is not None:
        command.extend(["--remote", str(remote)])
        if remote_workdir is not None:
            command.extend(["--remote-workdir", str(remote_workdir)])
    return command


def _recheck_outcome(completed: subprocess.CompletedProcess[str], execution: dict[str, Any]) -> tuple[bool, str]:
    target = "remote " + str(execution.get("remote")) if execution.get("remote") else "local"
    if completed.returncode == 0:
        return True, f"submit-round correctness recheck passed ({target})"
    detail = (completed.stderr or completed.stdout).strip().splitlines()
    summary = "\n".join(detail[-3:]) if detail else f"run-test-optimize returned {completed.returncode}"
    return False, f"submit-round correctness recheck failed ({target}): {summary}"


def _run_submit_round_correctness(round_dir: Path) -> tuple[bool, str]:
    workflow_state_path = round_dir.parent / ".helix" / "state.json"
    if not workflow_state_path.is_file():
        return False, "managed optimize workflow state is missing; restart optimize to rebuild it"
    try:
        state = load_json_object(workflow_state_path, display_name=".helix/state.json")
        baseline_issue = _baseline_integrity_issue(state)
        if baseline_issue is not None:
            return False, baseline_issue
        integrity = validate_integrity(workflow_state_path)
        execution = state.get("execution")
        if execution is None:
            execution = {"remote": None, "remote_workdir": None}
        if not isinstance(execution, dict):
            return False, "workflow state execution context must be an object"
        execution = cast(dict[str, Any], execution)
        command = _recheck_command(execution, integrity, round_dir)
        completed = subprocess.run(
            command,
            cwd=str(round_dir.parent),
            check=False,
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError, KeyError) as exc:
        return False, f"unable to execute submit-round correctness recheck: {exc}"
    return _recheck_outcome(completed, execution)


def _validate_execution_value(value: object, name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow state execution.{name} must be a non-empty string or null")
    if value.lstrip().startswith("-"):
        raise ValueError(f"workflow state execution.{name} must not start with '-'")


def _resolve_round_operator_for_gate(round_dir: Path) -> Path:
    from round.check import resolve_round_operator_file

    operator = resolve_round_operator_file(round_dir)
    if operator is None:
        raise ValueError(f"missing canonical round operator in {round_dir}")
    return operator.resolve()


def _run_eval_cli_path() -> Path:
    optimize_state_skill_dir = Path(__file__).resolve().parents[2]
    return optimize_state_skill_dir.parent / "triton-npu-run-eval" / "scripts" / "cli.py"


def _workflow_failure_guideline(message: str) -> str:
    if (
        "workflow state is not available" in message
        or ".helix/state.json" in message
    ):
        return (
            "Optimize workflow state is unavailable. Use the staged "
            "`triton-npu-optimize-state` skill's `submit-baseline` subcommand to repair "
            "session state, then reopen this `opt-round-N/` with `start-round` before "
            "retrying `submit-round`."
        )
    if (
        "workflow phase is awaiting_round_start" in message
        or "current_round=None" in message
        or "missing workflow state entry" in message
    ):
        return (
            "This round has not been formally started yet. Use the staged "
            "`triton-npu-optimize-state` skill's `start-round` subcommand for this "
            "`opt-round-N/` before running `submit-round`."
        )
    if "cannot complete non-active round" in message or "workflow state current_round=" in message:
        return (
            "The requested round is not the active workflow round. Finish the active round, or "
            "use `triton-npu-optimize-state` `start-round` to open the intended round "
            "before submitting it."
        )
    if "workflow state" in message:
        return (
            "The temporary optimize workflow state is invalid. Stop this attempt and restart "
            "the optimize session so the runner-managed workflow state is rebuilt cleanly."
        )
    return (
        "Round validation passed, but workflow-state completion failed. Repair the optimize "
        "session before continuing."
    )


def _cleanup_submitted_round_pt_files(round_dir: Path) -> None:
    """Delete round PT artifacts after submission validation and before state advancement."""
    if ordinary_optimize_pt_cleanup_mode() != "never":
        cleanup_dir_pt_files(round_dir)


def _cleanup_submitted_round_triton_cache(round_dir: Path) -> None:
    cleanup_workspace_triton_cache(round_dir.parent)


def _missing_round_directory_payload(round_dir: Path) -> dict[str, object]:
    result = build_check_result(
        kind="round",
        status="fail",
        issues=(f"missing round directory: {round_dir.name}",),
        summary=(
            f"round check requires fixes: missing round directory: {round_dir.name}. "
            "Create or reopen the expected `opt-round-N/` directory before submitting the round."
        ),
    )
    return build_check_payload(result)


def _emit_workflow_failure(exc: Exception) -> int:
    return _emit_workflow_failure_message(str(exc))


def _emit_workflow_failure_message(message: str) -> int:
    print(
        json.dumps(
            build_workflow_failure_payload(
                kind="round",
                issue=message,
                guideline=_workflow_failure_guideline(message),
            ),
            ensure_ascii=True,
        )
    )
    return 1


def _emit_config_failure(message: str) -> int:
    print(
        json.dumps(
            build_workflow_failure_payload(
                kind="round",
                issue=message,
                guideline=(
                    "The submit-round configuration is invalid. Correct the reported "
                    "environment setting before retrying."
                ),
            ),
            ensure_ascii=True,
        )
    )
    return 1


def _finalize_passed_round(
    round_dir: Path,
    args: argparse.Namespace,
    result: object,
    state_path: Path,
    run_submit_round_test: bool,
) -> int:
    if run_submit_round_test:
        gate_passed, gate_message = _run_submit_round_correctness(round_dir)
        if not gate_passed:
            failed_result = build_check_result(
                kind="round",
                status="fail",
                issues=(gate_message,),
                summary=gate_message,
            )
            print(json.dumps(build_check_payload(failed_result), ensure_ascii=True))
            return 1
        result = build_check_result(
            kind="round",
            status="pass",
            issues=(*result.issues, gate_message),
            summary=result.summary,
            next_option=result.next_option,
        )
    _cleanup_submitted_round_pt_files(round_dir)
    _cleanup_submitted_round_triton_cache(round_dir)
    if not state_path.exists():
        return _emit_workflow_failure_message("optimize workflow state is not available")
    try:
        complete_round(
            state_path,
            round_dir.name,
            current_round_arg=args.current_round,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _emit_workflow_failure(exc)
    print(json.dumps(build_check_payload(result), ensure_ascii=True))
    return 0


def _finalize_failed_round(
    round_dir: Path,
    args: argparse.Namespace,
    result: object,
    state_path: Path,
) -> int:
    if (
        state_path.exists()
        and is_terminal_round_directory(round_dir)
        and not _has_triton_api_check_failure(result.issues)
    ):
        try:
            _cleanup_submitted_round_pt_files(round_dir)
            _cleanup_submitted_round_triton_cache(round_dir)
            complete_round(
                state_path,
                round_dir.name,
                current_round_arg=args.current_round,
                final_status="failed",
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            return _emit_workflow_failure(exc)
        payload = build_check_payload(result)
        payload["guideline"] = _terminal_failure_guideline(
            round_name=round_dir.name,
            current_round=args.current_round,
            final_round=args.final_round,
        )
        if (
            args.current_round is not None
            and args.final_round is not None
            and args.current_round < args.final_round
        ):
            payload["next_option"] = f"opt-round-{args.current_round + 1}"
        print(json.dumps(payload, ensure_ascii=True))
        return 1

    print(json.dumps(build_check_payload(result), ensure_ascii=True))
    return 1


def main(argv: list[str] | None = None, *, prog_name: str | None = None) -> int:
    parser = build_parser(prog_name=prog_name)
    args = parser.parse_args(argv)
    round_dir = Path(args.round_dir).expanduser().resolve()
    if not round_dir.is_dir():
        print(json.dumps(_missing_round_directory_payload(round_dir), ensure_ascii=True))
        return 1
    try:
        min_speedup = _resolve_min_speedup()
        run_submit_round_test = _resolve_submit_round_run_test()
    except ValueError as exc:
        return _emit_config_failure(str(exc))

    try:
        result = check_round(
            round_dir,
            current_round=args.current_round,
            final_round=args.final_round,
            optimize_target=args.optimize_target,
            min_speedup=min_speedup,
            test_file=None if args.test_file is None else Path(args.test_file).expanduser().resolve(),
            enforce_triton_api_check=True,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        return _emit_workflow_failure(exc)
    state_path = round_dir.parent / ".helix" / "state.json"
    if result.status == "pass":
        return _finalize_passed_round(round_dir, args, result, state_path, run_submit_round_test)
    return _finalize_failed_round(round_dir, args, result, state_path)


def _has_triton_api_check_failure(issues: tuple[str, ...]) -> bool:
    return any(issue.startswith("Triton API check failed:") for issue in issues)


def _terminal_failure_guideline(
    *,
    round_name: str,
    current_round: int | None,
    final_round: int | None,
) -> str:
    """Explain that a terminal failed round no longer blocks the workflow."""
    if (
        current_round is not None
        and final_round is not None
        and current_round < final_round
    ):
        next_round = f"opt-round-{current_round + 1}"
        return (
            f"{round_name} was closed as failed after round validation. "
            f"The workflow is ready for the next round: {next_round}. "
            "Use the staged `triton-npu-optimize-state` skill's `start-round` "
            f"subcommand to open {next_round}."
        )
    if (
        current_round is not None
        and final_round is not None
        and current_round >= final_round
    ):
        return (
            f"{round_name} was closed as failed after round validation. "
            "This was the final round in the current worker batch; no further "
            "round can be opened."
        )
    return (
        f"{round_name} was closed as failed after round validation. "
        "The workflow is ready to open another round with the staged "
        "`triton-npu-optimize-state` skill's `start-round` subcommand."
    )


if __name__ == "__main__":
    raise SystemExit(main())
