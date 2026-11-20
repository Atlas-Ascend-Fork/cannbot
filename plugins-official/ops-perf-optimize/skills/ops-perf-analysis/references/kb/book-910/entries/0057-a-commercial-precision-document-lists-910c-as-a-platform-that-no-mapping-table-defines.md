```
ID:        0057-a-commercial-precision-document-lists-910c-as-a-platform-that-no-mapping-table-defines
LABEL:     boundary
LEVEL:     L7 (verification)
STRATUM:   harvested — an upstream platform list naming a part absent from the repo's own truth source; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ops-precision-standard/reference/golden/COMMERCIAL_OPS_PRECISION_DOCS.md:268-269 — "<strong>训练</strong>：<br>910A、910B2、910B3、910C及后续平台<br>" and "<strong>推理</strong>：<br>910B2、910B3、310P、310B及后续平台"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a definition of "910C" is found in upstream's product mapping table or in an installed `platform_config` INI, resolving it to a SocVersion and NpuArch.
```

# 0057 · A commercial precision document lists "910C" as a platform that no mapping table defines

## 1 · Claim
Upstream asserts a platform list for its commercial operator precision standard: for training,
910A, 910B2, 910B3, 910C and later platforms; for inference, 910B2, 910B3, 310P, 310B and later.
Upstream's self-declared product mapping table contains no row for 910C, and defines the DAV_2201
family as Ascend910B1–B4, Ascend910B2C and Ascend910_93. The term "910C" is used and nowhere
defined. Not established here.

## 2 · The wrong branch this removes
This book's operator uses the term "910C" and its own README names the book's span as "910B2 →
910C". If "910C" resolves to a real part, entries would need to say whether they cover it. If it
does not, writing it in a BOARD field would attach evidence to a name with no referent — and the
form checker accepts `910C` as a valid token, so nothing would stop it.

`form/CONVENTIONS.md` already anticipates this and rules: 910C is not defined anywhere upstream,
should be treated as probably-`910_93`/A3 vocabulary, and must never be written in a BOARD line on
upstream evidence alone. This entry supplies the evidence behind that rule and records where the
term actually occurs, so that a later reader does not rediscover the term in a real upstream file
and conclude the convention was over-cautious.

The wrong branch is therefore: seeing "910C" in an upstream document, treating it as a board, and
scoping a claim to it. The term appears — in this one place, in a platform list — and it resolves
to nothing.

Note also what the list implies if read literally: 910B2 and 910B3 appear as distinct platforms,
consistent with 0009's finding that they differ in core count, and inconsistent with any treatment
of DAV_2201 as one uniform target.

## 3 · Ground / Source
`ops/ops-precision-standard/reference/golden/COMMERCIAL_OPS_PRECISION_DOCS.md`, lines 268-269,
inside an HTML table, verbatim:
```
        - <strong>训练</strong>：<br>910A、910B2、910B3、910C及后续平台<br>
	- <strong>推理</strong>：<br>910B2、910B3、310P、310B及后续平台
```

Against upstream's truth source, `ops/npu-arch/references/npu-hardware-params.md` §0, lines 15-21 —
the complete product mapping table, quoted in 0001 — which lists Ascend910, Ascend310P1/P3/P5/P7,
Ascend910B1~B4, Ascend910B2C, Ascend910_93, Ascend310B1~B4, Ascend950DT, Ascend950PR. **No 910C.**
That table declares itself the shared truth source for the chip list (line 11: "需要修改芯片清单时
仅在此处更新").

The structural survey (`harvest/surveys/SURVEY_20260824_repo-structure.md` §3) reports that "910C"
appears twice repo-wide and is never defined. This entry re-verifies one of those two occurrences —
the one in scope for this book — and confirms it: the term appears in a platform list with no
mapping, no SocVersion and no NpuArch. The second occurrence was not located and is not claimed.

Two readings, neither established:
- 910C is a marketing or roadmap name for a part the mapping table calls something else, most
  plausibly Ascend910_93 (Atlas A3), which is `form/CONVENTIONS.md`'s working assumption.
- 910C is a part outside the repo's coverage entirely.
Nothing in scope distinguishes these, and this entry does not choose. That is the point: an
undefined term in a platform list is a gap, and the disciplined response is to record it as one
rather than to resolve it by plausibility (RULES.md Art. 7's spirit, applied to vocabulary).

Filed as `harvest/contradictions-910.md` **C-910-005** — a platform named by one upstream document
and absent from the document that declares itself the authority on the platform list.

## 4 · Procedure
Proposed, runnable later; not run. Resolving a name needs no card.

1. Read-only, no device: `grep -Rn "910C\|910_93\|Ascend910C" "$ASCEND_HOME_PATH"` (note `-R`;
   these trees symlink) across headers, `platform_config/*.ini` and any product tables. Record every
   hit with its file and what it maps to.
2. Enumerate `platform_config/*.ini` SoC names in full (this is 0012 §4 step 1 and should be run
   once for both). If an INI names 910C, its `NpuArch` field resolves the question directly.
3. If nothing resolves it, record the negative result explicitly. "Searched the installed toolkit
   for 910C and found nothing" is a durable finding that stops the question being reopened, and it
   is the likely outcome.
4. Do NOT resolve it by asking which part the team happens to own — a name's meaning is not
   established by the hardware in the room.

## 5 · Checker — acceptance declared before the run
Verdict variable `c910_resolution`: one of {resolved-to-<SocVersion>, absent-from-toolkit,
present-but-unmapped}.
This entry's claim (the term is undefined) is upheld iff `absent-from-toolkit` or
`present-but-unmapped`. It is overturned by `resolved-to-<X>`, at which point `form/CONVENTIONS.md`
should gain a board token or an explicit alias, and this book's entries can be scoped to it.
The three-way outcome is deliberate: `present-but-unmapped` (the string occurs in the toolkit but
resolves to nothing) is a different and more interesting finding than absence, and a boolean check
would collapse them.
The positive fixture: run the same search for a term known to be present and mapped —
`Ascend910_93` — and confirm the search FINDS it and reports its NpuArch. A search that returns
nothing for 910C is only informative if the same search returns something for a name that is there.
Exit code is not the verdict; `grep` exits non-zero on no match, which is the expected outcome and
not an error.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; no search performed against an installed toolkit. This entry
establishes only that one upstream document names 910C and that upstream's declared truth source
does not define it. It does not establish that 910C is Ascend910_93 — that remains
`form/CONVENTIONS.md`'s working assumption and is explicitly not adopted as a fact here. It does
not establish the second repo-wide occurrence reported by the structural survey, which was not
located. It does not establish anything about the precision standard's actual content or its
applicability to any part; only the platform list was read for this entry.
