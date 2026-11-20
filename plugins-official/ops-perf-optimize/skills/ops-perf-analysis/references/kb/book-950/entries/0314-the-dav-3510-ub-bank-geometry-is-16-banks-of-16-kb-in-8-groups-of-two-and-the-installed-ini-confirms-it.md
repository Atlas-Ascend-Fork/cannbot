```
ID:        0314-the-dav-3510-ub-bank-geometry-is-16-banks-of-16-kb-in-8-groups-of-two-and-the-installed-ini-confirms-it
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   corroborated — the upstream skills repo states the geometry from "官方示例推导 / 硬件手册",
           and the vendor's installed CANN 9.0.0-beta.2 platform_config set on this machine carries
           it as ini fields (`ubbank_num`, `ubbank_group_num`, `ubbank_size`, `ubsubbank_num`,
           `ubblock_size`). Two origins of authority, one of them not a document. NOTHING WAS
           MEASURED: no bank conflict was observed, no `ResourceConflictRatio.csv` was collected.
BOARD:     950PR, 950DT
SOURCE:    ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md:35-38 —
           "| 芯片 | UB 大小 | Bank 数 | Bank Group 数 | 每组 Bank 数 | 每 Bank 大小 | 每行大小 |" ·
           "| DAV_3510 | 256 KB | 16 | 8 | 2 | 16 KB (512 行) | 32 B |" ; :304 — "Atlas 350：256KB =
           16 bank × 16KB = 8 group × 2 bank，两次读操作同一 group 不同 bank 不冲突。"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2`,
           `aarch64-linux/data/platform_config/Ascend950{PR,DT}_*.ini` — all 32 files with
           `NpuArch=3510` carry, byte-identically: `ubbank_num=16`, `ubbank_group_num=8`,
           `ubbank_size=4096`, `ubsubbank_num=64`, `ubblock_size=32`, `ub_size=253952`.
