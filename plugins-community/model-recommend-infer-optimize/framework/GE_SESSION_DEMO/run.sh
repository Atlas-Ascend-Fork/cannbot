#!/bin/bash
# ============================================================
# GE_SESSION_DEMO convenience entry
#
# Usage:
#   bash run.sh <id>                         # run with defaults below
#   bash run.sh <id> --threads 4 --no-print-output  # override via args
#   bash run.sh <id> --show                  # print effective config and exit
#
# Notes:
#   - defaults come from this script (DEF_*) and test.sh env defaults; CLI overrides both.
#   - test.sh can still run standalone (env-driven); run.sh parses args, exports, then calls test.sh.
#   - --verify requires PrintOutput and threads=1; it checks the inference RC, then verifies only the
#     current run (GE_RUN_ID + output/.complete). --golden-source user never generates golden.
# ============================================================
set -u

ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT"

# ============ defaults (override via CLI) ============
DEF_THREADS=1            # concurrent threads
DEF_CORES="24|48"        # CORE_NUM = AIC|AIV
DEF_CIRCLE=1             # iterations (single request = 1)
DEF_DEBUG_FREQ=1000      # progress print interval
DEF_DEVICE=0             # start die
DEF_BATCH=""             # when set, update shape_config.batch_size and regenerate input
DEF_PRINT_OUTPUT=True    # dump outputs after inference
DEF_PROF="off"           # off | msprof | ge
DEF_VERIFY=False         # run accuracy verification after inference
DEF_VERIFY_SOURCE="auto" # auto | user | ort
DEF_GRAPH_MAX_PARALLEL=8 # RunGraphAsync graph instance parallel limit (reference)
DEF_INFO=False           # True = enable GE plog, normal logs (ASCEND_GLOBAL_LOG_LEVEL=2)
DEF_DEBUG=False          # True = enable GE plog, DEBUG logs (ASCEND_GLOBAL_LOG_LEVEL=0)
DEF_DUMP_GRAPH=False     # True = export graph structure (dumpGraphFlag)
DEF_DUMP_DATA=False      # True = enable GE data dump (DumpData)
DEF_RESTORE=False        # True = restore the workspace from the last --batch backup
DEF_DRY_RUN=False        # True = only print what --batch would change

usage() {
  cat <<'EOF'
usage: bash run.sh <model_id> [options]

options:
  --threads N          concurrent threads (default 1)
  --cores "A|V"        core limit AIC|AIV (default "24|48")
  --circle N           benchmark iterations (default 1)
  --debug-freq N       progress print interval (default 1000)
  --device N           start die (default 0)
  --batch N            set batch_size and regenerate input (default off)
  --print-output       dump output after inference (default on)
  --no-print-output    do not dump output
  --prof off|msprof|ge profiling (default off)
  --verify             run accuracy verification (tools/verify.py)
  --golden-source S    verify golden source: auto | user | ort (default auto)
  --ref-dir DIR        verify golden directory (default M<id>/reference; user source)
  --info               enable GE plog, normal logs (ASCEND_GLOBAL_LOG_LEVEL=2)
  --debug              enable GE plog, DEBUG logs (ASCEND_GLOBAL_LOG_LEVEL=0)
  --dump_graph         dump graph to models/M<id>/.cache/dump_graph
  --dump_data          dump GE data to models/M<id>/.cache/dump_data
  --dry-run            with --batch: print the planned change and exit without writing
  --restore            restore shape_config/io_config/input_data from the last --batch backup
  --show               print effective configuration and exit
  -h, --help           show this help
EOF
}

# ============ argument parsing ============
MODEL_ID=""
THREADS=$DEF_THREADS
CORES=$DEF_CORES
CIRCLE=$DEF_CIRCLE
DEBUG_FREQ=$DEF_DEBUG_FREQ
DEVICE=$DEF_DEVICE
BATCH=$DEF_BATCH
PRINT_OUTPUT=$DEF_PRINT_OUTPUT
PROF=$DEF_PROF
VERIFY=$DEF_VERIFY
VERIFY_SOURCE=$DEF_VERIFY_SOURCE
VERIFY_REF_DIR=""
GRAPH_MAX_PARALLEL=$DEF_GRAPH_MAX_PARALLEL
INFO=$DEF_INFO
DEBUG=$DEF_DEBUG
DUMP_GRAPH=$DEF_DUMP_GRAPH
DUMP_DATA=$DEF_DUMP_DATA
RESTORE=$DEF_RESTORE
DRY_RUN=$DEF_DRY_RUN
SHOW=0

