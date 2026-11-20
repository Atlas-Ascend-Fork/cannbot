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

"""Freeze runtime device mappings and launch the target in the recorded process.

Only ``probe`` loads CANN, in a fresh subprocess. Validation/recovery is offline.
Raw profiler device IDs are never rewritten into application device IDs.
"""

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from report_common import receipt

CONTRACT = "runtime_device_v1"
ENV_KEYS = (
    "ASCEND_RT_VISIBLE_DEVICES", "ASCEND_VISIBLE_DEVICES", "ASCEND_DEVICE_ID",
    "ASCEND_HOME_PATH", "ASCEND_OPP_PATH", "LD_LIBRARY_PATH", "PYTHONPATH",
)
SCRIPT = Path(__file__).resolve()


def require(value, message):
    if not value:
        raise ValueError(message)


def index(value, name):
    require(type(value) is int and value >= 0, f"invalid {name}: {value!r}")
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def snapshot(environment):
    return {key: environment.get(key) for key in ENV_KEYS}


def visible_list(value):
    if value is None:
        return None
    require(isinstance(value, str) and re.fullmatch(r"[0-9]+(?:,[0-9]+)*", value),
            "invalid ASCEND_RT_VISIBLE_DEVICES: use a nonempty comma-separated ID list or unset it")
    values = [int(item) for item in value.split(",")]
    require(len(set(values)) == len(values), "duplicate ASCEND_RT_VISIBLE_DEVICES entries")
    return values


def check_receipt(item):
    require(isinstance(item, dict) and set(item) == {"path", "sha256"}, "invalid device evidence receipt")
    require(receipt(item["path"]) == item, f"device evidence changed: {item['path']}")
    return Path(item["path"])


def validate(binding):
    require(isinstance(binding, dict) and binding.get("schema_version") == 1,
            "missing/unsupported device binding; prepare with --application-device")
    application = index(binding.get("application_device"), "application_device")
    index(binding.get("physical_device"), "physical_device")
    index(binding.get("runtime_device"), "runtime_device")
    count = index(binding.get("visible_count"), "visible_count")
    require(application < count, "application device is outside the runtime-visible device set")
    environment = binding.get("environment")
    require(isinstance(environment, dict) and set(environment) == set(ENV_KEYS)
            and all(value is None or isinstance(value, str) for value in environment.values()),
            "device binding must retain set/unset environment values")
    visible = visible_list(environment["ASCEND_RT_VISIBLE_DEVICES"])
    if visible is not None:
        require(len(visible) == count and visible[application] == binding["runtime_device"],
                "runtime mapping differs from the ordered visible list")
    require(binding.get("mapping_api") == "aclrtGetPhyDevIdByUserDevId",
            "unsupported device mapping method")
    require(isinstance(binding.get("host_boot_id"), str) and binding["host_boot_id"],
            "missing device mapping host identity")
    for key in ("runtime_library", "resolver", "launcher_python"):
        item = binding.get(key)
        require(isinstance(item, dict) and set(item) == {"path", "sha256"}
                and Path(item["path"]).is_absolute() and re.fullmatch(r"[0-9a-f]{64}", item["sha256"]),
                f"missing {key} identity")
    return binding


def for_plan(plan):
    require(plan.get("protocol", {}).get("device_contract") == CONTRACT,
            "device binding required; old plans are diagnostic-only, prepare a new plan")
    binding = validate(plan.get("device_binding"))
    require(type(plan.get("logical_device")) is int
            and plan["logical_device"] == binding["application_device"]
            and type(plan.get("physical_device")) is int
            and plan["physical_device"] == binding["physical_device"],
            "plan device aliases differ from the runtime binding")
    environment = plan.get("environment", {})
    require(all(key in environment and environment[key] == value
                for key, value in binding["environment"].items()),
            "plan environment differs from the runtime binding")
    return binding


def launch_environment(plan, inherited=None):
    for_plan(plan)
    environment = dict(os.environ if inherited is None else inherited)
    # Do not silently repair a changed parent environment or mutate os.environ.
    for key, value in plan["environment"].items():
        require(value is None or isinstance(value, str), f"invalid frozen environment value: {key}")
        require(environment.get(key) == value, f"frozen environment changed: {key}")
    return environment


def probe(application, environment):
    index(application, "application_device")
    visible_list(environment.get("ASCEND_RT_VISIBLE_DEVICES"))
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "probe", "--application-device", str(application)],
        env=environment, capture_output=True, text=True, timeout=30,
    )
    require(result.returncode == 0, f"device mapping unavailable: {result.stderr.strip() or result.stdout.strip()}")
    # Runtime libraries may print diagnostics; the marker is our protocol boundary.
    lines = [line[len("CANNBOT_DEVICE "):] for line in result.stdout.splitlines()
             if line.startswith("CANNBOT_DEVICE ")]
    require(len(lines) == 1, "missing/ambiguous runtime device probe result")
    return validate(json.loads(lines[0]))


