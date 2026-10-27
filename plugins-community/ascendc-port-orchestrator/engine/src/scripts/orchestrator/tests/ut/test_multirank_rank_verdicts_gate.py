# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""multirank (multirank, design §5 Layer 4a) — finalize gate contract tests for
`_check_multirank_rank_verdicts` (+ `_check_multirank_namespace`).

The gate validates the verification.json multi-rank rank-verdict contract:
  - `multirank` object present (else multirank_verify.py did not emit rank verdicts)
  - multirank.world_sizes are ints >= 1 (any positive rank count)
  - each group has exactly world_size entries, classified PASS/FAIL
  - verdict⟺claim consistency BOTH ways (design §3.2 ALL-rank-PASS)
  - UNVERIFIED channels carry objective probe evidence
  - coverage partitions the declared campaign (no drop / no double-count)

Scoping mirrors _check_arch35_wrap_cheat: applies ONLY to multirank; other
modes (single-rank verify) are out of scope.

Scope notes:
  - Option-A plugin wiring: the gate lives in
    multirank_finalize_check_rank_verdicts (NOT re-exported by finalize_pipeline)
    and is registered ONLY through the multirank plugin's
    extra_finalize_checks — the GateID / _pass_branch_gate_specs assertions
    are replaced by plugin-registration + plugin-extras-sentinel assertions
    (there is NO GateID.MULTIRANK_RANK_VERDICTS core entry by design);
  - `_check_multirank_namespace` gets direct coverage here because the plugin
    registers it as a second gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2]))  # .../orchestrator

from plugins.multirank.multirank_finalize_check_rank_verdicts import (  # type: ignore  # noqa: E402
    _check_multirank_namespace,
    _check_multirank_rank_verdicts,
)


def _make_ws(
    tmp_path: Path,
    *,
    multirank: bool = True,
    mr: dict | None = "UNSET",
    has_vj: bool = True,
) -> Path:
    """Synthetic port_a3 workspace optionally flagged multirank, with an
    optional verification.json `multirank` block. mr="UNSET" = omit the block."""
    ws = tmp_path / "workspace_op"
    ws.mkdir(parents=True, exist_ok=True)
    state = {"opgen_mode": "port_a3_to_a5"}
    if multirank:
        state["multirank"] = True
    (ws / ".opgen_state.json").write_text(json.dumps(state))
    if has_vj:
        vj: dict = {"precision": {"status": "PASS"}}
        if mr != "UNSET":
            vj["multirank"] = mr
        (ws / "verification.json").write_text(json.dumps(vj))
    return ws


def _valid_mr(world_size: int, fail_ranks: tuple[int, ...] = ()) -> dict:
    return {
        "world_sizes": [world_size],
        "rank_verdicts": {
            str(world_size): [
                {"rank": r, "status": "FAIL" if r in fail_ranks else "PASS"}
                for r in range(world_size)
            ]
        },
    }


def test_valid_rank_verdicts_passes(tmp_path):
    ws = _make_ws(tmp_path, mr=_valid_mr(2))
    assert _check_multirank_rank_verdicts(ws) is None


def test_world_size_one_passes(tmp_path):
    """Single-rank degenerate group is valid (rank count: any positive int)."""
    ws = _make_ws(tmp_path, mr=_valid_mr(1))
    assert _check_multirank_rank_verdicts(ws) is None


def test_world_size_four_passes(tmp_path):
    ws = _make_ws(tmp_path, mr=_valid_mr(4))
    assert _check_multirank_rank_verdicts(ws) is None


def test_missing_multirank_block_rejects(tmp_path):
    ws = _make_ws(tmp_path, mr="UNSET")
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and "missing" in r.lower()


def test_world_size_three_passes(tmp_path):
    """Non-power-of-two rank counts are supported (any positive int)."""
    ws = _make_ws(tmp_path, mr=_valid_mr(3))
    assert _check_multirank_rank_verdicts(ws) is None


