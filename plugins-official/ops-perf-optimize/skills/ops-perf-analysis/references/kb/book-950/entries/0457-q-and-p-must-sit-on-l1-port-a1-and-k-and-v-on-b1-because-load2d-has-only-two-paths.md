```
ID:        0457-q-and-p-must-sit-on-l1-port-a1-and-k-and-v-on-b1-because-load2d-has-only-two-paths
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/design.md:266-278 —
           "#### Q1:A1 / B1 端口分离 / 回答:**Q / P 放在哪个 L1 端口?K / V 放在哪个 L1 端口?** /
           **硬约束**:Cube `Load2D` 仅支持 A1→L0A、B1→L0B 两条通路。因此: /
           - **Q、P**(均要进 L0A 做 fm)→ **必须 A1**(`TBuf<TPosition::A1>`) /
           - **K、V**(均要进 L0B 做 filter)→ **必须 B1**(`TBuf<TPosition::B1>`) /
           **违反后果**:K/V 放 A1 时 Load2D 无法把它们搬到 L0B,P 段输出全零(GQA 早期历史 bug)。"
SOURCE:    same file:296-298 — "**易掩盖陷阱**: / - 假设"L1 容量 512KB 充裕"而不做分块——512KB 是
           A1+B1 总容量,单 buffer 分不到这么多 / - 只做 L0 K-axis 分块而忽略 L1 溢出 → 大 D 时精度
           崩塌或 kernel 静默错乱(典型 D≥512)" ; :286-287 — "perSlotElems = L1_PORT_SIZE /
           rotation_slots / sizeof(elem) / 若 一次 Nd2Nz 元素数 > perSlotElems → 必须实施 M 轴
           (或 N 轴)L1 分块"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a Cube `Load2D` on a named 950 board that moves a tile from an `A1`-declared L1 buffer into
           `L0B`, or from `B1` into `L0A` — the two-path restriction would then not be a hardware
           constraint on this part and the port assignment would be a convention. Equally: a build
           with K/V declared on `A1` whose `P` segment is NOT all zeros would falsify the stated
           symptom even if the restriction holds.
```

# 0457 · Q and P must sit on L1 port A1 and K and V on B1, because Load2D has only two paths

## 1 · Claim
Upstream asserts a hardware restriction on the Cube `Load2D` instruction: it supports exactly two
routes out of L1, `A1 → L0A` and `B1 → L0B`. Upstream asserts the consequent placement for a
FlashAttention operator's four L1-resident tensors: `Q` and `P` both enter `L0A` as the feature-map
operand and must therefore be declared `TBuf<TPosition::A1>`; `K` and `V` both enter `L0B` as the
filter operand and must be declared `TBuf<TPosition::B1>`. Upstream asserts the failure mode of the
wrong assignment: with `K`/`V` on `A1`, `Load2D` cannot move them to `L0B`, and the `P` segment's
output is all zeros — recorded as a historical GQA bug rather than as a hypothesis. Upstream asserts
separately that L1's stated 512 KB is the sum of the two ports and that no single buffer receives that
much, and gives a per-slot budget `perSlotElems = L1_PORT_SIZE / rotation_slots / sizeof(elem)` above
which M-axis or N-axis L1 blocking becomes mandatory. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent treats L1 as one pool. That is how L1 is described almost everywhere,
including in this corpus's own architecture entries, which give it as a capacity — and a capacity is
something you divide by need, not by port. So the natural allocation is "Q, K, V and P all live in L1,
sized by how much each needs", with the `TPosition` chosen from whichever example was copied. Three of
the four assignments will be right by luck in any layout that mirrors a matmul; the fourth is `P`,
which is produced by the vector core and consumed as the *feature map* of the second GEMM, and which
an agent thinks of as an intermediate rather than as an A-operand.

The normal checks do not catch it. The buffer is declared, allocated and written. `Load2D` is issued.
Nothing faults. What comes out of `P·V` is zeros, and the operator's output — after a rescale and a
normalisation by a `sum` that is itself correct — is zeros or garbage in the `O` tile only. An agent
debugging that looks at the softmax, at the accumulation, and at the cross-core handshake, all of which
are live suspects in this operator (`0451`), before it looks at a `TPosition` template argument.

The second wrong branch is the capacity one upstream names as `易掩盖陷阱`, easy to conceal: reading
"L1 is 512 KB" and concluding that a `mPad × D` tile fits. It is the sum across both ports, divided
again by the rotation depth, so the per-slot budget is a small fraction of the headline number. The
symptom upstream gives for that miss is not an overflow error but `大 D 时精度崩塌或 kernel 静默错乱`
at `D ≥ 512` — precision collapse or silent misbehaviour, which is the same non-symptom as the port
error and arrives at a different shape.

