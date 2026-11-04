# `_meta/isa_matrix` — dav-3510 SIMD vector ISA capability / constraint matrix

> **STATUS: BANKED** (constitution v0.2.3 ratified 2026-06-03). dav-3510 SIMD vector ISA
> capability/constraint matrix; tier 🥈T2/🧾H (static header guard-eval — spot-verify each
> `:line` before load-bearing book use). Derived from the 2026-06-03 verify panel (C) +
> `probes/isa_census/`. Scope = ISA matrix only.


> **`verify_cmd` 中的 `${PROBE_WORKSPACE}`**：各探针记录的 `verify_cmd` 原文写的是探针作者机器上
> 某个家目录下的绝对路径。该路径下的 `build.sh` / `run.sh` / `verify.sh` / `profile_simt.sh` 不随
> 本技能分发，CAKE2 上游亦无这些文件。移植时统一替换为 `${PROBE_WORKSPACE}`，以免把一台机器的
> 路径写进公开仓；这些 `verify_cmd` 是复现方式的记录，不是可直接执行的指令。

## HEAD

```yaml
head_schema: meta-matrix/v1
artifact: _meta/isa_matrix
subject: dav-3510 SIMD vector ISA (AIV) — per-op dtype support + mode/family constraints
tier: [🥈T2, 🧾H]                # static header guard-eval; spot-verify each :line before book use
oracle: "/usr/local/Ascend/cann-9.1.0-beta.1/tools/bisheng_compiler/lib/clang/15.0.5/include/__clang_cce_vector_intrinsics.h"
oracle_lines: 13437
arch_env: "{__NPU_ARCH__ = 3510, every __DAV_*__ undefined}"   # build flag --npu-arch=dav-3510
admissibility: "op/overload is in-census IFF its full enclosing #if evaluates TRUE under arch_env"
c_precedence_note: "&& binds tighter than || — applied to every multi-term guard below"
provenance:
  primary: probes/hw_verify_20260603/verify_C_isa_matrix.md   # adversarial guard-eval, 11 claims
  census:  probes/isa_census/RESULTS.md + isa_args.tsv             # 138 base ops / ~1422 overloads
needs_run_deferred: []            # every cell settleable by static header read; no fresh sim run
dtype_axis: [u8, s8, u16, s16, f16, bf16, u32, s32, f32]   # the 9-column grid axis (FP8/2xVL handled separately)
corrections_vs_HW_INVESTIGATION_§3:                          # C refuted/over-stated these — book MUST absorb
  - "DROP fabricated div mechanism: NO 'SupportType' / 'not supported on current device' static_assert exists (0 hits tree-wide). Int/8-bit div is absent because no overload is instantiated."
  - "REPLACE 'FP8 = load/store/cast/move ONLY' with 'FP8 = no ARITHMETIC' — FP8 has bitwise vand/vor/vxor/vnot + data-reorg vintlv/vdintlv/vsqz."
  - "FP8 cast list: f8e4m3/f8e5m2→f16 REVERSE is gated OUT for 3510 (5088); hif8↔bf16 does NOT exist. Keep only hif8↔f16/f32, f16→fp8 forward, fp8↔f32."
  - "histogram chistv2/dhistv2 is NOT 'dav-3510-specific' — present on 3510, shared with 6 arches; replaces older chist0-3/dhist0-3."
  - "RECONCILE census RESULTS.md:78 — vgatherb IS 3510-active (#define 3039 & 3114 guards include ==3510); only the L210/v300 overload-block (2987-90) is out."
```

Legend — grid cells:
- **✓** = an overload for that (op × dtype) is instantiated under arch_env, cited to its `:line`.
- **✗** = excluded for dav-3510; cited to the **exclusion guard** `:line` (the guard whose `(!=3510)` / missing-`==3510` term drops it), not to a present-dtype line.
- **—** = no overload of that dtype exists for the op on ANY arch (not a dav-3510-specific exclusion).
- **🔧UN** = unsettled this pass → see §8 TODO; never banked as ✓.

All `:line` refer to the oracle header above.

---

## 1 · Per-op dtype-support grid — integer/float binary arithmetic

Axis order: `u8 s8 | u16 s16 | f16 bf16 | u32 s32 | f32`. (8/16/32-bit + f16/bf16/f32.)

