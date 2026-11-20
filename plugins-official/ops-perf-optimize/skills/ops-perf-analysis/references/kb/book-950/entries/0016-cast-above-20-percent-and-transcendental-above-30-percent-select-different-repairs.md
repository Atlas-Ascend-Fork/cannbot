```
ID:        0016-cast-above-20-percent-and-transcendental-above-30-percent-select-different-repairs
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/vec.md:57-59 — "**判断规则**： - Cast 占比 >20% → 类型转换密集场景，优化 Cast 有高收益 - 超越函数占比 >30% → 深度 VEC bound，优化空间有限（转算法层减计算量）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an instruction-mix capture on a named 950 board in which a kernel above the 20% Cast
           line gains nothing from Cast removal or fusion (0021), or one below it gains
           substantially — either way the line does not select the treatment it is credited with.
```

# 0016 · Cast above 20% and transcendental above 30% select different repairs

## 1 · Claim
Upstream asserts that the VECTOR lane's events should be classified by instruction name into
four groups — arithmetic (`vec_add`/`vec_mul`/`vec_sub`, low latency), transcendental
(`vec_exp`/`vec_log`/`vec_rec`/`vec_rsqrt`, high latency and not hardware-accelerated), type
conversion (`vcvt_f2f`/`vcvt_f2s`/`vcvt_s2f`), and reduction (`vec_reduce_sum`/`vec_reduce_max`)
— and that two shares route to different repairs: Cast above 20% means conversion-dense, where
optimising Cast pays well; transcendental above 30% means deep VEC bound, where the remaining
room is small and the fix belongs at the algorithm level. Not established here.

## 2 · The wrong branch this removes
A VEC-bound verdict on its own selects no technique: the vec page lists fourteen cards. An agent
without an instruction mix picks by plausibility and usually lands on fusion, because fusion is
the most-described technique in the library. The mix is the cheap discriminator that separates
three different kernels that all look identical at the ratio level — one dominated by conversion
around a two-instruction computation, one dominated by a transcendental, one dominated by real
arithmetic. The first is fixed by removing casts and costs nothing in accuracy if the precision
standard allows; the second is not fixable at the instruction level at all; the third is where
fusion belongs. Getting this wrong is not neutral — the second case invites weeks of
micro-optimisation for a few percent.

## 3 · Ground / Source
`vec.md:46-59`, the whole VEC 内部指令分析 section: extract VECTOR-lane events from the trace,
group by `name`, and apply

> **判断规则**：
> - Cast 占比 >20% → 类型转换密集场景，优化 Cast 有高收益
> - 超越函数占比 >30% → 深度 VEC bound，优化空间有限（转算法层减计算量）

`vec.md:9` supplies the magnitude behind the first line from the card side — vec-02's diagnostic
condition repeats it and adds 计算本身只有 1–2 条指令，却夹着一进一出两次 Cast——Cast 可占总
VEC 时间 30–50%. The routing table at `vec.md:83` sends Cast >20% to vec-02 and vec-05; `:87`
sends transcendental depth (there stated as `aiv_vec_ratio` >90%) to vec-11.

Both lines are governed by `metrics.md:63` (0009): experience lines, `aiv_time` decides near
them. Note the instrument: these shares are read from the simulation trace's VECTOR-lane event
names, not from any msprof ratio column — so unlike the lane ratios, this classification
requires the simulator, which upstream elsewhere says is qualitative only (0010). That tension
is upstream's, and it is the reason the procedure below reports the mix from a trace but the
verdict from board `aiv_time`.

## 4 · Procedure
Later phase, needs a card for the verdict arm and a simulator for the mix arm.
1. Device selection per 0010; board token from the driver; occupancy either side.
2. Build a set of at least nine kernels with pre-registered instruction mixes, three per
   category: Cast-dense (a two-instruction computation wrapped in fp16→fp32→fp16), transcendental
   -dense (an exp/log chain), arithmetic-dense (a long fused-multiply chain).
3. Mix arm: capture an instruction-level trace, group VECTOR events by name into the four groups
   of `vec.md:50-55`, and record each share. Publish the grouping rule used, since the group
   membership of an unlisted opcode is our decision, not upstream's.
4. Verdict arm: apply each of the two prescribed treatments — Cast removal/fusion (0021) and the
   LUT path (0035) — to every kernel, and record board `aiv_time` before and after, five
   repetitions, median and spread.

## 5 · Checker — acceptance declared before the run
Verdict variables `cast_line_selects` and `transc_line_selects`, both declared before any run.
`cast_line_selects` is true iff every kernel with Cast share >20% gains more from Cast treatment
than from the LUT treatment, and every kernel below 20% does not. `transc_line_selects` is true
iff every kernel with transcendental share >30% gains less from micro-architectural treatment
than the Cast-dense kernels do — that is the "optimisation room is limited" half, and it is
stated as a comparison because "limited" alone is not checkable.

Exit code is not the verdict; the trace grouper exits 0 when it matches no opcode. The checker
asserts that the four groups plus an explicit `other` bucket sum to 100% of VECTOR events, and
reports the `other` share; a grouping that silently drops unmatched opcodes would inflate every
share it does compute, which is the arithmetic form of the blind-classifier species.

Red input: an arithmetic-dense kernel with no Casts at all. Its Cast share must be near zero and
its Cast treatment gain must be near zero; if the checker reports a gain there, the treatment is
doing something other than what it is named for.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. The two lines have no derivation, no shape, no board, no operator family
upstream. The instruction names quoted are upstream's examples, not an enumeration — the group
membership of any opcode not listed is undefined, and this entry does not fill that gap. The 30–50%
figure for a Cast round trip in vec-02 is a stated range with no case identity behind it. Nothing
here is evidence about the AIC side, about kernels whose casts happen inside the load/store path
(0021's after-C form, where the Cast is no longer a separate VECTOR event and the share is
therefore not comparable), or about any board.
