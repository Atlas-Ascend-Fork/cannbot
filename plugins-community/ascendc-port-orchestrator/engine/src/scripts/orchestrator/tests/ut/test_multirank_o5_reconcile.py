# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Coverage-aware O5 reconcile (three-way set logic) + durable VERIFIED marker.

The count-level reconcile minted a MISMATCH on every card-weather change and
spawned a worker for pure bookkeeping (matmul_allreduce kw-6..kw-9, zero
kernel changes). These tests pin the three-way set logic:

  path 1  intersection identity flip  -> real MISMATCH (no file write)
  path 2  shortage                    -> VERIFIED, claim untouched
  path 3  clean expansion             -> auto-VERIFIED + claim upgraded in place
  path 3b expansion with a FAIL cell  -> MISMATCH (worker analyzes)
  mixed   expansion + shortage        -> VERIFIED, claim untouched (conservative)
  guard   measured case the claim neither covers nor declared -> MISMATCH

and the R2 durable marker (write -> skip; any digest drift / unaccepted
unverified / dirty harness -> full re-measure).

Scope notes:
  - `_measured` builds the campaign extras via getattr(multirank_runner, "_measured") (the
    phase_o5.MeasuredResult does not declare unverified_world_sizes /
    multirank_case_verdicts — multirank_runner attaches them dynamically);
  - the marker's candidate binding is multirank_o5_reconcile._candidate_artifact_digest
    (a LOCAL digest over the kernel surface — no receipt stack involved),
    so the marker fixture stages no receipt monkeypatch: the
    digest is computed over the staged files and stays stable across the
    write/read round trip;
  - the dirty-harness case pins the REAL harness_pristine.HarnessState (the
    ut conftest's autouse CLEAN pin loses to the per-test patch, as designed).

Run: cd engine/src/scripts && PYTHONPATH=. python3 -m pytest \
     orchestrator/tests/ut/test_multirank_o5_reconcile.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))  # .../orchestrator (multirank_o5_reconcile)
sys.path.insert(0, str(_HERE.parents[3]))  # .../src/scripts (judge import chain)

from plugins.multirank import multirank_runner  # noqa: E402
from plugins.multirank import multirank_o5_reconcile as rec  # noqa: E402
import phase_o5  # noqa: E402
from plugins.multirank import multirank_phase_o25  # noqa: E402
from plugins.multirank.multirank_rank_verdicts import case_verdicts_of  # noqa: E402


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

CASES = [
    {"name": f"case{i}@ws{ws}[randn]", "world_size": ws}
    for ws in (1, 2, 4, 8)
    for i in range(4)
]


def _rank_entries(ws, failing=()):
    """rank_verdicts entries for one ws group: ws ranks, each covering the
    group's 4 cases; `failing` holds (case_name, rank) hard-fail cells."""
    entries = []
    for r in range(ws):
        cases = [c["name"] for c in CASES if c["world_size"] == ws]
        entry = {"rank": r, "status": "PASS", "cases": cases}
        failed = [
            {
                "case_id": c,
                "verdict": "FAIL",
                "ours_mere": 1e-5,
                "ours_mare": 124.0,
                "comp_mere": 2e-6,
                "comp_mare": 0.1,
            }
            for (c, rr) in failing
            if rr == r
        ]
        if failed:
            entry["status"] = "FAIL"
            entry["failed_cases"] = failed
        entries.append(entry)
    return entries


def _write_claim(
    workspace, ws_groups=(1, 2, 4, 8), failing=(), unverified_ws=(), unverified_cases=()
):
    mr = {
        "world_sizes": sorted(ws_groups),
        "cases": CASES,
        "rank_verdicts": {str(ws): _rank_entries(ws, failing) for ws in ws_groups},
    }
    if unverified_ws:
        mr["unverified"] = {
            str(ws): {
                "status": "UNVERIFIED",
                "reason": "card_shortage",
                "detail": f"all cases at ws={ws} card-short",
                "probe": "npu_probe",
            }
            for ws in unverified_ws
        }
    if unverified_cases:
        mr["unverified_cases"] = {
            c: {
                "status": "UNVERIFIED",
                "reason": "card_shortage",
                "detail": "card-short",
                "probe": "npu_probe",
                "world_size": next(x["world_size"] for x in CASES if x["name"] == c),
            }
            for c in unverified_cases
        }
    vj = {
        "precision": {
            "status": "FAIL" if failing else "PASS",
            "pass_a": {"status": "FAIL", "tier1_pass": 32, "total": 60},
            "pass_b": {"status": "N/A"},
            "persist_verdict": "PARTIAL_PERSIST",
        },
        "performance": {"status": "BELOW_THRESHOLD", "ratio": 0.427},
        "multirank": mr,
    }
    (workspace / "verification.json").write_text(json.dumps(vj, indent=2))
    return vj


