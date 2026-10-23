# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""AscendC Python API/source pairing and extension builds."""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
from pathlib import Path


ASCENDC_MODULE = "ascendc_ops"
ASCENDC_ARCH = "dav-3510"


def is_ascendc_operator(operator_file: Path) -> bool:
    """Return whether a Python API has a matching AscendC source file."""
    operator_path = operator_file.resolve()
    ascendc_source_file = operator_path.with_suffix(".asc")
    if not operator_path.is_file() or not ascendc_source_file.is_file():
        return False
    try:
        tree = ast.parse(operator_path.read_text(encoding="utf-8"), filename=str(operator_path))
    except (OSError, SyntaxError):
        return False
    return any(_imports_ascendc(node) for node in ast.walk(tree))


def ascendc_source_path(operator_file: Path) -> Path:
    return operator_file.resolve().with_suffix(".asc")


def ascendc_binary_paths(operator_file: Path) -> tuple[Path, ...]:
    return tuple(sorted(operator_file.resolve().parent.glob("ascendc_ops*.so")))


def build_ascendc_operator(operator_file: Path) -> None:
    """Build an AscendC operator before its Python API is imported."""
    operator_path = operator_file.resolve()
    cmake = shutil.which("cmake")
    if cmake is None:
        raise RuntimeError("AscendC operator requires cmake, but cmake was not found")

    api_dir = operator_path.parent
    ascendc_source_file = operator_path.with_suffix(".asc")
    root = api_dir / ".helix" / "ascendc-build"
    project_dir = root / "project"
    binary_dir = root / "build"
    project_dir.mkdir(parents=True, exist_ok=True)
    binary_dir.mkdir(parents=True, exist_ok=True)
    cmake_file = project_dir / "CMakeLists.txt"
    cmake_file.write_text(
        _render_cmake(ascendc_source_file=ascendc_source_file, output_dir=api_dir),
        encoding="utf-8",
    )

    _run_build_command(
        [cmake, "-S", str(project_dir), "-B", str(binary_dir)],
        cwd=api_dir,
        phase="configure",
    )
    _run_build_command(
        [cmake, "--build", str(binary_dir), "--parallel"],
        cwd=api_dir,
        phase="build",
    )
    outputs = sorted(api_dir.glob("ascendc_ops*.so"))
    if not outputs:
        raise RuntimeError(
            "AscendC build succeeded but did not produce ascendc_ops*.so beside "
            f"the operator: {api_dir}"
        )


def _imports_ascendc(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name == ASCENDC_MODULE for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return node.module == ASCENDC_MODULE
    return False


def _run_build_command(command: list[str], *, cwd: Path, phase: str) -> None:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=os.environ.copy(),
        )
    except OSError as exc:
        raise RuntimeError(f"AscendC {phase} command failed to start: {exc}") from exc
    if completed.returncode != 0:
        output = completed.stdout.strip()
        detail = f"\n{output}" if output else ""
        rendered = " ".join(command)
        raise RuntimeError(
            f"AscendC {phase} failed (exit {completed.returncode}): {rendered}{detail}"
        )


def _render_cmake(*, ascendc_source_file: Path, output_dir: Path) -> str:
    source = _cmake_quote(ascendc_source_file)
    output = _cmake_quote(output_dir)
    return f"""cmake_minimum_required(VERSION 3.16)

set(CMAKE_ASC_ARCHITECTURES \"{ASCENDC_ARCH}\" CACHE STRING \"AscendC architecture\")
find_package(ASC REQUIRED)
project(helix_ascendc LANGUAGES ASC CXX)
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)

execute_process(
    COMMAND ${{Python3_EXECUTABLE}} -c \"import torch; print(torch.utils.cmake_prefix_path)\"
    OUTPUT_STRIP_TRAILING_WHITESPACE
    OUTPUT_VARIABLE TORCH_CMAKE_PREFIX_PATH
)
find_package(Torch REQUIRED HINTS ${{TORCH_CMAKE_PREFIX_PATH}})

execute_process(
    COMMAND ${{Python3_EXECUTABLE}} -c \"import os, torch_npu; print(os.path.dirname(torch_npu.__file__))\"
    OUTPUT_STRIP_TRAILING_WHITESPACE
    OUTPUT_VARIABLE TORCH_NPU_PATH
)
set(TORCH_NPU_INCLUDE_DIRS ${{TORCH_NPU_PATH}}/include)
set(TORCH_NPU_LIBRARIES ${{TORCH_NPU_PATH}}/lib)

execute_process(
    COMMAND ${{Python3_EXECUTABLE}} -c \"import pybind11; print(pybind11.get_cmake_dir())\"
    OUTPUT_STRIP_TRAILING_WHITESPACE
    OUTPUT_VARIABLE PYBIND11_CMAKE_PREFIX_PATH
)
find_package(pybind11 REQUIRED HINTS ${{PYBIND11_CMAKE_PREFIX_PATH}})

pybind11_add_module({ASCENDC_MODULE} SHARED \"{source}\")
set_target_properties({ASCENDC_MODULE} PROPERTIES LIBRARY_OUTPUT_DIRECTORY \"{output}\")
target_include_directories({ASCENDC_MODULE} PRIVATE
    ${{TORCH_INCLUDE_DIRS}}
    ${{TORCH_NPU_INCLUDE_DIRS}}
)
target_link_libraries({ASCENDC_MODULE} PRIVATE torch_npu)
target_link_directories({ASCENDC_MODULE} PRIVATE ${{TORCH_NPU_LIBRARIES}})
target_compile_options({ASCENDC_MODULE} PRIVATE
    ${{TORCH_CXX_FLAGS}}
    $<$<COMPILE_LANGUAGE:ASC>:--npu-arch={ASCENDC_ARCH}>
)
"""


def _cmake_quote(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace('"', '\\"')
