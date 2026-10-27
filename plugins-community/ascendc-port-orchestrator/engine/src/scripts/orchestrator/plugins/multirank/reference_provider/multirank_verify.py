#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""multirank (compute-communication fusion) per-rank canonical verifier (design §3.2 / §5 Layer 4b).

Single responsibility: run ONE rank's worth of cases through the AscendC multirank
kernel, classify each via the CANONICAL judge (multirank_precision_eval_two_tier, which
delegates T1 math to precision_eval_two_tier.classify_output), and emit this
rank's summary as a last-line JSON. The orchestrator's multirank_runner spawns N copies
(one per rank), each initing the HCCL comm domain, and aggregates them into the op
verdict (ALL-rank-PASS, design §3.2) + writes verification.json with the mc2 rank-verdict block.

Harness-tree execution: multirank_runner launches this file IN PLACE from the harness
tree (engine/src/scripts/reference_provider/) — it is never staged or copied
into a worker workspace, so the worker has no edit surface on the verifier
(eliminating the worker-tampering surface per HARNESS_DESIGN_PHILOSOPHY §4e
mechanism-gate / §4j hermetic — author=worker, measurer's judge=orchestrator).

Per-case isolation: multirank_runner launches one process group PER CASE
(--filter-case + the case's own golden/<slug>.pt via --ref). Each launch then
covers exactly one case — its own HCCL init, its own golden load, its own
rank logs. The per-case golden stores full inputs + canonical outputs only;
this rank's input share and expected outputs are derived at launch from the
spec's shard/expected (rank shares are a deterministic derive, never stored).
A legacy monolithic golden (multirank_reference_outputs.pt, stored ranks) is still
accepted and filtered to this --world-size.

This is the multirank analog of port_a3's pass_a_runner.py — a per-rank
MULTI-PROCESS-ONLY verifier. The canonical math (tolerance, T1/T2 semantics,
MERE/MARE) lives in orchestrator code (multirank_precision_eval_two_tier); workers
do NOT re-derive it.

Single-process self-verify mode was REMOVED (2026-06-30): the prior `no --rank`
mode ran the kernel matmul-only (GetHcclContext null → only the compute half),
giving a false "compute PASS" while the comm half stayed untested until O5 — the
structural root of the matmul_allreduce 14h cold-start. multirank verify is now
MULTI-PROCESS ONLY: the comm half is exercised from worker generate onward.

Tolerance: the canonical judge uses two-tier T1 (MERE/MARE per dtype). When the
spec declares a `t2_competitor` callable (composed stock CANN path), each case
also runs the competitor on NPU and the judge's parity arm can return PASS_T2
(ours_MERE/MARE ≤ competitor's). With no competitor declared, T2 is
N/A_ALL_T1 and the verdict is T1-only (ours vs cpu_truth).

Output-driven compare: the kernel's output dict defines what gets compared — each
key it returns is matched against the golden's same-named key. Kernel output is
the current phase's result (single key for the final phase = combine_wsum); an
earlier-phase kernel emits its current-phase result the same way. No stage selector.

Exit codes: 0 = all PASS, 1 = some FAIL, 2 = device hang (watchdog os._exit(2)),
3 = environment error (torch_npu missing / forward-signature contract violation),
4 = golden-contract error (case/world-size mismatch). The last stdout line is
this rank's summary JSON (multirank_runner parses it + aggregate_all_ranks).

The worker adapter layer is model_new_ascendc.py — its forward must accept the
spec's input keys as kwargs and return a dict keyed by the spec's expected-output
names; group/rank auto-detect lives in the py_ext wrapper (torch.distributed),
with ONE exception: under group isolation (perf baseline / t2_competitor), this
verifier passes the candidate's isolated subgroup as a torch ProcessGroup
object via the optional `group` kwarg — the wrapper resolves the backend comm
name + rank/size from it op-side (the harness never touches backend comm
names). The per-rank canonical loop, tolerance, and last-line JSON schema are
generic.

Design refs: §3.2 (ALL rank PASS = PASS), §4.2 (device binding via
ASCEND_RT_VISIBLE_DEVICES mask), §5 Layer 4b/4c.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import sys
import threading
import time as _time_mod
from dataclasses import dataclass, field

import torch

# Diagnostic log: stderr (the runner/launcher merges stderr into the same
# rank log file). The rank-summary JSON protocol stays on stdout via its
# own bare-format logger — _parse_rank_summary keys on lines that start
# with "{" and carry "rank", so the protocol channel must stay unprefixed.
log = logging.getLogger("multirank_verify")
_summary = logging.getLogger("multirank_verify.summary")
_summary_handler = logging.StreamHandler(sys.stdout)
_summary_handler.setFormatter(logging.Formatter("%(message)s"))
_summary.addHandler(_summary_handler)
_summary.propagate = False

# Canonical multirank judge (orchestrator-owned). multirank_runner sets PYTHONPATH to the
# engine scripts root (env injection at the launcher); this fallback covers
# direct/worker invocation. Engine layout: the judge sits in the parent of this
# file's directory (engine/src/scripts/), next to precision_eval_two_tier.
try:
    from multirank_precision_eval_two_tier import (
        classify_multirank_case,
        summarize_per_rank,
    )
except ImportError:
    _here = pathlib.Path(__file__).resolve().parent
    for _cand in (pathlib.Path("src/scripts"), _here.parent):
        if (_cand / "multirank_precision_eval_two_tier.py").is_file():
            sys.path.insert(0, str(_cand))
            break
    from multirank_precision_eval_two_tier import (
        classify_multirank_case,
        summarize_per_rank,
    )  # noqa: E402


_LAUNCH_HANG_TIMEOUT = 90  # seconds; device-side (launch + synchronize) only


class _LaunchWatchdog(threading.Thread):
    """Device-side hang watchdog (design §4.2): if the kernel launch +
    synchronize window exceeds timeout_s, os._exit(2) — the runner's rc=2
    device-hang signal. Disarm via ``done.set()`` once synchronize returns."""

    def __init__(self, timeout_s, label=""):
        super().__init__(daemon=True)
        self.timeout_s = timeout_s
        self.label = label
        self.done = threading.Event()
        self._start = _time_mod.time()

    def run(self):
        while not self.done.wait(1.0):
            if _time_mod.time() - self._start > self.timeout_s:
                log.info(
                    f"[watchdog] TIMEOUT after {self.timeout_s}s "
                    f"({self.label}) — device-side hang, os._exit(2)"
                )
                getattr(os, "_exit")(2)


def _accepts_group_kwarg(fn) -> bool:
    """True when the spec baseline/competitor callable declares a `group`
    parameter (the isolated HCCL group it must run its collectives on)."""
    import inspect

    try:
        return "group" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _spec_fn(spec_mod, name: str):
    """Resolve a spec callable (shard / expected / perf_baseline /
    t2_competitor): the SPEC dict is the contract location; the
    module-level attribute is the conventional fallback."""
    if spec_mod is None:
        return None
    spec_dict = getattr(spec_mod, "SPEC", None) or {}
    fn = spec_dict.get(name) or getattr(spec_mod, name, None)
    return fn if callable(fn) else None


def _truth_tier(kernel_dir: pathlib.Path) -> str:
    """Read the workspace's truth tier from durable state. Same contract as
    plugins.multirank.read_truth_tier (key + valid enum + a3_live
    default), inlined because this subprocess's PYTHONPATH carries the
    package dir, not the package-qualified import path."""
    try:
        state = json.loads((kernel_dir / ".opgen_state.json").read_text())
        tier = state.get("multirank_truth_source")
    except Exception:
        tier = None
    return tier if tier in ("a3_live", "npubench") else "npubench"


def _manifest_golden_path(manifest_p: pathlib.Path, filter_case: str):
    """The per-case golden file named in golden/manifest.json, else None."""
    try:
        manifest = json.loads(manifest_p.read_text())
    except Exception:
        manifest = {}
    for c in manifest.get("cases") or []:
        if c.get("name") == filter_case:
            return manifest_p.parent / c["file"]
    return None


def _resolve_golden_path(args, kd: pathlib.Path) -> pathlib.Path:
    """Pick the golden file this launch reads.

    --ref wins (relative resolves against the kernel dir). Without it, a
    --filter-case lookup in golden/manifest.json finds the per-case file;
    otherwise fall back to the legacy monolith path."""
    if args.ref:
        p = pathlib.Path(args.ref)
        return p if p.is_absolute() else kd / p
    if args.filter_case:
        manifest_p = kd / "golden" / "manifest.json"
        if manifest_p.is_file():
            found = _manifest_golden_path(manifest_p, args.filter_case)
            if found is not None:
                return found
    return kd / "multirank_reference_outputs.pt"


def _build_cases(args, ref, ref_path, spec_mod) -> list:
    """Normalize the loaded golden into the case list the run loops consume.

    Per-case record ({"ranks": {rank: {"inputs", "outputs"}}} — one case per
    golden/<slug>.pt file): task-generated goldens STORE the collected
    per-rank shares (the task's generator is arbitrary Python; verify never
    re-derives). This rank's view comes straight from storage; the
    single-rank `ranks` view keeps the run loops below layout-agnostic."""
    if isinstance(ref, dict) and "ranks" in ref and "full_inputs" not in ref:
        # task-generated golden: per-rank shares were STORED at collection
        # time (the task's generator is arbitrary Python; verify never
        # re-derives). This rank's view comes straight from storage.
        rec = ref
        if rec.get("world_size") != args.world_size:
            raise VerifyRefused(
                4,
                (
                    f"case {rec.get('name')!r} is declared at world_size="
                    f"{rec.get('world_size')} but this launch is "
                    f"--world-size {args.world_size}"
                ),
            )
        if args.filter_case and args.filter_case != rec.get("name"):
            raise VerifyRefused(
                4,
                (
                    f"--filter-case {args.filter_case!r} does not match the "
                    f"loaded case {rec.get('name')!r} ({ref_path})"
                ),
            )
        key = str(args.rank)
        if key not in rec["ranks"]:
            raise VerifyRefused(
                4, (f"golden case {rec.get('name')!r} carries no rank {key} share")
            )
        share = rec["ranks"][key]
        return [
            {
                "name": rec.get("name"),
                "idx": rec.get("idx"),
                "case": rec.get("case"),
                "profile": rec.get("profile"),
                "world_size": rec["world_size"],
                "ranks": {
                    str(args.rank): {
                        "inputs": share["inputs"],
                        "outputs": share["outputs"],
                    }
                },
            }
        ]
    raise VerifyRefused(
        4,
        (
            f"golden {ref_path} carries no stored per-rank shares "
            f"(task-generated form expected)"
        ),
    )


def load_model_new(kernel_dir: pathlib.Path):
    # Thin wrapper: model_new_ascendc is imported in main() after kd is on
    # sys.path; returns the ModelNew class.
    mod_path = kernel_dir / "model_new_ascendc.py"
    if not mod_path.exists():
        raise FileNotFoundError(f"{mod_path} not found")
    import model_new_ascendc

    return model_new_ascendc.ModelNew


def run_kernel(
    model_new, rank_inputs: dict, device, group=None, group_triple=None
) -> dict:
    """Run the multirank kernel for ONE rank. Fixed convention: keyword splat of the
    spec's input keys plus the RESOLVED (group_str, rank_size, rank_id)
    triple — the op is the TORCH_LIBRARY first-class op taking the triple
    directly (no python wrapper layer; the forward stays graph-capture
    safe). `group` is a torch ProcessGroup OBJECT (the candidate's isolated
    subgroup, or None = WORLD); `group_triple` may carry the pre-resolved
    triple so a multi-launch caller resolves once via py_ext.resolve_group
    (backend comm knowledge stays op-side).
    Returns name->tensor keyed by the spec's expected-output names.
    """
    inputs_dev = {
        k: (v.to(device) if torch.is_tensor(v) else v) for k, v in rank_inputs.items()
    }
    if group_triple is None:
        import model_new_ascendc

        group_triple = getattr(model_new_ascendc, "_py_ext").resolve_group(group)
    (inputs_dev["group_str"], inputs_dev["rank_size"], inputs_dev["rank_id"]) = (
        group_triple
    )
    out = model_new(**inputs_dev)
    if isinstance(out, torch.Tensor):
        return {"y": out}
    if isinstance(out, (tuple, list)):
        return {f"out{i}": t for i, t in enumerate(out)}
    return dict(out)


def _build_reference_baseline(spec_mod, rank: int, world_size: int, base_group):
    """Build the npubench reference-baseline pair (task Model + comm
    namespace), or None when the spec carries no task reference
    implementation.

    The Model/init convention mirrors the collector's _run_rank_task; the
    comm namespace mirrors the collector's SimpleNamespace(hcomm_info=…,
    rank, world_size, device) so the baseline arm measures golden's
    producer exactly the way the collector produced golden.
    """
    for attr in ("Model", "get_init_inputs", "get_input_groups"):
        if not hasattr(spec_mod, attr):
            return None
    from types import SimpleNamespace

    init_args = spec_mod.get_init_inputs(rank=rank, world_size=world_size)
    model = spec_mod.Model(*init_args)
    if hasattr(model, "npu"):
        model = model.npu()
    hcomm = getattr(base_group, "_get_backend")(torch.device("npu")).get_hccl_comm_name(
        rank
    )
    comm = SimpleNamespace(
        hcomm_info=hcomm, rank=rank, world_size=world_size, device=rank
    )
    return model, comm


@dataclass
class ProfilerPlan:
    """Profiler window plan: warmup/active iterations, tag + rank (profile
    dir naming), and the per-iteration sync discipline.
    """

    warmup: int
    repeats: int
    tag: str
    rank: int
    sync_per_iter: bool = True


@dataclass
class CommDomain:
    """The rank's device + isolation groups (subgroups None outside
    perf/T2 runs).
    """

    device: object
    cand_group: "object | None"
    base_group: "object | None"


@dataclass
class RankRun:
    """One verify launch's fixed context threaded through the perf and
    precision campaign layers.
    """

    args: object
    spec: VerifySpec
    model_new: object
    comm: CommDomain
    kd: object


class VerifyRefused(Exception):
    """Loud verify-side refusal (golden/request mismatch); main() converts
    it to the runner-facing subprocess exit code.
    """

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _run_profiled_window(step_fn, plan: ProfilerPlan, profile_dir: str) -> None:
    """Warm up, then run the profiled window under torch_npu.profiler."""
    import torch_npu  # noqa: F401

    warmup, repeats = plan.warmup, plan.repeats
    for _ in range(warmup):
        step_fn()
        if plan.sync_per_iter:
            torch.npu.synchronize()
    if not plan.sync_per_iter:
        torch.npu.synchronize()
    exp = getattr(torch_npu.profiler, "_ExperimentalConfig")(
        profiler_level=torch_npu.profiler.ProfilerLevel.Level1,
        l2_cache=False,
        data_simplification=False,
        export_type=torch_npu.profiler.ExportType.Text,
    )
    with torch_npu.profiler.profile(
        activities=[
            torch_npu.profiler.ProfilerActivity.NPU,
            torch_npu.profiler.ProfilerActivity.CPU,
        ],
        schedule=torch_npu.profiler.schedule(
            wait=0, warmup=warmup, active=repeats, repeat=1
        ),
        on_trace_ready=torch_npu.profiler.tensorboard_trace_handler(profile_dir),
        record_shapes=False,
        profile_memory=False,
        with_stack=False,
        experimental_config=exp,
    ) as prof:
        for _ in range(warmup + repeats + 1):
            step_fn()
            prof.step()
            if plan.sync_per_iter:
                torch.npu.synchronize()
        if not plan.sync_per_iter:
            torch.npu.synchronize()


def _parse_profile_csv(profile_dir: str, repeats: int) -> tuple:
    """(per_iter_us, samples) from the window's operator_details.csv.

    Device-executed op rows are per-instance, in issue order (active phase
    only — the schedule's warmup phase is not exported). Sub-0.1us rows are
    profiler bookkeeping artifacts (record_event etc.) — excluded so the
    per-issue sequence contains real ops only. A composed baseline (matmul
    + all_reduce per issue) therefore still chunks correctly.
    Per-issue samples: chunk the durations into `repeats` consecutive
    groups and total each group (a fused kernel contributes one row per
    issue; a composed baseline contributes one row per op per issue)."""
    from pathlib import Path as _Path

    import pandas as _pd

    csv_files = list(_Path(profile_dir).rglob("operator_details.csv"))
    if not csv_files:
        raise RuntimeError(f"no operator_details.csv in {profile_dir}")
    df = _pd.read_csv(csv_files[0])
    col = "Device Self Duration(us)"
    if col not in df.columns:
        raise RuntimeError(f"missing {col} col in {csv_files[0]}")
    durations = [float(v) for v in df[col].tolist() if float(v) >= 0.1]
    per_iter_us = (sum(durations) / repeats) if durations else (df[col].sum() / repeats)
    samples = []
    if durations and len(durations) % repeats == 0:
        ops_per_iter = len(durations) // repeats
        for i in range(repeats):
            _lo = i * ops_per_iter
            _hi = (i + 1) * ops_per_iter
            samples.append(sum(durations[_lo:_hi]))
    return per_iter_us, samples


def _measure_profiler(step_fn, plan: ProfilerPlan):
    """Forward device self-duration via torch_npu.profiler.

    sync_per_iter=True: ONE torch.npu.synchronize() after each profiled
    iteration — the per-iteration realignment discipline for collectives
    (draining the queue each iteration realigns ranks at the last
    collective, bounding the next iteration's comm-op wait by one launch
    overhead). sync_per_iter=False: continuous issue — iterations queue
    back-to-back with a single sync at the end of the window (no
    per-iteration realignment).
    warmup + schedule(wait=0, warmup, active=repeats) under
    torch_npu.profiler.profile; parse operator_details.csv
    'Device Self Duration(us)' SUM / active -> per-iter us.
    profile_dir = /tmp/multirank_perf_rank{rank}_{tag}_{ms} (per-rank unique).
    Returns (per_iter_us, profile_dir, samples) — samples is the per-issue
    durations (one entry per issued iteration) when the op rows chunk evenly,
    else []."""
    import time as _time

    profile_dir = (
        f"/tmp/multirank_perf_rank{plan.rank}_{plan.tag}_{int(_time.time() * 1000)}"
    )
    _run_profiled_window(step_fn, plan, profile_dir)
    per_iter_us, samples = _parse_profile_csv(profile_dir, plan.repeats)
    return per_iter_us, profile_dir, samples


def _parse_args(argv):
    """CLI contract (one launch = one case at one rank; see module docstring)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("kernel_dir")
    ap.add_argument(
        "--ref",
        default=None,
        help="golden .pt path; default: the --filter-case entry in "
        "golden/manifest.json, else the legacy "
        "<kernel_dir>/multirank_reference_outputs.pt monolith",
    )
    ap.add_argument(
        "--filter-case",
        default=None,
        help="run ONLY the named case (e.g. case0@ws4[randn]) — "
        "the per-case isolation contract: one launch covers "
        "exactly one case",
    )
    ap.add_argument(
        "--rank",
        type=int,
        required=True,
        help="this rank's id (multirank_runner spawns one process per rank)",
    )
    ap.add_argument("--world-size", type=int, required=True)
    ap.add_argument("--master-addr", default=None)
    ap.add_argument("--master-port", type=int, default=None)
    ap.add_argument(
        "--run-only",
        action="store_true",
        help="run kernel, skip golden compare (diagnostic: output shape/nan/mean only)",
    )
    ap.add_argument(
        "--perf",
        action="store_true",
        help="perf mode: torch_npu.profiler device self-duration for "
        "candidate (+ perf_baseline if the spec declares one); "
        "skip golden compare. Emits per-rank perf in the rank summary.",
    )
    return ap.parse_args(argv)


@dataclass
class VerifySpec:
    """The spec-derived inputs one verify launch runs against.

    Constructed with one keyword per line by _load_spec_and_hooks.
    """

    ref: dict
    spec_mod: "object | None"
    tolerance: "object | None"
    perf_baseline_fn: "object | None"
    t2_competitor_fn: "object | None"


def _load_spec_and_hooks(args, kd) -> VerifySpec:
    """Golden view + spec hooks (tolerance / perf_baseline / t2_competitor)."""
    ref_path = _resolve_golden_path(args, kd)
    ref = torch.load(ref_path, map_location="cpu", weights_only=True)

    try:
        import spec as _spec_mod
    except ImportError:
        _spec_mod = None

    cases = _build_cases(args, ref, ref_path, _spec_mod)
    _tolerance = None
    if _spec_mod is not None:
        _spec_dict = getattr(_spec_mod, "SPEC", None)
        if isinstance(_spec_dict, dict):
            _tolerance = _spec_dict.get("tolerance")

    perf_baseline_fn = None
    t2_competitor_fn = None
    if args.perf:
        perf_baseline_fn = _spec_fn(_spec_mod, "perf_baseline")
    if not args.run_only and not args.perf:
        # T2 arm (design §4.1): the spec MAY declare a `t2_competitor` callable
        # (a composed stock CANN path). When declared, each case ALSO runs the
        # competitor on NPU and the canonical judge computes the parity verdict
        # (PASS_T2). Undeclared → T2 stays N/A_ALL_T1 (no silent fallback onto
        # perf_baseline — the two roles are declared separately on purpose).
        t2_competitor_fn = _spec_fn(_spec_mod, "t2_competitor")
    return VerifySpec(
        ref=ref,
        spec_mod=_spec_mod,
        tolerance=_tolerance,
        perf_baseline_fn=perf_baseline_fn,
        t2_competitor_fn=t2_competitor_fn,
    ), cases


def _init_comm(args, t2_competitor_fn):
    """torch_npu + the rank's HCCL domain; returns (device, cand_group,
    base_group) — the two subgroups stay None outside perf/T2 runs."""
    try:
        import torch_npu  # noqa: F401
    except Exception as e:
        raise VerifyRefused(3, f"torch_npu not available: {e}") from e

    # Multi-process HCCL: each rank inits the comm domain on its device.
    # design §4.2: the parent multirank_runner exports the ASCEND_RT_VISIBLE_DEVICES
    # mask, CANN remaps it to local indices, so set_device binds the right NPU.
    import torch.distributed as dist

    os.environ["MASTER_ADDR"] = args.master_addr or "127.0.0.1"
    os.environ["MASTER_PORT"] = str(args.master_port or 29500)
    torch.npu.set_device(args.rank)
    dist.init_process_group(
        "hccl",
        rank=args.rank,
        world_size=args.world_size,
        device_id=torch.device(f"npu:{args.rank}"),
    )
    device = torch.device(f"npu:{args.rank}")

    # Group isolation for perf-baseline and t2_competitor runs: the candidate and
    # the baseline/competitor EACH get their own comm domain — two
    # dist.new_group handles, never the shared WORLD group — so the fused
    # kernel's comm-resource usage and the baseline's collectives cannot
    # contaminate each other. The harness stays inside the torch API: it
    # passes the ProcessGroup OBJECT down via the optional `group` kwarg
    # (ModelNew.forward / the spec baseline alike); resolving the group to a
    # backend comm name is the op wrapper's own business (the HCCL binding
    # lives in py_ext, not in this file).
    base_group = None
    cand_group = None
    if args.perf or t2_competitor_fn is not None:
        cand_group = dist.new_group(ranks=list(range(args.world_size)), backend="hccl")
        base_group = dist.new_group(ranks=list(range(args.world_size)), backend="hccl")
        # Force comm creation on both subgroups up front (pure torch API).
        dist.barrier(group=cand_group)
        dist.barrier(group=base_group)
    return CommDomain(device=device, cand_group=cand_group, base_group=base_group)


def _load_candidate(kd, device, cand_group):
    """ModelNew on device; refuses a forward that cannot take the resolved
    group triple while group isolation is active."""
    model_new_cls = load_model_new(kd)
    model_new = (
        model_new_cls().to(device) if hasattr(model_new_cls, "to") else model_new_cls()
    )
    if cand_group is not None:
        import inspect as _inspect

        if "group_str" not in _inspect.signature(model_new_cls.forward).parameters:
            raise VerifyRefused(
                3,
                (
                    "multirank_verify convention: group isolation is active (perf "
                    "baseline / t2_competitor) but ModelNew.forward does not "
                    "accept the resolved (group_str, rank_size, rank_id) "
                    "triple — the candidate would silently run on the WORLD "
                    "group. Update the wrapper to take the resolved triple "
                    "(see workspace CLAUDE.md)."
                ),
            )
    return model_new


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    args = _parse_args(argv)

    kd = pathlib.Path(args.kernel_dir).resolve()

    # Import model_new once (kd on sys.path); reused by PREIMPORT_ENV + load_model_new.
    # Set op-declared PREIMPORT_ENV (HCCL_BUFFSIZE etc.) before torch_npu import.
    sys.path.insert(0, str(kd))
    import model_new_ascendc

    for _k, _v in getattr(model_new_ascendc, "PREIMPORT_ENV", {}).items():
        os.environ.setdefault(_k, str(_v))

    spec, cases = _load_spec_and_hooks(args, kd)
    comm = _init_comm(args, spec.t2_competitor_fn)
    model_new = _load_candidate(kd, comm.device, comm.cand_group)

    run = RankRun(
        args=args,
        spec=spec,
        model_new=model_new,
        comm=comm,
        kd=kd,
    )

    if args.perf:
        rank_summary = _run_perf_campaign(run, cases)
    else:
        rank_summary = summarize_per_rank(_run_precision_cases(run, cases))
    rank_summary["rank"] = args.rank
    import torch.distributed as dist

    dist.barrier()
    dist.destroy_process_group()
    # The last line holds this rank's summary JSON — multirank_runner parses
    # it, aggregates all ranks into the op verdict and writes verification.json.
    _summary.info(json.dumps(rank_summary))
    sys.exit(0 if rank_summary["status"] == "PASS" else 1)


@dataclass
class PerfSetup:
    """Per-campaign perf window + the resolved fallback baseline arm."""

    warmup: int
    repeats: int
    sync_per_iter: bool
    g_triple: tuple
    reference_model: "object | None" = None
    ref_comm: "object | None" = None
    profile_dirs: list = field(default_factory=list)


def _perf_setup(run: RankRun) -> PerfSetup:
    """Window sizes, sync discipline, the resolved group triple, and the
    npubench reference-model fallback baseline (spec perf_baseline wins)."""
    warmup_iters, active_iters = 5, 50
    # Sync discipline switch via env MULTIRANK_PERF_SYNC_MODE. The default
    # "iter" mode synchronizes torch.npu once per measured iteration so ranks
    # realign at collectives; the "end" mode issues back-to-back and syncs
    # once at the window end. The two trade realignment cost vs skew
    # exposure and both record per-iteration samples.
    sync_per_iter = os.environ.get("MULTIRANK_PERF_SYNC_MODE", "iter") != "end"
    # Eager measurement: the candidate (ModelNew with the resolved group
    # triple) and the spec baseline run as plain op calls, profiled via
    # torch_npu.profiler device self-duration — the only host-noise-
    # immune metric on this box, whose host dispatch is slow and jittery.
    import model_new_ascendc as _mna

    _g = getattr(_mna, "_py_ext").resolve_group(run.comm.cand_group)
    setup = PerfSetup(
        warmup=warmup_iters,
        repeats=active_iters,
        sync_per_iter=sync_per_iter,
        g_triple=_g,
    )
    # npubench reference baseline: absent an explicit perf_baseline,
    # the task Model IS the baseline (golden's producer) — build it
    # once on the isolated base group.
    if run.spec.perf_baseline_fn is None and _truth_tier(run.kd) == "npubench":
        _pair = _build_reference_baseline(
            run.spec.spec_mod, run.args.rank, run.args.world_size, run.comm.base_group
        )
        if _pair is not None:
            setup.reference_model, setup.ref_comm = _pair
    return setup


def _perf_baseline_arm(run: RankRun, setup: PerfSetup, inputs_dev):
    """Baseline-arm measurement: the spec perf_baseline callable, else the
    npubench reference Model; None when neither exists (ratio stays None)."""
    base_us, base_samples = None, []
    # perf_baseline (spec-declared callable) is the baseline arm;
    # the npubench reference Model is the fallback arm; specs with
    # neither skip the baseline honestly (ratio None → perf N/A).
    if run.spec.perf_baseline_fn is not None:

        def _base_step(_inp=inputs_dev):
            if _accepts_group_kwarg(run.spec.perf_baseline_fn):
                run.spec.perf_baseline_fn(
                    _inp,
                    run.comm.device,
                    run.args.rank,
                    run.args.world_size,
                    group=run.comm.base_group,
                )
            else:
                run.spec.perf_baseline_fn(
                    _inp, run.comm.device, run.args.rank, run.args.world_size
                )

        base_us, _dir, base_samples = _measure_profiler(
            _base_step,
            ProfilerPlan(
                warmup=setup.warmup,
                repeats=setup.repeats,
                tag="base",
                rank=run.args.rank,
                sync_per_iter=setup.sync_per_iter,
            ),
        )
        setup.profile_dirs.append(_dir)
    elif setup.reference_model is not None:
        # regenerate this case's positional input group — the
        # collector's generation path, same declaration order
        # (incl. attr slots) the task Model's forward expects.
        _ref_pos = tuple(
            run.spec.spec_mod.get_input_groups(
                rank=run.args.rank, world_size=run.args.world_size
            )
        )

        def _ref_step(
            _pos=_ref_pos, _comm=setup.ref_comm, _model=setup.reference_model
        ):
            _model(*_pos, comm=_comm)

        base_us, _dir, base_samples = _measure_profiler(
            _ref_step,
            ProfilerPlan(
                warmup=setup.warmup,
                repeats=setup.repeats,
                tag="base",
                rank=run.args.rank,
                sync_per_iter=setup.sync_per_iter,
            ),
        )
        setup.profile_dirs.append(_dir)
    return base_us, base_samples


def _perf_case_once(run: RankRun, setup: PerfSetup, case, ci) -> dict:
    """One case's A/B device self-duration record."""
    rk = str(run.args.rank)
    rank_data = (
        case["ranks"][rk] if rk in case["ranks"] else case["ranks"][run.args.rank]
    )
    log.info(f"-------- PERF CASE {ci} rank={run.args.rank} --------")

    # Inputs are moved to the device ONCE per case (resident tensors,
    # the production pattern) — per-iteration H2D copies would sit
    # inside the measured span and dominate it symmetrically on both
    # sides (ratio collapses to ~1.0).
    inputs_dev = {
        k: (v.to(run.comm.device) if torch.is_tensor(v) else v)
        for k, v in rank_data["inputs"].items()
    }

    # The candidate call goes through run_kernel — the SAME keyword-
    # splat convention the precision path uses (shard keys + the
    # resolved group triple), so both paths share one calling
    # contract regardless of how the kernel input set is derived.
    def _cand_step(_inp=inputs_dev, _triple=setup.g_triple):
        run_kernel(run.model_new, _inp, run.comm.device, group_triple=_triple)

    cand_us, _dir, cand_samples = _measure_profiler(
        _cand_step,
        ProfilerPlan(
            warmup=setup.warmup,
            repeats=setup.repeats,
            tag="cand",
            rank=run.args.rank,
            sync_per_iter=setup.sync_per_iter,
        ),
    )
    setup.profile_dirs.append(_dir)

    base_us, base_samples = _perf_baseline_arm(run, setup, inputs_dev)
    ratio = None
    if base_us is not None and cand_us > 0:
        ratio = round(base_us / cand_us, 3)

    def _ms(samples, fallback):
        """(mean, std) of per-issue samples, 3-decimal rounded; the
        aggregate us falls back when samples are unavailable."""
        import statistics as _st

        if not samples:
            return round(fallback, 3), None
        return (
            round(_st.mean(samples), 3),
            round(_st.stdev(samples), 3) if len(samples) > 1 else 0.0,
        )

    cand_mean, cand_std = _ms(cand_samples, cand_us)
    base_mean, base_std = (
        _ms(base_samples, base_us) if base_us is not None else (None, None)
    )
    record = {
        "case_id": case.get("name") or f"case_{ci}",
        "case_idx": ci,
        "candidate_us": round(cand_us, 3),
        "candidate_us_mean": cand_mean,
        "candidate_us_std": cand_std,
        "baseline_us": round(base_us, 3) if base_us is not None else None,
        "baseline_us_mean": base_mean,
        "baseline_us_std": base_std,
        "ratio": ratio,
    }
    log.info(
        f"[perf] case {ci} cand_us={cand_us:.2f}±{cand_std} "
        f"base_us={base_us}±{base_std} ratio={ratio}"
    )
    return record


def _run_perf_campaign(run: RankRun, cases) -> dict:
    """The perf-mode rank summary (precision unmeasured by design)."""
    import statistics as _st

    setup = _perf_setup(run)
    per_case_perf = [
        _perf_case_once(run, setup, case, ci) for ci, case in enumerate(cases)
    ]
    _cand_med = _st.median(p["candidate_us"] for p in per_case_perf)
    _base_vals = [
        p["baseline_us"] for p in per_case_perf if p["baseline_us"] is not None
    ]
    _base_med = _st.median(_base_vals) if _base_vals else None
    _ratio = round(_base_med / _cand_med, 3) if (_base_med and _cand_med > 0) else None
    return {
        "status": "PASS",
        "tier1_pass": len(cases),
        "total": len(cases),
        "tier1_pass_inclusive": len(cases),
        "tier2_status": "N/A_ALL_T1",
        "n_fail": 0,
        "n_err": 0,
        "method": "perf mode (precision unmeasured)",
        "results": [],
        "perf": {
            "candidate_us": round(_cand_med, 3),
            "baseline_us": round(_base_med, 3) if _base_med is not None else None,
            "ratio": _ratio,
            "profile_dirs": setup.profile_dirs,
            "cases": per_case_perf,
        },
    }


def _case_rank_data(run: RankRun, case, ci):
    """Log the case header (scalar meta only — tensor payloads are compare
    data, not log material) and return (case_label, this rank's view)."""
    case_label = case.get("name") or f"case_{ci}"
    _compare_keys = (
        "ranks",
        "idx",
        "name",
        "world_size",
        "profile",
        "full_inputs",
        "canonical_outputs",
        "outputs",
    )
    case_params = {}
    for k, v in case.items():
        if k not in _compare_keys:
            case_params[k] = v
    header = f"{'=' * 20} CASE {case_label} rank={run.args.rank} START {'=' * 20}"
    param_lines = "\n".join(f"{k} = {v}" for k, v in case_params.items())
    log.info(f"\n{header}\n{param_lines}")
    rk = str(run.args.rank)
    rank_data = (
        case["ranks"][rk] if rk in case["ranks"] else case["ranks"][run.args.rank]
    )
    return case_label, rank_data


def _launch_and_t2(run: RankRun, case_label, rank_data):
    """Candidate launch (watchdog-wrapped) + the T2 competitor arm.

    Returns (cand, comp_out, comp_err): a competitor crash degrades this
    case's T2 to N/A with a loud t2_competitor_error field — the T1
    verdict stands.
    """
    log.info("-------- KERNEL LAUNCH — CANN DumpHead below --------")
    wd = _LaunchWatchdog(_LAUNCH_HANG_TIMEOUT, case_label)
    wd.start()
    cand = run_kernel(
        run.model_new, rank_data["inputs"], run.comm.device, run.comm.cand_group
    )
    torch.npu.synchronize()
    # T2 arm: run the spec-declared competitor on NPU in the SAME HCCL
    # group (it may issue cross-rank collectives). Device-side → inside the
    # watchdog window.
    comp_out = None
    comp_err = None
    if run.spec.t2_competitor_fn is not None:
        log.info("-------- T2 COMPETITOR LAUNCH --------")
        try:
            if _accepts_group_kwarg(run.spec.t2_competitor_fn):
                _craw = run.spec.t2_competitor_fn(
                    rank_data["inputs"],
                    run.comm.device,
                    run.args.rank,
                    run.args.world_size,
                    group=run.comm.base_group,
                )
            else:
                _craw = run.spec.t2_competitor_fn(
                    rank_data["inputs"],
                    run.comm.device,
                    run.args.rank,
                    run.args.world_size,
                )
            torch.npu.synchronize()
            comp_out = {
                k: (v.detach().to("cpu") if torch.is_tensor(v) else v)
                for k, v in dict(_craw).items()
            }
        except Exception as e:  # noqa: BLE001
            comp_err = f"{type(e).__name__}: {e}"
            log.info(
                f"[t2-competitor] rank={run.args.rank} competitor "
                f"run failed: {comp_err}"
            )
    wd.done.set()  # device-side complete — disarm watchdog before CPU compare
    log.info("-------- KERNEL DONE --------")
    for name, t in cand.items():
        if torch.is_tensor(t):
            log.info(f"[forward] {name} | shape={list(t.shape)} | dtype={t.dtype}")
        else:
            log.info(f"[forward] {name} | {t!r}")
    return cand, comp_out, comp_err


def _run_only_stats(run, case, ci, cand) -> list:
    """--run-only diagnostic entry: output shape/nan/inf/mean/absmax, PASS."""
    for name, t in cand.items():
        t_cpu = t.detach().to("cpu") if torch.is_tensor(t) else t
        stat = (
            {
                "shape": list(t_cpu.shape),
                "has_nan": bool(torch.isnan(t_cpu).any().item()),
                "has_inf": bool(torch.isinf(t_cpu).any().item()),
                "mean": float(t_cpu.float().mean()),
                "absmax": float(t_cpu.float().abs().max()),
            }
            if torch.is_tensor(t_cpu)
            else {"value": t_cpu}
        )
        log.info(f"[run-only] out={name} {stat}")
    return [
        {
            "verdict": "PASS",
            "tier1_pass": True,
            "tier2_status": "N/A_ALL_T1",
            "case_id": case.get("name") or f"case_{ci}",
            "case_idx": ci,
            "rank": run.args.rank,
        }
    ]


def _fail_entry(run, case, ci, error: str) -> dict:
    """A per-output FAIL entry with the case/rank bookkeeping."""
    return {
        "verdict": "FAIL",
        "tier1_pass": False,
        "tier2_status": "N/A_ALL_T1",
        "error": error,
        "case_id": case.get("name") or f"case_{ci}",
        "case_idx": ci,
        "rank": run.args.rank,
    }


def _compare_one_output(run, case_label, out, comp) -> dict:
    """Classify one output vs golden; stamps the case/rank bookkeeping.

    out = (name, tensor, reference); comp = (competitor_map, competitor_error)."""
    name, t, ref_t = out
    comp_out, comp_err = comp
    m = classify_multirank_case(
        t.detach().to("cpu"),
        ref_t,
        cand_orig_dtype=t.dtype,
        competitor=(comp_out.get(name) if comp_out is not None else None),
        tolerance=run.spec.tolerance,
    )
    if comp_err:
        m["t2_competitor_error"] = comp_err
    m["case_id"] = case_label
    m["rank"] = run.args.rank
    return m


def _compare_case(run, case, ci, rank_data, artifacts):
    """Judge one case against golden (canonical classifier); returns
    (per-output entries, this-case pass flag)."""
    cand, comp_out, comp_err = artifacts
    entries: list = []
    this_case_pass = True
    if run.args.run_only:
        return _run_only_stats(run, case, ci, cand), True
    ref_out = rank_data["outputs"]
    log.info("-------- GOLDEN COMPARE --------")
    if not cand:
        this_case_pass = False
        entries.append(_fail_entry(run, case, ci, "kernel returned no outputs"))
        log.error("[FAIL] kernel returned no outputs")
    for name, t in cand.items():
        ref_t = ref_out.get(name)
        if ref_t is None:
            this_case_pass = False
            entries.append(
                _fail_entry(run, case, ci, f"output '{name}' has no golden reference")
            )
            log.error(f"[FAIL] output '{name}' has no golden reference")
            continue
        case_label = case.get("name") or f"case_{ci}"
        m = _compare_one_output(run, case_label, (name, t, ref_t), (comp_out, comp_err))
        entries.append(m)
        log.info(
            f"[compare] {name}: verdict={m.get('verdict')} "
            f"tier1_pass={m.get('tier1_pass')} "
            f"tier2_status={m.get('tier2_status')}"
        )
        if not str(m.get("verdict", "")).startswith("PASS"):
            this_case_pass = False
            _log_mismatch_detail(name, t, ref_t)
    return entries, this_case_pass


def _log_mismatch_detail(name, t, ref_t):
    """Diff stats for a failed output: mismatch counts plus exact-value
    bins 1 and 2 (shape-aware; skipped on shape mismatch or empty)."""
    _c = t.detach().to("cpu")
    _g = ref_t.detach().to("cpu")
    if _c.shape == _g.shape and _c.numel():
        _df = (_c.to(torch.float64) - _g.to(torch.float64)).abs()
        log.info(
            f"[diff] {name}: n_mismatch={int((_df > 0).sum().item())}/{_df.numel()} "
            f"max_diff={_df.max().item():.0f} "
            f"n_diff1={int((_df == 1).sum().item())} "
            f"n_diff2={int((_df == 2).sum().item())}"
        )


def _run_case_precision(run: RankRun, case, ci) -> list:
    """One case end-to-end under the default path: header, launch + T2,
    golden compare; returns the case's per-output entries."""
    case_label, rank_data = _case_rank_data(run, case, ci)
    artifacts = _launch_and_t2(run, case_label, rank_data)
    entries, passed = _compare_case(run, case, ci, rank_data, artifacts)
    case_verdict = "PASS" if passed else "FAIL"
    log.info(f"{'=' * 20} CASE {ci} END verdict={case_verdict} {'=' * 20}")
    return entries


def _run_precision_cases(run: RankRun, cases) -> list:
    """Default path: canonical classification per case (T1-only; T2 N/A
    unless the spec declares a competitor)."""
    entries: list = []
    for ci, case in enumerate(cases):
        entries.extend(_run_case_precision(run, case, ci))
    return entries


if __name__ == "__main__":
    # Entry-level guard: converts VerifyRefused (raised by the golden-view
    # helpers) to the runner-facing exit code. sys.exit stays legal here and
    # inside main — the entry-point exception the rule carves out.
    try:
        main()
    except VerifyRefused as exc:
        log.error(str(exc))
        sys.exit(exc.code)
