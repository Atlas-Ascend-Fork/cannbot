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
# CANNBot DSH dispatch-protocol uninstaller (tilelang2ascendc-ops-generator).
#
# Removes the managed block previously written into
# ${DSH_HOME:-$HOME/.dsh}/AGENTS.md by install.sh. Other content in the file is
# preserved; if the file is left empty it is removed, because the installer
# created it only for this block.
#
# Usage:
#   ./uninstall.sh [--dsh-home <path>] [--purge]
#
#   --dsh-home <path>  DSH home directory (default: $DSH_HOME or ~/.dsh)
#   --purge            also delete AGENTS.md backups created by install.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DSH_HOME_DIR="${DSH_HOME:-$HOME/.dsh}"
PURGE=0

BEGIN_MARK='<!-- cannbot:tilelang2ascendc-ops-generator:dsh-protocol:start -->'
END_MARK='<!-- cannbot:tilelang2ascendc-ops-generator:dsh-protocol:end -->'

usage() {
  sed -n '13,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

die() { printf '[cannbot-dsh-protocol] ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '[cannbot-dsh-protocol] %s\n' "$*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dsh-home)
      [[ -n "${2:-}" ]] || die "--dsh-home needs a path"
      DSH_HOME_DIR="$2"; shift 2 ;;
    --purge) PURGE=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
done

command -v python3 >/dev/null 2>&1 || die "python3 is required"

TARGET="${DSH_HOME_DIR}/AGENTS.md"

if [[ ! -f "${TARGET}" ]]; then
  log "nothing to do: ${TARGET} not found"
else
  python3 - "${TARGET}" "${BEGIN_MARK}" "${END_MARK}" <<'PY'
import pathlib, re, sys

target, begin, end = sys.argv[1:4]
path = pathlib.Path(target)
text = path.read_text(encoding="utf-8")

nb, ne = text.count(begin), text.count(end)
if nb == 0 and ne == 0:
    print("absent")
    raise SystemExit(0)
if nb != 1 or ne != 1 or text.index(begin) > text.index(end):
    print(f"malformed(begin={nb},end={ne})")
    raise SystemExit(3)

pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
remaining = pattern.sub("", text).strip("\n")

if remaining.strip():
    path.write_text(f"{remaining}\n", encoding="utf-8")
    print("block-removed")
else:
    path.unlink()
    print("file-removed")
PY
fi

if [[ "${PURGE}" == "1" ]]; then
  shopt -s nullglob
  backups=("${TARGET}".bak.*)
  if [[ "${#backups[@]}" -eq 0 ]]; then
    log "no backups to purge"
  else
    for backup in "${backups[@]}"; do
      rm -f "${backup}" && log "purged: ${backup}"
    done
  fi
fi

log "done; reinstall with: bash ${SCRIPT_DIR}/install.sh --dsh-home '${DSH_HOME_DIR}'"
