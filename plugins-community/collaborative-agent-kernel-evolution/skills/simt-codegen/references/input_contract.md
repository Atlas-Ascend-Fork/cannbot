# SIMT Codegen Input Contract

This skill consumes two files. In the normal pipeline both are produced upstream;
when invoking the skill standalone you write them yourself.

**Related**: [SKILL.md](../SKILL.md) | [simt_build_and_compile.md](simt_build_and_compile.md)

| File | Required | Produced by |
|---|---|---|
| `{op_name}_functional.py` | yes | upstream analysis stage, or hand-authored |
| `op_desc.json` | yes | upstream analysis stage, or hand-authored |

`op_desc.json` is a **project convention, not a CANN artifact.** msopgen has its own
operator-registration schema (the OpDef IR, templates under
`$ASCEND_HOME_PATH/python/site-packages/msopgen/json_template/`); that IR is emitted
later by Stage 6 and is a different thing. `op_desc.json` describes semantics and
test configuration for *this* skill.

---

## §1 `{op_name}_functional.py`

A PyTorch reference that defines the semantics the kernel must reproduce. Minimum
contract — the compute entry point:

```python
import torch

def module_fn(x: torch.Tensor, indices: torch.Tensor, axis: int) -> torch.Tensor:
    """Functional reference. Semantics the SIMT kernel must match bit-for-bit
    (fp32) or within dtype tolerance (fp16/bf16)."""
    return torch.index_select(x, dim=axis, index=indices)
```

Pipeline-generated files usually also carry a `Model(nn.Module)` wrapper plus
`get_inputs()` / `get_init_inputs()` shape generators. Those are optional for
codegen but useful for the Pass-N test harness.

**Read this file for the operator's *semantics*, not its shapes** — shapes come from
`op_desc.json`. Where the two disagree, `op_desc.json` wins for tiling and
`functional.py` wins for maths.

---

## §2 `op_desc.json`

### Fields

**The canonical example is [`skills/op-desc-generation/references/op_desc_template.json`](../../op-desc-generation/references/op_desc_template.json)**, with two worked
files beside it (`layer_norm_op_desc.json`, `foreach_norm_op_desc.json`). That skill
owns generation; read its template first and treat this section as a SIMT-specific
gloss on it, not a competing definition.

There is deliberately **no JSON Schema** for `op_desc.json`, here or anywhere in
cake — see §4 for why, and for the read pattern to use instead.

| Field | Type | Required | Consumed by |
|---|---|---|---|
| `op_name` | string | yes | output paths, kernel/entry names. Both `snake_case` and `CamelCase` occur in practice |
| `op_type` | string | no | msopgen project name (defaults to `{OpName}Custom`) |
| `description` | string | recommended | Pass 0 analysis; **state the exact variant here** |
| tensor container | object or array | yes | VF signature, tiling fields, launch sizing. Two layouts — see below |
| `attributes` + `attributes_meta[]` | object + array | no | tiling fields; `int[]` attrs trigger msopgen Step 2c |
| `attrs[]` | array | no | older equivalent of `attributes_meta[]` |
| `supported_dtypes[]` | array | recommended | one template instantiation and one `dtypeCode` case each |
| `supported_index_dtypes[]` | array | gather/scatter | `indexDtypeCode` cases |
| `access_pattern` | string | recommended | Pass 0 model selection |
| `simt_model` | `"A"` \| `"B"` \| `"C"` | no | overrides Q1–Q6 model selection |
| `soc_version` | string | no | `--soc` for `gen_project.py`. Use `ascend950`; most real files omit it and the SoC comes from the environment |
| `npu_arch` | string | no | `--npu-arch`; `dav-3510` for A950 |

### Tensor container: two layouts, both valid

Layout A — `shape_info`, what `op-desc-generation` emits and what every
SIMT operator in `operator_examples/` uses:

```json
"shape_info": {
  "input_shapes":  [ { "name": "x", "shape": [64, 512, 128], "dtype": "float16" } ],
  "output_shapes": [ { "name": "output", "shape": [64, 512, 128], "dtype": "float16" } ]
}
```

Layout B — top-level arrays, used by some `output/` directories, with `dtype` as an
array of specializations:

```json
"inputs":  [ { "name": "x", "shape": [6, 100, 48], "dtype": ["float32", "float16"], "format": "ND" } ],
"outputs": [ { "name": "y", "shape": [6, 13, 48],  "dtype": ["float32", "float16"], "format": "ND" } ]
```

Emit Layout A for new work. Accept either when reading. Two further forms exist in
the repo and are handled downstream rather than rejected: `input_shapes` as a
**name-keyed dict** instead of a list (`top_k`), and `input_shapes: null`
(`transpose`, the `foreach_*` fixtures).

Tensor entries:

| Key | Type | Notes |
|---|---|---|
| `name` | string | becomes the VF argument name |
| `shape` | int array | one representative shape; `-1` for a dynamic dim |
| `dtype` | string **or** string array | a single dtype (Layout A) or one specialization per entry (Layout B) — see [`simt_multi_dtype_guide.md`](simt_multi_dtype_guide.md) |
| `format` | string or array | `ND` unless the operator genuinely needs a tiled format. Array form gives one entry per dtype |
| `is_list` | bool | a `Tensor[]` arg is **one** `is_list: true` entry, never unrolled into `x_0`/`x_1` |
| `optional` | bool | upstream schema declares `Tensor?` |
| `layout` | string or null | channel-first etc.; null when irrelevant |
| `output_shape` | string or null | prose note when the output shape is computed, not literal |

