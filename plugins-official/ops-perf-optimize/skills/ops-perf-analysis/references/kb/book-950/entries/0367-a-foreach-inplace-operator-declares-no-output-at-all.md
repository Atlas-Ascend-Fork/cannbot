```
ID:        0367-a-foreach-inplace-operator-declares-no-output-at-all
LABEL:     boundary
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice), which names two
           shipped operators as evidence. Nothing was compiled and no prototype was registered.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/patterns/inplace_operator_patterns.md:160
           — "2. **隐式 inplace（无 OUTPUT 声明）**：部分 foreach inplace 算子（如 `ForeachZeroInplace`、
           `ForeachAddListInplace`）完全不声明 `OUTPUT`，输入被原地修改。这是另一种 inplace 模式，不使用
           同名规则。"
SOURCE:    same file:164-169 — the mode table: "| `InplaceIndexAdd` | `.INPUT(var)` | `.OUTPUT(var)`
           同名 | 显式同名 | / | `InplaceMatmulAllReduceAddRmsNorm` | `.INPUT(residual)` |
           `.OUTPUT(residual)` 同名 | 显式同名 | / | `ForeachZeroInplace` | `.DYNAMIC_INPUT(x)` |
           无 OUTPUT | 隐式 inplace | / | `ForeachAddListInplace` | `.DYNAMIC_INPUT(x1)` | 无 OUTPUT |
           隐式 inplace |"
SOURCE:    same file:42-48 — the three determination conditions, none of which is "the prototype has no
           output": operator name contains `Inplace`; the requirement document declares address reuse;
           `spec.yaml` carries `aliasing: inplace_with(<input_name>)` — with the caveat that
           `generate_spec.py` defaults that field to `none` and it "不一定存在".
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `Foreach*Inplace` operator whose GEIR prototype does declare an `OUTPUT` — the two modes
           would then not be disjoint and "no output" would be a property of two named operators rather
           than of a mode; or an implicit-inplace operator whose input is NOT modified in place, which
           would make the absent output mean something else entirely.
```

# 0367 · A foreach inplace operator declares no output at all

## 1 · Claim
Upstream asserts a second inplace mode alongside the same-name rule (0364): some foreach inplace
operators declare **no `OUTPUT` whatsoever** in their GEIR prototype, and their inputs are modified in
place. Upstream asserts this is a distinct mode — 另一种 inplace 模式 — that does not use the same-name
rule. Upstream names two shipped instances, `ForeachZeroInplace` and `ForeachAddListInplace`, both taking
`.DYNAMIC_INPUT` and declaring no output, and tabulates them against two explicit-same-name operators.
Upstream asserts elsewhere in the same card that inplace determination rests on three signals — the
operator's name, the requirement document, and a `spec.yaml` `aliasing` field whose generator defaults it
to `none` — and does **not** list "the prototype declares no output" among them. Not established here:
nothing was compiled and no prototype was registered.

## 2 · The wrong branch this removes
An operator with inputs and no outputs looks broken. That is the whole trap.

An agent auditing a `REG_OP` block, or a generator validating one, applies the obvious invariant — an
operator produces something — and either flags the prototype as incomplete or adds an `OUTPUT` to
"complete" it. Adding one is the destructive edit: under 0364's rule an output that does *not* share an
input's name is an ordinary out-of-place output, so the fix allocates a buffer the operator never writes
to, and the caller now reads an uninitialised tensor while the real result sits in the input it was told
was an input. Every symptom points at the kernel.

The second branch is the detection one, and it is where this mode does the most damage to tooling. Every
detector implied by upstream's own material looks for a *positive* signal: a name collision between
`Input` and `Output` (0364), an `_out` suffix in the kernel signature (0365, already shown unreliable), an
`aliasing` field. An implicit-inplace operator has none of the three. Its `OUTPUT` list is empty, so
there is no collision to find; its kernel signature has no output parameter, so there is no suffix; and
`aliasing` describes an output, so with no outputs there is nothing for it to annotate. The only surviving
signal is the substring `Inplace` in the operator's name — a naming convention, checked by nothing.

So the determination procedure upstream states at `:42-48` has a gap it does not acknowledge: three
conditions, of which condition 3 is structurally inapplicable to this mode and condition 1 is a string
match. An agent following the card in order meets the determination rules first, the explicit same-name
mechanism second, and this mode as an aside inside the GEIR section — by which point it has already built
its mental model around outputs.

