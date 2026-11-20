# CARD · ascendc-performance-analysis 001 — intra-core sync reserves TEventID 6 and 7, and a flagId caps at 15 settings

**BOOK: 910 (candidate entry) — held as a card: two hard limits with no stated architecture and no
observable failure mode described.**

## Quotes (verbatim, re-verified 2026-08-24)
`ascendc-performance-analysis/references/metrics_reference.md:428-436` (§8.1 核内同步):

> | **PipeBarrier** | 保证前序指令所有数据读写完成后，后序指令才执行 |
> | **SetFlag / WaitFlag** | 两个指令序列间的"锁"机制 |
> | **EventID** | 通过 AllocEventID/FetchEventID 获取，用完立即 ReleaseEventID |
>
> **注意**：
> - SetFlag/WaitFlag 必须成对使用，模板参数和事件 ID 完全一致
> - 不允许连续设置同一个 EventID
> - 不建议手动插入 TEventID 6 和 7（系统预留）

`ibid:446-449` (§8.2 核间同步（Atlas A2/A3）):

> - `CrossCoreSetFlag` / `CrossCoreWaitFlag` 必须成对使用
> - 同一 flagId 计数器最多设置 15 次
> - 不建议与 Matmul 高阶 API 同时使用

## Why this is a card and not an entry
Four constraints of genuinely different kinds are bundled in one place, and each is thin:

1. **TEventID 6 and 7 reserved** — a resource-partitioning fact. Stated as 不建议 (not advised),
   not forbidden, so what happens on violation is unknown. An entry's §2 would have to guess.
2. **flagId counter caps at 15 settings** — a real numeric limit, and the most entry-worthy of the
   four. It is A2/A3-scoped (the §8.2 heading). But no failure mode is described: whether the 16th
   set is dropped, wraps, or faults decides whether this is a trap or a capacity note, and nothing
   in scope says.
3. **Pairing requirements** — restatements of the API contract, not machine knowledge.
4. **"Not advised with Matmul high-level API"** — a compatibility warning with no mechanism.

Only (2) has a number, and its §4 would be: set one flagId 14, 15, 16, 20 times and observe. That
is writable — but the OVERTURN would be "the 16th set behaves like the 15th", and without knowing
the expected failure the checker cannot state in advance what red looks like, which the form
requires (§5 must name the input that makes it fail).

Held pending either a documented failure mode or a decision to write the procedure as an
exploration rather than a test.

## Relation to existing book-910 entries
The flagId limit is quoted in entry **0041 §3** as part of the evidence that A2 *does* have some
cross-core flag mechanism — which is `harvest/contradictions-910.md` **C-910-009** (radix_sort's
"A2 无硬件 barrier" against this documented `CrossCore*` API). So the 15-setting cap is already
load-bearing in the book without being its own entry.

## Guessed level
L4 (synchronisation).

## Evidence class
bare for (1), (3), (4); measured-unscoped for (2) — a specific integer with no derivation, no
measurement and (for §8.1) no architecture, though §8.2 carries an Atlas A2/A3 heading.

## OVERTURN sketch
For (2): on a named DAV_2201 board, setting one `flagId` 16 or more times before a matching wait
completes without loss of any signal and without a fault — i.e. the counter is not 4-bit and the
15 is not a hardware bound.
For (1): a kernel using TEventID 6 or 7 explicitly runs correctly and no slower than one using 0–5.

## Disposition
Card kept. Promote (2) to an entry if a failure mode is found, or if the exploration procedure is
accepted as a legitimate §4 for a capacity limit.
