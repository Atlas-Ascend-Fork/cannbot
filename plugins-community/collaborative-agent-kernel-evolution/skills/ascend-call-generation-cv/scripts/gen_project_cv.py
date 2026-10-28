#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------


"""
Use msopgen to create AscendC project for Cube+Vector (CV) fused operators.
Extends the standard gen_project.py with Catlass include paths and AIC/AIV dispatch template.

Usage:
    python3 gen_project_cv.py <op_name> <json_file_path>

Examples:
    python3 gen_project_cv.py matmul_gelu output/matmul_gelu/matmul_gelu_project.json
"""

from pathlib import Path
import logging
import argparse
import sys

# Add parent skill's scripts to path for reuse
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ascend-call-generation" / "scripts"))
from gen_project import prepare_ascend_project


# Catlass include path for CANN 8.x on Ascend 910B
# The kernel compiler (TBE/opc) does NOT use CMake's include_directories.
# Must use add_ops_compile_options(-I...) in op_kernel/CMakeLists.txt.
CATLASS_INCLUDE_CANDIDATES = [
    # CANN 8.5.0+ (new path structure with ops_legacy)
    "/usr/local/Ascend/cann-8.5.0/opp/built-in/op_impl/ai_core/tbe/impl/ops_legacy/ascendc/common/catlass/include",
    "/usr/local/Ascend/ascend-toolkit/latest/opp/built-in/op_impl/ai_core/tbe/impl"
    "/ops_legacy/ascendc/common/catlass/include",
    # CANN 8.3.x (old path structure)
    "/usr/local/Ascend/ascend-toolkit/8.3.RC1/opp/built-in/op_impl/ai_core/tbe/impl/ascendc/common/catlass/include",
    "/usr/local/Ascend/ascend-toolkit/8.3.RC2/opp/built-in/op_impl/ai_core/tbe/impl/ascendc/common/catlass/include",
    "/usr/local/Ascend/ascend-toolkit/latest/opp/built-in/op_impl/ai_core/tbe/impl/ascendc/common/catlass/include",
]


def find_catlass_include() -> str:
    """Find the actual catlass include path on this system."""
    for path in CATLASS_INCLUDE_CANDIDATES:
        if Path(path).exists():
            return path
    # Fallback: search filesystem (both old and new structures)
    import glob
    patterns = [
        "/usr/local/Ascend/*/opp/built-in/op_impl/ai_core/tbe/impl/ops_legacy/ascendc/common/catlass/include",
        "/usr/local/Ascend/ascend-toolkit/*/opp/built-in/op_impl/ai_core/tbe/impl"
        "/ops_legacy/ascendc/common/catlass/include",
        "/usr/local/Ascend/ascend-toolkit/*/opp/built-in/op_impl/ai_core/tbe/impl/ascendc/common/catlass/include",
    ]
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return sorted(matches)[-1]
    raise FileNotFoundError(
        "Cannot find catlass include directory. "
        "Searched both CANN 8.5+ (ops_legacy/ascendc) and CANN 8.3 (ascendc) paths."
    )


def patch_cmake_for_catlass(project_dir: Path):
    """
    Patch op_kernel/CMakeLists.txt to add Catlass include paths for CV operators.

    NOTE: The kernel compiler (TBE/opc) does NOT honor CMake's include_directories().
    We must use add_ops_compile_options(ALL OPTIONS -I<path>) in op_kernel/CMakeLists.txt
    to pass the include path to the kernel compiler.
    """
    kernel_cmake = project_dir / "op_kernel" / "CMakeLists.txt"
    if not kernel_cmake.exists():
        logging.warning(f"op_kernel/CMakeLists.txt not found at {kernel_cmake}, skipping Catlass patch")
        return

    content = kernel_cmake.read_text()

    # Skip if already patched
    if "CATLASS_INCLUDE_PATH" in content:
        logging.info("op_kernel/CMakeLists.txt already has Catlass include, skipping")
        return

    catlass_path = find_catlass_include()

    # Insert before add_kernels_compile()
    catlass_snippet = f"""
# Catlass include path for CV (Cube+Vector) fused operators
# NOTE: Must use add_ops_compile_options, not include_directories (TBE compiler ignores CMake includes)
set(CATLASS_INCLUDE_PATH "{catlass_path}")
add_ops_compile_options(ALL OPTIONS -I${{CATLASS_INCLUDE_PATH}})
"""

    if "add_kernels_compile()" in content:
        content = content.replace(
            "add_kernels_compile()",
            catlass_snippet.strip() + "\n\nadd_kernels_compile()"
        )
    else:
        content += "\n" + catlass_snippet

    kernel_cmake.write_text(content)
    logging.info(f"Patched op_kernel/CMakeLists.txt with Catlass include: {catlass_path}")


def patch_kernel_for_cv_dispatch(project_dir: Path, op_name: str):
    """
    Patch the kernel source to use ASCEND_IS_AIC / ASCEND_IS_AIV dispatch structure.
    """
    op_custom = op_name + "_custom"

    kernel_dir = project_dir / "op_kernel"
    if not kernel_dir.exists():
        logging.warning(f"op_kernel directory not found at {kernel_dir}")
        return

    # Find the kernel .cpp file
    kernel_files = list(kernel_dir.glob("*.cpp"))
    if not kernel_files:
        logging.warning("No kernel .cpp files found in op_kernel/")
        return

    kernel_file = kernel_files[0]
    snake_name = op_custom  # e.g., matmul_gelu_custom

    cv_kernel_template = f'''#include "kernel_operator.h"

// CV (Cube+Vector) fused kernel entry point
// KernelCube and KernelVector classes will be implemented during DSL lowering

extern "C" __global__ __aicore__
void {snake_name}(GM_ADDR a, GM_ADDR b, GM_ADDR y, GM_ADDR workspace, GM_ADDR tiling) {{
    // GET_TILING_DATA(t, tiling);
    // if ASCEND_IS_AIC {{
    //     KernelCube opCube;
    //     opCube.Init(...);
    //     opCube.Process();
    // }} else if ASCEND_IS_AIV {{
    //     KernelVector opVector;
    //     opVector.Init(...);
    //     opVector.Process();
    // }}
}}
'''
    kernel_file.write_text(cv_kernel_template)
    logging.info(f"Patched kernel file with CV dispatch template: {kernel_file}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    parser = argparse.ArgumentParser(description="AscendC CV operator project generator")
    parser.add_argument("op_name", type=str, help="Operator name (e.g., 'matmul_gelu')")
    parser.add_argument("project_json", type=Path, help="Project JSON file path")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Base directory for CMake project output (default: output/). "
                             "The project is created at <output-dir>/{OpNameCustom}/.")

    args = parser.parse_args()
    try:
        # Step 1: Create standard project
        project_path = prepare_ascend_project(args.op_name, args.project_json, args.output_dir)
        logging.info(f"Created base AscendC project at: {project_path}")

        # Step 2: Patch for CV support
        patch_cmake_for_catlass(project_path)
        patch_kernel_for_cv_dispatch(project_path, args.op_name)

        logging.info(f"CV project setup complete: {project_path}")
    except Exception as e:
        logging.error(e)
