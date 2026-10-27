# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""MULTIRANK multi-NPU phase_o5 runner (Layer 4c).

Per-case isolation: the campaign runs ONE CASE PER LAUNCH — world_size>=2
spawns N subprocesses (one per rank) for that case only, each running
`multirank_verify.py --rank r --world-size N --ref golden/<case>.pt --filter-case
<name> --master-addr/--master-port`, with ASCEND_RT_VISIBLE_DEVICES set to
the ordered lane mask. Every case launch gets its own HCCL comm domain, its
own golden file (the provision-published per-case tree), its own card probe
(lanes=None production path: pick_idle before launch, confirm_idle after),
and its own rank logs under workspace/.run/<case>/. Each multirank_verify.py emits
a last-line rank-summary JSON (classified via the canonical judge
multirank_precision_eval_two_tier); this runner parses them, folds the per-case
summaries back into the rank_verdicts group shape (exactly ws entries per
world_size), and aggregates_all_ranks → ALL-rank-PASS op verdict.
world_size==1 degenerates to a single-rank launch of the same path.

Harness gaps fixed here (2026-06-30, design §4e/§4j/§3):
  1. OPP env (ASCEND_CUSTOM_OPP_PATH) — multirank_build stages the op package but
     never persists the env; runtime dlsym fell through to system
     libopapi.so ("aclnnX not in libopapi.so"). Injected here (env unified
     at the launcher).
  2. Canonical separation — multirank_verify is a thin shell importing
     multirank_precision_eval_two_tier (orchestrator-owned judge); this runner
     aggregates via the SAME judge's aggregate_all_ranks (author=worker,
     judge=orchestrator — §4j hermetic).
  3. Perf — MeasuredResult.perf is populated from the per-rank profiler
     summaries via multirank_perf.aggregate_perf; no trusted-receipt assembly
     exists (the measurement result is returned as measured).

Device binding (design §4.2): the parent sets ASCEND_RT_VISIBLE_DEVICES=<mask>;
CANN remaps the mask to local indices 0..N-1, so rank r runs on lanes[r]. Each
child inherits the mask + calls torch.npu.set_device(rank) +
dist.init_process_group('hccl') inside multirank_verify.py.

Timeout layering: device-side deadlock (launch+synchronize hang) is caught by
multirank_verify's in-process _LaunchWatchdog at 90s via os._exit(2) (rc=2). This
runner's _MULTIRANK_RANK_TIMEOUT is the HOST-SIDE per-rank fallback (default 600s) —
it only fires if the whole rank subprocess (cold-start + all cases' launch +
comm + CPU golden compare) exceeds it, e.g. compare wedge.

Case-level failure discipline: a rank that produces NO parseable summary
(hard crash, rc=2 hang, host timeout) yields a SYNTHETIC ERROR entry
(schema-compatible with summarize_per_rank) and the campaign CONTINUES — every
case keeps its measured outcome. Before this, any single case-level crash
returned a campaign-wide runner_error that discarded every already-measured
case, making an honest PARTIAL worker claim structurally un-reconcilable at
O5 (moe_fused_a8w8: case6's hard crash dropped case0/case3's PASS verdicts).
runner_error is now reserved for GLOBAL could-not-execute refusals only. A
post-run card leak (confirm_idle) is a `probe_leak` note on that case's entry
— orthogonal to the verdicts, never a campaign abort: the next case's
pick_idle re-probes and avoids dirty cards on its own.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import logging
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import NamedTuple, Optional

import phase_o5_runner  # noqa: F401
from phase_o5 import MeasuredResult

# Canonical multirank judge (orchestrator-owned). This module lives under
# plugins/multirank/; src/scripts is three levels up — ensure it is importable
# for the judge module's shared precision_eval_two_tier dependency.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from .multirank_precision_eval_two_tier import aggregate_all_ranks  # noqa: E402

# Rank-verdict entry shaping (fold per-case summaries into the gate's group
# shape) lives in its own module; these aliases keep the historical names.
from .multirank_perf import aggregate_perf as _aggregate_perf  # noqa: E402
from .multirank_rank_verdicts import (  # noqa: E402
    GroupUnverifiedRecord,
    case_verdicts_of as _case_verdicts_of,
    fold_rank_verdicts as _fold_rank_verdicts,
    record_group_unverified as _record_group_unverified,
)
from .multirank_emit import emit_verification_json as _emit_verification_json  # noqa: E402
from .multirank_emit import VerificationPayload  # noqa: E402


class CampaignResolution(NamedTuple):
    """_resolve_campaign result: declared groups, provisioned cases and the
    feasible ws list for this invocation (err_result is a loud-refusal
    MeasuredResult, else None; feasible=[] with err_result=None means
    "delegate to run()").
    """

    declared_ws: "list[int] | None"
    cases: "list | None"
    by_ws: "dict | None"
    feasible: list
    skipped: "list | None"
    env: "object | None"
    err_result: "object | None"


class GroupCaseRun(NamedTuple):
    """_run_group_cases result: per-case rank summaries, misses, merged
    summaries, all-ok flag and first lane error (err_result on loud
    refusal).
    """

    ran: list
    missing: list
    merged: list
    all_ok: bool
    first_lane_err: "str | None"
    leaks: dict
    err_result: "object | None"


@dataclass
class CampaignOutcome:
    """Per-campaign accumulations across all feasible groups (built by
    _run_feasible_groups; the emit layer reads them).
    """

    merged: list = field(default_factory=list)
    rank_verdicts: dict = field(default_factory=dict)
    unverified: dict = field(default_factory=dict)
    unverified_cases: dict = field(default_factory=dict)
    all_ok: bool = True
    first_lane_err: "str | None" = None
    case_verdicts: dict = field(default_factory=dict)


@dataclass
class CampaignContext:
    """One campaign invocation's fixed context: workspace/op identity plus
    the mode flags threaded unchanged through every launch/collect layer.
    lanes stay OUT — they vary per case (auto-allocation re-probes).
    """

    workspace: Path
    op: str
    run_only: bool = False
    perf: bool = False
    env: "object | None" = None
    remote: '"_RemoteCampaign | None"' = None


log = logging.getLogger(__name__)

# Per-rank subprocess fallback timeout (host-side). Device-side deadlock is
# reported by multirank_verify's _LaunchWatchdog (90s, os._exit(2) → rc=2). This 600s
# only fires if the whole rank subprocess (cold-start + all cases + CPU golden
# compare) exceeds it.
_MULTIRANK_RANK_TIMEOUT = 600

# Harness-owned canonical verifier, executed in place from the harness tree —
# never staged into the workspace. A staged copy was worker-editable surface
# (the canonical gate below could only catch tampering after the fact); the
# in-place path removes the tamper vector by construction and guarantees every
# op's verify always tracks the harness version. Layout:
# engine/src/scripts/orchestrator/plugins/multirank/reference_provider/multirank_verify.py
# — the same path the multirank plugin declares for the scanner
# (plugins/multirank/__init__.py verify_files) and multirank_verify.py itself
# resolves the canonical judge from.
_CANONICAL_VERIFY = (
    Path(__file__).resolve().parent / "reference_provider" / "multirank_verify.py"
)


def _canonical_verify_error(*, short: bool = False) -> "str | None":
    """The canonical-verifier gate error (file missing / canonical judge not
    imported), else None. short=True drops the harness-tree path hint (the
    per-case loop's terse variant)."""
    verify = _CANONICAL_VERIFY
    if not verify.is_file():
        hint = (
            ""
            if short
            else (" — expected the harness-tree reference_provider/multirank_verify.py")
        )
        return (
            f"multirank_runner: canonical verifier missing at {verify} "
            f"(harness install broken{hint})"
        )
    if "classify_multirank_case" not in verify.read_text(errors="ignore"):
        return (
            "mc2 canonical gate: multirank_verify.py must import classify_multirank_case "
            "from multirank_precision_eval_two_tier (orchestrator canonical judge). "
            "Worker must not re-derive tolerance/allclose (§4e/§4j)."
        )
    return None


