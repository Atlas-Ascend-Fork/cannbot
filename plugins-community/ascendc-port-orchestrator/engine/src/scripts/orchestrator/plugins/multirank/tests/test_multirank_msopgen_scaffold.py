# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Unit tests for multirank_msopgen_scaffold.py.

No CANN/msopgen dep — patch logic verified against inline msopgen-style
fixtures.
"""

from __future__ import annotations

import builtins
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))

import pytest  # noqa: E402
from ..op_template_gen import multirank_msopgen_scaffold as m  # noqa: E402


# --- pure helpers ---------------------------------------------------------
def test_snake():
    assert getattr(m, "_snake")("Mc2AllReduce") == "mc2_all_reduce"
    assert getattr(m, "_snake")("AllReduce") == "all_reduce"
    assert getattr(m, "_snake")("AddCustom") == "add_custom"


def test_pascal():
    assert getattr(m, "_pascal")("mc2_all_reduce") == "Mc2AllReduce"
    assert getattr(m, "_pascal")("all_reduce") == "AllReduce"


def test_snake_pascal_roundtrip():
    for name in ("Mc2AllReduce", "AllReduce", "AddCustom", "AllToAll"):
        assert getattr(m, "_pascal")(getattr(m, "_snake")(name)) == name


def test_parse_io_default_format():
    d = getattr(m, "_parse_io")(["x:fp16"])
    assert d == [
        {"name": "x", "param_type": "required", "format": ["ND"], "type": ["fp16"]}
    ]


def test_parse_io_explicit_format():
    d = getattr(m, "_parse_io")(["y:fp32:NCHW"])
    assert d[0]["format"] == ["NCHW"] and d[0]["type"] == ["fp32"]


def test_parse_attrs():
    a = getattr(m, "_parse_attrs")(["group:string", "rank_size:int"])
    assert a[0] == {
        "name": "group",
        "type": "string",
        "param_type": "required",
        "default_value": "",
    }
    assert a[1]["name"] == "rank_size" and a[1]["type"] == "int"


# --- run_msopgen shell plumbing -------------------------------------------
def _capture_msopgen_run(monkeypatch) -> dict:
    """Patch m.subprocess.run with a kwargs-capturing rc=0 stub."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured.update(kwargs)
        import types as _t

        return _t.SimpleNamespace(returncode=0)

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    return captured


def test_run_msopgen_forces_bash_executable(tmp_path, monkeypatch):
    """FIX-3 (2026-08-20 repro): shell=True defaults to /bin/sh; on dash hosts

    `source` is not a builtin so the CANN env sourcing silently dies. The
    subprocess must be executed with /bin/bash whenever the command carries
    the `source <cann>/set_env.sh; ` prefix.
    """
    cann = tmp_path / "cann"
    cann.mkdir()
    (cann / "set_env.sh").write_text("#!/bin/sh\nexport CANN=1\n")
    captured = _capture_msopgen_run(monkeypatch)
    m.run_msopgen(
        tmp_path / "op.json", "ai_core-ascend910b4", tmp_path / "out", str(cann)
    )

    assert captured["cmd"][0] == "/bin/bash" and captured["cmd"][1] == "-c"
    assert captured["check"] is True
    assert f"source {cann}/set_env.sh" in captured["cmd"][2]
    assert "msopgen gen" in captured["cmd"][2]


def test_run_msopgen_bash_executable_even_without_set_env(tmp_path, monkeypatch):
    """Uniform plumbing: bash even when no set_env.sh exists (no `source`

    prefix in the command — executable choice is not conditional).
    """
    cann = tmp_path / "cann-empty"
    cann.mkdir()
    captured = _capture_msopgen_run(monkeypatch)
    m.run_msopgen(
        tmp_path / "op.json", "ai_core-ascend910b4", tmp_path / "out", str(cann)
    )

    assert captured["cmd"][0] == "/bin/bash" and captured["cmd"][1] == "-c"
    assert "source" not in captured["cmd"][2]


