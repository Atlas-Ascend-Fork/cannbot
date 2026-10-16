---
name: dsl-easyasc-codegen
disable-model-invocation: true
description: Author AscendC kernels via the easyasc Python DSL — write @kernel functions, smoke-test in easyasc's simulator against a PyTorch reference, then either compile to AscendC (a2 path) or stop at simulator validation (a5 path). Hand off to dsl-easyasc-post when AscendC artifacts are produced.
---

# dsl-easyasc-codegen

This skill provides a parallel path to the existing `dsl-baseline-generation` + `dsl-lowering` pipeline. It uses the **easyasc** Python DSL as the kernel authoring surface. It does NOT replace the existing path — both coexist.

```
functional.py
   │
   ▼
[dsl-easyasc-codegen]   ← THIS SKILL
   │
   ▼
easyasc workspace + (a2: AscendC artifacts | a5: simulator-only)
   │
   ▼ (a2 only)
[dsl-easyasc-post]
   │
   ▼
{op}Custom/  →  [ascend-evaluation]
```

## Two tracks

| Track | Authoring | Smoke | AscendC compile | Next step |
|-------|-----------|-------|-----------------|-----------|
| **a2** (host = 910B) | `easyasc.a2` | `OpExec(simulator=True)` × ≤3 | `OpExec(simulator=False)` runs b.sh + r.sh | `dsl-easyasc-post` |
| **a5** (any host)    | `easyasc.a5` | `OpExec(simulator=True)` × ≤3 | skipped (host can't run a5 AscendC) | report-only |

Smoke-fail handling:
- **a2** — after 3 fails, fall through to codegen anyway; defer accuracy/perf to AscendC layer.
- **a5** — after 3 fails, stop and ask the user. No AscendC fallback.

## Required inputs (from cake's existing flow)

- `output/{op_name}/{op_name}_functional.py` — PyTorch reference (already produced by other cake skills)
- The user-facing op name (e.g. `flash_attention`)

This skill produces all easyasc-specific artifacts; it does NOT produce or modify `*_reference.py`, `*_custom.py`, `*.cpp` (PyBind), or `test_cases.py`. Those remain the responsibility of the existing cake skills.

## Workflow (script-first)

### Step 1 — detect device, decide target

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/check_device.sh --target a2
```

Decision rules:
1. Default: parse host with `--target a2`. Pass → continue with `target=a2`.
2. If user has explicitly stated this is an A5 algorithm, run with `--target a5` instead.
3. Exit code 3 from check_device.sh = host detection failed → use `AskUserQuestion` to confirm target with the user (options: `a2 (910B host)`, `a5 (simulator-only)`, `cancel`).
4. Exit code 2 (a2 requested but host is not 910B) = hard fail; surface the JSON `error` field to the user.

Capture the JSON output and pass `host_device`, `host_family`, and warnings into `codegen_status.json` after `init_workspace.sh` runs (Step 2 seeds the file; you write the device_check fields after Step 1+2).

### Step 2 — initialize workspace

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/init_workspace.sh <op_name> <a2|a5>
```

Creates `output/<op>/easyasc_workspace/` containing:
- `env.sh` (sets `PYTHONPATH`)
- `codegen_status.json` (seeded; subsequent scripts mutate)

### Step 3 — author the kernel (natural language)

Write `output/<op>/easyasc_workspace/<op>_easyasc.py`. Required exports:

```python
from easyasc.a2 import *        # or easyasc.a5 — match target_device

@kernel()
def kernel(...):                # MUST be named `kernel`
    ...

def make_inputs():
    """Return tuple of positional args for OpExec — torch.Tensors first, then scalars."""
    ...

def reference(*inputs):
    """PyTorch reference. Same signature as make_inputs()'s return."""
    ...
```

These three names are a **hard contract** with `run_smoke.py` and `run_codegen.py`. Without them the scripts fail at setup.

Authoring checklist:
1. Read `output/<op>/<op>_functional.py` to derive the math contract.
2. Choose pipeline topology based on the algorithm:
   - cube only (matmul-like) — see `references/examples_<target>/matmul.py`
   - vec only (sort/cumsum/elementwise) — see `references/examples_a2/sort_rows.py` or `examples_a5/chunk_row_cumsum.py`
   - cube↔vec fusion — see `references/examples_<target>/flash_attention.py`
   - **reg/micro, data-dependent** (gather/LUT, sort/merge, compact/filter, histogram/scatter-stat)
     — see `references/reg_micro_cookbook.md`. These are NOT elementwise; the cheatsheet alone is insufficient.
3. Refer to `references/easyasc_<target>_cheatsheet.md` for available primitives.
4. Refer to `references/opexec_options.md` for `shape_bindings` if multiple scalars share values.
5. For a5 reg/micro kernels, in order:
   - `references/reg_vf_skeleton.md` — the `@vf` skeleton (scope-open reg/mask decls, mask-driven
     tail handling, mixed-precision load→fp32→store discipline). Start here.
   - `references/reg_micro_cookbook.md` — which data-dependent pattern to reach for.
   - `references/numerical_precision.md` — if it's a reduction/norm/softmax/quant op (fp32
     accumulation, max-sub, epsilon, clamp, rounding).
   - `references/micro_perf_rules.md` — after correctness: barrier elimination, dispatch cost,
     algorithm selection, multi-core/tiling, event-pipeline & cube↔vec sync construction.
