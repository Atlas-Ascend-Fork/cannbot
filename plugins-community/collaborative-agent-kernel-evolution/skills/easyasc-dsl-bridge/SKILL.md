---
name: easyasc-dsl-bridge
disable-model-invocation: true
description: 'Generate the torch_npu pybind cpp and ModelNew Python wrapper that wire an easyasc-codegen kernel into CAKE evaluation. Uses easyasc-style EXECOP dispatch instead of CAKE''s stock pytorch_npu_helper.hpp::EXEC_NPU_CMD, which throws aicore exception 507015 on these kernels. Runs as stage 6, after easyasc-codegen, deriving parameter ordering from the autogen aclnn header.'
---

## What I do

I read the easyasc DSL file (`{op_name}_dsl.py`), the operator description (`{op_name}_op_desc.json`), AND the autogen aclnn header at `output/{op_name}/easyasc_workspace/{op_name}_raw/build_out/autogen/aclnn_{snake}_custom.h`, then produce two artifacts that wire the kernel to PyTorch:

1. `output/{op_name}/{op_name}.cpp` — pybind cpp using easyasc-style EXECOP dispatch (bypasses CAKE's `pytorch_npu_helper.hpp::EXEC_NPU_CMD`)
2. `output/{op_name}/{op_name}_custom.py` — ModelNew Python wrapper (a passthrough skeleton; needs manual edit if Model has `nn.Parameter` members)

Without these, `ascendc-evaluation` fails on real device with `aicore exception, runtime result = 507015` even though the kernel binary itself is correct, and there is no Python wrapper for the eval harness to load.

Parameter ordering comes entirely from the aclnn header (see [How the aclnn header is used as ground truth](#how-the-aclnn-header-is-used-as-ground-truth)); the DSL AST is used only for input/output classification, Var → dim-alias mapping, output-shape inference, and dtype-cast detection.

## When to invoke

Triggered as **stage 6** of the cake agent workflow (v2.1), AFTER `easyasc-codegen` (stage 5) and before `ascendc-evaluation` (stage 7). The cpp produced here will be:
- Compiled by `generate_pybind.py` during stage 7 (`ascendc-evaluation`)
- Linked at runtime against `libcust_opapi.so` (provided by stage 5's installed `.run`) and `libnnopbase.so` (CANN runtime)

May also be re-run any time the DSL signature OR the aclnn header changes (added a Var, renamed inputs, etc.) — it overwrites `{op_name}.cpp` from scratch. ModelNew is **preserved** if it already exists (so manual nn.Parameter edits survive re-runs).

## Inputs

- `op_name` — the operator name (e.g. `dynamic_quant`)
- `output/{op_name}/{op_name}_dsl.py` — must contain a top-level `@kernel()`-decorated function named `{op_name}_custom`
- `output/{op_name}/{op_name}_op_desc.json` — must have `shape_info.input_shapes[].dtype` and `shape_info.output_shapes[].dtype` (and `.name` for sanity-checking against DSL params). Optionally `shape_info.output_shapes[i].shape_expr` for ops whose output shape can't be inferred from input shapes alone (see Pattern 5 below).
- `output/{op_name}/easyasc_workspace/{op_name}_raw/build_out/autogen/aclnn_{snake}_custom.h` — **must exist**. Produced by `easyasc-codegen --build` (stage 5). If missing, this skill exits non-zero with code 3 — there is no AST-based fallback, by design (the entire reason this skill runs after codegen is to use the header as ground truth).

## Outputs

- `output/{op_name}/{op_name}.cpp` — EXECOP-style pybind. Self-contained: no headers required outside torch_npu's bundled `third_party/acl/inc`. Overwritten on every run.
- `output/{op_name}/{op_name}_custom.py` — ModelNew Python wrapper. **Only written if not present** (preserves manual edits to add nn.Parameter mirroring). Skeleton is a passthrough that calls `custom_ops_lib.{op_name}_custom(*inputs)`.

Also `mkdir -p`s `{op_name}Custom/build_out/` idempotently for standalone runs (the link target itself is owned by `easyasc-codegen`, which produces the `.run`).

The file is structured as:
```
#include <torch/extension.h>
#include <torch_npu/csrc/core/npu/NPUStream.h>
#include <torch_npu/csrc/core/npu/NPUGuard.h>
#include "acl/acl.h"
#include <dlfcn.h>, <mutex>, <vector>, <iostream>

extern "C" forward decls of aclTensor / aclOpExecutor / aclnnStatus

namespace {
  // function-pointer typedefs for GetWorkspace, Exec, aclCreateTensor, aclDestroyTensor
  // std::once_flag-guarded loader that dlopen()s libcust_opapi.so + libnnopbase.so
  //   and dlsym()s aclnn{Camel}Custom + aclnn{Camel}CustomGetWorkspaceSize
  // CHECK_ACL macro
  // toAclTensor helper (uses dlsym'd aclCreateTensor)
}

std::tuple<at::Tensor, ...> {op_name}_custom_impl_npu(args...) {
  std::call_once(g_dl_once, load_aclnn_symbols);

  // shape inference for output tensors (from op_desc.json)
  // scalar inference (M = numel/last_dim, N = last_dim, etc.)
  // device guard + current torch_npu stream

  // EXECOP sequence:
  uint64_t workspace_size = 0;
  aclOpExecutor *executor = nullptr;
  void *workspace_addr = nullptr;
  int ws_ret = g_get_ws(...inputs..., ...scalars..., ...outputs..., &workspace_size, &executor);
  TORCH_CHECK(ws_ret == 0, ...);
  if (workspace_size > 0) CHECK_ACL(aclrtMalloc(&workspace_addr, ws_size, ACL_MEM_MALLOC_HUGE_FIRST));
  int run_ret = g_exec(workspace_addr, workspace_size, executor, acl_stream);
  TORCH_CHECK(run_ret == 0, ...);
  CHECK_ACL(aclrtSynchronizeStream(acl_stream));
  if (workspace_size > 0) CHECK_ACL(aclrtFree(workspace_addr));

  // aclDestroyTensor on each
  return std::make_tuple(outputs...);
}

PYBIND11_MODULE(TORCH_EXTENSION_NAME, m) {
  m.def("{op_name}_custom", &{op_name}_custom_impl_npu, ...);
}
```

## Workflow

1. **Sanity check** that `{op_name}_dsl.py`, `{op_name}_op_desc.json`, AND the aclnn header all exist:
   ```bash
   ls output/{op_name}/{op_name}_dsl.py \
      output/{op_name}/{op_name}_op_desc.json \
      output/{op_name}/easyasc_workspace/{op_name}_raw/build_out/autogen/aclnn_*.h
   ```
   If the header is missing, stage 5 (easyasc-codegen) did not finish — re-run it with `--build` and verify before proceeding here.
2. **Run the generator script**:
   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/gen_bridge.py {op_name} \
       [--work-dir output/{op_name}]
   ```
   This parses the DSL AST + op_desc.json + the aclnn header, then produces the cpp and ModelNew skeleton. cpp overwrites any prior content; ModelNew is preserved if it already exists. The script's stdout reports the resolved call sequence — confirm it matches your mental model of the kernel:
   ```
   call sequence (from header):
     input_tensor   x                const aclTensor *
     input_tensor   residual         const aclTensor *
     input_tensor   weight           const aclTensor *
     scalar         M                int64_t
     scalar         H                int64_t
     output_tensor  y                const aclTensor *
   ```
3. **Validate** the generated files:
   - `{op_name}.cpp` must contain the literal string `aclnn{CamelCase}Custom`.
   - The pybind function name must be `{op_name}_custom`.
   - `{op_name}_custom.py` must be importable: `python -c "import ast; ast.parse(open('output/{op_name}/{op_name}_custom.py').read())"`.
   - Compile-test by running `python3 skills/ascendc-evaluation/scripts/generate_pybind.py {op_name}`. The build must succeed; otherwise re-inspect the DSL signature or extend `gen_bridge.py`.
4. **Edit ModelNew if needed** — the generated skeleton is a passthrough that only handles `forward(*input_tensors)`. If the original `Model` class in `{op_name}_reference.py` has `nn.Parameter` members (weight / bias / scales / etc.), edit `output/{op_name}/{op_name}_custom.py` to mirror them:
   - Copy `Model.__init__`'s parameter declarations into `ModelNew.__init__` verbatim — including any `torch.manual_seed(...)` calls used for deterministic init.
   - Update `forward(...)` to pass those parameters as additional args to `fn(...)`.
   - Update `module_fn(...)` signature to receive them.

   Vars declared in the DSL kernel are typically baked at codegen time and do NOT need to be in `module_fn` — but if your op exposes a runtime Var (e.g. dynamic dim) through the pybind, add it. The bridge script's "call sequence" output tells you which Vars survive into the aclnn signature.
5. **Continue to the next stage** in the cake workflow (`ascendc-evaluation`).

## How the aclnn header is used as ground truth

`gen_bridge.py` parses the autogen header via `parse_aclnn_header()` to get an ordered list of `(param_name, c_type, kind)` tuples (kind ∈ {tensor, scalar, internal}). The trailing `uint64_t *workspaceSize, aclOpExecutor **executor` are stripped — those are handled by the cpp template.

The remaining ordered params are then matched against DSL entities via `build_call_sequence()`:

| Header param kind | Matching strategy (in order) |
|---|---|
| tensor | (a) case-insensitive name match against DSL inputs+outputs; (b) special case `out` → single remaining DSL output; (c) positional fallback with stderr WARN |
| scalar | (a) case-insensitive name match against DSL Vars; (b) positional fallback with stderr WARN |

DSL Vars that don't appear in the header are **silently skipped** — these are codegen-baked (e.g. an `eps` constant that easyasc inlined). The c++ assignment lines and the call arg list both reflect this filtering.

If the header's c_type for a scalar differs from what DSL+op_desc derived (e.g. DSL said `int64_t` but header says `double`), a stderr message is printed and the header's c_type wins.

Exit codes:
- `0` — cpp produced successfully
- `1` — DSL or op_desc file missing
- `2` — DSL parse error or scalar derivation unsupported
- `3` — aclnn header missing (run easyasc-codegen with --build first)
- `4` — aclnn header could not be parsed

## Bridge cpp design — why these specific patterns

The generator hardcodes three design choices, all derived from real failures seen on 910B2:

1. **`std::call_once`-guarded dlopen of `libcust_opapi.so` (RTLD_LAZY | RTLD_GLOBAL)**
   CAKE's stock helper dlopens `libopapi.so` (the system aclnn library) by default and falls back to `libcust_opapi.so` only if `ASCEND_CUSTOM_OPP_PATH` is set at extension-load time. The fallback path has subtly different stream-context handling. By dlopen'ing `libcust_opapi.so` directly, we both (a) sidestep the env-var ordering issue and (b) keep the dispatch path identical to easyasc's own torchplugin (which **is** the reference that works on real device).
2. **`c10_npu::NPUGuard guard(devidx)` before `getCurrentNPUStream(devidx).stream(false)`**
   Without the guard, calling aclnn from a process where torch_npu has multiple devices initialized produces `stream not in current ctx` (rt 107003 → aclnn 361001). The guard sets the ACL device context to match the tensor's device.
3. **`aclrtMalloc(... ACL_MEM_MALLOC_HUGE_FIRST)` for the workspace, freed after explicit `aclrtSynchronizeStream`**
   PyTorch's `at::empty(...kByte)` allocator returns memory from the caching pool, which is not always huge-page aligned. easyasc's macro uses `aclrtMalloc(... HUGE_FIRST)` to match what the kernel expects. Synchronous free after `SynchronizeStream` avoids leaking workspace across calls.

The generator does **not** create a raw `aclrtCreateStream` — that pollutes torch_npu's stream registry and breaks subsequent torch ops in the same process (verified during debugging).

## Supported patterns

The auto-generator handles common operator families. If your DSL doesn't match, the script raises a clear error; you can either fix the DSL or hand-maintain the cpp and skip this stage.

| Aspect | Supported |
|---|---|
| GMTensor inputs | ≥ 1 |
| GMTensor outputs | ≥ 1 (single-output returns `at::Tensor`; multi-output returns `std::tuple<at::Tensor, ...>`) |
| Scalar (Var) parameters | 0 or more, see "Scalar resolution rules" below. Vars not present in the aclnn header are skipped (codegen-baked). |
| Output shape | One of 5 patterns (see below) — covers elementwise, reductions, matmul, batched matmul, plus an explicit `shape_expr` escape hatch. |
| Call ordering | Whatever the aclnn header dictates (no longer constrained to inputs→scalars→outputs). |
| dtypes (tensor) | bfloat16, float16, float32, int8, int32, int64 |
| dtypes (scalar) | int → `int64_t`, float → `double`, bool → `bool` — final c_type comes from header, not DSL |
| Tensor layout | Contiguous ND only |

### Output shape inference patterns

Patterns are checked in order; pattern 5 (explicit `shape_expr`) takes priority over 1–4.

| # | Match condition | Typical operator family |
|---|---|---|
| 1 | `out.shape == in[0].shape` | Elementwise, LayerNorm, RMSNorm, residual fusion |
| 2 | `out.shape == in[0].shape[:-1]` | Per-row reductions, dynamic-quant scale |
| 3 | `out.shape == in[0].shape[:-1] + [in[1].shape[-1]]` | `(M,K)@(K,N)→(M,N)`, `(B,S,K)@(K,N)→(B,S,N)` |
| 4 | `out.shape == in[0].shape[:-2] + [in[0].shape[-2], in[1].shape[-1]]` | Batched matmul / attention `QK^T` |
| 5 | `op_desc.output_shapes[i].shape_expr` field present | Anything that doesn't fit 1–4 |

#### Pattern 5 — `shape_expr` mini-grammar

When the four built-in patterns don't fit, add a `shape_expr` string to the output decl in `op_desc.json`. Grammar (whitespace-insensitive, `+` joins terms; `<idx>`/`<start>`/`<stop>` are ints, may be negative):

```
term := "input<idx>.shape"
      | "input<idx>.shape[<start>:<stop>]"
      | "input<idx>.shape[<k>]"
```

Examples:

```jsonc
{ "name": "y",     "shape_expr": "input0.shape" }                                 // pattern 1
{ "name": "scale", "shape_expr": "input0.shape[:-1]" }                            // pattern 2
{ "name": "y",     "shape_expr": "input0.shape[:-1] + input1.shape[-1:]" }        // matmul
{ "name": "y",     "shape_expr": "input0.shape[:-2] + input0.shape[-2:-1] + input1.shape[-1:]" }
```

### Scalar resolution rules

For each `Var`-annotated parameter in the DSL, in DSL declaration order, the resolver looks up:

1. **Dim aliases** — Var name maps to a runtime expression on the first input tensor:

   | Var name | C++ expression | Type |
   |---|---|---|
   | `M` | `<input>.numel() / <last_dim>` | `int64_t` |
   | `N`, `H`, `D`, `K` | `<input>.size(-1)` | `int64_t` |

   When `M` co-occurs with one of `N/H/D/K`, M's expression reuses the sibling variable (avoids re-walking the shape). If `M` is the only dim Var, it falls back to `<input>.numel() / <input>.size(-1)`.

2. **`op_desc.json["attributes"]` lookup** — any non-dim Var name MUST appear as a key in `attributes`; the value is plumbed into the cpp by **one of four resolution modes** depending on the value's syntax:

   ```json
   "attributes": {
     "eps": 1e-6,                                    // mode A: baked literal
     "qmax": 127,                                    //         (numeric / bool)
     "use_smooth_scales": false,                     //         ↓ default if no marker

     "eps_tunable": "@pybind:1e-6",                  // mode B: runtime pybind arg
                                                     //         caller passes value at every call;
                                                     //         <default> shows up in py signature

     "inv_h": "@f:1.0 / static_cast<double>(H)",     // mode C: host-derived double
                                                     //         computed at call time on host;
                                                     //         can reference earlier-resolved Vars

     "N": "@y.size(-2)"                              // mode D: int64_t from C-expression
                                                     //         used to override dim alias for
                                                     //         multi-input ops (e.g. matmul)
   }
   ```

   Type mapping is by Python type: `bool` → `bool`, `int` → `int64_t`, `float` → `double`.

   **Mode B (`@pybind:<default>`)** is the **fm-easyasc-style runtime path**. The attribute becomes an explicit `double` arg in both the C++ `*_impl_npu` signature and the pybind module def (`py::arg("eps") = <default>`), so `ModelNew`/test_cases can pass per-call values like `1e-3` or `1e-12`. Use this for `eps`, `alpha`, `slope`, `threshold`, etc. that vary per test case.

   **Mode C (`@f:<C-expr>`)** is the **fm-easyasc `inv_h` host-precompute pattern**. The expression is emitted as a local `double` initializer; it can reference any already-resolved Var or input tensor. Saves a `dup+rec` pair inside the device kernel for the common `1/H` reciprocal:

   ```python
   # DSL: kernel signature takes inv_h as Var, kernel body uses muls(sum, sum, inv_h)
   @kernel()
   def rms_norm_custom(x, gamma, y, M: Var, H: Var, eps: Var, inv_h: Var): ...
   ```
   ```json
   // op_desc.json:
   "attributes": {
     "eps":   "@pybind:1e-6",
     "inv_h": "@f:1.0 / static_cast<double>(H)"
   }
   ```
   → cpp emits `int64_t H = x.size(-1); double inv_h = 1.0 / static_cast<double>(H);` (in dependency order — dim_last → pybind → derived → dim_row), saving 2 vec ops + a [TILE_M, 1] UB tile per row tile.

3. **Otherwise → `ValueError`**. The error message tells the user to either add the value to `op_desc.attributes`, or rename to a recognized dim alias, or bake as a Python constant in the kernel body.

#### Examples

| Operator | DSL Vars | op_desc.attributes | Result |
|---|---|---|---|
| `dynamic_quant` | `M, N` | (any) | both auto-derived from input shape |
| `add_rms_norm` (legacy) | `eps, M, H` | `{"eps": 1e-6}` | `H = x.size(-1); double eps = 1e-06; M = x.numel() / H;` — eps baked, no runtime config |
| `rms_norm` (fm-style) | `eps, inv_h, M, H` | `{"eps": "@pybind:1e-6", "inv_h": "@f:1.0/static_cast<double>(H)"}` | eps is a per-call pybind arg; inv_h precomputed on host (no device `dup+rec`); kernel signature: `rms_norm_custom(x, gamma, *, eps=1e-6)` |
| `leaky_relu` | `slope` | `{"slope": "@pybind:0.01"}` | slope per-call configurable; ModelNew can pass any value |
| `softmax_with_temp` | `temperature` | `{"temperature": 1.0}` | baked at 1.0 |
| `cumsum` | `dim` | `{"dim": -1}` | `int64_t dim = -1;` baked |
| `matmul_custom` | `M, N, K` | `{"M": "@x.size(-2)", "N": "@y.size(-2)", "K": "@x.size(-1)"}` | manual override per-tensor dim derivation |
| `unknown_scalar foo` | `foo` | (not present) | ❌ ValueError; user must add to attributes |

#### Output dtype follows input dtype (NOT op_desc dtype)

When DSL keeps fp32 internally but op_desc declares the public dtype as e.g. fp16, the bridge inserts a cast layer. The **output cast destination dtype is `<first_input>.scalar_type()`**, NOT the op_desc-baked dtype. This way the *same* kernel binary serves fp16 / fp32 / bf16 callers: fp32 input → no cast → fp32 output; fp16 input → cast in → kernel computes fp32 → cast back to fp16; etc. The op_desc dtype is used only to pick the kernel's internal dtype.

### When auto-generation fails

`gen_bridge.py` exits non-zero with a precise reason. Allowed responses:

1. **Fix the DSL** — restructure the DSL to use only supported patterns (most common: bake an awkward scalar as a Python constant).
2. **Add to `op_desc.attributes`** — if the Var represents a tunable attribute, add a default value to `attributes` and re-run.
3. **Hand-write the cpp** once, then in `cake.md` mark stage 5 as `skipped (manual cpp)` for that op. Note in `REVIEW.md` so the next op author can extend `gen_bridge.py`.

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `gen_bridge.py: autogen directory not found` (exit 3) | easyasc-codegen (stage 5) didn't finish building | Re-run `run_codegen.py {op_name} --build`; verify `build_out/autogen/aclnn_*.h` exists before retrying |
| `gen_bridge.py: function aclnn{Op}CustomGetWorkspaceSize not found in <header>` (exit 4) | Kernel name in DSL doesn't match what easyasc-codegen registered | Confirm DSL has `def {op_name}_custom(...)`; sometimes easyasc renames internal capitals — the header is authoritative |
| `gen_bridge.py: header tensor X cannot be matched to any remaining DSL tensor` (exit 4) | Header has more tensors than DSL declared | Either DSL is missing an input/output, or the header dropped a tensor unexpectedly — check whether codegen optimized something away |
| `gen_bridge.py: header scalar X cannot be matched to any remaining DSL Var` (exit 4) | Header expects a runtime scalar that DSL doesn't declare | Add a corresponding `Var` to the DSL kernel signature with the same name |
| `gen_bridge.py: kernel function `{op_name}_custom` not found` (exit 2) | DSL function name doesn't match | Fix DSL — function MUST be named `{op_name}_custom` |
| `gen_bridge.py: scalar derivation not supported` (exit 2) | DSL has Var with name unknown to dim-alias rules AND not in op_desc.attributes | Add value to `op_desc.json` attributes or rename Var to dim alias (M/N/H/D/K) |
| `gen_bridge.py: cannot infer output shape for 'foo'` (exit 2) | The output's shape in `op_desc.json` doesn't match any of the 5 supported patterns | Add `shape_expr` to the output decl in `op_desc.json` (see Pattern 5), or extend `infer_output_shape_expr` in `gen_bridge.py`, or hand-write cpp |
| Compile fails: `aclTensor does not name a type` | Wrong include path | Already handled by the generator's forward-declaration; if you see this, you're using a stale `gen_bridge.py` |
| Runtime `aclnnXxx not in libcust_opapi.so` | The `.run` from stage 5 wasn't installed yet, or `ASCEND_CUSTOM_OPP_PATH` not sourced | `source output/{op_name}/vendors/customize/bin/set_env.bash` before running evaluation |
| Runtime aclnn returns 161001 (PARAM_NULLPTR) | Tensor `.storage().data()` was nullptr — usually means the tensor wasn't moved to NPU | Verify `Model.to(device)` and `inputs.to(device)` precede the call |
| Runtime aclnn returns 361001 (stream not in current ctx) | NPUGuard or device index wrong | Check `input.device().index()` matches the active torch_npu device |
| Runtime aicore exception 507015 (MTE DDR out of range) | Real kernel bug — UB overalloc, mask issue, or out-of-bounds DataCopy | This is **NOT** a bridge issue. Invoke `ascendc-op-debug` per the cake workflow |

## Files

```
skills/easyasc-dsl-bridge/
├── SKILL.md                                 ← this file
├── scripts/
│   └── gen_bridge.py                        ← generator (Python AST + f-string template)
└── tests/
    └── test_shape_infer.py                  ← pytest for the 5 shape patterns + ModelNew skeleton
```

Run tests from the v2 repo root:

```bash
pytest skills/easyasc-dsl-bridge/tests/test_shape_infer.py -v
```
