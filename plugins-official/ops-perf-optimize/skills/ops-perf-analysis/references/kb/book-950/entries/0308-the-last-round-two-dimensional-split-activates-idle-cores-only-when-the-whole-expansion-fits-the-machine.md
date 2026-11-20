```
ID:        0308-the-last-round-two-dimensional-split-activates-idle-cores-only-when-the-whole-expansion-fits-the-machine
LABEL:     knowledge
LEVEL:     L1 (core & pipe assignment)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/swat_design.md:275-290 —
           "if ((endBlockIdx_ + 1) * params.mTailTile * params.nTailTile <= AscendC::GetBlockNum())
           { ... int64_t newEndBlockIdx = endBlockIdx_ + tailOriCnt * (totalTailTile_ - 1); ...
           if (blockIdx_ > newEndBlockIdx) { mTailTile_ = 1; nTailTile_ = 1; totalTailTile_ = 1; } }"
SOURCE:    same file:249 — "机制 C 把最后一轮里**所有原 tile**（共 `tailOriCnt = endBlockIdx_ + 1`
           个）各自在 M/N 方向切成 `mTailTile_ × nTailTile_` 个子块" ; :421 — "**机制 C**：只作用于
           最后一轮；...；门槛是 `(endBlockIdx_ + 1) × totalTailTile_ ≤ blockNum_`"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured matmul on a named 950 board where the last-round re-split raises the active
           core count as claimed and does not shorten the last round outside the run spread — the
           sub-blocks would then be too small to pay for their own launch, and the mechanism's
           premise (idle cores are the cost) would be false for that shape.
```

# 0308 · The last-round two-dimensional split activates idle cores only when the whole expansion fits the machine

## 1 · Claim
Upstream asserts that in the final scheduling round only the first `endBlockIdx_ + 1` cores hold
work and the rest idle, and that SWAT's mechanism C splits **every** tile of that last round — not
only the final one — into `mTailTile_ × nTailTile_` sub-blocks, expanding the active core count to
`tailOriCnt × totalTailTile_`. Upstream asserts a single admission gate evaluated on device:
`(endBlockIdx_ + 1) × mTailTile × nTailTile ≤ GetBlockNum()`. Upstream asserts that cores beyond the
expanded range demote themselves to `1 × 1` so they do not enter the sub-block branch, and that
sub-block coordinates landing outside the parent tile return a zero shape which the kernel skips
explicitly. Upstream asserts the host-side search grows the longer side first and is bounded by both
the core count and the cube granularity (`mTileMax = min(aicNum / tailBlockCnt, ⌈baseM / CUBE_BLOCK⌉)`).
Not established here.

## 2 · The wrong branch this removes
Three specific ones, all of which produce a kernel that runs.

First, reading "tail" as "the last tile". Upstream says so directly — `这里"尾"指的是"最后一整轮
里的 tile"，不只是最末那一个` — and an implementation that splits only the final tile activates
`totalTailTile_` extra cores instead of `tailOriCnt × (totalTailTile_ − 1)`, which for upstream's
worked case is 3 instead of 15.

Second, the off-by-one in the new end index. `newEndBlockIdx = endBlockIdx_ + tailOriCnt ×
(totalTailTile_ − 1)`, not `× totalTailTile_`, because `tailOriCnt` cores were *already* active
before the split. Getting this wrong sets some cores' `round_` one too high; they then execute a
round that does not exist and read tile indices past `tileNum`.

Third, and the one that decides whether the mechanism is used at all: mechanism C and StreamK's
DP+SK attack the same pathology, and upstream states the discriminator explicitly — when
`baseM`/`baseN` are already close to the cube minimum granularity, the sub-blocks become too small
and cube launch overhead overtakes the gain, at which point DP+SK is the answer instead (`0309`).
An agent that treats "idle cores in the last round" as having one fix will pick wrongly half the
time.

## 3 · Ground / Source
The pathology and the scope of "tail", `swat_design.md:249-251`:

```
最后一轮只有 `endBlockIdx_ + 1` 个核有活，其他核空转。机制 C 把最后一轮里**所有原 tile**
（共 `tailOriCnt = endBlockIdx_ + 1` 个）各自在 M/N 方向切成 `mTailTile_ × nTailTile_` 个子块，
让总活跃核数扩展到 `tailOriCnt × totalTailTile_`。

注意：这里"尾"指的是"最后一整轮里的 tile"，不只是最末那一个。
```

The device-side activation, `:275-290`:

```cpp
if ((endBlockIdx_ + 1) * params.mTailTile * params.nTailTile <= AscendC::GetBlockNum()) {
    mTailTile_     = params.mTailTile;
    nTailTile_     = params.nTailTile;
    totalTailTile_ = params.mTailTile * params.nTailTile;

    uint64_t tailOriCnt = AscendC::Std::min(totalCnt_, endBlockIdx_ + 1);
    int64_t  newEndBlockIdx = endBlockIdx_ + tailOriCnt * (totalTailTile_ - 1);

    if (blockIdx_ > endBlockIdx_ && blockIdx_ <= newEndBlockIdx) {
        round_ += 1;  // 本来不该有活的核，现在多跑一轮
    }
    if (blockIdx_ > newEndBlockIdx) {
        mTailTile_ = 1; nTailTile_ = 1; totalTailTile_ = 1;  // 仍闲，自降避免走子块分支
    }
    endBlockIdx_ = newEndBlockIdx;
}
```

Upstream's own explanation of the `− 1`, `:293-298`, which is why §2 can state it as a trap rather
than a preference: `切分前已经有 tailOriCnt 个核活跃；切分后每个原 tile 新增 totalTailTile_ − 1 个
子块，需要 tailOriCnt × (totalTailTile_ − 1) 个新核`.

