```
ID:        0034-compare-requires-its-count-to-occupy-a-whole-multiple-of-256-b
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-restrictions.md:118 — "**约束**：`count` 个元素所占空间必须 **256 字节对齐**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `Compare` whose count occupies a non-multiple of 256 B is shown to produce correct results across the whole count on a named DAV_2201 board.
```

# 0034 · Compare requires its count to occupy a whole multiple of 256 B

## 1 · Claim
Upstream asserts that the `Compare` API constrains its `count` argument such that the space
occupied by that many elements must be 256-byte aligned, and prescribes a padding strategy when it
is not. Not established here.

## 2 · The wrong branch this removes
`Compare` is the natural instruction for a mask-and-select pattern, and its count is the natural
place to put the row width. A row of 100 fp32 elements occupies 400 B, not a multiple of 256, and
the constraint is violated by a shape that is otherwise unremarkable — 100 is aligned to 32 B
(0021), which is the alignment rule an agent has already internalised. So the shape passes the
alignment check the agent knows about and fails a stricter one it does not.

The remedy interacts badly with the reduction hazard of 0026: padding a comparison input changes
what the comparison sees, and a padded region compared against a threshold produces mask bits that
a subsequent `ReduceSum` will count. Padding for alignment and padding safely are two problems and
upstream names only the first.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-restrictions.md` §2.1 "Compare API 256字节对齐约束",
line 118: "**约束**：`count` 个元素所占空间必须 **256 字节对齐**". Summarised at line 112:
"| **Compare 256字节对齐** | 见下文 2.1 | count 需 256B 对齐，padding 策略 |", and as a checklist
item at line 190: "- [ ] Compare API 的 count 是否满足 256 字节对齐 → 使用 padding 策略".
Routed from `ops/ascendc-api-best-practices/SKILL.md:22`: "| **Compare 256B对齐** | Compare |
[api-restrictions.md](...) | Padding 策略 |".

The 256 B here is the same quantity as the Vector repeat of 0032 and the mask ceiling of 0033 —
three appearances of one granularity, in three different guises (a repeat's coverage, a parameter's
ceiling, an API's alignment requirement). Upstream never connects them; the connection is drawn
here and is inference, not an upstream claim. It is worth drawing because it makes the number
memorable in the right unit: 256 B is what one Vector instruction touches, and APIs that must
consume whole instructions inherit it.

In element terms the constraint is 64 fp32, 128 fp16, 256 int8 — arithmetic performed here, not
upstream's, and subject to the same caution as 0033 §7.

One origin (this repo). No conflicting statement was found; as in 0004, the absence of a conflict
inside one origin is not evidence.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. One binary, count as a runtime argument, swept over fp32 counts 62, 63, 64, 65, 100, 127, 128
   — spanning the predicted boundary at 64 (256 B) and 128 (512 B) and including 100 as the
   realistic non-conforming case from §2.
3. Destination mask buffer poisoned to a recognisable pattern before each call; verify every mask
   bit against a host reference and report mismatch positions, not a count. The claim does not say
   what goes wrong, so where it goes wrong is the informative part — a tail-only corruption and a
   whole-result corruption are different failures.
4. Sweep fp16 counts 126, 127, 128, 129 to test the element-unit extrapolation of §3.

## 5 · Checker — acceptance declared before the run
Verdict variable `bad_positions(count, dtype)`.
PASS iff `bad_positions` is empty for counts whose byte span is a multiple of 256 (64, 128 fp32)
and non-empty for those that are not (62, 63, 65, 100, 127).
The pattern matters more than the count: if `bad_positions` is non-empty for conforming counts too,
the harness is wrong and no verdict is issued. That check runs first and is the gate.
Red input: empty `bad_positions` everywhere, which overturns the constraint — the likely reading
then being that the framework pads internally, which should be reported rather than treated as the
claim having been vacuous.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; no architecture stated by the source. This entry does not
establish what happens on violation — upstream states the constraint and the remedy but not the
consequence, so §1 cannot say whether the result is wrong, truncated, or faulted. It does not
establish the element counts for dtypes other than the derivation in §3. It does not establish
whether the padding strategy upstream prescribes is safe for the downstream reduction (see §2 and
0026), which is a real interaction upstream does not address. It says nothing about other
comparison APIs (`CompareScalar`, `Select`), whose constraints may differ.
