#!/usr/bin/env python3
"""Read user inputs under M<id>/input_data, normalize them, and generate framework input/output configs.

Usage:
  python3 tools/prepare_input.py <model_id> [--adopt-output-shapes] [--gen-input]

Flow:
  1) Use model_config.json (from model.onnx) as the input definition.
  2) Prefer <name>.npy; otherwise <name>.bin (auto-convert only for fully static onnx inputs).
     With --gen-input, inputs without any data file are auto-generated as <name>.npy.
  3) Compute parser_shape / hint_shape per shape_config.json policy.
  4) Generate M<id>/input_data/batch_list.json (inline JSON).
  5) Generate M<id>/config/io_config.json (read directly by the C++ runtime).
"""

import argparse
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402


# ============================================================
# auto-generated input (--gen-input)
# ============================================================
# Fixed seed, shared by all generated inputs. Edit here if you need a different
# one; intentionally NOT a CLI option so generated data stays reproducible.
GEN_INPUT_SEED = 20240101
# Size used for a dynamic dim other than the batch dim.
# 默认不允许静默填值：必须由 --input-shape / GEN_INPUT_SHAPE 显式给出；
# 仅在显式设置 GEN_INPUT_DYN_DIM 环境变量时才回退到该值（并逐次告警）。
GEN_INPUT_DYN_DIM = 1
# Range of auto-generated integer inputs: [0, GEN_INPUT_INT_MAX).
GEN_INPUT_INT_MAX = 10


# ============================================================
# input loading
# ============================================================


def load_bin(name, inp, model_id):
    """Read <name>.bin as a numpy array. Shape is auto-determined only for fully static onnx inputs.

    Optional escape hatch: input_data/bin_spec.json declares {"<name>":{"dtype","shape"}}.
    """
    bin_path = C.input_data_dir(model_id) / f"{name}.bin"
    dtype = inp["dtype"]
    shape = list(inp["onnx_shape"])

    spec_path = C.input_data_dir(model_id) / "bin_spec.json"
    if spec_path.exists():
        spec = C.read_json(spec_path).get(name)
        if spec:
            dtype = spec.get("dtype", dtype)
            shape = spec.get("shape", shape)

    if any(d == -1 for d in shape):
        raise SystemExit(
            f"[ERROR] input '{name}' only has .bin and its shape has dynamic dims {inp['onnx_shape']}, "
            f"cannot determine the length. Please:\n"
            f"  (a) make the input dims static in model.onnx, or\n"
            f"  (b) provide {name}.npy, or\n"
            f"  (c) write {{\"{name}\": {{\"dtype\":\"{dtype}\",\"shape\":[...]}}}} in {spec_path}."
        )

    C.ensure_supported_dtype(dtype, f"input {name} .bin conversion")
    elem_bytes = C.DTYPE_TABLE[dtype]["elem_bytes"]
    expect = int(np.prod(shape)) * elem_bytes
    actual = bin_path.stat().st_size
    if expect != actual:
        raise SystemExit(
            f"[ERROR] input '{name}' .bin size mismatch: expected {expect} bytes "
            f"(shape={shape}, dtype={dtype}), actual {actual} bytes."
        )

    arr = np.frombuffer(bin_path.read_bytes(), dtype=C.numpy_dtype(dtype)).reshape(shape)
    npy_path = C.input_data_dir(model_id) / f"{name}.npy"
    np.save(npy_path, arr.astype(arr.dtype, copy=False))
    print(f"[prepare_input] .bin -> .npy: {name} shape={shape} dtype={dtype}")
    return arr, dtype


def has_data_file(model_id, name):
    d = C.input_data_dir(model_id)
    return (d / f"{name}.npy").exists() or (d / f"{name}.bin").exists()


def existing_data_files(model_id):
    """List user-provided input data files (.npy/.bin) under input_data/ (batch_list.json excluded)."""
    d = C.input_data_dir(model_id)
    if not d.exists():
        return []
    return sorted([p for p in d.iterdir() if p.suffix in (".npy", ".bin")])


