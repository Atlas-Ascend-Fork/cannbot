```
ID:        0249-reg-div-defaults-to-one-ulp-and-needs-an-explicit-mode-for-correctly-rounded-division
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). Nothing was
           compiled and no division was evaluated; the ULP figures are upstream's assertion.
BOARD:     family-claimed(unverified)
           # the whitelist names no board; it is arch35-generic regbase material and no board was
           # contacted.
SOURCE:    ops/ascendc-regbase-best-practice/references/knowledge/api/regbase_api_whitelist.md:90 —
           "> † `Reg::Div` 默认 `INTRINSIC` 模式最大 1 ULP 误差（非 IEEE-754 correctly-rounded）。
           高精度场景传 `DivSpecificMode{precisionMode=true, algo=PRECISION_0ULP_FTZ_FALSE}`
           （差值补偿算法，0 ULP，仍为 `__simd_callee__` VF-safe）。"
SOURCE:    same file:76 — the VF-safe binary row that carries the dagger: "| Binary reg compute |
           `Add`, `Sub`, `Mul`, `Div`†, `Max`, `Min`, `And`, `Or`, `Xor`, `MulAddDst`, `Mull` | Yes |
           `basic_api/interface/reg_compute/` |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `Reg::Div` on a 950 board whose default-mode result is bit-identical to the
           `PRECISION_0ULP_FTZ_FALSE` result across a sweep spanning subnormals, powers of two and
           random mantissas — the two modes would then not differ and the trap is empty.
```

# 0249 · `Reg::Div` defaults to one ULP and needs an explicit mode for correctly rounded division

## 1 · Claim
Upstream asserts that `AscendC::Reg::Div` in its default `INTRINSIC` mode carries a maximum error of
1 ULP and is **not** IEEE-754 correctly-rounded. Upstream asserts that a correctly-rounded path exists
and is reached by passing `DivSpecificMode{precisionMode=true, algo=PRECISION_0ULP_FTZ_FALSE}`, that
this uses a difference-compensation algorithm, that it achieves 0 ULP, and that it remains
`__simd_callee__` — VF-safe, so it can be called from inside a VF like the default. Not established
here: nothing was compiled and no quotient was evaluated.

## 2 · The wrong branch this removes
Division is the one arithmetic primitive an agent will assume is exact. `Add`, `Sub` and `Mul` in the
same whitelist row carry no dagger, so the row reads as a list of ordinary operations and `Div` looks
like one of them. An agent writing a reciprocal, a normalisation, or a softmax denominator uses
`Reg::Div` and inherits 1 ULP without a decision having been made.

