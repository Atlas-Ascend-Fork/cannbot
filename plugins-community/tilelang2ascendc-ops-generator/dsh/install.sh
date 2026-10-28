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
#
# CANNBot DSH dispatch-protocol installer (tilelang2ascendc-ops-generator).
#
# Writes ONE managed block into ${DSH_HOME:-$HOME/.dsh}/AGENTS.md, the DSH
# user-level instruction channel. Only DeepSeek Harness reads that file, so this
# adapter never touches instructions consumed by Claude Code, Codex, OpenCode or
# TRAE.
#
# Properties: idempotent (the managed block is replaced in place), the previous
# file is backed up before the first change, and the written result is validated;
# on validation failure the previous content is restored.
#
# Usage:
#   ./install.sh [--dsh-home <path>] [--check] [--force]
#
#   --dsh-home <path>  DSH home directory (default: $DSH_HOME or ~/.dsh)
#   --check            report whether the managed block is present; write nothing
#   --force            skip the regular-file guard on the target
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROTOCOL_SRC="${SCRIPT_DIR}/protocol.md"

DSH_HOME_DIR="${DSH_HOME:-$HOME/.dsh}"
CHECK_ONLY=0
FORCE=0

BEGIN_MARK='<!-- cannbot:tilelang2ascendc-ops-generator:dsh-protocol:start -->'
END_MARK='<!-- cannbot:tilelang2ascendc-ops-generator:dsh-protocol:end -->'

usage() {
  sed -n '17,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

die() { printf '[cannbot-dsh-protocol] ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '[cannbot-dsh-protocol] %s\n' "$*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dsh-home)
      [[ -n "${2:-}" ]] || die "--dsh-home needs a path"
      DSH_HOME_DIR="$2"; shift 2 ;;
    --check) CHECK_ONLY=1; shift ;;
    --force) FORCE=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
done

[[ -f "${PROTOCOL_SRC}" ]] || die "protocol source not found: ${PROTOCOL_SRC}"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

TARGET="${DSH_HOME_DIR}/AGENTS.md"

state_of() {
  python3 -c '
import pathlib, sys
target, begin, end = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(target)
text = p.read_text(encoding="utf-8") if p.is_file() else ""
nb, ne = text.count(begin), text.count(end)
if nb == 0 and ne == 0:
    print("absent"); raise SystemExit(0)
if nb != 1 or ne != 1 or text.index(begin) > text.index(end):
    print(f"malformed(begin={nb},end={ne})"); raise SystemExit(2)
print("present"); raise SystemExit(0)
' "$1" "${BEGIN_MARK}" "${END_MARK}"
}

if [[ "${CHECK_ONLY}" == "1" ]]; then
  state="$(state_of "${TARGET}")" || die "managed block is malformed in ${TARGET}"
  log "target: ${TARGET}"
  log "state : ${state}"
  exit 0
fi

if [[ "${FORCE}" != "1" && -e "${TARGET}" && ! -f "${TARGET}" ]]; then
  die "target exists and is not a regular file: ${TARGET}"
fi

# 安装前先校验受管块：已损坏（标记重复或乱序）时拒绝写入。否则非贪婪匹配会连同标记
# 之间的内容一并删除，写后校验反而通过。此处与 uninstall.sh 对 malformed 的处理一致。
if [[ -f "${TARGET}" ]]; then
  state_of "${TARGET}" >/dev/null \
    || die "managed block is malformed in ${TARGET}; repair or remove it manually, then retry"
fi

mkdir -p "${DSH_HOME_DIR}" || die "cannot create ${DSH_HOME_DIR}"

BACKUP=""
if [[ -f "${TARGET}" ]]; then
  BACKUP="${TARGET}.bak.$(date +%Y%m%d%H%M%S)"
  cp -p "${TARGET}" "${BACKUP}" || die "cannot back up ${TARGET}"
fi

BLOCK_FILE="$(mktemp)"
restore() {
  rm -f "${BLOCK_FILE}"
  if [[ -n "${BACKUP}" && -f "${BACKUP}" ]]; then
    cp -p "${BACKUP}" "${TARGET}"
  else
    rm -f "${TARGET}"
  fi
}
trap 'rm -f "${BLOCK_FILE}"' EXIT

{
  printf '%s\n\n' "${BEGIN_MARK}"
  cat "${PROTOCOL_SRC}"
  printf '\n%s\n' "${END_MARK}"
} > "${BLOCK_FILE}"

python3 - "${TARGET}" "${BLOCK_FILE}" "${BEGIN_MARK}" "${END_MARK}" <<'PY'
import pathlib, re, sys

target, block_file, begin, end = sys.argv[1:5]
path = pathlib.Path(target)
text = path.read_text(encoding="utf-8") if path.is_file() else ""
block = pathlib.Path(block_file).read_text(encoding="utf-8").strip("\n")

pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
remaining = pattern.sub("", text).strip("\n")

if remaining.strip():
    path.write_text(f"{remaining}\n\n{block}\n", encoding="utf-8")
else:
    path.write_text(f"{block}\n", encoding="utf-8")
PY

if ! state="$(state_of "${TARGET}")" || [[ "${state}" != "present" ]]; then
  restore
  die "validation failed; previous state restored"
fi

log "installed managed block into ${TARGET}"
[[ -n "${BACKUP}" ]] && log "backup : ${BACKUP}"
log "scope  : only DeepSeek Harness reads this file"
log "disable: bash ${SCRIPT_DIR}/uninstall.sh --dsh-home '${DSH_HOME_DIR}'"
