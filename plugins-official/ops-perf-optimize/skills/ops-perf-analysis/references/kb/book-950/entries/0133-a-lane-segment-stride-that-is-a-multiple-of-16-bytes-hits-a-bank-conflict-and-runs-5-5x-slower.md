```
ID:        0133-a-lane-segment-stride-that-is-a-multiple-of-16-bytes-hits-a-bank-conflict-and-runs-5-5x-slower
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scan/fallback/tiling-flow.md:105-112 —
           "**lane 并行的段长**（同时是 lane 间的 UB 地址步长，**host 与 kernel 必须用同一个公式**，
           否则 UB 预算算错）： S = ceil(R / VLC)
            if (S * sizeof(C)) % 16 == 0:  S |= 1      # 步长是 16B 整数倍会撞 bank，实测慢 5.5 倍
            数据区要按 VLC*S（而非 R）备量，尾部补齐成幺元"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired run on a named 950 board, same shape and same build except for the `S |= 1`
           adjustment, showing no wall-clock difference beyond run variance — the bank conflict
           would then not bind at this stride, and the 5.5× figure would not reproduce.
```

# 0133 · A lane-segment stride that is a multiple of 16 bytes hits a bank conflict and runs 5.5× slower

## 1 · Claim
Upstream asserts that in the lane-parallel sequential scan, the per-lane segment length `S` is
simultaneously the UB address stride between lanes, that `S = ceil(R / VLC)`, and that when
`(S × sizeof(C)) % 16 == 0` the stride collides on memory banks, for which the remedy is to make
`S` odd (`S |= 1`). Upstream states the cost of not doing so as `实测慢 5.5 倍` — measured, 5.5×
slower. Upstream further asserts two consequences: the data region must be provisioned for
`VLC × S` elements rather than `R`, with the tail padded to the combine's identity element; and the
host and the kernel must compute `S` with the same function, or the UB budget is wrong. Not
established here.

## 2 · The wrong branch this removes
This is the only bank-conflict teaching anywhere in this skill. A prior survey counted three
mentions of bank conflict across the whole of `ascendc-perf-optimize` and zero cards teaching it;
the substantive rule is this one line, inside a scan sub-sub-section about lane-parallel segment
length. An agent that has never met it writes `S = ceil(R / VLC)` — the obvious, correct-looking
formula — and gets a kernel that is arithmetically right and, on the affected strides, several
times slower. Nothing in the profile names the cause: the vector pipe is busy, the memory pipe is
busy, the occupancy is fine, and the operator is simply slow. There is no counter called
"bank conflict" in the metrics this skill teaches an agent to read.

The `S |= 1` remedy is one token wide and looks like a typo to a reader who does not know why it is
there, which is the second wrong branch: an agent tidying the formula will remove it.

The third wrong branch is the host/kernel agreement. `S` decides both the gather stride in the
kernel and the buffer size in the host budget. Two implementations of "the same" formula that
differ by the `|= 1` disagree about how much UB is needed, and the resulting overflow is a wrong
result, not a build error. Upstream states this as a rule about *where the function lives* — one
function called from both sides, with the host copy conventionally suffixed `Host` — which is the
correct shape of fix: the rule is enforced by placement, not by remembering.

## 3 · Ground / Source
`scan/fallback/tiling-flow.md:105-112`, in full:

```
**lane 并行的段长**（同时是 lane 间的 UB 地址步长，**host 与 kernel 必须用同一个公式**，
否则 UB 预算算错）：

S = ceil(R / VLC)
if (S * sizeof(C)) % 16 == 0:  S |= 1      # 步长是 16B 整数倍会撞 bank，实测慢 5.5 倍
数据区要按 VLC*S（而非 R）备量，尾部补齐成幺元
```

The same-function requirement restated with the naming convention, `:199-201`:

