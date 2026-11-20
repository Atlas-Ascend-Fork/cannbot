# Entry rules — two books, one form

Short by design: this file keeps only what an agent filling or reading these books must obey.
`form/` carries the entry template, the strata definition and the naming conventions;
`GOVERNANCE.md` carries the procedures for citing, adding, promoting and appealing an entry.

Throughout these books, *upstream* denotes the document an entry's `SOURCE:` field cites —
most often an existing reference under `ops/` in this repository, or a vendor SDK header or
manual. It marks where a claim came from; it is not a judgement about that document.

## Art. 1 — Two books, one form, no leakage
There is a 910 book (`book-910/`, boards 910B2 through 910C) and a 950 book (`book-950/`, boards
950PR and 950DT). They share the form layer (`form/`) and nothing else. **No entry may cite, rely
on, or inherit a fact from the other book.** A fact wanted in both books is established twice.

## Art. 2 — Scope never exceeds evidence
Every claim names the board(s) its evidence touched (`BOARD:` in the header). A claim measured on
910B2 is *not established* on 910C — similar is not same; the books span board families precisely
because "similar" must be demonstrated per entry, never assumed. Measurement and inference are
separated at sentence level, and a sentence's scope must be covered by its measurement's scope.

## Art. 3 — Provenance before knowledge
An assertion taken from a source document enters only at the `harvested` stratum, with `SOURCE:`
quoting path and passage. "Upstream asserts X" is the strongest sentence a harvested entry may
write. Promotion is defined in `form/STRATA.md` and carried out as described in `GOVERNANCE.md`
§3. Two files of the same origin — one repository, one SDK release — count as one origin, so
their agreement is not corroboration.

## Art. 4 — Every claim carries its death
`OVERTURN:` is mandatory at every stratum: the concrete observation that would kill the claim,
stated before anyone looks for it. A claim that cannot name its overturn condition is not
admissible, at any stratum.

## Art. 5 — Checkers must be able to fail
Acceptance is declared before the run. Every checker in `tools/` ships a positive fixture — a
planted defect it must find — and its selftest fails if that fixture is not found. A selftest
that only asserts "nothing was reported" cannot detect its own blindness and is not sufficient.

## Art. 6 — Verification is separate from harvest
Harvesting and structuring entries touches no device. An entry reaches a stratum above
`harvested` only after the check named in its own §4 has been run on the named board, with the
command and the readout recorded in the entry. Nothing written at `harvested` may silently
depend on device access having happened.

## Art. 7 — Contradictions are recorded, not adjudicated by taste
When sources disagree (same topic, different advice or numbers), both versions are recorded in
`harvest/CONTRADICTIONS.md` and in the entry's §3. The disagreement is resolved only by a §4
procedure run on the named board — never by picking the more plausible author.

## Art. 8 — The consumer reads artifacts, not prefaces
Everything a consumer must obey lives in files it will actually open: entry files, filenames,
templates, `GOVERNANCE.md`. A rule that exists only in a preamble does not exist, so the form is
enforced by `tools/check_entries.sh` rather than by exhortation.

## Art. 9 — Corrections stay visible
An entry is never silently changed. A correction keeps the superseded text in the entry, dates
the change and cites the evidence that forced it; an amendment names what it amends. When a
correction changes what the claim says, the filename is updated with it, because the filename is
the index (`INDEX.md`, `ls entries/`) and a stale filename outlives the sentence it summarised.

## Art. 10 — Quote the minimum that identifies the claim
Cite `path:line-range` and quote the shortest passage a reader needs to recognise what the claim
rests on; do not reproduce whole sections, files or configuration blocks. Where the source is a
vendor SDK or manual, prefer stating the value and the path over copying the text around it.
