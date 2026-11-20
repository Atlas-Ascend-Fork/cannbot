```
ID:        0301-l1-buffer-num-is-the-largest-integer-whose-doubled-buffer-still-fits-l1-and-that-lands-at-eighty-percent
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
           # the matmul family is marked DAV_3510 in the shelf's SKILL.md table; not one of the
           # family's seven files names a chip (see 0347). No board is named by the evidence.
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/pingpong_design.md:163 —
           "**kL1=768 (L1_BUFFER_NUM=3) 的选取原则：尽可能用满 L1 空间**。在 pingpong 双缓冲
           （`PINGPONG_NUM=2`）约束下，`L1_BUFFER_NUM` 应取满足 `2 × singleBufferSize ≤ l1_size` 的
           **最大整数值** ... `L1_BUFFER_NUM=4` 时双 buffer 557,056 bytes 溢出；`L1_BUFFER_NUM=3` 时
           双 buffer 417,792 bytes ≤ 524,288 bytes（L1 利用率 80%），是合法最大值"
SOURCE:    same file:178 — "总 L1 占用 = PINGPONG_NUM × (aL1OneBuffer + bL1OneBuffer +
           scaleAL1OneBuffer + scaleBL1OneBuffer) ≤ L1_SIZE (512KB)"
INDEX:     none — nothing measured; see SOURCE. The capacity the rule is solved against is
           re-derivable by file read: grep -h '^l1_size=' $ASCEND_HOME_PATH/aarch64-linux/data/platform_config/Ascend950*.ini | sort -u
OVERTURN:  a measured matmul on a named 950 board where the largest legal `L1_BUFFER_NUM` is slower
           than a smaller one at the same shape — the "fill L1" principle would then be an
           unsupported heuristic rather than a rule, and the search would need a cost model instead
           of a capacity test.
```

# 0301 · `L1_BUFFER_NUM` is the largest integer whose doubled buffer still fits L1, and that lands at 80 %

## 1 · Claim
Upstream asserts a selection rule for `L1_BUFFER_NUM`, the factor by which one L1 buffer's K extent
exceeds `baseK`: under ping-pong double buffering (`PINGPONG_NUM = 2`) it is the largest integer
satisfying `2 × singleBufferSize ≤ l1_size`. Upstream asserts the stated reason — cover as much K
per buffer as possible, so the outer loop iterates fewer times and pays less pipeline start/stop
overhead — and gives a worked case at `baseM = baseN = 256, baseK = 256` for an MXFP4 shape
`M=1024, N=2048, K=4096`: `L1_BUFFER_NUM = 3` yields 417,792 B against a 524,288 B L1 (80 %
occupancy) and is the legal maximum, while `L1_BUFFER_NUM = 4` yields 557,056 B and overflows. Not
established here.

The L1 budget inequality upstream solves is stated separately and is the load-bearing half:
`PINGPONG_NUM × (aL1OneBuffer + bL1OneBuffer + scaleAL1OneBuffer + scaleBL1OneBuffer) ≤ L1_SIZE`.

## 2 · The wrong branch this removes
Without this entry an agent treats `L1_BUFFER_NUM` and `stepK` as the same knob and lets the tiling
generator set it. They are not the same knob (`0303`), and the generator's value is constrained to
powers of two by its own doubling search (`950:0109`), so it can never emit 3 — the value this
family's own worked case says is correct. The agent then either accepts a 2 (leaving 27 % of L1
unused and doubling the outer-loop trip count) or forces a 4 and gets an L1 overflow that surfaces
as a simulator error or a precision failure, not as a capacity message.

The second wrong branch is subtler and is why the arithmetic is re-derived in §3 rather than
quoted. `singleBufferSize` here is *not* `A + B`: it includes both scale buffers, and for MXFP4 the
A/B terms are half-byte packed (`>> 1`). An agent that estimates the budget as
`2 × baseM × kL1 × sizeof(dtype) × 2` gets a number that is wrong in two directions at once and
happens to be close enough to look right.

