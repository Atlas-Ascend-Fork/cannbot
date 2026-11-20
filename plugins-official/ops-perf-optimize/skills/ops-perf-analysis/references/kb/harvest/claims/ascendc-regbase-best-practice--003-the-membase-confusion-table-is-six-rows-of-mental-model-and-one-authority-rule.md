# CARD · ascendc-regbase-best-practice 003 — the membase confusion table is six rows of mental model and one authority rule

**BOOK: 950 — held as a card in full. Zero of its six table rows carries an observable; its one substantive
claim (which document is authoritative for regbase semantics) is a documentation-governance rule, and the
disagreement it papers over is `C-950rem-002`, carried by `950:0372`.**

Third of the three files named in the controller ruling on `references/knowledge/pitfalls/`. It is the
purest instance of the "process, not machine knowledge" category in the ruling: 89 lines, no code, no
numbers, no API signatures, no failure modes.

## The file's shape (re-verified 2026-08-24)
`ascendc-regbase-best-practice/references/knowledge/pitfalls/regbase_vs_membase_confusions.md`.
Frontmatter: `platform: ascend950-regbase`, `purpose: Separate regbase-authoritative guidance from membase
compatibility habits that keep leaking into direct-invoke work.` Five sections: the most common mistaken
assumption, a six-row confusion table, how confusion shows up in practice, a recovery pattern, and safe use
of membase context.

## The one substantive claim (verbatim, `:38-41`)
> Correction:
>
> - for regbase tasks, the template is an engineering scaffold
> - regbase knowledge, whitelist, and pattern notes are the authoritative source for implementation
>   semantics

That is an authority ordering over documents: whitelist and pattern notes outrank the direct-invoke
template. It is repeated as the table's last row (`:52`): "In the regbase branch, shared regbase docs are
the authoritative guidance source. Use reference-ops only to choose an existing implementation to inspect;
it does not outrank the shared regbase docs."

## The confusion table (verbatim, `:45-52`)
> | Confusion | Why It Is Wrong | What To Do Instead |
> |---|---|---|
> | "`ascend950` and `ascend910b` are interchangeable if the math is the same." | The math may match while API families, execution assumptions, and failure modes do not. | Keep the branch regbase-first once routed there, and only treat membase as compatibility context. |
> | "I can port a membase queue flow directly and optimize later." | That changes semantics before correctness is proven. | Re-derive the compute path from regbase docs, then use the template only for project skeleton concerns. |
> | "If output is wrong, I should add more membase-style pipeline structure." | The issue may be wrong branch reasoning, wrong API choice, or unstable numerics. | First confirm API-family correctness and the first bad intermediate. |
> | "Sync advice from membase examples applies unchanged." | Regbase and membase do not share identical synchronization assumptions or abstractions. | Use regbase sync guidance and inspect non-determinism before adding arbitrary barriers. |
> | "A familiar API name means the usage contract is the same." | Similar names can hide different branch expectations and data movement assumptions. | Re-check the regbase whitelist and usage notes before implementation. |
> | "Reference-ops or default template guidance outranks shared regbase docs." | In the regbase branch, shared regbase docs are the authoritative guidance source. | Use reference-ops only to choose an existing implementation to inspect; it does not outrank the shared regbase docs. |

## Why this is a card and not an entry
No row states a machine behaviour. Row 5 comes closest — "a familiar API name may hide a different usage
contract" — and it is exactly the species `950:0250` already establishes with named evidence (thirteen
whitelist-dual-listed names), `950:0351` extends with a fourteenth (`DataCopy`), and `950:0354` quantifies
(27 unlisted, 1 listed-and-absent). So the row's content is in the book, sourced from the whitelist and the
installed headers rather than from a table of mental models, which is where the evidence is.

Row 1 is a cross-family claim that this book handles by construction: RULES.md Art. 1 already forbids inheriting
a fact between books, and the row's content ("the math may match while API families and failure modes do
not") is that law restated as advice.

Row 4's "inspect non-determinism before adding arbitrary barriers" is the same discriminator entered as
`950:0394`, and its "do not add arbitrary barriers" half is entered as `950:0358`'s narrow prohibition.

**The file's central framing is contested by its own repo, and the card must say so.** Its whole premise is
that membase constructs in a regbase design are leakage. `regbase_programming_notes.md:49-56` states the
opposite — "Real regbase kernels often still have an outer shell with `TPipe` / `TQue` / `GlobalTensor` /
`LocalTensor` … Those constructs do not automatically mean the operator has left the regbase path" — and
`regbase_kernel_dataflow_patterns.md:36-38` lists `TQue` as a component of the *canonical* regbase kernel.
That is `C-950rem-002`, carried by `950:0372`. Note this file is actually the **more careful** of the two
sides: its row 2 forbids porting a *queue flow* (the compute path) and explicitly preserves the template
"for project skeleton concerns", which is close to the programming notes' position. `regbase_operator_patterns.md`
Pattern 5 is the sharp end of the disagreement, not this file.

## Guessed level
L1 (core & pipe assignment) for rows 1-3, L4 for row 4, L8 for rows 5-6.

## Evidence class
bare, all six rows plus all five sections. No measurement, no shape, no board, no code, no API signature,
no named operator anywhere in 89 lines.

## OVERTURN sketch
For the authority rule, if it were ever entered: a case where the direct-invoke template's semantics are
correct and the regbase pattern notes' are wrong — which this block has in fact found twice, in the
opposite direction from the one the file anticipates (`950:0353`'s whitelist-versus-canonical-VF-body, and
`950:0354`'s `Reg::Divs`). Both show the "authoritative" regbase documents being wrong about the SDK. The
authority ordering is therefore not safe as stated, and its real content should be "verify in the installed
headers", which is the whitelist's own escape hatch (`950:0245`).

## Disposition
Card kept, whole. Nothing in this file is entry-worthy on its own evidence. Its one durable contribution to
the books is negative and is recorded at `950:0372` and `C-950rem-002`: the repo does not agree with itself
about what a membase construct in a regbase shell means, and an agent holding only this file will rewrite
the staging layer of a correct kernel.
