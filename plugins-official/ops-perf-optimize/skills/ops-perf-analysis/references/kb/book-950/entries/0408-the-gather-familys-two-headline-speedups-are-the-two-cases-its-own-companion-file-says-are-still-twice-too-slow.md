```
ID:        0408-the-gather-familys-two-headline-speedups-are-the-two-cases-its-own-companion-file-says-are-still-twice-too-slow
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured by us
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/gather/guide.md:116 —
           "| **实测** | torch.gather P4(33.5M int32): 128ms→3.6ms (**35.7×**)；P6(67.1M int8):
           231ms→5.3ms (**43.2×**) |"
SOURCE:    same shelf, reference/gather/templates/gather_elements_v2_transpose.md:79-83 —
           "case4：x=`[8192,8192]` int32，index/output=`[4096,8192]`，dim=0。
           / - baseline SIMT：3581.81 us。 / - 强制进入单-kernel内部 Transpose：3634.21 us，约慢 1.46%。
           / - 官方 CANNBench：1677.7 us，路径记录为物理 `Transpose×3 + GatherElementsV2`。" ;
           :96-100 — "case6：x=`[16384,8192]` int8 … - baseline SIMT：约 5.35 ms。 …
           - 官方路径记录为物理 `Transpose×3 + Gather`，约 2.10 ms。" ;
           :92 — "此前没有优化不是 device 模板缺少 `carryNumAlign`，而是把官方物理 Transpose 路径
           误判成了内部模板路径。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a run on a named 950 board of upstream's case4 shape in which the SIMT template matches or
           beats a physical `Transpose×3 + last-axis Gather` sequence within the variance floor. The
           1677.7 µs figure would then not be reproducible as a better path, the guide's headline would
           be the best known result after all, and this entry's central claim would be wrong.
```

# 0408 · The gather family's two headline speed-ups are the two cases its own companion file says are still twice too slow

## 1 · Claim
Upstream asserts, in the gather family's index, two measured speed-ups for the SIMT scalar-parallel
template, with case identity: a 33.5 M-element int32 `torch.gather` from 128 ms to 3.6 ms (35.7×), and
a 67.1 M-element int8 one from 231 ms to 5.3 ms (43.2×). Upstream asserts, in a companion file in the
same directory, per-case detail for two cases it calls case4 and case6, including for each a SIMT
baseline, a result for the in-kernel transpose template, and an official CANNBench figure attributed to
a **physical** `Transpose×3` sequence — 3581.81 µs, 3634.21 µs and 1677.7 µs for case4; about 5.35 ms,
"never entered Transpose", and about 2.10 ms for case6. Upstream asserts that its previous failure to
optimise case4 was not a missing device-template feature but a misattribution: the official physical
`Transpose` path's timing had been credited to the in-kernel template. Upstream does not state that the
guide's two headline cases and the companion file's case4 and case6 are the same two cases. Not
established here.

## 2 · The wrong branch this removes
The index page is where an agent starts, and it reports the family's evidence as two large wins. An
agent that reads `35.7×` and `43.2×` concludes that SIMT is the answer for large non-last-axis
`torch.gather`, and it is not wrong about the direction — SIMT really is 35× better than whatever the
128 ms baseline was. It is wrong about the destination. On the same two cases, four files away, the
same shelf records a path that is **2.1× and 2.5× faster again**, and records it as the official
CANNBench result rather than as an aspiration.

The identification is an inference and is marked as one throughout this entry, but it is a tight one.
`P4(33.5M int32)`: case4's output is `[4096, 8192]` = 33 554 432 elements, int32. `P6(67.1M int8)`:
case6's output is `[8192, 8192]` = 67 108 864 elements, int8. Case4's SIMT baseline of 3581.81 µs
rounds to the guide's `3.6ms`, and `128 / 3.582 = 35.7`. Case6's `约 5.35 ms` rounds to `5.3ms`, and
`231 / 5.347 = 43.2`. Four independent coincidences per case; upstream never writes the equation, and
that silence is the trap. The two documents are internally consistent and mutually damning, and only a
reader who opens both sees it.

So the wrong branch is: **adopt the family's headline result as the target, stop, and leave a factor of
two on the floor** — while believing the number came with case identity and therefore needs no further
questioning. Case identity is what makes the number trustworthy; it is not what makes it optimal.

The second wrong branch is the opposite over-correction: reading `官方 CANNBench：1677.7 us` as
licence for the in-kernel transpose template, which is what the same file is at pains to prevent. The
1677.7 µs is a **physical** `Transpose×3 + GatherElementsV2` — three separate framework-level operators
plus a last-axis gather — not the single-kernel template the file documents. Upstream forced case4
through the in-kernel template and measured **3634.21 µs, slower than the SIMT baseline by 1.46 %**.
The two transposes share a word and nothing else.

