#!/bin/bash
# ============================================================
# GE_SESSION_DEMO build script
#   Output: ./GEsession_test_acl
#   Depends: CANN toolchain (libascendcl / libgraph / libge_runner ...)
#   Supports aarch64 and x86_64 hosts (arch auto-detected)
# ============================================================
set -e

ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT"

ARCH=$(uname -m)                                   # aarch64 | x86_64
CANN=${CANN_HOME:-/usr/local/Ascend/ascend-toolkit/latest}
if [ ! -d "$CANN" ]; then
  CANN=$(ls -d /usr/local/Ascend/ascend-toolkit/*/ 2>/dev/null | tail -1)
fi

LIBDIR=""
for d in "$CANN/${ARCH}-linux/lib64" "$CANN/lib64" "$CANN/${ARCH}-linux/devlib"; do
  if [ -e "$d/libascendcl.so" ]; then LIBDIR=$d; break; fi
done
if [ -z "$LIBDIR" ]; then
  echo "[compile][ERROR] libascendcl.so not found under CANN root: ${CANN:-<not found>}" >&2
  echo "[compile][ERROR] set CANN_HOME to your CANN install dir and retry" >&2
  exit 1
fi

g++ -g -std=c++17 \
  -I ./src -I "$CANN/include" \
  -L "$LIBDIR" -L /usr/lib64 -lpthread \
  -Wl,-rpath,"$LIBDIR" \
  -lascendcl -lfmk_parser -lgraph -lge_runner_v2 -lge_compiler -lgraph_base -lge_common \
  -lfmk_onnx_parser \
  -o GEsession_test_acl src/*.cc

echo "[compile] done -> $ROOT/GEsession_test_acl (arch=$ARCH, libdir=$LIBDIR)"