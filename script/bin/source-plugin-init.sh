#!/usr/bin/env bash
# Copyright (c) 2026 CANNBot contributors
# SPDX-License-Identifier: MIT
# See script/LICENSE for the full license text.


set -euo pipefail

# Keep this requirement in sync with package.json engines.node.
MIN_NODE_MAJOR=20

node_error() {
  printf 'cannbot: %s\n' "$1" >&2
  printf '请安装 Node.js >=%s，确保 node 在当前终端的 PATH 中可用，并运行 node --version 确认后重试。\n' "$MIN_NODE_MAJOR" >&2
  printf '安装指引：https://nodejs.org/en/download\n' >&2
  exit 1
}

check_node() {
  local version major
  if ! command -v node >/dev/null 2>&1; then
    node_error "未找到 Node.js，安装器要求 Node.js >=${MIN_NODE_MAJOR}。"
  fi
  if ! version="$(node --version 2>&1)"; then
    node_error "无法运行 Node.js：${version}"
  fi
  if [[ ! "$version" =~ ^v([0-9]+)\. ]]; then
    node_error "无法识别 Node.js 版本：${version}"
  fi
  major="${BASH_REMATCH[1]}"
  if (( 10#$major < MIN_NODE_MAJOR )); then
    node_error "当前 Node.js 版本为 ${version}，安装器要求 Node.js >=${MIN_NODE_MAJOR}。"
  fi
}

check_node

PLUGIN_DIR="$(cd "${1:?plugin directory is required}" && pwd)"
shift
PLUGIN_ID="$(node -p 'require(process.argv[1]).name' "${PLUGIN_DIR}/.claude-plugin/plugin.json")"

usage() {
  cat >&2 <<EOF
Usage: bash init.sh [project] [opencode|codex|claude|trae|dsh] [install_path] [--skills <SHA|path>]

Installs ${PLUGIN_ID} from this source checkout. The default tool is opencode
and the default install path is the source repository root.
Shared Skills follow the source branch, falling back to master if absent (or detached HEAD).
--skills selects a SHA or local Git worktree root.
EOF
}

LEVEL="project"
TOOL="opencode"
INSTALL_PATH=""
SKILLS_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --skills)
      if [[ $# -lt 2 || -z "$2" || "$2" == --* || -n "${SKILLS_ARGS[*]}" ]]; then usage; exit 1; fi
      SKILLS_ARGS=(--skills "$2")
      shift 2
      continue
      ;;
    project) LEVEL="project" ;;
    global) LEVEL="global" ;;
    opencode|codex|claude|trae|dsh) TOOL="$1" ;;
    cursor|copilot|codearts)
      echo "cannbot: $1 is not supported by the unified installer" >&2
      exit 1
      ;;
    --*) usage; exit 1 ;;
    *)
      if [[ -n "${INSTALL_PATH}" ]]; then usage; exit 1; fi
      INSTALL_PATH="$1"
      ;;
  esac
  shift
done

if [[ "${LEVEL}" != "project" ]]; then
  echo "cannbot: the unified installer currently supports project-level installation only" >&2
  exit 1
fi

if [[ -f "${PLUGIN_DIR}/../../script/bin/cannbot.js" ]]; then
  REPOSITORY_ROOT="$(cd "${PLUGIN_DIR}/../.." && pwd)"
  CLI="${REPOSITORY_ROOT}/script/bin/cannbot.js"
elif [[ -f "${PLUGIN_DIR}/../../../bin/cannbot.js" ]]; then
  REPOSITORY_ROOT="$(cd "${PLUGIN_DIR}/../../.." && pwd)"
  CLI="${REPOSITORY_ROOT}/bin/cannbot.js"
else
  echo "cannbot: cannot locate the unified installer from ${PLUGIN_DIR}" >&2
  exit 1
fi
INSTALL_PATH="${INSTALL_PATH:-${REPOSITORY_ROOT}}"

exec node "${CLI}" install "${PLUGIN_ID}" \
  --tool "${TOOL}" --target "${INSTALL_PATH}" --source "${REPOSITORY_ROOT}" --plugin-dir "${PLUGIN_DIR}" "${SKILLS_ARGS[@]}"
