#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""multirank op engineering scaffold via msopgen + multirank specialization patch.

Deterministic codegen (build Layer 3a): msopgen generates a generic AscendC op
project (the whole op_host OpDef / InferShape / InferDataType / kernel signature /
CMake / cmake util tree), then this script INCREMETALLY PATCHES only the multirank-
specific deltas — it does NOT regenerate what msopgen already produces correctly.

Patch boundary (what msopgen generates vs what multirank specializes):
- op_host/{op}.cpp: KEEP msopgen's OpDef (Input/Output/Attr chains), InferShape,
  InferDataType, OP_ADD (all generated from the op json). REPLACE only TilingFunc
  (msopgen's macro-DSL setter paradigm is incompatible with multirank's bare-struct +
  SetHcommCfg). INJECT `.MULTIRANK().HcclGroup({"group"})` + hccl/platform includes.
- op_kernel/{op}_tiling.h: REPLACE msopgen's macro-DSL (BEGIN_TILING_DATA_DEF)
  with a standard C++ struct (owner direction 2026-06-25: standard CPP syntax,
  no macros). Mc2InitTiling/Mc2CcTiling MUST be the first 2 fields (CANN contract).
- op_host/{op}_tiling.h: reduce to a placeholder (real def lives in op_kernel/).
- op_kernel/{op}.cpp: KEEP msopgen's `__global__` signature (GM_ADDR params from
  op json). REPLACE the body. Standard-C++ struct tiling uses the
  REGISTER_TILING_DEFAULT + GET_TILING_DATA pair (same pair as the macro-DSL
  form; skill 使用标准CPP语法定义Tiling结构体.md; reference op moe uses both).
  INJECT KERNEL_TYPE_MIX_AIC_1_2 + GetHcclContext init.
- op_host/wrapper/aclnn_{op}.cpp + scripts/rename_aclnn_autogen.py + CMakeLists
  patches: NEW (msopgen does NOT generate a wrapper, rename, or wrapper GLOB).

multirank HCCL tooling (HcclResource / CrossRankSync / window RDMA)
is INLINED from plugins/multirank/docs/multirank_communication.md P-P110-113 by the worker;
this scaffold emits placeholders pointing to that KB (HCCL tools inlined from
the KB, self-contained — design §3.1 + Layer 1). HCCL context init position
(AIV/AIC) is worker-decided (design §2.1).

CLI:
    python3 multirank_msopgen_scaffold.py <OpName> \
        --input x:fp16 --output y:fp16 --attr group:string --attr rank_size:int --attr rank_id:int \
        --out workspace/<op>

The HCCL resource-request profile (op type + alg chain) is FIXED in the
generated tiling: multirank reuses HCCL memory resources (window/memory
semantics), never the high-level collective APIs — HCCL_CMD_ALLTOALLV +
"AlltoAll=level0:fullmesh;level1:pairwise", all generations A2/A3/A5.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

CANN_DEFAULT = "/usr/local/Ascend/cann-8.5.1"


# ---------------------------------------------------------------------------
# msopgen plumbing
# ---------------------------------------------------------------------------
def infer_soc_version() -> str:
    """Derive ai_core-{soc} from npu-smi Chip Name (non-A3 path: lowercase)."""
    npu_smi = shutil.which("npu-smi") or "npu-smi"
    out = subprocess.run([npu_smi, "info"], capture_output=True, text=True).stdout
    m = re.search(r"\|\s*\d+\s+([A-Za-z0-9]+)\s+\|", out)
    if not m:
        raise RuntimeError("cannot parse Chip Name from `npu-smi info`")
    chip = m.group(1).lower()
    if not chip.startswith("ascend"):
        chip = "ascend" + chip
    return f"ai_core-{chip}"


def _parse_io(items: list[str]) -> list[dict]:
    """Parse 'name:dtype[:format]' into msopgen input/output desc."""
    descs = []
    for it in items:
        parts = it.split(":")
        name, dtype = parts[0], parts[1]
        fmt = parts[2] if len(parts) > 2 else "ND"
        descs.append(
            {"name": name, "param_type": "required", "format": [fmt], "type": [dtype]}
        )
    return descs


def _parse_attrs(items: list[str]) -> list[dict]:
    """Parse 'name:type' into msopgen attr desc."""
    return [
        {"name": n, "type": t, "param_type": "required", "default_value": ""}
        for n, t in (it.split(":", 1) for it in items)
    ]