The third branch is the dynamic-input dimension, which upstream shows in its table and never discusses.
Both named instances take `.DYNAMIC_INPUT`, i.e. a tensor list. So the mode that is hardest to detect is
also the one operating on a variable number of tensors, each modified in place, with the addresses parsed
on the device (0381, 0382). A kernel that mishandles the alias there mishandles it *n* times, and *n* is
not known at compile time.

Whether `.DYNAMIC_INPUT` is a *condition* of the mode or a coincidence of the two examples is not stated,
and that matters: if implicit inplace only applies to dynamic inputs, the rule is narrow and detectable
by input kind; if it applies generally, an ordinary single-input operator may also be implicitly inplace
and nothing distinguishes it from a no-op. Upstream's two examples cannot separate those.

## 3 · Ground / Source
The mode, `inplace_operator_patterns.md:160`:

> 2. **隐式 inplace（无 OUTPUT 声明）**：部分 foreach inplace 算子（如 `ForeachZeroInplace`、
>    `ForeachAddListInplace`）完全不声明 `OUTPUT`，输入被原地修改。这是另一种 inplace 模式，不使用同名规则。

完全不声明 — declares none at all — and 不使用同名规则 — does not use the same-name rule. Two flat
statements, one sentence, inside a numbered list whose item 1 is the same-name rule that occupies the rest
of the section.

The mode table, `:164-169`:

> | 算子 | REG_OP INPUT | REG_OP OUTPUT | 模式 |
> |------|-------------|---------------|------|
> | `InplaceIndexAdd` | `.INPUT(var)` | `.OUTPUT(var)` 同名 | 显式同名 |
> | `InplaceMatmulAllReduceAddRmsNorm` | `.INPUT(residual)` | `.OUTPUT(residual)` 同名 | 显式同名 |
> | `ForeachZeroInplace` | `.DYNAMIC_INPUT(x)` | 无 OUTPUT | 隐式 inplace |
> | `ForeachAddListInplace` | `.DYNAMIC_INPUT(x1)` | 无 OUTPUT | 隐式 inplace |

Four rows, two modes, and the only structural difference the table exposes besides the missing output is
that both implicit rows take `.DYNAMIC_INPUT` while both explicit rows take `.INPUT`. The table does not
comment on that and neither does the prose.

What upstream does not supply for this mode, and supplies for the other:
- no `OpDef` counterpart. The whole section is GEIR (`REG_OP` / `_proto.h`); whether an implicit-inplace
  operator's `OpDef` also declares no `Output`, or declares one that GEIR omits, is unstated. The two
  prototype systems must agree for the explicit mode (0364 §2); nothing says what agreement means here.
- no kernel signature. `:97-106` gives full `extern "C" __global__ __aicore__` signatures for both
  explicit examples and none for either implicit one. So the parameter list an implicit-inplace kernel
  receives is not shown anywhere in this material — and it is the thing a generating agent must emit.
- no statement of how the framework knows. The explicit mode has a stated mechanism (the name collision;
  "GE 框架据此识别 inplace 语义"). For the implicit mode there is no corresponding sentence: the inputs are
  modified in place, and what makes that legal or expected is not said.
- no `InferShape` guidance. `:173` says inplace constrains only the shared address and not shape/dtype
  inference — written for the explicit mode. An operator with no declared outputs has no output shapes to
  infer, which is a different situation the sentence does not cover.

The two named operators are upstream's citations into its wider repo and are outside this harvest's
scope; they were **not** re-verified. All quoted material is `upstream/skills-dev-main` — one origin
(RULES.md Art. 3).

## 4 · Procedure
Runnable later on a named 950 board. The claim has a structural half (the prototype) and a behavioural
half (the input is modified), and they need separate arms because the first is a file read and the second
is not.

Arm A — the prototype, read rather than cited. Locate `ForeachZeroInplace` and `ForeachAddListInplace` in
the vendor's installed operator prototypes or in upstream's wider repo and record their `REG_OP` blocks
verbatim: `INPUT`/`DYNAMIC_INPUT` list, `OUTPUT` list, attributes. Do the same for their `OpDef`. This is
the arm that turns upstream's table into this book's fact and answers the `OpDef` question §3 flags. No
device.

Arm B — the behaviour. Build a minimal operator with `.DYNAMIC_INPUT` and no `OUTPUT`, whose kernel writes
a known pattern into each input tensor. Run it and read the caller's tensors back on the host. If they
hold the pattern, an input-only prototype does receive writable device memory and the mode works as
described. If they do not, the absent output means something other than in-place modification and this
entry is overturned.

