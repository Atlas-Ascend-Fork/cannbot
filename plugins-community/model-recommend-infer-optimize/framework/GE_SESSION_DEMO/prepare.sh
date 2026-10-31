#!/bin/bash
# ============================================================
# GE_SESSION_DEMO model preparation entry
#   Fixes steps 3-5 for a new model:
#     prepare_model.py  ->  (shape policy)  ->  prepare_input.py
#
# Usage:
#   bash prepare.sh <model_id> [--mode all_static|all_dynamic|custom]
#                              [--batch N] [--force]
#                              [--gen-input]
#                              [--config-only] [--input-only]
#
# Prerequisite (place manually):
#   models/M<id>/model/model.onnx              model file
#   models/M<id>/model/<weights>               external weights (if any), same dir as model.onnx
#   models/M<id>/input_data/<onnx input>.npy   inputs (optional; skipped if absent)
#                                              --gen-input generates ALL inputs, only when input_data/ is empty
#
# Notes:
#   - model_id may be given with or without the leading 'M' (e.g. 101 or M101).
#   - --force overwrites an existing shape_config.json (otherwise it is kept).
# ============================================================
set -u

ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT"

MODE="all_static"
BATCH=""
FORCE=0
CONFIG_ONLY=0
INPUT_ONLY=0
GEN_INPUT=0
INPUT_SHAPES=()
MODEL_ID=""

usage() {
  cat <<'EOF'
usage: bash prepare.sh <model_id> [options]

options:
  --mode NAME     shape policy for prepare_model: all_static|all_dynamic|custom (default all_static)
  --batch N       set batch_size (maps to prepare_model --batch-size)
  --force         overwrite an existing shape_config.json
  --gen-input     auto-generate ALL inputs; requires an empty input_data/ (no mixing)
  --input-shape NAME=D0,D1,...  explicit shape for a generated input (repeatable);
                  required when the onnx input has dynamic dims other than axis 0;
                  can also be passed via GEN_INPUT_SHAPE (semicolon separated)
  --config-only   only run prepare_model (so you can edit shape_config.json before prepare_input)
  --input-only    only run prepare_input (run after editing shape_config.json)
                  (--config-only and --input-only are mutually exclusive)
  -h, --help      show this help
EOF
}

need_arg() {
  if [ "$2" -lt 2 ]; then echo "[prepare][ERROR] $1 requires an argument"; usage; exit 1; fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --mode)        need_arg "$1" "$#"; MODE="$2"; shift 2;;
    --batch)       need_arg "$1" "$#"; BATCH="$2"; shift 2;;
    --force)       FORCE=1; shift;;
    --gen-input)   GEN_INPUT=1; shift;;
    --input-shape) need_arg "$1" "$#"; INPUT_SHAPES+=("$2"); shift 2;;
    --config-only) CONFIG_ONLY=1; shift;;
    --input-only)  INPUT_ONLY=1; shift;;
    -h|--help)     usage; exit 0;;
    -*)            echo "[prepare][ERROR] unknown option: $1"; usage; exit 1;;
    *)             if [ -z "$MODEL_ID" ]; then MODEL_ID="$1"; shift; else
                     echo "[prepare][ERROR] unexpected positional argument: $1"; usage; exit 1; fi;;
  esac
done

if [ -z "$MODEL_ID" ]; then
  echo "[prepare][ERROR] missing <model_id>"; usage; exit 1
fi
MODEL_ID="${MODEL_ID#M}"
MODEL_ID="${MODEL_ID#m}"
case "$MODEL_ID" in
  ''|*[!A-Za-z0-9_]*) echo "[prepare][ERROR] invalid model_id (allowed: A-Z a-z 0-9 _)"; exit 1;;
esac
if [ "$CONFIG_ONLY" = 1 ] && [ "$INPUT_ONLY" = 1 ]; then
  echo "[prepare][ERROR] --config-only and --input-only are mutually exclusive"
  usage; exit 1
fi

WS=models/M$MODEL_ID
MFILE=$WS/model/model.onnx

if [ ! -d "$WS" ]; then
  echo "[prepare][ERROR] workspace not found: $WS"
  echo "[prepare] create it and place the model first: mkdir -p $WS/model $WS/input_data"
  exit 1