The core↔sub-block mapping, `:304-316`: `blockIdx_ / totalTailTile_` selects the parent tile,
`blockIdx_ % totalTailTile_` the sub-block, and out-of-range sub-blocks return `{0,0,0,0}` which the
kernel skips (`:81-83`, `if (Get<MNK_M>(singleShape) <= 0 || ...) return;`).

The worked example, `:324-338`, re-derived: `totalCnt = 5, blockNum = 24, mTailTile = nTailTile = 2
⇒ totalTailTile = 4`. Gate: `5 × 4 = 20 ≤ 24` ✓. `endBlockIdx = (5 − 1) % 24 = 4`, so
`tailOriCnt = min(5, 5) = 5` ✓. `newEndBlockIdx = 4 + 5 × 3 = 19` ✓. The table then assigns
blockIdx 0–3 → tile 0's four sub-blocks, 4–7 → tile 1, …, 16–19 → tile 4, and 20–23 remain idle at
`1 × 1` ✓. Active cores 5 → 20 ✓.

The host search, `:257-269`, grows the longer side first and caps each direction at
`min(aicNum / tailBlockCnt, CeilDiv(baseM or baseN, CUBE_BLOCK))`. That second term is the
cube-granularity bound §2's third branch turns on.

What upstream does **not** supply: any timing. There is no measured before/after for mechanism C
anywhere in the file, and no statement of how small a sub-block may get before launch overhead wins
— only the assertion, in the StreamK file (`streamk_design.md:8`), that such a point exists
(`子块太小、CUBE 启动开销反超`).

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — the activation arithmetic, echoed not timed. At `totalCnt = 5` with `blockNum` queried (not
assumed 24), build with mechanism C on and off and echo per core: `round_`, `endBlockIdx_`,
`totalTailTile_`, and for the last round the `(parent tile, sub-block)` pair. Check the echo against
§3's re-derivation exactly: 20 cores active, `newEndBlockIdx = 19`, cores 20…`blockNum−1` reporting
`totalTailTile_ == 1`, and no core reporting a tile index ≥ `tileNum`.

Arm 2 — does activation shorten the round? Time both builds and, separately, extract the last
round's duration from the trace (first-to-last task on the AIC lanes in that round). Mechanism C's
claim is about the last round; kernel time dilutes it by however many steady rounds precede it, so
the round duration is the primary readout and kernel time is secondary.

Arm 3 — the cube-granularity limit, which is the routing question. Repeat Arm 2 at a sequence of
shrinking `baseM`/`baseN` down to `CUBE_BLOCK`, recording where mechanism C stops paying. That
crossing point is the number upstream asserts exists and never gives, and it is what would let a
skill route between mechanism C and DP+SK (`0309`) on evidence rather than on adjectives.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, beside
every figure. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard if the die moved. Refuses to assume: that a free die stays free; that a die
may be substituted; that `GetBlockNum()` equals any literal — it is queried and echoed, and the gate
is written entirely against it (`950:0207`, `950:0217`: installed 950 SKUs span 4 to 36 cube cores,
so a gate tuned at one core count is not a gate at another).

## 5 · Checker — acceptance declared before the run
Verdict `active_cores` = the number of distinct `blockIdx_` values reporting non-empty work in the
final round. Declared before the run: pass is `active_cores == tailOriCnt × totalTailTile_` when the
gate holds, and `active_cores == tailOriCnt` when it does not.

Verdict `no_overrun` = true iff no echoed tile index reaches `tileNum` and no echoed sub-block
offset reaches its parent's extent. This is the off-by-one detector and it is a correctness verdict,
not a performance one.

Verdict `round_drop` = (last-round duration off − on) / off, with the floor. The OVERTURN fires iff
`active_cores` passes while `round_drop` is inside the floor.

The exit code is not the verdict. Three guards. First, output is compared elementwise against a CPU
reference in every arm: a sub-block whose zero-shape skip is mis-written drops a region of C
silently, and the result is a *faster* kernel with a hole in it. Second — the input that makes this
checker go red — Arm 1 is repeated with `mTailTile` forced so that
`(endBlockIdx_ + 1) × totalTailTile_ > GetBlockNum()`. The gate **must** decline, `active_cores`
**must** equal `tailOriCnt`, and `no_overrun` **must** stay true. If `active_cores` rises past
`GetBlockNum()`, the echo is fabricated and every reading from it is void; if it rises but stays
below, the gate is not the gate upstream describes. That fixture is a planted positive the checker
has to find. Third, `round_drop` is never reported without the floor, and never replaced by kernel
time.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `5 → 20` active-core
expansion is upstream's worked arithmetic, re-derived here on paper; no kernel has echoed a core
count and no round has been timed.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. Upstream gives no timing for mechanism C at any shape, so nothing
here establishes benefit — only the activation arithmetic and the gate. The worked example uses
`blockNum = 24`, a number that matches no installed 950 SKU's cube-core count in this book's own
record (`950:0217`: 4, 8, 28, 32, 36), so it is an illustration and not a configuration; the gate
must be re-evaluated at the real `GetBlockNum()` and this entry does not do that for any part. The
crossing point at which sub-blocks become too small is asserted to exist by a sibling file and is
given by nobody; §4 Arm 3 is the only thing here that would locate it. `CalUsedCoreNum`,
`preSplitMax` and `secSplitMax` appear in upstream's host search and are not defined in the file
(recorded in `harvest/standing/950-bp.md`). BOARD is `family-claimed(unverified)`: no file in this
family names a chip (`0347`). Nothing transfers to the other book (RULES.md Art. 1).
