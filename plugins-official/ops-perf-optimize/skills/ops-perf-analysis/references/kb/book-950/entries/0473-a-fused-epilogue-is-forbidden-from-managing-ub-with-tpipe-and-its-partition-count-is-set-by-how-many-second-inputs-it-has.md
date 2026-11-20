```
ID:        0473-a-fused-epilogue-is-forbidden-from-managing-ub-with-tpipe-and-its-partition-count-is-set-by-how-many-second-inputs-it-has
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/matmul/patterns.md:144-149 —
           "> **融合算子禁止使用 TPipe 管理 UB**，采用静态偏移分配。 / > / > `stageNum` 按输入路数选择： /
           > - 1（Relu/Cast 等无第二输入） → 仅 `resultLocal_` / > - 2（Div/Mul/Add 等单第二输入） →
           `secondLocal_` + `resultLocal_` / > - 3（Mul+Add 等双第二输入） → `secondLocal_` +
           `thirdLocal_` + `resultLocal_`"
SOURCE:    same family, matmul-fusion-design-template.md:224-229 —
           "**stageNum 选择**： / | stageNum | 输入路数 | 典型算子 | UB 分区 | /
           | 1 | 0（无额外输入） | Relu、GeLU、Cast | cLocal_ + cLocalTmp_ | /
           | 2 | 1（单第二路输入） | Div、Mul、Add | cLocal_ + dLocal_ + cLocalTmp_ | /
           | 3 | 2（双第二路输入） | Mul+Add | cLocal_ + dLocal1_ + dLocal2_ + cLocalTmp_ |" ;
           :207 — "> **融合算子禁止使用 TPipe 管理 UB**，采用静态偏移分配。" ;
           :388 — "| S3 | `stageNum = 2` | 输入路数变化导致布局错配 | 按 1/2/3 路重设 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an mxfp8 + eltwise fusion on a named 950 board built with `TPipe`-managed UB queues in the
           epilogue, whose output matches an FP64 reference and whose time is within the variance
           floor of the statically-offset build — the prohibition would then be a convention rather
           than a requirement. Equally: a single-input operator built with `stageNum = 2` whose
           output is wrong is the layout mismatch the sample register warns about, and its symptom
           is the observation this entry lacks.
```

# 0473 · A fused epilogue is forbidden from managing UB with TPipe, and its partition count is set by how many second inputs it has

## 1 · Claim
Upstream asserts that a fused matmul + eltwise operator must not use `TPipe` to manage UB, and must
instead allocate by static offsets. Upstream asserts that the number of UB stage partitions,
`stageNum`, is chosen by the number of *additional* inputs the epilogue consumes: 1 for operators with
no second input (Relu, GeLU, Cast), 2 for a single second input (Div, Mul, Add), 3 for two second
inputs (Mul+Add). Upstream asserts the corresponding UB partition lists — for `stageNum = 1`,
`cLocal_` plus a cast temporary; for 2, one staging buffer between them; for 3, two. Upstream lists
`stageNum = 2` in its sample-reevaluation register as a value whose risk is a layout mismatch when the
input count changes, with the required action being to reset it for 1, 2 or 3 paths. Not established
here.

## 2 · The wrong branch this removes
Without this entry an agent writes the epilogue the way every other Ascend C kernel in this corpus is
written: `TPipe pipe; pipe.InitBuffer(inQueue, 2, bytes); ...`. That is the framework's own idiom, it
is what the reduction, gather, broadcast and scan families all do, and it brings double buffering,
alloc/free discipline and the synchronisation events that the queue wrapper generates — which the FA
family relies on so heavily that omitting it is a documented defect there (`0463`). Here it is
forbidden, and upstream gives no reason at all: the prohibition is stated twice, in bold, in two files,
with no mechanism.

That silence is the finding. The most likely reading is that `matmulArea` — the Fixpipe landing region
— must sit at UB offset 0 with a layout the Cube side computes (`patterns.md:74-83`), and a
`TPipe`-managed allocator would place it wherever it liked; `0466` records, from a different family on
the same shelf, that `TBuf` membership itself determines the compiler's UB layout. That is an
inference and this entry does not promote it. Recorded as `Q-950fin-22`.

