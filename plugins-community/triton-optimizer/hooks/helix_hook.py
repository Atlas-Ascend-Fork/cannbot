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

"""Self-contained PreToolUse guard used by Codex, Claude, and TraeCLI hooks."""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any, cast

STRICT_AGENT_HOOK_ENV = "HELIX_STRICT_AGENT_HOOK"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"", "0", "false", "no", "off"})


def strict_agent_hook_enabled() -> bool:
    raw_value = os.environ.get(STRICT_AGENT_HOOK_ENV)
    if raw_value is None:
        return False
    normalized = raw_value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return False


READ_COMMANDS = {
    "cat",
    "head",
    "less",
    "ls",
    "more",
    "stat",
    "tail",
    "tree",
}
AMBIGUOUS_SHELL_CHARACTERS = frozenset({";", "\n", "|", "&", "<", ">", "(", ")", "#", "`"})

EDIT_TOOLS = {"Edit", "MultiEdit", "Write"}
# Codex native file edits (PreToolUse tool_name + streamed item type).
FILE_CHANGE_TOOL = "file_change"
READ_TOOLS = {"Read", "Grep", "Glob", "LS"}
READ_TOOL_PATH_KEYS = ("file_path", "path", "filePath", "directory_path", "directoryPath")
EDIT_TOOL_PATH_KEYS = ("file_path", "path", "filePath", "notebook_path", "notebookPath")
SHELL_WRAPPER_FLAGS = {"-c", "-lc"}
SHELL_WRAPPERS = {"bash", "sh", "zsh"}
WORKFLOW_STATE_RELATIVE_PATH = Path(".helix") / "state.json"
ROUND_ACTIVE_ALLOWED_TOP_LEVEL_FILES = frozenset(
    {
        "opt-note.md",
        "learned_lessons.md",
        "supervisor-report.md",
    }
)


class PathAccessContext:
    __slots__ = (
        "workspace_root",
        "cwd",
        "extra_read_roots",
        "deny_read_globs",
        "deny_edit_globs",
        "strict_deny_read_globs",
        "strict_deny_edit_globs",
        "deny_message",
        "strict",
    )

    def __init__(
        self,
        *,
        workspace_root: Path,
        cwd: Path,
        extra_read_roots: tuple[Path, ...],
        deny_read_globs: tuple[str, ...],
        deny_edit_globs: tuple[str, ...],
        strict_deny_read_globs: tuple[str, ...],
        strict_deny_edit_globs: tuple[str, ...],
        deny_message: str,
        strict: bool,
    ) -> None:
        self.workspace_root = workspace_root
        self.cwd = cwd
        self.extra_read_roots = extra_read_roots
        self.deny_read_globs = deny_read_globs
        self.deny_edit_globs = deny_edit_globs
        self.strict_deny_read_globs = strict_deny_read_globs
        self.strict_deny_edit_globs = strict_deny_edit_globs
        self.deny_message = deny_message
        self.strict = strict


def deny_reason_for_tool_use(policy: dict[str, Any], payload: dict[str, Any]) -> str | None:
    if policy.get("enabled") is not True:
        return None
    strict = strict_agent_hook_enabled()

    tool_name = payload.get("tool_name")
    raw_tool_input = payload.get("tool_input")
    if not isinstance(raw_tool_input, dict):
        return None
    tool_input = cast(dict[str, Any], raw_tool_input)

    context = _build_path_access_context(policy, payload, tool_input, strict=strict)
    if context is None:
        return None

    if tool_name in EDIT_TOOLS:
        path_text = _first_path_text(tool_input, EDIT_TOOL_PATH_KEYS)
        if path_text is None:
            return None
        return _deny_reason_for_built_in_edit_path(path_text, context)

    if tool_name == FILE_CHANGE_TOOL:
        return _deny_reason_for_file_change(tool_input, context)

    if tool_name in READ_TOOLS:
        path_text = _first_path_text(tool_input, READ_TOOL_PATH_KEYS)
        if path_text is None:
            return None
        return _deny_reason_for_path_access(path_text, context)

    if tool_name not in {"Bash", "RunCommand"}:
        return None

    command = tool_input.get("command")
    if not isinstance(command, str):
        return None
    return _deny_reason_for_bash_command(command, context)