def test_world_size_six_passes(tmp_path):
    ws = _make_ws(tmp_path, mr=_valid_mr(6))
    assert _check_multirank_rank_verdicts(ws) is None


def test_world_size_zero_rejects(tmp_path):
    ws = _make_ws(tmp_path, mr={"world_sizes": [0], "rank_verdicts": {"0": []}})
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and "positive int" in r.lower()


def test_world_size_non_int_rejects(tmp_path):
    ws = _make_ws(
        tmp_path,
        mr={
            "world_sizes": ["2"],
            "rank_verdicts": {"2": [{"rank": 0, "status": "PASS"}]},
        },
    )
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and "positive int" in r.lower()


def test_ranks_count_mismatch_rejects(tmp_path):
    ws = _make_ws(
        tmp_path,
        mr={
            "world_sizes": [2],
            "rank_verdicts": {"2": [{"rank": 0, "status": "PASS"}]},
        },
    )
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and ("ranks" in r.lower())


def test_not_all_ranks_pass_rejects(tmp_path):
    ws = _make_ws(tmp_path, mr=_valid_mr(2, fail_ranks=(1,)))
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and "ALL-rank-PASS" in r


def test_non_multirank_mode_out_of_scope(tmp_path):
    """Gate is multirank-scoped: a non-mc2 ws with an mc2 block is ignored."""
    ws = _make_ws(tmp_path, multirank=False, mr=_valid_mr(2))
    assert _check_multirank_rank_verdicts(ws) is None


def test_no_verification_json_passes(tmp_path):
    """No verification.json → None (VERIFICATION_FILE_MISSING gate owns absence)."""
    ws = _make_ws(tmp_path, has_vj=False)
    assert _check_multirank_rank_verdicts(ws) is None


def test_plugin_gate_names_registered():
    """Option-A: the gate ids are plugin-supplied strings registered via the

    multirank plugin (there is no core GateID.MULTIRANK_RANK_VERDICTS entry —
    the plugin-extras rejection carries these names in its `gate` field).
    """
    import plugins.multirank as pm

    names = [n for n, _ in pm.get_plugin_instance().extra_finalize_checks()]
    assert names == [
        "multirank_rank_verdicts_consistency",
        "multirank_namespace_violation",
        "multirank_perf_integrity",
    ]


# ---------------------------------------------------------------------------
# T2-inclusive full-pass claim (spec t2_competitor wired runs)
# ---------------------------------------------------------------------------


def _vj_with_pass_a(tier1, inclusive, total, status="PASS_WITHIN_TOLERANCE"):
    return {
        "precision": {
            "status": status,
            "pass_a": {
                "status": status,
                "tier1_pass": tier1,
                "tier1_pass_inclusive": inclusive,
                "total": total,
            },
        }
    }


def _make_ws_with_vj(tmp_path: Path, vj: dict) -> Path:
    ws = tmp_path / "workspace_op"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / ".opgen_state.json").write_text(
        json.dumps({"opgen_mode": "port_a3_to_a5", "multirank": True})
    )
    (ws / "verification.json").write_text(json.dumps(vj))
    return ws


def test_all_pass_rank_verdicts_with_inclusive_full_claim_passes(tmp_path):
    """T2-wired run: strict tier1 < total but inclusive == total and every

    rank PASS (T2 parity arm) — the consistent full-pass shape.
    """
    vj = _vj_with_pass_a(3, 5, 5)
    vj["multirank"] = _valid_mr(2)
    ws = _make_ws_with_vj(tmp_path, vj)
    assert _check_multirank_rank_verdicts(ws) is None


def test_all_pass_rank_verdicts_with_inclusive_partial_claim_rejects(tmp_path):
    """An all-PASS rank_verdicts with an inclusive PARTIAL claim is still the

    logically-impossible pair (the inclusive count is the claim once present).
    """
    vj = _vj_with_pass_a(3, 4, 5)
    vj["multirank"] = _valid_mr(2)
    ws = _make_ws_with_vj(tmp_path, vj)
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and "logically impossible" in r