def parse_input_shape_specs(specs):
    """把 ["name=d0,d1,...", ...] 解析为 {name: [d0, d1, ...]}。"""
    parsed = {}
    for spec in specs or []:
        if "=" not in spec:
            raise SystemExit(
                f"[ERROR] --input-shape expects name=d0,d1,... but got {spec!r}")
        name, _, dims = spec.partition("=")
        name = name.strip()
        try:
            values = [int(item) for item in dims.replace("x", ",").split(",") if item.strip()]
        except ValueError:
            raise SystemExit(
                f"[ERROR] --input-shape {spec!r}: dims must be integers, e.g. det_image=1,3,640,640")
        if not name or not values:
            raise SystemExit(f"[ERROR] --input-shape {spec!r}: empty name or dims")
        parsed[name] = values
    return parsed


def generate_input(name, inp, shape_config, rng, explicit_shape=None):
    """Build a random array for input `name` from its onnx dtype/shape.

    Dynamic dims: an explicit shape (--input-shape / GEN_INPUT_SHAPE) takes precedence;
    otherwise axis 0 uses shape_config.batch_size, and any OTHER dynamic dim must be
    given explicitly — silently filling it (old behaviour: 1) produces degenerate data
    such as [1,3,1,1] and an unusable baseline, so it is rejected by default.
    Dims sharing the same symbolic name get the same value so multi-input models stay
    shape-consistent. Returns (arr, dtype, shape).
    """
    dtype = inp["dtype"]
    C.ensure_supported_dtype(dtype, f"generated input {name}")
    onnx_shape = list(inp["onnx_shape"])
    symbolic = list(inp.get("symbolic") or [None] * len(onnx_shape))
    batch = int(shape_config.get("batch_size", 1))

    if explicit_shape is not None:
        if len(explicit_shape) != len(onnx_shape):
            raise SystemExit(
                f"[ERROR] --input-shape {name}: rank {len(explicit_shape)} != onnx rank "
                f"{len(onnx_shape)} (onnx_shape={onnx_shape})")
        shape = [int(v) for v in explicit_shape]
        return _alloc_generated(name, dtype, shape, rng)

    fallback = os.environ.get("GEN_INPUT_DYN_DIM")
    sym_values = {}
    shape = []
    unresolved = []
    for i, d in enumerate(onnx_shape):
        if d != -1:
            shape.append(int(d))
            continue
        sym = symbolic[i] if i < len(symbolic) else None
        if i == 0:
            shape.append(batch)
        elif sym is not None and sym in sym_values:
            shape.append(sym_values[sym])
        elif fallback is not None:
            sym_values[sym] = int(fallback)
            shape.append(int(fallback))
        else:
            unresolved.append(i if sym is None else f"{i}({sym})")
            shape.append(-1)
    if unresolved:
        raise SystemExit(
            f"[ERROR] input '{name}' has dynamic dims {unresolved} besides axis 0; "
            f"onnx_shape={onnx_shape}.\n"
            f"        给出显式形状后重跑，例如：\n"
            f"          python3 tools/prepare_input.py <model_id> --gen-input "
            f"--input-shape \"{name}={','.join('1' if d == -1 else str(d) for d in onnx_shape)}\"\n"
            f"        （或设置环境变量 GEN_INPUT_SHAPE；仅为兼容旧行为可显式设 GEN_INPUT_DYN_DIM=1，但不推荐）")
    return _alloc_generated(name, dtype, shape, rng)