fi
if [ ! -f "$MFILE" ]; then
  echo "[prepare][ERROR] model not found: $MFILE"
  echo "[prepare] place model.onnx (and its weight file, if any) under $WS/model/"
  exit 1
fi

# --- external weight check: every 'location' referenced by the onnx must exist next to it ---
if [ "$INPUT_ONLY" != 1 ]; then
  python3 - "$MFILE" <<'PY'
import os
import sys

path = sys.argv[1]
try:
    import onnx
except ImportError:
    print("[prepare][ERROR] python package 'onnx' not found: pip install onnx")
    sys.exit(1)

try:
    model = onnx.load(path, load_external_data=False)
except Exception as e:  # noqa: BLE001
    print(f"[prepare][ERROR] cannot read onnx: {e}")
    sys.exit(1)

locs = sorted({d.value for i in model.graph.initializer for d in i.external_data if d.key == "location"})
if not locs:
    print("[prepare] model is self-contained (no external weights)")
    sys.exit(0)

print(f"[prepare] external weights referenced: {locs}")
base = os.path.dirname(os.path.abspath(path))
missing = [l for l in locs if not os.path.exists(os.path.join(base, l))]
if missing:
    print(f"[prepare][ERROR] missing weight file(s) next to model.onnx: {missing}")
    print(f"[prepare] expected under: {base}/")
    sys.exit(1)
print("[prepare] external weights OK")
PY
  rc=$?
  if [ "$rc" -ne 0 ]; then exit 1; fi
fi

# --- step 3 (and optional re-run): prepare_model.py ---
if [ "$INPUT_ONLY" != 1 ]; then
  args=("$MODEL_ID" "--mode" "$MODE")
  [ -n "$BATCH" ] && args+=("--batch-size" "$BATCH")
  [ "$FORCE" = 1 ] && args+=("--force")
  echo "[prepare] run: python3 tools/prepare_model.py ${args[*]}"
  python3 tools/prepare_model.py "${args[@]}" || exit 1
fi

# --- step 4 hint: shape_config.json is user-editable ---
if [ "$CONFIG_ONLY" = 1 ]; then
  echo "[prepare] config-only done. Edit models/M$MODEL_ID/config/shape_config.json if needed,"
  echo "[prepare] then run: bash prepare.sh $MODEL_ID --input-only"
  exit 0
fi

# --- step 5: prepare_input.py ---
shopt -s nullglob
inputs=("$WS"/input_data/*.npy "$WS"/input_data/*.bin)
input_args=()
[ "$GEN_INPUT" = 1 ] && input_args+=("--gen-input")
for shape_spec in "${INPUT_SHAPES[@]}"; do
  input_args+=("--input-shape" "$shape_spec")
done

# --gen-input is only allowed on an empty input_data/; never mix provided and generated inputs.
if [ "$GEN_INPUT" = 1 ] && [ ${#inputs[@]} -gt 0 ]; then
  echo "[prepare][ERROR] --gen-input requires an EMPTY input_data/, but found ${#inputs[@]} file(s):"
  for f in "${inputs[@]}"; do echo "  $f"; done
  echo "[prepare] provide ALL inputs manually, or remove them and rerun with --gen-input."
  echo "[prepare] mixing provided and auto-generated inputs is not allowed."
  exit 1
fi

if [ ${#inputs[@]} -eq 0 ] && [ "$GEN_INPUT" != 1 ]; then
  echo "[prepare][WARN] no input data under $WS/input_data"
  echo "[prepare][WARN] place all <onnx input name>.npy there, or rerun with --gen-input to generate them."
  exit 0
fi

if [ "$GEN_INPUT" = 1 ]; then
  echo "[prepare] --gen-input: input_data/ is empty; all inputs will be auto-generated"
  echo "[prepare]             (fixed seed in tools/prepare_input.py; provide real data to override)"
else
  echo "[prepare] inputs found: ${#inputs[@]} file(s); run: python3 tools/prepare_input.py $MODEL_ID"
fi
python3 tools/prepare_input.py "$MODEL_ID" "${input_args[@]}" || exit 1

# --- next steps ---
echo "============================================================"
echo "[prepare] done for M$MODEL_ID"
echo "  next: bash compile.sh            # one-time build (skip if GEsession_test_acl exists)"
echo "        bash run.sh $MODEL_ID"
echo "        bash run.sh $MODEL_ID --verify"
echo "============================================================"