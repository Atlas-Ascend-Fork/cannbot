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
"""render_report.py — 从 route 的结构化 JSON 渲染 report.md（优化项④s）。

route 会话不再撰写 report.md（B7/④ 契约）；本脚本以固定章节结构渲染，数值全部来自 JSON：
  输入：--round-result round_result.json
        --iterations route_iterations.json（可选，缺省则迭代表省略）
        --knowledge knowledge_pool_update.json（可选）
        --manifest .task_manifest.json（可选，补充 fusion_plan/encoding 描述）
        --atom-file atom_decomposition.md（可选，仅引用路径）
  输出：--out report.md（缺省 stdout）

章节结构（与 golden 样例一致，顺序固定）：
  # 标题 / 基本信息 / 原子分解摘要 / E2 内部迭代记录 / 瓶颈分析 /
  知识-代码映射表 / 精英统计 / 知识价值评估与知识库更新 / 收敛检测（H0） / 最终交付

缺字段时对应行/表整体省略，不中断渲染。纯标准库实现（E1）。
"""

import argparse
import json
import sys
from pathlib import Path


def load_json(path: str | None) -> dict:
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def fmt(v, nd: int = 4) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}g}"
    return str(v)


def _render_basic_info(
    lines: list[str], round_result: dict, iterations: dict, manifest: dict, knowledge: dict,
) -> None:
    """Render the basic info section."""
    route_id = round_result.get("route_id", "route-?")
    strategy = round_result.get("round_strategy", "")
    lines.append("## 基本信息")
    lines.append("")
    device = iterations.get("device") or round_result.get("device")
    if device:
        lines.append(f"- **arch/device**: {device}")
    lines.append(f"- **route_id**: {route_id}（round_strategy={strategy}）")
    work_dir = round_result.get("work_dir") or manifest.get("work_dir")
    if work_dir:
        lines.append(f"- **work_dir**: `{work_dir}`")
    fusion = manifest.get("fusion_plan") or {}
    fusion_desc = fusion.get("description")
    if fusion_desc:
        lines.append(f"- **fusion_plan**: {fusion.get('fusion_id', round_result.get('fusion_id', ''))} {fusion_desc}")
    else:
        lines.append(f"- **fusion_plan**: {round_result.get('fusion_id', '-')}")
    active_units = (round_result.get("knowledge") or {}).get("active_units") or knowledge.get("active_units") or []
    if active_units:
        lines.append(f"- **知识编码（锁定，E2 三轮不变）**: {' / '.join(active_units)}")
    lines.append("")


def _render_atoms(lines: list[str], round_result: dict, atom_file: str | None) -> None:
    """Render the atom decomposition summary."""
    lines.append("## 原子分解摘要")
    lines.append("")
    atoms = round_result.get("atoms")
    if atoms:
        lines.append("| atom_id | op_type | formula | inputs | outputs | numerical_risk |")
        lines.append("|---------|---------|---------|--------|---------|----------------|")
        for a in atoms:
            lines.append("| " + " | ".join(
                str(a.get(k, "-")) for k in ("atom_id", "op_type", "formula", "inputs", "outputs", "numerical_risk")
            ) + " |")
    elif atom_file:
        lines.append(f"详见 `{atom_file}`。")
    lines.append("")


def _render_bottleneck(lines: list[str], round_result: dict, best_iter: dict | None) -> None:
    """Render the bottleneck analysis section."""
    lines.append("## 瓶颈分析（msprof 官方管道数据）")
    lines.append("")
    util = (best_iter or {}).get("utilization") or {}
    for kname, u in util.items():
        if isinstance(u, dict):
            parts = [f"- {kname}: mte2_ratio **{u.get('mte2', '-')}**，mac_ratio {u.get('mac', '-')}"]
            if u.get("cube_pct") is not None:
                parts.append(f"cube_utilization {u['cube_pct']}%")
            lines.append("，".join(parts))
    if not util and best_iter and best_iter.get("bottleneck"):
        lines.append(f"- {best_iter['bottleneck']}")
    diagnosis = round_result.get("bottleneck_diagnosis")
    if diagnosis:
        lines.append(f"- 结论：{diagnosis}")
    lines.append("")