| op | u8 | s8 | u16 | s16 | f16 | bf16 | u32 | s32 | f32 | constraint + `:line` (present / **exclusion**) |
|---|---|---|---|---|---|---|---|---|---|---|
| `vadd` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all 9; MERGING macro 7068-7079; bf16 guard 7076-7078 incl 3510. **MODE_MERGING_SRC0-capable** (§3) |
| `vsub` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all 9; `__VF_BINARY_OP` 7156-7167; 8-bit s8/u8 **UNGUARDED** at 7158-7159 (only `#if` in block is bf16 7164-7166) |
| `vmul` | ✗ | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | **no 8-bit**: s8/u8 guard 7181-7184 → false for 3510 (`&&`>`||`). s16/u16 7179-7180; s32 7170; u32 guard 7176; f32/f16 7190-7191 (guard `!=9202`); bf16 7194-7197 |
| `vdiv` | — | — | ✗ | ✗ | ✓ | — | ✗ | ✗ | ✓ | **float-only**: f16 7209 / f32 7210 unguarded. Integer s16/u16/s32/u32 **EXCLUDED** by 7201-7203 `(!=3510)` (comment 7200 "C310 doesn't support integer VDIV"). u8/s8/bf16 = **—**: no `vdiv` overload of those dtypes is instantiated on ANY arch (no exclusion guard to cite) |
| `vmax` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all 9; MERGING macro 7082-7093; bf16 guard 7090-7092 incl 3510. **MODE_MERGING_SRC0-capable** |
| `vmin` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | all 9; MERGING macro 7096-7107; bf16 guard 7104-7106 incl 3510. **MODE_MERGING_SRC0-capable** |
| `vabs` | — | ✓ | — | ✓ | ✓ | — | — | ✓ | ✓ | unary; s8/s16/s32/f16/f32 6867-6871 (no unsigned, no bf16) |
| `vneg` | — | ✓ | — | ✓ | ✓ | — | — | ✓ | ✓ | unary; s8/s16/s32/f16/f32 6894-6898 |
| `vabsdif` | ✗ | ✗ | ✗ | ✗ | ✓ | — | ✗ | ✗ | ✓ | **integer EXCLUDED**: u8/s8/u16/s16/s32 by guard 7212-7214 `(!=3510)`; u32 by a separate positive-list guard 7222-7224 (M300/L300/M310/L310/L311 only, no 3510). **FP-only** f16/f32 7226-7227 (present). bf16 = — (never instantiated) |

**Banked constraints from §1 (confirmed 🥈T2):**
- **`vdiv` is float-only (f16/f32), no 8-bit, no integer.** Mechanism is **absence of overload**, NOT a `SupportType` assert (that text has 0 hits tree-wide — fabricated; see HEAD corrections). 64-bit div → §4.
- **`vmul` has no 8-bit** (s8/u8 dropped at 7181-7184); 16/32-bit integer mul DOES exist (s16/u16/s32/u32). `vmul`'s f32/f16/bf16 come from `__VF_BINARY_OP`, so **no `MODE_MERGING_SRC0`** (§3).
- The grid asymmetry is load-bearing and primary-verified: **`vadd`/`vsub`/`vmax`/`vmin` keep 8-bit; `vmul` and integer-`vdiv`/`vabsdif` do not.** `vsub` shares the `__VF_BINARY_OP` macro with `vmul` yet its 8-bit cells are unguarded (7158-7159) — the 8-bit drop is `vmul`-specific, not a macro property.

---

## 2 · bf16 — arch-gated IN (not excluded)

bf16 is **gated to an arch list that INCLUDES `(__NPU_ARCH__ == 3510)`** → bf16 column above is **✓**, not excluded. Every guard read verbatim:

| op | bf16 instantiation `:line` | guard `:line` (includes `==3510`) |
|---|---|---|
| `vadd` | 7079 | 7076-7078 |
| `vsub` | 7167 | 7164-7166 |
| `vmul` | 7197 | 7194-7196 |
| `vmax` | 7093 | 7090-7092 |
| `vmin` | 7107 | 7104-7106 |
| `vmadd` | 7470 | 7468-7469 (`310R6 \| L510 \| 5102 \| 3510 \| 5161`) |

> **Trap note for the book:** "bf16 is gated" reads like an exclusion. It is the opposite — the gate
> admits 3510. Do not mark bf16 ✗.

---

## 3 · MODE_MERGING_SRC0 — exclusive to add / max / min

`MODE_MERGING_SRC0` is a predication mode (one of `{ZEROING, MERGING, MERGING_SRC0, UNKNOWN}`). On dav-3510 it is **permitted only by `add`, `max`, `min`**; every other binary/scalar op offers `{ZEROING, MERGING, UNKNOWN}` only.

