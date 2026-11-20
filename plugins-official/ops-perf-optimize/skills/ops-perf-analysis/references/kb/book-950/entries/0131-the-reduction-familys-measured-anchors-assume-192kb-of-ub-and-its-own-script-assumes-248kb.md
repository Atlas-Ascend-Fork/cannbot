```
ID:        0131-the-reduction-familys-measured-anchors-assume-192kb-of-ub-and-its-own-script-assumes-248kb
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/reduction/fallback/example/euclidean_norm/experience.md:5,91
           — "平台：Ascend 950 / arch35（dav-3510），CANN 9.0.0，coreNum=72，UB≈192KB。数据全部
           msprof 上板实测。" and "host 自检（g++ 纯 host，coreNum=72, UB=192KB）" ;
           reduction/fallback/script/reduction_tiling.py:57-58 — "ub_size: int = 248 * 1024" ·
           "core_num: int = 64"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a runtime capacity query on a named 950 board returning a usable UB that matches one of
           the two values — that value is then this board's, the other is wrong for it, and every
           budget calibrated at the loser must be re-derived.
```

# 0131 · The reduction family's measured anchors assume 192 KB of UB and its own script assumes 248 KB

## 1 · Claim
Upstream asserts, in a measurement banner, that its EuclideanNorm data were taken on
`Ascend 950 / arch35（dav-3510）`, CANN 9.0.0, with `coreNum=72` and `UB≈192KB`, all figures
`msprof 上板实测`. Upstream asserts, in the same family's reference script, defaults of
`ub_size = 248 * 1024` and `core_num = 64`. Upstream asserts, in the Softmax case file's worked
example, `假设 ub_size=248KB`, and computes `used_core_num` from an implied `core_num = 64`. The
same skill's own bound-diagnosis reference states UB as `192KB / 910B2, 248KB / 950`. The two UB
values differ by 29 % and the two core counts by 12.5 %, and every UB budget in this family — five
template budgets, two interleaved budgets, the BlockSplitR gate and its workspace sizing — is a
function of both. Not established here: this entry records the disagreement, not a value.

## 2 · The wrong branch this removes
Every quantitative artifact in this family inherits whichever number the reader happens to pick,
and the two numbers disagree by enough to change decisions rather than just sizes. The
FullLoad/Recompute boundary is `R ≤ (ub_size − tmp_buf − 64) / (2 × dtype_bytes)` (0123): at FP32
with `tmp_buf = 4096` that is R ≤ 23 936 at 192 KB and R ≤ 31 104 at 248 KB, so a case with
R = 28 000 routes to a different template under each. The interleaved gate `chunkA0 == A0` (0128)
is a *routing* condition computed from `ubSize`, so the same shape can hit or miss the fast template
depending on which capacity the host believes. BlockSplitR's `rGroupCnt` (0124) depends on
`coreNum`, so the published anchors (`rGroupCnt = 61`, `usedCoreNum = 61`, `workspaceBytes = 7808`)
are reproducible only at 72 and not at 64.

The wrong branch, then, is not "using the wrong number" — it is reproducing upstream's self-check
at the script's defaults, getting different values, and concluding the derivation is wrong. It is
not wrong; it is calibrated at a different capacity, and nothing in either file says so.

The second wrong branch is treating 192 KB as an error to be corrected up to 248 KB. It may be a
deliberate conservative host-side model — usable UB after whatever the runtime reserves — rather
than a mistake. Upstream's sort family does exactly that distinction explicitly, stating 240 KiB
usable of 248 KiB physical (0140), and it is the only place in this subtree where the difference is
named. Neither reduction file makes the claim either way, so the honest reading is: unknown.

## 3 · Ground / Source
The measurement banner, `reduction/fallback/example/euclidean_norm/experience.md:5`:

```
> 平台：Ascend 950 / arch35（dav-3510），CANN 9.0.0，coreNum=72，UB≈192KB。数据全部 msprof 上板实测。
```

The host self-check header, same file `:91`:

```
host 自检（g++ 纯 host，coreNum=72, UB=192KB）：
```

restated in the flow document at `reduction/fallback/tiling-flow.md:201`:

```
> **验证锚点**（g++ 纯 host，coreNum=72, UB=192KB）：#1 `[64000,32]` axes[0] → `templateType=1`（group），
> `rGroupCnt=61`、`usedCoreNum=61`、`workspaceBytes=61×32×4=7808`
```

The script defaults, `reduction/fallback/script/reduction_tiling.py:57-58`:

```python
    ub_size: int = 248 * 1024
    core_num: int = 64
```

The Softmax worked example, `reduction/fallback/example/softmax/experience.md:146-147`:

```
- 假设 ub_size=248KB：rows_per_ub ≥ 1 → **AR-FullLoad**
- 多核: rows_per_core = ceil(32/64) = 1，used_core_num = 32
```

(`ceil(32/64) = 1` is only consistent with `core_num = 64`.)

Both values are declared inputs, not derived: `reduction/fallback/index.md:40` lists
`平台参数：ub_size（单核 UB 可用字节）、core_num（可用核数）` among the algorithm's inputs, and
`tiling-fields.md:19` sources `core_num` as `平台参数`. So under 0104's provenance rule both are
chip specification fields — hardware constraints to be queried, not searched — and the correct
handling is neither 192 nor 248 but a runtime query (0141 records upstream's own instance of doing
exactly that, in the sort family). The defect is that two files in this family hardcode a platform
parameter that the family's own input list says comes from the platform.

