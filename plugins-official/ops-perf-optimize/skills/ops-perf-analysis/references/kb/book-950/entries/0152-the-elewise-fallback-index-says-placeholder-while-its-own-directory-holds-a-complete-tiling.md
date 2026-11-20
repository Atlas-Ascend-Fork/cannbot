```
ID:        0152-the-elewise-fallback-index-says-placeholder-while-its-own-directory-holds-a-complete-tiling
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/elewise/fallback/index.md:3,9-18 —
           "> 当前为占位文档，内容待补充。" · "## 待补充内容 - 多核切分策略（沿总元素数均匀切分）
           - 单核切分策略（UB 容量 / 单元素大小 → 单次处理量） - Buffer 规划（inBuf / outBuf）
           - 分支覆盖" · "> 当前返回：「Elementwise Tiling 建模暂未收录。」" ;
           tiling/index.md:73 — "| Elementwise | [elewise/](elewise/) | [fallback/](elewise/fallback/)（占位） |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a reading of `elewise/fallback/tiling-flow.md` and `tiling-fields.md` showing they do not
           in fact cover the four items the placeholder lists as missing — the label would then be
           accurate and this entry wrong.
```

# 0152 · The elewise fallback index says "placeholder" while its own directory holds a complete tiling

## 1 · Claim
Upstream asserts, in the elementwise fallback's index, that the document is a placeholder whose
content is yet to be supplied (`当前为占位文档，内容待补充`), lists four specific items as missing —
multi-core splitting, single-core splitting, buffer planning and branch coverage — and states the
routing answer to give in the meantime: `当前返回：「Elementwise Tiling 建模暂未收录。」`. The
top-level tiling registry repeats the label, marking the elementwise fallback `占位`. In the same
directory sit `tiling-flow.md` and `tiling-fields.md`, which between them give the multi-core split
formula, the UB split formula, the buffer plan including the promotion branch's extra FP32 buffers,
a two-way scenario branch, a fourteen-row TilingData field table, three named constants and four
empirical rules — that is, all four listed items. Not established here; this entry records a
labelling state.

## 2 · The wrong branch this removes
The consuming contract is a routing table plus a refusal string, and both say this family has no
content. An agent that routes an `Abs` or `Exp` case here reads `index.md`, sees `占位`, emits
`Elementwise Tiling 建模暂未收录`, and stops — never opening the two files one directory level down
that answer the question completely. The knowledge is present and unreachable through the path the
router defines.

The failure is worse than a missed optimisation because of what the elementwise family is: the
simplest, most common operator shape in the set, and the one whose formulas the broadcast family
shares (0151). A refusal here also removes the reference implementation that the broadcast UB formula
should be checked against.

The general form recurs across this subtree and is the reason this is a `trap` entry rather than a
note: the artifact a consumer opens first states a summary that the body contradicts, and nothing
reconciles them. Gather states six templates and lists nine (0150); the scan script emits a template
its own flow document forbids (0136); the top-level registry marks three of four `占位` labels wrongly
(0156, 0163). In every case the summary is what transmits.

## 3 · Ground / Source
`elewise/fallback/index.md`, in full — the entire file is 18 lines:

```
# Elementwise 逐元素类 — 兜底算法

> 当前为占位文档，内容待补充。

## 适用算子

Sin, Cos, Abs, Exp 及逐元素激活函数

## 待补充内容

- 多核切分策略（沿总元素数均匀切分）
- 单核切分策略（UB 容量 / 单元素大小 → 单次处理量）
- Buffer 规划（inBuf / outBuf）
- 分支覆盖

---

> 当前返回：「Elementwise Tiling 建模暂未收录。」
```

The registry's matching label, `tiling/index.md:73`:

```
| Elementwise | [elewise/](elewise/) | [fallback/](elewise/fallback/)（占位） | — | — |
```

Now the four "missing" items, each located in the same directory.

**多核切分策略** — `elewise/fallback/tiling-flow.md:25-38`:

```
## 2. 多核切分

coreNum = min(
  (dim0 * minDtypeBits + MIN_TILING_BITS - 1) / MIN_TILING_BITS,
  availableCoreNum
)

blockFormer = AlignUp(CeilDiv(dim0, coreNum), 512)
blockNum = CeilDiv(dim0, blockFormer)
blockTail = dim0 - (blockNum - 1) * blockFormer

确保每核至少4KB数据，元素数对齐到512。
```

**单核切分策略** — `tiling-flow.md:42-56`, the UB split quoted in full in 0151 §3, including
`maxElemNum`, `ubFormer`, `ubLoopFormer` and `ubTailFormer`.

**Buffer 规划** — `tiling-flow.md:80-86`:

```
## 5. 升精度分支 UB 预算

| 项 | 原dtype直算 | 升精度分支 |
|---|------------|-----------|
| 输入/输出Buffer | half/bf16 | half/bf16 (不变) |
| FP32中间Buffer | — | K份 ubFormer*sizeof(float) |
| UB总占用 | bufferNum*ubFormer*elemBytes | 左边 + K*ubFormer*4 |
```