def _case_entry(c, failing):
    """One case's verdict entry: every rank cell PASS unless listed in
    `failing` as (case_name, rank)."""
    name, ws = c["name"], c["world_size"]
    ranks = {str(r): "PASS_T1" for r in range(ws)}
    for fc, fr in failing:
        if fc == name:
            ranks[str(fr)] = "FAIL"
    failed = [
        {
            "case_id": fc,
            "verdict": "FAIL",
            "ours_mere": 1e-5,
            "ours_mare": 124.0,
            "comp_mere": 2e-6,
            "comp_mare": 0.1,
        }
        for (fc, fr) in failing
        if fc == name
    ]
    n_fail = sum(1 for v in ranks.values() if v == "FAIL")
    return name, {
        "world_size": ws,
        "ranks": ranks,
        "failed_cases": failed,
        "tier1_pass": ws - n_fail,
        "tier2_pass": 0,
        "total": ws,
    }


def _case_verdicts(ws_groups, failing=()):
    """MeasuredResult.multirank_case_verdicts-shaped map: every cell PASS unless
    listed in `failing` as (case_name, rank)."""
    out = {}
    for ws in ws_groups:
        for c in CASES:
            if c["world_size"] == ws:
                name, entry = _case_entry(c, failing)
                out[name] = entry
    return out


def _measured(ws_groups, failing=(), unverified=None):
    return getattr(multirank_runner, "_measured")(
        pass_a={"status": "FAIL", "tier1_pass": 16, "total": 28},
        multirank_case_verdicts=_case_verdicts(ws_groups, failing),
        unverified_world_sizes=unverified or {},
    )


def _rep():
    return phase_o5.O5Report(verdict="VERIFIED", truth_source="multirank")


# ---------------------------------------------------------------------------
# path 1: intersection identity flip -> real MISMATCH
# ---------------------------------------------------------------------------


def test_path1_identity_flip_is_real_mismatch(tmp_path):
    vj = _write_claim(tmp_path, failing=[("case1@ws1[randn]", 0)])
    measured = _measured(
        (1, 2, 4, 8), failing=[("case2@ws4[randn]", 2)]
    )  # claim says pass
    before = (tmp_path / "verification.json").read_text()
    rep = _rep()
    rec.reconcile_multirank_coverage(tmp_path, rep, measured, vj)
    assert rep.verdict == "MISMATCH"
    assert any("case2@ws4[randn] rank2" in m for m in rep.mismatches)
    assert (tmp_path / "verification.json").read_text() == before


# ---------------------------------------------------------------------------
# path 2: shortage -> VERIFIED, claim untouched
# ---------------------------------------------------------------------------


def test_path2_shortage_verified_claim_untouched(tmp_path):
    vj = _write_claim(tmp_path, failing=[("case1@ws1[randn]", 0)])
    measured = _measured(
        (1, 2, 4),
        failing=[("case1@ws1[randn]", 0)],
        unverified={"8": {"status": "UNVERIFIED"}},
    )
    before = (tmp_path / "verification.json").read_text()
    rep = _rep()
    rec.reconcile_multirank_coverage(tmp_path, rep, measured, vj)
    assert rep.verdict == "VERIFIED"
    assert "identity-match on 12 case(s)" in rep.summary
    assert "4 claim-covered case(s) unmeasured" in rep.summary
    assert (tmp_path / "verification.json").read_text() == before


# ---------------------------------------------------------------------------
# path 3: clean expansion -> auto-VERIFIED + claim upgraded
# ---------------------------------------------------------------------------


def _stage_run_logs(workspace, ws_groups, failing=()):
    """Write .run/<slug>/rank_*.log files whose last-line JSON matches what
    multirank_verify emits — the upgrade reloads these."""
    for cname, cv in _case_verdicts(ws_groups, failing).items():
        slug = multirank_phase_o25.case_slug(cname)
        log_dir = workspace / ".run" / slug
        log_dir.mkdir(parents=True)
        for r in range(cv["world_size"]):
            verdict = cv["ranks"][str(r)]
            summary = {
                "rank": r,
                "status": "PASS" if verdict == "PASS_T1" else "FAIL",
                "tier1_pass": 1 if verdict == "PASS_T1" else 0,
                "tier2_pass": 0,
                "total": 1,
                "results": [
                    {
                        "case_id": cname,
                        "verdict": verdict,
                        "ours_mere": 1e-5,
                        "ours_mare": 0.5,
                        "comp_mere": 2e-6,
                        "comp_mare": 0.4,
                    }
                ],
            }
            (log_dir / f"rank_{r}.log").write_text(
                "noise\n" + json.dumps(summary) + "\n"
            )