def _build_path_access_context(
    policy: dict[str, Any],
    payload: dict[str, Any],
    tool_input: dict[str, Any],
    *,
    strict: bool,
) -> PathAccessContext | None:
    workspace_root = _resolve_policy_path(policy.get("workspace_root"))
    if workspace_root is None:
        workspace_root = _resolve_cwd(tool_input.get("cwd") or payload.get("cwd"), Path.cwd())

    cwd = _resolve_cwd(tool_input.get("cwd") or payload.get("cwd"), workspace_root)
    extra_read_roots = tuple(_extra_read_roots(policy))
    deny_read_globs = tuple(_string_list(policy, "deny_read_globs"))
    strict_deny_read_globs = tuple(_string_list(policy, "strict_deny_read_globs"))
    strict_deny_edit_globs = tuple(_string_list(policy, "strict_deny_edit_globs"))
    deny_edit_globs = tuple(_string_list(policy, "deny_edit_globs"))
    deny_message = str(policy.get("deny_message") or "This read is blocked by workspace policy.")
    return PathAccessContext(
        workspace_root=workspace_root,
        cwd=cwd,
        extra_read_roots=extra_read_roots,
        deny_read_globs=deny_read_globs,
        deny_edit_globs=deny_edit_globs,
        strict_deny_read_globs=strict_deny_read_globs,
        strict_deny_edit_globs=strict_deny_edit_globs,
        deny_message=deny_message,
        strict=strict,
    )


def _deny_reason_for_file_change(
    tool_input: dict[str, Any],
    context: PathAccessContext,
) -> str | None:
    """Apply built-in edit policy to every path in a Codex file_change batch."""
    for path_text in _file_change_paths(tool_input):
        reason = _deny_reason_for_built_in_edit_path(path_text, context)
        if reason is not None:
            return reason
    return None


def _file_change_paths(tool_input: dict[str, Any]) -> list[str]:
    raw_changes = tool_input.get("changes")
    if not isinstance(raw_changes, list):
        return []
    paths: list[str] = []
    for entry in raw_changes:
        if not isinstance(entry, dict):
            continue
        path_text = entry.get("path")
        if isinstance(path_text, str) and path_text.strip():
            paths.append(path_text)
    return paths


def _deny_reason_for_bash_command(
    command: str,
    context: PathAccessContext,
) -> str | None:
    if _starts_with_helix_command(command):
        return _helix_command_denial()
    for path_text in _collect_command_path_references(command):
        reason = _deny_reason_for_path_access(path_text, context)
        if reason is not None:
            return reason
    return None


def _starts_with_helix_command(command: str) -> bool:
    tokens = _split_command(command)
    return bool(tokens and Path(tokens[0]).name == "helix")


def _flush_segment(segments: list[str], current: list[str]) -> list[str]:
    segment = "".join(current).strip()
    if segment:
        segments.append(segment)
    return []


def _shell_command_segments(command: str) -> list[str]:
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    in_comment = False
    for char in command:
        if in_comment:
            if char == "\n":
                in_comment = False
                current = _flush_segment(segments, current)
            continue
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            current.append(char)
            escaped = True
            continue
        if quote is not None:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            current.append(char)
            quote = char
            continue
        if char == "#" and (not current or current[-1].isspace()):
            in_comment = True
            continue
        if char in {";", "\n", "|", "&"}:
            current = _flush_segment(segments, current)
            continue
        current.append(char)
    if quote is not None or escaped:
        return []
    _flush_segment(segments, current)
    return segments


def _helix_command_denial() -> str:
    return (
        "Direct Helix CLI invocation is blocked by Helix agent-hook policy. "
        "Use the staged triton-npu-run-eval skill CLI so managed workflow evidence is recorded."
    )


def _deny_reason_for_path_access(
    path_text: str,
    context: PathAccessContext,
) -> str | None:
    resolved_path = _resolve_path_text(path_text, context.cwd, context.workspace_root)
    if resolved_path is None:
        return None
    if _matches_any_glob(resolved_path, list(context.deny_read_globs)):
        return context.deny_message
    if not context.strict:
        return None
    if not _is_under_any_root(resolved_path, [context.workspace_root, *context.extra_read_roots]):
        return context.deny_message
    if _matches_any_glob(resolved_path, list(context.strict_deny_read_globs)):
        return context.deny_message
    return None


