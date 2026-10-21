#!/usr/bin/env python3
# coding: utf-8
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: CANN-2.0
"""prepare-case 节点胶水脚本: 合成/校验 agent 工作输入 prepared_case.json.

本脚本完全自包含: 不解析任何外部仓的用例源文件, 不渲染桥接契约
(gen_prompt.md 的内容由调用方负责)。输入契约分两种模式:

``staged`` 模式 (预置用例, 走 ``--verify`` 入口): 外部调用方在触发
前把 ``REQUIRE.md`` / ``task_desc.py`` / ``gen_prompt.md`` 三个产物预写到
``custom/<op>/`` (即 ``$OP_DIR``), 并在 ``$USER_PROMPT`` 携带 op_name/op_dir/
device_id/性能目标/调优轮次等用例事实。本模式只做核对 (verify): 确认三个
产物存在且非空, 随后由命令行参数合成 ``prepared_case.json``
(``mode: "staged"``); 算子名以 ``--op-name`` 为准, 缺省取 ``$OP_DIR``
目录名兜底 (目录名是文件系统事实, 本脚本不打开/解析任何用例文件提取字段)。

``interactive`` 模式: 任意自然语言提示词或既有 REQUIRE.md 即可触发生成,
不假设任何外部仓:

- ``--from-require`` (入口引导已写好 REQUIRE.md): 从已有
  ``custom/<op>/REQUIRE.md`` 合成最小 prepared_case.json
  (``mode: "interactive"``, task_desc 为 null) 与 gen_prompt.md 占位
  (指向 REQUIRE.md); 桥接契约 (ModelNew) 仅 staged 模式适用;
  算子名同样以 ``--op-name`` 为准, 缺省取 REQUIRE.md 父目录名兜底
  (不解析 REQUIRE.md 内容);
- ``--from-desc`` (无 golden 纯提示词触发, 无任何用例文件): 接受任意自然
  语言需求文本 (内联字符串或既有 markdown/文本文件路径), 不校验章节结构、
  不解析 front matter、不要求文本含任何特定字段; 文本落盘为
  ``custom/<op>/REQUIRE.md`` 后走 ``--from-require`` 同一 interactive 通路。
  需求文本缺少 ``workflows/templates/require_template.md`` 的必备节结构
  (算子语义/数学公式、输入输出规格、精度要求) 时, 按该模板包一层 (原文
  完整保留在 "原始需求描述"一节), 保证下游 Stage 1/SPEC 验收所需信息
  承载格式一致; 已具备结构时逐字落盘。算子名必须经 ``--op-name`` 显式
  传入 (由节点 agent 从 $USER_PROMPT 解析, 提示词未给出时按算子语义自行
  拟定合法 Python 标识符; 本脚本不解析需求文本提取任何字段)。

``--verify`` 复核语义: ``prepared_case.json`` 已存在时只校验其字段齐全且
引用的路径存在非空 (staged 模式要求 task_desc 与 gen_prompt 非空,
interactive 模式不要求), 缺一则退出码 1 并打印缺失清单; 不存在时按上述
staged 入口处理 (核对调用方预写产物并合成记录)。

用法::

    python3 prepare_case.py --verify --work-dir "$WORK_DIR" \
        [--op-name <op>] [--op-dir "$WORK_DIR/custom/<op>"] \
        [--device-id N] [--perf-target-us FLOAT] [--tune-rounds 3]
    python3 prepare_case.py --from-require "$WORK_DIR/custom/<op>/REQUIRE.md" \
        --work-dir "$WORK_DIR" [--op-name <op>] \
        [--device-id N] [--perf-target-us FLOAT] [--tune-rounds 3]
    python3 prepare_case.py --from-desc "<算子需求文本或.md路径>" \
        --op-name <op> --work-dir "$WORK_DIR" \
        [--device-id N] [--perf-target-us FLOAT] [--tune-rounds 3]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_TUNE_ROUNDS = 3

_REQUIRE_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / "templates" / "require_template.md"
)

_PREPARED_KEYS = (
    "op",
    "op_dir",
    "require",
    "task_desc",
    "gen_prompt",
    "device_id",
    "perf_target_us",
    "tune_rounds",
    "mode",
)

_MODES = ("staged", "interactive")

# staged 模式调用方必须预写到 $OP_DIR 的三个产物
_STAGED_ARTIFACTS = ("REQUIRE.md", "task_desc.py", "gen_prompt.md")


def _fail(msg: str, code: int = 2) -> int:
    logger.error("[prepare_case] 错误: %s", msg)
    return code


# ────────────────────────────────────────────────────────────
# verify 模式 (复核已有记录 + staged 预置用例入口)
# ────────────────────────────────────────────────────────────


def verify_prepared(work_dir: Path) -> List[str]:
    """复核已有 prepared_case.json; 返回缺失/无效项清单, 空列表表示通过."""
    problems: List[str] = []
    prepared_path = work_dir / "prepared_case.json"
    if not prepared_path.is_file():
        return ["prepared_case.json 不存在: %s" % prepared_path]
    try:
        data = json.loads(prepared_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return ["prepared_case.json 解析失败: %s" % exc]
    for key in _PREPARED_KEYS:
        if key not in data:
            problems.append("prepared_case.json 缺字段: %s" % key)
    mode = data.get("mode")
    if mode not in _MODES:
        problems.append(
            "prepared_case.json mode 非法: %r (允许 %s)" % (mode, "/".join(_MODES))
        )
    file_keys = ["require"]
    if mode == "staged":
        # interactive 模式无 task_desc, gen_prompt 为可选占位; staged 模式两者必需
        file_keys.extend(["task_desc", "gen_prompt"])
    elif data.get("gen_prompt"):
        file_keys.append("gen_prompt")
    for key in file_keys:
        value = data.get(key)
        if not value:
            problems.append("prepared_case.json 字段为空: %s" % key)
            continue
        path = Path(value)
        if not path.is_file():
            problems.append("文件不存在 (%s): %s" % (key, path))
        elif path.stat().st_size == 0:
            problems.append("文件为空 (%s): %s" % (key, path))
    op_dir = data.get("op_dir")
    if op_dir and not Path(op_dir).is_dir():
        problems.append("op_dir 不存在: %s" % op_dir)
    return problems


def _resolve_staged_op_dir(
    op_dir_arg: Optional[Path], work_dir: Path
) -> Tuple[Optional[Path], Optional[str]]:
    """staged 入口的 $OP_DIR: --op-dir 优先, 缺省从 custom/ 下自动探测唯一用例目录."""
    if op_dir_arg is not None:
        op_dir = op_dir_arg.resolve()
        if not op_dir.is_dir():
            return None, "--op-dir 目录不存在: %s" % op_dir
        return op_dir, None
    custom_root = work_dir / "custom"
    candidates = []
    if custom_root.is_dir():
        for child in sorted(custom_root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if child.name.endswith(".bak") or not (child / "REQUIRE.md").is_file():
                continue
            candidates.append(child)
    if not candidates:
        return None, (
            "prepared_case.json 不存在, 且 custom/ 下未找到调用方预写的用例目录 "
            "(含 REQUIRE.md); 请由调用方预写产物后重试, 或显式传 --op-dir"
        )
    if len(candidates) > 1:
        return None, (
            "custom/ 下存在多个用例目录 (%s), 请显式传 --op-dir 指定"
            % ", ".join(str(c) for c in candidates)
        )
    return candidates[0], None


def _staged_op_name(
    op_dir: Path, op_name_arg: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """staged 用例算子名: --op-name 优先, 缺省取 $OP_DIR 目录名 (文件系统事实,
    不解析任何用例文件); 两者都得不到合法 Python 标识符时报错."""
    op_name = (op_name_arg or "").strip() or op_dir.name
    if not op_name.isidentifier():
        return (
            None,
            "算子名不是合法 Python 标识符: %s (--op-name 或 $OP_DIR 目录名); "
            "请显式传 --op-name" % op_name,
        )
    return op_name, None


def _run_verify_staged(args: argparse.Namespace, work_dir: Path) -> int:
    """staged 模式入口: 核对调用方预写的三产物, 合成 prepared_case.json."""
    op_dir, err = _resolve_staged_op_dir(args.op_dir, work_dir)
    if err:
        return _fail(err)
    problems: List[str] = []
    for name in _STAGED_ARTIFACTS:
        path = op_dir / name
        if not path.is_file():
            problems.append("调用方预写产物缺失: %s" % path)
        elif path.stat().st_size == 0:
            problems.append("调用方预写产物为空: %s" % path)
    if problems:
        for item in problems:
            logger.error("[prepare_case] 缺失: %s", item)
        return 1
    op_name, err = _staged_op_name(op_dir, args.op_name)
    if err:
        return _fail(err)
    prepared = {
        "op": op_name,
        "op_dir": str(op_dir),
        "require": str(op_dir / "REQUIRE.md"),
        "task_desc": str(op_dir / "task_desc.py"),
        "gen_prompt": str(op_dir / "gen_prompt.md"),
        "device_id": args.device_id,
        "perf_target_us": args.perf_target_us,
        "tune_rounds": args.tune_rounds,
        "mode": "staged",
    }
    _write_prepared_json(prepared, work_dir)
    # 契约输出: stdout JSON 需与 prepared_case.json 一致 (工作流核对);
    # stdout 契约输出, 用 os.write 直写 fd 1 而非 print/logging (修复 G.LOG.02)
    os.write(1, (json.dumps(prepared, ensure_ascii=False) + "\n").encode())
    return 0


# ────────────────────────────────────────────────────────────
# --from-desc 需求文本落盘 (无 golden 纯提示词触发)
# ────────────────────────────────────────────────────────────

# 必备节结构探测 (与 lint OL09 对齐: SPEC 需含 数学公式/输入输出规格/精度要求 三节);
# 需求文本三节齐备时不封装, 逐字落盘。
_DESC_REQUIRED_SECTION_PATTERNS = (
    re.compile(r"算子语义|数学公式"),
    re.compile(r"输入输出"),
    re.compile(r"精度"),
)


def _resolve_desc_text(value: str) -> Tuple[Optional[str], Optional[str]]:
    """--from-desc 取值: 指向既有文件则读文件, 否则按内联文本处理; 返回 (文本, 错误)."""
    candidate = Path(value)
    if candidate.is_file():
        try:
            text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return None, "需求文件读取失败 (%s): %s" % (candidate, exc)
    else:
        text = value
    if not text.strip():
        return None, "需求文本为空"
    return text, None


def _derive_desc_op_name(
    op_name_arg: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """算子名必须经 --op-name 显式传入 (提示词未给出时由节点 agent 按算子语义
    自行拟定; 本脚本不解析需求文本); 返回 (op, 错误)."""
    op_name = (op_name_arg or "").strip()
    if not op_name:
        return (
            None,
            "--from-desc 必须显式传 --op-name <算子名> (合法 Python 标识符; "
            "提示词未给出算子名时由 prepare-case 节点 agent 按算子语义拟定); "
            "本脚本不解析需求文本提取任何字段",
        )
    if not op_name.isidentifier():
        return None, "算子名不是合法 Python 标识符: %s" % op_name
    return op_name, None


def _desc_has_required_structure(text: str) -> bool:
    """需求文本是否已具备 require_template.md 的必备节结构."""
    return all(p.search(text) for p in _DESC_REQUIRED_SECTION_PATTERNS)


def _wrap_require_from_desc(op_name: str, raw_text: str) -> str:
    """按 require_template.md 封装缺结构的需求文本, 原文保留在"原始需求描述"一节.

    模板头部 ``<!-- ... -->`` 注释为模板填写说明, 不落进产物。
    """
    template = _REQUIRE_TEMPLATE_PATH.read_text(encoding="utf-8")
    comment = re.match(r"\s*<!--.*?-->\n", template, re.S)
    if comment:
        template = template[slice(comment.end(), None)]
    return template.replace("{{OP_NAME}}", op_name).replace(
        "{{RAW_DESC}}", raw_text.strip()
    )


def write_require_from_desc(
    op_name: str, raw_text: str, custom_root: Path
) -> Tuple[Optional[Path], Optional[str]]:
    """把需求文本落盘为 ``custom/<op>/REQUIRE.md``; 返回 (路径, 错误).

    幂等: 已存在且内容一致时不重写; 已存在但内容不同时报错
    (已有 REQUIRE.md 的场景应改用 --from-require), 不覆盖人工产物。
    """
    if _desc_has_required_structure(raw_text):
        content = raw_text.strip() + "\n"
    else:
        content = _wrap_require_from_desc(op_name, raw_text)
    op_dir = custom_root / op_name
    op_dir.mkdir(parents=True, exist_ok=True)
    require_path = op_dir / "REQUIRE.md"
    if require_path.exists():
        if require_path.read_text(encoding="utf-8") == content:
            return require_path, None
        return None, (
            "REQUIRE.md 已存在且内容与需求文本不一致: %s "
            "(已有 REQUIRE.md 的场景请改用 --from-require)" % require_path
        )
    require_path.write_text(content, encoding="utf-8")
    return require_path, None


# ────────────────────────────────────────────────────────────
# 主流程
# ────────────────────────────────────────────────────────────


def _add_interactive_args(parser: argparse.ArgumentParser) -> None:
    """interactive 模式的输入来源与算子名参数。"""
    parser.add_argument(
        "--from-require",
        type=Path,
        default=None,
        help="interactive 模式: 从已有 custom/<op>/REQUIRE.md 合成最小 prepared_case.json",
    )
    parser.add_argument(
        "--from-desc",
        type=str,
        default=None,
        help="interactive 模式: 算子需求文本 (内联字符串或既有 markdown/文本文件路径), "
        "落盘为 custom/<op>/REQUIRE.md 后走 --from-require 同一通路",
    )
    parser.add_argument(
        "--op-name",
        type=str,
        default=None,
        help="算子名 (合法 Python 标识符), 由节点 agent 从 $USER_PROMPT 解析后传入 "
        "(提示词未给出时按算子语义拟定; 脚本不解析任何用例文件/需求文本): "
        "--from-desc 模式必传; --verify (staged) 与 --from-require 缺省取目录名兜底",
    )


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    """staged/interactive 共用的工作区、用例与调优参数。"""
    parser.add_argument("--work-dir", required=True, type=Path, help="工作流 $WORK_DIR")
    parser.add_argument(
        "--op-dir",
        type=Path,
        default=None,
        help="--verify staged 入口的算子产物目录 ($OP_DIR); 缺省从 "
        "$WORK_DIR/custom/ 下自动探测唯一含 REQUIRE.md 的用例目录",
    )
    parser.add_argument(
        "--device-id",
        type=int,
        default=None,
        help="NPU device id (记入 prepared_case.json, 供工作流设备约束使用)",
    )
    parser.add_argument(
        "--perf-target-us",
        type=float,
        default=None,
        help="Stage 7 性能目标 (us); 缺省为无硬性性能目标",
    )
    parser.add_argument(
        "--tune-rounds",
        type=int,
        default=DEFAULT_TUNE_ROUNDS,
        help="Stage 7 性能优化轮次 (默认 %(default)s)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="复核已有 prepared_case.json; 不存在时作为 staged 模式入口: "
        "核对 $OP_DIR 下调用方预写的 REQUIRE.md/task_desc.py/gen_prompt.md "
        "并合成 mode=staged 的记录",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="合成/校验 prepared_case.json: staged 模式核对调用方预写产物 "
        "(--verify), interactive 模式从已有 REQUIRE.md (--from-require) 或 "
        "算子需求文本 (--from-desc) 合成最小记录"
    )
    _add_interactive_args(parser)
    _add_common_args(parser)
    return parser


def _run_verify(args: argparse.Namespace, work_dir: Path) -> int:
    if args.tune_rounds < 0:
        return _fail("--tune-rounds 必须是非负整数, 收到: %d" % args.tune_rounds)
    prepared_path = work_dir / "prepared_case.json"
    if not prepared_path.is_file():
        # staged 模式入口: 调用方已预写三产物, 本脚本只核对并合成记录
        return _run_verify_staged(args, work_dir)
    problems = verify_prepared(work_dir)
    if problems:
        for item in problems:
            logger.error("[prepare_case] 缺失: %s", item)
        return 1
    # 契约输出: stdout JSON 供工作流核对 verify 结果;
    # stdout 契约输出, 用 os.write 直写 fd 1 而非 print/logging (修复 G.LOG.02)
    os.write(
        1,
        (
            json.dumps({"status": "ok", "work_dir": str(work_dir)}, ensure_ascii=False)
            + "\n"
        ).encode(),
    )
    return 0


def _write_prepared_json(prepared: Dict[str, Any], work_dir: Path) -> None:
    """落盘 prepared_case.json (缩进格式, 断点续跑友好)."""
    prepared_path = work_dir / "prepared_case.json"
    work_dir.mkdir(parents=True, exist_ok=True)
    prepared_path.write_text(
        json.dumps(prepared, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _run_from_require(args: argparse.Namespace, work_dir: Path) -> int:
    """interactive 模式: 从已有 REQUIRE.md 合成最小 prepared_case.json (不解析其内容)."""
    require_path = args.from_require.resolve()
    if not require_path.is_file() or require_path.stat().st_size == 0:
        return _fail("REQUIRE.md 不存在或为空: %s" % require_path)
    op_name = (args.op_name or "").strip() or require_path.parent.name
    if not op_name.isidentifier():
        return _fail(
            "算子名不是合法 Python 标识符: %s (--op-name 或 REQUIRE.md 父目录名); "
            "请显式传 --op-name" % op_name
        )
    op_dir = require_path.parent
    gen_prompt_path = op_dir / "gen_prompt.md"
    if not gen_prompt_path.is_file():
        gen_prompt_path.write_text(
            textwrap.dedent(
                """\
                # 用例事实: %s (interactive 模式)

                工作目录: `%s/`
                算子需求文档 REQUIRE.md (Stage 1 用户需求输入): `%s`

                本用例为 interactive 模式: 无 task_desc, 桥接契约 (ModelNew) 不适用;
                设备号/性能目标/调优轮次等用例事实以 $USER_PROMPT 与 prepared_case.json 为准。
                """
            )
            % (op_name, op_dir, require_path),
            encoding="utf-8",
        )
    prepared = {
        "op": op_name,
        "op_dir": str(op_dir),
        "require": str(require_path),
        "task_desc": None,
        "gen_prompt": str(gen_prompt_path),
        "device_id": args.device_id,
        "perf_target_us": args.perf_target_us,
        "tune_rounds": args.tune_rounds,
        "mode": "interactive",
    }
    _write_prepared_json(prepared, work_dir)
    # 契约输出: stdout JSON 需与 prepared_case.json 一致 (工作流核对);
    # stdout 契约输出, 用 os.write 直写 fd 1 而非 print/logging (修复 G.LOG.02)
    os.write(1, (json.dumps(prepared, ensure_ascii=False) + "\n").encode())
    return 0


def _run_from_desc(args: argparse.Namespace, work_dir: Path) -> int:
    """无 golden 纯提示词触发: 需求文本落盘 REQUIRE.md 后走 --from-require 通路."""
    text, err = _resolve_desc_text(args.from_desc)
    if err:
        return _fail(err)
    op_name, err = _derive_desc_op_name(args.op_name)
    if err:
        return _fail(err)
    require_path, err = write_require_from_desc(op_name, text, work_dir / "custom")
    if err:
        return _fail(err)
    args.from_require = require_path
    return _run_from_require(args, work_dir)


def main() -> int:
    args = _build_parser().parse_args()
    work_dir = args.work_dir.resolve()
    if args.verify:
        return _run_verify(args, work_dir)
    if args.from_desc is not None:
        return _run_from_desc(args, work_dir)
    if args.from_require is not None:
        return _run_from_require(args, work_dir)
    return _fail("必须提供 --verify / --from-require / --from-desc 之一")


if __name__ == "__main__":
    sys.exit(main())
