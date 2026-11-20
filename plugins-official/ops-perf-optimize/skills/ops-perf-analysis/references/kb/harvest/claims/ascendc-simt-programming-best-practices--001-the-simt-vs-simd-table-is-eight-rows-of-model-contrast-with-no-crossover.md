# CARD · ascendc-simt-programming-best-practices 001 — the SIMT vs SIMD table is eight rows of model contrast with no crossover

**BOOK: 950 — held as a card. Two of its eight rows are entered from the reference files that carry them
(`950:0378`); the table as a whole is a model contrast with no threshold, no measurement and no crossover
point, which is the same gap `Q-950arch-23` records against `950:0243` from a different skill.**

## The table (verbatim, re-verified 2026-08-24)
`ascendc-simt-programming-best-practices/SKILL.md:46-58`:

> ## SIMT vs SIMD 差异速查
>
> | 维度 | SIMT | SIMD |
> |------|------|------|
> | **编程模型** | 多线程并行，每线程独立执行 | 单核向量指令，整块数据并行 |
> | **函数标记** | `__simt_vf__` | 无特殊标记 |
> | **启动方式** | `Simt::VF_CALL<VF>(Dim3(N), args)` | 直接在 kernel 内调用 |
> | **线程索引** | GetThreadIdx / GetBlockIdx | 无线程概念，靠 tile 循环 |
> | **数据访问** | GM 直接读写（`__gm__ T*`） | DataCopyPad 搬到 UB/L0C |
> | **计算方式** | C++ 运算符（`y[i]=x[i]+1`） | 向量 API（`Add(xLocal, yLocal, zLocal)`） |
> | **核内共享** | UB buffer + `__ubuf__` 指针 | TQue 流水线 queue |
> | **多核同步** | `SyncAll()` + `SetScheduleMode(1)` | 流水线 set/wait flag |
> | **适用场景** | 逐元素、条件分支、不规则访问 | 规则向量、高吞吐归约 |

## Disposition, row by row

| Row | Disposition |
|-----|-------------|
| 编程模型 | card — a definition |
| 函数标记 | card — `__simt_vf__` is entered as `950:0241` (a SIMT VF must return void and accept only listed parameter kinds) |
| 启动方式 | **entered from elsewhere** — `950:0232` (compile-time thread count, 2048 cap), `950:0373` (the launch primitive's preprocessor gate). Note this row's spelling `Simt::VF_CALL(Dim3(N))` is one of two in circulation; the vendor's own docs use `asc_vf_call(dim3(...))` (`950:0375`, `C-950rem-014`) |
| 线程索引 | **entered from elsewhere** — `950:0374`, which records that the guide's own return types disagree with the installed headers and that the accessors are 3-D templates |
| 数据访问 | **ENTRY `950:0378`** from `data-transfer.md`, which carries the same claim with a three-row selection table |
| 计算方式 | **ENTRY `950:0380`** from `compute-operators.md`, which carries the equivalence contradiction |
| 核内共享 | **ENTRY `950:0378`** (the UB-buffer half) and `950:0379` (the atomic requirement) |
| 多核同步 | **ENTRY `950:0376`** from `multi-core-sync.md` |
| 适用场景 | **card — and it is the row this card exists for** |

## The row that is not entered, and why it matters
适用场景: SIMT for 逐元素、条件分支、不规则访问 (element-wise, conditional branching, irregular access);
SIMD for 规则向量、高吞吐归约 (regular vector work, high-throughput reduction).

That is the model-selection rule, it is the first thing an agent needs, and it is **two qualitative lists
with no crossover point**. At what irregularity does a gather stop being worth a SIMD staged path? At what
branch density does divergence (which `950:0235` records as serialising both arms within a warp) cost more
than the branch-free SIMD alternative? At what reduction size does SIMT's per-thread accumulation lose to a
tree? Nothing in this skill or any other in scope answers any of them.

`Q-950arch-23` records exactly this gap reached from `ascendc-simt-tiling-design` via `950:0243`: "Upstream
gives two qualitative lists (Gather/Scatter/hash/sort vs dense matmul/long sequential) and **no crossover
point**." So the gap is now recorded from two independent documents in two skills, which strengthens the
case that it is a real absence in the upstream corpus rather than one file's omission. **This card's
contribution is that second sighting.**

## Why the table itself is a card
A comparison table is a routing artifact. Rows 1-8 are definitions and mechanism names, each of which is
either entered from the reference file that states it properly or is a bare fact about vocabulary; the
table adds no evidence to any of them. Row 9 is the one substantive claim and it has no threshold, so a §4
could not state what to measure or what red looks like.

Entering the table itself would also duplicate eight claims that already have better homes: each reference
file gives its row a worked example, a header, or a constraint list, and the table gives a phrase.

## One vocabulary observation worth preserving
The table's 启动方式 row writes `Simt::VF_CALL<VF>(Dim3(N), args)` and its 多核同步 row writes
`SyncAll() + SetScheduleMode(1)`. Both are the CamelCase `AscendC::Simt` surface. The installed toolkit
carries **two** parallel SIMT surfaces — the CamelCase one under `interface/simt_api/cpp/` and a lower-case,
CUDA-shaped one under `simt_api/` (`asc_vf_call`, `asc_syncthreads`, `asc_atomic_add`, `threadIdx.x`) — and
this skill mixes them: its `intra-core-shared.md:43` names `asc_atomic_add`, the lower-case spelling, while
everything else is CamelCase. The vendor's own `ascendc-simt-api-reference` uses the lower-case surface
throughout its examples. Carried by `950:0375` and `C-950rem-014`; recorded here because the table is where
an agent first meets the vocabulary and it presents one surface as *the* surface.

## Guessed level
L1 (core & pipe assignment) for the model rows; L3 for 数据访问; L4 for 核内共享 and 多核同步.

## Evidence class
bare. No measurement, no shape, no board anywhere in the table or its surrounding SKILL.md. The skill's
own header (`:8`) states its provenance: "本 skill 提供基于实际算子开发经验提炼的 SIMT 编程范式总结，这些
内容在 `asc-devkit` 中不包含" — distilled operator-development experience, explicitly not from the devkit
documentation.

## OVERTURN sketch
For the 适用场景 row, if it were ever entered: one operator implemented both ways and swept along the axis
the row names — index locality contiguous → shuffled for irregular access, or branch density 0 → 100% for
conditional work — with the crossover located. That is `Q-950arch-23`'s Arm C and `950:0378`'s Arm B
combined, and it is the measurement the whole SIMT/SIMD selection question rests on.

## Disposition
Card kept. **The 适用场景 row is the item to promote** once any crossover measurement exists; until then it
is two lists. Recorded for the merge: the missing crossover is now documented from two skills
(`Q-950arch-23` via `950:0243`, and this card via `SKILL.md:58`), and the delivered skill's routing cannot honestly
send an operator to SIMT or SIMD on either source's authority.