def _deny_reason_for_built_in_edit_path(path_text: str, context: PathAccessContext) -> str | None:
    resolved_path = _resolve_path_text(path_text, context.cwd, context.workspace_root)
    if resolved_path is None:
        return None
    inside_workspace = _is_relative_to(resolved_path, context.workspace_root)
    workspace_relative_path = (
        resolved_path.relative_to(context.workspace_root).as_posix()
        if inside_workspace
        else None
    )
    if workspace_relative_path is not None and _is_protected_runtime_edit_path(workspace_relative_path):
        return _protected_runtime_edit_denial(workspace_relative_path)
    if _matches_any_glob(resolved_path, list(context.deny_edit_globs)):
        return _protected_runtime_edit_denial_for_external_path(resolved_path)

    workflow_state = _workflow_state_or_none(context.workspace_root)
    if workflow_state is not None:
        phase_reason = _workflow_phase_edit_denial(
            workflow_state,
            workspace_relative_path,
        )
        if phase_reason is not None:
            return phase_reason

    if not context.strict:
        return None
    if not inside_workspace:
        return _built_in_edit_outside_workspace_denial()
    if _matches_any_glob(resolved_path, list(context.strict_deny_edit_globs)):
        return _strict_skill_script_edit_denial(workspace_relative_path or path_text)
    return None


def _workflow_phase_edit_denial(
    workflow_state: dict[str, Any],
    workspace_relative_path: str | None,
) -> str | None:
    phase = _require_state_string(workflow_state, "phase")
    if phase == "baseline":
        return None
    if phase == "awaiting_round_start":
        return _awaiting_round_start_built_in_edit_denial()
    if phase == "deep_analysis":
        return _deep_analysis_built_in_edit_denial()
    if phase == "round_active":
        active_round_dir = _active_round_dir(workflow_state)
        if active_round_dir is None:
            return _built_in_edit_missing_state_denial()
        if (
            workspace_relative_path is not None
            and _is_allowed_round_active_edit_path(workspace_relative_path, active_round_dir)
        ):
            if _is_active_round_operator_edit_path(
                workflow_state,
                workspace_relative_path,
                active_round_dir,
            ):
                return _operator_edit_claim_denial_reason(
                    workflow_state,
                    workspace_relative_path=workspace_relative_path,
                )
            return None
        return _round_active_built_in_edit_denial(active_round_dir)
    return _built_in_edit_missing_state_denial()


def _workflow_state_or_none(workspace_root: Path) -> dict[str, Any] | None:
    state_path = workspace_root / WORKFLOW_STATE_RELATIVE_PATH
    try:
        state = _load_json(state_path)
        _require_state_string(state, "phase")
    except (FileNotFoundError, ValueError, TypeError):
        return None
    return state


def _require_state_string(state: dict[str, Any], key: str) -> str:
    value = state.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"workflow state {key} must be a non-empty string")
    return value


def _active_round_dir(state: dict[str, Any]) -> str | None:
    round_entry = _active_round_entry(state)
    if round_entry is None:
        return None
    round_dir = round_entry.get("round_dir")
    if not isinstance(round_dir, str) or not round_dir:
        return None
    return round_dir


def _active_round_entry(state: dict[str, Any]) -> dict[str, Any] | None:
    current_round = state.get("current_round")
    raw_rounds = state.get("rounds")
    if not isinstance(current_round, int) or not isinstance(raw_rounds, dict):
        return None
    rounds = cast(dict[str, Any], raw_rounds)
    round_entry = rounds.get(str(current_round))
    if not isinstance(round_entry, dict):
        return None
    round_entry_dict = cast(dict[str, Any], round_entry)
    status = round_entry_dict.get("status")
    if status != "active":
        return None
    return round_entry_dict


def _is_active_round_operator_edit_path(
    state: dict[str, Any],
    workspace_relative_path: str,
    active_round_dir: str,
) -> bool:
    round_entry = _active_round_entry(state)
    if round_entry is None:
        return False
    operator_path = round_entry.get("operator_path")
    if isinstance(operator_path, str) and operator_path:
        return workspace_relative_path == operator_path
    relative_to_round = workspace_relative_path.removeprefix(f"{active_round_dir}/")
    return (
        workspace_relative_path.startswith(f"{active_round_dir}/")
        and "/" not in relative_to_round
        and workspace_relative_path.lower().endswith(".py")
    )


