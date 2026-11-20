```
ID:        0353-the-canonical-vf-body-calls-the-load-by-the-spelling-its-own-whitelist-marks-kernel-side-only
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), which states both
           sides of the disagreement in two of its own files. The installed toolkit resolves the
           factual question (0351) but not this one: what a whitelist is FOR is not a header fact.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/api/regbase_api_whitelist.md:26 —
           "If an API is absent from the lists below, treat it as unavailable until you verify it in
           the installed SDK headers and update the design instead of guessing."
SOURCE:    same file:64 — "| Data movement | `DataCopy`, `DataCopyPad`, `DataCopyGather`,
           `DataCopyUnAlignPre`, `DataCopyUnAlign`, `DataCopyUnAlignPost`, `Copy` | No |
           `basic_api/interface/` |" — the `VF Function?` column reads `No`.
SOURCE:    same file:80 — "| Reg load and store | `LoadAlign`, `StoreAlign`, `LoadUnAlignPre`,
           `LoadUnAlign`, `StoreUnAlign`, `StoreUnAlignPost`, `Load`, `Store`, `Gather`, `Scatter` |
           Yes | `basic_api/interface/reg_compute/` |" — `DataCopy` is not in this row.
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/regbase_kernel_dataflow_patterns.md:102
           — inside `__VEC_SCOPE__`: "`DataCopy<float, LoadDist::DIST_NORM>(vin, inAddr + i * VL);`"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an upstream revision of the whitelist that lists a VF-safe `DataCopy` row, or a revision of
           the dataflow pattern file that uses `LoadAlign` — either removes the disagreement. A
           compile is NOT an overturn condition for this entry: 0351 already establishes that both
           names resolve, and the defect here is that one document's gate says the other document's
           code is illegal.
```

# 0353 · The canonical VF body calls the load by the spelling its own whitelist marks kernel-side-only

## 1 · Claim
Upstream asserts, in its Regbase API whitelist, a launch gate: an API absent from the tables is to be
treated as unavailable until verified in the installed headers. Upstream asserts in the same file that
`DataCopy` belongs to the ordinary kernel-side families with `VF Function? = No`, and does not list any
`DataCopy` in the VF-function-safe tables. Upstream asserts, in the same skill's canonical minimal VF
body, a call to `DataCopy<float, LoadDist::DIST_NORM>` inside `__VEC_SCOPE__`. Not established here:
nothing was compiled.

Both statements are upstream's, in one repo, so this is one origin and cannot be settled by reading
more of it (RULES.md Art. 3). This entry records the disagreement; 0351 records what the installed headers
say about the underlying call, which is a different question.

## 2 · The wrong branch this removes
The disagreement is not academic, because the whitelist is written as a *gate* and gates are obeyed.

An agent that applies the gate literally rejects the subtree's own reference implementation. The
dataflow pattern file is where a new kernel gets its shape; its VF body is the only complete one in
`knowledge/`. Running the whitelist over it flags the two load/store calls as unavailable, and the
agent's repair — substitute `LoadAlign`/`StoreAlign` — happens to be correct, but the *reason* it
believes is wrong: it thinks it fixed an illegal call, when what it did was normalise a spelling. That
matters the next time, because the same belief will reject any other document using the internal
spelling, including the vendor's own advanced-API sources.

An agent that trusts the code instead concludes the whitelist is stale and stops using it. That is the
expensive branch. The whitelist's absence rule is the single most useful procedure in this subtree —
0245 records that it worked twice during this reconstruction — and an agent that has caught it being
wrong once will discount it, exactly where it is right.

The species is worth naming because the repair is placement, not diligence. Both files are correct in
isolation: the whitelist's `DataCopy | No` row is a true statement about the kernel-side `DataCopy`
that takes `LocalTensor`; the pattern file's `DataCopy<float, LoadDist::DIST_NORM>` is a true call to
the VF-side one. What is missing is any statement that *two different functions share the name*, which
is precisely the case the whitelist's own scope rules warn about at `:45` and `:50` — and having
warned about it in the abstract, the document then omits the one instance its own sibling file uses.
0250 establishes that species over the thirteen names the whitelist dual-lists in *both* tables;
`DataCopy` is the harder case, because it is listed in one table only, so the collision is invisible
to a reader diffing the two tables against each other.

There is a third branch, and it is the one a code-generation harness takes: emit whatever the pattern
file emits, because it is the example. That produces kernels written to the spelling the vendor's own
header marks internal (0351 §3). No gate in this repo catches it — the whitelist would catch it, and
the whitelist is the document being contradicted.

## 3 · Ground / Source
The gate, `regbase_api_whitelist.md:26`:

> This file is the local launch gate for regbase direct-invoke work. It separates ordinary regbase
> kernel-side APIs from VF-function-safe APIs so design and review do not mix `LocalTensor`-style
> assumptions with `AscendC::Reg::*` reg-compute semantics. … If an API is absent from the lists
> below, treat it as unavailable until you verify it in the installed SDK headers and update the
> design instead of guessing.

The scope rules that predict the collision without naming it, `:45` and `:50`:

> - Ordinary regbase kernel-side APIs and VF-function APIs are not interchangeable, even when names
>   look similar.
> - If the same capability exists in both a kernel-side and a VF-function-safe form, verify the
>   namespace, parameter style, and mask/control contract before coding.

and the guardrail at `:102` that comes closest:

> - Check the VF-capable header first when the code path uses `RegTensor`, `MaskReg`, `LoadDist`, or
>   `StoreDist`.

That guardrail would have resolved the case — the pattern file's call carries `LoadDist` — and it is
written as advice about *reading a header*, not as an amendment to the tables. So a reader who trusts
the tables and a reader who follows the guardrail reach opposite conclusions, and the document contains
both.

