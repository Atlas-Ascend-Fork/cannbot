#!/usr/bin/env bash
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

# Source adapter for the ops-perf-optimize plugin.

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install_opmodel() {
  local target="$1"
  local tool="$2"
  if ! bash "${PLUGIN_DIR}/installer/install-opmodel.sh" "$tool" "$target"; then
    echo "cannbot: OpModel setup unavailable; plugin installation will continue" >&2
    if [[ "${CANNBOT_OPMODEL_STRICT:-0}" == "1" ]]; then
      return 1
    fi
  fi
}

# Generic public installers run this entry point as an initializer and skip the
# source CLI that owns dependency provisioning. Prepare the knowledge consumer
# and project-local OpModel runtime here so those install paths remain usable.
if [[ -n "${CANNBOT_INIT_CONTEXT:-}" ]]; then
  INIT_TOOL="${CANNBOT_TOOL:-opencode}"
  INIT_TARGET="${CANNBOT_TARGET_DIR:-${PWD}}"
  bash "${PLUGIN_DIR}/installer/install-knowledge.sh" "$INIT_TOOL" "$INIT_TARGET"
  # Public installers run init.sh before publishing plugin Skills. Reserve the
  # expected Skill path so the wheel can be provisioned in the same transaction.
  CANNBOT_OPMODEL_ALLOW_MISSING_SKILL=1 install_opmodel "$INIT_TARGET" "$INIT_TOOL"
  exit 0
fi

resolve_source_install_context() {
  SOURCE_TOOL="opencode"
  SOURCE_TARGET=""
  SOURCE_HELP=0
  local skip_next=0
  local argument
  for argument in "$@"; do
    if (( skip_next )); then
      skip_next=0
      continue
    fi
    case "$argument" in
      --skills) skip_next=1 ;;
      opencode|codex|claude|trae|dsh) SOURCE_TOOL="$argument" ;;
      --help|-h) SOURCE_HELP=1 ;;
      project|global|--*) ;;
      *) if [[ -z "$SOURCE_TARGET" ]]; then SOURCE_TARGET="$argument"; fi ;;
    esac
  done
  if [[ -z "$SOURCE_TARGET" ]]; then
    if [[ -f "${PLUGIN_DIR}/../../script/bin/source-plugin-init.sh" ]]; then
      SOURCE_TARGET="$(cd "${PLUGIN_DIR}/../.." && pwd)"
    else
      SOURCE_TARGET="$(cd "${PLUGIN_DIR}/../../.." && pwd)"
    fi
  fi
}

if [[ -f "${PLUGIN_DIR}/../../script/bin/source-plugin-init.sh" ]]; then
  SOURCE_INIT="${PLUGIN_DIR}/../../script/bin/source-plugin-init.sh"
else
  SOURCE_INIT="${PLUGIN_DIR}/../../../bin/source-plugin-init.sh"
fi

bash "$SOURCE_INIT" "${PLUGIN_DIR}" "$@"
resolve_source_install_context "$@"
if [[ "$SOURCE_HELP" == "1" ]]; then
  exit 0
fi
install_opmodel "$SOURCE_TARGET" "$SOURCE_TOOL"