## 3 · Ground / Source
The port constraint, `references/flashattention/design.md:266-278`:

```
#### Q1:A1 / B1 端口分离

回答:**Q / P 放在哪个 L1 端口?K / V 放在哪个 L1 端口?**

**硬约束**:Cube `Load2D` 仅支持 A1→L0A、B1→L0B 两条通路。因此:
- **Q、P**(均要进 L0A 做 fm)→ **必须 A1**(`TBuf<TPosition::A1>`)
- **K、V**(均要进 L0B 做 filter)→ **必须 B1**(`TBuf<TPosition::B1>`)

**违反后果**:K/V 放 A1 时 Load2D 无法把它们搬到 L0B,P 段输出全零(GQA 早期历史 bug)。
```

Two things are worth separating here. The restriction is stated as a `硬约束`, a hard constraint of the
Cube data path, with no board named and no header cited — it is asserted, not shown. The consequence
is stated as history: `GQA 早期历史 bug`, an error someone already made. A rule whose justification is
a hardware property and whose evidence is a past defect is exactly the shape that deserves an entry,
because the rule survives even if the stated mechanism is wrong, and the mechanism is what a consumer
would generalise from.

Note also what the assignment is derived from: not from the tensors' roles in attention but from which
Mmad operand each becomes. `Q` and `P` are feature maps; `K` and `V` are filters. An agent that
reasons "Q and K are the inputs to the first GEMM, so they belong together" gets the opposite
grouping — and that grouping is the one the operator's *mathematics* suggests. The correct grouping
is the one the *instruction set* imposes, and it cuts across the maths.

The per-port budget, `:284-290`:

```
判定公式:
perSlotElems = L1_PORT_SIZE / rotation_slots / sizeof(elem)
若 一次 Nd2Nz 元素数 > perSlotElems → 必须实施 M 轴(或 N 轴)L1 分块

`L1_PORT_SIZE` 是 A1 / B1 端口的预算分配(`PlatformAscendC::GetCoreMemSize(CoreMemType::L1_A/L1_B)` 查询所得 ≥ 该预算)。`rotation_slots` 由 §2.4 流水线深度决策与 [`subfamilies.md` §2.2 L1 rotation 子族差异](./subfamilies.md)决定。
```

The parenthetical is precise and easy to skim past: the queried value is `≥` the budget, so
`L1_PORT_SIZE` is a *policy allocation* the designer sets, not the capacity the platform reports. The
formula therefore has a free parameter that upstream never fixes, and the corpus's existing L1 numbers
(`0102`'s cube-tiling-splits-at-L1 material, and the architecture block's per-board capacities) are
capacities, not budgets. Recorded as `Q-950fin-05`.

The two concealed traps, `:296-298`:

```
**易掩盖陷阱**:
- 假设"L1 容量 512KB 充裕"而不做分块——512KB 是 A1+B1 总容量,单 buffer 分不到这么多
- 只做 L0 K-axis 分块而忽略 L1 溢出 → 大 D 时精度崩塌或 kernel 静默错乱(典型 D≥512)
```