def _snake(name: str) -> str:
    """PascalCase -> snake_case (matches msopgen file naming, e.g. Mc2AllReduce -> mc2_all_reduce)."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _pascal(snake: str) -> str:
    """snake_case -> PascalCase (e.g. mc2_all_reduce -> Mc2AllReduce)."""
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[_-]", snake))


def gen_op_json(op: str, inputs, outputs, attrs, path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "op": op,
                    "input_desc": inputs,
                    "output_desc": outputs,
                    "attr": attrs,
                }
            ],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def run_msopgen(op_json: Path, soc: str, out_dir: Path, cann: str) -> None:
    env = os.environ.copy()
    env.setdefault("ASCEND_CANN_PACKAGE_PATH", cann)
    env_cmd = ""
    set_env = Path(cann) / "set_env.sh"
    if set_env.is_file():
        env_cmd = f"source {set_env} 2>/dev/null; "
    # Bash invoked explicitly via -c (FIX-3, 2026-08-20 repro): /bin/sh —
    # on dash hosts `source` is not a builtin, so the CANN env
    # sourcing silently fails (its stderr is swallowed by 2>/dev/null) and
    # the scaffold dies. Force bash so the `source` prefix works everywhere.
    subprocess.run(
        [
            "/bin/bash",
            "-c",
            f"{env_cmd}msopgen gen -i {op_json} -f pytorch -c {soc} "
            f"-out {out_dir} -lan cpp",
        ],
        check=True,
        env=env,
    )


# ---------------------------------------------------------------------------
# multirank incremental patches (msopgen has no multirank option)
# ---------------------------------------------------------------------------
_MC2_OPTILING_TEMPLATE = """namespace optiling {{
namespace optiling {{

typedef enum {{
    ATTR_GROUP_INDEX = 0,
    ATTR_RANK_SIZE_INDEX,
    ATTR_RANK_ID_INDEX
}} ATTR_TYPE;

// Fixed HCCL resource-request profile: multirank reuses HCcl MEMORY
// resources (window/memory semantics) — never its high-level collective
// APIs — so the op type/alg only shape the resource request, not the
// kernel's communication. All generations A2/A3/A5.
static constexpr uint32_t OP_TYPE_MULTIRANK = HCCL_CMD_ALLTOALLV;
static const std::string MULTIRANK_ALG_CONFIG = "AlltoAll=level0:fullmesh;level1:pairwise";

static void SetHcommCfg(const gert::TilingContext *context,
                        {op_pascal}TilingData *tiling, const std::string &group)
{{
    (void)context;
    AscendC::Mc2CcTilingConfig mc2CcTilingConfig(group, OP_TYPE_MULTIRANK, MULTIRANK_ALG_CONFIG);
    // Fixed comm-engine mode (all generations A2/A3/A5): SetCommEngine takes
    // the HcclOpExpansionMode enum (typedef HcclConfigTypeOpExpansionMode);
    // value 4 lets the HCCL comm domain request AIV memory resources.
    mc2CcTilingConfig.SetCommEngine(4);
    mc2CcTilingConfig.GetTiling(tiling->mc2InitTiling);
    mc2CcTilingConfig.GetTiling(tiling->mc2CcTiling);
}}

static ge::graphStatus TilingFunc(gert::TilingContext* context)
{{
    {op_pascal}TilingData *tiling = context->GetTilingData<{op_pascal}TilingData>();
    if (tiling == nullptr) return ge::GRAPH_FAILED;

    auto attrs = context->GetAttrs();
    std::string group = "hccl_world_group";
    uint32_t numRanks = 1, currentRank = 0;
    if (attrs != nullptr) {{
        auto g = attrs->GetAttrPointer<char>(ATTR_GROUP_INDEX);
        auto rs = attrs->GetAttrPointer<int64_t>(ATTR_RANK_SIZE_INDEX);
        auto ri = attrs->GetAttrPointer<int64_t>(ATTR_RANK_ID_INDEX);
        if (g) group = std::string(g);
        if (rs) numRanks = static_cast<uint32_t>(*rs);
        if (ri) currentRank = static_cast<uint32_t>(*ri);
    }}
    tiling->numRanks = numRanks;
    tiling->currentRank = currentRank;
    // TODO(worker): business tiling fields (dims/offsets/core counts)

    SetHcommCfg(context, tiling, group);
    auto plat = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
    // Workspace = system workspace (AscendC API temporaries, GetLibApiWorkSpaceSize)
    //           + user workspace (op scratch). The framework advances the kernel-entry
    // workspace pointer past the system workspace, so ws[0] MUST be the SUM
    // (usrWsBytes + sysWorkspace) — NEVER max(usr, sys): max understates the total,
    // the framework still offsets sysWorkspace, and kernel user-workspace writes
    // overrun -> Ascend log "The DDR address of the MTE instruction is out of range".
    // See EC-85 (Ascend C 算子开发 → 编程指南 → 附录 → 常用操作 → 如何使用 workspace).
    // Workspace byte lengths are 64-bit (uint64_t) END TO END: a 32-bit
    // intermediate silently truncates near the 4GiB boundary, under-allocates
    // the workspace and the kernel's user-workspace writes overrun (observed
    // as a ~4.3GB shortfall). ws itself keeps the framework's size_t* (the
    // same width on this target); every computed length stays uint64_t.
    size_t *ws = context->GetWorkspaceSizes(1);
    uint64_t sysWorkspace = static_cast<uint64_t>(plat.GetLibApiWorkSpaceSize());
    uint64_t usrWsBytes = 0;  // TODO(worker): op scratch bytes (GM staging / cross-pipe buffers); AlignUp(<total>, 512)
    ws[0] = usrWsBytes + sysWorkspace;  // SUM — EC-85 (NOT max)
    context->SetBlockDim(plat.GetCoreNumAic());
    return ge::GRAPH_SUCCESS;
}}
}}}}"""


def _patch_op_host_cpp(path: Path, op: str, op_pascal: str) -> None:
    """Increment-patch msopgen's op_host/{op}.cpp.

    KEEP: OpDef class (Input/Output/Attr chains generated from op json),
    InferShape, InferDataType, OP_ADD — all correct, no need to regenerate.
    REPLACE: namespace optiling { TilingFunc } — msopgen's macro-DSL setter
    paradigm (`AllReduceTilingData tiling; tiling.set_size(); SaveToBuffer`)
    is incompatible with multirank's bare-struct pointer + SetHcommCfg paradigm.
    INJECT: hccl/platform includes, `.MULTIRANK().HcclGroup({"group"})`.
    """
    t = path.read_text(encoding="utf-8")
    t = t.replace(
        f'#include "{op}_tiling.h"',
        f'#include "../op_kernel/{op}_tiling.h"\n'
        f'#include "tiling/hccl/hccl_tiling.h"\n'
        f'#include "tiling/platform/platform_ascendc.h"\n'
        f"#include <string>",
        1,
    )
    mc2_optiling = _MC2_OPTILING_TEMPLATE.format(op_pascal=op_pascal)
    opt_start = t.index("namespace optiling {")
    ge_start = t.index("namespace ge {")
    t = t[:opt_start] + mc2_optiling + "\n\n" + t[ge_start:]
    t = t.replace(
        ".SetTiling(optiling::TilingFunc);",
        '.SetTiling(optiling::TilingFunc);\n        this->MULTIRANK().HcclGroup({"group"});',
        1,
    )
    path.write_text(t, encoding="utf-8")


def _patch_kernel_cpp(path: Path, op: str, op_pascal: str) -> None:
    """KEEP msopgen's `__global__` signature (GM_ADDR params from op json);
    REPLACE the body. Standard-C++ struct tiling uses the
    REGISTER_TILING_DEFAULT + GET_TILING_DATA pair (same pair as the macro-DSL
    form; skill 使用标准CPP语法定义Tiling结构体.md + reference op moe both use
    it). INJECT KERNEL_TYPE_MIX_AIC_1_2 + GetHcclContext init."""
    t = path.read_text(encoding="utf-8")
    m = re.search(r'extern "C" __global__ __aicore__ void \w+\([^)]*\)', t)
    if not m:
        raise RuntimeError(f"cannot find __global__ signature in {path}")
    sig = m.group(0)
    path.write_text(
        f'''#include "kernel_operator.h"
#include "{op}_tiling.h"
// multirank HCCL tooling: INLINE HcclResource/CrossRankSync/window RDMA
// from plugins/multirank/docs/multirank_communication.md P-P110-113 into a worker header.
// HCCL tools are INLINED from KB P-P110-113 (self-contained — no external include).

KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_MIX_AIC_1_2);

{sig} {{
    REGISTER_TILING_DEFAULT({op_pascal}TilingData);
    GET_TILING_DATA(tiling_data, tiling);

    // multirank A-class: HCCL context init (null-check). Init location (AIV/AIC) is
    // worker-decided per fusion structure -- NOT fixed to AIV-only.
    auto ctx = AscendC::GetHcclContext<AscendC::HCCL_GROUP_ID_0>();
    if (ctx == nullptr) return;

    // TODO(worker): inline HcclResource (P-P110); AIV/AIC fusion logic
    //   (compute + window RDMA P-P112 + CrossRankSync P-P111).
    //   Read tiling fields via `tiling_data.<field>` (GET_TILING_DATA above).
}}
''',
        encoding="utf-8",
    )


def _write_tiling_h(
    op_kernel_dir: Path, op_host_tiling: Path, op: str, op_pascal: str, op_upper: str
) -> None:
    """Standard C++ struct (owner direction 2026-06-25: no macro DSL) in
    op_kernel/; op_host/{op}_tiling.h reduced to a placeholder."""
    (op_kernel_dir / f"{op}_tiling.h").write_text(
        f"""#ifndef {op_upper}_TILING_H