The second wrong branch is copying `stageNum` from the sample. The reference epilogue is `Div`, so the
sample carries `stageNum = 2`. An agent writing a `Relu` epilogue and keeping 2 reserves a staging
buffer that is never filled and, worse, computes `stageSize_` by dividing the residual by 2 rather than
1 (`0472`), so every buffer is half the size it could be. An agent writing `Mul+Add` and keeping 2 has
one staging buffer for two second inputs, and the second overwrites the first. The first error costs
performance silently; the second is a correctness defect whose symptom upstream does not state.

## 3 · Ground / Source
The prohibition and the selection rule, `references/matmul/patterns.md:144-149`:

```
> **融合算子禁止使用 TPipe 管理 UB**，采用静态偏移分配。
>
> `stageNum` 按输入路数选择：
> - 1（Relu/Cast 等无第二输入） → 仅 `resultLocal_`
> - 2（Div/Mul/Add 等单第二输入） → `secondLocal_` + `resultLocal_`
> - 3（Mul+Add 等双第二输入） → `secondLocal_` + `thirdLocal_` + `resultLocal_`
```

and the template's table of the same rule, `matmul-fusion-design-template.md:224-229`:

```
| stageNum | 输入路数 | 典型算子 | UB 分区 |
|----------|---------|---------|---------|
| 1 | 0（无额外输入） | Relu、GeLU、Cast | cLocal_ + cLocalTmp_ |
| 2 | 1（单第二路输入） | Div、Mul、Add | cLocal_ + dLocal_ + cLocalTmp_ |
| 3 | 2（双第二路输入） | Mul+Add | cLocal_ + dLocal1_ + dLocal2_ + cLocalTmp_ |
```

**The two lists do not name the same buffers.** `patterns.md` gives, for `stageNum = 1`, only
`resultLocal_`; the template gives `cLocal_ + cLocalTmp_` — two buffers, neither of them named
`resultLocal_`. For `stageNum = 2`, `patterns.md` gives `secondLocal_ + resultLocal_` and the template
gives `cLocal_ + dLocal_ + cLocalTmp_`. For 3, `secondLocal_ + thirdLocal_ + resultLocal_` versus
`cLocal_ + dLocal1_ + dLocal2_ + cLocalTmp_`. Two naming schemes for one layout, in one family, with
no mapping given. The template's own buffer table (`:201-205`) uses a third set of names —
`UB_L0COut (cLocal_)`, `UB_Eltwise (dLocal_)`, `UB_Cast (cLocalTmp_)` — which does map to the
template's list and not to `patterns.md`'s. Registered as `C-950fin-018`.

The `stageNum` count is also not the partition count. At `stageNum = 1` the template lists two
partitions; at 2, three; at 3, four. So `stageNum` counts the *stage* buffers and excludes
`matmulArea`/`cLocal_`, which is consistent with the budget formula
`matmulArea + stageNum × stageSize_` (`0472`) — the Fixpipe landing region is charged separately. An
agent reading `patterns.md`'s list, which omits `cLocal_` entirely, has no way to see that.

The sample-register row, `:388`:

```
| S3 | `stageNum = 2` | 输入路数变化导致布局错配 | 按 1/2/3 路重设 |
```

`布局错配`, layout mismatch — the risk is named and the symptom is not. This is one of ten such rows
(`0474`).

The prohibition appears at `patterns.md:144` and again at `matmul-fusion-design-template.md:207`,
identically worded. Two files, one repository: one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first, beside every timing point.

**Arm 1 — the prohibition, which upstream never justifies.** Two builds of one mxfp8 + Div fusion,
identical apart from the epilogue's UB management: static offsets per upstream, and `TPipe` with
`TQue`s of the same sizes. Echo every buffer's device-side address in both. Report: whether the
`TPipe` build compiles, whether the Fixpipe landing region still lands at the offset the Cube side
assumes, correctness, and time. The prediction from `Q-950fin-22` is that the `TPipe` build misplaces
`cLocal_`; if it does not, the prohibition has no mechanism visible from here and §7 says so.

