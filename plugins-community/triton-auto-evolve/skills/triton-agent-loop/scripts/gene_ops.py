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
"""gene_ops.py — gene-fusion 基因操作脚本化（优化项 A1，含 G1/G2/G6 登记表）。

把父 CLI（gene-fusion worker）在 G0-G4/G6 的确定性部分全部脚本化，直接操作 gene_pool.json：

  select          适应度比例选择 + 精英保留（--elite-count）
  crossover       单点/均匀交叉（--crossover-rate）
  mutate          参数扰动/基因替换/删除（--mutation-rate）
  update-fitness  route 结果写入适应度（平滑更新 + G6 卡间归一化 + G1 指纹登记 + G2 自动禁用）
  manifest        为每条 route 生成 manifest JSON 的结构化字段（叙述性 desc 留给调用方）
  combo-hash      组合指纹：排序后基因 id 集合的 sha256 前 16（G1）
  ban-gene        负面基因硬排除登记（G2）
  pool-init       Round 1 C0 产出 -> 初始基因池骨架

内置三张登记表（存在 gene_pool.json 内，缺键自动补全）：
  tested_combos: {combo_hash: {fitness, round, gene_ids}}     （G1 已测组合指纹去重）
  banned_genes:  [{gene_id, reason, round}]                    （G2 负面基因硬排除）
  card_offsets:  {card_id: offset_pct}                         （G6 卡间基线归一化，初始 0）

所有子命令输出 JSON（stdout）；写池操作需显式 --in-place 或 --out，避免误写。
纯标准库实现（禁止 import torch/pandas，优化项 E1）。
"""

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------- 基础工具


def load_pool(path: Path) -> dict:
    """读取 gene_pool.json 并补全登记表缺键。"""
    pool = json.loads(Path(path).read_text(encoding="utf-8"))
    pool.setdefault("genes", [])
    pool.setdefault("tested_combos", {})
    pool.setdefault("banned_genes", [])
    pool.setdefault("card_offsets", {})
    return pool


def pool_text(pool: dict) -> str:
    return json.dumps(pool, indent=2, ensure_ascii=False) + "\n"


def save_pool(pool: dict, out: Path | None, in_place: Path | None) -> None:
    if in_place is not None:
        Path(in_place).write_text(pool_text(pool), encoding="utf-8")
    elif out is not None:
        Path(out).write_text(pool_text(pool), encoding="utf-8")


def gene_by_id(pool: dict, gene_id: str) -> dict | None:
    for gene in pool["genes"]:
        if gene.get("gene_id") == gene_id:
            return gene
    return None


def banned_ids(pool: dict) -> set[str]:
    return {b.get("gene_id") for b in pool.get("banned_genes", [])}


def combo_hash(gene_ids: list[str]) -> str:
    """G1：排序后基因 id 集合的 sha256 前 16。"""
    return hashlib.sha256(",".join(sorted(gene_ids)).encode("utf-8")).hexdigest()[:16]


def conflicts_ok(pool: dict, gene_ids: list[str]) -> bool:
    """互斥基因不得共存于同一路线。"""
    chosen = set(gene_ids)
    for gid in gene_ids:
        gene = gene_by_id(pool, gid)
        if gene and set(gene.get("conflicts_with") or []) & chosen:
            return False
    return True


def filter_banned(pool: dict, gene_ids: list[str]) -> list[str]:
    """G2：硬过滤负面基因。"""
    banned = banned_ids(pool)
    return [g for g in gene_ids if g not in banned]


def eligible_genes(pool: dict, include_candidates: bool = False) -> list[dict]:
    """可选基因：非 banned 且（active 或按要求含 candidate）。"""
    banned = banned_ids(pool)
    allowed_status = {"active"}
    if include_candidates:
        allowed_status.add("candidate")
    return [
        g
        for g in pool["genes"]
        if g.get("gene_id") not in banned and g.get("status", "active") in allowed_status
    ]

# ---------------------------------------------------------------- G1 指纹


def lookup_tested_combo(pool: dict, gene_ids: list[str]) -> dict | None:
    """命中已测组合则返回 {fitness, round}，调用方直接继承、不再派发。"""
    return pool.get("tested_combos", {}).get(combo_hash(gene_ids))