Attribute metadata entries (`attributes_meta[]`, or `attrs[]` in older files):

| Key | Type | Notes |
|---|---|---|
| `name` | string | |
| `type` | string | `int`, `float`, `bool`, `str`, `string`, `int64`, `listint`, `int[]` all occur. `int[]`/`listint` require OpDef `.ListInt()` plumbing — msopgen Step 2c |
| `value` / `default` | scalar or array | representative value to tile for |
| `required` | bool | |
| `enum` | array or null | |
| `description` | string | note normalization rules (e.g. negative axis) here |

Accepted `dtype` spellings: `float32`, `float` (msopgen's spelling of float32),
`float16`, `bfloat16`, `int32`, `int64`, `int8`, `uint8`, `bool`.

### Template

```json
{
  "op_name": "Gather",
  "op_type": "GatherCustom",
  "description": "Axis-gather (np.take / index_select / ONNX Gather): out[a,j,c] = x[a,indices[j],c]. NOT torch.gather.",
  "inputs": [
    { "name": "x",       "shape": [6, 100, 48], "dtype": ["float32", "float16", "bfloat16", "int32"], "format": "ND" },
    { "name": "indices", "shape": [13],         "dtype": ["int32", "int64"],                          "format": "ND" }
  ],
  "outputs": [
    { "name": "y",       "shape": [6, 13, 48],  "dtype": ["float32", "float16", "bfloat16", "int32"], "format": "ND" }
  ],
  "attrs": [
    { "name": "axis", "type": "int", "value": 1, "description": "Gather axis, normalized to >=0 on the host." }
  ],
  "access_pattern": "irregular_read_contiguous_write",
  "simt_model": "B",
  "soc_version": "ascend950",
  "npu_arch": "dav-3510"
}
```

The template above is Layout B. For new work prefer Layout A (`shape_info`), matching
[`op_desc_template.json`](../../op-desc-generation/references/op_desc_template.json).

### `access_pattern` values

`elementwise` · `contiguous_read_contiguous_write` · `irregular_read_contiguous_write` ·
`contiguous_read_irregular_write` · `reduction` · `axis_parallel` · `sparse_csr` ·
`transpose_tiled`

These map onto the sections of [`simt_operator_patterns.md`](simt_operator_patterns.md).
Anything not in this list: describe it in `description` and pick the closest.

---

## §3 Writing `op_desc.json` by hand

1. Name the exact operator variant in `description`. For families where several
   operators share a name — gather above all — say which one and which it is *not*.
   The operator name in the schema already specifies the exact variant (parameter names,
   order, and formula disambiguate). Implement exactly what the schema describes.
2. Choose one representative shape per tensor, sized like the real workload. Tiling is
   derived from it, so a toy shape hides launch-sizing bugs.
3. List every dtype the operator must support. Each one costs a template
   instantiation and a `dtypeCode` case, so do not pad the list.
4. Keep `soc_version` at `ascend950` if you set it at all. Stage 6 must pass
   `--soc ascend950` to `gen_project.py`; the `ascend910b` default silently produces
   wrong artifacts.
5. Check the declared output shape against the declared semantics before generating
   anything. For axis-gather, `output.shape` is `x.shape` with `x.shape[axis]`
   replaced by `indices.numel()`; for `torch.gather`/GatherElements it is
   `index.shape`. A file can be perfectly well-formed and still describe the wrong
   operator — that is exactly how gap G5 produced a kernel that compiled, ran, and
   gathered from the wrong addresses.

---

## §4 Reading `op_desc.json` — and why there is no schema

Do not validate `op_desc.json` against a JSON Schema. No skill in cake does, and the
one that owns generation ships a **template plus worked examples** instead. That is
the contract: taught by example, absorbed at the read boundary.

Consumers coalesce across layouts rather than demanding one. The canonical pattern,
from [`aclnn-pack/scripts/pack_aclnn_bundle.py`](../../aclnn-pack/scripts/pack_aclnn_bundle.py):

```python
shape_info = op_desc.get("shape_info") or {}
inputs  = op_desc.get("inputs")  or shape_info.get("input_shapes")  or []
outputs = op_desc.get("outputs") or shape_info.get("output_shapes") or []
attrs   = op_desc.get("attrs")   or op_desc.get("attributes")       or []
```

Its own docstring: *"We support both this nested-under-shape_info form AND the
flatter form (some cake variants emit `inputs`/`outputs` at top level) for
resilience."* It then falls back to a synthetic single tensor rather than failing,
and tolerates entries that are bare strings instead of dicts. The name-keyed-dict
form has a dedicated normalizer (`_normalize_shape_info`), documented with the
operator that forced it (`engram_gate_fusion`, `KeyError: 0`) and why flattening is
order-safe.

**A strict schema was tried here and removed.** Validating every `*op_desc.json` in
the repo against it rejected 64 of ~70 files — all of which had run successfully.
Every rejection was a form the rest of cake deliberately supports. A validator that
fails known-good input is worse than none: it invites someone to "fix" a working
descriptor and break a passing run.

What is worth asserting is semantic, not structural — the shape-vs-semantics check in
§3 step 5. Schemas pass both gather variants; that check does not.
