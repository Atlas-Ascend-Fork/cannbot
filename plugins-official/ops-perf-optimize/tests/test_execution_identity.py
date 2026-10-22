# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_case_sets import code_identity, identity  # noqa: E402

SCRIPT = ROOT / "scripts" / "validate_execution_identity.py"
SPEC = importlib.util.spec_from_file_location("validate_execution_identity", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "kernel.cpp").write_text("void kernel() {}\n", encoding="utf-8")
    request = write_json(tmp_path / "request.json", {})
    manifest = write_json(
        tmp_path / "run-manifest.json",
        {
            "schema_version": 2,
            "request": identity(request),
            "inputs": {"code": code_identity(source)},
            "configuration": {
                "target_socs": ["Ascend910_93"],
                "performance_reference": {"kind": "baseline", "target_ratio": 1.0},
            },
        },
    )
    built = tmp_path / "build" / "libop.so"
    loaded = tmp_path / "runtime" / "libop.so"
    built.parent.mkdir()
    loaded.parent.mkdir()
    built.write_bytes(b"same implementation")
    loaded.write_bytes(built.read_bytes())
    return manifest, source, built, loaded


def record(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest, _, built, loaded = fixture(tmp_path)
    build_log = tmp_path / "build.log"
    build_log.write_text("build succeeded\n", encoding="utf-8")
    loader_log = tmp_path / "loader.log"
    loader_log.write_text(f"loaded {loaded.resolve()}\n", encoding="utf-8")
    runtime = write_json(
        tmp_path / "runtime-evidence.json",
        {
            "method": "loader trace",
            "target_soc": "Ascend910_93",
            "source_artifacts": [MODULE.file_identity(loader_log)],
            "loaded_artifacts": [MODULE.file_identity(loaded)],
        },
    )
    output = tmp_path / "execution-identity.json"
    args = SimpleNamespace(
        manifest=manifest,
        target_soc="Ascend910_93",
        build_command="build operator",
        build_log=build_log,
        built_artifact=[built],
        runtime_evidence=runtime,
        out=output,
    )
    assert MODULE.record(args)["status"] == "complete"
    return manifest, output, loaded


def test_records_complete_source_build_load_chain(tmp_path: Path) -> None:
    manifest, output, _ = record(tmp_path)
    document = MODULE.validate_execution_identity(manifest, output)
    dependencies = MODULE.dependency_paths(document)
    assert document["targets"][0]["target_soc"] == "Ascend910_93"
    assert str((tmp_path / "build.log").resolve()) in dependencies
    assert str((tmp_path / "runtime-evidence.json").resolve()) in dependencies


def runtime_args(tmp_path, manifest, built, loaded, loader_line):
    build_log = tmp_path / "build.log"
    build_log.write_text("build succeeded\n", encoding="utf-8")
    loader_log = tmp_path / "loader.log"
    loader_log.write_text(loader_line, encoding="utf-8")
    runtime = write_json(
        tmp_path / "runtime-evidence.json",
        {
            "method": "loader trace",
            "source_artifacts": [MODULE.file_identity(loader_log)],
            "loaded_artifacts": [MODULE.file_identity(loaded)],
        },
    )
    return SimpleNamespace(
        manifest=manifest,
        target_soc="Ascend910_93",
        build_command="build operator",
        build_log=build_log,
        built_artifact=[built],
        runtime_evidence=runtime,
        out=tmp_path / "execution-identity.json",
    )


def test_rejects_loaded_artifact_from_another_build(tmp_path: Path) -> None:
    manifest, _, built, loaded = fixture(tmp_path)
    loaded.write_bytes(b"different implementation")
    args = runtime_args(tmp_path, manifest, built, loaded, f"loaded {loaded.resolve()}\n")
    with pytest.raises(ValueError, match="do not match the recorded build"):
        MODULE.record(args)


def test_rejects_runtime_claim_without_raw_evidence(tmp_path: Path) -> None:
    manifest, _, built, loaded = fixture(tmp_path)
    args = runtime_args(tmp_path, manifest, built, loaded, "no target artifact recorded\n")
    with pytest.raises(ValueError, match="does not identify loaded artifact"):
        MODULE.record(args)


def test_rejects_source_change_after_freeze(tmp_path: Path) -> None:
    manifest, output, _ = record(tmp_path)
    (tmp_path / "source" / "kernel.cpp").write_text("void changed() {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen source identity changed"):
        MODULE.validate_execution_identity(manifest, output)