def record_tested_combo(pool: dict, gene_ids: list[str], fitness: float, round_index: int) -> None:
    pool.setdefault("tested_combos", {})[combo_hash(gene_ids)] = {
        "fitness": fitness,
        "round": round_index,
        "gene_ids": sorted(gene_ids),
    }

# ---------------------------------------------------------------- G6 归一化


def normalize_speedup(pool: dict, speedup: float, card_id: str | None) -> float:
    """G6：适应度入库按 speedup / (1 + offset_pct/100) 归一（offset 由同代码跨卡实测差维护）。"""
    if not card_id:
        return speedup
    offset_pct = float(pool.get("card_offsets", {}).get(card_id, 0) or 0)
    return speedup / (1.0 + offset_pct / 100.0)

# ---------------------------------------------------------------- G1 选择 / G2 交叉 / G3 变异


def weight_of(gene: dict) -> float:
    fitness = gene.get("fitness")
    if isinstance(fitness, (int, float)) and fitness > 0:
        return float(fitness)
    return 1.0  # fitness 为 null（含全 null 池）-> 等权重


def select_combo(pool: dict, rng: random.Random, k_min: int = 2, k_max: int = 5,
                 include_candidates: bool = False) -> list[str]:
    """适应度比例选择（有放回抽基因直到满足数量约束），保证互斥约束与去重。"""
    candidates = eligible_genes(pool, include_candidates=include_candidates)
    if not candidates:
        return []
    weights = [weight_of(g) for g in candidates]
    k = rng.randint(k_min, k_max)
    chosen: list[str] = []
    attempts = 0
    while len(chosen) < min(k, len(candidates)) and attempts < 200:
        attempts += 1
        gid = rng.choices([g["gene_id"] for g in candidates], weights=weights, k=1)[0]
        if gid in chosen:
            continue
        if not conflicts_ok(pool, chosen + [gid]):
            continue
        chosen.append(gid)
    return chosen


def elite_combo(pool: dict, last_best_gene_ids: list[str]) -> list[str]:
    """精英保留：上轮最优基因组合直接存活（剔除 banned，保持其余不变）。"""
    return filter_banned(pool, list(last_best_gene_ids))


def _cross_gene_params(pool: dict, gid: str, parent_a: list[str], parent_b: list[str],
                       rng: random.Random) -> dict:
    """单个基因的参数交叉：逐键 0.5 概率取另一方同名基因的参数值。"""
    new_params = dict((gene_by_id(pool, gid) or {}).get("params") or {})
    for key in list(new_params):
        other = _param_from_lists(pool, parent_a, parent_b, gid, key)
        if rng.random() < 0.5 and other is not None:
            new_params[key] = other
    return new_params


def _cross_params(pool: dict, parent_a: list[str], parent_b: list[str], fixed: list[str], rng: random.Random) -> dict:
    """参数交叉：同名基因参数不同时交叉参数值（逐键 0.5 概率取另一方）。"""
    crossed_params: dict[str, dict] = {}
    for gid in fixed:
        if gid in parent_a and gid in parent_b:
            crossed_params[gid] = _cross_gene_params(pool, gid, parent_a, parent_b, rng)
    return crossed_params


def crossover(pool: dict, parent_a: list[str], parent_b: list[str], rate: float,
              rng: random.Random) -> dict:
    """均匀交叉（p=0.5/位，经 rate 门控）+ 互斥修复 + 参数交叉。

    同名基因参数不同时交叉参数值（逐键 0.5 概率取另一方）。
    """
    if rng.random() >= rate:
        return {"executed": False, "child": filter_banned(pool, list(parent_a)), "params": {}}
    child: list[str] = []
    for a, b in zip(parent_a, parent_b):
        pick = a if rng.random() < 0.5 else b
        if pick not in child:
            child.append(pick)
    child += [g for g in parent_a[len(parent_b):] if g not in child]
    child += [g for g in parent_b[len(parent_a):] if g not in child]
    child = filter_banned(pool, child)
    # 互斥修复：按序保留可共存子集
    fixed: list[str] = []
    for gid in child:
        if conflicts_ok(pool, fixed + [gid]):
            fixed.append(gid)
    crossed_params = _cross_params(pool, parent_a, parent_b, fixed, rng)
    return {"executed": True, "child": fixed, "params": crossed_params}


