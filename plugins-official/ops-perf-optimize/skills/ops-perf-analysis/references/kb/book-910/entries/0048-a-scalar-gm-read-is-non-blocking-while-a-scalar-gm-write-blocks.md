```
ID:        0048-a-scalar-gm-read-is-non-blocking-while-a-scalar-gm-write-blocks
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin, a document declaring itself A2-verified; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:184-186 — "**非阻塞 GM 读**：`xGm_.GetValue(idx)` 发出后 scalar 立即继续，延迟被后续指令隐藏。**阻塞 GM 写**：`valGm_.SetValue(pos, val)` 等待写完成才继续"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a scalar `GetValue` on a named Atlas A2 board is shown to stall the scalar unit until the value arrives, or a `SetValue` is shown not to.
```

# 0048 · A scalar GM read is non-blocking while a scalar GM write blocks

## 1 · Claim
Upstream asserts that on Atlas A2, `GlobalTensor::GetValue` is non-blocking — the scalar unit
issues it and continues, with the latency hidden behind following instructions — while `SetValue`
blocks until the write completes. Upstream draws three counter-intuitive consequences: replacing a
non-blocking GM read with a synchronous scalar computation makes the code slower; reducing the
number of value outputs does not necessarily make it faster; and adding *unrelated* GM reads can
fill pipeline holes for free. Not established here.

## 2 · The wrong branch this removes
Three optimisations that look obviously correct and are, per upstream, wrong on this part.

First, replacing a GM read with arithmetic. "Recompute rather than reload" is a standard reflex on
machines where memory is slow. Here the read is free and the arithmetic is not — it occupies the
scalar unit that was going to be idle anyway.

Second, emitting fewer outputs. In a sparse-output kernel (TopK, NonZero, MaskedSelect) an agent
naturally tries to reduce the number of blocking `SetValue` calls. Per upstream, doing so creates
holes in the scalar pipeline and can be slower. The output cost is real — upstream calls `SetValue`
"标量输出的真实瓶颈" — but it is not reduced by writing less if what replaces it is nothing.

Third, and the one no agent would ever try without being told: *adding* GM reads to fill holes.
Upstream lists it as a technique ("增加无关 GM 读可以填充流水线空隙（免费延迟隐藏）"). That is the
kind of instruction only a measurement produces, and it is why this entry keeps upstream's three
inferences rather than only its two facts.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md` §3.3 "标量 GM 操作流水线",
lines 184-186, verbatim:
"**非阻塞 GM 读**：`xGm_.GetValue(idx)` 发出后 scalar 立即继续，延迟被后续指令隐藏。
**阻塞 GM 写**：`valGm_.SetValue(pos, val)` 等待写完成才继续。"

The pipeline picture, lines 190-193:
```
element i:   [GetValue_i]─────────[SetVal_i][SetIdx_i]
element i+1:              [GetValue_{i+1}]──────────[SetVal_{i+1}][SetIdx_{i+1}]
```
The three inferences, lines 195-198, verbatim: "**推论**：
- 不要用同步 scalar 计算替代非阻塞 GM 读（破坏流水线 → 变慢）
- 减少 value 输出不一定更快（流水线空洞 → 更慢）
- 增加无关 GM 读可以填充流水线空隙（免费延迟隐藏）"

The A2 hardware summary, lines 305-306: `| \`xGm_.GetValue\` | 非阻塞流水线读 | 不可替换为同步计算 |`
and `| \`SetValue\` | 阻塞写 | 是标量输出的真实瓶颈 |`. Two of the anti-patterns at lines 351-352
restate the first two inferences.

Note that upstream labels these 推论 — inferences — and not measurements, distinguishing them from
the two behavioural facts above. This book preserves that distinction: §1 states which are which,
and §5 tests them separately. The document also states that scalar output is unavoidable at line
281: "├─ 标量输出 → 无法优化（硬件限制），保持 GM SetValue".

The related incoherency that blocks the obvious workaround (batching output through UB and one DMA)
is 0019, from line 307 of this same table.

## 4 · Procedure
Proposed, runnable later; not run. The two facts and the three inferences need different arms.

1. Name the die; occupancy before and after; no substitution.
2. Fact arm A (read latency hiding): a scalar loop issuing `GetValue` followed by `K` independent
   arithmetic instructions, `K` swept over 0, 2, 4, 8, 16, 32. If the read is non-blocking, total
   time is flat until `K` exceeds the latency and then rises; if blocking, it rises from `K = 0`.
   The *shape*, not a single point, is the observation.
3. Fact arm B (write blocking): the same sweep with `SetValue` in place of `GetValue`. Predicted:
   rises from `K = 0`.
4. Inference arm 1: a loop with `GetValue` versus the same loop with the value recomputed by scalar
   arithmetic, identical results, md5-confirmed to differ only there. Predicted: the recompute
   version is slower.
5. Inference arm 3, the surprising one and therefore the one worth building: a sparse-output loop
   with and without an added unrelated `GetValue` per iteration whose result is discarded.
   Predicted: no slower, possibly faster. Guard against the compiler eliminating the dead read by
   consuming the value in a branch that never fires, and confirm from the device `.text` that the
   read survived — an eliminated read would make this arm silently vacuous.
6. Five repeats each, first discarded.

## 5 · Checker — acceptance declared before the run
`read_blocking`: derived from arm A's shape — the claim is upheld iff time at `K = 0` is
statistically indistinguishable from `K = 8` and rises only later. A monotone rise from `K = 0`
overturns.
`write_blocking`: upheld iff arm B rises from `K = 0`.
The two arms are each other's control: if BOTH are flat, the measurement is not resolving scalar
latency at all and both are VOID rather than one confirming and one refuting. That cross-check is
declared now.
`free_read_penalty` from arm 5: reported as a ratio with no declared pass threshold, because the
claim is that it is not positive rather than that it is any particular value. A ratio above 1.05
overturns inference 3.
Gate for arm 5: the `.text` comparison confirming the added read was emitted. If it was eliminated,
no verdict is issued — a dead-code-eliminated experiment that shows "no penalty" is a checker
reading only the lines it expects.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. "A2" is a product line, not a board (0041 §7). This entry
does not establish the latency of a scalar GM read, only that upstream reports it hidden — the
number would come from arm A's knee and is not claimed. It does not establish how many outstanding
reads the scalar unit supports. The three 推论 are upstream's inferences from its own measurements,
not measurements, and are marked as such throughout; a run of §4 arms 4 and 5 would establish them
independently. It says nothing about A3 or A5 (0047), nor about vector-issued GM access.
