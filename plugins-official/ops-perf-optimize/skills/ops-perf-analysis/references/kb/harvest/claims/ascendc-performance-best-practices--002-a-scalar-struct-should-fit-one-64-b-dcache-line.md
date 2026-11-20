# CARD · ascendc-performance-best-practices 002 — a scalar struct should fit one 64 B D-Cache line

**BOOK: 910 (candidate entry) — held as a card because the size rule is a coding guideline, not a
machine property, and its measured basis is absent.**

## Quote (verbatim, re-verified 2026-08-24)
`ascendc-performance-best-practices/reference/scalar/coding_principles.md:319`:

> 1. **缓存局部性差**：D-Cache cacheline 大小为 64 字节。结构体过大时，访问不同成员可能落在不同
> cacheline 上，导致 D-Cache miss 增多。建议结构体 ≤ 64B（1 个 cacheline），最大不超过 128B。

Index form, `reference/scalar/guide.md:17`:

> | [P7](coding_principles.md#p7-避免使用超大结构体) | 避免使用超大结构体 | > 64B 跨 cacheline；
> 超寄存器容量必 Spill；指针传递引入别名 |

Counter-example given, `:332`: `struct GodParams { ... }  // ~200B，跨多个 cacheline`, with `:349`
`int y = a->l0C;  // 与 l1A 在不同 cacheline`.

## Why this is a card and not an entry
The **64 B cache-line figure** is already carried by book-910 entry 0018, which cites this line as
the best-attributed statement of it — this guide's 適用架構 column
(`ascendc-performance-best-practices/SKILL.md:35`) reads **`DAV_2201 / DAV_3510`**, the strongest
architecture attribution for that number anywhere in scope.

What is left over is the **≤ 64 B / ≤ 128 B struct-size recommendation**, and that is a different
kind of claim: a coding guideline derived from the cache-line size plus an unstated assumption about
access patterns. Three reasons it is not entry-ready:

1. The two thresholds (64 B recommended, 128 B maximum) have no stated basis — why 2 lines and not
   3 is not derived.
2. It bundles three distinct mechanisms in one rule (cache-line straddling, register spill, pointer
   aliasing), each with its own wrong branch. Under book-910's merge test that is three entries or
   none, and none of the three has its own upstream evidence.
3. Its §4 would be a struct-size sweep measuring `SCALARLDST` time against struct size — which is
   0018 §4's line-size arm with a different x-axis. It adds an entry without adding an experiment.

## Guessed level
L5 (compute & numerics) or L2 (memory hierarchy & residency).

## Evidence class
recipe-no-numbers. A mechanism, a threshold pair, and a worked counter-example — no measurement, no
board, no case.

## OVERTURN sketch
A struct-size sweep on a named DAV_2201 board (16 B … 512 B, same members accessed in the same
order, `SCALARLDST` time per access, five repeats with the first discarded) shows no step at 64 B
and none at 128 B — i.e. the cost tracks total bytes touched rather than lines crossed.

## Disposition
Card kept. The 64 B figure it supplies is live in entry 0018 §3; the size recommendation waits for
either a sweep or a decision that a coding guideline belongs in the delivered skill rather than in a book.
