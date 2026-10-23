---
name: tiling-exception-coverage
description: "Exception-scenario coverage for Ascend C operator tiling UTs: a 31-item checklist with failure/degradation assertion discipline. Use when writing tiling gtest exception (negative) cases or auditing an existing tiling UT's exception coverage."
disable-model-invocation: true
---

# Tiling UT Exception-Scenario Coverage

## Scope

Applies to tiling UTs of register-mode Ascend C custom operators: the `test_tiling_gtest.cpp` pattern where gtest invokes the host-side `TilingFunc` directly.

Out of scope: TBE DSL operators; aclnn-level black-box negative cases (that is ST territory).

## Terminology

- **FAILED**: the umbrella term for expect-failure assertions; see "Assertion playbook".
- **Spec-dependent**: the scenario's legality is defined by the operator's interface specification. Illegal per spec → FAILED; legal per spec → treat as degraded success per "Assertion playbook".
- **Interception layer**: where the case is expected to be rejected, one of three — `infer` (shape/dtype inference stage), `tiling` (validation inside TilingFunc), `platform` (platform / compile_info initialization).

## Procedure

1. Read the operator interface spec (IO table), the OpDef definition, and the host-side validation/design docs → walk all 31 items: apply each A item directly; for each B item, judge whether its trigger condition hits;
2. For each hit item, write a TEST_F using its **construction recipe**, with assertions per the **expected** column and the "Assertion playbook";
3. Backfill the coverage matrix (default `exception-coverage.md`, placed in the tiling test directory; the caller may relocate it), then self-check against the "Completion criterion".

   **N/A evidence format (hard requirement, apply while writing)**: every N/A row's evidence cell must be written as —
   `N/A per spec.yaml <section>: "<quoted clause>"` or `N/A per Interface.md <section>: "<quoted clause>"`.
   The file name `spec.yaml` or `Interface.md` must appear literally with a quoted clause; citing design docs (HostTiling.md/Kernel.md/BranchRoute.md, ...),
   citing another matrix row, or giving a bare rationale (e.g. "operator has no X") does NOT count as evidence.

## A. Mandatory (10 items)

A items apply to nearly every operator; an N/A here needs correspondingly strong spec evidence.

| ID | Item | Construction recipe | Expected |
|----|------|---------------------|----------|
| A1 | dtype outside the whitelist | For each input, test one dtype outside the whitelist (e.g. only fp16/bf16 supported → pass INT32) | FAILED |
| A2 | Inconsistent dtypes across inputs | Change one input's dtype to differ from the other inputs | FAILED |
| A3 | Input/output dtype mismatch | Set the output dtype different from the input | FAILED |
| A4 | Input/output shape mismatch | Change one output dim to differ from the inferred result (e.g. last dim 64 vs 32) | FAILED |
| A5 | Broadcast rule violation | A dim whose sizes are unequal and neither is 1 | FAILED |
| A6 | attr out of range | For every numeric attr, test upper_bound+1 and lower_bound-1 (use semantic boundaries when no explicit bounds exist) | FAILED |
| A7 | attr special values | One case each of attr = 0 / negative / NaN, Inf (for float attrs) | Spec-dependent |
| A8 | Empty tensor | A dim = 0 | Spec-dependent |
| A9 | rank out of range | One case each of rank_upper_bound+1 and rank_lower_bound-1 | FAILED |
| A10 | tiling(nullptr) | Call TilingFunc directly with nullptr | FAILED |

## B. Conditional (test only when the trigger condition hits, 21 items)

