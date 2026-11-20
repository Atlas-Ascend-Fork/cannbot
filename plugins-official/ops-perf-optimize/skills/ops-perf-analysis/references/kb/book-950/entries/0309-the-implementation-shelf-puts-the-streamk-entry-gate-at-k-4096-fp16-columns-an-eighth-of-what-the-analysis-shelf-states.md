```
ID:        0309-the-implementation-shelf-puts-the-streamk-entry-gate-at-k-4096-fp16-columns-an-eighth-of-what-the-analysis-shelf-states
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled.
           The two shelves that disagree are two directories of the SAME repo, so this is one origin
           disagreeing with itself and corroborates nothing (RULES.md Art. 3).
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/streamk_design.md:16-17 —
           "| **Stream-K (SK)** | `mCnt·nCnt ≤ aicNum/2` 且 `K ≥ 4096 (FP16 列)` | 所有 MN 块都做
           K 切分（`kCnt = aicNum / (mCnt·nCnt)`） |" · "| **DP + Stream-K (DP+SK)** | `mCnt·nCnt ≥
           aicNum` 且 `mCnt·nCnt % aicNum ≠ 0` 且余数 ≤ `aicNum/2` 且 `K ≥ 8192/FP16` | ... |"
SOURCE:    same file:332 — "**现象**：打印 `[ERROR] StreamK requires: K >= 4096 and MN split count
           <= half of core number`"
SOURCE:    ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-flow.md:21 —
           "| **StreamK** | K 轴切分给多核，每核负责一段 K，workspace 归约 | K ≥ 32768 且 B=1 且
           无 group |" ; :283-285 — "| **SK** | `Align(K, 256) ≥ max(8192, aicNum×256) /
           sizeof(FP16)` 且 `mCnt×nCnt ≤ aicNum/2` |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a StreamK build on a named 950 board that is admitted and beats its SWAT baseline at
           `K = 4096` FP16 — that kills the `K ≥ 32768` prose rule outright; symmetrically, a build
           at `K = 4096` that the host tiling refuses or that loses to SWAT kills the implementation
           shelf's own gate and vindicates the prose.
```

# 0309 · The implementation shelf puts the StreamK entry gate at K ≥ 4096 FP16 columns, an eighth of what the analysis shelf states

## 1 · Claim
Upstream asserts, in the implementation shelf, that StreamK's SK sub-mode is entered when
`mCnt·nCnt ≤ aicNum/2` and `K ≥ 4096` FP16 columns, and its DP+SK sub-mode when
`mCnt·nCnt ≥ aicNum`, `mCnt·nCnt % aicNum ≠ 0`, the remainder is `≤ aicNum/2`, and
`K ≥ 8192 / sizeof(FP16)` — which is also 4096 columns. Upstream asserts the same 4096 a second
time, inside a runtime error string: `[ERROR] StreamK requires: K >= 4096 and MN split count <=
half of core number`. Upstream asserts, in the analysis shelf of the same repository, that the
StreamK gate is `K ≥ 32768 且 B=1 且无 group`, and — in a formula three hundred lines below that
prose — that SK's gate is `Align(K, 256) ≥ max(8192, aicNum×256) / sizeof(FP16)`. Not established
here: no build was made and no shape was routed.

The arithmetic relation matters and is stated separately from the assertions. At `aicNum ≤ 32` the
analysis shelf's SK formula evaluates to `8192 / 2 = 4096`, which is exactly the implementation
shelf's constant. So two of the three statements agree numerically at small core counts, and the
`K ≥ 32768` prose is the outlier by a factor of eight.

## 2 · The wrong branch this removes
`950:0108` already records that the analysis shelf states its StreamK gate one way and computes it
another. This entry is what a second shelf adds to that: the implementation side, which is where the
kernel actually lives, hard-codes the *computed* value into a user-visible error message. An agent
that reads only the prose rule refuses StreamK for every `K` between 4096 and 32768 — the entire
band where the mode was designed to be used, since StreamK exists for the small-MN long-K regime
and `K = 4096` at `M = N = 512` is upstream's own motivating example.