**分支覆盖** — `tiling-flow.md:8-21`:

```
## 1. 场景判定

给定: N个输入shape + M个输出shape

Step 1 — Shape判定:
  所有输入输出shape完全相同? → EleWise, 展平为dim0处理
  否则 → Broadcast分支

Step 2 — dtype×运算判定 (决定Compute路径):
  运算为Add/Sub + dtype∈{FP16,BF16} + 输入量级未知?
    → 升精度分支: Cast→FP32计算→Cast, 需额外FP32中间Buffer
    → 否则: 原dtype直接计算
```

plus the kernel execution model at `:60-76` and, in `tiling-fields.md`, a fourteen-row field table
(`:9-24`), a constants table (`:26-32`: `MIN_TILING_BITS = 32768 (4KB)`, `ELEM_ALIGN_FACTOR = 512`,
`ALIGN_256 = 256`) and four empirical rules (`:34-41`). A 260-line executable reference,
`fallback/script/elewise_tiling.py`, sits beside them.

So the placeholder's four bullets are each answered, in the same directory, by files the placeholder
does not mention. `elewise/fallback/index.md` links to nothing; it has no document index at all,
unlike every other family's fallback index in this subtree.

Registered as C-950tiling-026 (elewise `占位` label against present content), with the broadcast and
conversion instances as C-950tiling-027 and C-950tiling-028 (0156, 0163).

One nuance worth keeping: the placeholder's `分支覆盖` bullet and the flow document's Step-1 branch
are not the same thing. The flow's Step 1 routes non-identical shapes away to the broadcast family;
`分支覆盖` in the tiling-output schema sense (0103) means enumerating the dtype and shape-size
conditions a plan covers, and neither elewise file emits that block. So one of the four bullets is
answered only partially, and this entry says so rather than claiming a clean four-for-four.

## 4 · Procedure
The claim is about a document set, and the decisive test needs no device. It has not been run.

Arm 1 — coverage check, read-only, no device, no execution. For each of the placeholder's four
bullets, attempt to produce the corresponding artifact using only the files in
`elewise/fallback/`: a multi-core split for a given `dim0` and dtype; a UB split; a buffer plan
including the promotion branch; and a `branches` block in the schema of 0103. Record for each whether
it completed, and if not, the first missing symbol or rule. Expect three completions and one partial
(`分支覆盖`), per §3.

Arm 2 — routing behaviour, on a named 950 board (950PR or 950DT); never run in this phase. This arm
measures what the mislabel costs, which is the only part a board can answer.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved.

Take one elementwise case (`Exp`, fp16, `dim0 = 2^24`). Build two kernels with one compiler pin: the
plan derived from `tiling-flow.md` + the script (0151's script form), and a naive plan an agent would
write after receiving the refusal string — one core group, no 512-element alignment, `ubFormer` set to
a round number. md5 both; host echo of `coreNum`, `blockFormer`, `ubFormer`, `ubLoopFormer`; output
compared against an fp64 reference within the operator's declared tolerance; `aiv_time` under
`msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, against a variance floor
measured first.

Refuses to assume: that a free die stays free; that a die may be substituted; that `ubSize` or
`coreNum` are the script's literals (queried, 0141); that the naive plan is slower — arm 2 exists to
put a number on it, and a null is reported as a null.

## 5 · Checker — acceptance declared before the run
Verdict variable `bullets_covered`, 0 to 4, from arm 1, with the partial `分支覆盖` counted as 0.5 and
stated as such. Declared before the run: the `占位` label is wrong iff `bullets_covered ≥ 3`. The
OVERTURN fires iff `bullets_covered ≤ 1` — the directory would then genuinely lack the content and the
label would be accurate. Verdict `mislabel_cost` = naive median `aiv_time` / derived median
`aiv_time` from arm 2, reported with the variance floor.

The exit code is not the verdict. Arm 1's instrument is the four-row coverage table, and the checker
fails red if the table has fewer than four rows — a coverage check that silently skipped a bullet it
could not attempt would report a flattering count, which is the reads-only-what-it-expects species.
Arm 2's guard is the host echo of the tiling fields plus the elementwise output comparison, since a
naive plan with a wrong `ubFormer` may produce wrong results rather than slow ones (0151).

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Arm 1 needs no device and has
not been run either.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, and no coverage check was performed. The entry does not establish that the
content in `tiling-flow.md` and `tiling-fields.md` is *correct* — 0151 records a dimensional defect in
that very flow document, so "present" and "right" are separate questions and only the first is this
entry's subject. It does not establish that a consuming agent actually stops at the refusal string;
that is the predicted behaviour, not an observed one. It does not establish the cost of the mislabel.
It does not extend to the broadcast and conversion instances beyond citing them (0156, 0163). No chip
is named anywhere in the elewise family, so BOARD is `family-claimed(unverified)` and the chip is
unstated; §4 arm 2 names 950PR/950DT because that is where our run would happen. Nothing here is
established for any 910-family board.
