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

"""Plan candidates or associate evidence with an existing candidate frontier.

The implementation-stage --frontier mode consumes the analysis handoff without
regenerating candidates or rerunning models. This does not write workflow-state;
the main agent registers artifacts at existing workflow stage checkpoints.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from . import candidates as search_candidates
from . import evidence as search_evidence
from . import observe as search_observation
from . import selection as search_selection
from . import policy as search_policy
from . import prior
from . import proxy
from . import attribution as search_attribution


def _write(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path.resolve())


def _ranking_from(record, path):
    if isinstance(record.get("ranking"), list):
        return [str(item) for item in record["ranking"]]
    if path:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        ranking = payload.get("ranking") if isinstance(payload, dict) else payload
        if not isinstance(ranking, list):
            raise ValueError(
                "prefilter ranking must be a JSON list or {ranking: [...]}"
            )
        return [str(item) for item in ranking]
    return None


def run_l1_prefilter(frontier, args, out, *, accepted=()):
    """Run the OpModel prefilter between candidate generation and measurement.

    Coverage is the number of generated candidates submitted to the model.
    Pruning only happens when a scheme-level ranking artifact exists; dag_run
    ranks schedules, not our scheme ids, so its default output records
    budget_skipped=0 instead of inventing an ordering.
    """
    backend = getattr(args, "prefilter_backend", None)
    command = getattr(args, "prefilter_command", None)
    if not backend and not command:
        return frontier, None
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import search_prefilter

    original_nodes = list(frontier.get("nodes", []))

    prefilter_out = Path(
        getattr(args, "prefilter_out", None) or (out / "prefilter")
    ).resolve()
    record = search_prefilter.run_prefilter(
        frontier,
        backend=backend or "dag_run",
        model=getattr(args, "prefilter_model", None),
        out_dir=prefilter_out,
        extra=getattr(args, "prefilter_arg", []) or (),
        command=command,
        timeout=int(getattr(args, "prefilter_timeout", 600)),
    )
    candidate_count = len(frontier.get("nodes", []))
    record["candidate_count"] = candidate_count
    record["budget_skipped"] = 0
    record["pruned"] = []

    ranking = _ranking_from(record, getattr(args, "prefilter_ranking", None))
    top_k = int(getattr(args, "prefilter_top_k", 0) or 0)
    validation = getattr(args, "prefilter_validation", None)
    if record.get("status") == "applied" and ranking and top_k > 0:
        if validation is None:
            record["prune_skipped_reason"] = (
                "device ranking validation report required; ranking is advisory"
            )
            top_k = 0
        else:
            # Analysis reviews applicability and device-ranking agreement. Keep
            # its existing report in the same SHA-checked L1 evidence chain.
            validation_ref = search_policy.ref(validation)
            record["ranking_validation"] = validation_ref
            record.setdefault("evidence", []).extend(
                search_policy.checked_refs(
                    [validation_ref], "prefilter ranking validation"
                )
            )
    ranking_path = getattr(args, "prefilter_ranking", None)
    unmapped = {item["scheme_id"] for item in record.get("unmapped", [])}
    if ranking_path:
        record.setdefault("evidence", []).append(search_policy.ref(ranking_path))
        payload = json.loads(Path(ranking_path).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            unmapped.update(item["scheme_id"] for item in payload.get("unmapped", []))
    if record.get("status") == "applied" and ranking and top_k > 0:
        nodes = frontier.get("nodes", [])
        order = {scheme: index for index, scheme in enumerate(ranking)}
        ranked = sorted(
            (node for node in nodes if node.get("scheme_id") in order),
            key=lambda node: order[node["scheme_id"]],
        )
        keep = ranked[:top_k]
        keep += [
            node
            for node in nodes
            if (
                node.get("explore_tag") == "open"
                or node["scheme_id"] not in order
                or node["scheme_id"] in unmapped
            )
            and node not in keep
        ]
        minimum = math.ceil(frontier.get("n", 3) / frontier.get("p_pass", 0.5))
        if len(keep) < minimum:
            record["prune_skipped_reason"] = (
                f"ranking leaves {len(keep)} candidates, below frontier minimum {minimum}"
            )
        else:
            known = {node.get("scheme_id") for node in keep}
            record["pruned"] = [
                node.get("scheme_id")
                for node in nodes
                if node.get("scheme_id") not in known
            ]
            record["budget_skipped"] = len(record["pruned"])
            frontier = dict(frontier)
            frontier["nodes"] = keep

    fragment = {
        key: record.get(key)
        for key in (
            "status",
            "tool",
            "backend",
            "coverage",
            "budget_skipped",
            "candidate_count",
            "pruned",
            "reason",
            "returncode",
            "prune_skipped_reason",
            "ranking_validation",
            "evidence",
            "command",
        )
        if record.get(key) is not None
    }
    frontier = dict(frontier)
    frontier["prefilter"] = dict(frontier.get("prefilter", {}))
    frontier["prefilter"]["l1"] = fragment
    if record.get("status") == "applied":
        try:
            search_policy.validate_frontier(frontier, accepted=accepted)
        except (ValueError, KeyError, TypeError) as error:
            if record.get("pruned"):
                frontier["nodes"] = frontier["nodes"] + [
                    node
                    for node in original_nodes
                    if node.get("scheme_id") in set(record["pruned"])
                ]
                record["prune_skipped_reason"] = f"pruned frontier invalid: {error}"
                record["pruned"] = []
                record["budget_skipped"] = 0
                frontier["prefilter"]["l1"] = {
                    key: record.get(key)
                    for key in (
                        "status",
                        "tool",
                        "backend",
                        "coverage",
                        "budget_skipped",
                        "candidate_count",
                        "pruned",
                        "prune_skipped_reason",
                        "evidence",
                    )
                    if record.get(key) is not None
                }
                search_policy.validate_frontier(frontier, accepted=accepted)
            else:
                raise
    path = _write(out / "prefilter.json", record)
    return frontier, path


def base_factors(space_path):
    space = json.loads(Path(space_path).read_text(encoding="utf-8"))
    return {axis["name"]: axis["values"][0] for axis in space.get("axes", [])}


def acquisition_filter(frontier, history, soc, top_k=None, beta=0.5, *, accepted=()):
    """Original prior/proxy ranking, with the existing frontier constraints."""
    ranked = proxy.rank(history, frontier["nodes"], soc=soc, beta=beta)
    record = {"ranking": ranked, "pruned": []}
    if not top_k:
        return frontier, record
    keep = {item["scheme_id"] for item in ranked[:top_k]}
    keep.update(
        node["scheme_id"] for node in frontier["nodes"] if node["explore_tag"] == "open"
    )
    filtered = {
        **frontier,
        "nodes": [node for node in frontier["nodes"] if node["scheme_id"] in keep],
    }
    try:
        search_policy.validate_frontier(filtered, accepted=accepted)
    except ValueError as error:
        record["prune_skipped_reason"] = str(error)
        return frontier, record
    record["pruned"] = [
        node["scheme_id"] for node in frontier["nodes"] if node["scheme_id"] not in keep
    ]
    return filtered, record


def filter_combo_stage(frontier, stage, base):
    """Stage 0: <=1 changed axis; stage 1: exactly 2; stage 2: >=3.

    The current frontier is kept when the staged subset would fall below the
    measured-candidate minimum; the supplement is recorded, never hidden.
    """
    if stage is None or stage < 0:
        return frontier, None
    nodes = list(frontier.get("nodes", []))
    changed = {
        node.get("scheme_id"): sum(
            1
            for name, value in (node.get("factors") or {}).items()
            if base.get(name) != value
        )
        for node in nodes
    }
    want = (
        (lambda c: c <= 1)
        if stage == 0
        else (lambda c: c == 2)
        if stage == 1
        else (lambda c: c >= 3)
    )
    keep = [
        node
        for node in nodes
        if node.get("explore_tag") == "open" or want(changed[node.get("scheme_id")])
    ]
    minimum = math.ceil(frontier.get("n", 3) / frontier.get("p_pass", 0.5))
    supplemented = []
    if len(keep) < minimum:
        chosen = {node.get("scheme_id") for node in keep}
        for node in sorted(nodes, key=lambda item: changed[item.get("scheme_id")]):
            if len(keep) >= minimum:
                break
            if node.get("scheme_id") not in chosen:
                keep.append(node)
                supplemented.append(node.get("scheme_id"))
    filtered = dict(frontier)
    filtered["nodes"] = keep
    filtered["combo_stage"] = stage
    record = {
        "stage": stage,
        "kept": len(keep),
        "supplemented": supplemented,
        "changed_axis_counts": sorted(set(changed.values())),
    }
    return filtered, record


def run(args):
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    supplied_frontier = getattr(args, "frontier", None)
    accepted = search_policy.accepted_from_state(getattr(args, "state", None))
    contract = search_policy.load(args.contract) if args.contract else None
    stage_record = None
    prefilter_path = None
    acquisition_path = None
    history_paths = getattr(args, "history_state", []) or []
    history = prior.read_history(history_paths) if history_paths else []
    if supplied_frontier:
        search_policy.require(contract is not None, "--frontier requires --contract")
        search_policy.require(
            not args.dry_run, "--frontier consumes evidence; use --space for planning"
        )
        frontier_path = str(Path(supplied_frontier).resolve())
        frontier = search_policy.load(frontier_path)
        search_policy.validate_frontier(frontier, contract, accepted=accepted)
    else:
        search_policy.require(
            args.space and args.parent and args.trigger and args.best_us is not None,
            "candidate generation requires --space, --parent, --trigger and --best-us",
        )
        frontier = search_candidates.build(
            args.space.resolve(),
            args.parent,
            args.trigger,
            args.round,
            args.best_us,
            args.n,
            args.p_pass,
            args.max_candidates,
            args.method,
            accepted=accepted,
        )
        stage = getattr(args, "combo_stage", -1)
        if stage == "auto":
            match = re.fullmatch(r"(?:gen\.)?round([1-9][0-9]*)", args.round)
            search_policy.require(
                match is not None, "auto combo stage requires roundN or gen.roundN"
            )
            stage = min(2, int(match[1]) - 1)
        else:
            stage = int(stage) if stage is not None else -1
        if stage is not None and stage >= 0:
            frontier, stage_record = filter_combo_stage(
                frontier, stage, base_factors(args.space)
            )
            _write(out / "combo-stage.json", stage_record)
        frontier["base_factors"] = base_factors(args.space)
        if history_paths:
            search_policy.require(
                getattr(args, "soc", None), "history ranking requires --soc"
            )
            frontier, acquisition = acquisition_filter(
                frontier,
                history,
                args.soc,
                getattr(args, "top_k", None),
                getattr(args, "beta", 0.5),
                accepted=accepted,
            )
            acquisition["history"] = [
                {"contract": item["contract"], "effect_summary": item["effect_summary"]}
                for item in history
            ]
            acquisition_path = _write(out / "acquisition.json", acquisition)
        frontier, prefilter_path = run_l1_prefilter(
            frontier, args, out, accepted=accepted
        )
        if contract is not None:
            search_policy.validate_frontier(frontier, contract, accepted=accepted)
        frontier_path = _write(out / "candidate-frontier.json", frontier)
    if args.dry_run:
        return {
            "status": "planned",
            "frontier": frontier_path,
            "prefilter": prefilter_path,
            "acquisition": acquisition_path,
            "combo_stage": stage_record,
        }
    search_policy.require(
        args.evidence_index,
        "provide --evidence-index after collecting with the existing profiling workflow",
    )

    def adapt(index_path):
        payload = search_evidence.build(index_path.resolve(), frontier)
        if supplied_frontier:
            search_policy.require(
                all(
                    item["scheme_id"] == contract["scheme_id"]
                    for item in payload["candidates"]
                ),
                "frontier evidence must belong to the current contract scheme",
            )
        return payload

    measurements = adapt(args.evidence_index)
    measurements_path = _write(out / "measurements.json", measurements)
    holdout_path = None
    if args.holdout_evidence_index:
        holdout = adapt(args.holdout_evidence_index)
        holdout_path = _write(out / "holdout-measurements.json", holdout)
    observation = search_observation.build(
        measurements_path,
        frontier_path,
        holdout_path,
    )
    observation_path = _write(out / "observation.json", observation)
    attribution_path = None
    if getattr(args, "attribution", False):
        search_policy.require(
            "base_factors" in frontier,
            "attribution needs base_factors from the analysis frontier",
        )
        if getattr(args, "state", None):
            history = prior.read_history([args.state])
        current_schemes = {candidate["scheme_id"] for candidate in measurements["candidates"]}
        compatible = []
        for item in history:
            if item["parent"] != frontier["parent"] or item["workload"] != measurements["case_source"]:
                continue
            if item["scheme_id"] not in current_schemes:
                compatible.append(item)
        attribution = search_attribution.build(
            measurements, frontier, frontier["base_factors"], compatible
        )
        attribution_path = _write(out / "attribution.json", attribution)
    selection_path = None
    if args.selection and args.gate and args.effect_summary:
        merged = search_selection.build(
            args.selection.resolve(),
            observation_path,
            observation.get("recommended"),
            args.gate,
            args.effect_summary,
            [Path(item).resolve() for item in args.evidence],
            args.mechanism_status,
            [Path(item).resolve() for item in args.mechanism_evidence],
            args.retry_condition,
            replace=args.replace,
        )
        selection_path = _write(args.selection, merged)
    return {
        "status": "completed",
        "frontier": frontier_path,
        "measurements": measurements_path,
        "combo_stage": stage_record,
        "acquisition": acquisition_path,
        "attribution": attribution_path,
        "holdout_measurements": holdout_path,
        "observation": observation_path,
        "selection": selection_path,
        "ready_for_confirmation": observation.get("ready_for_confirmation"),
        "confirmation_blocker": observation.get("confirmation_blocker"),
        "no_go": observation.get("no_go", []),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--space", type=Path, help="generate candidates from this space"
    )
    source.add_argument(
        "--frontier", type=Path, help="consume the analysis frontier without replanning"
    )
    parser.add_argument(
        "--state", type=Path, help="workflow state for accepted dependencies"
    )
    parser.add_argument("--parent", type=Path)
    parser.add_argument("--trigger", type=Path)
    parser.add_argument("--round", default="round1")
    parser.add_argument("--best-us", type=float)
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--p-pass", type=float, default=0.5)
    parser.add_argument("--max-candidates", type=int, default=64)
    parser.add_argument("--method", choices=("cartesian", "pairwise"))
    parser.add_argument("--evidence-index", type=Path)
    parser.add_argument("--holdout-evidence-index", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--gate", type=Path)
    parser.add_argument("--effect-summary", type=Path)
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument(
        "--mechanism-status",
        choices=("verified", "refuted", "unknown"),
        default="unknown",
    )
    parser.add_argument("--mechanism-evidence", action="append", default=[])
    parser.add_argument("--retry-condition")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--prefilter-backend", choices=("dag_run", "graph_search", "agent_search")
    )
    parser.add_argument("--prefilter-model", type=Path)
    parser.add_argument("--prefilter-command")
    parser.add_argument("--prefilter-out", type=Path)
    parser.add_argument("--prefilter-ranking", type=Path)
    parser.add_argument(
        "--prefilter-validation",
        type=Path,
        help="analysis-reviewed device ranking calibration report; required for L1 pruning",
    )
    parser.add_argument("--prefilter-top-k", type=int, default=0)
    parser.add_argument("--prefilter-timeout", type=int, default=600)
    parser.add_argument("--prefilter-arg", action="append", default=[])
    parser.add_argument(
        "--combo-stage", choices=("-1", "0", "1", "2", "auto"), default="-1"
    )
    parser.add_argument(
        "--history-state",
        type=Path,
        action="append",
        default=[],
        help="existing workflow state to learn from; repeat for prior runs",
    )
    parser.add_argument("--soc", help="target SoC for historical ranking")
    parser.add_argument(
        "--top-k", type=int, help="optional prior/proxy candidate budget"
    )
    parser.add_argument("--beta", type=float, default=0.5)
    parser.add_argument(
        "--attribution", action="store_true", help="write advisory failure attribution"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = run(args)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(
            json.dumps({"status": "invalid", "reason": str(error)}, ensure_ascii=False)
        )
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
