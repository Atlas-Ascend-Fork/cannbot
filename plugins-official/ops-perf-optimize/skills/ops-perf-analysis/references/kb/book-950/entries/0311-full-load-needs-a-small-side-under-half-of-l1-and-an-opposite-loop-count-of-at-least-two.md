```
ID:        0311-full-load-needs-a-small-side-under-half-of-l1-and-an-opposite-loop-count-of-at-least-two
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/fullload_design.md:263-267 —
           "| 小侧容量 | `baseM × Align(K, c0) × dtype_A ≤ L1/2`（A 全载）；对称 B 全载 | L1 能装下，
           且预留 ≥ 1/2 L1 给对侧 pingpong | | 对侧循环次数 | `T = N_{pc} / baseN ≥ 2`（A 全载）
           ... | T=1 时小侧本来就只搬 1 次，收益为 0 | | 多核排布 | A 全载：`mBlockCnt ≤
           WINDOW_LEN(=4)` 且 `aicNum % mBlockCnt == 0` 且 `totalBlockCnt > aicNum` | ... |
           | MTE2 健康度 | 对侧流式 Bytes ≥ 20 KB（非"假 MTE2 bound"） | ... |"
SOURCE:    same file:7 — "典型收益：`T = 5` 时 MTE2 总字节下降约 **16%–20%**，Task 总时间下降
           **5%–15%**（对应 matmul MXFP4 `M=128, K=4096, N=81920` 实测 `183.87μs → 170.07μs`，
           约 **−7.5%**）。" ; :99-100 — "constexpr uint32_t M_TAIL_TILE = 1;  // *** 本优化强约束 ***
           A 全载下 M 尾禁止再切" ; :123 — "**强校验**：`isAFullLoad` 与 `isBFullLoad` **互斥**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured matmul on a named 950 board at the stated MXFP4 shape where A-Full-Load moves
           MTE2 bytes by less than the baseline arm's own repeat-to-repeat spread — the residency
           would then not be removing the repeated loads upstream attributes the gain to.
```

# 0311 · Full-Load needs a small side under half of L1 and an opposite loop count of at least two

## 1 · Claim
Upstream asserts that A-Full-Load (symmetrically B-Full-Load) makes the small operand and its
in-line scale resident in L1 for the whole `operator()`, so the opposite side's loop stops
re-fetching it, and states four admission conditions: the resident side must fit in half of L1
(`baseM × Align(K, c₀) × |dtype_A| ≤ L1/2`), the opposite loop count `T = N_pc / baseN` must be at
least 2, the multi-core layout must satisfy `mBlockCnt ≤ WINDOW_LEN(=4)` and
`aicNum % mBlockCnt == 0` and `totalBlockCnt > aicNum`, and the streaming side's per-transfer bytes
must already be ≥ 20 KB so that the case is a real and not a false MTE2 bound (`0312`). Upstream
asserts two hard constraints: `isAFullLoad` and `isBFullLoad` are mutually exclusive, and A-Full-Load
forces `mTailTile = 1`, forbidding SWAT mechanism C from re-splitting the M tail (`0308`) because
that would reintroduce the repeated loads. Upstream asserts mutual exclusion with StreamK, on the
ground that once K is split across cores the residency semantics no longer hold. Upstream asserts a
measurement at MXFP4 `M=128, K=4096, N=81920` with `aicNum=32`: 183.87 → 170.07 µs, −7.5 %, with a
stated envelope of 5 %–15 %. Not established here.

## 2 · The wrong branch this removes
Two failures of the same shape: doing the residency work where it cannot pay.

`T = 1` is the clean case. If the opposite loop runs once, the small side was already fetched once,
and residency saves nothing — upstream states `收益为 0`. An agent that checks only the capacity
condition (`fits in L1/2`) will find plenty of shapes that fit and pay nothing, and will then
conclude the technique does not work. The capacity test is necessary and the loop-count test is
what makes it sufficient; only checking one is the common error.

The multi-core condition is the one an agent will not think of at all. If `mBlockCnt > WINDOW_LEN`,
several cores each hold their own copy of the "resident" operand, and L1 is spent several times over
for one saving — upstream's phrase is `多核重复持有全载块、L1 浪费`. This condition couples the
residency decision to the *scheduler*, which is a different file, and that coupling is the reason it
gets dropped.

The third wrong branch is the one this entry shares with `0312`: reading high MTE2 busy as a reason
to make the big side resident. Upstream routes on the *kind* of MTE2 pressure — real bandwidth
saturation (≥ 85 % utilisation) wants Full-Load; small-block density at 50–70 % utilisation wants
coalescing first, and Full-Load on top of it, in that order (`分核 → 全载 → 合并载入`). Applying
them in the other order leaves the small blocks small.

