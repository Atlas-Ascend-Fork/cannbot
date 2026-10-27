# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License).
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""O5 verification flow for the finalize phase (module split from fsm_phase_finalize).

The runner dispatch, infra-retry loop, candidate stability guard, mismatch /
runner-failure classification, and the per-class rollback handlers. The
finalize entry (handle_finalize) and the promotion routing stay in
fsm_phase_finalize.
"""

from __future__ import annotations

import functools
import importlib
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import NamedTuple, Optional

import events
import finalize_pipeline
import fsm_finalize_coverage
import phase_o5
import schema_norm
import state_executor
from orchestrator_coldstart import _prepare_npubench_candidate_repair
from fsm_context import HandlerResult, OrchestratorContext

log = logging.getLogger(__name__)

_O5_INFRA_MAX_RETRIES = 2


_O5_INFRA_RETRY_BACKOFF_ENV = "CANNBOT_O5_INFRA_RETRY_BACKOFF_SEC"


_O5_INFRA_RETRY_BACKOFF_SECONDS = 600


_sleep = time.sleep


def _o5_infra_retry_backoff_seconds() -> int:
    raw = os.environ.get(_O5_INFRA_RETRY_BACKOFF_ENV)
    if raw is None:
        return _O5_INFRA_RETRY_BACKOFF_SECONDS
    try:
        value = int(raw.strip())
    except ValueError:
        return _O5_INFRA_RETRY_BACKOFF_SECONDS
    return max(value, 0)


_HOST_COPY_FAULT_MAX_TRANSIENT_ENV = "AOG_O5_HOST_COPY_FAULT_MAX_TRANSIENT"


_HOST_COPY_FAULT_MAX_TRANSIENT = 2


_HOST_COPY_FAULT_ESCALATION_FILE = ".o5_host_copy_fault_escalation.json"


def _host_copy_fault_max_transient() -> int:
    raw = os.environ.get(_HOST_COPY_FAULT_MAX_TRANSIENT_ENV)
    if raw is None:
        return _HOST_COPY_FAULT_MAX_TRANSIENT
    try:
        value = int(raw.strip())
    except ValueError:
        return _HOST_COPY_FAULT_MAX_TRANSIENT
    return max(value, 0)


def _candidate_tree_from_report(report: object) -> Optional[str]:
    """Return a candidate-tree digest from one evaluation report section."""
    if not isinstance(report, dict):
        return None
    binding = report.get("evaluation_binding")
    if not isinstance(binding, dict):
        return None
    tree = binding.get("candidate_tree_sha256")
    return str(tree) if tree else None


def _o5_candidate_tree_key(o5) -> str:
    """Identity of the candidate TREE under evaluation, stable across evals.

    2026-08-27 (PR875 3_FusionAttention oc line, equiv analysis P1-b): keying
    the copy-fault escalation on the precision ``binding_sha256`` never works —
    every O5 evaluation mints a fresh binding, so the per-binding count is
    always 1 and the same wedging candidate tree retries as "transient"
    forever.  Key on ``candidate_tree_sha256`` instead: identical trees keep
    accumulating, a worker re-author (new tree) resets the counter.  Fall back
    to the per-eval binding only when no tree digest is reachable.
    """
    measured = getattr(o5, "measured", None)
    if isinstance(measured, dict):
        for section in ("precision", "performance", "evaluate"):
            tree = _candidate_tree_from_report(measured.get(section))
            if tree:
                return tree
        precision = measured.get("precision")
        if isinstance(precision, dict):
            binding = precision.get("binding_sha256")
            if binding:
                return str(binding)
    return "unknown"


def _bump_host_copy_fault_escalation(workspace: Path, o5) -> int:
    """Increment and return the per-candidate-tree copy-fault count."""
    path = workspace / _HOST_COPY_FAULT_ESCALATION_FILE
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    key = _o5_candidate_tree_key(o5)
    entry = data.get(key)
    count = int(entry.get("count", 0)) + 1 if isinstance(entry, dict) else 1
    data[key] = {"count": count, "last_ts": time.time()}
    try:
        path.write_text(json.dumps(data, indent=1, sort_keys=True))
    except OSError:
        pass
    return count


def _mark_host_copy_fault_deterministic(ctx: OrchestratorContext, o5, count: int):
    """Stop calling a recurring copy fault transient; hand the worker the truth."""
    note = (
        f"host copy-fault classification fired {count}x for the SAME candidate "
        "tree — a transient host window does not reproduce byte-identically. "
        "Treat as a CANDIDATE device-kernel hard fault surfaced asynchronously "
        "at a copy op (torch_npu launches are async; a 507035/507015 at an H2D "
        "copy means an EARLIER launch wedged the device). Debug recipe: re-run "
        "the eval child with ASCEND_LAUNCH_BLOCKING=1 for true attribution, "
        "then bisect with per-launch aclrtSynchronizeStream. 2026-08-27 "
        "42_CoTAttention precedent: wedging kernel was cot_softmax_f32 (aivec "
        "error 340, VEC UB access not aligned; PB-21 pure-PipeBarrier pattern). "
        "This is NOT infra — do NOT wait out a window; fix the candidate."
    )
    log.error("O5 host copy-fault escalation: %s", note)
    events.emit(
        ctx.workspace,
        "orchestrator.phase_o5_host_copy_fault_deterministic",
        lane=ctx.lane,
        data={"count": count, "summary": o5.summary[:200]},
    )
    return phase_o5.O5Report(
        verdict="MISMATCH",
        summary=(o5.summary + " | " + note)[:2000],
        truth_source=getattr(o5, "truth_source", "unresolved"),
        mismatches=list(getattr(o5, "mismatches", None) or []),
        claimed=getattr(o5, "claimed", None) or {},
        measured=getattr(o5, "measured", None) or {},
        harness_git_state=getattr(o5, "harness_git_state", None),
        harness_dirty=getattr(o5, "harness_dirty", False),
    )


def _load_ascendc_static_checker():
    """Load the existing standalone checker without widening ``sys.path``."""
    checker_path = Path(__file__).resolve().parent.parent / "ascendc_static_check.py"
    spec = importlib.util.spec_from_file_location(
        "_aog_finalize_ascendc_static_check", checker_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load static checker from {checker_path}")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


def _is_delivery_cpp_source(path: Path, root: Path) -> bool:
    """Exclude generated/build/backup files beneath a declared source root."""
    if path.is_symlink() or not path.is_file() or path.suffix not in (".h", ".cpp"):
        return False
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    for part in relative.parts[:-1]:
        if _is_generated_or_backup_dir(part):
            return False
    return True


def _is_generated_or_backup_dir(part: str) -> bool:
    """Return whether ``part`` identifies an excluded generated subtree."""
    lowered = part.lower()
    return (
        part.startswith(".")
        or lowered in {"build", "build_out", "cmakefiles", "__pycache__"}
        or lowered.startswith("cmake-build")
        or lowered.endswith("_bak")
    )


def _delivery_cpp_roots(workspace: Path) -> list[Path]:
    """Return only this plugin's declared, present AscendC delivery roots.

    Never fall back to walking the whole workspace: it can contain staged
    upstream sources, build trees, or other prior-art that is not this run's
    deliverable.  Missing roots are left to the existing completeness and
    provenance eligibility gates.
    """
    plugin = getattr(finalize_pipeline, "_get_active_plugin")(workspace)
    if plugin is None:
        return []
    workspace_aware = getattr(plugin, "kernel_cpp_dirs_for_workspace", None)
    declared = (
        workspace_aware(workspace)
        if callable(workspace_aware)
        else plugin.kernel_cpp_dirs()
    )
    workspace_real = workspace.resolve()
    roots: list[Path] = []
    for relative in declared:
        candidate = (workspace / relative).resolve()
        try:
            candidate.relative_to(workspace_real)
        except ValueError:
            log.warning(
                "static check: ignoring delivery root outside workspace: %s", relative
            )
            continue
        if not candidate.is_dir():
            continue
        # The existing checker supports .h/.cpp.  Do not call it on an empty
        # root because its all-green empty report is not useful evidence.
        if any(
            _is_delivery_cpp_source(path, candidate) for path in candidate.rglob("*")
        ):
            roots.append(candidate)
    return roots


def _run_delivery_static_check(workspace: Path) -> dict:
    """Run the existing checker on current-plugin delivery roots only.

    Checker load/runtime/report errors fail closed.  A workspace with no
    declared present source root is explicitly skipped instead of scanning
    unrelated files; existing finalize eligibility owns missing-deliverable
    rejection.
    """
    try:
        roots = _delivery_cpp_roots(workspace)
        if not roots:
            return {
                "passed": True,
                "skipped": "no declared present AscendC delivery source",
                "reports": [],
            }
        checker = _load_ascendc_static_checker()
        reports = []
        for root in roots:
            # ``run_checks`` normally walks recursively.  Feed it the same
            # check registry and prestage-aware file collector, narrowed to
            # current delivery source (not build products or stale backups).
            collect_files = checker.collect_files
            delivery_files = [
                path
                for path in collect_files(str(root))
                if _is_delivery_cpp_source(Path(path), root)
            ]

            def collect_delivery_files(_directory, files=tuple(delivery_files)):
                """Return the already scoped files for this delivery root."""
                return list(files)

            checker.collect_files = collect_delivery_files
            try:
                report = checker.run_checks(str(root))
            finally:
                checker.collect_files = collect_files
            if not isinstance(report, dict) or not isinstance(
                report.get("passed"), bool
            ):
                raise RuntimeError(f"malformed static-check report for {root}")
            reports.append({"root": str(root), "report": report})
        return {
            "passed": all(item["report"]["passed"] for item in reports),
            "reports": reports,
        }
    except Exception as exc:
        return {"passed": False, "error": f"{type(exc).__name__}: {exc}", "reports": []}


def _multirank_o5_runner(workspace: Path):
    """Build the O5 runner for a multirank workspace (truth_source
    "multirank"): run every declared world_size group via
    run_all_groups with lanes=None — the runner auto-allocates each group's
    card set from the live idle probe right before that group's launch and
    re-confirms the cards are process-clean afterwards (`--lane` lists are
    inert for multirank). Allocation/probe failures surface as runner_error so the
    O5 infra-retry path treats busy-cards as transient. Extracted from
    _o5_post_verify (GOD_FUNCTION budget)."""
    from plugins.multirank import multirank_runner

    return lambda ws, _op, _ln: multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ws, op=_op), None
    )


def _o5_runner_for_workspace(
    workspace: Path,
    *,
    extra_lanes: Optional[list[int]] = None,
    truth_source: Optional[str] = None,
):
    """Reload the O5 runner and select its truth-source-specific entrypoint."""
    truth_source = phase_o5.expected_truth_source(workspace)
    if truth_source == "npubench":
        # Import no legacy O5 transport on this route: the NPUKernelBench
        # provider owns both its immutable task oracle and target evaluation.
        from npubench import npubench_o5_runner

        return functools.partial(
            npubench_o5_runner.npubench_verify_runner,
            extra_lanes=tuple(extra_lanes or ()),
        )
    import phase_o5_runner

    importlib.reload(phase_o5_runner)
    _ts = (
        truth_source
        if truth_source is not None
        else (phase_o5.expected_truth_source(workspace))
    )
    if _ts == "multirank":
        # Multirank multi-NPU re-measure: run_all_groups covers EVERY declared case
        # world_size group (never ssh_runner). run() covers a SINGLE group —
        # using it made all but one group silently drop out of the campaign
        # whenever a spec declared >1 world_size. run_all_groups delegates
        # back to run() for one-group specs (behaviour-identical). ALL-rank-
        # PASS is enforced by per-rank exit-code aggregation + the
        # _check_multirank_rank_verdicts gate. The physical card set is
        # AUTO-ALLOCATED from the live idle probe (--lane lists are inert).
        return _multirank_o5_runner(workspace)
    if _ts == "backward_autograd":
        return phase_o5_runner.backward_verify_runner
    return phase_o5_runner.ssh_runner


def _skip_remeasure_if_marked(ctx: OrchestratorContext, truth_source):
    """R2 durable VERIFIED marker (multirank): a current marker (digests match,
    unverified accepted, harness clean) skips the re-measure — a retry after
    a post-precision failure resumes at the failed stage instead of re-rolling
    the card-weather dice. None → full re-measure."""
    if truth_source != "multirank":
        return None
    from plugins.multirank import multirank_o5_reconcile

    return multirank_o5_reconcile.try_skip_remeasure(ctx.workspace, ctx.op)


def _dispatch_o5_runner_failed(
    ctx: OrchestratorContext,
    snap,
    o5,
    truth_source,
) -> HandlerResult:
    """Route an O5 RUNNER_FAILED verdict by truth source.

    Multirank workspaces adopt fsm_finalize_coverage's infra-vs-algorithm split:
    an infra failure that survived the bounded in-place retry is an EXTERNAL
    resource problem (lane auto-allocation / probe / ssh) the worker cannot
    fix — it pauses at await_user_decision instead of spawning a worker with
    nothing to do. Non-multirank modes keep this module's legacy routing (always
    await_worker): adopting the split there would change non-multirank behavior
    (infra → pause instead of a worker respawn), which this wiring
    deliberately does not do."""
    if truth_source == "multirank":
        return getattr(fsm_finalize_coverage, "_handle_o5_runner_failed")(ctx, snap, o5)
    return _handle_o5_runner_failed(ctx, snap, o5)


def _run_o5_verification(ctx: OrchestratorContext, runner):
    """Run the independent O5 verifier through the selected runner."""
    return phase_o5.post_verify_for_finalize(
        ctx.workspace,
        ctx.op,
        lane=ctx.lane,
        runner=runner,
    )


def _retry_infra_o5_verification(
    ctx: OrchestratorContext, o5, runner, backoff_seconds: Optional[int] = None
):
    """Retry only bounded infrastructure failures without consuming an iteration."""
    infra_retries = 0
    while (
        o5.verdict == "RUNNER_FAILED"
        and getattr(o5, "rollback_kind", None) == "infra"
        and infra_retries < _O5_INFRA_MAX_RETRIES
    ):
        infra_retries += 1
        log.warning(
            f"O5 RUNNER_FAILED (infra): {o5.summary[:160]} — re-attempting O5 "
            f"in place (retry {infra_retries}/{_O5_INFRA_MAX_RETRIES}); "
            "artifact intact, no worker respawn."
        )
        events.emit(
            ctx.workspace,
            "orchestrator.phase_o5_infra_retry",
            lane=ctx.lane,
            data={
                "attempt": infra_retries,
                "max": _O5_INFRA_MAX_RETRIES,
                "summary": o5.summary[:200],
            },
        )
        # P0-1 device-class split (2026-08-28): callers that already know the
        # failure is a device-class error pass backoff_seconds=0 — device
        # errors do not self-heal, so the 600s transient-window wait is pure
        # budget burn (3FA 507015: 4x600s over 95 minutes, zero recovery).
        backoff = (
            _o5_infra_retry_backoff_seconds()
            if backoff_seconds is None
            else max(backoff_seconds, 0)
        )
        if backoff > 0:
            log.info(
                "O5 infra retry backoff: sleeping %ss before re-attempt "
                "(transient host window avoidance)",
                backoff,
            )
            _sleep(backoff)
        o5 = _run_o5_verification(ctx, runner)
        # The retry may be the first attempt that reaches the authored
        # candidate validator (for example after a transient target-build
        # error).  Preserve that structured repair signal immediately instead
        # of allowing another infra retry to erase it.
        if (
            o5.verdict == "RUNNER_FAILED"
            and _is_direct_npubench_candidate_failure(ctx.workspace)
            and _is_repairable_npubench_candidate_failure(o5)
        ):
            break
    return o5


def _mismatch_at_worker_cap(
    ctx: OrchestratorContext,
    snap,
    o5,
) -> Optional[HandlerResult]:
    """Stop an O5 mismatch before a capped worker would create a loop."""
    workspace = ctx.workspace
    if not state_executor.at_iter_cap(workspace, "await_worker"):
        return None
    count = snap.iter_counts.get("worker", 0)
    cap = state_executor.iter_cap("await_worker", workspace=workspace)
    log.critical(
        f"O5 MISMATCH while await_worker already at iter_cap ({count}/{cap}). "
        f"Cannot progress — routing back would infinite-loop. Manual intervention "
        f"required: investigate why measured ({o5.measured}) differs from claim "
        f"({o5.claimed}); possibilities: (a) stale on-A5 binary not rebuilt, "
        f"(b) re-runner uses different inputs than worker, (c) genuine "
        f"non-determinism worker didn't see, (d) worker fabricated case_verdicts. "
        f"Diagnostic: ls workspace/{ctx.op}/kernel/build/ + diff "
        f"workspace/{ctx.op}/pass_a_results.json vs verification.json."
    )
    events.emit(
        workspace,
        "orchestrator.fsm_loop_guard_o5_mismatch",
        lane=ctx.lane,
        data={
            "worker_count": count,
            "worker_cap": cap,
            "claimed": o5.claimed,
            "measured": o5.measured,
        },
    )
    return HandlerResult.ret(2)


def _clear_harness_build_artifacts(workspace: Path) -> list[str]:
    """Remove harness-owned build/evaluation artifacts before an O5 rollback
    to ``await_worker`` (2026-08-21, graybox respawn fix).

    The O5 controlled build compiles the candidate into kernel/build/ and the
    npubench evaluation stages a built copy under .npubench_exec/ (and a
    candidate stage under .npubench_candidate/).  Those trees contain .o/.so
    binaries that the graybox construction scan classifies as assembled-answer
    artifacts, so a worker respawn with them present is rejected before it can
    run ("graybox construction rejected target/answer-bearing curated input").
    The next worker iteration regenerates the candidate from its own authored
    sources; these built outputs are harness-owned, not worker state, so
    removing them is the same clean-slate contract as cold-start.
    npubench_evidence/ (the durable reports the next iteration's brief
    references, including preflight_target_receipt.json) is preserved here and
    by the candidate-repair reset in
    orchestrator_coldstart._prepare_npubench_candidate_repair.
    """
    removed: list[str] = []
    for rel in ("kernel/build", ".npubench_exec", ".npubench_candidate"):
        p = workspace / rel
        try:
            if p.is_symlink() or p.is_file():
                p.unlink()
                removed.append(rel)
            elif p.is_dir():
                shutil.rmtree(p)
                removed.append(rel)
        except OSError as exc:
            log.warning(f"O5 rollback: failed to remove {rel}: {exc}")
    for so in sorted(workspace.glob("*.so")):
        if not (so.is_file() or so.is_symlink()):
            continue
        # 2026-08-25: mirror the cold-start pattern — move to a backup dir
        # (recoverable) instead of unlink (permanent).  The backup root follows
        # the same convention as orchestrator_coldstart (env override, else
        # ~/.opgen_backups/<workspace>) and is deliberately OUTSIDE the
        # worker-visible workspace: an in-workspace copy would be a restore
        # vector and would trip the graybox construction scan on respawn.
        backup_root_env = os.environ.get(
            "NPUBENCH_REPAIR_BACKUP_ROOT"
        ) or os.environ.get("COLD_START_BACKUP_ROOT")
        backup_root = (
            Path(backup_root_env) / workspace.name
            if backup_root_env
            else Path.home() / ".opgen_backups" / workspace.name
        )
        backup_dir = backup_root / f"o5-rollback-{int(time.time())}"
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(so), str(backup_dir / so.name))
            removed.append(so.name)
        except OSError as exc:
            log.warning(f"O5 rollback: failed to back up {so.name}: {exc}")
    if removed:
        log.info(f"O5 rollback: cleared harness build artifacts: {', '.join(removed)}")
    return removed


def _rollback_o5_mismatch(workspace: Path, o5) -> HandlerResult:
    """Record the existing mismatch rollback to ``await_worker``."""
    _clear_harness_build_artifacts(workspace)
    rollback_state = "await_worker"
    log.info(f"O5 MISMATCH rollback target: {rollback_state}")
    state_executor.record_transition(
        workspace,
        state_executor.TransitionDecision(
            next_state=rollback_state,
            matched_transition_index=-1,
            rationale=(
                f"P0kk O5 MISMATCH: {len(o5.mismatches)} count discrepancies — "
                f"rollback to {rollback_state} to re-iterate emission"
            ),
            from_state="finalize",
            handoff="",
        ),
    )
    finalize_pipeline.record_rollback(
        workspace,
        rollback_state=rollback_state,
        reason=f"P0kk O5 MISMATCH: {o5.summary}",
        gate="phase_o5_mismatch",
    )
    return HandlerResult.cont()


_NEAR_MISS_BLOCKED_FINGERPRINT_CLASSES = frozenset({"bimodal", "reference-unstable"})


_PRECISION_REPORT_REL = Path("npubench_evidence") / "precision_report.json"


def _repeat_fingerprint_classes(workspace: Path) -> dict[int, str]:
    """Per-case repeat-fingerprint classes from the precision report.

    Returns {} when the report or the per-case field is absent (legacy
    reports) or unreadable — callers treat {} as "no fingerprint evidence",
    never as "all admissible" or "all blocked".
    """
    try:
        report = json.loads((workspace / _PRECISION_REPORT_REL).read_text())
    except Exception:
        return {}
    if not isinstance(report, dict):
        return {}
    cases = report.get("cases")
    if not isinstance(cases, list):
        return {}
    classes: dict[int, str] = {}
    for position, case in enumerate(cases):
        if not isinstance(case, dict):
            continue
        fingerprint = case.get("repeat_fingerprint")
        if not isinstance(fingerprint, dict):
            continue
        klass = fingerprint.get("class")
        if not isinstance(klass, str) or not klass:
            continue
        idx = case.get("case_idx", case.get("index", position))
        try:
            classes[int(idx)] = klass
        except (TypeError, ValueError):
            continue
    return classes


def _near_miss_inadmissible_cases(workspace: Path) -> dict[int, str]:
    """Cases that must not be accepted via near-miss (bimodal/ref-unstable)."""
    return {
        idx: klass
        for idx, klass in _repeat_fingerprint_classes(workspace).items()
        if klass in _NEAR_MISS_BLOCKED_FINGERPRINT_CLASSES
    }


def near_miss_case_admitted(workspace: Path, case_idx: int) -> bool:
    """Fingerprint admission predicate for the near-miss acceptance rule.

    False only when fingerprint evidence positively marks the case bimodal or
    reference-unstable; a missing fingerprint field (legacy report) preserves
    the pre-existing behavior (True).
    """
    klass = _repeat_fingerprint_classes(workspace).get(case_idx)
    return klass not in _NEAR_MISS_BLOCKED_FINGERPRINT_CLASSES


def _handle_o5_mismatch(
    ctx: OrchestratorContext,
    snap,
    o5,
) -> HandlerResult:
    """Emit an O5 mismatch and either halt at cap or roll back the worker."""
    log.info(phase_o5.format_block_message(ctx.op, o5))
    # Near-miss fingerprint admission (P0-3 / DSH §4.c): cases classified
    # bimodal or reference-unstable by the evaluation repeat fingerprint are
    # recorded in the durable event trail so a later near-miss acceptance
    # decision (user adjudication at await_user_decision) cannot treat them as
    # admissible.  Missing fingerprint field (legacy report) → empty, behavior
    # unchanged.
    inadmissible = _near_miss_inadmissible_cases(ctx.workspace)
    if inadmissible:
        log.warning(
            "repeat_fingerprint near-miss admission gate: cases %s are "
            "bimodal/reference-unstable — NOT admissible for near-miss "
            "acceptance regardless of MERE margin",
            inadmissible,
        )
    events.emit(
        ctx.workspace,
        "orchestrator.phase_o5_block",
        lane=ctx.lane,
        data={
            "verdict": o5.verdict,
            "claimed": o5.claimed,
            "measured": o5.measured,
            "mismatches": o5.mismatches,
            "near_miss_inadmissible_cases": {
                str(k): v for k, v in inadmissible.items()
            },
        },
    )
    cap_result = _mismatch_at_worker_cap(ctx, snap, o5)
    if cap_result is not None:
        return cap_result
    return _rollback_o5_mismatch(ctx.workspace, o5)


def _record_o5_provisional(ctx: OrchestratorContext, o5) -> None:
    """Persist the dirty-harness O5 finding without rolling back."""
    log.warning(f"O5 post-verify: {o5.summary}")
    events.emit(
        ctx.workspace,
        "orchestrator.phase_o5_provisional",
        lane=ctx.lane,
        data={
            "verdict": o5.verdict,
            "harness_git_state": o5.harness_git_state,
            "harness_dirty": o5.harness_dirty,
            "claimed": o5.claimed,
            "measured": o5.measured,
        },
    )
    phase_o5.record_harness_state(ctx.workspace, o5)


_HOST_TRANSIENT_RECLASSIFY_PREFIX = "host-transient copy fault in measured precision: "


def _mismatch_is_device_error(o5) -> bool:
    """Whether a MISMATCH carries a device-error signature (5070xx / aivec).

    Checked BEFORE the host-transient copy markers: an async device fault
    surfaces at the next host copy op, so the same reason text carries both
    the copy marker and the device error code — the device code wins.
    """
    measured = getattr(o5, "measured", None)
    if not isinstance(measured, dict):
        return False
    precision = measured.get("precision")
    if not isinstance(precision, dict):
        return False
    reason = str(precision.get("reason") or "")
    if _DEVICE_ERROR_CODE_RE.search(reason):
        return True
    return any(marker in reason for marker in _DEVICE_ERROR_MARKERS)


def _retry_device_error_mismatch(ctx: OrchestratorContext, o5, runner):
    """Re-run a device-class MISMATCH through the infra retry loop, backoff 0."""
    log.warning(
        "O5 MISMATCH is device-class (5070xx/aivec signature in measured "
        "precision); re-attempting in place with NO backoff (device errors do "
        "not self-heal): %s",
        o5.summary[:160],
    )
    reclassified = phase_o5.O5Report(
        verdict="RUNNER_FAILED",
        summary=_DEVICE_RECLASSIFY_PREFIX + o5.summary,
        truth_source=getattr(o5, "truth_source", "npubench"),
        rollback_kind="infra",
    )
    return _retry_infra_o5_verification(ctx, reclassified, runner, backoff_seconds=0)


def _retry_host_transient_mismatch(ctx: OrchestratorContext, o5, runner):
    """Re-run a host-transient MISMATCH through the infra retry loop."""
    # The measured precision failed in the host H2D copy path, not in the
    # candidate.  Roll the transient failure into the infra retry loop
    # (with backoff) instead of routing a host fault to await_worker.
    log.warning(
        "O5 MISMATCH is host-transient (copy fault in measured precision); "
        "re-attempting in place as infra: %s",
        o5.summary[:160],
    )
    reclassified = phase_o5.O5Report(
        verdict="RUNNER_FAILED",
        summary=_HOST_TRANSIENT_RECLASSIFY_PREFIX + o5.summary,
        truth_source=getattr(o5, "truth_source", "npubench"),
        rollback_kind="infra",
    )
    return _retry_infra_o5_verification(ctx, reclassified, runner)


_DEVICE_ERROR_CODE_RE = re.compile(r"\b5070\d{2}\b")


_DEVICE_ERROR_MARKERS = ("aivec error", "device error type")


_DEVICE_RECLASSIFY_PREFIX = "device-class copy fault in measured precision: "


def _resolve_o5_report(ctx: OrchestratorContext, runner):
    """Run O5 and settle every infra-retryable verdict before dispatch."""
    first_o5 = _run_o5_verification(ctx, runner)
    # A controlled NPUBench build has already classified a pre-build candidate
    # rejection in its authenticated receipt.  Dispatch it before the generic
    # infra retry loop: this is a worker-owned defect, not a flaky evaluator
    # transport, and retrying can erase the only repairable observation.
    if (
        first_o5.verdict == "RUNNER_FAILED"
        and _is_direct_npubench_candidate_failure(ctx.workspace)
        and _is_repairable_npubench_candidate_failure(first_o5)
    ):
        o5 = first_o5
    else:
        o5 = _retry_infra_o5_verification(ctx, first_o5, runner)
    if o5.verdict == "MISMATCH" and _mismatch_is_device_error(o5):
        # Device-class errors are split OUT of the host-transient
        # classification (P0-1): zero backoff, and the same-signature parking
        # counter (threshold 2, enforced in _o5_post_verify) routes a repeat
        # to await_user_decision with device probe/reset/lane advice.
        o5 = _retry_device_error_mismatch(ctx, o5, runner)
    elif o5.verdict == "MISMATCH" and _mismatch_is_host_transient(o5):
        count = _bump_host_copy_fault_escalation(ctx.workspace, o5)
        if count > _host_copy_fault_max_transient():
            # Same candidate binding keeps tripping the copy-fault marker: a
            # genuinely transient host window does not reproduce
            # byte-identically — this is a candidate device-kernel fault
            # surfaced asynchronously at a copy op.  Dispatch the MISMATCH to
            # the worker with the deterministic-fault note instead of another
            # infra retry round.
            o5 = _mark_host_copy_fault_deterministic(ctx, o5, count)
        else:
            o5 = _retry_host_transient_mismatch(ctx, o5, runner)
    return o5


def _dispatch_o5_runner_failed(
    ctx: OrchestratorContext,
    snap,
    o5,
    truth_source=None,
) -> HandlerResult:
    """Route a settled RUNNER_FAILED verdict to its owning repair path.

    Multirank workspaces adopt fsm_finalize_coverage's infra-vs-algorithm
    split: an infra failure that survived the bounded in-place retry is an
    EXTERNAL resource problem (lane auto-allocation / probe / ssh) the worker
    cannot fix — it pauses at await_user_decision instead of spawning a
    worker with nothing to do. Non-multirank modes keep the taxonomy routing
    below (worker-owned repair re-entry); adopting the split there would
    change non-multirank behavior, which this wiring deliberately does not.
    """
    if truth_source == "multirank":
        return getattr(fsm_finalize_coverage, "_handle_o5_runner_failed")(ctx, snap, o5)
    # Provider-owned taxonomy has precedence over operator-facing text.
    # A candidate contract diagnostic may mention capability or toolchain
    # words; that must still re-enter the worker repair path.
    if _is_direct_npubench_candidate_failure(
        ctx.workspace
    ) and _is_repairable_npubench_candidate_failure(o5):
        log.warning(
            "O5 rejected the NPUBench candidate before build; "
            "persisting await_worker repair re-entry: %s",
            o5.summary[:500],
        )
        return _handle_npubench_candidate_failure(ctx, snap, o5)
    if "A5_SOC_UNSUPPORTED_FOR_VALIDATION" in o5.summary:
        log.error("O5 stopped: %s", o5.summary)
        events.emit(
            ctx.workspace,
            "orchestrator.phase_o5_target_capability_block",
            lane=ctx.lane,
            data={"summary": o5.summary},
        )
        return HandlerResult.ret(2)
    if _is_direct_npubench_candidate_failure(ctx.workspace):
        if _is_worker_fixable_candidate_rejection(o5):
            log.info(
                "O5 RUNNER_FAILED is a candidate-authoring rejection "
                "(independence gate — worker can re-author independently); "
                "routing await_worker for a fix round"
            )
            return _handle_o5_runner_failed(ctx, snap, o5)
        return _stop_direct_npubench_candidate_failure(ctx, o5)
    return _handle_o5_runner_failed(ctx, snap, o5)


def _dispatch_o5_non_blocking(
    ctx: OrchestratorContext,
    snap,
    o5,
    truth_source,
) -> Optional[HandlerResult]:
    """Record a non-blocking verdict and refuse anything outside the taxonomy."""
    if o5.verdict == "PROVISIONAL":
        _record_o5_provisional(ctx, o5)
    elif o5.verdict == "VERIFIED":
        # VERIFIED arm delegates to fsm_finalize_coverage (same log +
        # record_harness_state as before, plus the multirank R2 marker stamp
        # and the UNVERIFIED-coverage pause) — semantics preserved for
        # non-multirank (an empty unverified set proceeds exactly as before).
        _r = fsm_finalize_coverage.handle_o5_verified(ctx, ctx.lane, o5, truth_source)
        if _r is not None:
            return _r
    elif o5.verdict != "SKIPPED":
        failed = phase_o5.O5Report(
            verdict="RUNNER_FAILED",
            summary=f"unknown O5 verdict {o5.verdict!r}; refusing finalize",
            truth_source=getattr(o5, "truth_source", "unresolved"),
        )
        return _dispatch_o5_runner_failed(ctx, snap, failed, truth_source)
    return None


def _o5_post_verify(ctx: OrchestratorContext, snap) -> Optional[HandlerResult]:
    """Run O5 and dispatch its result without allowing unknown verdicts through."""
    _ts = phase_o5.expected_truth_source(ctx.workspace)
    # R2 durable VERIFIED marker (multirank): a current marker short-circuits
    # the re-measure — o5 is then the synthesized report and no runner is built.
    o5 = _skip_remeasure_if_marked(ctx, _ts)
    runner = (
        None
        if o5 is not None
        else _o5_runner_for_workspace(
            ctx.workspace, extra_lanes=ctx.extra_lanes, truth_source=_ts
        )
    )
    # P0-2 (PR875 equiv review): never evaluate a candidate caught mid
    # repair-reset (2026-08-27 FAS 14:52 empty-window race — the repair reset
    # had just moved model_new_ascendc.py out when the evaluation started,
    # producing a bogus infra ERROR round).
    guard_result = _await_o5_candidate_stable(ctx, snap)
    if guard_result is not None:
        return guard_result
    if o5 is None:
        o5 = _resolve_o5_report(ctx, runner)
    # P0-1 (DSH ruling §4.b): per-op PERSISTENT same-signature failure parking.
    # engine/infra/device classes accumulate in a workspace dotfile (survives
    # exit 77 / resume / cold-start); consecutive identical signatures past the
    # class threshold route to await_user_decision instead of another retry.
    park_result = _same_signature_park_route(ctx, o5)
    if park_result is not None:
        return park_result
    if o5.verdict == "MISMATCH":
        return _handle_o5_mismatch(ctx, snap, o5)
    if o5.verdict == "RUNNER_FAILED":
        return _dispatch_o5_runner_failed(ctx, snap, o5, _ts)
    return _dispatch_o5_non_blocking(ctx, snap, o5, _ts)


_O5_CANDIDATE_GUARD_MAX_RETRIES_ENV = "AOG_O5_CANDIDATE_GUARD_MAX_RETRIES"


_O5_CANDIDATE_GUARD_MAX_RETRIES = 3


_O5_CANDIDATE_GUARD_INTERVAL_ENV = "AOG_O5_CANDIDATE_GUARD_INTERVAL_SEC"


_O5_CANDIDATE_GUARD_INTERVAL_SECONDS = 5


_REPAIR_RESET_WINDOW_SECONDS = 60


_REPAIR_RECORD_FILENAME = ".npubench_candidate_repair.json"


def _o5_candidate_guard_max_retries() -> int:
    raw = os.environ.get(_O5_CANDIDATE_GUARD_MAX_RETRIES_ENV)
    if raw is None:
        return _O5_CANDIDATE_GUARD_MAX_RETRIES
    try:
        return max(int(raw.strip()), 0)
    except ValueError:
        return _O5_CANDIDATE_GUARD_MAX_RETRIES


def _o5_candidate_guard_interval_seconds() -> int:
    raw = os.environ.get(_O5_CANDIDATE_GUARD_INTERVAL_ENV)
    if raw is None:
        return _O5_CANDIDATE_GUARD_INTERVAL_SECONDS
    try:
        return max(int(raw.strip()), 0)
    except ValueError:
        return _O5_CANDIDATE_GUARD_INTERVAL_SECONDS


def _repair_reset_age_seconds(workspace: Path) -> Optional[float]:
    """Age of the last candidate repair-reset archival event, None if none."""
    try:
        record = json.loads((workspace / _REPAIR_RECORD_FILENAME).read_text())
    except Exception:
        return None
    created = record.get("created_at_utc") if isinstance(record, dict) else None
    if not created:
        return None
    try:
        import datetime as _dt

        stamp = _dt.datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=_dt.timezone.utc)
        return _dt.datetime.now(_dt.timezone.utc).timestamp() - stamp.timestamp()
    except (TypeError, ValueError):
        return None


def _candidate_tree_changed(
    entry_ok: bool,
    previous_tree_sha: Optional[str],
    tree_sha: Optional[str],
) -> bool:
    """Return whether two valid guard probes observed different trees."""
    if not entry_ok or not previous_tree_sha or not tree_sha:
        return False
    return tree_sha != previous_tree_sha


def _o5_candidate_stability_probe(workspace: Path, previous_tree_sha: Optional[str]):
    """One guard probe; returns (issues, tree_sha256_or_None).

    "tree sha agrees with the binding" is enforced as SELF-consistency inside
    the guard window: the digest computed here must match the previous probe's.
    Comparing against a HISTORICAL evaluation binding would mis-fire on every
    legitimately re-authored candidate, so no historical binding is consulted.
    """
    issues: list[str] = []
    age = _repair_reset_age_seconds(workspace)
    repair_recent = age is not None and age < _REPAIR_RESET_WINDOW_SECONDS
    if repair_recent:
        issues.append(
            f"candidate repair-reset archived {age:.1f}s ago "
            f"(< {_REPAIR_RESET_WINDOW_SECONDS}s window)"
        )
    tree_sha = None
    entry_ok = False
    try:
        from npubench.npubench_core import (
            _candidate_entry,
            _candidate_root,
            _candidate_tree_sha256,
        )

        candidate_root = _candidate_root(workspace)
        _candidate_entry(candidate_root)
        entry_ok = True
        tree_sha = _candidate_tree_sha256(candidate_root)
    except Exception as exc:
        # A missing/unstable entry only concerns the guard while a repair
        # reset is in flight; without one the runner's own candidate-contract
        # path reports the defect (unchanged legacy behavior).
        if repair_recent:
            issues.append(f"candidate entry not a regular file mid repair-reset: {exc}")
    if _candidate_tree_changed(entry_ok, previous_tree_sha, tree_sha):
        issues.append("candidate tree sha256 changed between guard probes")
    return issues, tree_sha


def _candidate_stability_guard_failure(
    ctx: OrchestratorContext,
    snap,
    max_retries: int,
    issues: list[str],
) -> HandlerResult:
    """Create the existing infra result after stability probes are exhausted."""
    log.error(
        "O5 candidate stability guard exhausted (%d attempts): %s — failing loud as infra",
        max_retries + 1,
        "; ".join(issues) or "tree sha never confirmed stable",
    )
    events.emit(
        ctx.workspace,
        "orchestrator.phase_o5_candidate_guard_failed",
        lane=ctx.lane,
        data={"issues": issues, "attempts": max_retries + 1},
    )
    failed = phase_o5.O5Report(
        verdict="RUNNER_FAILED",
        summary=(
            "O5 candidate stability guard: candidate unstable across "
            f"{max_retries + 1} probes ({'; '.join(issues)}) — a repair-reset "
            "race must not be evaluated (2026-08-27 FAS 14:52 empty-window "
            "incident). Re-invoke the orchestrator once the candidate settles."
        ),
        truth_source="npubench",
        rollback_kind="infra",
    )
    return _handle_o5_runner_failed(ctx, snap, failed)


def _await_o5_candidate_stable(
    ctx: OrchestratorContext, snap
) -> Optional[HandlerResult]:
    """Bounded suspend-retry until the candidate is stable for O5 evaluation.

    Stability requires TWO consecutive clean probes with an identical tree
    sha256 (a single probe cannot observe a tree being rewritten between the
    guard and the evaluation).  Returns None when evaluation may proceed
    (including non-npubench routes, where no candidate snapshot race exists);
    on exhausted retries returns the infra RUNNER_FAILED dispatch (fail loud,
    free re-entry, no worker respawn semantics change).
    """
    try:
        if phase_o5.expected_truth_source(ctx.workspace) != "npubench":
            return None
    except Exception as error:
        log.warning(
            "candidate stability guard: truth-source probe failed (%s); skipping", error
        )
        return None
    max_retries = _o5_candidate_guard_max_retries()
    interval = _o5_candidate_guard_interval_seconds()
    previous_tree_sha: Optional[str] = None
    confirmed = False  # one clean probe already seen; the next clean probe confirms
    issues: list[str] = []
    for attempt in range(max_retries + 1):
        issues, tree_sha = _o5_candidate_stability_probe(
            ctx.workspace, previous_tree_sha
        )
        previous_tree_sha = tree_sha
        if not issues and confirmed:
            if attempt > 1:
                log.info(
                    "O5 candidate stability guard: candidate settled after %d wait(s)",
                    attempt,
                )
            return None
        if not issues:
            confirmed = True
        else:
            confirmed = False
            log.warning(
                "O5 candidate stability guard (attempt %d/%d): %s",
                attempt + 1,
                max_retries + 1,
                "; ".join(issues),
            )
        if attempt < max_retries and interval > 0:
            _sleep(interval)
    return _candidate_stability_guard_failure(ctx, snap, max_retries, issues)


def _o5_failure_signature_input(o5) -> Optional[tuple[str, str]]:
    """Classify a settled O5 failure; returns (failure_class, reason) or None.

    failure_class ∈ {engine, infra, device, candidate} per DSH §4.b:
    engine = build/route/contract-schema class (incl. candidate_contract
    repair re-entries and ModuleNotFoundError evaluation rounds); infra =
    host/network/lease transients (incl. host copy faults without a device
    error code); device = 5070xx/aivec device errors (split out of the
    host-transient text class); candidate = genuine precision MISMATCH.
    """
    verdict = getattr(o5, "verdict", None)
    summary = str(getattr(o5, "summary", "") or "")
    if verdict == "MISMATCH":
        measured = getattr(o5, "measured", None)
        reason = ""
        if isinstance(measured, dict) and isinstance(measured.get("precision"), dict):
            reason = str(measured["precision"].get("reason") or "")
        reason = reason or summary
        if _mismatch_is_device_error(o5):
            return "device", reason
        if _mismatch_is_host_transient(o5):
            return "infra", reason
        return "candidate", reason
    if verdict == "RUNNER_FAILED":
        if summary.startswith(_DEVICE_RECLASSIFY_PREFIX):
            return "device", summary
        if summary.startswith(_HOST_TRANSIENT_RECLASSIFY_PREFIX):
            return "infra", summary
        # Candidate-contract re-entries are the engine class per DSH §4.b
        # (build/route/contract-schema — the FAS 27-round ModuleNotFoundError
        # loop was exactly this shape), even when they inherit an infra
        # rollback_kind from the runner transport.
        if getattr(o5, "failure_kind", None) == "candidate_contract":
            return "engine", summary
        if getattr(o5, "rollback_kind", None) == "infra":
            return "infra", summary
        return "engine", summary
    return None


def _candidate_precision_cases(o5) -> list[dict]:
    """Return dictionary-shaped precision cases from one O5 report."""
    measured = getattr(o5, "measured", None)
    if not isinstance(measured, dict):
        return []
    precision = measured.get("precision")
    if not isinstance(precision, dict):
        return []
    cases = precision.get("cases")
    if not isinstance(cases, list):
        return []
    return [case for case in cases if isinstance(case, dict)]


def _candidate_case_failure_signature(case: dict) -> Optional[str]:
    """Render one non-passing precision case for the parking signature."""
    status = str(case.get("status") or case.get("verdict") or "")
    if status.upper() in ("PASS", "SKIPPED"):
        return None
    # npubench precision_report cases key the index as "case"; the two-tier
    # evaluators use "case_idx"/"index".
    idx = case.get("case", case.get("case_idx", case.get("index", "?")))
    reason = state_executor.normalize_failure_reason(
        case.get("reason") or case.get("MERE") or ""
    )
    return f"{idx}:{status}:{reason}"


def _candidate_case_signature(o5) -> str:
    """Stable per-case failure signature for the candidate-class escalation."""
    parts: list[str] = []
    for case in _candidate_precision_cases(o5):
        signature = _candidate_case_failure_signature(case)
        if signature is not None:
            parts.append(signature)
    if parts:
        return "|".join(parts)
    return str(getattr(o5, "summary", "") or "")


def _candidate_failing_case_indices(o5) -> list[str]:
    """Identity of the failing precision-case set — tree-agnostic by design.

    Shares the status filter and the index key chain ("case" first, npubench
    precision_report shape) with `_candidate_case_failure_signature`, so the
    zero-progress fingerprint and the per-tree signature see the same set.
    """
    indices: list[str] = []
    for case in _candidate_precision_cases(o5):
        status = str(case.get("status") or case.get("verdict") or "")
        if status.upper() in ("PASS", "SKIPPED"):
            continue
        indices.append(
            str(case.get("case", case.get("case_idx", case.get("index", "?"))))
        )
    return indices


def _candidate_tier1_pass_count(o5) -> Optional[int]:
    """Net-progress probe: tier1 pass count from one O5 report, None if unknown."""
    measured = getattr(o5, "measured", None)
    if not isinstance(measured, dict):
        return None
    precision = measured.get("precision")
    if not isinstance(precision, dict):
        return None
    pass_a = precision.get("pass_a")
    candidates = [
        precision.get("passed_case_count"),
        pass_a.get("tier1_pass") if isinstance(pass_a, dict) else None,
        precision.get("tier1_pass"),
    ]
    for raw in candidates:
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    cases = _candidate_precision_cases(o5)
    if cases:
        passed = 0
        for case in cases:
            if (
                str(case.get("status") or "").upper() == "PASS"
                or case.get("tier1_pass") is True
            ):
                passed += 1
        return passed
    return None


def _route_await_user_decision_park(
    ctx: OrchestratorContext,
    o5,
    *,
    failure_class: str,
    count: int,
    detail: str,
    guard: str = "P0-1 same-signature",
    event: str = "orchestrator.same_signature_park",
) -> HandlerResult:
    """Park at await_user_decision (never hard-stop) with the class advisory."""
    advisory = ""
    if failure_class == "device":
        advisory = (
            " Device-class errors do not self-heal — DO NOT just resume into "
            "the same lane. Suggested diagnostics (engine performs no reset "
            "itself): 1) npu-smi info — check the leased device's Health/Util; "
            "2) re-run the eval child with ASCEND_LAUNCH_BLOCKING=1 for true "
            "fault attribution (an async 507035/507015 at an H2D copy can be "
            "an EARLIER candidate launch wedging the device — 2026-08-27 "
            "42_CoTAttention precedent), then bisect per-launch with "
            "aclrtSynchronizeStream; 3) ask the host admin for "
            "npu-smi/aclrtResetDevice on the wedged device; 4) re-lease on a "
            "different lane."
        )
    rationale = (
        f"{guard} parking: {count} consecutive identical "
        f"{failure_class}-class O5 failures (persistent counter, survives "
        f"exit 77/restart). {detail[:600]}{advisory} Halting at "
        "await_user_decision — write user_decision.md to cap-bump, switch "
        "lane, or repair the engine; the orchestrator does not hard-stop."
    )
    log.error(rationale)
    state_executor.record_transition(
        ctx.workspace,
        state_executor.TransitionDecision(
            next_state="await_user_decision",
            matched_transition_index=-1,
            rationale=rationale,
            from_state="finalize",
            handoff="",
        ),
    )
    events.emit(
        ctx.workspace,
        event,
        lane=ctx.lane,
        data={
            "failure_class": failure_class,
            "count": count,
            "summary": str(getattr(o5, "summary", "") or "")[:300],
        },
    )
    return HandlerResult.cont()


def _candidate_precision_signal_observable(o5) -> bool:
    """Does this O5 report carry the per-case precision block the guard reads?

    Only the npubench route writes `measured["precision"]`
    (`phase_o5._npubench_o5_report`). a3_live and backward go through
    `phase_o5._record_measured_passes`, which keys `measured` by PASS name
    (`pass_a` / `pass_b`) and never produces a `precision` key.

    Both of the guard's reset conditions read that block, so without it the guard
    has no signal at all and degrades into a plain round counter. A guard whose
    inputs are unobservable must abstain rather than fail closed; the per-tree
    counter still covers these routes.
    """
    measured = getattr(o5, "measured", None)
    return isinstance(measured, dict) and isinstance(measured.get("precision"), dict)


def _maybe_zero_progress_park(
    ctx: OrchestratorContext, o5, workspace
) -> Optional[HandlerResult]:
    """Park when the failing-case set is unchanged with no tier1 net growth.

    Tree-agnostic churn guard (2026-09-01, A3→A5 remeasure review): the
    per-tree counter resets whenever the worker re-authors, so a churn loop
    (small edits every round, metrics never move) escapes it.  This counter
    keys on the failing-case SET only and parks when the set is unchanged for
    N rounds with no tier1_pass net growth.

    Abstains entirely when the precision block it reads is absent — see
    `_candidate_precision_signal_observable`.
    """
    if not _candidate_precision_signal_observable(o5):
        return None
    zero = state_executor.record_zero_progress_round(
        workspace,
        _candidate_failing_case_indices(o5),
        _candidate_tier1_pass_count(o5),
    )
    if zero["count"] < state_executor.ZERO_PROGRESS_PARK_THRESHOLD:
        return None
    return _route_await_user_decision_park(
        ctx,
        o5,
        failure_class="candidate",
        count=zero["count"],
        detail=(
            "Same failing case set "
            f"{zero['failing_cases']} for {zero['count']} consecutive "
            "O5 candidate rounds with no tier1_pass net growth — the "
            "worker re-authors every round but the metrics never move "
            "(churn non-convergence; the per-tree case counter resets "
            "on every re-author and cannot see this). Mismatch: "
            + str(getattr(o5, "summary", "") or "")[:200]
        ),
        guard="zero-progress",
        event="orchestrator.zero_progress_park",
    )


def _same_signature_park_route(ctx: OrchestratorContext, o5) -> Optional[HandlerResult]:
    """Update the persistent same-signature counters and park when stuck.

    Returns a HandlerResult routing to await_user_decision, or None to let the
    normal verdict dispatch proceed.  Success verdicts (VERIFIED/PROVISIONAL)
    break the consecutive chain; SKIPPED is not a measurement and leaves it.
    """
    workspace = ctx.workspace
    verdict = getattr(o5, "verdict", None)
    if verdict in ("VERIFIED", "PROVISIONAL"):
        state_executor.clear_same_signature_state(workspace)
        state_executor.clear_candidate_case_state(workspace)
        state_executor.clear_zero_progress_state(workspace)
        return None
    classified = _o5_failure_signature_input(o5)
    if classified is None:
        return None
    failure_class, reason = classified
    tree_key = _o5_candidate_tree_key(o5)
    if failure_class == "candidate":
        # A candidate MISMATCH is a different-signature insertion for the
        # engine/infra/device chain, and feeds its own escalation counter.
        state_executor.clear_same_signature_state(workspace)
        entry = state_executor.record_candidate_case_failure(
            workspace, tree_key, _candidate_case_signature(o5)
        )
        if entry["count"] >= state_executor.CANDIDATE_CASE_PARK_THRESHOLD:
            return _route_await_user_decision_park(
                ctx,
                o5,
                failure_class="candidate",
                count=entry["count"],
                detail=(
                    "Same candidate tree + same per-case failure signature for "
                    f"{entry['count']} O5 rounds (worker cannot move the "
                    "failure — the '改不动=卡死' shape, FAS kw-17..21 "
                    "precedent). Mismatch: "
                    + str(getattr(o5, "summary", "") or "")[:200]
                ),
            )
        zero_progress_park = _maybe_zero_progress_park(ctx, o5, workspace)
        if zero_progress_park is not None:
            return zero_progress_park
        return None
    entry = state_executor.record_same_signature_failure(
        workspace, failure_class, reason, tree_key
    )
    threshold = state_executor.same_signature_park_threshold(failure_class)
    if entry["count"] >= threshold:
        return _route_await_user_decision_park(
            ctx,
            o5,
            failure_class=failure_class,
            count=entry["count"],
            detail=f"Signature {entry['signature'][:12]}… reason: {entry['reason_norm'][:200]}",
        )
    return None


_HOST_COPY_FAULT_MARKERS = (
    "copy_between_host_and_device",
    "CopyKernelOpApi",
    "copy_with_slice",
)


def _mismatch_is_host_transient(o5) -> bool:
    measured = getattr(o5, "measured", None)
    if not isinstance(measured, dict):
        return False
    precision = measured.get("precision")
    if not isinstance(precision, dict):
        return False
    reason = str(precision.get("reason") or "")
    if not any(marker in reason for marker in _HOST_COPY_FAULT_MARKERS):
        return False
    # P0abb (2026-08-25): a candidate kernel that wedges the device surfaces as
    # a copy fault on a LATER case's H2D move (45_CrossformerAttention: case-0
    # launch 507035 → case-1 input copy fault, pass_a=None).  If a completed
    # case already failed with a device error inside candidate execution, the
    # copy fault is a symptom, not the cause — classify as candidate MISMATCH
    # (worker-fixable) instead of host-transient infra so the worker sees the
    # kernel-wedge signature instead of a phantom H2D fault.
    for case in precision.get("cases") or []:
        case_reason = str(case.get("reason") or "")
        if "case execution failed" in case_reason and any(
            code in case_reason for code in ("507035", "507014", "507033", "507034")
        ):
            return False
    return True


_WORKER_FIXABLE_CANDIDATE_REJECTION_MARKERS = (
    # The candidate independence gate rejects the WORKER's authored candidate
    # (byte-copy / comments-only edit of the staged kernel / forbidden ACLNN
    # text / source-stage references).  These are authoring failures the
    # source-only worker CAN repair by re-authoring independently — unlike
    # target-side build/toolchain failures, which it cannot.
    "TileLang2AscendC candidate",
    "ACLNN candidate",
)


def _is_worker_fixable_candidate_rejection(o5) -> bool:
    """Return whether a direct-npubench O5 failure is worker-fixable.

    The terminal direct-npubench stop was designed for TARGET-side failures
    (build toolchain/device errors) that the isolated source-only worker
    cannot repair.  The candidate independence gate rejects the worker's own
    authored candidate, and compile errors in the worker's own kernel sources
    are equally authoring failures — the worker can fix them (re-author
    independently / correct the code using the durable build receipt's
    diagnostics), so route back to ``await_worker`` like any other authoring
    failure instead of stopping with "manual target diagnostics".
    """
    if getattr(o5, "rollback_kind", None) == "candidate":
        return True
    summary = getattr(o5, "summary", "") or ""
    return any(
        marker in summary for marker in _WORKER_FIXABLE_CANDIDATE_REJECTION_MARKERS
    )


def _is_direct_npubench_candidate_failure(workspace: Path) -> bool:
    """Return whether an O5 failure belongs to a direct NPUBench candidate route.

    TileLang2AscendC workers are intentionally isolated from their generated
    candidate and target toolchain.  Target-side build or evaluation failures
    must not be sent back to the source-only worker: routing them to
    ``await_worker`` cannot fix the target-side problem and risks making the
    candidate visible as source in the next graybox — the durable build
    receipt is the repair/resume handoff.  A pre-build candidate-contract
    rejection is different: the worker owns that artifact and needs a durable
    repair re-entry.

    The same taxonomy applies to the generic authored-kernel route
    (``opgen_mode=port_a3_to_a5``): there is no ``port_source`` binding, but
    the worker owns the same ``kernel/`` + ``model_new_ascendc.py`` project
    under the same graybox isolation, so an authenticated
    ``candidate_contract`` build failure must reach the repair worker instead
    of burning infra retries (2026-08-27 flash_attention_score: a genuine
    candidate compile error was retried twice with 600s backoffs as "infra").
    """
    try:
        from reference_source import load_durable_state

        state = load_durable_state(workspace)
    except Exception:
        return False
    source = state.get("port_source")
    reference = state.get("reference")
    source_kind = source.get("kind") if isinstance(source, dict) else None
    if not (isinstance(reference, dict) and reference.get("source") == "npubench"):
        return False
    # Do not require the candidate entry here.  A missing entry is itself a
    # worker-owned candidate-contract defect; the structured O5 failure kind
    # below must still be able to route it to the repair worker.  Target-side
    # failures remain terminal because they carry a different failure_kind.
    if source_kind == "port-aclnn-tilelang2ascendc":
        return True
    if source_kind is None:
        try:
            from npubench.npubench_o5_runner import _generic_kernel_project_present

            return _generic_kernel_project_present(workspace)
        except Exception:
            return False
    return False


def _is_repairable_npubench_candidate_failure(o5) -> bool:
    """Use the provider receipt's taxonomy to identify a repairable defect.

    This intentionally does not inspect ``summary``.  The summary is an
    operator-facing diagnostic and must never decide whether a target-side
    failure is sent back to the source worker.
    """
    return getattr(o5, "failure_kind", None) == "candidate_contract"


def _stop_direct_npubench_candidate_failure(
    ctx: OrchestratorContext,
    o5,
) -> HandlerResult:
    """Stop after a target failure without respawning the source-only worker."""
    summary = o5.summary[:500]
    log.error(
        "direct NPUKernelBench candidate requires manual target diagnostics; "
        "not routing to await_worker: %s",
        summary,
    )
    events.emit(
        ctx.workspace,
        "orchestrator.phase_o5_direct_candidate_block",
        lane=ctx.lane,
        data={
            "summary": summary,
            "rollback_kind": getattr(o5, "rollback_kind", None),
            "next_action": (
                "inspect the route-specific build receipt under "
                "npubench_evidence/ and repair the candidate or target "
                "environment before an explicit resume"
            ),
        },
    )
    return HandlerResult.ret(2)


def _worker_cap_stats(ctx: OrchestratorContext, snap):
    """(workspace, worker_count, worker_cap) when await_worker is at its iter
    cap, else None — the shared loop-guard gate for the capped-stop handlers."""
    workspace = ctx.workspace
    if not state_executor.at_iter_cap(workspace, "await_worker"):
        return None
    return (
        workspace,
        snap.iter_counts.get("worker", 0),
        state_executor.iter_cap("await_worker", workspace=workspace),
    )


def _runner_failure_at_worker_cap(
    ctx: OrchestratorContext,
    snap,
    o5,
) -> Optional[HandlerResult]:
    """Return the terminal loop-guard result for a capped O5 runner failure."""
    capped = _worker_cap_stats(ctx, snap)
    if capped is None:
        return None
    workspace, count, cap = capped
    log.critical(
        f"O5 RUNNER_FAILED while await_worker already at iter_cap ({count}/{cap}). "
        "Cannot progress — routing back would infinite-loop. Fix the runner "
        "discoverability (run_pass_b.py / pass_a_runner.py name) manually OR "
        "mark precision.pass_b N/A explicitly, then resume."
    )
    events.emit(
        workspace,
        "orchestrator.fsm_loop_guard_o5_runner_failed",
        lane=ctx.lane,
        data={"worker_count": count, "worker_cap": cap, "summary": o5.summary[:200]},
    )
    return HandlerResult.ret(2)


def _npubench_candidate_failure_at_worker_cap(
    ctx: OrchestratorContext,
    snap,
    o5,
) -> Optional[HandlerResult]:
    """Stop a repeated candidate-contract defect with NPUBench-owned wording."""
    capped = _worker_cap_stats(ctx, snap)
    if capped is None:
        return None
    workspace, count, cap = capped
    log.critical(
        "NPUKernelBench candidate contract still rejected while await_worker "
        "is at iter_cap (%s/%s). Cannot progress — repair the candidate "
        "source/build contract before explicitly resuming.",
        count,
        cap,
    )
    events.emit(
        workspace,
        "orchestrator.fsm_loop_guard_o5_candidate_contract",
        lane=ctx.lane,
        data={
            "worker_count": count,
            "worker_cap": cap,
            "failure_kind": getattr(o5, "failure_kind", None),
            "summary": o5.summary[:200],
        },
    )
    return HandlerResult.ret(2)


def _rollback_npubench_candidate_failure(workspace: Path, o5) -> HandlerResult:
    """Persist an NPUBench candidate repair handoff without legacy contracts."""
    rollback_state = "await_worker"
    reason = (
        "P0aba.O5 NPUKernelBench candidate contract rejected before build: "
        f"{o5.summary}"
    )
    receipt = workspace / "npubench_evidence" / "tilelang2ascendc_build_receipt.json"
    try:
        payload = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
        payload = None
    if isinstance(payload, dict):
        stderr_tail = payload.get("stderr_tail")
        if isinstance(stderr_tail, str) and stderr_tail.strip():
            reason += (
                "\nAuthenticated target-build stderr tail:\n" + stderr_tail[-4096:]
            )
    # The retry is an authoring attempt.  Remove stale answer-bearing output
    # before agent_dispatch constructs the next graybox, while preserving the
    # source stage/task/state and keeping a recoverable archive outside the
    # worker-visible workspace.
    _prepare_npubench_candidate_repair(
        workspace,
        failure_reason=reason,
        failure_kind=getattr(o5, "failure_kind", None),
    )
    state_executor.record_transition(
        workspace,
        state_executor.TransitionDecision(
            next_state=rollback_state,
            matched_transition_index=-1,
            rationale=(
                "P0aba.O5 NPUKernelBench candidate contract rejected before "
                f"build: {o5.summary}. Rollback to {rollback_state}. "
                "Worker must repair only the candidate source/build contract; "
                "the orchestrator owns controlled build, precision, and "
                "performance evidence. Do not create a legacy pass_b verifier "
                "or worker-owned NPUBench evidence."
            ),
            from_state="finalize",
            handoff="",
            # A candidate defect requires authoring work and consumes the
            # algorithm iteration budget. It is not an infra-free retry.
            rollback_kind="algorithm",
        ),
    )
    finalize_pipeline.record_rollback(
        workspace,
        rollback_state=rollback_state,
        reason=reason,
        gate="phase_o5_npubench_candidate_contract",
        reason_limit=None,
    )
    return HandlerResult.cont()


def _handle_npubench_candidate_failure(
    ctx: OrchestratorContext,
    snap,
    o5,
) -> HandlerResult:
    """Route a repairable NPUBench candidate defect to the next worker."""
    log.info(
        "O5 post-verify: NPUBench candidate contract failure — "
        "routing await_worker for candidate repair"
    )
    events.emit(
        ctx.workspace,
        "orchestrator.phase_o5_npubench_candidate_contract",
        lane=ctx.lane,
        data={
            "summary": o5.summary,
            "failure_kind": getattr(o5, "failure_kind", None),
            "next_state": "await_worker",
        },
    )
    cap_result = _npubench_candidate_failure_at_worker_cap(ctx, snap, o5)
    if cap_result is not None:
        return cap_result
    return _rollback_npubench_candidate_failure(ctx.workspace, o5)


def _rollback_o5_runner_failure(workspace: Path, o5) -> HandlerResult:
    """Record the existing runner-failure rollback and retry accounting."""
    _clear_harness_build_artifacts(workspace)
    rollback_state = "await_worker"
    rollback_kind = o5.rollback_kind
    retry_label = (
        "infra re-entry FREE (does not consume iter)"
        if rollback_kind == "infra"
        else "algorithm re-entry counts"
    )
    log.info(f"O5 RUNNER_FAILED rollback target: {rollback_state}")
    state_executor.record_transition(
        workspace,
        state_executor.TransitionDecision(
            next_state=rollback_state,
            matched_transition_index=-1,
            rationale=(
                f"P0aba.O5 RUNNER_FAILED: {o5.summary[:200]}. "
                f"Rollback to {rollback_state}. Worker must produce a canonical "
                "pass_b verifier filename at workspace root, OR set "
                "verification.json precision.pass_b to {status: 'N/A', reason: "
                "'<...>'} explicitly."
                + (
                    f" [NODE-5: rollback_kind={rollback_kind!r} — {retry_label}]"
                    if rollback_kind
                    else ""
                )
            ),
            from_state="finalize",
            handoff="",
            rollback_kind=rollback_kind,
        ),
    )
    finalize_pipeline.record_rollback(
        workspace,
        rollback_state=rollback_state,
        reason=f"P0aba.O5 RUNNER_FAILED: {o5.summary[:200]}",
        gate="phase_o5_runner_failed",
    )
    return HandlerResult.cont()


def _handle_o5_runner_failed(ctx: OrchestratorContext, snap, o5) -> HandlerResult:
    """Fail closed after O5 runner failure, bounded retries already exhausted."""
    log.info(f"O5 post-verify: RUNNER_FAILED — {o5.summary}")
    log.info("P0aba.O5 gate: routing await_worker for runner reconciliation")
    events.emit(
        ctx.workspace,
        "orchestrator.phase_o5_runner_failed",
        lane=ctx.lane,
        data={"summary": o5.summary},
    )
    cap_result = _runner_failure_at_worker_cap(ctx, snap, o5)
    if cap_result is not None:
        return cap_result
    return _rollback_o5_runner_failure(ctx.workspace, o5)


def _prepare_finalize_audit(ctx: OrchestratorContext) -> None:
    """Best-effort creation of audit artifacts needed by the final gate."""
    try:
        ctx.ensure_audit_artifacts(ctx.workspace, lane=ctx.lane)
    except Exception as error:
        log.warning(
            f"audit artifact production failed ({error}); continuing — "
            "finalize gate will block if artifacts missing"
        )


def _assemble_finalize_ge_ophost(workspace: Path) -> None:
    """Best-effort deterministic GE host assembly before eligibility."""
    try:
        ge_report = finalize_pipeline.assemble_ge_ophost(workspace)
        if ge_report.get("ran"):
            log.info(
                "assemble_ge_ophost: assembled=%s preserved=%s errors=%s",
                ge_report.get("assembled"),
                ge_report.get("preserved"),
                ge_report.get("errors"),
            )
        else:
            log.info(
                "assemble_ge_ophost: skipped (%s)", ge_report.get("skipped_reason")
            )
    except Exception as error:
        log.warning(
            f"GE op_host assembler failed ({error}); continuing — GE_OPHOST "
            "gate will block if GE host missing"
        )


def _normalize_finalize_workspace(workspace: Path) -> None:
    """Best-effort schema normalization for resumed or legacy workspaces."""
    try:
        norm_report = schema_norm.normalize_workspace(workspace, fail_strict=False)
        if norm_report.events:
            log.info(
                "finalize-branch schema_norm: %s normalizations",
                len(norm_report.events),
            )
    except Exception as error:
        log.warning(
            f"finalize-branch schema_norm failed ({error}); continuing — "
            "eligibility gate will catch any resulting issue"
        )


def _format_batch_precheck_failures(failures: list[dict]) -> Optional[str]:
    """Return the existing multi-failure worker handoff only when needed."""
    if len(failures) < 2:
        return None
    reasons = " || ".join(
        f"[{failure['gate']}] {failure['reason']}" for failure in failures
    )
    return (
        f"{len(failures)} finalize gates failed (fix ALL in one respawn, do "
        f"NOT fix one at a time): {reasons}"
    )


def _run_batch_finalize_precheck(workspace: Path) -> Optional[str]:
    """Run and record the collect-all precheck without weakening the backstop."""
    try:
        precheck = finalize_pipeline.batch_precheck(workspace)
        if not precheck.get("applicable"):
            return None
        report_md = finalize_pipeline.format_batch_precheck_report(precheck)
        try:
            (workspace / "finalize_precheck.md").write_text(report_md)
        except Exception as error:
            logging.getLogger(__name__).debug(
                "Recoverable operation failed.", exc_info=error
            )
        failures = precheck.get("failures", [])
        if precheck.get("ok"):
            log.info(
                "batch_precheck: all PASS-branch finalize gates clear — finalize promotes in one pass"
            )
        elif precheck.get("precondition_block"):
            log.info(
                "batch_precheck: blocked by precondition gate %s",
                precheck["precondition_block"]["gate"],
            )
        else:
            log.info(
                "batch_precheck: %s finalize-gate failure(s) at once → worker fixes "
                "ALL in one respawn: %s",
                len(failures),
                ", ".join(failure["gate"] for failure in failures),
            )
        return _format_batch_precheck_failures(failures)
    except Exception as error:
        log.warning(
            f"batch_precheck failed ({error}); continuing — per-gate eligibility "
            "check is the backstop"
        )
        return None


def _run_finalize_prep(ctx: OrchestratorContext) -> Optional[str]:
    """Run best-effort artifact preparation before the authoritative gate."""
    _prepare_finalize_audit(ctx)
    _assemble_finalize_ge_ophost(ctx.workspace)
    _normalize_finalize_workspace(ctx.workspace)
    return _run_batch_finalize_precheck(ctx.workspace)


def _log_perf_na_recommendation(action: dict) -> None:
    """Log the pre-existing recommendation for a stuck performance gate."""
    if action["action"] == "coerce_perf_na":
        log.info(
            "DEBT-192: op is precision-PASS port_a3 on a perf-methodology loop "
            "→ recommend coercing performance.status=N/A (retract the unmeasured "
            "perf claim). Deferring the coercion to the port_a3 perf-N/A "
            "contract; loop halted."
        )


class _LoopBreakVerdict(NamedTuple):
    """The loop-break detection event paired with its recommended action."""

    break_event: dict
    action: dict


def _record_nonconvergent_loop(
    workspace: Path,
    lane,
    eligibility: dict,
    gate_tag: str,
    verdict: _LoopBreakVerdict,
) -> HandlerResult:
    """Persist the DEBT-192 pause state after the existing rollback record."""
    loop_break, action = verdict.break_event, verdict.action
    _log_perf_na_recommendation(action)
    # The loop-break halts WITHOUT the normal rollback cleanup — but the
    # workspace still holds the O5 build tree (kernel/build/*.o|.so), which
    # the graybox construction scan classifies as assembled-answer input and
    # rejects on the next agent respawn (2026-08-23 Outlook: loop-break
    # pause → decision → await_worker spawn rejected, 16 answer-classified
    # files).  Clear the harness-owned build artifacts here so the respawn
    # after the operator decision succeeds.
    _clear_harness_build_artifacts(workspace)
    (workspace / ".finalize_loop_nonconvergent").write_text(
        json.dumps(
            {
                "pattern": loop_break.get("pattern"),
                "gate": gate_tag,
                "count": loop_break["loop_detected_at_count"],
                "recommended_action": action["action"],
                "reason": eligibility["reason"][:1000],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    state_executor.record_transition(
        workspace,
        state_executor.TransitionDecision(
            next_state="await_user_decision",
            matched_transition_index=-1,
            rationale=(
                f"DEBT-192 loop-break (pattern={loop_break.get('pattern')}): "
                f"perf/methodology gate fired {loop_break['loop_detected_at_count']}× "
                f"with no progress; recommended={action['action']}; halting at "
                f"await_user_decision (not another respawn). Last reason: "
                f"{eligibility['reason']}"
            ),
            from_state="finalize",
            handoff="",
        ),
    )
    events.emit(
        workspace,
        "orchestrator.finalize_loop_break",
        lane=lane,
        data={
            "gate": gate_tag,
            "pattern": loop_break.get("pattern"),
            "rollback_state": eligibility["rollback_state"],
            "loop_count": loop_break["loop_detected_at_count"],
            "recommended_action": action["action"],
            "reason": eligibility["reason"],
        },
    )
    return HandlerResult.cont()


def _nonconvergent_loop_result(
    workspace: Path,
    lane,
    eligibility: dict,
    gate_tag: str,
) -> Optional[HandlerResult]:
    """Detect and halt a non-convergent finalize rollback loop."""
    loop_break = finalize_pipeline.detect_nonconvergent_loop(workspace)
    if not loop_break:
        return None
    action = finalize_pipeline.classify_loop_break_action(workspace, loop_break)
    log.info(
        f"finalize LOOP-BREAK (DEBT-192, pattern={loop_break.get('pattern')}): "
        f"gate {gate_tag} / perf-methodology family fired "
        f"{loop_break['loop_detected_at_count']}× with no progress — "
        f"recommended action {action['action']!r}; halting at "
        f"await_user_decision instead of respawning "
        f"{eligibility['rollback_state']!r} to avoid infinite loop"
    )
    return _record_nonconvergent_loop(
        workspace,
        lane,
        eligibility,
        gate_tag,
        _LoopBreakVerdict(break_event=loop_break, action=action),
    )


def _rollback_rationale(eligibility: dict, precheck_all_reasons: Optional[str]) -> str:
    """Build the existing worker-facing rollback rationale."""
    if (
        precheck_all_reasons is not None
        and eligibility["rollback_state"] == "await_worker"
    ):
        return (
            f"P0ff rollback (batch precheck — fix ALL at once): {precheck_all_reasons}"
        )
    return f"P0ff rollback: {eligibility['reason']}"


def _record_finalize_rollback(
    workspace: Path,
    lane,
    eligibility: dict,
    precheck_all_reasons: Optional[str],
) -> HandlerResult:
    """Write the existing synthetic finalize-to-worker rollback transition."""
    if eligibility.get("rollback_state") in {
        "await_worker",
        "await_probe",
        "await_optimizer",
        "await_fused_optimizer",
        "await_researcher",
        "await_det_analyzer",
    }:
        # Same graybox-respawn contract as the O5 rollback paths: the O5
        # candidate stage (.npubench_candidate) and build tree are answer-
        # classified and would reject the respawn.  2026-08-22 Crossformer:
        # an await_probe rollback kept them, and the precision-probe spawn
        # was rejected by the graybox construction scan.
        _clear_harness_build_artifacts(workspace)
    log.info(
        f"finalize ROLLBACK: not eligible ({eligibility['reason']}); rolling back "
        f"to {eligibility['rollback_state']!r}"
    )
    from briefs._common import g7_slug  # noqa: F401

    state_executor.record_transition(
        workspace,
        state_executor.TransitionDecision(
            next_state=eligibility["rollback_state"],
            matched_transition_index=-1,
            rationale=_rollback_rationale(eligibility, precheck_all_reasons),
            from_state="finalize",
            handoff="",
        ),
    )
    events.emit(
        workspace,
        "orchestrator.finalize_rollback",
        lane=lane,
        data={
            "rollback_state": eligibility["rollback_state"],
            "reason": eligibility["reason"],
        },
    )
    return HandlerResult.cont()
