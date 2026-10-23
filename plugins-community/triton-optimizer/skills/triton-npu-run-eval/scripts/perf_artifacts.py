# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

import json
import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NamedTuple, Optional, TypedDict, Union, cast


_RETIRED_BENCH_MODE_ALIASES = {
    "standalone": "torch-npu-profiler",
    "msprof": "torch-npu-profiler",
}


def normalize_bench_mode(bench_mode: str) -> str:
    """Map retired bench-mode spellings to the mode that replaced them."""
    return _RETIRED_BENCH_MODE_ALIASES.get(bench_mode, bench_mode)


class PerfOpRow(TypedDict):
    op_type: str
    avg_time_us: float


class PerfMetricsRequired(TypedDict):
    kernel_avg_time_us: float | None
    ops: list[PerfOpRow]


class PerfMetrics(PerfMetricsRequired, total=False):
    total_op_avg_time_us: float | None


@dataclass(frozen=True)
class PerfCaseRecord:
    case_label: str
    kernel_names: list[str]
    kernel_source: str
    metrics: PerfMetrics | None = None
    error_message: str | None = None
    case_wall_clock_seconds: float | None = None
    bench_mode: str | None = None


ComparisonMode = Literal["latency", "total-op"]
MetricSource = Literal["auto", "kernel", "total-op", "all"]


@dataclass(frozen=True)
class PerfEntry:
    display_value: str
    numeric_value: float
    comparison_mode: ComparisonMode


@dataclass(frozen=True)
class PerfParseOutcome:
    entries: dict[str, PerfEntry]
    skipped_latency_errors: dict[str, str]


@dataclass(frozen=True)
class PerfPairOutcome:
    baseline_entries: dict[str, PerfEntry]
    compare_entries: dict[str, PerfEntry]
    skipped_latency_errors: dict[str, str]


@dataclass(frozen=True)
class MetricSourceSectionResult:
    metric_source: str
    rendered_output: str


@dataclass(frozen=True)
class _ComparableMetrics:
    """Intersected numeric metrics plus any invalid-metric errors found."""

    comparable_ids: list[str]
    baseline: dict[str, float]
    compare: dict[str, float]
    invalid_metric_errors: dict[str, str]


class PerfValueMap(dict[str, float]):
    def __init__(
        self,
        values: dict[str, float],
        *,
        comparison_modes: dict[str, ComparisonMode],
    ) -> None:
        super().__init__(values)
        self.comparison_modes = comparison_modes


RequiredLatencyIds = Union[Collection[str], dict[str, PerfEntry], PerfValueMap]
PerfPairValues = tuple[dict[str, float], dict[str, float], dict[str, ComparisonMode]]
RequiredLatencyIdResolution = tuple[set[str], dict[str, ComparisonMode]]


class PerfMetricSummary(NamedTuple):
    avg_improvement: Optional[float]
    geomean_speedup: Optional[float]
    regressed_case_count: int
    ordered_cases: tuple[tuple[str, float, float], ...]


