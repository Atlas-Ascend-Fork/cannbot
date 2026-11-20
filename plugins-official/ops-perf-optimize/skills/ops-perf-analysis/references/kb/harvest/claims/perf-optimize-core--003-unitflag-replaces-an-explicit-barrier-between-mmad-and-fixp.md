# CARD · perf-optimize-core 003 — UnitFlag replaces an explicit barrier between MMAD and Fixp

**BOOK: 950 (fragment) — held as a card: the only mention of this mechanism in the whole scope, on a
placeholder card, with no code and no measurement.**

## Quote (verbatim, re-verified 2026-08-24)
`ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-01-nobound.md:23`, one row
of the 手段清单 whose header says `before/after` 代码与 msprof 实测数据**待增量补**:

> | UnitFlag 减同步 | MMAD→Fixp 用 UnitFlag 同步替显式 Barrier | 减同步开销 |

and `no-bound.md:19`, from the diagnosis side:

> - 标记 UnitFlag 同步点，检查是否可以进一步减少

## Why this is a card and not an entry
Six words of mechanism and no more. Nothing in this scope says what a UnitFlag is, which pipes it
orders, how it is set, what it costs, or under what condition it is safe to substitute for an
explicit barrier — and the card that names it ships no code (entry **950:0051** records that
absence). An entry's §4 would have to invent the mechanism before it could test it, and its §2 could
not say what wrong branch it removes, because an agent cannot take *any* branch from this text.

It is worth a card rather than nothing because the pair it names — MMAD followed by Fixp — is
Cube-side, and the Cube side is otherwise absent from this skill's single-core half entirely (every
ratio the diagnosis layer uses is an `aiv_*` ratio). So this is the one thread in scope pointing at
AIC-side pipeline work.

## Guessed level
L4 (synchronisation).

## Evidence class
bare — a table row on a 占位 card.

## OVERTURN sketch
On a named 950 board, a Cube kernel built twice — explicit barrier between MMAD and Fixp, and
UnitFlag synchronisation — differing by less than run spread in `aiv_time`/`aicore_time`, with
bit-identical output: the substitution would then buy nothing.

## Disposition
Card kept. Promote to an entry only when the mechanism is documented somewhere (a neighbouring skill
or the installed headers) — otherwise the §4 would be exploration, not verification, and the entry
would state more than its source does.