def _stage_manifest_and_spec(workspace):
    (workspace / "golden").mkdir()
    (workspace / "golden" / "manifest.json").write_text(
        json.dumps(
            {
                "op": workspace.name,
                "spec_hash": "spec123",
                "world_sizes": [1, 2, 4, 8],
                "n_cases": len(CASES),
                "cases": CASES,
            }
        )
    )
    (workspace / "spec.py").write_text(
        "SPEC = " + repr({"world_sizes": [1, 2, 4, 8], "cases": CASES})
    )


def test_path3_clean_expansion_auto_upgrades_claim(tmp_path):
    """Degraded claim (ws8 declared unverified) + full clean measurement ->

    VERIFIED, the claim folds O5's campaign in place: ws8 covered, unverified
    declarations dropped, performance/persist_verdict preserved.
    """
    vj = _write_claim(
        tmp_path,
        ws_groups=(1, 2, 4),
        failing=[("case1@ws1[randn]", 0)],
        unverified_ws=(8,),
    )
    _stage_manifest_and_spec(tmp_path)
    _stage_run_logs(tmp_path, (1, 2, 4, 8), failing=[("case1@ws1[randn]", 0)])
    measured = _measured((1, 2, 4, 8), failing=[("case1@ws1[randn]", 0)])
    rep = _rep()
    rec.reconcile_multirank_coverage(tmp_path, rep, measured, vj)
    assert rep.verdict == "VERIFIED", rep.summary
    assert "auto-upgraded with 4 newly-measured case(s)" in rep.summary

    new = json.loads((tmp_path / "verification.json").read_text())
    assert set(new["multirank"]["rank_verdicts"]) == {"1", "2", "4", "8"}
    assert "unverified" not in new["multirank"]
    # the pre-existing failure roll survived the fold (intersection cells)
    ws1 = new["multirank"]["rank_verdicts"]["1"][0]
    assert ws1["status"] == "FAIL"
    assert ws1["failed_cases"][0]["case_id"] == "case1@ws1[randn]"
    # worker-authored blocks preserved
    assert new["performance"] == {"status": "BELOW_THRESHOLD", "ratio": 0.427}
    assert new["precision"]["persist_verdict"] == "PARTIAL_PERSIST"
    assert new["precision"]["pass_a"]["total"] == 60


# ---------------------------------------------------------------------------
# path 3b: expansion with a hard FAIL cell -> MISMATCH (worker analyzes)
# ---------------------------------------------------------------------------


def test_path3b_expansion_failure_routes_to_worker(tmp_path):
    vj = _write_claim(
        tmp_path,
        ws_groups=(1, 2, 4),
        failing=[("case1@ws1[randn]", 0)],
        unverified_ws=(8,),
    )
    before = (tmp_path / "verification.json").read_text()
    measured = _measured(
        (1, 2, 4, 8), failing=[("case1@ws1[randn]", 0), ("case0@ws8[randn]", 5)]
    )
    rep = _rep()
    rec.reconcile_multirank_coverage(tmp_path, rep, measured, vj)
    assert rep.verdict == "MISMATCH"
    assert "case0@ws8[randn] rank5" in rep.summary
    assert "New precision evidence" in rep.summary
    assert (tmp_path / "verification.json").read_text() == before


# ---------------------------------------------------------------------------
# mixed: expansion + shortage -> VERIFIED, claim untouched (conservative)
# ---------------------------------------------------------------------------


def test_mixed_weather_keeps_claim_and_forwards_shortage(tmp_path):
    vj = _write_claim(
        tmp_path,
        ws_groups=(1, 2, 4),
        failing=[("case1@ws1[randn]", 0)],
        unverified_ws=(8,),
    )
    before = (tmp_path / "verification.json").read_text()
    # ws1/2/8 measured: expansion (ws8) AND shortage (claim-covered ws4)
    measured = _measured(
        (1, 2, 8),
        failing=[("case1@ws1[randn]", 0)],
        unverified={"4": {"status": "UNVERIFIED"}},
    )
    rep = _rep()
    rec.reconcile_multirank_coverage(tmp_path, rep, measured, vj)
    assert rep.verdict == "VERIFIED", rep.summary
    assert "NOT folded into the claim" in rep.summary
    assert (tmp_path / "verification.json").read_text() == before


