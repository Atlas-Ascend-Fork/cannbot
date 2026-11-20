```
ID:        0045-a2-reducesum-accepts-only-half-and-float-so-integer-counts-go-through-half
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin, a document declaring itself A2-verified; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:303 — "| ReduceSum | 仅支持 half / float（无整型） | 必须 mask → half → ReduceSum |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `ReduceSum` over an integer tensor compiles and produces correct sums on a named Atlas A2 board.
```

# 0045 · A2's ReduceSum accepts only half and float, so integer counts go through half

## 1 · Claim
Upstream asserts that on Atlas A2, `ReduceSum` supports only `half` and `float` and has no integer
form, so counting operations must convert their mask to `half` before reducing. Upstream gives the
conversion trick: `And(mask, 0x3C00)` turns a 0xFFFF mask lane into `half(1.0)`, avoiding a
`Select` plus `Duplicate` pair. Not established here.

## 2 · The wrong branch this removes
Counting how many elements satisfy a predicate is the core operation of a histogram, a binary
search over a value range, a NonZero, or a MaskedSelect. The natural implementation compares into
an integer mask and sums it. With no integer `ReduceSum`, that path does not exist, and the agent
must route the count through a floating-point representation it did not choose.

The consequence is not just an extra instruction. It imports a precision limit that has nothing to
do with the data: `half` represents integers exactly only to 2048 (0046), so a count above 2048 in
one reduction is wrong. An agent that discovers the type restriction and reaches for the obvious
`half` fix has silently bounded its subchunk size, and will not know it until counts get large.
The two facts belong together, which is why 0046 sits next to this entry and why upstream's own
table lists them adjacently.

The `And(mask, 0x3C00)` trick is worth carrying because the obvious conversion — `Select` a 1.0
against a 0.0 from a `Duplicate`d constant — costs two more instructions per subchunk in the
innermost loop of exactly the kernels that need this.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md` §6.1 "A2 硬件特性速查",
line 303: `| ReduceSum | 仅支持 half / float（无整型） | 必须 mask → half → ReduceSum |`.

The conversion trick, §3.1 向量化直方图技巧, line 159:
`| **mask → half 计数** | \`And(mask, 0x3C00)\` 将 0xFFFF→half(1.0)，省去 Select+Duplicate |
-2 指令/subchunk |`.
Bit check performed here: 0x3C00 is the IEEE half encoding of 1.0 (sign 0, exponent 01111, mantissa
0) ✓, so masking a lane of all-ones with it yields exactly 1.0 and a lane of zeros yields 0.0. The
trick is arithmetically sound as stated.

The precision limit that comes with it, line 160: "| **合理 subchunk 大小** | half ReduceSum 精确到
2048；float ReduceSum 精确到 2^24 | 精度保障 |" — carried by 0046.

Two adjacent techniques in the same section, lines 157-158, are the counting patterns this
restriction shapes: "| **累计 GE 替代 EQ** | `CompareScalar(GE, b)` 得到 `count ≥ b`，差分推导 bin
count。bin[0] = total - cum[1]，省 1 次比较 |" and "| **2-bin batch ReduceSum** | 两个 bin 共享一个
PipeBarrier：sel+reduce → alt+reduce → barrier → read both | -50% barrier |".

One origin. A different skill in the same repo,
`ops/ascendc-api-best-practices/references/api-reduce.md`, covers reduction APIs generally and was
surveyed for a contradicting dtype list; none was found, which given one origin is a consistency
observation rather than support.

## 4 · Procedure
Proposed, runnable later; not run.

1. Compile arm, no device: attempt `ReduceSum` over int16, int32 and half tensors targeting
   `__NPU_ARCH__` 2201. Record which compile. The half arm is the positive control — if it fails,
   the harness is wrong and the integer results mean nothing.
2. Header arm, read-only: `grep -Rn "ReduceSum" "$ASCEND_HOME_PATH"/*/include` for the declared
   overloads and any `static_assert` on the element type, with header path and toolkit version.
   This is where a dtype restriction would actually be enforced and is an independent origin.
3. Device arm, on a named die (occupancy before and after, no substitution), for whatever compiles:
   sum a known integer tensor and compare against an exact host sum.
4. Trick arm: verify `And(mask, 0x3C00)` on a mask of 0xFFFF and 0x0000 lanes produces exactly 1.0
   and 0.0 in half, bitwise. This is cheap and confirms the mechanism rather than the outcome.

## 5 · Checker — acceptance declared before the run
`reducesum_compiles(dtype)`: PASS for the claim iff false for int16 and int32 AND true for half.
The conjunction is the verdict; a bare compile failure is consistent with a broken build, as in
0036 §5 and 0040 §5.
`trick_exact`: PASS iff the masked half values are bitwise 1.0 and 0.0. This can go red
independently of the dtype claim and would be a finding about upstream's technique rather than
about the API.
If an integer form does compile, `sum_correct` becomes the verdict and a correct result overturns
§1 — while an *incorrect* result would mean the restriction exists but is unenforced, which is a
worse finding than the documented one and must be reported as such rather than as an overturn.
Exit code is the observation in arm 1 only.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. "A2" is a product line, not a board (0041 §7). This entry
does not establish the behaviour of other reduction APIs — `ReduceMax`, `ReduceMin`,
`WholeReduceSum` and the `Reduce` pattern family are not covered by the source. It does not
establish whether bf16 is accepted; upstream names only half and float. It does not establish
anything for A3 or A5 (0047). The precision consequence is 0046's claim, not this one's.
