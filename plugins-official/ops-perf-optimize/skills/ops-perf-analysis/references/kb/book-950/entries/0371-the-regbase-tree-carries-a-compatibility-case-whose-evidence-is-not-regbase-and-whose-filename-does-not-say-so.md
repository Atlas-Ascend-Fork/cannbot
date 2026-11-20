```
ID:        0371-the-regbase-tree-carries-a-compatibility-case-whose-evidence-is-not-regbase-and-whose-filename-does-not-say-so
LABEL:     boundary
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). The claim is about the
           document's own pedigree and routing, which the document states about itself. Nothing was
           compiled and no transpose was timed.
BOARD:     family-claimed(unverified)
           # deliberately: the case's own evidence is scoped by upstream to a compatibility context
           # this book does not cover, and no board token this book recognises is claimed for it.
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/dev-experience/small_channel_transpose_notes.md:25
           — "This note preserves a high-value compatibility case from the 910b knowledge base. The
           filename is neutral because the lesson is about the engineering pattern, but the original
           evidence and performance numbers come from a `910b / membase` implementation context."
SOURCE:    same file:36 — "This is not a regbase default pattern. It is a proven compatibility
           experience note."
SOURCE:    same file:63-71 — "## 5. How To Use This In Regbase Work / Use this note as: / - a
           compatibility reference / - a performance intuition source / - a reminder that small-shape
           transpose work may justify a special path / Do not treat it as direct proof that the same
           implementation should be copied into the regbase branch."
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/dev-experience/index.md:25 — the
           routing table row: "| [Small Channel Transpose Notes](./small_channel_transpose_notes.md) |
           preserve a specialized small-channel transpose case | transpose/layout-change with very
           small channels | default regbase skeleton design | transpose, small channel |" — the
           `Purpose` and `Keywords` columns do not name the compatibility pedigree; the `Common Paths`
           entry at `:39` does ("from 910b experience").
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an upstream revision that renames the file, or that adds the pedigree to its own routing
           table's Purpose or Keywords column — the routing gap would then be closed at the layer an
           agent actually reads. Separately: a statement anywhere upstream that the case's route IS a
           regbase default would contradict the document's own §1 and would have to be adjudicated by a
           procedure, not by preference.
```

# 0371 · The regbase tree carries a compatibility case whose evidence is not regbase, and whose filename does not say so

## 1 · Claim
Upstream asserts, about one document inside its Regbase best-practice tree, that the case it preserves
comes from a different branch: its original evidence and performance numbers come from a compatibility
implementation context, not from the register-based path the surrounding tree documents. Upstream asserts
that the document's filename is deliberately neutral, and gives the reason — the lesson is held to be
about the engineering pattern rather than about the implementation. Upstream asserts twice that the case
is not a regbase default pattern, and states the use restriction: treat it as a compatibility reference, a
performance-intuition source, and a reminder that small-shape transpose work may justify a special path —
and **not** as proof that the same implementation should be copied into the regbase branch. Not
established here: nothing was compiled and no transpose was timed.

This entry claims the **routing fact and the restriction**, which are statements about the regbase
knowledge tree. It does not claim, restate, or evaluate the case's technique or its performance numbers:
those are scoped by upstream to a family this book does not cover, and repeating them here — even as
"upstream asserts" — would import a fact across the book boundary that RULES.md Art. 1 exists to keep closed.

## 2 · The wrong branch this removes
A knowledge tree's directory structure is a scope claim, and agents read it as one.

An agent routed into `ascendc-regbase-best-practice/references/knowledge/dev-experience/` has already been
told, by the path, that what it finds there is regbase development experience. It opens a file about
transpose for small channel counts, finds a concrete technique with a stated winner and stated losers,
and has every structural reason to treat that as the regbase answer. The disclaimer is in the file's
second paragraph — which an agent reading for the technique may reach, and an agent grepping for
`transpose` may not.

The failure that produces is not "the technique is wrong". It is a **scope error with no symptom**: the
generated regbase kernel adopts a route selected on evidence from a different execution model, and it
either works (and nobody learns anything) or underperforms for reasons that will be attributed to
implementation quality. There is no test that fails. `stated preferences are not directives` is the
same discipline from the other direction — here the wrong move is treating located material as scoped
material.

