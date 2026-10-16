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
# rebuild_if_modified.sh — rebuild the cake {Op}Custom/ tree after transform.py.
#
# transform.py always renames the op-class symbol (Kernel → {Op}Custom), so the
# .run package emitted by easyasc's run_codegen.py is stale: it has the wrong
# registered op name. Therefore this script ALWAYS rebuilds by default.
#
# To skip the rebuild (e.g. for a dry-run check), pass --skip-rebuild.
#
# Usage:
#   bash rebuild_if_modified.sh <op_name> [--output-root <path>] [--skip-rebuild]
#
# Reads / mutates: <output-root>/<op>/easyasc_workspace/codegen_status.json
#   - reads post.dst_dir
#   - on success: sets next_step="verify", post.run_package=<new .run path>
#   - on failure: sets next_step="human-intervention"
#
# Exit codes:
#   0  build succeeded (or skip-rebuild)
#   1  build failed
#   2  setup error

set -euo pipefail

usage() {
    echo "Usage: $0 <op_name> [--output-root <path>] [--skip-rebuild]" >&2
    exit 2
}

OP_NAME="${1:-}"
shift || true
[[ -z "${OP_NAME}" ]] && usage

OUTPUT_ROOT="./output"
SKIP_REBUILD=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-root) OUTPUT_ROOT="$2"; shift 2 ;;
        --skip-rebuild) SKIP_REBUILD=1; shift ;;
        *) echo "[rebuild] unknown arg: $1" >&2; usage ;;
    esac
done

OUTPUT_ROOT_ABS="$(cd "${OUTPUT_ROOT}" && pwd)"
WS="${OUTPUT_ROOT_ABS}/${OP_NAME}/easyasc_workspace"
STATUS="${WS}/codegen_status.json"

if [[ ! -f "${STATUS}" ]]; then
    echo "[rebuild] ERROR: ${STATUS} missing" >&2
    exit 2
fi

DST="$(python3 -c "import json,sys; s=json.load(open('${STATUS}')); print(s.get('post',{}).get('dst_dir','') or '')")"
if [[ -z "${DST}" || ! -d "${DST}" ]]; then
    echo "[rebuild] ERROR: post.dst_dir missing or invalid in status" >&2
    exit 2
fi

if [[ "${SKIP_REBUILD}" == "1" ]]; then
    EXISTING_RUN="$(ls "${DST}/build_out"/custom_opp_*.run 2>/dev/null | head -1 || true)"
    if [[ -z "${EXISTING_RUN}" ]]; then
        echo "[rebuild] ERROR: --skip-rebuild but no existing .run in ${DST}/build_out/" >&2
        exit 1
    fi
    echo "[rebuild] SKIP (using stale .run): ${EXISTING_RUN}"
    python3 - "${STATUS}" "${EXISTING_RUN}" <<'PY'
import json, sys
p, run = sys.argv[1], sys.argv[2]
s = json.load(open(p))
s.setdefault("post", {})["run_package"] = run
s["next_step"] = "verify"
json.dump(s, open(p, "w"), indent=2)
PY
    exit 0
fi

echo "[rebuild] building ${DST}"
cd "${DST}"

# Wipe stale build_out so we don't conflate easyasc's run.
if [[ -d build_out ]]; then
    rm -rf build_out
fi

LOG="${DST}/build.log"
if ! bash ./build.sh 2>&1 | tee "${LOG}"; then
    echo "[rebuild] FAIL: build.sh exited non-zero; see ${LOG}" >&2
    python3 - "${STATUS}" <<'PY'
import json, sys
p = sys.argv[1]
s = json.load(open(p))
s["next_step"] = "human-intervention"
json.dump(s, open(p, "w"), indent=2)
PY
    exit 1
fi

NEW_RUN="$(ls "${DST}/build_out"/custom_opp_*.run 2>/dev/null | head -1 || true)"
if [[ -z "${NEW_RUN}" ]]; then
    echo "[rebuild] FAIL: build.sh succeeded but no .run package found" >&2
    exit 1
fi

echo "[rebuild] PASS run_package=${NEW_RUN}"
python3 - "${STATUS}" "${NEW_RUN}" <<'PY'
import json, sys
p, run = sys.argv[1], sys.argv[2]
s = json.load(open(p))
s.setdefault("post", {})["run_package"] = run
s["next_step"] = "verify"
json.dump(s, open(p, "w"), indent=2)
PY
