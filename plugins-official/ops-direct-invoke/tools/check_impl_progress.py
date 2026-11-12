#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------
"""Aggregate per-Unit TDD and whitebox results from the test runner output.

The single implementation node covers every Unit, so it needs the per-Unit
verdicts that the removed Unit subgraph used to provide. The runner already
writes one row per case; this script maps them back to Units through
testcase.csv and prints the dependency order to resume from.
"""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import logging
import os
import re
import subprocess
import uuid
from collections import deque
from contextlib import contextmanager
import fcntl
import sys
from pathlib import Path

import yaml

RUNNER_STATUS = "passed"
LOGGER = logging.getLogger(__name__)
ERROR_LOGGER = logging.getLogger(__name__ + ".errors")


def load_units(directory):
    """Return unit_id -> dependencies, rejecting anything the runner cannot key on."""
    units = {}
    for source in sorted(Path(directory).glob("U*.yaml")):
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or set(document) != {"unit"}:
            raise ValueError(f"{source}: expected one unit object")
        unit = document["unit"]
        if not isinstance(unit, dict) or unit.get("unit_id") != source.stem:
            raise ValueError(f"{source}: unit_id must match filename")
        depends_on = unit.get("depends_on") or []
        if not isinstance(depends_on, list) or any(
            not isinstance(dependency, str) for dependency in depends_on
        ):
            raise ValueError(f"{source}: depends_on must list unit ids")
        units[source.stem] = depends_on
    if not units:
        raise ValueError(f"{directory}: no U*.yaml")
    return units


def dependency_order(units):
    """Order Units so a retry can resume at the first incomplete capability."""
    order, visiting = [], set()

    def visit(unit_id):
        if unit_id in order:
            return
        if unit_id in visiting:
            raise ValueError(f"unit dependency cycle includes {unit_id}")
        visiting.add(unit_id)
        for dependency in units[unit_id]:
            if dependency not in units:
                raise ValueError(f"{unit_id}: unknown dependency {dependency}")
            visit(dependency)
        visiting.discard(unit_id)
        order.append(unit_id)

    for unit_id in sorted(units):
        visit(unit_id)
    return order


def load_csv(path):
    if not Path(path).is_file():
        raise ValueError(f"{path}: missing; run the sheet before checking progress")
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def active_cases(rows, sheet):
    return [
        row
        for row in rows
        if row.get("sheet") == sheet and row.get("status") == "active"
    ]


def summarize(cases, results):
    """Split one sheet into passed, failed and missing case ids."""
    passed = [case for case in cases if results.get(case["case_id"], {}).get("status") == RUNNER_STATUS]
    failed = [
        case
        for case in cases
        if case["case_id"] in results and results[case["case_id"]].get("status") != RUNNER_STATUS
    ]
    missing = [case for case in cases if case["case_id"] not in results]
    return passed, failed, missing


def resolve_op(work, op):
    if op:
        return op
    spec_path = work / "design/doc/spec.yaml"
    if not spec_path.is_file():
        raise ValueError(f"{spec_path}: missing; pass --op to select the operator")
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    name = (spec.get("op") or {}).get("name") if isinstance(spec.get("op"), dict) else None
    if not isinstance(name, str) or not name.strip():
        raise ValueError("design/doc/spec.yaml has no op.name; pass --op")
    return name



SHEETS = ("tdd", "whitebox", "blackbox", "performance")
IGNORED = {".case_cache", "testcase_output", "__pycache__", ".pytest_cache", ".git", "build", "dist", ".cache"}
ENV_KEYS = ("CANNBOTDSL_OP_MODULE", "CANNBOTDSL_OP_ENTRY", "CANNBOTDSL_ERROR_MATCHER",
            "PYTHONPATH", "PATH", "LD_LIBRARY_PATH", "ASCEND_HOME_PATH", "ASCEND_TOOLKIT_HOME",
            "ASCEND_OPP_PATH", "ASCEND_DEVICE_ID", "ASCEND_RT_VISIBLE_DEVICES", "DEVICE_ID",
            "CONDA_PREFIX", "CANNBOTDSL_OP_MODULE_PATH")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execution_paths(work, op):
    if Path(op).name != op or op in (".", ".."):
        raise ValueError("invalid operator name")
    paths = {work / "design/doc/spec.yaml", work / "design/doc/DESIGN.md",
             work / "environment/environment.yaml", work / "environment/env_selected_soc.yaml",
             work / "运行环境.sh"}
    paths.update((work / "design/units").glob("U*.yaml"))
    for unit_file in (work / "design/units").glob("U*.yaml"):
        unit = (yaml.safe_load(unit_file.read_text()) or {}).get("unit", {})
        for name in (unit.get("scope") or {}).get("source_files", []):
            paths.add(work / name)
    operator = work / "operators" / op
    for path in operator.rglob("*"):
        if not any(part in IGNORED for part in path.relative_to(operator).parts) and path.is_file():
            paths.add(path)
    return paths


