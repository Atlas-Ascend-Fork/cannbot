```
ID:        0013-dav-2201-ub-is-48-banks-of-4-kb-arranged-in-16-groups-of-three
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 run on 910B2 2026-08-25; §5's literal PASS (`conflict_period == 16` by first rise) NOT met and
           neither red input met, so the entry is REFINED in place: `aiv_vec_bankgroup_cflt_ratio` first rises at S = 4
           (0.45), reaches 0.66 at S = 8 and 24, and PEAKS at S = 16 and 32 (0.84) — every S with gcd(S, 16) > 1 and no
           other — while instruction time rises only from S ≡ 8 (mod 16) (1.65×) and is maximal at S ≡ 0 (mod 16)
           (2.62×); baseline 0.0854 sys-cycles per instruction at every other S in 1..32. A 16-group mapping (blocks
           per group = 8·gcd(S,16)/16) predicts exactly this tiering; a period-8 (3510) mapping does not. §6.
BOARD:     910B2 (measured 2026-08-25); other 910 parts unverified
SOURCE:    ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md:37 — "| DAV_2201 | 192 KB | 48 | 16 | 3 | 4 KB (128 行) | 32 B |"; ibid:25 — "以 Ascend 910B 为例：UB (192KB) = 48 bank × 4KB = 16 bank group × 3 bank/group"
INDEX:     means=`Adds` fp16, 128 elements (8 DataBlocks) per instruction, `UnaryRepeatParams{1, S, 8, 8}`, 20000
           instructions per launch, in-kernel `GetSystemCycle()` per instruction; msprof `--aic-metrics=
           ResourceConflictRatio` (`aiv_vec_bankgroup_cflt_ratio`, `aiv_vec_bank_cflt_ratio`) at S ∈ {1,2,4,8,12,16,24,32}
           conditions=CANN 9.1.0, 910B2 die 0, one AIV, curFreq 800 MHz
           readouts: time/instr S=1..32 = 0.0856 baseline; S=8, 24 → 0.1409; S=16, 32 → 0.224; bankgroup ratio
           S=1/2 0.0, S=4/12 0.45, S=8/24 0.66, S=16/32 0.84; bank ratio S=4/12 0.30, S=8/24 0.19, S=16/32 0.0
           time=2026-08-25
OVERTURN:  a bank-conflict sweep on a named DAV_2201 board shows the conflict period is not 16 bank groups — e.g. padding by 512 B rather than 256 B is what breaks aliasing, or a `blk_stride` of 8 shows no conflict.
```

# 0013 · DAV_2201 UB is 48 banks of 4 KB arranged in 16 groups of three

