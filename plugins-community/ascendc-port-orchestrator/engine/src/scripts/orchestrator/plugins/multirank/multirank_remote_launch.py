# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Remote per-case rank launcher for multirank verify/perf (endpoint path).

Staged to the CANDIDATE endpoint's staging area next to the staged op
workspace, and executed there by multirank_runner's remote branch: it is the
remote twin of _spawn_rank_procs/_wait_rank_procs — one subprocess per rank,
all sharing the SAME full ordered ASCEND_RT_VISIBLE_DEVICES mask (CANN
renumbers the ordered mask to local indices, so verify-side
set_device(rank) binds rank r to physical dev_id r), running the staged
canonical multirank_verify.py with the same opp env the local path injects.

Exit code is ALWAYS 0 once the ranks were launched (a rank-level failure is
rank DATA, not a launcher failure): each rank's stdout lands in
<ws>/.run/<case_slug>/rank_<r>.log and its exit code in rank_<r>.rc — the
engine side pulls both and applies the same parse/synthetic-ERROR semantics
as the local path (no summary = no measurement = ERROR entry).

CLI: multirank_remote_launch.py <verify_py> <ws_dir> <case_slug> \
        <world_size> <master_port> <dev_id_0> [<dev_id_1> ...] -- \
        <extra verify argv...>            (--run-only/--perf/--ref/--filter-case)
"""

from __future__ import annotations

import os
import logging
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_RANK_TIMEOUT = 3600


def _opp_env(ws_dir: Path) -> dict:
    """Same opp probing order as multirank_runner._activate_opp_env, on the
    endpoint-side path layout (the staged workspace keeps the local
    relative layout, so the candidates are the same relative joins)."""
    e = dict(os.environ)
    customize = ".install", "packages", "vendors", "customize"
    op = ws_dir.name
    cands = [
        ws_dir / f"prj-{op}",  # mandated nest (prj-<op>/.install)
        ws_dir,  # legacy single-layer (workspace/.install)
        ws_dir / op,  # legacy nested workspace/<op>/<op>
    ]
    for base in cands:
        opp = base.joinpath(*customize)
        if (opp / "op_api" / "lib").is_dir():
            e["ASCEND_CUSTOM_OPP_PATH"] = str(opp)
            lib = str(opp / "op_api" / "lib")
            e["LD_LIBRARY_PATH"] = lib + ":" + e.get("LD_LIBRARY_PATH", "")
            break
    return e


class _RankLaunchSpec(NamedTuple):
    """Everything one remote-launch spawn needs besides its log dir."""

    verify_py: Path
    ws_dir: Path
    ws: int
    port_s: str
    extra: list
    base_env: dict


def _spawn_rank_processes(spec: _RankLaunchSpec, log_dir: Path) -> tuple:
    """Spawn one verify process per rank; returns ([(rank, proc, logf)], logfs).

    The caller owns every rank log's lifetime: _collect_rank_processes closes
    each logf (idempotent via the closed flag) and its finally pass closes
    anything the per-rank loop left open, so open/close stay paired even when
    a rank wait raises mid-loop."""
    procs = []
    logfs = []
    try:
        for r in range(spec.ws):
            env = dict(spec.base_env)
            env["MASTER_ADDR"] = "127.0.0.1"
            env["MASTER_PORT"] = str(spec.port_s)
            cmd = [
                sys.executable,
                str(spec.verify_py),
                str(spec.ws_dir),
                "--rank",
                str(r),
                "--world-size",
                str(spec.ws),
                "--master-addr",
                "127.0.0.1",
                "--master-port",
                str(spec.port_s),
                *spec.extra,
            ]
            logf = open(log_dir / f"rank_{r}.log", "w")
            logfs.append(logf)
            procs.append(
                (
                    r,
                    subprocess.Popen(
                        cmd,
                        env=env,
                        stdout=logf,
                        stderr=subprocess.STDOUT,
                        cwd=str(spec.ws_dir),
                    ),
                    logf,
                )
            )
        return procs, logfs
    except BaseException:
        # Partial-spawn failure: close what this function opened before the
        # exception escapes (a Popen whose logf dies mid-loop, etc.).
        for logf in logfs:
            logf.close()
        raise


def _wait_rank_exit(proc) -> int:
    """Wait one rank out; kill on timeout (bounded re-wait)."""
    try:
        return proc.wait(timeout=_RANK_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            pass
        return -1


def _collect_rank_processes(procs, logfs, log_dir) -> None:
    """Wait each rank out (kill on timeout) and record its exit code."""
    try:
        for r, p, logf in procs:
            rc = _wait_rank_exit(p)
            logf.close()
            (log_dir / f"rank_{r}.rc").write_text(str(rc) + "\n")
    finally:
        # Idempotent close for logs whose rank never reached logf.close().
        for logf in logfs:
            if not logf.closed:
                logf.close()


def main() -> int:
    argv = sys.argv[1:]
    if "--" not in argv:
        log.error(
            "usage: multirank_remote_launch.py <verify_py> <ws_dir> "
            "<case_slug> <world_size> <master_port> <dev...> -- <extra>"
        )
        return 2
    sep = argv.index("--")
    _s1 = sep + 1
    head, extra = argv[:sep], argv[_s1:]
    verify_py, ws_dir_s, case_slug, ws_s, port_s = (
        head[0],
        head[1],
        head[2],
        head[3],
        head[4],
    )
    dev_ids = head[5:]
    ws_dir = Path(ws_dir_s)
    ws = int(ws_s)
    if len(dev_ids) < ws:
        log.error(
            f"remote launcher: {len(dev_ids)} device ids for world_size="
            f"{ws} — insufficient cards fail LOUD"
        )
        return 5

    log_dir = ws_dir / ".run" / case_slug
    log_dir.mkdir(parents=True, exist_ok=True)
    for f in log_dir.glob("rank_*"):
        f.unlink()

    base_env = _opp_env(ws_dir)
    # Shared full ordered mask: CANN renumbers it to local 0..ws-1 inside
    # each rank process, so verify's set_device(rank) binds rank r to the
    # physical dev_ids[r] — a per-rank single-device mask would renumber
    # that one card to npu:0 and break set_device for every rank > 0.
    base_env["ASCEND_RT_VISIBLE_DEVICES"] = ",".join(str(x) for x in dev_ids)
    procs, logfs = _spawn_rank_processes(
        _RankLaunchSpec(
            verify_py=verify_py,
            ws_dir=ws_dir,
            ws=ws,
            port_s=port_s,
            extra=extra,
            base_env=base_env,
        ),
        log_dir,
    )
    _collect_rank_processes(procs, logfs, log_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
