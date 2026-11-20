```
ID:        0014-external-rvec-unit-names-translate-onto-five-msprof-lanes
LABEL:     knowledge
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/metrics.md:92-99 — "| RVECEX（RVEC 执行单元）泳道 | VECTOR 泳道 / `aiv_vec_ratio` | … | RVECSU（RVEC setup 单元）忙 | SCALAR/SCALARLDST 泳道忙 + V_S/S_V 同步 | … | RVECLD / RVECST（RVEC 载入/存储） | MTE2（载入）/ MTE3（写回）泳道 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a simultaneous capture on a named 950 board of the same kernel under both vocabularies
           in which an RVEC unit's busy time does not track the msprof lane it is mapped onto —
           for instance RVECSU busy while SCALAR is idle — which would make the translation table
           a naming convention rather than a correspondence.
```

# 0014 · External RVEC unit names translate onto five msprof lanes

## 1 · Claim
Upstream asserts a translation table for importing external RegBase VF material: RVECEX (execute)
corresponds to the VECTOR lane and `aiv_vec_ratio`; RVECSU (setup) busy corresponds to
SCALAR/SCALARLDST busy plus V_S/S_V synchronisation; RVECLD/RVECST correspond to the MTE2 and
MTE3 lanes; paired preg spill/reload appears as spill/reload in the trace; simulated
`total_cycle`/IPC corresponds to msprof `aiv_time` and aicore cycles; and an external golden
correctness check corresponds to this workflow's `func_cases` precision regression. Upstream
asserts that card text must use only the right-hand column. Not established here.

## 2 · The wrong branch this removes
Half of this skill's technique cards are ported from an external VF corpus (their 关联 sections
say 外部 VF 策略 N). An agent that ports the next one keeps the source's vocabulary, and the
card then names units that appear in no msprof CSV. Two costs. The reader cannot act: there is
no column called RVECSU, so the diagnostic condition is unexecutable. And the provenance is
laundered: a number measured with an external tool, reported in that tool's units, reads as a
measurement of this library's metric. The right-hand column is not just a style rule — it is
the boundary between "measured here, in the instrument this book names" and "measured
elsewhere, in an instrument this book does not have".

## 3 · Ground / Source
`metrics.md:88-101`, the section header states the purpose — 部分外部 VF 素材使用一套 RegBase
细粒度泳道/指标命名（RVEC 单元名 + 仿真 cycle/IPC）。移植其策略到本库卡片时，**一律翻译成下表
右列的 msprof/trace 口径**，卡片正文只用右列词汇，不引任何外部工具命令、报告文件名或 golden
校验开关 — followed by the six-row table quoted in SOURCE, and the closing rule at `:101`:

> 右列才是本库口径。凡卡片"何时用"引用泳道，用 VECTOR/MTE2/MTE3/SCALAR + `aiv_*_ratio`；凡
> "性能数据"给数字，用 `aiv_time`/aicore cycle；正确性一律指向 `func_cases` 精度回归，不引
> 外部 golden 工具。

`vec.md:61` states the same unit set from the other side: ascend950 regbase 范式使用 **RVEC**
单元：RVECEX（执行）、RVECLD（加载）、RVECST（存储）、RVECSU（设置）。与 msprof 泳道的对应见
`metrics.md` §4.

The discipline is visibly obeyed in the ported cards: vec-04 through vec-12 all cite 外部 VF
策略 N in 关联 and state their diagnostic conditions in msprof vocabulary. It is also visibly
strained: `vec-03:47`'s only number is 外部同类改造实测约 -40%（作为预期方向，非本库实测；须以
本 case 上板 `aiv_time` 前后确认）, which is the honest form — the number is kept, labelled
borrowed, and fenced with the measurement that would replace it. Note also the caveat inside the
table itself at `:97`: preg spill/reload 寄存器溢出，int64 用双寄存器时实际 preg ×2, which is
entry 0036's subject.

## 4 · Procedure
Later phase, needs a card and a tool that reports RVEC-level units; if no such tool is available
to this book, the entry stays harvested and says so.
1. Device selection per 0010; board token from the driver.
2. Build three kernels, each designed to load exactly one RVEC unit: (E) execute-heavy, a long
   chain of register arithmetic with a single load and store; (S) setup-heavy, many short VF
   invocations with mask/constant setup dominating; (L) load/store-heavy, minimal arithmetic
   over many UB↔register transfers.
3. Capture each with msprof (five lanes) and, if available, with the external RVEC-level tool,
   from the same build, in the same session.
4. Record, per kernel: the busy share of each RVEC unit and of each msprof lane.

## 5 · Checker — acceptance declared before the run
Verdict variable `translation_holds`: for each of the three kernels, the RVEC unit the kernel was
built to load must be the maximum of the RVEC columns, AND the msprof lane it maps to must be
the maximum of the msprof columns. Three kernels, two orderings each, no partial credit.

Exit code is not the verdict — a missing external tool exits non-zero and the correct report is
`untestable_here`, which is a legitimate outcome that leaves the entry harvested rather than
pretending a pass.

Red input: kernel L against the RVECSU row. If setup shows as the maximum for the load/store
kernel, either the translation or the kernel construction is wrong, and the checker names which
column disagreed rather than reporting an aggregate mismatch.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. It does not establish that the correspondence is exact — upstream offers it as
a translation for porting prose, not as a claim about hardware counters, and the table's own
header calls it 仅作翻译参照. It does not establish that this book can run the external tool at
all. It says nothing about which architecture the RVEC unit names belong to beyond 950-era
RegBase, and nothing about whether the same names mean the same units in a different CANN
version. The `func_cases` correspondence in the last row is a process claim about upstream's
workflow, not a technical one, and is carried here only because dropping it would leave the
table incomplete.