**Arm 2 — the wrong `stageNum`.** Three epilogues (`Relu`, `Div`, `Mul+Add`) × three `stageNum` values
(1, 2, 3), nine builds. Report correctness, echoed `stageSize_`, echoed total occupancy and time.
Predictions: the diagonal is correct; `stageNum` too low for the input count is a correctness defect
(the second input's buffer is missing); `stageNum` too high is correct but wastes half the residual.
Upstream states neither symptom, so both halves are new.

**Arm 3 — the buffer-name mapping.** From the correct `Div` build, echo the address and extent of every
UB region and match them against both naming schemes. This resolves `C-950fin-018` by observation:
either `resultLocal_` is `cLocalTmp_` under another name, or one of the two lists omits a buffer.

**Arm 4 — retained because it may not bite.** The `stageNum = 1` `Relu` build with the second staging
buffer's region pre-filled with a sentinel, to confirm it is genuinely unused. If the sentinel is
destroyed, `stageNum = 1` does not mean one stage buffer and the selection rule is not what it says.

Refuses to assume: that a free die stays free, or that a die may be substituted; that a build that
compiles has the layout the Cube side assumes (arm 1 echoes addresses); that a correct output means the
partition count was right (arm 2 reports occupancy and `stageSize_` separately from correctness); that
the two naming schemes describe the same buffers (arm 3 tests it); that `stageSize_` is what the host
computed (echoed).

## 5 · Checker — acceptance declared before the run
Verdict `clocal_offset(management)` from arm 1: the echoed device address of the Fixpipe landing region
under each management scheme, declared before the run. Acceptance for the prohibition having a
mechanism: the two differ, and the `TPipe` build is wrong or faults. The OVERTURN fires iff the `TPipe`
build is correct with `|Δt| ≤ floor`.

Verdict `stagenum_outcome(op, n)` from arm 2, a 3×3 table over {`correct`, `wrong_values`,
`correct_but_undersized`}, declared as a full prediction before the run rather than read off after.

Verdict `name_map` from arm 3: an explicit correspondence, or `inconsistent` if no bijection exists.

Verdict `unused_region_intact` from arm 4, boolean.

The exit code is not the verdict: the over-provisioned builds in arm 2 are correct and merely slower,
which no correctness suite distinguishes from the right answer. Guards: (1) every build reports its
echoed `stageSize_` and total occupancy alongside correctness, and a build reported without them is
`untestable` — a table of pass/fail cannot show the `correct_but_undersized` outcome, which is half the
claim; (2) **the input that makes this checker go red**: the `Div` operator at `stageNum = 2`, the
sample's own configuration, which must be `correct` in both management schemes' address echoes and in
its output — if it is not, the harness is not reproducing the reference configuration and the whole
table is an artifact; (3) no cell is reported without its operator, `stageNum`, echoed addresses,
`DataType`, floor, atol and CANN pin.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The prohibition in both
locations, the two `stageNum` lists, the template's buffer table and the S3 sample row are file reads
performed at drafting time. The observations that the two lists name different buffers, that
`stageNum` counts stage buffers and excludes the Fixpipe landing region, and that the template's own
buffer table maps to one list and not the other, are readings of upstream's own lines, not observations
of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish why `TPipe` is forbidden — upstream
states the prohibition twice and gives no reason; `Q-950fin-22` records the inference and does not
promote it. It does not establish that a wrong `stageNum` produces wrong values rather than a layout
that merely wastes UB; upstream names the risk (`布局错配`) and no symptom. It does not resolve which
buffer naming scheme is authoritative (`C-950fin-018`). It does not establish that 1, 2 and 3 are the
only reachable values, nor what an epilogue with three second inputs would do. It does not cover
`stageSize_` itself, which is `0472`'s subject and whose formula this entry's `stageNum` divides. It
covers the mxfp8 + eltwise fusion pattern only (`0469`); the `TPipe` prohibition is stated for fused
operators in this family and nothing here says anything about `TPipe` use anywhere else in this book,
where it is the normal idiom. No board token appears in any quoted passage, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