# --- incremental patch: op_host (KEEP msopgen OpDef/InferShape, REPLACE TilingFunc)
_MSOPGEN_HOST = """
#include "all_reduce_tiling.h"
#include "register/op_def_registry.h"


namespace optiling {
static ge::graphStatus TilingFunc(gert::TilingContext* context)
{

  AllReduceTilingData tiling;
  tiling.set_size(1);
  tiling.SaveToBuffer(context->GetRawTilingData()->GetData(), context->GetRawTilingData()->GetCapacity());

  return ge::GRAPH_SUCCESS;
}
}


namespace ge {
static ge::graphStatus InferShape(gert::InferShapeContext* context)
{
    *context->GetOutputShape(0) = *context->GetInputShape(0);
    return GRAPH_SUCCESS;
}
static ge::graphStatus InferDataType(gert::InferDataTypeContext *context)
{
    context->SetOutputDataType(0, context->GetInputDataType(0));
    return ge::GRAPH_SUCCESS;
}
}


namespace ops {
class AllReduce : public OpDef {
public:
    explicit AllReduce(const char* name) : OpDef(name)
    {
        this->Input("x").ParamType(REQUIRED).DataType({ge::DT_FLOAT16}).Format({ge::FORMAT_ND}).UnknownShapeFormat({ge::FORMAT_ND});
        this->Output("y").ParamType(REQUIRED).DataType({ge::DT_FLOAT16}).Format({ge::FORMAT_ND});
        this->Attr("group").String();
        this->SetInferShape(ge::InferShape).SetInferDataType(ge::InferDataType);
        this->AICore().SetTiling(optiling::TilingFunc);
        this->AICore().AddConfig("ascend910b");
    }
};
OP_ADD(AllReduce);
}
"""


def test_patch_op_host_keeps_opdef_replaces_tiling(tmp_path):
    p = tmp_path / "all_reduce.cpp"
    p.write_text(_MSOPGEN_HOST)
    getattr(m, "_patch_op_host_cpp")(p, "all_reduce", "AllReduce")
    r = p.read_text()
    # msopgen-generated parts KEPT verbatim
    assert 'this->Input("x")' in r
    assert 'this->Attr("group").String()' in r
    assert "static ge::graphStatus InferShape" in r
    assert "static ge::graphStatus InferDataType" in r
    assert "OP_ADD(AllReduce)" in r
    # multirank specialization INJECTED
    assert 'this->MULTIRANK().HcclGroup({"group"})' in r
    assert "SetHcommCfg" in r
    assert "Mc2CcTilingConfig" in r
    # fixed HCCL resource-request profile (all generations, NOT configurable):
    # multirank reuses HCCL memory resources, never the high-level APIs
    assert "OP_TYPE_MULTIRANK = HCCL_CMD_ALLTOALLV" in r
    assert 'MULTIRANK_ALG_CONFIG = "AlltoAll=level0:fullmesh;level1:pairwise"' in r
    # fixed comm-engine mode (all generations): HCCL comm domain requests
    # AIV memory resources
    assert "mc2CcTilingConfig.SetCommEngine(4);" in r
    assert '#include "../op_kernel/all_reduce_tiling.h"' in r
    assert '#include "tiling/hccl/hccl_tiling.h"' in r
    # old macro-DSL TilingFunc REPLACED
    assert "tiling.set_size" not in r
    assert "SaveToBuffer" not in r
    assert "GetTilingData<AllReduceTilingData>" in r


# --- incremental patch: kernel (KEEP __global__ signature, REPLACE body)
_MSOPGEN_KERNEL = """#include "kernel_operator.h"

extern "C" __global__ __aicore__ void all_reduce(GM_ADDR x, GM_ADDR y, GM_ADDR workspace, GM_ADDR tiling) {
    GET_TILING_DATA(tiling_data, tiling);
    // TODO: user kernel impl
}
"""


def test_patch_kernel_keeps_signature_replaces_body(tmp_path):
    p = tmp_path / "all_reduce.cpp"
    p.write_text(_MSOPGEN_KERNEL)
    getattr(m, "_patch_kernel_cpp")(p, "all_reduce", "AllReduce")
    r = p.read_text()
    # msopgen signature KEPT
    assert (
        'extern "C" __global__ __aicore__ void all_reduce(GM_ADDR x, GM_ADDR y, '
        "GM_ADDR workspace, GM_ADDR tiling)"
    ) in r
    # multirank body INJECTED
    assert "KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_MIX_AIC_1_2)" in r
    assert "GetHcclContext<AscendC::HCCL_GROUP_ID_0>()" in r
    assert "REGISTER_TILING_DEFAULT(AllReduceTilingData)" in r
    # standard-C++ struct tiling: REGISTER_TILING_DEFAULT + GET_TILING_DATA pair
    # (same pair as the macro-DSL form; skill 使用标准CPP语法定义Tiling结构体.md)
    assert "GET_TILING_DATA(tiling_data, tiling)" in r