def _alloc_generated(name, dtype, shape, rng):
    """按 dtype 生成随机输入。"""
    if dtype in ("float32", "float16", "bfloat16"):
        arr = rng.standard_normal(shape).astype(np.float32)
        if dtype == "float16":
            arr = arr.astype(np.float16)
        elif dtype == "bfloat16":
            try:
                import ml_dtypes
                arr = arr.astype(ml_dtypes.bfloat16)
            except ImportError:  # pragma: no cover
                arr = (arr.view(np.uint32) >> 16).astype(np.uint16)
    elif dtype in ("int32", "int64"):
        arr = rng.integers(0, GEN_INPUT_INT_MAX, size=shape, dtype=np.int64)
        arr = arr.astype(C.numpy_dtype(dtype))
    elif dtype == "bool":
        arr = rng.integers(0, 2, size=shape, dtype=np.uint8).astype(bool)
    else:  # pragma: no cover - ensure_supported_dtype already blocks this
        raise SystemExit(f"[ERROR] input '{name}' dtype '{dtype}' cannot be auto-generated")
    return arr, dtype, shape


def load_input(name, inp, model_id):
    npy_path = C.input_data_dir(model_id) / f"{name}.npy"
    if npy_path.exists():
        arr = np.load(npy_path)
        actual = str(arr.dtype)
        expected = inp["dtype"]
        C.ensure_supported_dtype(expected, f"input {name}")
        if expected == "bfloat16":
            # accept ml_dtypes.bfloat16, uint16 container, or bf16 read as void(<V2>) here
            is_v2 = (arr.dtype.kind == "V" and arr.dtype.itemsize == 2)
            if actual not in ("uint16", "bfloat16") and not is_v2:
                raise SystemExit(
                    f"[ERROR] input '{name}' is bfloat16; .npy should be ml_dtypes.bfloat16 / uint16 "
                    f"or a 2-byte bit container, got {actual}"
                )
        elif actual != expected:
            raise SystemExit(
                f"[ERROR] input '{name}' dtype mismatch: onnx={expected}, npy={actual}"
            )
        return arr, expected
    bin_path = C.input_data_dir(model_id) / f"{name}.bin"
    if bin_path.exists():
        return load_bin(name, inp, model_id)
    raise SystemExit(
        f"[ERROR] input '{name}' has no data file; expected {npy_path} or "
        f"{C.input_data_dir(model_id) / (name + '.bin')}\n"
        f"        place the input manually. To auto-generate, empty input_data/ (remove all "
        f".npy/.bin) and rerun with --gen-input; all inputs will be generated."
    )


# ============================================================
# shape policy
# ============================================================


def resolve_parser_shape(inp, runtime_shape, shape_config, override_shape=None):
    """Compute the parser shape per shape_config policy.

    override_shape (overrides[name].shape; positive pins a dim, -1 means dynamic) takes priority.
    Returns (parser_shape, is_dynamic_dim_list, pass_input_shape)
    """
    mode = shape_config.get("mode", "all_static")
    dyn_val = int(shape_config.get("default_parser_dynamic_value", -1))
    overrides = shape_config.get("overrides", {})
    name = inp["name"]

    if override_shape is not None:
        if len(override_shape) != len(runtime_shape):
            raise SystemExit(
                f"[ERROR] input '{name}' override.shape length {len(override_shape)} differs from data rank "
                f"{len(runtime_shape)}"
            )
        dynamic = [v == -1 for v in override_shape]
        parser = [dyn_val if dynamic[i] else int(override_shape[i]) for i in range(len(override_shape))]
        return parser, dynamic, True

    if len(inp["onnx_shape"]) != len(runtime_shape):
        raise SystemExit(
            f"[ERROR] input '{name}' .npy rank {runtime_shape} differs from onnx declaration {inp['onnx_shape']}"
        )

    if mode == "all_dynamic":
        # all dynamic: do not pass INPUT_SHAPE to GE; parser_shape is recorded only
        dynamic = [d == -1 for d in inp["onnx_shape"]]
        parser = [dyn_val if dynamic[i] else runtime_shape[i] for i in range(len(runtime_shape))]
        return parser, dynamic, False

    if mode == "all_static":
        dynamic = [False] * len(runtime_shape)
        return list(runtime_shape), dynamic, True

    # custom: override first, otherwise fall back to onnx dynamic dims
    ov = overrides.get(name) or {}
    if "dynamic" in ov:
        dynamic = list(ov["dynamic"])
        if len(dynamic) != len(runtime_shape):
            raise SystemExit(
                f"[ERROR] {name} override.dynamic length {len(dynamic)} differs from rank "
                f"{len(runtime_shape)}"
            )
    else:
        dynamic = [d == -1 for d in inp["onnx_shape"]]
    parser = [dyn_val if dynamic[i] else runtime_shape[i] for i in range(len(runtime_shape))]
    return parser, dynamic, True