def _campaign_refusal(runner_error: str) -> CampaignResolution:
    """A loud campaign-level refusal: every resolution field but err is None."""
    return CampaignResolution(
        None, None, None, None, None, None, _measured(runner_error=runner_error)
    )


def _measured(**fields) -> MeasuredResult:
    """Construct a MeasuredResult carrying the multirank campaign extras.

    phase_o5.MeasuredResult does not declare the
    `unverified_world_sizes` / `multirank_case_verdicts` fields; they are attached
    here as plain attributes (plain @dataclass, no slots) so the multirank
    plugin's finalize_perf_capture contract (mc2_res.unverified_world_sizes /
    mc2_res.perf / mc2_res.runner_error) holds without widening phase_o5.
    Both extras are ALWAYS present ({} / None defaults)."""
    unverified = fields.pop("unverified_world_sizes", None) or {}
    case_verdicts = fields.pop("multirank_case_verdicts", None)
    res = MeasuredResult(**fields)
    res.unverified_world_sizes = unverified
    res.multirank_case_verdicts = case_verdicts
    return res


def _rank_timeout() -> int:
    """Per-rank subprocess timeout (seconds). Default _MULTIRANK_RANK_TIMEOUT; the env
    var MULTIRANK_RANK_TIMEOUT overrides at call time (honored by BOTH the FSM path
    run_phase_gate->multirank_runner.run AND the manual run.py verify path), so a
    debug session can tighten/loosen it without code edits."""
    try:
        return int(os.environ.get("MULTIRANK_RANK_TIMEOUT", _MULTIRANK_RANK_TIMEOUT))
    except (ValueError, TypeError):
        return _MULTIRANK_RANK_TIMEOUT


def _device_mask(lanes: list[int]) -> str:
    """ASCEND_RT_VISIBLE_DEVICES value for a lane set."""
    return ",".join(str(ln) for ln in lanes)


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _activate_opp_env(env: dict, workspace: Path, op: str) -> dict:
    """multirank: multirank_build stages the op package under
    <op_project>/.install/packages/vendors/customize but never persists
    ASCEND_CUSTOM_OPP_PATH into the runtime env (multirank_build.setup_operator_env is
    a build_ext-only copy). Probe the op_project layout (mandated nest:
    workspace/<op>/prj-<op>/; single-layer + legacy-nested are fallbacks) and set
    ASCEND_CUSTOM_OPP_PATH + LD_LIBRARY_PATH so multirank_verify.py resolves aclnn* via
    GetOpApiFuncAddr — else dlsym falls through to system libopapi.so ("aclnnX
    not in libopapi.so", the 4-agent repeated-workaround root).

    keep-in-sync with multirank_build._opp_path (engine/src/scripts/patches/
    multirank_build.py — its comment points back here).
    Also adds src/scripts to PYTHONPATH so multirank_verify's
    `from multirank_precision_eval_two_tier import ...` resolves.
    """
    e = dict(env)
    customize = ".install", "packages", "vendors", "customize"
    # multirank layout (mandated 2026-07-07): C++ project under workspace/<op>/prj-<op>/;
    # .install at workspace/<op>/prj-<op>/.install. Earlier layouts kept as
    # fallback: single-layer workspace/.install, legacy nested workspace/<op>/<op>.
    cands = [
        workspace / f"prj-{op}",  # mandated nest (prj-<op>/.install)
        workspace,  # legacy single-layer (workspace/.install)
        workspace / op,  # legacy nested workspace/<op>/<op>
    ]
    for base in cands:
        opp = base.joinpath(*customize)
        if (opp / "op_api" / "lib").is_dir():
            e["ASCEND_CUSTOM_OPP_PATH"] = str(opp)
            lib = str(opp / "op_api" / "lib")
            e["LD_LIBRARY_PATH"] = lib + ":" + e.get("LD_LIBRARY_PATH", "")
            break
    # PYTHONPATH: this package's dir so multirank_verify imports the canonical
    # judge (plugins/multirank/ holds multirank_precision_eval_two_tier), plus
    # src/scripts — the judge's import closure reaches precision_eval_two_tier
    # at the scripts root. Without it the LOCAL launch path fails with
    # ModuleNotFoundError (the remote staged copy carries the tree and worked).
    pkg_dir = str(Path(__file__).resolve().parent)
    scripts_dir = str(Path(__file__).resolve().parents[3])
    e["PYTHONPATH"] = pkg_dir + ":" + scripts_dir + ":" + e.get("PYTHONPATH", "")
    return e


# ---------------------------------------------------------------------------
# Remote (endpoint) execution: the candidate endpoint's EXEC mode decides —
# local paths never touch any of this (zero behavior change).
# ---------------------------------------------------------------------------
_REMOTE_LAUNCH = Path(__file__).resolve().parent / "multirank_remote_launch.py"


class _RemoteCampaign:
    """One campaign's remote staging context (candidate endpoint, non-local).

    stage_host/stage_exec are the two sides of the endpoint's staging area;
    ws_exec is the exec-side copy of the op workspace (the local relative
    layout is preserved, so the launcher's opp probing works unchanged)."""

    def __init__(self, endpoint, stage_host: str, stage_exec: str, op: str):
        self.endpoint = endpoint
        self.stage_host = stage_host
        self.stage_exec = stage_exec
        self.ws_exec = f"{stage_exec}/{op}"
        self.verify_exec = f"{stage_exec}/multirank_verify.py"
        self.launch_exec = f"{stage_exec}/multirank_remote_launch.py"


def _resolve_remote(op: str):
    """Resolve the campaign's remote context from the live env; None for a
    local/absent candidate endpoint (the local Popen path stays untouched)."""
    from . import multirank_endpoint as _ep

    env = _ep.load_env_or_none()
    if env is None:
        return None
    endpoint = _ep.resolve_endpoint(env, "candidate")
    if endpoint.exec_mode == "local":
        return None
    stage_host, stage_exec = _ep.endpoint_stage_dir(endpoint, base="multirank_verify")
    return _RemoteCampaign(endpoint, stage_host, stage_exec, op)


def _stage_tree_files(files: list, root: Path, remote_prefix: str) -> None:
    """Append every file under root (recursive) as (local, prefix/relpath)."""
    if not root.is_dir():
        return
    for p in sorted(root.rglob("*")):
        if p.is_file():
            files.append((p, f"{remote_prefix}/{p.relative_to(root)}"))


def _remote_stage_files(workspace: Path, op: str) -> list:
    """(local, remote_name) manifest for one campaign staging: the canonical
    judge + launcher + precision_eval (verify's sibling import fallback),
    the judge's import closure, plus the op's executable surface (spec,
    golden tree, model entries, prj-<op>/.install + py_ext).

    The closure's remote layout mirrors the sys.path inserts the staged
    modules perform themselves: multirank_precision_eval_two_tier inserts
    its own dir and imports precision_eval_two_tier; that module (and
    precision_tier1) insert <root>/reference_provider and
    <root>/orchestrator/precision. Renaming a remote_name below breaks the
    endpoint-side import — the post-stage smoke in _remote_stage fails loud
    on exactly that drift."""
    scripts_root = Path(__file__).resolve().parents[3]
    grader_dir = scripts_root / "orchestrator" / "precision" / "cannbench_grader"
    files = [
        (_CANONICAL_VERIFY, "multirank_verify.py"),
        (_REMOTE_LAUNCH, "multirank_remote_launch.py"),
        (
            Path(__file__).resolve().parent / "multirank_precision_eval_two_tier.py",
            "multirank_precision_eval_two_tier.py",
        ),
        (scripts_root / "precision_eval_two_tier.py", "precision_eval_two_tier.py"),
        (scripts_root / "precision_tier1.py", "precision_tier1.py"),
        (scripts_root / "precision_tier2.py", "precision_tier2.py"),
        (
            scripts_root / "reference_provider" / "verify.py",
            "reference_provider/verify.py",
        ),
        *[
            (p, f"orchestrator/precision/cannbench_grader/{p.name}")
            for p in sorted(grader_dir.glob("*.py"))
        ],
    ]
    for name in ("spec.py", "model.py", "model_new_ascendc.py"):
        p = workspace / name
        if p.is_file():
            files.append((p, f"{op}/{name}"))
    _stage_tree_files(files, workspace / "golden", f"{op}/golden")
    for prj in sorted(workspace.glob("prj-*")):
        for sub in (".install", "py_ext"):
            _stage_tree_files(files, prj / sub, f"{op}/{prj.name}/{sub}")
    return files


