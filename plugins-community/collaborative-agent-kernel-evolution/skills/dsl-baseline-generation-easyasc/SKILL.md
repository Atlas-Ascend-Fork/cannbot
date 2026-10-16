---
name: dsl-baseline-generation-easyasc
disable-model-invocation: true
description: Generate initial easyasc-DSL code (Python @kernel() with GMTensor/Tensor/Var primitives) from functional PyTorch. Default target is `from easyasc.a2 import *` (ascend910b) — A2 exposes both Vector UB-only primitives AND cube primitives (DBuff/Position.L0C/matmul/GetCubeNum), so both Vector and CV/matmul operators can be authored without switching to A5. Use after functional-conversion in the cake workflow.
---

## What I do

Generate `output/{op_name}/{op_name}_dsl.py` — a Python file using **easyasc DSL** (`@kernel()` decorator, `GMTensor` / `Tensor` / `Var` primitives, `<<=` dataflow operator, `with auto_sync()` blocks). This file is both the **algorithm specification** (read by humans / reviewers) and the **codegen input** (read by `OpExec(simulator=False)` to emit AscendC).

This skill replaces `dsl-baseline-generation` in the cake agent. The downstream `dsl-lowering` skill is **not** used afterwards — easyasc has its own codegen.

**Operator scope**: this skill supports **both** target devices via `target_device` (a2|a5; default a2). On **a2** (`from easyasc.a2 import *`, ascend910b — CAKE's evaluation hardware) it covers both Vector and CV/cube operators:
- **Vector** (Sigmoid, Softmax, LayerNorm, ...): A2 UB-only primitives. End-to-end verified on 910B2.
- **CV / cube** (matmul, batched matmul, attention QK^T, ...): A2 also exposes `DBuff`, `Position.L1`, `Position.L0C`, `matmul()`, `GetCubeNum()`, `GetCubeIdx()`. End-to-end verified on 910B2 with bf16 matmul (5/5 precision pass).

On **a5** (`from easyasc.a5 import *`, ascend950) the surface adds A5-specific features — `@vf` register kernels, cumsum-style scan, `Position.L0A`/`L0B` direct access, fp8 micro-cast. Per the a2/a5 design (mirrors fm-easyasc), the a5 path is **simulator-only / report-only** on non-a5 hosts: stage 5 codegen refuses and validation is the DSL file's `__main__` self-check. **Default to a2** unless the op_desc requests `easyasc-a5` or an A5-only primitive is strictly required.

## Sub-Agent Strategy — three-phase split (brief → write → debug)

This skill reads **large reference files** (easyasc primer, pointers to the upstream `ops-easyasc-dsl` docs) that should not pollute the orchestrator context. It also must not run as ONE long sub-agent: heavy reference reads + an iterative simulator debug loop blow up a single sub-agent's context, and an oversized final message can be dropped (`[Tool result missing due to internal error]`). So the orchestrator splits stage 4 into up to three sub-agents that hand off **via files** and report back only short summaries.

### Stage-4 prelude (orchestrator MUST run before delegating)

Before invoking the sub-agent, the **cake orchestrator** computes a `tiling_classification` triple:

1. **Operator category** — from `op_desc.json["category"]` plus inspection of `module_fn` for the typical features (e.g. `torch.sum(dim=)`, `(x-mean)/std*weight+bias`, `torch.matmul`, etc). Buckets: Reduction / NN-Normalization / Elementwise / Loss-Reduce / Pooling / MatMul / Random / Broadcast / Conversion.
2. **TOP3 pitfalls** for that category — from this skill's own `references/constraints/` files (e.g. `reduction.md`, `precision.md`, `tail-safety.md`, `vec-reduction-a2.md`): take the 2–3 most relevant "高频坑" for the matched category.
3. **Conservative starting point** — a safe initial tiling for that category (e.g. for NN-Normalization: fix `hiddenDim ≤ SINGLE_ROW_SIZE` SingleRow path first; for Elementwise: Var-tile `Min(CeilDiv(N,64)*64, TILE_MAX)`).

The triple is injected into the sub-agent prompt as a prelude block named `TILING_PRELUDE`. The constraint files live inside this skill, so no external (now-removed) tiling-design skill is needed.

> **Target device**: the orchestrator also resolves `target_device` (a2|a5) from `output/{op_name}/easyasc_workspace/codegen_status.json` (or `op_desc.json["operator_type"]` = `easyasc-a2` / `easyasc-a5`; default **a2**) and passes it into the prompt so the sub-agent picks the right `from easyasc.<target> import *` line.

### Phase A — design-brief agent (reads the big references, returns a path)

Prompt includes: `op_name`, paths to `op_desc.json` / `{op_name}_functional.py`, `TILING_PRELUDE`, target device + operator surface (a2 default; CV vs Vector hint from grepping `module_fn` for `torch.matmul` / `@` / `F.linear` / `torch.bmm`), `${EASYASC_DSL_HOME}`, and the sections "Algorithm path selection" / "Dtype path" / "TILE sizing" of this SKILL.md.

The agent reads `references/easyasc_dsl_primer.md`, the mandatory `references/constraints/` files for the category (Workflow step 3), ≤2 pointers from `references/easyasc_dsl_pointers.md`, and exactly 1 closest match from `references/output_example/` (dtype instance MUST match op_desc: fp32 → `leaky_relu.py`/`add_rms_norm.py`; bf16/fp16 → `mish_bf16.py`/`rms_norm_bf16.py`). It writes `output/{op_name}/easyasc_workspace/dsl_design_brief.md` (≤100 lines): import line, algorithm style, tiling pattern + TILE_MAX, dtype path, UB tile inventory, top pitfalls (from constraint files), and the example file to copy.

**Final message: brief path + ≤3 lines summary. No file contents.**

### Phase B — DSL writer agent (reads only the brief + functional.py)

Prompt includes: brief path, functional.py path, the "Output requirements" + "Common Pitfalls" + "Verification Checklist" sections, `${EASYASC_DSL_HOME}`. It must NOT re-read the large references — the brief carries the design.

Writes `output/{op_name}/{op_name}_dsl.py`, runs the simulator self-check, pipes output to `scripts/check_ub_usage.py --dsl` (Var-tile recommended; see "TILE sizing"). Self-fix at most 2 rounds, always saving the latest simulator output to `output/{op_name}/easyasc_workspace/sim_check.log`.

**Final message: only `{dsl_path, simulator_pass, max_abs_diff, ub_usage, notes<200}` — no DSL source.**

### Phase C — debug agent (only if B failed; one agent per round, ≤3 rounds)

A fresh agent each round, prompted to read ONLY: the DSL file, `sim_check.log`, the brief, and the constraint file matching the failure. Each round fixes → reruns simulator → overwrites `sim_check.log`. Same final-message contract as B. >3 failed rounds → surface to cake (do not weaken the simulator check).

**Recovery**: if any phase's tool result is lost (e.g. `Tool result missing due to internal error`), do NOT relaunch — the artifacts are on disk: check the brief / DSL file / `sim_check.log` and continue.

Simple ops (Elementwise, ≤2 inputs, single dtype) may merge A+B into one agent; keep C separate.

**Example phase-A delegation** (B/C analogous):
```
Agent({
  description: "Design brief for {op_name} DSL",
  prompt: """Write dsl_design_brief.md for {op_name}.
  TILING_PRELUDE: Category NN-Normalization; TOP3 pitfalls 1.Welford nRec 2.epsilon 3.Normalize cfg; start hiddenDim<=6144 SingleRow.
  Target a2; Vector (UB-only); EASYASC_DSL_HOME=...
  [paste: Algorithm path selection / Dtype path / TILE sizing sections]
  Read primer + category constraints + <=2 pointers + 1 example; write output/{op}/easyasc_workspace/dsl_design_brief.md.
  Final message: brief path + 3-line summary ONLY."""
})
```

**When called directly** (not from cake): execute the workflow below in the current context — no sub-agents. Derive the tiling triple yourself from `op_desc.json["category"]` + this skill's `references/constraints/` files (no external tiling-design skill is required).

## Algorithm path selection

**Default everything to A2 (`from easyasc.a2 import *`).** A2 covers both UB-only Vector primitives and cube primitives needed for matmul.

| `module_fn` features | Algorithm style | Imports | Status |
|---|---|---|---|
| Pure elementwise / reduction / norm / quant / loss (no matmul) | **Vector** (UB-only) | `from easyasc.a2 import *` | ✅ End-to-end verified on 910B2 (Sigmoid 10/10) |
| `torch.matmul` / `@` / `F.linear` / `torch.bmm` / einsum matmul | **CV / cube** (uses A2 cube tiles) | `from easyasc.a2 import *` — `DBuff`/`Position.L1`/`Position.L0C`/`matmul`/`GetCubeNum`/`GetCubeIdx` | ✅ End-to-end verified on 910B2 (A2 cube bf16 matmul 5/5) |
| A5-only features: `@vf` register kernels, `Position.L0A`/`L0B` direct access, cumsum-style scan, fp8 micro-cast | A5-specific | `from easyasc.a5 import *` | 🧪 codegen targets ascend950, not validated on 910B2 — last resort only |

CV/cube examples to mimic (pick by closest pattern):
- **Base cube matmul** — `references/output_example/qk_matmul_batched.py` (A2 cube matmul — DBuff / L0C / matmul / GetCubeNum, identical to upstream). Use for: vanilla matmul, batched matmul, attention QK^T tiles. Upstream mirror: `${EASYASC_DSL_HOME}/agent/example/kernels/a2/qk_matmul_batched.py`.
- **Grouped matmul / MoE (cross-group dispatch)** — `references/output_example/grouped_matmul.py` (**canonical**, A2, fp16 in/out, fp32 L0C accumulator). Extends `qk_matmul_batched.py` with: (1) cross-group core round-robin via `count <<= (count + blocks_in_g) % core_num` (CANN GMMProcess equivalent — keeps cores busy across group boundaries), (2) multi-K-tile accumulate loop with `valid_m/valid_n/valid_k < TILE` padding via `set_constant_to_l1`, (3) mandatory `split_workspace` allocation to keep `userWorkspaceSize > 0` (without it device hangs silently at 507015), (4) `core_num_step = Var(1); core_num_step <<= core_num` alias trick so `range(start, stop, core_num)` doesn't trip codegen `.value=0`. Bias is **not** fused in cube — host-side post-add (the upstream `bias_mmad` BT path was tested and does not work on a2 device). Use for: grouped_matmul, MoE FFN, any algorithm with `for g in range(E): y[rows_g] = x[rows_g] @ w[g]`.
- **Flash attention — PREFILL** (long query S1, square QK/PV GEMMs): `references/output_example/flash_attn_full.py` (online-max rescale, TILE_M=128 M-tiling, BH×ceil(S1/128) parallelism, CvMutex/VcMutex cube↔vec overlap). Causal variants: `flash_attn_full_pj_*_causal.py` (in-kernel col-index + `compare_scalar`/`select` diagonal mask). Use for: standard attention where the query sequence is long (FIA "prefill" / PFA template).
- **Flash attention — DECODE / incremental** (tiny query Sq∈{1,2} vs long KV cache; FIA "decode"/IFA + MTP template): `references/output_example/flash_attn_decode.py` (**canonical**, 5/5 **sim + 910B2 device** verified fp16+bf16, D∈{128,256}). FULL flash online-softmax (running-max rescale, numerically safe for any score range) with **in-kernel normalisation** (single final output — no plugin post-divide). Hard-won a2-sim rules baked in (see file header): `exp` on a narrow `[MH,8]` tile returns **inf** → keep exp'd per-row scalars `[MH,64]`-wide; `[1,MH]` arithmetic is unreliable → use only as transient cmax/cadd output; **clamp exp args ≥ -80** (sim exp overflows on large negatives); a runtime-loop-Var slice offset (`acc[dc*64:...]`) trips codegen → **unroll D-chunks with Python-constant offsets**. For **SPLIT-KV / flash-decoding** (when BH < #cores with long KV), the companion `flash_attn_decode_splitkv.py` is a **two-kernel pipeline** (partial per (head,kv-split) → LSE-combine), 4/4 sim + 910B2 device verified. The decode-specific differences from prefill: (1) **M = Sq** (1 decode / 2 MTP) → ONE tiny query tile padded to `MH=16`, valid rows in the lower quarter `[0, MH/4)`, **no `tiles_m` loop**; (2) parallelism over **work-items (b,n) heads only** (each core streams a head's full KV cache — for cann-bench MHA decode BH=B·N is 32..4096 ≥ 24 cores, so split-KV/flash-decoding cross-core combine is **unnecessary**; the file documents where to add it if BH < cores); (3) bounded cann-bench scores ⇒ **no max-stabilisation, no online rescale** — just `exp` + plain accumulate; (4) emits **un-normalised `acc` + per-row `den`** (plugin divides, dodges the in-kernel `div` odd-row corruption); (5) branch-free **additive causal mask** `mbias [Sq,Skv]` (0/-1e30, plugin-built) for MTP. One kernel serves fp16+bf16 via `q.dtype`-typed L1/P buffers. Use for: MHA/GQA decode, incremental/autoregressive attention, MTP (multi-token-predict).

