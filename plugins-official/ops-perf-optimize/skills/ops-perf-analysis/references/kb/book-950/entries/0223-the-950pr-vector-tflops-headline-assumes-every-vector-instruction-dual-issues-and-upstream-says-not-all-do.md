```
ID:        0223-the-950pr-vector-tflops-headline-assumes-every-vector-instruction-dual-issues-and-upstream-says-not-all-do
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin, which marks the figure itself as a public-or-experience
           value with no ini field behind the ×2 (0206 row 12). The ini supplies the pre-doubling
           inputs only. Nothing was timed.
BOARD:     950PR
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:177 — "| 12 | Vector 算力 950PR Server=54T /
           PCIE=47T：基准 27T/23.7T × 双发 2，但并非所有 Vector 指令均支持双发 | Guide §3 算力与系统规格
           → Vector 算力推导 | 公开资料 / 经验值 |"
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:149-163 — "TFLOPS = vec_calc_size ×
           vector_core_cnt × vec_freq(MHz) × 2(FMA) ÷ 10⁶" with the parameter table and
           "**950PR Server**：128 × 64 × 1650 × 2 ÷ 10⁶ = 27T，含 Regbase OOO 双发（见 SIMD-Regbase 节）
           再 ×2 = **54 TFLOPS**[¹](#unverified)"   # same skill — ONE origin (RULES.md Art. 3).
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured fp16 Vector FMA throughput on 950PR Server exceeding 27 TFLOPS — the dual
           issue would then be real for that instruction mix; or an instruction mix upstream's model
           says dual-issues measuring at the single-issue rate, which breaks the ×2 as a blanket term.
```

# 0223 · The 950PR Vector TFLOPS headline assumes every Vector instruction dual-issues, and upstream says not all do

## 1 · Claim
Upstream asserts a Vector throughput derivation —
`TFLOPS = vec_calc_size × vector_core_cnt × vec_freq(MHz) × 2(FMA) ÷ 10⁶` — which yields 27 TFLOPS for
950PR Server (128 × 64 × 1650) and 23.7 for 950PR PCIE (128 × 56 × 1650). Upstream then asserts a second
factor of 2 for Regbase out-of-order dual issue, producing the published headline figures of 54 T and
47 T. Upstream marks both headline figures with its own unverified footnote, and states the caveat in
the same table cell that carries the number: **并非所有 Vector 指令均支持双发** — not all Vector
instructions support dual issue. Not established here: nothing was timed.

So the published figure is a ceiling for an unenumerated subset of the instruction set, and the
derivation and its own disclaimer live in one cell.

## 2 · The wrong branch this removes
This is the measurement-and-inference-in-one-sentence species in its purest form, written by upstream and
disclosed by upstream. The cell says: here is a number, here is how it was derived, and here is the
reason the derivation does not hold generally. All three are true. A reader takes the number.

The pre-doubling figure — 27 T Server, 23.7 T PCIE — is arithmetic over three ini fields, exactly like
the Cube derivation (0222) and with the same status. The ×2 is different in kind: it has no ini field, it
is upstream's row 12 of the 公开资料/经验值 table (0206), and it is qualified by the caveat. Fusing them
into one headline gives a figure whose two halves have different pedigrees, and nothing downstream
carries the distinction.

The operational damage is asymmetric and points one way. A Vector roofline built on 54 T is up to 2×
too high for any kernel whose instruction mix does not dual-issue — so a well-written kernel reports
50 % of peak, and the team optimises against a ceiling that does not exist for its code. There is no
signal: "we are at half of peak" is exactly what an unoptimised kernel also looks like.

The subset is the missing piece and upstream does not supply it. What *is* available, in a different
skill, is a per-instruction model that encodes the same distinction structurally:
`ascendc-performance-evaluation`'s cost table (0266) gives every instruction an `issue_slots` of 2 or 1,
with the units block stating "2 for VALU-only (dual-issue) instructions, 1 for instructions needing the
single non-replicated VECTOR engine". So the instructions that do **not** dual-issue are enumerable —
reductions, data-reorder, `Pack`/`UnPack` sit on `reduce_1slot_t1` / `vector_1slot_t1` /
`pack_unpack_1slot_t1` — and a kernel dominated by them is bounded by 27 T, not 54 T. That mapping is
this entry's most useful content and it required reading two skills that do not reference each other.

A third branch: `vec_calc_size = 128` is the per-cycle element count and `vector_core_cnt` is the core
count, so the base figure already assumes every Vector core is fed every cycle. The ×2 is layered on top
of an assumption that is itself a ceiling.

## 3 · Ground / Source
`npu-arch-guide.md:147-163`, the derivation with both steps visible:

> #### Vector 算力推导
>
> Vector 算力公式（FP16）：
>
> ```
> TFLOPS = vec_calc_size × vector_core_cnt × vec_freq(MHz) × 2(FMA) ÷ 10⁶
> ```
>
> | 参数 | 910B2 | 950PR PCIE | 950PR Server | 来源 |
> |------|:---:|:---:|:---:|------|
> | vec_calc_size | 128 | 128 | 128 | INI `[AICoreSpec] vec_calc_size` |
> | vector_core_cnt | 48 | 56 | 64 | INI `[SoCInfo] vector_core_cnt` |
> | 频率 (MHz) | 1800 | 1650 | 1650 | 910B2: `cube_freq`（INI 无独立 `vec_freq`）；950PR: `[VectorCoreSpec] vec_freq` |
>
> **950PR PCIE**：128 × 56 × 1650 × 2 ÷ 10⁶ = 23.7T，含 Regbase OOO 双发（见 SIMD-Regbase 节）再 ×2 = **47 TFLOPS**[¹](#unverified)
> **950PR Server**：128 × 64 × 1650 × 2 ÷ 10⁶ = 27T，含 Regbase OOO 双发（见 SIMD-Regbase 节）再 ×2 = **54 TFLOPS**[¹](#unverified)

Verified as arithmetic here: 128 × 64 × 1650 × 2 = 27,033,600 → 27.03 T, ×2 = 54.07. And
128 × 56 × 1650 × 2 = 23,654,400 → 23.65 T, ×2 = 47.31. Both reproduce. That checks upstream's
arithmetic, not the hardware.

The disclosure, `npu-hardware-params.md:164-177`, row 12 of the 公开资料/经验值 table:

> | # | 内容 | 文档位置 | 信息来源 |
> | 8 | SIMD-Regbase：OOO 指令双发 | Guide §6 SIMD-Regbase | 同上 |
> | 12 | Vector 算力 950PR Server=54T / PCIE=47T：基准 27T/23.7T × 双发 2，但并非所有 Vector 指令均支持双发 | Guide §3 算力与系统规格 → Vector 算力推导 | 公开资料 / 经验值 |

Rows 8 and 12 are the mechanism and the number, both unverified. The caveat sits inside row 12's content
cell rather than in a separate column — so a tool extracting the table's numbers, or a reader scanning
for figures, drops it.

The mechanism, `npu-arch-guide.md:319-330`:

> ## SIMD-Regbase 架构
> DAV_3510 在 Vector 单元上引入 Regbase 架构，与传统 Membase 并存。
> **新增寄存器组**：VFScalar / 地址寄存器 / 对齐寄存器 / 掩码寄存器 / 向量寄存器
> **核心优势**：
> - **寄存器内计算** — 减少 UB 访问带宽
> - **OOO 指令双发** — Vector 性能提升
> - 支持 LB **非 32B 对齐**数据处理

"Vector 性能提升" — a performance improvement, unquantified. The ×2 in the derivation is a quantification
that this section does not supply.

Corroborating the base inputs, the installed toolkit (read under the phase-1 read-only exception):
`Ascend950PR_9589.ini` carries `vec_calc_size=128`, `vector_core_cnt=64`, `[VectorCoreSpec] vec_freq=1650`;
`Ascend950PR_957b.ini` carries `vector_core_cnt=56`, `vec_freq=1650`. So the pre-doubling figure is
reproducible from this machine's files. **The ×2 has no ini field** — a search of the 950 ini set for a
dual-issue field returned nothing, consistent with upstream's own marking and establishing nothing.

The one place the ×2 appears as a named constant is
`ascendc-performance-evaluation/references/hardware/ascend950pr.json`,
`common.vector_core_spec.regbase_ooo_dual_issue_factor: 2`, with the variant peaks carrying
`"vector_fp16_ops_source": "npu-arch public/experience value with regbase dual issue"` and — usefully —
a companion field `vector_fp16_ops_per_s_without_dual_issue` (2.70336e13 for 9589, 2.36544e13 for 957b).
So that skill keeps both figures, cites npu-arch as its source, and its usage note says the evaluator
"should apply an instruction-specific efficiency factor" for instructions that cannot dual-issue. Same
repo as npu-arch, so one origin — but it is the only place the two-tier structure is represented rather
than collapsed.

## 4 · Procedure
Runnable later on `950PR`; **no 950DT figure is published**, so this entry's BOARD stays 950PR either way.

Arm A — the base rate, single-issue-friendly mix. Build a long chain of *independent* fp16 FMA-shaped
Regbase operations (`Reg::MulAddDst`, which is `alu_2slot_t2` in the cost table) with enough
instruction-level parallelism that dual issue can engage, UB-resident so MTE is not the limiter, minimum
`aiv_time` over 50 repetitions. Compute achieved TFLOPS = 2 × elements × iterations / time, and compare
against both 27 T and 54 T.

Arm B — the discriminating pair, which is the arm that tests the ×2 rather than measuring a number. Two
kernels at identical element count on the same die in the same session: one built from instructions the
cost table marks `issue_slots: 2` (`Add`, `Mul`, `MulAddDst`), one from instructions it marks
`issue_slots: 1` (`ReduceSum`, `Pack`, `Interleave`). Report the ratio. Upstream's model predicts ~2.0.
A single-arm throughput number cannot attribute anything to dual issue — this is the paired form 0206 §4
Kind C insists on, and it is the only design here that produces attribution.

Arm C — the ILP dependence, which distinguishes "dual issue exists" from "dual issue is reachable".
Repeat Arm A with the chain made fully dependent (each operation consuming the previous result) and
again fully independent. Dual issue requires independent work to issue; a dependent chain should collapse
toward the single-issue rate even for `2slot` instructions. If it does not, the ×2 is not an ILP-gated
effect and upstream's mechanism description is wrong.

Arm D — the subset, enumerated. For each of the ten execution models in the cost table (0266), time a
representative instruction and classify it as dual-issuing or not by comparing against Arm A's base rate.
The output is the list upstream's caveat implies and never supplies: which instructions the 54 T figure
applies to. This is the deliverable that would make the headline usable.

Device selection is explicit: the operator names the device index and the SKU (the figure differs between
957b and 9589), the harness prints both back with `compiler/version.info` and the resolved SoC string,
occupancy is checked before the run (shared machine, ≤4 dies), and no die is substituted for another. All
arms of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
Verdict variable `dual_issue_ratio`, from Arm B — the ratio of `2slot`-mix throughput to `1slot`-mix
throughput. This is the verdict, not Arm A's absolute figure, because the entry's claim is about a
*factor* and a single absolute number cannot test one.

Pass is declared now as `dual_issue_ratio ∈ [1.8, 2.2]`. Two alternatives are named now so neither can be
reinterpreted afterwards. A ratio near 1.0 means the ×2 does not hold even for the instruction classes
upstream's own cost model says it should, and the 54 T / 47 T headlines are wrong for everything — the
entry is corrected in place and the finding is large. A ratio above 2.2 means the `1slot` arm is limited
by something other than issue width and Arm B is not measuring what it claims.

`achieved_tflops` (Arm A) — reported against both 27 T and 54 T, with run variance. **No pass
threshold**, deliberately: upstream publishes a theoretical ceiling and inventing an acceptance band
around it would let a convenient result read as validation. What is declared is the falsifier — a reading
**above** 27 T for a `2slot` mix supports the ×2; a reading above 54 T overturns the whole derivation.

`ilp_collapse` (Arm C) — the dependent-chain rate divided by the independent-chain rate. Reported; a
value near 1.0 would mean dual issue is not ILP-gated, contradicting upstream's OOO description.

`dual_issue_subset` (Arm D) — the classified list. No pass condition; it is the missing enumeration and
either outcome is informative.

The positive fixture, declared before the run: Arm B must include a third arm using the *same*
instruction on both sides with only the element count differing. Its ratio must be 1.0. If the harness
reports a ratio far from 1.0 there, it is measuring something other than the instruction mix — loop
overhead, or a shape effect — and every `dual_issue_ratio` it produced is void. Without this, the checker
reads only "one kernel was twice another", which is the known blind species: many unrelated causes
produce a factor of two, and this entry is entirely about a factor of two.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built and nothing
was timed. The two multiplications reproduced in §3 are arithmetic over upstream's stated inputs,
performed here to confirm upstream's arithmetic closes. The ini fields are a file read under the
sanctioned phase-1 read-only exception; the search for a dual-issue field found nothing, and a search
that finds nothing establishes nothing.

## 7 · Scope limits — what this entry does NOT establish
Nothing was timed. The entry does not establish the base rate, the ×2, or which instructions dual-issue —
Arms A-D are all open, and Arm D is the enumeration upstream's caveat implies and no source supplies.
There is **no second origin** for the ×2: upstream marks it 公开资料/经验值 with no ini field, the
installed ini set carries no dual-issue field, and the one other place it appears
(`regbase_ooo_dual_issue_factor: 2`) is the same repo citing npu-arch. The base figure's inputs *are*
corroborated by the installed ini, so the two halves of the headline have different evidential status and
this entry's whole point is that they are printed as one number. It does not establish that the base
figure is achievable either: `vec_calc_size × vector_core_cnt` assumes every Vector core is fed every
cycle, which is a ceiling on top of which the ×2 is layered. BOARD is `950PR` and stays there: **no 950DT
Vector figure is published anywhere in this scope**, so there is nothing to carry or to test for it. It
covers FP16 only — upstream's formula is stated for FP16, and `npu-arch-guide.md:121` notes Vector does
not support bfloat16 at all, which is a separate claim not tested here. It says nothing about whether the
cost table's `issue_slots` partition (0266) is correct; §2 uses it to *name* the likely non-dual-issuing
instructions, and that mapping is an inference across two upstream skills that do not reference each
other, not a measurement. Nothing transfers to the other book (RULES.md Art. 1): the 910B2 column and its 22 T
figure are upstream's text, and note that the 910B2 row carries no `[¹]` marker precisely because no
dual-issue factor is applied to it.
