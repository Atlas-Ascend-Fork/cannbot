# Error recipes

Common failure modes and what to do, distilled from `doc_cn/10_troubleshooting.md` and from how the scripts use `OpExec`.

## Smoke (simulator) failures

### `Ambiguous scalar match for tensor #X dim #Y`
- Cause: two scalar `Var` arguments carry the same integer value at runtime; OpExec cannot infer which one a tensor dim is bound to.
- Fix: pass `shape_bindings` to `OpExec.__call__`. Map each tensor index to a list giving the scalar-arg index per dim (or `None` to skip):
  ```python
  OpExec(k, simulator=True)(x, y, z, m, n, k, shape_bindings={0: [0, 2], 1: [1, 2], 2: [0, 1]})
  ```
- In our skill: edit `make_inputs()` in `{op}_easyasc.py` to also produce a `shape_bindings` dict, or wrap the OpExec call inside the kernel module's `__main__` for ad-hoc testing.

### `Invalid kernel argument order for OpExec`
- Cause: a `GMTensor` parameter appears after a `Var` parameter in the `@kernel` signature.
- Fix: reorder — all `GMTensor` (inputs then outputs) first, all `Var` last.

### Numerical mismatch vs PyTorch reference
- First, check tolerances: matmul on float16 needs `rtol=atol=3e-3` typically (see `examples_a2/matmul.py:82`). Bumping tolerances above that is masking a bug, not fixing it.
- Tile boundary corruption: confirm `Min(begin + TILE, total)` guards on all writes when shape % TILE != 0.
- Wrong `is_init` on `matmul`: first tile must be `is_init=True`, accumulating tiles `is_init=False`.
- Layout mistakes: review `easyasc_a{2,5}_cheatsheet.md` "Storage positions" — vec ops require UB, `Tensor.T` only on L1.
- Mask-aware reductions: `cmax` treats masked source as `-inf`, `cmin` as `+inf`, `cadd` as `0`. Wrong assumption here is a classic flash-attention bug.

### Vec op rejected: "src/dst must be Position.UB"
- Move the operand to UB first via `gm_to_ub_pad` / `ub_to_ub`.

### `@vf` rejected
- Cause: passing a non-UB Tensor or non-scalar input to a `@vf` micro module.
- Fix: stage to UB before the `@vf` call.

### Smoke PASS 但 evaluation 精度失败（pattern=algorithm_error，仅特定 shape 失败）

- **症状**：smoke 通过（用较小的代表性 shape），但 evaluation 中某些 test case 精度失败，
  规律是 `row_len`（或某空间维度）超过 smoke 配置时才失败，其他 shape 均通过。
- **根因**：`Tensor(DT.float, [1, L], Position.UB)` 中的 `L` 是 smoke 时写死的编译时
  常数（如 128）。运行时 `row_len=512` 时，`GM2UBPAD` 试图将 512 个元素加载到只有
  128 个元素空间的 UB buffer，越界写入相邻 buffer，导致后续计算结果错误。
  这类精度失败往往表现为 `algorithm_error` pattern，系统性偏差，且与 shape 强相关。
- **修复**：在 kernel 内增加行内 tile 循环，使用固定的编译时常数 `TILE_L`：
  ```python
  n_tiles = CeilDiv(row_len, TILE_L)
  for r in range(row_start, row_end):
      for t in range(0, n_tiles):
          l_start = Var(t * TILE_L)
          l_end   = Min(l_start + TILE_L, row_len)
          with auto_sync():
              x_ub <<= x_gm[r:r+1, l_start:l_end]
              # ... compute ...
              y_gm[r:r+1, l_start:l_end] <<= y_ub
  ```
  参见 `easyasc_a2_cheatsheet.md` 的"UB Tiling 模板"获取完整可复用代码。
- **预防**：`make_inputs()` 应使用 api_description.md 中最大的维度值（如最大的 `L`），
  而不只用 `shape_info` 里的代表性小 shape。smoke 通过的 shape 不保证其他 shape 安全。

## Reg/micro (a5) simulator quirks

These bite when authoring **reg-based, data-dependent** kernels (gather/sort/mask/compact).
See `reg_micro_cookbook.md` for the patterns and `micro_perf_rules.md` for tuning. The V2
simulator's narrow-integer (UInt16) path is incomplete, so several masked/shift/cast ops on
u16 abort or silently misbehave — work in int16/bf16 reinterpreted views instead.