def runtime_probe(application):
    index(application, "application_device")
    environment = snapshot(os.environ)
    visible_list(environment["ASCEND_RT_VISIBLE_DEVICES"])
    home = environment["ASCEND_HOME_PATH"]
    require(home and Path(home).is_absolute(), "absolute ASCEND_HOME_PATH required")
    library = receipt(Path(home) / "lib64/libascendcl.so")
    acl = ctypes.CDLL(library["path"])
    signatures = {
        "aclInit": [ctypes.c_char_p], "aclFinalize": [],
        "aclrtGetDeviceCount": [ctypes.POINTER(ctypes.c_uint32)],
        "aclrtGetLogicDevIdByUserDevId": [ctypes.c_int32, ctypes.POINTER(ctypes.c_int32)],
        "aclrtGetPhyDevIdByUserDevId": [ctypes.c_int32, ctypes.POINTER(ctypes.c_int32)],
    }
    for name, args in signatures.items():
        require(hasattr(acl, name), f"runtime lacks required mapping API: {name}")
        function = getattr(acl, name)
        function.argtypes, function.restype = args, ctypes.c_int32

    def call(name, *args):
        status = getattr(acl, name)(*args)
        require(status == 0, f"{name} failed: {status}")

    call("aclInit", None)
    try:
        count = ctypes.c_uint32()
        call("aclrtGetDeviceCount", ctypes.byref(count))
        require(application < count.value, "application device out of range")
        runtime, physical = ctypes.c_int32(), ctypes.c_int32()
        call("aclrtGetLogicDevIdByUserDevId", application, ctypes.byref(runtime))
        call("aclrtGetPhyDevIdByUserDevId", application, ctypes.byref(physical))
        return validate({
            "schema_version": 1, "application_device": application,
            "runtime_device": runtime.value, "physical_device": physical.value,
            "visible_count": count.value, "environment": environment,
            "mapping_api": "aclrtGetPhyDevIdByUserDevId", "runtime_library": library,
            "resolver": receipt(SCRIPT), "launcher_python": receipt(sys.executable),
            "host_boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        })
    finally:
        call("aclFinalize")


def verify_live(plan, environment):
    binding = for_plan(plan)
    for key in ("runtime_library", "resolver", "launcher_python"):
        check_receipt(binding[key])
    require(probe(binding["application_device"], environment) == binding,
            "runtime device mapping changed since preparation")


def capture_id(output):
    return digest(str(Path(output).resolve()))


def paths(output):
    directory = Path(output).resolve().parent
    return directory / "device-binding.json", directory / "target-process.json"


def wrapped_runner(plan, runner, output):
    binding = for_plan(plan)
    binding_path, process_path = paths(output)
    return [binding["launcher_python"]["path"], "-B", binding["resolver"]["path"], "exec",
            "--binding", str(binding_path), "--receipt", str(process_path),
            "--capture-id", capture_id(output), "--", *runner]


def write_binding(plan, output):
    binding_path, _ = paths(output)
    with binding_path.open("x") as stream:
        json.dump(for_plan(plan), stream, indent=2)
    return receipt(binding_path)


def target_process(item, plan, output, runner):
    path = check_receipt(item)
    data = json.loads(path.read_text())
    binding = for_plan(plan)
    require(data.get("schema_version") == 1 and data.get("binding_sha256") == digest(binding)
            and data.get("capture_id") == capture_id(output)
            and data.get("runner") == runner
            and data.get("environment") == binding["environment"]
            and data.get("host_boot_id") == binding["host_boot_id"],
            "target process does not belong to this device binding/capture")
    require(type(data.get("pid")) is int and data["pid"] > 0
            and type(data.get("start_ticks")) is int and data["start_ticks"] > 0,
            "target process identity missing")
    return data


def exec_target(args):
    binding = validate(json.loads(args.binding.read_text()))
    require(receipt(SCRIPT) == binding["resolver"], "device launcher changed")
    require(snapshot(os.environ) == binding["environment"], "target inherited a different device environment")
    require(Path("/proc/sys/kernel/random/boot_id").read_text().strip() == binding["host_boot_id"],
            "target host differs from the device probe")
    runner = args.runner[1:] if args.runner[:1] == ["--"] else args.runner
    require(runner and Path(runner[0]).is_absolute(), "absolute target executable required")
    # os.execvpe preserves this PID. Shell runners must also replace their
    # process image so profiler records can be matched to the recorded PID.
    stat = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    data = {
        "schema_version": 1, "pid": os.getpid(), "start_ticks": int(stat[19]),
        "host_boot_id": binding["host_boot_id"], "binding_sha256": digest(binding),
        "capture_id": args.capture_id, "runner": runner, "environment": snapshot(os.environ),
    }
    with args.receipt.open("x") as stream:
        json.dump(data, stream, indent=2)
    os.execvpe(runner[0], runner, dict(os.environ))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    p = commands.add_parser("probe")
    p.add_argument("--application-device", type=int, required=True)
    p = commands.add_parser("exec")
    p.add_argument("--binding", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--capture-id", required=True)
    p.add_argument("runner", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.action == "probe":
            print("CANNBOT_DEVICE " + json.dumps(runtime_probe(args.application_device)))
        else:
            exec_target(args)
    except (ValueError, OSError, KeyError, AttributeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
