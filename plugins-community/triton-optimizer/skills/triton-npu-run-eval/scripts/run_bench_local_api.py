# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Parent-process API for isolated local benchmark execution."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from debug_device import maybe_print_visible_devices
from perf_artifacts import (
    PerfCaseRecord,
    perf_case_record_from_mapping,
    perf_file_case_labels,
    perf_output_path,
    synthesize_missing_case_records,
    write_perf_records_file,
)
from result_payload import ResultPayload, archive_long_failure_output, load_result
from worker_supervisor import (
    SupervisedRun,
    local_worker_command,
    print_prewarm_warning,
    run_supervised_worker,
)


SCRIPT_DIR = Path(__file__).resolve().parent

# Reason stamped on a planned case whose record never reached the parent. The
# parent sees a missing record, not a dead worker, so the wording says only
# that: a worker that lost a record this way can have completed normally.
MISSING_RECORD_REASON = "no perf record returned for this case"
TIMEOUT_REASON = "killed by timeout (HELIX_EVAL_TIMEOUT_SECONDS)"


def _resolve_perf_output_path(operator_file: Path, *, output: str | None = None) -> Path:
    if output is not None:
        return Path(output).expanduser().resolve()
    return perf_output_path(operator_file)


def run_local_bench(
    bench_file: Path,
    operator_file: Path,
    bench_mode: str,
    verbose: bool = False,
    output: str | None = None,
    *,
    warmup_cap: int | None = None,
    repeats_cap: int | None = None,
    extra_env: dict[str, str] | None = None,
) -> tuple[ResultPayload, Path | None]:
    if (warmup_cap is None) != (repeats_cap is None):
        raise ValueError("Both execution limits are required together")
    maybe_print_visible_devices()
    perf_path = _resolve_perf_output_path(operator_file, output=output)
    run = _run_bench_worker(
        bench_file,
        operator_file,
        bench_mode,
        perf_path=perf_path,
        verbose=verbose,
        warmup_cap=warmup_cap,
        repeats_cap=repeats_cap,
        extra_env=extra_env,
    )
    captured_records = [
        perf_case_record_from_mapping(record, bench_mode=bench_mode)
        for record in run.records
    ]
    if run.final is None:
        if not captured_records and not run.planned_case_ids:
            return archive_long_failure_output(run.result, workflow="run-bench"), None
        if not _perf_file_is_complete(run, perf_path):
            _write_synthesized_perf(perf_path, run, captured_records)
        return archive_long_failure_output(run.result, workflow="run-bench"), perf_path
    result = load_result(cast(Mapping[str, object], run.final["result"]))
    final_perf_path = _perf_path_from_final(run.final)
    if (
        final_perf_path is not None
        and _has_missing_planned_cases(run, captured_records)
        and not _perf_file_is_complete(run, final_perf_path)
    ):
        _write_synthesized_perf(final_perf_path, run, captured_records)
    return archive_long_failure_output(result, workflow="run-bench"), final_perf_path


def _run_bench_worker(
    bench_file: Path,
    operator_file: Path,
    bench_mode: str,
    *,
    perf_path: Path,
    verbose: bool,
    warmup_cap: int | None,
    repeats_cap: int | None,
    extra_env: dict[str, str] | None,
) -> SupervisedRun:
    args = [
        "--bench-file",
        str(bench_file.resolve()),
        "--operator-file",
        str(operator_file.resolve()),
        "--bench-mode",
        bench_mode,
        "--output",
        str(perf_path.resolve()),
    ]
    if verbose:
        args.append("--verbose")
    if warmup_cap is not None and repeats_cap is not None:
        args.extend(["--warmup-cap", str(warmup_cap), "--repeats-cap", str(repeats_cap)])
    return run_supervised_worker(
        local_worker_command(SCRIPT_DIR / "run_bench_worker.py", "run-bench", args),
        str(bench_file.resolve().parent),
        extra_env=extra_env,
        forward_stdout=sys.stdout if verbose else None,
        on_progress=None if verbose else print_prewarm_warning,
    )


def _write_synthesized_perf(
    perf_path: Path,
    run: SupervisedRun,
    captured_records: list[PerfCaseRecord],
) -> None:
    write_perf_records_file(
        perf_path,
        synthesize_missing_case_records(
            captured_records,
            run.planned_case_ids,
            TIMEOUT_REASON if run.timed_out else MISSING_RECORD_REASON,
        ),
    )


def _has_missing_planned_cases(
    run: SupervisedRun,
    captured_records: list[PerfCaseRecord],
) -> bool:
    captured_labels = {record.case_label for record in captured_records}
    return any(case_id not in captured_labels for case_id in run.planned_case_ids)


def _perf_file_is_complete(run: SupervisedRun, perf_path: Path) -> bool:
    """True when *perf_path* already holds this run's every planned case.

    The worker writes the perf file itself, before it emits ``final``, so a
    completed run normally leaves a complete artifact behind even when the
    parent's stream lost some of its ``case`` records. The parent's captured
    list is the fallback, never the source of truth: synthesizing over a
    complete artifact replaces real metrics with "missing record" rows.

    A file older than the worker is a leftover from an earlier run at the same
    deterministic path, and a file with no planned case ids to check against
    cannot be vouched for; both fall back to synthesis.
    """
    if not run.planned_case_ids:
        return False
    try:
        if perf_path.stat().st_mtime < run.started_at:
            return False
    except OSError:
        return False
    labels = perf_file_case_labels(perf_path)
    if labels is None:
        return False
    return all(case_id in labels for case_id in run.planned_case_ids)


def _perf_path_from_final(final: Mapping[str, object]) -> Path | None:
    raw = final.get("perf_path")
    return None if raw is None else Path(str(raw)).expanduser().resolve()


def run_local_profile_bench(
    bench_file: Path,
    operator_file: Path,
    case_id: str | None = None,
    kernel_name: str | None = None,
    output_dir: Path | None = None,
) -> tuple[ResultPayload, Path | None]:
    del kernel_name
    if case_id is None:
        raise ValueError("torch-npu-profiler benchmark profiling requires --case-id <id>.")
    args = [
        "--bench-file",
        str(bench_file.resolve()),
        "--operator-file",
        str(operator_file.resolve()),
        "--case-id",
        case_id,
    ]
    run = run_supervised_worker(
        local_worker_command(SCRIPT_DIR / "run_bench_worker.py", "profile-artifact", args),
        str(bench_file.resolve().parent),
        forward_stdout=sys.stdout,
    )
    if run.final is None:
        return run.result, None
    result = load_result(cast(Mapping[str, object], run.final["result"]))
    profile_dir = _profile_dir_from_final(run.final)
    if profile_dir is not None and output_dir is not None:
        profile_dir = _move_profile_dir(profile_dir, output_dir)
    return result, profile_dir


def _profile_dir_from_final(final: Mapping[str, object]) -> Path | None:
    raw = final.get("profile_dir")
    return None if raw is None else Path(str(raw)).expanduser().resolve()


def _move_profile_dir(profile_dir: Path, output_dir: Path) -> Path:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / profile_dir.name
    if target.exists():
        raise FileExistsError(f"Profile directory already exists: {target}")
    shutil.move(str(profile_dir), str(target))
    return target.resolve()
