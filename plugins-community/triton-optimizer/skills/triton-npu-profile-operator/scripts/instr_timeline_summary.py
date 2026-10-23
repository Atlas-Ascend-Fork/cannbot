# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Summarize an msprof InstrTimeline trace without assuming pipe overlap semantics."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, NamedTuple, Sequence, cast


_ISSUE_NAMES = frozenset(("VF", "VF_SIMT", "MMAD"))


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else None
    if isinstance(value, str):
        try:
            result = float(value)
        except ValueError:
            return None
        return result if math.isfinite(result) else None
    return None


def _trace_events(path: Path) -> list[Mapping[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("trace JSON must contain an object")
    raw_events: Any = cast(Any, payload).get("traceEvents")
    if not isinstance(raw_events, list):
        raise ValueError("trace JSON has no traceEvents list")
    events: list[Mapping[str, Any]] = []
    for raw_event in cast(list[Any], raw_events):
        if not isinstance(raw_event, Mapping):
            continue
        event: Mapping[str, Any] = cast(Mapping[str, Any], raw_event)
        if event.get("ph") != "X" or not isinstance(event.get("name"), str):
            continue
        if _number(event.get("ts")) is None or _number(event.get("dur")) is None:
            continue
        events.append(event)
    if not events:
        raise ValueError("traceEvents contains no usable duration events")
    return events


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    weight = index - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _format(value: float | None) -> str:
    if value is None:
        return "null"
    return f"{value:.6f}".rstrip("0").rstrip(".")


class _EventGroups(NamedTuple):
    """Events grouped by stream and by (tid, name) class."""
    streams: dict[tuple[str, str], list[Mapping[str, Any]]]
    class_durations: dict[tuple[str, str], float]
    class_counts: Counter[tuple[str, str]]
    pcs: dict[str, set[str]]


def _group_events(event_list: list[Mapping[str, Any]]) -> _EventGroups:
    streams: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    class_durations: dict[tuple[str, str], float] = defaultdict(float)
    class_counts: Counter[tuple[str, str]] = Counter()
    pcs: dict[str, set[str]] = defaultdict(set)

    for event in event_list:
        tid = str(event.get("tid", "UNKNOWN"))
        pid = str(event.get("pid", "UNKNOWN"))
        name = str(event["name"])
        ts = _number(event["ts"])
        dur = _number(event["dur"])
        if ts is None or dur is None:
            continue
        stream = (tid, pid)
        streams[stream].append(event)
        class_durations[(tid, name)] += dur
        class_counts[(tid, name)] += 1
        raw_args: Any = event.get("args")
        if isinstance(raw_args, Mapping):
            args: Mapping[str, Any] = cast(Mapping[str, Any], raw_args)
            if args.get("pc_addr") is not None:
                pcs[tid].add(str(args["pc_addr"]))

    return _EventGroups(
        streams=streams,
        class_durations=class_durations,
        class_counts=class_counts,
        pcs=pcs,
    )


def _collect_issue_intervals(
    streams: dict[tuple[str, str], list[Mapping[str, Any]]]
) -> dict[tuple[str, str], list[float]]:
    issue_intervals: dict[tuple[str, str], list[float]] = defaultdict(list)
    for (tid, pid), stream_events in streams.items():
        ordered = sorted(stream_events, key=lambda item: _number(item["ts"]) or 0.0)
        last_issue_ts: float | None = None
        for event in ordered:
            if str(event["name"]) not in _ISSUE_NAMES:
                continue
            current_ts = _number(event["ts"])
            if current_ts is None:
                continue
            if last_issue_ts is not None:
                issue_intervals[(tid, pid)].append(current_ts - last_issue_ts)
            last_issue_ts = current_ts
    return issue_intervals


def _trace_wall_span(event_list: list[Mapping[str, Any]]) -> float:
    wall_start = min(_number(event["ts"]) or 0.0 for event in event_list)
    wall_end = max(
        (_number(event["ts"]) or 0.0) + (_number(event["dur"]) or 0.0)
        for event in event_list
    )
    return wall_end - wall_start


def _build_streams_output(
    streams: dict[tuple[str, str], list[Mapping[str, Any]]],
    issue_intervals: dict[tuple[str, str], list[float]],
) -> list[dict[str, Any]]:
    streams_output: list[dict[str, Any]] = []
    for (tid, pid), stream_events in sorted(streams.items()):
        start = min(_number(event["ts"]) or 0.0 for event in stream_events)
        end = max(
            (_number(event["ts"]) or 0.0) + (_number(event["dur"]) or 0.0)
            for event in stream_events
        )
        intervals = issue_intervals.get((tid, pid), [])
        streams_output.append(
            {
                "tid": tid,
                "pid": pid,
                "event_count": len(stream_events),
                "wall_start_us": start,
                "wall_end_us": end,
                "wall_span_us": end - start,
                "issue_interval_us": {
                    "p10": _percentile(intervals, 0.10),
                    "p50": _percentile(intervals, 0.50),
                    "p90": _percentile(intervals, 0.90),
                    "sample_count": len(intervals),
                },
            }
        )
    return streams_output


def _build_classes_output(
    class_durations: dict[tuple[str, str], float],
    class_counts: Counter[tuple[str, str]],
    wall_span: float,
) -> list[dict[str, Any]]:
    classes_output: list[dict[str, Any]] = []
    for (tid, name), duration in sorted(class_durations.items()):
        classes_output.append(
            {
                "tid": tid,
                "name": name,
                "event_count": class_counts[(tid, name)],
                "duration_us": duration,
                "duration_share_of_trace_wall": duration / wall_span if wall_span > 0 else None,
            }
        )
    return classes_output


def summarize(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    event_list = list(events)
    groups = _group_events(event_list)
    issue_intervals = _collect_issue_intervals(groups.streams)
    wall_span = _trace_wall_span(event_list)

    return {
        "event_count": len(event_list),
        "trace_wall_span_us": wall_span,
        "streams": _build_streams_output(groups.streams, issue_intervals),
        "classes": _build_classes_output(groups.class_durations, groups.class_counts, wall_span),
        "distinct_pc_count_by_tid": {tid: len(values) for tid, values in sorted(groups.pcs.items())},
        "notes": [
            "Durations overlap; duration shares are descriptive and may exceed 1.0.",
            "Issue intervals are timestamp differences between consecutive VF/VF_SIMT/MMAD events.",
            "Bubble or idle-gap estimates are intentionally omitted.",
        ],
    }


def _markdown(summary: Mapping[str, Any]) -> str:
    lines = [
        "# InstrTimeline summary",
        "",
        f"- Events: {summary['event_count']}",
        f"- Trace wall span (us): {_format(summary['trace_wall_span_us'])}",
        "- Duration shares can overlap and are not busy percentages.",
        "",
        "## Streams",
        "",
        "| tid | pid | events | wall span (us) | issue p10 | issue p50 | issue p90 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for stream in summary["streams"]:
        intervals = stream["issue_interval_us"]
        lines.append(
            f"| {stream['tid']} | {stream['pid']} | {stream['event_count']} | "
            f"{_format(stream['wall_span_us'])} | {_format(intervals['p10'])} | "
            f"{_format(intervals['p50'])} | {_format(intervals['p90'])} |"
        )
    lines += [
        "",
        "## Event classes",
        "",
        "| tid | name | events | duration (us) | share of trace wall |",
        "|---|---|---:|---:|---:|",
    ]
    for event_class in summary["classes"]:
        share = event_class["duration_share_of_trace_wall"]
        lines.append(
            f"| {event_class['tid']} | {event_class['name']} | {event_class['event_count']} | "
            f"{_format(event_class['duration_us'])} | {_format(share)} |"
        )
    lines += ["", "## Distinct PCs", ""]
    for tid, count in summary["distinct_pc_count_by_tid"].items():
        lines.append(f"- `{tid}`: {count}")
    lines += ["", "## Notes", ""]
    lines.extend(f"- {note}" for note in summary["notes"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_json", type=Path, help="path to msprof trace.json")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()
    result = summarize(_trace_events(args.trace_json))
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(_markdown(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