def _render_knowledge_value(lines: list[str], round_result: dict, knowledge: dict, active_units: list) -> None:
    """Render the knowledge value assessment section."""
    lines.append("## 知识价值评估与知识库更新")
    lines.append("")
    deleted = knowledge.get("deleted_units") or (round_result.get("knowledge") or {}).get("deleted_units") or []
    lines.append(
        f"- active_units：{len(knowledge.get('active_units') or active_units or [])}，"
        f"deleted_units：{len(deleted)}"
    )
    for fals in knowledge.get("parameter_level_falsifications") or round_result.get("falsified_this_route") or []:
        variant = fals.get("variant") or fals.get("scope")
        evidence = fals.get("evidence") or fals.get("conclusion") or ""
        lines.append(f"- 参数级证伪：{variant}（{evidence}）")
    for insight in knowledge.get("new_insights") or []:
        lines.append(f"- 新知：{insight}")
    summary_txt = knowledge.get("kb_changes_summary")
    if summary_txt:
        lines.append(f"- KB 变更：{summary_txt}")
    distilled = (round_result.get("knowledge") or {}).get("distilled")
    if distilled is not None:
        lines.append(f"- G4 蒸馏：{'触发' if distilled else '不触发'}")
    lines.append("")


def _render_convergence(lines: list[str], round_result: dict) -> None:
    """Render the convergence detection section."""
    lines.append("## 收敛检测（H0）")
    lines.append("")
    conv = round_result.get("convergence") or {}
    if conv:
        changes = conv.get("last_2_rounds_change_pct")
        if changes:
            lines.append(f"- 最近 2 轮变化率：{'%，'.join(str(c) for c in changes)}%")
        ctype = conv.get("convergence_type")
        lines.append(f"- converged：**{conv.get('converged')}**" + (f"（{ctype}）" if ctype else ""))
        lines.append(
            f"- 最佳轮次 {conv.get('best_round', round_result.get('best_round', '-'))}，"
            f"best_task_duration_us="
            f"{conv.get('best_task_duration_us', round_result.get('best_task_duration_us', '-'))}"
        )
    note = conv.get("note")
    if note:
        lines.append(f"- 未收敛原因：{note}")
    lines.append("")


def _render_delivery(lines: list[str], round_result: dict, iterations: dict) -> None:
    """Render the final delivery section."""
    lines.append("## 最终交付")
    lines.append("")
    final_code = round_result.get("final_code") or round_result.get("code_path")
    if final_code:
        sha = round_result.get("final_code_sha256_16")
        sha_txt = f"（sha256-16={sha}）" if sha else ""
        lines.append(f"- 最终代码：`{final_code}`{sha_txt}")
    if round_result.get("verify_result"):
        lines.append(f"- verify：`{round_result['verify_result']}`（{round_result.get('precision', '')}）")
    if round_result.get("perf_result"):
        lines.append(f"- 性能：`{round_result['perf_result']}`")
    if iterations:
        lines.append("- 迭代数据：`output/route_iterations.json`")
    lines.append("")


def _parse_round_num(v) -> int | None:
    """兼容 1 / "1" / "E2-R1" 三种轮次写法。"""
    s = str(v)
    if "R" in s:
        s = s.rsplit("R", 1)[-1]
    try:
        return int(s)
    except ValueError:
        return None


def _render_iterations(lines: list[str], round_result: dict, iterations: dict) -> None:
    """Render the E2 internal iteration record."""
    iters = iterations.get("iterations") or round_result.get("iterations") or []
    if not iters:
        return
    lines.append("## E2 内部迭代记录")
    lines.append("")
    best_num = _parse_round_num(round_result.get("best_round") or iterations.get("best_round"))
    best_so_far = 0.0
    lines.append("| 轮次 | 变体 | 编译 | 精度 | k1(us) | k2(us) | Σ(us) | speedup | 判定 |")
    lines.append("|------|------|------|------|--------|--------|-------|---------|------|")
    for it in iters:
        is_best = best_num is not None and _parse_round_num(it.get("round")) == best_num
        speedup = it.get("speedup_vs_torch") or it.get("speedup")
        verdict = it.get("verdict")
        if not verdict:
            if is_best:
                verdict = "最优（保留）"
            elif best_so_far and speedup is not None:
                delta = (speedup - best_so_far) / best_so_far * 100
                verdict = f"{'提升' if delta >= 0 else '回归'} {delta:+.1f}%"
            else:
                verdict = "-"
        if speedup is not None:
            best_so_far = max(best_so_far, float(speedup))
        lines.append("| " + " | ".join([
            str(it.get("round", "-")),
            str(it.get("variant", "-"))[:80],
            str(it.get("compile", "-")),
            str(it.get("precision", "-")),
            fmt(it.get("task_duration_us_k1")),
            fmt(it.get("task_duration_us_k2")),
            fmt(it.get("task_duration_us_total")),
            ("**" + fmt(speedup) + "**") if is_best else fmt(speedup),
            str(verdict),
        ]) + " |")
    lines.append("")
    for note_key in ("duration_metric_note", "windows_note"):
        note = iterations.get(note_key)
        if note:
            lines.append(f"{note}  ")
    lines.append("")


