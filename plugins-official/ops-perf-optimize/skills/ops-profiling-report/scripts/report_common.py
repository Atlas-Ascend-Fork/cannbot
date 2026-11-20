# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Tool-independent evidence and cost helpers."""

from datetime import datetime, timezone
from decimal import Decimal
import errno
import json
import subprocess
import time

import hashlib
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory


def _publish_file(source, target):
    """Install a complete file atomically without replacing an occupied name."""
    if os.name == "nt":
        source.rename(target)  # Windows rename is exclusive.
        return
    try:
        os.link(source, target)
    except OSError as error:
        if error.errno not in (errno.EPERM, errno.EACCES, errno.ENOSYS, errno.EOPNOTSUPP, errno.EMLINK):
            raise
        # A mount can allow exclusive renames while disallowing hard links.
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        src, dst = os.fsencode(source), os.fsencode(target)
        if hasattr(libc, "renameat2"):
            result = libc.renameat2(-100, src, -100, dst, 1)  # AT_FDCWD, RENAME_NOREPLACE
        elif hasattr(libc, "renamex_np"):
            result = libc.renamex_np(src, dst, 4)  # RENAME_EXCL
        else:
            raise
        if result:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), os.fspath(target)) from error


def write_report_files(out, report, lines):
    """Publish complete files without overwriting, with JSON as the last step."""
    files = (
        (out / os.fsdecode("性能分析报告.md".encode("utf-8")), "\n".join(lines) + "\n"),
        (out / "profile-report.json", json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)),
    )
    for path, _ in files:
        if os.path.lexists(path):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(path))
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out, prefix=".profile-") as tmp:
        staging = Path(tmp)
        for path, content in files:
            (staging / (path.name + ".tmp")).write_text(content, encoding="utf-8", errors="backslashreplace")
        for path, _ in files:
            _publish_file(staging / (path.name + ".tmp"), path)


def check_report_output(report, out):
    root = report.get("collection_root")
    require(isinstance(root, str) and root, "report needs a capture path")
    require(not out.is_relative_to(Path(root).resolve()),
            "write reports outside immutable capture")


def _opened_path(stream):
    try:
        return os.readlink(f"/proc/self/fd/{stream.fileno()}")
    except OSError:
        return str(Path(stream.name).resolve(strict=True))


