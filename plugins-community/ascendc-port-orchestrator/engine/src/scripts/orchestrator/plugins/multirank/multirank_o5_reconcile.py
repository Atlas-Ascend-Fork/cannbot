# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Coverage-aware O5 reconcile for multirank + the durable VERIFIED marker.

The count-level reconcile (_reconcile_counts) compares claimed vs measured
totals exactly. On a SHARED multi-NPU box, card weather between the worker's
campaign and O5's re-measure changes how many cases CAN run — and every
coverage change minted a MISMATCH and spawned a worker to rewrite the claim
(matmul_allreduce kw-6/7/8/9: four spawns, zero kernel changes, the claim
literally chased card occupancy). The runner already distinguishes "measured
and differs" from "could not measure" (MeasuredResult.multirank_case_verdicts vs
unverified_world_sizes) — this module uses that information:

  C = cases the claim covers (multirank.rank_verdicts)
  M = cases this O5 campaign measured (MeasuredResult.multirank_case_verdicts)

  path 1  M∩C identity mismatch — measured and DISAGREES: real MISMATCH
          (the only path that spawns a worker over a wrong claim)
  path 2  M⊂C — card shortage: intersection matches → VERIFIED; the
          unmeasured coverage forwards as unverified_world_sizes (the
          coverage pause / accept-marker machinery owns it)
  path 3  M⊃C, every expansion cell passes — O5 measured cases the claim
          declared unverified and they are clean: AUTO-VERIFIED and the
          claim is upgraded in place (the harness folds its own campaign
          into verification.json — no worker bookkeeping)
  path 3b M⊃C, any expansion cell FAIL — new precision evidence the claim
          never documented: MISMATCH so the worker does the
          requirement-class analysis (its designated job)

A mixed round (expansion AND shortage in one campaign) is deliberately
conservative: the claim is NOT upgraded (an upgrade would drop the
claim-covered-but-unmeasured cases), the verdict carries the shortage as
unverified, and a calmer round completes the picture.

R2 durable marker: after a clean-harness VERIFIED, write .o5_verified.json
binding {verification.json claim sha256, candidate artifact digest, golden
spec_hash, unverified set, pass_a counts}. A later finalize entry whose
digests all match (and whose recorded unverified set is already
operator-accepted) skips the re-measure entirely — a retry after a
POST-precision failure (perf capture / audit / gate) resumes at the failed
stage instead of re-rolling the card-weather dice.

Design notes:
  - `measured.multirank_case_verdicts` / `measured.unverified_world_sizes` are
    MeasuredResult extras attached by multirank_runner._measured (the phase_o5
    dataclass does not declare them); every read is a defensive getattr so
    a plain MeasuredResult degrades to {} / None.
  - no trusted receipt/manifest stack: the marker's candidate binding is
    computed by the local `_candidate_artifact_digest` below (purpose —
    bind the executable kernel surface).
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_MARKER_NAME = ".o5_verified.json"
_MARKER_SCHEMA = "o5-verified-v1"
# The per-case verdict vocabulary of multirank_precision_eval_two_tier's canonical
# judge (rs["results"][i].verdict): PASS_T1 / PASS_T1_SMALLVAL / PASS_T2 are
# pass-class; FAIL / EVAL_ERR are hard failures. (rs["status"] is rank-level
# PASS/FAIL — the case_verdicts_of fallback when results is empty.)
_PASS_VERDICTS = ("PASS", "PASS_T1", "PASS_T1_SMALLVAL", "PASS_T2")
_FAIL_VERDICTS = ("FAIL", "EVAL_ERR")


# ---------------------------------------------------------------------------
# claim side (verification.json multirank block)
# ---------------------------------------------------------------------------


