# CARD · perf-optimize-core 002 — the collection convention cites a workflows file that does not exist

**BOOK: 950 (fragment) — held as a card: a dangling reference, recorded so the gap is not silently
inherited by the replacement.**

## Quote (verbatim, re-verified 2026-08-24)
`ascendc-perf-optimize/references/single-core-pipeline/metrics.md:17`:

> - **逐 case 采集**：性能优化工作流对 `{cases_csv}` 中**每个 case** 单独采一次 `aiv_time`，禁止只挑
>   代表性用例；对齐口径见 `workflows/cannbench-a5-baseline-collection.md`。

Re-verification: no file of that name exists anywhere under `upstream/skills-dev-main/ops/`
(`find ... -name "cannbench-a5-baseline-collection.md"` returns nothing; no `workflows/` directory
exists under `ops/` either — the only workflow YAMLs in the repo are under
`plugins-official/ops-registry-invoke-demo/workflows/`).

## Why this is a card and not an entry
The *rule* it supports — per-case capture, no representative sampling — is carried by entry
**950:0010**, which quotes this same line and records the dangling citation in its §3. What is left
over is the missing file itself: the alignment convention it was supposed to define (how the case CSV
is structured, what "aligned" means across runs) is nowhere in the tree, so the replacement cannot
reproduce it and must either define its own or say the convention is unavailable.

## Guessed level
L7 (verification).

## Evidence class
bare — a pointer, with nothing behind it.

## OVERTURN sketch
The file exists in a part of the upstream repo not mined here, or in a sibling repo the skill assumes
is checked out alongside — in which case the convention is recoverable and this card closes.

## Disposition
Card kept as a coverage gap for the the delivered skill builder: `references/` in the replacement must not
carry an unresolvable pointer (the same species as the off-by-one `../` links the deep-dive found in
the tiling subtree).