## 3 · Ground / Source
`pingpong_design.md:163`, in full:

```
5. **kL1=768 (L1_BUFFER_NUM=3) 的选取原则：尽可能用满 L1 空间**。在 pingpong 双缓冲
（`PINGPONG_NUM=2`）约束下，`L1_BUFFER_NUM` 应取满足 `2 × singleBufferSize ≤ l1_size` 的**最大
整数值**，使每个 buffer 覆盖尽可能多的 K 范围以减少外层循环迭代次数和流水起停开销。以
`baseM=baseN=256, baseK=256` 为例：`L1_BUFFER_NUM=4` 时双 buffer 557,056 bytes 溢出；
`L1_BUFFER_NUM=3` 时双 buffer 417,792 bytes ≤ 524,288 bytes（L1 利用率 80%），是合法最大值。
```

The worked budget, `:181-191`:

```
以 M=1024, N=2048, K=4096, baseM=baseN=256, kL1=768 为例：
- aL1OneBuffer = 256 × 768 / 2 = 98,304 bytes（FP4 半字节）
- bL1OneBuffer = 256 × 768 / 2 = 98,304 bytes
- scaleAL1OneBuffer = 256 × ⌈768/32⌉ = 256 × 24 = 6,144 bytes
- scaleBL1OneBuffer = 256 × 24 = 6,144 bytes
- 单 buffer 合计 = 208,896 bytes
- 双 buffer 合计 = 417,792 bytes ≤ 524,288 bytes ✅

若 `L1_BUFFER_NUM = 4`（kL1 = 1024）：
- 单 buffer 合计 = 2 × (256 × 1024 / 2) + 2 × (256 × 32) = 278,528 bytes
- 双 buffer 合计 = 557,056 bytes > 524,288 bytes ❌ **溢出**
```

Re-derived, every term. `kL1 = 256 × 3 = 768` ✓. `256 × 768 / 2 = 98304` ✓ (twice).
`⌈768/32⌉ = 24`, `256 × 24 = 6144` ✓ (twice). `98304 × 2 + 6144 × 2 = 208896` ✓.
`208896 × 2 = 417792` ✓. `417792 / 524288 = 79.7 %`, stated as 80 % ✓.
At `L1_BUFFER_NUM = 4`: `kL1 = 1024`, `2 × (256 × 1024 / 2) = 262144`, `⌈1024/32⌉ = 32`,
`2 × (256 × 32) = 16384`, sum `278528` ✓, doubled `557056` ✓, and `557056 > 524288` ✓.
The arithmetic is internally consistent throughout, which is not the norm in this shelf.

The capacity `524288` is the only place any matmul file in this shelf gives an L1 size, and it is
given as a literal. Two neighbouring files in the same family write the same constant with a wrong
unit — `fullload_design.md:52` and `scale_coalescing_design.md:117` both head an ASCII diagram
`L1 地址空间（L1_SIZE = 524 KB）`, where 524288 B is 512 KiB, not 524 KB. The inequalities in those
same files (`fullload_design.md:135`, `scale_coalescing_design.md:93`) use `524288 B` correctly, so
the slip is in the prose label only. Recorded here rather than spent as an entry.

`950:0212` carries the installed-ini value `l1_size=524288` for DAV_3510 separately; this entry does
not import it as evidence, it only notes that the literal upstream hard-codes here is the value that
entry's second origin reports.

## 4 · Procedure
Proposed, runnable later on a named 950 board (`950PR` or `950DT`; a run on one establishes nothing
about the other). Never run in this phase.

Arm 1 — the capacity test itself. Build the same MXFP4 matmul at `M=1024, N=2048, K=4096,
baseM=baseN=256, baseK=256` at `L1_BUFFER_NUM ∈ {1, 2, 3, 4}`, holding everything else fixed.
Record: does it build, does it launch, does it pass precision, and what `l1_size` the platform
reports. Prediction: 4 fails, 3 is the largest that passes.

