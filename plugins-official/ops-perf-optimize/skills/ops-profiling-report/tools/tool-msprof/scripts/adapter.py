# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Single-process network msprof capture and complete-invocation samples."""

import importlib.util
import json
import os
from pathlib import Path

import device_context
from report_common import (
    receipt,
    require,
    check_receipt,
    check_command,
    check_report_output,
    output_path,
    capture_manifest,
    validate_failure,
    publication_evidence,
    bound_capture,
    collect_attempt,
    recover_attempt,
)

TOOL_ROOT = Path(__file__).resolve().parents[1]
TOOL_SCRIPT = TOOL_ROOT / "scripts/msprof_tools.py"
_spec = importlib.util.spec_from_file_location("_report_msprof_tools", TOOL_SCRIPT)
tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools)

PROTOCOL = {"profiler": "msprof", "options": tools.OPTIONS,
            "metric": "Task Duration(us)", "statistic": "sum_of_target_kernel_durations",
            "device_contract": device_context.CONTRACT, "device_id_namespace": "physical"}


def prepare(context=None):
    data = json.loads(Path(context).read_text()) if isinstance(context, (str, Path)) else (context or {})
    require(not data.get("multi_process"), "formal adapter binds one target process")
    found = tools.capabilities(tools.find_tool(data.get("tool")))
    protocol = {**PROTOCOL, "options": data.get("options", list(tools.OPTIONS))}
    tools.build_command(found["tool"]["path"], ["application-not-executed"], Path.cwd(),
                        protocol["options"], found["options"])
    result = {"provider": "msprof", "tool": found["tool"], "protocol": protocol,
              "frequency_policy": "record_only",
              "report_context": {"tool_skill": str(TOOL_ROOT / "TOOL.md"),
                                 "tool_script": str(TOOL_SCRIPT), "capabilities": found}}
    if "application_device" in data:
        binding = device_context.probe(data["application_device"], dict(os.environ))
        result.update(device_binding=binding, logical_device=binding["application_device"],
                      physical_device=binding["physical_device"], environment=binding["environment"])
    result["device_binding_status"] = "bound" if "device_binding" in result else "required_for_measurement"
    return result


def command(plan, identity, output):
    return tools.build_command(plan["tool"]["path"],
                               device_context.wrapped_runner(plan, identity["runner"], output),
                               output, plan["protocol"]["options"])


def validate_measurement(plan):
    device_context.for_plan(plan)
    require(isinstance(plan.get("effect_case_id"), str) and plan["effect_case_id"].strip(),
            "nonempty effect_case_id required for a bound measurement")
    require(plan.get("frequency_policy") == "record_only",
            "msprof op_summary does not provide rated/current frequency; use record_only")
    require(all(plan["protocol"].get(key) == value for key, value in PROTOCOL.items() if key != "options"),
            "unknown msprof timing/device protocol")
    for identity in plan["identities"].values():
        targets = identity.get("kernels")
        require(targets == "all" or (isinstance(targets, list) and targets), "target kernels required")
        command(plan, identity, Path.cwd())


def read_bound_records(root, identity, plan):
    data = tools.inspect_collection(root)
    physical = device_context.for_plan(plan)["physical_device"]
    require(data["records"] and all(r["device_id"] == physical for r in data["records"]),
            f"DEVICE_ID_MISMATCH: application={plan['logical_device']}, expected_physical={physical}, "
            f"report_namespace=physical, observed={sorted({r['device_id'] for r in data['records']})}")
    return data


def verified_sample(document, identity, plan):
    validate_measurement(plan)
    require(document.get("effect_case_id") == plan["effect_case_id"], "sample case differs from plan")
    check_receipt(document["extraction"])
    extracted = json.loads(Path(document["extraction"]["path"]).read_text())
    expected = read_bound_records(document["capture_output"], identity, plan)
    require(expected == extracted, "extraction differs from captured raw records")
    process = device_context.target_process(document["target_process"], plan,
                                            document["capture_output"], identity["runner"])
    require(all(r["pid"] == process["pid"] for r in extracted["records"]),
            "TARGET_PID_MISMATCH: measured process must have the recorded runner PID")
    chosen = tools.select_records(extracted, identity)
    require(document["records"] == chosen, "frozen target invocation selection changed")
    return extracted, chosen, process["pid"]


