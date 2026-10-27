# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Command-line entry for the scoped AscendC port orchestrator.

Customer work starts through exactly three modes:

* ``--port-a3-ops`` for the current arch22 to arch35 migration;
* ``--backward`` for backward-operator generation;
* ``--multirank`` for the multirank harness extension (compute +
  collective-communication fusion ops) of the port_a3_to_a5 mode.

Status, resume, planning, and optimization are lifecycle operations over an
already-scoped workspace.  They cannot create a general operator-generation
run; ``run_single_op`` independently enforces the persisted workspace mode.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from logging_config import get_logger

log = get_logger(__name__)

_ORCH_MARKER = "run_single_op"


def _orch():
    """Resolve the live orchestrator module without an import-time cycle."""
    for name in ("orchestrator", "orchestrator.orchestrator", "__main__"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, _ORCH_MARKER):
            return module
    return sys.modules.get("orchestrator") or sys.modules["__main__"]


def _orch_attr(name: str):
    """Resolve a live orchestrator implementation detail for CLI dispatch."""
    return getattr(_orch(), name)


def _normalize_precision_standard(value: str | None) -> int:
    """Publish the explicit precision choice for the arch migration grader."""
    if value is None:
        return 0
    aliases = {"生态": "ecosystem", "商用": "commercial"}
    normalized = aliases.get(value.strip(), value.strip())
    if normalized not in ("ecosystem", "commercial"):
        print(
            "ERROR: --precision-standard must be ecosystem|commercial "
            f"(aliases 生态|商用); got {value!r}"
        )
        return 2
    os.environ["AOG_PRECISION_STANDARD_CLI"] = normalized
    log.info(
        "[orch] --precision-standard=%s -> arch migration grader CLI",
        normalized,
    )
    return 0


# Lifecycle inputs the start-mode conflict checks all exempt (mode input and
# bookkeeping flags shared by the port-a3/multirank branches).
_LIFECYCLE_EXCLUDED = (
    "op",
    "resume",
    "all",
    "dry_run",
    "optimize",
    "workspace",
    "backward",
)


def _conflicts(args, *, excluded: tuple[str, ...]) -> list[str]:
    """Return user-facing names for populated mutually-exclusive arguments."""
    labels = {
        "op": "positional <op>",
        "resume": "--resume",
        "all": "--all",
        "dry_run": "--dry-run",
        "plan": "--plan",
        "status": "--status",
        "optimize": "--optimize",
        "cold_start": "--cold-start",
        "lane": "--lane",
        "extra_lane": "--extra-lane",
        "workspace": "--workspace",
        "bump_cap": "--bump-cap",
        "precision_standard": "--precision-standard",
        "timing": "--timing",
        "port_a3": "--port-a3-ops",
        "backward": "--backward",
        "multirank": "--multirank",
        "reference_source": "--reference-source",
        "npubench_task": "--npubench-task",
        "npubench_root": "--npubench-root",
        "source_kind": "--source-kind",
        "source_arch": "--source-arch",
        "candidate_kind": "--candidate-kind",
    }
    conflicts = []
    for name in excluded:
        value = getattr(args, name, None)
        if value is not None and (name == "lane" or bool(value)):
            conflicts.append(labels[name])
    return conflicts


def _validated_lane(value: int | None) -> tuple[int | None, int]:
    """Resolve the default lane and fail closed outside the detected range."""
    lane = 0 if value is None else value
    max_lane = _orch_attr("_detect_max_lane")()
    if lane < 0 or lane > max_lane:
        print(f"ERROR: --lane must be in range 0..{max_lane}; got {lane}")
        return None, 2
    return lane, 0


