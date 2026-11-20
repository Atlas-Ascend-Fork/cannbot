```
ID:        0418-a-thirty-microsecond-dispatch-floor-hid-a-real-speedup-and-upstream-published-the-wrong-conclusion-it-caused
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured by us
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/scan/templates/usage_guide.md:189-194 —
           "### 计时方法：本地测量有 ~30 µs 的地板
           / torch 自定义算子经 python 派发，`n=64` 与 `n=1000003` 都测得 30 µs——小 kernel 的真实
           / 耗时完全被派发开销吞掉。做微优化 A/B 时要么用 cann-bench 的设备侧计时（一轮约 6 分钟），
           / 要么**把 M 放大 8~10 倍**再测：每行的 R/dtype/dim 不变，每行的开销特征就不变，比值可信。
           / 本轮一度因为忽略这个地板，得出「借 R 的算法改造无收益」的错误结论。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a timing harness on a named 950 board in which a 64-element scan and a 1 000 003-element
           scan measure times differing by more than the variance floor — the dispatch floor would then
           not dominate small kernels there, upstream's floor would be a property of their harness
           rather than of the measurement path, and the rule this entry carries would need its harness
           named before it applies.
```

# 0418 · A thirty-microsecond dispatch floor hid a real speed-up, and upstream published the wrong conclusion it caused

## 1 · Claim
Upstream asserts that its local timing path — a custom operator dispatched through Python — has a floor
of about 30 µs, evidenced by a 64-element case and a 1 000 003-element case both measuring 30 µs, so
that a small kernel's real cost is entirely absorbed by dispatch overhead. Upstream asserts two
workarounds for A/B comparisons under that floor: device-side timing through `cann-bench`, at about six
minutes per round, or scaling the row count `M` by eight to ten times while holding each row's `R`,
dtype and `dim` fixed, on the reasoning that the per-row cost profile is unchanged so the *ratio*
remains trustworthy. Upstream asserts that it ignored this floor during the round being documented and
consequently reached a wrong conclusion — that restructuring the algorithm to borrow the reduction axis
across cores bought nothing. Not established here.

## 2 · The wrong branch this removes
An instrument floor is invisible from inside a comparison. Two builds are timed, both read 30 µs, the
ratio is 1.00, and the honest-looking conclusion is "no improvement" — which is what upstream reached
and published as a retraction. Nothing about that measurement is careless: the runs happened, the
numbers are real, and the ratio is arithmetically correct. What is wrong is the **scope**: the
measurement covers dispatch plus kernel, and the sentence it was used to support was about the kernel.
This book has that failure species on file as a measurement whose scope does not cover the sentence's
scope, and this is the instance in which the two builds *both* sat under the floor, so no amount of
repetition would have separated them.

The second wrong branch is the one the fix invites. `把 M 放大 8~10 倍` sounds like "make the problem
bigger", and an agent that scales the wrong dimension destroys the comparison it is trying to save.
Upstream is precise about which: `每行的 R/dtype/dim 不变` — hold the reduction length, the element
type and the axis, and multiply only the row count. That is what keeps the per-row cost profile
constant so the ratio survives. Scaling `R` instead changes which template is selected
(`0134`), changes the number of UB chunks, and can cross the borrow-R trigger — three confounds that
turn a floor problem into an unattributable one.

## 3 · Ground / Source
`reference/scan/templates/usage_guide.md:189-194`, in full:

```
### 计时方法：本地测量有 ~30 µs 的地板

torch 自定义算子经 python 派发，`n=64` 与 `n=1000003` 都测得 30 µs——小 kernel 的真实
耗时完全被派发开销吞掉。做微优化 A/B 时要么用 cann-bench 的设备侧计时（一轮约 6 分钟），
要么**把 M 放大 8~10 倍**再测：每行的 R/dtype/dim 不变，每行的开销特征就不变，比值可信。
本轮一度因为忽略这个地板，得出「借 R 的算法改造无收益」的错误结论。
```

The evidence for the floor is the strongest kind available for this claim and is worth naming as a
pattern: **two cases four orders of magnitude apart in work, measuring the same time.** `n = 64` and
`n = 1000003` differ by a factor of 15 625 in elements; a measurement that returns 30 µs for both is
not measuring elements. That is a positive demonstration of an instrument's floor rather than an
assertion of one, and it is reusable — the same two-point test detects a floor in any harness, and it
is cheap.

