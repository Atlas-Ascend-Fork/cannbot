# ENTRY TEMPLATE — copy this skeleton verbatim; every slot is mandatory

An entry is one claim, one file, `entries/NNNN-<claim-shaped-slug>.md`. The slug is a sentence
fragment that states the claim ("gm-poison-does-not-survive-the-staged-copy"), never a topic
("memory-notes"). The filename is a transmission channel: an agent that only runs `ls` must
already learn something true.

**Entries are written to be imitated, and that is the point of the form.** A reader quotes these files
rather than a preamble, so every entry
is also a lesson in how to work: the seven sections in order are the reasoning path a consumer
replays (claim → the wrong branch you'd take without it → ground → how to check → declared
acceptance → what was seen → where it stops), the header voice teaches scope discipline, and §4
teaches kill-it-before-you-trust-it. Write each section so that an agent who has read three
entries starts writing its own claims this way. Never compensate with exhortation — a rule that
exists only as prose does not transmit.

---

## The header block (fenced, first thing in the file)

```
ID:        NNNN-<slug>                     # number is book-local; cross-book references write 910:NNNN / 950:NNNN
LABEL:     knowledge | trap | procedure | boundary
LEVEL:     Lx (<coarse topic level: L1 cores & pipes, L2 memory hierarchy & residency,
           L3 instructions & APIs, L4 toolchain & measurement>)
STRATUM:   harvested | corroborated | verified | admitted | overturned
           # plus one line of qualifier: what established it, or what it still lacks. See form/STRATA.md.
BOARD:     910B1 | 910B2 | 910B2C | 910B4 | 910_93 | 910C | 950PR | 950DT | family-claimed(unverified)
           # at harvested/corroborated strata: the board(s) the UPSTREAM evidence names (950PR if
           # their measurement says 950PR; family-claimed(unverified) if the source is generic or
           # silent). At verified/admitted strata: the board(s) OUR procedure actually ran on —
           # rewritten at promotion. Either way the stratum, not this field, says who measured.
SOURCE:    <upstream-relative-path>:<line-range> — "<shortest identifying quote>"
           # mandatory at harvested/corroborated strata; one line per independent origin.
           # Two files in the same repo are ONE origin.
INDEX:     means=<instrument> [re-derive: <command>]        # verified/admitted strata only;
           conditions=<pin/arch/shape/...> [re-derive: ...] # at harvested stratum write the single line:
           time=<date measured, absolute>                   #   INDEX: none — nothing measured; see SOURCE.
OVERTURN:  <the concrete observation that kills this claim>
           # mandatory at EVERY stratum, including harvested: state now what measurement would
           # falsify the upstream assertion. An entry that cannot say this is not admissible.
```

---

## The seven sections

## 1 · Claim
One claim, in one paragraph. Measurement and inference in separate sentences — never joined by
"so/because/which means" inside one sentence. The stated scope must not exceed the evidence scope:
at harvested stratum the only honest verb is "upstream asserts"; write
**"Upstream asserts X. Not established here."** and let the header's BOARD/STRATUM carry the rest.

## 2 · The wrong branch this removes
What a competent harness agent does WITHOUT this entry, and why the normal checks don't catch it.
If you cannot name the wrong branch, the entry is trivia and does not enter the book.

## 3 · Ground / Source
- harvested: the shortest passage that identifies the claim, with path and line range so a reader
  can open the original; quote what the claim rests on, not the whole section. Also list every
  other upstream place that states the same or a conflicting version (conflicts also go to
  harvest/CONTRADICTIONS.md).
- verified+: what the procedure assumes, and how each assumption is itself checked.

## 4 · Procedure
- harvested: the PROPOSED verification procedure — complete, runnable-later source and build/run
  lines, targeting the named board. Written now, run when a board is available. It must include how
  the device is selected and what the procedure refuses to assume.
- verified+: the procedure as actually run, self-contained, every value re-derived not pasted.

## 5 · Checker — acceptance declared before the run
The pass/fail predicate, stated before any readout exists. The verdict variable is named; the
process exit code is declared to be or not to be the verdict. Every checker must be able to go
red: state the input that would make it fail. A checker that reads only the lines it expects is
the known failure species — say how this one avoids it.

## 6 · Evidence
- harvested: the single line **"NOT YET RUN — no readout exists. Nothing in this file is a measurement."**
- verified+: the readouts as observed, including the poison/negative arm, including the arm that
  did not bite ("retained because it did not").

## 7 · Scope limits — what this entry does NOT establish
Mandatory, non-empty at every stratum. At minimum: the boards not touched, the shapes/regimes not
probed, and (at harvested) the fact that nothing was measured at all. A limit disclosed here is
the system working, not a defect.

---

## Promotion note
Promotion between strata edits STRATUM, INDEX, §4, §6 — never §1's scope silently. If verification
narrows or breaks the claim, the entry is corrected in place, the superseded text kept and the change dated in the entry (RULES.md Art. 9);
an overturned entry is kept, restratified `overturned`, with the killing observation in §6.
