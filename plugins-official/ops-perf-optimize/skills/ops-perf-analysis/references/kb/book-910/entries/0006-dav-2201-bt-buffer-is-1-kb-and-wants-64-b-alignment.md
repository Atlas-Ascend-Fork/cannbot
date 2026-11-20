```
ID:        0006-dav-2201-bt-buffer-is-1-kb-and-wants-64-b-alignment
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:84 — "| BT | `bt_size` | 1 KB (1024) |" (§2.3 DAV_2201); ops/ascendc-performance-analysis/references/metrics_reference.md:415 — "| BT Buffer | 1KB，64B 对齐 | — |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a DAV_2201 part reports a BT capacity other than 1024 bytes, or accepts a bias table whose base address is not 64 B aligned without penalty or error.
```

# 0006 · DAV_2201's BT buffer is 1 KB and wants 64 B alignment

## 1 · Claim
Upstream asserts that DAV_2201 has a Bias Table buffer of 1 KB (1024 bytes), reached via MTE1 from
L1, and that its alignment requirement is 64 B. Upstream asserts that the two earlier generations
DAV_1001 and DAV_2002 have no BT buffer at all. Not established here.

## 2 · The wrong branch this removes
A Matmul agent plans a per-tile bias residency sized to `baseN` without checking it against 1 KB.
At fp32 that is 256 elements — a `baseN` of 512 does not fit, and the tiling silently needs a
second BT load per tile that the cost model never accounted for. The reason the normal checks miss
it: BT is not one of the buffers a `GetCoreMemSize`-shaped budget check usually enumerates (UB,
L1, L0A/B/C), and unlike those it has no obvious presence in the kernel's tensor declarations —
the bias path is inside the Matmul high-level API. An agent auditing its own UB and L1 budgets can
be complete on both and still be wrong here.

## 3 · Ground / Source
`ops/npu-arch/references/npu-hardware-params.md` §2.3, line 84: `| BT | \`bt_size\` | 1 KB (1024)
|`. Same file §3, line 151: `| BT | — | — | 1 KB | 1 KB | 4 KB |` across DAV_1001 / DAV_2002 /
DAV_2201 / DAV_3002 / DAV_3510 — the em-dashes for the first two generations are stated in §2.1
and §2.2 as "— (不存在)".

Alignment, from a different skill but the same repo (one origin, RULES.md Art. 3):
`ops/ascendc-performance-analysis/references/metrics_reference.md:148` — "| BT Buffer | **64B** |
|" in the §3.3 alignment table, and line 415 in the §7 constraint table — "| BT Buffer | 1KB，64B
对齐 | — |". The data path is given at line 26 of the same file: "| **MTE1** | Move To Engine 1 |
L1 → L0A/L0B, L1 → BT Buffer | Cube 数据加载 |".

Related contradiction, NOT this book's to resolve: the same metrics table (line 123) gives BT
1 KB for the 950 column, where npu-arch gives 4 KB. That is `harvest/CONTRADICTIONS.md` C-002 and
belongs to book-950; it is cited here only because it means the metrics table's BT row is known to
be wrong in one of its columns, which is a reason to weight the npu-arch figure for our column
too — a reason, not a resolution.

## 4 · Procedure
Proposed, runnable later; not run.

1. Capacity: fold `CoreMemType::BT` into the single-pass query of 0004 §4. Name the die; occupancy
   before and after; no substitution.
2. Alignment: this half needs its own arm, because a capacity readout says nothing about
   alignment. Build two Matmul kernels differing only in the byte offset of the bias tensor's base
   address within L1 — one 64 B aligned, one offset by 32 B — same shapes, same tiling, same
   build flags, md5-compare the two binaries to confirm only the offset differs. Run both on the
   named die, back to back, alternating order, and record both correctness (bit-compare against
   the aligned arm) and `aic_mte1_ratio` from PipeUtilization.csv.
3. Record the arm that did not bite, if the unaligned arm is simply rejected at build time — that
   is a legitimate and informative outcome, not a failed experiment.

## 5 · Checker — acceptance declared before the run
Two verdict variables, reported separately and never combined into one boolean.
`bt_bytes`: PASS iff `== 1024`. Red input: 4096.
`align_effect`: the pair (bitwise_identical, mte1_ratio_delta) from step 2. The alignment half of
the claim is upheld iff the unaligned arm either fails to build, produces different results, or
shows an `mte1_ratio` increase outside the run-to-run spread — which must be established first
from three repeats of the *aligned* arm against itself, before the arms are compared. Without that
baseline spread the comparison has no threshold and the checker cannot go red honestly.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; per-arch. The capacity and the alignment come from two
different upstream files and are two different claims sharing one entry because they share a wrong
branch — a run that establishes one does not establish the other, and §5 keeps them separate for
exactly that reason. This entry does not establish what happens when a bias exceeds 1 KB (whether
the API splits, spills, or fails), nor whether the 64 B alignment is a hardware requirement or a
performance preference — upstream's two statements do not distinguish those, and the §4 procedure
is designed to tell them apart rather than to assume.