def _operator_edit_claim_denial_reason(
    state: dict[str, Any],
    *,
    workspace_relative_path: str,
) -> str | None:
    round_entry = _active_round_entry(state)
    if round_entry is None:
        return _built_in_edit_missing_state_denial()
    strategy_state = round_entry.get("strategy_state")
    if (
        isinstance(strategy_state, dict)
        and cast(dict[str, Any], strategy_state).get("round_strategy") == "plateau_review"
    ):
        return _plateau_review_operator_edit_denial(workspace_relative_path)
    raw_claim = round_entry.get("edit_claim")
    if not isinstance(raw_claim, dict):
        return _operator_edit_reason_required_denial(workspace_relative_path)
    claim = cast(dict[str, Any], raw_claim)
    if claim.get("enabled") is not True:
        return None
    if claim.get("active") is not True:
        return _operator_edit_reason_required_denial(workspace_relative_path)
    return None


def _is_protected_runtime_edit_path(workspace_relative_path: str) -> bool:
    if workspace_relative_path == ".helix" or workspace_relative_path.startswith(".helix/"):
        return True
    if workspace_relative_path == "helix-logs" or workspace_relative_path.startswith("helix-logs/"):
        return True
    if workspace_relative_path == ".codex/hooks.json":
        return True
    if workspace_relative_path == ".codex/helix-hooks" or workspace_relative_path.startswith(".codex/helix-hooks/"):
        return True
    if workspace_relative_path == ".claude/helix-hooks" or workspace_relative_path.startswith(".claude/helix-hooks/"):
        return True
    if workspace_relative_path == ".opencode/helix-hooks" or workspace_relative_path.startswith(
        ".opencode/helix-hooks/"
    ):
        return True
    if workspace_relative_path in {".opencode/plugins/helix-hook.js", ".opencode/plugins/agent-hook.mjs"}:
        return True
    if workspace_relative_path == ".pi/helix-hooks" or workspace_relative_path.startswith(".pi/helix-hooks/"):
        return True
    if workspace_relative_path == ".helix-dsh" or workspace_relative_path.startswith(".helix-dsh/"):
        return True
    if workspace_relative_path == ".trae/cli/hooks.json":
        return True
    if workspace_relative_path == ".trae/cli/helix-hooks" or workspace_relative_path.startswith(
        ".trae/cli/helix-hooks/"
    ):
        return True
    return False


def _is_allowed_round_active_edit_path(workspace_relative_path: str, active_round_dir: str) -> bool:
    if workspace_relative_path == active_round_dir or workspace_relative_path.startswith(f"{active_round_dir}/"):
        return True
    if "/" not in workspace_relative_path and workspace_relative_path in ROUND_ACTIVE_ALLOWED_TOP_LEVEL_FILES:
        return True
    return False


def _built_in_edit_missing_state_denial() -> str:
    return (
        "Built-in edit tool blocked by optimize workflow policy. "
        "The temporary optimize workflow state is missing or invalid. "
        "Ask the runner to restart the optimize session so workflow state can be rebuilt."
    )


def _operator_edit_reason_required_denial(target_path: str) -> str:
    return (
        "Built-in operator edit blocked because no active edit claim exists for this round. "
        "Run `triton-npu-optimize-state claim-edit --target "
        f"{target_path} "
        "--source pattern --pattern-path <pattern>.md --reason \"<why>\"` "
        "(or `--source self-directed` when no skill file was used), then retry the operator edit."
    )


def _plateau_review_operator_edit_denial(target_path: str) -> str:
    return (
        "Built-in operator edit blocked while this round is in plateau review. "
        "Reassess the complete selected optimization scope and applicable structural "
        "patterns, then run `triton-npu-optimize-state set-current-round-state "
        "--round-strategy structural_change --reason \"...\"` for a broader redesign or "
        "use `--round-strategy focused_tuning` when the new evidence shows that focused "
        f"work can plausibly close the remaining target gap. Then retry editing `{target_path}`."
    )


def _built_in_edit_outside_workspace_denial() -> str:
    return (
        "Built-in edit tool blocked by optimize workflow policy. "
        "Keep built-in edits inside the current optimize workspace."
    )


def _protected_runtime_edit_denial(workspace_relative_path: str) -> str:
    return (
        "Built-in edit tool blocked by optimize workflow policy. "
        f"`{workspace_relative_path}` is a protected internal runtime path. "
        "Do not edit `.helix/`, `helix-logs/`, or backend-managed staged hook files."
    )


