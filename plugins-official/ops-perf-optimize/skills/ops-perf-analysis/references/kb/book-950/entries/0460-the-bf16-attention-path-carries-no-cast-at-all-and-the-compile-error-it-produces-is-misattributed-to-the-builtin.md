```
ID:        0460-the-bf16-attention-path-carries-no-cast-at-all-and-the-compile-error-it-produces-is-misattributed-to-the-builtin
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/subfamilies.md:276-295 —
           "**关键契约**:bf16 路径**与 fp16 路径同型**——V 全程 bf16,**无任何 Cast / pre-cast /
           Reinterpret 中转**。" · "- **V1 输出到 GM 的中间段 dtype = bf16**(与 KV_T 同型):V1 末尾
           P 经 `Cast<bf16, float>` 写回 GM;**禁止**把 P Cast 到 half 让该段走 half(偏离官方实现,
           会引入精度退化)" · "#### dtype 编译错诊断 / `P_T = half` + `KV_T = bf16` 或 `P_T = bf16` +
           `KV_T = half` 同型约束未满足直接喂 Mmad → 编译失败 → 错误归因为"DAV-XXXX builtin 不接受
           bf16 ptr"是反模式。**真根因**:Mmad 模板参数同型约束未满足(API 文档 dtype 矩阵硬约束),
           改 fm/filter 为同 dtype 即可。"
SOURCE:    same file:286-291 — the four named anti-patterns (AIV pre-cast to a half workspace;
           `Cast<half, bfloat16_t>` inside L1; a host-CPU bf16→half pre-conversion; a per-s2-block
           bf16→half cast with an extra workspace rotation) ; :272-274 — the fp16 path's three lines
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a bf16 FlashAttention build on a named 950 board whose per-s2-block bf16→half cast path
           agrees with the FP64 reference within the declared atol at long `Sk`, and is not slower
           than the direct path beyond the variance floor — the "error amplification through rescale
           and accumulate" mechanism would then have no subject at that shape. Equally: a
           `Mmad<float, half, bfloat16_t>` instantiation that compiles under this toolkit pin would
           falsify the same-type constraint the diagnosis rests on.
```

# 0460 · The bf16 attention path carries no cast at all, and the compile error it produces is misattributed to the builtin

## 1 · Claim
Upstream asserts that a bf16 FlashAttention path is structurally identical to the fp16 path: `V`
stays bf16 from GM through Nd2Nz to L1, through `LoadData2D` with `ifTranspose=true` into L0B, into
`Mmad<float, bfloat16_t, bfloat16_t>` — with no cast, no pre-cast and no reinterpret anywhere on that
route. Upstream asserts that the GM intermediate segment `V1` writes must have the same dtype as the
KV tensor, so bf16, produced by a `Cast<bf16, float>` at the end of `V1`; casting `P` to half so that
the segment carries half is forbidden and is stated to introduce precision degradation. Upstream
asserts the Mmad template's feature-map and filter operands must be the same dtype, as a hard
constraint of the API's dtype matrix. Upstream asserts a diagnosis: when a mixed `P_T`/`KV_T` pair is
fed to Mmad the build fails, and attributing that failure to a `DAV-XXXX` builtin refusing a bf16
pointer is an anti-pattern — the real cause is the same-type constraint, and the repair is to make the
two operands the same dtype. Upstream names four further anti-patterns on the bf16 route. Not
established here.

## 2 · The wrong branch this removes
Without this entry an agent handed a bf16 attention operator reaches for a cast, and every reason to
do so is a good one. bf16 has fewer mantissa bits than fp16; the softmax is the numerically delicate
part; half is the dtype the fp16 path is known to work in; and the Ascend C API surface has `Cast` in
it for exactly this. So the natural design is "convert to half early, run the known-good path, convert
back" — which upstream names as its first anti-pattern (`AIV pre-cast 到 half workspace`) and rejects
on three grounds at once: an added AIV cast cost, an added GM workspace, and one added cross-core
synchronisation, `无任何收益`.

The normal checks do not catch it because the cast path is *correct enough to pass*. Precision
regression at short `Sk` passes; the error the fourth anti-pattern describes accumulates through the
rescale-and-accumulate chain, so it grows with the number of KV blocks and is smallest exactly where
an MVP tests.

The second wrong branch is the diagnostic one, and it is the reason this entry is a `trap` and not a
`knowledge`. When the same-type constraint is violated the build fails with a message about a builtin
and a bf16 pointer. That message points at the compiler and the architecture — `DAV-XXXX builtin
不接受 bf16 ptr` — and an agent that believes it concludes that bf16 is unsupported on the part and
writes the cast path, which is the first wrong branch, arrived at through a false statement about the
hardware. Upstream states the real cause explicitly, which is unusual: most of this corpus records what
to do, not what an error message will lie about.

## 3 · Ground / Source
The contract, `references/flashattention/subfamilies.md:276-283`:

```
### §4.2 bf16(Cube 直通 bf16)

**关键契约**:bf16 路径**与 fp16 路径同型**——V 全程 bf16,**无任何 Cast / pre-cast / Reinterpret 中转**。

- **V 全程 bf16**:GM(bf16)→ Nd2Nz → L1(bf16)→ LoadData2D `ifTranspose=true` → L0B(bf16)→ `Mmad<float, bfloat16_t, bfloat16_t>`(bf16 × bf16 → fp32 accumulator)
- **V1 输出到 GM 的中间段 dtype = bf16**(与 KV_T 同型):V1 末尾 P 经 `Cast<bf16, float>` 写回 GM;**禁止**把 P Cast 到 half 让该段走 half(偏离官方实现,会引入精度退化)
- **Mmad 模板同型约束**:Mmad fm 与 filter 必须同 dtype(API 文档 dtype 矩阵硬约束);bf16 路径 fm / filter 均 bf16,fp32 accumulator
- **Fixpipe L0C(fp32)→ Cube↔Vector 中间段(fp32)**,V2 末块 `Cast<bf16, float>` → outGm
```

Read against the fp16 path three lines above (`:272-274`), the two are the same structure with the
element type substituted: `Mmad<float, half, half>`, intermediate segment `= half`, all casts on UB
only. That is what `同型` means here — not "bf16 behaves like fp16 numerically" but "the two paths are
the same code with one type parameter changed", which is the claim that makes a single implementation
possible and which the anti-patterns all violate by adding structure to one of them.

Two casts survive in the correct path and it is worth being precise about where, because "no cast
anywhere" is the headline and is not literally true: `V1`'s tail casts `P` from fp32 down to bf16 on
the way to GM, and `V2`'s last block casts fp32 to bf16 on the way to the output. Both are on the
**vector** side and both are on the *P/O* route. The prohibition is on casts along **V's** route and
on any cast that changes the intermediate segment's dtype. `:288` states the general rule that makes
this mechanical: `Cast 仅在 UB 上执行,不能在 L1 执行`.

The four anti-patterns, `:286-291`:

```
#### 禁止反模式

- **AIV pre-cast 到 half workspace**:增加 AIV Cast 开销 + 额外 GM workspace + cross-core sync 一次,无任何收益,偏离官方生产实现
- **L1 内 Cast<half, bfloat16_t>**:Cast 仅在 UB 上执行,不能在 L1 执行
- **Host CPU bf16 → half 预转换**:违反 `development-guide §1.4 API 使用规则`("Host 侧禁止计算型操作"小节)
- **Kernel 内逐 s2 块 bf16 → half Cast + 额外 workspace 轮转**:既触发 BSND flat DataCopy 不感知 stride 的 race,又因逐 s2 Cast 链经 rescale + accumulate 放大累积误差
- **V1 末尾把 P Cast 到 half 让中间段走 half**:偏离官方实现,V1 输出中间段必须与 KV_T 同型 = bf16
```

Five items, not four — the last restates the segment-dtype rule as an anti-pattern, so the list and
the contract overlap by one. The four distinct ones fail for four *different* reasons: cost with no
benefit; a placement rule (`Cast` is a UB operation); a host-side policy rule from another skill; and a
compound failure that is both a race and an error-amplification. Only the fourth carries a numerical
mechanism, and it is the one that a short test cannot see: `逐 s2 Cast 链经 rescale + accumulate 放大
累积误差`, the per-block cast entering the online-softmax rescale chain. That is the same accumulation
hazard this book records at `0397` for a different family, arrived at from a different direction.

Three of the five justifications are appeals to authority rather than to mechanism — `偏离官方生产
实现`, deviates from the official production implementation, appears twice, and `违反 development-guide
§1.4` once. Upstream never identifies the official implementation or quantifies the deviation.
Recorded as `Q-950fin-09`.

The diagnosis, `:293-295`:

```
#### dtype 编译错诊断

`P_T = half` + `KV_T = bf16` 或 `P_T = bf16` + `KV_T = half` 同型约束未满足直接喂 Mmad → 编译失败 → 错误归因为"DAV-XXXX builtin 不接受 bf16 ptr"是反模式。**真根因**:Mmad 模板参数同型约束未满足(API 文档 dtype 矩阵硬约束),改 fm/filter 为同 dtype 即可。
```

The `DAV-XXXX` is upstream's own redaction of a specific architecture number in the error text. This
matters for scope: the error message an implementer saw named a `DAV` architecture, and upstream chose
not to record which. So the one place in the FA family where a real toolchain error is quoted is the
one place a board token is deliberately removed. Recorded as `C-950fin-006` against the family's other
architecture mentions (`design.md:94`, `:525`, `:617`, `subfamilies.md:195`, all `A5`).

One repository, one origin (RULES.md Art. 3). The same-type constraint is attributed to "the API
documentation's dtype matrix", which upstream does not quote and which is not in this repository —
so it is a pointer to a second origin, not a second origin.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The compile
arms need no device and are marked as such; they are still not run in this phase, because they contact
the compiler rather than reading a file.

