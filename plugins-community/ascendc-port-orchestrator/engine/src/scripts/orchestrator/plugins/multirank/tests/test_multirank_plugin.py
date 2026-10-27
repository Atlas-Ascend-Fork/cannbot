# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License).
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""multirank plugin unit tests.

Covers detect() mutual-exclusion semantics + the HCCL delegation forbidden
patterns (design §3.3 attack surface), the brief text contracts, and the
runtime-coupled hooks (extra_finalize_checks / finalize_perf_capture).

The companion runtime modules (multirank_runner, multirank_finalize_check_rank_verdicts,
fsm_finalize_coverage) are NOT importable from this test —
every case that reaches them injects a fake module into sys.modules.
Protocol conformance + registry mutual-exclusion are covered by
plugins/tests/test_protocol_conformance.py and test_registry.py.
"""

from __future__ import annotations

import json
import re
import sys
import types
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_ORCH_DIR = _HERE.parent.parent.parent.parent  # src/scripts/orchestrator/
if str(_ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(_ORCH_DIR))

from plugins.multirank import MultiRankPlugin, MULTIRANK_FORBIDDEN  # noqa: E402

_ASSETS_DIR = (
    Path(__file__).resolve().parent.parent / "op_template_gen" / "multirank_assets"
)


@pytest.fixture
def plugin() -> MultiRankPlugin:
    return MultiRankPlugin()


def _write_state(
    workspace: Path, opgen_mode: str | None, backend: str = "ascendc"
) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    if opgen_mode is not None:
        (workspace / ".opgen_state.json").write_text(
            json.dumps({"opgen_mode": opgen_mode, "backend": backend})
        )
    return workspace


def test_detect_never_claims_a_workspace(plugin, tmp_path):
    """Extension plugin semantics: detect() always returns False — workspace

    detection is owned by PortA3Plugin.is_multirank_workspace().
    """
    ws = _write_state(tmp_path / "ws", "multirank")
    assert plugin.detect(ws) is False


@pytest.mark.parametrize(
    "other",
    [
        "benchmark",
        "port_a3_to_a5",
        "backward",
        "port_cuda",
        "port_pytorch",
    ],
)
def test_detect_state_driven_mutex(plugin, tmp_path, other):
    ws = _write_state(tmp_path / other, other)
    assert plugin.detect(ws) is False


def test_detect_no_state_file(plugin, tmp_path):
    ws = tmp_path / "empty"
    ws.mkdir()
    assert plugin.detect(ws) is False


def test_detect_triton_backend_defer(plugin, tmp_path):
    ws = _write_state(tmp_path / "ws", "multirank", backend="triton")
    assert plugin.detect(ws) is False


def test_check_op_host_completeness_na(plugin, tmp_path):
    assert plugin.check_op_host_completeness(tmp_path) is None


def test_canonical_filenames_ol160(plugin):
    assert plugin.verifier_canonical_filenames() == ("model_new_ascendc.py", "model.py")


def test_runs_finalize_perf_capture_via_plugin_hook(plugin):
    """The finalize perf capture switch is ON (FSM G6: never accept

    worker-reported perf without independent re-measurement). The switch only
    decides whether measure_op_perf runs; the plugin's finalize_perf_capture
    hook (multi-NPU multirank_runner --perf) is dispatched FIRST, so the generic
    single-card path stays unreachable for multirank.
    """
    assert plugin.should_run_phase_o5_perf_capture() is True
    assert callable(plugin.finalize_perf_capture)


HCCL_DELEGATION_HITS = [
    "torch.distributed.all_reduce(grad)",
    "torch.distributed.all_to_all_single(output, input)",
    "dist.all_reduce(grad)",
    "dist.all_gather(gathered, x)",
    "hcom.AllReduce(handle, ...)",
    "HcomAllReduce(...)",
    "aclnnAllReduce(...)",
    "torch_npu.npu_all_reduce(x)",
]


@pytest.mark.parametrize("snippet", HCCL_DELEGATION_HITS)
def test_forbidden_patterns_hit_hccl_delegation(snippet):
    for pattern, _desc in MULTIRANK_FORBIDDEN:
        if re.search(pattern, snippet):
            return
    pytest.fail(f"HCCL delegation snippet not caught: {snippet!r}")


HCCL_CLEAN = [
    "c = a + b",
    "y = torch.matmul(a, b)",
    "out = model(x)",
    "torch.distributed.init_process_group('hccl', rank=0, world_size=2)",
    "torch.distributed.barrier()",
    "dist.init_process_group('hccl', rank=0, world_size=2)",
    "dist.barrier()",
    "dist.destroy_process_group()",
]


@pytest.mark.parametrize("snippet", HCCL_CLEAN)
def test_forbidden_patterns_no_false_positive(snippet):
    for pattern, _desc in MULTIRANK_FORBIDDEN:
        assert not re.search(pattern, snippet), (
            f"false positive: pattern {pattern!r} matched {snippet!r}"
        )


# ---------------------------------------------------------------------------
# kw_brief_phase_block — multirank-specific Phase A-D brief content
# ---------------------------------------------------------------------------
def _brief(plugin) -> str:
    b = plugin.kw_brief_phase_block(op="mc2_test")
    assert b is not None, "kw_brief_phase_block must override (not None) for multirank"
    return b


def test_kw_brief_has_aclass_symbols(plugin):
    """A-class HCCL integration details are KB-owned (single source:

    multirank_communication.md P-P110) — the brief points at the contract
    instead of restating symbols.
    """
    b = _brief(plugin)
    assert "A-class fixed set" in b
    assert "multirank_communication.md" in b
    assert "P-P110" in b
    assert "TilingData" in b


def test_kw_brief_points_to_kb_not_external_path(plugin):
    b = _brief(plugin)
    assert "plugins/multirank/docs/multirank_communication.md" in b
    for pid in ("P-P110", "P-P111", "P-P112"):
        assert pid in b, f"KB entry anchor missing: {pid}"
    assert "agent-ascop-dev" not in b


def test_kw_brief_points_to_sync_fundamentals(plugin):
    """auto-sync=off makes intra-core sync MANDATORY knowledge — the brief must

    point the worker at sync_fundamentals.md (the systematic method home), not
    leave it to discover. (2026-07: worker shipped 4 sync errors because it never
    read sync_fundamentals.)
    """
    b = _brief(plugin)
    assert "plugins/multirank/docs/sync_fundamentals.md" in b
    assert "MANDATORY" in b or "mandatory" in b


def test_kw_brief_init_position_unconstrained(plugin):
    b = _brief(plugin)
    assert "AIV-only" not in b
    assert "YOUR choice" in b
    assert "do NOT assume" in b


def test_kw_brief_initv2_non_mandatory(plugin):
    b = _brief(plugin)
    assert "NON-mandatory" in b or "non-mandatory" in b
    assert "InitV2 MUST" not in b
    assert "InitV2 must" not in b


def test_kw_brief_forbids_host_delegation(plugin):
    b = _brief(plugin)
    assert "HCCL delegation" in b
    assert "torch.distributed" in b


def test_kw_brief_all_rank_pass_semantics(plugin):
    b = _brief(plugin)
    assert (
        ("EVERY rank PASSes" in b) or ("all-rank PASS" in b) or ("all rank PASS" in b)
    )


def test_kw_brief_structure_follows_port_source(plugin):
    b = _brief(plugin)
    # The port source IS the structural authority — compute AND
    # communication structure follow it; only A5 hardware-mapping details
    # stay free (within the locked constraints).
    assert "structural authority for the port" in b
    assert "SAME structure, not redesigned" in b
    assert "the communication structure follow" in b
    assert "never a default" in b
    # library-agnostic phrasing + the locked-items precedence rule
    assert "catlass GMM" not in b
    assert "locked items bind" in b


def test_template_claude_binds_port_source():
    tpl = (_ASSETS_DIR / "template-CLAUDE.md").read_text(encoding="utf-8")
    assert "structural authority" in tpl
    assert "re-emits the SAME" in tpl


def test_kw_brief_single_card_regression(plugin, tmp_path):
    ws = tmp_path / "plain"
    ws.mkdir()
    assert plugin.detect(ws) is False


# ---------------------------------------------------------------------------
# kw_brief_fixed_layout_block — multirank op_kernel + op_host + py_ext layout
# ---------------------------------------------------------------------------
def test_kw_brief_fixed_layout_returns_mc2_layout(plugin):
    b = plugin.kw_brief_fixed_layout_block()
    assert b is not None
    for tok in (
        "op_kernel/",
        "op_host/",
        "py_ext/",
        "Mc2InitTiling",
        "Mc2CcTiling",
        "multirank_verify.py",
        "model_new_ascendc.py",
        "KERNEL_TYPE_MIX_AIC_1_2",
    ):
        assert tok in b, f"multirank layout token missing: {tok}"


def test_kw_brief_fixed_layout_forbids_wrong_layouts(plugin):
    """multirank layout explicitly excludes PB-33 arch35 / external util dir /

    flat kernel/ / model_new_mc2.py via Hard-rules negation markers. multirank
    USES op_host (tiling + OpDef), so the test asserts the negation markers
    are present rather than the tokens absent.
    """
    b = plugin.kw_brief_fixed_layout_block()
    assert "NO `op_kernel/arch35/`" in b
    assert "NO external util directory" in b
    assert "NO flat `kernel/`" in b
    assert "`model_new_multirank.py` FORBIDDEN" in b


def test_kw_brief_fixed_layout_no_external_path(plugin):
    b = plugin.kw_brief_fixed_layout_block()
    assert "agent-ascop-dev" not in b


def test_kw_brief_fixed_layout_shorter_than_canonical(plugin):
    """multirank layout must stay a bounded override (anti-bloat guard): multirank nests

    a full msopgen project (op_kernel/op_host/py_ext/scripts/cmake) so its
    layout contract is necessarily more detailed than the port_a3 PB-33
    shape. The byte-savings invariant from port_triton does NOT transfer;
    token completeness is covered by
    test_kw_brief_fixed_layout_returns_mc2_layout + _forbids_wrong_layouts.
    """
    from briefs._common import fixed_layout_block as canonical

    b = plugin.kw_brief_fixed_layout_block()
    canon = canonical()
    # anti-bloat: bounded well above the current size, not a strict < canon
    assert len(b) < 6000, f"multirank layout ({len(b)}) unbounded growth"
    assert b != canon, "multirank layout must differ from PB-33 default"


# ---------------------------------------------------------------------------
# extra_finalize_checks — rank-verdicts + namespace + perf-integrity gates (runtime mocked)
# ---------------------------------------------------------------------------
def test_extra_finalize_checks_registers_all_gates(plugin):
    gates = plugin.extra_finalize_checks()
    assert [name for name, _gate in gates] == [
        "multirank_rank_verdicts_consistency",
        "multirank_namespace_violation",
        "multirank_perf_integrity",
    ]


def test_extra_finalize_gate_callables_delegate_lazily(plugin, monkeypatch, tmp_path):
    """The gate callables import the (not-yet-ported) runtime module lazily
    and delegate with the workspace — registration itself must not import.
    """
    seen: list = []

    def _fake_rank_verdicts(ws):
        seen.append(("rank_verdicts", ws))
        return None

    def _fake_namespace(ws):
        seen.append(("namespace", ws))
        return None

    from plugins.multirank import multirank_finalize_check_rank_verdicts as _real_gates

    monkeypatch.setattr(
        _real_gates, "_check_multirank_rank_verdicts", _fake_rank_verdicts
    )
    monkeypatch.setattr(_real_gates, "_check_multirank_namespace", _fake_namespace)

    ws = tmp_path / "mc2_ws"
    ws.mkdir()
    for _name, gate in plugin.extra_finalize_checks():
        assert gate(ws, {}) is None
    assert seen == [("rank_verdicts", ws), ("namespace", ws)]


# ---------------------------------------------------------------------------
# finalize_perf_capture — multirank_runner perf campaign (runtime mocked)
# ---------------------------------------------------------------------------
def _mc2_result(**fields):
    defaults = dict(runner_error=None, perf=None, unverified_world_sizes=None)
    defaults.update(fields)
    return types.SimpleNamespace(**defaults)


def _install_multirank_runner(monkeypatch, result):
    from plugins.multirank import multirank_runner as _real_runner

    calls: dict = {}

    def _run_all_groups(ctx, lanes=None):
        calls["args"] = (ctx.workspace, ctx.op, lanes, ctx.perf)
        return result

    monkeypatch.setattr(_real_runner, "run_all_groups", _run_all_groups)
    return calls


def _npu_tier_ws(tmp_path, name="mc2"):
    """Workspace stamped with an NPU truth tier so finalize_perf_capture
    takes the runner path."""
    from plugins.multirank import TRUTH_TIER_STATE_KEY

    ws = tmp_path / name
    ws.mkdir()
    (ws / ".opgen_state.json").write_text(
        json.dumps(
            {
                "opgen_mode": "port_a3_to_a5",
                "multirank": True,
                TRUTH_TIER_STATE_KEY: "npubench",
            }
        )
    )
    return ws


def test_finalize_perf_capture_infra_error_pauses_for_resource(
    plugin, monkeypatch, tmp_path
):
    """An infra-class runner error (real phase_o5.classify_runner_error) is a

    resource shortage the WORKER cannot fix — pause for the user instead.
    """
    ws = _npu_tier_ws(tmp_path)
    calls = _install_multirank_runner(
        monkeypatch,
        _mc2_result(
            runner_error="multirank_runner: timeout after 300s probing idle lanes"
        ),
    )
    out = plugin.finalize_perf_capture(ws, "matmul_allreduce")
    assert out["status"] == "PAUSE_RESOURCE"
    assert "timeout after" in out["reason"]
    assert out["method"] == "multirank_runner --perf multi-NPU per-case A/B"
    # the perf campaign is invoked with perf=True on the full workspace
    assert calls["args"][0] == ws
    assert calls["args"][1] == "matmul_allreduce"
    assert calls["args"][2] is None
    assert calls["args"][3] is True


def test_finalize_perf_capture_algorithm_error_is_na(plugin, monkeypatch, tmp_path):
    ws = _npu_tier_ws(tmp_path)
    _install_multirank_runner(
        monkeypatch,
        _mc2_result(runner_error="multirank_runner: rank 1 golden mismatch"),
    )
    out = plugin.finalize_perf_capture(ws, "matmul_allreduce")
    assert out["status"] == "N/A"
    assert out["na_kind"] == "MEASUREMENT_FAILED"
    assert out["reason"] == "multirank_runner: rank 1 golden mismatch"


def test_finalize_perf_capture_card_shortage_pauses(plugin, monkeypatch, tmp_path):
    ws = _npu_tier_ws(tmp_path)
    _install_multirank_runner(
        monkeypatch,
        _mc2_result(
            unverified_world_sizes={"4": {"detail": "no idle lanes"}},
        ),
    )
    fake_cov = types.ModuleType("fsm_finalize_coverage")

    def _cov_not_satisfied(w, unv):
        return False

    fake_cov.coverage_accept_satisfied = _cov_not_satisfied
    monkeypatch.setitem(sys.modules, "fsm_finalize_coverage", fake_cov)

    out = plugin.finalize_perf_capture(ws, "matmul_allreduce")
    assert out["status"] == "PAUSE_RESOURCE"
    assert "world_sizes unverified" in out["reason"]
    assert "ws=4" in out["reason"]
    assert out["unverified_world_sizes"] == {"4": {"detail": "no idle lanes"}}


def test_finalize_perf_capture_accepted_coverage_gap_proceeds(
    plugin, monkeypatch, tmp_path
):
    """An operator-accepted coverage gap must NOT re-pause at the perf stage

    (pause-resume loop); the covered result flows on (here: honestly N/A).
    """
    ws = _npu_tier_ws(tmp_path)
    _install_multirank_runner(
        monkeypatch,
        _mc2_result(
            unverified_world_sizes={"4": {"detail": "accepted gap"}},
            perf={"ratio": None},
        ),
    )
    fake_cov = types.ModuleType("fsm_finalize_coverage")

    def _cov_satisfied(w, unv):
        return True

    fake_cov.coverage_accept_satisfied = _cov_satisfied
    monkeypatch.setitem(sys.modules, "fsm_finalize_coverage", fake_cov)

    out = plugin.finalize_perf_capture(ws, "matmul_allreduce")
    assert out["status"] == "N/A"
    assert out["na_kind"] == "UNMEASURABLE_BY_DESIGN"


def test_finalize_perf_capture_no_baseline_is_na(plugin, monkeypatch, tmp_path):
    ws = _npu_tier_ws(tmp_path)
    _install_multirank_runner(
        monkeypatch, _mc2_result(perf={"ran": True, "ratio": None})
    )
    out = plugin.finalize_perf_capture(ws, "matmul_allreduce")
    assert out["status"] == "N/A"
    assert out["na_kind"] == "UNMEASURABLE_BY_DESIGN"
    assert "perf_baseline" in out["reason"]


def test_finalize_perf_capture_measured_ratio_pass(plugin, monkeypatch, tmp_path):
    ws = _npu_tier_ws(tmp_path)
    _install_multirank_runner(
        monkeypatch,
        _mc2_result(
            perf={
                "ran": True,
                "ratio": 1.42,
                "median_ratio": 1.42,
                "rows": [{"rank": 0}],
                "case_stats": {"c0": {"ratio": 1.42}},
                "candidate_us": 100.0,
                "baseline_us": 142.0,
                "trusted_receipt": {"bogus": True},
                "execution_report": {"bogus": True},
            },
        ),
    )
    out = plugin.finalize_perf_capture(ws, "matmul_allreduce")
    assert out["status"] == "PASS"
    assert out["ratio"] == 1.42
    assert out["method"] == "multirank_runner --perf multi-NPU per-case A/B"
    assert out["rows"] == [{"rank": 0}]
    assert out["case_stats"] == {"c0": {"ratio": 1.42}}
    # no trusted perf receipt plumbing — no receipt keys
    assert "trusted_receipt" not in out
    assert "execution_report" not in out


def test_finalize_perf_capture_below_parity_is_below_threshold(
    plugin, monkeypatch, tmp_path
):
    """Parity band: the escalation threshold defaults to 1.0 (paradigm-uniform

    AscendC parity target), so a sub-parity ratio lands BELOW_THRESHOLD — the
    honest status, never a fabricated PASS.
    """
    ws = _npu_tier_ws(tmp_path)
    _install_multirank_runner(monkeypatch, _mc2_result(perf={"ratio": 0.5}))
    out = plugin.finalize_perf_capture(ws, "matmul_allreduce")
    assert out["status"] == "BELOW_THRESHOLD"
    assert out["ratio"] == 0.5