**The filename is the channel that fails.** `ls` over that directory is the index an agent reads first,
and the eleven filenames there are topic labels — `regbase_build_notes`, `tiling_review_notes`,
`working_vs_failed_950_cases`, `small_channel_transpose_notes`. Ten of them are in-branch and one is not,
and nothing in the listing distinguishes them. Upstream *chose* that neutrality and said why: the lesson
is held to be pattern-level. But a filename is where scope survives being skimmed, and a pedigree stated
only in the body is a pedigree that transmits only to readers who open the file — which is the same
finding this book records for its own form: what an agent learns from `ls` must already be true.

The routing table has the same shape one layer up. `index.md:25`'s row gives Purpose, Read When, Not For
and Keywords, and none of the four mentions the compatibility pedigree; the `Common Paths` line at `:39`
does mention it ("a proven small-channel transpose compatibility case from 910b experience"). So the
information exists in the index and is in the section an agent scanning a table will skip.

The **counter-branch**: this entry is not an argument for deleting the case. Upstream's three permitted
uses are real ones, and a cross-branch case with an honest label is better material than an absent one.
The claim is that the label has to be where the reader is, and upstream states the label in the one place
it is easiest to miss.

## 3 · Ground / Source
The pedigree statement, `small_channel_transpose_notes.md:25`, which is the document's own second
paragraph:

> This note preserves a high-value compatibility case from the 910b knowledge base. The filename is
> neutral because the lesson is about the engineering pattern, but the original evidence and performance
> numbers come from a `910b / membase` implementation context.

The restriction, stated twice. `:36`:

> This is not a regbase default pattern. It is a proven compatibility experience note.

and `:63-71`:

> ## 5. How To Use This In Regbase Work
>
> Use this note as:
>
> - a compatibility reference
> - a performance intuition source
> - a reminder that small-shape transpose work may justify a special path
>
> Do not treat it as direct proof that the same implementation should be copied into the regbase branch.

That is a well-made disclosure. It names the source context, names the consequence, and forbids the
specific misuse — three things most cross-branch material omits. The defect is placement, not honesty,
and the file's own explanation of the filename choice ("the filename is neutral because the lesson is
about the engineering pattern") is where the two part company: it treats the *lesson* as the thing being
named and the *evidence* as an implementation detail of the lesson. For a reader deciding whether to
adopt a route, the evidence's context is the thing that decides.

The routing row, `index.md:25`, is quoted in SOURCE. Comparing it with the `Common Paths` line at `:39` —
"Need a proven small-channel transpose compatibility case from 910b experience:
[Small Channel Transpose Notes](./small_channel_transpose_notes.md)" — shows the pedigree present in one
representation of the same link and absent from the other. Two representations of one routing decision,
maintained separately, one carrying the scope. That is the same drift species as 0354's whitelist tables
against the header enumeration, at documentation scale.

The file's own remaining sections (`:26-62`) contain the technique, the losing alternatives with reasons,
and four practical pitfalls. **They are deliberately not quoted or summarised in this entry.** Upstream
scopes that evidence to a compatibility context outside book-950's family, and `form/CONVENTIONS.md`
routes a passage into the book whose family it names. Carrying the technique here under an "upstream
asserts" verb would put a claim sourced from another family into this book, which Art. 1 forbids ("No
entry may cite, rely on, or inherit a fact from the other book"). The correct disposition is that the
technique is not this book's material at all — not that it is this book's material at a low stratum.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

## 4 · Procedure
The claim is about a knowledge tree's routing, so most of it is settled by reading and by a controlled
retrieval test. No device is needed for any arm.

Arm A — the routing test, which is the claim. Give an agent the task "find the recommended approach for
NCHW→NHWC transpose with a very small channel count on 950" and the regbase skill's own routing entry
point, with no other context. Record which files it opens, in what order, and what it recommends. Repeat
with five independent agents. The verdict is how many recommend the case's route **without** stating its
compatibility pedigree. This is a retrieval experiment, and it is the only way to test a placement claim:
placement is about what a reader meets, so the reader has to be in the experiment.

Arm B — the filename channel, isolated. Repeat Arm A with one change: the file renamed to state its
pedigree in the slug. If the recommendation rate with an unstated pedigree drops, the filename is the
channel and upstream's neutrality choice has a measurable cost. If it does not drop, the pedigree is being
carried by the body text after all and this entry's §2 is wrong about where the failure is.

Arm C — the scope of the problem, over the tree. Enumerate every file under `ascendc-regbase-best-practice/`
and classify each as in-branch or cross-branch by its own text, then check whether its filename or its
routing-table row carries the pedigree. Report the count of cross-branch files whose filename does not.
One instance is a finding; a pattern is a different finding with a different repair (a generator, not an
edit).

