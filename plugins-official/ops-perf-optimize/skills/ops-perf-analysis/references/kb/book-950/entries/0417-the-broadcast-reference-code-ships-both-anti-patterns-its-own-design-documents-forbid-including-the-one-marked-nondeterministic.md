```
ID:        0417-the-broadcast-reference-code-ships-both-anti-patterns-its-own-design-documents-forbid-including-the-one-marked-nondeterministic
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/broadcast/ub_broadcast_design.md:66 —
           "- **⚠️ 紧凑源跨 tile 要双缓冲（防 MTE2↔V WAR、非确定性 FAIL）**：多 tile 循环复用**单块裸
           `TBuf`** 做 `DataCopyPadCompact` 紧凑源时，本 tile 的 MTE2(写) 与上一 tile 的
           V(`Broadcast`/`Cast` 读) 存在 WAR，框架**不自动插同步** → **非确定性 FAIL**（run1 fail=N、
           run2 PASS，逐次波动）。修法：紧凑源改走双缓冲队列 `TQue<VECIN, 2>`"
SOURCE:    same family, code/broadcast_add_kernel.cpp:104 —
           "    TBuf<TPosition::VECCALC> bufSrc_;" ; :94 —
           "            LocalTensor<T> src = bufSrc_.template Get<T>();" (inside the per-tile loop)
SOURCE:    same family, onedim_design.md:109 — "**修法**：每核改用全局区间 `[blockStart, blockEnd)`
           对 `dimLen` clamp … —— **永不靠减法反推末核长度**。" ; code/broadcast_common.h:325 —
           "    int64_t blockTail   = ubOuter - (bn - 1) * blockFormer;            // 尾核块数 ∈[1, blockFormer]"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a multi-tile broadcast on a named 950 board, run through the shipped `bufSrc_` `TBuf` path
           enough times to exhaust the nondeterminism upstream describes (≥100 runs, mixed tile
           counts), that matches a CPU reference on every run. The WAR upstream says the framework does
           not close would then be closed by something else on this part, and the sample would be
           correct rather than lucky.
```

# 0417 · The broadcast reference code ships both anti-patterns its own design documents forbid, including the one marked non-deterministic

## 1 · Claim
Upstream asserts two hazards in its broadcast family's design notes and prescribes a fix for each.
First: reusing a single bare `TBuf` across tiles as the compact source for the UB Broadcast path leaves
a write-after-read between this tile's MTE2 write and the previous tile's Vector read, which upstream
asserts the framework does not synchronise automatically, producing a non-deterministic failure that
passes on one run and fails on the next; the prescribed fix is a double-buffered `TQue<VECIN, 2>`.
Second: deriving the last core's block count by subtraction can go negative when the per-core count was
rounded up, so the last core writes past the end of the tensor; the prescribed fix is to clamp each
core to a global interval and never to derive the tail by subtraction. Upstream's reference code in the
same directory does both forbidden things: it declares `TBuf<TPosition::VECCALC> bufSrc_` and calls
`Get<T>()` on it inside the per-tile loop, and it computes `blockTail = ubOuter - (bn - 1) *
blockFormer` with a trailing comment asserting a range that a third file in the same family
demonstrates is false. Not established here.

## 2 · The wrong branch this removes
The reference code is what gets copied. A design note is read once; a `.cpp` in a `code/` directory is
pasted, and everything in it inherits an implicit endorsement. An agent adapting this family will take
`bufSrc_` as the sanctioned way to hold a compact source — it is the only implementation shipped — and
will reproduce a WAR hazard that upstream describes in the strongest terms available to it: not slow,
not wrong, but *intermittently* wrong. `run1 fail=N、run2 PASS，逐次波动` is the profile that survives
CI, survives a reviewer, and surfaces later as a flaky test somebody disables.

The second wrong branch is the reader who notices and assumes the code is right because it is code. It
is not obviously wrong: `blockTail` is only used on the last core (`p.loops = lastCore ? blockTail :
blockFormer`), so a negative value produces a loop that runs zero times rather than an out-of-bounds
write, in *this* function. Upstream's warning at `onedim_design.md:109` is about a caller that then
writes a full tile anyway. So whether the shipped expression is a live defect or a latent one depends
on code not in this file — which is exactly the state in which a comment asserting `∈[1, blockFormer]`
does the most damage, because it tells the next reader the question has been settled.

## 3 · Ground / Source
**Hazard one, the prohibition.** `reference/broadcast/ub_broadcast_design.md:66`:

