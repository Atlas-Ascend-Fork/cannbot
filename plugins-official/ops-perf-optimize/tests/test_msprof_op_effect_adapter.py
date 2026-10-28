# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Synthetic receipts test the real op CSV format; these are not NPU measurements."""
from __future__ import annotations
import csv
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "ops-perf-optimize-workflow" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from performance_effect_evidence import build_proof, receipt, verify_proof, independent_statistics
from msprof_op_effect_adapter import KIND, validate_plan
from prepare_case_sets import code_identity
from summarize_performance_effects import summarize


def dump(path, value):
    path.write_text(json.dumps(value, indent=2))
    return path


def text(path, value):
    path.write_text(value)
    return path


def _fixture_environment(root):
    inventory = text(root / "cases.csv", "case_id,shape\nsfa,2\n")
    request = dump(root / "request.json", {"performance_effect_policy": {"id": "confidence_effect_v1", "version": 1}})
    manifest = dump(root / "manifest.json", {"configuration": {"target_socs": ["Ascend950"],
        "performance_effect_policy": {"id": "confidence_effect_v1", "version": 1}},
        "request": receipt(request), "collections": {"performance_full": receipt(inventory)}})
    snapshot = text(root / "inputs.bin", "frozen raw input fixture")
    reference = root / "reference.bin"
    reference.write_bytes(b"\x80?\x00@")
    protocol = {"profiler": "msprof op", "aic_metrics": "PipeTimeline", "launch_count": 1,
        "warmup": 5, "metric": "Task Duration(us)", "target_calls": 2, "synchronizations": 2,
        "warmup_time_included": False}
    precision_contract = {"status": "strict_pass", "rtol": 0, "atol": 0, "comparison": "raw_bf16_bytes_equal"}
    return manifest, SimpleNamespace(sources={}, binary={}, buildlog={}, generated={}, snapshot=snapshot,
                                     reference=reference, protocol=protocol,
                                     precision_contract=precision_contract)


def _execution_document(env, path, variant, raw, output=None, mixed=False, loaded_other=False, built_other=False,
                        pid=None):
    loaded = env.binary["baseline"] if loaded_other or built_other else env.binary[variant]
    built = env.binary["baseline"] if built_other else env.binary[variant]
    build_log = env.buildlog[variant]
    if built_other:
        build_log = text(path.with_name("sample-build.log"), " ".join([
            env.sources[variant]["sha256"], receipt(env.generated[variant])["sha256"], receipt(built)["sha256"]]))
    runtime = dump(path.with_name(path.stem + "-runtime.json"), {
        "method": "synthetic loader trace", "target_soc": "Ascend950", "physical_device": 3, "logical_device": 0,
        "pid": pid if pid is not None else 1000,
        "input_snapshot": receipt(env.snapshot), "target_calls": 2, "synchronizations": 2,
        "source_artifacts": raw, "loaded_artifacts": [receipt(loaded)]})
    return dump(path, {"schema_version": 1, "source": env.sources["baseline" if mixed else variant],
        "targets": [{"target_soc": "Ascend950", "build": {"command": "fixture-build", "log": receipt(build_log),
            "artifacts": [receipt(built)]}, "runtime": {"evidence": receipt(runtime),
            "loaded_artifacts": [receipt(loaded)], "source_artifacts": raw}}]})


def _fixture_variant(env, root, v, identities):
    source = root / v
    source.mkdir()
    text(source / "kernel.cpp", "// " + v)
    env.sources[v] = code_identity(source)
    env.generated[v] = text(root / (v + "-generated.cpp"), "// generated " + v)
    env.binary[v] = text(root / (v + ".so"), "synthetic binary " + v)
    env.buildlog[v] = text(root / (v + "-build.log"), " ".join([
        env.sources[v]["sha256"], receipt(env.generated[v])["sha256"], receipt(env.binary[v])["sha256"]]))
    loader = text(root / (v + "-loader.log"), "loaded " + str(env.binary[v]))
    doc = _execution_document(env, root / (v + "-normal.json"), v, [receipt(loader)])
    identities[v] = {"kernel_name": "kernel_" + v, "block_dim": 28, "mix_block_dim": 56,
        "generated": [receipt(env.generated[v])], "execution_identity": receipt(doc)}


