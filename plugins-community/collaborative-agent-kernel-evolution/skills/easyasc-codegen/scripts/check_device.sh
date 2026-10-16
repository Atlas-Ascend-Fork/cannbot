#!/bin/bash
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
# check_device.sh — detect host NPU device family and validate against requested target.
#
# Usage:
#   bash check_device.sh --target {a2|a5}
#
# Outputs JSON to stdout:
#   {
#     "host_device": "910B" | "910" | "...",  // raw model string from npu-smi
#     "host_family": "a2" | "a5" | "unknown",
#     "target": "a2" | "a5",
#     "passed": true | false,
#     "warnings": ["..."],
#     "error": null | "..."
#   }
#
# Exit codes:
#   0 — passed (target satisfied; for a5 may still emit warnings)
#   2 — hard fail (a2 requested but host is not 910B)
#   3 — host detection failed; caller should ask user
#   1 — usage error

set -u

TARGET=""
while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="${2:-}"; shift 2 ;;
    *) echo "{\"error\":\"unknown arg: $1\"}" >&2; exit 1 ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "{\"error\":\"--target is required\"}" >&2
  exit 1
fi

if [ "$TARGET" != "a2" ] && [ "$TARGET" != "a5" ]; then
  echo "{\"error\":\"--target must be a2 or a5, got: $TARGET\"}" >&2
  exit 1
fi

# Try to read device info from npu-smi.
HOST_DEVICE=""
HOST_FAMILY="unknown"
DETECTION_ERR=""

if command -v npu-smi >/dev/null 2>&1; then
  RAW=$(npu-smi info 2>&1 || true)
  # Look for a 910B / 910 / 310P / 910A pattern.
  if echo "$RAW" | grep -qE '910B'; then
    HOST_DEVICE="910B"
    HOST_FAMILY="a2"
  elif echo "$RAW" | grep -qE '910A'; then
    HOST_DEVICE="910A"
    HOST_FAMILY="unknown"
  elif echo "$RAW" | grep -qE '910'; then
    HOST_DEVICE="910"
    HOST_FAMILY="unknown"
  elif echo "$RAW" | grep -qE '310P'; then
    HOST_DEVICE="310P"
    HOST_FAMILY="unknown"
  else
    DETECTION_ERR="npu-smi output did not match a known device pattern"
  fi
else
  DETECTION_ERR="npu-smi not found in PATH"
fi

WARNINGS=()
PASSED=true
ERROR="null"
EXIT=0

if [ -n "$DETECTION_ERR" ]; then
  # Detection failed. Caller should AskUserQuestion to confirm device.
  PASSED=false
  ERROR="\"$DETECTION_ERR\""
  EXIT=3
else
  case "$TARGET" in
    a2)
      if [ "$HOST_FAMILY" = "a2" ]; then
        PASSED=true
      else
        PASSED=false
        ERROR="\"target a2 requires 910B host, got: $HOST_DEVICE\""
        EXIT=2
      fi
      ;;
    a5)
      # a5 only validates that CANN/PYTHONPATH/numpy are reachable; device family is informational.
      if [ "$HOST_FAMILY" != "a5" ]; then
        WARNINGS+=("\"host is $HOST_DEVICE (family=$HOST_FAMILY); running a5 in simulator-only mode\"")
      fi
      # Verify ASCEND_HOME_PATH (CANN).
      if [ -z "${ASCEND_HOME_PATH:-}" ] || [ ! -d "${ASCEND_HOME_PATH}" ]; then
        WARNINGS+=("\"ASCEND_HOME_PATH is not set or not a directory\"")
      fi
      # Verify numpy is importable.
      if ! python -c "import numpy" >/dev/null 2>&1; then
        WARNINGS+=("\"python -c 'import numpy' failed\"")
      fi
      PASSED=true
      ;;
  esac
fi

# Render JSON.
WARN_JSON="[]"
if [ ${#WARNINGS[@]} -gt 0 ]; then
  WARN_JSON="[$(IFS=,; echo "${WARNINGS[*]}")]"
fi

cat <<EOF
{
  "host_device": "${HOST_DEVICE}",
  "host_family": "${HOST_FAMILY}",
  "target": "${TARGET}",
  "passed": ${PASSED},
  "warnings": ${WARN_JSON},
  "error": ${ERROR}
}
EOF

exit $EXIT