def _param_from_lists(pool: dict, list_a: list[str], list_b: list[str], gid: str, key: str):
    for lst in (list_a, list_b):
        gene = gene_by_id(pool, gid)
        params = (gene or {}).get("params") or {}
        if key in params and gid in lst:
            return params[key]
    return None


def _mutate_param(gene: dict, gid: str, rng: random.Random, mutations: list[dict]) -> None:
    """参数扰动（±50%）。"""
    key = rng.choice(list(gene["params"]))
    value = gene["params"][key]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        new_value = value * rng.uniform(0.5, 1.5)
        if isinstance(value, int):
            new_value = max(1, int(round(new_value)))
        gene["params"][key] = new_value
        mutations.append({"gene": gid, "op": "param_mutation", "change": f"params.{key}: {value} -> {new_value}"})
    else:
        mutations.append({"gene": gid, "op": "param_mutation_skipped_nonnumeric", "change": f"params.{key}"})


@dataclass
class ReplaceCtx:
    """Working state for a gene-replacement mutation step."""

    pool: dict
    rng: random.Random
    result_ids: list[str]
    mutations: list[dict]


def _replace_gene(ctx: ReplaceCtx, gid: str, gene_ids: list[str]) -> bool:
    """尝试用候选基因替换；返回 True 如果替换成功。"""
    pool_candidates = [
        g["gene_id"]
        for g in eligible_genes(ctx.pool, include_candidates=True)
        if g["gene_id"] not in ctx.result_ids and g["gene_id"] not in gene_ids
    ]
    if pool_candidates:
        repl = ctx.rng.choice(pool_candidates)
        if conflicts_ok(ctx.pool, ctx.result_ids + [repl]):
            ctx.mutations.append({"gene": gid, "op": "gene_replace", "change": f"{gid} -> {repl}"})
            ctx.result_ids.append(repl)
            return True
    return False


def mutate(pool: dict, gene_ids: list[str], rate: float, rng: random.Random) -> dict:
    """变异：参数扰动（±50%）/ 基因删除；kb_guides 来源基因变异率减半。

    候补基因来自池内未入组的 active 基因（低概率替换）。
    """
    mutations: list[dict] = []
    result_ids: list[str] = []
    for gid in gene_ids:
        gene = gene_by_id(pool, gid)
        if gene is None:
            result_ids.append(gid)
            continue
        eff_rate = rate * (0.5 if gene.get("source") == "kb_guides" else 1.0)
        if rng.random() >= eff_rate:
            result_ids.append(gid)
            continue
        op = rng.choices(["param", "drop", "replace"], weights=[0.6, 0.2, 0.2], k=1)[0]
        if op == "param" and gene.get("params"):
            _mutate_param(gene, gid, rng, mutations)
            result_ids.append(gid)
        elif op == "drop":
            mutations.append({"gene": gid, "op": "gene_drop", "change": "removed from combo"})
        else:
            if not _replace_gene(ReplaceCtx(pool, rng, result_ids, mutations), gid, gene_ids):
                result_ids.append(gid)
    return {"genes": result_ids, "mutations": mutations}

# ---------------------------------------------------------------- G6 适应度更新


def _update_gene_fitness(pool: dict, res: dict, gene_ids: list[str], normalized: float,
                         smooth_old: float, round_index: int, log: list[dict]) -> None:
    """把归一化适应度写入各基因（指数平滑更新 + candidate 晋升/淘汰判定）。"""
    for gid in gene_ids:
        gene = gene_by_id(pool, gid)
        if gene is None:
            continue
        old = gene.get("fitness")
        new_fitness = normalized if old is None else smooth_old * float(old) + (1 - smooth_old) * normalized
        gene["fitness"] = round(new_fitness, 6)
        gene.setdefault("fitness_history", []).append({"round": round_index, "fitness": gene["fitness"]})
        if gene.get("status") == "candidate":
            gene["status"] = "active" if normalized >= float(pool.get("best_speedup") or 0) else "discarded"
            log.append({"route_id": res.get("route_id"), "gene": gid, "action": gene["status"]})