def _claim_cells(multirank_block: dict) -> dict:
    """{(case_name, rank): "pass"|"fail"} from the claim's rank_verdicts —
    the per-cell identity the claim CAN express (it has no per-case tier1/t2
    split, only hard-fail membership)."""
    cells: dict = {}
    for _ws_key, entries in (multirank_block.get("rank_verdicts") or {}).items():
        for entry in entries or []:
            failed = {f.get("case_id") for f in (entry.get("failed_cases") or [])}
            for cname in entry.get("cases") or []:
                cells[(cname, int(entry.get("rank")))] = (
                    "fail" if cname in failed else "pass"
                )
    return cells


def _claim_declared_unverified_cases(multirank_block: dict) -> set:
    """Cases the claim declares UNVERIFIED (ws-level placeholder expanded via
    multirank.cases + case-level entries)."""
    out = set((multirank_block.get("unverified_cases") or {}).keys())
    unv_ws = {int(k) for k in (multirank_block.get("unverified") or {})}
    for c in multirank_block.get("cases") or []:
        if c.get("world_size") in unv_ws:
            out.add(c.get("name"))
    return out


def _intersection_mismatches(
    claim_cells: dict, case_verdicts: dict, inter: set
) -> list:
    """Per-cell pass/fail identity compare on the measured intersection.
    strict↔PWT shifts inside "pass" are tolerated (det_policy=best_effort
    aligns); a pass↔fail flip is the only discrepancy."""
    mism = []
    for cname in sorted(inter):
        ranks = case_verdicts[cname].get("ranks") or {}
        for rstr, verdict in sorted(ranks.items(), key=lambda kv: int(kv[0])):
            cell = claim_cells.get((cname, int(rstr)))
            if cell is None:
                mism.append(
                    f"{cname} rank{rstr}: measured but the claim's "
                    f"rank_verdicts do not cover this cell"
                )
                continue
            if (cell == "pass") != (verdict in _PASS_VERDICTS):
                mism.append(
                    f"{cname} rank{rstr}: claim="
                    f"{'PASS' if cell == 'pass' else 'FAIL'} "
                    f"vs measured={verdict}"
                )
    return mism


# ---------------------------------------------------------------------------
# path-3 claim upgrade (the harness folds its own campaign)
# ---------------------------------------------------------------------------


def _reload_campaign_summaries(workspace: Path, case_names: set):
    """Re-read this O5 campaign's rank summaries from .run logs for exactly
    the measured cases. (ran_by_ws, merged) shaped for the runner's own
    fold/aggregate helpers — the upgrade reuses production fold code instead
    of a parallel implementation."""
    from . import multirank_phase_o25
    from .multirank_runner import (
        _parse_rank_summary,
        _synthetic_error_summary,
    )

    ran_by_ws: dict = {}
    merged: list = []
    for cname in sorted(case_names):
        log_dir = workspace / ".run" / multirank_phase_o25.case_slug(cname)
        summaries = []
        for lf in sorted(log_dir.glob("rank_*.log")):
            rs = _parse_rank_summary(lf.read_text(errors="ignore"))
            if rs is None:
                # A rank that crashed/hung during THIS campaign leaves a log
                # with no summary line; fold it the way the runner did — a
                # synthetic ERROR keeps the per-rank fold shape (the case is
                # measured-failed, never dropped from the upgraded claim).
                rk = int(lf.stem.split("_")[-1])
                rs = _synthetic_error_summary(
                    rk,
                    cname,
                    "rank log carries no parseable summary "
                    "(crash/hang during this O5 campaign)",
                    f"workspace/.run/{multirank_phase_o25.case_slug(cname)}/"
                    f"rank_{rk}.log",
                )
            summaries.append(rs)
        if not summaries:
            raise RuntimeError(f"no rank logs for measured case {cname}")
        ran_by_ws.setdefault(len(summaries), []).append((cname, summaries, None))
        merged.extend(summaries)
    return ran_by_ws, merged


