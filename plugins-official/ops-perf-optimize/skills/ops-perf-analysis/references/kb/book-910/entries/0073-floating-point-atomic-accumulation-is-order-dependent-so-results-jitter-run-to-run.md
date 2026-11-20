```
ID:        0073-floating-point-atomic-accumulation-is-order-dependent-so-results-jitter-run-to-run
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-atomic.md:49 — "**浮点原子累加非确定**：多次搬运的累加顺序不固定 | 浮点结果 run-to-run 抖动。需要确定性结果时，改用单写者 + 显式 reduce，或用 PipeBarrier<PIPE_MTE3>/核间同步保证顺序"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  repeated launches of a multi-core float atomic accumulation over identical input produce bit-identical output on a named DAV_2201 board across hundreds of runs.
```

# 0073 · Floating-point atomic accumulation is order-dependent, so results jitter run to run

## 1 · Claim
Upstream asserts that the order in which multiple transfers accumulate into one GM address is not
fixed, so floating-point atomic accumulation produces results that vary between runs. Upstream
names two remedies: a single writer plus an explicit reduce, or ordering enforced by
`PipeBarrier<PIPE_MTE3>` or cross-core synchronisation. Not established here.

## 2 · The wrong branch this removes
Atomic accumulation is the recommended way to fuse a reduction into the DMA write (0072), and it is
correct — for integers. For floats it makes the kernel **non-deterministic by construction**,
because float addition is not associative and the summation order is not fixed.

The wrong branch is not using it; it is using it without knowing, and the cost lands on
*verification* rather than on the result:
- **A bit-exactness test against a golden reference will fail intermittently.** An agent that sees
  a comparison pass four times and fail once will look for a race in its own synchronisation. There
  is none; the non-determinism is the documented behaviour of the feature it chose.
- **A/B performance comparison becomes unsound if it uses bit-comparison as its correctness gate.**
  This book's own procedures repeatedly require "bitwise identical against the control arm" — 0021,
  0023, 0027, 0065 all do. **Any such procedure applied to a float-atomic kernel must switch to a
  tolerance and say so**, or it will report a difference that is not a difference. That is a
  constraint this entry places on the rest of the book.
- **The jitter is small and shape-dependent**, so it is largest exactly where the reduction is
  widest — many cores, many partial sums — which is where atomics are most attractive.

The remedies are not free and the entry keeps them in §1 for that reason: a single writer plus an
explicit reduce gives up the fusion that motivated the atomic, and enforcing order with barriers
serialises the writers. Determinism here is bought, not tuned.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-atomic.md` §3.2 前置条件（官方约束，易遗漏),
line 49, verbatim in full:
"| **浮点原子累加非确定**：多次搬运的累加顺序不固定 | 浮点结果 run-to-run 抖动。需要确定性结果时，
改用单写者 + 显式 reduce，或用 PipeBarrier<PIPE_MTE3>/核间同步保证顺序 |"

The checklist form, line 161: "- [ ] 浮点累加场景已评估 run-to-run 非确定性（见 §3.2）".

The dtypes this bites, from the same document's A2/A3 support table at lines 129-137: `float`,
`half` and `bfloat16_t` are all supported for `SetAtomicAdd` — so all three carry the
non-determinism, and the narrower the mantissa the larger the effect. `half` is exact only to 2048
for integer-valued sums (0046), and bf16's 7-bit mantissa is narrower still, so an accumulation
whose partial sums arrive in a different order can differ by far more than a last-place bit.

A same-family, different-mechanism precedent already in this book:
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md` documents a deterministic mode
for a different accumulation hazard (0029's neighbour, `tail_block_design.md` Q4: "使用确定性模式
（deterministic mode），反向处理并检测边界索引冲突"). So upstream is aware of the
determinism/throughput trade in the tail-handling context and offers a mechanism there; no such
mechanism is named for DMA atomics beyond the two remedies quoted.

Same repo, one origin. IEEE 754 non-associativity is general knowledge and not an upstream claim;
what upstream supplies is that the *order is not fixed on this hardware*, which is the part that
matters and the part this book cannot derive.

## 4 · Procedure
Proposed, runnable later; not run. Non-determinism is established by repetition, not by one run.

1. Name the die; record the part; occupancy before and after; no substitution. Record
   `GetCoreNumAiv()`.
2. Jitter arm: a multi-core float atomic accumulation over **identical input data**, launched 200
   times, output hashed each time. Count distinct hashes.
3. Magnitude arm: report max − min per element across the 200 runs, in absolute terms and in ULPs,
   so the jitter's size is known and not merely its existence.
4. Dtype arm: repeat for `half` and `bfloat16_t`. Predicted: jitter grows as the mantissa narrows.
   Nothing upstream states this and it is the most useful thing the run would produce.
5. Determinism arm: the single-writer-plus-explicit-reduce remedy, 200 launches, and the
   `PipeBarrier<PIPE_MTE3>` remedy likewise. Both predicted to give one distinct hash.
6. Cost arm: time all three variants, so the price of determinism is recorded alongside its
   achievement.

## 5 · Checker — acceptance declared before the run
Verdict variable `distinct_hashes(variant, dtype)` over 200 launches.
PASS (claim upheld) iff `distinct_hashes(atomic, float) > 1`.
Gate, run first: `distinct_hashes(single_writer, float)` must equal 1. If even the deterministic
variant produces varying output, the harness has an unrelated source of variation — a changing
input, an uninitialised buffer (0072's zeroing precondition) — and no verdict is issued for the
atomic arm. That control is what separates "the atomic is non-deterministic" from "this test is
non-deterministic".
`distinct_hashes == 1` for the atomic arm after 200 launches does **not** establish determinism and
is recorded as "did not bite, retained" — an absence of observed jitter over a finite sample cannot
establish an ordering guarantee, and the OVERTURN line demands hundreds of runs for exactly that
reason. Declared now so a clean sweep cannot later be narrated as a refutation.
`jitter_ulps` is reported with no pass threshold; it is a magnitude, and its dtype trend is the
deliverable.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; no architecture stated by the source. This entry does not
establish the magnitude of the jitter, which depends on core count, partial-sum count, dtype and
data range — §4 arm 3 exists to find it and no source in scope gives one. It does not establish
that the two remedies fully restore determinism, only that upstream offers them. It does not
establish whether `SetAtomicMax`/`SetAtomicMin` are order-sensitive — max and min *are*
associative, so they plausibly are not, but upstream says nothing and this book does not infer it.
It does not cover integer atomic accumulation, which is order-independent and is why §1 is
restricted to floating point.
