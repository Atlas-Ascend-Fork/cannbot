# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""msopprof acquisition and raw CSV adapter for the report boundary."""

from collections import Counter
import importlib.util
import json
import os
from operator import itemgetter
from pathlib import Path
import re
import subprocess

from report_common import (positive, receipt, require, check_receipt, check_command, check_report_output,
                           output_path, capture_manifest, validate_failure,
                           publication_evidence, bound_capture, collect_attempt, recover_attempt)
import device_context

TOOL_ROOT = Path(__file__).resolve().parents[1]
TOOL_SCRIPT = TOOL_ROOT / "scripts/msopprof_tools.py"
_spec = importlib.util.spec_from_file_location("_report_msopprof_tools", TOOL_SCRIPT)
tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools)

PROTOCOL = {
    "profiler": "msopprof",
    "aic_metrics": "BasicInfo",
    "warmup": 3,
    "replay_mode": "kernel",
    "launch_count": 1,
    "metric": "Task Duration(us)",
    "statistic": "tool_reported_kernel_duration",
    "device_contract": device_context.CONTRACT,
    "device_id_namespace": "physical",
}


def prefix(plan):
    tool_prefix = plan.get("report_context", {}).get("command_prefix")
    if tool_prefix is None:
        tool_prefix = [plan["tool"]["path"]]
        if Path(tool_prefix[0]).name == "msprof":
            tool_prefix.append("op")
    require(
        tool_prefix[0] == plan["tool"]["path"] and len(tool_prefix) in (1, 2),
        "tool prefix mismatch",
    )
    require(len(tool_prefix) == 1 or tool_prefix[1] == "op", "expected msprof op prefix")
    return tool_prefix


def command(plan, identity, output):
    p = plan["protocol"]
    return tools.build_command(
        prefix(plan),
        device_context.wrapped_runner(plan, identity["runner"], output),
        output,
        metrics=p.get("aic_metrics"),
        preset=p.get("set"),
        warmup=p["warmup"],
        replay_mode=p["replay_mode"],
        launch_count=p["launch_count"],
        kernel_name=p.get("kernel_filter"),
        extra_options=p.get("extra_options"),
    )


def prepare(context=None):
    data = (
        json.loads(Path(context).read_text())
        if isinstance(context, (str, Path))
        else (context or {})
    )
    require(
        not data.get("multi_process"),
        "multi-process collection needs a caller-specific measurement adapter",
    )
    found = tools.capabilities(tools.find_tool(data.get("tool")))
    protocol = {**PROTOCOL}
    for key in (
        "warmup",
        "replay_mode",
        "launch_count",
        "kernel_filter",
        "set",
        "aic_metrics",
        "extra_options",
    ):
        if key in data:
            protocol[key] = data[key]
    if "set" in data and "aic_metrics" not in data:
        protocol.pop("aic_metrics", None)
    tools.build_command(
        found["command_prefix"],
        ["application-not-executed"],
        Path.cwd(),
        metrics=protocol.get("aic_metrics"),
        preset=protocol.get("set"),
        warmup=protocol["warmup"],
        replay_mode=protocol["replay_mode"],
        launch_count=protocol["launch_count"],
        kernel_name=protocol.get("kernel_filter"),
        supported=found["options"],
        extra_options=protocol.get("extra_options"),
    )
    result = {
        "provider": "msopprof",
        "tool": found["tool"],
        "protocol": protocol,
        "report_context": {
            "tool_skill": str(TOOL_ROOT / "TOOL.md"),
            "tool_script": str(TOOL_SCRIPT),
            "tool_reference": str(TOOL_ROOT / "references/results.md"),
            "command_prefix": found["command_prefix"],
            "capabilities": found,
        },
    }
    if "application_device" in data:
        validate_device_protocol(result)
        binding = device_context.probe(data["application_device"], dict(os.environ))
        result.update(device_binding=binding, logical_device=binding["application_device"],
                      physical_device=binding["physical_device"], environment=binding["environment"])
    result["device_binding_status"] = "bound" if "device_binding" in result else "required_for_measurement"
    return result


def validate_device_protocol(plan):
    require(plan.get("protocol", {}).get("replay_mode") in ("kernel", "range"),
            "application replay restarts the process and cannot use a single target-process receipt")
    require(plan.get("protocol", {}).get("device_id_namespace") == "physical",
            "unsupported msopprof report device namespace")
    capabilities = plan.get("report_context", {}).get("capabilities", {})
    require(capabilities.get("tool") == plan.get("tool"), "profiler capability/tool identity mismatch")


