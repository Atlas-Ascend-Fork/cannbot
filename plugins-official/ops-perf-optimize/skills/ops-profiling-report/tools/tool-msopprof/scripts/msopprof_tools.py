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

"""Small msopprof capability, argv and CSV helpers; target execution belongs to the caller."""

import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from report_common import check_report_output, kernel_overview, receipt, write_report_files


def find_tool(requested=None):
    if requested:
        candidates = [requested]
    else:
        candidates = ["msopprof"]
        for key in ("ASCEND_HOME_PATH", "ASCEND_HOME"):
            if os.environ.get(key):
                candidates.append(
                    str(Path(os.environ[key]) / "tools/msopprof/bin/msopprof")
                )
        candidates.append("msprof")
        for key in ("ASCEND_HOME_PATH", "ASCEND_HOME"):
            if os.environ.get(key):
                candidates.append(
                    str(Path(os.environ[key]) / "tools/profiler/bin/msprof")
                )
    for name in candidates:
        found = shutil.which(str(name))
        if found:
            path = Path(found).resolve()
            return [str(path), "op"] if Path(name).name == "msprof" else [str(path)]
    raise ValueError(
        "msopprof / msprof op unavailable in the selected CANN environment"
    )


def capabilities(prefix):
    help_run = subprocess.run([*prefix, "--help"], capture_output=True, text=True, errors="replace", timeout=30)
    help_text = help_run.stdout + help_run.stderr
    if help_run.returncode:
        raise ValueError("msopprof --help failed: " + help_text)
    try:
        run = subprocess.run([*prefix, "--version"], capture_output=True, text=True, errors="replace", timeout=3)
        version = {"returncode": run.returncode, "text": run.stdout + run.stderr}
    except (OSError, subprocess.TimeoutExpired) as error:
        version = {"returncode": None, "text": str(error)}
    return {
        "provider": "msopprof",
        "command_prefix": prefix,
        "tool": receipt(prefix[0]),
        "environment": {
            key: os.environ.get(key)
            for key in (
                "ASCEND_HOME_PATH",
                "ASCEND_HOME",
                "ASCEND_OPP_PATH",
                "ASCEND_RT_VISIBLE_DEVICES",
            )
        },
        "npu_smi": shutil.which("npu-smi"),
        "options": sorted(set(re.findall(r"--[a-z][a-z0-9-]*", help_text))),
        "version": version,
        "help": help_text,
    }


def build_command(
    prefix,
    runner,
    output,
    *,
    metrics=None,
    preset=None,
    warmup=3,
    replay_mode="kernel",
    launch_count=1,
    kernel_name=None,
    supported=None,
    extra_options=None,
):
    if not runner or not all(isinstance(v, str) and v for v in runner):
        raise ValueError("application argv required")
    if type(warmup) is not int or warmup < 0:
        raise ValueError("--warm-up must be a nonnegative integer")
    if type(launch_count) is not int or launch_count < 1:
        raise ValueError("--launch-count must be a positive integer")
    pairs = [
        ("--output", str(Path(output).resolve())),
        ("--warm-up", str(warmup)),
        ("--replay-mode", replay_mode),
        ("--launch-count", str(launch_count)),
    ]
    if preset:
        pairs.append(("--set", preset.lower()))
    if metrics:
        pairs.append(("--aic-metrics", metrics))
    if kernel_name:
        pairs.append(("--kernel-name", kernel_name))
    for option in extra_options or []:
        if (
            not isinstance(option, str)
            or not option.startswith("--")
            or "=" not in option
        ):
            raise ValueError("extra options use --name=value argv entries")
        key, value = option.split("=", 1)
        if key in {name for name, _ in pairs}:
            raise ValueError(f"duplicate profiler option: {key}")
        pairs.append((key, value))
    names = {name for name, _ in pairs}
    if "--set" in names and "--aic-metrics" in names:
        raise ValueError("--set and --aic-metrics are mutually exclusive")
    if "--set" in names and replay_mode == "range":
        raise ValueError("--set and --replay-mode=range are mutually exclusive")
    if supported is not None:
        missing = [key for key, _ in pairs if key not in supported]
        if missing:
            extra = (
                "; choose supported --aic-metrics explicitly; no automatic --set expansion"
                if "--set" in missing
                else ""
            )
            raise ValueError("installed msopprof lacks " + ", ".join(missing) + extra)
    return [*prefix, *(f"{key}={value}" for key, value in pairs), *runner]


