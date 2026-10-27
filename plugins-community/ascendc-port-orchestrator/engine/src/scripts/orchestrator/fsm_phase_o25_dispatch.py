# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""fsm_phase_o25_dispatch.py — Phase O2.5 reference-provider dispatch (DEBT-201).

Extracted VERBATIM from run_single_op's Phase O2.5 preamble block
(orchestrator.py) as part of the god-function decomposition. This is the
mode-dispatched reference-provider gate that runs BEFORE the FSM spawn loop:

  - port_a3_to_a5 + reference.source=a3_live →
    phase_o25_a3_ref.provision_a3_reference (live A3 truth)
  - port_a3_to_a5 + reference.source=npubench →
    phase_o25_npubench.provision_npubench_reference (staged old-format task)
  - port_a3_to_a5 + reference.source=cannbench → persisted UNSUPPORTED result
  - backward      → phase_o25_backward.provision_backward_reference
    (BACKWARD_E2E opt-out returns 98)
  - port_a3_to_a5 + multirank flag → plugins/multirank (extension) provision
    (self-contained truth-tier collection via the multirank collector)

DEPENDENCY CONTRACT: this slice references NO orchestrator-module-level names
at import time (no read-through needed) — only per-run inputs and the
mode-specific reference modules imported lazily. Sibling module objects are
the SAME ones tests patch, so `monkeypatch.setattr(<sibling>, ...)` bites
directly. The multirank canonical guard additionally resolves the (port-
missing) stock gate from the orchestrator module surface at CALL time — the
same lazy sys.modules lookup orchestrator_cmds._orch() documents.

Returns an int EXIT CODE when the run must abort (missing source → 7, ref
capture unrecoverable → 7, BACKWARD_E2E=0 opt-out → 98) and None when the O2.5
gate passed and run_single_op should proceed to Phase O3.  Provider routing is
resolved before reading A3-only state fields or importing A3-only helpers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Optional

import events
from logging_config import get_logger
from npubench.npubench_inputs import atomic_write_state
from reference_source import (
    A3_LIVE,
    CANNBENCH,
    NPUBENCH,
    ReferenceSourceError,
    load_durable_state,
    resolve_reference_binding,
)

log = get_logger(__name__)

_PORT_A3_BUILD_SOURCE_ENV = "CANNBOT_PORT_A3_BUILD_SOURCE"


def load_port_a3_build_source(*args, **kwargs):
    """Lazy compatibility seam for the live-A3-only source registry lookup."""
    from source_arch import load_port_a3_build_source as _load

    return _load(*args, **kwargs)


def verify_source_stage(*args, **kwargs):
    """Lazy compatibility seam; NPUBench/CannBench never call this function."""
    from source_arch import verify_source_stage as _verify

    return _verify(*args, **kwargs)


def _gate_tilelang_stage(
    workspace: Path, state: dict, reference_source
) -> Optional[int]:
    """TileLang2AscendC source requires the npubench reference + a valid
    staged source snapshot; an exit code, or None to proceed."""
    tilelang_claim = (
        isinstance(state.get("port_source"), dict)
        and state["port_source"].get("kind") == "port-aclnn-tilelang2ascendc"
    )
    if not tilelang_claim:
        return None
    if reference_source != NPUBENCH:
        log.info(
            "phase O2.5: TileLang2AscendC source requires reference.source=npubench; got %s",
            reference_source,
        )
        return 7
    try:
        from tilelang2ascendc_source import verify_tilelang2ascendc_source_stage

        valid_stage, stage_reason, _manifest = verify_tilelang2ascendc_source_stage(
            workspace, state
        )
    except Exception as exc:
        log.info("phase O2.5: TileLang2AscendC source verification raised: %r", exc)
        return 7
    if not valid_stage:
        log.info(
            "phase O2.5: TileLang2AscendC source snapshot rejected: %s", stage_reason
        )
        return 7
    return None