| fact | `:line` |
|---|---|
| Only macro whose `static_assert` allows `MERGING_SRC0` = `__VF_MERGING_BINARY_OP` | def 7034; assert 7039-7042 |
| Instantiated for **`vadd`** / **`vmax`** / **`vmin`** only | 7068-7079 / 7082-7093 / 7096-7107 |
| The `vmul` arm of that macro is **9202-only** → not 3510 | 7111-7113 (block `#if ==9202` at 7109) |
| `__VF_BINARY_OP` (`vsub`/`vmul`/`vdiv`/`vand`/…) assert = `ZEROING\|MERGING\|UNKNOWN` (no `MERGING_SRC0`) | — |
| Apparent counterexample `__VF_VEC_VMULS_MERGING_V920` asserts `MERGING_SRC0` **but** its instantiations are `#if ==9202`-gated; 3510 takes `#else` → plain `__VF_VEC_SCALAR_OP` (8138, assert 8143-8145, **no** `MERGING_SRC0`) | 8172 / 8177-8180 / 8220 / 8138 |
| **V210 forbids ZEROING**: `static_assert(!(MODE_ZEROING && isV210Target()), …)` | 7044-7046 (and 8147-8149 scalar) |

**Banked:** on dav-3510 the `MERGING_SRC0` set = **{vadd, vmax, vmin}**. Only two `MERGING_SRC0` asserts exist in the file (7042, 8180); the 8180/`vmuls` path is 9202-only → airtight.

---

## 4 · 2xVL B64 (s64/u64) — a SEPARATE ISA family, not dtype variants

64-bit element ops are **their own `__VF_*_B64` macro family** on `vector_2xvl_{s64,u64}` — NOT an `s64/u64` arm of the 32-bit op. **No floating-point 2xVL form exists.**

| B64 macro | `#define :line` | op | note |
|---|---|---|---|
| `__VF_VDIV_B64` / `__VF_VDIV_U64` | 11573 / 11772 | `vdiv` s64 (11755) / u64 (11940) | the only div for non-float dtypes |
| `__VF_BINARY_OP_B64` | — | `vadd` 10946-47 / `vsub` 10948-49 | s64/u64 (s32/u32 widen-src) |
| `__VF_VMUL_B64` | 10989 | `vmul` 10989-90 | |
| `__VF_MIN_MAX_B64` | — | `vmax` 11160-61 / `vmin` 11162-63 | |
| `__VF_VABS_B64` / `__VF_VNEG_B64` | 11241 / 11121 | `vabs` / `vneg` | |
| `__VF_VLOGIC_B64` | — | `vand`/`vor`/`vxor` 10859-64 | |
| `__VF_VSHL_B64` / `__VF_VSHR_B64` / `__VF_VSHLS_B64` | 9882 / 9904 / 9960 | shifts | |
| `__VF_VLDS_B64` / `__VF_VSTS_B64` / `__VF_VLOAD_B64` / `__VF_VSTORE_B64` | 10574 / 10604(→10619) / 12451 / 12532 | load/store | |
| `__VF_VGATHER2_B64` / `__VF_VSCATTER_B64` | 10588 / 10623 | gather/scatter | |
| `__VF_VBR_B64` / `__VF_VDUP_B64` / `__VF_VMOV_B64` / `__VF_VCI`(2xvl) | 10640 / 10651(→10687) / 10734 / 10895 | broadcast/move | |
| `__VF_VCMP_B64` / `__VF_VCMPS_B64` | — | compare 11005-11073 | |
| `__VF_VCADD_B64` / `__VF_VCMAX_MIN_B64` | — | reduce 12354-55 / 12376-79 | s64/u64 only |

**Banked:** the whole B64 block from 10574 onward sits under a 3510-inclusive guard at **10571-10573** → 3510-active. Each B64 op is its own `#define`, confirmed distinct from the 32-bit path. No `f16/f32/bf16` `_B64` define exists anywhere (negative over the grepped set).

---

## 5 · FP8 (e4m3 / e5m2 / hif8 / e8m0) — NO arithmetic; logical + reorg + cast only

> **⚠ This section is the load-bearing correction of HW_INVESTIGATION §3.** The §3 phrasing
> "FP8 = load/store/cast/move ONLY" is **REFUTED** and is NOT banked. The banked constraint is
> **"FP8 has no ARITHMETIC"**.