Arm 2 — the *principle*, which is the part a capacity test cannot reach. Upstream's rule is not
"the largest that fits"; it is "the largest that fits, because filling L1 is good". Time all the
`L1_BUFFER_NUM` values that pass Arm 1, at three K lengths (`K = 1024, 4096, 16384`), and record
kernel time, MTE2 segment time and outer-loop trip count for each. The rule predicts monotone
improvement with `L1_BUFFER_NUM`. The rule is *wrong* if any smaller value wins, which is the
plausible failure: a larger `kL1` also lengthens the ping-pong period and can starve the MTE1→CUBE
side.

Arm 3 — the budget formula, independent of both. Instrument the host tiling to print
`aL1OneBuffer`, `bL1OneBuffer`, `scaleAL1OneBuffer`, `scaleBL1OneBuffer` and their doubled sum for
each `L1_BUFFER_NUM`, and compare against §3's re-derivation term by term. This is the arm that
catches a formula that is right about the total and wrong about a term.

Device selection: operator names the index; the probe echoes it with `compiler/version.info`;
occupancy checked before the run (shared machine, ≤ 4 dies); no die substituted. The procedure
refuses to assume that `l1_size` is 524288 — it queries it (`950:0207`) and reports it beside every
verdict, because the whole rule is an inequality against that number.

## 5 · Checker — acceptance declared before the run
Verdict variable `max_legal` = the largest `L1_BUFFER_NUM` in Arm 1 that builds, launches and
passes precision. Declared before the run: pass is `max_legal == 3` **at the stated shape and
dtype**, and the entry is scoped to that shape — a different `baseM/baseN/baseK` moves the answer
and is not evidence about this one.

Verdict `monotone` = true iff Arm 2's kernel time is non-increasing in `L1_BUFFER_NUM` across
`1 … max_legal`, at every K, outside the variance floor. `monotone == false` fires the OVERTURN:
upstream's "尽可能用满 L1" is then a heuristic that this shape contradicts, and the entry is
corrected in place to state the rule as a capacity *bound* with no ordering claim inside it.

Verdict `budget_exact` = true iff every term Arm 3 prints matches §3's re-derivation exactly (not
approximately — these are integer byte counts).

The exit code is not the verdict. Two guards. First, Arm 1's "fails" must be shown to fail *for
capacity*: the failure message or the reported L1 request is recorded, and a build that fails for
an unrelated reason (a missing symbol, a tiling assertion) counts as `void`, not as `overflow`.
This is the guard that makes the checker able to go red for the right reason — the naive version of
this test cannot distinguish "L1 overflowed" from "the build was broken", and would confirm
upstream either way. Second, the variance floor is established before Arm 2 is interpreted: one
build, 30 in-process runs, 5 fresh-process runs, IQR over median, reported beside every comparison.
An 80 %-vs-60 % occupancy difference that moves kernel time less than the floor is reported as
`indistinguishable`.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Every byte count in §3 is
upstream's arithmetic, re-derived here on paper; re-deriving arithmetic is not measuring it, and
none of it has been observed on a part.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The claim is scoped to the one worked shape and dtype upstream
gives (MXFP4, `M=1024, N=2048, K=4096`, `baseM=baseN=256`, `baseK=256`); `max_legal = 3` is a
property of that budget, not of the family. The entry does not establish the *benefit* of filling
L1 — that is §4 Arm 2 and is the half most likely to fail. It does not establish `l1_size = 524288`
on any part; upstream hard-codes the literal and this entry treats it as a parameter, not a fact.
BOARD is `family-claimed(unverified)` because no file in the matmul family names a chip; the
architecture attribution comes from a single cell of the shelf's SKILL.md table (`0347`), and if
that cell is wrong every matmul entry in this block is mis-booked, which is a risk this book carries
openly rather than hides. Nothing here is established for 950DT if the run happens on 950PR, or the
reverse. Nothing transfers to the other book (RULES.md Art. 1). The relationship between
`L1_BUFFER_NUM` and the tiling engine's `stepK` is a separate claim and lives in `0303`.