def provision_reference(
    op: str,
    workspace: Path,
    *,
    lane: int,
    extra_lanes: Optional[list[int]] = None,
    plan_only: bool = False,
) -> Optional[int]:
    """Run the mode-dispatched Phase O2.5 reference gate.

    Returns an exit code to `return` from run_single_op, or None to proceed.
    """
    # W15 (2026-05-12, ROADMAP §1.5): Phase O2.5 dispatch on opgen_mode.
    # A migration may use either live A3-CANN truth or the frozen
    # NPUKernelBench task/sidecar bundle.  The latter must not touch an A3
    # environment or private original-source checkout.
    _opgen_mode_for_o25 = None
    _backward_forward_source = None
    _opst: dict[str, Any] = {}
    # Do not open the durable state with ``Path.read_text`` here.  A provider
    # task controls other workspace files, so the one controller-owned state
    # boundary must reject a symlink consistently with reference_source.
    if (workspace / ".opgen_state.json").exists():
        try:
            _opst = dict(load_durable_state(workspace))
            if not isinstance(_opst, dict):
                raise ValueError("durable state is not a JSON object")
            _opgen_mode_for_o25 = _opst.get("opgen_mode")
            _backward_forward_source = _opst.get("backward_forward_source")
        except Exception as exc:
            log.info("phase O2.5: durable state is unreadable: %r", exc)
            return 2

    # Only the three customer modes are accepted.  Unknown or missing state fails
    # closed even when this helper is called outside ``run_single_op``.
    if _opgen_mode_for_o25 == "port_a3_to_a5":
        # Multirank extension (compute + collective-communication fusion):
        # a port_a3_to_a5 workspace flagged `multirank: true` delegates its
        # reference provision to the multirank extension plugin. This check
        # intentionally precedes every reference-source binding — the
        # multirank truth tier is resolved inside the extension, not by the
        # single-card reference-source binding.
        if _opst.get("multirank") is True:
            return _provision_multirank(op, workspace, lane)
        try:
            reference_source, reference = _reference_for_o25(_opst)
        except ReferenceSourceError as exc:
            log.info("phase O2.5: durable reference selection rejected: %s", exc)
            return 2

        tilelang_rc = _gate_tilelang_stage(workspace, _opst, reference_source)
        if tilelang_rc is not None:
            return tilelang_rc

        # These branches intentionally precede every source-stage check,
        # port_a3_source field read, private build-source lookup, and A3 import.
        # A frozen benchmark is functional truth; the migration source tree is
        # only generation provenance and must not be consulted in this gate.
        if reference_source == NPUBENCH:
            return _provision_npubench(workspace, reference, lane)
        if reference_source == CANNBENCH:
            return _provision_cannbench(workspace, _opst, reference, lane)

        # From here on the only remaining registered source is live A3.  It is
        # the sole branch allowed to read A3-only fields or load A3 helpers.
        if reference_source != A3_LIVE:  # Defensive even though registry validates.
            log.info(
                "phase O2.5: unsupported durable reference source=%r", reference_source
            )
            return 2
        return _provision_a3_live(op, workspace, lane, _opst)
    elif _opgen_mode_for_o25 == "backward":
        return _provision_backward(op, workspace, lane, _backward_forward_source)
    log.info(
        "phase O2.5: unsupported or missing opgen_mode=%r; expected one of "
        "port_a3_to_a5/backward",
        _opgen_mode_for_o25,
    )
    return 2