def _upgrade_unverified_declarations(
    manifest_cases: list, measured_cases: set, measured
) -> tuple:
    """(unverified, unverified_cases) declarations for declared-but-unmeasured
    cases after the upgrade — the runner's projection carries the detail."""
    declared = {c["name"]: c.get("world_size") for c in manifest_cases}
    unmeasured = sorted(set(declared) - measured_cases)
    if not unmeasured:
        return None, None
    projection = getattr(measured, "unverified_world_sizes", None) or {}
    by_ws: dict = {}
    for cname in unmeasured:
        by_ws.setdefault(declared[cname], []).append(cname)
    unverified: dict = {}
    unverified_cases: dict = {}
    for ws, cnames in sorted(by_ws.items()):
        wstr = str(ws)
        proj = projection.get(wstr) or {}
        if len(cnames) == sum(1 for c in manifest_cases if c.get("world_size") == ws):
            unverified[wstr] = {
                "status": "UNVERIFIED",
                "reason": "card_shortage",
                "detail": proj.get("detail")
                or (f"all {len(cnames)} case(s) at world_size={ws} card-short"),
                "probe": proj.get("probe", "npu_probe"),
            }
        else:
            for cname in cnames:
                unverified_cases[cname] = {
                    "status": "UNVERIFIED",
                    "reason": "card_shortage",
                    "detail": proj.get("detail") or (f"needed {ws} idle NPU(s)"),
                    "probe": proj.get("probe", "npu_probe"),
                    "world_size": ws,
                }
    return unverified or None, unverified_cases or None


def _upgrade_claim_from_measurement(
    workspace: Path, case_verdicts: dict, measured
) -> dict:
    """Fold this O5 campaign into verification.json (path 3). Returns the new
    pass_a. Read-merge-write: persist_verdict / performance / pass_b and any
    other worker-authored keys are preserved; the claim's unverified
    declarations for cases that ARE now measured are dropped."""
    from . import multirank_phase_o25
    from .multirank_runner import _build_verdict, _fold_rank_verdicts

    ran_by_ws, merged = _reload_campaign_summaries(workspace, set(case_verdicts))
    rank_verdicts = {
        str(ws): _fold_rank_verdicts(ws, ran) for ws, ran in sorted(ran_by_ws.items())
    }
    overall, pass_a, determinism, _perf = _build_verdict(workspace, merged)
    pass_a["tier2_pass"] = overall["tier2_pass"]

    manifest = multirank_phase_o25.load_golden_manifest(workspace)
    manifest_cases = manifest.get("cases") or []
    unv, unv_cases = _upgrade_unverified_declarations(
        manifest_cases, set(case_verdicts), measured
    )
    mr_new = {
        "world_sizes": multirank_phase_o25.declared_case_world_sizes(workspace),
        "cases": [
            {"name": c["name"], "world_size": c.get("world_size")}
            for c in manifest_cases
        ],
        "rank_verdicts": rank_verdicts,
    }
    if unv:
        mr_new["unverified"] = unv
    if unv_cases:
        mr_new["unverified_cases"] = unv_cases

    vp = workspace / "verification.json"
    vj = json.loads(vp.read_text())
    prec = vj.setdefault("precision", {})
    prec["status"] = overall["status"]
    prec["pass_a"] = pass_a
    vj["determinism"] = determinism
    vj["multirank"] = mr_new
    vp.write_text(json.dumps(vj, indent=2))
    log.info(
        "multirank_o5_reconcile: claim upgraded from the O5 campaign "
        f"(pass_a={pass_a.get('tier1_pass')}/{pass_a.get('total')})"
    )
    return pass_a


# ---------------------------------------------------------------------------
# the reconcile (replaces _reconcile_counts for multirank)
# ---------------------------------------------------------------------------


