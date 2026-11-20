```
ID:        0328-the-scatter-family-retires-six-changes-in-a-falsification-list-and-four-of-them-for-zero-gain
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     950PR
SOURCE:    ops/ascendc-performance-best-practices/reference/scatter/scatter_design.md:171-180 —
           "## 8. 证伪清单（别重复试）" · "| int64 → int32 索引运算宽度收窄 | **零收益**（+0.04 分）。
           连带 quick-div magic number、按 rank 特化 kernel 同属标量优化，**预期同样无用**——瓶颈是
           访存延迟 |" · "| 缩小 block 换更多核 | `inner` 大时会把合并访问拆碎，净收益 ≈ 0 |" ·
           "| 线程数 512 vs 1024 | 1024 净收益更好但不均匀（个别用例退化 8~24%）。按用例挑最优只能
           再多一点点，**且没有正当的形状判据**，不值得 |"
SOURCE:    same file:166 — "**实测 quick-div 类标量优化在本族零收益**（§8），瓶颈在访存延迟不在
           标量流水"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured scatter on a named 950 board where any one of the six retired changes produces
           a gain outside the run spread — the list would then be recording a property of one
           implementation rather than of the family, and each row would need a scope condition.
```

# 0328 · The scatter family retires six changes in a falsification list, and four of them for zero gain

## 1 · Claim
Upstream asserts a list of six changes it tried and rejected, headed `证伪清单（别重复试）`, with a
result for each. Narrowing index arithmetic from int64 to int32: zero gain (`+0.04` on the score),
and upstream extends the prediction to the whole class — quick-division magic numbers and per-rank
kernel specialisation are the same kind of scalar optimisation and are expected to be equally
useless, because the bottleneck is memory latency and not the scalar pipeline. Shrinking the block
size to engage more cores: net gain about zero, because at large `inner` it fragments coalesced
accesses. The hardware fp16 atomic add: precision failure (`0323`). Relaxing path ⑤'s fiber-count
threshold from 1024 to 256: materially slower, with a measured counter-case. Relaxing path ⑤ to
8-byte values: zero gain, within noise, with the evidence pointing the other way. Thread count 512
against 1024: 1024 better on net but unevenly, with individual cases regressing 8–24 %, and
per-case selection judged not worth it because there is no legitimate shape criterion for it. Not
established here.

## 2 · The wrong branch this removes
Four of the six rows retire the *standard* scalar-optimisation playbook — narrower index types,
magic-number division, rank specialisation — and they retire it for a stated structural reason
rather than a local one: in this family the address arithmetic is not on the critical path, memory
latency is (`950:0161`). An agent that arrives with that playbook will spend a session on it and
gain `+0.04`.

The list's real function is different from any individual row, and it is what makes it worth an
entry rather than six. A falsification list changes the *default* on a class of work: without it,
every one of these is a reasonable thing to try, and trying them is how an engineer learns they do
not pay. With it, the cost of that knowledge has been paid once. The corresponding hazard is that a
falsification list is only as good as its scope — `零收益` on one implementation, one case set, one
board is not `零收益` in general — and §7 records that upstream states none of these scopes.

The sixth row removes a different branch and is the most transferable. Thread count 1024 wins on
net *and* regresses 8–24 % on individual cases; upstream declines per-case selection because there
is **no legitimate shape criterion** for it. That is a refusal to fit a routing rule to a case set,
and it is the same discipline `0326` records from the other direction — where fitting the input
domain to the cases in hand cost the correctness gate. A routing predicate justified only by which
cases it happens to win is a case-ID whitelist wearing a shape's clothes (`950:0046`).

## 3 · Ground / Source
`scatter/scatter_design.md:171-180`, the whole list:

