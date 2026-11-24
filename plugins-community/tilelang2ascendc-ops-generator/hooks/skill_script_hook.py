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
Skill 脚本执行 Hook (PreToolUse 协议)。

对 Bash 工具调用进行拦截：
- 命中 INTERCEPTED_PATTERNS: 直接由本 hook 执行脚本，并以 PreToolUse 协议返回
  permissionDecision=deny + additionalContext，把执行结果（exit_code/stdout/stderr）
  注入回 agent 的上下文，阻止 harness 二次执行。
- 不命中: 输出 permissionDecision=allow，让 harness 正常执行（不在 hook 中重复执行）。

输入：从 stdin 读取 harness PreToolUse JSON：
    {"tool_name": "Bash", "tool_input": {"command": "..."}, ...}

输出：单行 PreToolUse JSON 到 stdout。
"""

import json
import logging
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path


_protocol_logger = logging.getLogger("skill_script_hook.protocol")
_protocol_logger.propagate = False
_protocol_logger.setLevel(logging.INFO)
_protocol_handler = logging.StreamHandler(sys.stdout)
_protocol_handler.setFormatter(logging.Formatter("%(message)s"))
_protocol_logger.addHandler(_protocol_handler)


# 每个条目: (interpreter_regex, script_basename_regex)
# 只匹配“某个解释器 + 脚本路径”这种真正的脚本调用，
# 不匹配命令字符串里仅出现脚本名的情况（如 cat / grep / echo JSON 等）。
_PY_INTERP = r"(?:python|python3|python3\.\d+)"
_SH_INTERP = r"(?:bash|sh)"

INTERCEPTED_PATTERNS = [
    (_PY_INTERP, r"validate_tilelang_impl\.py"),
    (_PY_INTERP, r"validate_ascendc_impl\.py"),
    (_SH_INTERP, r"evaluate_tilelang\.sh"),
    (_SH_INTERP, r"evaluate_ascendc\.sh"),
    (_PY_INTERP, r"performance\.py"),
    (_PY_INTERP, r"build_ascendc\.py"),
    (_PY_INTERP, r"verification_ascendc\.py"),
    (_PY_INTERP, r"verification_tilelang\.py"),
]

# 命令前缀允许的部分（环境变量赋值、cd ... &&、source ... &&）
# 这里只是用于推断"真实的脚本调用"，不需要覆盖所有 shell 语法。
_LEADING_PREFIX = (
    r"^\s*"
    r"(?:export\s+)?"                                 # 可选的 export 关键字
    r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"           # ENV=VAL ...
    r"(?:cd\s+\S+\s*&&\s*)?"                          # cd <dir> &&
    r"(?:export\s+)?"                                 # 可选的 export 关键字
    r"(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*"           # 再次允许 ENV=VAL
    r"(?:&&\s+)*"                                     # 支持 && 链式连接
)

# 项目根目录（被拦截命令的默认 cwd）：
#   1. 显式设置的 PROJECT_ROOT
#   2. Claude Code 传入的 CLAUDE_PROJECT_DIR（用户启动 claude 的目录）
#   3. 插件根：hooks/ 的上一级
# 注意不要多剥一层——再多一层会落到 plugins-community/，命令就会在错误目录执行。
PROJECT_ROOT = os.environ.get("PROJECT_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR")
if not PROJECT_ROOT:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def should_intercept(command: str) -> bool:
    # 仅当命令的"实际执行段"是 <interpreter> <path-to-script> 形式时才拦截。
    # 兼容：环境变量前缀、可选的 `cd <dir> &&` 前缀。
    for interp, script in INTERCEPTED_PATTERNS:
        # 路径里允许出现 / 和非空白字符；脚本名用 \b 边界
        pattern = (
            _LEADING_PREFIX
            + interp
            + r"\s+"
            + r"(?:\S*/)?"
            + script
            + r"(?:\s|$)"
        )
        if re.search(pattern, command):
            return True
    return False


def emit_pretooluse(permission_decision: str, *, reason: str = "", additional_context: str = ""):
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": permission_decision,
        }
    }
    if reason:
        output["hookSpecificOutput"]["permissionDecisionReason"] = reason
    if additional_context:
        output["hookSpecificOutput"]["additionalContext"] = additional_context
    _protocol_logger.info(json.dumps(output, ensure_ascii=False))


def truncate(text: str, limit: int = 8000) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2:]
    return f"{head}\n\n... [truncated {len(text) - limit} chars] ...\n\n{tail}"


_INTERPRETER_RE = re.compile(r"^(?:python|python3|python3\.\d+|bash|sh)$")
_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_SHELL_META_CHARS = ("|", "&", ";", ">", "<")


def _consume_command_prefixes(tokens):
    """吃掉 cd / ENV=VAL / export 前缀，返回 (cd 目标, 环境变量, 剩余起始下标)。

    只在下标越界等无法解析的情况下返回 None。
    """
    cwd = None
    env = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in ("export", "&&"):
            index += 1
            continue
        if _ENV_ASSIGN_RE.match(token):
            name, value = token.split("=", 1)
            env[name] = value
            index += 1
            continue
        if token == "cd":
            if index + 1 >= len(tokens):
                return None
            cwd = os.path.expanduser(tokens[index + 1])
            index += 2
            continue
        break
    return cwd, env, index


def _parse_intercepted_command(command: str):
    """把 shell 命令拆成 (cd 目标, 环境变量, 真正的 argv)。

    拦截正则允许 `cd <dir> &&` 和 `ENV=VAL` 前缀，但命令不能整条丢给
    subprocess（shell=False 下 `cd` / `VAR=VAL` 会被当成可执行文件）。
    这里把前缀解析出来，分别落到 cwd 和 env，剩下的才是要执行的 argv。

    解析不了（含管道/重定向/复合命令等无法在 shell=False 下复刻的语法）时返回 None，
    由调用方交还 harness 正常执行，避免执行成错误的子集。
    """
    # shlex.split 会把裸换行当成普通空白：`cmd1\ncmd2` 会被拼成一条命令，
    # 第二条命令沦为第一条的参数。无法安全复刻时交还 harness。
    if "\n" in command or "\r" in command:
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens:
        return None
    # shlex.split 不做 shell 展开：`$VAR` / `${VAR}` / `$(...)` / 反引号会保留字面值，
    # 当 cwd/argv 用会指到错误位置。保守起见交还 harness 由 shell 自行展开。
    if any("$" in tok or "`" in tok for tok in tokens):
        return None

    prefix = _consume_command_prefixes(tokens)
    if prefix is None:
        return None
    cwd, env, index = prefix

    argv = tokens[index:]
    if len(argv) < 2:
        return None
    if not _INTERPRETER_RE.match(os.path.basename(argv[0])):
        return None
    # 命令尾部还有 shell 语法（链式、管道、重定向）时不接管。
    # 宁可保守回退（交还 harness 正常执行），也不要执行成错误的子集。
    if any(ch in tok for tok in argv for ch in _SHELL_META_CHARS):
        return None
    return cwd, env, argv


def _run_command(argv, cwd: str, env=None):
    """Execute an argv list.

    Returns (exit_code, stdout, stderr, duration_ms, started)：
    started=False 表示进程根本没有启动（如解释器不存在），调用方不应把它当作
    脚本的执行结果去更新门禁状态。
    """
    start_time = time.time()
    started = False
    try:
        proc = subprocess.run(
            argv, shell=False, cwd=cwd, env=env,
            capture_output=True, text=True, timeout=1800,
        )
        started = True
        exit_code = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except subprocess.TimeoutExpired as e:
        started = True          # 进程已启动，只是超时
        exit_code = 124
        stdout = (e.stdout if e.stdout else "")
        stderr = (e.stderr if e.stderr else "")
        stderr += "\n[HOOK] 命令执行超时（30 分钟）"
    except Exception as e:
        exit_code = 1
        stdout = ""
        stderr = f"[HOOK] 执行异常: {type(e).__name__}: {e}"

    duration_ms = int((time.time() - start_time) * 1000)
    return exit_code, stdout, stderr, duration_ms, started

# ── Precision Gate (D-class enforcement) ────────────────────
_PRECISION_GATE_STATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".claude", "hooks", "state", "precision_gate.json",
)

# Patterns for D-class detection in evaluate_ascendc.sh output
_A_CLASS_ERROR_PATTERNS = [
    r"\berror:\s",           # compilation error
    r"\bfatal error:\s",     # fatal compilation error
    r"undefined reference",  # linker error
    r"Segmentation fault",
    r"core dumped",
    r"cannot find -l",       # library not found
    r"No such file or directory",
    r"CMake Error",
    r"make\[\d+\]: \*\*\*",  # make build error
]
_A_CLASS_PATTERN_RE = re.compile("|".join(_A_CLASS_ERROR_PATTERNS), re.IGNORECASE)

_D_CLASS_PASS_RE = re.compile(r"^\s*Result:\s*(pass|fail)\s*$", re.MULTILINE | re.IGNORECASE)
_D_CLASS_NUMERIC_RE = re.compile(r"max_abs_diff\s*=\s*[\d.e+\-]+|MERE\s*=\s*[\d.e+\-]+|matched_ratio\s*=\s*[\d.]+")

_EVAL_ASCENDC_SCRIPT_RE = re.compile(r"evaluate_ascendc\.sh")


def _is_evaluate_ascendc(command: str) -> bool:
    return bool(_EVAL_ASCENDC_SCRIPT_RE.search(command))


def _extract_output_dir(command: str) -> str:
    """Extract output_dir argument from evaluate_ascendc.sh command."""
    m = re.search(r"evaluate_ascendc\.sh\s+(\S+)", command)
    return m.group(1) if m else ""


def _classify_result(exit_code: int, stdout: str, stderr: str) -> str:
    """
    Classify evaluate_ascendc.sh result as "D" (precision failure),
    "A" (code/environment error), or "PASS".
    """
    combined = f"{stdout}\n{stderr}"

    # Check for PASS
    pass_matches = _D_CLASS_PASS_RE.findall(combined)
    if pass_matches:
        last_result = pass_matches[-1].lower()
        if last_result == "pass":
            return "PASS"

    # Check for A-class (compilation/runtime error)
    if _A_CLASS_PATTERN_RE.search(combined):
        return "A"

    # Check for D-class: has numeric diff output and Result: fail
    if _D_CLASS_NUMERIC_RE.search(combined):
        return "D"

    # Non-zero exit without clear A-class or D-class patterns → A
    if exit_code != 0:
        return "A"

    return "UNKNOWN"


def _ensure_precision_gate_dir() -> None:
    os.makedirs(os.path.dirname(_PRECISION_GATE_STATE), exist_ok=True)


def _read_precision_gate() -> dict:
    """Read existing precision gate state to preserve counters across iterations."""
    try:
        with open(_PRECISION_GATE_STATE) as fh:
            return json.load(fh)
    except Exception:
        return {}


def _update_precision_gate(classification: str, stdout: str, output_dir: str) -> None:
    """Write or clear precision gate state based on evaluate_ascendc.sh result.
    On D-class: resets edits_allowed/skill_just_called but PRESERVES
    stage/debug_call_count/tune_call_count across iterations.
    On PASS/A: full reset.
    """
    if classification == "D":
        # Extract failure summary (first few lines of case diffs)
        summary_lines = []
        for line in stdout.splitlines():
            if "max_abs_diff" in line or "Result:" in line:
                summary_lines.append(line.strip())
        failure_summary = "\n".join(summary_lines[:5])

        # Preserve stage and counters from previous iteration
        existing = _read_precision_gate()
        stage = existing.get("stage", "D1")
        debug_count = existing.get("debug_call_count", 0)
        tune_count = existing.get("tune_call_count", 0)

        # Auto-advance stage based on accumulated counts
        if debug_count >= 7:
            stage = "D2"

        state = {
            "d_class_active": True,
            "output_dir": output_dir,
            "edits_allowed": 0,
            "skill_just_called": False,
            "stage": stage,
            "debug_call_count": debug_count,
            "tune_call_count": tune_count,
            "failure_summary": failure_summary,
        }
    else:
        # PASS or A-class: full reset
        state = {"d_class_active": False, "edits_allowed": 0}

    _ensure_precision_gate_dir()
    with open(_PRECISION_GATE_STATE, "w") as fh:
        json.dump(state, fh)


_NOOP_COMMAND = (
    "echo '[hook-noop] original command was intercepted and executed by skill_script_hook'"
)
_CLASS_LABELS = {"D": "D类-精度不匹配", "A": "A类-代码/编译错误", "PASS": "通过"}


def _default_cwd() -> str:
    """被拦截命令的默认工作目录。"""
    return PROJECT_ROOT if os.path.isdir(PROJECT_ROOT) else os.getcwd()


def _resolve_cwd(cd_target) -> str:
    """把 `cd` 目标解析成绝对路径；未指定时用默认工作目录。"""
    if not cd_target:
        return _default_cwd()
    if os.path.isabs(cd_target):
        return cd_target
    return os.path.join(_default_cwd(), cd_target)


def _run_parsed_command(argv, cwd: str, env_overrides: dict):
    """按解析结果执行命令；cd 目标不存在时模拟 shell 的报错（脚本未启动）。"""
    if not os.path.isdir(cwd):
        # 与 shell 的行为对齐：cd 失败即命令失败；started=False 表示脚本没有执行
        return 1, "", f"cd: {cwd}: No such file or directory", 0, False
    env = os.environ.copy()
    env.update(env_overrides)
    return _run_command(argv, cwd, env)


def _sync_precision_gate(command: str, exit_code: int, stdout: str, stderr: str):
    """评测类命令：分类并同步精度门禁状态；非评测命令返回 None。"""
    if not _is_evaluate_ascendc(command):
        return None
    classification = _classify_result(exit_code, stdout, stderr)
    _update_precision_gate(classification, stdout, _extract_output_dir(command))
    return classification


def _format_class_note(classification) -> str:
    """错误分类说明，附在 hook 提示语后面。"""
    if not classification:
        return ""
    label = _CLASS_LABELS.get(classification, classification)
    note = f" | 错误分类: {label}"
    if classification == "D":
        note += (
            " | [precision_gate] kernel 编辑已锁定，修改代码前必须先调用 "
            "ascendc-precision-debug 或 ascendc-precision-tuning Skill"
        )
    return note


def _format_additional_context(command, cwd, exit_code, duration_ms, stdout, stderr) -> str:
    return (
        f"[skill_script_hook intercepted execution]\n"
        f"command: {command}\n"
        f"cwd: {cwd}\n"
        f"exit_code: {exit_code}\n"
        f"duration_ms: {duration_ms}\n"
        f"--- stdout ---\n{truncate(stdout)}\n"
        f"--- stderr ---\n{truncate(stderr)}\n"
    )


def _format_reason(exit_code: int, class_note: str) -> str:
    status = "成功" if exit_code == 0 else "失败"
    return (
        f"[Hook 拦截提示] 该命令命中 skill_script_hook 拦截规则，"
        f"已由 hook 代为执行（{status}，exit_code={exit_code}）。{class_note}"
        f"执行结果见下方 additionalContext，原命令已被替换为 no-op，不会重复执行。"
    )


def _emit_intercepted_result(
    command, cwd, exit_code, duration_ms, stdout, stderr, classification, started=True
):
    """按 PreToolUse 协议把代执行结果回给 harness。"""
    class_note = _format_class_note(classification)
    if not started:
        class_note += " | [precision_gate] 命令未启动（cwd 不存在或解释器缺失），门禁状态未更新"
    _protocol_logger.info(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "permissionDecisionReason": _format_reason(exit_code, class_note),
                    "additionalContext": _format_additional_context(
                        command, cwd, exit_code, duration_ms, stdout, stderr
                    ),
                    "updatedInput": {"command": _NOOP_COMMAND},
                }
            },
            ensure_ascii=False,
        )
    )


def execute_intercepted(command: str) -> None:
    """接管命中拦截规则的命令：解析前缀 → 执行 → 分类 → 回传结果。"""
    parsed = _parse_intercepted_command(command)
    if parsed is None:
        # 无法在 shell=False 下安全复刻（管道/重定向/复合命令）：不接管，
        # 输出 allow 且不带 updatedInput，让 harness 按原命令正常执行。
        emit_pretooluse("allow")
        return

    cd_target, env_overrides, argv = parsed
    cwd = _resolve_cwd(cd_target)
    exit_code, stdout, stderr, duration_ms, started = _run_parsed_command(
        argv, cwd, env_overrides
    )
    # 脚本没有真正启动（cd 失败 / 解释器缺失）时不更新门禁状态：
    # 否则会把"未执行"误当成一次失败评测，连带清掉已有的 D 类状态。
    classification = _sync_precision_gate(command, exit_code, stdout, stderr) if started else None
    _emit_intercepted_result(
        command, cwd, exit_code, duration_ms, stdout, stderr, classification, started
    )


def read_stdin_command():
    try:
        raw = sys.stdin.read()
    except Exception:
        return None, None
    if not raw or not raw.strip():
        return None, None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(data, dict):
        return None, None
    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    return tool_name, command


def main():
    tool_name, command = read_stdin_command()

    # 没有命令或不是 Bash —— allow，由 harness 处理
    if not command or tool_name != "Bash":
        emit_pretooluse("allow")
        return

    if should_intercept(command):
        execute_intercepted(command)
    else:
        # 不拦截 —— 让 harness 正常处理（不在此重复执行）
        emit_pretooluse("allow")


if __name__ == "__main__":
    main()