def _protected_runtime_edit_denial_for_external_path(path: Path) -> str:
    return (
        "Built-in edit tool blocked by optimize workflow policy. "
        f"`{path}` is a protected backend-managed hook path. "
        "Do not edit installed Helix hook files."
    )


def _strict_skill_script_edit_denial(workspace_relative_path: str) -> str:
    return (
        "Built-in edit tool blocked by strict agent hook policy. "
        f"`{workspace_relative_path}` is a staged skill implementation file. "
        "Use the documented workflow interface or adjust the strict hook configuration if this edit is required."
    )


def _awaiting_round_start_built_in_edit_denial() -> str:
    return (
        "Built-in edit tool blocked by optimize workflow policy. "
        "Current phase is awaiting_round_start, so no optimize round is active yet. "
        "Use `triton-npu-optimize-state` `start-round` to open the next `opt-round-N/` before editing."
    )


def _deep_analysis_built_in_edit_denial() -> str:
    return (
        "Built-in edit tool blocked by optimize workflow policy. "
        "Current phase is deep_analysis, so the candidate must remain unchanged. "
        "Run profile-bench and the staged IR capture_ir.py command for the selected case, "
        "choose one to five symptom IDs (or `unknown` alone), then use "
        "`triton-npu-optimize-state` `submit-deep-analysis` with both manifests and repeated "
        "`--symptom <id>` arguments before editing."
    )


def _round_active_built_in_edit_denial(round_dir: str) -> str:
    return (
        "Built-in edit tool blocked by optimize workflow policy. "
        f"Current active round is {round_dir}. Built-in edits must stay inside `{round_dir}/`. "
        "Edit the round-local snapshot and round artifacts instead of top-level workspace files. "
        "If the round's intent or required evidence depth changes mid-round, use "
        "`triton-npu-optimize-state` `set-current-round-state` before continuing edits. "
        "When this round is ready, use `triton-npu-optimize-state` `submit-round` to submit it before moving on."
    )