def _remote_stage(remote: "_RemoteCampaign", workspace: Path, op: str):
    """Stage the campaign's executable surface to the endpoint once per
    campaign (md5-manifest skipped: an unchanged tree transfers nothing).
    Returns a loud-failure MeasuredResult, else None."""
    from . import multirank_endpoint as _ep

    files = _remote_stage_files(workspace, op)
    if not any(name.startswith(f"{op}/") for _, name in files):
        return _measured(
            runner_error=(
                f"multirank_runner: nothing to stage for remote verify — "
                f"workspace {workspace} has no executable surface (spec/golden/"
                f"prj-*)"
            )
        )
    subdirs = sorted(
        {str(Path(name).parent) for _, name in files if "/" in str(Path(name).parent)}
    )
    try:
        _ep.remote_exec(
            remote.endpoint,
            [
                "mkdir",
                "-p",
                remote.stage_exec,
                *[f"{remote.stage_exec}/{d}" for d in subdirs],
            ],
        )
        _ep.sync_up(remote.endpoint, files, remote.stage_host)
    except Exception as e:
        return _measured(
            runner_error=(
                f"multirank_runner: remote staging to {remote.stage_host} failed: {e!r}"
            )
        )
    # Judge import smoke: the closure is the one staging surface whose
    # gaps surface at RUN time as per-rank ModuleNotFoundError — probe the
    # import here so a manifest drift fails loud at stage time instead.
    r = _ep.remote_exec(
        remote.endpoint,
        [
            "python3",
            "-c",
            f"import sys; sys.path.insert(0, {remote.stage_exec!r}); "
            "import precision_eval_two_tier",
        ],
        timeout=120,
    )
    if r.returncode != 0:
        return _measured(
            runner_error=(
                f"multirank_runner: judge import smoke failed in "
                f"{remote.stage_exec}: {(r.stderr or '')[-300:]}"
            )
        )
    return None


def _pick_idle_remote(remote: "_RemoteCampaign", n: int):
    """Delegate to the shared endpoint probe (see multirank_endpoint)."""
    from . import multirank_endpoint as _ep

    return _ep.pick_idle_npu(remote.endpoint, n)


def _confirm_idle_remote(remote: "_RemoteCampaign", lanes: list):
    """Remote twin of npu_probe.confirm_idle: re-probe the endpoint and note
    any residual process on the used cards."""
    from . import multirank_endpoint as _ep

    r = _ep.remote_exec(remote.endpoint, ["npu-smi", "info"], timeout=90)
    if r.returncode != 0:
        return f"confirm re-probe failed rc={r.returncode}"
    import lane_pool

    statuses = lane_pool.parse_npu_smi(r.stdout, valid_ids=None)
    dirty = [
        str(nid)
        for nid in lanes
        if nid in statuses and statuses[nid].has_running_process
    ]
    if dirty:
        return f"cards {','.join(dirty)} still show processes after the case"
    return None


def _parse_rank_summary(log_text: str) -> Optional[dict]:
    """Parse multirank_verify.py's last-line rank-summary JSON from its stdout log.
    Returns None if no parseable JSON line found (runner_error upstream)."""
    lines = [ln.strip() for ln in log_text.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.startswith("{") and '"rank"' in ln:
            try:
                return json.loads(ln)
            except ValueError:
                continue
    return None


def _campaign_cases(workspace: Path) -> list[dict]:
    """Provisioned campaign cases from golden/manifest.json (the O2.5-published
    index: name/world_size/file per expanded case). [] when absent — callers
    fail loud (provision owns the golden tree)."""
    from . import multirank_phase_o25

    return multirank_phase_o25.load_golden_manifest(workspace).get("cases") or []


def _case_log_dir(workspace: Path, case_slug: str) -> Path:
    """Per-launch rank-log dir under workspace/.run/<slug>/, stale logs wiped.

    Rank logs are runtime byproducts (not candidate bytes). Keeping them under
    the dot-prefixed `.run/` tree keeps them out of any sealed-snapshot
    file-set that ignores dotfiles — a perf re-measure re-running verify
    would otherwise rewrite rank_*.log and trip candidate-context drift
    checks. Only `rank_*.log` files are removed before each launch (the dir
    itself is kept) so a re-run never mixes stale logs from a prior launch.
    `case_slug` names the launched case (one process group per case) — every
    launch has one."""
    if not case_slug:
        raise ValueError("_case_log_dir requires a launch slug")
    d = workspace / ".run" / case_slug
    d.mkdir(parents=True, exist_ok=True)
    for f in d.glob("rank_*.log"):
        f.unlink()
    return d


def _spawn_rank_procs(
    workspace: Path,
    op: str,
    lanes: list[int],
    extra_cmd_args: list[str],
    case_slug: str,
):
    """Build env (opp + device mask + free port), Popen N rank subprocesses.
    Rank stdout/stderr go to per-launch log files under
    workspace/.run/<case_slug>/rank_{r}.log (wiped per launch).
    Returns (procs, log_dir)."""
    env = _activate_opp_env(dict(os.environ), workspace, op)
    env["ASCEND_RT_VISIBLE_DEVICES"] = _device_mask(lanes)
    port = _free_port()
    verify = _CANONICAL_VERIFY
    log_dir = _case_log_dir(workspace, case_slug)
    ws = len(lanes)
    procs = []
    try:
        for r in range(ws):
            cmd = [
                sys.executable,
                str(verify),
                str(workspace),
                "--rank",
                str(r),
                "--world-size",
                str(ws),
                "--master-addr",
                "127.0.0.1",
                "--master-port",
                str(port),
                *extra_cmd_args,
            ]
            logf = open(log_dir / f"rank_{r}.log", "w")
            try:
                p = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    cwd=str(workspace),
                )
            except BaseException:
                logf.close()
                raise
            procs.append((r, p, logf))
    except BaseException:
        for _r, p, logf in procs:
            p.kill()
            logf.close()
        raise
    return procs, log_dir


def _wait_rank_procs(workspace: Path, procs, timeout: int, log_dir: Path):
    """Wait each rank subprocess (per-rank timeout fallback), SIGKILL on expiry,
    read each rank log. Returns [(rank, rc, stdout, timed_out)].
    rc==2 = device hang (multirank_verify _LaunchWatchdog os._exit(2))."""
    out = []
    for r, p, logf in procs:
        timed_out = False
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            log.error(
                f"[multirank_runner] rank {r} timed out after {timeout}s "
                f"(host-side fallback) — SIGKILL"
            )
            p.kill()
            try:
                p.wait(timeout=10)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                pass
            rc, timed_out = -1, True
        finally:
            logf.close()
        try:
            stdout = (log_dir / f"rank_{r}.log").read_text(errors="ignore")
        except OSError:
            stdout = ""
        out.append((r, rc, stdout, timed_out))
    return out


def _det_policy_satisfied(policy: str, observed: bool) -> bool:
    """determinism.md: n_a / best_effort are monitor-only (satisfied vacuously
    true, observation recorded only); only required gates on the observed value."""
    return True if policy in ("n_a", "best_effort") else observed


def _golden_world_sizes(workspace: Path) -> list[int]:
    """Declared case world_sizes from the multirank spec (single authoritative source
    — never a materialized copy in ref_runnable.json, which carries only
    anti-tamper fields). Empty list when the spec is absent/unreadable; the ws
    filter inside multirank_verify.py then remains the only guard."""
    from . import multirank_phase_o25

    return multirank_phase_o25.declared_case_world_sizes(workspace)