Arm D — the sibling channels. For the same file set, check whether the frontmatter `platform:` field
carries the pedigree. This file's frontmatter is not quoted in SOURCE because it has no `platform:` line
at all, while its siblings do (`platform: ascend950-regbase`, `platform: common`, `platform: 950-regbase`).
Whether an absent field is a third signal or an oversight is worth recording, and it is a file read.

Arm E — a boundary check on this entry itself. Have a second reader verify that this entry states no fact
from the case's own evidence: no technique name, no API name, no performance figure, no shape. An entry
about a cross-branch document is exactly where an Art. 1 leak would enter, and the check is cheap.

## 5 · Checker — acceptance declared before the run
`unscoped_recommendation_rate` (Arm A) — of five agents, how many recommend the case's route without
stating its compatibility pedigree. Reported, not gated: there is no correct rate to declare in advance,
and the number is the measurement of the placement gap. A rate of 0/5 means the disclosure works where it
is and this entry is a documentation nicety rather than a trap.

`filename_channel_delta` (Arm B) — the difference between Arm A's rate and the renamed-file rate. Pass iff
the renamed rate is strictly lower. This is the arm that attributes the effect to the filename rather than
to the body text; without it, Arm A alone shows a gap and not its cause.

`crossbranch_unlabelled_count` (Arm C) — two integers: cross-branch files, and cross-branch files whose
filename and routing row both omit the pedigree. Reported separately, because a small ratio and a large
count point at different repairs.

`platform_field_present` (Arm D) — reported per file. Declared in advance so an absent field is recorded
as an observation rather than skipped as a non-result.

`entry_is_leak_free` (Arm E) — true iff the second reader finds no fact from the case's evidence stated in
this entry. Pass condition **true**. Declared because it is the one verdict this entry can fail on its own
terms.

The positive fixture, declared before the run: Arm A's task set must include one query whose correct
answer is an **in-branch** file (for example, a query about regbase build artifacts, answered by
`regbase_build_notes.md`), and the agents must find it. If they do not, the retrieval harness is broken
and the unscoped-recommendation rate measures the harness rather than the placement. And Arm C's
classifier must be given one file that is unambiguously in-branch and one that is this file, and must
separate them; a classifier that labels everything cross-branch produces a large count and no information.
Without both, the checker reads only "agents recommended something and some files looked cross-branch",
which is the known blind species.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No retrieval experiment was run,
no agent was given a task, no file set was classified, and no transpose was compiled or timed. The quoted
passages are re-verified file reads of the upstream tree performed during this harvest, as is the
observation that this file's frontmatter carries no `platform:` line while its siblings do.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run, and no retrieval was measured. The entry does not establish that any agent
has ever misused the case, that the filename is the channel that fails, or that other cross-branch files
exist in the tree — Arms A through E are all open.

**It establishes nothing about the transpose case's content.** The technique, its losing alternatives,
its performance numbers, and its four practical pitfalls are scoped by upstream to a compatibility
implementation context outside this book's family. They are not quoted, summarised, or evaluated here,
and this entry must not be cited as a source for any of them — that is a book-boundary rule (RULES.md Art. 1),
not a stratum question, and no verification could promote such a claim into book-950. A consumer wanting
the technique must go to the source and read its scope for itself.

It does not establish that upstream's disclosure is inadequate *in general*. The disclosure is present,
explicit, and states the forbidden use — which is more than most cross-branch material carries. The claim
is about where the label sits relative to where the reader looks, and Arm B is what would attribute the
gap to placement rather than to content.

It does not establish anything about the frontmatter convention: whether an absent `platform:` field is a
signal, an oversight, or a third state is unknown, and Arm D would only report presence, not meaning.

It says nothing about whether a small-channel transpose on 950 needs a special path at all. That is a
question for this book's own layout-transform material (0163-0165 carry what the tiling families state),
and nothing in this entry bears on it.

**§4 carries no board arm, and that is a disclosed property of the claim rather than an omission.** The
claim is about the regbase knowledge tree's routing — where a scope label sits relative to where a reader
looks — so no procedure on any die could establish or refute it; the arms are retrieval experiments and file
reads. 0353 and 0385 have documentation-shaped subjects and do carry board arms because their claims reach
code; this one does not.

BOARD is `family-claimed(unverified)`, deliberately: the case's own evidence is scoped by upstream to a
context this book does not cover, this entry claims only the routing fact, and no board was contacted.