def _mutate_first_sample_row(row, bad):
    if bad == "zero":
        row["Task Duration(us)"] = 0
    if bad == "nan":
        row["Task Duration(us)"] = "nan"
    if bad == "frequency":
        row.pop("Current Freq")
    if bad == "low_frequency":
        row["Current Freq"] = 1600
    if bad == "device":
        row["Device Id"] = 4
    if bad == "kernel":
        row["Op Name"] = "wrong_kernel"


def _write_op_basic_info(folder, row, bad, i):
    raw = folder / "OpBasicInfo.csv"
    with raw.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        if not (i == 1 and bad == "missing_row"):
            writer.writerow(row)
        if i == 1 and bad == "extra_row":
            writer.writerow(row)
    return raw


def _fixture_sample(env, root, slot, bad, gain):
    v, i = slot["variant"], slot["slot"]
    folder = root / f"sample-{i:02}"
    folder.mkdir()
    duration = 1000 if v == "baseline" else 1000 - gain
    pid = (100 if v == "baseline" else 101) if bad == "reused_pid" else 100 + i
    row = {"Op Name": "kernel_" + v, "Op Type": "mix", "Task Duration(us)": duration,
           "Block Dim": 28, "Mix Block Dim": 56, "Device Id": 3, "Pid": pid,
           "Current Freq": 1650, "Rated Freq": 1650}
    if v == "candidate" and bad == "cross_frequency":
        row["Current Freq"] = row["Rated Freq"] = 1800
    if i == 1:
        _mutate_first_sample_row(row, bad)
    raw = _write_op_basic_info(folder, row, bad, i)
    log = text(folder / "run.log", f"Warm Up enabled. times:5\nAll task success\nTask Duration(us): {duration}\n"
                                   f"Pid: {pid}\nloaded {env.binary[v]}\nloaded {env.binary['baseline']}\n")
    output = folder / "output.bin"
    output.write_bytes(b"BAD!" if i == 1 and bad == "precision" else env.reference.read_bytes())
    doc = _execution_document(env, folder / "execution.json", v, [receipt(raw), receipt(log), receipt(output)],
                              output, mixed=i == 1 and bad == "source", loaded_other=i == 1 and bad == "loaded",
                              built_other=i == 1 and bad == "built", pid=pid)
    truth = dump(folder / "precision.json", {"contract": env.precision_contract, "case_id": "sfa",
        "input_snapshot": receipt(env.snapshot), "execution_identity": receipt(doc), "actual_output": receipt(output),
        "dtype": "bfloat16", "shape": [2]})
    start = datetime(2026, 10, 15, 1, 0, tzinfo=timezone.utc) + timedelta(seconds=10 * i)
    attempt = dump(folder / "attempt.json", {"schema_version": 1, **slot, "started_at": start.isoformat(),
        "ended_at": (start + timedelta(seconds=5)).isoformat(), "protocol": env.protocol,
        "physical_device": 3, "logical_device": 0,
        "command": ["msprof", "op", "--aic-metrics=PipeTimeline", "--launch-count=1"],
        "run_log": receipt(log), "returncode": 0, "status": "valid", "op_basic_info": receipt(raw),
        "execution_identity": receipt(doc), "precision": receipt(truth)})
    return {**slot, "attempts": [receipt(attempt)]}


def _fixture_order():
    order = []
    for pair in range(10):
        for v in (("baseline", "candidate") if pair % 2 == 0 else ("candidate", "baseline")):
            order.append({"slot": len(order), "variant": v, "sample_index": pair})
    return order