```
**host 与 kernel 的段长公式必须一致**：`LaneSegLen` / `GsSegLen` 在 host 侧算 UB 预算、
kernel 侧算 gather 步长时都要调同一个函数，否则 UB 预算算错。
host 侧函数名通常加 `Host` 后缀（如 `GsSegLenHost`），逻辑与 kernel 侧完全相同。
```

The context that decides when this path is taken, `:84-86` and `:194-197`:

```
② UB 内用什么算法扫
   R > 2*VLC → lane 并行顺序扫描（指令条数与 log2(R) 脱钩）
   否则      → 行内 Kogge-Stone（log2(R) 级，R 小时它那趟固定的 log2(VLC) 更划算）
```

```
**mode 5 内部的算法选择**（gsS 字段）：
- `R > 2 * guardC`（guardC = 64 for fp32/int32）→ `gsS = LaneSegLen(R, guardC, 4)`，走 lane 并行顺序扫描
  + 两行交错（`LaneParallelScanPair`），奇数尾行退回单行（`LaneParallelScan`）
- `R <= 2 * guardC` → `gsS = 0`，走 Kogge-Stone（log2(R) 级，R 小时那趟固定的 log2(VLC) 更划算）
```

Two symbols in the rule are not defined in the scan family. `VLC` appears at `:85`, `:86`, `:109`,
`:111` and `:197` and is never given a value or a definition; from `guardC = 256 / cBytes` at `:145`
and `guardC = 64 for fp32/int32` at `:195`, and from the parallel structure of `R > 2*VLC` and
`R > 2*guardC`, `VLC` is evidently the vector length in elements of the comparison type — 64 at
4 bytes — but upstream never says so. `C` in `sizeof(C)` is the comparison type, inferable from
`cBytes` in the mode-5 pseudocode and stated nowhere. Both are recorded in 0137 with the family's
other undefined symbols.

Re-derived, on the reading that `VLC = 64` at 4-byte comparison type and `sizeof(C) = 4`: the
condition `(S × 4) % 16 == 0` reduces to `S % 4 == 0`, so one stride in four is affected before the
fix and none after. At `R = 8192`, `S = 128`, which is divisible by 4 — so the flagship case for
this path hits the conflict, and `S` becomes 129. The buffer must then be provisioned for
`64 × 129 = 8256` elements rather than 8192, i.e. 0.8 % more, and the tail padded with the identity.
The provisioning consequence is small; the performance consequence upstream reports is 5.5×.

`实测慢 5.5 倍` carries no board, no dtype, no shape, no core count, no tool and no repetition
count. It is one of three unconditioned measurements in this family (see 0132 for the others) and
it is the most consequential, because it is the sole justification for a rule that changes a
formula.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. This is
the cleanest paired experiment in the domain: one build flag, one bit of difference, identical
output required.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

Paired build. Take a Cummin case with `N == 1`, fp32, `M` large enough to fill the machine, and
`R = 8192` so the lane-parallel path is selected (`R > 2 × guardC`) and `S = 128` is a multiple of
4, i.e. the conflict condition holds. Build two kernels from one source with one compiler pin,
differing only in whether the `S |= 1` line executes; md5 both binaries to show they differ; host
echo of `S`, `gsS`, `mode` and the provisioned buffer elements for each. Both must produce output
bit-identical to each other and to a CPU reference — this is a pure addressing change, so
bit-identity is required here and a difference is a build error, not a numerical tolerance question.
Record `aiv_time` under `msprof --aic-metrics=PipeUtilization` plus, if the profile exposes it, any
UB access-conflict counter; ≥10 iterations, first 5 dropped, per case, with the variance floor
measured first by running one build twice.

Stride ladder. Sweep `R` so that `S` takes values {126, 127, 128, 129, 130, 132, 136, 256, 257},
covering multiples of 4 and their odd neighbours, and record `aiv_time` at each with the fix
disabled. If the effect is a bank conflict at 16 B stride multiples, the curve has spikes exactly at
`S % 4 == 0` and is flat elsewhere. A monotone curve instead would mean the effect is size, not
alignment — which the paired build alone could not distinguish.