def apply_input_override_shape(inp, arr, shape_config):
    """Apply overrides[name].shape: positive pins a dim, -1 means dynamic.

    Only the batch dim (axis 0) set to -1 and differing from batch_size is expanded/tiled or truncated by batch_size;
    other dims must match the actual data. Returns (arr, target_shape, override_shape|None).
    """
    name = inp["name"]
    ov = (shape_config.get("overrides", {}) or {}).get(name) or {}
    if "shape" not in ov:
        return arr, [int(d) for d in arr.shape], None

    ovs = [int(x) for x in ov["shape"]]
    if len(ovs) != arr.ndim:
        raise SystemExit(
            f"[ERROR] input '{name}' override.shape length {len(ovs)} differs from data rank {arr.ndim}"
        )

    target = []
    for i, (v, d) in enumerate(zip(ovs, arr.shape)):
        if v == -1:
            target.append(int(shape_config.get("batch_size", d)) if i == 0 else int(d))
        else:
            target.append(int(v))

    for i in range(1, len(target)):
        if target[i] != arr.shape[i]:
            raise SystemExit(
                f"[ERROR] input '{name}' axis {i} override.shape={target[i]} differs from actual {arr.shape[i]} "
                f"; only the batch dim supports expand/truncate by batch_size"
            )

    if target[0] != arr.shape[0]:
        if ovs[0] != -1:
            raise SystemExit(
                f"[ERROR] input '{name}' axis 0 override.shape={target[0]} differs from actual {arr.shape[0]} "
                f"; set this dim to -1 to expand/truncate by batch_size"
            )
        if target[0] <= 0:
            raise SystemExit(f"[ERROR] input '{name}' target batch={target[0]} is invalid")
        if arr.shape[0] == 0:
            raise SystemExit(f"[ERROR] input '{name}' batch dim is 0, cannot expand")
        if target[0] < arr.shape[0]:
            arr = arr[:target[0]]
        else:
            reps = int(np.ceil(target[0] / arr.shape[0]))
            arr = np.tile(arr, [reps] + [1] * (arr.ndim - 1))[:target[0]]
    return arr, [int(d) for d in arr.shape], ovs


def maybe_expand_batch(inp, arr, shape_config):
    """all_static: make batch_size authoritative for inputs whose onnx axis 0 is dynamic.

    With mode=all_static and a dynamic onnx axis 0, the input data is expanded (tiled) or
    truncated along axis 0 to `batch_size`, so `batch_size=100` yields a static [100, ...]
    graph instead of reusing the .npy batch. Inputs with an explicit overrides[name].shape
    are left to apply_input_override_shape. Other modes are untouched.
    """
    if shape_config.get("mode", "all_static") != "all_static":
        return arr
    onnx_shape = inp.get("onnx_shape") or []
    if not onnx_shape or onnx_shape[0] != -1:
        return arr
    ov = (shape_config.get("overrides") or {}).get(inp["name"]) or {}
    if "shape" in ov:
        return arr
    target = int(shape_config.get("batch_size", 1))
    if target <= 0:
        raise SystemExit(f"[ERROR] input '{inp['name']}' batch_size={target} is invalid")
    if target == int(arr.shape[0]):
        return arr
    if arr.shape[0] == 0:
        raise SystemExit(f"[ERROR] input '{inp['name']}' batch dim is 0, cannot expand")
    if target < arr.shape[0]:
        arr = arr[:target]
    else:
        reps = int(np.ceil(target / arr.shape[0]))
        arr = np.tile(arr, [reps] + [1] * (arr.ndim - 1))[:target]
    print(f"[prepare_input] batch_size={target}: expanded input '{inp['name']}' along axis 0 "
          f"-> {list(arr.shape)}")
    return arr