**5a — no FP8 arithmetic (confirmed 🥈T2):** grep of `e4m3/e5m2/hif8/e8m0` against
`vadd/vsub/vmul/vdiv/vmax/vmin/vmadd/vmula/vaxpy/vfma/vrelu/vexp/vln/vsqrt` = **no arithmetic hits**.

**5b — what FP8 CAN do on dav-3510 (refutes "cast-only"):**

| FP8 capability | dtypes | `:line` (guard incl 3510) | census xref |
|---|---|---|---|
| bitwise `vand` / `vor` / `vxor` | f8e4m3, f8e5m2, f8e8m0 | 7308-7316 (guard 7302-7304) | tsv 149/153/155 |
| bitwise `vnot` | f8e4m3, f8e5m2, f8e8m0 | 6929-6931 | tsv 151 |
| data-reorg `vintlv` / `vdintlv` | f8e4m3, f8e5m2, f8e8m0 | 670-672 / 700-713 | tsv 205/203 |
| data-reorg `vsqz` | hif8, f8e4m3, f8e5m2, f8e8m0 | 7695-7698 (guard 7692-7694) | tsv 208 |
| load/store/move/broadcast/select | f8e4m3, f8e5m2, f8e8m0 | `vld`/`vst`/`vmov`/`vbr`/`vdup`/`vsel`/`vgatherb`/`vscatter` carry FP8 | tsv 57/62/63/126/128/133/194/215 |

**5c — FP8 cast support (precise; two §3 errors corrected):**

| cast | direction | dav-3510 status | `:line` |
|---|---|---|---|
| `hif8 ↔ f16` | both | ✓ | 5085 (guard 5082-5084 incl 3510) |
| `hif8 ↔ f32` | both | ✓ | 5239 (unguarded) |
| `f16 → f8e4m3 / f8e5m2` | forward | ✓ | 4816 / 4826 (guard 4807-4809 incl 3510) |
| `f8e4m3 / f8e5m2 ↔ f32` | both | ✓ | 5240-5241 (unguarded) |
| `f8e4m3 / f8e5m2 → f16` | **reverse** | **✗ GATED OUT** | 5088 guard = `L510 \| 5102 \| 5161` (no 3510) → 5089-5090 inactive |
| `hif8 ↔ bf16` | — | **— DOES NOT EXIST** | grep `hif8`+`bf16` = 0 hits |

**Banked:** FP8 has **no arithmetic**; it has bitwise-logical, data-reorg, load/store/move/cast.
Cast list = `{hif8↔f16, hif8↔f32, f16→fp8 forward, fp8↔f32}`. **Do NOT** bank
"e4m3/e5m2↔f16 bidirectional" (reverse is gated out) or "hif8↔bf16" (does not exist).

---

## 6 · Reduce family (vcadd / vcmax / vcmin / vcgadd / vcgmax / vcgmin / vcpadd)

| op | dav-3510 dtypes | `:line` | note |
|---|---|---|---|
| `vcadd` | s32, u32, f16, f32 | active set 7542-7547 (guard 7541 `!=9201 && !=9202`) | s8/u8 **EXCLUDED** 7535-7537 (`!=3510`). B64 s64/u64 12354-55 |
| `vcmax` | s16, s32, u16, u32, f16, f32 | active 7590-7595 (guard 7589 `!=9201 && !=9202`) | **s8/u8 EXCLUDED** for 3510 (guard 7583-7585 `(!=3510)`, bodies 7586-7587). B64 12376-77 |
| `vcmin` | s16, s32, u16, u32, f16, f32 | active 7603-7608 | **s8/u8 EXCLUDED** for 3510 (guard 7597-7599 `(!=3510)`, bodies 7600-7601). B64 12378-79 |
| `vcgadd` | f16, f32 (+ u16/s16→u32/s32 widen) | 8432-8439 / expand 8457-58 | group reduce |
| `vcgmax` | f16, f32 | 8435-8466 | group reduce |
| `vcgmin` | f16, f32 | 8438-8471 | group reduce |
| `vcpadd` | f16, f32 | 8441-8442 | pairwise |

**Banked nuances:**
- `vcadd` listed "s16/u16" are **widening *source* types** (s16-src→s32-dst at 7542; u16-src→u32-dst at 7544), **not** standalone s16/u16-dst reduces.
- `vcmax`/`vcmin` **s8/u8 are EXCLUDED** for dav-3510 — this **resolves** the verify_C still_UN: guards 7583-7585 / 7597-7599 each carry `(__NPU_ARCH__ != 3510)`. Active = {s16,s32,u16,u32,f16,f32}.
- `vcmax`/`vcmin` **output semantic ("broadcast")** → **🔧UN, NOT banked** (see §8).