```
- **⚠️ 紧凑源跨 tile 要双缓冲（防 MTE2↔V WAR、非确定性 FAIL）**：多 tile 循环复用**单块裸 `TBuf`** 做 `DataCopyPadCompact` 紧凑源时，本 tile 的 MTE2(写) 与上一 tile 的 V(`Broadcast`/`Cast` 读) 存在 WAR，框架**不自动插同步** → **非确定性 FAIL**（run1 fail=N、run2 PASS，逐次波动）。修法：紧凑源改走双缓冲队列 `TQue<VECIN, 2>`（Alloc→DataCopyPad→EnQue→DeQue→用→Free），框架自动管 MTE2↔V 同步。
```

Three parts worth separating. The hazard is named precisely (MTE2 write versus Vector read, across tile
iterations, on one buffer). The framework's behaviour is asserted (`不自动插同步`) — this book already
carries the general shape of that question at `0259`, where four upstream sources give three answers on
whether a barrier is needed after a VF, and at `0261`, where overlapping MTE destinations need a manual
barrier because hardware does not serialise them. And the fix is not a barrier but a *queue*, chosen
because the queue's `EnQue`/`DeQue` machinery inserts the synchronisation as a side effect.

**Hazard one, the shipped code.** `code/broadcast_add_kernel.cpp`:

```cpp
:34         pipe_.InitBuffer(bufSrc_, td_.elemNum * sizeof(T));   // ③ 用：广播前紧凑源
:94             LocalTensor<T> src = bufSrc_.template Get<T>();
:102    TQue<TPosition::VECIN, 2> qx_, qy_;
:103    TQue<TPosition::VECOUT, 2> qz_;
:104    TBuf<TPosition::VECCALC> bufSrc_;
```

Lines 102 and 103 are the tell. The same class uses `TQue<..., 2>` — the exact construct
`ub_broadcast_design.md:66` prescribes — for its input and output buffers, and a bare `TBuf` for the
one buffer the design note singles out as needing it. `Get<T>()` at `:94` is inside the per-tile loop,
which is the condition the note states (`多 tile 循环复用单块裸 TBuf`). So the sample is not unaware of
`TQue`; it applies it everywhere except where its own documentation says it is mandatory.

A second, smaller violation sits in the same declaration. `ub_broadcast_design.md:65`:

```
- **每个走 ③ 的输入要各自一块 `bufSrc`**：若多个输入都可能 ③（如 binary 的 x1/x2 都广播），共用一块 `TBuf` 会 RAW 冒险（第二个输入的 `DataCopyPadCompact` 覆盖第一个的紧凑源）。binary 算子应配 `bufSrc1_/bufSrc2_`，`aliveBuf` 相应增大（cann-bench Maximum 落地经验）。
```

The sample is a binary `Add` with two inputs and one `bufSrc_`. It escapes the RAW hazard only because
it exercises the UB path on one input; an adapter that broadcasts both — the case the note names — hits
it immediately. Registered together as `C-950td-021`.

**Hazard two, the prohibition.** `onedim_design.md:109`:

```
- **⚠️ 末核长度别用减法推（防负→越界踩踏 GM）**：`blockTail = ubOuter − (bn−1)·blockFormer` 在 `blockFormer` 向上取整后可能 **取负**（(bn−1)·blockFormer > ubOuter），末核仍按满 tile 写 → **越界写 `dimLen` 之外、踩踏相邻 GM**。症状极隐蔽：**单跑可能 PASS、msprof 多 launch 累积成大量 mismatch**（覆盖仿真 `oob>0`、`missing=0`、`maxAbsDiff` 巨大）。**修法**：每核改用全局区间 `[blockStart, blockEnd)` 对 `dimLen` clamp，每 tile `len = min(tileLen, blockEnd − off)`，`blockStart ≥ dimLen` 直接 return —— **永不靠减法反推末核长度**。
```

The forbidden expression is quoted in the prohibition, character for character.

**Hazard two, the shipped code.** `code/broadcast_common.h:320-328`:

```cpp
    int64_t ubTail      = dimLen - (ubOuter - 1) * tn;                 // 最后一块元素数（可非对齐）
    int64_t blockFormer = (ubOuter + bn - 1) / bn;                     // 每核块数（先定块数）
    int64_t blockTail   = ubOuter - (bn - 1) * blockFormer;            // 尾核块数 ∈[1, blockFormer]
    int64_t bid = AscendC::GetBlockIdx();
    OneDimCoreParam p;
    p.baseOffset = blockFormer * tn * bid;
    bool lastCore = (bid == bn - 1);
    p.loops   = lastCore ? blockTail : blockFormer;
```

