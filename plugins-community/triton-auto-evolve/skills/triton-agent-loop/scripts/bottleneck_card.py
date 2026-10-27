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
"""bottleneck_card.py — 从 Round N 的 B1 产物蒸馏 ≤30 行"瓶颈卡片"（优化项B1-脚本）。

卡片 = op 分解表 + 已证瓶颈结论 + 已否方向，供下一轮 route 的 B1 直接继承
（消费侧规则见 route.md「卡片继承（优先）」，三条 route 分解结论保持一致）。

输入：--round-dir opt-round-N（扫描 route-*/ 的 round_result.json / atom_decomposition.md /
      route_iterations.json / knowledge_pool_update.json，以 best_speedup 最高的成功 route 为准）
输出：--out bottleneck_card.json（JSON；--md 可同时输出渲染版 ≤30 行 markdown）

卡片字段：
  {source_round, op_name, best_route, atoms_md, proven_bottlenecks[], refuted_directions[],
   encoding_active[]}

纯标准库、确定性规则抽取（禁止 import torch/pandas，E1）。任何输入缺失都降级为部分卡片，
不阻塞 transition。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from workspace_utils import find_op_name  # noqa: E402

# 行数预算（渲染版硬上限 30 行）
MAX_ATOM_ROWS = 12
MAX_BOTTLENECKS = 4
MAX_REFUTED = 6


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def pick_best_route(round_dir: Path) -> tuple[str | None, dict]:
    """选 best_speedup 最高的成功 route，返回 (route_id, round_result)。"""
    best = (None, -1.0, {})
    for route_dir in sorted(round_dir.glob("route-*")):
        rr = load_json(route_dir / "round_result.json")
        if not rr:
            continue
        speedup = rr.get("best_speedup") or 0.0
        status = (rr.get("status") or "").lower()
        if status not in ("", "success", "completed") or not isinstance(speedup, (int, float)):
            continue
        if speedup > best[1]:
            best = (rr.get("route_id") or route_dir.name, float(speedup), rr)
    return best[0], best[2]


def extract_atom_table(round_dir: Path, route_id: str | None) -> str:
    """从最优 route 的 atom_decomposition.md 抽 markdown 表（含表头），超预算截断行数。"""
    candidates = []
    if route_id:
        candidates.append(round_dir / route_id / "atom_decomposition.md")
    candidates.append(round_dir / "atom_decomposition.md")
    for path in candidates:
        if not path.is_file():
            continue
        rows = [
            line.rstrip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.lstrip().startswith("|")
        ]
        if len(rows) >= 2:  # 至少表头 + 分隔行
            keep = rows[: 2 + MAX_ATOM_ROWS]
            return "\n".join(keep)
    return ""


def collect_route_artifacts(round_dir: Path, route_id: str | None) -> tuple[dict, dict]:
    iters = {}
    knowledge = {}
    if route_id:
        iters = load_json(round_dir / route_id / "output" / "route_iterations.json")
        knowledge = load_json(round_dir / route_id / "knowledge_pool_update.json")
    return iters, knowledge


def build_card(round_dir: Path) -> dict:
    round_dir = Path(round_dir)
    op_dir = round_dir.parent
    op_name = find_op_name(op_dir)

    summary = load_json(round_dir / "summary.json")
    route_id, best_rr = pick_best_route(round_dir)
    iters, knowledge = collect_route_artifacts(round_dir, route_id)

    # 已证瓶颈结论：最优 route 诊断 + 各轮 bottleneck 标签（去重、限流）
    bottlenecks: list[str] = []
    diag = best_rr.get("bottleneck_diagnosis") or best_rr.get("bottleneck")
    if diag:
        bottlenecks.append(str(diag))
    for it in iters.get("iterations") or []:
        tag = it.get("bottleneck")
        if tag and tag not in bottlenecks:
            bottlenecks.append(str(tag))
    bottlenecks = bottlenecks[:MAX_BOTTLENECKS]

    # 已否方向：route 级证伪 + 参数级证伪（去重、限流）
    refuted: list[dict] = []
    for fals in best_rr.get("falsified_this_route") or []:
        refuted.append({"variant": fals.get("variant"), "evidence": fals.get("evidence")})
    for fals in knowledge.get("parameter_level_falsifications") or []:
        variant = f"{fals.get('scope', '')} {fals.get('variant', '')}".strip()
        if not any(f.get("variant") == variant for f in refuted):
            refuted.append({"variant": variant, "evidence": fals.get("conclusion") or fals.get("evidence")})
    refuted = refuted[:MAX_REFUTED]

    return {
        "source_round": summary.get("round_index") or best_rr.get("round_index"),
        "op_name": op_name,
        "best_route": route_id,
        "best_speedup": best_rr.get("best_speedup"),
        "atoms_md": extract_atom_table(round_dir, route_id),
        "proven_bottlenecks": bottlenecks,
        "refuted_directions": refuted,
        "encoding_active": knowledge.get("active_units") or (best_rr.get("knowledge") or {}).get("active_units") or [],
    }


def card_to_md(card: dict) -> str:
    """渲染 ≤30 行的 markdown 版卡片（人工审读用）。"""
    lines = [f"# 瓶颈卡片（承 round {card.get('source_round')}，best {card.get('best_route')} "
             f"speedup {card.get('best_speedup')}）"]
    if card.get("atoms_md"):
        atom_rows = card["atoms_md"].splitlines()
        lines.append("## 原子分解（继承，勿重推）")
        lines.extend(atom_rows[: 2 + MAX_ATOM_ROWS])
    if card.get("proven_bottlenecks"):
        lines.append("## 已证瓶颈")
        for b in card["proven_bottlenecks"][:MAX_BOTTLENECKS]:
            lines.append(f"- {b}")
    if card.get("refuted_directions"):
        lines.append("## 已否方向（勿再盲试）")
        for r in card["refuted_directions"][:MAX_REFUTED]:
            evidence = r.get("evidence") or ""
            lines.append(f"- {r.get('variant')}: {evidence}"[:200])
    return "\n".join(lines)


def count_md_lines(card: dict) -> int:
    return len(card_to_md(card).splitlines())


def main() -> int:
    parser = argparse.ArgumentParser(description="Round N B1 产物 -> 瓶颈卡片（B1-脚本）")
    parser.add_argument("--round-dir", required=True, help="opt-round-N 目录")
    parser.add_argument("--out", default=None, help="卡片 JSON 输出路径（默认 <round-dir>/bottleneck_card.json）")
    parser.add_argument("--md", default=None, help="可选：同时输出 markdown 渲染版路径")
    args = parser.parse_args()

    round_dir = Path(args.round_dir)
    if not round_dir.is_dir():
        sys.stdout.buffer.write((json.dumps(
        {"error": f"round dir not found: {round_dir}"}, indent=2) + "\n").encode("utf-8"))
        return 2

    card = build_card(round_dir)
    out = Path(args.out) if args.out else round_dir / "bottleneck_card.json"
    out.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.md:
        Path(args.md).write_text(card_to_md(card) + "\n", encoding="utf-8")
    sys.stdout.buffer.write((json.dumps({
        "card_path": str(out),
        "md_lines": count_md_lines(card),
        "best_route": card.get("best_route"),
        "bottlenecks": len(card["proven_bottlenecks"]),
        "refuted": len(card["refuted_directions"]),
        "atoms_inherited": bool(card.get("atoms_md")),
    }, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