Vector examples to mimic, by pattern (all marked **canonical** are 2-D and simulator-verified):
- Pure elementwise / activation: **prefer `references/output_example/mish_var_tile.py`** (**Var-tile canonical**, shape-aware UB, same .run serves any N, +41% geomean vs fixed-TILE on mixed-shape bench). For first prototypes or single-target deploys, `leaky_relu.py` (fixed `[1, TILE_N]` 2-D row+col tile) is the simpler fallback. Copy `mish_var_tile.py` for any new elementwise op that sees mixed N (PReLU / ELU / Hardsigmoid / Hardswish / GELU / Swish / Sigmoid all benefit).
- Norm-along-last-dim / per-row reduce-then-scale: `references/output_example/add_rms_norm.py` (**canonical**, replaces the deleted stale `layer_norm.py`; cadd group reduction, `brcb([M,1]→[M,8])`, dup+rec for runtime `1/H`, tail handling via `gm_to_ub_pad`).
- Per-row reduce → row stat (sum/max/min/L1/L2): `references/output_example/sum_reduction_over_a_dimension.py` (**canonical**, 2-D 64×64 tile pattern, demonstrates cadd → brcb → broadcast-mul; chain after this for mean / sqrt / abs variants).
- Softmax (single op, 3-pass tiled): `references/output_example/softmax.py` (**canonical**, supports H multiples of 64). For non-aligned H or softmax-fused-in-attn, see `flash_attn_score.py` / `flash_attn_full.py`.
- Cumsum / scan: `references/output_example/cumsum.py`.