6. To resolve an a5 micro op's exact semantics ("same name ≠ same thing"), consult
   `references/arch35_micro_reference.md` §1 — the complete MicroAPI surface → easyasc.a5 mapping
   (enumerated from the authoritative `reg_compute/*_intf.h` headers), plus usage-mined recipes/pitfalls.
7. Before concluding "easyasc can't express this, must hand-write AscendC", check
   `references/dsl_coverage_and_gaps.md` — most reg/micro capabilities (LoadDist, pack/unpack,
   CastConfig, interleave, mask_xor, gather_mask, setflag/waitflag, cube↔vec sync, atomics) are
   already exported; only sort and histogram are genuine gaps.
8. If a genuine gap forces an AscendC **membase** fallback (whole-UB `LocalTensor` + `AscendC::*`
   vec API) instead of a `@vf` reg kernel, follow `references/membase_to_regbase_migration.md`:
   get the membase version correct as the golden, then incrementally lift each convertible compute
   region to regbase VF, re-verifying **bit-exact** after every step, leaving only the
   non-convertible regions (the gaps) on the membase path.

### ⚠️ UB Buffer 约束（必须遵守，违反会导致 smoke PASS 但 evaluation 精度失败）

**1. Tensor 声明维度必须是编译时常数 TILE_L**，不能用运行时 Var 或从 `make_inputs()` shape 推导：

```python
TILE_L = 128                                          # ✅ 模块级常数
x_ub = Tensor(DT.float, [1, TILE_L], Position.UB)    # ✅ 正确

row_len = Var(128)
x_ub = Tensor(DT.float, [1, row_len], Position.UB)   # ❌ 错误：row_len 是 Var
```

**2. 若 row_len（或任意空间维度）可能在不同 test case 中超过 TILE_L，必须在 kernel 内做内循环分块**。
否则运行时越界写入相邻 UB buffer，产生精度错误（pattern=`algorithm_error`）。
参见 `references/easyasc_a2_cheatsheet.md` 的"UB Tiling 模板"获取可复用代码。

**3. Tensor 下标只能是 slice，不能是 Var 或 int**：

```python
x_ub[0:1, :]       # ✅ slice — 合法
x_ub[c_idx, :]     # ❌ Var   — parse 阶段报 TypeError: dim0 index must be slice
x_ub[0, :]         # ❌ int   — 同上
```

若需要"按 channel 随机访问 UB"，在 `make_inputs()` 中将 per-channel 统计量预展开为
逐元素形式（如 `scale[B*C, L]`），kernel 只做纯 elementwise 操作。

**4. `make_inputs()` 的代表性 shape 必须覆盖 api_description.md 中最大的维度值**，
不能只用 `shape_info` 里的小 shape。smoke 通过的 shape 不代表所有 test case 都安全。

### Step 4 — smoke test (loop, max 3 attempts)

```bash
source output/<op>/easyasc_workspace/env.sh
python ${CLAUDE_SKILL_DIR}/scripts/run_smoke.py <op_name>
```

> **The a5 software smoke is ADVISORY, not authoritative.** `OpExec(simulator=True)` has known
> false negatives — most importantly, a kernel that builds a mask with `compare(...)` and consumes
> it with `select(...)` (bitonic sort, set-intersection, compaction, …) **fails the smoke even
> when it is correct** (simulator_v2 compare↔select mask-store mismatch; see `error_recipes.md`).
> For a5, **cannsim / `msprof op simulator` is the ground truth** (`a5_simulator.md`).

After each run, read `output/<op>/easyasc_workspace/codegen_status.json`:
- `smoke.passed = true` → proceed to Step 5 (a2) / Step 6 (a5).
- `smoke.passed = false` and `smoke.attempts < 3` → diagnose using `references/error_recipes.md`, edit `<op>_easyasc.py`, re-run.
  - **Before editing an a5 kernel**: if it uses `compare→select`/mask and the smoke shows a large/total
    mismatch, suspect the **software-smoke false negative** first — do NOT rewrite working logic.
    Confirm against `error_recipes.md` "compare → select chain"; if it matches, escalate to cannsim
    (next bullet) instead of burning smoke attempts.
- `smoke.attempts >= 3`:
  - **a2** → continue to Step 5 anyway. Set `smoke_fallback=true` in your handoff message (you can also annotate the status file). Do not raise an error.
  - **a5** → do **not** declare failure on a smoke fail alone. If an **A5-simulator host is available**
    (cannsim + an `Ascend950PR_*` variant present — see `a5_simulator.md` §1), **escalate to the
    cannsim path** (codegen → build → cannsim/msprof) and treat its result as authoritative; a
    compare-mask smoke fail is very likely the known false negative. Only if **no A5-sim host is
    available** (pure 910B), set `next_step="human-intervention"` and tell the user the smoke is
    inconclusive and authoritative a5 validation needs an A5-sim host.