def _expansion_hard_failures(expansion: set, case_verdicts: dict) -> list:
    """Failing cells among the expansion cases (evidence the claim never
    documented)."""
    exp_fail = []
    for cname in sorted(expansion):
        ranks = (case_verdicts[cname].get("ranks") or {}).items()
        for rstr, verdict in sorted(ranks, key=lambda kv: int(kv[0])):
            if verdict not in _PASS_VERDICTS:
                exp_fail.append(f"{cname} rank{rstr}={verdict}")
    return exp_fail


def _upgrade_claim_clean_expansion(workspace, rep, measured, case_verdicts) -> None:
    """Path 3: clean expansion with nothing claim-covered left unmeasured —
    fold O5's own campaign into the claim (auto-upgrade, no worker)."""
    new_pass_a = _upgrade_claim_from_measurement(workspace, case_verdicts, measured)
    rep.claimed["pass_a"] = dict(new_pass_a)


def _reconcile_partial_summary(rep, inter, expansion, shortage) -> None:
    """Path 2 (+ conservative mixed): intersection verified; claim unchanged;
    the unmeasured claim coverage forwards as unverified (the caller
    assigns the runner's unverified projection to the report)."""
    note = ""
    if expansion:
        note = (
            f"; {len(expansion)} newly-measured case(s) "
            f"({sorted(expansion)}) NOT folded into the claim because "
            f"{len(shortage)} claim-covered case(s) went unmeasured "
            f"this round (mixed weather) — the claim stays as-is"
        )
    gap = (
        (
            f"; {len(shortage)} claim-covered case(s) unmeasured this round "
            f"(card shortage) — forwarded as UNVERIFIED"
        )
        if shortage
        else ""
    )
    rep.summary = (
        f"O5 VERIFIED (coverage-aware): intersection identity-match on "
        f"{len(inter)} case(s){gap}{note}."
    )


def _reconcile_vacuous_coverage(rep, covered_claim, measured_cases) -> bool:
    """Vacuous-coverage guard: no claimed case and nothing measured means
    there is no identity to match — an "intersection identity-match on 0
    case(s)" verdict is empty, not verification (and would stamp a durable
    marker that skips every future re-measure). True when the verdict is
    settled."""
    if not covered_claim and not measured_cases:
        rep.verdict = "MISMATCH"
        rep.mismatches.append(
            "claim declares no covered cases and this O5 measured "
            "none — an empty intersection is vacuous, not verified"
        )
        rep.summary = (
            "O5 NOT VERIFIED: nothing to verify — the claim covers no "
            "cases and no case was measured this round"
        )
        return True
    return False


def _reconcile_expansion_failures(rep, exp_fail, expansion) -> bool:
    """Path 3b: expansion measured and contains hard failures — new
    precision evidence the claim never documented; the worker owns the
    requirement-class analysis. True when the verdict is settled."""
    if exp_fail:
        rep.mismatches.extend(exp_fail)
        rep.verdict = "MISMATCH"
        rep.summary = (
            f"O5 measured {len(expansion)} case(s) beyond the claim's "
            f"coverage and found {len(exp_fail)} failing cell(s): "
            f"{'; '.join(exp_fail[:3])}. New precision evidence — the "
            f"worker must analyze the failure class and re-emit the claim."
        )
        return True
    return False


