# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""CPU behavior tests using raw launches, not trusted reported confidence intervals."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import namedtuple
from pathlib import Path
import statistics
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "ops-perf-optimize-workflow" / "scripts"))
from performance_effect_evidence import build_proof, receipt, verify_proof, policy
from summarize_performance_effects import summarize, recompute_summary
from workflow_state import prepare_performance, recorded_performance, artifact_identity, performance_report
from validate_postprocess_performance import validate


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")
    return path


def csvfile(path, columns, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _artifact(root, name, content="immutable"):
    p = root / name
    p.parent.mkdir(exist_ok=True, parents=True)
    p.write_text(content)
    return receipt(p)


def _default_deltas(shared):
    if shared:
        return [-.7] * 6
    return [-.6, -.9, -.5, -.7, -.8, -.65, -.95, -.75, -.45, -1.0]


def _variant_artifacts(root, variant_names):
    refs, variants = {}, {}
    for variant in variant_names:
        source_file = _artifact(root, f"source-{variant}/kernel.py", variant)
        h = hashlib.sha256()
        h.update(b"kernel.py\0" + source_file["sha256"].encode() + b"\0")
        source = {"path": str(root / f"source-{variant}"), "sha256": h.hexdigest(),
                  "identity_method": "source-tree-v1", "file_count": 1, "files": [source_file]}
        normal = {k: _artifact(root, f"normal-{variant}-{k}", "binary" if k in ("built", "live") else variant)
                  for k in ("generated", "built", "live")}
        refs[variant] = {"source": source, "reference_artifacts": normal, "kernel_sequence": {"case_id": "t1"}}
        variants[variant] = {"source": source, **normal}
    return refs, variants


def _effect_plan(identity, snapshot, deltas, shared):
    plan = {"effect_case_id": "t1", "soc": "Ascend950", "physical_device": 3, "snapshot": snapshot,
            "expected_identity": receipt(identity), "samples_per_case": 10, "round_count": len(deltas),
            "baseline_variant": "baseline", "candidate_variant": "candidate",
            "original_precision_contract": {"status": "strict_pass", "rtol": 0, "atol": 0},
            "statistical_method": {"id": "python_mt19937_percentile_median_v1", "confidence": .95,
                                   "statistic": "median", "quantile": "linear", "seed": 2026, "draws": 2000},
            "expected_relevant_launches": 42 * len(deltas), "cases": []}
    if shared:
        plan.pop("baseline_variant")
        plan.update(kind="shared_candidate_paired_v1", baseline_variants=["original", "current"],
                    expected_relevant_launches=63 * len(deltas))
    return plan


def _variant_order(shared, variant_names, i):
    if shared:
        from itertools import permutations
        return list(permutations(variant_names))[i % 6]
    return ("baseline", "candidate") if i % 2 == 0 else ("candidate", "baseline")


def _case_run(case, variant):
    return {"case_id": case, "variant": variant, "preparation_kernel_sequence": ["target"],
            "warmup_kernel_sequence": ["warm"], "target_kernel_sequence": ["target"],
            "iteration_kernel_sequence": ["warm", "target"]}


def _case_duration(baseline, candidate, variant):
    if variant == "original":
        return baseline + 2
    if variant == "candidate":
        return candidate
    return baseline


def _sample_rows(root, case, sample, duration, raw, mapped, primes, checks, line, start):
    result = {"case_id": case, "sample_index": sample, "status": "PASS", "rtol": 0, "atol": 0,
              "artifact": _artifact(root, f"outputs/{case}-{sample}.bin")}
    (primes if sample == -1 else checks).append(result)
    for index, kernel in enumerate(["target"] if sample == -1 else ["warm", "target"]):
        time = duration if kernel == "target" else 10.0
        raw.append({"Op Name": kernel, "Task Duration(us)": time, "Task Start Time(us)": start,
                    "Block Num": "28"})
        mapped.append({"case_id": case, "sample_index": sample, "sequence_index": index,
                       "role": "preparation" if sample == -1 else "warmup" if kernel == "warm" else "target",
                       "source_row": line, "kernel": kernel, "duration_us": time,
                       "task_start_us": float(start), "block_num": "28"})
        line += 1
        start += 100
    return line, start


RoundEvidence = namedtuple(
    "RoundEvidence", ["raw", "mapped", "perf", "checks", "primes", "runs", "base", "cand"]
)


def _round_evidence(root, ed, plan, deltas, shared, variant_names, snapshot):
    raw, mapped, perf, checks, primes, runs, base, cand = [], [], [], [], [], [], [], []
    line, start = 2, 1000
    for i, delta in enumerate(deltas):
        baseline = 59.0 + (i % 3) * .1
        candidate = round(baseline + delta, 6)
        base.append(baseline)
        cand.append(candidate)
        variant_order = _variant_order(shared, variant_names, i)
        for position, variant in enumerate(variant_order):
            case = f"r{i:02d}-{variant}"
            plan["cases"].append({"case_id": case, "round": i, "variant": variant, "position": position})
            runs.append(_case_run(case, variant))
            if shared:
                runs[-1]["confirmation"] = {"round_id": i, "order": list(variant_order), "position": position,
                                            "variant": variant, "input_sha256": snapshot["sha256"]}
            duration = _case_duration(baseline, candidate, variant)
            perf.append({"case_id": case, "total_us": duration, "sample_count": 10,
                         "sample_total_us": json.dumps([duration] * 10)})
            for sample in range(-1, 10):
                line, start = _sample_rows(root, case, sample, duration, raw, mapped, primes, checks, line, start)
            for sample in (0, 9):
                dump(ed / "frequency" / f"{case}-{sample}.json",
                     {"case_id": case, "sample_index": sample, "rated": 1650, "activity": 1650})
    return RoundEvidence(raw, mapped, perf, checks, primes, runs, base, cand)


def _case_identity(root, variants, run):
    return {"case_id": run["case_id"], "variant": run["variant"], **variants[run["variant"]],
            "runtime_evidence": _artifact(root, f"runtime/{run['case_id']}.json")}


def _compile_identity(root, variants, runs, shared):
    compile_identity = {"variants": variants}
    if shared:
        compile_identity["case_runs"] = [_case_identity(root, variants, run) for run in runs]
    return compile_identity


def _shared_confirmation(root, plan, plan_path, runs, collection):
    keys = ("kind", "baseline_variants", "candidate_variant", "round_count", "statistical_method")
    declaration = {k: plan[k] for k in keys}
    declaration["effect_plan"] = receipt(plan_path)
    topology = dump(root / "topology.json",
                    {"schema_version": 1, "paired_confirmation": declaration, "case_runs": runs})
    c = json.loads(collection.read_text())
    c["paired_confirmation"] = {"plan": receipt(topology), "declaration": declaration,
                                "case_labels": [{"case_id": run["case_id"], **run["confirmation"]} for run in runs]}
    dump(collection, c)


def _summary_csvs(root, base, cand, shared):
    baseline = csvfile(root / "baseline.csv", ["case_id", "total_us"],
                       [{"case_id": "t1", "total_us": statistics.median(base)}])
    candidate = csvfile(root / "candidate.csv", ["case_id", "total_us"],
                        [{"case_id": "t1", "total_us": statistics.median(cand)}])
    if shared:
        csvfile(root / "original.csv", ["case_id", "total_us"],
                [{"case_id": "t1", "total_us": statistics.median(base) + 2}])
    return baseline, candidate


def fixture(root, deltas=None, shared=False):
    deltas = deltas or _default_deltas(shared)
    root.mkdir(exist_ok=True)
    ed = root / "evidence"
    ed.mkdir()
    snapshot = _artifact(root, "snapshot.bin")
    variant_names = ("original", "current", "candidate") if shared else ("baseline", "candidate")
    refs, variants = _variant_artifacts(root, variant_names)
    identity = dump(root / "expected.json", refs)
    plan = _effect_plan(identity, snapshot, deltas, shared)
    round_evidence = _round_evidence(root, ed, plan, deltas, shared, variant_names, snapshot)
    raw, mapped, perf, checks, primes, runs, base, cand = round_evidence
    warmup = {"mode": "framework_ops", "logical_op": "ArgMax",
              "implementation": "torch_argmax_256mib_fp16_v1", "tensor_bytes": 268435456,
              "tensor_allocation": {"dtype": "float16"}}
    raw_path = csvfile(root / "raw.csv", list(raw[0]), raw)
    performance_path = csvfile(root / "performance.csv", list(perf[0]), perf)
    execution = dump(root / "execution.json", {"samples_per_case": 10, "case_runs": runs, "warmup": warmup})
    order = [r["case_id"] for r in plan["cases"]]
    validation = dump(root / "validation.json", {"status": "pass", "case_order": order, "samples_per_case": 10,
                        "warmup": warmup, "warmup_time_included": False, "preparation_time_included": False,
                        "expected_relevant_launches": len(mapped), "parsed_relevant_launches": len(mapped),
                        "mapped_relevant_launches": len(mapped), "mapped_launches": mapped})
    dump(ed / "device.json", {"soc": "Ascend950", "physical": 3})
    dump(ed / "inputs.json", {"snapshot": snapshot})
    compile_identity = _compile_identity(root, variants, runs, shared)
    dump(ed / "compile-identity.json", compile_identity)
    dump(ed / "precision-results.json", {"status": "strict_pass", "sample_checks": checks, "prime_checks": primes,
             "unchanged_input_raw_bytes": True, "all_retained_outputs_rechecked": True})
    collection = dump(root / "collection.json",
                      {"status": "complete", "samples_per_case": 10, "warmup_time_included": False,
                       "case_count_expected": len(order), "case_count_collected": len(order), "case_ids": order,
                       "sessions": [{}], "started_at": "2026-10-13T07:20:00Z", "warmup": warmup,
                       "validation_json": str(validation), "execution_manifest": str(execution),
                       "op_summary": str(raw_path), "performance_csv": str(performance_path),
                       "identity": {"device_id": 3, "variant_sources": refs, "snapshot": snapshot}})
    plan_path = dump(root / "plan.json", plan)
    if shared:
        _shared_confirmation(root, plan, plan_path, runs, collection)
    registration = dump(root / "registration.json",
                        {"issued_at": "2026-10-13T07:19:00Z", "artifacts": [receipt(plan_path)]})
    baseline, candidate = _summary_csvs(root, base, cand, shared)
    return SimpleNamespace(root=root, plan=plan_path, registration=registration, collection=collection,
                           baseline=baseline, candidate=candidate, validation=validation, raw=raw_path)


def proof(f):
    return dump(f.root / "proof.json", build_proof(f.plan, f.registration, f.collection, f.baseline, f.candidate, "t1"))


def confirmed(f):
    return summarize(f.baseline, f.candidate, policy_id="confidence_effect_v1", evidence_paths=[proof(f)])


def test_realistic_small_gain_is_confirmed_without_changing_legacy(tmp_path):
    f = fixture(tmp_path)
    result = confirmed(f)
    case = result["cases"][0]
    assert result["schema_version"] == 3
    assert case["classification"] == "effective_improvement"
    assert abs(case["delta_percent"]) < 3
    assert case["statistical_evidence"]["paired_ci_us"][1] < 0
    assert result["effective_geomean_speedup"] == pytest.approx(case["speedup"])
    assert summarize(f.baseline, f.candidate)["cases"][0]["classification"] == "jitter_no_effect"
    assert recompute_summary(result) == result


def test_interval_crossing_zero_and_missing_evidence_are_pending(tmp_path):
    f = fixture(tmp_path, [.5, -.5] * 5)
    result = confirmed(f)
    assert result["cases"][0]["classification"] == "inconclusive"
    assert result["effective_geomean_speedup"] is None
    missing = summarize(f.baseline, f.candidate, policy_id="confidence_effect_v1")
    assert missing["inconclusive_case_count"] == 1
    assert missing["cases"][0]["classification_basis"] == "needs_confirmation"


def test_large_screening_change_is_not_a_statistical_confirmation(tmp_path):
    f = fixture(tmp_path, [-10.0] * 10)
    s = summarize(f.baseline, f.candidate, policy_id="confidence_effect_v1")
    assert s["cases"][0]["screening_signal"] == "effective_improvement"
    assert s["cases"][0]["classification"] == "inconclusive"


def _mutate_unbalanced(p):
    for i in range(0, len(p["cases"]), 2):
        pair = sorted(p["cases"][i:i + 2], key=lambda r: r["variant"])
        for j, r in enumerate(pair):
            r["position"] = j
        p["cases"][i:i + 2] = pair


def _mutate_validation(mutation, f):
    d = json.loads(f.validation.read_text())
    if mutation == "missing-launch":
        d["mapped_launches"].pop()
    else:
        d["mapped_launches"][1], d["mapped_launches"][2] = d["mapped_launches"][2], d["mapped_launches"][1]
    dump(f.validation, d)


def _mutate_precision(f):
    path = f.root / "evidence/precision-results.json"
    d = json.loads(path.read_text())
    d["sample_checks"][0]["rtol"] = .01
    dump(path, d)


def _mutate_frequency(f):
    path = f.root / "evidence/frequency/r00-baseline-0.json"
    d = json.loads(path.read_text())
    d["activity"] = 100
    dump(path, d)


def _mutate_spread(f):
    # A self-consistent map still cannot bypass the independent spread check.
    raw_rows = list(csv.DictReader(f.raw.open()))
    raw_rows[2]["Task Duration(us)"] = 70
    csvfile(f.raw, list(raw_rows[0]), raw_rows)
    d = json.loads(f.validation.read_text())
    d["mapped_launches"][2]["duration_us"] = 70
    dump(f.validation, d)
    perf = list(csv.DictReader((f.root / "performance.csv").open()))
    values = json.loads(perf[0]["sample_total_us"])
    values[0] = 70
    perf[0]["sample_total_us"] = json.dumps(values)
    csvfile(f.root / "performance.csv", list(perf[0]), perf)


@pytest.mark.parametrize("mutation,pattern", [
    ("missing-round", "round"), ("duplicate-round", "round"), ("wrong-soc", "SoC"),
    ("wrong-source", "source"), ("unbalanced", "order"), ("missing-launch", "mapping"),
    ("wrong-order", "mapping"), ("precision", "precision"), ("frequency", "frequency"),
    ("spread", "spread"), ("unknown-method", "method"), ("late-registration", "precede"),
])
def test_invalid_original_evidence_cannot_be_rescued_by_good_interval(tmp_path, mutation, pattern):
    f = fixture(tmp_path)
    p = json.loads(f.plan.read_text())
    if mutation == "missing-round":
        p["cases"].pop()
    elif mutation == "duplicate-round":
        p["cases"][2]["round"] = 0
    elif mutation == "wrong-soc":
        p["soc"] = "Ascend910"
    elif mutation == "unbalanced":
        _mutate_unbalanced(p)
    elif mutation == "unknown-method":
        p["statistical_method"]["id"] = "invented_ci"
    elif mutation == "late-registration":
        r = json.loads(f.registration.read_text())
        r["issued_at"] = "2026-10-14T00:00:00Z"
        dump(f.registration, r)
    elif mutation in ("missing-launch", "wrong-order"):
        _mutate_validation(mutation, f)
    elif mutation == "wrong-source":
        (f.root / "source-candidate/kernel.py").write_text("different implementation")
    elif mutation == "precision":
        _mutate_precision(f)
    elif mutation == "frequency":
        _mutate_frequency(f)
    elif mutation == "spread":
        _mutate_spread(f)
    dump(f.plan, p)
    r = json.loads(f.registration.read_text())
    r["artifacts"] = [receipt(f.plan)]
    dump(f.registration, r)
    with pytest.raises(ValueError, match=pattern):
        proof(f)


def test_tampered_stats_dependency_and_different_comparison_are_rejected(tmp_path):
    f = fixture(tmp_path)
    path = proof(f)
    original = json.loads(path.read_text())
    forged = json.loads(path.read_text())
    forged["statistics"]["paired_ci_us"] = [-100, -99]
    dump(path, forged)
    with pytest.raises(ValueError, match="recomputed"):
        verify_proof(path, f.baseline, f.candidate)
    dump(path, original)
    other = tmp_path / "other-baseline.csv"
    other.write_bytes(f.baseline.read_bytes())
    with pytest.raises(ValueError, match="different comparison"):
        verify_proof(path, other, f.candidate)
    (f.root / "outputs/r00-baseline-0.bin").write_text("changed")
    with pytest.raises(ValueError, match="dependency changed"):
        verify_proof(path, f.baseline, f.candidate)


def manifest(f):
    inventory = csvfile(f.root / "inventory.csv", ["case_id"], [{"case_id": "t1"}])
    collection = {**receipt(inventory), "count": 1}
    return dump(f.root / "manifest.json",
                {"schema_version": 2,
                 "configuration": {"target_socs": ["Ascend950"],
                                   "performance_effect_policy": {"id": "confidence_effect_v1", "version": 1}},
                 "collections": {"functional_full": collection, "performance_full": collection},
                 "inputs": {}})


def test_small_regression_routes_and_inconclusive_cannot_pass_full_gate(tmp_path):
    f = fixture(tmp_path, [.7] * 10)
    p = proof(f)
    m = manifest(f)
    gate = validate(m, "Ascend950", {k: (f.baseline, f.candidate) for k in ("functional", "performance")},
                    effect_evidence={k: [p] for k in ("functional", "performance")})
    assert gate["decision"] == "route_required"
    assert gate["collections"]["functional"]["regressed_case_ids"] == ["t1"]
    no_proof = validate(m, "Ascend950", {k: (f.baseline, f.candidate) for k in ("functional", "performance")})
    assert no_proof["decision"] == "confirmation_required"


def test_state_records_raw_proof_dependencies_and_invalidates_changed_input(tmp_path):
    f = fixture(tmp_path)
    summary = dump(tmp_path / "summary.json", confirmed(f))
    args = SimpleNamespace(performance_summary=summary, cumulative_performance_summary=summary,
                           selected_candidate="candidate", performance_scope="full")
    references, paths = prepare_performance(args)
    assert str(f.raw) in paths and str(f.root / "snapshot.bin") in paths
    record = {"performance": references,
              "artifacts": [artifact_identity(p) for p in paths],
              "status": "complete", "completed_at": "2026-10-13"}
    assert recorded_performance(record)[0]["schema_version"] == 3
    report = "\n".join(performance_report({"stages": {"final.performance": record}}))
    assert "paired_confidence" in report and "confidence_effect_v1" in report and "配对估计" in report
    (f.root / "snapshot.bin").write_text("changed input")
    with pytest.raises(ValueError, match="changed"):
        recorded_performance(record)


def test_unknown_policy_schema_and_forged_summary_are_rejected(tmp_path):
    f = fixture(tmp_path)
    with pytest.raises(ValueError, match="unknown"):
        policy({"id": "confidence_effect_v1", "version": 2})
    result = confirmed(f)
    result["schema_version"] = 9
    with pytest.raises(ValueError, match="unknown"):
        recompute_summary(result)
    result = confirmed(f)
    result["cases"][0]["classification"] = "effective_regression"
    p = dump(f.root / "bad-summary.json", result)
    with pytest.raises(ValueError, match="differs"):
        prepare_performance(SimpleNamespace(performance_summary=p, cumulative_performance_summary=p,
                                            selected_candidate="bad", performance_scope="full"))


def canonical_proof(f):
    p = json.loads(f.plan.read_text())
    c = json.loads(f.collection.read_text())
    order = c["case_ids"]
    p.update({"kind": "canonical10_independent", "statistical_method": {
        "id": "python_mt19937_independent_medians_v1", "statistic": "difference_of_medians", "confidence": .95,
        "seed": 2026, "draws": 2000, "quantile": "linear"}})
    for side, variant in (("baseline_collection", "baseline"), ("candidate_collection", "candidate")):
        p[side] = {"manifest": receipt(f.collection) if side == "baseline_collection" else {"path": str(f.collection)},
                   "case_id": f"r00-{variant}", "case_order": order,
                   "expected_relevant_launches": 42, "expected_identity": p["expected_identity"]}
    dump(f.plan, p)
    r = json.loads(f.registration.read_text())
    r["artifacts"] = [receipt(f.plan)]
    dump(f.registration, r)
    return proof(f)


def test_large_change_can_finish_from_ten_original_samples_without_repeated_rounds(tmp_path):
    f = fixture(tmp_path, [-5])  # One canonical10 per side, rather than ten paired rounds.
    p = canonical_proof(f)
    s = summarize(f.baseline, f.candidate, policy_id="confidence_effect_v1", evidence_paths=[p])
    case = s["cases"][0]
    assert case["classification"] == "effective_improvement"
    assert case["classification_basis"] == "canonical10_independent_confidence"
    assert "paired_estimate_us" not in case["statistical_evidence"]
    m = manifest(f)
    mdata = json.loads(m.read_text())
    mdata["configuration"]["precision_diagnosis_policy"] = "persistent"
    dump(m, mdata)
    gate = validate(m, "Ascend950", {k: (f.baseline, f.candidate) for k in ("functional", "performance")},
                    effect_evidence={k: [p] for k in ("functional", "performance")})
    assert gate["decision"] == "pass"
    from workflow_state import check_phase_artifacts
    report = tmp_path / "VERIFY_REPORT.md"
    report.write_text("CPU test report")
    gatepath = dump(tmp_path / "postprocess-performance-Ascend950.json", gate)
    raw_records = dump(tmp_path / "raw-execution-records.json", [{"case_id": "c1"}])
    artifacts = check_phase_artifacts("integration", [str(report), str(gatepath), str(raw_records)], m)
    assert str(f.raw) in artifacts and str(p) in artifacts
    assert str(raw_records) in artifacts
    with pytest.raises(ValueError, match="both full inventories"):
        check_phase_artifacts("integration", [str(report), str(raw_records)], m)


def test_small_change_canonical_ci_cannot_replace_balanced_paired_confirmation(tmp_path):
    f = fixture(tmp_path, [-.7])
    p = canonical_proof(f)
    s = summarize(f.baseline, f.candidate, policy_id="confidence_effect_v1", evidence_paths=[p])
    assert s["cases"][0]["classification"] == "inconclusive"
    assert s["cases"][0]["classification_basis"] == "small_change_requires_paired_confirmation"


def test_missing_output_receipt_is_rejected_when_building_new_proof(tmp_path):
    f = fixture(tmp_path)
    (f.root / "outputs/r00-baseline-0.bin").unlink()
    with pytest.raises(ValueError, match="missing effect dependency"):
        proof(f)


def test_nonzero_original_precision_is_preserved_and_weakening_rejected(tmp_path):
    f = fixture(tmp_path)
    p = json.loads(f.plan.read_text())
    p["original_precision_contract"] = {"status": "strict_pass", "rtol": .001, "atol": .01}
    dump(f.plan, p)
    r = json.loads(f.registration.read_text())
    r["artifacts"] = [receipt(f.plan)]
    dump(f.registration, r)
    path = f.root / "evidence/precision-results.json"
    d = json.loads(path.read_text())
    for row in d["sample_checks"] + d["prime_checks"]:
        row.update(rtol=.001, atol=.01)
    dump(path, d)
    assert confirmed(f)["cases"][0]["classification"] == "effective_improvement"
    d["sample_checks"][0]["rtol"] = .01
    dump(path, d)
    with pytest.raises(ValueError, match="precision"):
        proof(f)


@pytest.mark.parametrize("stage", ["integration.performance.Ascend950", "final.performance"])
def test_final_checkpoints_require_summary_in_real_cli(tmp_path, stage):
    import subprocess
    f = fixture(tmp_path)
    m = manifest(f)
    d = json.loads(m.read_text())
    d["configuration"]["precision_diagnosis_policy"] = "persistent"
    dump(m, d)
    state = tmp_path / "state.json"
    cli = [sys.executable, str(ROOT / "skills/ops-perf-optimize-workflow/scripts/workflow_state.py")]
    start = subprocess.run(cli + ["start", "--state", str(state), "--manifest", str(m)], capture_output=True, text=True)
    assert start.returncode == 0, start.stderr
    mark = subprocess.run(cli + ["mark", "--state", str(state), "--stage", stage, "--status", "complete"],
                          capture_output=True, text=True)
    assert mark.returncode != 0 and "requires" in mark.stdout + mark.stderr
    assert not json.loads(state.read_text())["stages"].get(stage, {}).get("completed_at")


def test_omitting_output_receipts_cannot_make_new_proof(tmp_path):
    f = fixture(tmp_path)
    path = f.root / "evidence/precision-results.json"
    d = json.loads(path.read_text())
    for row in d["sample_checks"] + d["prime_checks"]:
        row.pop("artifact")
    dump(path, d)
    with pytest.raises(ValueError, match="retained output artifact"):
        proof(f)


def test_policy_is_frozen_for_sync_and_direct_mark_real_cli(tmp_path):
    import subprocess
    f = fixture(tmp_path)
    m = manifest(f)
    d = json.loads(m.read_text())
    d["configuration"]["precision_diagnosis_policy"] = "persistent"
    dump(m, d)
    state = tmp_path / "state.json"
    cli = [sys.executable, str(ROOT / "skills/ops-perf-optimize-workflow/scripts/workflow_state.py")]
    assert subprocess.run(cli + ["start", "--state", str(state), "--manifest", str(m)],
                          capture_output=True).returncode == 0
    before = state.read_bytes()
    d["configuration"]["performance_effect_policy"] = {"id": "legacy_jitter_v1", "version": 1}
    dump(m, d)
    for args in (["sync-manifest"], ["mark", "--stage", "round1.complete", "--status", "complete"]):
        result = subprocess.run(cli + args + ["--state", str(state)], capture_output=True, text=True)
        assert result.returncode != 0 and "policy changed" in result.stdout + result.stderr
        assert state.read_bytes() == before


def test_noop_same_receipt_requires_real_identical_execution_identity(tmp_path):
    from prepare_case_sets import code_identity
    from validate_execution_identity import record
    f = fixture(tmp_path)
    m = manifest(f)
    data = json.loads(m.read_text())
    data["inputs"]["code"] = code_identity(f.root / "source-baseline")
    dump(m, data)
    built = f.root / "normal-baseline-built"
    log = f.root / "build.log"
    log.write_text("CPU fixture compiler log")
    raw = f.root / "runtime.log"
    raw.write_text(str(built))
    runtime = dump(f.root / "runtime.json",
                   {"method": "loaded library file from process maps", "target_soc": "Ascend950",
                    "source_artifacts": [receipt(raw)], "loaded_artifacts": [receipt(built)]})
    identity = f.root / "execution-identity.json"
    record(SimpleNamespace(manifest=m, target_soc="Ascend950", build_command="test compile",
                           build_log=log, built_artifact=[built], runtime_evidence=runtime, out=identity))
    binding = {"manifest": receipt(m), "identity": receipt(identity)}
    noop = dump(f.root / "noop.json",
                {"schema_version": 1, "kind": "byte_identical_noop",
                 "baseline": receipt(f.baseline), "candidate": receipt(f.baseline), "case_ids": ["t1"],
                 "baseline_execution": binding, "candidate_execution": binding})
    result = summarize(f.baseline, f.baseline, policy_id="confidence_effect_v1", same_implementation=noop)
    assert result["cases"][0]["classification"] == "same_implementation"
    assert str(f.root / "source-baseline/kernel.py") in {d["path"] for d in result["dependencies"]}
    f.root.joinpath("source-baseline/kernel.py").write_text("different source")
    with pytest.raises(ValueError, match="source identity changed"):
        summarize(f.baseline, f.baseline, policy_id="confidence_effect_v1", same_implementation=noop)


def casewise_fixture(root, overlap=False):
    from prepare_case_sets import code_identity
    from validate_execution_identity import record
    f = fixture(root, [0.] * 6 if overlap else None)
    identifier = "t1" if overlap else "unchanged"
    if not overlap:
        for path in (f.baseline, f.candidate):
            rows = list(csv.DictReader(path.open()))
            rows.append({"case_id": identifier, "total_us": "12.5"})
            csvfile(path, ["case_id", "total_us"], rows)
    m = manifest(f)
    document = json.loads(m.read_text())
    source = code_identity(f.root / "source-baseline")
    document["inputs"]["code"] = source
    dump(m, document)
    config = dump(f.root / "noop-config.json", {"source": source, "target_soc": "Ascend950"})
    built = f.root / "normal-baseline-built"
    generated = f.root / "normal-baseline-generated"
    log = f.root / "noop-build.log"
    log.write_text("\n".join([source["sha256"], receipt(config)["sha256"],
                             receipt(built)["sha256"], receipt(generated)["sha256"]]))
    provider = receipt(f.root / "source-baseline/kernel.py")
    raw = dump(f.root / "noop-invocations.json", {
        "method": "ProviderCallable synthetic CPU validator fixture; no hardware claims",
        "source": source, "loaded_artifacts": [receipt(built)],
        "python_imports": {"operator": provider["path"]},
        "invocations": [{"case_id": identifier, "args": [{"shape": [1], "dtype": "bf16"}], "kwargs": {}}],
    })
    runtime = dump(f.root / "noop-runtime.json", {
        "method": "Synthetic CPU fixture for loaded library identity; no hardware claims",
        "target_soc": "Ascend950", "compile_config": receipt(config),
        "source_artifacts": [receipt(raw)], "loaded_artifacts": [receipt(built)],
    })
    identity = f.root / "noop-execution-identity.json"
    record(SimpleNamespace(manifest=m, target_soc="Ascend950", build_command="synthetic CPU compile fixture",
                           build_log=log, built_artifact=[built], runtime_evidence=runtime, out=identity))
    inputs = dump(f.root / "noop-inputs.json", {identifier: {"q": "a" * 64}})
    side = {"execution": {"manifest": receipt(m), "identity": receipt(identity)},
            "compile_config": receipt(config), "normal_generated": [receipt(generated)],
            "actual_runtime": receipt(runtime), "raw_execution": receipt(raw),
            "actual_case_id": identifier, "provider_source": provider,
            "input_evidence": receipt(inputs), "input_selector": [identifier]}
    evidence = {"schema_version": 1, "kind": "casewise_byte_identical_noop",
                "baseline": receipt(f.baseline), "candidate": receipt(f.candidate),
                "case_ids": [identifier], "cases": [{"case_id": identifier, "baseline": side, "candidate": side}]}
    noop = dump(f.root / "casewise-noop.json", evidence)
    return f, noop


def test_mixed_paired_case_and_real_noop_subset_recompute_and_register_dependencies(tmp_path):
    f, noop = casewise_fixture(tmp_path)
    result = summarize(f.baseline, f.candidate, policy_id="confidence_effect_v1",
                       evidence_paths=[proof(f)], same_implementation=noop)
    assert [case["classification"] for case in result["cases"]] == ["effective_improvement", "same_implementation"]
    assert result["effective_case_count"] == 1
    assert result["same_implementation_case_count"] == 1
    assert result["inconclusive_case_count"] == 0
    assert recompute_summary(result) == result
    assert str(f.root / "noop-inputs.json") in {item["path"] for item in result["dependencies"]}


@pytest.mark.parametrize("mutation,match", [
    ("timing", "identical case timings"), ("duplicate", "subset"),
    ("coverage", "coverage"), ("input", "inputs differ"),
    ("generated", "bind"), ("missing_call", "invocation"),
    ("different_args", "arguments"), ("outside_provider", "outside"),
])
def test_casewise_noop_rejects_incomplete_or_forged_subset_identity(tmp_path, mutation, match):
    f, noop = casewise_fixture(tmp_path)
    value = json.loads(noop.read_text())
    side = value["cases"][0]["candidate"]
    if mutation == "timing":
        rows = list(csv.DictReader(f.candidate.open()))
        rows[1]["total_us"] = "12.6"
        csvfile(f.candidate, ["case_id", "total_us"], rows)
        value["candidate"] = receipt(f.candidate)
    elif mutation == "duplicate":
        value["case_ids"].append("unchanged")
    elif mutation == "coverage":
        value["cases"] = []
    elif mutation == "input":
        inputs = dump(f.root / "different-inputs.json", {"unchanged": {"q": "b" * 64}})
        side["input_evidence"] = receipt(inputs)
    elif mutation == "generated":
        other = f.root / "different-generated.asc"
        other.write_text("different code")
        side["normal_generated"] = [receipt(other)]
    elif mutation in ("missing_call", "different_args"):
        raw = json.loads(Path(side["raw_execution"]["path"]).read_text())
        if mutation == "missing_call":
            raw["invocations"] = []
        else:
            raw["invocations"][0]["args"] = [{"shape": [2], "dtype": "bf16"}]
        raw_path = dump(f.root / "different-invocations.json", raw)
        runtime = json.loads(Path(side["actual_runtime"]["path"]).read_text())
        runtime["source_artifacts"] = [receipt(raw_path)]
        runtime_path = dump(f.root / "different-runtime.json", runtime)
        document = json.loads(Path(side["execution"]["identity"]["path"]).read_text())
        document["targets"][0]["runtime"].update(evidence=receipt(runtime_path), source_artifacts=[receipt(raw_path)])
        identity_path = dump(f.root / "different-identity.json", document)
        side.update(raw_execution=receipt(raw_path), actual_runtime=receipt(runtime_path))
        side["execution"] = {**side["execution"], "identity": receipt(identity_path)}
    elif mutation == "outside_provider":
        side["provider_source"] = receipt(f.root / "source-candidate/kernel.py")
    dump(noop, value)
    with pytest.raises(ValueError, match=match):
        summarize(f.baseline, f.candidate, policy_id="confidence_effect_v1", same_implementation=noop)


def test_casewise_noop_and_paired_proof_must_not_overlap(tmp_path):
    f, noop = casewise_fixture(tmp_path, overlap=True)
    with pytest.raises(ValueError, match="overlap"):
        summarize(f.baseline, f.candidate, policy_id="confidence_effect_v1",
                  evidence_paths=[proof(f)], same_implementation=noop)


def test_canonical_independent_accepts_all_split_session_maps_without_extra_samples(tmp_path):
    f = fixture(tmp_path, [-5])
    c = json.loads(f.collection.read_text())
    original = json.loads((f.root / "execution.json").read_text())
    raw = list(csv.DictReader(f.raw.open()))
    v = json.loads(f.validation.read_text())
    sessions = []
    for i, run in enumerate(original["case_runs"]):
        execution = dump(f.root / f"execution-{i}.json", {**original, "case_runs": [run]})
        rows = raw[i * 21:(i + 1) * 21]
        op = csvfile(f.root / f"raw-{i}.csv", list(rows[0]), rows)
        sessions.append({"case_ids": [run["case_id"]], "execution_manifest": str(execution), "op_summary": str(op)})
        for index in range(21):
            v["mapped_launches"][i * 21 + index]["source_row"] = index + 2
    c["sessions"] = sessions
    c["session_count"] = 2
    c["execution_manifest"] = sessions[0]["execution_manifest"]
    c["op_summary"] = sessions[0]["op_summary"]
    dump(f.collection, c)
    dump(f.validation, v)
    p = canonical_proof(f)
    s = summarize(f.baseline, f.candidate, policy_id="confidence_effect_v1", evidence_paths=[p])
    assert s["cases"][0]["classification"] == "effective_improvement"
    paths = {d["path"] for d in s["dependencies"]}
    assert {str(f.root / "raw-0.csv"), str(f.root / "raw-1.csv")}.issubset(paths)
    # Dropping a complete split cannot reduce expected coverage or map requirements.
    c["sessions"].pop()
    dump(f.collection, c)
    with pytest.raises(ValueError, match="dependency changed|order/coverage"):
        proof(f)


def test_collector_topology_and_effect_plan_are_explicitly_linked_and_rechecked(tmp_path):
    f = fixture(tmp_path)
    plan = json.loads(f.plan.read_text())
    labels, runs = [], []
    execution_path = f.root / "execution.json"
    execution = json.loads(execution_path.read_text())
    for row, run in zip(plan["cases"], execution["case_runs"]):
        confirmation = {"round_id": f"round-{row['round']}", "order": "AB" if row["round"] % 2 == 0 else "BA",
                        "position": row["position"], "variant": row["variant"],
                        "input_sha256": plan["snapshot"]["sha256"]}
        run["confirmation"] = confirmation
        labels.append({"case_id": row["case_id"], **confirmation})
        runs.append(run)
    dump(execution_path, execution)
    declaration = {"round_count": plan["round_count"], "statistical_method": plan["statistical_method"],
                   "effect_plan": receipt(f.plan)}
    topology = dump(f.root / "topology.json",
                    {"schema_version": 1, "paired_confirmation": declaration, "case_runs": runs})
    collection = json.loads(f.collection.read_text())
    collection["paired_confirmation"] = {"plan": receipt(topology), "declaration": declaration, "case_labels": labels}
    dump(f.collection, collection)
    s = confirmed(f)
    assert s["cases"][0]["classification"] == "effective_improvement"
    assert str(topology) in {d["path"] for d in s["dependencies"]}
    # An edited actual manifest cannot borrow valid planned labels.
    execution["case_runs"][0]["confirmation"]["variant"] = "candidate"
    dump(execution_path, execution)
    with pytest.raises(ValueError, match="labels differ"):
        proof(f)


def test_real_cli_verify_invalidates_changed_registered_proof_dependency(tmp_path):
    import subprocess
    f = fixture(tmp_path)
    m = manifest(f)
    d = json.loads(m.read_text())
    d["configuration"]["precision_diagnosis_policy"] = "persistent"
    dump(m, d)
    summary = dump(f.root / "summary.json", confirmed(f))
    state = f.root / "state.json"
    cli = [sys.executable, str(ROOT / "skills/ops-perf-optimize-workflow/scripts/workflow_state.py")]
    assert subprocess.run(cli + ["start", "--state", str(state), "--manifest", str(m)],
                          capture_output=True).returncode == 0
    args = ["mark", "--state", str(state), "--stage", "round1.complete", "--status", "complete",
            "--performance-summary", str(summary), "--cumulative-performance-summary", str(summary),
            "--selected-candidate", "candidate"]
    marked = subprocess.run(cli + args, capture_output=True, text=True)
    assert marked.returncode == 0, marked.stdout + marked.stderr
    (f.root / "outputs/r00-baseline-0.bin").write_text("changed original output")
    verified = subprocess.run(cli + ["verify", "--state", str(state)], capture_output=True, text=True)
    assert verified.returncode != 0
    assert json.loads(state.read_text())["stages"]["round1.complete"]["status"] == "invalid"


@pytest.mark.parametrize("kind", ["pending", "regression"])
def test_real_cli_integrated_summary_cannot_pass_pending_or_regressed_cases(tmp_path, kind):
    import subprocess
    f = fixture(tmp_path, [.7] * 10)
    m = manifest(f)
    d = json.loads(m.read_text())
    d["configuration"]["precision_diagnosis_policy"] = "persistent"
    dump(m, d)
    result = (confirmed(f) if kind == "regression"
              else summarize(f.baseline, f.candidate, policy_id="confidence_effect_v1"))
    summary = dump(f.root / "summary.json", result)
    state = f.root / "state.json"
    cli = [sys.executable, str(ROOT / "skills/ops-perf-optimize-workflow/scripts/workflow_state.py")]
    assert subprocess.run(cli + ["start", "--state", str(state), "--manifest", str(m)],
                          capture_output=True).returncode == 0
    marked = subprocess.run(
        cli + ["mark", "--state", str(state), "--stage", "integration.performance.Ascend950",
               "--status", "complete", "--performance-summary", str(summary),
               "--cumulative-performance-summary", str(summary), "--selected-candidate", "candidate"],
        capture_output=True, text=True)
    assert marked.returncode != 0
    expected = "requiring confirmation" if kind == "pending" else "requiring original-code routing"
    assert expected in marked.stdout + marked.stderr


def test_canonical_source_variant_is_observed_not_inferred_from_case_name(tmp_path):
    f = fixture(tmp_path, [-5])
    p = canonical_proof(f)
    execution = json.loads((f.root / "execution.json").read_text())
    execution["case_runs"][1]["variant"] = "baseline"
    dump(f.root / "execution.json", execution)
    with pytest.raises(ValueError, match="executed source variant"):
        proof(f)


def test_shared_candidate_has_two_independent_contrasts_and_one_headline(tmp_path):
    f = fixture(tmp_path, shared=True)
    paths = []
    for variant, baseline in (("current", f.baseline), ("original", f.root / "original.csv")):
        value = build_proof(f.plan, f.registration, f.collection, baseline, f.candidate, "t1", variant)
        p = dump(f.root / f"proof-{variant}.json", value)
        assert verify_proof(p, baseline, f.candidate) == value
        summary = summarize(baseline, f.candidate, policy_id="confidence_effect_v1", evidence_paths=[p])
        assert summary["cases"][0]["classification"] == "effective_improvement"
        assert summary["candidate_path"] == str(f.candidate)
        paths.append(p)
    with pytest.raises(ValueError, match="different comparison"):
        verify_proof(paths[0], f.root / "original.csv", f.candidate)


@pytest.mark.parametrize("mutation,pattern", [
    ("dropped-other-baseline", "coverage"), ("unbalanced", "permutations"),
    ("wrong-actual-source", "executed source"), ("missing-live", "normal/build/live"),
    ("wrong-label-input", "labels differ"), ("missing-topology", "topology"),
])
def test_shared_candidate_cannot_drop_uncompared_work_or_borrow_identity(tmp_path, mutation, pattern):
    f = fixture(tmp_path, shared=True)
    plan = json.loads(f.plan.read_text())
    if mutation == "dropped-other-baseline":
        plan["cases"].pop(0)
        dump(f.plan, plan)
        reg = json.loads(f.registration.read_text())
        reg["artifacts"] = [receipt(f.plan)]
        dump(f.registration, reg)
    elif mutation == "unbalanced":
        group = [dict(row) for row in plan["cases"][:3]]
        for row in group:
            row["round"] = 1
            row["case_id"] = "duplicate-order-" + row["variant"]
        plan["cases"][3:6] = group
        dump(f.plan, plan)
        reg = json.loads(f.registration.read_text())
        reg["artifacts"] = [receipt(f.plan)]
        dump(f.registration, reg)
    elif mutation in ("wrong-actual-source", "missing-live"):
        p = f.root / "evidence/compile-identity.json"
        d = json.loads(p.read_text())
        if mutation == "wrong-actual-source":
            d["case_runs"][0]["source"] = d["variants"]["candidate"]["source"]
        else:
            d["case_runs"][0].pop("live")
        dump(p, d)
    elif mutation == "wrong-label-input":
        p = f.root / "execution.json"
        d = json.loads(p.read_text())
        d["case_runs"][0]["confirmation"]["input_sha256"] = "0" * 64
        dump(p, d)
    else:
        d = json.loads(f.collection.read_text())
        d.pop("paired_confirmation")
        dump(f.collection, d)
    with pytest.raises(ValueError, match=pattern):
        build_proof(f.plan, f.registration, f.collection, f.baseline, f.candidate, "t1", "current")


def chronology_fixture(tmp_path):
    from performance_effect_evidence import registration_precedes_capture
    directory = tmp_path / 'attempt-001'
    directory.mkdir()
    execution = dump(directory / 'execution.json', {'actual': True})
    summary = csvfile(directory / 'summary.csv', ['duration'], [{'duration': 1}])
    attempt = {'dir': str(directory), 'started_at': '2026-10-13T20:10:50+00:00',
               'returncode': 0, 'data_status': 'valid', 'execution_manifest': str(execution),
               'op_summary': str(summary), 'files': [receipt(execution), receipt(summary)]}
    dump(directory / 'attempt.json', attempt)
    collection = {'started_at': '2026-10-13T20:10:41+00:00',
                  'sessions': [{'attempts': [attempt], 'execution_manifest': str(execution),
                                'op_summary': str(summary)}]}
    registration = {'issued_at': '2026-10-13T20:10:41.014772+00:00'}
    return registration_precedes_capture, registration, collection, directory


def test_coarse_same_second_chronology_binds_actual_capture(tmp_path):
    fn, reg, collection, _ = chronology_fixture(tmp_path)
    deps = {}
    fn(reg, collection, deps)
    assert len(deps) == 3


@pytest.mark.parametrize('bad', ['different_second', 'precise_collection', 'no_attempt',
                                'late_registration', 'unbound_execution', 'changed_receipt',
                                'modified_attempt'])
def test_coarse_chronology_does_not_allow_post_capture_registration(tmp_path, bad):
    fn, reg, collection, directory = chronology_fixture(tmp_path)
    attempt = collection['sessions'][0]['attempts'][0]
    if bad == 'different_second':
        reg['issued_at'] = '2026-10-13T20:10:42+00:00'
    if bad == 'precise_collection':
        collection['started_at'] = '2026-10-13T20:10:41.000001+00:00'
    if bad == 'no_attempt':
        collection['sessions'][0]['attempts'] = []
    if bad == 'late_registration':
        attempt['started_at'] = reg['issued_at']
        dump(directory / 'attempt.json', attempt)
    if bad == 'unbound_execution':
        collection['sessions'][0]['execution_manifest'] = str(tmp_path / 'other.json')
    if bad == 'changed_receipt':
        (directory / 'execution.json').write_text('changed')
    if bad == 'modified_attempt':
        changed = dict(attempt, started_at='2026-10-13T20:10:51+00:00')
        dump(directory / 'attempt.json', changed)
    with pytest.raises(ValueError):
        fn(reg, collection, {})


def test_full_paired_proof_keeps_coarse_chronology_dependencies(tmp_path):
    f = fixture(tmp_path)
    reg = json.loads(f.registration.read_text())
    reg['issued_at'] = '2026-10-13T07:20:00.014772+00:00'
    dump(f.registration, reg)
    collection = json.loads(f.collection.read_text())
    attempt = {'dir': str(f.root), 'started_at': '2026-10-13T07:20:10Z',
               'returncode': 0, 'data_status': 'valid',
               'execution_manifest': collection['execution_manifest'], 'op_summary': collection['op_summary'],
               'files': [receipt(collection['execution_manifest']), receipt(collection['op_summary'])]}
    dump(f.root / 'attempt.json', attempt)
    collection['sessions'] = [{'attempts': [attempt], 'execution_manifest': collection['execution_manifest'],
                              'op_summary': collection['op_summary']}]
    dump(f.collection, collection)
    p = proof(f)
    result = verify_proof(p, f.baseline, f.candidate)
    assert receipt(f.root / 'attempt.json') in result['dependencies']
    (f.root / 'attempt.json').write_text('{}')
    with pytest.raises(ValueError):
        verify_proof(p, f.baseline, f.candidate)