def render(round_result: dict, iterations: dict, knowledge: dict, manifest: dict,
           atom_file: str | None) -> str:
    lines: list[str] = []
    route_id = round_result.get("route_id", "route-?")
    strategy = round_result.get("round_strategy", "")
    round_index = round_result.get("round_index")
    title_suffix = f"（gene-fusion, opt-round-{round_index}）" if round_index else "（gene-fusion）"
    lines.append(f"# {route_id} 报告 — {strategy}路线{title_suffix}")
    lines.append("")

    # ---- 基本信息
    _render_basic_info(lines, round_result, iterations, manifest, knowledge)

    # ---- 原子分解摘要
    _render_atoms(lines, round_result, atom_file)

    # ---- E2 内部迭代记录
    iters = iterations.get("iterations") or round_result.get("iterations") or []
    _render_iterations(lines, round_result, iterations)

    # ---- 瓶颈分析
    best_iter = next(
        (it for it in iters if str(it.get("round")) == str(round_result.get("best_round"))),
        iters[0] if iters else None,
    )
    _render_bottleneck(lines, round_result, best_iter)

    # ---- 知识-代码映射表
    attributions = round_result.get("gene_attributions") or {}
    if attributions:
        lines.append("## 知识-代码映射表")
        lines.append("")
        lines.append("| 基因 | 归因与验证状态 |")
        lines.append("|------|----------------|")
        for gid, note in attributions.items():
            lines.append(f"| {gid} | {note} |")
        lines.append("")

    # ---- 精英统计
    lines.append("## 精英统计")
    lines.append("")
    impl_vals = [it.get("impl_avg_ms") for it in iters if it.get("impl_avg_ms")]
    fw_vals = [it.get("framework_avg_ms") for it in iters if it.get("framework_avg_ms")]
    if impl_vals:
        impl_desc = f"- impl 延迟（各轮）：{min(impl_vals)}-{max(impl_vals)}ms"
        if fw_vals:
            impl_desc += f"；framework：{min(fw_vals)}-{max(fw_vals)}ms"
        lines.append(impl_desc)
    if round_result.get("impl_avg_latency_ms") is not None:
        lines.append(
            f"- 最优轮 impl {fmt(round_result.get('impl_avg_latency_ms'))}ms / framework "
            f"{fmt(round_result.get('framework_avg_latency_ms'))}ms"
            f" / speedup {fmt(round_result.get('best_speedup'))}"
        )
    if round_result.get("elite_retained"):
        lines.append("- 本 route 为精英保留路线")
    lines.append("")

    # ---- 知识价值评估与知识库更新
    active_units = (round_result.get("knowledge") or {}).get("active_units") or knowledge.get("active_units") or []
    _render_knowledge_value(lines, round_result, knowledge, active_units)

    # ---- 收敛检测
    _render_convergence(lines, round_result)

    # ---- 最终交付
    _render_delivery(lines, round_result, iterations)

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="route JSON -> report.md 渲染（④s）")
    parser.add_argument("--round-result", required=True, help="round_result.json 路径")
    parser.add_argument("--iterations", default=None, help="route_iterations.json 路径")
    parser.add_argument("--knowledge", default=None, help="knowledge_pool_update.json 路径")
    parser.add_argument("--manifest", default=None, help=".task_manifest.json 路径（可选）")
    parser.add_argument("--atom-file", default=None, help="atom_decomposition.md 路径（可选，仅引用）")
    parser.add_argument("--out", default=None, help="输出 report.md 路径（缺省 stdout）")
    args = parser.parse_args()

    round_result = load_json(args.round_result)
    if not round_result:
        sys.stderr.buffer.write((json.dumps(
        {"error": f"cannot read round_result: {args.round_result}"}, indent=2) + "\n").encode("utf-8"))
        return 2
    text = render(
        round_result,
        load_json(args.iterations),
        load_json(args.knowledge),
        load_json(args.manifest),
        args.atom_file,
    )
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.buffer.write((text + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
