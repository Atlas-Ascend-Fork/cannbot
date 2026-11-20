```
ID:        0043-double-buffering-is-enabled-by-initbuffer-num-not-by-tque-depth
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin; two documents in that repo state it, which is one origin
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/elementwise/double_buffer_design.md:133-135 — "注意：TQue 模板参数 depth 为队列深度（连续 EnQue 次数），与 double buffer 无关。double buffer 仅通过 InitBuffer 的 num 参数控制（num=2 开启）"; ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:309 — "| `TQue<VECIN, 1>` + `InitBuffer(que, 2, size)` | 支持真正并行 | double buffer 由 InitBuffer num=2 控制，depth=1 即可 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `TQue<VECIN, 2>` with `InitBuffer(que, 1, size)` is shown to overlap MTE2 with Vector on a named Atlas A2 board, or `InitBuffer(que, 2, ...)` with depth 1 is shown not to.
```

# 0043 · Double buffering is enabled by InitBuffer's num, not by TQue's depth

## 1 · Claim
Upstream asserts that the `TQue` template's `depth` parameter is the queue depth — the number of
consecutive `EnQue` calls permitted — and is unrelated to double buffering; that double buffering
is controlled solely by `InitBuffer`'s `num` argument, with `num = 2` enabling it; and that
`depth = 1` is sufficient. Upstream asserts that doubling `num` doubles UB consumption and requires
the UB tiling factor to be halved. Not established here.

## 2 · The wrong branch this removes
`TQue<QuePosition::VECIN, 2>` reads exactly like "a queue with two buffers", and an agent wanting
double buffering will write it. Per upstream it enables nothing of the kind — it permits two
outstanding `EnQue` calls, which is a different property — and `InitBuffer(que, 1, size)` alongside
it allocates one buffer. The code compiles, runs, produces correct results, and does not overlap.

This is the completion of 0042: an agent that correctly learns "TBuf cannot overlap, use TQue"
switches to TQue and can still get no overlap, by setting the wrong one of two plausible
parameters. Both mistakes present identically — correct output, serialised pipes — so an agent that
made the second after fixing the first has no signal that anything is still wrong.

The third branch is the budget half. `num = 2` doubles UB consumption, and upstream states the
compensating rule plainly: "InitBuffer 的 num 翻倍时 ub_factor 必须减半". An agent that enables
double buffering without halving the factor over-commits UB against the 192 KB of 0003.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/elementwise/double_buffer_design.md`, lines
133-139, verbatim:
"// 注意：TQue 模板参数 depth 为队列深度（连续 EnQue 次数），与 double buffer 无关。
//       double buffer 仅通过 InitBuffer 的 num 参数控制（num=2 开启）。
pipe.InitBuffer(inQueue,  2, tileSize * sizeof(T));  // num = 2 开启 double buffer
pipe.InitBuffer(outQueue, 2, tileSize * sizeof(T));  // num = 2 开启 double buffer"

The budget rule, same file lines 65 and 75: "uint32_t ubFactor;        // UB 分块因子，bufferNum
翻倍时减半" and "| `ubFactor` | 原值 / `bufferNum` | InitBuffer 的 num 翻倍时 ub_factor 必须减半 |".
The budget formula, lines 79-80:
```
Required UB = tile_size × sizeof(dtype) × buffer_num × num_tensors
Available UB = 192KB (Ascend 910B3)
```
— note the chip attribution: **Ascend910B3**, a part `form/CONVENTIONS.md` has no token for (see
0009 §3), in a family guide whose 適用架構 column reads DAV_3510. So a 910-scoped example sits
inside a 950-marked document; the example is taken here and the document's family marking is not.

The A2 statement, `ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:309`:
`| \`TQue<VECIN, 1>\` + \`InitBuffer(que, 2, size)\` | 支持真正并行 | double buffer 由 InitBuffer
num=2 控制，depth=1 即可 |`, with the same form at line 102-103 and the blocking note at line 118:
"- `AllocTensor` 在 queue 满时**阻塞**等待 `FreeTensor`" and line 119: "- 不能预先 Alloc 所有
chunk（死锁！）".

Same repo throughout: one origin, stated in two skills.

The deadlock note is worth carrying with the rest: the working pattern requires allocating and
freeing inside the loop, and an agent that hoists allocation out of the loop for efficiency
deadlocks rather than slowing down.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Four arms over one algorithm, differing only in the two parameters, md5-confirmed:
   - `TQue<VECIN,1>` + `InitBuffer(que, 1, size)` — neither; the control.
   - `TQue<VECIN,2>` + `InitBuffer(que, 1, size)` — depth only; predicted no overlap.
   - `TQue<VECIN,1>` + `InitBuffer(que, 2, size)` — num only; predicted overlap.
   - `TQue<VECIN,2>` + `InitBuffer(que, 2, size)` — both; predicted overlap, no better than num
     alone.
3. Per arm: the `overlap` metric of 0042 §5, plus host-reported peak UB. The UB reading is what
   tests the budget half — the two `num = 2` arms should consume about twice the two `num = 1` arms.
4. Five repeats, first discarded, arms interleaved. Total data and tile size identical across arms.

## 5 · Checker — acceptance declared before the run
Verdict variables `overlap(arm)` and `ub_bytes(arm)`.
PASS iff `overlap` is low for both `num = 1` arms and high for both `num = 2` arms, independent of
depth — that is, the four-cell pattern must split by `num` and not by `depth`.
The 2×2 design is what makes this checker able to go red in the informative direction: a
one-variable test comparing only the control against the both-set arm would pass whichever
parameter were responsible, which is exactly the confusion the entry exists to remove.
`ub_bytes`: PASS iff the `num = 2` arms consume within 10 % of twice the `num = 1` arms.
Red input: `overlap` splitting by depth rather than by num, which overturns and means the API
documentation an agent would infer from parameter names is the correct one.
Exit code is not the verdict; the deadlock case from §3 would hang rather than exit, so the
procedure sets a wall-clock timeout and records a timeout as its own outcome, not as a failure.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. The A2 statement is product-line-scoped (0041 §7); the
elementwise statement names Ascend910B3, which this book cannot write as a BOARD token. This entry
does not establish what `depth` IS for — upstream says "连续 EnQue 次数" and no source in scope
gives a case where a depth above 1 is needed. It does not establish triple buffering, which
`double_buffer_design.md:53` mentions for Cube+Vector fusion without detail. It does not establish
the deadlock condition precisely, only that upstream warns of it.