Arm C — the destructive edit §2 describes. Take Arm B's operator and add a differently-named `OUTPUT`.
Run again and record: does the input still change, does the new output buffer hold the result, and does
anything warn. §2 predicts the input stops changing and the caller reads stale data with no diagnostic.
That prediction, confirmed, is the sentence the delivered skill most needs to carry.

Arm D — the dynamic-input condition. Build the same experiment with a plain `.INPUT` and no `OUTPUT`
instead of `.DYNAMIC_INPUT`. If it registers and behaves the same way, the mode is not tied to dynamic
inputs and the detection problem is wider than upstream's two examples suggest. If registration is
rejected, the mode is scoped by input kind and a detector can use that.

Arm E — the detector, run over the repository. Implement the three determination conditions from `:42-48`
and run them over every operator prototype reachable, then separately flag every prototype with zero
outputs. Report how many zero-output operators the three conditions miss. That number is the size of the
gap §2 argues exists, and it is a file-read measurement.

Device selection, for Arms B, C and D: the operator names the device index, the harness prints it back
with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and all variants of one comparison run on one named die in one session.

## 5 · Checker — acceptance declared before the run
`prototype_has_no_output` (Arm A) — true iff both named operators' `REG_OP` blocks declare zero outputs.
Pass condition **true**; a declared output is the first OVERTURN clause. Reported alongside
`opdef_has_no_output`, the same predicate for the `OpDef`, as a separate variable — the two prototype
systems may disagree and one merged verdict would hide it.

`input_modified_in_place` (Arm B) — true iff the caller's tensors hold the kernel-written pattern. Pass
condition **true**; false is the second OVERTURN clause.

`added_output_breaks_inplace` (Arm C) — true iff adding a differently-named output stops the input from
changing. Reported, not gated: upstream states no consequence, and the *class* of outcome (input
unchanged / input changed anyway / registration rejected) is what a reviewer needs.

`mode_requires_dynamic_input` (Arm D) — true iff the plain-`.INPUT` variant is rejected. Reported.
Declared in advance because both answers change what a detector can rely on.

`detector_miss_count` (Arm E) — the number of zero-output prototypes the three stated conditions fail to
classify as inplace. Reported.

The positive fixture, declared before the run: Arm B must **poison** the caller's tensors with a known
sentinel before the run, and the pass condition is that the sentinel is gone and the pattern is present.
Checking only for the pattern cannot distinguish a kernel that wrote it from a buffer that already
contained it — and a zeroed test buffer plus a `ForeachZero`-style operator is exactly the case where
those are indistinguishable. A second fixture for Arm E: the detector must be given one operator that is
unambiguously inplace by all three conditions and must classify it as such; if it does not, its miss
count is measuring a broken detector. Without both, the checker reads only "the tensors looked right",
which is the known blind species.

Process exit codes are not the verdict: Arm D expects a registration rejection that exits non-zero by
design.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No prototype was read from an
installed package, no operator built or registered, no tensor poisoned or read back, no die contacted.
The quoted passages are re-verified file reads of the upstream tree; the four operators in the mode table
are upstream's citations into a repo outside this harvest's scope and were not re-verified.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled, registered, or run. The entry does not establish that either named operator's
prototype omits `OUTPUT`, that an input-only prototype receives writable memory, or that adding an output
breaks the mode — Arms A through E are all open.

It does not establish the mode's mechanism. For the explicit mode upstream states how the framework knows
("GE 框架据此识别 inplace 语义"); for this mode it states no corresponding sentence, so what makes the
in-place write legal or expected is unknown here and this entry does not invent it.

It does not establish the `OpDef` side at all. The entire section is GEIR (`REG_OP` / `_proto.h`), and
whether an implicit-inplace operator's `OpDef` also declares no `Output` — or declares one — is unstated.
For the explicit mode the two must agree (0364); what agreement means here is open.

It does not establish the kernel signature. Upstream gives full signatures for both explicit examples and
none for either implicit one, so the parameter list a generating agent must emit for this mode is stated
nowhere in this material.

It does not establish whether `.DYNAMIC_INPUT` is a condition of the mode or a coincidence of the two
cited examples (Arm D), and it does not establish how `InferShape` behaves for an operator with no
declared outputs — `:173`'s guidance is written for the explicit mode and does not cover the case.

BOARD is `family-claimed(unverified)`: a prototype declaration is not board-dependent, the card names no
board token this book recognises, and no board was contacted.