need_arg() {
  if [ "$2" -lt 2 ]; then
    echo "[ERROR] $1 requires an argument"
    usage
    exit 1
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --threads)      need_arg "$1" "$#"; THREADS="$2"; shift 2;;
    --cores)        need_arg "$1" "$#"; CORES="$2"; shift 2;;
    --circle)       need_arg "$1" "$#"; CIRCLE="$2"; shift 2;;
    --debug-freq)   need_arg "$1" "$#"; DEBUG_FREQ="$2"; shift 2;;
    --device)       need_arg "$1" "$#"; DEVICE="$2"; shift 2;;
    --batch)        need_arg "$1" "$#"; BATCH="$2"; shift 2;;
    --print-output) PRINT_OUTPUT="True"; shift;;
    --no-print-output) PRINT_OUTPUT="False"; shift;;
    --prof)         need_arg "$1" "$#"; PROF="$2"; shift 2;;
    --verify)       VERIFY="True"; shift;;
    --golden-source) need_arg "$1" "$#"; VERIFY_SOURCE="$2"; shift 2;;
    --ref-dir)      need_arg "$1" "$#"; VERIFY_REF_DIR="$2"; shift 2;;
    --graph-max-parallel) need_arg "$1" "$#"; GRAPH_MAX_PARALLEL="$2"; shift 2;;
    --info)         INFO="True"; shift;;
    --debug)        DEBUG="True"; shift;;
    --dump_graph)   DUMP_GRAPH="True"; shift;;
    --dump_data)    DUMP_DATA="True"; shift;;
    --dry-run)      DRY_RUN="True"; shift;;
    --restore)      RESTORE="True"; shift;;
    --show)         SHOW=1; shift;;
    -h|--help)      usage; exit 0;;
    -*)             echo "[ERROR] unknown option: $1"; usage; exit 1;;
    *)              if [ -z "$MODEL_ID" ]; then MODEL_ID="$1"; shift; else
                      echo "[ERROR] unexpected positional argument: $1"; usage; exit 1; fi;;
  esac
done

# ============ validation ============
if [ -z "$MODEL_ID" ]; then
  echo "[ERROR] missing <model_id>"; usage; exit 1
fi
case "$MODEL_ID" in
  *[!A-Za-z0-9_]*) echo "[ERROR] invalid MODEL_ID: $MODEL_ID (allowed: A-Z a-z 0-9 _)"; exit 1;;
esac
case "$THREADS" in ''|*[!0-9]*) echo "[ERROR] --threads must be a non-negative integer: $THREADS"; exit 1;; esac
case "$CIRCLE" in ''|*[!0-9]*) echo "[ERROR] --circle must be a non-negative integer: $CIRCLE"; exit 1;; esac
case "$DEBUG_FREQ" in ''|*[!0-9]*) echo "[ERROR] --debug-freq must be a non-negative integer: $DEBUG_FREQ"; exit 1;; esac
case "$DEVICE" in ''|*[!0-9]*) echo "[ERROR] --device must be a non-negative integer: $DEVICE"; exit 1;; esac
if [ -n "$BATCH" ]; then
  case "$BATCH" in ''|*[!0-9]*) echo "[ERROR] --batch must be a non-negative integer: $BATCH"; exit 1;; esac
fi
if ! echo "$CORES" | grep -qE '^[0-9]+\|[0-9]+$'; then
  echo "[ERROR] --cores must be \"AIC|AIV\" (e.g. \"24|48\"), got: $CORES"; exit 1
fi
case "$PROF" in off|msprof|ge) ;; *) echo "[ERROR] --prof must be off|msprof|ge, got: $PROF"; exit 1;; esac
case "$VERIFY_SOURCE" in auto|user|ort) ;; *) echo "[ERROR] --golden-source must be auto|user|ort, got: $VERIFY_SOURCE"; exit 1;; esac
case "$GRAPH_MAX_PARALLEL" in ''|*[!0-9]*) echo "[ERROR] --graph-max-parallel must be a non-negative integer: $GRAPH_MAX_PARALLEL"; exit 1;; esac
if [ ! -d "$ROOT/models/M$MODEL_ID" ]; then
  echo "[ERROR] workspace not found: $ROOT/models/M$MODEL_ID (prepare model and input first)"; exit 1
fi
if [ "$VERIFY" == "True" ] && [ "$THREADS" -gt 1 ]; then
  echo "[ERROR] --verify requires serial single concurrency (--threads 1)"; exit 1
fi
if [ "$VERIFY" == "True" ] && [ "$PRINT_OUTPUT" != "True" ]; then
  echo "[ERROR] --verify requires --print-output (output/.complete is needed)"; exit 1
fi

