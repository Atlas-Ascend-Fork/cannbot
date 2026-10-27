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
"""validate_round_result.py — H1 结果语义质检（规则化，替代父会话真推理质检）。

Round 2+ 无父化后，route 产物在入池/进化前由本脚本做规则质检：

  1. precision_pass        精度必须 PASS（validation.precision / 最优迭代轮）——不 PASS 拒收
  2. speedup_bounds        best_speedup 越界 [min,max]（默认 [0.3, 3.0]）——越界拒收
  3. code_sha256           代码文件存在、非空；round_result 自报 code_sha256 时比对——不一致拒收
  4. iterations_consistent best_speedup 落在 iterations 速度范围内——越界标 suspicious
  5. anchor_deviation      带锚臂数据（cross_window_anchor）时偏差超阈值标 suspicious
  6. proposed_genes_shape  route 提案的新基因（下沉契约）结构范围校验——畸形标 suspicious

输出 verdict JSON 到 stdout，exit 0=accepted / 1=rejected / 2=用法或 IO 错误。
suspicious 只标记不拒收；拒收项由调用方（orchestrator/父会话）负责剔除该 route。
可选兜底：每 K 轮一次轻量审计小模型会话（复用 H2 prose_render 通道，调用方编排）。
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_SPEEDUP_MIN = 0.3
DEFAULT_SPEEDUP_MAX = 3.0
DEFAULT_ANCHOR_TOLERANCE = 0.15

# proposed_genes 单元允许的基因类别（与 round.md C0 基因编码空间一致）
ALLOWED_CATEGORIES = {"tiling", "memory", "compute", "pipeline", "vectorization", "structural"}
REQUIRED_PROPOSED_FIELDS = {"gene_id", "category", "description", "bottleneck_tag", "hypothesis"}


def _is_precision_pass(round_result: dict) -> tuple[bool, str]:
    """validation.precision 是权威判定；仅其缺失时回退最优迭代轮。"""
    validation = round_result.get("validation") or {}
    precision = str(validation.get("precision", ""))
    if precision:
        return precision.upper().startswith("PASS"), f"validation.precision={precision}"
    best_round = round_result.get("best_round")
    for it in round_result.get("iterations") or []:
        if best_round is not None and it.get("round") == best_round:
            if str(it.get("precision", "")).upper().startswith("PASS"):
                return True, f"validation 未填，best iteration {best_round} precision=PASS 兜底"
    return False, f"validation.precision 缺失且 best_round={best_round} 无 PASS 迭代"


def _check_speedup_bounds(best_speedup, lo: float, hi: float) -> tuple[bool, str]:
    if not isinstance(best_speedup, (int, float)) or best_speedup <= 0:
        return False, f"best_speedup={best_speedup!r} 非正数"
    if not (lo <= best_speedup <= hi):
        return False, f"best_speedup={best_speedup} 越界 [{lo}, {hi}]"
    return True, f"best_speedup={best_speedup} ∈ [{lo}, {hi}]"


def _check_code_sha256(round_result: dict, work_dir: Path | None) -> tuple[str, str, str | None]:
    """返回 (status, detail, computed_sha)；status ∈ pass/mismatch/reject/skipped。"""
    code_path = round_result.get("code_path")
    if not code_path:
        return "reject", "round_result 缺 code_path", None
    # work_dir 相对候选优先(R3 实测缺陷): code_path 以 CWD 优先解析曾致 route
    # 质检 sha 错配; 调用方在 route 目录内运行时, work_dir 解析才是权威路径。
    candidates: list[Path] = []
    if work_dir is not None:
        candidates.append(work_dir / code_path)
        candidates.append(work_dir / Path(code_path).name)
    candidates.append(Path(code_path))
    code_file = next((c for c in candidates if c.is_file()), None)
    if code_file is None:
        return "reject", f"代码文件不存在: {code_path}", None
    try:
        data = code_file.read_bytes()
    except OSError as exc:
        return "reject", f"代码文件不可读: {exc}", None
    if not data:
        return "reject", f"代码文件为空: {code_file}", None
    computed = hashlib.sha256(data).hexdigest()
    claimed = round_result.get("code_sha256")
    if claimed:
        if str(claimed).lower().startswith(computed[: len(str(claimed))]):
            return "pass", f"sha256 一致（{computed[:16]}…）", computed
        return "mismatch", f"自报 code_sha256={claimed} 与实际 {computed[:16]}… 不一致", computed
    return "pass", f"已计算 sha256（{computed[:16]}…，route 未自报，供回填）", computed


def _check_iterations_consistent(round_result: dict) -> tuple[str, str]:
    iters = round_result.get("iterations") or []
    speeds = [it.get("speedup") for it in iters if isinstance(it.get("speedup"), (int, float))]
    best = round_result.get("best_speedup")
    if not speeds or not isinstance(best, (int, float)):
        return "suspicious", "iterations 缺 speedup 数据，无法核验自洽"
    if best < min(speeds) - 1e-9:
        return "suspicious", f"best_speedup={best} 小于 iterations 最小值 {min(speeds)}"
    if best > max(speeds) + 1e-9:
        return "suspicious", f"best_speedup={best} 大于 iterations 最大值 {max(speeds)}，疑似虚高"
    return "pass", f"best_speedup={best} 与 iterations（{len(speeds)} 轮）自洽"


def _check_anchor(round_result: dict, tolerance: float) -> tuple[str, str]:
    anchor = round_result.get("cross_window_anchor")
    if not isinstance(anchor, dict):
        return "skipped", "无跨窗锚臂数据（G5 允许：声明不可比或未引用他方数字）"
    local = anchor.get("anchor_speedup_local")
    remote = anchor.get("anchor_speedup_remote")
    if not (isinstance(local, (int, float)) and isinstance(remote, (int, float))) or remote <= 0:
        return "suspicious", f"锚臂数据畸形: {anchor}"
    deviation = abs(local - remote) / remote
    if deviation > tolerance:
        return "suspicious", f"锚臂偏差 {deviation:.1%} 超阈值 {tolerance:.0%}，跨窗数字可疑"
    return "pass", f"锚臂偏差 {deviation:.1%} ≤ {tolerance:.0%}"


def _check_proposed_genes(round_result: dict) -> tuple[str, str]:
    knowledge = round_result.get("knowledge") or {}
    proposed = knowledge.get("proposed_genes")
    if proposed is None:
        return "skipped", "route 未提案新基因"
    if not isinstance(proposed, list):
        return "suspicious", f"proposed_genes 应为 list，得到 {type(proposed).__name__}"
    for i, gene in enumerate(proposed):
        if not isinstance(gene, dict):
            return "suspicious", f"proposed_genes[{i}] 非对象"
        missing = REQUIRED_PROPOSED_FIELDS - set(gene)
        if missing:
            return "suspicious", f"proposed_genes[{i}] 缺字段 {sorted(missing)}"
        if gene.get("category") not in ALLOWED_CATEGORIES:
            return "suspicious", f"proposed_genes[{i}].category={gene.get('category')!r} 不在允许类别"
    return "pass", f"{len(proposed)} 条提案结构合规" if proposed else "空提案列表"


def main() -> int:
    parser = argparse.ArgumentParser(description="H1 结果语义质检：规则化校验 route 的 round_result.json")
    parser.add_argument("--round-result", required=True, help="round_result.json 路径")
    parser.add_argument("--work-dir", default=None, help="route 工作目录（code_path 相对解析）")
    parser.add_argument("--speedup-min", type=float, default=DEFAULT_SPEEDUP_MIN,
                        help=f"speedup 拒收下界，默认 {DEFAULT_SPEEDUP_MIN}")
    parser.add_argument("--speedup-max", type=float, default=DEFAULT_SPEEDUP_MAX,
                        help=f"speedup 拒收上界，默认 {DEFAULT_SPEEDUP_MAX}")
    parser.add_argument("--anchor-tolerance", type=float, default=DEFAULT_ANCHOR_TOLERANCE,
                        help=f"锚臂偏差 suspicious 阈值，默认 {DEFAULT_ANCHOR_TOLERANCE}")
    args = parser.parse_args()

    rr_path = Path(args.round_result)
    try:
        round_result = json.loads(rr_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stdout.buffer.write((json.dumps(
            {"accepted": False, "error": f"round_result 不可读: {exc}"},
            ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return 2

    work_dir = Path(args.work_dir) if args.work_dir else rr_path.parent

    checks: list[dict] = []

    ok, detail = _is_precision_pass(round_result)
    checks.append({"name": "precision_pass", "status": "pass" if ok else "reject", "detail": detail})

    ok, detail = _check_speedup_bounds(round_result.get("best_speedup"), args.speedup_min, args.speedup_max)
    checks.append({"name": "speedup_bounds", "status": "pass" if ok else "reject", "detail": detail})

    status, detail, computed = _check_code_sha256(round_result, work_dir)
    checks.append({"name": "code_sha256", "status": status, "detail": detail})

    status, detail = _check_iterations_consistent(round_result)
    checks.append({"name": "iterations_consistent", "status": status, "detail": detail})

    status, detail = _check_anchor(round_result, args.anchor_tolerance)
    checks.append({"name": "anchor_deviation", "status": status, "detail": detail})

    status, detail = _check_proposed_genes(round_result)
    checks.append({"name": "proposed_genes_shape", "status": status, "detail": detail})

    rejected = any(c["status"] in ("reject", "mismatch") for c in checks)
    suspicious = [c["name"] for c in checks if c["status"] == "suspicious"]
    verdict = {
        "accepted": not rejected,
        "route_id": round_result.get("route_id"),
        "round_index": round_result.get("round_index"),
        "rejected": [c["name"] for c in checks if c["status"] in ("reject", "mismatch")],
        "suspicious": suspicious,
        "checks": checks,
        "code_sha256_computed": computed,
    }
    sys.stdout.buffer.write((json.dumps(
        verdict, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
