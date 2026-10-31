#!/bin/bash
# ============================================================
# GE_SESSION_DEMO run entry
#
# Usage:
#   MODEL_ID=<id> bash test.sh                 # single inference
#   MODEL_ID=<id> THREAD_NUM=4 CircleCount=5000 bash test.sh  # benchmark
#
# Prerequisite:
#   python3 tools/prepare_model.py <id>
#   (edit M<id>/config/shape_config.json if needed)
#   python3 tools/prepare_input.py <id>
# ============================================================

# ---------- 0. common environment (CANN / driver; arm64 + x86 auto-detected) ----------
ARCH=$(uname -m)                                   # aarch64 | x86_64
CANN=${CANN_HOME:-/usr/local/Ascend/ascend-toolkit/latest}
if [ ! -d "$CANN" ]; then
  CANN=$(ls -d /usr/local/Ascend/ascend-toolkit/*/ 2>/dev/null | tail -1)
fi
if [ -f "$CANN/set_env.sh" ]; then
  source "$CANN/set_env.sh" 2>/dev/null || true
else
  source /usr/local/Ascend/ascend-toolkit/set_env.sh 2>/dev/null || true
fi
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/Ascend/driver/lib64/driver
# C++ headers may be needed by runtime TBE/GE compile; pick the active gcc/arch path if it exists
GCC_VER=$(gcc -dumpversion 2>/dev/null || true)
GCC_MACH=$(gcc -dumpmachine 2>/dev/null || true)
for d in "/usr/include/c++/$GCC_VER/$GCC_MACH" "/usr/include/c++/$GCC_VER/${ARCH}-linux-gnu"; do
  if [ -n "$GCC_VER" ] && [ -d "$d" ]; then
    export CPLUS_INCLUDE_PATH=$d:/usr/include/c++/$GCC_VER:$CPLUS_INCLUDE_PATH
    break
  fi
done
# GE initialization (CANN_KB) needs numpy/tbe, so python site-packages is required
PY_SITE=$(python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])' 2>/dev/null || true)
[ -n "$PY_SITE" ] && export PYTHONPATH=$PY_SITE:$PYTHONPATH
export PYTHONPATH=$PYTHONPATH:/usr/local/lib/python3.11/site-packages:/usr/local/lib64/python3.11/site-packages
export PYTHONPATH=$PYTHONPATH:$CANN/python/site-packages
export PYTHONPATH=$PYTHONPATH:$CANN/opp/built-in/op_impl/ai_core/tbe

# Model-specific environment is provided by models/M<id>/M<id>_env.sh (see section 1 below).

# ---------- 1. model and workspace ----------
CODE_ROOT=$(cd "$(dirname "$0")" && pwd)              # code/build root (this script)
export GE_DEMO_ROOT=${GE_DEMO_ROOT:-$CODE_ROOT}       # workspace root; override to use another models/ tree
if [ -z "${MODEL_ID:-}" ]; then
  echo "[ERROR] MODEL_ID is required (e.g. MODEL_ID=<id> bash test.sh)"; exit 1
fi
case "$MODEL_ID" in
  ''|*[!A-Za-z0-9_]*) echo "[ERROR] invalid MODEL_ID: $MODEL_ID (allowed: A-Z a-z 0-9 _)"; exit 1;;
esac
# export GE_DEVICE_ID=0                             # ge.exec.deviceId, default 0

# Model env: source models/M<id>/M<id>_env.sh on every run; models are isolated.
MODEL_ENV=$GE_DEMO_ROOT/models/M$MODEL_ID/M${MODEL_ID}_env.sh
if [ -f "$MODEL_ENV" ]; then
  source "$MODEL_ENV"
else
  echo "[test.sh][WARN] model env not found: $MODEL_ENV (using default environment)"
fi

# ---------- 2. run scale (device / threads / iterations) ----------
export DEVICE_NUM=${DEVICE_NUM:-1}       # number of devices to use
export START_DEVICE=${START_DEVICE:-0}   # start device/die id
export THREAD_NUM=${THREAD_NUM:-1}       # concurrent threads
export CircleCount=${CircleCount:-1}     # iterations per thread (default 1; pass explicitly for benchmark)
export MaxQPS=${MaxQPS:-20000}           # global request rate limit (shared by all threads)
export DebugFreq=${DebugFreq:-1000}      # progress print interval (every N iterations)
export GRAPH_MAX_PARALLEL=${GRAPH_MAX_PARALLEL:-8}  # RunGraphAsync graph instance parallel limit (reference)

# ---------- 3. precision and memory ----------
export CORE_NUM=${CORE_NUM:-"24|48"}     # ge.aicoreNum = AIC|AIV
export FORCE_16=${FORCE_16:-False}       # True=force_fp16；False=must_keep_origin_dtype
export ENABLE_HF32=${ENABLE_HF32:-False} # True/1=all, 01=MatMul only, 10=Conv only, 00/False=off
export KeepDims=${KeepDims:-False}       # True = do not expand input by batch

# optional: GE precision/fusion config (unset by default)
# export GE_OP_PRECISION_MODE=/path/to/implmode.ini
# export GE_FUSION_SWITCH_FILE=/path/to/fusion_switch.cfg

# ---------- 4. feature switches ----------
export PrintOutput=${PrintOutput:-True}  # True = parse and dump outputs to M<id>/output/
export DumpData=${DumpData:-false}       # GE data dump

dumpGraphFlag=${dumpGraphFlag:-false}     # export graph structure (enabled by run.sh --dump_graph or explicit export)
plogFlag=${plogFlag:-false}               # enable GE plog (enabled by run.sh --info/--debug or explicit export)
# profiling collection: off | msprof | ge (default off, explicit)
export PROF=${PROF:-off}

# ---------- 4.1 concurrency constraints ----------
# Concurrency (THREAD_NUM>1) is for benchmarking only: no dump/verify, no output dump.
if [ "${THREAD_NUM:-1}" -gt 1 ]; then
  if [ "$DumpData" == "true" ]; then
    echo "[ERROR] DumpData is not allowed when THREAD_NUM>1 (concurrent benchmark)"; exit 1
  fi
  if [ "$dumpGraphFlag" == "true" ]; then
    echo "[ERROR] dumpGraphFlag is not allowed when THREAD_NUM>1 (concurrent benchmark)"; exit 1
  fi
  if [ "$PrintOutput" == "True" ]; then
    echo "[test.sh][WARN] PrintOutput disabled in concurrent mode; output will not be dumped"
  fi
fi

# ---------- 5. cache and artifact management ----------
# per-model cache dir: M<id>/.cache/
#   run/                 process cwd; fusion_result.json + kernel_meta (removed by default)
#   dump_graph/ dump_data/  kept artifacts, at most 3 each
#   profiling/           kept artifacts, unlimited
CACHE_DIR=$GE_DEMO_ROOT/models/M$MODEL_ID/.cache
RUN_DIR=$CACHE_DIR/run
mkdir -p "$RUN_DIR" "$CACHE_DIR/dump_graph" "$CACHE_DIR/dump_data" "$CACHE_DIR/profiling"
export GE_DUMP_PATH=$CACHE_DIR/dump_data
export GE_ERROR_LOG=$CACHE_DIR/error.log
rm -f "$GE_ERROR_LOG" 2>/dev/null || true

# Reuse compile cache for repeated runs of the same config (KEEP_KERNEL_META=True)
if [ "${KEEP_KERNEL_META:-False}" != "True" ]; then
  rm -rf "$RUN_DIR/kernel_meta"/* 2>/dev/null || true
  rm -f "$RUN_DIR/fusion_result.json" 2>/dev/null || true
fi

if [ "$dumpGraphFlag" == true ]; then
  echo "dump graph!!!"
  export DUMP_GRAPH_PATH="$CACHE_DIR/dump_graph"
  export PRINT_MODEL=1
  export DUMP_GE_GRAPH=2
  export DUMP_GRAPH_LEVEL=1
fi

if [ "$plogFlag" == true ]; then
  # log level provided by caller: run.sh --info=2 (normal) / --debug=0 (DEBUG); default 0
  export ASCEND_GLOBAL_LOG_LEVEL=${ASCEND_GLOBAL_LOG_LEVEL:-0}
  echo "plog open!!! ASCEND_GLOBAL_LOG_LEVEL=$ASCEND_GLOBAL_LOG_LEVEL"
  export ASCEND_GLOBAL_EVENT_ENABLE=1
  export ASCEND_SLOG_PRINT_TO_STDOUT=1
  export ASCEND_HOST_FILE_NUM=1000
fi

if [ "$PROF" == "ge" ]; then
  echo "profiling(GE) open!!!"
  export PROFILING_MODE=true
  export PROFILING_OPTIONS="{\"output\":\"$CACHE_DIR/profiling\", \"training_trace\":\"on\", \"task_trace\":\"on\", \"aicpu\":\"on\", \"aic_metrics\":\"PipeUtilization\", \"runtime_api\": \"on\"}"
fi

# ---------- 6. launch (cwd=RUN_DIR to isolate GE artifacts) ----------
if [ "$PROF" == "msprof" ]; then
  echo "profiling(msprof) open -> $CACHE_DIR/profiling"
  ( cd "$RUN_DIR" && msprof --output="$CACHE_DIR/profiling" --task-time=on --aicpu=on \
      --aic-metrics=PipeUtilization --runtime-api=on "$CODE_ROOT/GEsession_test_acl" )
  RC=$?
else
  npu-smi info 2>/dev/null || true
  # when --info/--debug/--dump_graph/--dump_data is on, save stdout to models/M<id>/report/ to avoid flooding and allow review
  if [ "$plogFlag" == true ] || [ "$dumpGraphFlag" == true ] || [ "$DumpData" == true ]; then
    LOG_DIR=$GE_DEMO_ROOT/models/M$MODEL_ID/report
    mkdir -p "$LOG_DIR"
    RUN_LOG=$LOG_DIR/run_debug_$(date +%Y%m%d_%H%M%S).log
    echo "[test.sh][debug] run log -> $RUN_LOG"
    ( cd "$RUN_DIR" && "$CODE_ROOT/GEsession_test_acl" ) > "$RUN_LOG" 2>&1
    RC=$?
    echo "[test.sh][debug] run log saved: $RUN_LOG ($(du -h "$RUN_LOG" 2>/dev/null | cut -f1))"
  else
    ( cd "$RUN_DIR" && "$CODE_ROOT/GEsession_test_acl" )
    RC=$?
  fi
fi

# ---------- 7. artifact retention: keep latest 3 of dump_graph/dump_data; print inventory ----------
keep_latest() {
  local d=$1
  [ -d "$d" ] || return 0
  local count=0 line path
  while IFS= read -r line; do
    count=$((count + 1))
    [ "$count" -le 3 ] && continue
    path=${line#* }
    rm -rf -- "$path"
  done < <(find "$d" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' 2>/dev/null | sort -rn)
}
keep_latest "$CACHE_DIR/dump_graph"
keep_latest "$CACHE_DIR/dump_data"

echo "[test.sh] artifacts: $CACHE_DIR"
du -sh "$CACHE_DIR"/* 2>/dev/null || true
exit $RC