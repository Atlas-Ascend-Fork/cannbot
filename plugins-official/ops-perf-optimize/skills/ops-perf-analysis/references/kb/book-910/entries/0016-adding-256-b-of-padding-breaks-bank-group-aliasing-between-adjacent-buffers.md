```
ID:        0016-adding-256-b-of-padding-breaks-bank-group-aliasing-between-adjacent-buffers
LABEL:     procedure
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 run on 910B2 2026-08-25 via §5: gate `bg_U` 0.48 > `bg_P` 0.0 ✓ (the planted conflict is
           found); `bg_P2` = 0.0 ≈ `bg_P` AND `bk_P2` = 0.416 > `bk_P` = 0.0 → the claim is UPHELD with the
           two-mechanism reading confirmed: 256 B on x alone removes the read-read GROUP conflict, the y inflation
           is what removes the read-write BANK conflict. Times: U 165 µs, P 86 µs, P2 147 µs per 2000 Adds. §6.
BOARD:     910B2 (measured 2026-08-25); other 910 parts unverified
SOURCE:    ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md:117 — "在 `xBuf` 后增加 256B padding，打破地址周期性，使 `x` 和 `y` 的 DataBlock 分散到不同 bank group"; ibid:130-134 — the 官方推荐 InitBuffer form
INDEX:     means=three TQue buffers x/y/z (fp32, 4096 elements) at upstream's three layouts, `Add(z, x, y, 4096)` × 2000,
           UB addresses echoed; msprof ResourceConflictRatio ×2 per arm, in-kernel `GetSystemCycle()` ×3 per arm
           conditions=CANN 9.1.0, 910B2 die 0, one AIV, curFreq 800 MHz
           readouts: U (x 0 / y 16384 / z 32768) bankgroup 0.48 bank 0.047 aiv 165 µs; P (0 / 16640 / 65536) 0.0 / 0.0 /
           86 µs; P2 (0 / 16640 / 33024) 0.0 / 0.416 / 147 µs; all outputs correct
           time=2026-08-25
OVERTURN:  a paired run on a named DAV_2201 board shows the padded arm's conflict ratio unchanged from the unpadded arm, or shows a padding other than 256 B is required.
```

# 0016 · Adding 256 B of padding breaks bank-group aliasing between adjacent buffers