Device selection for the runtime arms: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3
at 20 s spacing; bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`;
re-sample after and discard the case if the die moved.

**Arm 1 — the same-type constraint (compile-only).** Instantiate `Mmad` with the four combinations of
`{half, bfloat16_t}` for fm and filter, fp32 accumulator, in a minimal translation unit for a
DAV_3510 target under a stated toolkit pin. Record, per combination, whether it compiles and the
**verbatim** diagnostic when it does not. This is the arm that decides whether the misattributed error
message is what upstream says it is — and the message itself, not the pass/fail, is the datum.

**Arm 2 — the direct path versus the pre-cast path.** Two builds of one bf16 GQA kernel: (a) V direct
per the contract; (b) AIV pre-cast to a half workspace. Report `aiv_time`, `aic_time`, the number of
cross-core synchronisations, the workspace total, and elementwise agreement against an FP64 reference,
across `Sk ∈ {512, 2048, 8192, 32768}`. Upstream claims (b) has `无任何收益` — no benefit at all — so
the prediction is (b) slower or equal at every point, with more workspace and one more sync.

**Arm 3 — the amplification, which is the claim a short test cannot see.** Build (c): per-s2-block
bf16→half cast with the extra workspace rotation. Report max absolute error against FP64 **as a
function of the KV block count**, alongside (a). Upstream's mechanism predicts (c)'s error grows with
block count while (a)'s does not. A flat error curve for (c) would mean the amplification claim has no
subject at these shapes, which §5 declares as an OVERTURN condition now.

**Arm 4 — the intermediate segment dtype, retained because it is expected to bite.** Build (a) with
the `V1` output segment forced to half. Report agreement per `Sk`. Upstream says this degrades
precision; if it does not, `禁止把 P Cast 到 half` rests on the deviation-from-official argument alone,
which no procedure can test, and §7 records that.

Refuses to assume: that a free die stays free, or that a die may be substituted; that a compile failure
means what its message says (arm 1 records the message and the cause separately); that error magnitude
at one `Sk` predicts another (arm 3's whole design is the `Sk` dependence); that "no benefit" means
"slower" (arm 2 reports time, sync count and workspace as three separate quantities, because a claim of
no benefit is falsified by a benefit on any of them); that the FP64 reference may be computed at the
kernel's own precision (`0396`).

## 5 · Checker — acceptance declared before the run
Verdict `mmad_accepts(fm, filter)` from arm 1, a 2×2 boolean table plus the verbatim diagnostics.
Acceptance for the constraint: the diagonal compiles and the off-diagonal does not. The OVERTURN's
second half fires iff any off-diagonal combination compiles. Separately, verdict
`message_names_builtin` — whether the off-diagonal diagnostic mentions a builtin or a pointer type
rather than a template constraint. This is what makes the misattribution real or not, and it is
recorded even when the pass/fail is as predicted.

Verdict `precast_benefit` from arm 2 ∈ {`none`, `time`, `sync`, `workspace`}, a set. Upstream's claim
is `precast_benefit == ∅`. Any non-empty result is a correction to upstream, not a failure of the run.

Verdict `error_growth_slope(build)` from arm 3: the regression slope of max absolute error against KV
block count, with its confidence interval. Acceptance for the amplification claim:
`slope(c) > slope(a) + interval`. The OVERTURN's first half fires iff `slope(c) ≤ slope(a) + interval`
across the `Sk` range including 32768.

The exit code is not the verdict: every runtime build here produces plausible output, and three of the
four differ only in precision. Guards: (1) arm 1's verdict includes the verbatim message, and the
checker fails red if a diagnostic was not captured — a compile arm that records only "failed" cannot
test a claim about what the failure *says*, which is this arm's actual subject; (2) **the input that
makes this checker go red**: build (a) at `Sk = 512` with a single KV block, where the online-softmax
rescale chain has no rounds and all four builds must agree to within one ulp of bf16 — if they
disagree there, the builds differ in more than their cast placement and every slope in arm 3 is an
artifact; (3) no point is reported without its `Sk`, its block count, its atol, its variance floor, the
toolkit pin and the compiler command.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement, and no compiler was invoked.
The contract, the fp16 comparison lines, the five anti-patterns, the placement rule for `Cast`, and the
diagnosis with its quoted misattribution are file reads performed at drafting time. The observations
that two casts survive in the correct path, that the anti-pattern list and the contract overlap by one
item, that three of the five justifications appeal to an unnamed official implementation, and that
`DAV-XXXX` is a redacted architecture token, are readings of upstream's own lines, not observations of
a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or run. The entry does not establish the Mmad same-type constraint —
upstream attributes it to an API dtype matrix that is not in this repository and does not quote it, so
this is a pointer to a second origin and not a second origin. It does not establish that the compile
error says what upstream says it says; the architecture token in the quoted message is redacted, and
`C-950fin-006` records that. It does not establish that any anti-pattern is slower or less accurate:
upstream gives no number for any of the five, and three of them are justified by deviation from an
implementation it never identifies (`Q-950fin-09`). It does not establish the error-amplification
mechanism, only that upstream states it. It does not cover fp32 or the quantised dtypes, which
`subfamilies.md §4.3` treats separately and which have their own cast chains (`0455`). It does not
establish `ifTranspose=true` as required, only that upstream's route names it. No board token appears
in any quoted passage — the one architecture reference is redacted — so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