def execution_files(work, paths):
    files = {}
    for path in sorted(paths):
        if not path.resolve().is_relative_to(work):
            raise ValueError(f"execution input outside work directory: {path}")
        files[str(path.relative_to(work))] = digest(path) if path.is_file() else None
    return files


def runtime_packages():
    packages = {}
    for name in ("torch", "torch-npu", "cannbotdsl", "numpy", "PyYAML"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return packages


def runtime_environment(work, op):
    environment = {name: os.environ.get(name) for name in ENV_KEYS}
    environment["CANNBOTDSL_OP_MODULE"] = environment["CANNBOTDSL_OP_MODULE"] or f"operators.{op}.{op}"
    environment["CANNBOTDSL_OP_ENTRY"] = environment["CANNBOTDSL_OP_ENTRY"] or "run"
    import_paths = [str(work)]
    for name in (environment["PYTHONPATH"] or "").split(os.pathsep):
        if name:
            path = Path(name)
            import_paths.append(str((path if path.is_absolute() else work / path).resolve()))
    environment["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(import_paths))
    return environment


def execution_identity(work, op):
    """Conservative identity of local source/contracts/tests and configured runtime.

    It does not attest to live hardware state or arbitrary external import closure;
    the verifier must still check actual loading and environment evidence.
    """
    files = execution_files(work, execution_paths(work, op))
    packages = runtime_packages()
    environment = runtime_environment(work, op)
    return {"files": files, "recorder_sha256": digest(Path(__file__)), "python": {"executable": sys.executable,
            "realpath": str(Path(sys.executable).resolve()), "version": sys.version,
            "sha256": digest(Path(sys.executable))}, "packages": packages,
            "environment": environment}


@contextmanager
def result_lock(test_dir, exclusive=False):
    root = test_dir / "testcase_output"
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".execution.lock").open("a") as handle:
        try:
            fcntl.flock(handle, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("test results are in use; do not run concurrent writers") from error
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)




def native_tdd_cases(rows, units):
    """Match the Skill's lowercase CSV unit_id to native Unit file identities.

    Preserve the original CSV and case IDs; uppercase legacy rows map identically.
    """
    aliases = {}
    for native in units:
        key = native.lower()
        if key in aliases:
            raise ValueError("ambiguous Unit identities after lowercase normalization")
        aliases[key] = native
    cases = []
    for row in active_cases(rows, "tdd"):
        value = row.get("unit_id")
        native = aliases.get(value.lower()) if isinstance(value, str) else None
        if native is None:
            raise ValueError(f"testcase.csv tdd row references unknown Unit: {value!r}")
        cases.append({**row, "unit_id": native})
    return cases


def unit_selection(work, cases, unit_id):
    units = load_units(work / "design/units")
    order = dependency_order(units)
    if unit_id not in units:
        raise ValueError(f"unknown Unit: {unit_id}")
    selected = set()

    def include(name):
        if name not in selected:
            selected.add(name)
            for dependency in units[name]:
                include(dependency)

    include(unit_id)
    rows = native_tdd_cases(cases, units)
    for name in selected:
        if not any(row.get("unit_id") == name for row in rows):
            raise ValueError(f"{name}: no active tdd case")
    ids = [row["case_id"] for row in rows if row.get("unit_id") in selected]
    if any(not isinstance(value, str) or not value for value in ids):
        raise ValueError("selected tdd case ids must be nonempty text")
    if len(ids) != len(set(ids)):
        raise ValueError("selected tdd case ids must be unique")
    return [name for name in order if name in selected], ids


def selection_pattern(case_ids):
    return r"\A(?:" + "|".join(re.escape(value) for value in case_ids) + r")\Z"


def result_paths(test_dir, sheet, unit=None, selected_ids=None):
    directory = test_dir / "testcase_output" / sheet
    if directory.is_symlink():
        raise ValueError(f"result directory cannot be a symlink: {directory}")
    if unit is not None:
        pattern = selection_pattern(selected_ids)
        suffix = hashlib.sha256(pattern.encode()).hexdigest()[:16]
        return (directory / f"verify_result_{sheet}_grep_{suffix}.csv",
                directory / f"execution-unit-{unit}.json")
    return directory / f"verify_result_{sheet}.csv", directory / "execution.json"


def validated_rows(cases, path, sheet, device, selected_ids=None):
    rows = load_csv(path)
    expected = selected_ids if selected_ids is not None else [row["case_id"] for row in active_cases(cases, sheet)]
    ids = [row.get("case_id") for row in rows]
    if not expected or len(set(expected)) != len(expected):
        raise ValueError(f"{sheet}: nonempty unique active case ids required")
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError(f"{sheet}: duplicate, missing or unexpected result case ids")
    if any(row.get("sheet") != sheet or row.get("device") != device
           or row.get("status") not in {"passed", "failed"} for row in rows):
        raise ValueError(f"{sheet}: result sheet/device/status differs from recorded execution")
    return rows


def bound_results(work, op, cases, sheet, current, expected_device=None, unit=None, selected_ids=None):
    test_dir = work / "operators" / op / "test"
    path, evidence_path = result_paths(test_dir, sheet, unit, selected_ids)
    if path.is_symlink():
        raise ValueError("result CSV cannot be a symlink")
    rows = load_csv(path)
    if not evidence_path.is_file() or evidence_path.is_symlink():
        raise ValueError(f"{sheet}: execution binding missing; rerun via --run-sheet, do not sign old CSV")
    evidence = json.loads(evidence_path.read_text())
    if not isinstance(evidence, dict):
        raise ValueError("invalid execution binding")
    expected_binding = {"version": 1, "identity": current, "result_sha256": digest(path), "sheet": sheet}
    if any(evidence.get(key) != value for key, value in expected_binding.items()):
        raise ValueError(f"{sheet}: stale execution binding; rerun tests for current version")
    if evidence.get("unit") != unit or (unit is not None and evidence.get("case_ids") != selected_ids):
        raise ValueError(f"{sheet}: execution scope does not match selected Unit")
    if expected_device is not None and evidence.get("device") != expected_device:
        raise ValueError(f"{sheet}: result was produced on a different device")
    validated_rows(cases, path, sheet, evidence.get("device"), selected_ids)
    unsupported_failure = evidence.get("returncode") == 1 and "--all" not in evidence.get("command", [])
    if evidence.get("returncode") not in (0, 1):
        raise ValueError(f"{sheet}: runner exit code does not support these results")
    if unsupported_failure and all(row["status"] == "passed" for row in rows):
        raise ValueError(f"{sheet}: runner exit code does not support these results")
    return {row["case_id"]: row for row in rows}


def loop_path(work, op):
    return work / "operators" / op / "test/testcase_output/.executions/unit-loop.json"


def load_loop(work, op):
    path = loop_path(work, op)
    if not path.exists():
        return None  # Older frozen runs retain their original protocol.
    if path.is_symlink():
        raise ValueError("Unit loop record cannot be a symlink")
    record = json.loads(path.read_text())
    order = dependency_order(load_units(work / "design/units"))
    closed = record.get("closed") if isinstance(record, dict) else None
    if not isinstance(record, dict):
        raise ValueError("invalid or changed Unit loop; do not hand-edit progress")
    if record.get("version") != 1 or record.get("order") != order or not isinstance(closed, list):
        raise ValueError("invalid or changed Unit loop; do not hand-edit progress")
    if closed != order[:len(closed)] or len(closed) > len(order):
        raise ValueError("invalid or changed Unit loop; do not hand-edit progress")
    expected_active = order[len(closed)] if len(closed) < len(order) else None
    if record.get("active") != expected_active:
        raise ValueError("invalid or changed Unit loop; do not hand-edit progress")
    return record


def save_loop(work, op, record):
    path = loop_path(work, op)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def verify_unit_green(work, op, unit, device):
    cases = load_csv(work / "operators" / op / "test/testcase.csv")
    _, ids = unit_selection(work, cases, unit)
    current = execution_identity(work, op)
    results = bound_results(work, op, cases, "tdd", current, device, unit, ids)
    if any(row["status"] != RUNNER_STATUS for row in results.values()):
        raise ValueError(f"{unit}: current Unit/dependency TDD is not green; repair it before advancing")
    _, evidence = result_paths(work / "operators" / op / "test", "tdd", unit, ids)
    binding = json.loads(evidence.read_text())
    return {"unit": unit, "run_id": binding["run_id"], "binding_sha256": digest(evidence)}


def enter_unit(work, op, unit, device):
    """Single-session numerical transition guard, not a semantic approval or sandbox."""
    if not device or device.lower().startswith("cpu"):
        raise ValueError("--enter-unit requires the selected accelerator --device")
    order = dependency_order(load_units(work / "design/units"))
    if unit not in order:
        raise ValueError(f"unknown Unit: {unit}")
    record = load_loop(work, op)
    if record is None:
        if unit != order[0]:
            raise ValueError(f"enter {order[0]} first; cannot start at {unit}")
        record = {"version": 1, "order": order, "active": unit, "closed": [], "transitions": []}
    elif unit == record["active"]:
        pass  # Resume without clearing failed attempts or pretending they passed.
    elif unit in record["closed"]:
        # Explicitly repair an earlier capability; affected successors must be rechecked.
        record["closed"] = order[:order.index(unit)]
        record["active"] = unit
        record["transitions"].append({"repair_from": unit})
    else:
        active = record["active"]
        expected = order[len(record["closed"]) + 1:len(record["closed"]) + 2]
        if active is None or expected != [unit]:
            raise ValueError(f"cannot skip Unit: active={active}, next={expected}")
        proof = verify_unit_green(work, op, active, device)
        record["closed"].append(active)
        record["active"] = unit
        record["transitions"].append(proof)
    save_loop(work, op, record)
    LOGGER.info("unit-loop: active=%s; numerical scope only; design review still required", unit)


def guard_loop_run(work, op, sheet, unit, device):
    record = load_loop(work, op)
    if sheet not in ("tdd", "all"):
        return
    if record is None:
        manifest = work / ".workflow-tools/manifest.json"
        if manifest.exists() and json.loads(manifest.read_text()).get("unit_loop_required"):
            raise ValueError("Unit loop required by this run; use --enter-unit before implementation/testing")
        return
    active = record["active"]
    if active is None:
        return  # Existing complete implementation: retain scoped/full repair support.
    if unit is not None:
        if unit != active:
            raise ValueError(f"Unit loop active={active}; cannot run {unit}; use --enter-unit after green")
        return
    if active != record["order"][-1]:
        raise ValueError(f"Unit loop active={active}; full TDD is blocked until all Units advance")
    proof = verify_unit_green(work, op, active, device)
    record["closed"].append(active)
    record["active"] = None
    record["transitions"].append(proof)
    save_loop(work, op, record)


def guard_loop_release(work, op):
    record = load_loop(work, op)
    if record is not None and record["active"] is not None:
        raise ValueError(f"Unit loop active={record['active']}; no full release; inspect --unit instead")
    manifest = work / ".workflow-tools/manifest.json"
    if record is None and manifest.exists() and json.loads(manifest.read_text()).get("unit_loop_required"):
        raise ValueError("required Unit loop missing; no full release")


def archive_previous_results(test_dir, sheets, unit, selected_ids, archive):
    """Remove old bindings before launch; a crash must never re-sign old passes."""
    for value in sheets:
        result, evidence = result_paths(test_dir, value, unit, selected_ids)
        result.parent.mkdir(parents=True, exist_ok=True)
        old_paths = [result, evidence]
        if unit is not None:
            # A scoped attempt cannot leave an earlier full-sheet green active.
            old_paths.extend(result_paths(test_dir, "tdd"))
        for old in dict.fromkeys(old_paths):
            if old.is_symlink():
                raise ValueError(f"result cannot be a symlink: {old}")
            if old.exists():
                old.replace(archive / f"previous-{value}-{old.name}")


def runner_command(runner, sheet, device, unit, selected_ids):
    command = [sys.executable, str(runner), "--all" if sheet == "all" else "--sheet"]
    if sheet != "all":
        command.append(sheet)
    if unit is not None:
        command.extend(["--grep", selection_pattern(selected_ids)])
    return command + ["--device", device, "--require-accelerator"]


def execute_runner(work, command, before, archive, unit):
    child_env = os.environ.copy()
    for name in ("CANNBOTDSL_OP_MODULE", "CANNBOTDSL_OP_ENTRY", "PYTHONPATH"):
        child_env[name] = before["environment"][name]
    log = archive / "runner.log"
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.run(command, cwd=work, env=child_env, stdout=stream, stderr=subprocess.STDOUT)
    (archive / "runner-process.json").write_text(json.dumps({
        "command": command, "returncode": process.returncode, "identity": before,
        "log": str(log.relative_to(work)), "unit": unit,
    }, ensure_ascii=False, indent=2) + "\n")
    with log.open(encoding="utf-8", errors="replace") as stream:
        tail = "".join(deque(stream, maxlen=12))
    LOGGER.info("%s", tail[-6000:].removesuffix("\n"))
    LOGGER.info("runner returncode=%s; raw log: %s", process.returncode, log)
    return process.returncode


def collect_bindings(test_dir, cases, sheets, record):
    records = []
    for value in sheets:
        path, evidence = result_paths(test_dir, value, record["unit"], record["case_ids"])
        rows = validated_rows(cases, path, value, record["device"], record["case_ids"])
        if record["returncode"] == 1 and len(sheets) == 1:
            if all(row["status"] == "passed" for row in rows):
                raise ValueError("runner failed despite all passing rows; no results bound")
        binding = {**record, "sheet": value, "result_sha256": digest(path)}
        records.append((path, evidence, binding))
    if record["returncode"] == 1 and all(
        row["status"] == "passed" for path, _, _ in records for row in load_csv(path)
    ):
        raise ValueError("runner failed despite all passing rows; no results bound")
    return records


def publish_bindings(archive, records):
    for path, evidence, record in records:
        (archive / path.name).write_bytes(path.read_bytes())
        data = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        (archive / (record["sheet"] + "-execution.json")).write_text(data)
        temporary = evidence.with_suffix(".json.tmp")
        temporary.write_text(data)
        temporary.replace(evidence)
    LOGGER.info("execution binding: %s", archive)


def run_locked_sheet(work, op, sheet, device, unit, test_dir, runner):
    guard_loop_run(work, op, sheet, unit, device)
    cases = load_csv(test_dir / "testcase.csv")
    selected_ids = unit_selection(work, cases, unit)[1] if unit is not None else None
    sheets = list(SHEETS[:3]) if sheet == "all" else [sheet]
    if sheet == "all" and active_cases(cases, "performance"):
        sheets.append("performance")
    if any(not active_cases(cases, value) for value in sheets):
        raise ValueError("requested test groups must have active cases")
    before = execution_identity(work, op)
    archive = test_dir / "testcase_output" / ".executions" / uuid.uuid4().hex
    archive.mkdir(parents=True)
    archive_previous_results(test_dir, sheets, unit, selected_ids, archive)
    command = runner_command(runner, sheet, device, unit, selected_ids)
    returncode = execute_runner(work, command, before, archive, unit)
    if execution_identity(work, op) != before:
        raise ValueError("execution inputs changed during testing; no results bound")
    if returncode not in (0, 1):
        raise ValueError(f"runner failed with exit {returncode}; no results bound")
    record = {"version": 1, "run_id": archive.name, "identity": before, "command": command,
              "device": device, "unit": unit, "case_ids": selected_ids, "returncode": returncode}
    records = collect_bindings(test_dir, cases, sheets, record)
    publish_bindings(archive, records)
    return returncode


def run_sheet(work, op, sheet, device, unit=None):
    """Run the fixed test entry; there is intentionally no record-only mode."""
    if unit is not None and sheet != "tdd":
        raise ValueError("--unit is TDD-only")
    if not device or device.lower().startswith("cpu"):
        raise ValueError("--run-sheet requires the selected accelerator --device")
    test_dir = work / "operators" / op / "test"
    runner = test_dir / f"test_{op}.py"
    if not runner.is_file():
        raise ValueError(f"missing fixed runner: {runner}")
    with result_lock(test_dir, exclusive=True):
        return run_locked_sheet(work, op, sheet, device, unit, test_dir, runner)


def sheet_report(work, op, cases, sheet, current, expected_device):
    sheet_cases = active_cases(cases, sheet)
    if sheet == "performance" and not sheet_cases:
        return False, "performance NOT_PROVIDED cases=0"
    results = bound_results(work, op, cases, sheet, current, expected_device)
    passed, broken, missing = summarize(sheet_cases, results)
    state = "PASS" if sheet_cases and not broken and not missing else "FAIL"
    line = f"{sheet} {state} passed={len(passed)} failed={len(broken)} missing={len(missing)}"
    return state != "PASS", line


def report(work, op, require_whitebox=False, require_blackbox=False,
           require_performance=False, expected_device=None, unit=None):
    """Return (failed, lines) for the requested sheets, keyed by Unit dependency order."""
    units = load_units(work / "design/units")
    order = dependency_order(units)
    test_dir = work / "operators" / op / "test"
    cases = load_csv(test_dir / "testcase.csv")
    current = execution_identity(work, op)
    selected_ids = None
    if unit is not None:
        order, selected_ids = unit_selection(work, cases, unit)
    tdd_results = bound_results(work, op, cases, "tdd", current, expected_device, unit, selected_ids)

    tdd_cases = native_tdd_cases(cases, units)
    unknown = sorted({case.get("unit_id") for case in tdd_cases} - set(units))
    if unknown:
        raise ValueError(f"testcase.csv tdd rows reference unknown Units: {unknown}")

    lines, failed = [], False
    for unit_id in order:
        unit_cases = [case for case in tdd_cases if case.get("unit_id") == unit_id]
        passed, broken, missing = summarize(unit_cases, tdd_results)
        state = "PASS" if unit_cases and not broken and not missing else "FAIL"
        failed = failed or state != "PASS"
        detail = "no active tdd case" if not unit_cases else (
            f"passed={len(passed)} failed={len(broken)} missing={len(missing)}"
        )
        lines.append(f"{unit_id} {state} {detail}")

    requirements = (("whitebox", require_whitebox), ("blackbox", require_blackbox),
                    ("performance", require_performance))
    for sheet, required in requirements:
        if not required:
            continue
        sheet_failed, line = sheet_report(work, op, cases, sheet, current, expected_device)
        failed = failed or sheet_failed
        lines.append(line)
    counts = " ".join(
        f"{sheet}_cases={len(active_cases(cases, sheet))}"
        for sheet in ("tdd", "whitebox", "blackbox", "performance")
    )
    if unit is not None:
        lines.append(f"scope=unit:{unit} selected_tdd_cases={len(selected_ids)}; not full-sheet release")
    lines.append(f"units={len(order)} {counts}")
    return failed, lines


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True, help="workflow work directory")
    parser.add_argument("--op", help="operator name; defaults to spec.op.name")
    parser.add_argument(
        "--require-whitebox",
        action="store_true",
        help="also gate on the whitebox run; leave off during the per-Unit red/green loop",
    )
    parser.add_argument(
        "--require-blackbox",
        action="store_true",
        help="also gate on the blackbox run; precision validation requires it",
    )
    parser.add_argument(
        "--require-performance", action="store_true",
        help="gate on user performance cases when present; no timing",
    )
    parser.add_argument(
        "--run-sheet", choices=(*SHEETS, "all"),
        help="execute fixed runner and bind fresh results; never sign existing CSV",
    )
    parser.add_argument(
        "--device", help="selected accelerator for --run-sheet; optionally require the same device when checking",
    )
    parser.add_argument("--unit", help="TDD-only scope: selected Unit and transitive dependencies; never full release")
    parser.add_argument("--enter-unit", help="enter/resume one Unit in the same-session ordered TDD loop")
    return parser