def test_strict_full_claim_without_inclusive_still_passes(tmp_path):
    """Pre-T2 archives (no tier1_pass_inclusive key) keep the strict path."""
    vj = {
        "precision": {
            "status": "PASS",
            "pass_a": {"status": "PASS", "tier1_pass": 2, "total": 2},
        }
    }
    vj["multirank"] = _valid_mr(2)
    ws = _make_ws_with_vj(tmp_path, vj)
    assert _check_multirank_rank_verdicts(ws) is None


def test_honest_partial_rank_verdicts_with_partial_claim_passes(tmp_path):
    """A PARTIAL op: FAIL ranks + inclusive partial claim — consistent."""
    vj = _vj_with_pass_a(3, 4, 5, status="PARTIAL")
    vj["multirank"] = _valid_mr(2, fail_ranks=(1,))
    ws = _make_ws_with_vj(tmp_path, vj)
    assert _check_multirank_rank_verdicts(ws) is None


def test_gate_fires_via_plugin_extras_sentinel():
    """Option-A equivalent of the source's pass-branch registration test: the

    plugin-extras sentinel MUST participate in the PASS-branch gate spec list
    (else the registered plugin gates never fire there).
    """
    from finalize_pipeline import _PLUGIN_EXTRAS_SENTINEL, _pass_branch_gate_specs

    ids = [g for g, _ in _pass_branch_gate_specs()]
    assert _PLUGIN_EXTRAS_SENTINEL in ids


# ---------------------------------------------------------------------------
# Verdict-consistency (2026-08-12, matmul_allreduce kw-1 dishonest-rank_verdicts
# incident): all-ranks-PASS rank_verdicts ⟺ full-pass precision claim, BOTH ways.
# ---------------------------------------------------------------------------
def _make_partial_ws(
    tmp_path: Path, *, tier1_pass=25, total=35, rank_verdicts=None
) -> Path:
    """PARTIAL-claiming multirank workspace (requirement-class shape) with an
    explicit rank_verdicts dict."""
    ws = tmp_path / "workspace_op"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / ".opgen_state.json").write_text(
        json.dumps({"opgen_mode": "port_a3_to_a5", "multirank": True})
    )
    if rank_verdicts is None:
        rank_verdicts = {
            "1": [{"rank": 0, "status": "PASS"}],
            "2": [{"rank": 0, "status": "FAIL"}, {"rank": 1, "status": "FAIL"}],
        }
    vj = {
        "precision": {
            "status": "PARTIAL",
            "pass_a": {"status": "PARTIAL", "tier1_pass": tier1_pass, "total": total},
        },
        "multirank": {
            "world_sizes": sorted(int(k) for k in rank_verdicts),
            "rank_verdicts": rank_verdicts,
        },
    }
    (ws / "verification.json").write_text(json.dumps(vj))
    return ws


def test_partial_claim_honest_mixed_rank_verdicts_passes(tmp_path):
    """A PARTIAL op honestly records FAIL ranks at the world_sizes whose

    cases failed T1 — structure + consistency both hold -> gate accepts.
    """
    ws = _make_partial_ws(tmp_path)
    assert _check_multirank_rank_verdicts(ws) is None


def test_partial_claim_all_pass_stencil_rejects(tmp_path):
    """kw-1's exact fraud shape: all-ranks-PASS stencil over a 25/35 PARTIAL

    claim — logically impossible (a rank with any failing case is FAIL).
    """
    rank_verdicts = {
        "1": [{"rank": 0, "status": "PASS"}],
        "2": [{"rank": 0, "status": "PASS"}, {"rank": 1, "status": "PASS"}],
    }
    ws = _make_partial_ws(tmp_path, rank_verdicts=rank_verdicts)
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and "consistency" in r