```
## 8. 证伪清单（别重复试）

| 试过的 | 结果 |
|---|---|
| int64 → int32 索引运算宽度收窄 | **零收益**（+0.04 分）。连带 quick-div magic number、按 rank
  特化 kernel 同属标量优化，**预期同样无用**——瓶颈是访存延迟 |
| 缩小 block 换更多核 | `inner` 大时会把合并访问拆碎，净收益 ≈ 0 |
| 硬件 fp16 原子加 | `asc_atomic_add(__gm__ half*)` **存在**（声明在 `simt_api/asc_fp16.h`，**不在**
  `device_atomic_functions.h`），但每次操作都舍回 fp16 —— 换用后 MARE 与软件版**逐位重现**
  `0.020576`，精度过不了。累加类必须走 fp32 累加器 |
| 放宽⑤的纤维数门槛 1024 → 256 | **明显更慢**：某用例（511 纤维、`sIdx=2048`）从③的 133.67us
  劣化到⑤的 295.94us。... **门槛 1024 是合理的** |
| 放宽⑤到 8 字节值 | 零收益（噪声内）。改动本身安全（`T` 只出现在最后一句赋值，排序全基于 uint32
  key），但**无任何 int64 + 大纤维数的实测证据支持**，反而有相反证据。要启用先补实测 |
| 线程数 512 vs 1024 | 1024 净收益更好但不均匀（个别用例退化 8~24%）。按用例挑最优只能再多一点点，
  **且没有正当的形状判据**，不值得 |
```

The generalisation, stated separately at `:166` inside the comparison against the vendor's built-in
implementation:

```
| 多维寻址 | `GetUintDivMagicAndShift` + `Simt::UintDiv` quick-div，按 rank 特化 `SimtComputeDim1~8`
| 快路径压成 `(o, j, c)` 三段、`outer==1` 时省一次除法；通用路径逐维取模 | **实测 quick-div 类
标量优化在本族零收益**（§8），瓶颈在访存延迟不在标量流水 |
```

Two of the six rows are carried by other entries and are cited rather than re-entered: the hardware
fp16 atomic is `0323`; the ⑤ threshold counter-case (511 fibers, `sIdx = 2048`, 133.67 µs against
295.94 µs) is already in `950:0161` §3 from the sibling shelf, which quotes the same figures. The
four rows this entry adds to the book are the int64→int32 narrowing, the block-shrinking, the
8-byte relaxation, and the 512-vs-1024 thread-count decision.

`+0.04 分` is a scoring-harness delta, not a time. `8~24%` is a per-case regression range with no
case identity. `噪声内` is upstream's own acknowledgement that it has a noise floor and that this
result sits inside it — which is more than most rows in this shelf say, and it is exactly the
statement `0327` shows is necessary before any ratio is readable.

Row 5 is the one worth reading twice. Upstream establishes that a change is *safe* (`T` appears only
in the final assignment; the sort is entirely on a uint32 key), finds zero measured gain, notes that
the one adjacent data point argues *against* it, and declines to ship it pending evidence —
`要启用先补实测`. Safety is not a reason to enable something; that is the whole content of the row.

Measured/inferred split at sentence level: **measured** — `+0.04`, `净收益 ≈ 0`, `噪声内`, the
`8~24%` regressions, the 133.67/295.94 µs pair, the bit-identical MARE. **not measured** — that
quick-div and rank specialisation are equally useless (upstream writes `预期同样无用`, marking it as
a prediction); that memory latency is the bottleneck in every case of the family; that no legitimate
shape criterion for thread count exists (an absence-of-evidence claim).

The prediction `预期同样无用` collides directly with the shelf's own SIMT guide, which lists
fast division as a `高`-priority rule with no applicability condition (`simt/optimization-guide.md:24`).
Recorded as `C-950bp-009` and carried by `0342`.

## 4 · Procedure
Proposed, runnable later on `950PR` — the board this family's provenance names. Never run in this
phase. Four rows are re-testable here; two are carried elsewhere.

Variance floor first, and it is the entry's precondition rather than a formality: four of the six
verdicts are "no difference", and a null result against an unstated spread is not a result. One
build, 30 in-process runs and 5 fresh-process runs per configuration, IQR over median, reported
beside every figure. Upstream's own `噪声内` on row 5 implies it had such a floor and never states
it.

Arm 1 — int64 → int32 narrowing. Two builds differing only in index arithmetic width, on a case set
spanning `inner` and fiber count. Primary readout is not total time but the **scalar pipe share**
(`msprof --aic-metrics=PipeUtilization`): upstream's claim is that address arithmetic is not on the
critical path, and the scalar share is what says so directly. A narrowing that reduces scalar share
without reducing kernel time confirms the mechanism *and* the null in one reading.

