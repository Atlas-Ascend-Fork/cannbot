# CARD · ascendc-regbase-best-practice 006 — the knowledge tree caps a subtree read at five leaf documents

**BOOK: 950 — held as a card. A retrieval-discipline rule aimed at a consuming agent's context budget, not
at the machine. It is carded rather than dropped because it is the only place upstream states how its own
knowledge tree is meant to be consumed, and the delivered skill has to decide whether to inherit it.**

## The rule (re-verified 2026-08-24)
Stated three times, once per subtree index, in near-identical wording.

`references/knowledge/patterns/index.md:7-9`:

> - Read this index first when the task is already in the `regbase` branch and now needs a workable kernel
>   shape.
> - For one subproblem, shortlist by `purpose`, `read_when`, and `keywords`, then expand **at most 5 leaf
>   documents** from this directory.
> - If you still need more than 5 pattern notes, split the issue into smaller subproblems or move to
>   `api/`, `pitfalls/`, or `dev-experience/` instead of scanning the whole subtree.

`references/knowledge/dev-experience/index.md:7-9`, the same three bullets with "engineering judgment,
execution habits, or reference-reading advice rather than raw API lookup" in the first and the same
**at most 5** cap and the same escape ("split the question into smaller subproblems or switch to `api/`,
`patterns/`, or `pitfalls/`").

Each index also carries a routing table whose columns are `File | Purpose | Read When | Not For |
Keywords`, and a `Common Paths` list mapping a need to a file.

## Why this is worth a card at all
Three reasons, none of which is a machine claim.

**It is a designed retrieval contract and this tree's consumer is an agent.** The `Not For` column is the
unusual part: most documentation says what a file covers, and this says what it does not, which is a
negative signal a router can act on. `950:0371` records the one place that channel fails — a
compatibility case whose `Purpose` and `Keywords` columns omit its cross-branch pedigree while the
`Common Paths` line carries it — so the routing metadata is load-bearing and is not uniformly maintained.

**The cap has a consequence the tree does not acknowledge.** Five leaves is below the number this harvest
needed to establish several single claims. `950:0372` rests on four files; `950:0355` on two in different
subtrees; `950:0357` on three; `950:0353` on three plus the installed headers. An agent obeying the cap
within one subtree would not assemble any of those, because the relevant files are *distributed across*
subtrees — and the escape hatch the rule offers ("move to `api/`, `pitfalls/`, or `dev-experience/`") is a
switch, not an increase. So the cap is a per-subtree budget in a tree whose contradictions are
cross-subtree. That is an observation about this reconstruction's own experience, not a criticism the
sources make of themselves, and it is why the card exists.

**the delivered skill must decide.** The CONTRACT's transmission section is explicit that the form must stay light
and that "heavy alien ceremony displaces work". A five-leaf cap is exactly the kind of cheap, in-artifact
discipline that transmits — it lives in a file an agent opens for another reason, which is the mechanism
the CONTRACT names. Whether to carry it, drop it, or carry it with the cross-subtree caveat above is a
decision for the the delivered skill builder, and the alternatives should be on the record rather than settled by
whoever writes the index.

## Why this is a card and not an entry
No §4 exists that touches a device. A procedure could measure whether agents given a cap produce better or
worse answers than agents without one — that is a study of agents, and the parent book records that such
studies are hard to attribute (the same-input pair that diverged in 15 minutes). It is not machine
knowledge and it does not belong in a book whose stratum field is about what a device did.

The claim is also **not falsifiable in the form upstream states it**: "at most 5" is a budget, not a
prediction, so nothing observable would contradict it.

## Guessed level
None. This is a property of the documentation, not of any level in the map.

## Evidence class
bare. No measurement, no derivation, no statement of why five.

## OVERTURN sketch (if it were ever entered)
Two agent populations given the same regbase task, one capped at five leaves per subtree and one uncapped,
producing designs scored blind. If the uncapped population is not worse, the cap costs coverage and buys
nothing. Note this is a measurement of agents, and the parent book's own record is that a two-arm
comparison of differently-equipped agents attributes very little — so even this sketch should be read as
the shape of a study rather than a resolvable question.

## Disposition
Card kept. **Flagged for the the delivered skill builder** as a decision, not a finding: the five-leaf cap is a real,
transmissible retrieval discipline; it is stated per subtree; and this reconstruction's experience is that
several single claims in the 0351-0399 block required more files than the cap allows, drawn from more than
one subtree. Recorded alongside: the routing tables' `Not For` column is a useful negative channel, and
`950:0371` documents one row where its `Purpose` and `Keywords` cells omit a scope the `Common Paths` line
carries.
