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
"""Supply pinned standalone workflow helpers; never alter harness state or user tools."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

LOGGER = logging.getLogger(__name__)

TOOLS = {
    "validate_contract_consistency.py": ["--units-dir", "--test-dir"],
    "check_impl_progress.py": [
        "--work-dir", "--require-whitebox", "--require-blackbox", "--require-performance",
        "--run-sheet", "--device", "--unit", "--enter-unit",
    ],
    "check_design_evidence.py": ["--work-dir", "--snapshot"],
    "check_perf_contract.py": ["--contract", "--purpose", "--measurement", "--reference"],
    "validate_unit_contracts.py": ["--units-dir"],
    "review_fix.py": ["baseline", "--work-dir"],
    "assemble_cannbotdsl_design.py": ["--help"],
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic_create(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        temporary.chmod(0o444)
        os.link(temporary, path)
    except FileExistsError as error:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            raise ValueError(f"runtime tool conflict; no overwrite: {path}") from error
    finally:
        temporary.unlink(missing_ok=True)


def static_children(document, workflow, work):
    """Yield existing subgraphs, or None for a runtime-generated child."""
    if not isinstance(document, dict):
        return
    nodes = document.get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("workflow nodes must be a list")
    for node in nodes:
        if not isinstance(node, dict) or node.get("task_type") != "subgraph":
            continue
        name = node.get("file")
        if not isinstance(name, str):
            continue
        candidates = (work / name, workflow.parent / name)
        yield next((candidate for candidate in candidates if candidate.is_file()), None)


def required(workflow, work):
    """Follow existing static inputs only; generated children use the same pinned helpers."""
    import yaml

    seen = set()
    found = False

    def visit(path):
        nonlocal found
        path = path.resolve(strict=True)
        if path in seen:
            return
        seen.add(path)
        document = yaml.safe_load(path.read_text())
        serialized = yaml.safe_dump(document, allow_unicode=True)
        found = found or any(name in serialized for name in TOOLS)
        for candidate in static_children(document, workflow, work):
            if candidate is None:
                # Generated definitions do not exist yet; pin the same helpers now.
                found = True
            else:
                visit(candidate)
    visit(workflow)
    return found


def tool_matches(path, info):
    if not isinstance(info, dict) or path.is_symlink() or not path.is_file():
        return False
    if sha(path.read_bytes()) != info.get("sha256"):
        return False
    flags = info.get("required_help")
    if not isinstance(flags, list) or not flags:
        return False
    return all(isinstance(flag, str) and flag for flag in flags)


def file_conflicts(path, data):
    if path.is_symlink():
        return True
    return path.exists() and (not path.is_file() or path.read_bytes() != data)


def verify(work, manifest):
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("unsupported runtime tools manifest")
    tools = manifest.get("tools")
    if not isinstance(tools, dict) or not tools:
        raise ValueError("incomplete runtime tools manifest")
    for name, info in tools.items():
        if not isinstance(name, str) or Path(name).name != name or not name.endswith(".py"):
            raise ValueError("invalid runtime tool name")
        path = work / "scripts" / name
        if not tool_matches(path, info):
            raise ValueError(f"pinned runtime tool missing or modified: {path}; not repairing in place")
    bootstrap = work / ".workflow-tools/bootstrap.py"
    if (bootstrap.is_symlink() or not bootstrap.is_file()
            or sha(bootstrap.read_bytes()) != manifest.get("bootstrap_sha256")):
        raise ValueError("pinned runtime bootstrap missing or modified; not repairing in place")
    return manifest


def prepare(workflow, work, source=None):
    source = source or Path(__file__).resolve().parent
    root = work / ".workflow-tools"
    manifest_path = root / "manifest.json"
    if root.is_symlink() or (work / "scripts").is_symlink():
        raise ValueError("runtime tool directories must not be symlinks")
    if manifest_path.exists() or manifest_path.is_symlink():
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError("invalid runtime tools manifest path")
        manifest = verify(work, json.loads(manifest_path.read_text()))
        if manifest.get("workflow_sha256") != sha(workflow.read_bytes()):
            raise ValueError("workflow differs from pinned runtime tools; use the frozen YAML or a new run directory")
        return root
    if not required(workflow, work):
        return None
    # Preflight every destination before publishing anything; preserve unrelated user files.
    payloads = {}
    for name in TOOLS:
        data = (source / name).read_bytes()
        compile(data, name, "exec")
        path = work / "scripts" / name
        if file_conflicts(path, data):
            raise ValueError(f"runtime tool conflict; no overwrite: {path}; use a new run directory")
        payloads[name] = data
    bootstrap = Path(__file__).resolve().read_bytes()
    bootstrap_path = root / "bootstrap.py"
    if file_conflicts(bootstrap_path, bootstrap):
        raise ValueError(f"runtime bootstrap conflict; no overwrite: {bootstrap_path}")
    manifest = {"version": 1, "workflow_sha256": sha(workflow.read_bytes()),
                "unit_loop_required": "--enter-unit" in workflow.read_text(),
                "bootstrap_sha256": sha(bootstrap),
                "tools": {name: {"sha256": sha(data), "required_help": TOOLS[name]}
                          for name, data in payloads.items()}}
    for name, data in payloads.items():
        atomic_create(work / "scripts" / name, data)
    atomic_create(root / "bootstrap.py", bootstrap)
    atomic_create(manifest_path, (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
    verify(work, manifest)
    return root


def preflight(root):
    work = root.parent
    manifest = verify(work, json.loads((root / "manifest.json").read_text()))
    evidence = {"python": sys.executable, "python_version": sys.version, "tools": {}}
    error = None
    for name, info in manifest["tools"].items():
        try:
            result = subprocess.run([sys.executable, str(work / "scripts" / name), "--help"],
                                    cwd=work, capture_output=True, text=True, timeout=30)
            output = result.stdout + result.stderr
            passed = result.returncode == 0 and all(flag in output for flag in info["required_help"])
            evidence["tools"][name] = {"returncode": result.returncode, "help": output,
                                       "parameters_present": passed}
            if not passed:
                error = f"runtime tool import/CLI preflight failed: {name}"
                break
        except (OSError, subprocess.TimeoutExpired) as exc:
            evidence["tools"][name] = {"error": str(exc)}
            error = f"runtime tool could not start: {name}"
            break
    evidence["status"] = "fail" if error else "pass"
    record = root / f"preflight-{uuid.uuid4().hex}.json"
    atomic_create(record, (json.dumps(evidence, ensure_ascii=False, indent=2) + "\n").encode())
    if error:
        raise ValueError(f"{error}; evidence: {record}")
    LOGGER.info("runtime tools preflight passed; evidence: %s", record)


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", required=True, type=Path)
    args = parser.parse_args()
    try:
        preflight(args.preflight.resolve())
    except (OSError, ValueError, SyntaxError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