#define {op_upper}_TILING_H

#include <cstdint>
#include "kernel_tiling/kernel_tiling.h"

struct {op_pascal}TilingData {{
    Mc2InitTiling mc2InitTiling;
    Mc2CcTiling   mc2CcTiling;
    uint32_t numRanks = 1;
    uint32_t currentRank = 0;
    // TODO(worker): business tiling fields
}};

#endif // {op_upper}_TILING_H
""",
        encoding="utf-8",
    )
    op_host_tiling.write_text(
        f"// Placeholder: TilingData is defined in op_kernel/{op}_tiling.h as a\n"
        f"// standard C++ struct (MULTIRANK requires Mc2InitTiling/Mc2CcTiling first 2\n"
        f"// fields; msopgen macro-DSL tiling replaced). Do not include this file;\n"
        f'// use #include "../op_kernel/{op}_tiling.h".\n',
        encoding="utf-8",
    )


def _wrapper_cpp(op: str, op_pascal: str) -> str:
    """multirank aclnn wrapper. msopgen does NOT generate a wrapper — this is new.
    The exact GetWorkspaceSize/op param list is back-filled from the autogen
    .build/autogen/aclnn_{op}.h by multirank_build.py after configure (deferred)."""
    return f"""#include "aclnn_{op}.h"

enum NnopbaseHcclServerType {{
    NNOPBASE_HCCL_SERVER_TYPE_AICPU = 0,
    NNOPBASE_HCCL_SERVER_TYPE_MTE,
    NNOPBASE_HCCL_SERVER_TYPE_END
}};
extern "C" void __attribute__((weak)) NnopbaseSetHcclServerType(
    void *executor, NnopbaseHcclServerType sType);

