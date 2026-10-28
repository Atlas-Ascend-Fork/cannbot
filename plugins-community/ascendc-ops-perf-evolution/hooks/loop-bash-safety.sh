#!/usr/bin/env bash
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------


# loop-bash-safety.sh — PreToolUse(Bash) hook for Z-Search loop.
#
# Activated by hooks/hooks.json. Receives Claude Code's hook JSON on stdin:
#   { "session_id": ..., "tool_name": "Bash", "tool_input": { "command": "...", ... }, ... }
#
# Inspects the command for path-safety violations (B1: empty var as path; B2:
# protected root). If violation found, exit 2 with stderr message — Claude
# Code will surface the message to the model and block the tool call.
#
# Escape hatch: LINGXI_LOOP_HOOK_DISABLE=1 downgrades to warn-only.

set -uo pipefail

HOOK_NAME="loop-bash-safety"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"
# shellcheck source=lib/paths.sh
source "${SCRIPT_DIR}/lib/paths.sh"

read_stdin_json

cmd="$(json_get "tool_input.command")"
if [[ -z "${cmd}" ]]; then
    hook_allow
fi

# Run the safety check; capture stderr reason
reason="$(check_bash_path_safety "${cmd}" 2>&1 >/dev/null)"
rc=$?

if [[ ${rc} -ne 0 && -n "${reason}" ]]; then
    hook_block "${reason}"
fi

hook_allow