def report_device_id(plan):
    validate_device_protocol(plan)
    return device_context.for_plan(plan)["physical_device"]


def report_op_name(identity):
    """CSV selector; protocol.kernel_filter belongs to the runtime CLI instead."""
    if identity.get("kernels") == "all":
        require(not {"report_op_name", "kernel_name"}.intersection(identity),
                "select either the isolated launch or an exact report name")
        return None
    name = identity.get("report_op_name", identity.get("kernel_name"))
    require(isinstance(name, str) and name.strip() and not any(c in name for c in "*?"),
            "exact CSV Op Name required in report_op_name (legacy: kernel_name); "
            "put runtime symbol/glob in protocol.kernel_filter")
    return name


def uses_legacy_symbol(identity):
    return "report_op_name" not in identity and identity.get("kernel_name", "").startswith("_Z")


def runtime_name_binding(run_log, identity):
    """Recover legacy symbol selectors only from the original profiler's log."""
    symbol = identity.get("kernel_name", "")
    require(uses_legacy_symbol(identity),
            "runtime-name recovery only applies to legacy mangled kernel_name")
    check_receipt(run_log)
    log = Path(run_log["path"]).read_text(errors="replace")
    header = re.compile(
        r"^\[INFO\]\s+Start analyze kernel on device: device(\d+), "
        r"kernel: (.+?), name is: .+$", re.MULTILINE)
    blocks = list(header.finditer(log))
    launches, other_names = [], set()
    for index, block in enumerate(blocks):
        end = blocks[index + 1].start() if index + 1 < len(blocks) else len(log)
        pairs = re.findall(
            r"^\s*(Op Name|Device Id|Pid|Task Duration\(us\)|Block Dim):[^\S\n]*(.*?)\s*$",
            log[block.end():end], re.MULTILINE)
        names = [value for key, value in pairs if key == "Op Name"]
        require(len(names) == 1 and names[0], "KERNEL_NAME_MAPPING_AMBIGUOUS: missing or repeated Op Name")
        if block[2] != symbol:
            other_names.add(names[0])
            continue
        fields = dict(pairs)
        require(len(fields) == len(pairs), "KERNEL_NAME_MAPPING_AMBIGUOUS: repeated target fields")
        row = {
            "runtime_symbol": block[2], "op_name": fields.get("Op Name"),
            "device_id": tools.number(fields.get("Device Id"), True),
            "pid": tools.number(fields.get("Pid"), True),
            "duration_us": tools.number(fields.get("Task Duration(us)")),
            "block_dim": tools.number(fields.get("Block Dim"), True),
        }
        require(row["device_id"] == int(block[1]) and positive(row["pid"])
                and positive(row["duration_us"]) and row["block_dim"] is not None,
                "KERNEL_NAME_MAPPING_MISSING: incomplete profiler analysis block")
        launches.append(row)
    names = {row["op_name"] for row in launches}
    require(len(names) == 1, "KERNEL_NAME_MAPPING_MISSING: expected an exact symbol and a unique CSV Op Name")
    name = names.pop()
    require(name not in other_names, "KERNEL_NAME_MAPPING_AMBIGUOUS: different symbols share this Op Name")
    return {"runtime_symbol": symbol, "report_op_name": name, "run_log": run_log, "launches": launches}


def read_bound_records(root, identity, plan, run_log=None):
    """The sole report/device boundary; keep the raw parser's fields untouched."""
    name = report_op_name(identity)
    data = tools.inspect_collection(root, [name] if name is not None else None)
    if not data["records"] and run_log is not None and uses_legacy_symbol(identity):
        binding = runtime_name_binding(run_log, identity)
        data = tools.inspect_collection(root, [binding["report_op_name"]])
        launch_key = itemgetter("op_name", "device_id", "pid", "duration_us", "block_dim")
        require(Counter(map(launch_key, data["records"])) == Counter(map(launch_key, binding["launches"])),
                "KERNEL_NAME_MAPPING_MISMATCH: CSV launches differ from original run.log")
        data["kernel_name_binding"] = binding
    bound_targets(data, identity, plan)
    return data


def bound_targets(data, identity, plan):
    expected = report_device_id(plan)
    name = data.get("kernel_name_binding", {}).get("report_op_name", report_op_name(identity))
    targets = [r for r in data["records"] if name is None or r["op_name"] == name]
    if name is None:
        require(len(targets) == 1, "isolated single-kernel sample needs exactly one captured launch")
    require(all(type(r["device_id"]) is int and r["device_id"] == expected for r in targets),
            f"DEVICE_ID_MISMATCH: application={plan['logical_device']}, expected_physical={expected}, "
            f"report_namespace=physical, observed={[r['device_id'] for r in targets]}")
    return targets