def _provision_a3_live(
    op: str, workspace: Path, lane: int, state: dict
) -> Optional[int]:
    """The live-A3 branch: verify the migration source stage + the private
    build-source binding, then dispatch. The sole branch allowed to read
    A3-only fields or load A3 helpers."""
    _port_a3_source = state.get("port_a3_source")
    _port_a3_build_source = os.environ.pop(_PORT_A3_BUILD_SOURCE_ENV, None)

    valid_stage, stage_reason, _stage_manifest = verify_source_stage(workspace, state)
    if not valid_stage:
        log.info(
            "phase O2.5: migration source-only snapshot rejected: %s",
            stage_reason,
        )
        return 7

    try:
        registered_build_source = load_port_a3_build_source(
            workspace,
            source_stage_digest=state.get("source_stage_digest"),
        )
    except (OSError, ValueError) as exc:
        log.info(
            "phase O2.5: private migration build-source binding rejected: %s",
            exc,
        )
        return 7
    if _port_a3_build_source is not None:
        try:
            transient_build_source = (
                Path(_port_a3_build_source).expanduser().resolve(strict=True)
            )
        except (OSError, RuntimeError) as exc:
            log.info(
                "phase O2.5: transient migration build source is invalid: %r",
                exc,
            )
            return 7
        if transient_build_source != registered_build_source:
            log.info("phase O2.5: transient/private migration build-source mismatch")
            return 7
    return _provision_port_a3(
        op, workspace, lane, _port_a3_source, str(registered_build_source)
    )


def _backward_e2e_optout(op: str, bref) -> int:
    """BACKWARD_E2E=0 opt-out: stop at the B3.2 reference boundary.

    Reference truth + canonical model.py / forward_spec.py / backward_ref.json
    / backward_cpu_truth.pt are on disk; no worker spawn. For reference-truth
    debugging / inspecting the autograd oracle without a full generation run."""
    print("=" * 72)
    print(
        f"B3.2 (BACKWARD_E2E=0): backward reference truth READY for {op} — "
        f"{bref.n_ok} scoreable cases, grads for {bref.wrt}."
    )
    print(f"  artifacts: {', '.join(bref.artifacts)}")
    print(
        "  Worker kernel-gen + on-hardware verify SKIPPED (opt-out). "
        "Unset BACKWARD_E2E to run end-to-end."
    )
    print("=" * 72)
    return 98


def _reference_for_o25(
    state: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any]]:
    """Resolve only the registered explicit binding; never infer legacy A3."""
    reference = resolve_reference_binding(state)
    return str(reference["source"]), reference


def _provision_npubench(
    workspace: Path, reference: Mapping[str, Any], lane: int
) -> Optional[int]:
    """Dispatch the old-format NPUKernelBench preflight without A3 imports."""
    try:
        import phase_o25_npubench
    except ImportError as exc:
        log.info("phase O2.5 (npubench): provider module is unavailable: %s", exc)
        return 7
    return phase_o25_npubench.provision_npubench_reference(
        workspace=workspace,
        reference=reference,
        lane=lane,
    )


def _provision_cannbench(
    workspace: Path,
    state: Mapping[str, Any],
    reference: Mapping[str, Any],
    lane: int,
) -> int:
    """Persist CannBench's reserved-but-unimplemented terminal provider state."""
    updated = dict(state)
    updated_reference = dict(reference)
    updated_reference["provisioning_status"] = {
        "verdict": "UNSUPPORTED_REFERENCE_SOURCE",
        "source": CANNBENCH,
        "retryable": False,
    }
    updated["reference"] = updated_reference
    try:
        atomic_write_state(workspace, updated)
    except Exception as exc:
        log.info(
            "phase O2.5 (cannbench): could not persist unsupported result: %r", exc
        )
        return 2
    events.emit(
        workspace,
        "orchestrator.phase_o25_cannbench_block",
        lane=lane,
        data={"verdict": "UNSUPPORTED_REFERENCE_SOURCE", "retryable": False},
    )
    log.info("phase O2.5 (cannbench): UNSUPPORTED_REFERENCE_SOURCE")
    return 7