## Dtype path — one canonical pattern, dtype-specialized instances

cake has **ONE canonical pattern** for compute dtype in vector kernels:

> **Universal rule**: vec computation is ALWAYS fp32 in UB. The caller's dtype only decides whether the kernel adds a `cast()` step at the GM↔UB boundary — nothing else changes.

This applies to **every elementwise / norm / activation / loss / quant op**. It matches the tiling-design rule for Elementwise (`references/constraints/...`):

> "FP16 直接计算 → FP16 加减乘要先 Cast 到 FP32, 计算完再 Cast 回."

### Why we keep separate `_bf16.py` files alongside the fp32 ones (not one unified template)

A unified template that does `if x.dtype is DT.float: ub_lo = Tensor(...) else: ...` to gate UB allocation **does not work** in easyasc, because the `@kernel()` decorator does AST rewriting (see `easyasc/pythonic.py::_IfRewriter`): every Python `if/elif/else` inside the kernel body is transformed into `with If(cond): ... with Elif(...): ... with Else(): ...` context managers. With-statements ALWAYS execute their Python body, so `Tensor(...)` inside the `if`-branch allocates the tile even when the condition is False — both branches' bodies run; the `If`/`Else` classes only control which branch's effects survive in the recorded IR.

**Empirical confirmation** (sub-agent reproduce):
```
needs_in_cast = False             # x.dtype is DT.float
if needs_in_cast:
    ub_x_lo = Tensor(x.dtype, ...)  # ← STILL allocates! (Python body executes)
else:
    pass

# Simulator output:
# Usage: 24 KB (4 fp32 + 2 lo tiles)  ← 2 unwanted lo tiles allocated
```

Consequence: dtype-specialization must happen at the **file level** (different `build_codegen_inputs`, different UB declarations), not inside the kernel body. The two-file pattern below is the practical implementation of the universal rule.

### The two-file pattern (each file is one instance of the canonical pattern)

| Pattern | fp32-caller instance | bf16/fp16-caller instance | Difference |
|---|---|---|---|
| Pure elementwise / activation | `references/output_example/leaky_relu.py` | `references/output_example/mish_bf16.py` | bf16 file adds 2 bf16 UB tiles (~4 KB) + 2 `cast()` calls per tile loop; everything else identical |
| Norm-along-last-dim with reduction | `references/output_example/add_rms_norm.py` | `references/output_example/rms_norm_bf16.py` | bf16 file uses bf16 UB tiles for GM↔UB + cast(); reduction stays fp32 (precision-critical) |

Both columns share the same compute structure: fp32 UB tiles for math, the same tiling, the same data-flow shape. The bf16 column adds boundary cast steps + extra UB to hold caller-dtype tiles temporarily.