| ID | Item | Trigger condition | Construction recipe | Expected |
|----|------|-------------------|---------------------|----------|
| B1 | Auxiliary-input dtype semantic error | Has index/group/mask/offset-style auxiliary inputs | Change the auxiliary input to a type other than required (e.g. requires INT64 → pass FLOAT) | FAILED |
| B2 | Fixed-dim relation broken | Aligned dims exist across inputs (e.g. detection-style boxes-scores alignment, elementwise all-inputs-equal-shape) | Break the dim equality relation | FAILED |
| B3 | Wrong layout | Layout/axis-order-sensitive operator (e.g. a (B,3,N) convention, reduction axis-order convention) | Swap/alter the layout-convention dims | FAILED |
| B4 | storageShape ≠ originShape | Supports dynamic shape / layout conversion | Tamper with the storage dim of each IO one by one | FAILED |
| B5 | Dynamic-shape unknown dims | Supports dynamic shape | Set key dims to -1/-2; legal per spec → degraded-success assertion, illegal → FAILED | Spec-dependent |
| B6 | attr contradicts shape | attr is axis-order-dependent (data_format/axes style) | Make the attr contradict the actual shape's axis order | FAILED |
| B7 | Illegal attr combination | Multiple attrs have combination/exclusion constraints | One case per opposite of each legal combination | FAILED |
| B8 | Illegal enum attr value | Has enum/string attrs | For each enum attr, test one undefined value | FAILED |
| B9 | Division by zero / zero index dim | Tiling does division or indexing internally | Set the divisor/index dim to 0 | FAILED |
| B10 | Rank violates semantics | Fixed-rank semantics (3D/4D tensor conventions) | Input rank ±1 | FAILED |
| B11 | Negative dim values | Has negative-capable params (axis/padding/stride) | Negative value legal per semantics → success assertion; illegal → FAILED | Spec-dependent |
| B12 | Hardware alignment constraint | Key dims have alignment requirements (headDim/K/N, or elementwise 32B tail-dim alignment) | Change a key dim to a non-aligned value | FAILED |
| B13 | Integer overflow | shape/attr participates in int32/int64 arithmetic | Use overflow boundaries such as INT32_MAX+1 | FAILED |
| B14 | Size exceeds hardware limit | A single dim / total size has a hardware cap | limit+1 | FAILED |
| B15 | Illegal const input value | Has const/scalar inputs (isConst=true) | One case each of const value out of range / 0 / negative | FAILED |
| B16 | Optional input missing | OpDef declares an optional input | Pass the optional tensor with an empty shape / FORMAT_NULL | Spec-dependent |
| B17 | Private format unsupported | Only public formats supported | Feed inputs FRACTAL_Z / NC1HWC0 etc. | FAILED |
| B18 | Mixed formats | Multiple formats supported | Inconsistent combinations such as ND input with NCHW output | FAILED |
| B19 | Platform configuration unsupported | Differentiated support across platforms/archs | Pass a normal shape under an unsupported arch configuration | FAILED |
| B20 | Insufficient resources | Has UB blocking / workspace computation | ubSize below the minimum block, coreNum=0 | FAILED or degraded success |
| B21 | compile_info parse failure | Uses JSON compile_info | One case each of missing field / wrong type / empty object | FAILED |

> Boundary: a negative-value case on a sign-sensitive param (axis/padding/stride) counts once, under B11 — not also under A7.

## Assertion playbook

- **Expect failure**: assert the return value ≠ `GRAPH_SUCCESS`; do not pin the concrete error code (`GRAPH_FAILED` / `PARAM_INVALID` etc. are implementation details); do not compare tilingData contents on failure paths.
- **Error-log assertion**: every expect-failure case also asserts the log output (captured via stderr redirect or the framework's log hook) contains a stable **anchor** that identifies the root cause — the param/attr name, the offending dim or dtype value, or the violated constraint's keyword (e.g. `"axis"`, `"not aligned"`). Assert substrings, never the full message text. The purpose of exception coverage is that when an exception fires, a human/agent can pinpoint the root cause from the error message — the anchor is what makes the log falsifiable against that purpose. If the log carries no usable anchor, that is a DFX defect in the operator's validation: record it in the coverage matrix and report it; do not weaken the assertion to match the deficient log.
- **Degraded success** (the spec-legal subset of A7/A8/B5/B11/B16/B20): pin only the degradation contract declared by the design docs — blockDim, tilingKey (if that path writes it), and fields the kernel reads. Do not compare fields the docs leave undefined, and leave a comment in the test recording this.
- **Interception-layer annotation**: every covered case records its expected interception layer (infer / tiling / platform) in the coverage matrix. A case intercepted at the infer stage does not count toward tiling-validation coverage — an assertion that passes without ever reaching TilingFunc is false coverage.
- Recommended: every TEST_F prints one `[case] TilingFunc returned <ret>` marker line, so entry evidence can be verified from the run log.

## Coverage matrix format

One row per checklist item:

`| ID | State (covered / N/A) | TEST_F name or N/A reason | Interception layer (infer / tiling / platform) | Log anchor |`

Log anchor applies to covered expect-failure rows only: the substring the case asserts in the log output. Degraded-success rows leave it empty.

## Completion criterion

In the coverage matrix, **every checklist item** must satisfy exactly one of two states:

1. **covered**: name at least one real `TEST_F` (in the form `TEST_F(Fixture, <name>)`, grep-able in the test file), annotated with its interception layer; expect-failure cases also name the asserted log anchor;
2. **N/A**: give the reason the item's trigger condition does not hit, quoting the exact clause **with its file name from Interface.md or spec.yaml only** — a citation of a design doc (HostTiling.md, Kernel.md, BranchRoute.md, ...) or of another matrix row does NOT satisfy this requirement (e.g. "N/A per spec.yaml boundary_conditions: rank_range [0,8] on the single input excludes rank-0 scalars").

Criterion: **all 31 items resolved one by one; every covered TEST_F name grep-hits; every covered expect-failure case names a log anchor; every N/A reason cites the exact clause in Interface.md or spec.yaml by file name (design docs or other matrix rows do not count)**. Any "looks inapplicable" item without evidence counts as unfinished.