## 1 · Claim
Measured on 910B2 with upstream's own three-buffer case (`Add(z, x, y)`, 4096 fp32 each): with x, y, z
allocated back to back at 16 KB spacing the bank-group conflict counter reads **0.48** and 2000 Adds take
**165 µs**; with upstream's 官方推荐 fix (x + 256 B, y inflated to fill 64 KB) both conflict counters read
**0.0** and the same work takes **86 µs** — 1.9× faster. The third arm settles what each displacement does:
with only the 256 B added to x (y not inflated, z at 33024) the group counter is **0.0 but the bank counter
is 0.416** and the time is 147 µs — the 256 B removes the read-read conflict between x and y, and the y
inflation is what moves z off x/y's bank. Upstream's sentence "add 256 B of padding" is therefore half the
fix, as §3 read it. Not established: whether a smaller displacement than the y inflation would also move z
(a padding sweep, C-910-008's 32-B question).

## 2 · The wrong branch this removes
The wrong branch is the *default* branch. `pipe.InitBuffer(inQueueX, 1, N); pipe.InitBuffer(
inQueueY, 1, N); pipe.InitBuffer(outQueueZ, 1, N);` is the canonical AscendC allocation pattern —
it appears in every tutorial — and when `N` is a power of two large enough to be a multiple of the
bank stride, it constructs the conflict. So the agent is not making a mistake; it is following the
standard idiom, and the standard idiom is the trap. Nothing in the API surface signals it, and the
symptom (Vector time above model) points elsewhere.

The second wrong branch is over-correcting: an agent that learns "add padding" and applies it to
every buffer inflates UB occupancy for no gain. Upstream notes this cost explicitly (line 307:
"**Padding 增加 UB 占用**：256B padding 虽然小，但多个 buffer 累积后需计入总 UB 预算"), and on a
192 KB UB (0003) the accumulation is not negligible.

## 3 · Ground / Source
The failure case, `ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md`
§2.2.5 场景 4, lines 122-127:
"// 220x 原始实现：x/y/z 连续分配，起始地址差为 0x4000（16KB）
// x: bank0, y: bank0（地址差 16KB = 4×bank size），z: bank0
// 一个 Repeat 内 x 和 y 同时读同一 group，x/y 和 z 同时读写同一 bank
pipe.InitBuffer(inQueueX, 1, 4096 * sizeof(float));
pipe.InitBuffer(inQueueY, 1, 4096 * sizeof(float));
pipe.InitBuffer(outQueueZ, 1, 4096 * sizeof(float));"

Arithmetic check performed here: 4096 × 4 B = 16 KB = 4 × the 4 KB bank size of 0013 ✓, so
consecutive buffers land on the same bank number. The example is self-consistent with the geometry
entry.

The fix, lines 130-134, verbatim and marked 官方推荐:
```cpp
// x 多申请 256B，避免一个 Repeat 内 x 和 y 同时读同一 bank group
// y 多申请空间，确保 z 不会和 x/y 落入同一个 bank
pipe.InitBuffer(inQueueX, 1, 4096 * sizeof(float) + 256);
pipe.InitBuffer(inQueueY, 1, 64 * 1024 - (4096 * sizeof(float) + 256));
pipe.InitBuffer(outQueueZ, 1, 4096 * sizeof(float));
```
Note the second line: `y` is not padded by 256 B but inflated to fill out a 64 KB span. So
upstream's own fix uses two different displacements for two different aliasing pairs, and "add
256 B" understates it. The read-read pair (x, y) takes 256 B; the read-write pair (x/y, z) takes
the larger displacement. An agent copying only the first line fixes half the problem.

The general form, line 117: "**规避**：在 `xBuf` 后增加 256B padding，打破地址周期性，使 `x` 和
`y` 的 DataBlock 分散到不同 bank group。" And the checklist form, line 339: "- [ ] Bank 冲突规避：
相邻 buffer 间隔 ≥ 256B 或 不在同一 bank group".

Same repo, one origin, the diagnostic side: `ops/ops-profiling/references/csv_fields_reference.md`
line 249 gives the corresponding fix direction — "| bank_cflt 高 | 修改 UB tensor 起始地址，添加
padding 使不同操作数落入不同 bank |". `ops/ops-profiling/references/optimization_quickref.md:145`
adds a quantity the design doc does not: "添加 padding（32B 整数倍间隔）" — a *different* padding
granularity (32 B) from the 256 B here. Filed as `harvest/contradictions-910.md` **C-910-008**:
numerically compatible (256 is a multiple of 32) but **not the same advice** — an agent following the
profiling guide's version may under-pad by up to 8×, and upstream's own worked fix above uses two
different displacements for two different aliasing pairs, so even "256 B" understates it.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Two arms from one source file, differing only in the three `InitBuffer` sizes, md5-confirmed:
   - Arm U (unpadded): the three-buffer case quoted above verbatim.
   - Arm P (padded): upstream's 官方推荐 form verbatim, including the `y` inflation.
3. A third arm is required and is the reason this procedure can conclude anything: Arm P2, padded
   by 256 B on `x` ONLY, without the `y` inflation. §3 predicts P2 fixes the read-read conflict and
   leaves the read-write one. If P2 is indistinguishable from P, the `y` inflation is unnecessary
   and upstream's recipe is over-specified; if P2 sits between U and P, the two-mechanism reading
   is confirmed.
4. Per arm: `aiv_vec_bankgroup_cflt_ratio`, `aiv_vec_bank_cflt_ratio`, `aiv_total_cycles`, and the
   host-reported total UB consumed. Five repeats, first discarded, arms interleaved rather than
   run in blocks, so that any drift in device state hits all arms alike.

**As run (2026-08-25, job bank910, die 0):** one source, `arm` a runtime argument selecting the three
`InitBuffer` triples verbatim from §3 (U: 16384 / 16384 / 16384; P: 16640 / 48896 / 16384; P2: 16640 / 16384 /
16384), `TQue<VECIN,1>` ×2 and `TQue<VECOUT,1>`, `AllocTensor` addresses echoed to GM (U: 0 / 16384 / 32768;
P: 0 / 16640 / 65536; P2: 0 / 16640 / 33024 — the layouts upstream's comments describe). 2000 `Add(z, x, y,
4096)` per launch; three interleaved launches per arm timed in-kernel, two interleaved msprof launches per
arm for the counters; outputs checked against the host (all correct). Deviation: msprof gives whole-kernel
`aiv_time`, not per-arm cycles; the in-kernel tick counts carry the same ratios. The "UB consumed" cost side
is the sum of the three InitBuffers: U 49152 B, P 81920 B, P2 49408 B.

## 5 · Checker — acceptance declared before the run
Verdict variables: `bg_U, bg_P, bg_P2` (bank-group conflict ratios) and `bk_U, bk_P, bk_P2`
(bank conflict ratios), medians over four post-warm-up repeats.
Gate: `bg_U` must exceed `bg_P` by more than three times arm P's spread. Arm U is this
procedure's planted positive — a constructed conflict the instrument must FIND. If U and P are
indistinguishable, the run is VOID and reports nothing about padding, because a counter that
cannot see a deliberate conflict cannot certify its absence.
Given the gate passes, the claim is upheld iff `bg_P2 ≈ bg_P` (the 256 B padding alone fixes the
group conflict) while `bk_P2 > bk_P` (the bank conflict survives without the `y` inflation).
An outcome where `bg_P2 ≈ bg_U` overturns the 256 B figure specifically and sends the entry back
to a padding sweep.
The cost side is recorded regardless of verdict: UB bytes consumed per arm, so the fix is never
reported without its price. Exit code is not the verdict.

## 6 · Evidence
RUN 2026-08-25, 910B2 die 0 (idle before and after).

**In-kernel timing (system-counter ticks per `Add` of 4096 fp32; three interleaved launches):**

| arm | ticks per Add | x / y / z UB address | wrong elements |
|---|---|---|---|
| U | 4.018 | 0 / 16384 / 32768 | 0 |
| P | 2.064 | 0 / 16640 / 65536 | 0 |
| P2 | 3.574 | 0 / 16640 / 33024 | 0 |
| U | 4.013 | 0 / 16384 / 32768 | 0 |
| P | 2.058 | 0 / 16640 / 65536 | 0 |
| P2 | 3.576 | 0 / 16640 / 33024 | 0 |
| U | 4.014 | 0 / 16384 / 32768 | 0 |
| P | 2.054 | 0 / 16640 / 65536 | 0 |
| P2 | 3.576 | 0 / 16640 / 33024 | 0 |

**msprof ResourceConflictRatio (2000 Adds; two interleaved launches per arm):**

| arm | aiv_time µs | bankgroup_cflt_ratio | bank_cflt_ratio |
|---|---|---|---|
| U | 165.422 | 0.477 | 0.047 |
| P | 86.246 | 0.0 | 0.0 |
| P2 | 146.941 | 0.0 | 0.416 |
| U | 164.441 | 0.48 | 0.047 |
| P | 86.357 | 0.0 | 0.0 |
| P2 | 147.257 | 0.0 | 0.415 |

Gate: `bg_U` (0.48) exceeds `bg_P` (0.0) — spread of the P pair 0.0 — the planted conflict is found.
Verdict: `bg_P2` ≈ `bg_P` (both 0.0) and `bk_P2` (0.416) > `bk_P` (0.0) → claim upheld with the two
mechanisms separated. Cost: P spends 81920 B of UB for the 1.9×; P2 spends 49408 B for 1.12×.

## 7 · Scope limits — what this entry does NOT establish
910B2 only; one operator shape (three 16 KB fp32 buffers, `Add`); the minimal displacement that moves z off
x/y's bank is not swept — upstream's y inflation to a 64 KB span is confirmed to work, not shown to be
necessary (C-910-008's 32-B-multiple alternative remains untested); `bank_cflt_ratio` 0.047 in arm U is
recorded, not explained. Nothing transfers to the 950 book (RULES.md Art. 1) — on 950PR the classic-vector
read path showed no bank conflict at any stride (950:0314).