# ============================================================
# inline batch_list
# ============================================================


def to_inline_entry(name, arr, dtype, shape_config):
    C.ensure_supported_dtype(dtype, f"input {name}")
    elem_bytes = C.DTYPE_TABLE[dtype]["elem_bytes"]
    runtime_shape = list(arr.shape)
    key = C.DTYPE_TABLE[dtype]["val_key"]
    if dtype in ("float16", "bfloat16"):
        # lossless: write uint16 bit patterns
        data = C.to_uint16_bits(arr, dtype).tolist()
    elif dtype == "float32":
        data = arr.astype(np.float32).tolist()
    elif dtype == "int32":
        data = arr.astype(np.int32).tolist()
    elif dtype == "int64":
        data = arr.astype(np.int64).tolist()
    elif dtype == "bool":
        data = arr.astype(np.uint8).tolist()
    else:  # pragma: no cover - ensure_supported_dtype already blocks this
        raise SystemExit(f"[ERROR] input '{name}' dtype '{dtype}' cannot be represented inline")
    return {
        "ori_name": name,
        "dim": runtime_shape,
        "item_feature": 0,
        "size": int(arr.size) * elem_bytes,
        "ori_batch": int(shape_config.get("batch_size", 1)),
        key: data,
    }


# ============================================================
# output config
# ============================================================


def resolve_dims_expr(dims, input_shapes, out_name):
    """Resolve output_overrides.dims expressions: int or {"from_input": name, "dim": i}."""
    resolved = []
    for item in dims:
        if isinstance(item, int):
            resolved.append(int(item))
        elif isinstance(item, dict) and "from_input" in item:
            iname = item["from_input"]
            if iname not in input_shapes:
                raise SystemExit(
                    f"[ERROR] output '{out_name}' dims expression references unknown input '{iname}'"
                )
            s = input_shapes[iname]
            axis = int(item.get("dim", 0))
            try:
                resolved.append(int(s[axis]))
            except IndexError:
                raise SystemExit(
                    f"[ERROR] output '{out_name}' dims reference input '{iname}' axis {axis} out of range"
                )
        else:
            raise SystemExit(
                f"[ERROR] output '{out_name}' dims supports only int or {{\"from_input\",\"dim\"}}, got: {item}"
            )
    return resolved