When starting a new op, **pick the column matching your `op_desc` input dtype**:
- `op_desc` dtype is fp32 → start from `leaky_relu.py` (elementwise) or `add_rms_norm.py` (norm)
- `op_desc` dtype is bf16 / fp16 → start from `mish_bf16.py` (elementwise) or `rms_norm_bf16.py` (norm)

The bf16/fp16 instances are required for bandwidth-bound bf16/fp16 callers — otherwise the bridge auto-inserts host-side casts with 3-5× HBM penalty (see proof below).

### What goes wrong if you pick the wrong instance

If `op_desc` declares bf16 but your DSL is fp32-only (e.g. you copied `leaky_relu.py` and forgot to migrate to the bf16 version), the bridge cpp auto-inserts a **host-side cast layer**:

```cpp
// gen_bridge.py auto-emits this when DSL dtype ≠ op_desc dtype:
at::Tensor x_dsl   = (x.scalar_type() == at::kFloat) ? x : x.to(at::kFloat);
at::Tensor y_out_dsl = at::empty(...);
// ... kernel call ...
at::Tensor y = (y_out_dsl.scalar_type() == x.scalar_type())
             ? y_out_dsl : y_out_dsl.to(x.scalar_type());
```

This works correctly but **the casts happen on HBM**, not in UB:

For an RMSNorm `[2048, 4096]` bf16 = 16 MB workload:

| Step | wrong: fp32-only DSL + bf16 caller (host cast) | right: bf16 DSL + bf16 caller (kernel cast) |
|---|---|---|
| Bridge: `x.to(at::kFloat)` host cast | **16 MB read + 32 MB write = 48 MB** | (skipped) |
| Kernel: GM→UB read | **32 MB** (fp32) | **16 MB** (bf16) |
| Kernel: UB cast bf16→fp32 | (on fp32, no cast needed) | **0 MB** (UB-local) |
| Kernel: math in UB | 0 | 0 |
| Kernel: UB cast fp32→bf16 (out) | (on fp32, no cast needed) | **0 MB** (UB-local) |
| Kernel: UB→GM write | **32 MB** (fp32) | **16 MB** (bf16) |
| Bridge: `y.to(at::kBFloat16)` host cast | **32 MB read + 16 MB write = 48 MB** | (skipped) |
| **Total HBM** | **160 MB** | **32 MB** |
| **Ratio** | **5× more HBM** | baseline |

For 910B2 HBM bandwidth ~1.6 TB/s, the 128 MB extra HBM costs ~80 µs per call — more than the entire kernel compute time for most norm/elementwise shapes. The math itself is identical (fp32 throughout), no precision loss either way; the cost is pure bandwidth.

### How `gen_bridge.py` tells you when you picked wrong

When DSL dtype differs from op_desc dtype, `gen_bridge.py` prints to **stderr** at stage 6:

```
⚠️  PERFORMANCE WARNING — host-side dtype cast emitted
  The bridge cpp is inserting a host-side cast layer because the
  DSL's GMTensor dtype differs from the public-facing op_desc dtype.
  Estimated HBM overhead per call (shape from op_desc): 12.0 MB
  To eliminate this overhead, rewrite the DSL in the kernel-side cast
  pattern. References:
    skills/dsl-baseline-generation-easyasc/references/output_example/mish_bf16.py
    skills/dsl-baseline-generation-easyasc/references/output_example/rms_norm_bf16.py
```

If this fires, copy from the matching `_bf16.py` instance and adjust the math — don't ignore the warning unless your tensor sizes are small enough that dispatch overhead dominates (typically numel < 256 K).

### Caveats

- A bf16 kernel binary won't accept fp32 input — calling it with fp32 raises `aclnn returns DTYPE_NOT_MATCH (rt 161003)`. If you need to serve both bf16 and fp32 callers from one ModelNew, you currently must either write two DSL files + dispatch in cpp, or accept the host-cast overhead for one of the two. (Future: cake may support "one DSL → multiple dtype-specialized binaries" — not yet.)
- bf16 instance UB cost is ~1.5× the fp32 instance's (extra bf16 tile per tensor). For shapes where the fp32 UB already fills 60%+ of UB, you may need to shrink `TILE_N`/`TILE_H` to fit the doubled allocation. Check the `Usage: NN KB / 192 KB` line in simulator output.

## TILE sizing — recommended pattern is **shape-aware Var-tile**

After choosing algorithm + dtype, the third important decision is **how UB tiles are sized**. There are two patterns:

| Pattern | Tile size | When to use | Canonical example |
|---|---|---|---|
| **Var-tile** (recommended) | Runtime expression: `Min(64 * CeilDiv(N, 64), TILE_MAX)` | Mixed-shape workloads (e.g. LLM bench seeing N=128 to N=8192). UB scales with caller shape. | `mish_var_tile.py` |
| **Fixed-tile** (legacy) | Compile-time int: `TILE_N = 1024` | Single-target deployments where you know N at build time; first prototypes where simplicity > perf | `leaky_relu.py`, `mish_bf16.py` |

### How easyasc allocates UB

The simulator uses a **bump allocator with no liveness analysis**: every `Tensor(...)` adds its byte size to `next_offset`, the budget never shrinks. Tiles allocated in `if`/`else` branches both count (AST-rewriting, see "Dtype path" section). Pass-1 tiles that the algorithm could free for pass-2 instead stay live to the end of the kernel.

Per-AIV core, UB capacity is **192 KB** (set via `globvars.ub_cap = 192`). The simulator prints actual usage as `| Usage: NN KB / 192 KB |` at the end of each run.