# ---------------------------------------------------------------------------
# guard: measured case the claim silently dropped -> MISMATCH
# ---------------------------------------------------------------------------


def test_claim_incomplete_guard(tmp_path):
    vj = _write_claim(tmp_path, ws_groups=(1, 2, 4))  # ws8 not even declared
    measured = _measured((1, 2, 4, 8))
    rep = _rep()
    rec.reconcile_multirank_coverage(tmp_path, rep, measured, vj)
    assert rep.verdict == "MISMATCH"
    assert any("silently dropped" in m for m in rep.mismatches)


# ---------------------------------------------------------------------------
# #12 shape: a plain MeasuredResult (no dynamic extras) reconciles as a
# full shortage ({} case verdicts) instead of crashing.
# ---------------------------------------------------------------------------


def test_plain_measured_result_degrades_to_shortage(tmp_path):
    vj = _write_claim(tmp_path, failing=[("case1@ws1[randn]", 0)])
    measured = phase_o5.MeasuredResult(
        pass_a={"status": "FAIL", "tier1_pass": 0, "total": 0}
    )
    rep = _rep()
    rec.reconcile_multirank_coverage(tmp_path, rep, measured, vj)
    assert rep.verdict == "VERIFIED"
    assert "16 claim-covered case(s) unmeasured" in rep.summary


# ---------------------------------------------------------------------------
# case_verdicts_of shape
# ---------------------------------------------------------------------------


def test_case_verdicts_of_shape():
    rs = {
        "rank": 1,
        "status": "FAIL",
        "tier1_pass": 0,
        "tier2_pass": 0,
        "total": 1,
        "results": [
            {
                "case_id": "case0@ws2[randn]",
                "verdict": "FAIL",
                "ours_mere": 1e-5,
                "ours_mare": 9.0,
                "comp_mere": 2e-6,
                "comp_mare": 8.0,
            }
        ],
    }
    ran = [
        (
            "case0@ws2[randn]",
            [
                {
                    "rank": 0,
                    "status": "PASS",
                    "tier1_pass": 1,
                    "tier2_pass": 0,
                    "total": 1,
                    "results": [{"case_id": "case0@ws2[randn]", "verdict": "PASS_T1"}],
                }
            ],
            {0: True, 1: False},
        )
    ]
    ran[0][1].append(rs)
    out = case_verdicts_of(ran)
    cv = out["case0@ws2[randn]"]
    assert cv["world_size"] == 2
    assert cv["ranks"] == {"0": "PASS_T1", "1": "FAIL"}
    assert cv["failed_cases"][0]["case_id"] == "case0@ws2[randn]"
    assert cv["tier1_pass"] == 1 and cv["total"] == 2


# ---------------------------------------------------------------------------
# R2 durable marker
# ---------------------------------------------------------------------------


@pytest.fixture
def marker_env(tmp_path):
    """Stage a workspace with claim + manifest (+ candidate kernel surface)."""
    vj = _write_claim(tmp_path, failing=[("case1@ws1[randn]", 0)])
    _stage_manifest_and_spec(tmp_path)
    kernel = tmp_path / "prj-kernel" / "op_kernel"
    kernel.mkdir(parents=True)
    (kernel / "op.h").write_text("AscendC::GlobalTensor<float> x;\n")
    (tmp_path / "model_new_ascendc.py").write_text("import glob\n")
    return tmp_path, vj


def test_marker_round_trip_skips_remeasure(marker_env):
    ws, _vj = marker_env
    rec.write_verified_marker(ws, unverified={}, pass_a={"tier1_pass": 32, "total": 60})
    rep = rec.try_skip_remeasure(ws, ws.name)
    assert rep is not None and rep.verdict == "VERIFIED"
    assert "durable marker" in rep.summary
    assert rep.claimed["pass_a"]["total"] == 60


