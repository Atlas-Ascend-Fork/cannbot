```
ID:        0135-the-cross-core-borrow-r-trigger-is-stated-as-r-4096-in-prose-and-r-16384-in-the-mode-table
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scan/fallback/tiling-flow.md:212,158-159,191
           and scan/fallback/script/scan_tiling.py:81-82 — "**触发**：`M×N` 极小 ... 且 R 超长
           （如 R≥4096）" · "MIN_SEG = 8192; if M * 2 < core_num and R >= MIN_SEG * 2:" ·
           "| 3+4 | N==1, M*2 < core_num, R >= 16384 |" · "if items * 2 < core_num and r >= 4096:
           rBorrow = min(core_num, ceil_div(r, 1024))"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured sweep on a named 950 board locating the R at which cross-core borrowing
           starts to pay — if it falls cleanly at 4096 the mode table is wrong, if at 16384 the
           prose and the script are wrong, and either outcome corrects this entry in place.
```

# 0135 · The cross-core borrow-R trigger is stated as R ≥ 4096 in prose and R ≥ 16384 in the mode table

## 1 · Claim
Upstream asserts, in the section that defines cross-core R borrowing, that the trigger is
`M×N` very small together with a very long R, `如 R≥4096`. Upstream asserts, in the mode-selection
pseudocode in the same file, `MIN_SEG = 8192` with the condition `R >= MIN_SEG * 2`, i.e.
R ≥ 16384. Upstream asserts, in the mode quick-reference table nine lines below that pseudocode,
`N==1, M*2 < core_num, R >= 16384`. Upstream asserts, in the family's reference script,
`if items * 2 < core_num and r >= 4096`. The two thresholds differ by 4×. Upstream also states
the minimum segment length two ways: `MIN_SEG = 8192` in the pseudocode against
`rBorrow = min(core_num, ceil_div(r, 1024))` in the script, i.e. a 1024-element minimum segment —
an 8× difference in the same quantity. Not established here; this entry records the disagreement.

## 2 · The wrong branch this removes
The 4× gap sits directly on the most common 1D scan sizes. An agent tiling a `[8192]` Cummin gets
cross-core borrowing under the prose and the script, and per-row Kogge-Stone under the mode table
and its pseudocode. Those are different kernels with different workspace requirements, different
synchronisation, and — per the family's own account (0132) — a very different core count. No check
downstream disagrees with either: both plans are schema-valid and both produce correct output.

The `MIN_SEG` gap is the sharper one because it changes the *shape* of the split rather than
whether it happens. At `R = 100000` with `core_num = 72`, the pseudocode gives
`segs = min(72/M, R/8192)` — at most 12 segments — while the script gives
`rBorrow = min(72, ceil(100000/1024)) = 72`. Twelve segments versus seventy-two is a six-fold
difference in `usedCoreNum`, in the workspace size (`workspaceBytes` scales with segment count,
0132), and in the length of the Phase-B ordered carry chain. An agent that reads the script and an
agent that reads the flow document produce plans that are not variants of each other.

## 3 · Ground / Source
Statement A — the section that owns the branch, `scan/fallback/tiling-flow.md:212`:

```
**触发**：`M×N` 极小（切行只能用满极少核，`items ≪ core_num`）且 R 超长（如 R≥4096）。典型 1D `[1000003]`（M=N=1）。
```

Statement B — the mode-5/3/4 selection pseudocode in the same file, `:157-165`:

```
    # ---- mode 3/4：跨核借 R（行数喂不饱核且 R 足够长）----
    MIN_SEG = 8192
    if M * 2 < core_num and R >= MIN_SEG * 2:
        segs = core_num / M
        segs = min(segs, R / MIN_SEG)
        if segs > 1:
            segLen = ceil(R / segs)
            segs = ceil(R / segLen)          // 回推丢掉空核
            → mode 3(Phase A) + mode 4(Phase B), wsSegs=segs, blockDim=M*segs
```

Statement B again, in the quick-reference table, `:191`:

```
| 3+4 | N==1, M*2 < core_num, R >= 16384 | 跨核借 R + SyncAll + 向量化 ReadCarry | cum_core_partition_scan |
```

Statement A again, in the reference script, `scan/fallback/script/scan_tiling.py:80-85`:

```python
    # 跨核借 R 判定：M×N 极小 + R 超长，切行仍严重用不满核
    if items * 2 < core_num and r >= 4096:
        rBorrow = min(core_num, ceil_div(r, 1024))
        return ScanTiling("core_partition", m, r, n, 1, max(1, n),
                          m, ceil_div(n, max(1, n)), rBorrow, rBorrow,
                          with_index, rBorrow=rBorrow)
```