The third wrong branch this removes is the one upstream itself took and then published. Its stated root
cause is worth reading twice: `此前没有优化不是 device 模板缺少 carryNumAlign，而是把官方物理
Transpose 路径误判成了内部模板路径。` — the earlier diagnosis blamed a missing feature in the device
template, and the real cause was that a fast number produced by path A had been credited to path B. That
is a **two-point comparison of two different builds carrying no attribution**, self-reported and
retracted in the shipped document. An agent doing performance work on this family will meet the same
shape: two numbers, two paths, and no record of which kernel sequence produced which. Upstream's own
mitigation is stated as a verification-list item — `路由变化必须记录实际 kernel 序列` (`:117`) — and it
is the transferable rule here.

## 3 · Ground / Source
The index page's evidence row, `ascendc-performance-best-practices/reference/gather/guide.md:108-116`,
in its table:

```
### 2. SIMT 标量并行（通用兜底）

| 项 | 内容 |
|----|------|
| **适用** | 所有 Gather 场景（散点读，无连续性假设） |
| **核心策略** | 2048 SIMT 线程并行，每线程直接 GM 标量读 index + x，写 y；fast-division 替代 div/mod |
| **UB 使用** | 无（直接 GM→GM） |
| **代码** | [.template](templates/dav310/gather_simt.template) · [.md](templates/simt_gather.md) |
| **实测** | torch.gather P4(33.5M int32): 128ms→3.6ms (**35.7×**)；P6(67.1M int8): 231ms→5.3ms (**43.2×**) |
```

That is the family's entire measured record on its index page: two ratios, two element counts, two
dtypes. No board, no core count, no tool, no repetition count, no variance. `0148` records that the
analysis shelf's gather family is bare of measurements entirely, so these two rows are the whole of
what either shelf publishes as gather evidence up front.

The companion file, `reference/gather/templates/gather_elements_v2_transpose.md:77-92`, in full:

```
## 6. case4 为什么没有优化

case4：x=`[8192,8192]` int32，index/output=`[4096,8192]`，dim=0。

- baseline SIMT：3581.81 us。
- 强制进入单-kernel内部 Transpose：3634.21 us，约慢 1.46%。
- 官方 CANNBench：1677.7 us，路径记录为物理 `Transpose×3 + GatherElementsV2`。

以 ops-nn 的 48 核成本代理计算：

direct ≈ 8192*8192*4 + 4096*8192*4 = 402.7 MB
inside ≈ 4096*8192*4 + 48*128*(4096*4 + 8192*4) = 436.2 MB

`direct > inside` 不成立，因此内部 Transpose 应被拒绝。此前没有优化不是 device 模板缺少 `carryNumAlign`，而是把官方物理 Transpose 路径误判成了内部模板路径。
```

Every number in that block is internally re-derivable, and re-deriving them at drafting time is how
this entry checks that upstream's arithmetic supports upstream's conclusion:

- `8192 × 8192 × 4 = 268 435 456`; `4096 × 8192 × 4 = 134 217 728`; sum `402 653 184` B = **402.65 MB**
  (decimal), which upstream rounds to `402.7 MB`. ✓
- `48 × 128 × (4096×4 + 8192×4) = 6144 × 49 152 = 301 989 888`; plus `134 217 728` gives
  `436 207 616` B = **436.21 MB**, upstream's `436.2 MB`. ✓
- The `128` in that product is `workspaceLen`, and it re-derives from the route header's
  `min(kCachelineElementsBytes / xDtypeSize, …) = min(512 / 4, …) = 128` (`0407`, `:62-63`). ✓
- `402.65 < 436.21`, so `direct > inside` is false and the gate rejects — matching upstream's
  conclusion and matching the measurement, since the forced internal path was indeed slower. ✓
- `(3634.21 − 3581.81) / 3581.81 = 1.463 %`, upstream's `约慢 1.46%`. ✓

Five checks, five agreements. That matters: this is a case where a model, a measurement and a stated
conclusion were published together and are mutually consistent, which is rare in this repository and is
why the case is worth carrying rather than merely noting.

The unflattering ratio the family does not compute: `3581.81 / 1677.7 = 2.135`. The path the guide
advertises as a 35.7× win is 2.13× slower than the path the same shelf records as official for that
case. This entry performs that division; upstream does not.

case6, `:94-102`:

```
## 7. case6 检查结论

case6：x=`[16384,8192]` int8，index/output=`[8192,8192]`，dim=0。

- baseline SIMT：约 5.35 ms。
- 当前内部模板没有 Byte1 `TransDataTo5HD` 实现，实验分支实际未进入 Transpose。
- 官方路径记录为物理 `Transpose×3 + Gather`，约 2.10 ms。

因此 case6 应路由到物理 Transpose（平台可用时），不能把文档中的 2B/4B 内部模板宣称为 int8 优化方案。若要新增 Byte1 内部模板，必须作为新实现单独做精度、编译和全量 A/B，不能只改 dtype 门控。
```

`5.35 / 2.10 = 2.548`, again computed here and not upstream. The second bullet is its own finding: an
experimental branch that *appeared* to test the internal transpose on int8 never entered it, because no
1-byte `TransDataTo5HD` exists — a run that produced a number without exercising the thing it was
supposed to test. Upstream caught this and says so.

The prohibitions the two cases produced, `:104-110`:

```
## 8. 禁止的选型方式

- `dim != last` 就进入内部 Transpose。
- 只检查 128KB transpose buffer/UB 是否放得下。
- 用 cache-line 浪费的理论上界断言 Transpose“恒优”。
- 把物理 Transpose 的官方耗时归因到单-kernel内部模板。
- 在没有 Byte1 device 实现时让 int8 进入内部路径。
```

The second bullet retires exactly the test the analysis shelf's `needTrans` computes — `0148` records
that `needTrans` is "usually the binding one" and that the two fixed transpose buffers demand 128 KiB
— and the fourth names the attribution error the same file confesses. A prohibition list written from
one's own retracted diagnoses is the honest form; this book carries two other instances (`0159`'s
`extentsMatch` omission, `0328`'s falsification list of six retired changes), and this is the third.

The verification list that follows, `:112-117`, converts each into a test, including two named cases
that must land on named routes:

```
## 9. 验证清单

- 路由单测覆盖：last dim、内部可用、成本拒绝、dtype 拒绝、物理 Transpose 不可用。
- case4 必须命中 `PHYSICAL_TRANSPOSE`，不能命中 `INTERNAL_TRANSPOSE`。
- case6 必须因 int8 拒绝内部模板；物理路径能力与成本门控通过时命中 `PHYSICAL_TRANSPOSE`。
- 对所有受影响 case 做精度回归和 CANNBench A/B；路由变化必须记录实际 kernel 序列。
```

Those are checklist items that can fail — the counter-species to this project's F5 — and the last
clause is the general repair for the misattribution.

Registered as `C-950td-013`: the index page's headline evidence and the companion file's per-case
detail describe the same two cases and imply opposite recommendations, and neither file references the
other's numbers.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. Upstream's
numbers are upstream's; this procedure exists to reproduce the *ranking*, which is the part this entry
depends on, and to close the identification §2 marks as an inference.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs, IQR
over median, beside every figure. Upstream reports a 1.46 % difference; without a floor this entry
cannot say whether that is a result or noise, and establishing the floor is therefore the first
obligation, not a formality.

**Arm 1 — the three paths on case4, built from upstream's own files.** Shape exactly as stated:
`x = [8192, 8192]` int32, `index = y = [4096, 8192]`, `dim = 0`. Build (a) SIMT from
`dav310/gather_simt.template`, (b) the in-kernel transpose from
`dav310/gather_elements_v2_transpose.template`, forced past the route gate, and (c) a physical sequence
— `Transpose(x)`, `Transpose(index)`, last-axis gather, `Transpose(y)` — assembled from available
operators, with each stage's wall time recorded separately so the sum is attributable. One compiler
pin, three md5s, host echo of the kernel sequence actually launched for each arm (upstream's own
`路由变化必须记录实际 kernel 序列`). Elementwise comparison against a CPU reference on all three.

**Arm 2 — case6, and the branch that did not bite.** `x = [16384, 8192]` int8,
`index = y = [8192, 8192]`, `dim = 0`. Build SIMT and the physical sequence. Then attempt the in-kernel
transpose and record **which** of the two outcomes occurs: a compile refusal (no 1-byte
`TransDataTo5HD`) or a silent fall-through to another path. Upstream reports the second — a branch that
ran without entering the code under test — and confirming which failure mode a later reader will meet
is the point of the arm. Retained explicitly because it is expected to produce no transpose measurement
at all; "the arm that did not bite" is kept because it did not.

**Arm 3 — close the identification.** Run the SIMT arm on both shapes and compare its median against
the guide's `3.6 ms` and `5.3 ms`. If both land within the floor, the inference that P4 = case4 and
P6 = case6 is supported by measurement rather than by rounding coincidence. This is cheap and it
converts §2's central argument from a reading into an observation.

