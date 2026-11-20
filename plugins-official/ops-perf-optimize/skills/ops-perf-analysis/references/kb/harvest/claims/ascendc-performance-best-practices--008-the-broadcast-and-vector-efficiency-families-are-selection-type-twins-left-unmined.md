# CARD · ascendc-performance-best-practices 008 — the broadcast and vector-efficiency families are selection-type twins left unmined

**BOOK: 950 — candidates, deliberately deferred by the 950-bp a later harvest pass harvester. This card records
the boundary so a later pass starts from it.**

## Broadcast — a genuine 950 self-attribution and an existing twin
`reference/broadcast/broadcast_design.md:6`, re-verified 2026-08-24:

> 适用：DAV_3510（A5 / Ascend950，C310）。广播 = 某输入在某些轴上 shape=1 / stride=0，需铺开到
> 输出 shape。

This is one of the few documents in the shelf that scopes itself explicitly (`950:0347` records that the
matmul family does not), and it names a token — **`C310`** — that appears nowhere in `npu-arch`'s
mapping table. `950:0203` already records that `__DAV_C310__` is a build macro that must not be read
as a numeric architecture value; `C310` appearing as a *chip* alias in a scope line is the same
vocabulary hazard as `Atlas 350` (`C-950bp-011`) and is the first thing a later pass should record.

The family is four implementations plus a front gate: OneDim axis-collapse fast path (④, stated
★前置优先), then within a tile NDDMA (①), DataCopyPad (②), or UB Broadcast (③). Upstream's framing
is the same one the scatter family uses — this is a **selection-type** family (SKILL.md structure B),
where the optimisation *is* choosing the implementation, and `选错直接慢甚至出错（nan）`.

**Why deferred:** book-950 `950:0154`–`950:0156` already carry the broadcast family's tiling side from the
analysis shelf — the four-branch selection by chip generation then by where the broadcast happens,
the script that keeps the chip-generation branch and drops every constraint that branch carries, and
the placeholder index over a real tiling. The bp shelf's four implementation documents are the twin
of that, and a useful pass is a diff against those three entries, not a read. In particular
`950:0155` records that the analysis shelf's script **drops the DAV_2201 constraints
unconditionally** — so the question worth asking of this shelf is whether its OneDim gate and its
three tile-internal paths carry the constraints that script drops.

**The `nan` claim is the highest-value unmined item.** `选错直接慢甚至出错（nan）` asserts that a
wrong implementation choice produces NaN, not merely slowness. That is a correctness claim about a
routing decision, it is stated twice in the family's opening, and nothing in book-950 carries it.
Its §4 would be: construct a case each path claims, run it under all four, and find the input under
which the wrong path produces NaN. If none does, the claim is rhetorical.

## Vector efficiency — three mechanisms, four unscoped ratios
`reference/elementwise/vector_efficiency_design.md:5-11`, re-verified:

> | Scalar 控制指令 | 每条 Vector API 前手动计算 repeat/mask | Counter 模式一次设置，全程自动 |
>   Scalar 开销降低 30-50% |
> | GM 搬运次数（n 步 Vector 链） | 2n 次（每步搬入+搬出） | 2 次（首次搬入 + 最终搬出） |
>   搬运次数减少 n 倍 |
> | 归约指令延迟 | WholeReduceSum 单条高延迟 | BlockReduceSum + WholeReduceSum 组合 |
>   延迟降低 20-40% |
> | 指令级并行 | 循环体串行执行 | 循环展开暴露并行性 | ILP 提升 |

Three separable mechanisms: `SetMaskCount(dataSize)` Counter mode replacing hand-computed
`repeatTimes`/`tailSize`; keeping a multi-step Vector chain resident in `VECCALC` so an `n`-step
chain costs 2 GM transfers instead of `2n`; and replacing a single high-latency `WholeReduceSum`
with a `BlockReduceSum + WholeReduceSum` pair.

**Why deferred:** the middle mechanism is `950:0020` (chain adjacent vector steps in UB so
intermediates never round-trip through GM) — already entered, from the analysis shelf, and the
`2n → 2` arithmetic is that entry's claim in another notation. The first and third are new. The
file names no architecture at all, and its sibling in the same directory calibrates every capacity
on a 910 part (`950:0319`, `C-950bp-010`), so a later pass must not assume the family marking scopes it.

**What is genuinely new and worth an entry:** the Counter-mode claim, because it removes a *scalar*
cost from a *vector* operator — which is the same cross-pipe move `950:0348` records for depthwise
convolution and `950:0336` for FlashAttention, and three independent instances of one pattern is worth a
book entry in its own right. And the two-stage reduction, because it is a latency claim about two
specific named APIs and is therefore directly measurable.

**What must travel with them:** `30-50%`, `20-40%` and `n 倍` are unscoped ranges with no case,
shape, dtype, board or tool — the same register `950:0318` §7 records for the residency document. Only
the `2n → 2` figure is arithmetic rather than measurement.

## Also unmined in this pass, with the same "diff, don't read" reason
- `reference/reduce/` (13 md) — twin of `950:0121`–`950:0131`. `templates/state_resident_design.md` and
  `templates/fused_attention_online_softmax_design.md` are the two files with no analysis-shelf
  counterpart; the latter names Ascend 910B three times (`:275`, `:370`, `:412`) and is not this
  book's on those lines.
- `reference/scan/` (8 md) — twin of `950:0132`–`950:0139`.
- `reference/gather/` (12 md) — twin of `950:0147`–`950:0150`. `950:0148` already records that the real
  cost gate lives *outside* the analysis skill, in this shelf's `templates/` — so this is the one
  family where the analysis shelf explicitly points here for the missing content, and it is the
  highest-priority remaining diff.
- `reference/conversion/` (12 md) — twin of `950:0163`–`950:0165`.

## Evidence class
broadcast: recipe-with-a-correctness-claim, self-scoped to DAV_3510, no measurement.
vector efficiency: three mechanisms with four unscoped ranges, no architecture named.

## OVERTURN sketch (for the deferrals)
A measured figure, or a constraint the analysis shelf drops, found in any of these families' bp-side
documents. `950:0155` makes that a live possibility for broadcast specifically.

## Disposition
Deferred with named starting points. Recorded in `harvest/standing/950-bp.md` Q-950bp-14. Priority
order for a later pass: gather (the analysis shelf points here for a missing gate) → broadcast (the
`nan` claim and the dropped constraints) → vector efficiency (Counter mode) → reduce → scan →
conversion.

> 2026-08-24 correction (950-td miner, applied by controller): this card's broadcast NaN quote
> "选错直接慢甚至出错（nan）" DOES NOT EXIST in the corpus and "appears twice" is wrong; the real
> text is "选错直接慢甚至 nan，选对才快", once, at broadcast_design.md:3. The prioritization this
> card carries was correct; the transcription was invented. Entries built on the real sentence:
> see the 0401-block broadcast entries.