def reconcile_multirank_coverage(workspace: Path, rep, measured, v: dict) -> None:
    """Three-way coverage-aware reconcile — mutates rep (verdict/mismatches/

    summary); may fold the campaign into verification.json (path 3).
    """
    multirank_block = v.get("multirank") or {}
    case_verdicts = getattr(measured, "multirank_case_verdicts", None) or {}
    claim_cells = _claim_cells(multirank_block)
    covered_claim = {c for (c, _r) in claim_cells}
    measured_cases = set(case_verdicts)

    inter = covered_claim & measured_cases
    expansion = measured_cases - covered_claim
    shortage = covered_claim - measured_cases

    if _reconcile_vacuous_coverage(rep, covered_claim, measured_cases):
        return

    mismatches = _intersection_mismatches(claim_cells, case_verdicts, inter)
    # claim-incomplete guard: a measured case the claim neither covers nor
    # declared unverified means the claim silently dropped a declared case.
    for cname in sorted(expansion - _claim_declared_unverified_cases(multirank_block)):
        mismatches.append(
            f"{cname}: measured by O5 but absent from the claim's covered "
            f"cases AND from its declared unverified — the claim silently "
            f"dropped a declared case"
        )
    if mismatches:
        rep.mismatches.extend(mismatches)
        rep.verdict = "MISMATCH"
        rep.summary = (
            f"O5 NOT VERIFIED: {len(mismatches)} cell-level "
            f"claim/measurement discrepancy(ies) on the measured "
            f"intersection: " + "; ".join(mismatches[:3])
        )
        return

    if _reconcile_expansion_failures(
        rep, _expansion_hard_failures(expansion, case_verdicts), expansion
    ):
        return

    if expansion and not shortage:
        _upgrade_claim_clean_expansion(workspace, rep, measured, case_verdicts)
        rep.summary = (
            f"O5 VERIFIED (coverage-aware): intersection identity-match on "
            f"{len(inter)} case(s); claim auto-upgraded with "
            f"{len(expansion)} newly-measured case(s) "
            f"({sorted(expansion)})."
        )
        return

    _reconcile_partial_summary(rep, inter, expansion, shortage)


# ---------------------------------------------------------------------------
# R2 durable VERIFIED marker
# ---------------------------------------------------------------------------


