#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Network msprof CLI and op_summary reader; no application instrumentation."""

import argparse
import csv
from collections import defaultdict
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from report_common import (
    check_receipt,
    check_report_output,
    kernel_overview,
    positive,
    receipt,
    require,
    write_report_files,
)

OPTIONS = ["--task-time=l0", "--ai-core=off", "--ascendcl=off", "--sys-lp=off"]


def find_tool(requested=None):
    candidates = [requested] if requested else ["msprof"] + [
        str(Path(os.environ[key]) / "tools/profiler/bin/msprof")
        for key in ("ASCEND_HOME_PATH", "ASCEND_HOME") if os.environ.get(key)
    ]
    for candidate in candidates:
        found = shutil.which(str(candidate))
        if found:
            return str(Path(found).resolve())
    raise ValueError("network msprof unavailable in the selected CANN environment")


def capabilities(tool):
    run = subprocess.run([tool, "--help"], capture_output=True, text=True, timeout=30)
    require(run.returncode == 0, "msprof --help failed: " + run.stdout + run.stderr)
    return {"tool": receipt(tool), "help": run.stdout + run.stderr,
            "options": sorted(set(re.findall(r"--[a-z][a-z0-9-]*", run.stdout + run.stderr)))}


def build_command(tool, runner, output, options=None, supported=None):
    require(isinstance(runner, list) and runner
            and all(isinstance(v, str) and v for v in runner), "application argv required")
    options = OPTIONS if options is None else options
    require(isinstance(options, list), "options must be --name=value argv entries")
    names = []
    for option in options:
        require(isinstance(option, str) and re.fullmatch(r"--[a-z][a-z0-9-]*=.+", option),
                "options must be --name=value argv entries")
        name = option.split("=", 1)[0]
        require(name not in names and name not in ("--output", "--application", "--environment"),
                "duplicate or launch-overriding msprof option: " + name)
        names.append(name)
    if supported is not None:
        require(set(names + ["--output"]).issubset(supported), "installed msprof lacks selected options")
    # Positional argv avoids re-parsing shell quoting in --application.
    return [tool, "--output=" + str(Path(output).resolve()), *options, *runner]


def inspect_collection(root):
    root = Path(root).resolve(strict=True)
    files = [root] if root.is_file() else sorted(root.rglob("op_summary*.csv"))
    records, evidence, seen = [], {}, set()
    required = {"Device_id", "Task ID", "Stream ID", "Op Name",
                "Task Start Time(us)", "Task Duration(us)"}
    for path in files:
        source = receipt(path)
        profile = next((p for p in path.parents if (p / "host/info.json").is_file()), None)
        require(profile is not None, f"missing host/info.json for {path}")
        process = receipt(profile / "host/info.json")
        metadata = json.loads(Path(process["path"]).read_text())
        pid = str(metadata.get("pid", ""))
        require(pid.isdecimal() and int(pid) > 0, "missing real process ID in host/info.json")
        pid = int(pid)
        evidence[source["path"]], evidence[process["path"]] = source, process
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            require(required.issubset(fields) and len(fields) == len(set(fields)),
                    f"missing or duplicate op_summary fields: {path}")
            for line, row in enumerate(reader, 2):
                require(None not in row and all(v is not None for v in row.values()),
                        f"CSV column count mismatch: {path}:{line}")
                start = row["Task Start Time(us)"].strip()
                try:
                    timestamp = Decimal(start)
                except ArithmeticError as error:
                    raise ValueError(f"invalid task timestamp: {path}:{line}") from error
                require(timestamp.is_finite(), f"invalid task timestamp: {path}:{line}")
                device, task, stream = (int(row[key]) for key in ("Device_id", "Task ID", "Stream ID"))
                require((profile / f"device_{device}").is_dir(),
                        f"Device_id does not match capture device directory: {device}")
                key = (pid, device, stream, task, timestamp)
                require(key not in seen, "duplicate device task in op_summary exports")
                seen.add(key)
                duration = row["Task Duration(us)"].strip()
                records.append({"source": source, "line": line, "process": process, "pid": pid,
                                "op_name": row["Op Name"], "op_type": row.get("OP Type"),
                                "task_type": row.get("Task Type"), "device_id": device,
                                "stream_id": stream, "task_id": task, "start_us": start,
                                "duration_us": None if duration in ("N/A", "NA", "") else float(duration),
                                "raw": row})
    records.sort(key=lambda r: (Decimal(r["start_us"]), r["source"]["path"], r["line"]))
    return {"provider": "msprof", "collection_root": str(root), "records": records,
            "evidence": list(evidence.values()), "status": "parsed" if records else "incomplete"}