---

## 7 · Fused ops, activations, data-reorg, gather/scatter, histogram

### 7a · Fused single-instruction ops

| op | dav-3510 dtypes | `:line` | note |
|---|---|---|---|
| `vmadd` (FMA) | f16, f32, bf16 | 7465-7466 (+bf16 7470) | guard 7464 `!=9201 && !=9202` |
| `vmula` | s32, s16, u16, u32 (integer) | 7441-7445 (+u32 7452, +bf16 7462) | **FP f32/f16/bf16 DELEGATES to `vfma`** (body 10367; def 10372-74; comment 10371) → "single-instr" true only for integer `vmula` |
| `vaxpy` | f32, f16 | 8038-8039 (unguarded) | |
| `vfma` / `vfms` / `vfnma` / `vfnms` | f16, bf16, f32 each | 10399-10401 / 10403-05 / 10407-09 / 10411-13 (`__VF_MAS_OP`, no enclosing `#if`) | |
| `vexpdif` | f16, f32 (+ f32/f32, f16/f16, bf16/bf16) | 5847 / 5852 / 5856 / 5859 (def 5832) | |

> Distinct from the c_api L2 composites (`AddRelu`, `FusedMulAdd`, `MulAddDst`, …) which lower to
> **multiple** intrinsics (census RESULTS.md §6) — those are not single-instruction.

### 7b · Activations (unary)

| op | dav-3510 dtypes | `:line` |
|---|---|---|
| `vrelu` | f16, f32, **s32** | 6873-6875 |
| `vexp` | f16, f32 | 6877-6878 |
| `vsqrt` | f16, f32 | 6880-6881 |
| `vln` | f16, f32 | 6891-6892 (also alt high-precision `__VF_LN_VEXP_OP` 10495-10498) |
| `vlrelu` | f32, f16 | 8249-8250 |
| `vprelu` | f16, f32 | 7267-7268 |

> All unguarded in their neighborhood; the only nearby `#if` (6883-6889) brackets `vrsqrt`/`vrec`
> (directly verified — NOT `vsqrt`/`vln`). `vrelu`'s `+s32` is exactly as cited.

### 7c · Data-reorg / move / select

| op | `:line` | note |
|---|---|---|
| `vintlv` / `vdintlv` | 663-676 / 697-709 | incl. FP8/bf16/s64/u64 |
| `vpack` / `vunpack` | 6771-6774 / 6795-6798 | |
| `vsqz` (compact-by-mask) | 7680+ (FP8 7695-7698; int 7701-7707) | |
| `vbr` / `vdup` / `vmov` / `vci` | 9793-9807 / 6704-6724 / 6424-6438 / 7902-7922 | broadcast/move (B64 variants → §4) |
| `vsel` / `vselr` / `vselrv2` | 6358-6375 / 6561-6579 / 6597-6600 | |
| `vslide` | predicate `pslide` 8516-8518 | (vector slide via predicate family) |

### 7d · Gather / scatter — **vgatherb 3510-ACTIVE (census reconcile)**

| op | dav-3510 status | `:line` |
|---|---|---|
| `vgatherb` | **✓ ACTIVE** | `#define` 3039 (guard 3033-3040 incl `==3510`) **and** `#define` 3114; first block `#define` 2991 (guard 2987-2990, **no 3510**) is the only inactive one |
| `vgather2` / `vgather2_bc` | ✓ | 3166+ (guard 3142-3147 incl 3510) / 3253-3262 |
| `vscatter` | ✓ | 2845-2866 (defs 2818/2839) |

> **Census reconcile (task-required):** `probes/isa_census/RESULTS.md:78` lumps `vgatherb` into the
> 153 excluded rows. That is at the **overload** granularity — only the **L210/v300 overload block**
> (`#define` 2991, guard 2987-2990) is out; the **op `vgatherb` IS present** for dav-3510 via the
> 3039 & 3114 blocks (guards include `==3510`). Verify_C Claim 10 confirms. The book must treat
> `vgatherb` as a dav-3510 op.

### 7e · Histogram — present on 3510, NOT 3510-exclusive

| op | signature | `:line` | note |
|---|---|---|---|
| `chistv2` | `vector_u16 &dst, vector_u8 src, …` (**u8 → u16**) | 7870 | guard 7842-7847 incl `==3510` |
| `dhistv2` | `vector_u16 &dst, vector_u8 src, …` (**u8 → u16**) | 7852 | same guard |

