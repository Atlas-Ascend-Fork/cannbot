# book-950 — boards 950PR / 950DT

Scope: the current 950 generation (950PR and 950DT). This is the regbase/SIMT-era architecture:
much upstream material that reads as generic AscendC advice is in fact 910-era advice, and much
950 material announces itself by vocabulary (regbase, SIMT, new pipe/buffer names) rather than by
board name — harvesters must scope by mechanism, not by whether "950" appears in the text. When
in doubt, an upstream claim lands in the book whose mechanism it names, and its §7 records the
doubt.

Nothing here inherits from book-910 (RULES.md Art. 1). "The 910 book verified X and the architectures
are similar" is exactly the sentence this separation exists to forbid.

## Level map (provisional — adopted from the parent book's C-9, unvalidated for this architecture)
L0 launch & host · L1 core & pipe assignment · L2 memory hierarchy & residency ·
L3 data movement & layout · L4 synchronisation · L5 compute & numerics ·
L6 tiling & scheduling · L7 verification · L8 toolchain & build · L9 performance.

Provisional means: the first harvester who finds a 950 failure mode that fits no level, or that
straddles two (register pressure vs residency is the predicted strain point), amends the map here
and logs it, rather than forcing the fit.

## SKILL.md
Same contract as book-910's: installation provenance with re-derive commands, populated only when
a 950 verification phase opens. Until then: "no installation bound yet".

## Files
- `entries/` — `NNNN-<claim-shaped-slug>.md`, form per `../form/ENTRY_TEMPLATE.md`
- `STANDING_QUESTIONS.md` — named measurements owed, posed during harvest, answerable only on-card

**Self-contained for handover (2026-08-24):** this book carries its own form pack (`form/`)
and checker (`tools/check_entries.sh`, run it from the book root with no arguments; `--selftest`
verifies the checker itself). Extensions to this book follow `form/ENTRY_TEMPLATE.md` and must
pass the checker.