def frequency_policy(plan):
    policy = plan.get("frequency_policy", "rated")
    require(policy in ("rated", "record_only"), "unknown frequency_policy")
    if policy == "rated":
        require(
            positive(plan.get("rated_frequency_mhz")),
            "positive rated_frequency_mhz required for frequency_policy='rated' (the default)",
        )
    return policy


def validate_measurement(plan):
    frequency_policy(plan)
    require(isinstance(plan.get("effect_case_id"), str) and plan["effect_case_id"].strip(),
            "nonempty effect_case_id required for a bound measurement")
    report_device_id(plan)
    p = plan["protocol"]
    require(
        p.get("profiler") in ("msopprof", "msprof op")
        and p.get("metric") == PROTOCOL["metric"]
        and p.get("statistic") == PROTOCOL["statistic"],
        "unknown msopprof timing protocol",
    )
    for identity in plan["identities"].values():
        report_op_name(identity)
        command(plan, identity, Path.cwd())


def select_record(data, identity, plan):
    matches = bound_targets(data, identity, plan)
    if "block_dim" in identity:
        matches = [r for r in matches if r["block_dim"] == identity["block_dim"]]
    if "mix_block_dim" in identity:
        matches = [
            r for r in matches if r["mix_block_dim"] == identity["mix_block_dim"]
        ]
    if "occurrence" in identity:
        index = identity["occurrence"]
        require(
            type(index) is int and 0 <= index < len(matches),
            "comparison occurrence out of range",
        )
        matches = [matches[index]]
    require(
        len(matches) == 1,
        f"comparison target ambiguous/missing ({len(matches)} matching launches); "
        f"expected CSV Op Name={report_op_name(identity)!r}. "
        "Use report_op_name for the exact report name, protocol.kernel_filter for the "
        "runtime symbol/glob, and occurrence to disambiguate repeated launches",
    )
    return matches[0]


def raw_sample(path, identity, plan):
    frequency = frequency_policy(plan)
    document = json.loads(Path(path).read_text())
    require(document.get("effect_case_id") == plan["effect_case_id"], "sample case differs from plan")
    check_receipt(document["extraction"])
    extracted = json.loads(Path(document["extraction"]["path"]).read_text())
    root = document["capture_output"]
    process = device_context.target_process(document["target_process"], plan, root, identity["runner"])
    binding = extracted.get("kernel_name_binding")
    run_log = receipt(Path(root).parent / "run.log") if binding else None
    data = read_bound_records(root, identity, plan, run_log)
    require(data == extracted, "extraction differs from captured raw records")
    require(all(row["pid"] == process["pid"] for row in data["records"]),
            "TARGET_PID_MISMATCH: measured process must have the recorded runner PID")
    info = select_record(data, identity, plan)
    require(info == document["record"], "frozen kernel/occurrence selection changed")
    require(positive(info["duration_us"]), "Task Duration must be finite and positive")
    if frequency == "rated":
        require(
            positive(info["current_frequency_mhz"])
            and info["current_frequency_mhz"]
            == info["rated_frequency_mhz"]
            == plan["rated_frequency_mhz"],
            "frequency missing or different from frozen rated frequency",
        )
    return info["duration_us"], info["pid"]


def validate_publication(attempt, archive, summary, log, import_log, plan):
    identity, _, manifest = publication_evidence(attempt, archive, summary, import_log, plan)
    extracted = json.loads(import_log)
    require(
        attempt.get("import_returncode") == 0
        and extracted["provider"] == "msopprof"
        and extracted["collection_root"] == manifest["output"],
        "extraction does not belong to this capture",
    )
    archived = {item["path"] for item in manifest["files"]}
    require(all(csv["path"] in archived for csv in extracted["csv_files"]), "CSV absent from capture manifest")
    if "kernel_name_binding" in extracted:
        require(extracted["kernel_name_binding"]["run_log"] == attempt["run_log"], "mapping log receipt changed")
    raw_sample(summary, identity, plan)
    return extracted


