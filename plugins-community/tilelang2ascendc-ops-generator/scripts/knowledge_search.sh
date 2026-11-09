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
# 固定知识检索封装（cannbot-knowledge）。
#
# 统一负责：定位项目级/全局 knowledge.env、解析平台、discover 一次、检索、
# 去重、限流。无命中或知识不可用时只打印状态并以 0 退出，不阻断主流程。
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: knowledge_search.sh --query <text> --profile <profile> [options]

Required:
  --query <text>          检索词（Phase 4 报错用精确报错原文或 API 名）
  --profile <profile>     路径 Profile：guides|runbooks|optimizations|apis|operators|concepts|examples

Options:
  --technology <name>     默认 ascendc；TileLang 设计检索传 tilelang
  --domain <name>         默认 ops
  --match <text|literal>  默认 text；精确报错/API 名用 literal
  -k, --limit <1-5>       默认 5，超过 5 按 5 处理
  --platform <id>         覆盖 knowledge.env 中的 CANNBOT_KNOWLEDGE_PLATFORM
  --status <state>        stable|draft|deprecated|all，默认 stable
  --include-shared        同时召回 shared 跨技术卡
  --allow-unlocated       主查询无命中时补查缺 platforms 的卡（平台待核验）
  --project-root <dir>    从该目录向上查找 .cannbot/knowledge.env，默认 $PWD
  --knowledge-root <dir>  覆盖知识仓根
EOF
}

QUERY=""
PROFILE=""
TECHNOLOGY="ascendc"
DOMAIN="ops"
MATCH="text"
LIMIT=5
STATUS="stable"
PLATFORM=""
PROJECT_ROOT=""
KNOWLEDGE_ROOT=""
INCLUDE_SHARED=0
ALLOW_UNLOCATED=0
UNVERIFIED=0

while [ $# -gt 0 ]; do
    case "$1" in
        --query) QUERY="${2:-}"; shift 2 ;;
        --profile) PROFILE="${2:-}"; shift 2 ;;
        --technology) TECHNOLOGY="${2:-}"; shift 2 ;;
        --domain) DOMAIN="${2:-}"; shift 2 ;;
        --match) MATCH="${2:-}"; shift 2 ;;
        -k|--limit) LIMIT="${2:-}"; shift 2 ;;
        --status) STATUS="${2:-}"; shift 2 ;;
        --platform) PLATFORM="${2:-}"; shift 2 ;;
        --project-root) PROJECT_ROOT="${2:-}"; shift 2 ;;
        --knowledge-root) KNOWLEDGE_ROOT="${2:-}"; shift 2 ;;
        --include-shared) INCLUDE_SHARED=1; shift ;;
        --allow-unlocated) ALLOW_UNLOCATED=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "knowledge: unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [ -z "$QUERY" ] || [ -z "$PROFILE" ]; then
    usage >&2
    exit 2
fi
case "$MATCH" in text|literal) ;; *) echo "knowledge: --match must be text or literal" >&2; exit 2 ;; esac
case "$LIMIT" in ''|*[!0-9]*) echo "knowledge: --limit must be a positive integer" >&2; exit 2 ;; esac
[ "$LIMIT" -ge 1 ] || { echo "knowledge: --limit must be >= 1" >&2; exit 2; }
[ "$LIMIT" -le 5 ] || LIMIT=5

PROJECT_ROOT="${PROJECT_ROOT:-$PWD}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# 根解析顺序：--knowledge-root > 向上查找 .cannbot/knowledge.env > 全局 knowledge.env。
env_file=""
if [ -z "$KNOWLEDGE_ROOT" ]; then
    dir="$PROJECT_ROOT"
    while :; do
        if [ -f "$dir/.cannbot/knowledge.env" ]; then
            env_file="$dir/.cannbot/knowledge.env"
            break
        fi
        [ "$dir" = "/" ] && break
        dir="$(dirname "$dir")"
    done
    if [ -z "$env_file" ] && [ -f "$HOME/.cannbot/knowledge.env" ]; then
        env_file="$HOME/.cannbot/knowledge.env"
    fi
fi
if [ -n "$env_file" ]; then
    # shellcheck disable=SC1090
    . "$env_file"
fi

KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT:-${CANNBOT_KNOWLEDGE_ROOT:-}}"
if [ -z "$KNOWLEDGE_ROOT" ]; then
    echo "knowledge: unavailable (no knowledge root)"
    exit 0
fi

KQ="$KNOWLEDGE_ROOT/.agents/skills/knowledge-query/scripts/knowledge_query.py"
if [ ! -f "$KQ" ]; then
    echo "knowledge: unavailable (knowledge-query missing)"
    exit 0
fi

PLATFORM="${PLATFORM:-${CANNBOT_KNOWLEDGE_PLATFORM:-}}"
if [ -z "$PLATFORM" ]; then
    echo "knowledge: unavailable (platform unresolved; resolve SoC first)"
    exit 0