### Step 5 — codegen + build + run (a2, or a5 on an A5-sim host)

```bash
source output/<op>/easyasc_workspace/env.sh
python ${CLAUDE_SKILL_DIR}/scripts/run_codegen.py <op_name>
```

This executes `OpExec(simulator=False)` from inside the workspace, which:
1. Generates AscendC source under `<op>_raw/op_host/`, `<op>_raw/op_kernel/`, and `<op>_raw_aclnn_test/`.
2. Writes `b.sh` / `r.sh` in the workspace.
3. Runs `b.sh` (build) then `r.sh` (cannsim run).

`run_codegen.py` runs for **a2**, and for **a5 when an A5-simulator host is detected** (cannsim +
an `Ascend950PR_*` variant). For a5 **without** an A5-sim host it refuses and sets
`next_step="report-only"` (no way to build/run a5 on a plain 910B).

On success:
- **a2** → `next_step = "post"` (hand off to `dsl-easyasc-post`).
- **a5** → `next_step = "report-only"` (the `r.sh` cannsim run IS the authoritative validation; post
  does not apply to a5). `raw_dir`, `aclnn_test_dir`, `run_package` populated; logs in `b.sh.log` / `r.sh.log`.

On failure: `next_step = "human-intervention"`. Inspect logs and `references/error_recipes.md`.

### Step 6 — report and hand off

Read the final `codegen_status.json`. Summarize to the user based on `next_step`:

| `next_step` | Meaning | What to tell the user |
|-------------|---------|----------------------|
| `"post"` | a2 path complete with AscendC artifacts | "Ready for `dsl-easyasc-post`. Workspace at `output/<op>/easyasc_workspace/`." |
| `"report-only"` (a5 + A5-sim host, `ascendc_generated=true`) | a5 built + validated on cannsim | "A5 kernel codegen'd, built, and run on cannsim. Artifacts in `<op>_raw/`; profiling in `<op>_raw_aclnn_test/OPPROF_*`." |
| `"report-only"` (a5, no A5-sim host) | a5 software-smoke only | "A5 software-smoke done; couldn't build/run on this plain 910B host. Note: the software smoke is advisory — for `compare→select` kernels it can be a false negative. Authoritative validation needs an A5-sim host." |
| `"human-intervention"` | failure that exhausted automated retries | Show smoke / codegen logs and ask user how to proceed. |

## Reference index

- `references/easyasc_a2_cheatsheet.md` — a2 DSL primitives
- `references/easyasc_a5_cheatsheet.md` — a5 DSL primitives
- `references/opexec_options.md` — `OpExec` flags, `shape_bindings`
- `references/env_checklist.md` — environment variables and self-check
- `references/error_recipes.md` — common smoke / build / run failures (incl. a5 reg/micro sim quirks)
- `references/reg_micro_cookbook.md` — a5 reg-based / data-dependent patterns (gather/LUT, sort/merge, compact, histogram) + arch35 ground-truth pointers
- `references/reg_vf_skeleton.md` — a5 `@vf` kernel skeleton: scope-open reg/mask decls, mask-driven tail handling, mixed-precision discipline
- `references/numerical_precision.md` — a5 precision methodology for reduction/norm/softmax/quant (fp32 accumulation, max-sub, epsilon, clamp, rounding)
- `references/micro_perf_rules.md` — a5 VF perf tuning: barrier elimination, dispatch cost, algorithm selection, multi-core/tiling, event-pipeline & cube↔vec sync
- `references/arch35_micro_reference.md` — **complete** MicroAPI surface → easyasc.a5 mapping (enumerated from the authoritative `reg_compute/*_intf.h` headers), plus usage-mined recipes + pitfalls
- `references/dsl_coverage_and_gaps.md` — what easyasc.a5 already exports vs genuine gaps (sort export, histogram); check before dropping to AscendC
- `references/membase_to_regbase_migration.md` — escape hatch when a DSL gap forces AscendC membase: membase golden → incremental bit-exact lift to regbase VF → residual membase for non-convertible regions
- `references/a5_simulator.md` — cycle-profiling a compiled a5 kernel on an A5-sim host (cannsim vs msprof op simulator, clean-env discipline, pitfalls)
- `references/examples_a2/{matmul,sort_rows,flash_attention}.py` — a2 kernel templates
- `references/examples_a5/{matmul,chunk_row_cumsum,flash_attention}.py` — a5 kernel templates

## Hard contracts (do not break)

1. **Kernel module exports**: `kernel`, `make_inputs`, `reference`. Anything else and the scripts fail.
2. **Argument order in `@kernel`**: all `GMTensor` (inputs then outputs) before all `Var`. OpExec validates.
3. **Workspace layout**: `output/<op>/easyasc_workspace/` and `<op>_raw/` inside it. `dsl-easyasc-post` reads exactly these paths via `codegen_status.json`.
4. **Status file is the only handoff channel**: don't communicate workspace info to post via prose. Update `codegen_status.json` and let post read it.