## 1 · Claim
Measured on 910B2 with an 8-DataBlock `Adds` whose source block stride S runs 1..32: the bank-group conflict
counter is zero at S = 1 and 2, **0.45 at S = 4 and 12, 0.66 at S = 8 and 24, 0.84 at S = 16 and 32** — it rises at
exactly the strides where gcd(S, 16) > 1 and by exactly the number of blocks that land in one group under a
16-group mapping (2, 4, 8 of the 8); the instruction's time is unchanged at S = 4 and 12, **1.65× at S = 8 and
24, 2.62× at S = 16 and 32**, and at the baseline (0.0856 system-counter ticks ≈ 1.7 ns) everywhere else
in 1..32. Upstream's 16 groups and its "adjacent rows → adjacent banks, group = bank mod 16" mapping are what
the counter and the clock both show; upstream's cost ("8 cycles per repeat at S = 16 against 1–2") is
measured as 2.62× on this part, and a two-blocks-per-group collision (S = 4) registers on the counter without
costing time. Not established: the bank COUNT 48 and the bank SIZE 4 KB — the sweep sees groups, not banks
(the bank-conflict counter's 0.30 / 0.19 / 0.0 pattern at S = 4 / 8 / 16 is recorded, not interpreted).

Inference, stated separately: the tiering 1.0 / 1.0 / 1.65 / 2.62 for 1 / 2 / 4 / 8 blocks per group says a
group serves two blocks per cycle without penalty and serialises beyond — consistent with upstream's "one
32-B row per group per cycle" only if the counter's 0.45 at two-per-group is counting a hidden stall.

## 2 · The wrong branch this removes
Without the bank geometry, an agent treats UB as flat and allocates its tensors back to back —
which is the natural thing to do and the specific thing that creates aliasing. Two buffers whose
start addresses differ by a multiple of the group stride put their corresponding DataBlocks in the
same group on every repeat, and a Vector instruction that reads both then serialises. The
resulting slowdown appears in `aiv_vec_ratio` as if the Vector unit were the bottleneck, so the
agent's next move is to optimise the arithmetic — the one thing that will not help. The number
that makes the diagnosis possible is 16 (the group count), and without it the padding fix (0016)
is a guess.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md` §2.2.2, line 37,
in a two-row per-architecture table:
```
| 芯片 | UB 大小 | Bank 数 | Bank Group 数 | 每组 Bank 数 | 每 Bank 大小 | 每行大小 |
| DAV_2201 | 192 KB | 48 | 16 | 3 | 4 KB (128 行) | 32 B |
```
Line 25, the same fact in prose with a chip name: "以 Ascend 910B 为例：UB (192KB) = 48 bank × 4KB
= 16 bank group × 3 bank/group。不同芯片的 bank 数可能不同，需查阅对应硬件手册。" — note the
file's own caveat that bank counts differ by chip, which is why this entry does not extend past
DAV_2201.

Group membership, lines 40-44: "**Bank Group 组成方式**：group 内各 bank 的编号满足
`bank_id % num_groups` 相同。以 220x 为例：group 0: bank 0, 16, 32 / group 1: bank 1, 17, 33 /
… / group 15: bank 15, 31, 47".

Arithmetic check performed here, not taken on trust: 48 × 4 KB = 192 KB ✓; 16 groups × 3 banks =
48 ✓; 4 KB / 32 B = 128 rows ✓. The three statements are mutually consistent, which is a weak but
real signal — an inconsistent triple would have been a finding.

Second same-repo statement, `ops/ascendc-performance-analysis/references/metrics_reference.md`
§3.5, lines 162-169:
```
### 3.5 UB Bank 结构（910B/950/A2/A3）
总 bank 数:       48
bank group:       16 组（每组 3 个 bank）
单 bank 大小:     128 行 × 32B = 4KB
每周期访问:       每个 bank group 1 行（32B）
```
The 910 numbers agree exactly. **But its heading scope does not**: it claims one structure for
910B *and* 950, whereas ub_resident's table gives DAV_3510 a different geometry entirely (16 banks
of 16 KB, 8 groups of 2). Filed as `harvest/contradictions-910.md` **C-910-001**. This matters to
the 910 book not because the 950 row is our problem — it is not — but because the metrics table's
scope line is demonstrably wrong, which withdraws it as an independent check on our row. Same repo
made it one origin anyway; the conflict makes it a weak one.

The "每周期访问：每个 bank group 1 行（32B）" line comes only from metrics_reference and is the
throughput half of the geometry — 16 groups × 32 B = 512 B per cycle if every group is busy.
That product is arithmetic performed here and is NOT an upstream claim; it is offered as the
quantity §4 would measure, not as a fact.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; refuse substitution.
2. Geometry is not directly queryable, so it is inferred from a conflict sweep. Build one kernel
   running `Adds(dst, src, scalar, MASK, 1, {1, S, 1, S})` at fixed shape, with `S` (the block
   stride) swept over 1..32. Same binary otherwise; md5 the build per `S` to confirm only the
   template parameter changed.
3. Per `S`, collect `aiv_vec_bankgroup_cflt_ratio` and `aiv_vec_ratio` from
   ResourceConflictRatio.csv and PipeUtilization.csv, on device — the conflict counters are
   explicitly device-only and unavailable in simulation (see 0052), so a simulator run cannot
   substitute for this.
4. Five repeats per `S`, first discarded as warm-up, report the median and the spread.

**As run (2026-08-25, the 910 machine, die 0, job bank910):** one binary; S a runtime argument (the
`srcBlkStride` field of `UnaryRepeatParams`, dst stride 1, repeat 1 so only block strides act), fp16,
128-element mask, 20000 back-to-back instructions per launch over an 8·S·32-byte UB source; every S from 1
to 32 timed in-kernel (`GetSystemCycle()`, ≈ 50 MHz), the counters collected under msprof for S ∈ {1, 2,
4, 8, 12, 16, 24, 32} (the CSV op_summary on this machine carries `aiv_vec_bankgroup_cflt_ratio` and
`aiv_vec_bank_cflt_ratio`). Deviations: the "md5 per S" of the text is moot (S is a runtime argument, one
binary); repeats = the 20000-instruction loop rather than five launches — the spread of the timing
baseline across the 27 non-conflicting S values is 0.0848–0.0861 (1.5 %), which is the floor used.

## 5 · Checker — acceptance declared before the run
Verdict variable `conflict_period`: the smallest `S > 0` at which
`aiv_vec_bankgroup_cflt_ratio` rises above the sweep's own baseline, where the baseline is defined
BEFORE the sweep as the median ratio at `S = 1` plus three times its spread over the five repeats.
PASS iff `conflict_period == 16` and the ratio peaks again at multiples of 16.
Red inputs, stated now: a period of 8 (which would be the DAV_3510 geometry and would mean the
per-arch table is inverted), or no rise at any `S` (which would mean the counter is not wired on
this part and the whole sweep is uninformative — recorded as INCONCLUSIVE, not PASS).
The baseline-from-`S=1` construction is what stops this being a checker that reads only the lines
it expects: the threshold is derived from the run's own quiet arm rather than asserted, so an
instrument that reports a constant value cannot pass.
Exit code is not the verdict.

## 6 · Evidence
RUN 2026-08-25, 910B2 die 0 (idle before and after; curFreq 800 MHz). Correctness: dst[0] = 0x4000 (1.0 + 1.0)
at every S.

**Time per instruction (system-counter ticks, 20000 instructions), S = 1..32:**

| S | ticks / instr | × baseline |
|---|---|---|
| 1 | 0.0857 | 1.00× |
| 2 | 0.0855 | 1.00× |
| 3 | 0.0854 | 1.00× |
| 4 | 0.0855 | 1.00× |
| 5 | 0.0854 | 1.00× |
| 6 | 0.0853 | 1.00× |
| 7 | 0.0854 | 1.00× |
| 8 | 0.1409 | 1.65× |
| 9 | 0.0860 | 1.00× |
| 10 | 0.0854 | 1.00× |
| 11 | 0.0861 | 1.01× |
| 12 | 0.0858 | 1.00× |
| 13 | 0.0856 | 1.00× |
| 14 | 0.0861 | 1.01× |
| 15 | 0.0856 | 1.00× |
| 16 | 0.2238 | 2.61× |
| 17 | 0.0861 | 1.01× |
| 18 | 0.0856 | 1.00× |
| 19 | 0.0856 | 1.00× |
| 20 | 0.0858 | 1.00× |
| 21 | 0.0848 | 0.99× |
| 22 | 0.0856 | 1.00× |
| 23 | 0.0858 | 1.00× |
| 24 | 0.1409 | 1.65× |
| 25 | 0.0854 | 1.00× |
| 26 | 0.0857 | 1.00× |
| 27 | 0.0858 | 1.00× |
| 28 | 0.0857 | 1.00× |
| 29 | 0.0854 | 1.00× |
| 30 | 0.0856 | 1.00× |
| 31 | 0.0859 | 1.00× |
| 32 | 0.2241 | 2.62× |

**msprof ResourceConflictRatio (20000 instructions):**

| S | aiv_time µs | bankgroup_cflt_ratio | bank_cflt_ratio |
|---|---|---|---|
| 1 | 36.912 | 0.0 | 0.003 |
| 2 | 36.623 | 0.0 | 0.003 |
| 4 | 36.786 | 0.453 | 0.302 |
| 8 | 59.008 | 0.659 | 0.188 |
| 12 | 36.949 | 0.451 | 0.301 |
| 16 | 92.424 | 0.842 | 0.0 |
| 24 | 59.377 | 0.655 | 0.187 |
| 32 | 92.62 | 0.84 | 0.0 |

§5 read literally: `conflict_period` (first rise above the S = 1 baseline of 0.0) = **4**, not 16 → not
PASS; red input "period 8" not met (S = 8 is neither the first rise nor the peak); red input "no rise" not
met. The counter peaks at S = 16 and 32 (0.84) as the PASS clause's second half requires. Refinement: the
ratio tracks blocks-per-group under a 16-group mapping — 2 (S ≡ 4 mod 8) 0.45, 4 (S ≡ 8 mod 16) 0.66, 8
(S ≡ 0 mod 16) 0.84 — and the clock only pays from 4 per group.

## 7 · Scope limits — what this entry does NOT establish
The bank count (48) and bank size (4 KB) are not measured — the sweep resolves GROUPS (period 16 in the block
stride) and the bank counter's pattern is recorded uninterpreted; the row-to-bank mapping is inferred from
the tiering, not read from a document. One instruction form (`Adds`, fp16, 8 blocks, repeat 1); one part;
one clock state (800 MHz — the tick-per-instruction figures scale with it, the ratios do not). The 0.45
counter reading at two blocks per group with no time cost is reported, not explained. Nothing transfers to
the 950 book (RULES.md Art. 1) — on 950PR the same instruction form showed NO conflict at any stride (950:0314 §4).