def _synthetic_error_summary(
    rank: int, case_slug: str, why: str, log_path: str
) -> dict:
    """Rank summary for a rank that produced no parseable summary (hard
    crash / device hang rc==2 / host timeout). Schema-compatible with
    summarize_per_rank so aggregate_all_ranks, case_verdicts_of and
    fold_rank_verdicts consume it without special-casing: status ERROR
    (≠ PASS → the aggregate honestly fails), zero pass counts, one ERROR
    result carrying the failure class and the rank-log evidence pointer."""
    return {
        "rank": rank,
        "status": "ERROR",
        "tier1_pass": 0,
        "tier2_pass": 0,
        "tier1_pass_inclusive": 0,
        "total": 1,
        "n_fail": 0,
        "n_err": 1,
        "tier2_status": "FAIL",
        "method": f"multirank_runner synthetic (no rank summary: {why})",
        "results": [
            {
                "case_id": case_slug,
                "rank": rank,
                "verdict": "ERROR",
                "error": why,
                "evidence": log_path,
            }
        ],
    }


def _launch_and_collect(
    ctx: CampaignContext, lanes: list[int], extra_cmd_args: list[str], case_slug: str
):
    """Spawn rank procs for ONE case launch, wait, parse summaries.

    Returns (rank_summaries, rank_ok, detail) with EXACTLY one summary entry
    per rank, real or synthetic: a rank whose stdout parses keeps its real
    verdict; a rank that produced no parseable summary (hard crash, device
    hang rc==2, host timeout) gets a synthetic ERROR entry pointing at its
    rank log. A case-level execution failure is therefore MEASURED — the
    campaign continues and aggregates the ERROR — instead of aborting with a
    campaign-wide runner_error that discarded every already-measured case
    (moe_fused_a8w8: case6's hard crash dropped case0/case3's PASS verdicts
    and made the worker's honest PARTIAL claim structurally un-reconcilable
    at O5). Global could-not-execute refusals (empty lanes,
    missing verifier) stay with the callers.

    remote (endpoint path): launch the STAGED remote launcher on the
    candidate endpoint (one subprocess per rank over there), pull the rank
    logs back, and apply the SAME parse/synthetic semantics — verdict
    aggregation is endpoint-agnostic; local stays the historical Popen path
    unchanged."""
    timeout = _rank_timeout()
    if ctx.remote is None:
        procs, log_dir = _spawn_rank_procs(
            ctx.workspace, ctx.op, lanes, extra_cmd_args, case_slug=case_slug
        )
        results = _wait_rank_procs(ctx.workspace, procs, timeout, log_dir)
    else:
        results = _remote_launch(ctx, lanes, extra_cmd_args, case_slug, timeout)
    return _collect_from_results(lanes, results, case_slug, timeout)


def _remote_launch(
    ctx: CampaignContext,
    lanes: list[int],
    extra_cmd_args: list[str],
    case_slug: str,
    timeout: int,
):
    """Launch the staged remote launcher for ONE case and pull the rank
    artifacts back. The launcher always exits 0 once ranks were launched —
    rank-level outcomes are rank DATA (rank_<r>.log + rank_<r>.rc), not
    launcher failures. A launcher-level failure (ssh/stage broken) surfaces
    as every rank recorded ERROR — the case is MEASURED, never dropped."""
    from . import multirank_endpoint as _ep

    port = _free_port()
    cmd = [
        "python3",
        ctx.remote.launch_exec,
        ctx.remote.verify_exec,
        ctx.remote.ws_exec,
        case_slug,
        str(len(lanes)),
        str(port),
        *[str(x) for x in lanes],
        "--",
        *extra_cmd_args,
    ]
    try:
        _ep.remote_exec(ctx.remote.endpoint, cmd, timeout=timeout + 600)
        _ep.sync_down(
            ctx.remote.endpoint,
            f"{ctx.remote.stage_host}/{ctx.workspace.name}",
            [f".run/{case_slug}/rank_{r}.log" for r in range(len(lanes))]
            + [f".run/{case_slug}/rank_{r}.rc" for r in range(len(lanes))],
            ctx.workspace,
        )
    except Exception as e:
        log.error(
            f"[multirank_runner] ctx.remote launch failed for {case_slug}: "
            f"{e!r} — ranks recorded as ERROR"
        )
        return [(r, -1, "", True) for r in range(len(lanes))]
    results = []
    log_dir = ctx.workspace / ".run" / case_slug
    for r in range(len(lanes)):
        stdout = ""
        try:
            stdout = (log_dir / f"rank_{r}.log").read_text(errors="ignore")
        except OSError:
            pass
        rc = -1
        try:
            rc = int((log_dir / f"rank_{r}.rc").read_text().strip())
        except (OSError, ValueError):
            pass
        results.append((r, rc, stdout, False))
    return results


def _collect_from_results(
    lanes: list[int], results: list, case_slug: str, timeout: int
):
    """Shared tail of _launch_and_collect (endpoint-agnostic): parse each
    rank's stdout into a summary or a synthetic ERROR entry."""
    ws = len(lanes)
    mask = _device_mask(lanes)
    rank_ok = {r: (rc == 0) for r, rc, _, _ in results}
    timed_out = [r for r, _, _, to in results if to]
    device_hang = [r for r, rc, _, _ in results if rc == 2]

    detail = f"world_size={ws} device_mask={mask} rank_exit0={rank_ok}"
    if device_hang:
        detail += (
            f" rank_device_hang={device_hang} (multirank_verify _LaunchWatchdog "
            f"os._exit(2) — device-side deadlock)"
        )
    elif timed_out:
        detail += f" rank_timed_out={timed_out} (host-side fallback after {timeout}s)"

    rank_summaries = []
    exec_errors: list[str] = []
    for r, rc, stdout, to in results:
        rs = _parse_rank_summary(stdout)
        if rs is not None:
            rank_summaries.append(rs)
            continue
        # No parseable summary = this rank did not measure. Record a
        # synthetic ERROR (never drop the case) and mark the rank not-ok
        # even when rc==0 — no summary is no measurement.
        if rc == 2:
            why = (
                "device-side hang — multirank_verify _LaunchWatchdog fired "
                "(launch+synchronize exceeded 90s)"
            )
        elif to:
            why = f"host-side timeout after {timeout}s (SIGKILL fallback)"
        else:
            why = f"rank exited rc={rc} without a parseable summary"
        rank_ok[r] = False
        exec_errors.append(f"rank {r}: {why}")
        rank_summaries.append(
            _synthetic_error_summary(
                r, case_slug, why, f"workspace/.run/{case_slug}/rank_{r}.log"
            )
        )
    if exec_errors:
        detail += f" case_exec_errors=[{'; '.join(exec_errors)}]"
    return rank_summaries, rank_ok, detail


def _build_verdict(workspace: Path, rank_summaries: list[dict]):
    """(overall, pass_a, determinism, perf) from rank summaries — shared by
    run() (single group) and run_all_groups() (merged groups). perf is the
    _aggregate_perf result (None for precision-only runs)."""
    overall = aggregate_all_ranks(rank_summaries)
    # tier2_pass is carried: the verification-schema gate requires it and a
    # pass_a without it erases the kw-maintained field on every O5 rewrite.
    pass_a = {
        "status": overall["status"],
        "tier1_pass": overall["tier1_pass"],
        "tier2_pass": overall["tier2_pass"],
        "tier1_pass_inclusive": overall["tier1_pass_inclusive"],
        "total": overall["total"],
        "tier2_status": overall["tier2_status"],
        "method": overall["method"],
    }
    # Determinism: every rank produced an identical-shape, finite verdict across
    # its cases (the canonical judge is deterministic; multirank forward with no
    # scatter-add is deterministic by construction). n_identical = ranks PASS.
    n_pass_ranks = sum(1 for rs in rank_summaries if rs.get("status") == "PASS")
    # det_policy classification lives in .opgen_state.json (written by the
    # orchestrator's O1.5 classifier); default "n_a" when absent.
    try:
        _st = json.loads((workspace / ".opgen_state.json").read_text())
        _det_policy = _st.get("det_policy") or "n_a"
    except Exception:
        _det_policy = "n_a"
    _observed_det = n_pass_ranks == len(rank_summaries)
    determinism = {
        "policy": _det_policy,
        "observed_deterministic": _observed_det,
        "policy_satisfied": _det_policy_satisfied(_det_policy, _observed_det),
        "n_identical_cases": n_pass_ranks,
        "n_cases_checked": len(rank_summaries),
        "method": (
            "MULTIRANK per-rank verdict equality across world_size ranks "
            "(deterministic by construction: forward has no "
            "scatter-add/atomicAdd)"
        ),
    }
    return overall, pass_a, determinism, _aggregate_perf(rank_summaries)


