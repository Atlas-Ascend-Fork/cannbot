# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Evidence-driven, single-candidate search over the existing workflow events.

Contracts own decisions, selection artifacts own observations, and workflow_state
owns all writes. This module neither runs experiments nor changes stopping goals.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from performance_effect_evidence import policy as effect_policy
from summarize_performance_effects import recompute_summary, summary_dependency_paths
from validate_schedule_contract import (
    ref,
    source_identity,
    verify_ref as verify_file_ref,
)


POLICY = {"id": "architecture_search_v1", "version": 1}
PATIENCE = 3
ROUND = r"(?:gen\.)?round[1-9]\d*"
OUTCOMES = (
    "measured",
    "implementation_failed",
    "precision_failed",
    "evidence_invalid",
    "no_candidate",
)
REPLAN_REASONS = ("plateau", "graph_exhausted", "gate_impasse", "architecture_limit")


def require(condition, message):
    if not condition:
        raise ValueError(f"search: {message}")


def load(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def verify_ref(value, dependencies):
    verify_file_ref(value, {})
    if value not in dependencies:
        dependencies.append(value)


def validate_policy(value):
    require(
        isinstance(value, dict)
        and value == POLICY
        and type(value.get("version")) is int,
        "unsupported search_policy",
    )
    return dict(value)


def enabled(manifest):
    config = manifest.get("configuration", {})
    request = manifest.get("request", {})
    if request.get("path"):
        verify_ref({k: request[k] for k in ("path", "sha256")}, [])
        frozen = load(request["path"])
        require(
            ("search_policy" in frozen) == ("search_policy" in config)
            and frozen.get("search_policy") == config.get("search_policy"),
            "policy differs from frozen request",
        )
    if "search_policy" not in config:
        return False
    validate_policy(config["search_policy"])
    return True


def checked_refs(values, label):
    require(isinstance(values, list) and values, f"{label} needs evidence references")
    dependencies = []
    for value in values:
        verify_ref(value, dependencies)
    return dependencies


def case_ids(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    ids = [
        next((row[k] for k in ("case_id", "id", "case", "name") if row.get(k)), None)
        for row in rows
    ]
    require(
        ids and all(ids) and len(ids) == len(set(ids)), "workload needs unique case IDs"
    )
    return ids


def validate_workload(contract, manifest, ids, dependencies):
    config = manifest["configuration"]
    key = (
        "generalization_full"
        if config.get("tuning_mode") == "generalization"
        else "performance_tuning"
    )
    inventory = manifest.get("collections", {}).get(key, {})
    frozen = {k: inventory[k] for k in ("path", "sha256") if k in inventory}
    verify_ref(frozen, dependencies)
    frozen_ids = case_ids(frozen["path"])
    require(set(ids) <= set(frozen_ids), "workload escapes frozen inventory")
    if key == "performance_tuning":
        require(ids == frozen_ids, "standard workload differs from frozen tuning set")
    require(
        contract.get("target_socs") == config.get("target_socs"),
        "target SoCs differ",
    )
    require(
        contract.get("backend", "ascendc") == config.get("backend", "ascendc"),
        "backend differs",
    )


def validate_parent(search, baseline):
    parent = search.get("parent")
    require(
        isinstance(parent, dict) and set(parent) == {"path", "sha256"},
        "missing parent source identity",
    )
    require(
        source_identity(Path(parent["path"])) == parent,
        "parent source identity changed",
    )
    if baseline is not None:
        require(
            source_identity(Path(baseline)) == parent,
            "implementation baseline differs from decision parent",
        )


def validate_contract(contract, manifest=None, baseline=None):
    """Validate metadata without inventing a second implementation contract."""
    required = manifest is not None and enabled(manifest)
    if "search" not in contract:
        require(not required, "implementation contract requires search metadata")
        return []
    search = contract["search"]
    require(isinstance(search, dict), "contract.search must be an object")
    require(search.get("kind") in ("architecture", "local"), "invalid decision kind")
    for name in ("mechanism", "mechanism_check"):
        require(
            isinstance(search.get(name), str) and search[name].strip(),
            f"missing {name}",
        )
    scheme = contract.get("scheme_id")
    require(
        isinstance(scheme, str) and re.fullmatch(r"[A-Za-z0-9_-]+", scheme),
        "invalid scheme_id",
    )
    parents = search.get("depends_on")
    require(
        isinstance(parents, list)
        and all(isinstance(x, str) and x for x in parents)
        and len(parents) == len(set(parents))
        and scheme not in parents,
        "dependencies must be unique decision IDs without self-dependency",
    )
    validate_parent(search, baseline)
    dependencies = checked_refs(search.get("trigger"), "trigger")
    for name in ("workload", "baseline_performance"):
        verify_ref(search.get(name), dependencies)
    ids = case_ids(search["workload"]["path"])
    require(
        contract.get("case_ids") == ids, "contract cases must match ordered workload"
    )
    require(
        case_ids(search["baseline_performance"]["path"]) == ids,
        "baseline performance coverage differs",
    )
    if manifest is not None:
        validate_workload(contract, manifest, ids, dependencies)
    retry = search.get("retry")
    if retry is not None:
        require(
            isinstance(retry, dict)
            and retry.get("decision_id")
            and retry.get("reason"),
            "invalid retry",
        )
        dependencies.extend(checked_refs(retry.get("evidence"), "retry"))
    return dependencies


def contracts(paths):
    found = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.suffix == ".json" and path.name.startswith("implementation-contract-"):
            found.append((path, load(path)))
    return found


def context(contract):
    search = contract["search"]
    value = {
        "parent": search["parent"],
        "workload": search["workload"]["sha256"],
        "socs": contract["target_socs"],
        "backend": contract.get("backend", "ascendc"),
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def reopened_decisions(decisions, reopen):
    affected = set(reopen)
    while True:
        children = {
            sid
            for sid, (_, contract) in decisions.items()
            if affected.intersection(contract["search"]["depends_on"])
        }
        if children <= affected:
            return affected
        affected |= children


def replay(state):
    """Rebuild counters and applicability; repeated checkpoints cannot add trials."""
    decisions, results, retired, accepted = {}, {}, set(), set()
    anchor, anchor_decision, streak, scope = None, None, 0, None
    action = "analyze"
    for event in state.get("events", []):
        kind = event.get("kind")
        if kind == "search_plan":
            contract = load(event["contract"]["path"])
            decisions[contract["scheme_id"]] = (event, contract)
            anchor = anchor or contract["search"]["parent"]
            action = "implement"
        elif kind == "search_result":
            result = event["result"]
            scheme = result.get("scheme_id")
            if scheme:
                results[scheme] = event
            if event.get("context") != scope:
                streak, scope = 0, event.get("context")
            if event["classification"] == "no_improvement":
                streak += 1
            if event.get("promoted"):
                anchor, anchor_decision = event["promoted"], scheme
                accepted.add(scheme)
                streak = 0
            action = {
                "inconclusive": "confirm",
                "evidence_invalid": "repair_evidence",
                "implementation_failed": "repair_candidate",
                "precision_failed": "repair_candidate",
                "no_candidate": "replan",
            }.get(event["classification"], "analyze")
            if streak >= PATIENCE:
                action = "replan"
        elif kind == "search_replan":
            retired |= reopened_decisions(decisions, event["reopen"])
            streak, scope, action = 0, None, "analyze"
    return {
        "decisions": decisions,
        "results": results,
        "retired": retired,
        "accepted": accepted,
        "anchor": anchor,
        "anchor_decision": anchor_decision,
        "stagnation": streak,
        "context": scope,
        "next_action": action,
    }


def append_once(state, event, key):
    for old in state.get("events", []):
        if old.get("kind") == event["kind"] and old.get(key) == event[key]:
            require(
                old == event,
                "checkpoint already recorded with different search evidence",
            )
            return False
    state.setdefault("events", []).append(event)
    return True


def validate_retry(current, contract):
    search = contract["search"]
    for prior_id, prior in reversed(list(current["results"].items())):
        previous = current["decisions"][prior_id][1]["search"]
        if (
            prior.get("context") == context(contract)
            and previous["mechanism"] == search["mechanism"]
            and prior["classification"]
            in (
                "no_improvement",
                "implementation_failed",
                "precision_failed",
                "evidence_invalid",
            )
        ):
            retry = search.get("retry", {})
            require(
                retry.get("decision_id") == prior_id,
                "retry needs the failed decision and changed conditions",
            )
            known = {r["sha256"] for r in prior["artifacts"]}
            require(
                any(r["sha256"] not in known for r in retry.get("evidence", [])),
                "retry needs new evidence",
            )
            break


def require_analysis_ready(state, current):
    require(
        not verify(state),
        "restore accepted search stages before freezing another decision",
    )
    require(
        state.get("stages", {}).get("phase.preparation", {}).get("status")
        == "complete",
        "preparation acceptance is incomplete",
    )
    finished = {
        e["round"] for e in state.get("events", []) if e.get("kind") == "search_result"
    }
    require(
        all(e["round"] in finished for e, _ in current["decisions"].values()),
        "complete the current round before freezing another decision",
    )
    require(
        current["next_action"] != "replan",
        "architecture review required before another decision",
    )


def register_analysis(state, stage, paths, manifest):
    found = contracts(paths)
    require(len(found) <= 1, "each round may freeze only one implementation contract")
    if not enabled(manifest) or not found:
        return []
    path, contract = found[0]
    dependencies = validate_contract(contract, manifest)
    current = replay(state)
    scheme = contract["scheme_id"]
    round_name = stage.removesuffix(".analysis")
    old = current["decisions"].get(scheme)
    if old:
        require(
            old[0]["contract"] == ref(path) and old[0]["round"] == round_name,
            "decision IDs are immutable and round-specific",
        )
        return dependencies
    require_analysis_ready(state, current)
    search = contract["search"]
    if current["anchor"]:
        require(
            search["parent"] == current["anchor"],
            "decision parent is not the retained implementation",
        )
    require(
        set(search["depends_on"]) <= current["accepted"] - current["retired"],
        "dependencies must be accepted, applicable decisions",
    )
    validate_retry(current, contract)
    for event, _ in current["decisions"].values():
        require(
            event["round"] != round_name,
            "round already has a decision; replan in the next round",
        )
    event = {
        "kind": "search_plan",
        "round": round_name,
        "contract": ref(path),
        "artifacts": [ref(path), *dependencies],
        "sources": [search["parent"]],
    }
    append_once(state, event, "round")
    return dependencies


def check_handoff(state, stage):
    match = re.fullmatch(rf"({ROUND})\.impl\.([^.]+)", stage)
    if not match or "search_policy" not in state:
        return
    current = replay(state)
    entry = current["decisions"].get(match[2])
    require(
        entry and entry[0]["round"] == match[1], "scheme was not frozen for this round"
    )
    analysis = state.get("stages", {}).get(f"{match[1]}.analysis", {})
    require(
        analysis.get("status") == "complete"
        and any(
            a["path"] == entry[0]["contract"]["path"]
            and a["sha256"] == entry[0]["contract"]["sha256"]
            for a in analysis.get("artifacts", [])
        ),
        "analysis handoff is missing or invalid",
    )
    require(
        match[2] not in current["retired"],
        "decision was reopened; re-analyze its dependencies",
    )
    require(
        entry[1]["search"]["parent"] == current["anchor"], "retained parent changed"
    )
    require(
        set(entry[1]["search"]["depends_on"])
        <= current["accepted"] - current["retired"],
        "decision depends on a reopened mechanism",
    )


def checked_summary(reference, manifest):
    dependencies = []
    verify_ref(reference, dependencies)
    summary = load(reference["path"])
    frozen = effect_policy(manifest["configuration"].get("performance_effect_policy"))
    actual = effect_policy(
        {
            "id": summary.get("policy_id", "legacy_jitter_v1"),
            "version": summary.get("policy_version", 1),
        }
    )
    require(actual == frozen, "effect policy differs from manifest")
    computed = recompute_summary(summary)
    require(
        all(summary.get(k) == v for k, v in computed.items()),
        "effect summary differs from evidence",
    )
    paths = [
        summary["baseline_path"],
        summary["candidate_path"],
        *summary_dependency_paths(summary),
    ]
    dependencies.extend(ref(p) for p in paths)
    return summary, dependencies


def classify(summary):
    if summary.get("inconclusive_case_count", 0):
        return "inconclusive"
    if (
        summary.get("effective_improvement_count", 0)
        and (summary.get("effective_geomean_speedup") or 0) > 1
    ):
        return "improvement"
    return "no_improvement"


def round_plan(state, current, round_name):
    analysis = state.get("stages", {}).get(f"{round_name}.analysis", {})
    require(analysis.get("status") == "complete", "round analysis is incomplete")
    plan = next(
        (
            entry
            for entry in current["decisions"].values()
            if entry[0]["round"] == round_name
        ),
        None,
    )
    if plan:
        recorded = any(
            e.get("kind") == "search_result" and e["round"] == round_name
            for e in state.get("events", [])
        )
        require(
            recorded or plan[1]["scheme_id"] not in current["retired"],
            "decision was reopened; re-analyze before evaluation",
        )
    return plan


def round_selection(record, plan):
    selections = [
        a for a in record["artifacts"] if Path(a["path"]).name == "selection.json"
    ]
    require(len(selections) == 1, "round requires one selection.json")
    selection = selections[0]
    result = load(selection["path"]).get("search")
    require(
        isinstance(result, dict) and result.get("outcome") in OUTCOMES,
        "selection.search needs an outcome",
    )
    expected = plan[1]["scheme_id"] if plan else None
    require(
        result.get("scheme_id") == expected,
        "selection decision differs from round contract",
    )
    require(
        (result["outcome"] == "no_candidate") == (plan is None),
        "no_candidate requires an analysis without a contract",
    )
    artifacts = [
        ref(selection["path"]),
        *checked_refs(result.get("evidence"), "outcome"),
    ]
    mechanism = result.get("mechanism", {})
    require(
        mechanism.get("status") in ("verified", "refuted", "unknown"),
        "invalid mechanism verdict",
    )
    if mechanism["status"] != "unknown":
        artifacts.extend(checked_refs(mechanism.get("evidence"), "mechanism"))
    require(
        isinstance(result.get("retry_condition"), str)
        and result["retry_condition"].strip(),
        "outcome needs a retry condition or an evidence-backed not_applicable reason",
    )
    return result, artifacts


def accepted_implementation(state, plan, gate_ref, artifacts):
    event, contract = plan
    stage = f"{event['round']}.impl.{contract['scheme_id']}"
    implementation = state.get("stages", {}).get(stage, {})
    require(
        implementation.get("status") == "complete",
        "implementation acceptance is incomplete",
    )
    require(
        any(
            a["path"] == gate_ref["path"] and a["sha256"] == gate_ref["sha256"]
            for a in implementation.get("artifacts", [])
        ),
        "gate absent from accepted implementation",
    )
    artifacts.extend(
        {k: a[k] for k in ("path", "sha256")}
        for a in implementation["artifacts"]
        if a.get("kind") == "file"
    )


def candidate_gate(state, plan, result, artifacts):
    from validate_implementation_conformance import verify_gate

    gate_ref = result.get("conformance_gate")
    verify_ref(gate_ref, artifacts)
    gate = verify_gate(Path(gate_ref["path"]))
    identity = gate["evidence_identity"]
    require(
        identity["contract"] == plan[0]["contract"], "gate belongs to another decision"
    )
    require(identity["baseline"] == plan[1]["search"]["parent"], "gate parent differs")
    artifacts.extend(
        identity[name] for name in ("contract", "result", "manifest", "isolation_scope")
    )
    artifacts.extend(
        {"path": p, "sha256": sha} for p, sha in identity["feature_evidence"].items()
    )
    schedule = gate.get("schedule")
    if schedule:
        artifacts.extend(schedule[name] for name in ("model", "runtime"))
        artifacts.extend(
            {"path": p, "sha256": sha}
            for p, sha in schedule["report"]["dependencies"].items()
        )
    accepted_implementation(state, plan, gate_ref, artifacts)
    return identity


def checked_measurement(result, manifest, contract, identity, artifacts):
    summary, dependencies = checked_summary(result.get("effect_summary"), manifest)
    artifacts.extend(dependencies)
    require(
        ref(summary["baseline_path"]) == contract["search"]["baseline_performance"],
        "comparison uses a different baseline",
    )
    require(
        [c["case_id"] for c in summary["cases"]] == contract["case_ids"],
        "effect coverage differs",
    )
    for case in summary["cases"]:
        if not case.get("proof_path"):
            continue
        proof = load(case["proof_path"])
        require(
            proof["target_soc"] in contract["target_socs"],
            "performance proof targets another SoC",
        )
        for side in ("baseline", "candidate"):
            measured_source = proof["source_identities"][proof[f"{side}_variant"]][
                "source"
            ]
            require(
                Path(measured_source["path"]).resolve() == Path(identity[side]["path"]),
                f"performance proof belongs to another {side} implementation",
            )
    require(
        classify(summary) != "inconclusive",
        "comparison is inconclusive; confirm before completing this round",
    )
    return summary


def candidate_selection(record, result, summary, candidate, manifest, baseline_names):
    selected = record["performance"]["selected_candidate"]
    classification = classify(summary)
    if selected not in (result["scheme_id"], candidate["path"]):
        require(
            selected in baseline_names,
            "selection is neither the candidate nor the retained baseline",
        )
        # Ratio/retreat/complexity selection remains owned by the stage's existing policy.
        return "no_improvement", None
    require(classification == "improvement", "promotion needs measured net improvement")
    if manifest["configuration"].get("tuning_mode", "standard") == "standard":
        require(
            all(
                c["speedup"] >= 0.70
                for c in summary["cases"]
                if c["classification"] == "effective_regression"
            ),
            "candidate exceeds the per-case retreat limit",
        )
    require(
        ref(record["performance"]["round_summary"]) == result["effect_summary"],
        "promoted performance differs from evaluated candidate",
    )
    return classification, candidate


def retained_summary(record, manifest, plan, artifacts):
    kept, dependencies = checked_summary(
        ref(record["performance"]["round_summary"]), manifest
    )
    artifacts.extend(dependencies)
    if plan:
        require(
            ref(kept["baseline_path"]) == plan[1]["search"]["baseline_performance"],
            "retained comparison uses another baseline",
        )
    require(
        all(c["baseline_total_us"] == c["candidate_total_us"] for c in kept["cases"]),
        "retained baseline must use its own performance evidence",
    )


def complete_round(state, stage, record, manifest):
    """Consume the one decision's outcome, including a rejected candidate's evidence."""
    if not enabled(manifest):
        return []
    current = replay(state)
    round_name = stage.removesuffix(".complete")
    require(
        not verify(state), "restore accepted search stages before completing the round"
    )
    plan = round_plan(state, current, round_name)
    result, artifacts = round_selection(record, plan)
    classification, promoted = result["outcome"], None
    sources = [plan[1]["search"]["parent"]] if plan else []
    baseline_names = {"baseline", current["anchor_decision"]}
    if current["anchor"]:
        baseline_names.add(current["anchor"]["path"])
    if result["outcome"] == "measured":
        identity = candidate_gate(state, plan, result, artifacts)
        summary = checked_measurement(result, manifest, plan[1], identity, artifacts)
        sources.append(identity["candidate"])
        classification, promoted = candidate_selection(
            record, result, summary, identity["candidate"], manifest, baseline_names
        )
    else:
        require(
            record["performance"]["selected_candidate"] in baseline_names,
            "unevaluated candidate cannot be promoted",
        )
    if promoted is None:
        retained_summary(record, manifest, plan, artifacts)
    event = {
        "kind": "search_result",
        "round": round_name,
        "result": result,
        "classification": classification,
        "context": context(plan[1]) if plan else None,
        "promoted": promoted,
        "artifacts": artifacts,
        "sources": sources,
    }
    append_once(state, event, "round")
    return artifacts


def replan(state, reason, reopen, evidence, message):
    require(
        reason in REPLAN_REASONS and message.strip(),
        "replan needs a reason and diagnosis",
    )
    current = replay(state)
    require(set(reopen) <= set(current["decisions"]), "unknown reopened decision")
    finished = {
        e["round"] for e in state.get("events", []) if e.get("kind") == "search_result"
    }
    require(
        all(e["round"] in finished for e, _ in current["decisions"].values()),
        "complete the active round before architecture review",
    )
    artifacts = checked_refs([ref(p) for p in evidence], "replan")
    event = {
        "kind": "search_replan",
        "reason": reason,
        "reopen": sorted(set(reopen)),
        "message": message,
        "artifacts": artifacts,
        "sources": [],
        "after_round": next(
            (
                e["round"]
                for e in reversed(state.get("events", []))
                if e.get("kind") == "search_result"
            ),
            None,
        ),
    }
    if event in state.get("events", []):
        return
    if reason == "plateau":
        require(
            current["stagnation"] >= PATIENCE,
            "plateau needs three comparable unsuccessful evaluations",
        )
    state.setdefault("events", []).append(event)


def event_owners(event):
    if event["kind"] == "search_plan":
        return [f"{event['round']}.analysis"]
    if event["kind"] != "search_result":
        return []
    owners = [f"{event['round']}.complete"]
    if event["result"]["outcome"] == "measured":
        owners.append(f"{event['round']}.impl.{event['result']['scheme_id']}")
    return owners


def verify(state, *, check_stages=True):
    errors = []
    for event in state.get("events", []):
        if not event.get("kind", "").startswith("search_"):
            continue
        owners = event_owners(event) if check_stages else []
        errors.extend(
            {
                "kind": "search_stage",
                "stage": stage,
                "reason": f"search acceptance invalidated: {stage}",
            }
            for stage in owners
            if state.get("stages", {}).get(stage, {}).get("status") != "complete"
        )
        try:
            for artifact in event.get("artifacts", []):
                verify_ref(artifact, [])
            for source in event.get("sources", []):
                require(
                    source_identity(Path(source["path"])) == source,
                    "search source changed",
                )
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(
                {
                    "kind": "search_evidence",
                    "round": event.get("round"),
                    "reason": str(error),
                }
            )
    return errors


def view(state):
    if "search_policy" not in state:
        return None
    errors = verify(state)
    if errors:
        return {"next_action": "repair_evidence", "errors": errors}
    current = replay(state)
    action = (
        "complete"
        if state.get("terminal", {}).get("status") == "success"
        else current["next_action"]
    )
    return {
        "next_action": action,
        "stagnation": current["stagnation"],
        "patience": PATIENCE,
        "anchor": current["anchor"],
        "accepted_decisions": sorted(current["accepted"]),
        "reopened_decisions": sorted(current["retired"]),
        "observations": [
            {
                "decision_id": sid,
                "classification": e["classification"],
                "mechanism": e["result"]["mechanism"],
                "retry_condition": e["result"]["retry_condition"],
            }
            for sid, e in current["results"].items()
        ],
    }