def _claim_digest(vp: Path) -> str:
    """sha256 of the CLAIM content of verification.json — everything except
    the performance block. The finalize perf capture legitimately REWRITES
    performance on every attempt (B2/perf_only discipline never touches
    precision/multirank/determinism), so a whole-file digest would go stale the
    moment the next stage runs and the skip would only ever fire for
    failures that happened BEFORE the perf stage — the exact opposite of
    the marker's purpose (retry after a post-precision failure)."""
    vj = json.loads(vp.read_text())
    claim = {k: v for k, v in vj.items() if k != "performance"}
    return hashlib.sha256(
        json.dumps(
            claim, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def _candidate_artifact_digest(workspace: Path) -> str:
    """Bind the executable kernel surface the campaign measures.

    sha256 over the canonical manifest of
    the candidate artifacts — model_new_ascendc.py (canonical entry point),
    the op_kernel/kernel *.h/*.cpp sources (nest prj-*/ + legacy flat), and
    every built *.so outside dot-dirs (the py_ext extension; .install staging
    trees are dot-dirs and skipped as redundant with the .so). Deterministic
    (sorted by relative path); a kernel edit or rebuild changes the digest
    and invalidates the marker."""
    from .multirank_finalize_check_rank_verdicts import _candidate_subdirs

    files: list[Path] = []
    entry = workspace / "model_new_ascendc.py"
    if entry.is_file():
        files.append(entry)
    for sub in ("op_kernel", "kernel"):
        for d in _candidate_subdirs(workspace, sub):
            if d.is_dir():
                files += sorted(d.glob("*.h")) + sorted(d.glob("*.cpp"))
    for so in sorted(workspace.rglob("*.so")):
        rel = so.relative_to(workspace)
        if any(part.startswith(".") for part in rel.parts):
            continue  # dot-dirs (.install staging, .run logs, ...) are not
            # independent candidate bytes — the py_ext .so already binds them
        files.append(so)
    manifest = []
    for f in sorted(files, key=lambda p: p.relative_to(workspace).as_posix()):
        data = f.read_bytes()
        manifest.append(
            {
                "path": f.relative_to(workspace).as_posix(),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return hashlib.sha256(
        json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def write_verified_marker(workspace: Path, *, unverified: dict, pass_a: dict) -> None:
    """Persist the digests binding this VERIFIED verdict: verification.json

    claim bytes + candidate artifacts + golden spec_hash + the unverified set.
    """
    from . import multirank_phase_o25

    vp = workspace / "verification.json"
    marker = {
        "schema": _MARKER_SCHEMA,
        "verification_sha256": _claim_digest(vp),
        "candidate_digest": _candidate_artifact_digest(workspace),
        "spec_hash": multirank_phase_o25.load_golden_manifest(workspace).get(
            "spec_hash"
        ),
        "unverified_world_sizes": sorted(unverified or {}),
        "pass_a": dict(pass_a or {}),
    }
    (workspace / _MARKER_NAME).write_text(json.dumps(marker, indent=2))


def _marker_if_current(workspace: Path) -> "dict | None":
    """The marker iff every bound digest still matches, else None."""
    from . import multirank_phase_o25

    mp = workspace / _MARKER_NAME
    try:
        marker = json.loads(mp.read_text()) if mp.is_file() else None
    except Exception:
        return None
    if not isinstance(marker, dict) or marker.get("schema") != _MARKER_SCHEMA:
        return None
    vp = workspace / "verification.json"
    if not vp.is_file():
        return None
    if marker.get("verification_sha256") != _claim_digest(vp):
        return None
    try:
        if marker.get("candidate_digest") != (_candidate_artifact_digest(workspace)):
            return None
    except Exception:
        return None
    if marker.get("spec_hash") != multirank_phase_o25.load_golden_manifest(
        workspace
    ).get("spec_hash"):
        return None
    return marker


def stamp_verified_marker(workspace: Path, o5) -> None:
    """R2: persist the durable marker after a clean-harness VERIFIED (the FSM

    VERIFIED arm calls this for multirank ops). Non-fatal by design — a marker
    write failure costs the skip on the next resume, never the verdict.
    """
    try:
        write_verified_marker(
            workspace,
            unverified=getattr(o5, "unverified_world_sizes", None) or {},
            pass_a=(o5.measured.get("pass_a") or o5.claimed.get("pass_a")),
        )
    except Exception as e:
        log.info(f"R2 verified-marker write failed (non-fatal): {e!r}")


def try_skip_remeasure(workspace: Path, op: str):
    """Synthesize a VERIFIED O5Report when the durable marker is current and

    its unverified set is already operator-accepted and the harness is clean
    — the finalize resumes at the NEXT stage. None → full re-measure.
    """
    import fsm_finalize_coverage
    import harness_pristine
    import phase_o5

    marker = _marker_if_current(workspace)
    if marker is None:
        return None
    unv = {
        k: {
            "status": "UNVERIFIED",
            "reason": "card_shortage",
            "detail": "carried from the durable verified marker",
        }
        for k in marker.get("unverified_world_sizes") or []
    }
    # vacuous-marker guard: no verified case and no forwarded shortage —
    # accepting this marker would only re-stamp a VERIFIED that never
    # measured anything. Force the full re-measure instead.
    if not (marker.get("pass_a") or {}).get("total") and not unv:
        return None
    if not fsm_finalize_coverage.coverage_accept_satisfied(workspace, unv):
        return None
    state = harness_pristine.harness_state()
    if state.is_dirty:
        return None  # a dirty harness re-measures (PROVISIONAL path owns it)
    rep = phase_o5.O5Report(verdict="VERIFIED", truth_source="multirank")
    pa = dict(marker.get("pass_a") or {})
    rep.claimed["pass_a"] = dict(pa)
    rep.measured["pass_a"] = dict(pa)
    rep.unverified_world_sizes = unv
    rep.harness_git_state = state.state
    rep.harness_dirty = []
    rep.summary = (
        "O5 VERIFIED (durable marker): verification.json / candidate "
        "artifacts / golden spec digests all match the verified marker — "
        "re-measure skipped, finalize resumes at the next stage."
    )
    log.info(f"O5 post-verify: {rep.summary}")
    return rep
