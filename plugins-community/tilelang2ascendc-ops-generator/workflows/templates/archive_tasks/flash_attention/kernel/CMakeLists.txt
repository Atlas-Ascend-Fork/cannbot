# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

cmake_minimum_required(VERSION 3.16.0)
project(flash_attention_gen_kernel)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(SOC_VERSION "$ENV{SOC_VERSION}" CACHE STRING "system on chip type")
set(ASCEND_CANN_PACKAGE_PATH "$ENV{ASCEND_HOME_PATH}" CACHE PATH "ASCEND CANN package installation directory")
set(RUN_MODE "npu" CACHE STRING "run mode: npu")
set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type Release/Debug (default Release)")
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")

if(CMAKE_SYSTEM_PROCESSOR)
  set(SYSTEM_PREFIX ${CMAKE_SYSTEM_PROCESSOR}-linux)
else()
  set(SYSTEM_PREFIX aarch64-linux)
endif()

# kernel 源由 bisheng -xasc 一次编译（设备码 + <<<>>> host 启动 stub 同 TU），
# 与 gcc 编译的 host/register 一起链进 <op>_ext.so
if(EXISTS ${ASCEND_CANN_PACKAGE_PATH}/bin/bisheng)
  set(BISHENG ${ASCEND_CANN_PACKAGE_PATH}/bin/bisheng)
elseif(EXISTS ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/ccec_compiler/bin/bisheng)
  set(BISHENG ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/ccec_compiler/bin/bisheng)
else()
  message(FATAL_ERROR "bisheng compiler does not exist, please check ASCEND_CANN_PACKAGE_PATH.")
endif()

# SOC -> npu-arch（910B 系列 = dav-2201）
set(NPU_ARCH "dav-2201" CACHE STRING "bisheng --npu-arch")

# Catlass and the generated helpers are header-only dependencies from TileLang-Ascend.
set(TL_ROOT "$ENV{TL_ROOT}" CACHE PATH "TileLang-Ascend repository root")
foreach(REQUIRED_HEADER
    src/tl_templates/ascend/common.h
    3rdparty/catlass/include/catlass/catlass.hpp
    3rdparty/shmem/include/shmem.h)
    if(NOT EXISTS "${TL_ROOT}/${REQUIRED_HEADER}")
        message(FATAL_ERROR "Missing ${REQUIRED_HEADER}; set TL_ROOT to the TileLang-Ascend checkout")
    endif()
endforeach()
set(TL_INCLUDE_DIRS
    ${TL_ROOT}/src
    ${TL_ROOT}/3rdparty/catlass/include
    ${TL_ROOT}/3rdparty/shmem/include
    ${TL_ROOT}/3rdparty/shmem/src/device)

# 与 legacy 构建逐项对齐的 include 集（asc/tikcfw 头 + CANN 公共头）
set(KERNEL_INCLUDE_DIRS
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/utils
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/impl/adv_api
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/impl/basic_api
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/impl/c_api
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/impl/basic_api/reg_compute
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/impl/simt_api
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/impl/utils
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/include
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/include/adv_api
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/include/basic_api
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/include/aicpu_api
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/include/c_api
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/include/basic_api/reg_compute
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/include/simt_api
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/include/utils
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/tikcpp/tikcfw
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/tikcpp/tikcfw/interface
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/tikcpp/tikcfw/impl
    ${ASCEND_CANN_PACKAGE_PATH}/include
    ${ASCEND_CANN_PACKAGE_PATH}/include/experiment/runtime
    ${ASCEND_CANN_PACKAGE_PATH}/include/experiment/msprof
    ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc
    ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/runtime
    ${ASCEND_CANN_PACKAGE_PATH}/pkg_inc/profiling
    ${TL_INCLUDE_DIRS})
set(KERNEL_INCLUDE_OPTIONS)
foreach(INC_DIR IN LISTS KERNEL_INCLUDE_DIRS)
  list(APPEND KERNEL_INCLUDE_OPTIONS "-I${INC_DIR}")
endforeach()

# 设备侧 flags 与 legacy ascendc.cmake 逐项对齐：--cce-auto-sync（gen 产物
# 依赖编译器自动插同步，缺了会竞态）、-O3、mllvm 栈/溢出检查参数
set(KERNEL_BISHENG_FLAGS
    --npu-arch=${NPU_ARCH} -xasc -std=c++17 -fPIC -O3 -DNDEBUG
    --cce-auto-sync
    -mllvm -cce-aicore-stack-size=0x8000
    -mllvm -cce-aicore-function-stack-size=0x8000
    -mllvm -cce-aicore-record-overflow=true
    -mllvm -cce-aicore-addr-transform
    -mllvm -cce-aicore-dcci-insert-for-scalar=false
    -DCATLASS_ARCH=2201 -DBACKEND_HYBM
)
if(EXISTS ${ASCEND_CANN_PACKAGE_PATH}/include/version/asc_devkit_version.h)
  list(APPEND KERNEL_BISHENG_FLAGS
    -include ${ASCEND_CANN_PACKAGE_PATH}/include/version/asc_devkit_version.h)