The retracted conclusion is the part with the most transfer value. `借 R 的算法改造无收益` — borrowing
the reduction axis across cores buys nothing — was wrong, and the same shelf carries the numbers that
show how wrong. The 1D case `[1000003]` is reported at 2002 µs before the restructure and, after it,
at three different figures in three files of this one shelf (`0420`), all between 34 µs and 59 µs. So
the change was worth roughly 34× to 59×, and the floor reported it as zero. A floor does not merely
add noise; it clamps, and a clamped comparison of two clamped numbers reads as a clean null result.

The workarounds are asymmetric in cost and upstream says so: device-side timing is authoritative and
takes about six minutes per round; the `M`-scaling trick is fast and yields a *ratio*, not a time. That
distinction matters for what each can support. A ratio from scaled `M` can say "A is 1.6× B"; it cannot
say "A takes 9 µs", because the per-row time was never isolated. This book records the general form of
that rule at `0009` (no metric has an absolute pass line; the verdict is before-versus-after) and at
`0010` (every case captured alone, with the profiler as truth and the simulator qualitative only).

Two further notes on scope. First, the floor is a property of **this measurement path** — a custom
operator behind Python dispatch — not of the hardware, and upstream states the mechanism
(`经 python 派发`). A different harness has a different floor, possibly much lower, which is why §4's
first arm re-derives it rather than adopting 30 µs. Second, the `一轮约 6 分钟` figure is this shelf's
only statement of measurement *cadence*, and it is what makes the trade real: at six minutes a round,
an exhaustive sweep is not free, and the `M`-scaling shortcut exists because of that budget rather than
because it is better.

The retraction is one of three self-reported wrong conclusions this shelf publishes, and the set is
worth citing together as an evidence-culture exemplar: this one (a wrong null from an instrument
floor), `cum_lane_parallel_scan.md:42` (`换了扫描算法，比较类型的选型必须重测，旧结论不会自动跟着算法
迁移`), and `usage_guide.md:50-51`, where a row of the shelf's own optimisation table is marked as
having been overturned by a later row (`注意倒数第三行推翻了第五行`). Registered as `C-950td-023` for
the third of these, since a table that contradicts itself in place is a contradiction rather than a
lesson.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. This entry is
about an instrument, so the procedure characterises the instrument before it measures anything with it.
That ordering is the content.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved.

**Arm 1 — re-derive the floor rather than adopting it.** Build one scan kernel and time it through each
available path: the Python-dispatched custom-operator path upstream used, a direct C++ launch, and
`msprof` device-side timing. At each, run `n ∈ {64, 1024, 16384, 262144, 1000003}` — a ladder spanning
upstream's two points — 30 in-process and 5 fresh-process runs each. Plot time against `n` per path.
The floor is where the curve goes flat; report it per path, with its value, rather than assuming 30 µs
transfers to this harness.

**Arm 2 — the two-point floor test, as a reusable check.** From arm 1's data, compute
`t(64) / t(1000003)` per path. Upstream's observation is that this ratio is ≈ 1 on the dispatched path.
Report it for all three paths. A path where the ratio is ≈ 1 cannot be used for any A/B below its
floor, and that statement is the deliverable — this arm produces a *gate*, not a number.

**Arm 3 — does the `M`-scaling workaround preserve the ratio?** Take two builds known to differ (the
Kogge-Stone and lane-parallel scans, which the shelf measures at 1.54× and 1.62× on a `1152×1024` case)
and time both at `M` and at `8M` and `10M`, holding `R`, dtype and `dim` fixed, on the dispatched path
and on the device-side path. If the ratio measured at `8M` on the dispatched path agrees with the ratio
measured at `M` on the device-side path within the variance floor, the workaround is validated. If it
does not, the shortcut is unsound and the six-minute path is the only option — which is a finding with
real cost consequences.

**Arm 4 — the retracted conclusion, re-run.** Build the borrow-R restructure and its predecessor at
`[1000003]` and time both on the device-side path. Upstream's three published figures put the result
between 34 µs and 59 µs against a 2002 µs baseline (`0420`). Reproduce the *direction* and report where
in that range this board lands. This is the arm that shows the floor's cost: the same comparison on the
dispatched path should read as a null.

