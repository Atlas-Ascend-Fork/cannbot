```
ID:        0243-a-simt-thread-reads-gm-directly-where-a-simd-vf-must-stage-through-ub
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — three upstream files state it, all `upstream/skills-dev-main`, therefore ONE
           origin (RULES.md Art. 3). The DCache that upstream says makes it work is itself marked by
           upstream as a public-or-experience value with no ini field (0206 row 2). Nothing was run.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:297-301 — "| GM 离散访问 | **支持直接访问**
           （核内 DCache） | 不支持，需先搬入 UB |"; :308 "**SIMT 适用场景**：Gather/Scatter、Hash 插入、
           随机数、排序（含原子操作）。"
SOURCE:    ops/npu-arch/references/simt-arch-guide.md:99-112 — "### Global Memory (GM) /
           - 所有核所有线程均可访问 / - SIMT VF 支持直接读写 GM，无需显式 Load/Store /
           - 通过 `__gm__` 指针访问" and the 与 SIMD 的差异 table "| 数据搬运 | 需显式 Load/Store |
           支持直接读写 GM 和 UB |"
SOURCE:    ops/ascendc-simt-tiling-design/SKILL.md:18 — "| 数据搬运 | 需显式 Load/Store | 支持直接读写 GM |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a SIMT VF dereferencing a `__gm__` pointer that fails to compile or produces wrong data
           on a 950 board, or a discrete-gather comparison in which the SIMD staged path beats the
           SIMT direct path at every access pattern — the capability would then exist and buy nothing.
```

# 0243 · A SIMT thread reads GM directly where a SIMD VF must stage through UB

## 1 · Claim
Upstream asserts that a SIMT VF can read and write Global Memory directly through a `__gm__` pointer,
with no explicit Load/Store and no staging through the Unified Buffer, and that the enabling hardware is
the per-core DCache. Upstream asserts the contrast: SIMD does **not** support direct discrete GM access
and must move data into UB first. Upstream names the workloads this exists for — Gather/Scatter, hash
insertion, random number generation, sorting including atomics — and names the ones it does not:
large dense BF16/FP16 matmul and convolution, long sequential vector computation, and any architecture
before DAV_3510, where the SIMT hardware does not exist. Not established here: nothing was compiled and
no access was timed.

## 2 · The wrong branch this removes
This is the reason SIMT exists on this architecture, and without it an agent has no basis for choosing
between the two programming models — so it will choose by familiarity, which means SIMD, which means
writing a gather as a staged copy.

The concrete wrong branch: an operator whose access pattern is data-dependent — a gather over an index
vector, a scatter with duplicate targets, a hash probe — expressed in SIMD requires materialising the
touched region into UB first. When the indices are scattered across a large tensor, "the touched region"
is most of the tensor, so the staged path moves far more bytes than the operator reads. The kernel is
correct, the UB tiling is tidy, and the DMA volume is bounded by the *span* of the indices rather than
by their count. Nothing in a profile says "this should have been SIMT"; it shows an MTE2-bound kernel,
and MTE2-bound kernels have a dozen ordinary remedies, all of which are the wrong remedy here.

The inverse branch is the one upstream spends more words on and is just as costly. An agent that learns
"SIMT can touch GM directly" and applies it to a dense sequential kernel loses the vectorised
instruction throughput SIMD gives and gains nothing, because a sequential stream never needed the
indirection. Upstream's 不适用场景 list exists precisely to close that, and it is the half a reader
skims.

There is a third branch that neither list closes and that this entry has to leave open: direct access is
*enabled* by a cache, and a cache has a hit rate. The capability is unconditional; the benefit is not.
An access pattern with no locality at 128-byte granularity will fault through DCache on every thread,
and whether that beats a staged copy is a measurement upstream never supplies. So "SIMT supports direct
GM access" is a statement about what compiles, and the choice between models is a statement about what
is fast — §4 keeps them apart.

## 3 · Ground / Source
`npu-arch-guide.md:295-315`, the SIMT-vs-SIMD section, quoted around the capability row because the
surrounding rows are what make it a model choice rather than a feature:

