#!/usr/bin/env python3
"""Generate accuracy golden data with CPU onnxruntime.

Usage:
  python3 tools/gen_golden.py <model_id> [--ref-dir DIR]

Outputs:
  M<id>/reference/output_<i>.npy   (one per output; dtype/shape from onnxruntime)
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import common as C  # noqa: E402


def generate(model_id, ref_dir=None):
    model_id = C.normalize_model_id(model_id)
    mf = C.model_file(model_id)
    C.check_exists(mf, "model.onnx")
    batch_list = C.input_data_dir(model_id) / "batch_list.json"
    C.check_exists(batch_list, "batch_list.json (run prepare_input.py first)")

    inputs = C.load_batch_list_inputs(model_id)

    try:
        import onnxruntime as ort
    except ImportError as e:
        raise SystemExit(f"[ERROR] onnxruntime unavailable: {e}")

    try:
        sess = ort.InferenceSession(str(mf), providers=["CPUExecutionProvider"])
    except Exception as e:
        raise SystemExit(f"[ERROR] failed to load model with onnxruntime: {e}")

    feed = {}
    for name, arr in inputs:
        try:
            feed[name] = np.ascontiguousarray(arr)
        except Exception as e:
            raise SystemExit(f"[ERROR] failed to build input '{name}': {e}")

    try:
        outs = sess.run(None, feed)
    except Exception as e:
        raise SystemExit(f"[ERROR] onnxruntime inference failed: {e}")

    ref_dir = Path(ref_dir) if ref_dir else C.model_dir(model_id) / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    for i, o in enumerate(outs):
        np.save(ref_dir / f"output_{i}.npy", o)
    print(f"[gen_golden] generated {len(outs)} golden files -> {ref_dir}")
    return ref_dir


def main():
    ap = argparse.ArgumentParser(description="Generate accuracy golden data with CPU onnxruntime")
    ap.add_argument("model_id")
    ap.add_argument("--ref-dir", default=None, help="golden directory (default M<id>/reference)")
    args = ap.parse_args()
    generate(args.model_id, args.ref_dir)


if __name__ == "__main__":
    main()
