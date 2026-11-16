#!/usr/bin/env bash
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${ASCEND_HOME_PATH:?Source the CANN set_env.sh before building}"
: "${TL_ROOT:?Set TL_ROOT to the TileLang-Ascend repository root}"
cmake -S "${SCRIPT_DIR}" -B "${SCRIPT_DIR}/build" \
    -DASCEND_CANN_PACKAGE_PATH="${ASCEND_HOME_PATH}" \
    -DTL_ROOT="${TL_ROOT}" \
    -DNPU_ARCH="${NPU_ARCH:-dav-2201}" -DCMAKE_BUILD_TYPE=Release
cmake --build "${SCRIPT_DIR}/build" --parallel "${BUILD_JOBS:-4}"