INDEX:     none — nothing measured; see SOURCE. The ini side is re-derivable by file read:
           for f in $(grep -l 'NpuArch=3510' $ASCEND_HOME_PATH/aarch64-linux/data/platform_config/*.ini); do
             grep -hE '^ub(bank_size|bank_num|subbank_num|bank_group_num|block_size|_size)=' "$f"; done | sort -u
OVERTURN:  a padding sweep on a named 950 board in which the Vector repeat cost changes period at a
           stride other than a multiple of 8 banks — the group count would then not be 8; or a
           `ResourceConflictRatio` reading that goes red for two concurrent reads landing in two
           DIFFERENT banks of one group, which would make DAV_3510's read-read rule the same as
           220x's and delete this entry's reason to exist.
```

# 0314 · The DAV_3510 UB bank geometry is 16 banks of 16 KB in 8 groups of two, and the installed ini confirms it

## 1 · Claim
Upstream asserts that on DAV_3510 the Unified Buffer is organised as 16 banks in 8 bank groups of
two banks each, that each bank is 16 KB holding 512 rows, that a row is 32 B, and that the total so
described is 256 KB. Upstream asserts the group membership rule — banks whose ids agree modulo the
group count share a group — and that address-adjacent 32 B rows map to adjacent banks, cycling
through the bank count. The installed CANN 9.0.0-beta.2 platform-config set on this machine carries
the same counts as ini fields: `ubbank_num=16` and `ubbank_group_num=8` in all 32 files with
`NpuArch=3510`, alongside `ubsubbank_num=64`, `ubbank_size=4096` and `ubblock_size=32`. Not
established here: no bank conflict was observed and no board was contacted; the mapping from an
address to a bank id was not measured, only read.

*[Deleted 2026-08-24 per §4 Arm B's own clause. This paragraph rested the entry on a
physical-vs-available distinction — "the 8 KB gap is real and unavailable" — and the measured
answer is that the gap is a QUERY under-report, not unavailable memory: the single-tensor
InitBuffer boundary on 950PR is 262144 with EVERY byte round-tripping (950:0209 §6, the same
probe §4 Arm B describes; 950:0141 overturned on exactly this). The arithmetic reconciliations
the paragraph quoted (64 × 4096 = 262144; 262144 / 16 / 32 = 512) remain true and remain
recorded in §3 — what died is the "unavailable" reading of the 8 KB.]*

## 2 · The wrong branch this removes
Two, and the second is the expensive one.

The first: an agent that reads only the DAV_2201 row of the same table, or that carries a 220x
padding recipe onto a 950 part, pads by the wrong quantum. 220x has 48 banks of 4 KB in 16 groups
of three; DAV_3510 has 16 banks of 16 KB in 8 groups of two. A stride that aliases on one does not
alias on the other, and a padding constant chosen for one is a pure UB tax on the other. Nothing
crashes and nothing is incorrect — the operator is simply slower, or simply larger, for the life of
the kernel.

The second, and this is the branch this entry exists for: an agent that meets `256 KB` in
`ub_resident_design.md:38` and `248 KB` in `950:0209` concludes one of them is a typo, picks the
one it trusts more, and propagates the choice. Both are right about different quantities. 256 KB is
what the bank array physically holds — `ubsubbank_num × ubbank_size = 64 × 4096 = 262144`. 248 KB
(`ub_size = 253952`) is what the allocator exposes. The gap is `262144 − 253952 = 8192` bytes, and
that 8 KB is not a rounding artefact: it is the same 8 KB that upstream's SIMT budget subtracts
(`950:0238`, `可用 UB = 256KB − 8KB − 32KB = 216 KB`), which is why that formula starts from 256 KB
and still lands on a number consistent with a 248 KB user-visible buffer (`253952 − 32768 = 221184
= 216 KB`, the same answer by the other route). An agent that "corrects" the 256 KB to 248 KB
breaks the bank arithmetic; an agent that "corrects" the 248 KB to 256 KB over-allocates. The
correct move is to keep both and label which is which — which is what this entry does.

## 3 · Ground / Source
The upstream table in full, `common/ub_resident_design.md:33-38`:

```
#### 2.2.2 不同芯片的 UB Bank 结构

| 芯片 | UB 大小 | Bank 数 | Bank Group 数 | 每组 Bank 数 | 每 Bank 大小 | 每行大小 |
|------|---------|---------|---------------|-------------|-------------|---------|
| DAV_2201 | 192 KB | 48 | 16 | 3 | 4 KB (128 行) | 32 B |
| DAV_3510 | 256 KB | 16 | 8 | 2 | 16 KB (512 行) | 32 B |
```

The DAV_2201 row is upstream's text and is quoted only to show what the DAV_3510 row is being
distinguished from; nothing about it is carried into this book (RULES.md Art. 1).

The group-membership rule and the address→bank mapping, `:40` and `:60-62`:

```
**Bank Group 组成方式**：group 内各 bank 的编号满足 `bank_id % num_groups` 相同。
...
**映射的核心规律**（由官方示例推导，具体公式以芯片手册为准）：
- 地址上相邻的 32B 行通常映射到相邻的 bank（按 bank 总数循环）。
- 因此，**DataBlock 之间的地址差（由 `blk_stride` 决定）直接决定了它们是否落入同一 bank group**。
```

Note the provenance upstream gives itself: `由官方示例推导，具体公式以芯片手册为准` — the mapping is
an inference from worked examples, not a quoted specification, and upstream says so. The bank
*counts* are presented as fact; the *mapping law* is presented as a derivation. §4 separates them.

The restatement in the constraints section, `:302-305`:

```
4. **Bank 冲突规避需区分芯片型号**：
   - NPU 220x（A2/A3）：192KB = 48 bank × 4KB = 16 group × 3 bank，读写/写写/读读冲突条件见 2.2.2 节。
   - Atlas 350：256KB = 16 bank × 16KB = 8 group × 2 bank，两次读操作同一 group 不同 bank 不冲突。
   - 具体规格和推荐配置务必查阅对应版本的《Ascend C 算子开发最佳实践》。
```

`Atlas 350` is the name upstream uses here for the DAV_3510 part. It is not a token this book's
`form/CONVENTIONS.md` defines, and it is not in `npu-arch`'s vocabulary map (which gives
ASCEND950 = DAV_3510 = arch35 = Atlas A5 = 950DT / 950PR). It *is* defined elsewhere in the same
upstream repo — `ascendc-regbase-best-practice/.../cast-api.md:5`, "**适用平台**：Atlas 350 加速卡
（arch35 / DAV_3510）" — so it is a product-card name for the arch35 part, not a fourth chip. The
name appears 1042 times repo-wide. It is recorded in `harvest/standing/950-bp.md` as a vocabulary
gap, and this entry uses the `950PR, 950DT` tokens the ini files actually name.

Second origin — the installed toolkit, read under the phase-1 read-only exception. Verbatim from
`Ascend950DT_9575.ini`, `[AICoreSpec]`:

```
ub_size=253952
ubblock_size=32
ubbank_size=4096
ubbank_num=16
ubsubbank_num=64
ubburst_in_one_block=32
ubbank_group_num=8
```

All 32 `NpuArch=3510` files carry this block byte-identically, across every core count and every
L2 size present in the set. The reconciliations:

- `ubbank_num = 16` ↔ upstream's "Bank 数 16" — agree.
- `ubbank_group_num = 8` ↔ upstream's "Bank Group 数 8" — agree; `16 / 8 = 2` banks per group ↔
  upstream's "每组 Bank 数 2" — agree.
- `ubblock_size = 32` ↔ upstream's "每行大小 32 B" — agree.
- `ubbank_size = 4096` does **not** equal upstream's "每 Bank 大小 16 KB". It equals a *sub*-bank:
  `ubsubbank_num = 64`, and `64 / 16 = 4` sub-banks per bank, `4 × 4096 = 16384 = 16 KB` — agree
  once the sub-bank level is read. `16384 / 32 = 512` rows — agree with "(512 行)".
- `64 × 4096 = 262144 = 256 KB` ↔ upstream's "UB 大小 256 KB" — agree, **as physical bank capacity**.
- `ub_size = 253952 = 248 KB` — this is the field `950:0209` carries, and the field `npu-arch`
  identifies with `GetCoreMemSize(CoreMemType::UB, ...)`'s return. `262144 − 253952 = 8192`.

So the 256 KB in this file is not the contradiction the C-003 / C-004 / C-006 family reads it as.
It is a different quantity in the same units. This does not close those rows — `ascendc-code-review`'s
`UB_SIZE(256KB)` is used there as an *allocation* threshold, which is the user-visible quantity and
is still wrong at 256 KB — but it removes this file from the list of documents that disagree, and it
supplies the arithmetic that makes `950:0238`'s "256 KB − 8 KB" derivation legible instead of
arbitrary. Recorded as `C-950bp-001` in `harvest/contradictions-950-bp.md`, disposition "resolved by
distinguishing two quantities, pending the §4 measurement".

## 4 · Procedure
Runnable later on `950PR` and, separately, on `950DT`. Never run in this phase. Two arms, because
the entry makes two different kinds of claim and only one of them a capacity query can touch.

Arm A — the counts, by aliasing period. Build one kernel that issues `Adds(dst, src, scalar, MASK,
repeat, {1, S, 1, S})` over a fixed 8-DataBlock repeat, sweeping the block stride `S` over
`1 … 64`, holding element count, dtype and repeat count constant. Record `aiv_time` and, from
`msprof --aic-metrics=ResourceConflictRatio`, the UB bank-conflict ratio per point. Upstream's
mapping law predicts the conflict ratio is periodic in `S` with period equal to the bank count
(16), and that the *severe* points — all eight DataBlocks in one group — are those where `S` is a
multiple of the group count (8). The measured period **is** the bank count and the measured severe
set **is** the group multiples; that is what makes 16 and 8 measurements rather than ini fields.
The variance floor is established first: one build, 30 in-process runs, 5 fresh-process runs,
interquartile range over median, reported beside every ratio.

Arm B — the two capacities, kept apart. `GetCoreMemSize(CoreMemType::UB, ubSize)` on the host side,
printed alongside the SoC string the runtime resolved (`950:0209` §4 arm A, same probe). Then the
allocation boundary: bisect a single UB tensor upward in `ubblock_size` (32 B) steps until
`InitBuffer` or launch refuses; record the largest success `N_ok` and the smallest failure. This
entry predicts `N_ok ≈ 253952` and **not** 262144 — i.e. that the 8 KB gap is real and unavailable —
and Arm A predicts the aliasing period is nonetheless set by a 262144-byte array. If Arm B returns
262144, the physical/available distinction this entry rests on is wrong and §1's second paragraph is
deleted.

Arm C — the read-read rule, which is the one behaviour that distinguishes this geometry from 220x's
and is carried separately in `0315`. Two concurrent reads placed (i) in the same bank, (ii) in two
different banks of one group, (iii) in two different groups; compare conflict ratio and repeat cost
across the three. Case (ii) is the discriminating one.

**As-run instantiation notes (2026-08-24, recorded before any Arm A verdict was read):**
1. Arm B is ANSWERED by an existing run, not re-run: 950:0209's §4 was precisely this bisect
   (single UB tensor, 32 B steps) and returned 262144 granted / 262176 refused with a full-byte
   round-trip. Per this §5's pre-declared branch, ub_bytes = 262144 → §1's second paragraph is
   deleted (done, tombstone in place). The aliasing-span prediction ("period set by a
   262144-byte array") is what Arm A now tests.
2. Arm A instantiated: single-repeat 8-block `Adds` windows instead of one multi-repeat
   instruction (the ISA's srcRepStride field cannot carry 8·S at S > 31), pos-wrap arithmetic
   keeping every read inside a 245760 B span (span mod 16 banks = 0, so the mapping periodicity
   is unaffected under the interleave hypothesis §1 states); dtype fp16 with exactly-
   representable payload values; correctness = the last window's dst against a host mirror of
   the same arithmetic. Variance floor instantiated as ≥3 profiled repeats per stride point
   (the entry's 30 in-process runs live inside one task as the window loop), floor = spread of
   repeats, declared before the sweep.
3. Conflict readout: msprof `--aic-metrics=ResourceConflictRatio` op-summary columns (this
   pin's msprof offers the group; column names discovered at bring-up and recorded in §6).
4. The §5 second guard (time-based cross-verdict) runs as a separate PipeUtilization-only
   sweep, same binary, same strides.
5. Fleet: one 950 SKU — the 950DT half of BOARD stays unmeasured, as for the other verified
   950 entries.
6. **Arm A outcome with the classic-vector instrument (2026-08-24/25): NO phenomenon.**
   bank_cflt = 0 at every stride (S ∈ 1..64, two instruction forms, correctness green
   throughout), aiv time flat within ≤10 % and non-periodic — consistent with upstream's own
   3510 read-tolerance claim (0315): strided READS inside one vector instruction do not
   conflict on this part. The geometry verdicts therefore need the per-lane concurrent
   instrument (0483's gather). **That instrument is BLOCKED on direct launch**: `__simt_vf__`
   compiles and runs (GM access green) under the bound `-xasc` line, but any UB access from
   inside a VF fails with 507035 under FOUR allocation routes (TPipe pointer, raw base-0,
   the `dynamicStartUB` symbol, `LocalMemAllocator`) — UB-in-VF is coupled to the
   op-framework tiling grant (`SetLocalMemorySize`/`SetDynUBufSize`), which the round-2 survey
   could not express on direct launch. **SUPERSEDED 2026-08-25**: the direct-launch grant EXISTS —
   `aclrtLaunchKernelWithHostArgs` takes an attr list, and
   `ACL_RT_LAUNCH_KERNEL_ATTR_DYN_UBUF_SIZE` (acl_rt.h; `localMemorySize` deprecated toward
   `dynUBufSize`) carries the quota. Measured: no attr → 507035 (round-2 replication); 4096 B →
   507035 (the VALUE is consumed); 65536 B → the TPipe+VF gather runs with all 512 sums exact at
   two geometries. The geometry arms now run on DIRECT LAUNCH — no op-framework vehicle needed.
   Readouts in harvest/RUNS_20260824.md. STRATUM stays corroborated (geometry itself unmeasured).
7. **Arm A′ run with the gather instrument (2026-08-25, device times via msprof, 5 launches per
   point; 950:0489 is the entry whose §5 governs it):** `Reg::DataCopyGather` over 128 half
   lanes, stride 32·k B for k = 1..17, 24, 32. The TIME curve takes exactly three values decided by
   k mod 4 — k odd 636.7–637.0 µs, k ≡ 2 (mod 4) 1272.4–1272.8 µs, k ≡ 0 (mod 4) 2543.6–2544.6 µs —
   unchanged through k = 32; **time period in k = 4, i.e. the alias period is 128 B, and the
   penalty saturates at 128 B**. Under this §3's mapping law (adjacent 32-B rows → adjacent banks
   over 16 banks) the period would be 16 and saturation would arrive at 512 B; it does not. The
   times are linear in the number of lanes sharing one 128-B residue (16 → 319, 32 → 637, 64 →
   1272, 128 → 2544 µs). **The conflict counter `aiv_vec_bank_cflt_ratio` stayed between 0.00034
   and 0.00063 across the whole curve** — flat, no periodicity, no verdict. This §5 defines
   `bank_period`/`group_period` on that counter, so this entry issues no verdict and stays
   corroborated; the time-defined period is REPORTED here, and the §5 second guard's premise
   ("if the ratio-based verdict is green while the time-based one shows no periodicity") arrived
   inverted: the time curve has structure and the ratio has none. What this says about §1: the bank
   COUNTS (16, 8 groups, 32-B rows) are ini facts and untouched; the address→bank mapping law,
   which §3 already marked as upstream's inference, does not describe what a 128-lane vgather
   pays for on this part. Pair readout (0489 Arm 3): lanes offset by 256 B pay the same as lanes
   at the same address; lanes offset by 32 B pay half. Full tables: 0489 §6.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Refuses to assume: that a free die stays free; that a die may be substituted
for another; that the part is un-partitioned (a vNPU slice reports a smaller `ub_size`, `950:0207`,
and would move Arm B's boundary without moving Arm A's period — which is itself a useful cross-check
and is recorded rather than avoided); that `ubbank_size` names a bank rather than a sub-bank, which
is the reading §3 adopts and Arm A is what would confirm it.

## 5 · Checker — acceptance declared before the run
Verdict variables, all declared now.

`bank_period` = the smallest `S > 0` at which Arm A's conflict-ratio curve repeats, and
`group_period` = the smallest `S > 0` at which the curve reaches its maximum. Pass is declared as
`bank_period == 16` **and** `group_period == 8`. Both alternatives are named before the run so
neither can be reinterpreted after: `bank_period == 48` with `group_period == 16` would mean the
part in front of us has the 220x geometry and the whole DAV_3510 row is wrong; any other pair
overturns the row without vindicating anything.

`ub_bytes` = Arm B's largest success. `ub_bytes == 253952` supports §1's split; `ub_bytes == 262144`
overturns it.

`readread_group` = true iff Arm C case (ii) shows a conflict ratio within the variance floor of case
(iii). That is upstream's DAV_3510-specific claim, carried in `0315`; it is measured here because
the same build measures it for free.

The exit code is not the verdict for any arm. Three guards, and the second is the one that matters.

First: every timed build's output is compared elementwise against a CPU reference. A stride sweep
that silently reads out of the tensor would produce a beautiful periodic curve made of garbage.

Second — the checker must be able to go red, and here is the input that does it. Arm A is run a
second time with the conflict-ratio counter *disabled* (`--aic-metrics=PipeUtilization` only) and
the verdict recomputed from `aiv_time` alone. If the two runs give the same `bank_period`, good. If
the ratio-based verdict is green while the time-based one shows no periodicity at all, then the
conflict counter is reporting something the wall clock cannot see, and every green from Arm A is
void. This is the guard against the known failure species — a checker that reads only the lines it
expects — because the conflict ratio is exactly the line this checker most wants to be true.

Third: the variance floor exists before any ratio is reported. A conflict-ratio difference smaller
than the floor is reported as `indistinguishable`, never as absence.

`ubbank_size`'s interpretation has no separate pass condition; it is settled by whether Arm A's
severe points fall at multiples of 8 over a 262144-byte span, and that is `bank_period` /
`group_period` again.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The ini values in §3 come
from reading files in the installed toolkit under the sanctioned phase-1 read-only exception; a file
read cannot observe a bank conflict, cannot call `GetCoreMemSize`, and cannot distinguish a bank
from a sub-bank — which is the one interpretive step §3 takes and §4 Arm A is written to check.

## 7 · Scope limits — what this entry does NOT establish
No device was contacted. The entry does not establish that any of these counts is observable: it
establishes that a document and an ini file agree about them. The address→bank mapping is upstream's
own inference from worked examples (`由官方示例推导`), not a specification, and this entry does not
raise it above that; §4 Arm A is the only thing here that would. The reading of `ubbank_size=4096`
as a *sub*-bank rather than a bank is this book's reconciliation, not upstream's statement and not
the ini's — the ini does not say what its own fields mean, and the reconciliation is admitted here
as an inference, load-bearing for §2's second paragraph and untested. The two origins are not fully
independent in the way the stratum word suggests: upstream cites a hardware manual it does not
reproduce, the ini is vendor data, and `950:0204` records upstream's own convention that an ini is
necessary-but-not-sufficient — so `corroborated` raises the priority of running §4 and raises
nothing else. The reading is pinned to one toolkit (`9.0.0-beta.2`), one host-architecture directory
(`aarch64-linux`) and one machine; no other toolkit was enumerated. Nothing here establishes the
*cost* of a conflict on DAV_3510 — upstream's own figure is "1-2 拍" clean against "多拍（具体拍数因
芯片和冲突 DataBlock 数量而异）", which is not a number. Nothing is established for any 910-family
board; the DAV_2201 row quoted in §3 is upstream's text, not a fact carried across (RULES.md Art. 1). The
`Atlas 350` name is not resolved to a board token by any upstream mapping table, and this entry's
BOARD line comes from the ini filenames, not from that name.
