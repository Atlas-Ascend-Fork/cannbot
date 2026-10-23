# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Concrete run-bench execution: validation, baseline derivation, and benchmark runs.

Timing events and evidence appends live in run_bench_core; this module runs
the benchmark flow itself, though it still registers a regenerated baseline
perf artifact into managed workflow state when one is produced. Invalid
input combinations raise RunBenchInputError so the command adapter can
surface them through argparse. Every raise happens before the caller's
timed region starts.
"""

from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path
from typing import TextIO

from command_paths import require_existing_path
from execution_lifecycle import record_managed_generated_file
from perf_artifacts import MetricSource, compare_perf_files, probe_perf_output_path
from result_payload import ResultPayload, archive_long_failure_output, render_result
from run_bench_local_api import run_local_bench
from run_bench_modes import normalize_bench_mode
from run_bench_remote_api import run_remote_bench, run_remote_bench_comparison


_RUN_BENCH_HINT = "Hint: use `compare-perf` to inspect this perf artifact instead of reading it directly."
_FAST_PROBE_WARMUP_CAP = 1
_FAST_PROBE_REPEATS_CAP = 3
_FAST_PROBE_DISCLAIMER = (
    "NOTE: --fast-probe capped warmup/repeats at "
    "1/3; the comparison above is a screening signal, not a reliable conclusion."
)


class RunBenchInputError(Exception):
    """Invalid run-bench input combination; the adapter renders it as a CLI error."""


@dataclass(frozen=True)
class RunBenchRequest:
    """One run-bench invocation expressed independently of argparse.

    The baseline operator path stays raw (as typed on the CLI) so the
    executor validates it only after the recording wrapper's workflow gates
    pass, preserving the original error ordering.
    """

    command: str
    bench_file: Path
    operator_file: Path
    bench_mode: str | None = None
    baseline_operator_file: str | None = None
    fast_probe: bool = False
    output: str | None = None
    skip_latency_errors: bool = False
    metric_source: MetricSource = "auto"
    remote: str | None = None
    remote_workdir: str | None = None
    keep_remote_workdir: bool = False
    verbose: bool = False


@dataclass(frozen=True)
class RunBenchSpec:
    """Complete specification of one benchmark execution, produced by prepare_execution.

    Everything execute_benchmarks and compare_results need is here: the
    normalized bench mode, the resolved baseline inputs, the fast-probe
    derivation, the managed state path for mid-pipeline artifact
    registration, and the execution inputs carried over from the request.
    """

    command: str
    bench_file: Path
    operator_file: Path
    bench_mode: str
    baseline_operator_file: Path | None
    baseline_perf_path: Path | None
    using_canonical_baseline: bool
    managed_state_path: Path | None
    fast_probe: bool
    output: str | None
    skip_latency_errors: bool
    metric_source: MetricSource
    remote: str | None
    remote_workdir: str | None
    keep_remote_workdir: bool
    verbose: bool


@dataclass(frozen=True)
class BenchExecution:
    """Outcome of the benchmark runs for the recording wrapper.

    ``record_baseline_evidence`` is False only for the baseline-repair early
    exit, which historically records no baseline evidence; every other path
    (success or failure) records it.
    """

    benchmark_return_code: int
    candidate_perf_path: Path | None
    baseline_perf_path: Path | None
    using_canonical_baseline: bool
    record_baseline_evidence: bool = True


def _resolve_baseline_inputs(
    request: RunBenchRequest,
    canonical_baseline_operator_file: Path | None,
    canonical_baseline_perf_file: Path | None,
) -> tuple[Path | None, Path | None, bool]:
    """Resolve the baseline operator/perf pair, preferring the canonical managed one."""
    baseline_operator_file = _resolve_optional_input_path(
        request.baseline_operator_file, "Baseline operator file"
    )
    if request.command == "run-bench-baseline" and baseline_operator_file is not None:
        raise RunBenchInputError("run-bench-baseline does not accept --baseline-operator-file")
    baseline_perf_path = (
        _derived_perf_path(baseline_operator_file) if baseline_operator_file is not None else None
    )
    using_canonical_baseline = False
    if canonical_baseline_operator_file is not None:
        if baseline_operator_file is None:
            if not canonical_baseline_operator_file.is_file():
                raise RunBenchInputError(
                    f"canonical baseline operator does not exist: {canonical_baseline_operator_file}; "
                    "restore it or pass --baseline-operator-file explicitly"
                )
            baseline_operator_file = canonical_baseline_operator_file
            baseline_perf_path = canonical_baseline_perf_file
            using_canonical_baseline = True
        elif baseline_operator_file.resolve() == canonical_baseline_operator_file.resolve():
            baseline_perf_path = canonical_baseline_perf_file
            using_canonical_baseline = True
    return baseline_operator_file, baseline_perf_path, using_canonical_baseline


def _validate_fast_probe(
    request: RunBenchRequest,
    bench_mode: str,
    baseline_perf_path: Path | None,
    optimize_round_active: bool,
) -> None:
    if not request.fast_probe:
        return
    if request.command == "run-bench-baseline":
        raise RunBenchInputError("--fast-probe is not supported for run-bench-baseline")
    if not optimize_round_active:
        raise RunBenchInputError("--fast-probe requires an active optimize round")
    if bench_mode != "torch-npu-profiler":
        raise RunBenchInputError("--fast-probe supports only the torch-npu-profiler bench mode")
    if baseline_perf_path is None or not baseline_perf_path.exists():
        raise RunBenchInputError(
            "--fast-probe requires an existing baseline perf file; run a full run-bench first"
        )


def prepare_execution(
    request: RunBenchRequest,
    *,
    canonical_baseline_operator_file: Path | None,
    canonical_baseline_perf_file: Path | None,
    optimize_round_active: bool,
    managed_state_path: Path | None,
) -> RunBenchSpec:
    """Validate the request and derive baseline inputs before the timed region."""
    bench_mode = normalize_bench_mode(request.bench_mode or "torch-npu-profiler")
    baseline_operator_file, baseline_perf_path, using_canonical_baseline = _resolve_baseline_inputs(
        request, canonical_baseline_operator_file, canonical_baseline_perf_file
    )
    if baseline_perf_path is not None and baseline_perf_path.exists():
        print(f"Baseline perf file: {baseline_perf_path}")
    _validate_fast_probe(request, bench_mode, baseline_perf_path, optimize_round_active)
    output = request.output
    if output is None and request.fast_probe:
        output = str(probe_perf_output_path(request.operator_file))
    return RunBenchSpec(
        command=request.command,
        bench_file=request.bench_file,
        operator_file=request.operator_file,
        bench_mode=bench_mode,
        baseline_operator_file=baseline_operator_file,
        baseline_perf_path=baseline_perf_path,
        using_canonical_baseline=using_canonical_baseline,
        managed_state_path=managed_state_path,
        fast_probe=request.fast_probe,
        output=output,
        skip_latency_errors=request.skip_latency_errors,
        metric_source=request.metric_source,
        remote=request.remote,
        remote_workdir=request.remote_workdir,
        keep_remote_workdir=request.keep_remote_workdir,
        verbose=request.verbose,
    )


@dataclass(frozen=True)
class _BaselineRepairOutcome:
    """Result of the baseline-repair run; remote repairs carry the paired candidate run."""

    baseline_result: ResultPayload
    generated_perf: Path | None
    workspace: str | None
    candidate_result: ResultPayload | None = None
    candidate_perf: Path | None = None


def _run_baseline_repair(spec: RunBenchSpec) -> _BaselineRepairOutcome:
    """Benchmark the missing baseline; remote runs combine it with the candidate run."""
    if spec.baseline_operator_file is None:
        raise RuntimeError("internal error: baseline repair requires a baseline operator file")
    if spec.remote is not None:
        (baseline_result, generated_perf), candidate_pair, remote_workspace = run_remote_bench_comparison(
            spec.bench_file,
            spec.baseline_operator_file,
            spec.operator_file,
            spec.bench_mode,
            remote=spec.remote,
            remote_workdir=spec.remote_workdir,
            keep_remote_workdir=spec.keep_remote_workdir,
            verbose=spec.verbose,
            stderr=sys.stderr,
            output=spec.output,
        )
        candidate_result = candidate_perf = None
        if candidate_pair is not None:
            candidate_result, candidate_perf = candidate_pair
        return _BaselineRepairOutcome(
            baseline_result=baseline_result,
            generated_perf=generated_perf,
            workspace=remote_workspace,
            candidate_result=candidate_result,
            candidate_perf=candidate_perf,
        )
    baseline_result, generated_perf, baseline_workspace = _run_bench_once(
        spec.bench_file,
        spec.baseline_operator_file,
        spec.bench_mode,
        spec.remote,
        spec.remote_workdir,
        keep_remote_workdir=spec.keep_remote_workdir,
        verbose=spec.verbose,
        stderr=sys.stderr,
        output=None,
    )
    return _BaselineRepairOutcome(
        baseline_result=baseline_result,
        generated_perf=generated_perf,
        workspace=baseline_workspace,
    )


def _apply_baseline_repair(spec: RunBenchSpec, outcome: _BaselineRepairOutcome) -> BenchExecution | None:
    """Register a repaired baseline perf artifact; return an early exit on failure."""
    if int(outcome.baseline_result["return_code"]) != 0:
        render_result(
            archive_long_failure_output(outcome.baseline_result, workflow="run-bench"),
            spec.remote is not None and spec.verbose,
        )
    baseline_perf_path = (
        outcome.generated_perf if outcome.generated_perf is not None else spec.baseline_perf_path
    )
    if outcome.generated_perf is not None:
        if spec.managed_state_path is not None and spec.using_canonical_baseline:
            record_managed_generated_file(
                spec.managed_state_path, role="baseline_perf_file", path=outcome.generated_perf
            )
        print(f"Baseline perf file: {outcome.generated_perf}")
    if int(outcome.baseline_result["return_code"]) != 0 or outcome.generated_perf is None:
        if spec.remote is not None and spec.keep_remote_workdir and outcome.workspace is not None:
            print(f"Remote workspace: {outcome.workspace}")
        return BenchExecution(
            benchmark_return_code=int(outcome.baseline_result["return_code"]) or 1,
            candidate_perf_path=None,
            baseline_perf_path=baseline_perf_path,
            using_canonical_baseline=spec.using_canonical_baseline,
            record_baseline_evidence=False,
        )
    return None


def execute_benchmarks(spec: RunBenchSpec) -> BenchExecution:
    """Run the baseline-repair/candidate pipeline and render its outputs.

    When the baseline perf artifact is missing, the baseline operator is
    benchmarked first (combined with the candidate run for remote execution)
    and the regenerated artifact is registered into managed state; a failed
    repair exits early with no baseline evidence recording.
    """
    needs_baseline = (
        spec.baseline_operator_file is not None
        and spec.baseline_perf_path is not None
        and not spec.baseline_perf_path.exists()
    )
    baseline_perf_path = spec.baseline_perf_path
    candidate_result = None
    candidate_perf = None
    remote_workspace: str | None = None
    if needs_baseline:
        repair = _run_baseline_repair(spec)
        repair_failure = _apply_baseline_repair(spec, repair)
        if repair_failure is not None:
            return repair_failure
        if repair.generated_perf is not None:
            baseline_perf_path = repair.generated_perf
        candidate_result = repair.candidate_result
        candidate_perf = repair.candidate_perf
        remote_workspace = repair.workspace

    if needs_baseline and spec.remote is not None:
        if candidate_result is None:
            raise RuntimeError("internal error: remote baseline repair lost the candidate run")
        result, perf_path = candidate_result, candidate_perf
        workspace = remote_workspace
    else:
        result, perf_path, workspace = _run_bench_once(
            spec.bench_file,
            spec.operator_file,
            spec.bench_mode,
            spec.remote,
            spec.remote_workdir,
            keep_remote_workdir=spec.keep_remote_workdir,
            verbose=spec.verbose,
            stderr=sys.stderr,
            output=spec.output,
            warmup_cap=_FAST_PROBE_WARMUP_CAP if spec.fast_probe else None,
            repeats_cap=_FAST_PROBE_REPEATS_CAP if spec.fast_probe else None,
        )
    return _bench_execution_result(spec, result, perf_path, workspace, baseline_perf_path)


def _bench_execution_result(
    spec: RunBenchSpec,
    result: ResultPayload,
    perf_path: Path | None,
    workspace: str | None,
    baseline_perf_path: Path | None,
) -> BenchExecution:
    benchmark_return_code = int(result["return_code"])
    if benchmark_return_code != 0:
        render_result(
            archive_long_failure_output(result, workflow="run-bench"),
            spec.remote is not None and spec.verbose,
        )
    if spec.remote is not None and spec.keep_remote_workdir and workspace is not None:
        print(f"Remote workspace: {workspace}")
    if perf_path is not None:
        print(f"Perf file: {perf_path}")
    return BenchExecution(
        benchmark_return_code=benchmark_return_code,
        candidate_perf_path=perf_path,
        baseline_perf_path=baseline_perf_path,
        using_canonical_baseline=spec.using_canonical_baseline,
    )


def compare_results(spec: RunBenchSpec, execution: BenchExecution) -> int:
    """Produce the final return code from the executed benchmark artifacts.

    Without both perf artifacts there is nothing to compare: the benchmark's
    own return code stands (with a pointer to compare-perf when the
    candidate artifact exists).
    """
    if execution.candidate_perf_path is None or execution.baseline_perf_path is None:
        if execution.candidate_perf_path is not None:
            print(_RUN_BENCH_HINT)
        return execution.benchmark_return_code
    final_code = compare_perf_files(
        execution.baseline_perf_path,
        execution.candidate_perf_path,
        skip_latency_errors=spec.skip_latency_errors,
        metric_source=spec.metric_source,
    )
    if spec.fast_probe:
        print(_FAST_PROBE_DISCLAIMER)
    return final_code


def _run_bench_once(
    bench_file: Path,
    operator_file: Path,
    bench_mode: str,
    remote: str | None,
    remote_workdir: str | None,
    *,
    keep_remote_workdir: bool,
    verbose: bool,
    stderr: TextIO | None,
    output: str | None,
    warmup_cap: int | None = None,
    repeats_cap: int | None = None,
) -> tuple[ResultPayload, Path | None, str | None]:
    if remote is not None:
        result, perf_path, workspace = run_remote_bench(
            bench_file,
            operator_file,
            bench_mode,
            remote,
            remote_workdir,
            keep_remote_workdir=keep_remote_workdir,
            verbose=verbose,
            stderr=stderr,
            output=output,
            warmup_cap=warmup_cap,
            repeats_cap=repeats_cap,
        )
        return result, perf_path, workspace
    result, perf_path = run_local_bench(
        bench_file,
        operator_file,
        bench_mode,
        verbose=verbose,
        output=output,
        warmup_cap=warmup_cap,
        repeats_cap=repeats_cap,
    )
    return result, perf_path, None


def _resolve_optional_input_path(raw_path: str | None, label: str) -> Path | None:
    """Resolve an optional CLI path input, or None when it was not given.

    The ValueError catch is scoped to the path check alone so unrelated
    ValueErrors keep bubbling.
    """
    if raw_path is None:
        return None
    try:
        return require_existing_path(raw_path, label)
    except ValueError as exc:
        raise RunBenchInputError(str(exc)) from exc


def _derived_perf_path(operator_file: Path) -> Path:
    return operator_file.parent / f"{operator_file.stem}_perf.txt"