fi

# 与 init.sh 一致：只接受 knowledge 仓注册的平台 ID。
platform_registered() {
    local registry="$1" platform="$2"
    [ -f "$registry" ] || return 1
    awk '
        /^platforms:[[:space:]]*$/ { in_platforms = 1; next }
        in_platforms && /^[^[:space:]]/ { in_platforms = 0 }
        in_platforms && /^  [^[:space:]].*:/ {
            line = $0
            sub(/^  /, "", line)
            sub(/:.*/, "", line)
            gsub(/"/, "", line)
            print line
        }
    ' "$registry" | grep -Fxq -- "$platform"
}
if ! platform_registered "$KNOWLEDGE_ROOT/governance/schemas/registries.yaml" "$PLATFORM"; then
    echo "knowledge: unavailable (unknown platform: $PLATFORM)"
    exit 0
fi

if ! "$PYTHON_BIN" "$KQ" --knowledge-root "$KNOWLEDGE_ROOT" discover >/dev/null 2>&1; then
    echo "knowledge: unavailable (discover failed)"
    exit 0
fi

tmp="$(mktemp "${TMPDIR:-/tmp}/knowledge-search.XXXXXX")"
trap 'rm -f "$tmp" "${tmp2:-}"' EXIT

run_search() {
    local out="$1"
    shift
    "$PYTHON_BIN" "$KQ" --knowledge-root "$KNOWLEDGE_ROOT" search "$@" >"$out" 2>/dev/null
}

base_args=(
    --query "$QUERY"
    --domain "$DOMAIN"
    --technology "$TECHNOLOGY"
    --type "$PROFILE"
    --match "$MATCH"
    -k "$LIMIT"
    --status "$STATUS"
)
[ "$INCLUDE_SHARED" -eq 1 ] && base_args+=(--include-shared)

if ! run_search "$tmp" "${base_args[@]}" --platform "$PLATFORM"; then
    echo "knowledge: unavailable (search failed)"
    exit 0
fi

count=$("$PYTHON_BIN" - "$tmp" <<'PY'
import json, sys

with open(sys.argv[1], encoding="utf-8") as fh:
    print(len(json.load(fh).get("hits") or []))
PY
)

if [ "$count" -eq 0 ] && [ "$ALLOW_UNLOCATED" -eq 1 ]; then
    tmp2="$(mktemp "${TMPDIR:-/tmp}/knowledge-search.XXXXXX")"
    # --include-unlocated 只返回缺少 platforms 的卡，且不能与 --platform 同时使用。
    unlocated_args=(
        --query "$QUERY"
        --domain "$DOMAIN"
        --technology "$TECHNOLOGY"
        --type "$PROFILE"
        --match "$MATCH"
        -k "$LIMIT"
        --status all
        --include-unlocated
    )
    [ "$INCLUDE_SHARED" -eq 1 ] && unlocated_args+=(--include-shared)
    if run_search "$tmp2" "${unlocated_args[@]}"; then
        if "$PYTHON_BIN" - "$tmp2" <<'PY'
import json, sys

with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)
raise SystemExit(0 if data.get("hits") else 1)
PY
        then
            UNVERIFIED=1
            mv "$tmp2" "$tmp"
            count=$("$PYTHON_BIN" - "$tmp" <<'PY'
import json, sys

with open(sys.argv[1], encoding="utf-8") as fh:
    print(len(json.load(fh).get("hits") or []))
PY
)
        else
            rm -f "$tmp2"
        fi
    else
        rm -f "$tmp2"
    fi
fi

if [ "$count" -eq 0 ]; then
    echo "knowledge: no-hit profile=$PROFILE technology=$TECHNOLOGY platform=$PLATFORM"
    exit 0
fi

if [ "$UNVERIFIED" -eq 1 ]; then
    echo "knowledge: hits=$count profile=$PROFILE technology=$TECHNOLOGY platform=$PLATFORM (platform-unverified; cards without platforms)"
else
    echo "knowledge: hits=$count profile=$PROFILE technology=$TECHNOLOGY platform=$PLATFORM"
fi
"$PYTHON_BIN" - "$tmp" "$LIMIT" <<'PY'
import json
import signal
import sys

signal.signal(signal.SIGPIPE, signal.SIG_DFL)

with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)

seen = set()
shown = 0
for hit in data.get("hits") or []:
    path = hit.get("path") or ""
    if path in seen:
        continue
    seen.add(path)
    title = (hit.get("title") or "").strip()
    desc = (hit.get("description") or "").strip().replace("\n", " ")
    if len(desc) > 160:
        desc = desc[:157] + "..."
    print(f"- {path} — {title}")
    if desc:
        print(f"  {desc}")
    shown += 1
    if shown >= int(sys.argv[2]):
        break
PY
