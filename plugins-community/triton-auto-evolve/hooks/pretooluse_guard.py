#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""
PreToolUse guard for triton-auto-evolve Agent Loop.

Provides round-aware security policy for file operations and
self-protection against deletion or modification of infrastructure files.

Invoked by Claude/Cursor PreToolUse hook. Exits 0 (allow) or 2 (deny).
"""
import json
import logging
import os
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def get_tool_info() -> tuple[str, dict]:
    """Read tool name and input from the PreToolUse hook payload.

    Claude Code sends the payload as JSON on stdin (fields include
    ``tool_name``, ``tool_input``, and ``cwd``).  Some alternative harnesses
    may still pass the same data via ``CLAUDE_TOOL_NAME`` /
    ``CLAUDE_TOOL_INPUT`` environment variables, so we keep a fallback.
    """
    payload: dict = {}
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError, OSError):
        pass

    if isinstance(payload, dict) and payload:
        return payload.get("tool_name", ""), payload.get("tool_input", {})

    # Fallback for harnesses that pass data via environment variables.
    tool_name = os.environ.get("CLAUDE_TOOL_NAME", "")
    tool_input_raw = os.environ.get("CLAUDE_TOOL_INPUT", "{}")
    try:
        tool_input = json.loads(tool_input_raw)
    except (json.JSONDecodeError, TypeError):
        tool_input = {}
    return tool_name, tool_input


def _is_worker_mode() -> bool:
    """Return True if running as a per-round sub-agent worker.

    Workers execute Phase 0-8 in isolation and do not perform round
    transitions, so the Phase 8 round-contract gate and state-dependent
    round_index.json checks are bypassed. Infrastructure protection
    remains active.
    """
    return os.environ.get("TRITON_OPTIMIZER_MODE", "").lower() == "worker"


def get_plugin_root() -> Path:
    """Determine the plugin root directory (where hooks/ resides)."""
    script = Path(__file__).resolve()
    return script.parent.parent  # hooks/ is one level below plugin root


HOOKS_DIR: Path | None = None


def _hooks_dir() -> Path:
    global HOOKS_DIR
    if HOOKS_DIR is None:
        HOOKS_DIR = get_plugin_root() / "hooks"
    return HOOKS_DIR


_PROTECTED_PATH_PATTERNS: list[re.Pattern] | None = None


def _compile_patterns(patterns_cfg: list[str]) -> list[re.Pattern]:
    """Compile protected patterns, ignoring malformed ones."""
    patterns: list[re.Pattern] = []
    for p in patterns_cfg:
        try:
            patterns.append(re.compile(p))
        except re.error:
            pass
    return patterns


def _load_guard_config() -> list[re.Pattern]:
    """Load protected benchmark/user-data patterns from guard-config.json.

    Returns a list of compiled regex patterns. Paths matching these patterns
    are read-only: Write/Edit and destructive Bash commands are blocked.
    """
    global _PROTECTED_PATH_PATTERNS
    if _PROTECTED_PATH_PATTERNS is not None:
        return _PROTECTED_PATH_PATTERNS

    config_path = get_plugin_root() / "hooks" / "guard-config.json"
    patterns: list[re.Pattern] = []
    if config_path.is_file():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            patterns = _compile_patterns(cfg.get("protected_patterns", []))
        except (OSError, json.JSONDecodeError):
            pass

    _PROTECTED_PATH_PATTERNS = patterns
    return patterns


def _is_protected_path(path: Path | str) -> bool:
    """Return True if path matches a protected benchmark/user-data pattern."""
    try:
        s = str(path)
        resolved = Path(path).resolve()
        candidates = {s, str(resolved)}
        # Also check absolute form relative to CWD for relative paths
        if not Path(path).is_absolute():
            candidates.add(str(Path.cwd() / path))
    except (OSError, RuntimeError):
        return False

    for candidate in candidates:
        for pat in _load_guard_config():
            if pat.search(candidate):
                return True
    return False


def _is_under_hooks(path: Path) -> bool:
    """Check if a resolved path is inside the hooks/ directory."""
    try:
        resolved = path.resolve()
        hooks_resolved = _hooks_dir().resolve()
        return hooks_resolved in resolved.parents or resolved == hooks_resolved
    except (OSError, RuntimeError):
        return False


def _is_infrastructure_path(path: Path) -> bool:
    """Check if path is a critical infrastructure file."""
    name = path.name
    if name in ("AGENTS.md", "CLAUDE.md"):
        return True
    try:
        resolved = path.resolve()
        parent = resolved.parent
        if parent.name == ".claude-plugin":
            return True
        if parent.name == "hooks" and _is_under_hooks(parent):
            return True
        # Check skills/triton-agent-loop/
        if "skills/triton-agent-loop" in str(resolved):
            return True
        # Check .claude/references/ (authoritative agent-loop spec, read-only for the agent)
        if ".claude/references" in str(resolved):
            return True
        # Check the source references/ directory, which is symlinked into .claude/references
        ref_dir = get_plugin_root() / "references"
        if ref_dir.exists():
            ref_resolved = ref_dir.resolve()
            if ref_resolved in resolved.parents or resolved == ref_resolved:
                return True
    except (OSError, RuntimeError):
        pass
    return False


def _find_state_dir() -> Path | None:
    """Find .triton-agent/ directory by searching from CWD upward.

    Searches CWD, triton_ascend_output/ (code convention), then walks
    up parent directories to handle both possible locations.
    """
    cwd = Path.cwd()
    checked: set[Path] = set()

    for p in [cwd] + list(cwd.parents):
        if p in checked:
            continue
        checked.add(p)
        # Workspace root location (CLAUDE.md convention)
        candidate = p / ".triton-agent"
        if candidate.is_dir():
            return candidate
        # Inside triton_ascend_output/{op_name}-{algorithm}-{run_tag}/ (transition_next_round.py code convention)
        candidate = p / "triton_ascend_output" / ".triton-agent"
        if candidate.is_dir():
            return candidate

    return None


def _state_files(state_dir: Path | None) -> list[Path]:
    """Return all per-operator state files in .triton-agent/.

    Includes state-{op_name}-{algorithm}-{run_tag}.json files and the legacy
    state.json.
    """
    if state_dir is None or not state_dir.is_dir():
        return []
    files = sorted(state_dir.glob("state-*.json"))
    legacy = state_dir / "state.json"
    if legacy.is_file():
        files.append(legacy)
    return files


def _operator_lock_path_for_state(state_path: Path) -> Path | None:
    """Derive the operator-level .transition_lock.json path from a state file.

    state.work_dir is {op_dir}/opt-round-N/; its parent is the operator directory.
    The lock file is stored at {op_dir}/.transition_lock.json.
    """
    if not state_path.is_file():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        work_dir = state.get("work_dir")
        if not work_dir:
            return None
        op_dir = Path(work_dir).parent  # work_dir/.. = operator directory
        return op_dir / ".transition_lock.json"
    except (json.JSONDecodeError, OSError, AttributeError):
        return None


def _is_allowed_script(command: str) -> bool:
    """Check if a Bash command calls an allowed gate-release script."""
    allowed = [
        r'transition_next_round\.py',
        r'check_stop_decision\.py',
    ]
    for pattern in allowed:
        if re.search(pattern, command):
            return True
    return False


def _operator_lock_path(state_dir: Path) -> Path | None:
    """Deprecated helper kept for compatibility.

    New code should use _operator_lock_path_for_state with an explicit state file.
    """
    files = _state_files(state_dir)
    if not files:
        return None
    return _operator_lock_path_for_state(files[0])


def check_transition_gate(tool_name: str, tool_input: dict) -> str | None:
    """Check the Phase 7 transition gate.

    When any per-operator state file has last_phase == 7 and its corresponding
    .transition_lock.json does not exist, the round transition gate is closed:
    the Agent must call either transition_next_round.py (to continue) or
    check_stop_decision.py (to stop) before any write operations are allowed.

    The lock file is stored at the operator directory level
    (triton_ascend_output/{op_name}-{algorithm}-{run_tag}/.transition_lock.json), NOT in .triton-agent/.

    Returns error message or None.
    """
    state_dir = _find_state_dir()
    if state_dir is None:
        return None  # No active optimization session

    state_files = _state_files(state_dir)
    if not state_files:
        return None

    closed_gates: list[Path] = []
    for state_path in state_files:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        last_phase = state.get("last_phase")
        if last_phase != 7:
            continue

        lock_path = _operator_lock_path_for_state(state_path)
        if lock_path is None:
            continue
        if not lock_path.is_file():
            closed_gates.append(lock_path)

    if not closed_gates:
        return None  # No operator is waiting for transition/stop

    # Read-only operations always allowed
    if tool_name in ("Read", "Glob", "Grep"):
        return None

    # Bash calling allowed gate-release scripts is allowed
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if _is_allowed_script(command):
            return None

    # All other tool calls are blocked
    lock_list = "\n  ".join(str(p) for p in closed_gates)
    return (
        "Phase 7 过渡门禁已关闭：以下算子上一轮已完成 (last_phase=7)，"
        f"但未找到过渡锁文件：\n  {lock_list}\n"
        "在过渡或停止决策完成前，禁止所有写操作。请执行以下命令之一：\n\n"
        "  继续到下一轮:\n"
        "    python3 skills/triton-agent-loop/scripts/transition_next_round.py ...\n\n"
        "  检查是否可以停止:\n"
        "    python3 skills/triton-agent-loop/scripts/check_stop_decision.py ...\n\n"
        "注意：check_stop_decision.py 会在 can_stop=true 时自动释放门禁，"
        "此后可以正常输出最终报告。"
    )


def _last_phase_from_state(state_dir: Path | None) -> int | None:
    """Read the maximum last_phase across all state files.

    Returns the highest last_phase value found, or None if no state exists.
    """
    files = _state_files(state_dir)
    if not files:
        return None
    max_phase: int | None = None
    for state_path in files:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            phase = state.get("last_phase")
            if isinstance(phase, int) and (max_phase is None or phase > max_phase):
                max_phase = phase
        except (json.JSONDecodeError, OSError):
            continue
    return max_phase


def _operator_lock_exists(state_dir: Path | None) -> bool:
    """Check if any operator-level .transition_lock.json exists."""
    if state_dir is None:
        return False
    for state_path in _state_files(state_dir):
        lock_path = _operator_lock_path_for_state(state_path)
        if lock_path is not None and lock_path.is_file():
            return True
    return False


def check_round_index_write_worker(tool_name: str, tool_input: dict) -> str | None:
    """Worker-mode guard: sub agents must never write round_index.json.

    Workers do not have the orchestrator's view of round history, so any
    write to round_index.json is a contract violation.
    """
    file_path = tool_input.get("file_path", "")
    command = tool_input.get("command", "")

    if tool_name in ("Write", "Edit", "MultiEdit") and "round_index.json" in file_path:
        return (
            "Worker 模式禁止写入 round_index.json。"
            "子代理无权更新轮次索引，该操作必须由 Orchestrator 执行。"
        )

    if tool_name == "Bash" and command:
        write_patterns = [
            r'(?:>|>>)\s*.*round_index\.json',
            r'round_index\.json.*(?:write_text|write_bytes|open\(.*["\'][wa])',
            r'(?:json\.dump|json\.dumps).*round_index\.json',
            r'(?:pickle\.dump).*round_index\.json',
            r'cat\s+.*>.*round_index\.json',
        ]
        for pattern in write_patterns:
            if re.search(pattern, command):
                return "Worker 模式禁止通过 Bash 写入 round_index.json。"

    return None


def check_template_write_worker(tool_name: str, tool_input: dict) -> str | None:
    """Worker-mode guard: sub agents must never write template files.

    Experience accumulation (.claude/template/{category}.md updates) is the
    responsibility of the Orchestrator after all rounds complete.
    """
    file_path = tool_input.get("file_path", "")
    command = tool_input.get("command", "")

    template_indicators = [".claude/template/", "/template/"]
    is_template_write = any(ind in file_path for ind in template_indicators) and file_path.endswith(".md")

    if tool_name in ("Write", "Edit", "MultiEdit") and is_template_write:
        return (
            "Worker 模式禁止写入 template 文件（.claude/template/*.md）。"
            "经验沉淀必须由 Orchestrator 在所有 round 结束后统一完成。"
        )

    if tool_name == "Bash" and command:
        write_patterns = [
            r'(?:>|>>)\s*.*\.claude/template/.*\.md',
            r'\.claude/template/.*\.md.*(?:write_text|write_bytes|open\(.*["\'][wa])',
            r'(?:json\.dump|json\.dumps).*\.claude/template/',
            r'cat\s+.*>.*\.claude/template/.*\.md',
        ]
        for pattern in write_patterns:
            if re.search(pattern, command):
                return "Worker 模式禁止通过 Bash 写入 .claude/template/*.md。"

    return None


def check_state_write_worker(tool_name: str, tool_input: dict) -> str | None:
    """Worker-mode guard: sub agents must never write orchestrator state files."""
    file_path = tool_input.get("file_path", "")
    command = tool_input.get("command", "")

    is_state_write = (
        ".triton-agent/state.json" in file_path
        or ".triton-agent/state-" in file_path
    )

    if tool_name in ("Write", "Edit", "MultiEdit") and is_state_write:
        return (
            "Worker 模式禁止写入 Orchestrator 状态文件（.triton-agent/state*.json）。"
            "状态文件由 Orchestrator 独占更新。"
        )

    if tool_name == "Bash" and command:
        write_patterns = [
            r'(?:>|>>)\s*.*\.triton-agent/state\.json',
            r'\.triton-agent/state\.json.*(?:write_text|write_bytes|open\(.*["\'][wa])',
            r'(?:json\.dump|json\.dumps).*\.triton-agent/state\.json',
            r'cat\s+.*>.*\.triton-agent/state\.json',
            r'(?:>|>>)\s*.*\.triton-agent/state-[^/]*\.json',
            r'\.triton-agent/state-[^/]*\.json.*(?:write_text|write_bytes|open\(.*["\'][wa])',
            r'(?:json\.dump|json\.dumps).*\.triton-agent/state-[^/]*\.json',
            r'cat\s+.*>.*\.triton-agent/state-[^/]*\.json',
        ]
        for pattern in write_patterns:
            if re.search(pattern, command):
                return "Worker 模式禁止通过 Bash 写入 Orchestrator 状态文件（.triton-agent/state*.json）。"

    return None


def check_round_index_write(tool_name: str, tool_input: dict) -> str | None:
    """Block direct writes to round_index.json outside of authorized flows.

    round_index.json is the authoritative round tracking index. It must
    only be written by transition_next_round.py (round transition) or
    check_stop_decision.py (stop decision). Direct writes from the Agent
    at any phase after Phase 0 risk corrupting round tracking.

    Phase 0 is exempted because Idle Recovery (Step 5a.5) may need to
    update the current round's direction/hypothesis before proceeding.
    """
    state_dir = _find_state_dir()
    if state_dir is None:
        return None  # No active optimization

    # If gate is open (operator-level lock exists), allow
    if _operator_lock_exists(state_dir):
        return None

    # Phase 0 allows round_index.json updates (Idle Recovery)
    last_phase = _last_phase_from_state(state_dir)
    if last_phase == 0:
        return None

    # Check if this tool call targets round_index.json
    file_path = tool_input.get("file_path", "")
    command = tool_input.get("command", "")

    # ── Write/Edit targeting round_index.json ──
    if tool_name in ("Write", "Edit", "MultiEdit") and "round_index.json" in file_path:
        return (
            "禁止直接写入 round_index.json。该文件是轮次追踪的权威记录，"
            "必须通过以下授权脚本之一更新：\n\n"
            "  python3 skills/triton-agent-loop/scripts/transition_next_round.py ...\n"
            "  python3 skills/triton-agent-loop/scripts/check_stop_decision.py ...\n\n"
            f"当前 last_phase={last_phase}，非 Phase 0 不允许直接操作。"
        )

    # ── Bash command targeting round_index.json ──
    if tool_name == "Bash":
        if not command or _is_allowed_script(command):
            return None  # Allowed: authorized script call

        write_patterns = [
            # Shell redirect to round_index.json
            r'(?:>|>>)\s*.*round_index\.json',
            r'round_index\.json.*(?:write_text|write_bytes|open\(.*[\"\'][wa])',
            r'(?:json\.dump|json\.dumps).*round_index\.json',
            r'(?:pickle\.dump).*round_index\.json',
            r'cat\s+.*>.*round_index\.json',
        ]
        for pattern in write_patterns:
            if re.search(pattern, command):
                return (
                    "禁止通过 Bash 直接写入 round_index.json。"
                    "必须调用 transition_next_round.py 或 check_stop_decision.py。"
                )

    return None


def check_write_edit(tool_input: dict) -> str | None:
    """Check if a Write/Edit targets infrastructure paths. Return error message or None."""
    file_path = tool_input.get("file_path", "")
    if not file_path:
        return None

    target = Path(file_path)
    if _is_under_hooks(target):
        return (
            f"禁止修改安全基础设施文件: {file_path}\n"
            f"hooks/ 目录下的文件受保护，不允许删除、移动或修改。"
        )
    if _is_infrastructure_path(target):
        return (
            f"禁止修改安全基础设施文件: {file_path}\n"
            f"AGENTS.md、CLAUDE.md、.claude-plugin/、skills/triton-agent-loop/ "
            f"及 hooks/ 下的文件受保护。"
        )
    if _is_protected_path(target):
        return (
            f"禁止修改或删除受保护的源 benchmark / 用户数据路径: {file_path}\n"
            f"该路径只允许读取（Read/Grep/Glob），禁止 Write/Edit/删除/覆盖。"
        )
    return None


def check_bash(tool_input: dict) -> str | None:
    """Check if a Bash command targets infrastructure files. Return error message or None."""
    command = tool_input.get("command", "")
    if not command:
        return None

    # Patterns that target hooks/ or infrastructure files.
    # 收窄原则(R10 后实测误拦修复): ① 动词加 \b 词边界, 防 lsattr 等词内误匹配;
    # ② [^;|&]*? 限定不跨命令分隔符(; | && ||)与 fd 复制目标(&), 防前段命令或
    #    2>/dev/null、2>&1 的重定向段殃及后段路径; 裸 > 保留, 1>/2> 真覆写仍拦。
    dangerous_patterns = [
        # Direct file operations on hooks/
        (r'\b(?:rm|mv|cp|chmod|chattr)\b[^;|&]*?hooks/',
         "禁止删除、移动或修改 hooks/ 目录下的文件"),
        (r'\brm\b(?:\s+-\w+)*\s+[^;|&]*?pretooluse_guard\.py',
         "禁止删除 guard 脚本"),
        (r'>\s*[^;|&]*?hooks/[^;|&]*?\.py',
         "禁止覆写 hooks/ 下的文件"),
        # chattr -i to remove protection
        (r'\bchattr\s+-i[^;|&]*?hooks/',
         "禁止移除 hooks/ 文件的不可变属性"),
        (r'\bchattr\s+-i[^;|&]*?pretooluse_guard',
         "禁止移除 guard 脚本的不可变属性"),
        # Editing AGENTS.md via bash
        (r'>\s*[^;|&]*?AGENTS\.md|sed\s+-i[^;|&]*?AGENTS\.md',
         "禁止通过 bash 覆写 AGENTS.md"),
        # Deleting settings.json
        (r'\brm\b(?:\s+-\w+)*\s+[^;|&]*?settings\.json',
         "禁止删除 hook 配置文件"),
        # Direct file operations on skills/triton-agent-loop/
        (r'\b(?:rm|mv|chattr)\b[^;|&]*?skills/triton-agent-loop',
         "禁止删除、移动或修改 skills/triton-agent-loop/ 目录下的控制技能文件"),
        (r'\brm\b(?:\s+-\w+)*\s+[^;|&]*?triton-agent-loop',
         "禁止删除 triton-agent-loop 控制技能"),
        (r'>\s*[^;|&]*?skills/triton-agent-loop[^;|&]*?\.py',
         "禁止覆写 skills/triton-agent-loop/ 下的脚本"),
        # chattr -i on control skills
        (r'\bchattr\s+-i[^;|&]*?skills/triton-agent-loop',
         "禁止移除 control skills 的不可变属性"),
    ]

    for pattern, message in dangerous_patterns:
        if re.search(pattern, command):
            return message

    return None


def check_bash_protected_paths(tool_input: dict) -> str | None:
    """Block destructive Bash commands against protected benchmark/user-data paths."""
    command = tool_input.get("command", "")
    if not command:
        return None

    # Find any protected path mentions in the command
    protected_hits: list[str] = []
    for pat in _load_guard_config():
        for m in pat.finditer(command):
            protected_hits.append(m.group(0))
    if not protected_hits:
        return None

    # Always-blocked destructive command prefixes
    destructive_patterns = [
        (r'\brm\s+(?:-rf|-r|-f)?\s*', "删除"),
        (r'\bmv\s+', "移动/重命名"),
        (r'\bchmod\s+', "修改权限"),
        (r'\bchattr\s+', "修改属性"),
        (r'\bsed\s+-i', "原地编辑"),
        (r'\btee\s+', "通过 tee 覆盖"),
        (r'(?:>|>>)\s*', "通过重定向覆盖"),
    ]
    for prefix_pat, action in destructive_patterns:
        if re.search(prefix_pat, command):
            return (
                f"禁止{action}受保护的源 benchmark / 用户数据路径：{protected_hits[0]}。"
                "该路径只读。"
            )

    # cp: block only when the protected path is the destination (last token).
    # Copying *from* a protected source to the work_dir is a read and is allowed.
    if re.search(r'\bcp\s+(?:-[aAefpPrR]+\s+)*', command):
        last_hit = protected_hits[-1]
        if re.search(re.escape(last_hit) + r'\s*$', command):
            return (
                f"禁止向受保护的源 benchmark / 用户数据路径复制/覆盖文件：{last_hit}。"
                "该路径只读。"
            )

    # 检测通过 Python 代码写入受保护路径的两种形态：
    # 一是以写入/追加模式打开字面量路径的调用；二是 Path 对象的 write_text/write_bytes 调用
    py_write_patterns = [
        r"""open\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][wa]['\"]""",
        r"""Path\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\.\s*write_(?:text|bytes)\s*\(""",
    ]
    for pat in py_write_patterns:
        for m in re.finditer(pat, command):
            captured = m.group(1)
            if captured and _is_protected_path(captured):
                return (
                    f"禁止通过 Python 写入受保护的源 benchmark / 用户数据路径：{captured}。"
                    "该路径只读。"
                )

    return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    tool_name, tool_input = get_tool_info()
    worker = _is_worker_mode()

    # ── Phase 7 transition gate (orchestrator mode only) ──
    if not worker:
        gate_error = check_transition_gate(tool_name, tool_input)
        if gate_error:
            logger.error("[Guard] %s", gate_error)
            return 2

    # ── Round index write protection ──
    # In orchestrator mode, only transition_next_round.py / check_stop_decision.py may
    # write round_index.json. In worker mode, sub agents must never write it.
    if worker:
        ri_error = check_round_index_write_worker(tool_name, tool_input)
    else:
        ri_error = check_round_index_write(tool_name, tool_input)
    if ri_error:
        logger.error("[Guard] %s", ri_error)
        return 2

    # ── Template write protection (worker mode only) ──
    if worker:
        tpl_error = check_template_write_worker(tool_name, tool_input)
        if tpl_error:
            logger.error("[Guard] %s", tpl_error)
            return 2

    # ── State.json write protection (worker mode only) ──
    if worker:
        state_error = check_state_write_worker(tool_name, tool_input)
        if state_error:
            logger.error("[Guard] %s", state_error)
            return 2

    if tool_name in ("Write", "Edit", "MultiEdit"):
        error = check_write_edit(tool_input)
        if error:
            logger.error("[Guard] %s", error)
            return 2

    if tool_name == "Bash":
        error = check_bash(tool_input)
        if error:
            logger.error("[Guard] %s", error)
            return 2
        protected_error = check_bash_protected_paths(tool_input)
        if protected_error:
            logger.error("[Guard] %s", protected_error)
            return 2

    # All checks passed
    return 0


if __name__ == "__main__":
    sys.exit(main())
