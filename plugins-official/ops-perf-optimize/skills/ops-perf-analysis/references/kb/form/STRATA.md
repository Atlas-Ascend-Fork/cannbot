# STRATA — the entry lifecycle, and what each stratum permits

The whole point of the stratum field: **a claim harvested from a document and a claim measured on
a die must never be confusable**, not even by an agent skimming. The word "harvested" in a header
is a fence, not a stage direction.

```
claim-card ──draft──▶ HARVESTED ──2nd origin──▶ CORROBORATED ──procedure run──▶ VERIFIED(board) ──independent walk──▶ ADMITTED
 (harvest/claims/)        │                          │                              │                                    │
                          └──────────────── any stratum ──killing observation──▶ OVERTURNED (kept, marked)
```

## S0 · claim-card (not yet an entry)
Lives in `harvest/claims/`, one file per extracted claim: quote, upstream path, guessed chip
scope, guessed level, one-line OVERTURN sketch. Cheap, plentiful, disposable. Cards are the
quarry; entries are the masonry.

## S1 · HARVESTED
A full-form entry (all seven sections) whose only ground is upstream text. Permitted verbs in §1:
"upstream asserts", "upstream's code does". Forbidden: any sentence that reads as a measurement.
INDEX is the literal line `none — nothing measured; see SOURCE`. §4 carries the proposed,
runnable-later procedure; §6 carries the NOT-YET-RUN line. OVERTURN is already concrete.

## S2 · CORROBORATED
Same as S1 plus a second INDEPENDENT origin in SOURCE. Independence means a different origin of
authority — the vendor's published CANN/AscendC documentation, a different team's repo, a header
in the installed toolchain — never a second file in the same skills repo (same repo = one
contact). Corroboration raises priority for verification; it does not raise trust: two documents
can copy the same error.

## S3 · VERIFIED(board)
The §4 procedure was run on the named board; the §5 checker went green AND its positive fixture
was shown to go red when blinded; §6 holds real readouts including the negative/poison arm; INDEX
is fully populated with re-derive commands. BOARD names exactly the boards run. A run on 910B2
verifies NOTHING about 910C: the entry stays BOARD:910B2 and §7 says so. A family claim needs the
family's ends measured, else it stays partial with the measured subset listed.

## S4 · ADMITTED
Verified, plus an independent walk (a different agent, from the entry text alone, reproduces the
procedure and verdict without contacting the author's tree). Admission is per book; nothing about
admission in one book transfers to the other.

## X · OVERTURNED
Any stratum can fall here at any time. The entry is kept in place, STRATUM rewritten, the killing
observation appended to §6, and the LOG carries the event. Deleting an overturned entry is
forbidden — a book that forgets its overturns will re-admit them.

## Hard rules
- Promotion ONLY by the named mechanism (origin count, procedure run, walk). No stratum is ever
  granted for effort, elegance, or agreement between readers.
- Demotion needs no permission — evidence outranks everything.
- The 910 book and the 950 book promote independently. The same upstream sentence spawns TWO
  harvested entries (one per book) only when it names both families; otherwise it enters the book
  it names, and the other book gets nothing.