`blockTail = ubOuter - (bn - 1) * blockFormer` is the prohibited expression verbatim, and the comment
`尾核块数 ∈[1, blockFormer]` asserts the property that makes it safe. A third file in the same family
supplies a counter-example to exactly that assertion, `advanced_tiling.md:59`:

```
> 顺序很关键：若先 `blockNum=min(coreNum,totalTiles)` 再 `blockFormer=ceil(totalTiles/blockNum)`，会出现 `blockTail<0`（如 totalTiles=100、coreNum=64 → blockFormer=2、blockTail=-26），非尾核处理越界 tile。必须先定 blockFormer 再回收核。
```

Re-derived here: `ceil(100 / 64) = 2`; `100 - 63 × 2 = -26`. Upstream's arithmetic checks. So within
this one family, one file states the expression can go negative and gives numbers, a second file
forbids the expression outright, and a third ships it with a comment asserting it cannot.

The two prohibitions do not agree on the fix, and that is the third finding here.
`advanced_tiling.md:59` says the failure comes from the *order* of operations and prescribes fixing the
order — `必须先定 blockFormer 再回收核` — which is what `broadcast_common.h:321` actually does
(`blockFormer` first, comment `先定块数`). `onedim_design.md:109` says the derivation itself is
forbidden regardless of order and prescribes an interval clamp. Under the first prohibition the shipped
code is compliant; under the second it is not. Upstream never reconciles them, and the shipped code's
comment reads as if the first settles the matter. Registered as `C-950td-022`.

Whether the shipped code is *actually* safe turns on a fact neither prohibition states: `bn` is
computed at `broadcast_common.h` from `ubOuter`, and if `bn ≤ ubOuter` always holds then
`(bn-1) × ceil(ubOuter/bn) < ubOuter` and the tail is positive. `advanced_tiling.md:59`'s
counter-example has `bn = 64 > ` nothing — it has `totalTiles = 100`, `coreNum = 64`, so
`bn ≤ ubOuter` holds there too, and it still goes negative. So the ordering fix alone does not obviously
suffice, and the safety of the shipped expression is not established by anything in this family.
Recorded in `harvest/standing/950-td.md` as `Q-950td-07`.

One more anti-pattern the sample does not commit but is worth recording beside these, because it is the
same species and upstream discloses it in the same file — `ub_broadcast_design.md:67` warns that very
small tiles turn this path into a scalar bound, with the fix being multi-batch packing
(`batchPerTile = elemNum/plane`), which is the identical move this book carries at `0017`. No
measurement accompanies it; `降一个量级` is the only order-of-magnitude claim in the family.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. A
non-deterministic failure cannot be shown by one run, so the procedure's shape is repetition, and its
central risk is concluding "no bug" from a small sample.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved.

**Arm 1 — the WAR, as shipped.** Build the sample kernel unmodified. Choose shapes forcing many tiles
through the ③ path (`totalTiles ∈ {2, 8, 64, 512}`), FP16 and FP32. Run each **200 times in fresh
processes**, comparing elementwise against a CPU reference every run, and record the failure count and
which elements differ. Upstream's description predicts a nonzero, unstable failure rate; the run count
is fixed in advance so that a zero result is a bounded statement (`0 of 200`) rather than an unbounded
one.

**Arm 2 — the prescribed fix, same shapes.** Rebuild with the compact source as `TQue<VECIN, 2>` per
`ub_broadcast_design.md:66`, same 200 runs. Expected: zero failures. If arm 1 also shows zero, the two
arms are indistinguishable and the OVERTURN condition is met; if arm 1 fails and arm 2 does not, the
hazard and the fix are both confirmed.

**Arm 3 — the RAW, which the sample does not exercise.** Extend the sample to a binary case where
**both** inputs take the ③ path, sharing the single `bufSrc_`. Upstream predicts the second input's
`DataCopyPadCompact` overwrites the first's compact source. Compare elementwise; this failure should be
deterministic, not intermittent, which distinguishes it from arm 1 and is why it is a separate arm.

**Arm 4 — device-free. The tail expression.** Enumerate `ubOuter ∈ [1, 4096]` and `bn ∈ [1, 128]` as
the shipped code computes them, evaluate `blockTail = ubOuter - (bn-1) * ceil(ubOuter/bn)`, and report
every `(ubOuter, bn)` pair for which it is `≤ 0`. Then check whether any such pair is reachable given
how `bn` is derived from `ubOuter` in `broadcast_common.h`. This settles `Q-950td-07` with no device and
no ambiguity, and it is the cheapest arm in this entry.