def _fixture_plan(root, manifest, env, identities, order):
    plan_data = {"schema_version": 1, "kind": KIND, "manifest": receipt(manifest), "collection": "performance_full",
        "effect_case_id": "sfa", "soc": "Ascend950", "physical_device": 3, "logical_device": 0,
        "rated_frequency_mhz": 1650,
        "protocol": env.protocol, "snapshot": receipt(env.snapshot), "samples_per_variant": 10,
        "precision": env.precision_contract,
        "output_contract": {"dtype": "bfloat16", "shape": [2], "reference": receipt(env.reference)},
        "baseline_variant": "baseline", "candidate_variant": "candidate", "identities": identities, "order": order,
        "retry_policy": "record_failed_attempts_then_first_success_no_valid_sample_replacement",
        "statistical_method": {"id": "python_mt19937_independent_medians_v1", "confidence": .95,
            "statistic": "difference_of_medians", "quantile": "linear", "seed": 2026, "draws": 1000}}
    plan = dump(root / "plan.json", plan_data)
    registration = dump(root / "registration.json", {"issued_at": "2026-10-15T00:00:00Z", "artifacts": [receipt(plan)]})
    return plan, registration


def _fixture_collection(root, plan, registration, samples, bad, gain):
    if bad == "count":
        samples.pop()
    if bad == "order":
        samples[0], samples[1] = samples[1], samples[0]
    if bad == "late":
        dump(registration, {"issued_at": "2026-10-15T02:00:00Z", "artifacts": [receipt(plan)]})
    collection = dump(root / "collection.json",
                      {"schema_version": 1, "kind": KIND, "plan": receipt(plan), "samples": samples})
    base = text(root / "baseline.csv", "case_id,total_us\nsfa,1000\n")
    cand = text(root / "candidate.csv", f"case_id,total_us\nsfa,{1000 - gain}\n")
    return SimpleNamespace(plan=plan, registration=registration, collection=collection, baseline=base, candidate=cand)


def fixture(root, bad=None, gain=100):
    manifest, env = _fixture_environment(root)
    identities = {}
    for v in ("baseline", "candidate"):
        _fixture_variant(env, root, v, identities)
    frozen = json.loads(manifest.read_text())
    frozen["inputs"] = {"code": env.sources["baseline"]}
    dump(manifest, frozen)
    order = _fixture_order()
    plan, registration = _fixture_plan(root, manifest, env, identities, order)
    samples = [_fixture_sample(env, root, slot, bad, gain) for slot in order]
    return _fixture_collection(root, plan, registration, samples, bad, gain)


def proof(f):
    return build_proof(f.plan, f.registration, f.collection, f.baseline, f.candidate, "sfa")


def test_op10_proof_and_existing_summary_gate(tmp_path):
    f = fixture(tmp_path)
    value = proof(f)
    assert value["kind"] == KIND and value["statistics"]["ci_us"] == [-100, -100]
    saved = dump(tmp_path / "proof.json", value)
    assert verify_proof(saved, f.baseline, f.candidate) == value
    summary = summarize(f.baseline, f.candidate, policy_id="confidence_effect_v1", evidence_paths=[saved])
    assert summary["cases"][0]["classification"] == "effective_improvement"
    assert summary["cases"][0]["classification_basis"] == KIND + "_confidence"


@pytest.mark.parametrize("bad,expected", [("missing_row", "one complete"), ("extra_row", "one complete"),
    ("zero", "positive"), ("nan", "positive"), ("frequency", "Current Freq"), ("low_frequency", "frequency"),
    ("cross_frequency", "frequency"), ("reused_pid", "process reused"),
    ("device", "physical device"), ("kernel", "kernel identity"), ("source", "source identity"),
    ("loaded", "loaded artifacts do not match"), ("built", "build differs"),
    ("precision", "BF16 output"), ("count", "twenty"), ("order", "order"), ("late", "chronology")])
def test_malformed_or_unattributed_op_samples_rejected(tmp_path, bad, expected):
    with pytest.raises(ValueError, match=expected):
        proof(fixture(tmp_path, bad))


def test_small_op_change_still_requires_paired_confirmation(tmp_path):
    f = fixture(tmp_path, gain=1)
    saved = dump(tmp_path / "proof.json", proof(f))
    summary = summarize(f.baseline, f.candidate, policy_id="confidence_effect_v1", evidence_paths=[saved])
    assert summary["cases"][0]["classification"] == "inconclusive"
    assert summary["cases"][0]["classification_basis"] == "small_change_requires_paired_confirmation"


