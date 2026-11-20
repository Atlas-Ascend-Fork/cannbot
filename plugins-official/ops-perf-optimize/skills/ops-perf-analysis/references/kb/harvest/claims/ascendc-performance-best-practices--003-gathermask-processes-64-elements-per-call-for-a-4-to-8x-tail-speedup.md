# CARD · ascendc-performance-best-practices 003 — GatherMask processes 64 elements per call for a claimed 4–8× tail speed-up

**BOOK: 910 (candidate entry) — held as a card: an unscoped speed-up range whose element count is
dtype-dependent in a way the source does not state.**

## Quote (verbatim, re-verified 2026-08-24)
`ascendc-performance-best-practices/reference/common/tail_block_design.md:12`:

> | 尾块计算 | 标量循环处理 | GatherMask 向量化处理 | 一次处理 64 个元素，提升 4-8 倍 |

Adjacent rows in the same benefit table (`:11`, `:13`, `:14`):

> | 尾块处理 | 简单截断，可能越界 | 双轨制 norm/tail 核分离 | 避免数据竞争和越界访问 |
> | 多核负载 | 尾核空闲或超载 | 动态 costLimit + 容忍度机制 | 非整除场景性能提升 10-30% |
> | 内存对齐 | 未考虑对齐 | 32B/64B 对齐 + DataCopyPad | 避免非对齐访问性能损失 |

Usage form, `:167-174`, with the pattern-type rule at `:180`: "**GatherMask 的 pattern buffer
类型**。float 类型用 uint32_t pattern，half/bfloat16_t 用 uint16_t pattern."

## Why this is a card and not an entry
Three problems, any one of which would be survivable and which together are not:

1. **"64 个元素" is dtype-dependent and stated as a constant.** 64 fp32 elements is 256 B — the
   Vector repeat coverage of book-910 entry **0032**. At fp16 the same 256 B is 128 elements. So the
   figure is either fp32-specific (and the source does not say so) or it is an element count that
   contradicts 0032's byte-based derivation. Writing it as an entry would import that ambiguity into
   the book's §1.
2. **"提升 4-8 倍" has no case at all** — no shape, no tail size, no dtype, no board, no tool. A 2×
   range on a speed-up claim, against a scalar baseline whose own cost depends entirely on the tail
   length, is not a magnitude that can be checked.
3. The same table's neighbouring row ("非整除场景性能提升 10-30%") is equally unscoped, so the
   pattern is a benefit table filled in by estimate rather than by measurement — the class this
   book's 0053 records for thresholds.

Entry-worthy content **was** extracted from this file: `0029` (the negative-tail-length
out-of-bounds trap, upstream's item 8, which supplies an invariant, a detection signature and a
host-side coverage check) and `0028`/`0021` (the alignment figures). Those had mechanisms. This row
has a number.

## Relation to existing book-910 entries
The element count needs reconciling with **0032** (one Vector repeat covers 8 × 32 B = 256 B) and
**0033** (the FP32 mask ceiling of 64 elements = 256 B ÷ 4 B). If 64 here is the fp32 mask ceiling
under another name, this is not a new fact and the card resolves into those two entries.

## Guessed level
L3 (data movement & layout) or L9 (performance).

## Evidence class
measured-unscoped, and weakly — a range, not a value; no case identity of any kind.

## OVERTURN sketch
On a named DAV_2201 board, a GatherMask tail-compaction against a scalar-loop equivalent at matched
tail lengths (1 … 512 elements) and dtypes (fp32, fp16) shows a speed-up outside 4–8× across the
sweep — the likely outcome being that the ratio depends strongly on tail length, so that no single
range exists. Separately: the element count per call is measured and found to be 128 at fp16, which
would show "64" as fp32-specific.

## Disposition
Card kept. Promote only if the element count is reconciled with 0032/0033 first — otherwise the
entry would state a constant that this book elsewhere derives differently.