> **Banked nuance:** "dav-3510-specific" (§3 phrasing) **over-states** — the same guard also admits
> 310R6/L510/5102/9201/9202/5161. Correct framing: **`chistv2`/`dhistv2` are present on dav-3510,
> replacing the older numbered `chist0-3`/`dhist0-3`** (those are guarded away from 3510). u8→u16 is exact.

---

## 8 · TODO — still_UN (NOT banked; never marked ✓)

| item | why UN | settle by |
|---|---|---|
| `vcmax` / `vcmin` **output semantic = "broadcast"?** | `__VF_VCMAX_MIN` body (7554+) does a horizontal compare-reduce with a `pge_##PTYPE(PAT_VL2)` / `vmov_m` merge tail (7569-7571); whether the result is **broadcast across lanes** vs a **single-lane scalar** is not unambiguous from the macro alone | read the underlying `__builtin_cce_*` spec, or a 1-op trace of `vcmax`; **do NOT inherit "broadcast" verbatim** into the book |

> Resolved this pass (no longer UN): `vcmax`/`vcmin` **s8/u8** active status — **EXCLUDED** for 3510
> (guards 7583-7585 / 7597-7599 carry `(!=3510)`), now banked in §6.

---

## 9 · EXCLUDED from dav-3510 (3510-negated guards) — confirmed 🥈T2

| excluded | exclusion guard `:line` | note |
|---|---|---|
| `vbcnt` | 6900-6902 (`… && (__NPU_ARCH__ != 3510) && …`) | bit-count; bodies 6903-6908 |
| `vcls` | 6900-6902 (same guard) | count-leading-sign; bodies 6910-6915 |
| integer `vdiv` (s16/u16/s32/u32) | 7201-7203 (`(!=3510)`) | float `vdiv` f16/f32 stays (§1) |
| integer `vabsdif` (u8/s8/u16/s16/s32) | 7212-7214 (`(!=3510)`) | FP `vabsdif` f16/f32 stays (7226-7227) |
| `vdivf` | 7229-7230 (`(!=3510)`) | the `u16` divf overload at 7231 dropped |
| 9202-only **merging `vmul`** | 7109 block `#if ==9202` (bodies 7111-7113) | dav-3510 gets `vmul` from `__VF_BINARY_OP` instead (§1, §3) |

> Also note (census §"Surprises"): **`v4dtrans` / `vtranspose` do NOT exist** as SIMD intrinsics
> (absent from the vector header); transpose lives only at the c_api L2 layer and does not lower to a
> vector-ISA op on dav-3510. (Out of scope for the dtype grid; recorded so the book does not invent it.)

---

## 10 · Reconciliation ledger (census ↔ verify_C, as required by the task)

| topic | census says | verify_C / this file | resolution |
|---|---|---|---|
| `vgatherb` for 3510 | excluded (RESULTS.md:78, in the 153) | **active** (#define 3039 & 3114 incl 3510) | **active** — census exclusion was overload-granular (L210/v300 block only). §7d. |
| div mechanism | (census silent on "SupportType") | §3 phrasing's `SupportType` assert = **0 hits** | mechanism **fabricated** → dropped; constraint (float-only) kept via absence-of-overload. §1. |
| FP8 scope | logical/reorg/cast FP8 forms exist (tsv 149-208) | §3 "cast-only" **refuted** | bank **"no arithmetic"**, not "cast-only". §5. |
| histogram scope | guard shared with 6 arches | §3 "dav-3510-specific" over-stated | "present on 3510, replaces chist0-3/dhist0-3". §7e. |
| `vmul` MERGING | dav-3510 vmul from `__VF_BINARY_OP`, 9202 path is merging | same | no `MERGING_SRC0` for `vmul`. §3. |
| `vmula` FP | TERNARY_OP rows incl f32/f16/bf16 (tsv 38) | FP arm **delegates to vfma** (10367) | "single-instr" only for integer `vmula`. §7a. |

---

### Tier summary
- All grid cells, mode constraints, family memberships, and exclusions: **🥈T2** (static header guard-eval at a cited `:line`) — spot-verify each `:line` before book use, per house rule.
- `vcmax`/`vcmin` "broadcast" output semantic: **🔧UN** (§8).
- No item is `needs_run_deferred`: every cell is settleable by a static header read (verify_C Claim-set; no fresh simulation required).