def _workspace_identity_matches(value: object, workspace: Path) -> bool:
    """Match a durable workspace identity without following an input alias."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        actual = Path(workspace).resolve(strict=False)
        declared = Path(value).expanduser()
        if declared.is_absolute():
            return declared.resolve(strict=False) == actual
        # Older durable state may persist the scoped directory name rather than
        # an absolute path.  Accept that narrow form and a path relative to the
        # workspace parent; never accept an arbitrary basename from another tree.
        return (
            value == actual.name
            or (actual.parent / declared).resolve(strict=False) == actual
        )
    except (OSError, RuntimeError, ValueError):
        return False


def _persisted_identity_error(op: str, workspace: Path) -> str | None:
    """Return a user-facing error when durable scope identity is contradictory."""
    workspace = Path(workspace)
    if workspace.is_symlink():
        return "workspace must be a real non-symlink directory"
    state_path = workspace / ".opgen_state.json"
    if not state_path.exists():
        return None
    if state_path.is_symlink() or not state_path.is_file():
        return "durable state must be a regular non-symlink file"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return f"durable state is unreadable: {type(exc).__name__}: {exc}"
    if not isinstance(state, Mapping):
        return "durable state must be a JSON object"

    records: list[Mapping] = [state]
    nested = state.get("identity")
    if nested is not None:
        if not isinstance(nested, Mapping):
            return "durable state identity must be an object"
        records.append(nested)
    for record in records:
        if "op" in record:
            declared_op = record.get("op")
            if not isinstance(declared_op, str) or not declared_op.strip():
                return "durable state op identity is malformed"
            if declared_op != op:
                return (
                    "positional op does not match durable state identity: "
                    f"state={declared_op!r}, requested={op!r}"
                )
        if "workspace" in record:
            declared_workspace = record.get("workspace")
            if not _workspace_identity_matches(declared_workspace, workspace):
                return (
                    "workspace does not match durable state identity: "
                    f"state={declared_workspace!r}, resolved={str(workspace)!r}"
                )
    return None


def main() -> int:
    _orch_attr("_refuse_if_detached")()
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        allow_abbrev=False,
        description=(
            "AscendC arch22->arch35 migration, backward-operator generation, "
            "and the multirank harness extension (compute + collective-communication fusion ops)"
        ),
    )
    parser.add_argument(
        "op",
        nargs="?",
        default=None,
        help="existing scoped workspace name (for --resume/--plan/--optimize only)",
    )
    parser.add_argument(
        "--port-a3-ops",
        dest="port_a3",
        type=Path,
        metavar="SOURCE_DIR",
        help=(
            "migrate an arch22 ops-nn operator from the CANN ops repository "
            "(canonical ops-format route)"
        ),
    )
    parser.add_argument(
        "--source-kind",
        choices=(
            "port-aclnn-tilelang2ascendc",
            "port_aclnn_tilelang2ascendc",
        ),
        default=None,
        help=(
            "source layout; omit for the legacy ACLNN ops-nn route; "
            "port-aclnn-tilelang2ascendc selects the TileLang2AscendC custom-op project"
        ),
    )
    parser.add_argument(
        "--source-arch",
        choices=("arch22", "arch35"),
        default=None,
        help=("explicit architecture for TileLang2AscendC project sources (arch35)"),
    )
    parser.add_argument(
        "--candidate-kind",
        choices=("tilelang2ascendc_custom_op",),
        default=None,
        help="required target ABI/project contract for explicit source kinds",
    )
    parser.add_argument(
        "--backward",
        type=Path,
        metavar="FORWARD_SPEC",
        help="generate a backward operator from a differentiable forward spec",
    )
    parser.add_argument(
        "--multirank",
        action="store_true",
        default=False,
        help=(
            "multirank harness extension of the port_a3_to_a5 mode "
            "(compute + collective-communication fusion ops): a STACKING "
            "flag combined with --port-a3-ops <ops-nn-dir> (the REQUIRED "
            "migration source, same constraint as the single-card mode) "
            "and --npubench-task <task.py> (the multi-rank reference "
            "pair: Model + get_input_groups/get_init_inputs accepting "
            "rank/world_size; same-stem sidecar declares per-case "
            "world_size — statically converted to the internal spec). "
            "World size is case-declared; cards are auto-allocated from "
            "the idle-NPU probe, so --lane lists are ignored"
        ),
    )
    reference = parser.add_argument_group("reference provider")
    reference.add_argument(
        "--reference-source",
        choices=("npubench", "a3_live", "cannbench"),
        default=None,
        help=(
            "reference provider, orthogonal to the mode flag. npubench: "
            "reference implementation as truth — with --port-a3-ops a "
            "NPUKernelBench task+sidecar pair; with --multirank the "
            "spec's expected, executed on the target A5 (no source "
            "machine needed). a3_live: explicit live source-side capture "
            "— with --port-a3-ops live A3 capture; with --multirank the "
            "source-side real op on multi-rank source NPUs (the "
            "multirank default). cannbench: reserved"
        ),
    )
    reference.add_argument(
        "--npubench-task",
        type=Path,
        metavar="TASK_PY",
        help="original NPUKernelBench task .py (requires --reference-source npubench)",
    )
    reference.add_argument(
        "--npubench-root",
        type=Path,
        metavar="TASK_ROOT",
        help="optional source-root closure for --npubench-task",
    )

    lifecycle = parser.add_argument_group("lifecycle")
    lifecycle.add_argument("--resume", action="store_true", help="resume scoped state")
    lifecycle.add_argument(
        "--all", action="store_true", help="with --resume, scan all scoped workspaces"
    )
    lifecycle.add_argument(
        "--dry-run", action="store_true", help="with --resume, diagnose only"
    )
    lifecycle.add_argument("--plan", action="store_true", help="show the plan only")
    lifecycle.add_argument(
        "--status", action="store_true", help="show workspace states"
    )
    lifecycle.add_argument(
        "--classify-sha",
        type=Path,
        default=None,
        metavar="WORKSPACE_DIR",
        help=(
            "print the Phase O1.7 source-content SHA256 for a workspace and "
            "exit; the aog-op-classify agent MUST obtain source_sha256 from "
            "this command (single source of truth — file set, 200KB "
            'truncation, b"\\n".join all live in _compute_source_sha256), '
            "never compute it itself"
        ),
    )
    lifecycle.add_argument(
        "--optimize",
        action="store_true",
        help="re-enter optimization for an already verified scoped workspace",
    )
    lifecycle.add_argument(
        "--cold-start",
        action="store_true",
        help=(
            "restart a --port-a3-ops, --backward, or --multirank run after "
            "archiving prior state"
        ),
    )

    parser.add_argument(
        "--lane",
        default=None,
        help=(
            "NPU lane id, or a comma-separated list (default: 0). Multirank "
            "(--multirank): IGNORED — the physical card set is "
            "auto-allocated from the idle-NPU probe (a list only triggers "
            "a warning)"
        ),
    )
    parser.add_argument(
        "--extra-lane",
        action="append",
        type=int,
        default=None,
        metavar="N",
        help="additional assigned NPU lane for npubench precision/performance parallelism",
    )
    parser.add_argument(
        "--workspace", type=Path, help="explicit existing workspace for lifecycle use"
    )
    parser.add_argument(
        "--bump-cap",
        action="append",
        default=None,
        metavar="COUNTER:DELTA",
        help="audited iteration-cap increase for this scoped run",
    )
    parser.add_argument(
        "--precision-standard",
        default=None,
        metavar="STD",
        help="arch migration precision standard: ecosystem or commercial",
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="generate TIMING_REPORT.md from the scoped run event logs",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("ORCH_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="logger threshold",
    )

    args = parser.parse_args()

    from logging_config import setup_run_logger

    setup_run_logger(workspace=None, level=args.log_level)

    # --lane accepts a single id ('3') or a comma list ('0,1') — the list is
    # multirank's physical card-set syntax, but multirank auto-allocates its cards from
    # the idle-NPU probe, so the list only draws a warning in the multirank branch
    # below. Single-card consumers read the primary (first) id via
    # _validated_lane, exactly as before.
    if args.lane is None:
        args.lane_list = []
    else:
        try:
            args.lane_list = [
                int(part) for part in str(args.lane).split(",") if part.strip()
            ]
        except ValueError:
            print(
                f"ERROR: --lane must be an int or comma-separated ints; "
                f"got {args.lane!r}"
            )
            return 2
        if not args.lane_list:
            print("ERROR: --lane produced an empty lane list")
            return 2
        args.lane = args.lane_list[0]

    reference_flags = (
        args.reference_source,
        args.npubench_task,
        args.npubench_root,
        args.source_kind,
        args.source_arch,
        args.candidate_kind,
    )
    reference_flags_present = any(flag is not None for flag in reference_flags)
    if reference_flags_present and args.port_a3 is None and not args.multirank:
        print(
            "ERROR: --reference-source, --npubench-task, and --npubench-root "
            "require --port-a3-ops or --multirank"
        )
        return 2

    # The reference axis is shared by both modes under one vocabulary:
    # npubench (reference implementation as truth) and a3_live (live
    # source-side capture). The multirank reference IS the npubench task —
    # same file pair, same semantics, multi-rank declarations inside.
    if args.multirank:
        if args.reference_source == "cannbench":
            print(
                "ERROR: --reference-source cannbench is reserved and not "
                "available under --multirank; use npubench or a3_live"
            )
            return 2
        if args.npubench_task is None:
            print(
                "ERROR: --multirank requires --npubench-task <task.py> "
                "(the multi-rank reference pair)"
            )
            return 2
        if args.port_a3 is None:
            print(
                "ERROR: --multirank requires --port-a3-ops <ops-nn-dir> "
                "(the migration source operator — same constraint as the "
                "single-card mode)"
            )
            return 2
        if (args.source_kind, args.source_arch, args.candidate_kind) != (
            None,
            None,
            None,
        ):
            print(
                "ERROR: --source-kind/--source-arch/--candidate-kind are "
                "single-card source inputs; multirank takes --port-a3-ops "
                "ops-nn directories only"
            )
            return 2

    if args.status:
        conflicts = _conflicts(
            args,
            excluded=(
                "op",
                "resume",
                "all",
                "dry_run",
                "plan",
                "optimize",
                "cold_start",
                "lane",
                "extra_lane",
                "workspace",
                "bump_cap",
                "precision_standard",
                "timing",
                "port_a3",
                "backward",
                "multirank",
                "reference_source",
                "npubench_task",
                "npubench_root",
                "source_kind",
                "source_arch",
                "candidate_kind",
            ),
        )
        if conflicts:
            print(f"ERROR: --status cannot be combined with: {', '.join(conflicts)}")
            return 2
        return _orch_attr("_cmd_status")()

    if args.classify_sha is not None:
        return _orch_attr("_cmd_classify_sha")(args.classify_sha)

    # Multirank harness extension dispatch (port_a3_to_a5 mode flagged
    # `multirank: true`). Mutually exclusive with the other start modes and
    # positional lifecycle inputs.
    if args.multirank:
        # --port-a3-ops is deliberately NOT in this conflict set: multirank
        # composes with it (the migration source is REQUIRED, same as the
        # single-card mode).
        conflicts = _conflicts(
            args,
            excluded=(*_LIFECYCLE_EXCLUDED, "precision_standard"),
        )
        if conflicts:
            print(f"ERROR: --multirank cannot be combined with: {', '.join(conflicts)}")
            return 2
        # Multirank lanes are AUTO-ALLOCATED from the live idle-NPU probe; a
        # manual comma-list --lane is inert (warn + drop; the primary is kept
        # as the .opgen_state.json bookkeeping lane).
        if len(args.lane_list) > 1:
            print(
                "WARNING: --multirank auto-allocates the physical card set "
                "from the idle-NPU probe (npu_probe); ignoring: "
                f"--lane {args.lane_list}"
            )
        lane, lane_rc = _validated_lane(args.lane)
        if lane_rc:
            return lane_rc
        try:
            cap_bumps = _orch_attr("_parse_bump_caps")(args.bump_cap or [])
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 2
        return _orch_attr("_cmd_multirank")(
            task=args.npubench_task,
            lane=lane,
            plan_only=args.plan,
            cold_start=args.cold_start,
            cap_bumps=cap_bumps,
            timing=args.timing,
            reference_source=args.reference_source,
            port_a3_dir=args.port_a3,
        )

    if args.port_a3 is not None:
        conflicts = _conflicts(args, excluded=_LIFECYCLE_EXCLUDED)
        if conflicts:
            print(
                f"ERROR: --port-a3-ops cannot be combined with: {', '.join(conflicts)}"
            )
            return 2
        lane, lane_rc = _validated_lane(args.lane)
        if lane_rc:
            return lane_rc
        extra_lanes: list[int] = []
        for requested in args.extra_lane or []:
            extra_lane, extra_lane_rc = _validated_lane(requested)
            if extra_lane_rc:
                return extra_lane_rc
            if extra_lane == lane:
                print("ERROR: --extra-lane must differ from --lane")
                return 2
            if extra_lane in extra_lanes:
                print(f"ERROR: duplicate --extra-lane {extra_lane}")
                return 2
            extra_lanes.append(extra_lane)
        precision_rc = _normalize_precision_standard(args.precision_standard)
        if precision_rc:
            return precision_rc
        try:
            cap_bumps = _orch_attr("_parse_bump_caps")(args.bump_cap or [])
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 2
        return _orch_attr("_cmd_port_a3")(
            port_a3_dir=args.port_a3,
            lane=lane,
            plan_only=args.plan,
            cold_start=args.cold_start,
            cap_bumps=cap_bumps,
            timing=args.timing,
            reference_source=args.reference_source,
            npubench_task=args.npubench_task,
            npubench_root=args.npubench_root,
            extra_lanes=extra_lanes,
            source_kind=args.source_kind,
            source_arch=args.source_arch,
            candidate_kind=args.candidate_kind,
        )

    if args.backward is not None:
        conflicts = _conflicts(
            args,
            excluded=(
                "op",
                "resume",
                "all",
                "dry_run",
                "optimize",
                "workspace",
                "port_a3",
                "bump_cap",
                "precision_standard",
            ),
        )
        if conflicts:
            print(f"ERROR: --backward cannot be combined with: {', '.join(conflicts)}")
            return 2
        lane, lane_rc = _validated_lane(args.lane)
        if lane_rc:
            return lane_rc
        return _orch_attr("_cmd_backward")(
            forward_spec=args.backward,
            lane=lane,
            plan_only=args.plan,
            cold_start=args.cold_start,
            timing=args.timing,
        )

    if args.cold_start:
        print(
            "ERROR: --cold-start requires --port-a3-ops, --backward, or --multirank "
            "so mode input is explicit"
        )
        return 2

    if args.resume:
        conflicts = _conflicts(
            args,
            excluded=(
                "optimize",
                "plan",
                "workspace",
                "bump_cap",
                "precision_standard",
                "timing",
            ),
        )
        if args.all and args.op:
            conflicts.append("positional <op> with --all")
        if conflicts:
            print(f"ERROR: --resume cannot be combined with: {', '.join(conflicts)}")
            return 2
        lane, lane_rc = _validated_lane(args.lane)
        if lane_rc:
            return lane_rc
        return _orch_attr("_cmd_resume")(
            op=args.op,
            all_mode=args.all,
            lane=lane,
            dry_run=args.dry_run,
        )

    if args.all or args.dry_run:
        print("ERROR: --all and --dry-run require --resume")
        return 2

    if not args.op:
        parser.print_help()
        return 2

    try:
        workspace = (
            Path(args.workspace)
            if args.workspace is not None
            else Path(_orch_attr("_resolve_workspace")(args.op, backend="ascendc"))
        )
    except Exception as exc:
        print(
            f"ERROR: could not resolve positional workspace for "
            f"{args.op!r}: {type(exc).__name__}: {exc}; "
            "new work must start with --port-a3-ops, --backward, or "
            "--multirank (a positional workspace is lifecycle-only)"
        )
        return 2

    identity_error = _persisted_identity_error(args.op, workspace)
    if identity_error:
        print(f"ERROR: positional workspace rejected: {identity_error}")
        return 2

    if not (args.plan or args.optimize):
        try:
            scoped_mode = _orch_attr("_read_scoped_opgen_mode")(workspace)
        except Exception as exc:
            print(
                "ERROR: could not inspect positional workspace state: "
                f"{type(exc).__name__}: {exc}"
            )
            return 2
        if scoped_mode is None:
            print(
                "ERROR: new work must start with --port-a3-ops, --backward, or "
                "--multirank; a positional workspace is lifecycle-only"
            )
            return 2
        # A positional re-invocation of an existing workspace with a persisted
        # scoped mode continues the state machine from its current state;
        # resume.py's mid-flight recovery relies on this entry point.

    conflicts = _conflicts(
        args,
        excluded=("precision_standard",),
    )
    if args.plan and args.optimize:
        conflicts.append("--plan with --optimize")
    if conflicts:
        print(
            "ERROR: positional lifecycle operation cannot be combined with: "
            f"{', '.join(conflicts)}"
        )
        return 2

    lane, lane_rc = _validated_lane(args.lane)
    if lane_rc:
        return lane_rc

    cap_bumps = {}
    if args.bump_cap:
        try:
            cap_bumps = _orch_attr("_parse_bump_caps")(args.bump_cap)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 2

    if args.optimize:
        try:
            ok, message = _orch_attr("_optimize_reentry_workspace")(workspace)
        except Exception as exc:
            print(f"ERROR (--optimize workspace rejected): {type(exc).__name__}: {exc}")
            return 2
        log.info("[--optimize] %s", message)
        if not ok:
            print(f"ERROR (--optimize rejected): {message}")
            return 7

    return _orch().run_single_op(
        args.op,
        workspace=workspace,
        lane=lane,
        plan_only=args.plan,
        cap_bumps=cap_bumps,
        timing=args.timing,
        backend="ascendc",
    )