The fourth is a correctness trap, disclosed by upstream and easy to hit: with A resident, the A-side
`SetFlag<MTE1_MTE2>` release **must be deleted**. If it is left in place the ping-pong machinery
keeps releasing a buffer nothing will rewrite — until it does, and the resident A is overwritten mid
kernel. Upstream's signature for it is precise: `精度错误集中在 N 方向第 2 轮之后`.

## 3 · Ground / Source
The admission table, `fullload_design.md:261-267`, in full:

```
| 维度 | 条件 | 说明 |
| 小侧容量 | `baseM × Align(K, c0) × dtype_A ≤ L1/2`（A 全载）；对称 B 全载 | L1 能装下，且预留
  ≥ 1/2 L1 给对侧 pingpong |
| 对侧循环次数 | `T = N_{pc} / baseN ≥ 2`（A 全载）；对称 B 全载 | T=1 时小侧本来就只搬 1 次，收益为 0 |
| 多核排布 | A 全载：`mBlockCnt ≤ WINDOW_LEN(=4)` 且 `aicNum % mBlockCnt == 0` 且
  `totalBlockCnt > aicNum` | 不然多核重复持有全载块、L1 浪费 |
| MTE2 健康度 | 对侧流式 Bytes ≥ 20 KB（非"假 MTE2 bound"） | 小数据块密集场景需叠加合并载入，
  不可单用全载 |
| 分支 | 未走 StreamK | StreamK 已把 K 切给多核，"全载"语义失效 |
```

The worked shape table, `:271-276`, gives four routed examples including two negatives, which is
unusual for this shelf and is worth carrying: `[128, 4096, 81920]` MXFP4 at `aicNum=32` → A-Full-Load
with `T_A = 81920/(32·512) = 5`; `[81920, 4096, 128]` → B-Full-Load, `T_B = 5`;
`[1024, 4096, 1024]` → SWAT, because `两侧都 2 MB > L1/2`; `[128, 512, 81920]` → SWAT or coalescing,
because `kL1Iter = 512/(2·128) = 2 偏少`. Re-derived: `81920 / (32 × 512) = 5` ✓;
`512 / (2 × 128) = 2` ✓.

The L1 budget inequality, `:127-136`, sums the resident A, the resident scaleA, the streaming B
under ping-pong and the scaleB ping-pong against `524288 B`, and prescribes shrinking `stepKb`
downward on overflow, falling back to SWAT if `stepKb = 1` still overflows.

The benefit statement, `:7`, and its own correction, `:317`. §1 of the file says the technique
`等效把 MTE2 总字节数压缩 (T-1)/T`. §7's table row states the same quantity correctly as
`下降 (T−1)/T × Bytes_side / Bytes_total`. Those are different claims: the first says total MTE2
bytes fall by 80 % at `T = 5`, the second says the *small side's* bytes do, weighted by its share of
the total. The §7 form is the one consistent with the file's own headline number (`16 %–20 %` at
`T = 5`, not 80 %). Recorded as a scope overreach in §1 corrected in §7 of the same document — the
`0304`-style hazard of quoting a summary line rather than the table.

The measurement: `183.87 → 170.07 µs`. Re-derived: `13.80 / 183.87 = 7.505 %` ✓, matching the stated
−7.5 %. The table at `:314-320` reports the same −7.5 % for both the MTE2 segment and total task
time, which would mean the MTE2 saving carried the whole task delta with no other segment moving —
possible, and unusual enough that it is recorded rather than smoothed.

The event-model change, `:231-243`, is where the correctness trap lives:
`不发 A/scaleA 的 MTE1→MTE2 释放（L1 驻留永不覆写）`, with `漏掉这一改动会导致 A 被错误覆写`.

`c₀` in the capacity condition is never defined in this family. `950:0111` records the same symbol
undefined in the analysis shelf's FullLoad capacity test — one repo, one origin, and the second
place the same undefined quantum gates the same decision. Owed in `harvest/standing/950-bp.md`.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase.

Arm 1 — reproduce the measurement. Two builds (SWAT baseline, A-Full-Load) at MXFP4
`M=128, K=4096, N=81920`, `aicNum` queried and echoed. Primary readout is **MTE2 bytes moved**, not
time: the mechanism's entire claim is that `(T−1)` copies of the small side stop happening, and byte
count is the quantity that says so directly. Time is secondary. Variance floor established on the
baseline first (one build, 30 in-process runs, 5 fresh-process runs, IQR over median) — a −7.5 %
effect against an unstated spread cannot be evaluated.

