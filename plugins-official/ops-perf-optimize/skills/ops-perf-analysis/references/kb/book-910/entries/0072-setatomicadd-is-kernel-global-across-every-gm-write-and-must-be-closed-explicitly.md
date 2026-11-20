```
ID:        0072-setatomicadd-is-kernel-global-across-every-gm-write-and-must-be-closed-explicitly
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-atomic.md:9 — "作用范围**不限于 Fixpipe（L0C→GM）**，还包括 DataCopy UB→GM（MTE3），A2/A3 上还含 L1→GM"; ibid:66 — "作用域是核内全局的（不限于单次搬运调用），**必须显式关闭**"; ibid:81 — "同 kernel 内后续所有目的地址为 GM 的搬运…都会被累加，导致结果翻倍或数据损坏"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a GM write issued after `SetAtomicAdd` and outside the intended accumulation region is shown to overwrite rather than accumulate on a named DAV_2201 board — i.e. the scope is per-call, not kernel-global.
```

# 0072 · SetAtomicAdd is kernel-global across every GM write and must be closed explicitly

## 1 · Claim
Upstream asserts that DMA atomic mode governs **all** transfers whose destination is GM — not only
FixPipe (L0C→GM) but also `DataCopy` UB→GM via MTE3, and on A2/A3 additionally L1→GM. Upstream
asserts the scope is kernel-global rather than per-call and must be closed explicitly, that
`SetAtomicAdd` must be called before the first GM write and `DisableDmaAtomic` after the last
accumulating transfer is *issued*, and that failing to close it makes every subsequent GM-destined
transfer in the kernel accumulate — "结果翻倍或数据损坏". Upstream asserts `SetAtomicNone()` is
deprecated in favour of `DisableDmaAtomic()`. Not established here.

## 2 · The wrong branch this removes
An agent enables atomic accumulation for a split-K Matmul epilogue, gets the right answer, and moves
on. The mode is still on. Everything the kernel writes to GM afterwards — a separate output tensor,
a workspace flush, a debug buffer, an unrelated stage's result — is accumulated into whatever was
already there. The first output is correct, which is what makes the omission survive review.

Three properties make this worse than an ordinary unbalanced-pair bug:
- **The blast radius is wider than the API suggests.** An agent who reads `SetAtomicAdd` as a
  Matmul/FixPipe setting — a natural reading, since §5.3 of the same document draws it on the Matmul
  pipeline — will not expect it to capture a plain `DataCopy` from UB. Upstream states the wider
  scope in its first paragraph, and the wider scope is the whole hazard.
- **It is a mode, not an argument.** There is no call site to inspect. An audit that checks every
  `DataCopy` for correctness finds nothing wrong with any of them.
- **The symptom is "doubled", which reads as a loop bug.** A result exactly 2× the expectation
  sends an investigation to the tiling and the loop bounds, not to a mode set two hundred lines
  earlier.

