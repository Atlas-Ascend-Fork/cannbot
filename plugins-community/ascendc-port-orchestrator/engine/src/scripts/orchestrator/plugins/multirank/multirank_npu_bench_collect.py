# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""NPU-side golden collector for the npubench truth tier.

Executed as a SUBPROCESS (local: Popen via multirank_endpoint.run_collector;
remote: the ssh primitive once wired) at provision time. The orchestrator
process NEVER imports torch_npu; a crash or hang in the reference
implementation therefore cannot poison the orchestrator, and the NPU
context dies with this process.

CLI: multirank_npu_bench_collect.py <spec.py> <input.pt> <output.pt>
    [--rank N] [--wrapper WRAPPER]

Two input modes, selected by the spec's ``input_mode``:

* ``derived`` (spec-authored shard/expected): the caller CPU-materializes
  the full inputs (deterministic seed, constrain applied); this process
  moves them to NPU, runs every rank's shard/expected there plus the
  canonical single-process view, and writes the outputs back as CPU
  tensors.
  input.pt  = {"idx", "name", "case", "world_size", "profile",
               "full_inputs": {name: CPU tensor}}   # constrain already applied

* ``task_generated`` (KernelBench task form): inputs come from the task's
  ``get_input_groups(rank=..., world_size=...)`` generator executed here —
  the harness materializes nothing. Each rank builds its own
  ``Model(*get_init_inputs(rank=..., world_size=...))`` instance. When the
  task declares ``NEEDS_EP_COMM``, one subprocess per rank is spawned (one
  NPU each, live HCCL group, hcomm handle extracted and passed to
  ``forward`` as the trailing ``comm`` keyword); otherwise ranks run
  sequentially in this process.
  input.pt  = {"idx", "name", "world_size", "mode": "task"}

output.pt (both modes) = {"kernel_input_order": [str],
             "per_rank": {str(rank): {"inputs": {...}, "outputs": {...}}},  # CPU
             "canonical_outputs": {name: CPU tensor}}                       # CPU
