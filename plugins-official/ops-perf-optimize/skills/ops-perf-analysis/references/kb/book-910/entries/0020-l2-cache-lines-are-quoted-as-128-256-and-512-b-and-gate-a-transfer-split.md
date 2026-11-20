```
ID:        0020-l2-cache-lines-are-quoted-as-128-256-and-512-b-and-gate-a-transfer-split
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — drafted from one upstream origin; nothing measured, and no architecture is stated
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-analysis/references/metrics_reference.md:179 — "| L2 Cache | 见 3.1 | 128B / 256B / 512B (Cache Line) | 全芯片共享，缓存 GM 数据 |"; ibid:419 — "| 搬运拆分 | 按 128B/256B/512B 拆分，非对齐向上取整 | 搬运内轴 512B 对齐最优 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a GM-alignment sweep on a named DAV_2201 board shows bandwidth steps at granularities other than 128, 256 and 512 B, or shows no step at 512 B.
```

# 0020 · L2 cache lines are quoted as 128, 256 and 512 B and gate a transfer split

## 1 · Claim
Upstream asserts that the shared L2 cache uses cache lines of 128 B, 256 B and 512 B — three
values, listed without a rule for which applies when. Upstream separately asserts that data
movement is split at those same three granularities with unaligned remainders rounded up, and that
a 512 B-aligned inner axis is optimal. Upstream asserts elsewhere, with a chip name, that 512 B is
the optimal GM alignment on Ascend 910B. No architecture is stated for the cache-line row itself.
Not established here.

## 2 · The wrong branch this removes
An agent aligns its GM accesses to 32 B — the DataCopy requirement (0021), the number every
alignment discussion in the API documentation is about — and considers alignment handled. It is
handled for *correctness* and not for *bandwidth*: per 0024, the 32 B-aligned case reaches roughly
70 % of the 512 B-aligned case on Ascend 910B. The 32 B rule and the 512 B rule live in different
documents, answer different questions, and the smaller number is the one an agent meets first
because it is the one that causes visible failures. Alignment that is merely legal is the wrong
branch here.

The rounding-up half matters independently: a transfer split at 128/256/512 B with unaligned
remainders rounded up means a request of 520 B costs a full extra unit. An agent tiling to a
"nice" element count in the data's own units can land just past a boundary on every tile.

## 3 · Ground / Source
`ops/ascendc-performance-analysis/references/metrics_reference.md` §3.6, line 179:
```
| L2 Cache | 见 3.1 | 128B / 256B / 512B (Cache Line) | 全芯片共享，缓存 GM 数据 |
```
§7 硬件约束速查表, line 419: `| 搬运拆分 | 按 128B/256B/512B 拆分，非对齐向上取整 | 搬运内轴 512B
对齐最优 |`, and line 409: `| GM 对齐 | 非 512B 对齐带宽降 30% | Tiling 保证内轴对齐 |`.
§3.3 对齐要求, line 150: `| GM 搬运（最优） | **512B** | ≥16KB 数据量时可达峰值带宽 |`.

The chip-named version, same repo (one origin) but with a board family attached —
`ops/ascendc-performance-best-practices/reference/common/datacopy_optimization_design.md:29`:
"通过按设备最优粒度的 GM 对齐（如 Ascend 910B 为 512B）最大化带宽利用率" and line 245:
"7. **GM 按设备最优粒度对齐**：Kernel 入参（包括 Workspace/Tiling）地址通常已保证对齐，开发者需
关注偏移量是否保持该设备的最优对齐粒度（如 Ascend 910B 为 512B，其他设备需查阅手册或实测确认）。"
That file's numbers are carried by 0024, which is where the measured claim and its missing
conditions live; here only the 512 B granularity is taken.

**What is missing, stated plainly**: no source in scope says which of 128 / 256 / 512 B is the L2
line size under what condition. Three values in one cell with no selector is not a specification.
The 512 B figure has independent support as an *alignment optimum*, which is a different property
from a line size — they may coincide or may not, and nothing here establishes that they do.
That conflation is exactly the "measurement and inference in one sentence" species and is refused:
this entry claims the three quoted numbers and the alignment advice, and does not claim that the
L2 line is 512 B.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Offset sweep: one DataCopy kernel, fixed transfer size (64 KB, comfortably above the 16 KB
   peak-bandwidth threshold quoted at line 150), GM source offset swept over
   {0, 32, 64, 128, 256, 384, 512, 544} B. Same binary, offset passed as a runtime argument, so no
   build differences exist at all.
3. Record achieved bandwidth (bytes / `aiv_mte2_time`) per offset, five repeats, first discarded.
4. Second sweep for the rounding claim: offset fixed at 0, transfer size swept over
   {504, 512, 520, 1016, 1024, 1032} B, looking for a step at each 512 B boundary rather than a
   linear rise.

## 5 · Checker — acceptance declared before the run
Verdict variables: `bw(offset)` from sweep 1 and `t(size)` from sweep 2.
The alignment claim is upheld iff `bw(0) ≈ bw(512)` and both exceed `bw(32)` by a margin larger
than three times the spread at offset 0. The margin threshold is derived from the run's own
repeats, declared before the arms are compared.
The granularity claim is upheld iff `bw` shows steps at 128 and 256 as well — a monotone decline
with no structure would mean the three quoted numbers describe nothing observable, which
overturns the granularity half while leaving the 512-is-best half intact. The two halves are
reported separately for that reason.
The rounding claim is upheld iff `t(520) ≈ t(1024)` rather than `t(520) ≈ t(512)`.
Red input for the whole procedure: `bw` flat across all offsets, which would mean either the part
does not care about alignment or the measurement is not resolving it — distinguished by checking
that `bw(0)` at 64 KB exceeds `bw(0)` at 1 KB, the known-good bandwidth-versus-size effect. If
that control is also flat, the run is VOID.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. **The source states no architecture** for the cache-line row;
the 512 B alignment optimum has a chip-family attribution ("Ascend 910B", a SocVersion spanning
six parts, not a board). This entry does not establish the L2 line size — see §3. It does not
establish the 30 % bandwidth penalty figure of line 409 or the 70 % figure of 0024; those are
measured-voice claims with their own scoping problems and are handled in 0024. It does not
establish that the split granularities apply to MTE3 as well as MTE2, nor whether they differ
between GM→UB and GM→L1. It says nothing about the interaction with L2 cache hints.