def _ban_rejected_genes(pool: dict, res: dict, gene_ids: list[str],
                        round_index: int, log: list[dict]) -> None:
    """G2：route 判废（status=rejected）时把未登记的基因加入负面登记。"""
    if (res.get("status") or "success").lower() != "rejected":
        return
    reason = res.get("reject_reason") or "route verdict rejected"
    existing = banned_ids(pool)
    for gid in gene_ids:
        if gid not in existing:
            pool.setdefault("banned_genes", []).append(
                {"gene_id": gid, "reason": reason, "round": round_index}
            )
            log.append({"route_id": res.get("route_id"), "gene": gid, "action": "banned"})


def _update_one_route(pool: dict, res: dict, smooth_old: float,
                      round_index: int, log: list[dict]) -> None:
    """单条 route 结果的适应度更新（G6 归一 + G1 登记 + G2 禁用）。"""
    gene_ids = filter_banned(pool, res.get("gene_ids") or [])
    speedup = res.get("speedup")
    status = (res.get("status") or "success").lower()
    if speedup is None or status in ("failed", "timeout", "error"):
        log.append({"route_id": res.get("route_id"), "action": "skipped", "reason": f"status={status}"})
        return
    normalized = normalize_speedup(pool, float(speedup), res.get("card_id"))
    _update_gene_fitness(pool, res, gene_ids, normalized, smooth_old, round_index, log)
    _ban_rejected_genes(pool, res, gene_ids, round_index, log)
    record_tested_combo(pool, gene_ids, float(speedup), round_index)
    pool["route_results"].append({
        "route_id": res.get("route_id"),
        "gene_ids": gene_ids,
        "speedup": speedup,
        "normalized_speedup": round(normalized, 6),
        "card_id": res.get("card_id"),
        "status": status,
        "round": round_index,
    })


def update_fitness(pool: dict, route_results: list[dict], smooth_old: float = 0.3,
                   round_index: int = 0) -> dict:
    """route 结果 -> 适应度写入（G6 归一 + G1 登记 + G2 禁用）。"""
    log: list[dict] = []
    pool.setdefault("route_results", [])
    for res in route_results:
        _update_one_route(pool, res, smooth_old, round_index, log)
    return {"log": log}

# ---------------------------------------------------------------- manifest 结构化字段


@dataclass
class ManifestSpec:
    """Inputs for building a route manifest's structured fields."""

    pool: dict
    route_id: str
    route_type: str
    work_dir: str
    baseline_dir: str
    gene_ids: list[str]
    op_name: str
    round_index: int
    hypothesis: str = ""
    direction: str = ""


def build_manifest_fields(spec: ManifestSpec) -> dict:
    """round.md §6.1 manifest 的结构化字段（叙述性 desc 留给调用方）。"""
    pool, route_id, route_type = spec.pool, spec.route_id, spec.route_type
    work_dir, baseline_dir = spec.work_dir, spec.baseline_dir
    gene_ids, op_name, round_index = spec.gene_ids, spec.op_name, spec.round_index
    hypothesis, direction = spec.hypothesis, spec.direction
    genes = []
    verified = []
    for gid in gene_ids:
        gene = gene_by_id(pool, gid) or {}
        genes.append({
            "gene_id": gid,
            "ku_id": gene.get("ku_id"),
            "category": gene.get("category"),
            "description": gene.get("description"),
            "params": gene.get("params") or {},
        })
        code_sha = (gene.get("verified_code") or {}).get("sha256_16")
        if code_sha:
            verified.append({"gene_ids": sorted(set(gene_ids)), "sha256_16": code_sha,
                             "fitness": gene.get("fitness")})
    inherited = lookup_tested_combo(pool, gene_ids)
    manifest = {
        "op_name": op_name,
        "round_index": round_index,
        "work_dir": work_dir,
        "baseline_dir": baseline_dir,
        "algorithm": "gene-fusion-route",
        "algorithm_reference": ".claude/references/algorithms/gene-fusion/route.md",
        "route_id": route_id,
        "round_strategy": route_type,
        "hypothesis": hypothesis,
        "direction": direction,
        "evidence_sources": ["gene_pool", "fusion_plan"],
        "optimization_genes": genes,
        "genetic_metadata": {
            "generation": pool.get("generation"),
            "gene_ids": list(gene_ids),
            "route_type": route_type,
        },
        # B2 去重继承：已验证代码清单（sha256-16 -> 适应度）
        "gene_pool": {"verified_codes": verified},
    }
    if inherited:
        manifest["genetic_metadata"]["inherited"] = {
            "combo_hash": combo_hash(gene_ids),
            "fitness": inherited.get("fitness"),
            "round": inherited.get("round"),
        }
    # B1 瓶颈卡片透传（transition 生成 bottleneck_card.json 时由调用方合并）
    return manifest