The second is a partial-fix trap and belongs with `0456`: `K`-axis blocking at L0 decouples L0 from
`D` and is the obvious first move, and it leaves L1 coupled to `D` through `mPad × D`. So an agent that
has done the harder-looking piece of work is *more* likely to stop before the one that still bites. The
`512` KB figure is stated with no board attached; the corpus's own architecture entries put L1 at 512 KB
for both DAV_2201 and DAV_3510 (`0211`'s neighbourhood), so the number is consistent with the family
but its split across ports is not stated anywhere in this shelf.

The rotation depth in the denominator is subfamily-specific (`subfamilies.md:55-59`: standard
task-level double buffering for FA/GQA inference, one extra prefetch segment optionally for GQA
prefill, deeper for MLA), which is the fourth slot semantics `0453` records as sharing this family's
constant-separation prohibition.

Two files in one repository are one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample afterwards and
discard the case if the die moved.

**Arm 1 — the restriction itself, isolated from attention.** Not a FlashAttention kernel: four tiny
kernels that declare one L1 buffer each and issue one `Load2D` — `A1 → L0A`, `A1 → L0B`, `B1 → L0A`,
`B1 → L0B` — followed by one `Mmad` whose result is copied out. Record, per kernel: whether it
compiles, whether it faults, and what the destination fragment contains. The two diagonal cases are the
control; the two off-diagonal cases are the claim. A compile failure is as informative as a zero
result and is recorded as a distinct outcome, because "the API refuses it" and "the hardware ignores
it" are different constraints with the same consequence for a designer.

**Arm 2 — the stated symptom, in situ.** A minimal GQA kernel with the four `TPosition` declarations
switchable. Run the correct assignment (control) and the `K`/`V`-on-`A1` assignment. Record the
fraction of exactly-zero elements in the `P·V` result segment specifically, dumped before the rescale,
not in the final output. Upstream's symptom is about the `P` segment; measuring it in the final output
would not distinguish it from the several other zero-producing failures in this operator.

**Arm 3 — the port budget.** With the correct assignment, query
`GetCoreMemSize(CoreMemType::L1_A)` and `(CoreMemType::L1_B)` and echo both, alongside the
`L1_PORT_SIZE` the design chose and the `rotation_slots` in force. Then sweep `D ∈ {128, 256, 512,
1024}` at fixed `rotation_slots`, with L1 M-axis blocking disabled, and record the first `D` at which
the operator's output disagrees with the FP64 reference — upstream predicts `D ≥ 512` typical. Enable
blocking and repeat: the disagreement must disappear. This is the arm that gives `Q-950fin-05` its
first number, by reporting the queried capacities next to the budget the design assumed.

**Arm 4 — the partial fix, retained because it is expected to bite.** L0 `K`-axis blocking enabled and
L1 M-axis blocking disabled, at `D = 512`. Upstream says this combination still fails. If it does not,
the two blocking decisions are not independent at this shape and §7 records that the trap's stated
mechanism is unconfirmed.

Refuses to assume: that a free die stays free, or that a die may be substituted; that `L1_A`/`L1_B`
report a per-port capacity rather than a shared one (both are queried and echoed, and their sum is
compared against the 512 KB the document assumes); that a compile failure and a runtime zero are the
same finding; that `P`'s zeros can be read from the final output (arm 2 dumps the segment); that a
correct output at one `D` says anything about another; that the operator's correctness implies each
`Load2D` took the route intended.

## 5 · Checker — acceptance declared before the run
Verdict `load2d_routes` from arm 1, a 2×2 table over {source port} × {destination fragment}, each cell
in {`compile_error`, `fault`, `zeros`, `correct`}. Acceptance for the entry: the diagonal is `correct`
and the off-diagonal is not. The OVERTURN fires iff either off-diagonal cell is `correct` — `Load2D`
would then have more than two paths on this part.

Verdict `p_segment_zero_fraction` from arm 2, control versus swapped. Declared before the run:
supported iff the swapped build's `P·V` segment is more than 99% exactly zero while the control's is
at the padding level. A swapped build that produces *wrong but non-zero* values does not support
upstream's stated symptom and is reported as `symptom_differs`, not as agreement — the restriction
could still hold while the symptom is misremembered, and those are separate findings.

Verdict `l1_overflow_onset` from arm 3: the smallest swept `D` at which the unblocked build disagrees,
reported with the queried `L1_A`/`L1_B` values and the assumed `L1_PORT_SIZE`.

The exit code is not the verdict: every failing configuration here exits 0. Guards: (1) arm 1's cells
are decided by comparing the destination fragment against a known pattern written into the source
buffer, not by whether the kernel ran — a `Load2D` that silently does nothing leaves the fragment at
its initial value, which the checker must distinguish from zeros written by the instruction, so the
fragment is pre-filled with a non-zero sentinel; (2) **the input that makes this checker go red**: the
diagonal cases in arm 1, which must be `correct` — if `A1 → L0A` does not reproduce the sentinel
pattern, the harness cannot detect a working route and the whole table is meaningless, so the checker
refuses to emit a verdict; (3) every point carries its queried capacities, its `rotation_slots`, its
`D`, its CANN pin and its atol.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The two-path restriction, the
four-tensor assignment, the all-zeros symptom, the per-slot budget formula, the `≥ budget` parenthetical
and the two concealed traps are file reads performed at drafting time. The observation that the correct
grouping follows the Mmad operand roles rather than the attention data flow, and the observation that
`L1_PORT_SIZE` is a policy allocation with no stated value, are readings of upstream's own lines, not
observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that `Load2D` has only two routes —
upstream asserts it as a hard constraint and cites no header, no ISA document and no board. It does
not establish that a wrong port produces all zeros rather than a fault or wrong values; upstream's
evidence for the symptom is a remembered historical defect. It does not establish `L1_PORT_SIZE`, which
upstream leaves as a design-chosen budget, nor the 512 KB total, nor its split between the two ports —
no document in this shelf states the split. It does not establish `D ≥ 512` as the L1 overflow onset;
that figure is upstream's "typical" with no shape, dtype or rotation depth attached. It does not cover
the N-axis blocking alternative beyond naming it, nor the `L0B InitBuffer` trigger condition at
`design.md:94` which names `A5` and is `0463`'s neighbourhood. It says nothing about `TPosition`
placement for any operator family other than FA. No board token appears in the quoted passages, so
BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen.
Nothing here is established for any 910-family board.
