# CARD · ascendc-tiling-design 001 — FlashAttention `mode = 2` is the A2/A3 setting

**BOOK: 910 (candidate entry) — held as a card because the parameter it configures is never defined
in scope.**

## Quote (verbatim, re-verified 2026-08-24)
`ascendc-tiling-design/references/flashattention/design.md:525`:

> - **mode**:平台相关(A2/A3 用 mode=2;A5 推荐 mode=4 + AIV1 早返回;详见 `/npu-arch` 平台 API 版本表)

## Why this matters to book-910
This is a **directly A2/A3-scoped configuration value** — the class of statement this book is
hunting, and rare: the 2026-08-24 harvest found only a handful of upstream lines that name Atlas
A2/A3 and give a concrete value. Per book-910 entry 0001, "A2/A3" is exactly DAV_2201.

## Why this is a card and not an entry
`mode` is not defined anywhere in the sources in scope. The line points at "`/npu-arch` 平台 API
版本表" for the definition, and **no such table exists** in `npu-arch`: its four reference files and
SKILL.md contain no platform-API-version table. So the card records a value for a parameter whose
meaning, valid range and effect are unknown.

An entry needs a §2 ("the wrong branch this removes") and a §4 (a runnable procedure). Neither can
be written: without knowing what `mode` selects, the wrong branch cannot be named beyond "sets the
wrong number", and a procedure cannot make the OVERTURN observable. Per the plan's Stage 2 rule —
"An entry whose §4 you cannot write is not ready — leave it a card" — it stays here.

The dangling cross-reference is itself worth reporting: a load-bearing definition pointer into
`npu-arch` that does not resolve.

## Guessed level
L4 (synchronisation) — the A5 note pairs `mode=4` with "AIV1 早返回", which reads like a cross-core
synchronisation mode, plausibly the same three-mode family as
`ascendc-performance-analysis/references/metrics_reference.md:438-444` ("核间同步（Atlas A2/A3）",
模式 0/1/2). If that identification holds, `mode=2` would be "AI Core 内部 AIC 与 AIV 之间同步" —
**this is a guess and is not established**; the two documents never reference each other.

## Evidence class
bare — a value with a platform scope and no derivation, no measurement, and no resolvable definition.

## OVERTURN sketch
On a named DAV_2201 board, a FlashAttention kernel built with `mode=4` (the A5 recommendation) runs
correctly and no slower than one built with `mode=2`, at the same shape — i.e. the platform
dependence does not bite. Requires first establishing what `mode` is, which is the blocking step.

## Disposition
Card kept, with a standing sub-question: locate the definition of `mode`, or record that upstream's
pointer to it does not resolve. Related to book-910 STANDING_QUESTIONS Q-910-13 (the A2 cross-core
synchronisation question) if the level guess above is right.
