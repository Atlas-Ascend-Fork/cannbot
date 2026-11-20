# book-910 — boards 910B2 → 910C

Scope: the 910 board family as upstream and our own work encounter it — 910B2/910B4 (Atlas A2
era) through 910C. "Family" is a shelf label, not a claim: every entry names the board(s) its
evidence touched (`BOARD:`), and nothing measured on one board is thereby established on another
(RULES.md Art. 2). Facts inherited from the parent `ascend910` book are NOT imported wholesale: if one
is wanted here, it enters as its own entry with its own SOURCE (the parent entry is a legitimate
origin — one origin) at the `harvested` stratum, and earns verification here like anything else.

## Level map (adopted from the parent book, C-9)
L0 launch & host · L1 core & pipe assignment · L2 memory hierarchy & residency ·
L3 data movement & layout · L4 synchronisation · L5 compute & numerics ·
L6 tiling & scheduling · L7 verification · L8 toolchain & build · L9 performance.

These cover the machine — chip and toolchain — and nothing else. Because this book exists to back
a performance-optimization skill, expect L9/L6/L2 to carry most entries; that is a prediction,
not a quota. Unusable if a machine failure fits no level or two levels prove inseparable — then
amend the map here and log it.

## SKILL.md
The single home for installation provenance (toolchain pins, arch tokens, include/link lines) —
each value paired with the command that re-derives it. Populated only when a verification phase
opens on a real installation; until then it carries the explicit line "no installation bound yet".

## Files
- `entries/` — `NNNN-<claim-shaped-slug>.md`, form per `../form/ENTRY_TEMPLATE.md`
- `STANDING_QUESTIONS.md` — named measurements owed, posed during harvest, answerable only on-card

**Self-contained for handover (2026-08-24):** this book carries its own form pack (`form/`)
and checker (`tools/check_entries.sh`, run it from the book root with no arguments; `--selftest`
verifies the checker itself). Extensions to this book follow `form/ENTRY_TEMPLATE.md` and must
pass the checker.
