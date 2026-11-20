```
ID:        0206-thirteen-of-the-truth-sources-own-specs-carry-no-ini-field-and-are-labelled-public-or-experience-values
LABEL:     boundary
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin declares the list; the installed ini directory was
           searched for the two most load-bearing of the thirteen and neither field was found,
           which is consistent with upstream but is an absence, and an absence is weak evidence.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:158-179 — "## 4. 基于公开资料与经验值的规格
           … 以下信息无法从当前安装的 INI 直接推导，数据来源于公开资料或工程经验积累" followed by a
           13-row table whose 信息来源 column reads 公开资料 / 经验值 for every row.
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:431 — "<a id=\"unverified\">¹</a> 基于公开资料
           与经验值，暂未在当前安装的 INI 中找到直接对应的可核验字段。"
           # same skill as the row above — ONE origin (RULES.md Art. 3).
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an ini field, in any shipped `platform_config/*.ini`, that directly supplies any of the
           thirteen — SSBuffer capacity, SIMT register-file size, DCache maximum, warp-scheduler
           count, or the dual-issue factor would each on its own move that row off this list.
```

# 0206 · Thirteen of the truth source's own specs carry no ini field and are labelled public-or-experience values

## 1 · Claim
Upstream asserts that thirteen named specifications in its own architecture documentation cannot be
derived from the installed INI set, and marks each with the source label 公开资料 / 经验值 (public
material / engineering experience). The list includes SIMT Register File 128 KB, SIMT DCache max
128 KB, SSBuffer 256 KB, the CV direct paths, the deletion of L1→GM and GM→L0A/L0B, BufferID
replacing set/wait, the same-address multi-core GM optimisation, SIMD-Regbase OOO dual issue,
4 Warp Schedulers per AIV, the NDDMA/ND-DMA Cache spec, the CCU paradigms and KFC change, the
950PR Vector TFLOPS figures, and the memory-bandwidth figures. Upstream marks the same items inline
with a `[¹]` footnote wherever they appear. Not established here.

## 2 · The wrong branch this removes
Without this entry the thirteen are indistinguishable from the ini-backed constants sitting in the
same tables, in the same bold, in the same document. An agent building a roofline or a buffer budget
pulls "SSBuffer 256 KB" and "1.6 TB/s" with the same confidence as "UB 248 KB" and prices a design
on them. The three have different pedigrees and only one is checkable from a file.

The sharper failure is directional. An unverifiable capacity that is too *large* produces a design
that does not fit; that fails loudly. An unverifiable *rate* that is too large produces a roofline
whose bound is unreachable, so every implementation looks 40 % off target and the team optimises
against a ceiling that does not exist. Nothing in the pipeline distinguishes "the kernel is slow"
from "the denominator was a public figure". This entry is what makes the second hypothesis
available.

## 3 · Ground / Source
`npu-hardware-params.md:158-179`, quoted with its own preamble:

> ## 4. 基于公开资料与经验值的规格
> 以下信息无法从当前安装的 INI 直接推导，数据来源于公开资料或工程经验积累：
> > **位置标注约定**：本表"文档位置"列使用章节锚点（如 `Guide §5`），不使用行号，以避免文档行号
> > 漂移导致引用失效。

Rows 1-13, abbreviated to content and keeping upstream's numbering: 1 SIMT Register File 128 KB ·
2 SIMT DCache 最大 128 KB · 3 SSBuffer 256 KB · 4 CV 直通通路 L0C→UB、UB→L1、SSBuffer 消息 ·
5 L1→GM 和 GM→L0A/L0B 通路已删除 · 6 BufferID 取代 set/wait 同步 · 7 多核同时访问 GM 同地址性能优化 ·
8 SIMD-Regbase OOO 指令双发 · 9 Warp Scheduler 每 AIV 4 个 · 10 NDDMA + ND-DMA Cache 规格 ·
11 CCU 三种通信范式及 KFC 调度变化 · 12 "Vector 算力 950PR Server=54T / PCIE=47T：基准 27T/23.7T ×
双发 2，但并非所有 Vector 指令均支持双发" · 13 Memory 带宽 Server 1.6 TB/s / PCIE 1.4 TB/s.

Row 12 is the one to read twice. It states the derivation *and* the caveat that undermines it in a
single cell: the ×2 applies to instructions that dual-issue, and not all Vector instructions do. So
the headline 54 T is a ceiling for a subset upstream does not enumerate. That is honest and it is
also unusable as a roofline denominator without the subset. Carried separately as 0223.

Two things are worth noting about the mechanism, not just the list. First, upstream chose section
anchors over line numbers in this table specifically so the references survive edits — a small
piece of provenance engineering that most of the repo does not do. Second, the `[¹]` footnote is
attached at each *use site* in `npu-arch-guide.md`, not only at the definition; that is the
placement that actually transmits, because a reader who meets the number in the Buffer table meets
the caveat in the same row.

Independent search, this machine's installed toolkit (`cann-9.0.0-beta.2`): across the shipped
`platform_config/*.ini`, a case-insensitive search for `ssbuf`, `dcache`, `cache_line`, `cacheline`
returned nothing in `Ascend950PR_9589.ini`. That is consistent with rows 2 and 3, but it is an
absence of evidence: the field could exist under a name not searched, or in a file not read. It is
recorded because a negative that agrees with a documented negative is worth having, and it is not
promoted to a second origin because it cannot be.

## 4 · Procedure
Runnable later on `950PR` and `950DT`. The list is heterogeneous, so the procedure is per-row and
splits into three kinds, and the split is the useful part.

Kind A — capacities (rows 1, 2, 3, 10). Establish by consumption, not by query: allocate against the
resource until the build or the runtime refuses, and record the last size that succeeded. For
DCache, this is the `SetLocalMemorySize` boundary — bisect the reserved size downward until the
documented compile-time check fires (see 0237), which locates the *minimum reservation*, and upward
until allocation fails, which locates the maximum. For SSBuffer, allocate CV message slots until
failure. Neither number is readable; both are findable.

Kind B — topology and mechanism (rows 4, 5, 6, 7, 9, 11). Establish by attempting the operation and
observing refusal. Row 5 is the cleanest: write a kernel performing an L1→GM copy and record
whether it compiles for a 3510 target. A build failure with a diagnostic naming the path is the
positive result; a silent success means the path exists and row 5 is overturned.

Kind C — rates (rows 8, 12, 13). Establish by microbenchmark with a declared roof: stream a working
set far larger than L2 and compute achieved bytes/second, then compare against the published figure.
Row 8's dual-issue factor is *not* obtainable this way from an aggregate number — it needs a paired
kernel, one instruction mix that upstream's model says dual-issues and one it says does not, run at
identical shape, with the ratio as the readout. A single-arm throughput number cannot attribute
anything to dual issue.

Device selection is explicit in all three kinds: the operator names the die, the probe prints it
back, occupancy is checked before the run, and nothing is inferred from environment defaults.

## 5 · Checker — acceptance declared before the run
One verdict per row, never an aggregate — a 13-row list with one summary boolean would let twelve
passes hide one failure, and the failures are the point.

For Kind A, verdict `capacity_bracket` is a pair (largest success, smallest failure); pass requires
the pair to bracket the published figure and to be adjacent at the probe's granularity. A run that
produces only successes is RED, not green: it means the ceiling was never reached and the bracket is
open on one side.

For Kind B, verdict `path_refused` is the presence of a build or runtime diagnostic naming the
attempted path. Absence of a diagnostic is not a pass; the checker must distinguish "refused" from
"the test never ran", so each Kind-B probe ships a paired arm using a path upstream says *does*
exist, which must succeed in the same session. That paired arm is the positive fixture: if the
supposedly-valid path also fails, the harness is broken and every refusal it reported is void.

For Kind C, verdict `rate_ratio` = achieved / published, with the acceptance band declared now at
±10 % and the arm that did not bite retained and reported. Exit codes are not verdicts anywhere in
this checker.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The ini search reported in
§3 is a read of installed files under the phase-1 exception; it found nothing, and a search that
finds nothing establishes nothing about the hardware.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. This entry does not establish that any of the thirteen figures is wrong, or
right — it establishes that upstream declares them unverifiable from the installed configuration
and labels them accordingly. It does not establish that the list is complete: an unmarked figure
elsewhere in npu-arch could have the same pedigree and simply not be listed, and no audit for that
was performed. The ini absence recorded in §3 covers four search terms in one file of one toolkit on
one host architecture, and is not a survey. Nothing here transfers to the other book (RULES.md Art. 1),
even though several rows describe DAV_3510 as a delta from an earlier architecture; those deltas are
quoted as upstream's framing only. Finally, the entry does not rank the thirteen by risk — §2 argues
that rate rows are more dangerous than capacity rows, which is reasoning, not evidence, and the
procedure in §4 treats all thirteen as open.
