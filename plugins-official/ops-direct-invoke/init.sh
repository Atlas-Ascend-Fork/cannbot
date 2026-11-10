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

# Keep plugin-specific answers outside the shared installer command line.
FORWARD_ARGS=()
CONFIG_GIVEN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --init-config)
      if [[ $# -lt 2 || -z "$2" || "$2" == --* || "$CONFIG_GIVEN" == "1" ]]; then
        echo "cannbot: --init-config requires one JSON file" >&2
        exit 1
      fi
      export CANNBOT_DIRECT_INVOKE_CONFIG="$2"
      CONFIG_GIVEN=1
      shift 2
      ;;
    *) FORWARD_ARGS+=("$1"); shift ;;
  esac
done
if [[ -f "${PLUGIN_DIR}/../../script/bin/source-plugin-init.sh" ]]; then
  exec bash "${PLUGIN_DIR}/../../script/bin/source-plugin-init.sh" "${PLUGIN_DIR}" "${FORWARD_ARGS[@]}"
fi
exec bash "${PLUGIN_DIR}/../../../bin/source-plugin-init.sh" "${PLUGIN_DIR}" "${FORWARD_ARGS[@]}"