Arm 2 — block shrinking. Sweep block size downward at fixed total threads, recording achieved
coalescing (bytes moved per useful byte) alongside time. Upstream's stated reason is fragmentation
at large `inner`, so the sweep is run at two `inner` magnitudes and the interaction is the finding.

Arm 3 — the 8-byte relaxation for path ⑤, at the regime upstream says is missing. Build ⑤ with
`esize == 8` enabled and run it specifically at **int64 with large fiber counts** — the case
upstream says has no evidence either way. This is the arm most likely to change a shipped decision.

Arm 4 — thread count 512 against 1024, with the per-case structure kept. Run both across the whole
case set and report the *distribution* of per-case ratios, not the mean. Upstream's decision rests
on the spread (8–24 % regressions), so a mean would erase the thing being decided. Then attempt to
predict the per-case winner from shape features alone, and report the predictor's accuracy: that
number is what upstream's `没有正当的形状判据` asserts is low, and it has never been measured.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; re-sample after; discard the case if the die moved — and
`0327`'s discriminant is applied to every table before any row is interpreted, because this family
has met an 18× contamination on this board. Refuses to assume: that a free die stays free; that a
die may be substituted; that a null result means the change did nothing (Arm 1's scalar-share
readout is what distinguishes "no effect on the kernel" from "no effect at all"); that upstream's
case set is this case set.

## 5 · Checker — acceptance declared before the run
Verdict per row: `retired` if the measured gain is inside the floor or negative, `revived` if it is
positive and outside the floor. Declared before the run: rows 1, 2 and 5 are expected `retired` and
row 6's decision is expected to stand. Any `revived` fires the OVERTURN for that row and the entry is
corrected in place — a falsification list is not a conclusion, it is a record with a scope, and
finding a scope where a row does not hold is the useful outcome.

Verdict `scalar_share_delta` from Arm 1, reported whether or not the timing moved.
Verdict `shape_predictor_acc` from Arm 4, against a declared baseline of 0.5 (a coin flip). Upstream's
claim is supported iff the predictor does not materially beat it.

The exit code is not the verdict. Three guards.

First — the input that makes this checker go red. Every "no difference" arm is paired with a
**positive control**: a change on the same case set that is known to move time (path ③ against
path ①, whose difference this family measures at 4.81× on index distribution alone). If the
positive control does not separate outside the floor, the harness is not sensitive enough to detect
anything, and every `retired` verdict in the run is void rather than confirming. Four null results
from an insensitive instrument is the known blind species, and this is what excludes it here.

Second, Arm 4 reports a distribution and never a mean. A decision made on the spread cannot be
audited from a centre.

Third, no row is interpreted before `0327`'s same-path same-magnitude sibling check has been applied
to its table. On this board, in this family, a contaminated reading has already once looked like an
18× result.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. `+0.04`, `净收益 ≈ 0`,
`噪声内`, `8~24%`, 133.67 µs, 295.94 µs and `0.020576` are upstream's readouts on Ascend950PR under
a harness not present in this tree; this book has built nothing and timed nothing.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. Every row is scoped to one implementation, one case set, one
board, and one harness — none of which upstream states — so `零收益` records what happened there and
not a property of the family or of the architecture. `+0.04 分` is a scoring delta whose relation to
time is unknown. The extension of row 1 to quick-division and rank specialisation is upstream's own
prediction (`预期同样无用`), not a measurement, and it conflicts with the shelf's SIMT guide
(`C-950bp-009`, `0342`). The `8~24%` regression range has no case identity. Row 5's null is stated as
`噪声内` with no floor given, so its strength cannot be assessed. Two of the six rows are carried by
other entries (`0323`, `950:0161`) and are not independently established here. Nothing establishes
that no legitimate shape criterion for thread count exists — that is an absence claim and §4 Arm 4
is the only thing here that would put a number on it. BOARD is `950PR`; nothing is established for
950DT. Nothing transfers to the other book (RULES.md Art. 1).