def test_op_receipts_rechecked_after_source_or_raw_mutation(tmp_path):
    f = fixture(tmp_path)
    saved = dump(tmp_path / "proof.json", proof(f))
    text(tmp_path / "sample-00" / "OpBasicInfo.csv", "altered")
    with pytest.raises(ValueError, match="changed"):
        verify_proof(saved, f.baseline, f.candidate)


def test_registration_cli_refuses_overwrite(tmp_path):
    f = fixture(tmp_path)
    out = tmp_path / "new-registration.json"
    command = ["timeout", "30s", sys.executable, str(SCRIPTS / "msprof_op_effect_adapter.py"),
               "--plan", str(f.plan), "--register", str(out)]
    run = subprocess.run(command, capture_output=True, text=True, timeout=35)
    assert run.returncode == 0, run.stdout + run.stderr
    before = out.read_bytes()
    run = subprocess.run(command, capture_output=True, text=True, timeout=35)
    assert run.returncode != 0 and out.read_bytes() == before


def test_failed_timeout_attempt_retained_before_first_success(tmp_path):
    f = fixture(tmp_path)
    c = json.loads(f.collection.read_text())
    first = json.loads(Path(c["samples"][0]["attempts"][0]["path"]).read_text())
    failed = {k: v for k, v in first.items() if k not in ("op_basic_info", "execution_identity", "precision")}
    failed.update(started_at="2026-10-15T00:59:50Z", ended_at="2026-10-15T00:59:55Z", status="failed", returncode=124,
                  run_log=receipt(text(tmp_path / "failed.log", "timeout124; no valid duration\n")))
    attempt = dump(tmp_path / "failed-attempt.json", failed)
    c["samples"][0]["attempts"].insert(0, receipt(attempt))
    dump(f.collection, c)
    value = proof(f)
    assert receipt(attempt) in value["dependencies"]
    assert len(value["statistics"]["baseline_samples_us"]) == 10


def test_original_frozen_baseline_cannot_be_replaced(tmp_path):
    f = fixture(tmp_path)
    plan = json.loads(f.plan.read_text())
    plan["identities"]["baseline"] = plan["identities"]["candidate"]
    dump(f.plan, plan)
    with pytest.raises(ValueError, match="original frozen source"):
        validate_plan(f.plan)


def test_successful_attempt_cannot_be_replaced_by_faster_retry(tmp_path):
    f = fixture(tmp_path)
    c = json.loads(f.collection.read_text())
    c["samples"][0]["attempts"] *= 2
    dump(f.collection, c)
    with pytest.raises(ValueError, match="cannot be discarded"):
        proof(f)


def test_nonzero_exit_cannot_hide_complete_successful_timing(tmp_path):
    f = fixture(tmp_path)
    c = json.loads(f.collection.read_text())
    old = json.loads(Path(c["samples"][0]["attempts"][0]["path"]).read_text())
    failed = dict(old, returncode=124, status="failed",
                  started_at="2026-10-15T00:59:50Z", ended_at="2026-10-15T00:59:55Z")
    receipt_path = dump(tmp_path / "claimed-failure.json", failed)
    c["samples"][0]["attempts"].insert(0, receipt(receipt_path))
    dump(f.collection, c)
    with pytest.raises(ValueError, match="complete successful timing"):
        proof(f)


def archive_baseline(f, root):
    """Rebind real sample receipts to a pre-registered byte-identical archive."""
    import shutil
    original = root / "baseline"
    archive = root / "immutable-original"
    shutil.copytree(original, archive)
    archived = code_identity(archive)
    plan = json.loads(f.plan.read_text())
    mapping = dump(root / "extraction-manifest.json", {"schema_version": 1, "manifest": plan["manifest"],
        "original_source": code_identity(original), "original_snapshot": archived})

    def relocate(doc_path):
        document = json.loads(doc_path.read_text())
        document["source"] = archived
        dump(doc_path, document)
        return receipt(doc_path)
    identity = plan["identities"]["baseline"]
    identity["execution_identity"] = relocate(Path(identity["execution_identity"]["path"]))
    identity["source_archive"] = receipt(mapping)
    dump(f.plan, plan)
    registration = json.loads(f.registration.read_text())
    registration["artifacts"] = [receipt(f.plan)]
    dump(f.registration, registration)
    collection = json.loads(f.collection.read_text())
    collection["plan"] = receipt(f.plan)
    for sample in collection["samples"]:
        if sample["variant"] != "baseline":
            continue
        attempt_path = Path(sample["attempts"][0]["path"])
        attempt = json.loads(attempt_path.read_text())
        attempt["execution_identity"] = relocate(Path(attempt["execution_identity"]["path"]))
        precision_path = Path(attempt["precision"]["path"])
        precision = json.loads(precision_path.read_text())
        precision["execution_identity"] = attempt["execution_identity"]
        dump(precision_path, precision)
        attempt["precision"] = receipt(precision_path)
        dump(attempt_path, attempt)
        sample["attempts"] = [receipt(attempt_path)]
    dump(f.collection, collection)
    return mapping, archive


