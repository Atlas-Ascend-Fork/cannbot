#!/usr/bin/env python3
"""Analyze model.onnx and generate the model configuration.

Usage:
  python3 tools/prepare_model.py <model_id> [--mode all_static|all_dynamic|custom]
                                         [--batch-size N] [--force]

Outputs:
  M<id>/config/model_config.json    onnx input/output list (model info for the framework)
  M<id>/config/shape_config.json    default static/dynamic policy (kept if exists unless --force)
"""

import argparse
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))

import common as C  # noqa: E402


def gen_default_shape_config(mode: str, batch_size: int):
    """Generate the default static/dynamic policy.

    - all_static  : pin every input to its real request shape (default, memory bounded).
    - all_dynamic : do not pass INPUT_SHAPE to GE; fully dynamic (workspace may be large).
    - custom      : mark dynamic dims per input via overrides; inputs not listed
                    fall back to the onnx declared dynamic dims.
    """
    return {
        "_help": "mode: all_static|all_dynamic|custom. In custom mode use overrides.dynamic; "
                 "inputs not listed fall back to onnx dynamic dims. output_overrides is a manual fallback for output dims.",
        "mode": mode,
        "batch_size": batch_size,
        "default_parser_dynamic_value": -1,
        "overrides": {},
        "output_overrides": {},
    }


def main():
    ap = argparse.ArgumentParser(description="Analyze model.onnx and generate the model configuration")
    ap.add_argument("model_id", help="model id, e.g. M<id> or <id>")
    ap.add_argument("--mode", default="all_static",
                    choices=["all_static", "all_dynamic", "custom"],
                    help="default static/dynamic policy (default all_static, memory bounded)")
    ap.add_argument("--batch-size", type=int, default=1, help="default batch size")
    ap.add_argument("--force", action="store_true", help="overwrite an existing shape_config.json")
    args = ap.parse_args()

    model_id = C.normalize_model_id(args.model_id)
    mf = C.model_file(model_id)
    C.check_exists(mf, "model.onnx")

    model = C.load_onnx(mf)
    # Run onnx shape inference first to resolve dynamic dims of inputs/outputs
    inferred = False
    try:
        import onnx
        from onnx import shape_inference
        model = shape_inference.infer_shapes(model)
        inferred = True
    except Exception as e:
        print(f"[prepare_model][WARN] onnx shape inference failed (continuing): {e}")
    inputs, outputs = C.build_input_output_info(model)

    unsupported = sorted(
        {t["dtype"] for t in (inputs + outputs) if not C.is_supported_dtype(t["dtype"])}
    )
    if unsupported:
        print(
            f"[prepare_model][WARN] unsupported dtype detected: {', '.join(unsupported)}; "
            f"supported set is {', '.join(C.SUPPORTED_DTYPES)}. prepare_input will fail."
        )

    model_config = {
        "model_id": model_id,
        "model_file": C.rel_to_root(mf),
        "framework": "onnx",
        "graph_name": model.graph.name,
        "ir_version": model.ir_version,
        "producer": model.producer_name,
        "batch_size_default": args.batch_size,
        "inputs": inputs,
        "outputs": outputs,
        "extra": {
            "initializer_count": len(model.graph.initializer),
            "opset": [[o.domain, o.version] for o in model.opset_import],
            "doc_string": model.doc_string or None,
            "shape_inference": inferred,
        },
    }

    mc_path = C.config_dir(model_id) / "model_config.json"
    C.write_json(mc_path, model_config)

    sc_path = C.config_dir(model_id) / "shape_config.json"
    if sc_path.exists() and not args.force:
        print(f"[prepare_model] keeping existing {sc_path} (not overwritten; use --force to rebuild)")
    else:
        C.write_json(sc_path, gen_default_shape_config(args.mode, args.batch_size))
        print(f"[prepare_model] generated {sc_path} (mode={args.mode})")

    print(f"[prepare_model] generated {mc_path}")
    print(f"  inputs : {len(inputs)}")
    print(f"  outputs: {len(outputs)}")
    for o in outputs:
        print(f"    output[{o['index']}] {o['name']} {o['dtype']} shape={o['onnx_shape']} "
              f"dynamic={o['dynamic_dims']}")


if __name__ == "__main__":
    main()