Registered as C-950tiling-009. It extends `harvest/CONTRADICTIONS.md` C-004 (which recorded the
same 192-vs-248 pair between this skill's `single-core-pipeline/vec.md:102` and this very
experience file) and intersects C-006 and C-007 (the four UB and five `coreNum` script defaults
across this subtree, cited and not duplicated here). What this entry adds to C-004 is the
consequence inside one family: the 192 KB figure is not a stray sentence, it is the calibration
point of five template budgets, two interleaved budgets, a routing gate and three published
self-check anchors — so it is the value that would have to move, or all of them would.

A re-verification note on C-007. That row attributes the value 72 to `(scan, reduction)` script
defaults. Re-checking the files: `scan/fallback/script/scan_tiling.py:103` does pass
`core_num=72, ub_size=192 * 1024`, but that is a call in the script's demo block, not a dataclass
default; and `reduction/fallback/script/reduction_tiling.py:58` defaults to `core_num: int = 64`,
not 72. The reduction family's 72 comes from the *experience* file quoted above, not from its
script. The contradiction stands; the attribution in C-007's parenthesis does not, and this is
reported rather than corrected in place, since `harvest/CONTRADICTIONS.md` is not this agent's file
to edit.

## 4 · Procedure
Proposed. The decisive arm needs a named 950 board; a second arm needs no device and has not been
run either.

Host-only arm (no device, permitted in this phase, not run): compile the reduction tiling host with
g++ alone and evaluate the three published anchors at both configurations — (`coreNum=72`,
`UB=192KB`) and (`coreNum=64`, `UB=248KB`) — recording `templateType`, `rGroupCnt`, `usedCoreNum`
and `workspaceBytes` for each. This does not say which capacity is real; it quantifies how much the
answer moves, which is the number a consumer needs in order to know whether the ambiguity matters
for their shape.

Device arm. Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at
20 s spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after
and discard the case if the die moved. Board named explicitly (950PR or 950DT), and a result on one
is not a result on the other.

Query, then probe. First, read the usable UB from the platform at runtime — the
`GetCoreMemSize(CoreMemType::UB)`-style accessor upstream itself uses at
`sort/topk_host_tiling.md:81` (0141) — and print it with the toolkit pin and the board identifier.
Second, because a query returns what the runtime reports rather than what is allocatable, probe it:
allocate a single UB buffer and walk its size upward in 4 KB steps from 176 KB to 256 KB, building
and launching a trivial kernel at each size, and record the largest size that builds, launches and
produces correct output. The probe is the measurement; the query is a claim by the runtime about
itself.

Third, the routing consequence: take one reduction case with R chosen to sit between the two
FullLoad boundaries (R = 28 000, FP32, A0 = 1) and record which template the host selects at each
configured capacity and which is actually faster on the board.

Refuses to assume: that the queried value is the allocatable value (the probe is what settles it);
that 950PR and 950DT share a capacity; that a free die stays free; that a die may be substituted;
that "UB" means the same thing in both sources — one says `单核 UB 可用字节` (usable per core) and
the other says nothing, so the probe result is reported as *allocatable* bytes with that word
attached.

## 5 · Checker — acceptance declared before the run
Verdict variable `ub_allocatable`, the largest buffer size in the probe that builds, launches and
produces correct output, on the named board with the recorded toolkit pin. Declared before the run:
the 248 KB reading is supported iff `ub_allocatable ∈ [244, 256] KB`; the 192 KB reading iff
`ub_allocatable ∈ [188, 200] KB`; any other value supports neither and is reported as the number
measured. A second verdict `ub_queried` records what the runtime accessor returned, and the pair
`(ub_queried, ub_allocatable)` is reported together — a gap between them is the "usable versus
physical" distinction (0140) made visible, and is itself a finding. A third, `core_queried`, settles
64 versus 72 the same way.

The exit code is not the verdict. The blind mode: an allocation that silently succeeds by spilling
or by being lazily backed would make the probe report a capacity that does not exist. The probe's
kernel therefore writes a known pattern across the whole buffer and reads it back, and a size counts
as working only if every byte round-trips; a size that "allocates" but fails the pattern check is
recorded as failing. The checker also fails red if `ub_queried` is unavailable, rather than
substituting a literal — substituting is the defect this entry is about.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The `UB≈192KB`,
`coreNum=72` and CANN 9.0.0 figures are upstream's statement about upstream's platform; the 248 KB
and 64 are upstream's script defaults. This book has queried nothing and probed nothing.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not say which value is right — Art. 7 forbids resolving a
contradiction by preferring an author — and it does not establish that either is right for any
board. It does not establish whether the gap is error or a deliberate conservative usable-UB model;
upstream never says, and both readings are recorded. It does not establish the core count. It does
not extend to the other families' UB literals (C-006 lists four values across this subtree,
C-007 five core counts; both are cited, not duplicated, and the sort family's chip-scoped
240-of-248 KiB figure is 0140's subject). The re-verification note about C-007's attribution is
reported here and in this agent's final report; `harvest/CONTRADICTIONS.md` is not edited by this
agent. `Ascend 950 / arch35 (dav-3510)` names a family, not a board, so BOARD is
`family-claimed(unverified)` even though this is the most fully identified measurement in the
domain; §4 names 950PR/950DT because that is where our run would happen. Nothing here is
established for any 910-family board, and the `192KB / 910B2` half of C-004 belongs to that book,
not this one.
