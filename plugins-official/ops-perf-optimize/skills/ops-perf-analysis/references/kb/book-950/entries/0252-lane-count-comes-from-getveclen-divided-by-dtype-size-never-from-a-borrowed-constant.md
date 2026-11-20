```
ID:        0252-lane-count-comes-from-getveclen-divided-by-dtype-size-never-from-a-borrowed-constant
LABEL:     procedure
LEVEL:     L8 (toolchain & build)
STRATUM:   verified — §4 run on 950PR 2026-08-25, via §5's declared predicates: lane_expr_tracks_hardware
           PASS (expression predicts 64/128, ratio 2:1 in one run), borrowed_expr_diverges PASS
           (B32 constant wrong at half, ONE_BLK_SIZE wrong at both), failure_mode = correct-in-
           window PLUS a silent 64-element out-of-window write (§6). Previously corroborated
           (upstream rule + installed-header declarations, both documents).
BOARD:     950PR (measured 2026-08-25)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-03-fused-instr.md:52
           — "lane 数用 `GetVecLen()/sizeof(dtype)`，**不要借** `B32_DATA_NUM_PER_REPEAT(=64)` 或
           `ONE_BLK_SIZE/sizeof(dtype)`——换 dtype/换代会全错。"
SOURCE:    same file:29 — "uint32_t lane = GetVecLen() / sizeof(float);              // A5 fp32=64，
           不要硬编码"
SOURCE:    INSTALLED TOOLKIT (independent origin, read-only): /usr/local/Ascend/cann-9.0.0-beta.2/arm64-linux/asc/impl/adv_api/detail/quantization/quant/ascend_quant_l300_impl.h:30-31 — "constexpr uint32_t ASCENDC_QUANT_B16_VF_LEN = GetVecLen() / sizeof(uint16_t); constexpr uint32_t ASCENDC_QUANT_B32_VF_LEN = GetVecLen() / sizeof(uint32_t);"
INDEX:     GetVecLen()=256 (device echo; constexpr, sys_var_intf.h:76) · observed lanes 64/128 ·
           B32_DATA_NUM_PER_REPEAT=64, ONE_BLK_SIZE=32 (device echo) · borrowed-build overrun = 64
           halves beyond the task window · narrowed-mask fixture=8. Run 2026-08-25, Ascend950PR.
OVERTURN:  a 950 board on which `GetVecLen()/sizeof(T)` disagrees with the number of elements a
           full-mask `RegTensor<T>` store actually writes — the rule's expression would then be
           wrong even though the discipline stands.
```

# 0252 · Lane count comes from `GetVecLen()` divided by dtype size, never from a borrowed constant

## 1 · Claim
Upstream asserts that the per-iteration lane count of a Regbase VF must be computed as
`GetVecLen() / sizeof(dtype)`, and names two specific wrong sources by name: the constant
`B32_DATA_NUM_PER_REPEAT` (which is 64) and the expression `ONE_BLK_SIZE / sizeof(dtype)`. Upstream
states the reason as a scope claim — 换 dtype/换代会全错, both are wrong on a dtype change and on an
architecture change. Not established here: nothing was compiled and `GetVecLen()` was never called.

The 2026-08-24 deep-dive nominated this as its single **ADOPT AS RULE** item — a rule to take on
without verifying, because it is the correct side of a family-wide disagreement. This entry is that
adoption, generalised: the rule is not about lane counts, it is about capacity constants.

## 2 · The wrong branch this removes
The trap is that both forbidden expressions give the **right answer today**. On DAV_3510
`GetVecLen()` is 256 bytes (0219), so `GetVecLen()/sizeof(float)` is 64 — and
`B32_DATA_NUM_PER_REPEAT` is also 64. A kernel written either way passes every fp32 test on this
architecture. There is no signal at all.

The divergence arrives on a change the author did not make. Template the kernel on `half` and the
correct expression yields 128 while the borrowed constant still yields 64: the loop processes half the
data per pass, and whether the remainder is silently dropped or read out of bounds depends on whether
the mask was derived from the same constant. Change architecture and the correct expression tracks while
the constant does not.

