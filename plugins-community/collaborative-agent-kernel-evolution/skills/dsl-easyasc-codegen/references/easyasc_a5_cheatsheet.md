# easyasc.a5 cheatsheet

A5 DSL surface. Use when the kernel target is the A5 architecture. **On a 910B host this path is simulator-only** — `OpExec(simulator=True)` is the terminal validation step; `simulator=False` lowering is skipped.

> Parallel surface to `easyasc.a2`, not a compatibility layer. Different instruction families.

## Imports

```python
from easyasc.a5 import *
```

Exports: `@kernel`, `@func`, `@vf`, `@auto_sync`, `Tensor`, `GMTensor`, `DBuff`, `TBuff`, `Var`, `Reg`, `RegList`, `MaskReg`, `OpExec`, `DT`, `Position`, full a5 cube + vec + micro stub library, plus `matmul` and other shortcuts.

## Kernel skeleton (same shape as a2)

```python
@kernel()
def my_kernel(x: GMTensor, y: GMTensor, z: GMTensor, M: Var, N: Var, K: Var):
    l1x = Tensor(DT.half, [M, K], Position.L1)
    l1y = Tensor(DT.half, [N, K], Position.L1)
    l0c = Tensor(DT.float, [M, N], Position.L0C)
    l1x <<= x[:, :]
    l1y <<= y[:, :]
    matmul(l0c, l1x, l1y, m=M, n=N, k=K, is_init=True)
    z[:, :] <<= l0c
    return z
```

## Where a5 differs from a2

### Cube hardware family

- a5 cube is **C310** (`device_type == "950"`, `__DAV_C310__` in `tensorutils.h`)
- a2 cube is C220 (b-series chips)
- Same set of cube primitives at the API surface (`matmul`, `gm_to_l1_nd2nz`, `l1_to_l0`, `mmad`, `l0c_to_gm_nz2nd`, `l0c_to_l1`, `l0c_to_ub`, `set_constant_to_l1`)

### Vec / micro story

a5 emphasizes **micro modules** (`@vf`-decorated UB ops) more than a2 does. Many top-level names that exist in a2 as direct UB vec functions (e.g. `add`, `sub`, `exp`, `log`) are in a5 **micro register operations** instead — the names overlap but the semantics differ. When porting a2 → a5 or reading a5 examples, do not assume same-name = same-thing.

a5 micro categories (from doc_cn/api):
- `a5_micro_cast`
- `a5_micro_compare_select`
- `a5_micro_data_movement`
- `a5_micro_mask_operations`
- `a5_micro_math`

### Vec data movement (a5 exports the full set)

a5 exposes everything: `gm_to_ub`, `gm_to_ub_pad`, `ub_to_gm`, `ub_to_gm_pad`, `ub_to_ub`, `ub_to_l1_nd2nz`, `ub_to_l1_nz`, plus the rest of the `easyasc/stub_functions/vec/datamove.py` API. a2 exports only the **pad** subset (`gm_to_ub_pad`, `ub_to_gm_pad`, `ub_to_ub`).

## Storage positions (same as a2)

`Position.L1`, `Position.L0A`, `Position.L0B`, `Position.L0C`, `Position.UB`. Same NZ packing rules for L1/L0A/L0B; same fixed C0=16 for L0C.

## Data types (same as a2)

`DT.half`, `DT.float`, `DT.bfloat16`, `DT.int8`, `DT.uint8`, `DT.int32`. Plus a5-specific FP8 variants used in some examples: see e.g. `examples_a5/flash_attention.py` (fp8 causal flash attn).

## Buffers, control flow, sync — identical to a2

Same `DBuff`/`TBuff`, same `range()` rewrite, same `if/elif/else` rewrite, same `auto_sync()`, same `bind_cv_mutex` / `bind_vc_mutex` for cross-side handshakes.

## Validation flow on a 910B host

1. Author kernel with `easyasc.a5`.
2. `OpExec(kernel, simulator=True)(...)` — V2 simulator runs cube + vec sides in software.
3. Compare output to PyTorch reference. **This is the last step.** No AscendC lowering, no b.sh/r.sh, no post.
4. `codegen_status.json.next_step` should land at `report-only` (smoke pass) or `human-intervention` (smoke fail after 3 attempts).

## Reference: examples in this skill

- `examples_a5/matmul.py` — `matmul_float_mmad`, the minimal cube-only example
- `examples_a5/chunk_row_cumsum.py` — vec-leaning chunked cumsum
- `examples_a5/flash_attention.py` — fp8 causal flash attention, full cube↔vec fusion