def test_archived_baseline_proof_survives_integration_at_original_root(tmp_path):
    f = fixture(tmp_path)
    archive_baseline(f, tmp_path)
    saved = dump(tmp_path / "proof.json", proof(f))
    text(tmp_path / "baseline" / "kernel.cpp", "// integrated candidate changed original root")
    assert verify_proof(saved, f.baseline, f.candidate)["kind"] == KIND


@pytest.mark.parametrize("bad", ["original", "manifest", "snapshot", "bytes"])
def test_baseline_archive_rejects_changed_mapping_or_content(tmp_path, bad):
    f = fixture(tmp_path)
    mapping_path, archive = archive_baseline(f, tmp_path)
    mapping = json.loads(mapping_path.read_text())
    if bad == "bytes":
        text(archive / "kernel.cpp", "// replaced baseline")
    else:
        field = {"original": "original_source", "manifest": "manifest", "snapshot": "original_snapshot"}[bad]
        mapping[field]["sha256"] = "0" * 64
        dump(mapping_path, mapping)
        plan = json.loads(f.plan.read_text())
        plan["identities"]["baseline"]["source_archive"] = receipt(mapping_path)
        dump(f.plan, plan)
    with pytest.raises(ValueError, match="mapping|frozen source identity changed"):
        validate_plan(f.plan)


@pytest.mark.parametrize("complete", [False, True])
def test_all_failed_raw_captures_bound_and_success_not_discarded(tmp_path, complete):
    f = fixture(tmp_path)
    collection = json.loads(f.collection.read_text())
    first = json.loads(Path(collection['samples'][0]['attempts'][0]['path']).read_text())
    raws = [receipt(text(tmp_path / f'failed-{i}.csv', 'incomplete profiler output\n')) for i in range(2)]
    if complete:
        raws[1] = first['op_basic_info']
    failed = {k: v for k, v in first.items() if k not in ('op_basic_info', 'execution_identity', 'precision')}
    failed.update(returncode=124, status='failed', started_at='2026-10-15T00:59:50Z',
                  ended_at='2026-10-15T00:59:55Z', raw_captures=raws)
    failure_path = dump(tmp_path / 'failed-attempt.json', failed)
    collection['samples'][0]['attempts'].insert(0, receipt(failure_path))
    dump(f.collection, collection)
    if complete:
        with pytest.raises(ValueError, match='complete successful timing'):
            proof(f)
    else:
        result = proof(f)
        assert all(item in result['dependencies'] for item in raws)
        saved = dump(tmp_path / 'proof.json', result)
        text(Path(raws[1]['path']), 'changed failure raw')
        with pytest.raises(ValueError, match='changed'):
            verify_proof(saved, f.baseline, f.candidate)


def test_successful_raw_capture_array_cannot_hide_multiple_targets(tmp_path):
    f = fixture(tmp_path)
    collection = json.loads(f.collection.read_text())
    path = Path(collection['samples'][0]['attempts'][0]['path'])
    attempt = json.loads(path.read_text())
    attempt['raw_captures'] = [attempt['op_basic_info'], receipt(tmp_path / 'sample-01/OpBasicInfo.csv')]
    dump(path, attempt)
    collection['samples'][0]['attempts'] = [receipt(path)]
    dump(f.collection, collection)
    with pytest.raises(ValueError, match='one unambiguous raw capture'):
        proof(f)