def _provision_port_a3(
    op: str,
    workspace: Path,
    lane: int,
    _port_a3_source,
    _port_a3_build_source=None,
) -> Optional[int]:
    """Require a complete live A3 reference capture before proceeding."""
    if not _port_a3_source:
        log.info(
            "phase O2.5 (port_a3_to_a5): port_a3_source missing "
            "from .opgen_state.json — cannot proceed. Re-invoke with "
            "`python3 -m orchestrator --port-a3-ops <ops-nn-op-dir>`."
        )
        events.emit(
            workspace,
            "orchestrator.phase_o25_port_a3_block",
            lane=lane,
            data={"verdict": "MISSING_PORT_A3_SOURCE"},
        )
        return 7
    import phase_o25_a3_ref

    try:
        from briefs._common import load_env as __load_env_a3

        __env_a3 = __load_env_a3()
    except Exception as _e:
        log.info(f"phase O2.5 (port_a3_to_a5): failed to load env: {_e!r}")
        return 7
    o25_a3 = phase_o25_a3_ref.provision_a3_reference(
        op_dir=Path(_port_a3_source),
        source_build_op_dir=(
            Path(_port_a3_build_source) if _port_a3_build_source else None
        ),
        workspace=workspace,
        a3_host=__env_a3.a3_host,
        a3_user=__env_a3.a3_user or "root",
        a3_container=__env_a3.a3_container,
        a3_cann_path=__env_a3.a3_cann_path,
        probe_only=False,  # W14b live exec
    )
    # A cross-generation run may proceed only with a complete live source-device
    # capture.  Probe-only or synthetic truth is not an acceptable substitute.
    if o25_a3.verdict != "READY":
        print(phase_o25_a3_ref.format_block_message(op, o25_a3))
        events.emit(
            workspace,
            "orchestrator.phase_o25_port_a3_block",
            lane=lane,
            data={"verdict": o25_a3.verdict, "errors": o25_a3.errors},
        )
        return 7
    log.info(f"phase O2.5 (port_a3_to_a5): {o25_a3.summary}")
    # port_a3 provisioned its own A3-CANN reference (a3_reference_runnable.json
    # + edge_dataset.pt with a3_outputs); the stock CPU-truth check would fail
    # looking for ref_runnable.json, so we skip it and proceed to Phase O3.
    return None


def _provision_backward(
    op: str,
    workspace: Path,
    lane: int,
    _backward_forward_source,
) -> Optional[int]:
    """backward O2.5: self-contained autograd reference. Returns 7 on missing
    forward-spec / provision failure, 98 on BACKWARD_E2E=0 opt-out, None to
    proceed."""
    # B3.2 (BACKWARD_PLUGIN_DESIGN §5.5): backward (gradient) mode O2.5.
    # Produce the backward reference truth SELF-CONTAINED (autograd oracle
    # over the forward spec — NO edge_dataset, NO NPU/A3/CANN). The owner-
    # fixed decision (§5.5) is the self-contained verify path that mul_grad
    # hardware-validated, not the benchmark edge_dataset path (which depends
    # on the github-unreachable benchmark submodule).
    if not _backward_forward_source:
        log.info(
            "phase O2.5 (backward): backward_forward_source missing from "
            ".opgen_state.json — re-invoke with `--backward <forward_spec.py>`."
        )
        events.emit(
            workspace,
            "orchestrator.phase_o25_backward_block",
            lane=lane,
            data={"verdict": "FORWARD_SPEC_MISSING"},
        )
        return 7
    import phase_o25_backward

    bref = phase_o25_backward.provision_backward_reference(
        workspace=workspace,
        forward_spec=Path(_backward_forward_source),
        op=op,
    )
    if bref.verdict != "READY":
        print(phase_o25_backward.format_block_message(op, bref))
        events.emit(
            workspace,
            "orchestrator.phase_o25_backward_block",
            lane=lane,
            data={"verdict": bref.verdict, "errors": bref.errors},
        )
        return 7
    log.info(f"phase O2.5 (backward): {bref.summary}")
    events.emit(
        workspace,
        "orchestrator.phase_o25_backward_ready",
        lane=lane,
        data={
            "n_ok": bref.n_ok,
            "n_skipped": bref.n_skipped,
            "wrt": bref.wrt,
            "artifacts": bref.artifacts,
        },
    )
    if os.environ.get("BACKWARD_E2E") != "0":
        # B3.3b DEFAULT (2026-05-31): `orch --backward` runs END-TO-END.
        # Flow into the worker loop; the backward worker brief
        # (BackwardPlugin.kw_brief_phase_block, B3.3a) drives self-contained
        # generation + verify vs this autograd reference. Synthesize a READY
        # O25Report so the stock-path artifact check is skipped (mirrors the
        # port_a3 _port_a3_handled flow).
        #
        # Default flipped ON after increment-2 (#313, e1841476) landed the
        # finalize/phase_o5 backward-awareness (BackwardPlugin op_host override
        # + phase_o5_runner.backward_verify_runner + the pass_a/pass_b-N/A
        # schema contract) AND a full cold-start `BACKWARD_E2E=1 orch --backward`
        # e2e ran end-to-end to a clean archive (rms_norm_grad, 6/6 precision
        # PASS, O5 VERIFIED, finalize→done, zero manual spawn/finalize —
        # 2026-05-31). Opt-OUT with `BACKWARD_E2E=0` to stop at the B3.2
        # reference boundary (reference-only, no worker; for ref-truth debugging).
        log.info(
            "phase O2.5 (backward): flowing to worker loop "
            "(B3.3b end-to-end default; set BACKWARD_E2E=0 to stop at reference)"
        )
        # backward provisioned its own self-contained autograd reference;
        # skip the stock CPU-truth check and proceed to Phase O3.
        return None
    return _backward_e2e_optout(op, bref)