The reverse branch is available too and is worse operationally. An agent that reads only the
implementation gate loses two conditions the prose carries and the implementation does not:
`B = 1` (no batch) and `无 group`. Neither appears anywhere in `streamk_design.md`. If they are real
constraints, a batched or grouped matmul admitted at `K = 4096` will produce wrong results or hang,
and nothing in the implementation shelf would have warned it.

So the honest disposition is not "4096 wins because two files say it". It is: the *numeric* half of
the disagreement is 2-vs-1 in favour of 4096, the *conditional* half exists only on the prose side,
and neither half is settled until a procedure runs on a named board (RULES.md Art. 7). This entry's job
is to make an agent carry both halves rather than pick the one it read first.

## 3 · Ground / Source
The implementation shelf's sub-mode table, `streamk_design.md:14-17`:

```
| 子模式 | 触发条件（简化） | 切分方式 |
| **Stream-K (SK)** | `mCnt·nCnt ≤ aicNum/2` 且 `K ≥ 4096 (FP16 列)` | 所有 MN 块都做 K 切分
  （`kCnt = aicNum / (mCnt·nCnt)`） |
| **DP + Stream-K (DP+SK)** | `mCnt·nCnt ≥ aicNum` 且 `mCnt·nCnt % aicNum ≠ 0` 且余数 ≤ `aicNum/2`
  且 `K ≥ 8192/FP16` | 稳态轮按 DP 走（K 不切）；仅**最后一整轮**的 tail tile 做 K 切分 |
```

Note the table calls itself `（简化）` — upstream flags its own condition set as abridged, which is
consistent with the missing `B=1` / `无 group` terms and is the reason §2 does not treat the
implementation shelf as authoritative merely for being closer to the code.

Restated in the constraints section, `:274`:

```
1. **只对特定 shape 有收益**：host tiling `IsCapable()` 会拒绝非目标 shape（SK 需 K≥4096 FP16 列
   & mn≤核数/2；DP+SK 需 M/N 256 对齐 & K≥8192/FP16 & 余数≤核数/2）。不在目标区间的 shape 走
   StreamK 反而会因 workspace 归约开销劣化，应退回 pingpong / SWAT。
```

`M/N 256 对齐` appears here and not in the table — a third condition set for DP+SK in one file.

And in a symptom, `:332`, where it is a string a user will actually see:

```
**现象**：打印 `[ERROR] StreamK requires: K >= 4096 and MN split count <= half of core number`；
或即使 shape 满足，性能反而劣化。
```

The analysis shelf, prose form, `tiling-flow.md:21`:

```
| **StreamK** | K 轴切分给多核，每核负责一段 K，workspace 归约 | K ≥ 32768 且 B=1 且无 group |
```

and formula form, same file `:283-285`:

```
| **SK** | `Align(K, 256) ≥ max(8192, aicNum×256) / sizeof(FP16)` 且 `mCnt×nCnt ≤ aicNum/2` |
| **DP+SK** | `M%256==0 ∧ N%256==0 ∧ K ≥ max(8192, aicNum×128) / sizeof(FP16)` ∧ `mCnt×nCnt ≥
  aicNum` ∧ `(mCnt×nCnt) % aicNum ∈ (0, aicNum/2]` |
```

Evaluated: SK at `aicNum = 24` gives `max(8192, 6144)/2 = 4096`; at `aicNum = 32`,
`max(8192, 8192)/2 = 4096`; at `aicNum = 36`, `max(8192, 9216)/2 = 4608`. DP+SK at `aicNum = 24`
gives `max(8192, 3072)/2 = 4096`; the term `aicNum × 128` only dominates above `aicNum = 64`. So the
implementation shelf's constants are the analysis shelf's formulas with the `aicNum` term collapsed
— correct for every installed 950 SKU this book records except a 36-cube-core part, where the
formula says 4608 and the constant says 4096 (`950:0217`).

That last point is the finding inside the finding: the implementation shelf did not merely pick a
number, it **froze an `aicNum`-dependent threshold into a literal**, including into an error string.
On a 36-core part the two shelves disagree by 512 columns and the literal is the permissive one.

The `M/N 256 对齐` condition agrees across shelves; `B = 1` and `无 group` exist only on the prose
side. Recorded as `C-950bp-003`.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. The disagreement is about a
routing threshold, so the procedure sweeps across it rather than testing a point.