> ## SIMT vs SIMD 硬件能力差异
>
> | 维度 | SIMT | SIMD |
> |-----|------|------|
> | 编程范式 | 标量编程（线程视角） | 矢量编程（VF 内连续计算） |
> | 控制逻辑 | Warp Scheduler 硬件分支调度 | 软件展开循环 |
> | **GM 离散访问** | **支持直接访问**（核内 DCache） | 不支持，需先搬入 UB |
> | 寄存器类型 | 标量寄存器（per-Thread） | 矢量寄存器（per-VF） |
> | 寄存器组织 | 128 KB 寄存器堆，按线程并发数切分 [¹](#unverified) | 多条 VL=256 B 矢量寄存器 |
>
> **SIMT 独有硬件**（DAV_3510 新增）：Warp Scheduler（每 AIV 4 个）[¹] / SIMT Register File /
> SIMT DCache（最大 128KB，复用 UB 作 Cacheline，128B 粒度）[¹]
> **SIMD/SIMT 共享**：ALU / ICache / Unified Buffer
>
> **SIMT 适用场景**：Gather/Scatter、Hash 插入、随机数、排序（含原子操作）。
>
> **SIMT 不适用场景**：
> - 大块 dense BF16/FP16 矩阵乘 / 卷积 — SIMD + Cube 流水更高效
> - 长向量顺序计算 — SIMD 矢量化指令吞吐更高
> - DAV_3510 之前架构 — SIMT 硬件不存在，无法使用

Note the `[¹]` markers: the DCache line — the mechanism this entry's claim rests on — carries upstream's
own unverified footnote (0206 row 2), while the capability row does not. So upstream is more confident
that direct access works than that it knows the cache's size, which is a coherent position and worth
preserving rather than flattening.

The 128 B granularity in that same line is load-bearing for §2's third branch: DCache "复用 UB 作
Cacheline，128B 粒度" means a thread touching 4 bytes pulls a 128-byte line. Sixteen fp32 elements per
line, so an index stride above 32 elements defeats the cache entirely — an arithmetic consequence of
upstream's own figure, stated here as arithmetic and not as a measurement.

`simt-arch-guide.md:99-112`, the memory-space section, which gives the programming form:

> ### Global Memory (GM)
> - 所有核所有线程均可访问
> - SIMT VF 支持直接读写 GM，无需显式 Load/Store
> - 通过 `__gm__` 指针访问
> - 在 kernel 入口通过 `GM_ADDR` 参数传入
>
> ### 与 SIMD 的差异
> | 维度 | SIMD | SIMT |
> | 数据搬运 | 需显式 Load/Store | 支持直接读写 GM 和 UB |
> | GM 访问 | 不支持直接到寄存器 | 支持直接访问 |

and the worked kernel at `ascendc-simt-api-reference/references/overview.md:69-85`, which is the artefact
that transmits — the whole body is a `__gm__` dereference with no copy anywhere:

```cpp
__simt_vf__ __launch_bounds__(2048) inline void SimtCompute(
    __gm__ float* dst, __gm__ float* src0, __gm__ float* src1, int count) const
{
    for(int idx = threadIdx.x + blockIdx.x * blockDim.x; idx < count; idx += gridDim.x * blockDim.x)
    {
        dst[idx] = src0[idx] + src1[idx];
    }
}
```

`ascendc-simt-tiling-design/SKILL.md:14-20` draws the tiling consequence, which is the part a tiling
routine needs: SIMT splits by element count rather than by UB capacity, and "UB 使用 | 全量使用 |
仅核内共享场景使用，DCache >= 32KB" — UB is used *only* for intra-core sharing, not as the data path
(0237, 0240).

All four files are `upstream/skills-dev-main` — **one origin** (RULES.md Art. 3). The repetition across three
skills means a reader in any of them meets the claim; it does not make it corroborated.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion. The capability
and the benefit are separate claims and need separate arms — this is exactly the place where one
sentence would fuse a compile result with a timing result.

Arm A — the capability, compile and run, no benefit claimed. Build the `overview.md:69-85` kernel
verbatim, dereferencing `__gm__` pointers inside a `__simt_vf__` with no UB staging anywhere, and check
output against a host reference. This establishes that direct access compiles and is correct. It
establishes nothing about speed.

Arm B — the SIMD counterpart, refused. Attempt the same discrete gather inside a `__simd_vf__` by
dereferencing a `__gm__` pointer directly, and record the diagnostic. Upstream says SIMD does not
support it; a clean compile here would mean the *contrast* is wrong even if Arm A passed, and the model
choice loses its basis. This arm is the one that tests upstream's actual distinction rather than SIMT's
capability alone.

Arm C — the benefit, paired. Implement one gather over a shuffled index vector two ways — SIMT direct,
and SIMD staged through UB — at identical logical shape, on the same die in the same session. Sweep the
index locality: contiguous, stride 4, stride 32, stride 256, and fully shuffled over a working set well
above L2 (0270). Report `aiv_time` for both at each pattern. The crossover point is the readout, and it
is the number a model-selection rule would actually need; upstream supplies a qualitative list and no
crossover.

Arm D — the DCache granularity, which explains Arm C rather than merely measuring it. Repeat the SIMT
arm with index stride swept across 16, 32, 64, 128 and 256 *bytes*. Upstream's 128 B line size predicts
a knee at 128 B; its absence would mean Arm C's curve comes from something other than line granularity,
and the explanation offered in §2 would be wrong even if the curve is right.

Arm E — the DCache reservation interaction. Rerun Arm C's shuffled point at DCache residuals of 32, 64
and 128 KB (0237, 0239). If direct access is DCache-mediated, the shuffled case should be sensitive to
the residual and the contiguous case should not. That contrast is what ties this entry to the
reservation rule, and it is the only arm that would tell a tiling routine what to reserve for a
gather-shaped operator.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and no die is substituted for another. Every paired comparison runs on one named die in one
session — a SIMT-versus-SIMD timing assembled across dies attributes nothing.

## 5 · Checker — acceptance declared before the run
Three verdict variables, never aggregated, because they are three different claims and the entry's
honesty depends on not letting one carry another.

`direct_access_works` (Arm A) — pass iff the kernel compiles and output matches the host reference
bit-for-bit. This is the capability claim and the only one this entry states as fact-shaped.

`simd_refuses` (Arm B) — pass iff the SIMD attempt fails, **and** its diagnostic names the address space
or the unsupported access. The checker matches diagnostic text, not exit status: "it did not compile" and
"it did not compile for the stated reason" are different results, and only the second establishes the
contrast. A clean compile is recorded as `contrast not established` and is a finding against upstream's
table, not against Arm A.

`crossover_pattern` (Arm C) — the index-locality point at which SIMT direct overtakes SIMD staged, per
working-set size. **No pass threshold is declared**, deliberately: upstream makes a qualitative claim and
inventing a threshold here would let a convenient result read as confirmation. What is declared is the
shape the result must have to support upstream's advice — SIMT must win at the fully-shuffled end and
must lose at the contiguous end. A curve where SIMT wins everywhere, or loses everywhere, contradicts
one of upstream's two lists and is reported as such.

`granularity_knee` (Arm D) — pass iff a knee appears at 128 B stride. Its absence does not fail the
entry; it removes the explanation and is logged.

The positive fixture, declared before the run: Arm C must include a contiguous-index point, where the
staged SIMD path is expected to **win**. If SIMT wins even there, the two implementations are not
comparable — most likely the SIMD arm is staging more than it needs, which is §2's own failure mode
reproduced inside the harness — and every crossover figure is void. A second fixture for Arm A: poison
the destination beyond the intended extent and require zero changed words, so a "correct" result cannot
come from a kernel that also wrote elsewhere. Without both, the checker reads only "SIMT was faster",
which is the known blind species.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no GM
pointer was dereferenced, and nothing was timed. The 128 B / 16-fp32-elements-per-line arithmetic in §2
is arithmetic over upstream's own figure, performed here, and upstream marks that figure as a
public-or-experience value with no ini field behind it (0206).

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that direct GM access works, that SIMD
refuses it, or that either is faster than the other anywhere — Arms A, B and C are all open and are
deliberately separate, because a compile result and a timing result are different claims. It does not
establish the DCache's existence, size, or line granularity: all three are upstream assertions carrying
upstream's own unverified marker, and there is **no second origin** — the installed toolkit's ini
carries no DCache field (0237 §3), and all four quoted files are one repo. It supplies **no crossover
point** between the two models: upstream gives two qualitative lists and no threshold, so an agent
choosing between SIMT and SIMD from this entry alone is choosing on upstream's judgement, not on a
number. It says nothing about atomics, which upstream lists among SIMT's applicable workloads and which
have their own correctness semantics entirely. It says nothing about write behaviour — whether direct
GM *writes* are cached, write-through, or coherent across cores — which upstream's tables mention only as
"读写" and which matters more than reads for scatter. It says nothing about the mixed SIMD/SIMT case,
where UB is shared and the budget differs (0238). BOARD is 950PR and 950DT because upstream names both
for the SIMT hardware; a run on one establishes only that one. Nothing transfers to the other book (RULES.md
Art. 1) — upstream states the SIMT hardware does not exist before DAV_3510, so there is no corresponding
claim to make there.