#ifdef __cplusplus
extern "C" {{
#endif

// TODO(worker): copy exact param list from .build/autogen/aclnn_{op}.h
// aclnnInner{op_pascal}GetWorkspaceSize / aclnnInner{op_pascal}, then forward.
__attribute__((visibility("default")))
aclnnStatus aclnn{op_pascal}GetWorkspaceSize(uint64_t *workspaceSize, aclOpExecutor **executor)
{{
    return aclnnInner{op_pascal}GetWorkspaceSize(workspaceSize, executor);
}}

__attribute__((visibility("default")))
aclnnStatus aclnn{op_pascal}(void *workspace, uint64_t workspaceSize,
                       aclOpExecutor *executor, aclrtStream stream)
{{
    // HCCL server on MTE (not AICPU): pairs with the kernel window-RDMA path
    // (GetHcclContext/HcclResource reuse the Hccl resource; AICPU hccl service
    // offline). multirank locks to window RDMA — high-level HCCL collective APIs
    // (HcclAllReduce etc.) use the AICPU service and conflict with this.
    if (NnopbaseSetHcclServerType) {{
        NnopbaseSetHcclServerType(executor, NNOPBASE_HCCL_SERVER_TYPE_MTE);
    }}
    return aclnnInner{op_pascal}(workspace, workspaceSize, executor, stream);
}}

#ifdef __cplusplus
}}
#endif
"""


_RENAME_ACLNN = '''#!/usr/bin/env python3
"""Rename autogen aclnn{op_pascal} -> aclnnInner{op_pascal} so the wrapper exposes public aclnn{op_pascal}."""
import re, sys
from pathlib import Path

if len(sys.argv) < 2:
    sys.exit(0)
d = Path(sys.argv[1])
for h in d.glob("aclnn_*.h"):
    stem = h.stem[5:]
    op = "".join(w.capitalize() for w in re.split(r"[_-]", stem))
    txt = h.read_text(encoding="utf-8", errors="ignore")
    txt = txt.replace(f"aclnn{op}", f"aclnnInner{op}")
    txt = txt.replace(f"aclnn{op.lower()}", f"aclnnInner{op.lower()}")
    h.write_text(txt, encoding="utf-8")
    cpp = h.with_suffix(".cpp")
    if cpp.is_file():
        t = cpp.read_text(encoding="utf-8", errors="ignore")
        t = t.replace(f"aclnn{op}", f"aclnnInner{op}")
        cpp.write_text(t, encoding="utf-8")
'''


def _cmake_patch_rename(t: str, cm: Path) -> str:
    """Patch 1: rename autogen aclnn{op} -> aclnnInner{op} after codegen."""
    if "rename_aclnn_autogen.py" in t:
        return t
    rename_block = (
        "\nexecute_process(COMMAND python3 ${CMAKE_SOURCE_DIR}/scripts/rename_aclnn_autogen.py"
        " ${ASCEND_AUTOGEN_PATH} RESULT_VARIABLE _rename_rc)\n"
        "if(NOT _rename_rc EQUAL 0)\n"
        '    message(WARNING "rename_aclnn_autogen.py failed ${_rename_rc}")\n'
        "endif()\n"
    )
    m_new = re.search(r"npu_op_code_gen\(.*?\n\)", t, re.DOTALL)
    legacy_anchor = "        OUT_DIR ${ASCEND_AUTOGEN_PATH}\n)"
    if m_new:
        _me = m_new.end()
        return t[:_me] + rename_block + t[_me:]
    if legacy_anchor in t:
        return t.replace(legacy_anchor, legacy_anchor + rename_block, 1)
    raise RuntimeError(
        f"op_host/CMakeLists.txt rename patch found no anchor in {cm}: "
        "neither the msopgen 26.x npu_op_code_gen(...) block nor the "
        "legacy opbuild OUT_DIR tail matched — the msopgen template "
        "has drifted; update the anchors in _patch_op_host_cmakelists"
    )


def _cmake_patch_wrapper(t: str, cm: Path) -> str:
    """Patch 2: compile the hand-written wrapper into cust_opapi."""
    if "wrapper_src" in t:
        return t
    wrapper_glob = (
        "file(GLOB wrapper_src ${CMAKE_CURRENT_SOURCE_DIR}/wrapper/aclnn_*.cpp)\n"
    )
    m_new = re.search(r"npu_op_library\(\s*cust_opapi\s+ACLNN(.*?)\n\)", t, re.DOTALL)
    legacy_glob = "file(GLOB aclnn_inc"
    legacy_lib = "add_library(cust_opapi SHARED ${aclnn_src})"
    if m_new:
        body = m_new.group(1).rstrip()
        replacement = (
            wrapper_glob
            + "npu_op_library(cust_opapi ACLNN"
            + body
            + "\n    ${wrapper_src}\n)\n"
            + "target_include_directories(cust_opapi PRIVATE "
            "${CMAKE_CURRENT_SOURCE_DIR}/wrapper ${ASCEND_AUTOGEN_PATH})"
        )
        _ms = m_new.start()
        _me = m_new.end()
        return t[:_ms] + replacement + t[_me:]
    if legacy_glob in t and legacy_lib in t:
        t = t.replace(legacy_glob, wrapper_glob + legacy_glob, 1)
        return t.replace(
            legacy_lib,
            "add_library(cust_opapi SHARED ${aclnn_src} ${wrapper_src})\n"
            "    target_include_directories(cust_opapi PRIVATE"
            " ${CMAKE_CURRENT_SOURCE_DIR}/wrapper ${ASCEND_AUTOGEN_PATH})",
            1,
        )
    raise RuntimeError(
        f"op_host/CMakeLists.txt wrapper patch found no anchor in {cm}: "
        "neither the msopgen 26.x npu_op_library(cust_opapi ACLNN ...) "
        "call nor the legacy add_library(cust_opapi SHARED ...) form "
        "matched — the msopgen template has drifted; update the anchors "
        "in _patch_op_host_cmakelists"
    )


def _patch_op_host_cmakelists(cm: Path) -> None:
    """Inject ONLY what msopgen does NOT generate (no duplication of msopgen
    CMake — it already links nnopbase/ascendcl/intf_pub to cust_optiling +
    cust_opapi and GLOBs autogen aclnn_*.cpp):
    1. rename_aclnn execute_process after codegen (renames aclnn -> aclnnInner
       so the wrapper can expose the public aclnn symbol).
    2. wrapper_src GLOB + cust_opapi sources + wrapper/autogen include dir
       (msopgen GLOBs only autogen aclnn_*.cpp; the multirank wrapper in wrapper/ is
       hand-written and must be compiled into cust_opapi).

    Two template generations are supported: msopgen 26.x macro style
    (`npu_op_code_gen(...)` / `npu_op_library(cust_opapi ACLNN ...)`) and the
    legacy style (`add_library(cust_opapi SHARED ...)`). A patch whose marker
    is absent MUST land — anchors are matched against both generations and a
    total miss raises (same fail-loud discipline as _patch_kernel_cpp): a
    silent str.replace no-op once left the wrapper uncompiled and surfaced
    only at runtime as a commEngine rejection.
    """
    t = cm.read_text(encoding="utf-8")
    t = _cmake_patch_rename(t, cm)
    t = _cmake_patch_wrapper(t, cm)
    cm.write_text(t, encoding="utf-8")


def _patch_cmake_presets(proj: Path) -> None:
    """CMakePresets binaryDir: msopgen defaults to build_out; skill standard uses
    .build (multirank_build also targets .build via -B)."""
    cm = proj / "CMakePresets.json"
    if not cm.is_file():
        return
    t = cm.read_text(encoding="utf-8")
    t = t.replace("${sourceDir}/build_out", "${sourceDir}/.build")
    cm.write_text(t, encoding="utf-8")


def _patch_intf_cmake(proj: Path) -> None:
    """intf.cmake: c++11 -> c++17; drop the C-language-only warning line and
    unify warnings without a language guard (skill standard P2)."""
    cm = proj / "cmake" / "intf.cmake"
    if not cm.is_file():
        return
    t = cm.read_text(encoding="utf-8")
    t = t.replace("-std=c++11", "-std=c++17")
    t = t.replace(
        "    $<$<COMPILE_LANGUAGE:C>:-pthread -Wfloat-equal -Wshadow -Wformat=2 -Wno-deprecated -Wextra>\n",
        "    -pthread -Wall -Wextra -Wfloat-equal -Wshadow -Wformat=2 -Wno-deprecated\n",
    )
    cm.write_text(t, encoding="utf-8")


def _patch_config_cmake(proj: Path) -> None:
    """config.cmake: drop the CMAKE_INSTALL_PREFIX=build_out FORCE block so the
    CMakePresets value wins (skill standard). Absent on msopgen >= 26 (no
    cmake/ tree) — the install prefix there is governed by the root
    CMakeLists INSTALL_PATH patch instead."""
    cm = proj / "cmake" / "config.cmake"
    if not cm.is_file():
        return  # msopgen >= 26 ships no cmake/ tree
    t = cm.read_text(encoding="utf-8")
    t = t.replace(
        "if (CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT)\n"
        '    set(CMAKE_INSTALL_PREFIX "${CMAKE_SOURCE_DIR}/build_out" CACHE PATH "" FORCE)\n'
        "endif()\n",
        "",
    )
    cm.write_text(t, encoding="utf-8")


def _patch_func_cmake(proj: Path) -> None:
    """func.cmake: (1) replace hardcoded ${CMAKE_SOURCE_DIR}/build_out with
    ${CMAKE_BINARY_DIR}; (2) drop trailing / on install() DESTINATION paths +
    the INSTALL_DIR definition (skill standard P4 — CMake >=3.31 CMP0177 path
    normalization warning; keep DIRECTORY source trailing / or the dir itself
    gets copied -> dynamic/dynamic/ nesting)."""
    cm = proj / "cmake" / "func.cmake"
    if not cm.is_file():
        return
    t = cm.read_text(encoding="utf-8")
    t = t.replace("${CMAKE_SOURCE_DIR}/build_out", "${CMAKE_BINARY_DIR}")
    # strip trailing / on DESTINATION lines (DIRECTORY source keeps its /)
    t = re.sub(r"(DESTINATION [^\n]*?)/(\s*\n)", r"\1\2", t)
    # strip trailing / on the INSTALL_DIR definition
    t = re.sub(r"(set\(INSTALL_DIR [^\n]*?)/(\s*\))", r"\1\2", t)
    cm.write_text(t, encoding="utf-8")


def _patch_root_cmakelists_modify_vendor(proj: Path) -> None:
    """Root CMakeLists.txt modify_vendor: `cp -r scripts/*` copies ALL scripts
    (incl. rename_aclnn_autogen.py + filter_build_warnings.py) into the build
    dir, where `sed scripts/*` can match a directory and error. Restrict to the
    three msopgen installer files (install.sh / upgrade.sh / help.info) — skill
    standard P6."""
    cm = proj / "CMakeLists.txt"
    if not cm.is_file():
        return
    t = cm.read_text(encoding="utf-8")
    old_cp = "COMMAND cp -r ${CMAKE_SOURCE_DIR}/scripts/* ${CMAKE_BINARY_DIR}/scripts/"
    new_cp = (
        "COMMAND cp ${CMAKE_SOURCE_DIR}/scripts/install.sh "
        "${CMAKE_SOURCE_DIR}/scripts/upgrade.sh "
        "${CMAKE_SOURCE_DIR}/scripts/help.info ${CMAKE_BINARY_DIR}/scripts/"
    )
    t = t.replace(old_cp, new_cp)
    cm.write_text(t, encoding="utf-8")


def _patch_root_cmakelists_install_path(proj: Path) -> None:
    """Root CMakeLists.txt npu_op_package INSTALL_PATH (msopgen-26 macro
    style): the template pins it to ${CMAKE_BINARY_DIR}/ and the macro
    OVERWRITES CMAKE_INSTALL_PREFIX with that value (func.cmake
    set(... PARENT_SCOPE)) — every install() rule then lands under .build/
    and .install/ is never generated at all (the runner's
    _activate_opp_env probes .install/packages/vendors/customize). Re-point
    it at ${CMAKE_INSTALL_PREFIX} so the whole install tree follows the
    -DCMAKE_INSTALL_PREFIX=<prj>/.install the build driver passes.

    Legacy templates (no npu_op_package macro) are skipped: their install
    prefix is governed by config.cmake's FORCE block, which
    _patch_config_cmake already drops.
    """
    cm = proj / "CMakeLists.txt"
    if not cm.is_file():
        return
    t = cm.read_text(encoding="utf-8")
    if "npu_op_package(" not in t:
        return  # legacy template — no macro-style INSTALL_PATH pin
    anchor = "INSTALL_PATH ${CMAKE_BINARY_DIR}/"
    replacement = "INSTALL_PATH ${CMAKE_INSTALL_PREFIX}/"
    if anchor not in t:
        raise RuntimeError(
            f"root CMakeLists.txt has npu_op_package but no {anchor!r} "
            f"anchor in {cm} — the msopgen-26 template has drifted; update "
            f"the anchors in _patch_root_cmakelists_install_path"
        )
    t = t.replace(anchor, replacement, 1)
    cm.write_text(t, encoding="utf-8")


def _patch_op_kernel_cmakelists(proj: Path) -> None:
    """op_kernel/CMakeLists.txt: align to ascendc-project-template-gen skill Step 3
    — fold msopgen's Debug-only add_ops_compile_options(-g -O0) into the
    KERNEL_COMPILE_OPTIONS var (-Wall -Wextra --cce-auto-sync=off + ASCENDC_DUMP +
    L2_CACHE_HINT). Keeps msopgen's add_kernels_compile() (msopgen emits it;
    scaffold does not regenerate the file)."""
    cm = proj / "op_kernel" / "CMakeLists.txt"
    if not cm.is_file():
        return
    t = cm.read_text(encoding="utf-8")
    if "KERNEL_COMPILE_OPTIONS" in t:
        return
    skill_block = (
        "# Append ALL kernel flags to KERNEL_COMPILE_OPTIONS; ONE add_ops_compile_options(ALL) below.\n"
        'set(KERNEL_COMPILE_OPTIONS "")\n'
        'if ("${CMAKE_BUILD_TYPE}x" STREQUAL "Debugx")\n'
        "    list(APPEND KERNEL_COMPILE_OPTIONS -g -O0)\n"
        "endif()\n"
        "list(APPEND KERNEL_COMPILE_OPTIONS -Wall -Wextra --cce-auto-sync=off)\n"
        "if (ASCENDC_DUMP)\n"
        "    list(APPEND KERNEL_COMPILE_OPTIONS -DASCENDC_DUMP=1)\n"
        "else()\n"
        "    # dump OFF; enable: python3 run.py build --dump (passes cmake -DASCENDC_DUMP=ON).\n"
        "    list(APPEND KERNEL_COMPILE_OPTIONS -DASCENDC_DUMP=0)\n"
        "endif()\n"
        "if (L2_CACHE_HINT)\n"
        "    list(APPEND KERNEL_COMPILE_OPTIONS -DL2_CACHE_HINT=1)\n"
        "endif()\n"
        "add_ops_compile_options(ALL OPTIONS ${KERNEL_COMPILE_OPTIONS})"
    )
    new_t, n = re.subn(
        r'if\s*\(\s*"\$\{CMAKE_BUILD_TYPE\}x"\s*STREQUAL\s*"Debugx"\s*\)\s*\n'
        r"\s*add_ops_compile_options\(ALL OPTIONS -g -O0\)\s*\n"
        r"endif\s*\(\s*\)",
        skill_block,
        t,
    )
    if n == 0:
        new_t = t.replace(
            "add_kernels_compile()", skill_block + "\n\nadd_kernels_compile()", 1
        )
    cm.write_text(new_t, encoding="utf-8")


# ---------------------------------------------------------------------------
# py_ext launch layer (Python import of the built .so via torch::Dispatcher)
# ---------------------------------------------------------------------------
def _py_ext_assets_dir() -> Path:
    """Locate the fixed py_ext assets (setup.py + pytorch_npu_helper.hpp).

    Primary: this tree's own op_template_gen/py_ext_assets; fallback: the
    single-card template tree's identical assets (engine/src/scripts/
    op_template_gen/py_ext_assets) — staged multirank copies may ship
    without the full multirank subtree, and both trees hold the same
    op-agnostic bytes. Fail-loud when neither exists: the py_ext launch
    layer cannot be staged without them. Resolved lazily (NOT at module
    import) so a missing dir never breaks importing this module.
    """
    here = Path(__file__).resolve().parent
    primary = here / "py_ext_assets"
    if primary.is_dir():
        return primary
    fallback = here.parents[3] / "op_template_gen" / "py_ext_assets"
    if fallback.is_dir():
        return fallback
    raise RuntimeError(
        f"py_ext assets not found: tried {primary} and {fallback} (need "
        f"setup.py + pytorch_npu_helper.hpp)"
    )


_MULTIRANK_ASSETS = Path(__file__).resolve().parent / "multirank_assets"


def _py_ext_cpp(op: str, op_pascal: str) -> str:
    """ext_{op}.cpp skeleton. Worker authors the op per its actual signature —
    param shapes vary per op (multi-input/output, str/int/other attrs, single vs
    tuple return, EXEC_NPU_CMD vs manual GetOpApiFuncAddr). The scaffold emits
    only the fixed entry structure + reference pointers, NOT a generated aclnn
    call (that would assume one param form)."""
    return f"""#include <torch/library.h>
