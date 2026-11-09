#!/usr/bin/env python3
# Copyright 2026 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Translate Claude hook payloads and decisions through the shared policy.

Only SubagentStop settles Claude diagnosis attempts, whether the Agent
(formerly Task) runs in the foreground or background.
Successful post-tool guidance is delivered as one additionalContext payload.
"""

import json
import os
import re
import sys
from pathlib import Path

# This adapter lives at <project>/.claude/hooks/cc_hook.py; the neutral
# decision layer lives at <project>/scripts/. Put scripts/ on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from op_autoresearch.utils.console import emit
from decide import AgentEvent, Decision, decide

# --- Claude stdin payload parsing ------------------------------------------
# Claude's native tool names -> decide()'s neutral tool taxonomy. This map is
# the Claude adapter's own business; decide() only ever sees the neutral kind.
_CC_TOOL_KIND = {
    "Bash": "shell",
    "Edit": "edit",
    "Write": "edit",
    "MultiEdit": "edit",
    "NotebookEdit": "edit",
    "Task": "subagent",
    "Agent": "subagent",
}


def _read_payload() -> dict:
    """Parse the hook payload from stdin. Tolerates Windows paths whose
    backslashes arrive unescaped in the JSON (C:\\Users → C:\\\\Users).
    """
    raw = sys.stdin.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        fixed = re.sub(r'(?<!\\)\\(?![\\"/bfnrtu])', r"\\\\", raw)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            return {}


def _event_from_payload(kind: str, payload: dict) -> AgentEvent:
    tool_input = payload.get("tool_input", {}) or {}
    tool_name = payload.get("tool_name", "Agent" if kind == "subagent_stop" else "")
    response = payload.get("tool_response", payload.get("tool_output", ""))
    tool_kind = _CC_TOOL_KIND.get(tool_name, "")
    if kind == "post_tool" and tool_kind == "subagent" and isinstance(response, dict):
        if response.get("status") == "async_launched" or response.get("isAsync"):
            tool_kind = ""  # No completion decision for a background launch.
    return AgentEvent(
        kind="post_tool" if kind == "subagent_stop" else kind,
        tool_kind=tool_kind,
        tool=tool_name,
        command=tool_input.get("command", ""),
        file_path=tool_input.get("file_path") or tool_input.get("notebook_path", ""),
        subagent_type=tool_input.get("subagent_type") or payload.get("agent_type", ""),
        subagent_completed=kind == "subagent_stop",
        output=str(response),
        stop_reason=payload.get("stop_reason", "unknown"),
        session_id=(
            os.environ.get("AR_SESSION_ID")
            or payload.get("session_id")
            or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
        ),
    )


# --- Decision -> Claude wire ------------------------------------------------
def _todo_context(header: str, todos: list) -> str:
    """Render the optional plan mirror; plan.md remains the source of truth."""
    return (
        f"{header}\n"
        f"If you have a todo/task-list tool (e.g. TodoWrite), mirror the exact "
        f"list below with it — replace any existing entries, do not merge or "
        f"append. If you have no such tool, ignore this. plan.md is the source "
        f"of truth; the mirror reflects current live work only (completed items "
        f"live in plan.md's Settled History). Pass the payload verbatim.\n"
        f"Plan-mirror payload:\n{json.dumps({'todos': todos}, ensure_ascii=False)}"
    )


def _emit(kind: str, d: Decision) -> int:
    if kind == "subagent_stop":
        return 0  # Completion bookkeeping must not re-prompt the child.
    if d.block:
        if kind == "pre_tool":
            emit(d.block_reason, file=sys.stderr)
            return 2
        emit(json.dumps({"decision": "block", "reason": d.block_reason}))
        return 0

    output = {}
    if kind == "post_tool":
        lines = [*d.status, d.context or ""]
        if d.todos_header is not None:
            lines.append(_todo_context(d.todos_header, d.todos or []))
        context = "\n".join(filter(None, lines))
        if context:
            output = {"hookEventName": "PostToolUse", "additionalContext": context}
    else:
        for line in d.status:
            emit(line, file=sys.stderr)
    if output:
        emit(json.dumps({"hookSpecificOutput": output}))
    return 0


def main() -> int:
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    if kind not in ("pre_tool", "post_tool", "subagent_stop", "stop"):
        # Unknown invocation → behave as a no-op allow, never crash a hook.
        return 0
    payload = _read_payload()
    event = _event_from_payload(kind, payload)
    os.environ["AR_SESSION_ID"] = event.session_id
    return _emit(kind, decide(event))


if __name__ == "__main__":
    sys.exit(main())