def resolve_outputs(model_config, shape_config, input_shapes=None, adopted=None):
    overrides = shape_config.get("output_overrides", {})
    input_shapes = input_shapes or {}
    adopted = adopted or {}
    outputs = []
    for out in model_config["outputs"]:
        name = out["name"]
        base_shape = list(out["onnx_shape"])
        shape = list(base_shape)
        dtype = out["dtype"]
        ov = overrides.get(name) or {}
        resolve_src = "onnx_static"

        if "shape" in ov:
            shape = list(ov["shape"])
            resolve_src = "manual_shape"
        elif "dims" in ov:
            shape = resolve_dims_expr(ov["dims"], input_shapes, name)
            resolve_src = "expr_from_input"
        elif name in adopted:
            shape = list(adopted[name])
            resolve_src = "adopt_runtime"

        # conflict check: onnx already resolved a static shape and the manual/probed value differs
        if resolve_src != "onnx_static" and all(d != -1 for d in base_shape):
            if [int(d) for d in shape] != [int(d) for d in base_shape]:
                raise SystemExit(
                    f"[ERROR] output '{name}' conflict: onnx inferred shape={base_shape}, "
                    f"while {resolve_src} gives shape={shape}. Decide explicitly in shape_config.json."
                )

        if "dtype" in ov:
            dtype = ov["dtype"]
        C.ensure_supported_dtype(dtype, f"output {name}")
        elem_bytes = C.DTYPE_TABLE[dtype]["elem_bytes"]

        if resolve_src != "onnx_static" and len(shape) != len(base_shape):
            print(f"[prepare_input][WARN] output '{name}' override shape rank {len(shape)} "
                  f"differs from onnx rank {len(base_shape)}")

        # Dynamic output dims are kept as -1 placeholders: GE decides the actual shape at
        # runtime and dumps it to output/output_shapes.json, which verify.py uses to interpret
        # output_i.bin. No manual output_overrides is required.
        if any(d == -1 for d in shape):
            if resolve_src == "onnx_static":
                resolve_src = "onnx_dynamic"
            size_bytes = None
        else:
            size_bytes = int(np.prod(shape)) * elem_bytes

        outputs.append({
            "index": out["index"],
            "name": name,
            "dtype": dtype,
            "elem_bytes": elem_bytes,
            "shape": [int(d) for d in shape],
            "size_bytes": size_bytes,
            "resolve": resolve_src,
        })
    return outputs


def load_adopted_shapes(model_id):
    """Read the actual output shapes dumped by the C++ runtime (probe backfill)."""
    p = C.output_dir(model_id) / "output_shapes.json"
    if not p.exists():
        return {}
    try:
        data = C.read_json(p)
    except Exception as e:
        print(f"[prepare_input][WARN] failed to read {p}: {e}")
        return {}
    adopted = {}
    for item in data.get("outputs", []):
        name = item.get("name")
        shape = item.get("shape")
        if name and shape:
            adopted[name] = shape
    return adopted


# ============================================================
# main
# ============================================================