# ============ effective configuration ============
export GE_DEMO_ROOT=$ROOT
export MODEL_ID=$MODEL_ID
export THREAD_NUM=$THREADS
export CORE_NUM=$CORES
export CircleCount=$CIRCLE
export DebugFreq=$DEBUG_FREQ
export START_DEVICE=$DEVICE
export PrintOutput=$PRINT_OUTPUT
export PROF=$PROF
export GRAPH_MAX_PARALLEL=$GRAPH_MAX_PARALLEL

# log switches: --info normal (level 2) / --debug DEBUG (level 0); if both, --debug wins
if [ "$INFO" == "True" ] || [ "$DEBUG" == "True" ]; then
  export plogFlag=true
fi
if [ "$DEBUG" == "True" ]; then
  export ASCEND_GLOBAL_LOG_LEVEL=0
elif [ "$INFO" == "True" ]; then
  export ASCEND_GLOBAL_LOG_LEVEL=2
fi

# dump switches: graph and data are independent
if [ "$DUMP_GRAPH" == "True" ]; then
  export dumpGraphFlag=true   # graph dump to M<id>/.cache/dump_graph
fi
if [ "$DUMP_DATA" == "True" ]; then
  export DumpData=true        # data dump to M<id>/.cache/dump_data
fi

# shape strategy: io_config.json is ground truth (shape_mode/pass_input_shape);
# fall back to shape_config.json mode when io_config has not been generated yet.
SHAPE_INFO=$(python3 - "$MODEL_ID" <<'PY' 2>/dev/null
import json, sys
mid = sys.argv[1].lstrip("Mm")
mode = "<shape_config.json not found>"
try:
    mode = json.load(open(f"models/M{mid}/config/shape_config.json")).get("mode", "?")
except Exception:
    pass
pis = "<io_config.json not generated>"
try:
    d = json.load(open(f"models/M{mid}/config/io_config.json"))
    pis = str(d.get("pass_input_shape"))
    mode = d.get("shape_mode", mode)
except Exception:
    pass
print(f"{mode}\t{pis}")
PY
)
SHAPE_MODE="<unknown>"
PASS_INPUT_SHAPE="<unknown>"
if [ -n "$SHAPE_INFO" ]; then
  IFS=$'\t' read -r SHAPE_MODE PASS_INPUT_SHAPE <<< "$SHAPE_INFO"
fi

echo "============================================================"
echo " run.sh - effective configuration"
echo "============================================================"
printf "  %-18s : %s\n" "MODEL_ID"           "$MODEL_ID"
printf "  %-18s : %s\n" "BATCH"              "${BATCH:-<default>}"
printf "  %-18s : %s\n" "shape_mode"         "$SHAPE_MODE"
printf "  %-18s : %s\n" "pass_input_shape"   "$PASS_INPUT_SHAPE"
echo "------------------------------------------------------------"
printf "  %-18s : %s\n" "THREAD_NUM"         "$THREADS"
printf "  %-18s : %s\n" "CORE_NUM"           "$CORES"
printf "  %-18s : %s\n" "DEVICE"             "$DEVICE"
printf "  %-18s : %s\n" "CircleCount"        "$CIRCLE"
printf "  %-18s : %s\n" "DebugFreq"          "$DEBUG_FREQ"
printf "  %-18s : %s\n" "PrintOutput"        "$PRINT_OUTPUT"
echo "------------------------------------------------------------"
printf "  %-18s : %s\n" "PROF"               "$PROF"
printf "  %-18s : %s\n" "VERIFY"             "$VERIFY"
printf "  %-18s : %s\n" "VERIFY_SOURCE"      "$VERIFY_SOURCE"
printf "  %-18s : %s\n" "VERIFY_REF_DIR"     "${VERIFY_REF_DIR:-<default>}"
printf "  %-18s : %s\n" "GRAPH_MAX_PARALLEL" "$GRAPH_MAX_PARALLEL"
printf "  %-18s : %s\n" "INFO"               "$INFO"
printf "  %-18s : %s\n" "DEBUG"              "$DEBUG"
printf "  %-18s : %s\n" "DUMP_GRAPH"         "$DUMP_GRAPH"
printf "  %-18s : %s\n" "DUMP_DATA"          "$DUMP_DATA"
echo "============================================================"

if [ "$SHOW" == "1" ]; then
  exit 0
fi

# ============ batch workspace backup / restore ============
# --batch rewrites shape_config / io_config and regenerates input_data, so keep a
# restorable snapshot under models/M<id>/.cache.
CACHE_DIR="models/M${MODEL_ID}/.cache"
BACKUP_POINTER="$CACHE_DIR/pre_batch_last"