def task_table(source):
    return source.with_name(source.name.replace("op_summary", "task_time", 1))


def overview(data, receipts=None):
    """Add runtime names when the same export identifies the same device task."""
    result = kernel_overview(data)
    if len({r["process"]["path"] for r in data["records"]}) != 1:
        return result
    groups = {(row["device"], row["pid"], row["name"]): row for row in result["kernels"]}
    by_file = defaultdict(dict)
    for r in data["records"]:
        key = (str(r["device_id"]), str(r["stream_id"]), str(r["task_id"]), r["start_us"])
        by_file[Path(r["source"]["path"])][key] = groups[r["device_id"], r["pid"], r["op_name"]]
    for source, wanted in by_file.items():
        timeline = task_table(source)
        if not timeline.is_file() or timeline == source:
            continue
        if receipts is not None:
            original = receipts.get(str(timeline))
            if original is None:
                continue
            check_receipt(original)
        keys = ("Device_id", "stream_id", "task_id", "task_start(us)")
        hits = {}
        try:
            with timeline.open(newline="", encoding="utf-8-sig") as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames or []
                if len(fields) != len(set(fields)) or not set((*keys, "kernel_name")).issubset(fields):
                    continue
                for line, task in enumerate(reader, 2):
                    key = tuple((task[k] or "").strip() for k in keys)
                    if key in wanted:
                        hits[key] = (task["kernel_name"], line) if key not in hits else None
        except (OSError, csv.Error, UnicodeError):
            continue
        root = Path(data["collection_root"])
        path = str(timeline.relative_to(root)) if root in timeline.parents else str(timeline)
        for key, hit in hits.items():
            if hit and hit[0] and hit[0] not in ("N/A", "NA"):
                names = wanted[key].setdefault("runtime_names", {})
                hint = names.setdefault(hit[0], {"launches": 0, "first": [path, hit[1]]})
                hint["launches"] += 1
    return result


def select_records(data, identity):
    targets = identity.get("kernels")
    if targets == "all":
        records = data["records"]
        require(records and all(positive(row["duration_us"]) for row in records)
                and len({(row["process"]["path"], row["device_id"]) for row in records}) == 1,
                "isolated invocation needs timed launches from one process and device")
        return records
    require(isinstance(targets, list) and targets, "describe the target invocation with a nonempty kernels list")
    by_name = defaultdict(list)
    for row in data["records"]:
        by_name[row["op_name"]].append(row)
    selected, used = [], set()
    for target in targets:
        require(isinstance(target, dict) and set(target) <= {"name", "occurrence"}
                and isinstance(target.get("name"), str) and target["name"].strip(),
                "each kernel needs an exact op_summary name and optional occurrence")
        matches = by_name[target["name"]]
        if "occurrence" in target:
            index = target["occurrence"]
            require(type(index) is int and 0 <= index < len(matches), "kernel occurrence out of range")
            matches = [matches[index]]
        require(len(matches) == 1, "target ambiguous/missing; select each kernel occurrence explicitly")
        record = matches[0]
        key = (record["source"]["path"], record["line"])
        require(key not in used, "same launch selected more than once")
        used.add(key)
        require(positive(record["duration_us"]), "Task Duration must be finite and positive")
        selected.append(record)
    return selected


def invocation(records):
    return {"duration_us": float(sum(Decimal(r["raw"]["Task Duration(us)"]) for r in records)),
            "statistic": "sum_of_target_kernel_durations", "records": records}


def measurements(records, binding=None):
    return [{"kernel": r["op_name"], "device": r["device_id"], "pid": r["pid"],
             "stream_id": r["stream_id"], "task_id": r["task_id"], "duration_us": r["duration_us"],
             "evidence": r["source"], "line": r["line"],
             **({"application_device": binding["application_device"],
                 "physical_device": binding["physical_device"], "device_namespace": "physical"} if binding else {})}
            for r in records]


