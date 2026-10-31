#!/usr/bin/env python3
"""GE_SESSION_DEMO toolchain common module.

Provides: path resolution, dtype mapping, onnx loading, JSON I/O.
All tools use GE_SESSION_DEMO/ as root by default; override with GE_DEMO_ROOT.
"""

import json
import os
from pathlib import Path

# ============================================================
# Paths
# ============================================================


def demo_root() -> Path:
    """Return the GE_SESSION_DEMO root directory (parent of tools/)."""
    env = os.environ.get("GE_DEMO_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent


def normalize_model_id(model_id: str) -> str:
    """Strip an optional 'M' prefix: 'M<id>' / '<id>' -> '<id>'."""
    s = str(model_id).strip()
    if s[:1] in ("M", "m"):
        s = s[1:]
    return s


def model_dir(model_id: str) -> Path:
    return demo_root() / "models" / ("M" + normalize_model_id(model_id))


def model_file(model_id: str) -> Path:
    return model_dir(model_id) / "model" / "model.onnx"


def input_data_dir(model_id: str) -> Path:
    return model_dir(model_id) / "input_data"


def config_dir(model_id: str) -> Path:
    return model_dir(model_id) / "config"


def output_dir(model_id: str) -> Path:
    return model_dir(model_id) / "output"


def rel_to_root(p: Path) -> str:
    """Return a path string relative to demo_root (for configs, avoiding hardcoded absolute paths)."""
    try:
        return str(Path(p).resolve().relative_to(demo_root()))
    except ValueError:
        return str(p)


# ============================================================
# dtype mapping
# ============================================================

# onnx TensorProto.elem_type -> canonical dtype name
ONNX_TYPE_NAME = {
    1: "float32",
    2: "uint8",
    3: "int8",
    4: "uint16",
    5: "int16",
    6: "int32",
    7: "int64",
    8: "string",
    9: "bool",
    10: "float16",
    11: "float64",
    12: "uint32",
    13: "uint64",
    16: "bfloat16",
}

# ============================================================
# dtype authority table
# ============================================================
# name -> {elem_bytes, numpy, supported, val_key}
# supported=True is the 6 dtypes the framework supports; others are for onnx listing only.
DTYPE_TABLE = {
    "float32": {"elem_bytes": 4, "numpy": "float32", "supported": True,
                "val_key": "float_val"},
    "float16": {"elem_bytes": 2, "numpy": "float16", "supported": True,
                "val_key": "float16_bits"},
    "bfloat16": {"elem_bytes": 2, "numpy": "bfloat16", "supported": True,
                 "val_key": "bfloat16_bits"},
    "int32": {"elem_bytes": 4, "numpy": "int32", "supported": True,
              "val_key": "int32_val"},
    "int64": {"elem_bytes": 8, "numpy": "int64", "supported": True,
              "val_key": "int64_val"},
    "bool": {"elem_bytes": 1, "numpy": "bool", "supported": True,
             "val_key": "bool_val"},
    # below are not supported; kept only for elem_bytes/type name display
    "uint8": {"elem_bytes": 1, "numpy": "uint8", "supported": False},
    "int8": {"elem_bytes": 1, "numpy": "int8", "supported": False},
    "uint16": {"elem_bytes": 2, "numpy": "uint16", "supported": False},
    "int16": {"elem_bytes": 2, "numpy": "int16", "supported": False},
    "uint32": {"elem_bytes": 4, "numpy": "uint32", "supported": False},
    "uint64": {"elem_bytes": 8, "numpy": "uint64", "supported": False},
    "float64": {"elem_bytes": 8, "numpy": "float64", "supported": False},
    "string": {"elem_bytes": 0, "numpy": "str", "supported": False},
}

SUPPORTED_DTYPES = tuple(name for name, spec in DTYPE_TABLE.items() if spec["supported"])


def is_supported_dtype(name: str) -> bool:
    return bool(DTYPE_TABLE.get(name, {}).get("supported", False))


def ensure_supported_dtype(name: str, where: str = "") -> None:
    if not is_supported_dtype(name):
        raise SystemExit(
            f"[ERROR] unsupported dtype '{name}' ({where}). Supported: "
            f"{', '.join(SUPPORTED_DTYPES)}. Please use a supported input/output dtype."
        )


def to_uint16_bits(arr, dtype: str):
    """Convert a float16/bfloat16 array to uint16 bit patterns (lossless)."""
    import numpy as np

    arr = np.ascontiguousarray(arr)
    if dtype == "float16":
        return arr.astype(np.float16, copy=False).view(np.uint16)
    if dtype == "bfloat16":
        if arr.dtype == np.uint16:
            return arr
        # npy written by ml_dtypes may be read as void(<V2>) here; treat it as a bit container
        if arr.dtype.kind == "V" and arr.dtype.itemsize == 2:
            return arr.view(np.uint16)
        try:
            import ml_dtypes
            if arr.dtype == ml_dtypes.bfloat16:
                return arr.view(np.uint16)
        except ImportError:
            pass
        return arr.astype(np.uint16, copy=False)
    raise ValueError(f"to_uint16_bits only supports float16/bfloat16, got {dtype}")


def bits_to_float(bits, dtype: str):
    """Convert uint16 bit patterns to a float32 array (for printing/comparison)."""
    import numpy as np

    b = np.asarray(bits, dtype=np.uint16)
    if dtype == "float16":
        return b.view(np.float16).astype(np.float32)
    if dtype == "bfloat16":
        return (b.astype(np.uint32) << 16).view(np.float32)
    raise ValueError(f"bits_to_float only supports float16/bfloat16, got {dtype}")

def numpy_dtype(name: str):
    """Canonical dtype name -> numpy dtype (bfloat16 uses a uint16 container)."""
    import numpy as np

    if name == "bfloat16":
        return np.dtype("uint16")  # bfloat16 stored in a uint16 container
    return np.dtype(DTYPE_TABLE[name]["numpy"])


# ============================================================
# onnx loading
# ============================================================


def load_onnx(path: Path):
    try:
        import onnx
    except ImportError:
        raise SystemExit("[ERROR] onnx package required: pip install onnx")
    # Read only graph structure and tensor shapes, without loading external weight data.
    # Full loading + shape_inference may return an empty graph for external-data models, and config generation needs no weight values.
    return onnx.load(str(path), load_external_data=False)


def onnx_shape_to_list(shape_proto):
    """onnx ShapeProto -> (dims, symbolic)。

    dim_value>0 -> concrete; dim_param or dim_value<=0 -> -1, with the symbol name kept in symbolic.
    """
    dims, symbolic = [], []
    for d in shape_proto.dim:
        if d.HasField("dim_value") and d.dim_value > 0:
            dims.append(int(d.dim_value))
            symbolic.append(None)
        else:
            dims.append(-1)
            symbolic.append(d.dim_param if d.dim_param else None)
    return dims, symbolic


def build_input_output_info(model, skip_initializers: bool = True):
    """Extract the input/output list from an onnx ModelProto.

    Returns (inputs, outputs); each item has index/name/dtype/elem_bytes/onnx_shape/dynamic_dims/symbolic.
    """
    graph = model.graph
    init_names = {init.name for init in graph.initializer} if skip_initializers else set()

    def one(tp, index):
        dims, symbolic = onnx_shape_to_list(tp.type.tensor_type.shape)
        type_id = tp.type.tensor_type.elem_type
        name = ONNX_TYPE_NAME.get(type_id, "unknown")
        return {
            "index": index,
            "name": tp.name,
            "dtype": name,
            "elem_bytes": DTYPE_TABLE.get(name, {}).get("elem_bytes", 0),
            "onnx_shape": dims,
            "dynamic_dims": [d == -1 for d in dims],
            "symbolic": symbolic,
        }

    inputs = []
    idx = 0
    for inp in graph.input:
        if inp.name in init_names:
            continue
        inputs.append(one(inp, idx))
        idx += 1

    outputs = [one(out, i) for i, out in enumerate(graph.output)]
    return inputs, outputs


# ============================================================
# JSON I/O
# ============================================================


def read_json(path: Path):
    with open(path, "r") as f:
        return json.load(f)


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def check_exists(path: Path, what: str):
    if not Path(path).exists():
        raise SystemExit(f"[ERROR] {what} not found: {path}")


# ============================================================
# Input/output <-> numpy conversion (reused by accuracy verification)
# ============================================================


def inline_entry_to_array(entry):
    """Restore one inline record from batch_list.json as (name, numpy array)."""
    import numpy as np

    dim = [int(d) for d in entry["dim"]]
    if "float_val" in entry:
        arr = np.array(entry["float_val"], dtype=np.float32)
    elif "float16_bits" in entry:
        arr = np.array(entry["float16_bits"], dtype=np.uint16).view(np.float16)
    elif "bfloat16_bits" in entry:
        bits = np.array(entry["bfloat16_bits"], dtype=np.uint16)
        try:
            import ml_dtypes
            arr = bits.view(ml_dtypes.bfloat16)
        except ImportError:  # pragma: no cover
            arr = bits
    elif "int32_val" in entry:
        arr = np.array(entry["int32_val"], dtype=np.int32)
    elif "int64_val" in entry:
        arr = np.array(entry["int64_val"], dtype=np.int64)
    elif "bool_val" in entry:
        arr = np.array(entry["bool_val"], dtype=np.uint8).astype(bool)
    else:
        raise ValueError(f"unrecognized inline input record: {entry.get('ori_name')}")
    return entry["ori_name"], arr.reshape(dim)


def load_batch_list_inputs(model_id):
    """Read M<id>/input_data/batch_list.json and restore as [(name, array)] in order."""
    bl = read_json(input_data_dir(model_id) / "batch_list.json")
    return [inline_entry_to_array(e) for e in bl]


def normalize_for_compare(arr, dtype: str):
    """Normalize arrays of different dtypes to a comparable form (floats unified to float32/float64)."""
    import numpy as np

    if dtype == "float16":
        return np.asarray(arr).astype(np.float16).astype(np.float32)
    if dtype == "bfloat16":
        a = np.asarray(arr)
        if a.dtype == np.uint16:
            return bits_to_float(a, "bfloat16")
        try:
            import ml_dtypes
            if a.dtype == ml_dtypes.bfloat16:
                return bits_to_float(a.view(np.uint16), "bfloat16")
        except ImportError:  # pragma: no cover
            pass
        if a.dtype.kind == "V" and a.dtype.itemsize == 2:
            return bits_to_float(a.view(np.uint16), "bfloat16")
        return a.astype(np.float32)
    return np.asarray(arr)


def bytes_to_array(data: bytes, dtype: str, shape):
    """Raw bytes -> numpy (floats unified to float32 for comparison)."""
    import numpy as np

    n = int(np.prod(shape)) if len(shape) else 1
    shape = list(shape)
    if dtype == "float32":
        return np.frombuffer(data, dtype=np.float32, count=n).reshape(shape)
    if dtype == "int32":
        return np.frombuffer(data, dtype=np.int32, count=n).reshape(shape)
    if dtype == "int64":
        return np.frombuffer(data, dtype=np.int64, count=n).reshape(shape)
    if dtype == "bool":
        return np.frombuffer(data, dtype=np.uint8, count=n).reshape(shape).astype(bool)
    if dtype == "float16":
        bits = np.frombuffer(data, dtype=np.uint16, count=n).reshape(shape)
        return bits.view(np.float16).astype(np.float32)
    if dtype == "bfloat16":
        bits = np.frombuffer(data, dtype=np.uint16, count=n).reshape(shape)
        return bits_to_float(bits, "bfloat16")
    raise ValueError(f"bytes_to_array unsupported dtype: {dtype}")
