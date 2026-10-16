# Reg-VF kernel skeleton (a5 `@vf` authoring)

The structural methodology for a register-level a5 `@vf` kernel — the "how to start" that
the pattern catalogue (`reg_micro_cookbook.md`) assumes you already know. Production arch35
reg kernels share one skeleton; follow it rather than improvising.

---

## 1. The canonical reg-`@vf` skeleton

Every production reg kernel has the same shape:

1. **Declare all register tensors and masks once, at the top of the VF body** — before any
   loop. Registers are statically allocated by the compiler; allocating inside the loop wastes
   register live-range and can exhaust the VREG file.
2. **Create the master mask once**, then **re-update it each iteration** to the active element
   count (see §2). One mask drives every op in the loop body.
3. **Loop body is always load → compute → store**, all gated by the current mask.

```
@vf()
def kernel_vf(x_ub, y_ub, total_len):
    # ---- declare ALL regs/masks up front (not in the loop) ----
    r_x   = Reg(DT.float)
    r_y   = Reg(DT.float)
    m     = MaskReg()

    one_repeat  = VREG_LANES          # = VREG_SIZE / sizeof(dtype); see §2
    repeat_times = CeilDiv(total_len, one_repeat)

    rem = Var(total_len)
    for i in range(0, repeat_times):
        update_mask(m, rem)           # narrow mask on the tail iteration
        ub_to_reg(r_x, x_ub, ...)     # load (advance the pointer per iter)
        # ---- compute on r_x -> r_y, every op takes mask=m ----
        reg_to_ub(y_ub, r_y, mask=m)  # store
        rem = rem - one_repeat
```

> The same loop body handles full and tail iterations — there is **no separate tail loop**.
> The mask is what makes the last (partial) iteration correct.

---

## 2. Mask-driven tail handling (replaces a tail loop)

- **Lane count is dtype-dependent**: `one_repeat = VREG_SIZE / sizeof(dtype)`. Wider dtypes →
  fewer lanes per register. Compute it from the dtype, never hard-code 64/128.
- `repeat_times = CeilDiv(total_len, one_repeat)`.
- Each iteration: `update_mask(m, remaining)` where `remaining` shrinks by `one_repeat`. On the
  last iteration the mask covers only the leftover lanes; out-of-range lanes are disabled, so no
  OOB read/write and no garbage feeding into reductions.
- **The mask dtype must match the register dtype** of every op it gates. Narrow↔wide transitions
  need an explicit `mask_pack` / `mask_unpack` (mismatched mask width corrupts lanes silently).

---

## 3. Mixed-precision discipline (load narrow → compute fp32 → store narrow)

When I/O is bf16/fp16/int8 but the math needs precision, the recurring discipline is:

1. **Load narrow, widen to fp32 on the way in.** Use the unpack-on-load datamove variants
   (`ub_to_reg_unpack` / `ub_to_reg_unpack4`) or a `LoadDist` that unpacks, then `cast` to fp32.
2. **Compute entirely in fp32 registers** (accumulation, reductions, transcendentals).
3. **Cast back to the narrow dtype and pack on the way out** (`reg_to_ub_pack4`, or a packing
   `StoreDist`).
4. **Pre-declare cast configs per dtype-pair** with `CastConfig` (layout / saturation / round
   mode) and reuse them — don't re-spell cast parameters at each call site. Widening (narrow→fp32)
   needs no saturation; narrowing (fp32→bf16) uses round-to-nearest (`RoundMode.CAST_RINT`).
5. **Promote narrow scalar args to fp32** before using them in fp32 compute (a bf16 scalar fed
   into fp32 math must be converted first).

> All of `LoadDist`/`StoreDist`, `cast`+`CastConfig`/`RoundMode`, and the unpack/pack datamove
> variants are exported by `easyasc.a5` — see `dsl_coverage_and_gaps.md`. Do **not** drop to
> raw AscendC for mixed precision; the DSL already covers it.

---

## 4. Copy ↔ compute ordering

UB is shared between the load/store (MTE) engine and the vector engine. When the VF reads a UB
region that was just written by a copy (or vice-versa), the two pipes must be ordered:

- Inside `auto_sync()` the parser inserts the intra-side handshakes for supported pipe pairs —
  prefer this.
- Where `auto_sync()` doesn't cover it, insert an explicit barrier (`bar_v` / `bar_mte2` /
  `bar_mte3`) or a `setflag`/`waitflag` pair between the producing copy and the consuming compute.
- See `micro_perf_rules.md` for which barriers are redundant (removable) vs required, and for the
  event-id discipline when building a throughput pipeline.

---

## 5. Authoring checklist for a reg-`@vf`

1. Pick the pattern from `reg_micro_cookbook.md`; confirm the micro-op semantics in
   `arch35_micro_reference.md`.
2. Lay out the skeleton (§1): declare regs/masks up front, master mask, load/compute/store loop.
3. Size `one_repeat` from the dtype; drive the tail with `update_mask` (§2).
4. If I/O is narrow, apply the mixed-precision discipline (§3) — fp32 compute, `CastConfig` reuse.
5. If the op is a reduction/normalization/quant, also apply `numerical_precision.md`.
6. Order copy↔compute (§4); then tune with `micro_perf_rules.md`.