backup_batch_state() {
  local stamp backup item src
  stamp=$(date +%Y%m%d_%H%M%S)
  backup="$CACHE_DIR/pre_batch_$stamp"
  mkdir -p "$backup"
  for item in config/shape_config.json config/io_config.json input_data; do
    src="models/M${MODEL_ID}/$item"
    [ -e "$src" ] || continue
    mkdir -p "$backup/$(dirname "$item")"
    cp -a "$src" "$backup/$item"
  done
  printf '%s\n' "$backup" > "$BACKUP_POINTER"
  echo "[run.sh] backed up batch-affecting state -> $backup"
}

restore_batch_state() {
  local backup item dst
  if [ ! -f "$BACKUP_POINTER" ]; then
    echo "[ERROR] no --batch backup recorded ($BACKUP_POINTER); cannot restore"
    return 1
  fi
  backup=$(cat "$BACKUP_POINTER")
  if [ ! -d "$backup" ]; then
    echo "[ERROR] backup directory missing: $backup"
    return 1
  fi
  for item in config/shape_config.json config/io_config.json input_data; do
    [ -e "$backup/$item" ] || continue
    dst="models/M${MODEL_ID}/$item"
    rm -rf "$dst"
    mkdir -p "$(dirname "$dst")"
    cp -a "$backup/$item" "$dst"
  done
  echo "[run.sh] restored workspace from $backup"
  echo "         (backup pointer kept at $BACKUP_POINTER; --restore can be repeated)"
}

if [ "$RESTORE" == "True" ]; then
  restore_batch_state || exit 1
  exit 0
fi

# ============ batch override (optional) ============
if [ -n "$BATCH" ]; then
  if [ "$DRY_RUN" == "True" ]; then
    echo "[run.sh][dry-run] would set batch_size=$BATCH in models/M${MODEL_ID}/config/shape_config.json"
    echo "[run.sh][dry-run] would run tools/prepare_input.py $MODEL_ID (regenerates io_config + input_data)"
    echo "[run.sh][dry-run] current batch_size=$(python3 -c "import json;print(json.load(open('models/M${MODEL_ID}/config/shape_config.json'))['batch_size'])" 2>/dev/null || echo '?')"
    exit 0
  fi
  backup_batch_state
  echo "[run.sh] set batch_size=$BATCH and regenerate input ..."
  if ! python3 - "$MODEL_ID" "$BATCH" <<'PY'
import json, os, sys, tempfile
mid, b = sys.argv[1], int(sys.argv[2])
p = f"models/M{mid}/config/shape_config.json"
d = json.load(open(p))
d["batch_size"] = b
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".shape_config.", text=True)
with os.fdopen(fd, "w") as f:
    json.dump(d, f, indent=2)
    f.write("\n")
os.replace(tmp, p)
PY
  then
    echo "[ERROR] failed to update shape_config.json"
    exit 1
  fi
  if ! python3 tools/prepare_input.py "$MODEL_ID"; then
    echo "[ERROR] failed to regenerate input for batch=$BATCH"
    exit 1
  fi
fi

# ============ run ============
GE_RUN_ID="$(date +%Y%m%d_%H%M%S)_$$"
export GE_RUN_ID

OUT_DIR=$(python3 - "$MODEL_ID" <<'PY' 2>/dev/null
import json, sys
mid = sys.argv[1].lstrip("Mm")
try:
    d = json.load(open(f"models/M{mid}/config/io_config.json"))
    print(d.get("output_dir") or f"models/M{mid}/output")
except Exception:
    print(f"models/M{mid}/output")
PY
)
if [ -z "$OUT_DIR" ]; then
  OUT_DIR="models/M$MODEL_ID/output"
fi
mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/.complete" "$OUT_DIR/.complete.tmp" 2>/dev/null || true
if [ "$VERIFY" == "True" ]; then
  rm -f "$OUT_DIR"/output_*.bin "$OUT_DIR"/output_shapes.json \
        "$OUT_DIR"/output_shapes.json.tmp "$OUT_DIR"/verify_report.json \
        "$OUT_DIR"/verify_table.log 2>/dev/null || true
fi

bash "$ROOT/test.sh"
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[run.sh] inference failed (rc=$RC); skip verification"
  exit "$RC"
fi

# ============ optional accuracy verification ============
if [ "$VERIFY" == "True" ]; then
  echo "[run.sh] verify accuracy ..."
  VERIFY_ARGS=(--golden-source "$VERIFY_SOURCE" --run-id "$GE_RUN_ID")
  if [ -n "$VERIFY_REF_DIR" ]; then
    VERIFY_ARGS+=(--ref-dir "$VERIFY_REF_DIR")
  fi
  python3 tools/verify.py "$MODEL_ID" "${VERIFY_ARGS[@]}"
  RC=$?
fi
exit $RC