```
ID:        0162-excluding-multiply-from-the-atomic-path-cost-3-3x-and-the-shipped-gate-is-the-wrong-criterion-by-its-own-text
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     950PR
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scatter/fallback/tiling-flow.md:332-339 —
           "曾在 `useAtomicEP` 上多挂 `&& red != MUL`，让 multiply 一律退回①，结果某 fp32 multiply
           用例（16.7M 元素）**从 3767us 劣化到 12602us**。" · "反过来也成立：**冲突密集时 CAS 会
           退化**，那时①才对。**判据应该是冲突度，不是"是不是 multiply"**——当前实现用的是 `starved`
           （间接相关），如果遇到"更新数远大于输出位置数"的形状，这里值得补一条真正的冲突度判据。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured scatter on a named 950 board with updates far outnumbering output positions
           where the element-level CAS path beats the fiber-exclusive path — the conflict-density
           concern would then be unfounded and `starved` would be an adequate proxy after all.
```

# 0162 · Excluding `multiply` from the atomic path cost 3.3×, and the shipped gate is the wrong criterion by its own text

## 1 · Claim
Upstream asserts a defect it introduced and removed: adding `&& red != MUL` to `useAtomicEP`, sending
every `multiply` back to the fiber-exclusive path, degraded one fp32 multiply case of 16.7 M elements
from 3767 µs to 12602 µs. Upstream asserts the reason the exclusion was wrong: under random indices
each output position is updated about once on average, so contention is light and the CAS loop almost
always succeeds first try. Upstream then asserts the converse and, in the same paragraph, that its own
shipped gate is the wrong criterion: when conflicts are dense the CAS loop degrades and the
fiber-exclusive path is right, so the criterion should be conflict density and not "is it multiply" —
and the current implementation uses `starved`, which is only indirectly related, so a shape with
updates far outnumbering output positions would warrant a real conflict-density criterion that has not
been written. Upstream lists this in its own gaps table as `冲突度判据 | 用 starved 间接近似`. Not
established here.

## 2 · The wrong branch this removes
The excluded-multiply reasoning is the natural one and it is wrong in a specific, learnable way.
`multiply` has no hardware atomic, so it needs a CAS loop, and CAS loops are the textbook example of
a primitive that degrades under contention — therefore, the reasoning goes, keep `multiply` off the
element-level path. What the reasoning omits is the actual contention level: on a random-index scatter
each output position is touched about once, so the loop is a compare-exchange that succeeds
immediately and costs about what a plain atomic would. Excluding it forfeits the element-level
parallelism that the `starved` regime exists to buy, at a measured 3.3×.

The second and more useful half is upstream's disclosure about its own fix. Having removed the wrong
exclusion, upstream states plainly that the criterion it now ships is still not the right one:
`starved` is a proxy for whether the fiber path can fill the machine, which correlates with conflict
density only indirectly. So the gate is known-approximate, the regime where it fails is named
(updates far outnumbering output positions — `epTotal ≫ numelData`), and the correct criterion is
named but not implemented. An agent reading only the code would find a gate that looks principled; an
agent reading this passage knows which shapes it is expected to get wrong.

That combination — a disclosed regression with numbers, plus a statement that the current fix is still
the wrong criterion, plus the named regime where it will fail — is the practice this book exists to
preserve. It is the same species as the reduction family's disclosed gate misfires (0127) and it
points the same way: a gate derived from a mechanism argument needs a board to validate, and the
document should say which shapes were never tested.

## 3 · Ground / Source
`scatter/fallback/tiling-flow.md:332-339`, §5.5 in full:

```
### 5.5 `multiply` 必须留在 ④，不要因为"CAS 可能活锁"排除它

曾在 `useAtomicEP` 上多挂 `&& red != MUL`，让 multiply 一律退回①，
结果某 fp32 multiply 用例（16.7M 元素）**从 3767us 劣化到 12602us**。
随机索引下同一输出位置平均只被更新 ~1 次，竞争很轻，CAS 循环几乎总是一次成功。

反过来也成立：**冲突密集时 CAS 会退化**，那时①才对。**判据应该是冲突度，不是"是不是 multiply"**——
当前实现用的是 `starved`（间接相关），如果遇到"更新数远大于输出位置数"的形状，这里值得补一条真正的冲突度判据。
```

Re-derived: `12602 / 3767 = 3.345×`. The same pair appears in the document's header at `:7` as the
headline illustration of what choosing the wrong path costs —
`选错是数量级差距——实测同一用例 **12602us ↔ 3767us**（`multiply` 被错误地排除在元素级原子路径外）` —
so this case is the family's canonical example, quoted twice.

The gate as shipped, `:119-120`:

```
useAtomicEP  = (red == ADD || red == AMIN || red == AMAX || red == MUL)
               && needScatter && extentsMatch && starved;
```

`red == MUL` is present, so the exclusion was removed; `starved` is the only density-adjacent term.

The gaps table entry, `:365`:

```
| 冲突度判据 | 用 `starved` 间接近似 | 见 §5.5 |
```

The `multiply` mechanism, `:76-77`:

```
  ├─ add / amin / amax / multiply（结果与顺序无关）→ ④ 直接原子
  │     · multiply 无硬件原子乘 → CAS 循环（fp32 / int32 / int64）
```

and its half-precision restriction, `:233-234`:

```
`multiply` 的半精度还有一层硬约束：**half/bf16 没有标量 CAS**（只有 `half2` / `bfloat16x2_t`），
所以 `if constexpr (!IsHalfLike<ACC_T>())` 挡掉实例化，半精度乘只能走 fp32 累加器。
```

So `multiply` at fp16/bf16 cannot use the CAS path at all and must route through the fp32 accumulator
(0157 §3, `:219-234`) — a separate constraint from the conflict-density question, and one that is a
hard capability limit rather than a policy threshold.

The related half-precision accumulator rule, `:228-231`, which is the other place this family
distinguishes a real capability from a performance choice:

```
| reduce | 半精度走法 | 原因 |
|---|---|---|
| `add` / `multiply` | **必须** fp32 累加器 | `asc_atomic_add(__gm__ half*)` **存在**（在 `simt_api/asc_fp16.h`，**不在** `device_atomic_functions.h`），但**每次操作都舍回 fp16** —— 换用后 MARE 与软件版**逐位重现** `0.020576`，精度过不了 |
| `amin` / `amax` | 直接用原生半精度原子 | 不产生舍入；绕 workspace 只是白付两趟 cast（实测那两趟能占某用例约一半时间） |
```

That row is worth noting for its evidence quality: the half-precision atomic add exists, its header is
named, the header it is *not* in is also named, and the failure is quantified as a MARE reproducing
bit-for-bit at `0.020576` against a software implementation. A claim with that much identity is rare
in this domain.

The other declined change with a stated reason, `:366`, completing the picture of what upstream chose
not to tune:

```
| 逐用例挑最优线程数 | 未做 | 1024 净收益更好但不均匀（个别用例退化 8~24%）；按用例挑最优收益很小**且没有正当的形状判据** |
```

Registered in `harvest/standing/950-tiling.md` as an open question rather than a contradiction row:
the conflict-density criterion is named by upstream, not written by upstream, and no two sources
disagree about it.

## 4 · Procedure
Proposed, runnable later on Ascend950PR — the board upstream names; a 950DT run is a separate claim.
Never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Arm 1 — reproduce the regression, a poison arm. Build the fp32 `multiply` case at 16.7 M elements two
ways with one compiler pin: `useAtomicEP` as shipped (path ④, CAS) and with `&& red != MUL` restored
(forcing path ①). md5 both; host echo of the selected path, `blocks`, `threads` and any workspace
request; output compared elementwise against a CPU reference on the same input. Record `aiv_time` and,
if the profile exposes it, the CAS retry count, under `msprof --aic-metrics=PipeUtilization`, ≥10
iterations, first 5 dropped. Upstream's numbers are 3767 µs and 12602 µs.