| Quirk | Symptom | Workaround |
|---|---|---|
| `cast(u8 → u16)` not implemented in sim | `index_put_not_impl_UInt16`, core process aborts | Drop the cast; have host pre-extend u8 → u16 (zero-extend is free) |
| `select` / `vcopy` on **u16** with a mask | same `index_put_not_impl_UInt16` abort | Do the splice in the **bf16 domain** (`select` on bf16 works) |
| `shiftls` on a **u16** reg | `lshift_cpu_not_impl_UInt16` abort | Use an **int16 reg** + `Tensor.reinterpret(DT.int16)` view of the same UB |
| `mul(..., mask=hi64)` on bf16 silently ignored | ~40% of lanes get the wrong value, no error | **Dual-compute + `select`** instead of masked mul (compute both, splice with mask) |
| `ub_to_reg` source not 128-wide | partial-chunk read goes past the tensor (OOB) | Pad UB **and** GM by `+CHUNK`; over-read junk is masked out at store |
| MTE2 row stride not aligned to C0 (32 B for u8) | `gm_to_ub_pad ... need=487 bytes, have=112 bytes` | Host pads the row to a C0 multiple (e.g. `[N,7]` u8 → `[N,16]` u16) |
| `Ambiguous scalar match` with reg/sort kernels | OpExec can't bind a tensor dim to a scalar | provide `shape_bindings` (see `opexec_options.md`); leave padded dims unbound with `None` |

> **General principle**: the V2 simulator's UInt16 path is incomplete. Keep masked/shift work in
> `int16`/`bf16` reinterpreted views, and prefer dual-path + `select` over masked elementwise ops.

### ⚠️ `compare → select` chain silently broken in the SOFTWARE smoke (false negative)

**Symptom**: a data-dependent reg kernel that builds a mask with `compare(...)` and consumes it with
`select(...)` (bitonic sort, set-intersection, stream-compaction, …) **fails the
`OpExec(simulator=True)` software smoke with large/total numerical mismatch — even though the kernel
is actually correct** (passes bit-exact on cannsim / real hardware).

**Root cause (simulator_v2 store mismatch, not your kernel)**: `compare` writes its result mask into
the **register store** (`_set_reg` → `bindings`), but `select` reads the mask via `_get_mask`, which
only consults **`ctx.masks`**. `ctx.masks` still holds the **all-true default** from the `MaskReg`
declaration, so `select` ignores `compare`'s real result and behaves as if the mask were all-true
(always takes the first operand). Verified by tracing `_get_mask` → returns a FOUND **all-true** mask
while `compare` computed the correct predicate elsewhere.

**Tells it apart from a real bug**:
- `update_mask`-built masks DO work with `select` in the smoke (they write to `ctx.masks`). Only
  **`compare`-built** masks are affected.
- `MicroAPI::Compare`/`MicroAPI::Select` in the **generated AscendC are correct** — the defect is
  purely in the easyasc V2 software simulator.

**What to do — do NOT "fix" the kernel**:
1. A software-smoke FAIL on a `compare→select` reg kernel is **not authoritative**. Validate via the
   **cannsim / `msprof op simulator`** path on an A5-sim host (see `a5_simulator.md`) — that is the
   ground truth for a5 reg kernels.
2. If you must keep validating in the software smoke, build the mask via `update_mask` (+ `mask_not`/
   `mask_and`/…) instead of `compare`, **or** blend arithmetically with a static 0/1 pattern
   (`dst = a*pat + b*(1-pat)`) to side-step the broken `compare→select` path.
3. This is an upstream `easyasc` `simulator_v2` defect (compare↔select mask-store mismatch) worth
   reporting; it does not affect codegen/cannsim/hardware.

> **Smoke FAIL ≠ op failure** for a5 compare-mask kernels. cannsim is authoritative.

## Codegen / build failures (a2 only)

### `ERROR: ASCEND_HOME_PATH is not set`
- `b.sh` checks this first. Export it to the directory containing `bin/setenv.bash`.

### `op_build` cannot find shared libs
- `setenv.bash` did not run; verify `ASCEND_HOME_PATH/bin/setenv.bash` exists.

### `python3: import numpy` fails inside b.sh
- CANN bundled `python3` lacks numpy. Set `EASYASC_PYTHON_BIN` to a directory containing a python with numpy (e.g. `<conda_env>/bin`) — this gets prepended to `PATH`.

### r.sh fails to find `cannsim` or libraries
- After build, `vendors/customize/bin/{setenv,set_env}.bash` must source. Check that the previous `b.sh` finished and the install step (`for f in custom_*.run; do bash ./$f --install-path=...`) succeeded.

### Build succeeds but no `.run` package in `<raw>/build_out/`
- `op_build` failed silently; inspect `b.sh.log` for compile errors. Common: a Python-rewritten control-flow construct that emitted invalid IR — search for the kernel function name in the log.

## When to give up the smoke loop

Hard cap: **3 smoke attempts**. If all 3 fail:
- **a2 path** — proceed to `run_codegen.py` anyway. Accuracy/perf tuning shifts to AscendC layer (post + evaluation).
- **a5 path** — stop. Set `next_step="human-intervention"` and surface to user. There is no AscendC fallback on a 910B host for a5 kernels.
