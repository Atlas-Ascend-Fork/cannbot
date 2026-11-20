# CARD · perf-optimize-core 001 — cannsim was renamed npusim, and both names share one entry point

**BOOK: 950 (fragment) — held as a card: a tooling-identity claim with no second source and no
observable consequence for any kernel.**

## Quote (verbatim, re-verified 2026-08-24)
`ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-02-stage-order-rescheduling.md:11`:

> npusim record ./<user_app> -s Ascend950 -g -o ./out   # cannsim 已更名 npusim，两名字同入口

with `:12` — `npusim report -e ./out -n all   # 逐核指令级 trace（chrome trace json）` — and
`index.md:33`, which names the simulator entry as `/ops-simulator`, 仅支持 950.

## Why this is a card and not an entry
It is a fact about a command name, not about a machine. There is no claim to falsify on a board, no
wrong branch a consuming agent takes at kernel level, and no §4 that is more than "run both names and
see". It matters only because 950:0010's simulator arm has to invoke *something*, and the neighbouring
`ops-simulator` skill documents only `cannsim` — so an agent following that skill and an agent
following this card would type different commands.

## Guessed level
L8 (toolchain & build).

## Evidence class
bare — an aside in a code comment.

## OVERTURN sketch
On an installed toolkit, `npusim` and `cannsim` resolve to different binaries with different
behaviour, or one of them does not exist at all.

## Disposition
Card kept; the question is posed in `harvest/standing/950-core.md` (L8, answerable read-only without
a card). Promote only if the answer changes what 950:0010's procedure must run.