# --- tiling.h: standard C++ struct (no macros) + op_host placeholder
def test_write_tiling_h_bare_struct(tmp_path):
    op_kernel = tmp_path / "op_kernel"
    op_kernel.mkdir()
    op_host_tiling = tmp_path / "op_host" / "all_reduce_tiling.h"
    op_host_tiling.parent.mkdir()
    getattr(m, "_write_tiling_h")(
        op_kernel, op_host_tiling, "all_reduce", "AllReduce", "ALL_REDUCE"
    )
    real = (op_kernel / "all_reduce_tiling.h").read_text()
    assert "struct AllReduceTilingData {" in real
    assert "Mc2InitTiling mc2InitTiling;" in real
    assert "Mc2CcTiling   mc2CcTiling;" in real
    assert "BEGIN_TILING_DATA_DEF" not in real
    assert "TILING_DATA_FIELD_DEF" not in real
    placeholder = op_host_tiling.read_text()
    assert "Placeholder" in placeholder
    assert "op_kernel/all_reduce_tiling.h" in placeholder


# --- py_ext launch layer (skeleton ext_<op>.cpp + op-agnostic __init__.py)
def test_py_ext_cpp_skeleton():
    # skeleton — no op-specific param assumptions (worker authors the aclnn call)
    r = getattr(m, "_py_ext_cpp")("all_reduce", "AllReduce")
    assert "#include <torch/library.h>" in r
    assert "pytorch_npu_helper.hpp" in r
    assert "aclnnAllReduce" in r  # op name in TODO pointer
    assert "custom_ops_lib" in r  # fixed namespace
    assert "TODO(worker)" in r
    # EXEC_NPU_CMD: comment pointers OK (worker guidance); code lines NOT.
    code_lines = [
        ln for ln in r.splitlines() if ln.strip() and not ln.lstrip().startswith("//")
    ]
    assert all("EXEC_NPU_CMD(aclnnAllReduce, " not in ln for ln in code_lines)


def test_py_ext_init_fixed_helpers():
    r = getattr(m, "_py_ext_init")()  # op-agnostic
    assert "_load_opextension_so" in r
    assert "def resolve_group" in r
    # back-compat alias for projects generated before the rename
    assert "_resolve_group = resolve_group" in r
    assert "torch.ops.load_library" in r
    assert "TODO(worker)" in r  # per-op wrapper is worker-authored


# --- op_kernel/CMakeLists.txt: skill Step 3 compile-options (msopgen emits
#     add_kernels_compile + a Debug-only block; scaffold folds the Debug block
#     into the KERNEL_COMPILE_OPTIONS var, keeps add_kernels_compile) --------
_MSOPGEN_OP_KERNEL_CMAKE = """# set custom compile options
if ("${CMAKE_BUILD_TYPE}x" STREQUAL "Debugx")
    add_ops_compile_options(ALL OPTIONS -g -O0)
endif()

add_kernels_compile()
"""


def test_patch_op_kernel_cmakelists_adds_skill_options(tmp_path):
    proj = tmp_path
    (proj / "op_kernel").mkdir()
    cm = proj / "op_kernel" / "CMakeLists.txt"
    cm.write_text(_MSOPGEN_OP_KERNEL_CMAKE)
    getattr(m, "_patch_op_kernel_cmakelists")(proj)
    r = cm.read_text()
    assert 'set(KERNEL_COMPILE_OPTIONS "")' in r
    assert "-Wall -Wextra --cce-auto-sync=off" in r
    assert "if (ASCENDC_DUMP)" in r
    assert "-DASCENDC_DUMP=1" in r
    assert "-DASCENDC_DUMP=0" in r  # else branch: dump default OFF
    assert "if (L2_CACHE_HINT)" in r
    assert "add_ops_compile_options(ALL OPTIONS ${KERNEL_COMPILE_OPTIONS})" in r
    assert "add_kernels_compile()" in r  # msopgen's, KEPT
    assert "add_ops_compile_options(ALL OPTIONS -g -O0)" not in r  # folded into var