# The canonical five O2.5 artifacts every mode provider publishes through
# o25_mode_reference.publish_mode_reference (same filenames the source's
# phase_o25.check_reference_artifacts gated on).
_MULTIRANK_CANONICAL_ARTIFACTS = (
    "input_gen.py",
    "edge_inputs.pt",
    "manifest.json",
    "edge_dataset.pt",
    "ref_runnable.json",
)


def _orchestrator_module():
    """Live handle to the orchestrator MODULE, resolved lazily at CALL time.

    Same lookup orchestrator_cmds._orch() documents (kept local per the
    sibling-module convention): orchestrator.py can sit in sys.modules under
    `orchestrator`, `orchestrator.orchestrator` or `__main__`; pick the first
    candidate carrying the orchestrator globals so the package shell is never
    mistaken for the module. Call-time attribute LOOKUP keeps the
    monkeypatch-bite contract on `orchestrator.<name>`.
    """
    import sys

    for _name in ("orchestrator", "orchestrator.orchestrator", "__main__"):
        _m = sys.modules.get(_name)
        if _m is not None and hasattr(_m, "run_single_op"):
            return _m
    return None


def _check_canonical_artifacts(workspace: Path):
    """Local canonical five-artifact guard (source's phase_o25 gate, ported).

    Presence of every canonical filename + ref_runnable verdict RUNNABLE. The
    port ships no stock phase_o25 module, so the multirank branch runs this
    inline fail-closed check when no gate is bound on the orchestrator module
    surface.
    """
    missing = [
        name
        for name in _MULTIRANK_CANONICAL_ARTIFACTS
        if not (workspace / name).is_file()
    ]
    if missing:
        return SimpleNamespace(
            verdict="MISSING_ARTIFACTS",
            missing=missing,
            failed=[],
            recommendations=[f"  - missing {name}" for name in missing],
            summary=f"canonical multirank artifacts missing: {', '.join(missing)}",
        )
    try:
        verdict = json.loads((workspace / "ref_runnable.json").read_text()).get(
            "verdict"
        )
    except Exception as exc:
        verdict = None
        reason = repr(exc)
    else:
        reason = str(verdict)
    if verdict != "RUNNABLE":
        return SimpleNamespace(
            verdict="REF_FAILED",
            missing=[],
            failed=["ref_runnable.json"],
            recommendations=[
                f"  - ref_runnable.json verdict is {reason}, expected RUNNABLE"
            ],
            summary=f"ref_runnable verdict {reason!r} != RUNNABLE",
        )
    return SimpleNamespace(
        verdict="READY",
        missing=[],
        failed=[],
        recommendations=[],
        summary="canonical multirank artifacts present (five-artifact check)",
    )