Arm 2 — the `T ≥ 2` condition, tested at the boundary rather than assumed. Repeat Arm 1 at
`T ∈ {1, 2, 3, 5, 8}` by varying `N`. Prediction: zero benefit at `T = 1`, benefit appearing at
`T = 2` and growing as `(T−1)/T` weighted by the small side's byte share. A benefit at `T = 1` would
mean something other than de-duplicated loads is producing the gain.

Arm 3 — the multi-core condition, which nothing else in this book touches. Force
`mBlockCnt ∈ {2, 4, 8}` at fixed shape and record L1 occupancy per core and MTE2 bytes. Upstream
predicts waste above `WINDOW_LEN = 4`. This arm is the one most likely to surprise, because it
predicts that a *scheduler* parameter breaks a *residency* optimisation.

Arm 4 — the negative arm, retained whatever it shows. Run the two shapes upstream routes away from
Full-Load (`[1024, 4096, 1024]` and `[128, 512, 81920]`) with Full-Load forced on. Upstream predicts
overflow in the first and negligible-or-negative benefit in the second. An arm that does not bite is
recorded as an arm that did not bite.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; re-sample after; discard if the die moved. Refuses to assume: that a
free die stays free; that a die may be substituted; that `aicNum` is 32 — it is queried and echoed,
and `T` is computed from it, so a wrong `aicNum` silently changes which regime the run is in; that
`c₀` is any particular value — the capacity condition is evaluated with `c₀` swept over its plausible
set (16, 32) and both results reported, because the family never defines it.

## 5 · Checker — acceptance declared before the run
Verdict `byte_drop` = (baseline MTE2 bytes − full-load MTE2 bytes) / baseline MTE2 bytes, with the
floor. Declared before the run: pass is `byte_drop` positive, outside the floor, and consistent with
`(T−1)/T × Bytes_side/Bytes_total` — the §7 form, not the §1 form. The OVERTURN fires iff
`byte_drop` is inside the floor.

Verdict `t_threshold` = the smallest `T` in Arm 2 at which `byte_drop` leaves the floor. Pass is
`t_threshold == 2`. `t_threshold == 1` means the gain is not de-duplication and the entry is
corrected in place.

Verdict `mblock_penalty` = the `mBlockCnt` at which Arm 3's per-core L1 occupancy first exceeds the
single-core figure. Pass is `> WINDOW_LEN`, i.e. the condition is not binding below 4.

The exit code is not the verdict. Three guards. First, every build is compared elementwise against a
CPU reference — the resident-A overwrite trap produces output that is wrong only from the second N
round onward, which a spot check of the first tile will not see, so the comparison covers the whole
of C. Second — the input that makes this checker go red — Arm 1 is repeated with the A-side
`SetFlag<MTE1_MTE2>` release *left in* (upstream's disclosed defect). The precision comparison
**must** fail, and it must fail in the second N round and later. If it passes, the comparison is not
covering the region where the defect lives and every green from Arm 1 is void. That fixture is a
planted positive the checker has to find. Third, no `byte_drop` is reported without the floor and
without the echoed `aicNum` and `T`.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. 183.87 µs, 170.07 µs, the
−7.5 %, the 16 %–20 % byte reduction and the 5 %–15 % envelope are upstream's figures on an unnamed
part; this book has reproduced none of them and has moved no bytes.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. Upstream's measurement carries a dtype, a shape and a core count
but no board, no tool, no repeat count, no variance and no CANN pin. The MTE2-segment and task-time
deltas are reported as the same −7.5 %, which is recorded and not reconciled. §1 of the source
overstates the byte reduction relative to §7 of the same source; this entry adopts the §7 form and
does not adjudicate which the implementation realises. `c₀`, `N_pc`, `Bytes_total^{nl}` and the
B-Full-Load template (`当前 tutorial 未提供`, `:163`) are undefined or unimplemented in the source,
so the B side is asserted by symmetry and established by nothing. The four admission conditions are
stated by upstream and tested by nobody; §4 tests two of them. The generalisation table at `:330-336`
(bias vectors, MoE routing LUTs, attention masks, KV cache heads) carries benefit ranges with no case
identity at all and is not carried into this entry. BOARD is `family-claimed(unverified)`: no file in
this family names a chip (`0347`). Nothing transfers to the other book (RULES.md Art. 1).