def test_full_pass_claim_with_fail_rank_rejects(tmp_path):
    """Full-pass counts (35/35) + a FAIL rank -> the other direction of the

    implication rejects (claim vs rank_verdicts disagreement).
    """
    ws = _make_partial_ws(tmp_path, tier1_pass=35, total=35)
    vj = json.loads((ws / "verification.json").read_text())
    vj["precision"]["status"] = "PASS"
    vj["precision"]["pass_a"]["status"] = "PASS"
    (ws / "verification.json").write_text(json.dumps(vj))
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and "ALL-rank-PASS" in r


def test_invalid_status_string_rejects(tmp_path):
    """Per-rank verdicts must be the classified PASS/FAIL strings — anything

    else (SKIP/N-A/etc.) is rejected as malformed rank_verdicts.
    """
    rank_verdicts = {
        "1": [{"rank": 0, "status": "PASS"}],
        "2": [{"rank": 0, "status": "SKIP"}, {"rank": 1, "status": "FAIL"}],
    }
    ws = _make_partial_ws(tmp_path, rank_verdicts=rank_verdicts)
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and "PASS/FAIL" in r


def test_plugin_extra_finalize_checks_registered(tmp_path):
    """PortA3Plugin unions the multirank extension's finalize checks so

    PARTIAL_PERSIST finalizes validate rank_verdicts too (the plugin-extras
    entry fires on BOTH finalize branches).
    """
    from plugins import detect_plugin
    from plugins.port_a3 import get_plugin_instance

    ws = _make_partial_ws(tmp_path)
    plugin = detect_plugin(ws)
    assert plugin is not None and plugin.name == "port_a3_to_a5"
    assert get_plugin_instance().is_multirank_workspace(ws) is True
    extras = plugin.extra_finalize_checks()
    names = [n for n, _ in extras]
    assert "multirank_rank_verdicts_consistency" in names
    assert "multirank_namespace_violation" in names
    # and the registered callable actually gates: honest rank_verdicts -> None
    fn = dict(extras)["multirank_rank_verdicts_consistency"]
    vj = json.loads((ws / "verification.json").read_text())
    assert fn(ws, vj) is None


# ---------------------------------------------------------------------------
# Per-case UNVERIFIED evidence + coverage partition (per-case isolation):
# multirank.cases declares the campaign; folded rank entries carry their covered
# case names; missing cases must be probe-evidenced UNVERIFIED records.
# ---------------------------------------------------------------------------
_PROBE = "npu_probe.pick_idle (test)"


def _case_campaign_mr() -> dict:
    """A fully-verified per-case campaign block: 2 cases at ws=2, folded into
    exactly 2 rank entries whose `cases` cover the declared campaign."""
    return {
        "world_sizes": [2],
        "cases": [
            {"name": "case0@ws2[randn]", "world_size": 2},
            {"name": "case1@ws2[randn]", "world_size": 2},
        ],
        "rank_verdicts": {
            "2": [
                {
                    "rank": r,
                    "status": "PASS",
                    "cases": ["case0@ws2[randn]", "case1@ws2[randn]"],
                }
                for r in range(2)
            ]
        },
    }


def test_coverage_partition_full_coverage_passes(tmp_path):
    ws = _make_ws(tmp_path, mr=_case_campaign_mr())
    assert _check_multirank_rank_verdicts(ws) is None


def test_coverage_partition_partial_with_evidenced_unverified_passes(tmp_path):
    """case0 folded into the rank verdicts; case1 unverified with full probe

    evidence -> the coverage still partitions -> gate accepts.
    """
    mc2 = _case_campaign_mr()
    for r in mc2["rank_verdicts"]["2"]:
        r["cases"] = ["case0@ws2[randn]"]
    mc2["unverified_cases"] = {
        "case1@ws2[randn]": {
            "status": "UNVERIFIED",
            "reason": "card_shortage",
            "detail": "needed 2 idle NPU(s): only 1 idle",
            "probe": _PROBE,
            "world_size": 2,
        }
    }
    ws = _make_ws(tmp_path, mr=mc2)
    assert _check_multirank_rank_verdicts(ws) is None


