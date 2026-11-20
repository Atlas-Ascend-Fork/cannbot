```
ID:        0010-dav-2201-supports-four-to-two-structured-sparsity-which-dav-3510-dropped
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:85 — "| 稀疏 | `sparsity` | 1（支持 4:2） |" (§2.3 DAV_2201); ibid:152 — "| 稀疏 4:2 | — | — | 支持 | 支持 | 不支持 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  the INI field `sparsity` reads 0 on a DAV_2201 part, or a 4:2 structured-sparse Matmul path refuses to build or produces no speed-up against its dense twin on a named DAV_2201 board.
```

# 0010 · DAV_2201 supports 4:2 structured sparsity, which DAV_3510 dropped

## 1 · Claim
Upstream asserts that DAV_2201 sets the INI field `sparsity` to 1, meaning 4:2 structured sparsity
is supported, and that the later DAV_3510 generation sets it to 0 — the capability was removed,
not extended. Not established here.

## 2 · The wrong branch this removes
The wrong branch runs in the direction newcomers do not expect. An agent porting a kernel *from*
the 950 family *to* the 910 family assumes the older part is a subset of the newer one and never
considers a sparse Cube path — leaving a capability unused. An agent porting the other way builds
a 4:2 sparse Matmul that works on 910 and finds it unavailable on 950, and reads the failure as a
toolchain problem rather than an architectural removal. Neither error is visible in a correctness
test: sparsity is a performance path, and the dense fallback (where one exists) is correct.

## 3 · Ground / Source
`ops/npu-arch/references/npu-hardware-params.md` §2.3, line 85: `| 稀疏 | \`sparsity\` | 1（支持
4:2） |`. §2.1 (DAV_1001) line 57 and §2.2 (DAV_2002) line 72 both read "— (不存在)"; §2.4
(DAV_3002) line 99 reads "1（支持 4:2）"; §2.5 (DAV_3510) line 112 reads "0（不再支持 4:2）" —
"不再" ("no longer") is upstream's own word for the removal.

The generational row, line 152: `| 稀疏 4:2 | — | — | 支持 | 支持 | 不支持 |`.

No second origin, and — worth stating plainly — no upstream file in the scope surveyed for this
book explains how to *use* 4:2 sparsity on DAV_2201: no API, no tiling constraint, no measured
speed-up. The capability is asserted as an INI bit and nowhere taught. That absence is recorded in
STANDING_QUESTIONS rather than filled in by inference.

## 4 · Procedure
Proposed, runnable later; not run.

1. Read-only INI arm first, because it is the cheapest and needs no card:
   `grep -Rn "sparsity" "$ASCEND_HOME_PATH"/*/data/platform_config/`, recording the value against
   every SoC name found. This establishes what the installed toolkit believes, which is a
   different claim from what the silicon does (0012).
2. Device arm: name the die, occupancy before and after, no substitution. Build a Matmul whose B
   operand is 4:2 structured-sparse through whatever API the installed CANN exposes, and its dense
   twin at identical shape, dtype and tiling. md5 the two binaries to confirm they differ only in
   the intended way. Alternate the two arms, five repeats each, discarding the first as warm-up
   per the capture protocol, and record `aic_cube_ratio` and task duration for both.
3. Record the arm that does not bite. If no sparse API is exposed by the installed CANN at all,
   that is the result: the capability bit is set and unreachable from AscendC, which is worth more
   to a consuming agent than a speed-up number.

## 5 · Checker — acceptance declared before the run
Two verdicts, kept separate.
`sparsity_bit`: PASS iff the INI reads 1 for the installed DAV_2201 SoC. Red input: 0.
`sparse_speedup`: the ratio dense_time / sparse_time, with the run-to-run spread of the dense arm
against itself established FIRST from its five repeats and stated as the threshold before the arms
are compared. The capability half is upheld iff the sparse arm builds, is numerically acceptable
against its declared tolerance, and beats dense by more than that spread.
A speed-up of 1.0 does not overturn the entry — the claim is that the hardware supports 4:2, not
that it is faster in this shape — but it must be recorded, including the case where it is recorded
as "retained because it did not bite". Conflating "no speed-up here" with "capability absent" is
the error this split prevents. Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; per-arch, so no individual board. This entry does not
establish which dtypes support 4:2 on DAV_2201, what the sparsity layout is, which API reaches it,
or what speed-up it yields — upstream states none of these, and §3 says so rather than filling the
gap. It does not establish that `sparsity = 1` in an INI corresponds to working silicon; 0012 is
exactly the reason that inference is refused. It says nothing about DAV_3510, whose removal is
quoted here only as the contrast that makes the 910-side claim consequential.