def main():
    ap = argparse.ArgumentParser(description="Normalize inputs and generate framework configs")
    ap.add_argument("model_id")
    ap.add_argument("--adopt-output-shapes", action="store_true",
                    help="backfill io_config output shapes from M<id>/output/output_shapes.json")
    ap.add_argument("--gen-input", action="store_true",
                    help="auto-generate <name>.npy for inputs that have no data file "
                         f"(fixed seed GEN_INPUT_SEED={GEN_INPUT_SEED})")
    ap.add_argument("--input-shape", action="append", default=None, metavar="NAME=D0,D1,...",
                    help="explicit shape for a generated input; required when the onnx input has "
                         "dynamic dims other than axis 0 (env: GEN_INPUT_SHAPE, ';'-separated)")
    args = ap.parse_args()

    model_id = C.normalize_model_id(args.model_id)
    C.output_dir(model_id).mkdir(parents=True, exist_ok=True)
    mc_path = C.config_dir(model_id) / "model_config.json"
    sc_path = C.config_dir(model_id) / "shape_config.json"
    C.check_exists(mc_path, "model_config.json (run prepare_model.py first)")
    C.check_exists(sc_path, "shape_config.json (run prepare_model.py first)")

    model_config = C.read_json(mc_path)
    shape_config = C.read_json(sc_path)

    # --gen-input is only allowed on an empty input_data/: never mix provided and generated inputs.
    if args.gen_input:
        existing = existing_data_files(model_id)
        if existing:
            names = ", ".join(p.name for p in existing)
            raise SystemExit(
                f"[ERROR] --gen-input requires an empty input_data/, but found {len(existing)} "
                f"data file(s): {names}\n"
                f"        provide ALL inputs manually, or remove them and rerun with --gen-input.\n"
                f"        mixing provided and auto-generated inputs is not allowed."
            )

    rng = np.random.default_rng(GEN_INPUT_SEED) if args.gen_input else None
    shape_specs = list(args.input_shape or [])
    env_specs = os.environ.get("GEN_INPUT_SHAPE", "")
    if env_specs:
        shape_specs.extend(item for item in env_specs.split(";") if item.strip())
    explicit_shapes = parse_input_shape_specs(shape_specs)
    known_inputs = {item["name"] for item in model_config["inputs"]}
    unknown = sorted(set(explicit_shapes) - known_inputs)
    if unknown:
        raise SystemExit(
            f"[ERROR] --input-shape 指定的输入名不存在：{unknown}；模型输入为 {sorted(known_inputs)}")
    batch_entries = []
    io_inputs = []
    for inp in model_config["inputs"]:
        name = inp["name"]
        if args.gen_input and not has_data_file(model_id, name):
            gen_arr, gen_dtype, gen_shape = generate_input(
                name, inp, shape_config, rng, explicit_shape=explicit_shapes.get(name))
            npy_path = C.input_data_dir(model_id) / f"{name}.npy"
            npy_path.parent.mkdir(parents=True, exist_ok=True)
            np.save(npy_path, gen_arr)
            print(f"[prepare_input] generated input {name} shape={gen_shape} dtype={gen_dtype} "
                  f"seed={GEN_INPUT_SEED} -> {npy_path}")
        arr, dtype = load_input(name, inp, model_id)
        arr = maybe_expand_batch(inp, arr, shape_config)
        arr, runtime_shape, override_shape = apply_input_override_shape(inp, arr, shape_config)
        parser_shape, dynamic, pass_input_shape = resolve_parser_shape(
            inp, runtime_shape, shape_config, override_shape=override_shape)

        batch_entries.append(to_inline_entry(name, arr, dtype, shape_config))
        io_inputs.append({
            "index": inp["index"],
            "name": name,
            "dtype": dtype,
            "elem_bytes": C.DTYPE_TABLE[dtype]["elem_bytes"],
            "runtime_shape": runtime_shape,
            "parser_shape": ",".join(str(d) for d in parser_shape),
            "hint_shape": f"{inp['index']}:[" + ",".join(str(d) for d in runtime_shape) + "]",
            "dynamic_dims": dynamic,
        })
        print(f"[prepare_input] {name:<48} runtime={runtime_shape} parser={parser_shape}")

    input_shapes = {e["name"]: e["runtime_shape"] for e in io_inputs}
    adopted = load_adopted_shapes(model_id) if args.adopt_output_shapes else {}
    if adopted:
        print(f"[prepare_input] probe backfill: using actual output shapes {adopted}")
    outputs = resolve_outputs(model_config, shape_config, input_shapes, adopted)

    batch_list_path = C.input_data_dir(model_id) / "batch_list.json"
    C.write_json(batch_list_path, batch_entries)

    # whether any input needs INPUT_SHAPE (False for all_dynamic)
    pass_input_shape = shape_config.get("mode", "all_static") != "all_dynamic"
    io_config = {
        "model_id": model_id,
        "model_file": model_config["model_file"],
        "framework": model_config.get("framework", "onnx"),
        "batch_size": int(shape_config.get("batch_size", 1)),
        "pass_input_shape": pass_input_shape,
        "shape_mode": shape_config.get("mode", "all_static"),
        "batch_list": C.rel_to_root(batch_list_path),
        "output_dir": C.rel_to_root(C.output_dir(model_id)),
        "inputs": io_inputs,
        "outputs": outputs,
    }
    io_path = C.config_dir(model_id) / "io_config.json"
    C.write_json(io_path, io_config)

    print(f"[prepare_input] generated {batch_list_path}")
    print(f"[prepare_input] generated {io_path}")
    print(f"  pass_input_shape={pass_input_shape} mode={io_config['shape_mode']} "
          f"inputs={len(io_inputs)} outputs={len(outputs)}")


if __name__ == "__main__":
    main()