def _resolve_single_group(ctx: CampaignContext, lanes) -> tuple:
    """Pre-checks for the single-ws path: (ws, cases, err_result) — the
    err_result is a loud refusal, else None."""
    if not lanes:
        return None, None, _measured(runner_error="multirank_runner: empty lanes list")

    ws = len(lanes)
    declared_ws = _golden_world_sizes(ctx.workspace)
    if declared_ws and ws not in declared_ws:
        return (
            None,
            None,
            _measured(
                runner_error=(
                    f"multirank_runner: len(lanes)={ws} matches no declared case world_size "
                    f"{declared_ws} — physical lanes select which cards execute "
                    f"declared cases; they cannot create new ones. Adjust the "
                    f"lane list length or declare world_size={ws} cases in spec.py."
                )
            ),
        )
    cases = [c for c in _campaign_cases(ctx.workspace) if c.get("world_size") == ws]
    if not cases:
        return (
            None,
            None,
            _measured(
                runner_error=(
                    f"multirank_runner: no provisioned cases at world_size={ws} in "
                    f"golden/manifest.json — re-run provision (the golden tree is "
                    f"the campaign index)."
                )
            ),
        )
    # Canonical gate (§4e mechanism-gate / §4j hermetic): the verifier MUST
    # import the orchestrator judge classify_multirank_case. With the verifier
    # executed from the harness tree this is a harness self-check (the worker
    # cannot reach the file), guarding against a broken template.
    verify_err = _canonical_verify_error()
    if verify_err is not None:
        return None, None, _measured(runner_error=verify_err)
    log.info(
        f"[multirank_runner] {ctx.op}: world_size={ws} lanes={lanes} "
        f"cases={len(cases)} run_only={ctx.run_only}"
    )
    return ws, cases, None


def run(ctx: CampaignContext, lanes: list[int]) -> MeasuredResult:
    """MULTIRANK multi-NPU phase_o5 re-measure for the cases at ONE world_size.

    lanes: allocated NPU ids (primary = lanes[0]); CANN remaps the ordered
    mask to local indices, so rank r runs on lanes[r]. world_size = len(lanes)
    must match one of the golden's declared case world_sizes (per-case ws
    contract) — physical lanes only select which cards execute declared
    cases, they cannot create new ones. The ws group's provisioned cases run
    SEQUENTIALLY on these lanes, one launch per case (per-case isolation:
    each case gets its own HCCL init, golden file, and rank logs).
    run_all_groups() covers every declared group in one call (orchestrator
    entry).
    multirank verify always uses multirank_verify.py multi-process path (never ssh_runner)
    — ssh_runner looks for pass_a/b_runner.py which multirank ops don't produce.

    run_only: pass --run-only to multirank_verify.py (run kernel, skip golden compare).
    Used by the G1 smoke check so a phased kernel (where only 1 of N stages is
    implemented) doesn't fail the smoke test on unimplemented golden outputs.
    Crash detection still works (non-zero exit → runner_error).

    Output-driven compare: multirank_verify.py matches the kernel's output dict keys
    against the golden's same-named keys (no stage selector). A rank exiting
    rc==2 signals device-side hang (multirank_verify _LaunchWatchdog).

    Verdict-vs-execution contract: a rank
    whose cases all pass exits 0; a rank with ANY failing case still prints
    its classified summary and exits 1 — either way the run is a completed
    MEASUREMENT. A rank that produces NO summary (hard crash / device hang
    rc==2 / host timeout) yields a synthetic ERROR entry and the campaign
    continues: every case-level outcome (PASS/FAIL/ERROR) is measured and
    returned, so phase_o5 can reconcile counts against the worker's claim
    (honest PARTIAL claims reconcile; overclaims MISMATCH). runner_error is
    reserved for global could-not-execute refusals (empty lanes, missing
    verifier, no provisioned cases). verification.json is emitted ONLY on
    ALL-rank-PASS (GAP-1 contract) — a FAIL measurement never overwrites the
    worker-authored claimed artifact.
    """
    ctx.workspace = Path(ctx.workspace).resolve()
    ws, cases, err_result = _resolve_single_group(ctx, lanes)
    if err_result is not None:
        return err_result
    # Verifier presence + canonical-judge gate: already enforced by
    # _resolve_single_group (a None err_result means both checks passed).

    details: list[str] = []
    ran, _missing, merged, all_ok, _first_err, _leaks, err_result = _run_group_cases(
        ctx, ws, cases, lanes, details
    )
    if err_result is not None:
        return err_result

    verdict, perf_agg = _build_campaign_verdict([ws], cases, ctx.workspace, merged)

    _perf_error_cases(perf_agg, ran)

    if all_ok:
        single = CampaignOutcome(
            merged=merged,
            rank_verdicts={str(ws): _fold_rank_verdicts(ws, ran)},
        )
        _emit_all_pass_artifact(ctx, verdict, single)
    elif not ctx.perf:
        _log_measured_failure(
            "measured-FAIL: not all ranks PASS", verdict.overall, details
        )
    return _measured(
        pass_a=None if ctx.perf else verdict.pass_a,
        determinism=None if ctx.perf else verdict.determinism,
        perf=perf_agg,
        multirank_case_verdicts=None if ctx.perf else (_case_verdicts_of(ran) or None),
    )


def _run_group_cases(
    ctx: CampaignContext,
    ws: int,
    group_cases: list,
    lanes: "list[int] | None",
    details: list,
):
    """Launch every case of ONE world_size group (per-case isolation: probe
    before each case's own launch, confirm the cards process-clean after).

    Returns (ran, missing, merged, all_ok, first_lane_err, leaks,
    err_result); err_result is a MeasuredResult on any loud failure, else
    None. `leaks` maps case name → confirm_idle note for cases whose cards
    showed residual processes after finishing — the verdicts stay in `ran`
    (already collected) and the campaign continues: the next case's pick_idle
    re-probes and avoids dirty cards on its own."""
    from . import multirank_phase_o25

    ran: list = []
    missing: list = []
    merged: list = []
    leaks: dict[str, str] = {}
    all_ok = True
    first_lane_err: str | None = None
    for case in group_cases:
        cname = case["name"]
        case_lanes, lane_err = _resolve_case_lanes(ctx, lanes, ws)
        if lane_err:
            if first_lane_err is None:
                first_lane_err = f"{cname} (world_size={ws}): {lane_err}"
            missing.append((case, lane_err))
            details.append(f"{cname}: UNVERIFIED ({lane_err})")
            continue
        verify_err = _canonical_verify_error(short=True)
        if verify_err is not None:
            return GroupCaseRun(
                None, None, None, False, None, {}, _measured(runner_error=verify_err)
            )
        extra = ["--ref", f"golden/{case['file']}", "--filter-case", cname]
        if ctx.run_only:
            extra.append("--run-only")
        if ctx.perf:
            extra.append("--perf")
        # Perf launches get their own rank-log dir (<case>.perf/) so a ctx.perf
        # re-measure never overwrites the precision run's rank logs.
        slug = multirank_phase_o25.case_slug(cname) + (".perf" if ctx.perf else "")
        rank_summaries, rank_ok, detail = _launch_and_collect(
            ctx, case_lanes, extra, case_slug=slug
        )
        if lanes is None:
            leak = _confirm_case_idle(ctx, case_lanes)
            if leak is not None:
                # Hygiene note, orthogonal to the verdicts just collected.
                # Never abort the campaign for a leak: the measurements are
                # in hand and valid, and a dirty card is the next case's
                # pick_idle problem (it re-probes per case by design).
                leaks[cname] = leak
                details.append(
                    f"{cname}: LEAK {leak} (verdicts kept; next case re-probes)"
                )
        merged.extend(rank_summaries)
        ran.append((cname, rank_summaries, rank_ok))
        all_ok = all_ok and all(rank_ok.get(r) for r in range(ws))
        details.append(f"{cname}: {detail}")
    return GroupCaseRun(ran, missing, merged, all_ok, first_lane_err, leaks, None)