def _first_path_text(tool_input: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _collect_command_path_references(command: str) -> list[str]:
    return _collect_command_path_references_inner(command, seen_commands=set())


def _collect_command_path_references_inner(
    command: str,
    *,
    seen_commands: set[str],
) -> list[str]:
    if command in seen_commands:
        return []
    references: list[str] = []
    for segment in _shell_command_segments(command):
        references.extend(_collect_segment_path_references(segment, seen_commands=seen_commands))
    return references


def _collect_segment_path_references(
    segment: str,
    *,
    seen_commands: set[str],
) -> list[str]:
    if segment in seen_commands:
        return []

    simple_command = _simple_command_text(segment)
    if simple_command is None:
        return []
    tokens = _split_command(simple_command)
    if not tokens:
        return []

    nested_command = _first_shell_wrapper_command(tokens)
    if nested_command is not None:
        return _collect_command_path_references_inner(
            nested_command,
            seen_commands=seen_commands | {segment},
        )

    if not _is_read_command_token(tokens[0]):
        return []
    return _simple_read_command_operands(tokens)


def _first_shell_wrapper_command(tokens: list[str]) -> str | None:
    if not tokens:
        return None
    if Path(tokens[0]).name not in SHELL_WRAPPERS:
        return None
    if len(tokens) < 3:
        return None
    if tokens[1] not in SHELL_WRAPPER_FLAGS:
        return None
    return tokens[2]


def _simple_command_text(command: str) -> str | None:
    quote: str | None = None
    escaped = False
    for char in command:
        if quote == "'":
            if char == "'":
                quote = None
            continue
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char in AMBIGUOUS_SHELL_CHARACTERS:
            return None
    return command if quote is None and not escaped else None


def _simple_read_command_operands(tokens: list[str]) -> list[str]:
    operands: list[str] = []
    positional_only = False
    for token in tokens[1:]:
        if positional_only:
            operands.append(token)
            continue
        if token == "--":
            positional_only = True
            continue
        if token.startswith("-"):
            continue
        operands.append(token)
    return operands


def _split_command(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return []


def _is_read_command_token(token: str) -> bool:
    return Path(token).name in READ_COMMANDS


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return cast(dict[str, Any], data)


def _resolve_policy_path(value: object) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    return Path(value).expanduser().resolve()


def _resolve_cwd(value: object, workspace_root: Path) -> Path:
    if not isinstance(value, str) or not value:
        return workspace_root
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = workspace_root / path
    return path.resolve()


def _extra_read_roots(policy: dict[str, Any]) -> list[Path]:
    roots: list[Path] = []
    for raw_root in _string_list(policy, "extra_read_roots"):
        root = _resolve_policy_path(raw_root)
        if root is not None and root not in roots:
            roots.append(root)
    return roots


def _string_list(mapping: dict[str, Any], key: str) -> list[str]:
    value = mapping.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _resolve_path_text(path_text: str, cwd: Path, workspace_root: Path) -> Path | None:
    if any(ch in path_text for ch in "*?{}"):
        return None
    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = cwd / path_text
    try:
        return path.resolve()
    except OSError:
        return (workspace_root / path_text).resolve()


def _is_under_any_root(path: Path, roots: list[Path]) -> bool:
    return any(_is_relative_to(path, root) for root in roots)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _matches_any_glob(path: Path, patterns: list[str]) -> bool:
    raw_path = str(path)
    return any(fnmatch.fnmatch(raw_path, pattern) for pattern in patterns)


_PLUGIN_DENY_MESSAGE = (
    "This read is blocked by helix workspace policy. Stay within the current workspace "
    "and do not inspect protected optimize runtime files or `helix-logs/` output. "
    "Use the skill instructions and documented command interface instead."
)


def build_denial_output(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--policy")
    mode.add_argument("--claude-plugin", action="store_true")
    parser.add_argument("--failure-prefix")
    args = parser.parse_args(argv)

    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("expected JSON object payload on stdin")
        typed_payload = cast(dict[str, Any], payload)
        if args.claude_plugin:
            policy = _claude_plugin_policy(typed_payload)
            if policy is None:
                return 0
        else:
            policy = _load_json(Path(args.policy))
        reason = deny_reason_for_tool_use(policy, typed_payload)
    except Exception as exc:  # noqa: BLE001 - hooks must fail open
        prefix = args.failure_prefix or (
            "helix claude plugin PreToolUse"
            if args.claude_plugin
            else "helix agent hook"
        )
        print(f"{prefix} failed open: {exc}", file=sys.stderr)
        return 0

    if reason is not None:
        json.dump(build_denial_output(reason), sys.stdout)
    return 0


def _claude_plugin_policy(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw_cwd = payload.get("cwd")
    if not isinstance(raw_cwd, str) or not raw_cwd:
        return None
    root = Path(raw_cwd).expanduser().resolve()
    plugin_hook_root = Path(__file__).resolve().parent
    plugin_hook_globs = [str(plugin_hook_root), str(plugin_hook_root / "**")]
    extra_read_roots: list[str] = []
    compiler_source = _existing_plugin_compiler_source()
    if compiler_source is not None:
        extra_read_roots.append(str(compiler_source))
    return {
        "workspace_root": str(root),
        "enabled": True,
        "extra_read_roots": extra_read_roots,
        "deny_read_globs": [
            str(root / ".helix"),
            str(root / ".helix" / "**"),
            str(root / "helix-logs"),
            str(root / "helix-logs" / "**"),
            *plugin_hook_globs,
        ],
        "deny_edit_globs": plugin_hook_globs,
        "strict_deny_read_globs": [
            str(root / ".claude" / "skills" / "*" / "scripts"),
            str(root / ".claude" / "skills" / "*" / "scripts" / "**"),
        ],
        "strict_deny_edit_globs": [
            str(root / ".claude" / "skills" / "*" / "scripts"),
            str(root / ".claude" / "skills" / "*" / "scripts" / "**"),
        ],
        "deny_message": _PLUGIN_DENY_MESSAGE,
    }


def _existing_plugin_compiler_source() -> Path | None:
    configured = os.environ.get("HELIX_CLAUDE_PLUGIN_COMPILER_SOURCE", "auto")
    if configured.strip().lower() in {"0", "false", "no", "off", "disabled"}:
        return None
    raw_cache_dir = os.environ.get("HELIX_COMPILER_SOURCE_CACHE_DIR")
    cache_dir = (
        Path(raw_cache_dir).expanduser().resolve()
        if raw_cache_dir
        else (Path.home() / ".helix").resolve()
    )
    checkout = cache_dir / "compiler-sources" / "AscendNPU-IR"
    if checkout.is_dir() and (checkout / ".git").exists():
        return checkout.resolve()
    return None


if __name__ == "__main__":
    raise SystemExit(main())
