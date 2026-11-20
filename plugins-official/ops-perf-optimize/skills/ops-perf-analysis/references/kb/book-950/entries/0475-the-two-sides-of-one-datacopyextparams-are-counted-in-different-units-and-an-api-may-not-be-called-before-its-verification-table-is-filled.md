```
ID:        0475-the-two-sides-of-one-datacopyextparams-are-counted-in-different-units-and-an-api-may-not-be-called-before-its-verification-table-is-filled
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/matmul/matmul-fusion-design-template.md:129 —
           "> **DataCopyPad 关键说明**：`curN < N` 时必须使用 `DataCopyPad + DataCopyExtParams` 显式设置
           `srcGap/dstGap`。`DataCopyExtParams` 中 **GM 侧单位为字节**，**UB 侧单位为 dataBlock（32B）**
           ——两者不可混用。"
SOURCE:    same file:87 — "**每个 Vector 侧 API 调用前，必须填写验证表**。" ; :95-100 —
           "**验证清单**（每个 API 必须完成）： / - [ ] 1. 数据布局确认（内存排列、连续性、对齐） /
           - [ ] 2. 功能需求明确（操作类型、维度、输出格式） / - [ ] 3. 已查阅官方文档（提供链接） /
           - [ ] 4. 匹配验证（数据布局与 API 能力匹配、限制条件满足） / - [ ] 5. 已记录验证过程" ;
           :121 — "**验证公式**：`正确使用 = (数据布局 ∈ API 支持范围) AND (满足所有限制条件) AND
           (无更好选择)`" ; :91 — "DataCopy 要求 32B 对齐；DataCopyPad 要求 `blockLen` 为
           dataBlock（32B）倍数"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `DataCopyPad` on a named 950 board whose `DataCopyExtParams` UB-side gap is given in
           bytes and which nevertheless lands the data where a dataBlock-unit gap would — the two
           sides would then take the same unit and the warning would have no subject. Equally: a
           `DataCopyPad` whose `blockLen` is NOT a multiple of 32 bytes and which still writes the
           partial row correctly would falsify `:91`, which contradicts `:126`'s rule that `blockLen`
           takes the effective length.
```

# 0475 · The two sides of one DataCopyExtParams are counted in different units, and an API may not be called before its verification table is filled

## 1 · Claim
Upstream asserts that whenever a tile's column count is less than the full output width, the fused
epilogue must use `DataCopyPad` with an explicit `DataCopyExtParams` carrying `srcGap`/`dstGap`.
Upstream asserts that inside that one parameter structure the two sides are counted in different
units — the GM side in **bytes**, the UB side in **dataBlocks of 32 bytes** — and that the two must not
be mixed. Upstream asserts an obligation on every vector-side API call in this family: a verification
table must be filled before the call, covering the data layout, the functional requirement, the
official documentation consulted with a link, whether the layout matches the API's capability and its
restrictions, and a record of the verification — and states it as a formula,
`正确使用 = (数据布局 ∈ API 支持范围) AND (满足所有限制条件) AND (无更好选择)`. Upstream asserts, in
the same table, that `DataCopy` requires 32-byte alignment and that `DataCopyPad` requires `blockLen`
to be a multiple of the 32-byte dataBlock. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent fills a `DataCopyExtParams` from one mental model. The structure has a
source gap and a destination gap; they are the same field kind, adjacent in the same struct, and every
other stride-carrying parameter in the corpus uses one unit throughout. Getting it wrong by a factor of
32 in one direction places every row after the first at 32 times the intended offset — which, for a
tile whose rows are hundreds of bytes apart, is far outside the buffer, and for a tile whose rows are a
few blocks apart is *inside* it, so the failure is either an obvious explosion or a quiet shear
depending on the shape.

The normal checks do not catch the quiet case. This is the tail-column path (`0471`): it is taken only
when `curN < N`, which is the shape a benchmark does not have, and its damage is confined to rows after
the first, which an aggregate error metric averages away.