`ONE_BLK_SIZE / sizeof(dtype)` is the worse of the two because it is *dimensionally* plausible — it
looks like exactly this rule with a different capacity — and it is a different capacity. A block is the
32-byte UB granularity (0219's `ubblock_size=32`); a vector register is 256 bytes. The expression yields
8 for fp32 rather than 64, an eightfold error, and it will look like a deliberate choice to any reviewer
who does not know both constants.

The generalisation is the part worth carrying. Every capacity in this architecture has an accessor and a
tempting literal that agrees with it on the machine in front of you: UB has `GetCoreMemSize(UB)` against
`248 * 1024` (0207, 0209), core count has `GetCoreNumAiv()` against `64` (0216, 0217), VL has
`GetVecLen()` against `256`. The upstream card libraries hardcode four UB values and five core counts
across one subtree (C-006, C-007), all of which were right somewhere. So this is not one card's advice —
it is the discipline that C-006 and C-007 are the cost of not having.

## 3 · Ground / Source
`vec-03-fused-instr.md:49-55`, the 红线 block, with the neighbouring rules kept because the lane rule is
one of a set and the set is what a reader scans:

> ## 红线（Stop rules）
>
> - `MulDstAdd(dst, src1, src2, mask)` 语义 = `dst = dst*src1 + src2`（dst 既是源又是目标）。
>   **替换前比对 ground truth 的参数顺序**：weight 走 src1、bias 走 src2；写反得到 `x*b+w`，静默编译通过
>   但精度错。
> - lane 数用 `GetVecLen()/sizeof(dtype)`，**不要借** `B32_DATA_NUM_PER_REPEAT(=64)` 或
>   `ONE_BLK_SIZE/sizeof(dtype)`——换 dtype/换代会全错。
> - 入参用裸 `__ubuf__ T*`，**不要用 LocalTensor**（封装会阻止 RegTensor 寄存器分配）。
> - VF 段后该有的 `PipeBarrier<PIPE_V>()` 要保留——VF 内部不替你做同步。
> - 尾段单次 lane < 32 的短向量不值得改（VF 启动有固定开销）。

and the worked line, `:29`, which shows the rule applied and carries its own note:

```cpp
    uint32_t lane = GetVecLen() / sizeof(float);              // A5 fp32=64，不要硬编码
```

The comment is doing something careful: it records the value the expression takes on A5 fp32 *and*
forbids writing that value down. That is the shape a capacity constant should be documented in, and it
is worth imitating — the number is there so a reader can sanity-check, and it is marked as an output
rather than an input.

`vec-03` is the card whose evidence is weakest in the library — its performance figure is an external,
disclaimed −40 % — and yet its stop rules are the sharpest in it. Two of the five have become entries in
this book on their own evidence (0247, 0259). That asymmetry between a card's *measurement* and its
*rules* is worth noting: the rules are compile-and-correctness knowledge and did not need the
measurement.

**The same repo breaks this rule in its canonical VF template.**
`ascendc-regbase-best-practice/references/paradigms/common/vf-programming-rules.md:98`:

```cpp
constexpr uint32_t kRepF32 = 256 / sizeof(float);  // = 64
```

That is the forbidden shape with the capacity written as a literal `256` rather than borrowed from
another constant — arguably worse, since it hardcodes VL itself. Carried as 0253, and it is the reason
this rule enters as a rule: an agent that learned by imitating the regbase template would learn the
wrong habit, and only the perf-optimize card states the discipline. The two libraries have essentially
no coupling (the 2026-08-24 deep-dive measured one shared line ≥40 characters between them), so neither
sees the other's version.

What upstream does not supply: `GetVecLen()`'s declaring header, its return type, or whether it is
`constexpr`. The last matters — if it is not a compile-time constant, `kRepF32` cannot be `constexpr`
and the fix is not a substitution. §4 Arm A is a file read and settles it.

## 4 · Procedure
Runnable later on `950PR`; the decisive arm needs no device.

Arm A — the accessor's nature, file read only. Locate `GetVecLen()` in the installed toolkit's
`reg_compute/` headers and record its declaration: namespace, return type, and whether it is `constexpr`
or `__simd_callee__`.

```bash
grep -RIn "GetVecLen" "$ASCEND_HOME_PATH/include/ascendc/basic_api/interface/reg_compute/"
```

`grep -R`, not `-r` — symlink farms. This arm decides whether the rule is even expressible in a
`constexpr` and therefore whether 0253's template can be fixed by substitution or needs restructuring.

Arm B — the value, in a VF. Evaluate `GetVecLen()` and store it as a raw integer beside `sizeof(float)`
so the readout shows 256/4 rather than handing over 64 (0219 Arm A; the two entries share one run
deliberately).

Arm C — the equality that matters. Compare `GetVecLen()/sizeof(T)` against the number of elements a
full-mask `RegTensor<T>` store actually writes into a poisoned UB region, for `float` and for `half`.
The rule is only correct if the expression predicts the observed lane count; two dtypes, because one
cannot distinguish "the expression is right" from "64 happens to be right".

Arm D — the forbidden expressions, made observable. In the same kernel, compute all three —
`GetVecLen()/sizeof(T)`, `B32_DATA_NUM_PER_REPEAT`, `ONE_BLK_SIZE/sizeof(T)` — and store all three for
`float` and `half`. Under this entry the first tracks the observed lane count at both dtypes, the second
is right at fp32 and wrong at half, and the third is wrong at both. This arm produces the table that
makes the rule teachable rather than assertable, and it costs nothing beyond Arm C.

Arm E — the consequence, which is the only arm that shows the failure rather than the discrepancy. Build
one elementwise VF twice at `half`, once with each lane expression, and compare output buffers against a
host reference. The borrowed-constant build should leave half the elements unwritten or write a wrong
tail; recording *which* is the finding, because "drops the tail" and "writes out of bounds" call for
different repairs.

Device selection is explicit for Arms B-E: the operator names the device index, the probe prints it back
with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All dtypes of one comparison run on one named
die in one session.

**As-run notes (2026-08-25, before the promoting evaluation of §6).** Arm A resolved OFF the
sketched path: `GetVecLen()` is not declared under `reg_compute/` — it lives at
`asc/include/basic_api/kernel_operator_sys_var_intf.h:76` (9.1.0), namespace `AscendC` (not
`Reg::`), declared `__aicore__ inline constexpr uint32_t`, returning `VECTOR_REG_WIDTH` (= 256 in
every per-arch block of `kernel_utils_constants.h`); a host-side compile probe additionally proved
`constexpr uint32_t lanes = GetVecLen()/sizeof(float)` is well-formed (Q-950arch-15 → the
substitution is legal). CAUTION recorded at the time: a namespace-scope `static_assert` on
`GetVecLen()` evaluates the HOST pass of the -xasc TU (where `__NPU_ARCH__` is undefined and the
function returns 0) — the first such probe printed a false "≠256" and was caught before use;
device-side echo is the meaningful carrier. Arms B/C/D ran in one regbase `__VEC_SCOPE__` kernel
(shared with 0219's run, as §4 intends): device echo 256; observed full-mask store extents 64
(fp32) / 128 (half); constants echoed device-side (B32_DATA_NUM_PER_REPEAT=64, ONE_BLK_SIZE=32).
Arm E ran twice: the first instrument used ONE sentinel for both the source tail and the
destination poison, so an out-of-window write of tail values was invisible ("beyond=0" was
blindness, not cleanliness — self-reported); the re-run with distinct sentinels (src tail 0xDEAD
vs poison 0xFBFF) is the readout of record. VF detail forced by the compiler: the loop induction
variable inside `__VEC_SCOPE__` must be `uint16_t` (hard error otherwise) — the borrowed-constant
loop was written accordingly. The §5 positive fixture ran as declared (remaining=8 → 8 written).

## 5 · Checker — acceptance declared before the run
Verdict variable `lane_expr_tracks_hardware`, from Arm C, evaluated per dtype and requiring both in one
predicate: pass iff `GetVecLen()/sizeof(float)` equals the observed float lane count **and**
`GetVecLen()/sizeof(half)` equals the observed half lane count, **and** the two observed counts stand in
a 2:1 ratio. The ratio clause is not decoration — it is what distinguishes a correct expression from two
independent coincidences, and 64 is a number this architecture produces from several unrelated
quantities.

`borrowed_expr_diverges` (Arm D) — pass iff `B32_DATA_NUM_PER_REPEAT` differs from the observed lane
count at `half`, **and** `ONE_BLK_SIZE/sizeof(T)` differs at both dtypes. This verdict is the entry's
actual content: if the forbidden expressions never diverge on any dtype this toolkit supports, the rule
is prudence rather than a correctness requirement, and the delivered skill should say so. Declaring that now
prevents a null result reading as vindication.

`failure_mode` (Arm E) — reported, not gated: whether the borrowed-constant build drops a tail, writes
out of bounds, or produces correct output. "Correct output" is a real possible outcome — a well-written
mask can absorb a wrong lane count at the cost of throughput only — and it would relocate this rule from
correctness to performance.

The positive fixture, declared before the run: run Arm C with the mask narrowed via `UpdateMask` to a
remaining count of 8. The observed lane count must become 8 while `GetVecLen()/sizeof(T)` stays 64, and
`lane_expr_tracks_hardware` must therefore go **false**. If the checker still passes, it is comparing the
expression against itself rather than against a store, and every pass it issued is void. Without this it
reads only "two numbers agreed", which is the known blind species.

Process exit code is not the verdict for any arm.

## 6 · Evidence
RUN 2026-08-25 — all five arms plus the declared positive fixture. 2026-08-25 direct-launch probes, Ascend950PR, bound pin CANN 9.1.0 build 20260730_231653901, `-xasc --npu-arch=dav-3510`; probe sources and full logs with the verification run.

- **Arm A (file read + compile)**: `GetVecLen()` is NOT under `reg_compute/` — it is
  `asc/include/basic_api/kernel_operator_sys_var_intf.h:76`, namespace `AscendC`, declared
  `__aicore__ inline constexpr uint32_t`, returning `VECTOR_REG_WIDTH` (256 in every per-arch block
  of `kernel_utils_constants.h`). A host-side probe compiled
  `constexpr uint32_t lanes = GetVecLen()/sizeof(float)` — the substitution is LEGAL
  (`Q-950arch-15` answered), so 0253's template literal is avoidable, not forced.
- **Arm B**: device echo **256**, stored raw beside sizeof (256/4, 256/2).
- **Arm C**: observed full-mask store extents **64** (fp32) and **128** (half); the expression
  `GetVecLen()/sizeof(T)` predicts both, and the two observed counts stand in the required 2:1
  ratio in one run. `lane_expr_tracks_hardware` = PASS.
- **Arm D**: device-side echo of the forbidden constants beside the observed counts —
  `B32_DATA_NUM_PER_REPEAT` = 64 (right at fp32, WRONG at half: 64 ≠ 128);
  `ONE_BLK_SIZE` = 32 → `/sizeof(T)` = 8 (fp32) and 16 (half), wrong at BOTH dtypes.
  `borrowed_expr_diverges` = PASS — the rule is a correctness requirement, not prudence.
- **Arm E (`failure_mode`)**: the borrowed-kRep=64 build at half over a 128-element task produced
  a THIRD outcome the arm's declared dichotomy did not name: **correct output inside the task
  window AND a silent 64-element write beyond it** (each store moves a full 128-half VL; the
  second iteration's store lands half out-of-window). First instrument iteration used ONE sentinel
  for the source tail and the destination poison, making the out-of-window write invisible
  ("beyond=0" was blindness, self-reported before use); the re-run with distinct sentinels
  (src tail 0xDEAD vs poison 0xFBFF) showed **64 src-tail sentinels in the overrun zone**. So the
  borrowed constant does not merely waste throughput — it corrupts whatever sits after the
  destination window, silently.
- **Positive fixture, as declared**: `UpdateMask<float>` remaining=8 → exactly 8 written while the
  expression stays 64 — the checker's comparison is live.

Toolchain constraint recorded during the run: the loop induction variable inside `__VEC_SCOPE__`
must be `uint16_t` (hard compiler error otherwise).

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish that `GetVecLen()` exists under that spelling, its
return type, or whether it is usable in a `constexpr` — Arm A is open and it gates whether 0253's
template is fixable by substitution. It does not establish that the expression predicts the hardware
lane count (Arm C), nor that the forbidden expressions actually diverge on any dtype this toolkit
supports (Arm D) — and §5 declares in advance that a null result there demotes the rule from correctness
to prudence. It does not establish the failure mode of a wrong lane count; Arm E exists because "drops
the tail" and "writes out of bounds" are different defects and upstream asserts neither. There is **no
second origin**: one upstream card, and the same repo's canonical template contradicts it (0253). BOARD
is `family-claimed(unverified)` — the card declares itself A5/arch3510 RegBase but names no board token
this book recognises, and none was contacted. The generalisation in §2 — that every capacity constant
has an accessor and a tempting literal — is reasoning across 0207, 0209, 0216 and C-006/C-007, not a
measurement, and this entry claims only the lane-count case. Finally, it says nothing about
`B32_DATA_NUM_PER_REPEAT`'s or `ONE_BLK_SIZE`'s own definitions or intended uses; they are named here
only as sources the rule forbids borrowing from, and each presumably has a context in which it is the
right constant.
