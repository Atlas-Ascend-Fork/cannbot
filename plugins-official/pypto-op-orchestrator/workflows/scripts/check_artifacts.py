#!/usr/bin/env python3
# coding: utf-8
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: CANN-2.0
"""pypto-op-develop 工作流的确定性产物验收脚本.

a) 必备产物齐全且非空: ``<op>_impl.py`` / ``<op>_golden.py`` /
   ``test_<op>.py`` / ``SPEC.md``; staged 模式 (prepared_case.json 的
   mode == "staged") 额外要求桥接产物 ``<op>_pypto_impl.py``;
b) ``.orchestrator_state.json`` 存在且 Stage 1-7 全部 ``completed``; 存在
   failed/blocked/cancelled 状态时打印失败 stage 与
   ``stage5_phases.phase_status`` 摘要;
c) 扁平布局检查: 禁止 custom.* 包路径导入 / modules 子模块导入 /
   内嵌 sys.path hack.

任一失败即退出码 1 并逐条打印原因; 全部通过打印 ``ARTIFACTS_OK <op>`` 退出 0.

用法::

    python3 check_artifacts.py --prepared "$WORK_DIR/prepared_case.json"
    python3 check_artifacts.py --op relu --op-dir "$WORK_DIR/custom/relu"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

REQUIRED_ARTIFACTS = (
    "{op}_impl.py",
    "{op}_golden.py",
    "test_{op}.py",
)
BRIDGE_ARTIFACTS = ("{op}_pypto_impl.py",)
SPEC_ARTIFACT = "SPEC.md"

REQUIRED_ORCHESTRATOR_STAGES = tuple(str(i) for i in range(1, 8))
_FAILED_STATES = {"failed", "blocked", "cancelled"}
_OK_PHASE_STATES = {
    "verified",
    "verified_with_deviation",
    "completed",
    "passed",
    "done",
}

_IMPORT_TARGET_RE = re.compile(r"^(?:from|import)\s+([A-Za-z0-9_.]+)")


def expected_artifact_paths(op_name: str, op_dir: Path) -> Dict[str, Path]:
    """必备产物 + staged 桥接产物 + SPEC.md 的完整清单."""
    out: Dict[str, Path] = {}
    for tpl in REQUIRED_ARTIFACTS + BRIDGE_ARTIFACTS:
        rel = tpl.format(op=op_name)
        out[rel] = op_dir / rel
    out[SPEC_ARTIFACT] = op_dir / SPEC_ARTIFACT
    return out


def find_flat_layout_violations(
    source_files: Dict[str, str], op_name: str
) -> List[str]:
    """扁平布局违规静态检查 (纯文本扫描, 不 import 目标文件)."""
    violations: List[str] = []
    module_marker = "%s_module" % op_name
    for fname in sorted(source_files):
        src = source_files[fname]
        for lineno, raw in enumerate(src.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "sys.path" in line:
                violations.append("%s:%d: 内嵌 sys.path hack" % (fname, lineno))
                continue
            m = _IMPORT_TARGET_RE.match(line)
            if not m:
                continue
            target = m.group(1)
            if target == "custom" or target.startswith("custom."):
                violations.append(
                    "%s:%d: custom.* 包路径导入 (%s)" % (fname, lineno, target)
                )
            elif target.startswith("modules.") or (
                module_marker in target and target.endswith("_impl")
            ):
                violations.append(
                    "%s:%d: modules/ 子模块导入 (%s)" % (fname, lineno, target)
                )
    return violations


def find_impl_structure_violations(op_dir: Path, op_name: str) -> List[str]:
    """对 impl 与桥接产物做扁平布局检查."""
    source_files: Dict[str, str] = {}
    for fname in ("%s_impl.py" % op_name, "%s_pypto_impl.py" % op_name):
        fpath = op_dir / fname
        if fpath.exists():
            source_files[fname] = fpath.read_text(encoding="utf-8", errors="replace")
    return find_flat_layout_violations(source_files, op_name)


def _read_orchestrator_state(op_dir: Path) -> Optional[dict]:
    state_file = op_dir / ".orchestrator_state.json"
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _stage5_phase_details(state: dict) -> List[str]:
    """提取 stage5_phases.phase_status 中非 OK 阶段的失败详情行."""
    details: List[str] = []
    s5 = state.get("stage5_phases")
    if not isinstance(s5, dict):
        return details
    phase_status = s5.get("phase_status")
    if not isinstance(phase_status, dict):
        return details
    for name, info in sorted(phase_status.items()):
        if not isinstance(info, dict):
            continue
        status = str(info.get("status", "")).lower()
        if status in _OK_PHASE_STATES:
            continue
        details.append(
            "stage5 phase %s: status=%s failure_category=%s last_error=%s"
            % (
                name,
                info.get("status"),
                info.get("failure_category") or "-",
                (str(info.get("last_error") or "-"))[:300],
            )
        )
    return details


def _stage_problems(state: Optional[dict]) -> Tuple[List[str], List[str]]:
    """返回 (问题清单, 失败详情行); 问题为空表示 Stage 1-7 全部 completed."""
    if not isinstance(state, dict):
        return [".orchestrator_state.json 缺失或非法"], []
    stage_status = state.get("stage_status")
    if not isinstance(stage_status, dict) or not stage_status:
        return [".orchestrator_state.json 缺少 stage_status"], []
    problems: List[str] = []
    details: List[str] = []
    for stage in REQUIRED_ORCHESTRATOR_STAGES:
        status = str(stage_status.get(stage)).lower()
        if status != "completed":
            problems.append(
                "Stage %s 状态为 %r (要求 completed)" % (stage, stage_status.get(stage))
            )
    for stage, value in sorted(stage_status.items()):
        if str(value).lower() in _FAILED_STATES:
            details.append("stage %s: %s" % (stage, value))
    details.extend(_stage5_phase_details(state))
    return problems, details


def check(op_name: str, op_dir: Path, require_bridge: bool = True) -> List[str]:
    """返回失败原因清单; 空列表表示全部通过.

    require_bridge=False (interactive 模式) 时不要求桥接产物
    ``<op>_pypto_impl.py``。
    """
    problems: List[str] = []
    if not op_dir.is_dir():
        return ["op_dir 不存在: %s" % op_dir]

    # a) 必备产物齐全且非空
    templates = REQUIRED_ARTIFACTS + (BRIDGE_ARTIFACTS if require_bridge else ())
    for tpl in templates + (SPEC_ARTIFACT,):
        rel = tpl.format(op=op_name)
        path = op_dir / rel
        if not path.is_file():
            problems.append("必备产物缺失: %s" % rel)
        elif path.stat().st_size == 0:
            problems.append("必备产物为空: %s" % rel)

    # b) orchestrator state: Stage 1-7 全部 completed
    state = _read_orchestrator_state(op_dir)
    stage_problems, details = _stage_problems(state)
    problems.extend(stage_problems)
    problems.extend(details)

    # c) 扁平布局契约
    for violation in find_impl_structure_violations(op_dir, op_name):
        problems.append("扁平布局违规: %s" % violation)
    return problems


def _resolve_args(
    args: argparse.Namespace,
) -> Tuple[Optional[str], Optional[Path], bool, Optional[str]]:
    """返回 (op_name, op_dir, 是否要求桥接产物, 错误说明)."""
    if args.prepared:
        try:
            data = json.loads(Path(args.prepared).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return (
                None,
                None,
                True,
                "prepared_case.json 读取失败 (%s): %s" % (args.prepared, exc),
            )
        op_name = data.get("op")
        op_dir = data.get("op_dir")
        if not op_name or not op_dir:
            return (
                None,
                None,
                True,
                "prepared_case.json 缺少 op/op_dir 字段: %s" % args.prepared,
            )
        return str(op_name), Path(op_dir), data.get("mode") == "staged", None
    if args.op and args.op_dir:
        return args.op, Path(args.op_dir), True, None
    return None, None, True, "必须提供 --prepared PATH 或 --op NAME --op-dir PATH"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="pypto-op-develop 工作流产物验收: 产物齐全 + Stage1-7 completed + 扁平布局合规"
    )
    parser.add_argument(
        "--prepared",
        default=None,
        help="prepared_case.json 路径 (取其中 op/op_dir/mode)",
    )
    parser.add_argument("--op", default=None, help="算子名")
    parser.add_argument("--op-dir", default=None, help="算子产物目录")
    args = parser.parse_args()

    op_name, op_dir, require_bridge, err = _resolve_args(args)
    if err:
        logger.error("[check_artifacts] 错误: %s", err)
        return 2
    problems = check(op_name, op_dir, require_bridge=require_bridge)
    if problems:
        for item in problems:
            logger.error("[check_artifacts] FAIL: %s", item)
        return 1
    # 契约输出: 工作流 verify 依赖 grep "ARTIFACTS_OK";
    # stdout 契约输出, 用 os.write 直写 fd 1 而非 print/logging (修复 G.LOG.02)
    os.write(1, ("ARTIFACTS_OK %s\n" % op_name).encode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