def number(value, integer=False):
    if value is None or str(value).strip().upper() in ("", "NA", "N/A", "NONE"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or (integer and not result.is_integer()):
        return None
    return int(result) if integer else result


def inspect_collection(
    root, op_names=None, device=None, basic_info=None, include_data=False
):
    root = Path(root).resolve(strict=True)
    paths = [root] if root.is_file() else sorted(root.rglob("*.csv"))
    chosen = Path(basic_info).resolve(strict=True) if basic_info else None
    if chosen and chosen not in paths:
        raise ValueError("selected BasicInfo file is outside this collection")
    files, records, warnings = [], [], []
    for path in paths:
        source = receipt(path)
        is_basic = path.name.startswith("OpBasicInfo")
        fields, rows = [], []
        try:
            with path.open(newline="", encoding="utf-8-sig") as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames or []
                if not fields or len(fields) != len(set(fields)):
                    raise ValueError(f"empty or duplicate CSV header: {path}")
                rows = list(reader)
            malformed = [
                row
                for row in rows
                if None in row or any(value is None for value in row.values())
            ]
            if malformed:
                raise ValueError(f"CSV column count mismatch: {path}")
            if is_basic and not {"Op Name", "Task Duration(us)"}.issubset(fields):
                raise ValueError(f"missing Op Name / Task Duration(us): {path}")
        except (ValueError, csv.Error) as error:
            selected = (
                path == chosen
                or root.is_file()
                or (is_basic and chosen is None and not op_names)
            )
            if is_basic and chosen is None and op_names:
                selected = (fields.count("Op Name") != 1 or not rows
                            or any(not row.get("Op Name") or row["Op Name"] in op_names for row in rows))
            if selected:
                raise ValueError(str(error)) from error
            warnings.append({"path": str(path), "reason": str(error)})
            files.append({**source, "inspection_error": str(error)})
            continue
        files.append(
            {
                **source,
                "fields": fields,
                "row_count": len(rows),
                **({"rows": rows} if include_data else {}),
            }
        )
        if not path.name.startswith("OpBasicInfo") or (chosen and path != chosen):
            continue
        for index, row in enumerate(rows, 2):
            if op_names and row["Op Name"] not in op_names:
                continue
            current_device = number(row.get("Device Id"), True)
            if device is not None and current_device != device:
                continue
            records.append(
                {
                    "source": source,
                    "line": index,
                    "op_name": row["Op Name"],
                    "op_type": row.get("Op Type"),
                    "duration_us": number(row["Task Duration(us)"]),
                    "device_id": current_device,
                    "pid": number(row.get("Pid"), True),
                    "block_dim": number(row.get("Block Dim"), True),
                    "mix_block_dim": number(row.get("Mix Block Dim"), True),
                    "current_frequency_mhz": number(row.get("Current Freq")),
                    "rated_frequency_mhz": number(row.get("Rated Freq")),
                    "raw": row,
                }
            )
    missing = sorted(set(op_names or []) - {row["op_name"] for row in records})
    return {
        "schema_version": 1,
        "provider": "msopprof",
        "collection_root": str(root),
        "status": "parsed" if records and not missing else "incomplete",
        "records": records,
        "csv_files": files,
        "missing_op_names": missing,
        "warnings": warnings,
        "aggregation": "none; each kernel/launch remains a separate record",
    }


def build_report(
    root,
    case_id,
    op_names,
    out,
    identity=None,
    protocol=None,
    basic_info=None,
    device=None,
    conditions=None,
    publish=True,
    line=None,
):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out == root or out.is_relative_to(root):
        raise ValueError("write reports outside immutable collection files")
    data = inspect_collection(root, op_names, device, basic_info)
    if line is not None:
        if not basic_info and not root.is_file():
            raise ValueError("--line needs a single CSV or --basic-info")
        data["records"] = [r for r in data["records"] if r["line"] == line]
        if len(data["records"]) != 1 or set(op_names or []) - {data["records"][0]["op_name"]}:
            raise ValueError("selected CSV line does not match the requested launch")
    result = report_from_data(data, case_id, identity, protocol, conditions)
    if publish:
        write_report(result, out)
    return result


def measurements(records, binding=None):
    return [{"kernel": r["op_name"], "device": r["device_id"], "pid": r["pid"],
             "duration_us": r["duration_us"], "evidence": r["source"], "line": r["line"],
             **({"application_device": binding["application_device"], "physical_device": binding["physical_device"],
                 "device_namespace": "physical"} if binding else {})} for r in records]


def report_from_data(data, case_id, identity, protocol, conditions, binding=None):
    records = data["records"]
    result = {
        **data,
        "case_id": case_id,
        "identity": identity or {},
        "conditions": conditions or {},
        "performance_eligible": False,
        "status": (
            "diagnostic_valid"
            if records
            and not data["missing_op_names"]
            and all(
                (row["duration_us"] is not None and row["duration_us"] > 0)
                for row in records
            )
            else "incomplete"
        ),
        "protocol": protocol
        or {
            "profiler": "msopprof",
            "metric": "Task Duration(us)",
            "statistic": "tool_reported_kernel_duration",
        },
    }
    result["measurements"] = measurements(records, binding)
    result["evidence"] = [
        {key: item[key] for key in ("path", "sha256")} for item in data["csv_files"]
    ]
    result["limitations"] = [item["reason"] for item in data["warnings"]]
    if len(records) == 1:
        info = records[0]
        result.update(
            summary=info["source"],
            op_info=info["raw"],
            timing={
                "duration_us": info["duration_us"],
                "metric": "Task Duration(us)",
                "current_frequency_mhz": info["current_frequency_mhz"],
                "rated_frequency_mhz": info["rated_frequency_mhz"],
            },
        )
    return result


def write_report(result, out):
    out = Path(out).resolve()
    check_report_output(result, out)
    lines = [
        "# msopprof 专项报告",
        "",
        f"case: {result['case_id']}；逐 kernel/launch 保留，不自动聚合。",
        "",
        "| kernel | device | pid | Task Duration (us) | current/rated MHz | source |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in result["records"]:
        name = row["op_name"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {name} | {row['device_id']} | {row['pid']} | {row['duration_us']} | "
            f"{row['current_frequency_mhz']}/{row['rated_frequency_mhz']} | "
            f"{row['source']['path']}:{row['line']} |"
        )
    report_path = str(out / "profile-report.json")
    write_report_files(out, {**result, "report": report_path}, lines)
    result["report"] = report_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    env = sub.add_parser("env", help="query CLI only, never launch a target")
    env.add_argument("--tool")
    command = sub.add_parser(
        "command", help="emit argv without running the application"
    )
    command.add_argument("--tool")
    command.add_argument(
        "--probe", action="store_true", help="check options against installed --help"
    )
    command.add_argument("--output", required=True)
    command.add_argument("--set", dest="preset")
    command.add_argument("--aic-metrics", dest="metrics")
    command.add_argument("--warm-up", type=int, default=3)
    command.add_argument("--replay-mode", default="kernel")
    command.add_argument("--launch-count", type=int, default=1)
    command.add_argument("--kernel-name")
    command.add_argument(
        "--option",
        action="append",
        help="extra profiler argv, e.g. --option=--mstx=true",
    )
    command.add_argument("runner", nargs=argparse.REMAINDER)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("root", type=Path)
    inspect.add_argument("--op-name", action="append")
    inspect.add_argument("--device", type=int)
    inspect.add_argument("--basic-info", type=Path)
    inspect.add_argument(
        "--include-data", action="store_true", help="include original metric CSV rows"
    )
    inspect.add_argument("--out", type=Path)
    report = sub.add_parser(
        "report", help="extract a specialist report from existing data"
    )
    report.add_argument("root", type=Path)
    report.add_argument("--case-id", help="Case label for an unbound diagnostic report")
    report.add_argument("--op-name", action="append")
    report.add_argument("--basic-info", type=Path)
    report.add_argument("--line", type=int, help="select one raw CSV record in a diagnostic report")
    report.add_argument("--device", type=int)
    report.add_argument("--protocol", type=Path)
    report.add_argument("--identity", type=Path)
    report.add_argument("--plan", type=Path, help="Frozen plan for a device-bound report")
    report.add_argument("--attempt", type=Path, help="Validated attempt belonging to --plan")
    report.add_argument(
        "--conditions", type=Path, help="recorded warmup/L2/ownership evidence"
    )
    report.add_argument("--out", type=Path, required=True)
    for action in (inspect, report):
        action.add_argument("--brief", action="store_true", help="show names, counts and device time on stdout")
    args = parser.parse_args()
    try:
        if args.action == "env":
            result = capabilities(find_tool(args.tool))
        elif args.action == "command":
            prefix = find_tool(args.tool) if args.probe else [args.tool or "msopprof"]
            if not args.probe and Path(prefix[0]).name == "msprof":
                prefix.append("op")
            available = capabilities(prefix)["options"] if args.probe else None
            runner = args.runner[1:] if args.runner[:1] == ["--"] else args.runner
            result = {
                "argv": build_command(
                    prefix,
                    runner,
                    args.output,
                    metrics=args.metrics,
                    preset=args.preset,
                    warmup=args.warm_up,
                    replay_mode=args.replay_mode,
                    launch_count=args.launch_count,
                    kernel_name=args.kernel_name,
                    supported=available,
                    extra_options=args.option,
                )
            }
        elif args.action == "report":
            if args.plan or args.attempt:
                if not (args.plan and args.attempt):
                    raise ValueError("--plan and --attempt must be provided together")
                if any(
                    value is not None
                    for value in (
                        args.case_id,
                        args.protocol,
                        args.identity,
                        args.device,
                        args.basic_info,
                        args.op_name,
                        args.line,
                    )
                ):
                    raise ValueError("bound reports take identity, selection and protocol from the plan")
                import report_contract
                adapter = report_contract.backend({"provider": "msopprof"})
                attempt = json.loads(args.attempt.read_text())
                if args.root.resolve() != adapter.output_path(attempt):
                    raise ValueError("report root differs from the bound capture")
                result = adapter.build_bound_report(args.plan, args.attempt, args.out,
                    conditions=json.loads(args.conditions.read_text()) if args.conditions else None)
            else:
                if not args.case_id:
                    raise ValueError("--case-id is required for an unbound diagnostic report")
                protocol = json.loads(args.protocol.read_text()) if args.protocol else None
                if protocol and "protocol" in protocol:
                    protocol = protocol["protocol"]
                result = build_report(
                    args.root,
                    args.case_id,
                    args.op_name,
                    args.out,
                    protocol=protocol,
                    identity=(
                        json.loads(args.identity.read_text()) if args.identity else None
                    ),
                    conditions=(
                        json.loads(args.conditions.read_text()) if args.conditions else None
                    ),
                    basic_info=args.basic_info,
                    device=args.device, line=args.line,
                )
        else:
            result = inspect_collection(
                args.root, args.op_name, args.device, args.basic_info, args.include_data
            )
        if args.action == "inspect" and args.out:
            with args.out.open("x") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        brief = getattr(args, "brief", False)
        print(json.dumps(kernel_overview(result) if brief else result, ensure_ascii=False,
                         indent=None if brief else 2, allow_nan=False))
        return 0
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(
            json.dumps({"status": "failed", "reason": str(error)}, ensure_ascii=False)
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