# ---------------------------------------------------------------- CLI


def _add_select_parser(sub) -> None:
    p = sub.add_parser("select", help="适应度比例选择 + 精英保留")
    p.add_argument("--gene-pool", required=True)
    p.add_argument("--elite-gene-ids", default="", help="上轮最优基因 id 列表（逗号分隔），非空时输出精英组")
    p.add_argument("--elite-count", type=int, default=1)
    p.add_argument("--k-min", type=int, default=2)
    p.add_argument("--k-max", type=int, default=5)
    p.add_argument("--include-candidates", action="store_true")
    p.add_argument("--picks", type=int, default=2, help="除精英外再抽的组合数")
    p.add_argument("--seed", type=int, default=None)


def _add_crossover_parser(sub) -> None:
    p = sub.add_parser("crossover", help="均匀交叉 + 参数交叉")
    p.add_argument("--gene-pool", required=True)
    p.add_argument("--parent-a", required=True, help="逗号分隔基因 id")
    p.add_argument("--parent-b", required=True, help="逗号分隔基因 id")
    p.add_argument("--crossover-rate", type=float, default=0.7)
    p.add_argument("--seed", type=int, default=None)


def _add_mutate_parser(sub) -> None:
    p = sub.add_parser("mutate", help="参数扰动/基因替换/删除")
    p.add_argument("--gene-pool", required=True)
    p.add_argument("--genes", required=True, help="逗号分隔基因 id")
    p.add_argument("--mutation-rate", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--in-place", action="store_true", help="变异直接写回池（参数变异需入库）")


def _add_update_fitness_parser(sub) -> None:
    p = sub.add_parser("update-fitness", help="route 结果写入适应度（G6 归一 + G1 登记 + G2 禁用）")
    p.add_argument("--gene-pool", required=True)
    p.add_argument("--routes", required=True, help="route 结果 JSON 文件路径或内联 JSON 数组")
    p.add_argument("--smooth-old", type=float, default=0.3)
    p.add_argument("--round-index", type=int, default=0)
    p.add_argument("--out", default=None)
    p.add_argument("--in-place", action="store_true")


def _add_manifest_parser(sub) -> None:
    p = sub.add_parser("manifest", help="生成 route manifest 结构化字段")
    p.add_argument("--gene-pool", required=True)
    p.add_argument("--route-id", required=True)
    p.add_argument("--route-type", default="exploration", choices=["elite", "crossover", "exploration"])
    p.add_argument("--work-dir", required=True)
    p.add_argument("--baseline-dir", required=True)
    p.add_argument("--gene-ids", required=True, help="逗号分隔基因 id")
    p.add_argument("--op-name", required=True)
    p.add_argument("--round-index", type=int, required=True)
    p.add_argument("--hypothesis", default="")
    p.add_argument("--direction", default="")
    p.add_argument("--bottleneck-card", default=None, help="bottleneck_card.json 路径，存在则合并进 manifest")
    p.add_argument("--out", default=None)


def _add_combo_hash_parser(sub) -> None:
    p = sub.add_parser("combo-hash", help="G1 组合指纹")
    p.add_argument("--genes", required=True)


def _add_ban_gene_parser(sub) -> None:
    p = sub.add_parser("ban-gene", help="G2 负面基因硬排除登记")
    p.add_argument("--gene-pool", required=True)
    p.add_argument("--gene", required=True)
    p.add_argument("--reason", default="")
    p.add_argument("--round-index", type=int, default=0)
    p.add_argument("--out", default=None)
    p.add_argument("--in-place", action="store_true")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="gene-fusion 基因操作脚本（A1/G1/G2/G6）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    _add_select_parser(sub)
    _add_crossover_parser(sub)
    _add_mutate_parser(sub)
    _add_update_fitness_parser(sub)
    _add_manifest_parser(sub)
    _add_combo_hash_parser(sub)
    _add_ban_gene_parser(sub)
    return parser.parse_args()


def _ids(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def _routes(raw: str) -> list[dict]:
    if raw.strip().startswith("["):
        return json.loads(raw)
    return json.loads(Path(raw).read_text(encoding="utf-8"))


def _cmd_select(args, pool, rng) -> None:
    out = {"elite": [], "picks": [], "tested_hits": []}
    last_best = _ids(args.elite_gene_ids)
    if last_best:
        out["elite"] = elite_combo(pool, last_best)
    for _ in range(args.picks):
        combo = select_combo(pool, rng, args.k_min, args.k_max, args.include_candidates)
        if combo:
            out["picks"].append(combo)
    for combo in [out["elite"]] + out["picks"]:
        if combo:
            hit = lookup_tested_combo(pool, combo)
            if hit:
                out["tested_hits"].append({"gene_ids": combo, "combo_hash": combo_hash(combo),
                                           "fitness": hit.get("fitness"), "round": hit.get("round")})
    sys.stdout.buffer.write((json.dumps(out, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _cmd_crossover(args) -> None:
    pool = load_pool(args.gene_pool)
    result = crossover(pool, _ids(args.parent_a), _ids(args.parent_b), args.crossover_rate, random.Random(args.seed))
    result["combo_hash"] = combo_hash(result["child"])
    result["tested_hit"] = lookup_tested_combo(pool, result["child"])
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _cmd_mutate(args) -> None:
    pool = load_pool(args.gene_pool)
    result = mutate(pool, _ids(args.genes), args.mutation_rate, random.Random(args.seed))
    if args.in_place:
        Path(args.gene_pool).write_text(pool_text(pool), encoding="utf-8")
    result["combo_hash"] = combo_hash(result["genes"])
    result["tested_hit"] = lookup_tested_combo(pool, result["genes"])
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _cmd_update_fitness(args) -> None:
    pool = load_pool(args.gene_pool)
    summary = update_fitness(pool, _routes(args.routes), args.smooth_old, args.round_index)
    save_pool(pool, args.out, Path(args.gene_pool) if args.in_place else None)
    sys.stdout.buffer.write((json.dumps(summary, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _cmd_manifest(args) -> None:
    pool = load_pool(args.gene_pool)
    manifest = build_manifest_fields(ManifestSpec(
        pool=pool, route_id=args.route_id, route_type=args.route_type, work_dir=args.work_dir,
        baseline_dir=args.baseline_dir, gene_ids=_ids(args.gene_ids), op_name=args.op_name,
        round_index=args.round_index, hypothesis=args.hypothesis, direction=args.direction,
    ))
    if args.bottleneck_card and Path(args.bottleneck_card).is_file():
        manifest["bottleneck_card"] = json.loads(Path(args.bottleneck_card).read_text(encoding="utf-8"))
    text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))


def _cmd_ban_gene(args) -> None:
    pool = load_pool(args.gene_pool)
    if args.gene not in banned_ids(pool):
        pool.setdefault("banned_genes", []).append(
            {"gene_id": args.gene, "reason": args.reason, "round": args.round_index}
        )
    save_pool(pool, args.out, Path(args.gene_pool) if args.in_place else None)
    sys.stdout.buffer.write((json.dumps(
        {"banned": sorted(banned_ids(pool))}, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


_CMD_HANDLERS = {
    "select": lambda args: _cmd_select(args, load_pool(args.gene_pool), random.Random(args.seed)),
    "crossover": _cmd_crossover,
    "mutate": _cmd_mutate,
    "update-fitness": _cmd_update_fitness,
    "manifest": _cmd_manifest,
    "combo-hash": lambda args: sys.stdout.buffer.write(
        (json.dumps({"combo_hash": combo_hash(_ids(args.genes))}, indent=2) + "\n").encode("utf-8")),
    "ban-gene": _cmd_ban_gene,
}


def main() -> int:
    args = _parse_args()
    _CMD_HANDLERS[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