The two adjacent preconditions close the remaining branches. **GM is not zeroed** by the interface,
so accumulating into a buffer with no first-write step accumulates onto residual data (0019's
neighbour hazard: the residue may be a previous launch's output, so a single run can look clean).
And the enable/disable instructions are `PIPE_S` while the transfers are `PIPE_FIX`/`PIPE_MTE3`, so
upstream states explicitly that **no manual synchronisation is needed** between them — which
forecloses an agent inserting a barrier that costs time and fixes nothing.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-atomic.md:9`, verbatim:
"DMA 原子操作控制**所有目的地址为 GM 的数据搬运**如何处理多核/多 rank 对同一 GM 地址的并发写入。
官方原文：\"对后续目的地址为 GM 的数据搬运开启原子累加\"——作用范围**不限于 Fixpipe（L0C→GM）**，
还包括 DataCopy UB→GM（MTE3），**A2/A3 上还含 L1→GM**。"

The API set, lines 21-25: `SetAtomicAdd<T>()`, `SetAtomicMax<T>()`, `SetAtomicMin<T>()`,
`SetAtomicNone()` ("已废弃，建议用 `DisableDmaAtomic`"), `DisableDmaAtomic()`. Header:
`basic_api/kernel_operator_set_atomic_intf.h` (line 17).

The timing constraints, lines 63-66, verbatim:
"1. `SetAtomicAdd` 必须在首次 GM 写入之前调用
2. `DisableDmaAtomic` 在所有需要累加的搬运指令发射之后调用
3. 作用域是核内全局的（不限于单次搬运调用），**必须显式关闭**"

The failure, lines 75-81: "❌ 错误：SetAtomicAdd 后未关闭，影响同 kernel 内后续所有 GM 写入 …
**后果**：同 kernel 内后续所有目的地址为 GM 的搬运（含 UB→GM DataCopy）都会被累加，导致结果翻倍
或数据损坏。"

The preconditions, lines 48-50:
"| **GM 不会自动清零**：接口执行前不会清零 GM 数据，需开发者手动初始化 | 结果 = GM 随机残留值 +
部分和 |
| 开启/关闭原子指令为 PIPE_S，与搬运指令（PIPE_FIX/PIPE_MTE3）不同流水 | 官方明确：开启原子操作的
指令与后续搬运指令之间**不需要**开发者插入同步 |"

And the L0C distinction, line 150: "`SetAtomicAdd` 不影响 L0C 内的累加（L0C 累加是 MMAD 行为，与
DMA 随路原子无关）。需要 L0C 级累加时不要用原子操作，直接在 L0C 累加后单次 Fixpipe 写出。"

Note the A2/A3-specific clause in line 9: the L1→GM path is named for our family specifically. Note
also that `ops/npu-arch/SKILL.md:63` lists "L1→GM 通路已删除" among DAV_3510's changes (via
`npu-hardware-params.md:170`, "L1→GM 和 GM→L0A/L0B 通路已删除"), which is consistent — the path
exists on DAV_2201 and not later — and is a second same-repo statement, so one origin, but a
mutually corroborating one on a question of fact.

The non-determinism precondition is carried separately by 0073.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Scope arm, the substance: a kernel that calls `SetAtomicAdd<float>()`, performs an accumulating
   FixPipe write to buffer A, then **without disabling** performs a plain `DataCopy` UB→GM to a
   *different* buffer B that was pre-filled with a known non-zero pattern. If the scope is
   kernel-global, B holds pattern + payload; if per-call, B holds payload alone.
3. Control arm: identical with `DisableDmaAtomic()` between the two writes. B must hold payload
   alone.
4. Path arm, testing the A2/A3-specific clause: repeat with an L1→GM transfer as the second write.
5. Zeroing arm: accumulate into a buffer pre-filled with a known non-zero pattern and confirm the
   result is pattern + sum, establishing that no implicit zeroing occurs.
6. Verify every element; report the arithmetic relationship (overwritten / summed), not merely
   equality.

## 5 · Checker — acceptance declared before the run
Verdict per arm: `B_relation` ∈ {overwritten, summed, other}.
PASS (claim upheld) iff arm 2 gives `summed` and arm 3 gives `overwritten`.
Both clauses are required and the control is not optional: `summed` in arm 2 alone is consistent
with the pre-fill never having been written, so arm 3 is what proves the mode is what changed.
`other` — neither overwritten nor summed — is a third recorded outcome and is not collapsed into
either; it would indicate a dtype or width mismatch of the kind upstream warns about at line 90.
The positive fixture: arm 5's pre-filled buffer must show pattern + sum. If it shows sum alone, the
interface *is* zeroing and upstream's precondition is wrong — a real finding, and one a checker that
only tested arm 2 would never surface.
Exit code is not the verdict; atomic accumulation onto residue does not fault.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. The A2/A3 clause covers the L1→GM path only; the rest of the
claim carries no architecture. This entry does not establish the cost of enabling or disabling the
mode. It does not establish whether the scope is per-core or per-kernel across cores — upstream
says "核内全局" (core-internal global), which leaves multi-core semantics unstated. It does not
establish what "数据损坏" means beyond doubling, nor whether `SetAtomicMax`/`Min` share the same
scope rule. It does not cover the deprecated `SetAtomicNone()` beyond upstream's statement that the
two are internally equivalent.