def _multirank_canonical_gate(workspace: Path):
    """Resolve the common canonical O2.5 artifact guard for multirank.

    Source parity (v3.18.1 integration): multirank's O2.5 still runs the
    common canonical guard after the provider returns READY —
    multirank_phase_o25 publishes the standard five artifacts via
    publish_mode_reference, so the stock gate applies as usual (no SSH
    ref_preflight: the multirank ref_runnable.json is self-contained RUNNABLE).
    This port has no stock phase_o25 module, so the gate is consumed from the
    orchestrator module surface (`orchestrator.phase_o25`) when bound there,
    with the local five-artifact check as the fail-closed default.
    """
    _orch_mod = _orchestrator_module()
    _gate = getattr(_orch_mod, "phase_o25", None) if _orch_mod is not None else None
    if _gate is not None and hasattr(_gate, "check_reference_artifacts"):
        return _gate.check_reference_artifacts(workspace)
    return _check_canonical_artifacts(workspace)


def _provision_multirank(
    op: str,
    workspace: Path,
    lane: int,
) -> Optional[int]:
    """Multirank extension O2.5: self-contained multi-rank CPU reference.
    Returns 7 on provision failure / canonical gate failure, None to proceed.

    Delegates to the multirank extension plugin
    (`plugins/multirank/multirank_phase_o25.provision_multirank_reference`) —
    the core dispatch only routes; the capability lives in the extension.
    """
    # Self-contained multi-rank CPU reference: per-case golden tree
    # golden/<case>.pt (identity + full inputs + canonical outputs) +
    # golden/manifest.json + canonical model.py + ref_runnable.json
    # with verdict RUNNABLE, self-contained — NO SSH. The worker (Phase A-D)
    # authors the AscendC fusion kernel + verifies vs this truth via
    # multirank_runner on real NPU.
    from plugins.multirank import multirank_phase_o25

    mref = multirank_phase_o25.provision_multirank_reference(
        workspace=workspace,
        op=op,
    )
    if mref.verdict != "READY":
        print(multirank_phase_o25.format_block_message(op, mref))
        events.emit(
            workspace,
            "orchestrator.phase_o25_multirank_block",
            lane=lane,
            data={"verdict": mref.verdict, "errors": mref.errors},
        )
        return 7
    canonical = _multirank_canonical_gate(workspace)
    if canonical.verdict != "READY":
        print("=" * 72)
        print(
            f"Multirank Phase O2.5 BLOCK — op: {op}  canonical gate: "
            f"{canonical.verdict}"
        )
        for rec in getattr(canonical, "recommendations", None) or []:
            print(f"  - {rec}")
        print("=" * 72)
        events.emit(
            workspace,
            "orchestrator.phase_o25_multirank_block",
            lane=lane,
            data={
                "verdict": canonical.verdict,
                "errors": list(getattr(canonical, "recommendations", None) or []),
                "failed": list(getattr(canonical, "failed", None) or []),
                "missing": list(getattr(canonical, "missing", None) or []),
            },
        )
        return 7
    log.info(f"phase O2.5 (multirank): {mref.summary}")
    events.emit(
        workspace,
        "orchestrator.phase_o25_multirank_ready",
        lane=lane,
        data={
            "world_sizes": mref.world_sizes,
            "n_ok": mref.n_ok,
            "n_skipped": mref.n_skipped,
            "artifacts": mref.artifacts,
        },
    )
    # multirank provisioned its own self-contained reference; skip the stock
    # CPU-truth check and proceed to Phase O3.
    return None