endif()

set(KERNEL_SRC ${CMAKE_CURRENT_SOURCE_DIR}/op_kernel/flash_attention_kernels.cpp)
set(KERNEL_OBJ ${CMAKE_CURRENT_BINARY_DIR}/flash_attention_kernels.o)
file(GLOB_RECURSE TL_HEADERS CONFIGURE_DEPENDS
    "${TL_ROOT}/src/tl_templates/ascend/*.h"
    "${TL_ROOT}/3rdparty/catlass/include/*.hpp"
    "${TL_ROOT}/3rdparty/shmem/include/*.h"
    "${TL_ROOT}/3rdparty/shmem/src/device/*.h"
    "${TL_ROOT}/3rdparty/shmem/src/device/*.hpp")
add_custom_command(
  OUTPUT ${KERNEL_OBJ}
  COMMAND ${BISHENG} ${KERNEL_BISHENG_FLAGS} ${KERNEL_INCLUDE_OPTIONS}
          -c ${KERNEL_SRC} -o ${KERNEL_OBJ}
  DEPENDS ${KERNEL_SRC}
          ${TL_HEADERS}
          ${CMAKE_CURRENT_SOURCE_DIR}/op_kernel/fa_gen_kernel.h
          ${CMAKE_CURRENT_SOURCE_DIR}/op_kernel/flash_attention_cube.h
          ${CMAKE_CURRENT_SOURCE_DIR}/op_kernel/flash_attention_launch.h
          ${CMAKE_CURRENT_SOURCE_DIR}/op_kernel/flash_attention_vec.h
          ${CMAKE_CURRENT_SOURCE_DIR}/op_kernel/kernel_common.h
          ${CMAKE_CURRENT_SOURCE_DIR}/ops.h
  VERBATIM
)
add_custom_target(kernels_obj DEPENDS ${KERNEL_OBJ})

# torch extension library (op_host + register + kernel objects)
add_library(flash_attention_gen_ext SHARED
    ${CMAKE_CURRENT_SOURCE_DIR}/op_host/flash_attention_gen.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/register.cpp
    ${KERNEL_OBJ}
)
add_dependencies(flash_attention_gen_ext kernels_obj)

execute_process(COMMAND python3 -c "import os; import torch; print(os.path.dirname(torch.__file__))"
    OUTPUT_STRIP_TRAILING_WHITESPACE
    OUTPUT_VARIABLE TORCH_PATH
)
message("TORCH_PATH is ${TORCH_PATH}")
set(ENV{ASCEND_HOME_PATH} ${ASCEND_CANN_PACKAGE_PATH})
execute_process(COMMAND python3 -c "import os; import torch_npu; print(os.path.dirname(torch_npu.__file__))"
    OUTPUT_STRIP_TRAILING_WHITESPACE
    OUTPUT_VARIABLE TORCH_NPU_PATH
)
message("TORCH_NPU_PATH is ${TORCH_NPU_PATH}")

target_link_directories(flash_attention_gen_ext PRIVATE
    ${TORCH_PATH}/lib
    ${TORCH_NPU_PATH}/lib
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/lib64
    ${ASCEND_CANN_PACKAGE_PATH}/lib64
)
target_include_directories(flash_attention_gen_ext PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/utils
    ${TORCH_NPU_PATH}/include
    ${TORCH_PATH}/include
    ${TORCH_PATH}/include/torch/csrc/api/include
    ${ASCEND_CANN_PACKAGE_PATH}/include
    ${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/asc/include
)

target_link_libraries(flash_attention_gen_ext PRIVATE
    torch
    torch_cpu
    torch_npu
    ascendcl
    platform
    register
    tiling_api
    ascendc_runtime
    runtime
    profapi
    m
    dl
)

execute_process(COMMAND python3 -m pybind11 --includes
    OUTPUT_STRIP_TRAILING_WHITESPACE
    OUTPUT_VARIABLE PYBIND11_INC
)
string(REPLACE " " ";" PYBIND11_INC ${PYBIND11_INC})
target_compile_options(flash_attention_gen_ext PRIVATE
    ${PYBIND11_INC}
    -D_GLIBCXX_USE_CXX11_ABI=1
)

execute_process(COMMAND python3 -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '.so')"
    OUTPUT_STRIP_TRAILING_WHITESPACE
    OUTPUT_VARIABLE PYTHON_EXTENSION_SUFFIX
)
set_target_properties(flash_attention_gen_ext PROPERTIES
    OUTPUT_NAME flash_attention_gen_ext
    PREFIX ""
    SUFFIX "${PYTHON_EXTENSION_SUFFIX}"
    BUILD_RPATH "${TORCH_PATH}/lib;${TORCH_NPU_PATH}/lib;${ASCEND_CANN_PACKAGE_PATH}/${SYSTEM_PREFIX}/lib64;${ASCEND_CANN_PACKAGE_PATH}/lib64"
)