Refuses to assume: that a free die stays free; that a die may be substituted; that 30 µs is this
harness's floor (arm 1 re-derives it); that a flat region of the curve is a floor rather than a real
plateau (the three-path comparison is what distinguishes them — a real plateau appears on every path,
a dispatch floor does not); that the `M`-scaling workaround is valid (arm 3 is the test, not the
assumption); that `cann-bench` and `msprof` measure the same interval (both are recorded and any
difference is reported rather than reconciled).

## 5 · Checker — acceptance declared before the run
Verdict `floor(path)` = the largest `n` at which median time is within the variance floor of
`median time at n = 64`, per path. Declared before the run: this entry is **supported** iff
`floor(dispatched) ≥ 262144` — the dispatched path cannot resolve kernels an order of magnitude apart
in work — **and** `floor(device_side)` is at least two ladder rungs lower, so the recommended path
actually resolves what the other cannot. The OVERTURN fires iff `t(64)` and `t(1000003)` differ by more
than the variance floor on the dispatched path: there is then no floor to warn about on this harness.

Verdict `ratio_preserved` from arm 3: true iff
`|ratio(8M, dispatched) − ratio(M, device_side)| ≤ floor`. Declared now because it decides whether the
cheap workaround may be used at all, and a false result makes this entry's advice more restrictive
rather than less.

Verdict `borrow_r_gain` from arm 4 = median `t(before)` / median `t(after)` on the device-side path,
and the same ratio on the dispatched path. Upstream's retraction predicts the first is large and the
second ≈ 1. Both are reported; the pair is the entry's demonstration.

The exit code is not the verdict — every run in every arm completes successfully, which is precisely
the problem this entry documents. Three guards. First, no time is reported without its variance floor
from the declared 30 in-process and 5 fresh-process runs; a floor study whose points carry no
uncertainty cannot distinguish a flat curve from a noisy one. Second, **the input that makes this
checker go red**: arm 1 includes `n = 16777216`, far above any plausible dispatch floor, where **all
three paths must agree** on the time within a factor of two. If the paths disagree there, they are not
measuring the same work and no cross-path comparison in arms 2–4 is interpretable — a floor study whose
only outcome is "the paths differ" cannot separate an instrument floor from three different
instruments. Third, every reported ratio names the path it was taken on and the `n` or `M` it was taken
at; a ratio without both is untestable, and the whole point of this entry is that ratios taken under a
floor look identical to ratios taken above one.

## 6 · Evidence
NOT YET RUN by us — no readout of ours exists. Nothing in this file is our measurement. Upstream's
figures are upstream's: a ~30 µs floor, two case sizes measuring the same time, a six-minute round, and
an 8–10× scaling factor, none carrying a board, a repetition count, a variance, or a statement of which
timer was read. The factor 15 625 between upstream's two case sizes is arithmetic performed here
(`1000003 / 64`). The 34×–59× range attributed to the retracted conclusion is arithmetic on upstream's
own published figures, which `0420` records as three mutually inconsistent numbers for one case.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. The entry does not establish that any harness has a 30 µs floor — it
records that upstream states one for its Python-dispatched path and gives a two-point demonstration.
It does not establish that the floor is dispatch overhead rather than some other fixed cost; upstream
names the mechanism and nothing here tests it. It does not establish that the `M`-scaling workaround
preserves ratios (§4 arm 3 is the test, and this entry does not assume its result). It does not
establish the six-minute cadence, which is a property of upstream's `cann-bench` configuration. It does
not establish the borrow-R gain: `0420` records that this shelf publishes three different values for it,
and this entry cites the range only to show what the floor concealed. It does not establish that any
conclusion other than the one upstream retracted was affected. It says nothing about which scan
template is right for any shape (`0134`, `0135`), nor about the bank-conflict rule (`0419`). No board
token appears anywhere in the scan family on either shelf, and the only hardware name in the shelf
describes a different operator's core-count defect; BOARD is `family-claimed(unverified)`, and §4 names
950PR/950DT only as where our run would happen. Nothing here is established for any 910-family board.
