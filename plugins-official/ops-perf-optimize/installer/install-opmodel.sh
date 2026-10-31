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

# Install the optional OpModel wheel in a project-local virtual environment.

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="${1:-${CANNBOT_TOOL:-opencode}}"
TARGET="${2:-${CANNBOT_TARGET_DIR:-}}"

if [[ -z "$TARGET" || ! -d "$TARGET" ]]; then
  echo "cannbot: install-opmodel.sh requires an existing target directory" >&2
  exit 1
fi
TARGET="$(cd "$TARGET" && pwd)"

if [[ "${CANNBOT_SKIP_OPMODEL_INSTALL:-0}" == "1" ]]; then
  echo "Skipping OpModel installation (CANNBOT_SKIP_OPMODEL_INSTALL=1)" >&2
  exit 0
fi
case "$TOOL" in
  opencode|codex) SKILL_CANDIDATES=("${TARGET}/.agents/skills/ops-opmodel-toolkit") ;;
  claude) SKILL_CANDIDATES=("${TARGET}/.claude/skills/ops-opmodel-toolkit") ;;
  trae) SKILL_CANDIDATES=(
    "${TARGET}/.traecli/skills/ops-opmodel-toolkit"
    "${TARGET}/.marscode/skills/ops-opmodel-toolkit"
    "${TARGET}/.trae/skills/ops-opmodel-toolkit"
    "${TARGET}/.trae-cn/skills/ops-opmodel-toolkit"
  ) ;;
  dsh) SKILL_CANDIDATES=("${TARGET}/.dsh/skills/ops-opmodel-toolkit") ;;
  *) SKILL_CANDIDATES=() ;;
esac

SKILL_DIR=""
for candidate in "${SKILL_CANDIDATES[@]}"; do
  if [[ -f "${candidate}/SKILL.md" ]]; then
    SKILL_DIR="$(cd "$candidate" && pwd)"
    break
  fi
done
if [[ -z "$SKILL_DIR" ]]; then
  if [[ "${CANNBOT_OPMODEL_ALLOW_MISSING_SKILL:-0}" == "1" && ${#SKILL_CANDIDATES[@]} -gt 0 ]]; then
    SKILL_DIR="${SKILL_CANDIDATES[0]}"
    echo "  opmodel environment: deferring Skill link verification to the public installer"
  else
    echo "cannbot: ops-opmodel-toolkit is not installed for tool ${TOOL}; OpModel setup skipped" >&2
    exit 1
  fi
fi

BASE_PYTHON="${CANNBOT_OPMODEL_PYTHON:-${CANNBOT_PYTHON:-python3}}"
if ! command -v "$BASE_PYTHON" >/dev/null 2>&1; then
  echo "cannbot: Python interpreter not found: ${BASE_PYTHON}" >&2
  exit 1
fi

PLUGIN_ID="$(node -p 'require(process.argv[1]).name' "${PLUGIN_DIR}/.claude-plugin/plugin.json")"
INSTALL_ROOT="${TARGET}/.cannbot/dependencies/${PLUGIN_ID}/opmodel"
VENV_DIR="${CANNBOT_OPMODEL_VENV:-${INSTALL_ROOT}/venv}"
ENV_FILE="${TARGET}/.cannbot/opmodel.env"
VERSION_FILE="${INSTALL_ROOT}/installed-version.txt"
mkdir -p "$INSTALL_ROOT" "$(dirname "$ENV_FILE")"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "  opmodel environment: creating ${VENV_DIR}"
  if ! "$BASE_PYTHON" -m venv "$VENV_DIR"; then
    echo "cannbot: failed to create an OpModel virtual environment with ${BASE_PYTHON}" >&2
    echo "cannbot: install a Python build with venv/ensurepip support, then rerun the installer" >&2
    exit 1
  fi
fi

VENV_PYTHON="${VENV_DIR}/bin/python"
PACKAGE_SPEC="${CANNBOT_OPMODEL_PACKAGE:-opmodel}"
INDEX_URL="${CANNBOT_OPMODEL_INDEX_URL:-https://pypi.org/simple}"
PIP_ARGS=(--disable-pip-version-check install --upgrade --pre)
if [[ -n "${CANNBOT_OPMODEL_WHEELHOUSE:-}" ]]; then
  if [[ ! -d "$CANNBOT_OPMODEL_WHEELHOUSE" ]]; then
    echo "cannbot: OpModel wheelhouse does not exist: ${CANNBOT_OPMODEL_WHEELHOUSE}" >&2
    exit 1
  fi
  PIP_ARGS+=(--no-index --find-links "$CANNBOT_OPMODEL_WHEELHOUSE")
else
  PIP_ARGS+=(--index-url "$INDEX_URL")
fi
PIP_ARGS+=("$PACKAGE_SPEC")

echo "  opmodel wheel: installing ${PACKAGE_SPEC}"
if ! PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-30}" PIP_RETRIES="${PIP_RETRIES:-2}" \
  "$VENV_PYTHON" -m pip "${PIP_ARGS[@]}"; then
  echo "cannbot: OpModel wheel installation failed" >&2
  echo "cannbot: repair: ${VENV_PYTHON} -m pip ${PIP_ARGS[*]}" >&2
  exit 1
fi

if ! VERSION="$("$VENV_PYTHON" -c 'from importlib.metadata import version; print(version("opmodel"))')"; then
  echo "cannbot: opmodel metadata is unavailable after installation" >&2
  exit 1
fi
if ! "$VENV_PYTHON" -c 'import accel_model' >/dev/null; then
  echo "cannbot: opmodel is installed but accel_model cannot be imported" >&2
  exit 1
fi
if ! "${VENV_DIR}/bin/opmodel-assets" list >/dev/null; then
  echo "cannbot: opmodel is installed but opmodel-assets is not usable" >&2
  exit 1
fi

quote_shell() {
  printf "'%s'" "${1//\'/\'\\\'\'}"
}
OPMODEL_WORKSPACE="${TARGET}/.cannbot/workspaces/ops-opmodel-toolkit"
mkdir -p "$OPMODEL_WORKSPACE"
TEMP_ENV="$(mktemp "${ENV_FILE}.XXXXXX")"
trap 'rm -f "${TEMP_ENV:-}"' EXIT
{
  echo "# Generated by ops-perf-optimize/init.sh"
  echo "export OPMODEL_SKILL_DIR=$(quote_shell "$SKILL_DIR")"
  echo "export OPMODEL_VENV=$(quote_shell "$VENV_DIR")"
  echo "export OPMODEL_PYTHON=$(quote_shell "$VENV_PYTHON")"
  echo "export OPMODEL_WORKSPACE=$(quote_shell "$OPMODEL_WORKSPACE")"
  printf 'export PATH=%s:"$PATH"\n' "$(quote_shell "${VENV_DIR}/bin")"
} > "$TEMP_ENV"
mv "$TEMP_ENV" "$ENV_FILE"
trap - EXIT
printf '%s\n' "$VERSION" > "$VERSION_FILE"

echo "  opmodel wheel: ready (${VERSION})"
echo "  opmodel environment: ${ENV_FILE}"
