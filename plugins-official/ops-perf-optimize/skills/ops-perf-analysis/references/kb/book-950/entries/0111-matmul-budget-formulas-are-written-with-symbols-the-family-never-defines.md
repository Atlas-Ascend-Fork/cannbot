```
ID:        0111-matmul-budget-formulas-are-written-with-symbols-the-family-never-defines
LABEL:     boundary
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-flow.md:204-206,250-254,
           316-321,66-72,158 — "Bytes_A = baseM × Align(K, c0) × sizeof(dtype)" ·
           "≤ L1_SIZE" · "GetWorkSpace() = aicNum × 256² × sizeof(FP32) + RPC_WORKSIZE × MB_SIZE" ·
           "baseM * baseN * sizeof(float) <= L0cSize" · "(al1Size + bl1Size)*sizeof(dtype)要超过48KB"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  finding any of c0, L1_SIZE, L0aSize, L0cSize, biasTableSize, RPC_WORKSIZE or MB_SIZE
           defined with a value and a board anywhere in this skill — the absence recorded here
           would then be a reading error of ours, and this entry is corrected in place.
```

# 0111 · MatMul budget formulas are written with symbols the family never defines

## 1 · Claim
Upstream asserts a set of capacity inequalities that decide every matmul tiling parameter, and
writes them in symbols that the matmul family never assigns a value: `c0` (the K alignment
granularity in the FullLoad capacity test), `L1_SIZE`, `L0aSize`, `L0cSize`, `biasTableSize`,
`RPC_WORKSIZE` and `MB_SIZE` (the two factors of StreamK's cross-core communication workspace).
Upstream states where they come from — `算法来源：CANN conv_api_tiling_*.cpp（arch35），关键常量定义见
conv_api_tiling_util.h / conv_template_utils.h` — and those headers are not part of this
reference set. Upstream gives exactly one numeric L1 capacity anywhere in the subtree, `524 288`,
inside a FAQ table about a different question, with no board attached. Not established here; this
entry records an absence, and the absence is the claim.

## 2 · The wrong branch this removes
An agent that meets `min(Bytes_A, Bytes_B) × 2 ≤ L1_SIZE` does the natural thing: it substitutes a
number it has seen. The numbers available in this subtree are script defaults with no chip scope —
four incompatible UB values and five incompatible core counts (`harvest/CONTRADICTIONS.md` C-006,
C-007, cited not duplicated) — plus the single unattributed `524 288`. Whichever it picks, the
gate decision, and therefore the strategy choice, and therefore the whole plan, rests on a
literal nobody scoped. The plan is then not wrong in a way anyone can see: it is a decision made
at an invented boundary, and the resulting kernel runs.

The specific harm differs per symbol and is worth naming. `c0` sits inside `Align(K, c0)` in gate
2 of FullLoad: at `c0 = 16` versus `c0 = 32` the computed `Bytes_A` differs for any K not already
aligned, so the gate flips for shapes near the boundary. `L0cSize` bounds
`baseM × baseN × sizeof(float)`, i.e. it caps the basic block directly — the single most
consequential number in §3.1. `RPC_WORKSIZE × MB_SIZE` is an additive term in StreamK's workspace
request: an agent that ignores it because it cannot evaluate it under-allocates, and a workspace
under-allocation is a runtime failure, not a slow kernel.

The correct move, and the reason this is a `boundary` entry rather than a defect report, is
0104's rule plus 0141's query discipline: these symbols name chip specification fields, so they
are hardware constraints that must be *queried*, never guessed, and a plan that cannot query them
should say so rather than substitute.

## 3 · Ground / Source
The undefined symbols in their formulas, quoted with their context.

Basic-block constraints, `matmul/fallback/tiling-flow.md:65-74`:

```
2. 基本快约束:
   baseM、baseN要求16对齐
   baseK要求16对齐（MXFP8/MXFP4 场景要求 MXFP_DIVISOR_SIZE(=64) 对齐）
   baseM * baseN * sizeof(float) <= L0cSize
   baseK >= min(32, Align(K, 16))
   max(baseM, baseN) * baseK * sizeof(dtype) * DB_SIZE(2) <= L0aSize
   baseN * DB_SIZE(2) * sizeof(float) <= biasTableSize // 输入带bias的时候触发
```

`L0cSize`, `L0aSize`, `biasTableSize`: no value, here or elsewhere in the family.

FullLoad gate 2, `:203-206`:

```
2. 小侧矩阵容量（至少一侧通过）:
   Bytes_A = baseM × Align(K, c0) × sizeof(dtype)
   Bytes_B = Align(K, c0) × baseN × sizeof(dtype)
   条件: min(Bytes_A, Bytes_B) × 2 ≤ L1_SIZE
```

`c0` and `L1_SIZE`: no value. `c0` appears nowhere else in the tiling subtree.

StreamK workspace, `:316-321`:

```
StreamK 需要 Workspace 做跨核 partial sum 归约：

GetWorkSpace() = aicNum × 256² × sizeof(FP32)    # 部分和区
               + RPC_WORKSIZE × MB_SIZE           # 跨核通信区
```

`RPC_WORKSIZE`, `MB_SIZE`: no value, and no other mention in the subtree. The file's own worked
example at `:356` evaluates only the first term (`24 × 256² × 4 ≈ 6.3 MB`) and silently drops the
second — which is what an agent will also do.

A separate defect of the same family, recorded here because it is a units error inside a
load-bearing inequality rather than a missing value. `:158`, inside the L1 affinity constraints:

```
   (al1Size + bl1Size)*sizeof(dtype)要超过48KB
```

`al1Size` and `bl1Size` are defined 13 lines above at `:144-145` as
`ml1 * kl1 * sizeof(dtype)` and `nl1 * kl1 * sizeof(dtype)` — they are already byte counts.
Multiplying by `sizeof(dtype)` a second time makes the left side bytes × bytes, so the stated
48 KB floor is a factor of `sizeof(dtype)` away from whatever was meant. At FP16 that is 2×; at
FP4 it is 0.5×. Registered as C-950tiling-005.

The one capacity number in the subtree, `matmul/fallback/tiling-fields.md:193-197`, is a column
header in a FAQ about `L1_BUFFER_NUM`: `vs L1 (524 288)`. It carries no board, no arch and no
provenance, and it is the only place `L1_SIZE` is effectively given a value. It is recorded in
`harvest/standing/950-tiling.md` as a question, not adopted as a fact — see 0109 §3 for the
re-derivation of that table's arithmetic.

Upstream's declared source for all of these, `:9`:
`**算法来源**：CANN conv_api_tiling_*.cpp（arch35），关键常量定义见 conv_api_tiling_util.h /
conv_template_utils.h`. Those headers are not present in `upstream/skills-dev-main/`; whether they
exist in an installed toolkit on any given machine is a separate question and is the subject of
§4's read-only arm.

## 4 · Procedure
Proposed. It has two arms: one that needs no device at all and is permitted in this phase but has
not been run, and one that needs a named 950 board.

Arm 1 — read-only header lookup, no device, no execution. If a 950-era CANN toolkit is installed
on the machine, locate the declared headers and record the value, path and toolkit pin for each
symbol: `grep -Rn 'RPC_WORKSIZE\|MB_SIZE\|L1_SIZE\|L0cSize\|L0aSize\|biasTableSize\|\bc0\b'`
over the toolkit include tree. `-R` and not `-r`: these trees contain symlinked directories and
`grep -r` does not follow them, which would produce a false absence. Read only; nothing is
compiled, nothing is executed, no device is contacted. If no 950 toolkit is installed, that is
recorded and this entry stays exactly as it is.

Arm 2 — runtime query on a named 950 board (950PR or 950DT); never run in this phase.
Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard if the die moved. Query every capacity from the platform rather than from a literal — the
`GetCoreMemSize`-family accessor for UB and its L1/L0A/L0C counterparts, plus the platform's
reported core count — and print all of them from the host alongside the toolkit pin and the
board identifier. Then, for `c0` specifically: build a FullLoad case at a K deliberately chosen
so that `Align(K, 16)` and `Align(K, 32)` give different `Bytes_A` and straddle the gate (e.g.
K = 4080 with `baseM` set so that the gate passes under one alignment and fails under the other),
and record which branch the generator takes. That makes `c0` observable behaviourally even if no
header is available.

Refuses to assume: that a free die stays free; that a die may be substituted; that a header found
on this machine is the header upstream compiled against (the toolkit pin is recorded and the claim
is scoped to it); that the queried capacity on 950PR is the capacity on 950DT.

## 5 · Checker — acceptance declared before the run
Verdict variable `resolved`, a per-symbol tri-state: `header` (found with a value, path and
toolkit pin), `runtime` (obtained from a platform query on the named board), or `unresolved`.
Declared before the run: the entry is corrected in place, and the OVERTURN fires, if any symbol
resolves to `header` from a file *inside this skills repo* — that would mean the absence recorded
in §3 is a reading error of ours. Resolution from an installed toolkit is not an overturn; it is
the expected outcome of arm 1 and is recorded as a new SOURCE line with the pin, which is a
different origin of authority and would raise this entry to `corroborated`.

For `c0` the behavioural verdict is `c0_observed ∈ {16, 32, other}`, read from which branch the
generator took at the straddling K. The checker goes red — rather than reporting a value — if the
two alignments produce the same `Bytes_A` at the chosen K, because then the case did not straddle
anything and the observation is void. That guard is the reason this checker is not the
read-only-what-it-expects species: the straddle is verified arithmetically before the branch is
read, so "no difference observed" cannot be scored as "16 confirmed".

The exit code is not the verdict: `grep` exits 1 on no match, which is a legitimate finding
(`unresolved`) and not a failure, and the host print in arm 2 exits 0 whether or not the queried
values are sane. The verdict is the recorded per-symbol table, and it must have a row for every
one of the seven symbols; a missing row fails the check.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, and arm 1 — which is permitted in this no-card phase — has not been run
either, so no header path or toolkit pin is recorded anywhere in this entry. The entry does not
establish that the symbols are undefined *everywhere*, only that they are undefined in the matmul
family and unmentioned elsewhere in the tiling subtree; upstream names two headers outside this
repo where they are said to live. It does not establish a value for any of them, does not
establish that `524 288` is the L1 capacity of any board, and does not establish that the double
`sizeof(dtype)` at `:158` is an error rather than a convention this book has failed to understand
— it records the units mismatch and the two readings it produces. No board is named in the source
file, so BOARD is `family-claimed(unverified)` and the chip is unstated; §4 names 950PR/950DT
because that is where our run would happen. Nothing here is established for any 910-family board.