Note also that the *parallelism* half of the condition differs in form: the pseudocode and the mode
table test `M * 2 < core_num` (rows only), the section prose tests `items ≪ core_num` (work-items),
and the script tests `items * 2 < core_num`. At `N == 1` with one row per work-item these coincide;
at `N > 1` they do not, and the `N > 1` case is exactly the one upstream marks as designed but
unimplemented (`:240`, 0132).

Registered as C-950tiling-014 (the R threshold) and C-950tiling-015 (the minimum segment length).
Under 0104's provenance rule every one of these numbers — 4096, 8192, 16384, 1024 — traces to a
literal with no chip-configuration pedigree, so all are software 经验值 and all are inside the
searchable range that 0106's rule would enumerate rather than obey.

A closing observation about which of the two documents is likely to be read. The script is 106
lines and self-contained with a `__main__` demo; the flow document is 345 lines and the trigger
appears in three separate places within it. A consuming agent that opens the script alone gets
`R ≥ 4096` and `MIN_SEG = 1024` and never sees the other numbers.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. Art. 7:
the disagreement is resolved by a run, not by preferring the code or the prose.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Measure a variance floor first: build one configuration once,
run it 30 times in-process and 5 times across processes, and report the interquartile range as a
fraction of the median.

R ladder at fixed low parallelism. Fix `M = 1`, `N = 1`, fp32 Cummin — the regime both conditions'
parallelism halves agree on — and sweep
`R ∈ {2048, 4096, 8192, 12288, 16384, 24576, 32768, 65536, 1000003}`, which brackets both
thresholds and includes the family's own flagship 1D case. At every R build two kernels with one
compiler pin: cross-core borrowing forced, and the per-row fallback (mode 1 Kogge-Stone) forced.
md5 both binaries. Host echo of `mode`, `rBorrow`/`wsSegs`, `segLen`, `blockDim` and
`workspaceBytes`. Compare both outputs elementwise against a CPU reference and require
bit-identity for min/max; report the first differing index if any. Record `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Segment-length arm, which settles the second contradiction independently of the first. Fix
`R = 1000003`, `M = 1`, and force the segment count to the values the two rules produce —
`segs = min(core_num, ceil(R/1024))` from the script and `segs = min(core_num/M, R/8192)` from the
pseudocode — plus a sweep of intermediate segment counts. Record `aiv_time`, `workspaceBytes` and
the Phase-B carry-chain length at each.

Refuses to assume: that a free die stays free; that a die may be substituted; that `core_num` is
64 or 72 (queried, and both conditions contain it); that the two thresholds must have a single
crossover — the answer may be a band, and a band is reported as a band; that a forced mode is the
mode that ran (host echo required).

## 5 · Checker — acceptance declared before the run
Verdict variable `borrow_cross`, the smallest swept R at which forced cross-core borrowing beats
the per-row fallback by more than the variance floor. Declared before the run: statement A (4096)
is supported iff `borrow_cross ≤ 8192`; statement B (16384) iff `borrow_cross ≥ 12288`; a value
between supports neither and is reported as the measured crossover. If borrowing never wins at any
swept R, `borrow_cross = none`, which would be a stronger result than either and would put the
whole branch in question. The segment arm's verdict is `best_segs`, the segment count with the
lowest median time at `R = 1000003`, compared against the 12 and 72 the two rules predict.

The exit code is not the verdict. The blind mode: forcing cross-core borrowing on an R below the
host's own threshold may be silently refused, in which case both arms are the same kernel, the
times match at every R, and `borrow_cross = none` would be reported from an experiment that never
ran the branch. The guard is structural — the borrowing arm must echo `rBorrow > 1`, a non-zero
`workspaceBytes` and `blockDim > 1` at every R, and the checker goes red at any R where it does not
rather than recording a comparison. Second guard: the elementwise output comparison runs at every
point, because a segment count the host did not expect is more likely to produce a carry bug than a
slow run.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not pick a threshold — Art. 7 forbids resolving a
contradiction by preferring an author — and it does not establish that either number is right. It
does not establish `core_num`, which appears in both conditions' parallelism halves. It does not
resolve whether the parallelism test should count rows or work-items; that difference only bites
at `N > 1`, a path upstream marks unimplemented. It does not establish that the crossover is a
single R rather than a region, and the procedure is written to report a band if that is what it
finds. No chip is named anywhere in the scan family, so BOARD is `family-claimed(unverified)` and
the chip is unstated; §4 names 950PR/950DT because that is where our run would happen. Nothing
here is established for any 910-family board.