**Arm 5 — the out-of-bounds consequence, only if arm 4 finds a reachable pair.** Construct that shape,
poison the GM region immediately after the output tensor with a known pattern, run, and report whether
the poison was overwritten. `onedim_design.md:109` predicts `oob > 0`, `missing = 0`, `maxAbsDiff` large
— a specific signature worth confirming or refuting.

Refuses to assume: that a free die stays free; that a die may be substituted; that one passing run means
absence (the run count is declared before the run and reported with every result); that arm 4's
enumeration covers the reachable `(ubOuter, bn)` space (the derivation of `bn` is read from the source
and echoed, and a pair outside the enumeration is reported as untested); that a negative `blockTail`
implies an out-of-bounds write (arm 5 is what tests the consequence, and arm 4 only finds the
precondition).

## 5 · Checker — acceptance declared before the run
Verdict `war_failures(shape, arm)` = failures out of 200 fresh-process runs. Declared before the run:
this entry is **supported** iff `war_failures > 0` for some shape in arm 1 **and** `war_failures == 0`
for every shape in arm 2. The OVERTURN fires iff `war_failures == 0` across all of arm 1 — reported
explicitly as `0 of 200 at tile counts {2, 8, 64, 512}`, never as "no bug", because a 200-run null
bounds the failure rate at roughly 1.5 % and upstream's `逐次波动` does not say the rate is higher
than that.

Verdict `raw_deterministic` from arm 3: true iff the shared-`bufSrc_` binary case fails on every run.

Verdict `negative_reachable` from arm 4 ∈ {`yes` with the pair listed, `no` over the enumerated range}.
Verdict `oob_confirmed` from arm 5, applicable only when arm 4 says `yes`.

The exit code is not the verdict, and this entry is the clearest case of that in the block: arm 1's
failure mode is a *correct exit code with wrong data*, on some runs. Three guards. First, every run of
every arm compares the full output elementwise against a CPU reference — a sampled or reduced
comparison cannot see an intermittent partial corruption, which is the documented profile. Second,
**the input that makes this checker go red**: arm 1 includes a single-tile shape (`totalTiles == 1`),
where no cross-tile WAR can exist and the buffer is written once. That case **must** pass 200 of 200.
If it fails, the harness has a defect unrelated to the hazard and every failure count in the sweep is
uninterpretable — a flakiness study whose only outcome is "some runs failed" cannot distinguish the
documented WAR from an unstable test rig. Third, no arm reports a count without its run total, its
build md5, and its echoed buffer construct (`TBuf` or `TQue`); arms 1 and 2 differ in exactly one line
of source and a result that cannot prove which one ran is not a result.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement, and upstream supplies none
either: `run1 fail=N、run2 PASS` uses `N` as a placeholder rather than a count, and the family contains
no timing, percentage or ratio of any kind. The `-26` in §3 is arithmetic performed here on upstream's
own worked numbers (`ceil(100/64) = 2`; `100 - 63×2 = -26`), and it agrees with upstream's stated
result. Nothing was compiled and no kernel was run.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the shipped sample fails on any
board — it establishes that the sample does two things its own family's design notes forbid, and that
one of those notes describes the consequence as non-deterministic. It does not establish that the
framework fails to insert MTE2↔V synchronisation; that is upstream's assertion, this book records four
upstream sources giving three answers to the adjacent question at `0259`, and §4 arm 1 is what would
settle it here. It does not establish that `blockTail` can go negative in the shipped code: `Q-950td-07`
records that as open, arm 4 is what closes it, and the counter-example that exists
(`advanced_tiling.md:59`) is stated for a *different* computation order than the one shipped. It does
not establish that a negative `blockTail` produces an out-of-bounds write in this sample — the value is
used only as a loop count, which would produce zero iterations rather than a write. It does not
adjudicate between the two incompatible fixes upstream prescribes for the same failure
(`C-950td-022`). It does not cover the RAW hazard's reachability in any shipped operator, only that
upstream names it for binary broadcasts. It says nothing about the `ub_broadcast_design.md:67` scalar
-bound regression beyond recording it. No board token appears in the sample or in `onedim_design.md`;
the family scopes itself to `DAV_3510（A5 / Ascend950，C310）` at `broadcast_design.md:6`, an
architecture and a family, with `C310` a token no upstream mapping table defines (`0203`). BOARD is
`family-claimed(unverified)`. Nothing here is established for any 910-family board.
