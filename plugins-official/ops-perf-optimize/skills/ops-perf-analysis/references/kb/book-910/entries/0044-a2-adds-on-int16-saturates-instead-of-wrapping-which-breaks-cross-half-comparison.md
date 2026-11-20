```
ID:        0044-a2-adds-on-int16-saturates-instead-of-wrapping-which-breaks-cross-half-comparison
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin, a document declaring itself A2-verified; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:220 — "`Adds(data, scalar)` 在溢出时**饱和到 ±32767/−32768**，不回绕"; ibid:302 — "| Adds(int16) | 饱和（非回绕） | 跨 0x8000 需 cross-half 修正 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an `Adds` on int16 data is shown to wrap modulo 2¹⁶ rather than saturate on a named Atlas A2 board.
```

# 0044 · A2's Adds on int16 saturates instead of wrapping, which breaks cross-half comparison

## 1 · Claim
Upstream asserts that on Atlas A2, `Adds(data, scalar)` on int16 saturates at +32767 / −32768 on
overflow rather than wrapping. Upstream asserts the consequence for a specific and common pattern:
`Adds(sortable, -threshold)` produces a wrong sign bit when the value and the threshold fall on
opposite sides of 0x8000, and gives a three-branch correction template. Not established here.

## 2 · The wrong branch this removes
Comparing values against a threshold by subtracting and testing the sign bit is a standard
vectorisation trick — it turns a comparison into one arithmetic op and one shift, which matters
when the comparison runs over the whole dataset per binary-search step. It is correct under
wrapping arithmetic and wrong under saturating arithmetic, and nothing in the source distinguishes
the two.

The failure is data-dependent in the worst way: it appears only when the value and the threshold
straddle 0x8000, so it depends on the *data distribution* and on which search step is running.
Early binary-search steps with a mid-range threshold are fine; a step whose threshold crosses the
boundary silently mis-classifies a subset of elements. In a TopK that means a slightly wrong
threshold, which means a slightly wrong result set — plausible output, no error, and a test with
uniformly distributed positive data may never trigger it.

C and C++ programmers carry a strong prior that integer arithmetic wraps. That prior is what makes
this a trap rather than a documented limit.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md` §4.2 "A2 Adds(int16) 饱和
问题", line 220: "`Adds(data, scalar)` 在溢出时**饱和到 ±32767/−32768**，不回绕。"
Line 222, the consequence: "**影响**：`Adds(sortable, -threshold)` 当 sortable 和 threshold 分属
0x8000 两侧时，结果符号位错误。"
The correction template, lines 226-235, verbatim:
```
if threshold == 0x8000:
    mask = ShiftRight(data, 15)         // 特判：直接用符号位
elif threshold >= 0x8000:
    mask = Adds+ShiftRight+Not          // 同半区正确
    And(mask, ShiftRight(data, 15))     // 低半区 → 不合格
else:
    mask = Adds+ShiftRight+Not
    Or(mask, ShiftRight(data, 15))      // 高半区 → 合格
```
The A2 hardware summary, line 302: `| Adds(int16) | 饱和（非回绕） | 跨 0x8000 需 cross-half 修正 |`.
The anti-pattern entry, line 353: "| `Adds(int16)` 跨 0x8000 直接比较 | 饱和而非回绕，符号位结果
错误 | 分高/低半区做 cross-half 修正 (§4.2) |".

A second consequence upstream draws, line 78, in the order-preserving transform section: "逆变换
不一定 = 正变换（如 Adds 饱和导致 VtS ≠ SortToRaw）" — the saturation makes a float-to-sortable
transform non-invertible by its own inverse, so a kernel that modifies its input in place and
restores it afterwards must implement the restoration separately rather than reusing the forward
path. That is a second, independent bug the same property causes.

The document's A2 scope and its refusal to extend to A3 are at line 5 (see 0041 §3, 0047).

## 4 · Procedure
Proposed, runnable later; not run. Saturation versus wrapping is directly observable and the
procedure is short; the value is in the sweep, not the mechanism.

1. Name the die; occupancy before and after; no substitution.
2. Direct arm: `Adds` on an int16 tensor holding {32000, 32760, 32767, −32000, −32760, −32768} with
   scalars {+100, −100}, compared element-wise against both a saturating and a wrapping host
   reference. Report which reference matches, per element — not "matches expected", since the
   entire question is which expectation is right.
3. Consequence arm: the threshold-subtraction comparison over int16 values swept across the whole
   range, with thresholds on both sides of 0x8000, against a host reference comparison. Report the
   value/threshold pairs that misclassify, so the predicted straddle pattern is confirmed or
   refuted as a pattern rather than as a count.
4. Correction arm: the three-branch template from §3, over the same sweep. Predicted: zero
   misclassifications.
5. Repeat arm 2 for int8 and int32, which upstream does not cover — saturation on one width does
   not imply it on another, and a consuming agent will want to know.

## 5 · Checker — acceptance declared before the run
`arith_mode(dtype)`: one of {saturating, wrapping, neither}, from arm 2. PASS for the claim iff
int16 is `saturating`.
Reporting three outcomes rather than a boolean is deliberate: an implementation matching neither
reference is a real possibility (undefined-on-overflow) and would be invisible to a two-way test.
`misclassified_pairs`: PASS iff non-empty in arm 3 AND empty in arm 4. Both clauses are required —
a non-empty arm 3 with a still-broken arm 4 would mean the correction template does not work, which
is a finding about upstream's fix rather than about the hardware, and must be reported separately.
`arith_mode(int8)`, `arith_mode(int32)`: reported with no declared expectation, since no source
states them.
Exit code is not the verdict; saturation is not an error condition.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. "A2" is a product line, not a board (0041 §7). This entry
does not establish the behaviour for int8, int32, or the unsigned types — §4 step 5 exists to fill
that in and currently nothing does. It does not establish whether other arithmetic APIs (`Add`,
`Muls`, `Sub`) saturate on the same widths; upstream names only `Adds`. It does not establish
anything for A3 or A5, per the source's own refusal (0047). The correction template is upstream's
and is untested here.