**Critical lower-level detail**: `AllocateLocalTensor<T>(int len)` (in `tensorutils.h`) internally calls `TPipe::InitBuffer(tbuf, len * sizeof(T))` — this is the standard AscendC runtime UB allocation. The `len` parameter is **not required to be compile-time constant** at the AscendC level. easyasc's `Tensor` constructor checks `len(shape) == 2` but doesn't restrict element types, so **Var expressions in shape are legal**. The codegen lowers `Tensor(DT.float, [1, Min(N, 4096)], Position.UB)` to `LocalTensor<float> ub = AllocateLocalTensor<...>(1 * Min(N, 4096))`, where `Min(...)` is computed at kernel entry on device.

### Var-tile pattern (the recommended canonical)

```python
TILE_MAX = 4096                                        # compile-time UB ceiling
tile_var = Min(CeilDiv(N, 64) * 64, TILE_MAX)          # runtime, 64-aligned

ub_x = Tensor(DT.float, [1, tile_var], Position.UB)
ub_y = Tensor(DT.float, [1, tile_var], Position.UB)
# ... and so on for the other tiles ...

cols_per_row = CeilDiv(N, tile_var)                    # runtime col-loop count
for r in range(r_begin, r_end):
    for c in range(0, cols_per_row):
        with auto_sync():
            n_off = Var(c * tile_var)
            count = Min(tile_var, N - n_off)
            # ... GM→UB, math, UB→GM as usual ...
```

UB scales with shape:

| N     | tile_var | UB per fp32 tile | Total UB (4 tiles) |
|-------|----------|------------------|--------------------|
| 128   | 128      | 0.5 KB           | 2 KB               |
| 1024  | 1024     | 4 KB             | 16 KB              |
| 2048  | 2048     | 8 KB             | 32 KB              |
| 4096  | 4096     | 16 KB            | 64 KB              |
| 8192  | 4096 (capped) | 16 KB       | 64 KB (with 2 col-tile sweeps) |

**The same .run binary natively serves any N**, picking the right UB footprint at execution time. Same as CANN's `ub_factor` design pattern in built-in RmsNorm — just with the tile computation done in DSL/kernel rather than a separate host TilingFunc.

### Critical constraint — `tile_var` must be 64-aligned

A2 vec instructions (Exp, Mul, Add, Ln, Div, etc) operate on **64-fp32-element masks** (256-byte alignment). If `tile_var` is not a multiple of 64, the kernel emits vec ops that try to read 64 elements but the allocated buffer has only `tile_var` valid → simulator errors:

```
RuntimeError: task memory validation failed for exp src:
  need=4096 bytes, have=4092 bytes
```

**Fix**: always wrap `tile_var` in `CeilDiv(N, 64) * 64`:

```python
# WRONG — fails for non-64-aligned N (1023, 1021, 4097, etc):
tile_var = Min(N, TILE_MAX)

# RIGHT — round up to 64-multiple:
tile_var = Min(CeilDiv(N, 64) * 64, TILE_MAX)
```

### Empirical comparison: Var-tile vs fixed TILE (mish 9-shape bench)

| Config | Geomean (case 1-8) | Comment |
|---|---|---|
| A: `TILE_N = 1024` | 0.565x | Baseline; conservative default. Small N OK, large N wastes col-loop sweeps. |
| B: `TILE_N = 8192` | 0.533x | Wastes UB on small shapes (case 7-8: 0.25-0.29x). |
| **C: Var-tile `Min(64*CeilDiv(N,64), 4096)`** | **0.795x** ⭐ | Best on every shape except dispatch-bound short-row outlier (see Known Limitations). |

Per-case wins of Var-tile over baseline:
- N=2048: 0.67 → **1.05x** (first case > 1.0×)
- N=4096: 0.82 → **1.30x**
- N=8192 fp32: 0.53 → **1.37x**
- N=1023 bf16 tiny: previously FAIL → now PASS (0.49x; 64-aligned `tile_var=1024` changed ULP noise distribution favorably)

### TILE sizing recipe — choose pattern by op shape range

**Use Var-tile when**:
- `op_desc.test_cases` has N spread across > 2× (e.g. N=128 to N=8192)
- Op is bandwidth-bound (elementwise / activation / quant / norm) — any kernel where UB layout matters

**Use Fixed-tile when**:
- N is bounded to a narrow range you can pick statically
- Reduction is forced to a fixed granularity (e.g. `cadd` 64-element groups → naturally fixed at TILE=64)
- Memory-tight algorithms (flash-attention with 6+ fp32 tiles) where UB is already saturated; runtime adaptation buys nothing

#### Sizing the parameters

1. **For Var-tile**: pick `TILE_MAX` as the compile-time ceiling (TPipe reserves this much per tile regardless of runtime tile_var).
   - Recipe: `bytes_per_elem = sum(num_tiles_of[dt] * sizeof(dt) for each dtype)`
   - `TILE_MAX = floor(160 KB / bytes_per_elem)` → round down to power of 2
   - For mish (4 fp32 = 16 B/elem): `TILE_MAX = floor(160K / 16) = 10240` → 8192 or 4096

2. **For Fixed-tile**: `TILE_N = floor(160 KB / bytes_per_elem)` directly, then verify with simulator + check_ub_usage.py.

### Automated verification — `check_ub_usage.py`

Run this after the simulator self-check:

```bash
# For Var-tile DSL (pass --dsl so the script detects Var-tile mode):
python3 path/to/{op_name}_dsl.py 2>&1 \
  | python3 skills/dsl-baseline-generation-easyasc/scripts/check_ub_usage.py \
      --dsl path/to/{op_name}_dsl.py

# For fixed-TILE DSL (no --dsl flag, legacy mode):
python3 path/to/{op_name}_dsl.py 2>&1 \
  | python3 skills/dsl-baseline-generation-easyasc/scripts/check_ub_usage.py
```

**With `--dsl`** (Var-tile detected): exit 0, shows UB range across runs. Low usage on small shapes is OK — it proves Var-tile is adapting.

**Without `--dsl`** (fixed-TILE mode): exit 1 if any run uses < 30% UB. Suggests both the fixed-TILE multiplier AND the Var-tile pattern reference file.