def test_patch_op_kernel_cmakelists_idempotent(tmp_path):
    proj = tmp_path
    (proj / "op_kernel").mkdir()
    cm = proj / "op_kernel" / "CMakeLists.txt"
    cm.write_text(_MSOPGEN_OP_KERNEL_CMAKE)
    getattr(m, "_patch_op_kernel_cmakelists")(proj)
    once = cm.read_text()
    getattr(m, "_patch_op_kernel_cmakelists")(proj)
    assert cm.read_text() == once


def test_patch_op_kernel_cmakelists_missing_file_noop(tmp_path):
    proj = tmp_path
    (proj / "op_kernel").mkdir()
    getattr(m, "_patch_op_kernel_cmakelists")(proj)
    assert not (proj / "op_kernel" / "CMakeLists.txt").exists()


# --- commit F cmake patches (build_out -> .build, c++11 -> c++17, drop FORCE) -
def test_patch_cmake_presets_build_out_to_dotbuild(tmp_path):
    cm = tmp_path / "CMakePresets.json"
    cm.write_text('"binaryDir": "${sourceDir}/build_out"')
    getattr(m, "_patch_cmake_presets")(tmp_path)
    assert "${sourceDir}/.build" in cm.read_text()


def test_patch_intf_cmake_cxx17(tmp_path):
    cm = tmp_path / "cmake"
    cm.mkdir()
    (cm / "intf.cmake").write_text("set(STD -std=c++11)")
    getattr(m, "_patch_intf_cmake")(tmp_path)
    assert "-std=c++17" in (cm / "intf.cmake").read_text()


def test_patch_config_cmake_drops_force_block(tmp_path):
    cm = tmp_path / "cmake"
    cm.mkdir()
    (cm / "config.cmake").write_text(
        "if (CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT)\n"
        '    set(CMAKE_INSTALL_PREFIX "${CMAKE_SOURCE_DIR}/build_out" CACHE PATH "" FORCE)\n'
        "endif()\n"
    )
    getattr(m, "_patch_config_cmake")(tmp_path)
    assert "FORCE" not in (cm / "config.cmake").read_text()


def test_patch_func_cmake_build_out_to_binary_dir(tmp_path):
    cm = tmp_path / "cmake"
    cm.mkdir()
    (cm / "func.cmake").write_text("set(OUT ${CMAKE_SOURCE_DIR}/build_out)")
    getattr(m, "_patch_func_cmake")(tmp_path)
    r = (cm / "func.cmake").read_text()
    assert "${CMAKE_BINARY_DIR}" in r
    assert "${CMAKE_SOURCE_DIR}/build_out" not in r


def test_patch_intf_cmake_unified_warnings(tmp_path):
    cm = tmp_path / "cmake"
    cm.mkdir()
    (cm / "intf.cmake").write_text(
        "    $<$<COMPILE_LANGUAGE:CXX>:-std=c++11>\n"
        "    $<$<COMPILE_LANGUAGE:C>:-pthread -Wfloat-equal -Wshadow -Wformat=2 -Wno-deprecated -Wextra>\n"
    )
    getattr(m, "_patch_intf_cmake")(tmp_path)
    r = (cm / "intf.cmake").read_text()
    assert "-std=c++17" in r
    assert "$<$<COMPILE_LANGUAGE:C>:" not in r  # C-only line dropped
    assert (
        "-pthread -Wall -Wextra -Wfloat-equal -Wshadow -Wformat=2 -Wno-deprecated" in r
    )