Dtype arm: repeat at `sizeof(C) = 2` if a 16-bit comparison path is reachable (`:92` says
Kogge-Stone supports native 16-bit comparison), where the condition becomes `S % 8 == 0`, and record
whether the spike positions move as the formula predicts.

Refuses to assume: that a free die stays free; that a die may be substituted; that `VLC = 64` —
the stride ladder is expressed in `S`, which is echoed by the host, so the experiment does not
depend on knowing `VLC`; that the profile exposes a bank-conflict counter (if it does not, the
timing ladder is the only instrument and that is stated); that the two builds are otherwise
identical (md5 and the bit-identity check together establish it).

## 5 · Checker — acceptance declared before the run
Verdict variable `bank_ratio` = median `aiv_time` (conflicting stride, fix disabled) / median
`aiv_time` (fix enabled), on the paired build. Declared before the run: upstream's figure
reproduces iff `bank_ratio ∈ [4.0, 7.0]`; the effect exists but is smaller iff
`bank_ratio ∈ (1 + variance_floor, 4.0)`; the OVERTURN fires iff
`bank_ratio ≤ 1 + variance_floor`. A second verdict `spike_alignment` is true iff every `S` with
`S % 4 == 0` in the ladder is slower than both its odd neighbours by more than the variance floor
— that is what distinguishes an alignment effect from a size effect, and the entry's mechanism
claim rests on it, not on the ratio.

The exit code is not the verdict. Two guards, both necessary here. First, bit-identity: the two
builds must produce byte-identical output, and the checker goes red if they do not — a difference
would mean the `S |= 1` changed the computation and not just its addressing, in which case the
timing comparison is between two different programs and says nothing. Second, `S` identity: the host
echo must show `S = 128` in the unfixed build and `S = 129` in the fixed one; if both echo the same
`S`, the fix did not take and a `bank_ratio ≈ 1` would be a false overturn. The checker fails on
either condition rather than reporting a ratio. This is the guard that keeps the experiment from
being a two-point comparison of two different builds, which carries no attribution at all.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 5.5× is upstream's
number, stated with no conditions; this book has not reproduced it.

## 7 · Scope limits — what this entry does NOT establish
*[Annotation 2026-08-25 — this §4's paired Cummin build was NOT run; what follows is from
950:0489's pre-declared §5 on 950PR with upstream's own gather primitive.] The 16-byte trigger this
entry carries is the predicate that survived: every stride that is a multiple of 16 B pays (outcome
`16-only`), the "power of two" wording pays nothing extra — 192 B pays exactly what 64 B pays. The
5.5× is reproduced as the **64-B tier at 128 lanes** (5.37×, bf16-width elements, S = 32 → 64 B,
upstream's own fixture), and the penalty is graded by the largest power of two dividing the byte
stride: 16·odd → 1.35×, 32·odd → 2.7×, 64·odd → 5.4×, ≥128 → 10.7× at 128 lanes (half of each at
64 lanes). So this entry's remedy `S |= 1` is right, its cost figure is right for its shape, and
its trigger is right; its mechanism sentence ("collides on memory banks") is the part 0489 §7 keeps
open — the vendor's bank-conflict counter read ≈0 throughout.*

Nothing was measured. The entry does not establish the 5.5× factor, does not establish that the
mechanism is a bank conflict rather than some other stride effect, and does not establish the bank
geometry (how many banks, what width) — upstream states none of it and the 16 B condition is the
only clue. It does not establish `VLC` or `sizeof(C)`'s default (0137). It does not establish that
the rule applies outside the lane-parallel scan path in this family; whether the same stride hazard
affects any other UB access pattern in this skill is unknown, and the fact that this is the skill's
only bank-conflict teaching means the question is open everywhere else. The `S |= 1` remedy is
stated for one condition and this entry does not generalise it. No board, dtype, shape or tool is
named with the 5.5×, and no chip is named anywhere in the scan family, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT because that is where our run would happen.
Nothing here is established for any 910-family board.