def test_marker_survives_perf_block_rewrite(marker_env):
    """The finalize perf capture REWRITES the performance block on every

    attempt — the marker binds the CLAIM (precision/mc2/determinism), so a
    perf-block rewrite must NOT invalidate it (that rewrite is exactly the
    post-precision failure the marker exists to skip past).
    """
    ws, _vj = marker_env
    rec.write_verified_marker(ws, unverified={}, pass_a={"tier1_pass": 32, "total": 60})
    vj = json.loads((ws / "verification.json").read_text())
    vj["performance"] = {
        "status": "N/A",
        "na_kind": "MEASUREMENT_FAILED",
        "independent_re_measure": {"ran": False},
    }
    (ws / "verification.json").write_text(json.dumps(vj))
    rep = rec.try_skip_remeasure(ws, ws.name)
    assert rep is not None and rep.verdict == "VERIFIED"


def test_marker_skips_nothing_on_claim_drift(marker_env):
    ws, _vj = marker_env
    rec.write_verified_marker(ws, unverified={}, pass_a={})
    vj = json.loads((ws / "verification.json").read_text())
    vj["precision"]["pass_a"]["tier1_pass"] = 31  # hand-edited claim
    (ws / "verification.json").write_text(json.dumps(vj))
    assert rec.try_skip_remeasure(ws, ws.name) is None


def test_marker_skips_nothing_on_spec_drift(marker_env):
    ws, _vj = marker_env
    rec.write_verified_marker(ws, unverified={}, pass_a={})
    manifest = json.loads((ws / "golden" / "manifest.json").read_text())
    manifest["spec_hash"] = "different"
    (ws / "golden" / "manifest.json").write_text(json.dumps(manifest))
    assert rec.try_skip_remeasure(ws, ws.name) is None


def test_marker_skips_nothing_on_candidate_drift(marker_env):
    """Port-specific: the LOCAL candidate digest binds the kernel surface —

    a kernel-source edit invalidates the marker.
    """
    ws, _vj = marker_env
    rec.write_verified_marker(ws, unverified={}, pass_a={})
    kernel = ws / "prj-kernel" / "op_kernel" / "op.h"
    kernel.write_text("AscendC::GlobalTensor<float> x;  // edited\n")
    assert rec.try_skip_remeasure(ws, ws.name) is None


def test_marker_unverified_requires_acceptance(marker_env):
    ws, _vj = marker_env
    rec.write_verified_marker(ws, unverified={"8": {}}, pass_a={})
    # no .coverage_accept.json -> the gap was never accepted -> full re-measure
    assert rec.try_skip_remeasure(ws, ws.name) is None
    (ws / ".coverage_accept.json").write_text(
        json.dumps({"accepted_world_sizes": ["8"]})
    )
    rep = rec.try_skip_remeasure(ws, ws.name)
    assert rep is not None and set(rep.unverified_world_sizes) == {"8"}


def test_marker_skips_nothing_on_dirty_harness(marker_env, monkeypatch):
    ws, _vj = marker_env
    rec.write_verified_marker(ws, unverified={}, pass_a={})
    import harness_pristine

    dirty = harness_pristine.HarnessState(harness_pristine.DIRTY, dirty_paths=["x.py"])
    monkeypatch.setattr(harness_pristine, "harness_state", lambda *a, **k: dirty)
    assert rec.try_skip_remeasure(ws, ws.name) is None


def test_empty_claim_and_empty_measurement_is_not_verified(tmp_path):
    """Vacuous coverage guard: a claim covering no cases plus an O5 that

    measured none has no identity to match — the verdict must be a loud
    MISMATCH, never the "identity-match on 0 case(s)" VERIFIED that stamps
    a marker and skips every future re-measure.
    """
    _write_claim(tmp_path, ws_groups=())
    rep = _rep()
    measured = getattr(multirank_runner, "_measured")(
        pass_a={}, multirank_case_verdicts={}, unverified_world_sizes={}
    )
    rec.reconcile_multirank_coverage(
        tmp_path,
        rep,
        measured,
        json.loads((tmp_path / "verification.json").read_text()),
    )
    assert rep.verdict == "MISMATCH"
    assert rep.mismatches and "vacuous" in rep.mismatches[0]
    assert "NOT VERIFIED" in rep.summary


def test_vacuous_marker_forces_remeasure(marker_env):
    """A marker with no verified case and no forwarded shortage is empty

    evidence — try_skip_remeasure must refuse it and re-measure, not
    re-stamp a VERIFIED that never measured anything.
    """
    ws, _vj = marker_env
    rec.write_verified_marker(ws, unverified={}, pass_a={})
    assert rec.try_skip_remeasure(ws, ws.name) is None
    rec.write_verified_marker(ws, unverified={}, pass_a={"total": 0})
    assert rec.try_skip_remeasure(ws, ws.name) is None
