#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------

set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Install the complete performance workflow before initializing direct invocation.
# Clear the public-installer context so its init installs the whole plugin.
CANNBOT_INIT_CONTEXT= bash "${PLUGIN_DIR}/../ops-perf-optimize/init.sh" "$@"
export CANNBOT_PREINITIALIZED_PLUGIN=ops-perf-optimize

if [[ -f "${PLUGIN_DIR}/../../script/bin/source-plugin-init.sh" ]]; then
  exec bash "${PLUGIN_DIR}/../../script/bin/source-plugin-init.sh" "${PLUGIN_DIR}" "$@"
fi
exec bash "${PLUGIN_DIR}/../../../bin/source-plugin-init.sh" "${PLUGIN_DIR}" "$@"