def raw_sample(path, identity, plan):
    _, chosen, pid = verified_sample(json.loads(Path(path).read_text()), identity, plan)
    return tools.invocation(chosen)["duration_us"], pid


def validate_publication(attempt, archive, summary, log, import_log, plan):
    identity, document, manifest = publication_evidence(attempt, archive, summary, import_log, plan)
    extracted, _, _ = verified_sample(document, identity, plan)
    require(attempt.get("import_returncode") == 0 and extracted["provider"] == "msprof"
            and extracted["collection_root"] == manifest["output"], "extraction does not belong to capture")
    require(all(item in manifest["files"] for item in extracted["evidence"]), "CSV/host metadata absent from archive")
    return extracted


def extract_attempt(plan, identity, attempt, directory):
    root = output_path(attempt)
    capture_manifest(attempt, root, directory)
    data = read_bound_records(root, identity, plan)
    extraction = directory / "extract.log"
    extraction.write_text(json.dumps(data, indent=2, allow_nan=False))
    attempt.update(import_returncode=0, import_log=receipt(extraction), import_method="read_bound_records")
    selected = directory / "selected-records.json"
    selected.write_text(json.dumps({"records": tools.select_records(data, identity),
                                   "extraction": attempt["import_log"], "target_process": attempt["target_process"],
                                   "capture_output": str(root), "effect_case_id": plan["effect_case_id"]}, indent=2))
    attempt["summary"] = receipt(selected)
    validate_publication(attempt, Path(attempt["archive"]["path"]), selected, "", extraction.read_text(), plan)


def validate_report(report):
    binding = None
    if report.get("device_evidence"):
        plan, attempt, data = bound_capture(report["device_evidence"], validate_publication)
        require(report["collection_root"] == data["collection_root"], "report capture changed")
        binding = device_context.for_plan(plan)
        require(report.get("device_binding") == binding and report["protocol"] == plan["protocol"]
                and report["identity"] == attempt["comparison_identity"]
                and report["case_id"] == plan["effect_case_id"], "report identity/protocol/device/case changed")
    else:
        data = tools.inspect_collection(report["collection_root"])
    require(report["records"] == data["records"], "report differs from raw op_summary/host metadata")
    if report.get("identity"):
        require(report.get("invocation") == tools.invocation(tools.select_records(data, report["identity"])),
                "invocation total/selection differs from raw records")
    else:
        require("invocation" not in report, "invocation needs an explicit target")
    require(report["measurements"] == tools.measurements(data["records"], binding), "normalized measurements changed")


def overview(report):
    evidence = report["evidence"]
    if report.get("device_evidence"):
        attempt = json.loads(device_context.check_receipt(report["device_evidence"]["attempt"]).read_text())
        evidence = json.loads(device_context.check_receipt(attempt["archive"]).read_text())["files"]
    return tools.overview(report, {item["path"]: item for item in evidence})


def build_bound_report(plan_path, attempt_path, out, conditions=None):
    evidence = {"plan": receipt(plan_path), "attempt": receipt(attempt_path)}
    plan, attempt, data = bound_capture(evidence, validate_publication)
    report = tools.report_from_data(data, plan["effect_case_id"], attempt["comparison_identity"],
                                    plan["protocol"], conditions, plan["device_binding"])
    report.update(device_binding=plan["device_binding"], device_evidence=evidence)
    report["evidence"].extend(evidence.values())
    tools.write_report(report, out)
    return report


def validate_screening(report):
    require(report.get("device_evidence"), "unbound report cannot be used for comparison; supply plan and attempt")
    validate_report(report)
    evidence = report["device_evidence"]
    plan = json.loads(Path(evidence["plan"]["path"]).read_text())
    attempt = json.loads(Path(evidence["attempt"]["path"]).read_text())
    dependencies = [
        attempt[key] for key in ("target_process", "device_binding_file", "archive", "import_log", "summary", "run_log")
    ]
    dependencies.extend(json.loads(Path(attempt["archive"]["path"]).read_text())["files"])
    return {"duration_us": report["invocation"]["duration_us"], "frequency_mhz": None,
            "dependencies": [*report["evidence"], *dependencies],
            "comparison_key": {"protocol": report["protocol"], "device_binding": report["device_binding"],
                               "tool": plan["tool"], "environment": plan["environment"],
                               "frequency_policy": plan["frequency_policy"]}}