"""

from __future__ import annotations

import importlib.util
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

log = logging.getLogger(__name__)

_RANK_TIMEOUT = 3600


def _load_spec(spec_path: Path):
    """Load the spec module from exact bytes (same loader semantics as the
    provision-side _load_spec)."""
    mod = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(
            f"_spec_{abs(hash(str(spec_path)))}", loader=None
        )
    )
    mod.__file__ = str(spec_path)
    code = compile(spec_path.read_bytes(), str(spec_path), "exec")
    exec(code, mod.__dict__)
    return mod


def _to_cpu(value):
    return value.cpu() if hasattr(value, "cpu") else value


def _split_args_by_decl(inputs_decl: list, group: list) -> tuple[dict, list]:
    """Map a positional argument group onto the sidecar declaration:
    returns ({tensor_name: value}, [all positional values]) — the tensor
    subset keyed by declared name (kernel-input order), everything kept
    positionally for the forward call."""
    named = {}
    pos = 0
    for decl in inputs_decl:
        if not isinstance(decl, dict):
            pos += 1
            continue
        if decl.get("type") == "tensor" and pos < len(group):
            named[decl.get("name", f"input{pos}")] = group[pos]
        pos += 1
    return named, list(group)


def _run_rank_task(torch, spec_mod, payload, rank: int, comm=None):
    """One rank of the task-generated mode: build this rank's Model via its
    init inputs, generate this rank's inputs, run the reference forward.
    Returns ({inputs}, {outputs}) — device placement stays the task's
    responsibility (get_input_groups/Model own it)."""
    spec = spec_mod.SPEC
    ws = int(payload["world_size"])
    init_args = spec_mod.get_init_inputs(rank=rank, world_size=ws)
    model = spec_mod.Model(*init_args)
    if hasattr(model, "npu"):
        model = model.npu()
    group = spec_mod.get_input_groups(rank=rank, world_size=ws)
    named, pos_args = _split_args_by_decl(spec["inputs"], group)
    if comm is not None:
        outputs = model(*pos_args, comm=comm)
    else:
        outputs = model(*pos_args)
    if isinstance(outputs, (tuple, list)):
        outs = {f"out{i}": v for i, v in enumerate(outputs)}
    elif isinstance(outputs, dict):
        outs = outputs
    else:
        outs = {"out0": outputs}
    return {k: _to_cpu(v) for k, v in named.items()}, {
        k: _to_cpu(v) for k, v in outs.items()
    }


def _collect_task_sequential(torch, spec_mod, payload, out_path) -> int:
    spec = spec_mod.SPEC
    per_rank: dict[str, dict] = {}
    order = list(spec.get("kernel_input_order") or [])
    for r in range(int(payload["world_size"])):
        named, outs = _run_rank_task(torch, spec_mod, payload, r)
        if not order:
            order = list(named.keys())
        per_rank[str(r)] = {"inputs": named, "outputs": outs}
    torch.save(
        {
            "kernel_input_order": order,
            "per_rank": per_rank,
            "canonical_outputs": dict(per_rank.get("0", {}).get("outputs", {})),
        },
        out_path,
    )
    return 0


@dataclass
class RankTaskSpec:
    """Per-rank collector subprocess inputs (rank re-entry via argv)."""

    me: Path
    spec_path: Path
    in_path: Path
    out_file: Path
    rank: int
    wrapper_path: "object | None" = None


def _run_rank_task_process(task: RankTaskSpec) -> int:
    """Per-rank re-entry (spawned by _collect_task_multiproc): pin to one
    NPU, join the HCCL group, extract the hcomm handle, run the rank."""
    import torch
    import torch_npu  # noqa: F401 — registers the npu backend
    import torch.distributed as dist

    _, spec_path, in_path = task.me, task.spec_path, task.in_path
    out_file, rank, wrapper_path = task.out_file, task.rank, task.wrapper_path
    if wrapper_path is not None:
        # The a3_live tier forwards its source-operator wrapper here, but the
        # wrapper execution body (run(rank_inputs, rank, world_size, comm))
        # is not wired in this collector yet — executing the task Model
        # instead would silently measure the WRONG reference. Fail loud
        # until the a3_live collection driver lands.
        log.error(
            f"collector rank subprocess received --wrapper {wrapper_path} "
            f"but a3_live wrapper execution is not wired (npubench task "
            f"mode only)"
        )
        return 6
    payload = torch.load(in_path, weights_only=False)
    spec_mod = _load_spec(spec_path)
    ws = int(payload["world_size"])

    os.environ.setdefault("MASTER_ADDR", "127.0.0.1")
    os.environ.setdefault("MASTER_PORT", str(29700 + (int(payload["idx"]) % 200) * 10))
    torch.npu.set_device(rank)
    dist.init_process_group(
        "hccl", rank=rank, world_size=ws, device_id=torch.device(f"npu:{rank}")
    )
    ep_group = dist.new_group(backend="hccl", ranks=list(range(ws)))
    hcomm = getattr(ep_group, "_get_backend")(torch.device("npu")).get_hccl_comm_name(
        rank
    )

    named, outs = _run_rank_task(
        torch,
        spec_mod,
        payload,
        rank,
        comm=SimpleNamespace(hcomm_info=hcomm, rank=rank, world_size=ws, device=rank),
    )
    dist.destroy_process_group()
    torch.save({"rank": rank, "inputs": named, "outputs": outs}, out_file)
    # torch_npu's atexit/watchdog teardown can hang after a rank's HCCL work
    # (joining comm threads stuck in sched_wait_event) while the parent waits
    # on this process; the output is already durable — flush and hard-exit
    # to skip that teardown entirely (fixes post-save hangs).
    sys.stdout.flush()
    sys.stderr.flush()
    getattr(os, "_exit")(0)
    return 0  # unreachable: os._exit never returns (keeps return style uniform)


def _resolve_lanes(ws: int) -> "tuple[list[int] | None, str | None]":
    """Shared card-group lanes for one collection world_size.

    Priority: (1) MULTIRANK_LANES env — the explicit override AND the
    injection channel the parent process uses on remote endpoints, where
    this subprocess cannot import npu_probe; (2) npu_probe.pick_idle(n=ws)
    when importable (local exec, engine PYTHONPATH reachable); (3) None —
    the caller falls back to the legacy per-rank single-card mask with a
    stderr warning. Sharing ONE mask across all rank subprocesses follows
    the multirank_runner convention: ASCEND_RT_VISIBLE_DEVICES renumbers
    the visible set from 0, so rank r addresses logical r inside the group
    (a per-rank mask of str(r) leaves only logical 0 — set_device(r>0)
    would be out of range on ANY host).
    """
    env_lanes = os.environ.get("MULTIRANK_LANES", "").strip()
    if env_lanes:
        try:
            lanes = [int(x) for x in env_lanes.split(",") if x.strip()]
        except ValueError:
            return None, f"MULTIRANK_LANES={env_lanes!r} is not an int list"
        if len(lanes) < ws:
            return None, (
                f"MULTIRANK_LANES has {len(lanes)} lane(s) but "
                f"world_size={ws} needs {ws}"
            )
        return lanes, None
    try:
        import npu_probe
    except ImportError:
        return None, "npu_probe not importable in this subprocess"
    lanes, err = npu_probe.pick_idle(None, ws)
    if err is not None:
        return None, err
    return lanes, None


def _spawn_collect_ranks(me: Path, spec_path: Path, payload, lanes, stub: Path) -> list:
    """One subprocess per rank; returns [(rank, proc, logf, rank_out)].

    ALL rank subprocesses share the lane-group mask (same convention as
    multirank_runner: rank r = logical r inside the visible group). The
    legacy per-rank str(r) fallback keeps old behavior when no lanes could
    be resolved (warned by the caller)."""
    procs = []
    in_path = Path(payload["_in_path"])
    ws = int(payload["world_size"])
    try:
        for r in range(ws):
            rank_out = f"{stub}{r}"
            env = dict(os.environ)
            env["ASCEND_RT_VISIBLE_DEVICES"] = (
                ",".join(str(x) for x in lanes) if lanes is not None else str(r)
            )
            logf = open(f"{stub}{r}.log", "w")
            cmd = [
                sys.executable,
                str(me),
                str(spec_path),
                str(in_path),
                str(rank_out),
                "--rank",
                str(r),
            ]
            if payload.get("wrapper_path"):
                cmd += ["--wrapper", str(payload["wrapper_path"])]
            procs.append(
                (
                    r,
                    subprocess.Popen(
                        cmd, env=env, stdout=logf, stderr=subprocess.STDOUT
                    ),
                    logf,
                    rank_out,
                )
            )
        return procs
    except BaseException:
        # Partial-spawn failure: kill what was spawned, close what was opened.
        for _r, p, logf, _out in procs:
            p.kill()
            logf.close()
        raise


def _wait_collect_ranks(procs: list, stub: Path, ws: int) -> int:
    """Wait every rank out (kill the rest on the first failure); 0, or 5.

    Keep the report lean: no tail echo (torch dispatcher preamble easily
    dwarfs it) — name the on-disk rank logs for post-mortem instead. The
    phase keeps this scratch dir alive on failure."""
    failed = None
    for r, p, logf, rank_out in procs:
        try:
            rc = p.wait(timeout=_RANK_TIMEOUT)
        except subprocess.TimeoutExpired:
            p.kill()
            rc = -1
        logf.close()
        if rc != 0:
            failed = (r, rc, rank_out)
            break
    if failed is None:
        return 0
    for _r, p, logf, _ in procs:
        if p.poll() is None:
            p.kill()
        logf.close()
    log_dir = Path(f"{stub}{failed[0]}.log").resolve().parent
    log.error(
        f"task rank {failed[0]} failed rc={failed[1]}; full rank "
        f"logs kept under: {log_dir} "
        f"({stub.name}<r>.log for r in 0..{ws - 1})"
    )
    return 5


def _merge_rank_records(torch, spec_mod, stub: Path, ws: int, out_path) -> None:
    """Fold the per-rank output records into the collector output.pt shape."""
    per_rank: dict[str, dict] = {}
    order = list(spec_mod.SPEC.get("kernel_input_order") or [])
    for r in range(ws):
        rec = torch.load(f"{stub}{r}", weights_only=False)
        if not order:
            order = list(rec["inputs"].keys())
        per_rank[str(r)] = {"inputs": rec["inputs"], "outputs": rec["outputs"]}
    torch.save(
        {
            "kernel_input_order": order,
            "per_rank": per_rank,
            "canonical_outputs": dict(per_rank.get("0", {}).get("outputs", {})),
        },
        out_path,
    )


def _collect_task_multiproc(torch, me: Path, spec_path: Path, payload, out_path) -> int:
    spec_mod = _load_spec(spec_path)
    ws = int(payload["world_size"])
    lanes, lane_err = _resolve_lanes(ws)
    if lanes is None:
        log.error(
            f"[collector] WARNING: shared-lane resolution failed "
            f"({lane_err}); falling back to the legacy per-rank "
            f"single-card mask (str(rank) + set_device(rank)) — CANN "
            f"mask semantics renumber from 0, so ranks > 0 will fail "
            f"on any host"
        )
    stub = out_path.with_suffix(".rank")
    procs = _spawn_collect_ranks(me, spec_path, payload, lanes, stub)
    wait_rc = _wait_collect_ranks(procs, stub, ws)
    if wait_rc != 0:
        return wait_rc
    _merge_rank_records(torch, spec_mod, stub, ws, out_path)
    return 0


def _parse_cli(argv: list) -> "tuple[list, int | None, str | None]":
    """Strip the optional --rank/--wrapper flags; returns
    (positional_args, rank, wrapper)."""
    rank_arg = None
    if "--rank" in argv:
        i = argv.index("--rank")
        rank_arg = int(argv[i + 1])
        _j = i + 2
        del argv[i:_j]
    wrapper_arg = None
    if "--wrapper" in argv:
        i = argv.index("--wrapper")
        wrapper_arg = argv[i + 1]
        _j = i + 2
        del argv[i:_j]
    return argv, rank_arg, wrapper_arg


def main() -> int:
    argv, rank_arg, wrapper_arg = _parse_cli(list(sys.argv[1:]))
    if len(argv) != 3:
        log.error(
            "usage: multirank_npu_bench_collect.py <spec.py> <input.pt> "
            "<output.pt> [--rank N] [--wrapper WRAPPER]"
        )
        return 2
    spec_path, in_path, out_path = (Path(a) for a in argv)
    try:
        import torch
        import torch_npu  # noqa: F401 — registers the npu backend (loud fail without)
    except Exception as exc:
        log.error(
            f"collector requires torch + torch_npu on the candidate endpoint: {exc!r}"
        )
        return 3

    if rank_arg is not None:
        return _run_rank_task_process(
            RankTaskSpec(
                me=Path(__file__),
                spec_path=spec_path,
                in_path=in_path,
                out_file=out_path,
                rank=rank_arg,
                wrapper_path=wrapper_arg,
            )
        )

    payload = torch.load(in_path, weights_only=False)
    if wrapper_arg is not None:
        payload["wrapper_path"] = wrapper_arg
    mod = _load_spec(spec_path)
    spec = mod.SPEC

    if spec.get("input_mode") != "task_generated":
        log.error(
            "collector serves the task-generated spec form only "
            "(the derived shard/expected form is retired)"
        )
        return 4
    if spec.get("needs_ep_comm"):
        payload["_in_path"] = str(in_path)
        return _collect_task_multiproc(
            torch, Path(__file__), spec_path, payload, out_path
        )
    return _collect_task_sequential(torch, mod, payload, out_path)


if __name__ == "__main__":
    sys.exit(main())