def _jsonl_modes(path: Path) -> list[tuple[int, str | None]]:
    modes: list[tuple[int, str | None]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            has_record, record_mode = _jsonl_record_bench_mode(line)
            if has_record:
                modes.append((line_no, record_mode))
    return modes


def _read_bench_mode_from_jsonl(path: Path) -> str | None:
    """Return the bench_mode from the first non-empty JSONL record.

    Also verifies that all records in the file have the same bench_mode.
    A mix of modes within one file is treated as corrupt data. Retired
    spellings (for example ``msprof``) are normalized to their replacement
    mode so historical files stay comparable with new runs.
    """
    try:
        modes = _jsonl_modes(path)
    except (json.JSONDecodeError, OSError):
        return None
    if not modes:
        return None
    mode = modes[0][1]
    for line_no, record_mode in modes[1:]:
        if mode != record_mode:
            raise ValueError(
                f"{path}: mixed bench_mode in same file: "
                f"line {line_no} has bench_mode={record_mode}, "
                f"but earlier records have bench_mode={mode}"
            )
    return mode


def _jsonl_record_bench_mode(line: str) -> tuple[bool, str | None]:
    """Decode one JSONL line into (has_record, normalized bench_mode)."""
    stripped = line.strip()
    if not stripped:
        return False, None
    record = json.loads(stripped)
    raw_mode = record.get("bench_mode")
    if raw_mode is None:
        return True, None
    return True, normalize_bench_mode(str(raw_mode))


def _check_cross_mode(baseline_perf: Path, compare_perf: Path) -> None:
    try:
        baseline_mode = _read_bench_mode_from_jsonl(baseline_perf)
        compare_mode = _read_bench_mode_from_jsonl(compare_perf)
    except ValueError as exc:
        raise ValueError(f"cannot compare results: {exc}") from exc
    if baseline_mode is None and compare_mode is None:
        return
    if baseline_mode is None:
        raise ValueError(
            f"cannot compare results: candidate has bench_mode={compare_mode} "
            f"but baseline has no bench_mode (pre-perf-counter record)"
        )
    if compare_mode is None:
        raise ValueError(
            f"cannot compare results: baseline has bench_mode={baseline_mode} "
            f"but candidate has no bench_mode (pre-perf-counter record)"
        )
    if baseline_mode != compare_mode:
        raise ValueError(
            f"cannot compare results from different bench modes: "
            f"baseline={baseline_mode}, candidate={compare_mode}"
        )


def compare_perf_files(
    baseline_perf: Path,
    compare_perf: Path,
    *,
    skip_latency_errors: bool = False,
    metric_source: MetricSource = "auto",
) -> int:
    if metric_source == "all":
        return _compare_perf_files_all(
            baseline_perf,
            compare_perf,
            skip_latency_errors=skip_latency_errors,
        )
    try:
        baseline_outcome, compare_outcome, pair_outcome = _load_comparison_pair(
            baseline_perf,
            compare_perf,
            skip_latency_errors=skip_latency_errors,
            metric_source=metric_source,
        )
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    metrics = _resolve_comparable_metrics(
        pair_outcome,
        baseline_perf=baseline_perf,
        compare_perf=compare_perf,
        skip_latency_errors=skip_latency_errors,
    )
    first_invalid_error = _first_invalid_metric_error(metrics.invalid_metric_errors)
    if first_invalid_error is not None and not skip_latency_errors:
        print(f"FAIL: {first_invalid_error}")
        return 1
    for line in _comparison_report_lines(
        metrics,
        pair_outcome,
        metric_source=metric_source,
    ):
        print(line)
    skipped_latency_errors = _merged_skipped_latency_errors(
        baseline_outcome, compare_outcome, pair_outcome, metrics
    )
    if skipped_latency_errors:
        print(f"FAIL: skipped {len(skipped_latency_errors)} latency entries due to latency errors")
        for _latency_id, detail in sorted(skipped_latency_errors.items()):
            print(detail)
        return 1
    print(f"PASS: compared {len(metrics.baseline)} latency entries")
    return 0


def _parse_comparison_outcomes(
    baseline_perf: Path,
    compare_perf: Path,
    *,
    skip_latency_errors: bool,
    metric_source: MetricSource,
) -> tuple[PerfParseOutcome, PerfParseOutcome]:
    """Parse both perf files into comparison-ready outcomes."""
    baseline_outcome = _parse_perf_entries_for_comparison(
        baseline_perf,
        skip_latency_errors=skip_latency_errors,
        metric_source=metric_source,
    )
    compare_outcome = _parse_required_perf_entries_for_comparison(
        compare_perf,
        baseline_outcome.entries,
        skip_latency_errors=skip_latency_errors,
        metric_source=metric_source,
    )
    return baseline_outcome, compare_outcome


def _load_comparison_pair(
    baseline_perf: Path,
    compare_perf: Path,
    *,
    skip_latency_errors: bool,
    metric_source: MetricSource,
) -> tuple[PerfParseOutcome, PerfParseOutcome, PerfPairOutcome]:
    """Parse both perf files and normalize the entry pair for comparison."""
    _check_cross_mode(baseline_perf, compare_perf)
    baseline_outcome, compare_outcome = _parse_comparison_outcomes(
        baseline_perf, compare_perf, skip_latency_errors=skip_latency_errors, metric_source=metric_source
    )
    pair_outcome = _normalize_perf_pair_for_comparison(
        baseline_perf=baseline_perf,
        compare_perf=compare_perf,
        baseline_entries=baseline_outcome.entries,
        compare_entries=compare_outcome.entries,
        metric_source=metric_source,
        tolerate_latency_errors=skip_latency_errors,
    )
    return baseline_outcome, compare_outcome, pair_outcome


def _resolve_comparable_metrics(
    pair_outcome: PerfPairOutcome,
    *,
    baseline_perf: Path,
    compare_perf: Path,
    skip_latency_errors: bool,
) -> _ComparableMetrics:
    """Intersect both sides numerically, dropping invalid metrics when skipping."""
    comparable_ids = sorted(set(pair_outcome.baseline_entries) & set(pair_outcome.compare_entries))
    baseline = _numeric_metric_values(pair_outcome.baseline_entries, comparable_ids)
    compare = _numeric_metric_values(pair_outcome.compare_entries, comparable_ids)
    invalid_metric_errors = _collect_invalid_metric_errors(
        baseline,
        compare,
        baseline_perf=baseline_perf,
        compare_perf=compare_perf,
    )
    if invalid_metric_errors and skip_latency_errors:
        comparable_ids = [
            latency_id
            for latency_id in comparable_ids
            if latency_id not in invalid_metric_errors
        ]
        baseline = _numeric_metric_values(pair_outcome.baseline_entries, comparable_ids)
        compare = _numeric_metric_values(pair_outcome.compare_entries, comparable_ids)
    return _ComparableMetrics(
        comparable_ids=comparable_ids,
        baseline=baseline,
        compare=compare,
        invalid_metric_errors=invalid_metric_errors,
    )


def _merged_skipped_latency_errors(
    baseline_outcome: PerfParseOutcome,
    compare_outcome: PerfParseOutcome,
    pair_outcome: PerfPairOutcome,
    metrics: _ComparableMetrics,
) -> Mapping[str, str]:
    return {
        **baseline_outcome.skipped_latency_errors,
        **compare_outcome.skipped_latency_errors,
        **pair_outcome.skipped_latency_errors,
        **metrics.invalid_metric_errors,
    }


def _numeric_metric_values(
    entries: dict[str, PerfEntry],
    comparable_ids: Collection[str],
) -> dict[str, float]:
    return {latency_id: entries[latency_id].numeric_value for latency_id in comparable_ids}


def _first_invalid_metric_error(invalid_metric_errors: Mapping[str, str]) -> str | None:
    if not invalid_metric_errors:
        return None
    first_latency_id = sorted(invalid_metric_errors)[0]
    return invalid_metric_errors.get(first_latency_id)


def _comparison_report_lines(
    metrics: _ComparableMetrics,
    pair_outcome: PerfPairOutcome,
    *,
    metric_source: MetricSource,
) -> list[str]:
    lines = ["Perf comparison:"]
    for latency_id in metrics.comparable_ids:
        baseline_value = metrics.baseline[latency_id]
        compare_value = metrics.compare[latency_id]
        baseline_display = pair_outcome.baseline_entries[latency_id].display_value
        compare_display = pair_outcome.compare_entries[latency_id].display_value
        lines.append(
            f"{latency_id}: baseline={baseline_display}, "
            f"compare={compare_display}, "
            f"delta={_format_delta_percent(baseline_value, compare_value)}"
        )
    lines.extend(_summary_report_lines(metrics.baseline, metrics.compare))
    compared_entries = {
        latency_id: pair_outcome.baseline_entries[latency_id]
        for latency_id in metrics.comparable_ids
    }
    lines.append(f"Metric source: {_summarize_metric_source(compared_entries, metric_source=metric_source)}")
    return lines


def _summary_report_lines(
    baseline: dict[str, float],
    compare: dict[str, float],
) -> list[str]:
    summary = _summarize_perf_metrics(baseline, compare)
    lines = [
        f"Avg improvement: {_format_improvement_percent(summary.avg_improvement)}",
        f"Geomean speedup: {_format_speedup(summary.geomean_speedup)}",
        "Best case speedup: "
        f"{_format_speedup(summary.ordered_cases[-1][1] if summary.ordered_cases else None)}",
        "Worst case speedup: "
        f"{_format_speedup(summary.ordered_cases[0][1] if summary.ordered_cases else None)}",
        f"Regressed cases: {summary.regressed_case_count}",
    ]
    review_disposition = _review_disposition(
        summary.geomean_speedup, [case[1] for case in summary.ordered_cases]
    )
    lines.append(f"Review disposition: {review_disposition}")
    for latency_id, speedup, baseline_value in summary.ordered_cases[:3]:
        lines.append(f"Bottom case: {latency_id} speedup={_format_speedup(speedup)}, baseline={baseline_value:g}")
    return lines


def _compare_perf_files_all(
    baseline_perf: Path,
    compare_perf: Path,
    *,
    skip_latency_errors: bool,
) -> int:
    try:
        _check_cross_mode(baseline_perf, compare_perf)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1
    exit_codes: list[int] = []
    section_results: list[MetricSourceSectionResult] = []
    for section_metric_source in ("kernel", "total-op"):
        section_result, exit_code = _compare_metric_source_section(
            baseline_perf,
            compare_perf,
            section_metric_source,
            skip_latency_errors=skip_latency_errors,
        )
        section_results.append(section_result)
        exit_codes.append(exit_code)

    for section_result in section_results:
        print(section_result.rendered_output, end="")
    return 0 if section_results and all(code == 0 for code in exit_codes) else 1


def _compare_metric_source_section(
    baseline_perf: Path,
    compare_perf: Path,
    section_metric_source: str,
    *,
    skip_latency_errors: bool,
) -> tuple[MetricSourceSectionResult, int]:
    """Render one metric-source section of the ``all`` comparison report."""
    metric_source = cast(MetricSource, section_metric_source)
    pair_outcome, failure_detail = _try_section_pair(
        baseline_perf,
        compare_perf,
        metric_source,
        skip_latency_errors=skip_latency_errors,
    )
    if failure_detail is not None or pair_outcome is None:
        return _section_failure(section_metric_source, failure_detail or "unavailable"), 1
    metrics = _resolve_comparable_metrics(
        pair_outcome,
        baseline_perf=baseline_perf,
        compare_perf=compare_perf,
        skip_latency_errors=skip_latency_errors,
    )
    first_invalid_error = _first_invalid_metric_error(metrics.invalid_metric_errors)
    if first_invalid_error is not None and not skip_latency_errors:
        return _section_failure(section_metric_source, f"FAIL: {first_invalid_error}"), 1
    lines = [f"Metric source section: {section_metric_source}"]
    lines.extend(
        _comparison_report_lines(metrics, pair_outcome, metric_source=metric_source)
    )
    skipped_latency_errors = _merged_skipped_latency_errors(
        baseline_outcome, compare_outcome, pair_outcome, metrics
    )
    if skipped_latency_errors:
        lines.append(
            f"FAIL: skipped {len(skipped_latency_errors)} latency entries due to latency errors"
        )
        for _latency_id, detail in sorted(skipped_latency_errors.items()):
            lines.append(detail)
        exit_code = 1
    else:
        lines.append(f"PASS: compared {len(metrics.baseline)} latency entries")
        exit_code = 0
    return (
        MetricSourceSectionResult(
            metric_source=section_metric_source,
            rendered_output="\n".join(lines) + "\n",
        ),
        exit_code,
    )


def _try_section_pair(
    baseline_perf: Path,
    compare_perf: Path,
    metric_source: MetricSource,
    *,
    skip_latency_errors: bool,
) -> tuple[PerfPairOutcome | None, str | None]:
    """Parse and normalize one section's perf pair; (outcome, failure detail)."""
    try:
        baseline_outcome, compare_outcome = _parse_comparison_outcomes(
            baseline_perf,
            compare_perf,
            skip_latency_errors=skip_latency_errors,
            metric_source=metric_source,
        )
    except ValueError as exc:
        return None, f"unavailable: {exc}"
    try:
        return _normalize_perf_pair_for_comparison(
            baseline_perf=baseline_perf,
            compare_perf=compare_perf,
            baseline_entries=baseline_outcome.entries,
            compare_entries=compare_outcome.entries,
            metric_source=metric_source,
            tolerate_latency_errors=skip_latency_errors,
        ), None
    except ValueError as exc:
        return None, f"FAIL: {exc}"


def _section_failure(section_metric_source: str, detail: str) -> MetricSourceSectionResult:
    return MetricSourceSectionResult(
        metric_source=section_metric_source,
        rendered_output=f"Metric source section: {section_metric_source}\n{detail}\n",
    )


def parse_perf_file(path: Path) -> dict[str, float]:
    return _parse_perf_file(path)


def parse_required_perf_file(path: Path, required_latency_ids: RequiredLatencyIds) -> dict[str, float]:
    return _parse_required_perf_file(path, required_latency_ids)


def parse_perf_file_for_metric_source(
    path: Path,
    *,
    metric_source: MetricSource = "auto",
) -> dict[str, float]:
    if metric_source == "all":
        raise ValueError("parse_perf_file_for_metric_source does not support metric_source='all'")
    outcome = _parse_perf_entries_for_comparison(
        path,
        skip_latency_errors=False,
        metric_source=metric_source,
    )
    return PerfValueMap(
        {latency_id: entry.numeric_value for latency_id, entry in outcome.entries.items()},
        comparison_modes={
            latency_id: entry.comparison_mode for latency_id, entry in outcome.entries.items()
        },
    )


def parse_required_perf_file_for_metric_source(
    path: Path,
    required_latency_ids: RequiredLatencyIds,
    *,
    metric_source: MetricSource = "auto",
) -> dict[str, float]:
    if metric_source == "all":
        raise ValueError(
            "parse_required_perf_file_for_metric_source does not support metric_source='all'"
        )
    outcome = _parse_required_perf_entries_for_comparison(
        path,
        required_latency_ids,
        skip_latency_errors=False,
        metric_source=metric_source,
    )
    return PerfValueMap(
        {latency_id: entry.numeric_value for latency_id, entry in outcome.entries.items()},
        comparison_modes={
            latency_id: entry.comparison_mode for latency_id, entry in outcome.entries.items()
        },
    )


def parse_perf_pair_for_comparison(
    baseline_perf: Path,
    compare_perf: Path,
    *,
    metric_source: MetricSource = "auto",
) -> PerfPairValues:
    if metric_source == "all":
        raise ValueError("parse_perf_pair_for_comparison does not support metric_source='all'")
    _check_cross_mode(baseline_perf, compare_perf)
    baseline_outcome = _parse_perf_entries_for_comparison(
        baseline_perf,
        skip_latency_errors=False,
        metric_source=metric_source,
    )
    compare_outcome = _parse_required_perf_entries_for_comparison(
        compare_perf,
        baseline_outcome.entries,
        skip_latency_errors=False,
        metric_source=metric_source,
    )
    pair_outcome = _normalize_perf_pair_for_comparison(
        baseline_perf=baseline_perf,
        compare_perf=compare_perf,
        baseline_entries=baseline_outcome.entries,
        compare_entries=compare_outcome.entries,
        metric_source=metric_source,
        tolerate_latency_errors=False,
    )
    baseline_values = {
        latency_id: entry.numeric_value
        for latency_id, entry in pair_outcome.baseline_entries.items()
    }
    compare_values = {
        latency_id: entry.numeric_value
        for latency_id, entry in pair_outcome.compare_entries.items()
    }
    invalid_metric_errors = _collect_invalid_metric_errors(
        baseline_values,
        compare_values,
        baseline_perf=baseline_perf,
        compare_perf=compare_perf,
    )
    if invalid_metric_errors:
        first_latency_id = sorted(invalid_metric_errors)[0]
        raise ValueError(invalid_metric_errors[first_latency_id])
    comparison_modes: dict[str, ComparisonMode] = {
        latency_id: entry.comparison_mode
        for latency_id, entry in pair_outcome.baseline_entries.items()
    }
    return baseline_values, compare_values, comparison_modes


def perf_output_path(operator_file: Path) -> Path:
    return operator_file.parent / f"{operator_file.stem}_perf.txt"


def probe_perf_output_path(operator_file: Path) -> Path:
    return operator_file.parent / f"{operator_file.stem}_probe.txt"


def write_perf_lines(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


def format_latency_value(value: float) -> str:
    rendered = f"{value:.6f}".rstrip("0").rstrip(".")
    if "." not in rendered:
        rendered += ".0"
    return rendered


def render_perf_case_record_jsonl(
    record: PerfCaseRecord,
    *,
    missing_kernel_match_error: str | None = None,
) -> str:
    metrics = record.metrics
    kernel_avg_time_us: float | None = None
    ops: list[PerfOpRow] | None = None
    total_op_avg_time_us: float | None = None
    if metrics is not None:
        kernel_avg_time_us = metrics["kernel_avg_time_us"]
        ops = metrics["ops"]
        explicit_total_op_avg_time_us = metrics.get("total_op_avg_time_us")
        if explicit_total_op_avg_time_us is not None:
            total_op_avg_time_us = explicit_total_op_avg_time_us
        elif ops:
            total_op_avg_time_us = sum(op["avg_time_us"] for op in ops)
        elif record.bench_mode == "perf-counter":
            total_op_avg_time_us = kernel_avg_time_us
        else:
            total_op_avg_time_us = 0.0
    error_message = record.error_message
    if error_message is None and metrics is not None and kernel_avg_time_us is None:
        error_message = missing_kernel_match_error
    payload: dict[str, object] = {
        "case_label": record.case_label,
        "kernel_names": record.kernel_names,
        "kernel_source": record.kernel_source,
        "kernel_avg_time_us": kernel_avg_time_us,
        "ops": ops,
        "total_op_avg_time_us": total_op_avg_time_us,
        "error_message": error_message,
        "case_wall_clock_seconds": record.case_wall_clock_seconds,
        "bench_mode": record.bench_mode,
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def render_perf_case_records_jsonl(
    records: list[PerfCaseRecord],
    *,
    missing_kernel_match_error: str | None = None,
) -> list[str]:
    return [
        render_perf_case_record_jsonl(
            record,
            missing_kernel_match_error=missing_kernel_match_error,
        )
        for record in records
    ]


def perf_case_record_from_mapping(
    payload: Mapping[str, object],
    *,
    bench_mode: str,
) -> PerfCaseRecord:
    """Rebuild a ``PerfCaseRecord`` from a decoded worker ``case`` payload.

    The supervisor delivers per-case records as decoded JSON dicts. The
    ``bench_mode`` argument is the mode the run was launched with and fills
    in records the worker emitted without one.
    """
    metrics_payload = payload.get("metrics")
    parsed_bench_mode = payload.get("bench_mode")
    return PerfCaseRecord(
        case_label=str(payload["case_label"]),
        kernel_names=[
            str(name) for name in cast(list[object], payload.get("kernel_names") or [])
        ],
        kernel_source=str(payload.get("kernel_source") or "metadata"),
        metrics=None if metrics_payload is None else cast(PerfMetrics, metrics_payload),
        error_message=(
            None if payload.get("error_message") is None else str(payload["error_message"])
        ),
        case_wall_clock_seconds=(
            None
            if payload.get("case_wall_clock_seconds") is None
            else float(cast("int | float | str", payload["case_wall_clock_seconds"]))
        ),
        bench_mode=bench_mode if parsed_bench_mode is None else str(parsed_bench_mode),
    )


def perf_record_to_mapping(record: PerfCaseRecord) -> dict[str, object]:
    """Serialize one case record to the worker ``case`` payload shape.

    The emit seam carries decoded-JSON mappings, not dataclasses; this is
    the exact seven-key shape ``perf_case_record_from_mapping`` rebuilds a
    ``PerfCaseRecord`` from on the other side.
    """
    return {
        "case_label": record.case_label,
        "kernel_names": record.kernel_names,
        "kernel_source": record.kernel_source,
        "metrics": record.metrics,
        "error_message": record.error_message,
        "case_wall_clock_seconds": record.case_wall_clock_seconds,
        "bench_mode": record.bench_mode,
    }


def synthesize_missing_case_records(
    records: list[PerfCaseRecord],
    planned_case_ids: Sequence[str],
    reason: str,
) -> list[PerfCaseRecord]:
    """Complete a partial record list for the perf JSONL artifact.

    Captured records keep their arrival order; one error record is appended
    per planned case id that has no captured record, so the artifact always
    carries one line per planned case after a worker death or timeout. The
    synthesized records reuse the captured records' bench mode (defaulting
    to ``torch-npu-profiler``) because one perf file must carry a single
    bench mode.
    """
    captured_labels = {record.case_label for record in records}
    bench_mode = next(
        (record.bench_mode for record in records if record.bench_mode is not None),
        "torch-npu-profiler",
    )
    synthesized = [
        PerfCaseRecord(
            case_label=case_id,
            kernel_names=[],
            kernel_source="metadata",
            error_message=reason,
            case_wall_clock_seconds=None,
            bench_mode=bench_mode,
        )
        for case_id in dict.fromkeys(planned_case_ids)
        if case_id not in captured_labels
    ]
    return [*records, *synthesized]


def write_perf_records_file(path: Path, records: list[PerfCaseRecord]) -> Path:
    return write_perf_lines(
        path,
        render_perf_case_records_jsonl(
            records,
            missing_kernel_match_error="no resolved kernels matched profiler kernel view",
        ),
    )


def perf_file_case_labels(path: Path) -> "Optional[set[str]]":
    """Case labels recorded in an existing perf JSONL artifact.

    ``None`` when the file is missing or any line fails to decode, so a caller
    can tell "no usable artifact here" apart from "an artifact that covers
    fewer cases than planned".
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    labels: "set[str]" = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except ValueError:
            return None
        if not isinstance(entry, Mapping):
            return None
        label = cast(Mapping[str, object], entry).get("case_label")
        if isinstance(label, str):
            labels.add(label)
    return labels


def _parse_perf_file(path: Path) -> dict[str, float]:
    entries = _parse_perf_entries(path)
    return PerfValueMap(
        {latency_id: entry.numeric_value for latency_id, entry in entries.items()},
        comparison_modes={latency_id: entry.comparison_mode for latency_id, entry in entries.items()},
    )


def _parse_perf_entries(path: Path) -> dict[str, PerfEntry]:
    return _parse_perf_entries_strict(path).entries


def _parse_perf_entries_strict(path: Path) -> PerfParseOutcome:
    return _parse_perf_entries_impl(path, tolerate_latency_errors=False)


def _parse_perf_entries_for_comparison(
    path: Path,
    *,
    skip_latency_errors: bool,
    metric_source: MetricSource,
) -> PerfParseOutcome:
    return _parse_perf_entries_impl(
        path,
        tolerate_latency_errors=skip_latency_errors,
        metric_source=metric_source,
    )


def _parse_perf_entries_impl(
    path: Path,
    *,
    tolerate_latency_errors: bool,
    metric_source: MetricSource = "auto",
) -> PerfParseOutcome:
    lines = path.read_text(encoding="utf-8").splitlines()
    return _parse_perf_entries_from_jsonl(
        path,
        lines,
        tolerate_latency_errors=tolerate_latency_errors,
        metric_source=metric_source,
    )


def _parse_required_perf_file(path: Path, required_latency_ids: RequiredLatencyIds) -> dict[str, float]:
    entries = _parse_required_perf_entries(path, required_latency_ids)
    values: dict[str, float] = {}
    for latency_id, entry in entries.items():
        values[latency_id] = entry.numeric_value
    return values


def _parse_required_perf_entries(
    path: Path, required_latency_ids: RequiredLatencyIds
) -> dict[str, PerfEntry]:
    return _parse_required_perf_entries_strict(path, required_latency_ids).entries


def _parse_required_perf_entries_strict(
    path: Path, required_latency_ids: RequiredLatencyIds
) -> PerfParseOutcome:
    return _parse_required_perf_entries_impl(
        path, required_latency_ids, tolerate_latency_errors=False
    )


def _parse_required_perf_entries_for_comparison(
    path: Path,
    required_latency_ids: RequiredLatencyIds,
    *,
    skip_latency_errors: bool,
    metric_source: MetricSource,
) -> PerfParseOutcome:
    return _parse_required_perf_entries_impl(
        path,
        required_latency_ids,
        tolerate_latency_errors=skip_latency_errors,
        metric_source=metric_source,
    )


def _parse_required_perf_entries_impl(
    path: Path,
    required_latency_ids: RequiredLatencyIds,
    *,
    tolerate_latency_errors: bool,
    metric_source: MetricSource = "auto",
) -> PerfParseOutcome:
    required_ids, comparison_modes = _resolve_required_latency_requirements(required_latency_ids)
    if not required_ids:
        return PerfParseOutcome(entries={}, skipped_latency_errors={})

    lines = path.read_text(encoding="utf-8").splitlines()
    full_outcome = _parse_perf_entries_from_jsonl(
        path,
        lines,
        tolerate_latency_errors=tolerate_latency_errors,
        metric_source=metric_source,
        required_ids=required_ids,
        comparison_modes=comparison_modes,
    )
    missing_ids = sorted(
        required_ids
        - set(full_outcome.entries)
        - set(full_outcome.skipped_latency_errors)
    )
    if missing_ids:
        raise ValueError(f"{path} is missing required latency ids: {missing_ids}")
    return full_outcome


def _parse_perf_entries_from_jsonl(
    path: Path,
    lines: list[str],
    *,
    tolerate_latency_errors: bool,
    metric_source: MetricSource = "auto",
    required_ids: set[str] | None = None,
    comparison_modes: dict[str, ComparisonMode] | None = None,
) -> PerfParseOutcome:
    entries: dict[str, PerfEntry] = {}
    skipped_latency_errors: dict[str, str] = {}
    for line_no, raw_line in enumerate(lines, start=1):
        record = _decode_perf_jsonl_record(path, line_no, raw_line)
        if record is None:
            continue
        outcome = _perf_record_outcome(
            path,
            line_no,
            record,
            entries=entries,
            tolerate_latency_errors=tolerate_latency_errors,
            metric_source=metric_source,
            required_ids=required_ids,
            comparison_modes=comparison_modes,
        )
        if outcome.latency_id is None:
            continue
        if outcome.skipped_error is not None:
            skipped_latency_errors[outcome.latency_id] = outcome.skipped_error
        elif outcome.entry is not None:
            entries[outcome.latency_id] = outcome.entry
    if not entries and not skipped_latency_errors:
        if required_ids is not None:
            return PerfParseOutcome(entries={}, skipped_latency_errors={})
        raise ValueError(f"{path} did not contain any JSONL performance records")
    return PerfParseOutcome(entries=entries, skipped_latency_errors=skipped_latency_errors)


@dataclass(frozen=True)
class _PerfRecordOutcome:
    """One decoded JSONL record's contribution: a selected entry, a skip, or neither."""

    latency_id: str | None
    entry: PerfEntry | None
    skipped_error: str | None


def _decode_perf_jsonl_record(path: Path, line_no: int, raw_line: str) -> dict[str, object] | None:
    line = raw_line.strip()
    if not line:
        return None
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path}:{line_no} must contain a JSONL record; invalid JSON: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{path}:{line_no} JSONL record must be an object")
    return cast(dict[str, object], parsed)


def _perf_record_outcome(
    path: Path,
    line_no: int,
    record: dict[str, object],
    *,
    entries: dict[str, PerfEntry],
    tolerate_latency_errors: bool,
    metric_source: MetricSource,
    required_ids: set[str] | None,
    comparison_modes: dict[str, ComparisonMode] | None,
) -> _PerfRecordOutcome:
    case_label = str(record["case_label"])
    latency_id = f"latency-{case_label}"
    matched_latency_id = latency_id
    if required_ids is not None:
        resolved_latency_id = _resolve_required_latency_id_match(latency_id, required_ids)
        if resolved_latency_id is None:
            return _PerfRecordOutcome(None, None, None)
        matched_latency_id = resolved_latency_id
    if matched_latency_id in entries:
        raise ValueError(f"{path}:{line_no} duplicates latency id '{matched_latency_id}'")
    error_text = _perf_record_error_text(path, line_no, record)
    if error_text is not None and not error_text.startswith("no resolved kernels matched"):
        message = (
            f"{path}:{line_no} cannot compare '{latency_id}' because "
            f"'error_message: {error_text}' is present"
        )
        if tolerate_latency_errors:
            return _PerfRecordOutcome(matched_latency_id, None, message)
        raise ValueError(message)
    entry = _perf_entry_from_record(
        path,
        line_no,
        record,
        latency_id,
        matched_latency_id,
        metric_source=metric_source,
        comparison_modes=comparison_modes,
    )
    return _PerfRecordOutcome(matched_latency_id, entry, None)


def _perf_record_error_text(path: Path, line_no: int, record: dict[str, object]) -> str | None:
    error_message_raw = record.get("error_message")
    if error_message_raw is not None and not isinstance(error_message_raw, str):
        raise ValueError(f"{path}:{line_no} 'error_message' must be a string or null")
    return str(error_message_raw) if error_message_raw is not None else None


def _perf_entry_from_record(
    path: Path,
    line_no: int,
    record: dict[str, object],
    latency_id: str,
    matched_latency_id: str,
    *,
    metric_source: MetricSource,
    comparison_modes: dict[str, ComparisonMode] | None,
) -> PerfEntry:
    kernel_avg_time_us_raw = record.get("kernel_avg_time_us")
    total_op_avg_time_us_raw = record.get("total_op_avg_time_us")
    effective_source = metric_source
    if metric_source == "auto" and comparison_modes is not None:
        mode = comparison_modes.get(matched_latency_id)
        if mode == "total-op":
            effective_source = "total-op"
    if kernel_avg_time_us_raw is not None:
        return _kernel_metric_entry(
            path,
            line_no,
            latency_id,
            kernel_avg_time_us_raw=kernel_avg_time_us_raw,
            total_op_avg_time_us_raw=total_op_avg_time_us_raw,
            effective_source=effective_source,
        )
    if total_op_avg_time_us_raw is not None:
        if effective_source == "kernel":
            raise ValueError(
                f"{path}:{line_no} requires kernel latency for '{latency_id}' "
                "under --metric-source kernel"
            )
        value = float(cast("int | float | str", total_op_avg_time_us_raw))
        return PerfEntry(
            display_value=f"NA ({_format_total_op_display(value)})",
            numeric_value=value,
            comparison_mode="total-op",
        )
    raise ValueError(f"{path}:{line_no} has no usable metric for '{latency_id}'")


def _kernel_metric_entry(
    path: Path,
    line_no: int,
    latency_id: str,
    *,
    kernel_avg_time_us_raw: object,
    total_op_avg_time_us_raw: object,
    effective_source: MetricSource,
) -> PerfEntry:
    if effective_source == "total-op":
        if total_op_avg_time_us_raw is None:
            raise ValueError(
                f"{path}:{line_no} requires total-op for '{latency_id}' "
                "under --metric-source total-op but total_op_avg_time_us is null"
            )
        value = float(cast("int | float | str", total_op_avg_time_us_raw))
        return PerfEntry(
            display_value=_format_total_op_display(value),
            numeric_value=value,
            comparison_mode="total-op",
        )
    value = float(cast("int | float | str", kernel_avg_time_us_raw))
    return PerfEntry(
        display_value=format_latency_value(value),
        numeric_value=value,
        comparison_mode="latency",
    )


def _resolve_required_latency_requirements(
    required_latency_ids: RequiredLatencyIds,
) -> RequiredLatencyIdResolution:
    required_ids = set(required_latency_ids)
    comparison_modes: dict[str, ComparisonMode] = {latency_id: "latency" for latency_id in required_ids}
    if isinstance(required_latency_ids, dict):
        typed_required_latency_ids = cast(object, required_latency_ids)
        for latency_id in required_ids:
            value = cast(dict[str, object], typed_required_latency_ids)[latency_id]
            if isinstance(value, PerfEntry):
                comparison_modes[latency_id] = value.comparison_mode
        return required_ids, comparison_modes
    raw_modes = (
        required_latency_ids.comparison_modes
        if isinstance(required_latency_ids, PerfValueMap)
        else None
    )
    if raw_modes is not None:
        for latency_id in required_ids:
            mode = raw_modes.get(latency_id)
            if mode in ("latency", "total-op"):
                comparison_modes[latency_id] = mode
    return required_ids, comparison_modes


def _resolve_required_latency_id_match(
    latency_id: str,
    required_ids: set[str],
) -> str | None:
    if latency_id in required_ids:
        return latency_id
    alias = _legacy_msprof_latency_id_alias(latency_id)
    if alias is not None and alias in required_ids:
        return alias
    return None


def _legacy_msprof_latency_id_alias(latency_id: str) -> str | None:
    case_prefix = "latency-case-"
    if latency_id.startswith(case_prefix):
        case_index = latency_id.removeprefix(case_prefix)
        if case_index.isdigit():
            return f"latency-{case_index}"
        return None
    latency_prefix = "latency-"
    if latency_id.startswith(latency_prefix):
        case_index = latency_id.removeprefix(latency_prefix)
        if case_index.isdigit():
            return f"latency-case-{case_index}"
    return None


def _rebuild_entry_for_mode(
    path: Path,
    latency_id: str,
    *,
    target_mode: ComparisonMode,
) -> PerfEntry:
    metric_source: MetricSource = "kernel" if target_mode == "latency" else "total-op"
    return _parse_required_perf_entries_for_comparison(
        path,
        {latency_id},
        skip_latency_errors=False,
        metric_source=metric_source,
    ).entries[latency_id]


def _format_total_op_display(value: float) -> str:
    return f"total-op={format_latency_value(value)}"


def _format_delta_percent(baseline: float, compare: float) -> str:
    if baseline == 0:
        if compare == 0:
            return "0.00%"
        return "inf"
    delta = ((compare - baseline) / baseline) * 100.0
    return f"{delta:.2f}%"


def _collect_invalid_metric_errors(
    baseline: dict[str, float],
    compare: dict[str, float],
    *,
    baseline_perf: Path,
    compare_perf: Path,
) -> dict[str, str]:
    errors: dict[str, str] = {}
    for latency_id in sorted(set(baseline) & set(compare)):
        baseline_value = baseline[latency_id]
        compare_value = compare[latency_id]
        if baseline_value <= 0:
            errors[latency_id] = (
                f"{baseline_perf} cannot compare '{latency_id}' because baseline timing "
                f"{baseline_value} must be > 0"
            )
            continue
        if compare_value <= 0:
            errors[latency_id] = (
                f"{compare_perf} cannot compare '{latency_id}' because compare timing "
                f"{compare_value} must be > 0"
            )
    return errors


def _normalize_perf_pair_for_comparison(
    *,
    baseline_perf: Path,
    compare_perf: Path,
    baseline_entries: dict[str, PerfEntry],
    compare_entries: dict[str, PerfEntry],
    metric_source: MetricSource,
    tolerate_latency_errors: bool,
) -> PerfPairOutcome:
    if metric_source != "auto":
        return PerfPairOutcome(
            baseline_entries=dict(baseline_entries),
            compare_entries=dict(compare_entries),
            skipped_latency_errors={},
        )

    normalized_baseline = dict(baseline_entries)
    normalized_compare = dict(compare_entries)
    skipped_latency_errors: dict[str, str] = {}
    shared_ids = sorted(set(normalized_baseline) & set(normalized_compare))
    for latency_id in shared_ids:
        baseline_entry = normalized_baseline[latency_id]
        compare_entry = normalized_compare[latency_id]
        if baseline_entry.comparison_mode == compare_entry.comparison_mode:
            continue
        try:
            normalized_baseline[latency_id] = _rebuild_entry_for_mode(
                baseline_perf,
                latency_id,
                target_mode="total-op",
            )
            normalized_compare[latency_id] = _rebuild_entry_for_mode(
                compare_perf,
                latency_id,
                target_mode="total-op",
            )
        except ValueError as exc:
            if not tolerate_latency_errors:
                raise
            skipped_latency_errors[latency_id] = str(exc)
            normalized_baseline.pop(latency_id, None)
            normalized_compare.pop(latency_id, None)
    return PerfPairOutcome(
        baseline_entries=normalized_baseline,
        compare_entries=normalized_compare,
        skipped_latency_errors=skipped_latency_errors,
    )


def _summarize_perf_metrics(
    baseline: dict[str, float],
    compare: dict[str, float],
) -> PerfMetricSummary:
    case_values = [
        (latency_id, baseline[latency_id], compare[latency_id])
        for latency_id in sorted(baseline)
    ]
    if not case_values:
        return PerfMetricSummary(None, None, 0, ())
    if any(
        baseline_value <= 0 or compare_value <= 0
        for _, baseline_value, compare_value in case_values
    ):
        return PerfMetricSummary(None, None, 0, ())

    improvements = [
        (baseline_value - compare_value) / baseline_value
        for _, baseline_value, compare_value in case_values
    ]
    ratios = [baseline_value / compare_value for _, baseline_value, compare_value in case_values]
    avg_improvement = sum(improvements) / len(improvements)
    geomean_speedup = math.exp(sum(math.log(ratio) for ratio in ratios) / len(ratios))
    regressed_case_count = sum(ratio < 1.0 for ratio in ratios)
    ordered_cases = tuple(
        sorted(
            (
                (latency_id, ratio, baseline_value)
                for (latency_id, baseline_value, _), ratio in zip(case_values, ratios)
            ),
            key=lambda case: case[1],
        )
    )
    return PerfMetricSummary(
        avg_improvement,
        geomean_speedup,
        regressed_case_count,
        ordered_cases,
    )


def _review_disposition(geomean_speedup: float | None, speedups: list[float]) -> str:
    if geomean_speedup is None or not speedups:
        return "inconclusive"
    if geomean_speedup >= 1.0 and not any(value < 1.0 for value in speedups):
        return "uniform-keep"
    if any(value < 1.0 for value in speedups) and any(value > 1.0 for value in speedups):
        return "localization-candidate"
    return "uniform-reject"


def _format_improvement_percent(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value * 100:+.1f}%"


def _format_speedup(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.2f}x"


def _summarize_metric_source(
    entries: dict[str, PerfEntry],
    *,
    metric_source: MetricSource = "auto",
) -> str:
    if not entries:
        return "unknown"
    if metric_source == "kernel":
        return "kernel"
    if metric_source == "total-op":
        return "total-op"
    modes = {entry.comparison_mode for entry in entries.values()}
    if modes == {"latency"}:
        return "kernel"
    if modes == {"total-op"}:
        return "total-op"
    return "mixed (kernel + total-op fallback)"