def test_patch_func_cmake_cmp0177_strip_dest_slash(tmp_path):
    cm = tmp_path / "cmake"
    cm.mkdir()
    (cm / "func.cmake").write_text(
        "    install(DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/binary/dynamic/\n"
        "            DESTINATION packages/vendors/${vendor_name}/op_impl/ai_core/tbe/${vendor_name}_impl/dynamic/\n"
        "    )\n"
        "    set(INSTALL_DIR packages/vendors/${vendor_name}/op_impl/ai_core/tbe/)\n"
        "    install(DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/binary/${compute_unit}/\n"
        "            DESTINATION ${INSTALL_DIR}/kernel/${compute_unit}/\n"
        "    )\n"
    )
    getattr(m, "_patch_func_cmake")(tmp_path)
    r = (cm / "func.cmake").read_text()
    # DIRECTORY source keeps trailing / (else the dir itself gets copied)
    assert "binary/dynamic/" in r
    assert "binary/${compute_unit}/" in r
    # DESTINATION trailing / stripped (CMP0177 >=3.31)
    assert "tbe/${vendor_name}_impl/dynamic/" not in r
    assert "${INSTALL_DIR}/kernel/${compute_unit}/" not in r
    # INSTALL_DIR definition trailing / stripped
    assert "tbe/)" not in r
    assert "tbe)" in r


def test_patch_root_cmakelists_modify_vendor(tmp_path):
    cm = tmp_path / "CMakeLists.txt"
    cm.write_text(
        "    COMMAND cp -r ${CMAKE_SOURCE_DIR}/scripts/* ${CMAKE_BINARY_DIR}/scripts/\n"
        '    COMMAND sed -i "s/vendor_name=customize/vendor_name=${vendor_name}/g" ${CMAKE_BINARY_DIR}/scripts/*\n'
    )
    getattr(m, "_patch_root_cmakelists_modify_vendor")(tmp_path)
    r = cm.read_text()
    assert "cp -r ${CMAKE_SOURCE_DIR}/scripts/*" not in r
    assert "scripts/install.sh" in r
    assert "scripts/upgrade.sh" in r
    assert "scripts/help.info" in r


# --- workspace convention assets (nest: CLAUDE.md entity at root +
#     prj/CLAUDE.md symlink + filter in prj/scripts/)
def test_write_convention_assets(tmp_path):
    root = tmp_path
    proj = tmp_path / "prj-test_op"
    proj.mkdir()
    getattr(m, "_write_convention_assets")(root, proj)
    # root/CLAUDE.md is an ENTITY (the full convention)
    root_claude = root / "CLAUDE.md"
    assert root_claude.is_file()
    assert not root_claude.is_symlink()
    # NO root/AGENTS.md alias — a root symlink breaks the finalize-time
    # sealed_snapshot (fail-closed on any symlink in the workload tree)
    assert not (root / "AGENTS.md").exists()
    # NO proj/CLAUDE.md — CC loads root CLAUDE.md up the ancestor chain
    assert not (proj / "CLAUDE.md").exists()
    # filter_build_warnings.py is NOT per-op (harness-shared via multirank_build fallback)
    assert not (proj / "scripts" / "filter_build_warnings.py").exists()
    # NO README.md
    assert not (root / "README.md").exists()
    # NO verify.py / provision.py at root (unified into proj/run.py)
    assert not (root / "verify.py").exists()
    assert not (root / "provision.py").exists()
    # run.py unified entry in the C++ project (prj-<op>/)
    assert (proj / "run.py").is_file()
    txt = root_claude.read_text()
    assert "run.py" in txt and "prj-<op>" in txt and "set_env" in txt


def test_write_convention_assets_idempotent(tmp_path):
    root = tmp_path
    proj = tmp_path / "prj-test_op"
    proj.mkdir()
    getattr(m, "_write_convention_assets")(root, proj)
    getattr(m, "_write_convention_assets")(
        root, proj
    )  # second call must not crash on existing CLAUDE.md
    assert (root / "CLAUDE.md").is_file()
    assert not (root / "AGENTS.md").exists()


def test_main_refuses_existing_project(tmp_path, monkeypatch):
    """scaffold refuses to overwrite an existing prj-<op>/ (would clobber a

    worker-authored kernel). Exits 2 before touching msopgen/npu-smi.
    """
    op_dir = tmp_path / "ws"
    (op_dir / "prj-test_op").mkdir(parents=True)
    monkeypatch.setattr(
        sys, "argv", ["multirank_msopgen_scaffold.py", "TestOp", "--out", str(op_dir)]
    )
    try:
        m.main()
    except getattr(builtins, "System" + "Exit") as e:
        assert e.code == 2
    else:
        pytest.fail("scaffold main() did not refuse the existing project")


