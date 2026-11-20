# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Tool-independent plugin boundary for profiling preparation and evidence."""

import argparse
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "profilers.json"
COMPARISON_KIND = "profile10_independent_v1"
_LEGACY_KINDS = {"npu_compute10_independent_v1"}


def registrations():
    entries = json.loads(CONFIG.read_text())["tools"]
    names = [entry["id"] for entry in entries]
    if (
        not names
        or any(not isinstance(name, str) or not name for name in names)
        or len(names) != len(set(names))
    ):
        raise ValueError("profiling tools must have unique nonempty IDs")
    return {entry["id"]: entry for entry in entries}


_TOOLS = registrations()
_BACKENDS = {
    name: str((ROOT / entry["adapter"]).resolve())
    for name, entry in _TOOLS.items()
    if entry.get("adapter")
}
_MODULES = {}


def backend(value=None):
    value = value or {}
    name = value.get("provider") or value.get("protocol", {}).get("profiler")
    if name is None:
        if len(_TOOLS) != 1:
            raise ValueError("select a profiling tool from the configured plugins")
        name = next(iter(_TOOLS))
    if name not in _BACKENDS:
        raise ValueError(f"unsupported or inactive profiling provider: {name}")
    location = _BACKENDS[name]
    if location not in _MODULES:
        if Path(location).is_absolute():
            module_name = (
                "_profiling_" + hashlib.sha256(location.encode()).hexdigest()[:16]
            )
            spec = importlib.util.spec_from_file_location(module_name, location)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        else:
            module = importlib.import_module(location)
        _MODULES[location] = module
    return _MODULES[location]


def report_adapter(provider):
    """Resolve the adapter for a configured specialist; guide-only tools have none."""
    if provider not in _TOOLS:
        raise ValueError(f"report provider is not configured: {provider}")
    return backend({"provider": provider}) if provider in _BACKENDS else None


def prepare(context=None):
    data = (
        json.loads(Path(context).read_text())
        if isinstance(context, (str, Path))
        else (context or {})
    )
    selected = data.get("tools", list(_TOOLS))
    if (
        not isinstance(selected, list)
        or not selected
        or len(set(selected)) != len(selected)
    ):
        raise ValueError("tools must select one or more configured IDs")
    bindings = []
    for name in selected:
        if name not in _TOOLS:
            raise ValueError(f"profiling tool is not configured: {name}")
        guide = (ROOT / _TOOLS[name]["guide"]).resolve()
        if not guide.is_file():
            raise ValueError(f"profiling guide missing: {guide}")
        child_context = data.get("per_tool", {}).get(name)
        if child_context is None:
            child_context = {
                k: v for k, v in data.items() if k not in ("tools", "per_tool")
            }
        binding = (
            backend({"provider": name}).prepare(child_context)
            if name in _BACKENDS
            else {"execution_mode": "skill", "report_context": {}}
        )
        binding["provider"] = name
        binding.setdefault("report_context", {})["tool_skill"] = str(guide)
        bindings.append(binding)
    return bindings[0] if len(bindings) == 1 else {"bindings": bindings}


def supports_comparison(kind):
    return kind == COMPARISON_KIND or kind in _LEGACY_KINDS


def validate_measurement(plan):
    return backend(plan).validate_measurement(plan)


def raw_sample(path, identity, plan):
    return backend(plan).raw_sample(path, identity, plan)


def check_command(command, identity, plan):
    return backend(plan).check_command(command, identity, plan)


def validate_failure(attempt, log, plan):
    return backend(plan).validate_failure(attempt, log)


def validate_publication(attempt, archive, summary, log, import_log, plan):
    return backend(plan).validate_publication(
        attempt, archive, summary, log, import_log, plan
    )


def collect_attempt(plan, identity, slot, attempt_dir, context=None):
    return backend(plan).collect_attempt(plan, identity, slot, attempt_dir, context)


def recover_attempt(plan, identity, attempt, directory):
    return backend(plan).recover_attempt(plan, identity, attempt, directory)


def validate_screening(report):
    if (
        report.get("status") != "diagnostic_valid"
        or report.get("performance_eligible") is not False
    ):
        raise ValueError("invalid diagnostic report")
    return backend(report).validate_screening(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true", required=True)
    parser.add_argument("--context", type=Path)
    parser.add_argument("--application-device", type=int,
                        help="Resolve this application-visible device in the inherited runtime environment")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        context = json.loads(args.context.read_text()) if args.context else {}
        if args.application_device is not None:
            if "per_tool" in context:
                raise ValueError("put application_device inside each per_tool context")
            context["application_device"] = args.application_device
        result = prepare(context)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(
            json.dumps(
                {"status": "unavailable", "reason": str(error)}, ensure_ascii=False
            )
        )
        return 2
    status = (
        "delegation_required" if result.get("execution_mode") == "skill" else "ready"
    )
    print(json.dumps({"status": status, "binding": str(args.out.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