### Exceptions where Var-tile is NOT the right choice

- **Group reduction granularity**: `cadd` reduces 64 fp32 lanes per repeat. For per-row reduce ops, the inner dim is naturally bounded at 64. Multi-stage reduce (`rms_norm_bf16.py`) lets you go higher *with a fixed TILE_H*; Var-tile on this dim brings no benefit.
- **`brcb` broadcast pattern**: `brcb([M,1] → [M,8])` requires `TILE_M=64` exactly. Don't Var-ize this dimension.
- **Short-row, huge-M shapes** (e.g. mish case 9: M=133221, N=373): Var-tile actually performs *worse* than fixed TILE=1024 because **the bottleneck is per-row DMA dispatch overhead**, not UB sizing. The fix is multi-row packed DMA tiling, which is a different DSL pattern entirely (not yet templatized in cake).
- **Memory-tight algorithms** (e.g. flash-attention with `q/k/v/p/score/out` all in UB simultaneously): if 6+ fp32 tiles already saturate UB, runtime adaptation has nothing to give. Document this in `PROGRESS.md`.

### Known limitation of Var-tile (under investigation)

When N > TILE_MAX, the last col-tile has `count = N - (cols-1) * tile_var` which can be much smaller than `tile_var`. Vec ops still default to full-mask repeats over the allocated `tile_var` (with masked-out lanes), but for some downstream stride configurations the masked-off output may interact with stored memory in subtle ways. Empirically, on mish case 16 (N=8193, multi col-tile) Var-tile sometimes fails precision checks that fixed TILE=8192 passes.

**Workaround**: if your op_desc has shapes where `N % TILE_MAX != 0` and accuracy at fp32 boundary matters, either (a) bump TILE_MAX so N always fits in one col-tile, or (b) fall back to fixed TILE.

## Prerequisites

- `${EASYASC_DSL_HOME}` is set to the root of `ops-easyasc-dsl` (cake stage 0 enforces this). It is needed at **runtime** (PYTHONPATH for `import easyasc.*`, simulator, codegen scripts), not for documentation reads — all docs and examples are mirrored locally under `references/`.
- `${EASYASC_DSL_HOME}/easyasc/` exists (cake stage 0 runs `bash ${EASYASC_DSL_HOME}/agent/scripts/init.sh` to restore the runtime tarball on first use).
- `output/{op_name}/{op_name}_functional.py` exists (from the `functional-conversion` stage).
- `output/{op_name}/{op_name}_op_desc.json` exists (from the `op-desc-generation` stage).

## Workflow

1. **Read input**: `output/{op_name}/{op_name}_functional.py`.
2. **Required primer**: read `references/easyasc_dsl_primer.md` (5–10 minutes; covers the minimum viable DSL surface).
3. **Mandatory constraint reads — by operator category** (NEW, P0 fix — added after a debugging session where a sub-agent reproduced 5 separate known-pitfall failures because none of these files were proactively loaded):

   Look at the `TILING_PRELUDE` category injected by the orchestrator (or, when called standalone, classify the op yourself from `op_desc.json["category"]` + `module_fn` features). Then **read the matching row's constraint files in full** before opening any example:

   | Category (from TILING_PRELUDE) | Mandatory reads (under `references/constraints/`) |
   |--------------------------------|---------------------------------------------------|
   | **Reduction**, **NN-Normalization**, **Loss-Reduce** | `vec-reduction-a2.md` (cadd group semantics + brcb broadcast), `reduction.md` (multi-pass row stats), `autosync.md` (V↔MTE pipe edges only — control-lane Var reads are NOT auto-synced with vec writes), `tail-safety.md` (`valid_h`/`valid_m` at GM boundary, full local tile shape) |
   | **Elementwise**, **Loss-Elementwise** | `autosync.md`, `tail-safety.md` |
   | **MatMul** (CV path) | `vec-reduction-a2.md` (if a vec postprocess is fused), `tiling.md`, `datamove.md` (L1/L0 staging), `autosync.md` |
   | **Pooling**, **Conversion**, **Random**, **Broadcast** | `tail-safety.md`, plus the closest pattern doc from `easyasc_dsl_pointers.md` |

   These four files are small (each <300 lines) and answer ~90% of the recurring A2-DSL pitfalls: cadd-is-not-whole-reduce, `[M,1]→[M,8]` brcb idiom, `auto_sync()` doesn't cross V→MTE2, partial-load auto-zero padding. Skipping them is the #1 cause of "simulator passed, device gave wrong/garbage output" bugs.

4. **Optional targeted depth**: pick **at most 2** docs from `references/easyasc_dsl_pointers.md` based on the operator's compute pattern (e.g. an `api_reference` page for exact APIs, plus a `kernel_patterns` page for a similar topology). Do not preload all docs.
5. **Concrete example**: in `references/output_example/`, find the file most similar to `{op_name}` (by computation pattern, not by name). For norm/reduce ops the canonical reference is `add_rms_norm.py` (replaces the deleted stale `layer_norm.py`). For elementwise ops, the 2-D allocation pattern in `output/Sigmoid/Sigmoid_dsl.py` or `output/ReLU/ReLU_dsl.py` is the working baseline — the in-skill `leaky_relu.py` still has a STALE 1-D allocation banner. Read the chosen file carefully. If no close match locally — only then — run `${EASYASC_DSL_HOME}/agent/scripts/select_kernel_example.py` to search the upstream library.
6. **Generate** `output/{op_name}/{op_name}_dsl.py`. See **Output requirements** below.
7. **Self-check**: run `python output/{op_name}/{op_name}_dsl.py`. The simulator should pass `torch.testing.assert_close` against the reference. If it fails, debug and fix the DSL (do **not** soften the assertion or skip the check).
8. Continue to the next stage in the cake workflow (`easyasc-codegen`).

## Output requirements

### 1. Imports

