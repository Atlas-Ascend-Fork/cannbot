# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

import copy
import importlib.util
import os
import shutil
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "ops-perf-optimize-workflow"
    / "scripts"
    / "validate_source_isolation.py"
)
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("source_isolation", SCRIPT)
assert SPEC and SPEC.loader
ISOLATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ISOLATION)
TARGETS = ["Ascend950"]


def write(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def prepared(tmp_path: Path) -> tuple[Path, Path, dict]:
    baseline, candidate = tmp_path / "baseline", tmp_path / "candidate"
    write(baseline, "op_kernel/shared.h", "template<class T> void Legacy(T x) { Compute(x); }\n")
    write(baseline, "common/params.h", "constexpr int kTile = 128;\n")
    write(baseline, "op_kernel/entry.cpp", "void Run() {\n  Legacy(x);\n}\n")
    write(baseline, "op_kernel/uninvolved.h", "void OtherShape() { Legacy(y); }\n")
    write(baseline, "op_host/config/ascend910b/op.json", '{"source": "shared.h"}\n')
    write(baseline, "CMakeLists.txt", "add_subdirectory(op_kernel)\n")
    shutil.copytree(baseline, candidate)
    scope = {
        "schema_version": 1,
        "target_socs": TARGETS,
        "baseline_files": ISOLATION.snapshot(baseline),
        "editable_ranges": {
            "op_kernel/entry.cpp": [{
                "start": 2, "end": 2, "kind": "routing",
                "reason": "Dispatch only; original shared implementation remains intact",
            }],
        },
        "new_files": {"op_kernel/arch35/optimized.h": {"copied_from": "op_kernel/shared.h"}},
    }
    write(candidate, "op_kernel/arch35/optimized.h", "template<class T> void Optimized(T x) { FastCompute(x); }\n")
    write(
        candidate,
        "op_kernel/entry.cpp",
        "void Run() {\n  if (TargetSoc() && SupportedShape()) Optimized(x);\n  else Legacy(x);\n}\n",
    )
    return baseline, candidate, scope


def test_copy_and_narrow_route_edits_pass(prepared) -> None:
    baseline, candidate, scope = prepared
    report = ISOLATION.validate_source_isolation(scope, baseline, candidate, TARGETS)
    assert report["decision"] == "pass"
    assert (baseline / "op_kernel/shared.h").read_bytes() == (candidate / "op_kernel/shared.h").read_bytes()


@pytest.mark.parametrize("path,text", [
    ("op_kernel/shared.h", "template<class T> void Legacy(T x) { FastCompute(x); }\n"),
    ("common/params.h", "constexpr int kTile = 256;\n"),
    ("op_kernel/uninvolved.h", "void OtherShape() { Optimized(y); }\n"),
    ("op_host/config/ascend910b/op.json", '{"source": "arch35/optimized.h"}\n'),
    ("CMakeLists.txt", "add_subdirectory(arch35)\n"),
])
def test_shared_helpers_uninvolved_templates_and_build_routes_are_protected(prepared, path, text) -> None:
    baseline, candidate, scope = prepared
    write(candidate, path, text)
    report = ISOLATION.validate_source_isolation(scope, baseline, candidate, TARGETS)
    assert report["decision"] == "fail"
    assert any(path in error for error in report["failures"])


def test_all_target_socs_does_not_unlock_other_templates(prepared) -> None:
    baseline, candidate, scope = prepared
    scope["target_socs"] = ["Ascend910B", "Ascend950"]
    write(candidate, "op_kernel/uninvolved.h", "void OtherShape() { Optimized(y); }\n")
    assert ISOLATION.validate_source_isolation(scope, baseline, candidate, scope["target_socs"])["decision"] == "fail"


def test_insertions_do_not_move_permission_to_neighboring_code(prepared) -> None:
    baseline, candidate, scope = prepared
    write(
        candidate,
        "op_kernel/entry.cpp",
        "void ChangedInterface() {\n  if (TargetSoc()) Optimized(x);\n  else Legacy(x);\n}\n",
    )
    assert ISOLATION.validate_source_isolation(scope, baseline, candidate, TARGETS)["decision"] == "fail"


@pytest.mark.parametrize("change", ["delete", "undeclared_new", "missing_copy"])
def test_file_inventory_cannot_be_silently_changed(prepared, change) -> None:
    baseline, candidate, scope = prepared
    if change == "delete":
        (candidate / "op_kernel/shared.h").unlink()
    elif change == "undeclared_new":
        write(candidate, "common/override.h", "#define kTile 256\n")
    else:
        (candidate / "op_kernel/arch35/optimized.h").unlink()
    assert ISOLATION.validate_source_isolation(scope, baseline, candidate, TARGETS)["decision"] == "fail"


@pytest.mark.parametrize("field", ["baseline_files", "target_socs", "copied_from", "range"])
def test_invalid_or_stale_scope_is_rejected(prepared, field) -> None:
    baseline, candidate, original = prepared
    scope = copy.deepcopy(original)
    if field == "baseline_files":
        scope["baseline_files"].pop("common/params.h")
    elif field == "target_socs":
        scope[field] = ["Ascend910B"]
    elif field == "copied_from":
        scope["new_files"]["op_kernel/arch35/optimized.h"][field] = "../outside.h"
    else:
        scope["editable_ranges"]["op_kernel/entry.cpp"][0]["end"] = 500
    with pytest.raises(ValueError):
        ISOLATION.validate_source_isolation(scope, baseline, candidate, TARGETS)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory_symlink"])
def test_aliasing_original_source_is_rejected(prepared, kind) -> None:
    baseline, candidate, scope = prepared
    if kind == "directory_symlink":
        (candidate / "linked_common").symlink_to(baseline / "common", target_is_directory=True)
    else:
        path = candidate / "common/params.h"
        path.unlink()
        if kind == "symlink":
            path.symlink_to(baseline / "common/params.h")
        else:
            path.hardlink_to(baseline / "common/params.h")
    with pytest.raises(ValueError, match="isolated"):
        ISOLATION.validate_source_isolation(scope, baseline, candidate, TARGETS)


def test_reports_do_not_become_source_changes(prepared) -> None:
    baseline, candidate, scope = prepared
    write(candidate, "scheme-conformance.json", '{"decision": "pass"}\n')
    assert ISOLATION.validate_source_isolation(scope, baseline, candidate, TARGETS)["decision"] == "pass"


@pytest.mark.skipif(not os.environ.get("OPS_PERF_VALIDATION_ROOT"), reason="optional real operator checkout")
@pytest.mark.parametrize("old,new", [
    ("kBufferNum = 2", "kBufferNum = 3"),
    ("kStreamingTwoPass = 1", "kStreamingTwoPass = 2"),
])
def test_xllm_shared_code_mutation_in_physical_copy_is_rejected(tmp_path: Path, old: str, new: str) -> None:
    original = Path(os.environ["OPS_PERF_VALIDATION_ROOT"]) / "xllm-ops/xllm_ops/layer_norm_fwd"
    before = ISOLATION.snapshot(original)
    declaration = (original / "op_host/layer_norm_fwd_def.cpp").read_text()
    assert all(f'AddConfig("{soc}"' in declaration for soc in ("ascend910b", "ascend910_93", "ascend950"))
    baseline, candidate = tmp_path / "baseline", tmp_path / "candidate"
    shutil.copytree(original, baseline)
    shutil.copytree(original, candidate)
    scope = {
        "schema_version": 1, "target_socs": TARGETS,
        "baseline_files": ISOLATION.snapshot(baseline), "editable_ranges": {}, "new_files": {},
    }
    assert ISOLATION.validate_source_isolation(scope, baseline, candidate, TARGETS)["decision"] == "pass"
    kernel = candidate / "op_kernel/layer_norm_fwd.cpp"
    source = kernel.read_text()
    assert source.count(old) == 1
    kernel.write_text(source.replace(old, new), encoding="utf-8")
    report = ISOLATION.validate_source_isolation(scope, baseline, candidate, TARGETS)
    assert report["decision"] == "fail"
    assert any("op_kernel/layer_norm_fwd.cpp" in error for error in report["failures"])
    assert ISOLATION.snapshot(original) == before