def validate_modes(args):
    required = (args.require_whitebox, args.require_blackbox, args.require_performance)
    if args.enter_unit and any((args.unit, args.run_sheet, *required)):
        raise ValueError("--enter-unit is a standalone transition check")
    if args.unit and (args.run_sheet not in (None, "tdd") or any(required)):
        raise ValueError("--unit is TDD-only and cannot be used for full-sheet release")


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    ERROR_LOGGER.addHandler(logging.StreamHandler(sys.stderr))
    ERROR_LOGGER.propagate = False
    args = argument_parser().parse_args()
    try:
        work = Path(args.work_dir).resolve()
        op = resolve_op(work, args.op)
        if Path(op).name != op or op in (".", ".."):
            raise ValueError("invalid operator name")
        validate_modes(args)
        if args.enter_unit:
            with result_lock(work / "operators" / op / "test", exclusive=True):
                enter_unit(work, op, args.enter_unit, args.device)
            return 0
        if args.run_sheet:
            return run_sheet(work, op, args.run_sheet, args.device, args.unit)
        with result_lock(work / "operators" / op / "test"):
            if args.unit is None:
                guard_loop_release(work, op)
            failed, lines = report(
                work, op, require_whitebox=args.require_whitebox,
                require_blackbox=args.require_blackbox,
                require_performance=args.require_performance, expected_device=args.device, unit=args.unit,
            )
    except (ValueError, OSError, yaml.YAMLError) as error:
        ERROR_LOGGER.error("impl-progress: %s", error)
        return 2
    LOGGER.info("%s", "\n".join(lines))
    LOGGER.info("impl-progress: FAIL" if failed else "impl-progress: PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