def _perf_error_cases(perf_agg, ran) -> None:
    """Name the cases whose perf rows are missing because the rank crashed
    mid-measure — the aggregate shows the coverage gap instead of a
    silently absent case."""
    if perf_agg is None:
        return
    _err = sorted(
        {c for c, s, _ok in ran if any(rs.get("status") == "ERROR" for rs in s)}
    )
    if _err:
        perf_agg["error_cases"] = _err


def _resolve_case_lanes(ctx: CampaignContext, lanes, ws):
    """One case's cards: the explicit-lane slice, the remote idle probe, or
    the local idle probe. Returns (case_lanes, lane_err)."""
    if lanes is not None:
        return lanes[:ws], None
    if ctx.remote is not None:
        return _pick_idle_remote(ctx.remote, ws)
    import npu_probe

    return npu_probe.pick_idle(ctx.env, ws)


def _confirm_case_idle(ctx: CampaignContext, case_lanes):
    """Post-run residual-process check on the case's cards (None = clean)."""
    if ctx.remote is not None:
        return _confirm_idle_remote(ctx.remote, case_lanes)
    import npu_probe

    return npu_probe.confirm_idle(ctx.env, case_lanes)


def _group_cases_by_ws(cases, declared_ws):
    """Group provisioned cases by world_size; refuses manifest entries that
    fall outside the spec's declared set (the spec is authoritative)."""
    by_ws: dict[int, list[dict]] = {}
    for c in cases:
        cws = c.get("world_size")
        if isinstance(cws, int):
            by_ws.setdefault(cws, []).append(c)
    unknown = sorted(set(by_ws) - set(declared_ws))
    if unknown:
        return None, _measured(
            runner_error=(
                f"multirank_runner.run_all_groups: golden/manifest.json declares "
                f"world_size(s) {unknown} absent from the spec's declared "
                f"{declared_ws} — the spec is authoritative; re-run provision "
                f"(the golden tree is stale)."
            )
        )
    return by_ws, None


def _feasible_ws(declared_ws, lanes, filter_ws, env):
    """The ws list this invocation runs (plus skipped and the probe env).
    filter_ws validates against the declared set; explicit lanes cap by
    capacity. Returns (feasible, skipped, env, err_result)."""
    if lanes is None:
        # Per-case auto-allocation: every declared group's cases are
        # attempted; the probe decides card availability per case at its own
        # launch time.
        if env is None:
            # Probe env: npu_probe's cohesive loader (load_npu_info_cmd —
            # target-first NPU_INFO_CMD resolution). briefs._common.load_env
            # exists but AscendCEnv carries no npu_info_cmd attribute, which
            # would silently drop the custom probe command (fetch_devices
            # duck-types only that attribute).
            try:
                import npu_probe

                env = npu_probe.ProbeEnv.from_env_file()
            except Exception:
                env = None
        if filter_ws is not None:
            # Deliberate single-group subset — never a campaign: validate
            # against the spec (no inventing groups), and (below) never emit
            # verification.json from a one-group run.
            if filter_ws not in declared_ws:
                return (
                    None,
                    None,
                    env,
                    _measured(
                        runner_error=(
                            f"multirank_runner.run_all_groups: --filter-ws={filter_ws} "
                            f"matches no declared case world_size {declared_ws} — "
                            f"only declared groups may be run."
                        )
                    ),
                )
            feasible = [filter_ws]
        else:
            feasible = list(declared_ws)  # ascending (spec-validated order)
        skipped: list[int] = []
    else:
        feasible = [ws for ws in declared_ws if ws <= len(lanes)]
        skipped = [ws for ws in declared_ws if ws > len(lanes)]
    if not feasible:
        return (
            None,
            None,
            env,
            _measured(
                runner_error=(
                    f"multirank_runner.run_all_groups: len(lanes)={len(lanes)} covers NO "
                    f"declared case world_size {declared_ws} — provide at least "
                    f"{min(declared_ws)} lanes."
                )
            ),
        )
    return feasible, skipped, env, None


def _resolve_campaign(workspace: Path, op: str, lanes, filter_ws, env):
    """Resolve the campaign's declared groups + provisioned cases + the
    feasible ws list for this invocation.

    Returns (declared_ws, cases, by_ws, feasible, skipped, env, err_result) —
    err_result is a MeasuredResult on any loud refusal (no declared ws, no
    provisioned cases, stale manifest, bad flags, empty coverage), else None.
    A single-declared-ws explicit-lane call returns err_result=None with
    feasible=[] as the "delegate to run()" signal."""
    declared_ws = _golden_world_sizes(workspace)
    if not declared_ws:
        return _campaign_refusal(
            "multirank_runner.run_all_groups: no declared case world_sizes in "
            "spec.py — author the spec's cases (then run.py provision)."
        )
    if lanes is not None and not lanes:
        return _campaign_refusal("multirank_runner: empty lanes list")
    if lanes is not None and filter_ws is not None:
        return _campaign_refusal(
            "multirank_runner.run_all_groups: --filter-ws and an explicit lane list "
            "are mutually exclusive — pick one (filter_ws probes for the "
            "group's cards itself)"
        )
    if lanes is not None and len(declared_ws) == 1 and len(lanes) == declared_ws[0]:
        return CampaignResolution(
            declared_ws, None, None, [], None, env, None
        )  # delegate to run()

    cases = _campaign_cases(workspace)
    if not cases:
        return _campaign_refusal(
            "multirank_runner.run_all_groups: no provisioned campaign cases "
            "(golden/manifest.json missing or empty) — run.py provision "
            "first."
        )
    by_ws, err_result = _group_cases_by_ws(cases, declared_ws)
    if err_result is not None:
        return CampaignResolution(None, None, None, None, None, None, err_result)

    feasible, skipped, env, err_result = _feasible_ws(
        declared_ws, lanes, filter_ws, env
    )
    if err_result is not None:
        return CampaignResolution(None, None, None, None, None, None, err_result)
    return CampaignResolution(declared_ws, cases, by_ws, feasible, skipped, env, None)