def test_unverified_cases_without_evidence_rejects(tmp_path):
    mc2 = _case_campaign_mr()
    for r in mc2["rank_verdicts"]["2"]:
        r["cases"] = ["case0@ws2[randn]"]
    mc2["unverified_cases"] = {
        "case1@ws2[randn]": {
            "status": "UNVERIFIED",
            "reason": "card_shortage",
            "world_size": 2,
        }
    }
    ws = _make_ws(tmp_path, mr=mc2)
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and "UNVERIFIED evidence" in r


def test_coverage_partition_dropped_case_rejects(tmp_path):
    """A declared case neither folded nor recorded unverified = a silently dropped case -> rejected."""
    mc2 = _case_campaign_mr()
    for r in mc2["rank_verdicts"]["2"]:
        r["cases"] = ["case0@ws2[randn]"]  # case1 vanished from the report
    ws = _make_ws(tmp_path, mr=mc2)
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and "coverage partition" in r
    assert "never-accounted" in r


def test_coverage_partition_overlap_rejects(tmp_path):
    """The same case in BOTH the folded verdicts and unverified_cases is a

    double-counted coverage report -> rejected.
    """
    mc2 = _case_campaign_mr()
    mc2["unverified_cases"] = {
        "case1@ws2[randn]": {
            "status": "UNVERIFIED",
            "reason": "card_shortage",
            "detail": "needed 2 idle NPU(s)",
            "probe": _PROBE,
            "world_size": 2,
        }
    }
    ws = _make_ws(tmp_path, mr=mc2)
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and "coverage partition" in r
    assert "covered∩unverified" in r


def test_coverage_partition_full_group_plus_case_entries_rejects(tmp_path):
    """A full-group UNVERIFIED placeholder and per-case unverified entries at

    the same ws are mutually exclusive -> rejected.
    """
    mc2 = {
        "world_sizes": [2],
        "cases": [
            {"name": "case0@ws2[randn]", "world_size": 2},
            {"name": "case1@ws2[randn]", "world_size": 2},
        ],
        "rank_verdicts": {},
        "unverified": {
            "2": {
                "status": "UNVERIFIED",
                "reason": "card_shortage",
                "detail": "all cases card-short",
                "probe": _PROBE,
            }
        },
        "unverified_cases": {
            "case1@ws2[randn]": {
                "status": "UNVERIFIED",
                "reason": "card_shortage",
                "detail": "needed 2 idle NPU(s)",
                "probe": _PROBE,
                "world_size": 2,
            }
        },
    }
    ws = _make_ws(tmp_path, mr=mc2)
    r = _check_multirank_rank_verdicts(ws)
    assert r is not None and "mutually exclusive" in r


def test_coverage_partition_full_group_placeholder_passes(tmp_path):
    """Full-group UNVERIFIED with multirank.cases declared: the placeholder accounts

    for every case at that ws -> coverage partitions -> gate accepts.
    """
    mc2 = {
        "world_sizes": [1, 2],
        "cases": [
            {"name": "case0@ws1[randn]", "world_size": 1},
            {"name": "case0@ws2[randn]", "world_size": 2},
            {"name": "case1@ws2[randn]", "world_size": 2},
        ],
        "rank_verdicts": {
            "1": [{"rank": 0, "status": "PASS", "cases": ["case0@ws1[randn]"]}]
        },
        "unverified": {
            "2": {
                "status": "UNVERIFIED",
                "reason": "card_shortage",
                "detail": "all 2 case(s) at world_size=2 card-short",
                "probe": _PROBE,
            }
        },
    }
    ws = _make_ws(tmp_path, mr=mc2)
    assert _check_multirank_rank_verdicts(ws) is None


# ---------------------------------------------------------------------------
# namespace gate (_check_multirank_namespace) — dedicated coverage: the
# plugin registers it as the second extra finalize gate.
# ---------------------------------------------------------------------------


