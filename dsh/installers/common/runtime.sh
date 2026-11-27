#!/bin/sh
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

set -eu
umask 077
if [ "${1:-}" = --help ] || [ "${1:-}" = -h ]; then
    echo 'CANNBot-Setup.sh [--edition client|server] [--profile NAME]'
    exit 0
fi
common=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! grep -Eq '"manifestUrl"[[:space:]]*:[[:space:]]*"https://' "$common/release-source.json"; then
    echo '安装包未配置版本清单地址。' >&2
    exit 1
fi
if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 &&
   node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>24 || a===24 && b>=9 ? 0:1)'; then
    exec node "$common/install-unix.mjs" "$@"
fi
case "$(uname -s)-$(uname -m)" in
    Linux-x86_64) target=linux-x64 ;;
    Linux-aarch64|Linux-arm64) target=linux-arm64 ;;
    Darwin-x86_64) target=darwin-x64 ;;
    Darwin-arm64) target=darwin-arm64 ;;
    *) echo '当前系统架构尚未支持。' >&2; exit 1 ;;
esac
archive="node-v24.22.3-$target"
base="$HOME/.local/share/cannbot/runtime"
if [ -x "$base/$archive/bin/node" ]; then
    bin="$base/$archive/bin"
else
    temp="$CANNBOT_SETUP_TEMP"
    CANNBOT_RUNTIME_TO_KEEP="$archive"
    export CANNBOT_RUNTIME_TO_KEEP
    echo '正在下载官方 Node.js 运行环境…'
    curl --fail --silent --show-error --proto '=https' --max-time 300 --output "$temp/runtime.tgz" "https://nodejs.org/dist/v24.22.3/$archive.tar.gz"
    tar -xzf "$temp/runtime.tgz" -C "$temp"
    bin="$temp/$archive/bin"
fi
PATH="$bin:$PATH"; export PATH
exec node "$common/install-unix.mjs" "$@"