def receipt(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        resolved = _opened_path(stream)
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": resolved, "sha256": digest.hexdigest()}


def read_json_with_receipt(path):
    with Path(path).open("rb") as stream:
        resolved = _opened_path(stream)
        contents = stream.read()
    return json.loads(contents), {"path": resolved, "sha256": hashlib.sha256(contents).hexdigest()}


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def kernel_overview(data):
    """One row per device/process/name, keeping the first raw row as a lookup hint."""
    groups = {}
    root = Path(data["collection_root"])
    for record in data["records"]:
        key = (record["device_id"], record["pid"], record["op_name"])
        if key not in groups:
            source = Path(record["source"]["path"])
            groups[key] = {"name": record["op_name"], "device": record["device_id"], "pid": record["pid"],
                           "launches": 0, "duration_us": Decimal(0),
                           "first": [str(source.relative_to(root)) if root in source.parents else str(source),
                                     record["line"]]}
        row = groups[key]
        row["launches"] += 1
        if row["duration_us"] is not None and positive(record["duration_us"]):
            row["duration_us"] += Decimal(record["raw"]["Task Duration(us)"])
        else:
            row["duration_us"] = None
    for row in groups.values():
        if row["duration_us"] is not None:
            row["duration_us"] = float(row["duration_us"])
    result = {k: data[k] for k in ("provider", "status", "collection_root", "report") if k in data}
    if data.get("missing_op_names"):
        result["missing_op_names"] = data["missing_op_names"]
    if data.get("invocation"):
        value = data["invocation"]
        result["invocation"] = {"duration_us": value["duration_us"], "launches": len(value["records"])}
    return {**result, "kernels": list(groups.values()), "launches": len(data["records"])}


def roofline(duration_us, hbm_bytes=None, flops=None, peak_bw=None, peak_flops=None):
    """Use caller-supplied, evidenced costs/peaks. Unknown values remain null."""
    for name, value in [
        ("duration_us", duration_us),
        ("peak_bw", peak_bw),
        ("peak_flops", peak_flops),
    ]:
        if value is not None and not positive(value):
            raise ValueError(f"{name} must be finite and positive when supplied")
    for name, value in [("hbm_bytes", hbm_bytes), ("flops", flops)]:
        if value is not None and (
            type(value) not in (int, float) or not math.isfinite(value) or value < 0
        ):
            raise ValueError(f"{name} must be finite and nonnegative when supplied")
    sec = duration_us * 1e-6 if duration_us is not None else None
    t_mem = (
        hbm_bytes / peak_bw * 1e6
        if hbm_bytes is not None and peak_bw is not None
        else None
    )
    t_compute = (
        flops / peak_flops * 1e6
        if flops is not None and peak_flops is not None
        else None
    )
    # A missing compute term cannot establish a complete roofline or convergence.
    complete = t_mem is not None and t_compute is not None
    ceiling = max(t_mem, t_compute) if complete else None
    return {
        "MBU": hbm_bytes / sec / peak_bw if sec and t_mem is not None else None,
        "MFU": flops / sec / peak_flops if sec and t_compute is not None else None,
        "memory_lower_bound_us": t_mem,
        "compute_lower_bound_us": t_compute,
        "ceiling_us": ceiling,
        "roofline_complete": complete,
        "headroom_us": (
            max(0, duration_us - ceiling) if complete and duration_us else None
        ),
        "cost_bound": (
            ("Memory-Bound" if t_mem >= t_compute else "Compute-Bound")
            if complete
            else "unknown"
        ),
        "verdict": "requires analysis against evidenced intrinsic and implementation costs",
    }


def require(value, message):
    if not value:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def check_receipt(item):
    try:
        path_bytes = os.fsencode(item["path"])
    except UnicodeEncodeError:
        path_bytes = item["path"].encode("utf-8", errors="surrogateescape")
    actual = receipt(os.fsdecode(path_bytes))
    require(
        os.fsencode(actual["path"]) == path_bytes and actual["sha256"] == item["sha256"],
        "profiling evidence changed",
    )
    return actual


def check_command(actual, identity, plan):
    import report_contract
    adapter = report_contract.backend(plan)
    require(isinstance(actual, list), "retain actual profiler argv")
    outputs = [
        value.split("=", 1)[1] for value in actual if value.startswith("--output=")
    ]
    require(
        len(outputs) == 1 and Path(outputs[0]).is_absolute(),
        "one absolute output required",
    )
    require(
        actual == adapter.command(plan, identity, outputs[0]),
        "profiler argv or runner changed after registration",
    )


def output_path(attempt):
    values = [
        v.split("=", 1)[1] for v in attempt["command"] if v.startswith("--output=")
    ]
    require(len(values) == 1, "missing output path")
    return Path(values[0])


def capture_manifest(attempt, root, directory):
    if attempt.get("archive"):
        check_receipt(attempt["archive"])
        return
    require(not attempt.get("summary") and not attempt.get("import_log"), "capture manifest receipt missing")
    files = [receipt(path) for path in sorted(root.rglob("*")) if path.is_file()]
    require(files, "no captured artifacts")
    manifest = directory / "capture-manifest.json"
    manifest.write_text(json.dumps({"output": str(root), "files": files}, indent=2))
    attempt["archive"] = receipt(manifest)


def has_capture_files(root):
    return root.exists() and any(path.is_file() for path in root.rglob("*"))


def validate_failure(attempt, log):
    root = output_path(attempt)
    require(
        not attempt.get("archive") and not has_capture_files(root),
        "partial/published output needs review; do not discard or recollect",
    )


def comparison_identity(plan, attempt):
    variant = attempt.get("variant")
    if variant is None:
        identity = attempt.get("comparison_identity")
        require(identity in plan["identities"].values(), "comparison identity not frozen")
    else:
        require(variant in plan["identities"], "capture variant not frozen")
        identity = plan["identities"][variant]
    require(attempt.get("comparison_identity") == identity, "capture comparison identity changed")
    return identity


def publication_evidence(attempt, archive, summary, import_log, plan):
    import device_context
    case = plan.get("effect_case_id")
    require(isinstance(case, str) and case.strip() and attempt.get("effect_case_id") == case,
            "capture case differs from plan")
    identity = comparison_identity(plan, attempt)
    check_command(attempt["command"], identity, plan)
    require(attempt.get("returncode") == 0 and attempt.get("protocol") == plan["protocol"],
            "capture returncode/protocol differs from plan")
    check_receipt(attempt["run_log"])
    require(receipt(archive) == attempt["archive"] and receipt(summary) == attempt["summary"],
            "capture manifest/selected summary receipt changed")
    require(Path(attempt["import_log"]["path"]).read_text() == import_log,
            "extraction text differs from its receipt")
    require(all(attempt.get(key) == plan.get(key) for key in
                ("device_binding", "environment", "physical_device", "logical_device")),
            "attempt device binding differs from plan")
    binding = device_context.check_receipt(attempt["device_binding_file"])
    require(json.loads(binding.read_text()) == device_context.for_plan(plan), "capture device binding changed")
    manifest = json.loads(Path(archive).read_text())
    require(manifest["output"] == str(output_path(attempt)) and manifest["files"], "capture manifest mismatch")
    for item in manifest["files"]:
        check_receipt(item)
    document = json.loads(Path(summary).read_text())
    require(document.get("target_process") == attempt.get("target_process")
            and document.get("capture_output") == manifest["output"]
            and document.get("extraction") == attempt["import_log"], "selected capture identity changed")
    return identity, document, manifest


def bound_capture(evidence, validate_publication):
    import device_context
    plan = json.loads(device_context.check_receipt(evidence["plan"]).read_text())
    attempt = json.loads(device_context.check_receipt(evidence["attempt"]).read_text())
    require(attempt.get("status") == "valid", "report attempt is not validated")
    data = validate_publication(attempt, Path(attempt["archive"]["path"]), Path(attempt["summary"]["path"]),
                                "", Path(attempt["import_log"]["path"]).read_text(), plan)
    return plan, attempt, data


def collect_attempt(plan, identity, slot, attempt_dir, context=None):
    import device_context
    import report_contract
    adapter = report_contract.backend(plan)
    adapter.validate_measurement(plan)
    comparison_identity(plan, {**slot, "comparison_identity": identity})
    check_receipt(plan["tool"])
    environment = device_context.launch_environment(plan)
    device_context.verify_live(plan, environment)
    root = attempt_dir / "output"
    root.mkdir()
    binding_receipt = device_context.write_binding(plan, root)
    argv = adapter.command(plan, identity, root)
    log_path = attempt_dir / "run.log"
    started = now()
    timer = time.monotonic()
    with log_path.open("w") as stream:
        code = subprocess.run(
            argv, cwd=identity["cwd"], env=environment, stdout=stream, stderr=subprocess.STDOUT
        ).returncode
    attempt = {
        "schema_version": 1,
        **slot,
        "protocol": plan["protocol"],
        "physical_device": plan["physical_device"],
        "logical_device": plan["logical_device"],
        "environment": plan["environment"],
        "command": argv,
        "returncode": code,
        "started_at": started,
        "capture_ended_at": now(),
        "status": "needs_review",
        "run_log": receipt(log_path),
        "comparison_identity": identity,
        "effect_case_id": plan["effect_case_id"],
        "device_binding": plan["device_binding"],
        "device_binding_file": binding_receipt,
    }
    try:
        captured = has_capture_files(root)
        if code or not captured:
            if not captured:
                attempt["status"] = "failed"
            raise ValueError("profiler exited unsuccessfully or produced no output")
        attempt["target_process"] = receipt(device_context.paths(root)[1])
        adapter.extract_attempt(plan, identity, attempt, attempt_dir)
        attempt["status"] = "valid"
    except (OSError, ValueError, KeyError) as error:
        attempt["error"] = str(error)
    attempt["ended_at"] = now()
    attempt["tool_elapsed_seconds"] = time.monotonic() - timer
    return attempt


def recover_attempt(plan, identity, attempt, directory):
    import report_contract
    adapter = report_contract.backend(plan)
    attempt = dict(attempt)
    if attempt.get("status") != "valid":
        attempt.pop("tool_elapsed_seconds", None)
    attempt["status"] = "needs_review"
    try:
        require(attempt.get("device_binding") == plan.get("device_binding")
                and attempt.get("device_binding") is not None,
                "device binding missing/changed; old captures remain diagnostic-only")
        require(attempt.get("environment") == plan.get("environment")
                and attempt.get("physical_device") == plan.get("physical_device")
                and attempt.get("logical_device") == plan.get("logical_device"),
                "attempt device identity differs from plan")
        check_command(attempt["command"], identity, plan)
        check_receipt(attempt["run_log"])
        if not attempt.get("archive") and not has_capture_files(output_path(attempt)):
            attempt.update(status="failed", error="profiler produced no captured files")
            return attempt
        require(attempt["returncode"] == 0, "capture did not exit successfully")
        adapter.extract_attempt(plan, identity, attempt, directory)
        attempt["status"] = "valid"
        attempt.pop("error", None)
    except (OSError, ValueError, KeyError) as error:
        attempt["error"] = str(error)
    return attempt