The failure is not a wrong answer — 1 ULP is small — it is a *debugging* failure, and it is the
expensive kind. A kernel that misses its precision gate by a few ULP sends the author looking for the
usual suspects: accumulation order (0220's neighbourhood), a low-precision intermediate, a cast
placement (0267). The regbase pitfall material names this loop directly: "Blindly widening everything
to `fp32`" and "verify rounding and cast behavior assumptions before claiming 1 ULP bugs"
(`common_traps.md` §9, §10). An agent that does not know `Div` is inexact by default will widen
everything to fp32, watch the error persist because the divide is still 1 ULP, and conclude the
hardware is at fault.

The inverse branch costs throughput. `PRECISION_0ULP_FTZ_FALSE` is described as a
difference-compensation algorithm — more instructions per element, necessarily. An agent that discovers
the flag and applies it everywhere pays for exactness in every divide, including the ones inside a
tolerance that never needed it. Upstream frames it as a 高精度场景 option, not a default, and that
framing is the claim.

The third branch is the `FTZ_FALSE` in the algorithm name. It reads as a second, independent knob —
flush-to-zero disabled — bundled into the precision mode. So selecting exactness may also change
subnormal handling, which is a different property from ULP error and would show up only on inputs near
the bottom of the exponent range. Nothing upstream in this scope separates the two, and §4 is built so
they are not conflated.

## 3 · Ground / Source
`regbase_api_whitelist.md:74-90`, the VF-Function-Safe table with the dagger and its footnote — quoted
together because the dagger is the only thing linking them and a reader who copies the row loses it:

> | Family | Representative APIs | VF Function? | Primary Header Root |
> |---|---|---|---|
> | Unary reg compute | `Abs`, `Relu`, `Exp`, `Sqrt`, `Ln`, `Log`, `Log2`, `Log10`, `Neg`, `Not` | Yes | `basic_api/interface/reg_compute/` |
> | Binary reg compute | `Add`, `Sub`, `Mul`, `Div`†, `Max`, `Min`, `And`, `Or`, `Xor`, `MulAddDst`, `Mull` | Yes | `basic_api/interface/reg_compute/` |
> | Scalar reg compute | `Adds`, `Muls`, `Divs`, `Maxs`, `Mins`, `ShiftLefts`, `ShiftRights` | Yes | `basic_api/interface/reg_compute/` |
> …
>
> > † `Reg::Div` 默认 `INTRINSIC` 模式最大 1 ULP 误差（非 IEEE-754 correctly-rounded）。高精度场景传
> > `DivSpecificMode{precisionMode=true, algo=PRECISION_0ULP_FTZ_FALSE}`（差值补偿算法，0 ULP，仍为
> > `__simd_callee__` VF-safe）。

This is the only per-API numerical caveat in the whole whitelist — one dagger on one name across five
tables. That singularity is worth noticing two ways. It means the whitelist's authors judged `Div` the
one API whose default would surprise someone, which is a signal about where precision problems come
from. It also means the mechanism is fragile: the caveat travels as a footnote marker, and a table
extracted into a design document or a generated reference loses it silently. This entry exists largely
to give the caveat a home that cannot be de-daggered.

Note what the footnote does *not* say. It does not say what `INTRINSIC` mode is called in the header, or
what the other `algo` values are — `PRECISION_0ULP_FTZ_FALSE` implies at least a `FTZ_TRUE` sibling and
probably others, none named. It does not say whether the 1 ULP bound is per-element worst case or an
average, nor whether it holds across fp16, bf16 and fp32 equally. And it does not price the exact mode:
"差值补偿算法" tells you the method and not the cost.

Two adjacent sources bear on it without stating it. `Reg::Divs` — the scalar-divisor form in the row
below — carries **no** dagger, so either it is exact or its caveat was not recorded; the whitelist does
not say which, and an agent optimising `x / scalar` into `Divs` may be changing precision as well as
throughput. And `ascendc-perf-optimize`'s vec-11 card offers `Exp<expandLevel=0>` as an explicit
precision-for-speed trade, which shows the API family has a general pattern of mode parameters
governing accuracy; `Div`'s is simply the one the whitelist chose to flag.

The instruction-cost table (0266) lists `Div` under `instructions` with dtypes including
`int16`/`int32`/`int64` and `complex32` alongside the floats, and gives it a throughput model — but no
mode parameter, so the cost table cannot distinguish the two precision paths at all. A roofline built on
it prices exact division as though it were the default (0264).

## 4 · Procedure
Runnable later on `950PR`; the decisive arms are numerical and need one board.

Arm A — the default's error. Build a `__simd_vf__` calling `Reg::Div` with no mode argument over a
sweep of (numerator, denominator) pairs chosen to expose rounding: random mantissas with random
exponents, exact powers of two (where correctly-rounded division is exact and any error is diagnostic),
pairs whose true quotient sits exactly halfway between representable values, and denominators near 1.0
where relative error is most visible. Compare each result against a correctly-rounded reference computed
on the host in double precision and rounded once to the target type. Report the error distribution in
ULP — maximum and histogram, not mean; upstream's claim is a bound, and a mean cannot test a bound.

Arm B — the exact mode. Repeat Arm A with
`DivSpecificMode{precisionMode=true, algo=PRECISION_0ULP_FTZ_FALSE}` and the same inputs on the same
die in the same session. Upstream predicts 0 ULP on every pair.

Arm C — the paired difference, which is the arm that establishes the two modes are actually different
code. Compare Arm A and Arm B outputs bit-for-bit. Bit-identical results across the whole sweep would
mean the mode argument is inert on this toolkit — a finding, and one that would make the trap empty
regardless of what Arms A and B measured against the reference.

Arm D — the subnormal question, which the algorithm's name raises and the footnote does not answer. Run
both modes on denominators and numerators in the subnormal range and just above it, and record whether
results differ in *flush* behaviour as well as in ULP. `FTZ_FALSE` names flush-to-zero; a mode that
changes both exactness and subnormal handling has two effects and this arm separates them.

Arm E — the cost, which is what makes the default/exact choice actionable. Time a long independent
divide chain under each mode, identical shape, same die, same session, minimum over 50 repetitions, and
disassemble both to count emitted instructions per divide. The instruction count is the attributable
measurement; the timing is the one a team will quote.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All arms of one comparison run on one named
die in one session — a mode-versus-mode comparison across dies attributes nothing.

## 5 · Checker — acceptance declared before the run
Three verdict variables, never aggregated. An aggregate would let the exact mode's 0 ULP stand in for
the default's 1 ULP bound, and the entry's content is the *gap* between them.

`default_max_ulp` (Arm A) — pass iff ≤ 1.0 across the whole sweep. Declared now: a value **above** 1.0
overturns upstream's bound and is the more valuable outcome; a value of exactly 0.0 across the sweep
means the default is already correctly rounded on this toolkit and the footnote is stale. Neither is
reinterpreted afterwards.

`exact_max_ulp` (Arm B) — pass iff 0.0 across the whole sweep. Any non-zero value falsifies the "0 ULP"
claim for the named algorithm.

`modes_differ` (Arm C) — pass iff at least one input pair produces different bits under the two modes.
This verdict **gates** the other two: if the modes are bit-identical, Arms A and B measured one code path
twice and their verdicts are reported as `NOT ESTABLISHED` regardless of the numbers. That gate is the
design of this checker — two agreeing error measurements are exactly what a silently-ignored mode
argument produces.

`exact_mode_cost` (Arm E) — instructions per divide under each mode, plus wall time with run variance.
No pass threshold; it is the price, and a difference below variance is reported as "below variance",
never as zero.

The positive fixture, declared before the run: include in Arm A's input sweep a pair whose correctly
rounded quotient is known to be inexact in the target type and whose 1-ULP neighbours are known — for
fp32, `1.0f / 3.0f`. The harness must report a non-zero ULP error for the *reference comparison itself*
when the reference is deliberately computed in single precision instead of double. If it reports 0 ULP
there, the reference is not more accurate than the thing it is judging and every ULP figure is void.
This is the regbase pitfall material's own §10 — "Using weak reference outputs … NPU output is compared
against a reference that shares the same numerical weakness" — turned into a fixture.

Process exit code is not the verdict for any arm.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no
division was evaluated, no disassembly was inspected, and no device was contacted. The 1 ULP and 0 ULP
figures in §3 are upstream's assertions in a footnote; no header was read to confirm that
`DivSpecificMode` or `PRECISION_0ULP_FTZ_FALSE` exist under those spellings — that check is a file read
and is the cheapest open item here.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or evaluated. The entry does not establish either ULP figure, that `DivSpecificMode`
exists in the installed toolkit, or that the two modes are different code paths — Arms A-C are all open
and Arm C gates the rest. There is **no second origin**: one footnote in one upstream file, and no
installed header was consulted for it, unlike 0244 and 0246 where the toolkit answered. It does not
establish which dtypes the bound covers: upstream says nothing about fp16 versus bf16 versus fp32, and
the cost table lists integer and complex dtypes for `Div` whose rounding behaviour is a different
question entirely. It says nothing about `Reg::Divs`, the scalar-divisor sibling, which carries no
dagger and whose precision is therefore unstated rather than known-exact — an agent rewriting `Div` to
`Divs` for throughput is making an unrecorded precision change. It does not enumerate the other `algo`
values the naming implies, nor separate the ULP claim from the flush-to-zero behaviour the algorithm's
`FTZ_FALSE` suffix names; Arm D exists because those are two properties in one identifier. It does not
price the exact mode — Arm E is open — so the entry gives an agent the choice and not the basis for it.
BOARD is `family-claimed(unverified)`: the whitelist names no board, the material is arch35-generic
regbase, and no board was contacted; a result on 950PR would not establish 950DT. Finally, nothing here
addresses the cost model's inability to represent the mode at all (0266), which means a roofline will
price exact division as the default until that is fixed.