The second wrong branch is the verification table itself — specifically, skipping it because it looks
like process. It is not: the table's columns are `数据布局 / 功能需求 / API选择 / 限制条件 / 匹配 /
文档`, and its final clause is `无更好选择`, no better option available. That last conjunct is the one
that cannot be checked by reading a signature, and it is the reason this family states the rule as a
formula rather than as a checklist. An agent that fills the first four and skips the fifth has verified
that the call is *legal*, not that it is *right*.

## 3 · Ground / Source
The unit split, `matmul-fusion-design-template.md:129`:

```
> **DataCopyPad 关键说明**：`curN < N` 时必须使用 `DataCopyPad + DataCopyExtParams` 显式设置 `srcGap/dstGap`。`DataCopyExtParams` 中 **GM 侧单位为字节**，**UB 侧单位为 dataBlock（32B）**——两者不可混用。
```

One sentence, three obligations: use `DataCopyPad` when the tile is narrower than the output; set the
gaps explicitly; and do not mix the units. The third is the only one with a stated hazard, and it is
the only one a compiler cannot see — both fields are integers.

**A second statement in the same table contradicts the family's own parameter rule.** `:91` gives, as
`DataCopyPad`'s restriction, `DataCopyPad 要求 `blockLen` 为 dataBlock（32B）倍数`. But the parameter
rule at `:126` (`0471`) puts `DataCopyPad blockLen` in the **effective length** column with the aligned
length explicitly excluded, and `patterns.md:93` computes it as `rowBytes = curN × sizeof(float)` for a
`curN` that is expressly not a multiple of 8 floats. Those cannot both hold: `curN = 15` floats is 60
bytes, an effective length that is not a multiple of 32. Registered as `C-950fin-019`. The whole point
of `DataCopyPad` over `DataCopy` is that it handles unaligned lengths — the API name says so — which
makes `:91`'s row the likely error, but Art. 7 forbids settling it by which reading is more plausible,
and §4 arm 2 is what would settle it.

The verification obligation, `:87` and `:95-100`:

```
**每个 Vector 侧 API 调用前，必须填写验证表**。
```

```
**验证清单**（每个 API 必须完成）：
- [ ] 1. 数据布局确认（内存排列、连续性、对齐）
- [ ] 2. 功能需求明确（操作类型、维度、输出格式）
- [ ] 3. 已查阅官方文档（提供链接）
- [ ] 4. 匹配验证（数据布局与 API 能力匹配、限制条件满足）
- [ ] 5. 已记录验证过程
```

with the formula at `:121`:

```
**验证公式**：`正确使用 = (数据布局 ∈ API 支持范围) AND (满足所有限制条件) AND (无更好选择)`
```

This is a *pre-call* obligation with a documentation-link requirement, in a corpus where the same
problem — an API called with a signature that does not exist — is recorded twice from other shelves
(`0477`, `0478`, both from the elementwise family's own reference code). So the family that states this
discipline most explicitly is on the same shelf-set as the family that violates it most visibly. The
obligation is not empty ceremony; item 3 in particular would have caught both.

The obligation's own weakness is the one this book keeps finding: nothing checks that the table was
filled. It is a `[ ]` list in a design template, satisfied by the author who also wrote the call —
the same shape as `0464`'s barrier accounting and `0474`'s sample register, and the third instance in
this family alone. Recorded as `Q-950fin-24`.

One file; the parameter rule and `patterns.md`'s `rowBytes` are two more locations in one repository —
one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved.

**Arm 1 — the unit split, isolated.** Not the fusion: one kernel that fills a UB region with a known
per-element pattern and issues one `DataCopyPad` to GM with `DataCopyExtParams`, at
`blockCount ∈ {1, 4}`, `blockLen` in bytes, and the UB-side gap given (a) in dataBlocks per upstream
and (b) in bytes. Read GM back and report, for each variant, the *observed* row pitch in bytes. The
prediction is a factor of 32 between them. This measures the unit rather than inferring it from a
correctness verdict, which is the only way to distinguish "wrong unit" from "wrong value".

**Arm 2 — `blockLen`'s alignment requirement, which is `C-950fin-019`.** The same kernel with
`blockLen ∈ {32, 60, 64, 132}` bytes — two multiples of 32 and two not. Report, per value: fault,
truncation to the next lower multiple, or the exact byte count written. If 60 writes exactly 60 bytes,
`:91` is wrong and `:126` is right; if it faults or truncates, `:91` is right and the family's own
`rowBytes = curN × sizeof(float)` is unusable at non-multiple-of-8 `curN`, which would make `0471`'s
ODD-N path unimplementable as written — a much larger finding.

**Arm 3 — the quiet shear, in situ.** The mxfp8 + Div fusion at `curN ∈ {15, 33}` with the UB-side gap
mis-specified in bytes. Report per-row agreement, not aggregate, and the row index of the first
disagreement. This is where the factor-of-32 error becomes the shape-dependent symptom §2 describes,
and the per-row index identifies it as a stride error rather than a value error.

**Arm 4 — the verification obligation, retained because it may not bite.** Take the reference
project's epilogue and, for every vector-side API call in it, check items 1–4 of the checklist against
the installed CANN headers under the stated pin (read-only, no device). Report calls whose signature or
restriction does not match. A clean result would say the obligation was honoured in the reference; a
dirty one would say the family that states the discipline does not follow it, which is what `0477` and
`0478` find one shelf over.

Refuses to assume: that a free die stays free, or that a die may be substituted; that a correct output
implies the right unit (arm 1 measures the pitch); that `DataCopyPad` accepts an unaligned `blockLen`
(arm 2 tests both readings rather than choosing); that an aggregate error metric can see a stride error
(arm 3 reports per row); that the reference epilogue's API use is correct (arm 4 checks it against
headers); that a fast copy is a correct one.

## 5 · Checker — acceptance declared before the run
Verdict `observed_row_pitch(unit)` from arm 1, in bytes, declared before the run. Acceptance for the
unit split: `pitch(dataBlock_units) / pitch(byte_units) == 32` exactly, or the byte-unit variant faults.
The OVERTURN's first half fires iff the two pitches are equal.

Verdict `blocklen_accepted(n)` from arm 2 for `n ∈ {32, 60, 64, 132}`, each ∈ {`exact`, `truncated`,
`fault`}. `C-950fin-019` resolves to `:126` if 60 and 132 are `exact`, and to `:91` otherwise. Declared
now: if it resolves to `:91`, `0471` acquires a scope limit it does not currently carry, and that
consequence is written down before the run rather than discovered as a surprise.

Verdict `first_bad_row(curN)` from arm 3.

Verdict `reference_api_mismatches` from arm 4, a list.

The exit code is not the verdict: a mis-strided copy exits 0, and at some shapes lands inside the
buffer. Guards: (1) arm 1 pre-fills GM with a sentinel and reports the pitch by locating the pattern,
not by comparing against an expected image — a comparison against an expectation cannot report a pitch
that differs from it, only that it differs; (2) **the input that makes this checker go red**:
`blockCount = 1`, where there is no second row and both unit interpretations must produce identical
output — if they differ there, the two variants change more than the gap unit and every pitch is an
artifact; (3) no point is reported without its `blockCount`, `blockLen`, both gap values as passed,
the CANN pin and the compiler command.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The unit-split sentence, the
`blockLen` restriction row, the verification checklist, the verification formula and the parameter rule
are file reads performed at drafting time. The arithmetic in §3 — that `curN = 15` floats is 60 bytes
and therefore not a multiple of 32 — is a calculation over upstream's own `rowBytes` expression and its
own example values, not an observation of any call.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish the unit split — upstream asserts it and
cites no header; the installed toolkit's `DataCopyExtParams` definition was not consulted for this
claim and arm 1 measures the behaviour rather than reading the declaration. It does not resolve
`C-950fin-019`, whether `DataCopyPad`'s `blockLen` must be a multiple of 32 bytes or takes the
effective length; both statements are upstream's, they are incompatible at the shapes this family
names, and Art. 7 leaves the resolution to §4 arm 2. It does not establish that the verification table
is ever filled or that filling it prevents anything (`Q-950fin-24`). It does not cover `DataCopy`'s
32-byte alignment requirement beyond quoting it, nor `srcGap`/`dstGap` semantics beyond their units. It
covers the mxfp8 + eltwise fusion pattern's epilogue only (`0469`); `DataCopyPad` is used differently
in the FA family (`0461`) and nothing here transfers to it. No board token appears in any quoted
passage, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would
happen. Nothing here is established for any 910-family board.
