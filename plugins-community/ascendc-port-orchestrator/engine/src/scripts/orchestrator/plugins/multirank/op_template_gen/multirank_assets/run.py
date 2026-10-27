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

"""multirank op unified entry — run from prj-<op>/:
    python3 run.py build [-j N] [--no-filter-warnings]
    python3 run.py verify [--run-only] [--perf]
    python3 run.py provision

Subcommands (thin wrappers over harness — complex logic stays shared):
  build     -> src/scripts/orchestrator/plugins/multirank/patches/multirank_build.py
                (autogen + kernel binary + install + py_ext)
  verify    -> src/scripts/orchestrator/plugins/multirank/multirank_runner (multi-rank, one launch per
               declared case world_size group; --run-only = run kernel, skip
               golden compare — diagnostic)
  provision -> src/scripts/orchestrator/plugins/multirank/multirank_phase_o25.provision_mc2_reference
               (CPU sim, gen golden; world_size comes from each case's own
               declaration in spec.py — never from a CLI flag)
"""

import argparse
import logging
import json  # noqa: F401
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

PRJ = Path(__file__).resolve().parent  # workspace/<op>/prj-<op>/
ROOT = PRJ.parent  # workspace/<op>/


class ProjectRootNotFound(RuntimeError):
    """The harness tree anchor file is missing (run.py is outside it)."""


def _project_root():
    for anc in PRJ.parents:
        if (
            anc
            / "src"
            / "scripts"
            / "orchestrator"
            / "plugins"
            / "multirank"
            / "patches"
            / "multirank_build.py"
        ).is_file():
            return anc
    raise ProjectRootNotFound(
        "project root (containing src/scripts/orchestrator/plugins/"
        "multirank/patches/multirank_build.py) not found"
    )


def cmd_build(args):
    multirank_build = (
        _project_root()
        / "src"
        / "scripts"
        / "orchestrator"
        / "plugins"
        / "multirank"
        / "patches"
        / "multirank_build.py"
    )
    cmd = [sys.executable, str(multirank_build), "."]
    cmd += ["-j", str(args.jobs)]
    if args.no_filter_warnings:
        cmd += ["--no-filter-warnings"]
    if args.dump:
        cmd += ["--dump"]
    subprocess.run(cmd, cwd=str(PRJ), check=True)


def cmd_verify(args):
    orch = _project_root() / "src" / "scripts" / "orchestrator"
    sys.path.insert(0, str(orch))
    if getattr(args, "timeout", None) is not None:
        os.environ["MULTIRANK_RANK_TIMEOUT"] = str(args.timeout)
    from plugins.multirank import multirank_runner  # noqa: E402

    op = args.op or PRJ.name.removeprefix("prj-")
    # Every verify path AUTO-ALLOCATES from the live idle probe (npu_probe):
    # per ws group, in ascending order — probe right before the group's
    # launch, confirm the cards are process-clean right after. There is no
    # manual lane flag: cards always come from the probe.
    # --filter-ws N: run ONLY the world_size=N group (single-group iteration;
    # verdict printed but verification.json intentionally untouched).
    if args.run_only:
        if args.filter_ws is not None:
            log.info("[verify] --run-only and --filter-ws are mutually exclusive")
            return
        multirank_runner.run_only_mode(ROOT, op, None)
        return
    result = multirank_runner.run_all_groups(
        multirank_runner.CampaignContext(workspace=ROOT, op=op, perf=args.perf),
        None,
        filter_ws=args.filter_ws,
    )
    if result.runner_error:
        log.error(f"[verify] runner_error: {result.runner_error}")
    if result.perf:
        _p = result.perf
        log.info(
            f"[verify] perf: ratio={_p.get('ratio')} "
            f"candidate_us={_p.get('candidate_us')} "
            f"baseline_us={_p.get('baseline_us')} "
            f"(full block in verification.json.performance)"
        )
    if result.pass_a:
        log.info(
            f"[verify] status={result.pass_a.get('status')} "
            f"tier1_pass={result.pass_a.get('tier1_pass')} "
            f"total={result.pass_a.get('total')}"
        )


def cmd_provision(args):
    orch = _project_root() / "src" / "scripts" / "orchestrator"
    sys.path.insert(0, str(orch))
    from plugins.multirank.multirank_phase_o25 import provision_mc2_reference  # noqa: E402

    op = args.op or PRJ.name.removeprefix("prj-")
    report = provision_mc2_reference(ROOT, op=op)
    log.info(
        f"[provision] verdict={report.verdict} n_cases={report.n_cases} "
        f"n_ok={report.n_ok} n_skipped={report.n_skipped} "
        f"world_sizes={report.world_sizes}"
    )


def _register_build_cmd(sub):
    """The build subcommand (harness multirank_build.py)."""
    pb = sub.add_parser(
        "build", help="build + install + py_ext (harness multirank_build.py)"
    )
    pb.add_argument("-j", "--jobs", type=int, default=8)
    pb.add_argument(
        "--no-filter-warnings",
        action="store_true",
        help="disable build warning filter (show raw output)",
    )
    pb.add_argument(
        "--dump",
        action="store_true",
        help="enable ASCENDC_DUMP debug prints for this build "
        "(recompile; never use for gate/perf runs)",
    )
    pb.set_defaults(fn=cmd_build)


def _register_verify_cmd(sub):
    """The verify subcommand (harness multirank_runner)."""
    pv = sub.add_parser("verify", help="multi-rank verify (harness multirank_runner)")
    pv.add_argument(
        "--run-only",
        action="store_true",
        help="run kernel, skip golden compare (diagnostic: output shape/nan/mean)",
    )
    pv.add_argument(
        "--filter-ws",
        type=int,
        default=None,
        metavar="N",
        help="run ONLY the world_size=N case group (must be "
        "declared in spec.py; single-group iteration — "
        "verification.json intentionally untouched. "
        "Mutually exclusive with --run-only)",
    )
    pv.add_argument(
        "--perf",
        action="store_true",
        help="perf mode: torch_npu.profiler device self-duration "
        "(candidate vs spec perf_baseline if declared); "
        "perf stays N/A without perf_baseline",
    )
    pv.add_argument("--op", default=None, help="op name (default: ROOT dir name)")
    pv.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="per-rank subprocess timeout in seconds (default 600, i.e. "
        "multirank_runner._MULTIRANK_RANK_TIMEOUT; env MULTIRANK_RANK_TIMEOUT "
        "overrides — a hung/deadlocked rank is "
        "SIGKILL'd after this many seconds)",
    )
    pv.set_defaults(fn=cmd_verify)


def _register_provision_cmd(sub):
    """The provision subcommand (truth-tier collector via multirank_phase_o25)."""
    pp = sub.add_parser(
        "provision",
        help="gen golden (truth-tier collector via multirank_phase_o25; "
        "world_size from each case's spec.py declaration)",
    )
    pp.add_argument("--op", default=None, help="op name (default: ROOT dir name)")
    pp.set_defaults(fn=cmd_provision)


def _build_parser():
    """The build/verify/provision subcommand registry."""
    ap = argparse.ArgumentParser(
        description="multirank op unified entry (run from prj-<op>/)"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    _register_build_cmd(sub)
    _register_verify_cmd(sub)
    _register_provision_cmd(sub)
    return ap


def main():
    args = _build_parser().parse_args()
    try:
        args.fn(args)
    except ProjectRootNotFound as exc:
        sys.exit(f"ERROR: {exc}")


if __name__ == "__main__":
    main()