#include "pytorch_npu_helper.hpp"

// multirank py_ext entry — aclnn{op_pascal} dispatch. multirank specialization
// (NnopbaseSetHcclServerType) is in op_host/wrapper, already built into
// libcust_opapi.so — this layer is a pure aclnn call (no multirank code here).
//
// TODO(worker): author the op per its actual signature:
//   1. {op}_impl_npu — NPU impl. aclnn{op_pascal} via EXEC_NPU_CMD(aclnn{op_pascal}, args...)
//      (see pytorch_npu_helper.hpp) OR manual GetOpApiFuncAddr + ConvertTypes.
//      String attrs need a local const char* lvalue (ConvertTypes binds by ref):
//        const char* g = group.c_str();
//      EXEC_NPU_CMD arg order = aclnn{op_pascal} signature (inputs + attrs + outputs).
//   2. {op}_impl_meta — shape inference (required by the dispatcher).
//   3. Register: TORCH_LIBRARY(custom_ops_lib, m) + m.def("...")
//      + TORCH_LIBRARY_IMPL PrivateUse1 (NPU) + Meta (autograd optional).
// Namespace is fixed: torch.ops.custom_ops_lib.{op} on the Python side.
"""


def _py_ext_init() -> str:
    """__init__.py: load_library + HCCL group helper (fixed, op-agnostic). The
    per-op wrapper is worker-authored (param shapes vary per op)."""
    return '''import pathlib
import torch
import torch.distributed as dist


def _load_opextension_so():
    so_dir = pathlib.Path(__file__).parent
    so_files = list(so_dir.glob('_C*.so'))
    if not so_files:
        raise FileNotFoundError(f"not find _C*.so in {so_dir}")
    torch.ops.load_library(str(so_files[0]))


_load_opextension_so()


def resolve_group(group=None):
    """Resolve (group_str, rank_size, rank_id) for the op launch.

    The HCCL binding lives HERE (op side): the harness/verifier only ever
    passes a torch ProcessGroup object (or nothing), never a backend comm
    name. `group` may be:
      - None        → WORLD group (standalone / non-isolated default)
      - a torch ProcessGroup (e.g. a dist.new_group subgroup from the
        verifier's isolation mode) → resolve the HCCL comm name + the
        subgroup's own rank/size from the group object.

    Fail-loud: any resolution failure RAISES — no fabricated default group
    name / rank identity is ever passed to the op launch.
    """
    if not dist.is_initialized():
        raise RuntimeError(
            "torch.distributed is not initialized — an multirank op launch needs an "
            "HCCL process group (multirank_verify inits one; for a standalone smoke "
            "test, init a single-rank group explicitly first)")
    pg = group if group is not None else dist.group.WORLD
    try:
        group_str = pg._get_backend(torch.device('npu')).get_hccl_comm_name(
            dist.get_rank())
    except AttributeError:
        try:
            group_str = pg.get_hccl_comm_name(dist.get_rank())
        except AttributeError as e:
            raise RuntimeError(
                "cannot resolve the HCCL comm name from the process group — "
                "this torch_npu exposes neither "
                "pg._get_backend(...).get_hccl_comm_name nor "
                "pg.get_hccl_comm_name") from e
    return group_str, dist.get_world_size(pg), dist.get_rank(pg)


# Back-compat alias: harness call sites use the public name above; projects
# generated before the rename may still reference _resolve_group.
_resolve_group = resolve_group


# TODO(worker): per-op wrapper. Param shapes vary per op — author per the op
# signature with an optional `group=None` kwarg (torch ProcessGroup, mirroring
# torch collectives); resolve via resolve_group(group) and call
# torch.ops.custom_ops_lib.<op>(..., group_str, rank_size, rank_id).
'''


def _write_convention_assets(root: Path, proj: Path) -> None:
    """Write the workspace convention assets under the nest layout:
      root/CLAUDE.md    (entity — full convention; auto-loaded by Claude Code)
      proj/run.py       (unified entry: build | verify | provision subcommands)
    filter_build_warnings.py is NOT copied per-op — multirank_build uses the shared
    harness copy (multirank_assets/scripts/) via _find_filter_script fallback. proj/scripts/
    holds only rename_aclnn_autogen.py (written by patch_mc2, required by msopgen opbuild).
    No AGENTS.md alias: a root symlink breaks the finalize-time sealed_snapshot
    (fail-closed on any symlink in the workload tree).
    The convention source is multirank_assets/template-CLAUDE.md — named CLAUDE.md
    in the TEMPLATE TREE it would be auto-loaded into any harness session
    that reads a file under multirank_assets/ (an asset file); its CLAUDE.md
    name is only meaningful INSIDE the generated op workspace."""
    root_claude = root / "CLAUDE.md"
    if root_claude.is_symlink() or root_claude.exists():
        root_claude.unlink()
    shutil.copy(_MULTIRANK_ASSETS / "template-CLAUDE.md", root_claude)
    shutil.copy(_MULTIRANK_ASSETS / "run.py", proj / "run.py")


def patch_mc2(proj: Path, op_snake: str, op_dir: Path | None = None) -> None:
    """Apply multirank incremental patches + py_ext launch layer to a msopgen project.

    All patches are incremental on msopgen's output (op_host/kernel read msopgen
    files; py_ext ships a skeleton + fixed assets) — no op-json params needed.
    proj = workspace/<op>/prj-<op>/ (C++ project); op_dir = workspace/<op>/ (root,
    where README/AGENTS/CLAUDE convention assets land). If op_dir is None the
    convention assets fall back to proj (legacy single-layer call sites).
    """
    op = op_snake
    op_pascal = _pascal(op_snake)
    op_upper = op_snake.upper()
    op_host = proj / "op_host"
    op_kernel = proj / "op_kernel"
    _patch_op_host_cpp(op_host / f"{op}.cpp", op, op_pascal)
    _patch_kernel_cpp(op_kernel / f"{op}.cpp", op, op_pascal)
    _write_tiling_h(op_kernel, op_host / f"{op}_tiling.h", op, op_pascal, op_upper)
    wrap = op_host / "wrapper"
    wrap.mkdir(exist_ok=True)
    (wrap / f"aclnn_{op}.cpp").write_text(_wrapper_cpp(op, op_pascal), encoding="utf-8")
    _patch_op_host_cmakelists(op_host / "CMakeLists.txt")
    _patch_cmake_presets(proj)
    _patch_intf_cmake(proj)
    _patch_config_cmake(proj)
    _patch_func_cmake(proj)
    _patch_root_cmakelists_modify_vendor(proj)
    _patch_root_cmakelists_install_path(proj)
    _patch_op_kernel_cmakelists(proj)
    scripts = proj / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "rename_aclnn_autogen.py").write_text(_RENAME_ACLNN, encoding="utf-8")
    # py_ext launch layer (Python import of the built .so via torch::Dispatcher)
    py_ext = proj / "py_ext"
    py_ext.mkdir(exist_ok=True)
    (py_ext / f"ext_{op}.cpp").write_text(_py_ext_cpp(op, op_pascal), encoding="utf-8")
    (py_ext / "__init__.py").write_text(_py_ext_init(), encoding="utf-8")
    py_ext_assets = _py_ext_assets_dir()
    shutil.copy(py_ext_assets / "setup.py", py_ext / "setup.py")
    shutil.copy(
        py_ext_assets / "pytorch_npu_helper.hpp", py_ext / "pytorch_npu_helper.hpp"
    )
    # workspace convention assets — persistent, auto-sensed by every agent that
    # reads a file under root/ or proj/ (CLAUDE.md auto-loaded into context).
    _write_convention_assets(op_dir if op_dir is not None else proj, proj)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
_DEFAULT_MC2_ATTRS = [
    {
        "name": "group",
        "type": "string",
        "param_type": "required",
        "default_value": "",
    },
    {
        "name": "rank_size",
        "type": "int",
        "param_type": "required",
        "default_value": "1",
    },
    {
        "name": "rank_id",
        "type": "int",
        "param_type": "required",
        "default_value": "0",
    },
]


def _scaffold_args():
    """Parse the scaffold CLI contract."""
    ap = argparse.ArgumentParser(description="multirank msopgen scaffold")
    ap.add_argument("op", help="PascalCase op name (e.g. AllReduce)")
    ap.add_argument("--input", action="append", default=[], help="name:dtype[:format]")
    ap.add_argument("--output", action="append", default=[], help="name:dtype[:format]")
    ap.add_argument("--attr", action="append", default=[], help="name:type")
    ap.add_argument("--out", required=True, help="output project dir")
    ap.add_argument("--cann", default=CANN_DEFAULT)
    ap.add_argument("--soc", default=None, help="ai_core-{soc}; auto-detect if unset")
    return ap, ap.parse_args()


def main() -> int:
    ap, args = _scaffold_args()
    op = args.op
    op_snake = _snake(op)
    op_dir = args.out.rstrip("/")
    proj = Path(op_dir) / f"prj-{op_snake}"
    if proj.is_dir():
        ap.error(
            f"{proj} already exists — scaffold refuses to overwrite a project "
            f"that may contain a worker-authored kernel. To regenerate, move/"
            f"delete the dir first (or rerun the orchestrator with --cold-start)."
        )
    inputs = _parse_io(args.input)
    outputs = _parse_io(args.output)
    attrs = _parse_attrs(args.attr) or _DEFAULT_MC2_ATTRS
    soc = args.soc or infer_soc_version()

    op_json = Path(op_dir) / f"{op_snake}_op.json"
    op_json.parent.mkdir(parents=True, exist_ok=True)
    gen_op_json(op, inputs, outputs, attrs, op_json)
    log.info(f"[scaffold] wrote {op_json}")
    run_msopgen(op_json, soc, proj, args.cann)
    log.info(f"[scaffold] msopgen generated {proj}")
    patch_mc2(proj, op_snake, op_dir=Path(op_dir))
    log.info(f"[scaffold] patched multirank specialization into {proj}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