def test_namespace_clean_kernel_passes(tmp_path):
    """Explicit AscendC:: qualification everywhere -> gate accepts (nest

    prj-<op>/op_kernel layout + canonical model_new_ascendc.py).
    """
    ws = _make_ws(tmp_path)
    kernel = ws / "prj-workspace_op" / "op_kernel"
    kernel.mkdir(parents=True)
    (kernel / "op.h").write_text(
        "AscendC::GlobalTensor<float> x;\nnamespace mc2_sync {}\n"
    )
    (ws / "model_new_ascendc.py").write_text("# loads the built _C.so\nimport glob\n")
    assert _check_multirank_namespace(ws) is None


def test_namespace_using_directive_rejects(tmp_path):
    """`using namespace AscendC` in the nested op_kernel is rejected with the

    file:line — multirank requires explicit AscendC:: qualification.
    """
    ws = _make_ws(tmp_path)
    kernel = ws / "prj-workspace_op" / "op_kernel"
    kernel.mkdir(parents=True)
    (kernel / "op.h").write_text("// header\nusing namespace AscendC;\n")
    r = _check_multirank_namespace(ws)
    assert r is not None and "MULTIRANK_NAMESPACE_VIOLATION" in r
    assert "op.h:2" in r


def test_namespace_using_directive_in_pybind_rejects(tmp_path):
    """pybind11.cpp at the workspace root is part of the scan surface."""
    ws = _make_ws(tmp_path)
    (ws / "pybind11.cpp").write_text("using namespace AscendC;\n")
    r = _check_multirank_namespace(ws)
    assert r is not None and "pybind11.cpp" in r


def test_namespace_non_multirank_mode_out_of_scope(tmp_path):
    ws = _make_ws(tmp_path, multirank=False)
    (ws / "kernel.h").write_text("using namespace AscendC;\n")
    assert _check_multirank_namespace(ws) is None


def test_namespace_guidance_comment_does_not_trip(tmp_path):
    """The gate judges code, not prose: the mc2/templates header's own

    guidance line ("No `using namespace AscendC` — explicit qualification
    only.") legitimately CONTAINS the forbidden phrase while forbidding it,
    and the template mandates a verbatim copy — a comment-strip-less match
    rejected every conformant workspace on the template's own text.
    """
    ws = _make_ws(tmp_path)
    kernel = ws / "prj-workspace_op" / "op_kernel"
    kernel.mkdir(parents=True)
    (kernel / "mc2_hccl_resource.h").write_text(
        "// No `using namespace AscendC` — explicit qualification only.\n"
        "AscendC::GlobalTensor<float> x;\n"
    )
    (ws / "model_new_ascendc.py").write_text("import glob\n")
    assert _check_multirank_namespace(ws) is None


def test_namespace_block_comment_and_py_comment_do_not_trip(tmp_path):
    """Block comments (C++) and # comments (python) are stripped the same

    way; the line-preserving strip keeps violation line numbers true.
    """
    ws = _make_ws(tmp_path)
    kernel = ws / "prj-workspace_op" / "op_kernel"
    kernel.mkdir(parents=True)
    (kernel / "op.h").write_text(
        "/*\n * using namespace AscendC in a block comment\n */\n"
        "AscendC::GlobalTensor<float> x;\n"
    )
    (ws / "model_new_ascendc.py").write_text(
        "# guidance: never write using namespace AscendC here\nimport glob\n"
    )
    assert _check_multirank_namespace(ws) is None


def test_namespace_real_directive_after_comments_still_rejects(tmp_path):
    """Comment stripping never blinds the gate: a real using-directive below

    comment lines is still rejected with the true (original) line number.
    """
    ws = _make_ws(tmp_path)
    kernel = ws / "prj-workspace_op" / "op_kernel"
    kernel.mkdir(parents=True)
    (kernel / "op.h").write_text("// header\n/* block */\n\nusing namespace AscendC;\n")
    r = _check_multirank_namespace(ws)
    assert r is not None and "op.h:4" in r


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
