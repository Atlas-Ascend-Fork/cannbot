```
ID:        0032-an-unrolled-loop-keeps-its-trip-count-runtime-derived
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-08-multi-accumulator-unroll.md:42 — "**循环次数绝不写死成常量**：VF 要对不同 shape 通用，trip count 必须由 shape/tiling 运行期推出。N 路展开 = 「常量步长 N + 运行期主循环界（`i+N<=loops`）+ 运行期尾段」，**不是**把循环展平成 N 条定长直线指令"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-10-small-loop-unroll.md:37 — "运行期 trip count（随 shape 变化）**不属**本卡适用范围，那类归约链请用 vec-08 的「常量步长 + 运行期循环界」"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a shape sweep on a named 950 board in which a VF with a hardcoded trip count produces
           correct results across every shape the operator admits — the rule would then be a
           style preference rather than a correctness constraint, at least for that kernel.
```

# 0032 · An unrolled loop keeps its trip count runtime-derived

## 1 · Claim
Upstream asserts a boundary between two unrolling techniques that look alike in the emitted code
and are not interchangeable. Unrolling a reduction chain means a compile-time *step* with a
runtime *bound* and a runtime tail; the trip count must be derived from shape or tiling at run
time and never written as a constant, because the VF must serve every shape. Full unrolling into
N straight-line instructions is admissible only where the trip count is itself a compile-time
constant and small (a convolution kernel width of 3, two sequence positions). Not established
here; both statements are upstream's and neither carries a measurement.

## 2 · The wrong branch this removes
The two techniques produce nearly identical code for one shape. An agent that measures a kernel
at one shape, unrolls the inner loop by writing out four instructions, and confirms a gain, has
built a kernel that is silently wrong for every shape whose count is not a multiple of four — it
drops the tail or reads past the end, and the failure appears far from the change. The dangerous
part is that the intermediate stage looks like success: correct results, better time, on the
shape in front of the developer. The rule converts a shape-dependent correctness bug into a
structural constraint that can be checked by reading the source: a literal loop bound in a VF
that serves variable shapes is a defect, independently of any measurement.

## 3 · Ground / Source
`vec-08:42`, quoted in full in SOURCE, states the positive form — constant step, runtime bound,
runtime tail — and names the anti-pattern. `vec-08:23,28` shows it in code:
`for (uint16_t i = 0; i + 4 <= aTimes; i += 4)` with the comment 循环界是运行期变量，不是常量,
followed by `for (uint16_t r = aTimes / 4 * 4; r < aTimes; r++)`.

`vec-10:37` states the boundary from the other side, and `vec-10:35` gives the admission
condition for full unrolling — 仅对**编译期常量、次数很小**的循环做；大循环全展开会爆指令
cache. `vec-10:19-26` shows the admissible case: `for (uint32_t k = 0; k < 3; ++k)` with K=3
known at compile time, flattened to three multiplies and two adds.

Second-order costs the two cards attach to over-unrolling: register count may exceed the budget
and spill (`vec-10:36`, `vec-08:45`), which is 0036's subject; and the reduction-axis tail must
be handled or constrained divisible in tiling (`vec-08:43`), which is where this rule touches the
tiling side.

## 4 · Procedure
Two arms; the first is a static check over sources and needs no device.
```bash
# Arm 1 — structural: find VF loop bounds that are literals in kernels serving variable shapes.
grep -rn "for *( *[a-z_0-9]* *[a-zA-Z_]* *= *0; *[a-zA-Z_]* *< *[0-9]\+ *;" <kernel-src-root> \
  | grep -v "constexpr\|static_assert"
```
Arm 2 (later phase, needs a card; device selection per 0010, board token from the driver): build
one reduction VF twice — (D) constant step with runtime bound and runtime tail; (H) the same
unroll factor with the trip count hardcoded to the value that suits one shape — and run both over
a shape set whose reduction lengths are deliberately not multiples of the unroll factor, plus one
that is. Compare every output element against a host reference.

## 5 · Checker — acceptance declared before the run
Verdict variable `shape_general(build)` = true iff every shape in the set matches the reference
element-for-element. Declared expectation: `shape_general(D)` true, `shape_general(H)` false on
at least the non-divisible shapes. The static arm's verdict is `literal_bounds_found`, a list of
file:line, and it is reported even when empty — an empty list is a result only if the grep was
shown to match a planted literal first.

Exit code is not the verdict. The comparison is element-wise over the full output; a reduction
that returns a scalar is compared including the tail elements' contribution, since dropping the
tail changes the sum by a small amount that a loose tolerance would absorb — the tolerance is the
dtype threshold from 0021 and no looser.

Red input: build H on a divisible shape. It must pass. If H fails everywhere, the difference
between the builds is not the trip count and the experiment says nothing about this rule.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. It does not establish the unroll factor at which instruction-cache pressure
begins, nor the register budget at which spilling starts — both are named upstream without
numbers. It does not establish that the static grep in arm 1 finds every violation; a literal
bound reached through a `constexpr` alias or a template parameter would not match, and this entry
does not claim otherwise. No board, no shape, no toolkit is implicated.