def run_all_groups(
    ctx: CampaignContext,
    lanes: "list[int | None]" = None,
    filter_ws: "int | None" = None,
) -> MeasuredResult:
    """Run EVERY provisioned campaign case (one multi-rank launch per case)
    and merge into one MeasuredResult + verification.json.
    Orchestrator/step_executor entry; run() covers a single explicit-lane ws.

    Per-case isolation: cases run ws-ascending, then in manifest order within
    a ws. Every case is its own launch — its own HCCL init, its own golden
    file (--ref golden/<case>.pt --filter-case <name>), its own rank logs
    under workspace/.run/<case>/.

    lanes semantics:
    - lanes=None (DEFAULT, the production path): PER-CASE auto-allocation.
      Right before each case's launch the idle cards are probed (npu_probe,
      custom NPU_INFO_CMD or local npu-smi) and the case's ws cards are
      picked fresh; right after the case finishes, the used cards must show
      processes==0 (leaked rank process check). A foreign tenant grabbing a
      card mid-campaign therefore contaminates at most the cases it actually
      overlaps — later cases re-probe and either get clean cards or record
      their own UNVERIFIED.
    - lanes given (diagnostic): the explicit capacity set — cases at
      ws ≤ len(lanes) run on lanes[:ws]; declared groups above the capacity
      are a LOUD partial-coverage runner_error (never silently dropped).

    filter_ws (lanes=None only): run ONLY the cases with this world_size —
    a deliberate single-group subset for iteration, NOT a campaign. The ws
    must be declared in the spec (loud error otherwise; no new group may be
    invented). A filtered run NEVER emits verification.json — the
    authoritative claimed artifact comes from full campaigns only; a
    one-group run must not overwrite it with partial data.

    Card shortage is recorded PER CASE as UNVERIFIED (objective probe
    evidence — a worker cannot fabricate "cards were busy") and the campaign
    CONTINUES with the remaining cases. A ws whose cases ALL went unverified
    is projected to the ws-level `unverified` placeholder (the finalize
    gate's full-group shape); a partially-run ws folds the cases that ran
    into rank_verdicts and records the missing ones under
    `unverified_cases`. Only when NOTHING has run at all does the failure
    stay a runner_error (the O5 infra retry / pause path owns that case).
    A post-run card leak (confirm_idle saw residual processes) is a
    `probe_leak` note on that case's entry in multirank_case_verdicts — the
    verdicts stay measured, the campaign continues, and the next case's
    pick_idle re-probes and avoids dirty cards on its own.
    Declared cases are never degraded or silently dropped — UNVERIFIED
    coverage is loud in verification.json + the MeasuredResult.

    Measured-FAIL (verdict-level) is NOT runner_error: every case launched
    ends in a measured outcome — PASS/FAIL verdicts from ranks that produced
    summaries, synthetic ERROR entries for ranks that did not (hard crash /
    device hang / host timeout). The merged measurement is returned as
    MeasuredResult(pass_a=...) with aggregate status FAIL so phase_o5 can
    reconcile counts (VERIFIED on honest PARTIAL match, MISMATCH on
    overclaim). verification.json emit remains the ALL-rank-PASS GAP-1
    contract (not emitted on measured-FAIL).
    """
    ctx.workspace = Path(ctx.workspace).resolve()
    declared_ws, cases, by_ws, feasible, skipped, env, err_res = _resolve_campaign(
        ctx.workspace, ctx.op, lanes, filter_ws, ctx.env
    )
    ctx.env = env  # the resolved env flows into the per-group launches
    if err_res is not None:
        return err_res
    ctx.remote = _resolve_remote(ctx.op)
    if ctx.remote is not None:
        err_res = _remote_stage(ctx.remote, ctx.workspace, ctx.op)
        if err_res is not None:
            return err_res
    if feasible == [] and cases is None:
        # single declared ws + explicit matching lanes → the run() path
        return run(
            ctx.workspace,
            ctx.op,
            lanes,
            run_only=ctx.run_only,
            perf=ctx.perf,
            remote=ctx.remote,
        )
    details: list[str] = []
    outcome, err_res = _run_feasible_groups(ctx, lanes, by_ws, feasible, details)
    if err_res is not None:
        return err_res

    refusal = _coverage_refusal(outcome, feasible, skipped, lanes, details)
    if refusal is not None:
        return refusal

    # ws-level projection for the O5/finalize UNVERIFIED channel: a ws is
    # reported when ANY of its cases went unverified (full groups carry the
    # gate's placeholder shape; partial groups point at unverified_cases).
    unv_projection = _project_unverified(outcome)

    verdict, perf_agg = _build_campaign_verdict(
        declared_ws, cases, ctx.workspace, outcome.merged
    )
    _annotate_perf_gaps(perf_agg, outcome, by_ws)
    _report_campaign_verdict(ctx, verdict, outcome, filter_ws, details)
    if unv_projection:
        _log_unverified_projection(unv_projection, outcome)
    return _measured(
        pass_a=None if ctx.perf else verdict.pass_a,
        determinism=None if ctx.perf else verdict.determinism,
        perf=perf_agg,
        unverified_world_sizes=unv_projection,
        multirank_case_verdicts=None if ctx.perf else (outcome.case_verdicts or None),
    )


def _log_unverified_projection(unv_projection: dict, outcome) -> None:
    """The loud UNVERIFIED-coverage warning (card shortage, probe evidence)."""
    log.warning(
        f"[multirank_runner] UNVERIFIED coverage (card shortage, objective "
        f"probe evidence — the campaign continued): world_sizes="
        f"{sorted(int(w) for w in unv_projection)}"
        + (
            f" cases={sorted(outcome.unverified_cases)}"
            if outcome.unverified_cases
            else ""
        )
    )


@dataclass
class CampaignVerdict:
    """The emit layer's view of one campaign's aggregate verdict."""

    declared_ws: list
    cases: list
    overall: dict
    pass_a: dict
    determinism: "dict | None"
    perf_agg: "dict | None"


def _build_campaign_verdict(declared_ws, cases, workspace, merged) -> tuple:
    """Aggregate the merged rank summaries and wrap them for the emit layer;
    returns (CampaignVerdict, perf_agg)."""
    overall, pass_a, determinism, perf_agg = _build_verdict(workspace, merged)
    verdict = CampaignVerdict(
        declared_ws=declared_ws,
        cases=cases,
        overall=overall,
        pass_a=pass_a,
        determinism=determinism,
        perf_agg=perf_agg,
    )
    return verdict, perf_agg


def _run_feasible_groups(
    ctx: CampaignContext, lanes, by_ws, feasible, details
) -> tuple:
    """Run every feasible ws group (ascending), accumulating the campaign
    outcome; the second element is a loud-refusal MeasuredResult, else None."""
    _probe_note = (
        "npu_probe.pick_idle (custom NPU_INFO_CMD or local npu-smi; "
        "ctx.remote endpoints probe the ctx.remote npu-smi)"
    )
    outcome = CampaignOutcome()
    for ws in feasible:  # ascending world_size — smallest card count first
        group_cases = by_ws.get(ws) or []
        if not group_cases:
            return outcome, _measured(
                runner_error=(
                    f"multirank_runner.run_all_groups: spec declares world_size={ws} "
                    f"but golden/manifest.json has no cases at it — re-run "
                    f"provision (the golden tree is stale)."
                )
            )
        ran, missing, grp_merged, grp_ok, grp_first_err, grp_leaks, err_res = (
            _run_group_cases(ctx, ws, group_cases, lanes, details)
        )
        if err_res is not None:
            return outcome, err_res
        if outcome.first_lane_err is None:
            outcome.first_lane_err = grp_first_err
        outcome.merged.extend(grp_merged)
        outcome.all_ok = outcome.all_ok and grp_ok
        outcome.case_verdicts.update(_case_verdicts_of(ran, leaks=grp_leaks))
        _record_group_unverified(
            GroupUnverifiedRecord(
                ws=ws,
                group_cases=group_cases,
                ran=ran,
                missing=missing,
                probe_label=_probe_note,
            ),
            outcome.unverified,
            outcome.unverified_cases,
        )
        if ran:
            outcome.rank_verdicts[str(ws)] = _fold_rank_verdicts(ws, ran)
    return outcome, None


def _project_unverified(outcome: CampaignOutcome) -> dict:
    """ws-level projection for the O5/finalize UNVERIFIED channel: a ws is
    reported when ANY of its cases went unverified (full groups carry the
    gate's placeholder shape; partial groups point at unverified_cases)."""
    unv_projection: dict[str, dict] = dict(outcome.unverified)
    for _cname, ph in outcome.unverified_cases.items():
        wstr = str(ph["world_size"])
        if wstr not in unv_projection:
            unv_projection[wstr] = {
                "status": "UNVERIFIED",
                "reason": "card_shortage",
                "detail": (
                    f"partial coverage at world_size={ph['world_size']}: "
                    f"case(s) unverified (see mc2.unverified_cases)"
                ),
                "probe": ph["probe"],
            }
    return unv_projection


def _annotate_perf_gaps(perf_agg, outcome: CampaignOutcome, by_ws) -> None:
    """Name the cases missing from the perf aggregate (card-short and
    crashed-mid-measure) instead of leaving them silently absent."""
    if perf_agg is not None and (outcome.unverified or outcome.unverified_cases):
        # Card-short cases contribute no ctx.perf rows; name them explicitly so
        # the aggregate shows the coverage gap instead of a silently
        # missing case.
        unv_names = set(outcome.unverified_cases)
        for wstr in outcome.unverified:
            for c in by_ws.get(int(wstr), []):
                unv_names.add(c["name"])
        perf_agg["unverified_cases"] = sorted(unv_names)
    if perf_agg is not None:
        # Same for cases whose rank crashed mid-measure (synthetic ERROR):
        # the ctx.perf rows are missing by failure, not by card shortage.
        err_names = sorted(
            c
            for c, cv in outcome.case_verdicts.items()
            if "ERROR" in (cv.get("ranks") or {}).values()
        )
        if err_names:
            perf_agg["error_cases"] = err_names