The other side, `regbase_kernel_dataflow_patterns.md:94-108`, quoted in full at 0351 §3; the operative
lines are `:102` and `:106`:

> ```cpp
>         DataCopy<float, LoadDist::DIST_NORM>(vin, inAddr + i * VL);
>         …
>         DataCopy<float, StoreDist::DIST_NORM_B32>(outAddr + i * VL, vout, mask);
> ```

And the third document in the same skill, `paradigms/common/vf-programming-rules.md:15`, which uses
neither table nor code but a directive — "新代码统一走 `LoadAlign` / `StoreAlign`" — and is therefore
the only place in the repo where the two spellings are implicitly acknowledged to coexist.

Recorded as `C-950rem-001` in `harvest/contradictions-950-rem.md`. All three passages are
`upstream/skills-dev-main`: one origin. Reading more of that repo cannot settle it, and the installed
header (0351) settles the *factual* question — both names resolve — without settling this one, which
is whether the whitelist means to admit the second spelling. A document's intent is not in a header.

## 4 · Procedure
This is a documentation contradiction, so the procedure is a documentation procedure plus one compile
that makes the consequence concrete. No device is needed for the decisive arms.

Arm A — the gate applied mechanically, which is what an agent does. Write the whitelist check as a
script: extract every `AscendC::Reg::*` / `MicroAPI::*` / bare call name from a source file, look each
up in the two tables, and report unlisted names. Run it over the pattern file's VF body and over the
vendor's `asc/impl/adv_api/detail/quantization/quant/ascend_quant_per_group_l300_impl.h`. Record how
many calls the gate rejects in each. The number is the finding: it is the cost of the gate as written,
paid by every agent that obeys it.

Arm B — the repair, and whether it is behaviour-preserving. Take the pattern file's VF body verbatim,
produce a second copy with `DataCopy` replaced by `LoadAlign`/`StoreAlign`, compile both for a 3510
target, and compare outputs bit-for-bit and disassembly-for-disassembly. This is 0351's Arm B applied
to the actual disputed code rather than to a synthetic call. If they differ, the repair the whitelist
implies is not a rename and this entry becomes much more serious.

Arm C — the coverage question the gate raises and cannot answer, and which is a file read. Enumerate
every function name declared inside `namespace Reg` across
`$ASCEND_HOME_PATH/include/ascendc/basic_api/interface/reg_compute/`, and diff against the union of the
whitelist's VF-safe rows. Report the count and the list. This is `Q-950arch-17` made concrete, and its
answer decides how the delivered skill should present the tables: a small difference means the tables are a
whitelist with exceptions, a large one means they are a sample.

Arm D — the reverse direction, which nobody checks. Diff the other way: names in the whitelist's
VF-safe rows that are **not** declared anywhere under `reg_compute/`. A table that lists a name the
headers do not carry is the same defect facing the other way, and it would be silently absorbed by the
absence rule (the reader verifies the header, finds nothing, and blames the toolkit pin).

## 5 · Checker — acceptance declared before the run
`gate_rejects_count` (Arm A) — the number of calls the mechanical whitelist check rejects in each of
the two files. Reported, not gated: there is no pass value, because the question is how large the cost
is, not whether it is zero. A count of 0 in **both** files would mean the gate as written does not
actually reject the pattern file's code, which would overturn §2's first branch and is a live outcome
worth naming in advance — it would mean my reading of the tables is stricter than a real
implementation of the check.

`rename_is_behaviour_preserving` (Arm B) — pass iff bit-identical outputs **and** identical
disassembly after symbol renaming. Both clauses required, for the reason recorded at 0351 §5: a
bit-identical comparison alone cannot distinguish "same instruction" from "this input does not
discriminate", and certifying a sameness claim with an instrument that cannot see difference is the
known blind species.

`whitelist_coverage_ratio` (Arms C, D) — two integers: declared-and-unlisted, and listed-and-undeclared.
Reported. Declared in advance so the arm cannot be reported as "the whitelist looked fine": a run that
produces no numbers has not been run.

The positive fixture, declared before the run: Arm A's script must be given a control file containing
one call that is unambiguously **in** the VF-safe tables (`Reg::Exp`) and one that is unambiguously
outside any table (`Reg::NoSuchApiXyz`). It must accept the first and reject the second. If it rejects
both, it is rejecting on a parse failure rather than on the tables and every count it produced is void;
if it accepts both, it is not checking at all. Without this control the arm reads only "some names were
rejected", which is the failure species this book keeps finding.

Process exit codes are not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No script was written, no
translation unit compiled, no header enumerated, and no board contacted. The three quoted passages are
re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or enumerated. The entry does not establish which of the two upstream documents is
right, and by Art. 7 it must not: both are one origin, and a disagreement inside one repo is resolved
by a procedure, not by preferring the more official-looking file. It does not establish that a
mechanical whitelist check would in fact reject the pattern file's calls — that is Arm A, and §5 names
a zero result as a live outcome that would overturn §2's first branch.

It does not establish anything about the underlying API. Whether `Reg::DataCopy` exists, whether it is
the same call as `Reg::LoadAlign`, and whether the internal-header note makes it a risk are 0351's
claims, resting on a header read; nothing here adds to them.

It does not establish the size of the whitelist's coverage gap. Arms C and D are unrun, and
`Q-950arch-17` remains the open question — with the added note, from this entry, that the gap has two
directions and only one of them has ever been discussed.

It does not establish that this is the *only* instance. One name was examined. The whitelist's own
scope rule at `:45` implies the class is larger, and the parallel case in the SIMT documentation
(0374, 0375) suggests the same authoring pattern recurs across skills.

BOARD is `family-claimed(unverified)`: the disagreement is between two documents, neither names a board
token this book recognises, and no board was contacted.