**Arm 4 — the 128 ms baselines.** Neither file says what the `128ms` and `231ms` are. Attempt the two
obvious candidates — a naive scalar single-core gather, and the framework default path before this
work — and record which, if either, reproduces them. If neither does, that is the finding: the
denominators of the family's two headline ratios are unidentified, and a ratio whose denominator cannot
be reconstructed is not a reusable figure.

Refuses to assume: that a free die stays free; that a die may be substituted; that upstream's
`48 核` matches this board (`coreNum` is queried and echoed, per `0141`/`0207`, and a different value
changes the cost proxy's `inside` term directly); that CANNBench and `msprof` measure the same
interval (both are recorded and the difference reported rather than reconciled); that the physical
sequence available here is the one upstream benchmarked; that a build labelled with a path ran it.

## 5 · Checker — acceptance declared before the run
Verdict `rank(case)` = the ordering of the three (case4) or two-plus-one (case6) paths by median
`aiv_time`, with the floor. Declared before the run: this entry is **supported** iff
`rank(case4) = physical < SIMT < internal` and `rank(case6) = physical < SIMT`, i.e. the physical
sequence is fastest on both. The OVERTURN fires iff `physical ≥ SIMT` within the floor on case4 — the
1677.7 µs would then not reproduce as a better path and the guide's headline would be the best known
result.

Verdict `internal_margin` = `(median internal − median SIMT) / median SIMT` on case4, with the floor.
Upstream reports `+1.46 %`. Declared now: a floor wider than 1.46 % means upstream's figure is not
resolvable by this instrument, and the honest report is "not distinguishable", **not** agreement. That
declaration is made before the floor is known precisely so it cannot be adjusted afterwards.

Verdict `identity_confirmed` from arm 3: true iff SIMT's median on both shapes falls within the floor
of the guide's `3.6 ms` / `5.3 ms`.

Verdict `baseline_found` from arm 4 ∈ {`naive_scalar`, `framework_default`, `neither`}.

The exit code is not the verdict: a gather with wrong indices exits 0 and is fast, and on case6 one arm
is expected not to run at all. Three guards. First, all arms are compared elementwise against a CPU
reference and the checker fails red if any comparison did not execute; an arm that did not run is
reported `did_not_run` with its reason, never folded into a ranking as a missing row. Second, **the
input that makes this checker go red**: arm 1 includes a fourth build — the in-kernel transpose on a
shape the route gate *admits* (`0407` arm 3's admitted case) — which must come out **faster** than SIMT
there. If the internal template loses everywhere, including where its own gate admits it, then the
build is broken rather than the template, and case4's `+1.46 %` is uninformative. A study whose only
possible outcome is "the internal path always loses" cannot distinguish a correctly-rejecting gate from
a mis-built kernel. Third, every arm reports its echoed kernel sequence, its md5 and its floor; an arm
missing any of the three is untestable, and the physical sequence additionally reports per-stage times
so that a sum is never presented as a single measurement.

## 6 · Evidence
NOT YET RUN by us — no readout of ours exists. Nothing in this file is our measurement. The figures in
§3 are upstream's, reported with case identity and without board, tool, core count or repetition count.
What was performed here, on paper at drafting time, is arithmetic **on upstream's own numbers**: the
five re-derivations of upstream's cost proxy and its 1.46 % (all five agreed), and the two ratios
upstream does not compute (`3581.81 / 1677.7 = 2.135`, `5.35 / 2.10 = 2.548`). Arithmetic on a
published number is not a measurement of the machine, and the identification of P4 with case4 and P6
with case6 is an inference from four coincidences per case, not a statement either document makes.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. The entry does not establish any of upstream's six timings, and does not
establish that they were taken on the same board, tool or build as each other — `官方 CANNBench` and
the SIMT baselines are attributed to different instruments in the same list, which is precisely the
comparison this book treats as unattributable until the variable is isolated. It does not establish
that P4 is case4 or P6 is case6; §4 arm 3 exists to settle that and until it runs the identification is
this entry's inference and its weakest joint. It does not establish that the physical `Transpose×3`
path is available on any board, only that upstream records a figure for it; `0407` records that its
profitability is a caller-supplied boolean nobody computes. It does not establish what the `128ms` and
`231ms` baselines were — nothing in either file says, and a speed-up whose denominator is unidentified
cannot be transferred to another baseline. It does not establish the `48 核` core count, the
`carryNumAlign` claim it reports as retracted, or that a 1-byte `TransDataTo5HD` is absent from every
toolkit (upstream says the current template lacks it, which is a statement about the template). It does
not extend to `PER_SLICE` gathers, which route entirely differently (`0147`), or to `dim == last`,
which is `0411`. No board token appears anywhere in the gather family on either shelf, and no chip is
named beside any of these six figures, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT
only as where our run would happen. Nothing here is established for any 910-family board.
