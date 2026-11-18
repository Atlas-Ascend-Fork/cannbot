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
#
# Project-level install entry for the isolated A2/A3 legacy bundle.
#
# Everything it installs lives in this directory (skills/, workflow/, agents/), so
# the installer reads this cannbot checkout and nothing else: the cannbot-skills
# repository's ops-registry-invoke directory is neither read nor required. The
# remaining shared Skills are installed by name from cannbot-skills by the
# workflow (see skills.txt).
#
# Usage: bash init.sh [project] [opencode|codex|claude|trae|dsh|codearts] [install_path]

set -euo pipefail
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REPOSITORY_ROOT="$BUNDLE_DIR"
while [[ "$REPOSITORY_ROOT" != "/" && ! -f "${REPOSITORY_ROOT}/script/bin/cannbot.js" ]]; do
  REPOSITORY_ROOT="$(dirname "$REPOSITORY_ROOT")"
done
if [[ ! -f "${REPOSITORY_ROOT}/script/bin/cannbot.js" ]]; then
  echo "cannbot: cannot locate the cannbot repository root from ${BUNDLE_DIR}" >&2
  exit 1
fi

LEVEL="project"
TOOL="opencode"
TARGET=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      cat >&2 <<EOF
Usage: bash init.sh [project] [opencode|codex|claude|trae|dsh|codearts] [install_path]

Installs the isolated A2/A3 legacy bundle at project level from this cannbot
checkout: ${BUNDLE_DIR}
EOF
      exit 0
      ;;
    project) LEVEL="project" ;;
    global) LEVEL="global" ;;
    opencode|codex|claude|trae|dsh|codearts) TOOL="$1" ;;
    cursor|copilot)
      echo "cannbot: $1 is not supported by the unified installer" >&2
      exit 1
      ;;
    --*) echo "cannbot: unsupported option $1" >&2; exit 1 ;;
    *)
      if [[ -n "${TARGET}" ]]; then
        echo "cannbot: only one install path is accepted" >&2
        exit 1
      fi
      TARGET="$1"
      ;;
  esac
  shift
done
if [[ "${LEVEL}" != "project" ]]; then
  echo "cannbot: the unified installer currently supports project-level installation only" >&2
  exit 1
fi

TARGET="${TARGET:-${REPOSITORY_ROOT}}"
exec node "${REPOSITORY_ROOT}/script/bin/cannbot.js" install ops-registry-invoke-a2-a3 \
  --tool "${TOOL}" --target "${TARGET}" --source "${REPOSITORY_ROOT}" --plugin-dir "${BUNDLE_DIR}"