```python
from easyasc.a2 import *   # DEFAULT — Vector path, targets ascend910b
import torch               # required for the simulator self-check section
```

Only switch to `from easyasc.a5 import *` if the operator strictly requires cube primitives (`mmad`, `Position.L0A/B/C`) and cannot be expressed in A2. The CV/A5 path is not end-to-end validated in this repo — see "Algorithm path selection" above.

### 2. Kernel signature — naming is a HARD CONSTRAINT
The kernel function name MUST be exactly `{op_name}_custom`. This is not stylistic — it is the bridge between easyasc's auto-derived AscendC op type (`_to_camel(name)` → e.g. `LayerNormCustom`) and the CAKE pybind wrapper (`aclnn{CamelCase}Custom`). If the names mismatch, evaluation fails to find the registered op.

Example (functional input is `softmax(x, dim=1)`):
```python
@kernel()
def softmax_custom(x: GMTensor, y: GMTensor, M: Var, N: Var):
    ...
```

### 3. Argument order (enforced by OpExec)
`input GMTensor* → output GMTensor* → Var*`. Outputs come **after** inputs and **before** scalars. Mixing orders raises a runtime error.

### 4. Algorithm — full implementation, no shortcuts
Implement EVERY operation from `module_fn` exactly as specified.

**FORBIDDEN**:
- Placeholder values (e.g., `gate = 0.5`, `result = 0.0`)
- Simplified logic (e.g., skipping a normalization step, using fixed constants)
- Comments like `simplified`, `placeholder`, `TODO`, `will be refined later`
- Partial implementations (only first tile, skipping reduction loops)
- Approximations that do not match the reference (e.g., `x * 0.5` instead of full sigmoid)

**REQUIRED**:
- Implement EVERY operation from `module_fn` exactly
- Use ALL input tensors (load and consume each one)
- Implement ALL loops (tile loops, reduction loops, sub-batch loops)
- Use easyasc-provided high-level APIs (see `references/docs/09_api_reference.md`); do NOT call Python `math` functions on Tensors
- Accumulate reductions across ALL tiles (not just the last tile)
- Apply ALL activations and transformations correctly
- Handle boundary conditions (e.g., last tile not divisible by tile size)

### 5. Core partitioning (Vector path)
Use `GetVecNum()` and `GetVecIdx()` for dynamic core count — do not hardcode a number. For workloads not evenly divisible across cores, use `CeilDiv(total_chunks, GetVecNum())` to derive `chunks_per_core`, then bound the per-core range with `Min(...)` to handle the tail core.

### 6. On-chip buffers
Allocate inside the kernel with explicit `Position`:
```python
ub_buf = Tensor(DT.float, [tile_rows, tile_cols], Position.UB)
```
For pure Vector kernels, almost everything lives in `Position.UB`.

### 7. Data movement & synchronization
Wrap all GM↔UB movement and compute ops in `with auto_sync():`. Use the `<<=` operator for moves:
```python
with auto_sync():
    ub_buf <<= x[row_start:row_end, 0:H]   # GM → UB
    # ... compute on ub_buf ...
    y[row_start:row_end, 0:H] <<= out_buf  # UB → GM
```

### 8. `build_codegen_inputs()` builder — REQUIRED
The DSL file must expose a module-level function `build_codegen_inputs()` returning a positional-argument tuple suitable for `OpExec(...)(*args)`. This is the single source of truth for shapes used by both the simulator check and the next stage (`easyasc-codegen`):

```python
def build_codegen_inputs():
    """Build inputs/outputs/scalars for OpExec.
    Must use shapes consistent with {op_name}_functional.py's get_inputs().
    Returns: tuple of (input_tensors..., output_tensors..., var_scalars...)
    """
    M, N = 16, 16384
    x = torch.randn(M, N, dtype=torch.float32)
    y = torch.zeros(M, N, dtype=torch.float32)
    return (x, y, M, N)
```

The argument order in the returned tuple MUST match the kernel's parameter order (input GMTensor* → output GMTensor* → Var*).

### 9. Mandatory self-check section
Append `if __name__ == "__main__":` that calls `build_codegen_inputs()`, runs the simulator, and asserts vs a torch reference:

```python
if __name__ == "__main__":
    args = build_codegen_inputs()
    y_kernel = OpExec({op_name}_custom, simulator=True)(*args)
    # build the torch reference using the same input(s) — usually args[0]
    y_ref = torch.<op>(args[0], ...)
    torch.testing.assert_close(y_kernel, y_ref, rtol=..., atol=...)
    print(f"max_abs_diff={torch.abs(y_kernel - y_ref).max().item():.6e}")
```

The simulator self-check is **part of the deliverable**, not optional. The next stage (`easyasc-codegen`) imports `build_codegen_inputs()` and trusts that simulator parity has been verified here.

### 9. Comments
Natural-language comments are mandatory and are part of the DSL. Comment what each block computes and why a particular tile/core split was chosen.

## Common Pitfalls — `Var.value` 误用（必读！）

⚠ **不要用 `Var.value` 当编译期常量**。`Var` 类型的参数（`M: Var`、`H: Var` 等）在
codegen 阶段会有一个绑定的 `.value` 字段（来自 `build_codegen_inputs()` 提供的具
体 int），但读取 `.value` 把它当 Python int / float 用会把那个具体值**烤进 kernel
二进制**：kernel 在运行时不再根据传进来的 `Var` 取值，而是永远用 codegen 那一次绑
定的值。结果是 kernel 只对一个 shape 工作，其它 shape 全错。

### ❌ 错误模式（kernel 只对一个 H 工作）

```python
@kernel()
def my_norm_custom(x: GMTensor, y: GMTensor, M: Var, H: Var):
    n_h_tiles = H.value // TILE_H        # H.value 是 codegen-time int，被折叠
    inv_H     = 1.0 / float(H.value)      # 同上，被折叠成字面量
    for hi in range(0, n_h_tiles):        # 循环上限烤死成具体数
        ...
        muls(sum_s, sum_s, inv_H)         # 倒数也烤死
```