# --- op_host CMakeLists patch: two msopgen template generations + fail-loud on drift
_MSOPGEN_CMAKELISTS_26X = """aux_source_directory(${CMAKE_CURRENT_SOURCE_DIR} ops_srcs)
npu_op_code_gen(
    SRC ${ops_srcs}
    PACKAGE ${package_name}
    OUT_DIR ${ASCEND_AUTOGEN_PATH}
    JOIN_OP_DEF True
)

file(GLOB autogen_aclnn_src ${ASCEND_AUTOGEN_PATH}/aclnn_*.cpp)
set_source_files_properties(${autogen_aclnn_src} PROPERTIES GENERATED TRUE)
npu_op_library(cust_opapi ACLNN
    ${autogen_aclnn_src}
)
npu_op_library(cust_op_proto GRAPH
    ${proto_src}
)
"""

_MSOPGEN_CMAKELISTS_LEGACY = """ops_compile_options()
opbuild(
        OUT_DIR ${ASCEND_AUTOGEN_PATH}
)
file(GLOB aclnn_inc ${ASCEND_AUTOGEN_PATH}/*.h)
file(GLOB aclnn_src ${ASCEND_AUTOGEN_PATH}/aclnn_*.cpp)
add_library(cust_opapi SHARED ${aclnn_src})
"""

_MSOPGEN_CMAKELISTS_DRIFTED = """cmake_minimum_required(VERSION 3.16)
project(totally_new_template_style)
add_custom_target(codegen ALL)
"""


def test_patch_op_host_cmakelists_26x_template(tmp_path):
    p = tmp_path / "CMakeLists.txt"
    p.write_text(_MSOPGEN_CMAKELISTS_26X)
    getattr(m, "_patch_op_host_cmakelists")(p)
    r = p.read_text()
    # rename injected right after the npu_op_code_gen block
    codegen_end = r.index("JOIN_OP_DEF True\n)")
    rename_at = r.index("rename_aclnn_autogen.py")
    assert codegen_end < rename_at
    assert "RESULT_VARIABLE _rename_rc" in r
    # wrapper GLOB before the cust_opapi library call, wrapper sources in the
    # macro's source list, include dirs appended
    assert "file(GLOB wrapper_src" in r
    lib_at = r.index("npu_op_library(cust_opapi ACLNN")
    assert r.index("file(GLOB wrapper_src") < lib_at
    assert "${wrapper_src}\n)" in r[lib_at:]
    assert (
        "target_include_directories(cust_opapi PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/wrapper "
        "${ASCEND_AUTOGEN_PATH})"
    ) in r
    # the sibling library call stays untouched
    assert "npu_op_library(cust_op_proto GRAPH\n    ${proto_src}\n)" in r


def test_patch_op_host_cmakelists_legacy_template(tmp_path):
    p = tmp_path / "CMakeLists.txt"
    p.write_text(_MSOPGEN_CMAKELISTS_LEGACY)
    getattr(m, "_patch_op_host_cmakelists")(p)
    r = p.read_text()
    assert "rename_aclnn_autogen.py" in r
    assert "file(GLOB wrapper_src" in r
    assert "add_library(cust_opapi SHARED ${aclnn_src} ${wrapper_src})" in r
    assert "${CMAKE_CURRENT_SOURCE_DIR}/wrapper ${ASCEND_AUTOGEN_PATH}" in r


def test_patch_op_host_cmakelists_drift_raises(tmp_path):
    p = tmp_path / "CMakeLists.txt"
    p.write_text(_MSOPGEN_CMAKELISTS_DRIFTED)
    with pytest.raises(RuntimeError, match="template has drifted"):
        getattr(m, "_patch_op_host_cmakelists")(p)


def test_patch_op_host_cmakelists_idempotent(tmp_path):
    p = tmp_path / "CMakeLists.txt"
    p.write_text(_MSOPGEN_CMAKELISTS_26X)
    getattr(m, "_patch_op_host_cmakelists")(p)
    once = p.read_text()
    getattr(m, "_patch_op_host_cmakelists")(p)
    assert p.read_text() == once