def build_report(root, case_id, identity=None, protocol=None, conditions=None):
    data = inspect_collection(root)
    report = report_from_data(data, case_id, identity, protocol, conditions)
    sources = {Path(row["source"]["path"]) for row in data["records"]}
    report["evidence"].extend(receipt(path) for path in sorted({task_table(p) for p in sources} - sources)
                              if path.is_file())
    return report


def report_from_data(data, case_id, identity=None, protocol=None, conditions=None, binding=None):
    result = {
        **data,
        "case_id": case_id,
        "identity": identity or {},
        "protocol": protocol or {},
        "conditions": conditions or {},
        "performance_eligible": False,
        "status": "diagnostic_valid"
        if data["records"] and all(positive(r["duration_us"]) for r in data["records"])
        else "incomplete",
        "measurements": measurements(data["records"], binding),
        "limitations": [],
    }
    if identity:
        result["invocation"] = invocation(select_records(data, identity))
    return result


def write_report(report, out):
    out = Path(out).resolve()
    check_report_output(report, out)
    lines = ["# msprof 专项报告", "", f"case: {report['case_id']}", ""]
    if report.get("invocation"):
        lines += [f"目标调用 Σkernel = {report['invocation']['duration_us']} µs", ""]
    lines += ["| kernel | device | PID | stream/task | duration (µs) | source |", "|---|---:|---:|---|---:|---|"]
    for r in report["records"]:
        name = r["op_name"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {name} | {r['device_id']} | {r['pid']} | {r['stream_id']}/{r['task_id']} | "
            f"{r['duration_us']} | {r['source']['path']}:{r['line']} |"
        )
    report_path = str(out / "profile-report.json")
    write_report_files(out, {**report, "report": report_path}, lines)
    report["report"] = report_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    env = sub.add_parser("env")
    env.add_argument("--tool")
    command = sub.add_parser("command")
    command.add_argument("--tool", default="msprof")
    command.add_argument("--output", required=True)
    command.add_argument("--option", action="append", help="replace defaults with explicit --name=value entries")
    command.add_argument("runner", nargs=argparse.REMAINDER)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("root", type=Path)
    inspect.add_argument("--out", type=Path)
    report = sub.add_parser("report")
    report.add_argument("root", type=Path)
    report.add_argument("--case-id")
    report.add_argument("--identity", type=Path, help="target kernels list for an unbound report")
    report.add_argument("--plan", type=Path)
    report.add_argument("--attempt", type=Path)
    report.add_argument("--conditions", type=Path)
    report.add_argument("--out", type=Path, required=True)
    for action in (inspect, report):
        action.add_argument("--brief", action="store_true", help="show names, counts and device time on stdout")
    args = parser.parse_args()
    try:
        if args.action == "env":
            result = capabilities(find_tool(args.tool))
        elif args.action == "command":
            runner = args.runner[1:] if args.runner[:1] == ["--"] else args.runner
            result = {"argv": build_command(args.tool, runner, args.output, args.option)}
        elif args.action == "inspect":
            result = inspect_collection(args.root)
            if args.out:
                with args.out.open("x") as stream:
                    json.dump(result, stream, indent=2, allow_nan=False)
        else:
            conditions = json.loads(args.conditions.read_text()) if args.conditions else None
            if args.plan or args.attempt:
                require(args.plan and args.attempt and not args.identity and not args.case_id,
                        "bound reports take case and identity from --plan and --attempt together")
                import report_contract
                adapter = report_contract.backend({"provider": "msprof"})
                require(args.root.resolve() == adapter.output_path(json.loads(args.attempt.read_text())),
                        "report root differs from bound capture")
                result = adapter.build_bound_report(args.plan, args.attempt, args.out, conditions)
            else:
                require(args.case_id, "--case-id required for an unbound report")
                identity = json.loads(args.identity.read_text()) if args.identity else None
                result = build_report(args.root, args.case_id, identity, conditions=conditions)
                write_report(result, args.out)
        brief = getattr(args, "brief", False)
        if brief:
            if args.action == "report":
                import report_contract
                result = report_contract.backend(result).overview(result)
            else:
                result = overview(result)
        print(json.dumps(result, ensure_ascii=False,
                         indent=None if brief else 2, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, ArithmeticError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "failed", "reason": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