### ✅ 正确模式（运行时 Var 算术）

```python
@kernel()
def my_norm_custom(x: GMTensor, y: GMTensor, M: Var, H: Var):
    n_h_tiles = CeilDiv(H, TILE_H)       # Var，运行时算 ⌈H/TILE_H⌉
    inv_H     = var_div(1.0, H)          # Var scalar，运行时算 1/H
    for hi in range(0, n_h_tiles):       # range() 接受 Var stop
        ...
        muls(sum_s, sum_s, inv_H)        # muls / adds 都接受 Var 标量
```

可用的运行时 Var 算术：`CeilDiv(a, b)` / `var_div(a, b)` / `Min(a, b)` /
`Max(a, b)`，定义在 `easyasc/stub_functions/var_op.py`。`from easyasc.a2 import *`
已自动 re-export 这些 API。

参考 working 实现：`references/output_example/qk_matmul_batched.py` (A2 cube path, canonical) 或上游 `${EASYASC_DSL_HOME}/agent/example/kernels/a5/matmul_rowwise_norm.py`（A5 fallback）
（第 38-79 行）。

### 自我审查清单（写完 DSL 必须勾完）

- [ ] kernel 函数体内**没有任何** `.value` 出现（grep 一下确认）
- [ ] 所有循环上限 / 倒数 / 余数计算都走 `CeilDiv` / `var_div` / `Min` / `Max`
- [ ] `__main__` simulator 自检至少跑 **2 个不同的 Var 取值组合**（典型：默认 + 一个明显不同的 shape），确认 max_abs_diff 都 < 1e-4

## Verification Checklist (must all be YES)

- [ ] Top-level import is `from easyasc.a2 import *` (DEFAULT — Vector path). Only use `from easyasc.a5 import *` if cube primitives are strictly required; if so, the choice must be flagged in PROGRESS.md (CV path is not end-to-end validated)
- [ ] Kernel function is decorated with `@kernel()`
- [ ] Kernel function name is exactly `{op_name}_custom`
- [ ] Parameters are annotated as `GMTensor` / `Var`
- [ ] Argument order is `input GMTensor* → output GMTensor* → Var*`
- [ ] All on-chip buffers carry an explicit `Position`
- [ ] All data movement is inside `with auto_sync():`
- [ ] Implementation is complete — no placeholders, no simplifications, no skipped steps
- [ ] All input tensors are loaded; all reductions accumulate across tiles
- [ ] Module-level `build_codegen_inputs()` returns `(input_tensors..., output_tensors..., var_scalars...)` in argument order
- [ ] `if __name__ == "__main__":` block calls `build_codegen_inputs()`, runs `OpExec(..., simulator=True)`, asserts vs torch reference
- [ ] Running `python {op_name}_dsl.py` prints `max_abs_diff` and exits 0
- [ ] **No `Var.value` reads inside the kernel body** — runtime-variable shapes must use `CeilDiv` / `var_div` / `Min` / `Max` (see *Common Pitfalls* above)
- [ ] **Simulator self-check covers ≥ 2 distinct `Var` value combinations** — proves the kernel is not baked to a single shape
- [ ] **TILE pattern + UB utilization verified**:
      Recommended: write a **Var-tile** DSL (`tile_var = Min(64*CeilDiv(N, 64), TILE_MAX)`, see `references/output_example/mish_var_tile.py`). Run `python3 path/to/{op}_dsl.py 2>&1 | python3 skills/dsl-baseline-generation-easyasc/scripts/check_ub_usage.py --dsl path/to/{op}_dsl.py`; exit 0 required.
      Legacy: if you used fixed-TILE (e.g. simple first prototype copying `leaky_relu.py`), run the same script **without `--dsl`** and require utilization ≥ 30%; otherwise bump TILE or migrate to Var-tile.
      Exception: memory-tight / cadd-granularity-bound ops can ignore with PROGRESS.md justification.
- [ ] **DSL dtype instance matches op_desc dtype** (universal rule: vec compute is always fp32 in UB; caller dtype only adds boundary cast):
      - op_desc input dtype is **fp32** → start from `leaky_relu.py` (elementwise) or `add_rms_norm.py` (norm). DSL uses `Tensor(DT.float, ...)` only, `build_codegen_inputs` returns fp32 tensors.
      - op_desc input dtype is **bf16 / fp16** → start from `mish_bf16.py` (elementwise) or `rms_norm_bf16.py` (norm). DSL declares BOTH caller-dtype and fp32 UB tiles + uses `cast()` at every GM↔UB boundary, `build_codegen_inputs` returns bf16/fp16 tensors.
      - Mismatch (fp32-only DSL with bf16 op_desc) triggers a 3-5× HBM host-cast warning at stage 6 and is rejected unless explicitly justified in PROGRESS.md.
      - **Do NOT try to write one unified DSL with `if x.dtype is DT.float: ...`** — easyasc's `@kernel()` AST rewrites `if` to `with If(cond):` context managers that execute both branches' Python bodies, so the gating doesn't work. See "Dtype path" section for the AST constraint and the two-file pattern.

If any checkbox fails, fix the DSL before reporting completion. Do not weaken the simulator check.

## Output files

- `output/{op_name}/{op_name}_dsl.py`  — the easyasc DSL, naming-compliant and simulator-verified

## Notes

- Do NOT generate AscendC C++ here — that is `easyasc-codegen`'s job in the next stage.
- Do NOT call `OpExec(..., simulator=False)` from this stage — that triggers full codegen + build, which belongs to the next skill.
- If the simulator check fails consistently, surface the error to cake; do not paper over it. Common root causes: argument order, missing `auto_sync` wrap, wrong `Position`, mis-shaped Tensor allocation.
