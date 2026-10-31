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

# Install the cannbot-knowledge consumer from a generic plugin initializer.
#
# Public installers may run a plugin's init.sh without selecting the source
# CLI that provisions dependency repositories. Keep this bootstrap plugin-local
# so every installer path that executes init.sh also prepares the knowledge
# consumer, project config and read-only index.

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOL="${1:-${CANNBOT_TOOL:-}}"
TARGET="${2:-${CANNBOT_TARGET_DIR:-}}"
if [[ -z "$TOOL" || -z "$TARGET" ]]; then
  echo "cannbot: install-knowledge.sh requires a tool and target" >&2
  exit 0
fi
TARGET="$(cd "$TARGET" && pwd)"

if [[ "${CANNBOT_SKIP_DEPENDENCY_REPOS:-0}" == "1" ]]; then
  echo "Skipping knowledge base installation (CANNBOT_SKIP_DEPENDENCY_REPOS=1)" >&2
  exit 0
fi
if [[ "${CANNBOT_SKIP_KNOWLEDGE_INDEX:-0}" == "1" ]]; then
  echo "Skipping knowledge consumer setup (CANNBOT_SKIP_KNOWLEDGE_INDEX=1)" >&2
  exit 0
fi

DEFINITION="${PLUGIN_DIR}/plugin-install.json"
[[ -f "$DEFINITION" ]] || exit 0

META="$(node - "$DEFINITION" <<'NODE'
const fs = require("fs");
const definition = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const knowledge = (definition.dependencies || []).find((entry) => entry && entry.name === "cannbot-knowledge");
if (!knowledge || !knowledge.repository) process.exit(3);
process.stdout.write(`${knowledge.repository}\n${knowledge.ref || ""}\n`);
NODE
)" || exit 0

REPOSITORY="$(printf '%s\n' "$META" | sed -n '1p')"
REF="$(printf '%s\n' "$META" | sed -n '2p')"
[[ -n "$REPOSITORY" ]] || exit 0

PLUGIN_ID="$(node -p 'require(process.argv[1]).name' "${PLUGIN_DIR}/.claude-plugin/plugin.json")"
DEPENDENCY_ROOT="${TARGET}/.cannbot/dependencies/${PLUGIN_ID}"
DESTINATION="${DEPENDENCY_ROOT}/cannbot-knowledge"

normalize_repository() {
  local url="${1%/}"
  printf '%s' "${url%.git}"
}

if [[ -e "$DESTINATION" ]]; then
  if [[ ! -d "${DESTINATION}/.git" ]]; then
    echo "cannbot: ${DESTINATION} exists but is not a Git checkout; knowledge setup skipped" >&2
    exit 0
  fi
  ORIGIN="$(git -C "$DESTINATION" remote get-url origin 2>/dev/null || true)"
  if [[ "$(normalize_repository "$ORIGIN")" != "$(normalize_repository "$REPOSITORY")" ]]; then
    echo "cannbot: cannbot-knowledge has an unexpected origin; knowledge setup skipped" >&2
    exit 0
  fi
  if ! git -C "$DESTINATION" pull --ff-only >/dev/null 2>&1; then
    echo "cannbot: failed to update cannbot-knowledge; using the existing checkout" >&2
  fi
else
  mkdir -p "$DEPENDENCY_ROOT"
  CLONE=(git clone --depth 1)
  [[ -n "$REF" ]] && CLONE+=(--branch "$REF")
  CLONE+=("$REPOSITORY" "$DESTINATION")
  if ! "${CLONE[@]}"; then
    echo "cannbot: failed to clone cannbot-knowledge; knowledgeIndex=pending" >&2
    echo "cannbot: repair: git clone ${REPOSITORY} ${DESTINATION}" >&2
    exit 0
  fi
fi

INSTALLER="${DESTINATION}/install.sh"
if [[ ! -f "$INSTALLER" ]]; then
  echo "cannbot: missing knowledge installer: ${INSTALLER}; knowledgeIndex=pending" >&2
  exit 0
fi

ARGS=(bash "$INSTALLER" "$TOOL" "$TARGET" consumer --skip-repository-update)
[[ "${CANNBOT_SKIP_KNOWLEDGE_RESOURCES:-0}" == "1" ]] && ARGS+=(--skip-resources)
echo "  knowledge consumer: preparing runtime, resources and search index ..."
if ! (cd "$DESTINATION" && "${ARGS[@]}"); then
  echo "cannbot: knowledge consumer: unavailable; knowledgeIndex=pending" >&2
  echo "cannbot: repair: ${ARGS[*]}" >&2
  exit 0
fi

QUERY="${TARGET}/.agents/skills/knowledge-query/scripts/knowledge_query.py"
PYTHON="${CANNBOT_PYTHON:-python3}"
DISCOVERED=""
if [[ -f "$QUERY" ]] && DISCOVERED="$(cd "$TARGET" && "$PYTHON" "$QUERY" discover --json 2>&1)"; then
  if printf '%s' "$DISCOVERED" | "$PYTHON" -c '
import json, os, sys
coverage = json.load(sys.stdin)
assert coverage.get("schema_version") == "knowledge-discovery.v1"
assert isinstance(coverage.get("cards"), int)
assert os.path.realpath(coverage.get("root", "")) == os.path.realpath(sys.argv[1])
' "$DESTINATION" 2>/dev/null; then
    echo "  knowledge index: ready"
    exit 0
  fi
  echo "cannbot: knowledge consumer: discover did not confirm the installed knowledge root; knowledgeIndex=pending" >&2
else
  echo "cannbot: knowledge consumer: ${DISCOVERED:-missing knowledge-query entry}; knowledgeIndex=pending" >&2
fi
echo "cannbot: repair: ${ARGS[*]}" >&2
exit 0