Arm 2 — the conflict-density sweep, which is the arm that would supply the criterion upstream says is
missing. Hold `epTotal` fixed and sweep the ratio `epTotal / numelData` — the average number of
updates per output position — across {0.25, 1, 4, 16, 64, 256} by shrinking `sVar` while keeping the
update count constant, so contention rises with nothing else changing. At each ratio build both path ④
and path ①. Record `aiv_time` and CAS retry counts for both. The crossover ratio is the
conflict-density threshold that does not currently exist, and it is the deliverable of this arm.

Arm 3 — is `starved` a proxy? Over the same sweep, record whether `starved` is true at each point and
compare its value against the arm-2 crossover. Upstream's claim is that the two are only indirectly
related; the measure of that is how far the `starved` boundary sits from the crossover ratio.

Arm 4 — the half-precision constraint, build-only. Attempt to instantiate a scalar CAS on `half` and
on `bfloat16` and record whether it compiles, confirming or refuting the stated hard limit, with the
compiler version recorded since the claim is toolchain-scoped.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` is a
literal (queried, 0141 — `starved` depends on it); that a forced path was taken (host echo required);
that random indices give a contention of ~1 (arm 2 constructs the contention explicitly rather than
inferring it from the distribution); that the profile exposes CAS retries — if it does not, arm 2
reports the timing crossover and declines the mechanism claim.

## 5 · Checker — acceptance declared before the run
Verdict variable `mul_regression` = forced-① median `aiv_time` / path-④ median, on the reproduced
case. Declared before the run: upstream's disclosure is confirmed iff `mul_regression ∈ [2.5, 4.5]`
(upstream: 3.345×). A value near 1 would mean the regression does not reproduce, and that is reported
as measured.

Verdict `conflict_crossover` = the `epTotal / numelData` ratio at which path ① first beats path ④ by
more than the variance floor, from arm 2. This is a new number, not a check against upstream, and is
reported as such. Verdict `starved_is_proxy`: true iff the `starved` boundary and
`conflict_crossover` select the same path on at least 5 of the 6 swept ratios. Upstream predicts
false; a true result would mean the approximation is adequate and the missing criterion unnecessary —
which is the OVERTURN condition.

Verdict `half_cas_exists` from arm 4, with the compiler version.

The exit code is not the verdict: a `multiply` scatter with a lost CAS update exits 0 with plausible
values. The elementwise comparison runs on every arm and the checker fails red if it did not. Second
guard: arm 2's sweep must hold `epTotal` constant while varying `numelData` — the checker verifies
both echoed values at every rung and goes red if the update count moved, because a sweep that changed
two things carries no attribution about contention. Third: path identity via host echo, since a forced
path the host overrode would make `mul_regression ≈ 1` read as a failure to reproduce.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 3767 µs / 12602 µs pair,
the ~1-update-per-position observation, the `0.020576` MARE and the 8–24 % per-case degradation range
are upstream's readouts on Ascend950PR; this book has reproduced none of them.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. `BOARD: 950PR` records the board upstream's evidence names; the stratum,
not the board field, says who measured. The entry does not establish the 3.345× regression, and
upstream's case is identified only by dtype, reduce mode and element count — no shape, no index
distribution, no repetition count, no CANN version. It does not establish that CAS succeeds first try
under random indices; upstream states it as the explanation, not as a measurement. It does not supply
the conflict-density criterion upstream says is missing — §4 arm 2 is designed to produce one and has
not been run, so the criterion does not exist in this book either. It does not establish that
`starved` is or is not an adequate proxy. It does not establish the half-precision CAS limitation,
which is a toolchain claim with no compiler version attached. Nothing here is established for 950DT or
for any 910-family board.