def _log_measured_failure(title: str, overall: dict, details) -> None:
    """Measured-FAIL report (single group and campaign variants share it):
    the aggregate verdict IS the measurement — phase_o5 reconciles it
    against the worker's claim (VERIFIED on honest PARTIAL match, MISMATCH
    on overclaim; a claimed crash matches a measured ERROR), exactly like
    ssh_runner's FAIL-count path. runner_error stays reserved for global
    could-not-execute refusals. verification.json is NOT emitted — a FAIL
    measurement must not overwrite the worker-authored claimed artifact
    (emit is the ALL-rank-PASS GAP-1 contract only)."""
    log.error(
        f"[multirank_runner] {title} — "
        f"{' | '.join(details)}; returning measured verdict "
        f"(status={overall['status']} {overall['tier1_pass']}/"
        f"{overall['total']}) for O5 reconciliation. "
        f"See workspace/.run/"
    )


def _coverage_refusal(outcome: CampaignOutcome, feasible, skipped, lanes, details):
    """Loud refusals before any verdict: PARTIAL coverage under explicit
    lanes, or nothing could run at all. None = proceed."""
    if skipped:
        return _measured(
            runner_error=(
                f"multirank_runner.run_all_groups: PARTIAL coverage — ran world_sizes "
                f"{feasible} ({' | '.join(details)}), but declared world_sizes "
                f"{skipped} are UNVERIFIED (need {max(skipped)} lanes, have "
                f"{len(lanes)}). Declared cases must not silently drop out of the "
                f"campaign: provide more lanes or remove the ws cases from "
                f"spec.py."
            )
        )
    if not outcome.merged:
        return _measured(
            runner_error=(
                f"multirank_runner.run_all_groups: no case could run — lane "
                f"auto-allocation failed for every case (first: "
                f"{outcome.first_lane_err}). Declared case groups are never degraded or "
                f"silently dropped."
            )
        )
    return None


def _report_campaign_verdict(
    ctx: CampaignContext,
    verdict: CampaignVerdict,
    outcome: CampaignOutcome,
    filter_ws,
    details,
) -> None:
    """Report the campaign verdict: filtered one-group diagnostic log, the
    ALL-rank-PASS artifact emit, or the measured-FAIL log for O5
    reconciliation (verification.json is the GAP-1 contract — never written
    on a FAIL measurement)."""
    if outcome.all_ok and filter_ws is not None:
        # A filtered one-group run is a diagnostic subset, never the campaign:
        # it must NOT overwrite the authoritative verification.json (whose
        # claim comes from full campaigns only) with one-group data. The
        # verdict is still returned in MeasuredResult / printed.
        log.info(
            f"[multirank_runner] filter_ws={filter_ws}: group verdict "
            f"{verdict.overall['status']} {verdict.overall['tier1_pass']}/"
            f"{verdict.overall['total']} "
            f"(verification.json intentionally untouched)"
        )
    elif outcome.all_ok:
        _emit_all_pass_artifact(ctx, verdict, outcome)
    elif not ctx.perf:
        # measured-FAIL: every case ends in a measured outcome — PASS/FAIL
        # verdicts from ranks that produced summaries, synthetic ERROR
        # entries for ranks that did not (crash / device hang / timeout).
        # This IS the measurement — return it so phase_o5 reconciles counts
        # against the worker's claim (VERIFIED on honest PARTIAL match,
        # MISMATCH on overclaim). runner_error stays reserved for global
        # could-not-execute refusals and PARTIAL coverage (above).
        # verification.json is intentionally NOT emitted here (emit is the
        # ALL-rank-PASS GAP-1 contract; a FAIL measurement must not overwrite
        # the worker-authored claimed artifact).
        log.error(
            f"[multirank_runner] measured-FAIL across groups — "
            f"{' | '.join(details)}; returning measured verdict "
            f"(status={verdict.overall['status']} "
            f"{verdict.overall['tier1_pass']}/{verdict.overall['total']}) "
            f"for O5 reconciliation. See ctx.workspace/.run/"
        )


def _emit_all_pass_artifact(
    ctx: CampaignContext, verdict: CampaignVerdict, outcome: CampaignOutcome
) -> None:
    """Emit verification.json for an ALL-rank-PASS campaign (GAP-1)."""
    multirank_block = {
        "world_sizes": verdict.declared_ws,
        "cases": [
            {"name": c["name"], "world_size": c["world_size"]} for c in verdict.cases
        ],
        "rank_verdicts": outcome.rank_verdicts,
    }
    if outcome.unverified:
        multirank_block["unverified"] = outcome.unverified
    if outcome.unverified_cases:
        multirank_block["unverified_cases"] = outcome.unverified_cases
    payload = VerificationPayload(
        overall=verdict.overall,
        pass_a=verdict.pass_a,
        rank_summaries=outcome.merged,
        determinism=verdict.determinism,
        multirank_block=multirank_block,
        perf=verdict.perf_agg,
        perf_only=ctx.perf,
    )
    _emit_verification_json(ctx.workspace, payload)


def _run_only_probe_lanes(workspace: Path, remote, env):
    """Probe the largest declared group's idle cards for the run-only smoke
    path; None = skip (nothing declared / probe failed / no cards)."""
    declared = _golden_world_sizes(workspace)
    if not declared:
        log.info("[multirank_runner] run_only: no declared world_sizes — skipped")
        return None
    if remote is not None:
        lanes, lane_err = _pick_idle_remote(remote, max(declared))
    else:
        import npu_probe

        if env is None:
            try:
                env = npu_probe.ProbeEnv.from_env_file()
            except Exception:
                env = None
        lanes, lane_err = npu_probe.pick_idle(env, max(declared))
    if lane_err:
        log.error(
            f"[multirank_runner] run_only: lane auto-allocation failed: {lane_err}"
        )
        return None
    return lanes or None


def _run_only_launch_cases(workspace: Path, op: str, remote, lanes) -> None:
    """One --run-only launch per provisioned case at the lanes' world_size."""
    from . import multirank_phase_o25

    ws = len(lanes)
    for case in [c for c in _campaign_cases(workspace) if c.get("world_size") == ws]:
        _launch_and_collect(
            CampaignContext(workspace=workspace, op=op, remote=remote),
            lanes,
            [
                "--ref",
                f"golden/{case['file']}",
                "--filter-case",
                case["name"],
                "--run-only",
            ],
            case_slug=multirank_phase_o25.case_slug(case["name"]),
        )


def run_only_mode(
    workspace: Path, op: str, lanes: "list[int] | None" = None, env=None
) -> None:
    """Launch multirank_verify.py --run-only per case across lanes: run kernel, skip
    golden compare. Diagnostic (no verdict aggregation / no verification.json)
    — for confirming the kernel runs end-to-end (comm + compute, finite
    output) without measuring precision. One launch per case at the chosen
    world_size (per-case isolation, same as the measured path); the lanes are
    probed once for the group (a smoke check, not a measurement).

    lanes=None (default): probe for the largest declared world_size's idle
    card set (npu_probe), launch that group's cases, then confirm the cards
    are clean.
    """
    workspace = Path(workspace).resolve()
    remote = _resolve_remote(op)
    if remote is not None:
        stage_err = _remote_stage(remote, workspace, op)
        if stage_err is not None:
            raise RuntimeError(f"run_only: remote staging failed: {stage_err}")
    if lanes is None:
        lanes = _run_only_probe_lanes(workspace, remote, env)
    if not lanes:
        return
    ws = len(lanes)
    if ws == 1:
        return
    declared_ws = _golden_world_sizes(workspace)
    if declared_ws and ws not in declared_ws:
        log.info(
            f"[multirank_runner] run_only: len(lanes)={ws} matches no declared case "
            f"world_size {declared_ws} — skipped"
        )
        return
    if not _CANONICAL_VERIFY.is_file():
        return
    _run_only_launch_cases(workspace, op, remote, lanes)