def extract_attempt(plan, identity, attempt, directory):
    root = output_path(attempt)
    capture_manifest(attempt, root, directory)
    log_path = directory / "extract.log"
    data = read_bound_records(root, identity, plan, attempt["run_log"])
    log_path.write_text(json.dumps(data, indent=2))
    attempt.update(import_returncode=0, import_log=receipt(log_path),
                   import_method="read_bound_records", device_binding=plan["device_binding"])
    chosen = select_record(data, identity, plan)
    selected_path = directory / "selected-record.json"
    selected_path.write_text(
        json.dumps({"record": chosen, "extraction": attempt["import_log"],
                    "target_process": attempt["target_process"], "capture_output": str(root),
                    "effect_case_id": plan["effect_case_id"]}, indent=2)
    )
    attempt["summary"] = receipt(selected_path)
    validate_publication(
        attempt,
        Path(attempt["archive"]["path"]),
        selected_path,
        "",
        log_path.read_text(),
        plan,
    )


def validate_screening(report):
    require(report.get("device_evidence"),
            "unbound diagnostic report cannot be used for comparison; supply plan and attempt")
    validate_report(report)
    require(report.get("provider") == "msopprof", "unexpected provider")
    chosen = report["selected_record"]
    attempt = json.loads(Path(report["device_evidence"]["attempt"]["path"]).read_text())
    plan = json.loads(Path(report["device_evidence"]["plan"]["path"]).read_text())
    dependencies = [attempt[key] for key in
                    ("target_process", "device_binding_file", "archive", "import_log", "summary", "run_log")]
    dependencies.extend(json.loads(Path(attempt["archive"]["path"]).read_text())["files"])
    return {
        "duration_us": chosen["duration_us"],
        "frequency_mhz": chosen["rated_frequency_mhz"],
        "dependencies": [report["summary"], *report["device_evidence"].values(), *dependencies],
        "comparison_key": {"protocol": report["protocol"], "device_binding": report["device_binding"],
                           "tool": plan["tool"], "environment": plan["environment"],
                           "frequency_policy": plan.get("frequency_policy", "rated"),
                           "rated_frequency_mhz": plan.get("rated_frequency_mhz")},
    }


def validate_report(report):
    binding = None
    if report.get("device_evidence"):
        plan, attempt, data = bound_capture(report["device_evidence"], validate_publication)
        require(report["collection_root"] == data["collection_root"], "report capture changed")
        binding = device_context.for_plan(plan)
        identity = attempt["comparison_identity"]
        require(report["records"] == data["records"] and report["protocol"] == plan["protocol"],
                "report differs from the bound capture")
        require(report.get("kernel_name_binding") == data.get("kernel_name_binding"),
                "report runtime/report name binding changed")
        require(report.get("device_binding") == binding, "report device binding changed")
        require(report.get("identity") == identity, "report execution identity changed")
        require(report.get("case_id") == plan["effect_case_id"], "report case differs from plan")
        selected = json.loads(Path(attempt["summary"]["path"]).read_text())["record"]
        require(all(report.get(key) == value for key, value in selected_fields(selected).items()
                    if key != "invocation" or key in report),
                "report scalar fields differ from the frozen selected record")
    if binding is None:
        originals = {}
        for record in report["records"]:
            path = record["source"]["path"]
            if path not in originals:
                originals[path] = {r["line"]: r for r in tools.inspect_collection(path)["records"]}
            require(originals[path].pop(record["line"], None) == record,
                    "specialist record differs from original CSV or launch is repeated")
    require(report["measurements"] == tools.measurements(report["records"], binding), "normalized measurements changed")
    require(binding is not None or "invocation" not in report,
            "an invocation total requires a bound selection")


def selected_fields(record):
    return {"selected_record": record, "summary": record["source"], "op_info": record["raw"],
            "invocation": {"duration_us": record["duration_us"],
                           "statistic": "sum_of_target_kernel_durations", "records": [record]},
            "timing": {"duration_us": record["duration_us"], "metric": "Task Duration(us)",
                       "current_frequency_mhz": record["current_frequency_mhz"],
                       "rated_frequency_mhz": record["rated_frequency_mhz"]}}


def build_bound_report(plan_path, attempt_path, out, conditions=None):
    evidence = {"plan": receipt(plan_path), "attempt": receipt(attempt_path)}
    plan, attempt, data = bound_capture(evidence, validate_publication)
    selected = json.loads(Path(attempt["summary"]["path"]).read_text())["record"]
    report = tools.report_from_data(data, plan["effect_case_id"], attempt["comparison_identity"],
                                    plan["protocol"], conditions, plan["device_binding"])
    report.update(device_binding=plan["device_binding"], device_evidence=evidence)
    report.update(selected_fields(selected))
    report["evidence"].extend(evidence.values())
    tools.write_report(report, out)
    return report