Arm 1 — admission. At `M = N = 512, baseM = baseN = 256` (upstream's motivating shape,
`mCnt·nCnt = 4`), sweep `K ∈ {2048, 4096, 8192, 16384, 32768, 65536}` FP16 and record for each:
does host tiling admit StreamK, which sub-mode, and does the error string appear. This alone
adjudicates *which document describes the shipped gate* — and that is a fact about the code, not
about the hardware, so it is the cheap half.

Arm 2 — value. At every admitted point, and at every refused point with the gate patched open, time
StreamK against the SWAT baseline on the same shape. The prose rule is right if StreamK loses below
32768; the formula is right if it wins from 4096. This is the half that decides which threshold is
*correct*, as opposed to which is *implemented*, and only this arm can (RULES.md Art. 7).

Arm 3 — the `aicNum` dependence. Repeat Arm 1 with `aicNum` restricted (fewer visible cores) and
then at the part's full core count, and check whether the admitted threshold moves. The formula says
it should above `aicNum = 32`; the literal says it never does.

Arm 4 — the conditions that exist on one side only. Run a batched (`B > 1`) and a grouped matmul at
an otherwise-admitted point. If either is admitted and produces wrong output or hangs, the prose
shelf's extra conditions are real and the implementation shelf's abridged table is dangerous; if
both are correct, the prose conditions are stale.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, beside
every timing. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard if the die moved. Refuses to assume: that a free die stays free; that a die
may be substituted; that `aicNum` is 24 or any other literal — it is queried and echoed beside every
verdict, because the entire disagreement is about whether the threshold depends on it; that the
workspace budget is available (`0310` — StreamK's workspace note contradicts its own formula, and
Arm 1 records the actual request).

## 5 · Checker — acceptance declared before the run
Verdict `k_admit` = the smallest swept `K` at which Arm 1 admits SK. Declared now, with all three
outcomes named before the run so none can be reinterpreted after: `k_admit == 4096` means the
implementation shelf describes the shipped gate; `k_admit == 32768` means the prose does;
`k_admit == 4608` at a 36-cube-core part means the *formula* does and both literals are wrong.

Verdict `k_pays` = the smallest `K` at which Arm 2's StreamK beats SWAT outside the floor. The
OVERTURN fires in whichever direction `k_pays` lands: `k_pays ≈ 4096` kills the prose rule,
`k_pays ≈ 32768` kills the implementation gate.

Verdict `aicnum_sensitive` = true iff Arm 3's `k_admit` moves with the core count.

Verdict `extra_conditions` = the set of Arm 4 configurations that are admitted and incorrect.
Non-empty means the abridged table omits a real constraint, and that outcome is more important than
either threshold.

The exit code is not the verdict. Three guards. First, every admitted build is compared elementwise
against a CPU reference — StreamK's own defect list (`0310` §2) contains two ways to get a fast
wrong answer, and a routing study that only measures time would rank them highest. Second — the
input that makes this checker go red — Arm 1 is repeated at `K = 1024`, far below every candidate
threshold, where admission **must** be refused. If StreamK is admitted there, the gate is not being
evaluated at all, `k_admit` means nothing, and the run is void. That is a planted positive the
checker has to find, not a clean line it hopes to read. Third, no `k_pays` is reported without the
floor: two thresholds whose builds are within run spread of each other are not ordered.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. 4096, 8192 and 32768 are
upstream's stated thresholds; the evaluations of the analysis shelf's formula at `aicNum` = 24, 32
and 36 are arithmetic done here on paper, not routings observed on a part.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does **not** resolve the disagreement and must not be
read as doing so: both shelves are directories of one repository, two files in one repo are one
origin (RULES.md Art. 3), and a contradiction is resolved only by a procedure on a named board
(RULES.md Art. 7). The 2-vs-1 count is a count of statements, not of independent authorities. The entry
does not establish that `B = 1` and `无 group` are real constraints, nor that they are stale — §4
Arm 4 is the only thing here that would tell. It does not establish which document the shipped
`IsCapable()` implements; neither shelf's source is present in this tree. `aicNum` is never given a
value by either shelf. BOARD is `family-claimed(unverified)`: no file in this family names a chip
(`0347`). Nothing here is established for 950DT if a run happens on 950PR or the reverse, and
nothing transfers to the other book (RULES.md Art. 1).
