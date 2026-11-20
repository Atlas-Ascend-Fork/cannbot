```
ID:        0158-scatter-collisions-are-confined-to-one-fiber-and-that-single-invariant-generates-the-whole-decision-tree
LABEL:     knowledge
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     950PR
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scatter/fallback/tiling-flow.md:49-60,64-86 —
           "更新元素的落点**只把第 `d` 维坐标换成 index 值，其余坐标原样保留** ⇒ 两个更新撞同一输出
           位置，当且仅当非 dim 坐标全同且 index 值相同 ⇒ **冲突严格局限在一条纤维内**" ·
           "**按纤维分线程 ⇒ 输出集互不相交 ⇒ 完全免原子**" · "`dst = o·sVar·inner + ix·inner + c`
           ... 是**混合进制表示**，`(o,ix,c) ↔ dst` 一一对应"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a scatter case on a named 950 board where the fiber-exclusive path produces a wrong result
           under duplicate indices — two threads would then be writing the same output position, and
           the invariant that makes path ① atomic-free would be false.
```

# 0158 · Scatter collisions are confined to one fiber, and that single invariant generates the whole decision tree

## 1 · Claim
Upstream asserts one structural invariant and derives the entire six-path decision tree from it. The
invariant: an update element lands by replacing only the `d`-th coordinate with the index value and
keeping every other coordinate, so two updates collide on the same output position exactly when all
non-`dim` coordinates agree and the index values agree — collisions are therefore strictly confined
within one fiber. Upstream asserts two consequences it calls directly cashable. First, partitioning
threads by fiber makes the output sets disjoint, so no atomics are needed at all, and since a thread
walks `dim` in increasing order, `reduce=none` gets last-write-wins for free. Second, under
element-level parallelism an `atomic_max` on the `dim` index arbitrates a unique winner, because
`dst = o·sVar·inner + ix·inner + c` with `0 ≤ c < inner` and `0 ≤ ix < sVar` is a mixed-radix
representation, so `(o, ix, c) ↔ dst` is a bijection, so one `dst` can only come from one fiber, and
within a fiber the `j` values are distinct. Upstream asserts that last-write-wins is a hard
requirement because the acceptance metric is a maximum relative error that one wrong winner fails,
and that CANN's built-in `REDU_NONE` is a bare write which does not provide it — the three
arbitration paths for `none` (②③⑤) exist to buy that guarantee. Not established here.

## 2 · The wrong branch this removes
The wrong branch is reaching for atomics by default. Scatter looks like a canonical
read-modify-write hazard, and an agent will make every write atomic. Path ① shows that for a whole
regime — whenever the fiber count fills the machine — atomics are unnecessary, not merely
avoidable: the partition itself makes the output sets disjoint. That is a factor that does not appear
in any profile as "atomic overhead"; it appears as the operator being slower than it needs to be.

The second wrong branch is the opposite error and is a correctness one. Under element-level
parallelism with `reduce=none`, an agent that writes without arbitration produces output that is
*usually* right — duplicate indices are needed to expose it — and wrong under exactly the inputs the
acceptance metric targets. Upstream's note that a built-in `REDU_NONE` does not provide the guarantee
is the load-bearing detail: reaching for the vendor primitive is the natural move and it does not
satisfy torch semantics.

The third is subtler and worth stating because it is the reason the entry exists as a claim rather
than as background. The invariant is what licenses `atomic_max` over `j` to be a *correct*
arbitration rather than a heuristic. An agent that adopts path ③ without the bijection argument has
no reason to believe `atomic_max` picks the last writer, and will either add a redundant second pass
or use a lock.

## 3 · Ground / Source
The invariant and its two consequences, `scatter/fallback/tiling-flow.md:49-60`, in full:

```
### 1.2 核心不变量（决策树的全部依据）

更新元素的落点**只把第 `d` 维坐标换成 index 值，其余坐标原样保留** ⇒ 两个更新撞同一输出位置，
当且仅当非 dim 坐标全同且 index 值相同 ⇒ **冲突严格局限在一条纤维内**。由此得到两条可直接变现的结论：

1. **按纤维分线程 ⇒ 输出集互不相交 ⇒ 完全免原子**；且线程内沿 dim 递增 ⇒ `reduce=none` 天然"后写覆盖"。
2. **元素级并行时 `atomic_max` 按 dim 下标裁决出的胜者唯一**。因为
   `dst = o·sVar·inner + ix·inner + c`（`0≤c<inner`、`0≤ix<sVar`）是**混合进制表示**，`(o,ix,c) ↔ dst` 一一对应
   ⇒ 同一 `dst` 只可能来自同一条纤维，纤维内 `j` 互不相同 ⇒ 比 `j` 永远分得出胜负。

> **后写覆盖是硬要求**：判据 MARE 取最大相对误差，重复索引选错一个胜者就整例挂。
> CANN 内置的 `REDU_NONE` 是裸写、不提供这个保证——`none` 那三条仲裁路径（②③⑤）付的开销就是买这个保证。
```

The tree the invariant generates, `:64-86`, in full:

```
Step 0 — extentsMatch?
  ├─ 否 → ⑥ 通用逐维 stride 路径（正确性优先：索引一律 int64，不收窄）
  └─ 是 ↓

Step 1 — starved = (numFibers < coreNum × 1024)?
  ├─ 否（铺得满核）→ ① 纤维独占            ★ 免原子、免 workspace，到此为止
  └─ 是 ↓

Step 2 — 按 reduce 分叉
  ├─ add / amin / amax / multiply（结果与顺序无关）→ ④ 直接原子
  │     · multiply 无硬件原子乘 → CAS 循环（fp32 / int32 / int64）
  │     · fp16/bf16 的 add / multiply → 叠加 fp32 累加器（见 §3.5）
  │     · fp16/bf16 的 amin / amax → 直接用原生半精度原子，**不要**绕 workspace
  └─ none（必须保证后写覆盖）↓

Step 3 — 按键宽与纤维数选仲裁方式
  ├─ esize==4 && jBits+idxBits ≤ 31 && numFibers ≥ 1024 → ⑤ warp 段末
  ├─ esize==2 && sIdx+1 ≤ 65535                        → ② 打包键单趟
  └─ 其余（4/8 字节值、或键装不下）                       → ③ 两趟胜者
```

The bit-width arithmetic the Step-3 gates use, `:88-102`:

```cpp
auto bitWidth = [](int64_t n) { int32_t b = 0; for (int64_t v = n - 1; v > 0; v >>= 1) ++b; return b; };

const int32_t jBits   = bitWidth(sIdx);      // ⑤ 用：index 在键内的起始位
const int32_t idxBits = bitWidth(sVar);
// 预留 0xffffffff 作无效 lane 哨兵 ⇒ 合法键最多用低 31 位
const bool warpKeyFits32 = (jBits > 0) && (jBits + idxBits <= 31);

// ② 用：2 字节值 + (j+1) 挤进高 16 位
const bool key32 = (esize == 2) && (sIdx + 1 <= 65535);

// ③ 用：胜者数组记的是线性下标 i+1，必须落在 uint32 内
const bool winnerLinearFits32 = epTotal < (int64_t{1} << 32) - 1;
```

Three different 32-bit budgets for three different encodings: ⑤ packs index and value coordinates
into 31 bits (one value reserved as an invalid-lane sentinel), ② packs a 2-byte value plus `j+1`
into 32 bits, ③ stores a linear ordinal that must fit `uint32`. Each is a capacity argument about a
key, not a hardware limit, and each is checked explicitly.

The winner-encoding choice, `:215-217`, which is a design note worth carrying:

```
> 趟 1 记的是**线性下标 `i+1` 而不是 `j+1`**：对固定 `(o,c,dst)`，`i` 随 `j` 严格递增，同样能裁决最后写；
> 而且趟 2 可以直接 `updates[winner-1]` 取值，**不必重算 `dst`、也不必再读 `indices`**。
> （⑥ 通用路径例外：`updates` 有自己的 stride，`i` 不能当 `updates` 下标，所以那里记 `j+1`。）
```

and the free optimisation the mixed-radix decomposition permits, `:286-297`:

```
元素级路径把线性下标 `i` 分解成 `(o, j, c)` 时，`outer == 1` 可省掉一次除法：

if (outer == 1) { o = 0; j = i / inner;      c = i - j * inner; }
else            { o = i / (sIdx * inner);
                  rem = i - o * (sIdx * inner);
                  j = rem / inner;           c = rem - j * inner; }

大量真实 shape 是 `dim=0` 的二维/三维张量，这条特判值得保留。
```

The path cost comparison the tree ranks against, `:128-139`:

```
| 路径 | 散射趟数 | 顺序流量 | workspace | 原子宽度 |
|---|---|---|---|---|
| ① 纤维独占 | 1 | clone（1× numel） | 无 | 无 |
| ② 打包键 | 1 | init + unpack（2× numel） | `int32[numel]` | 32 位 |
| ③ 两趟胜者 | 2 | clone + fill-zero（2× numel） | `int32[numel]` | 32 位 |
| ④ 直接原子 | 1 | clone（1× numel）；半精度累加类 +2 趟 cast | 半精度累加类 `float[numel]` | 32 位 |
| ⑤ warp 段末 | 1 | clone（1× numel） | **无** | **无** |
| ⑥ 通用 | 同 ③/④ | 同 ③/④ | 同 ③/④ | 同 ③/④ |

⑤ 在成本上全面占优，但适用面最窄（四条条件全中才用）。
```

## 4 · Procedure
Proposed, runnable later on Ascend950PR — the board upstream names; a 950DT run is a separate claim.
Never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

Arm 1 — the invariant, a correctness arm. Construct inputs with heavy index duplication: every index
value repeated 8 times within each fiber, and a second input where the same value appears at
different positions across fibers. Build path ① (fiber-exclusive) and run it 200 times, comparing
output elementwise against a CPU reference implementing last-write-wins each time. A single wrong
element in any run kills the invariant. 200 runs rather than one because path ① claims freedom from
atomics: a race would be intermittent.

Arm 2 — the arbitration. On a `starved` shape with `reduce=none`, build path ③ and a deliberately
unarbitrated variant that writes without `atomic_max`. Compare both against the reference on the
duplicated input. The unarbitrated arm is a poison arm and is retained whether or not it bites; the
fraction of wrong elements is recorded, because that fraction is what a duplicate-free test would
have missed.

Arm 3 — the bijection's boundary. Construct a case where `sIdx > sVar` — index values legal only up
to `sVar` — and one where an out-of-range index appears, and record what each path does. The
bijection argument assumes `0 ≤ ix < sVar`; behaviour outside it is not covered by the invariant and
upstream does not state it.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` is a
literal (queried, 0141 — `starved` depends on it); that one clean run proves an atomic-free path is
race-free (200 runs are fixed in advance); that the CPU reference's tie policy is right — it is
validated on a hand-computed duplicated case first.

## 5 · Checker — acceptance declared before the run
Verdict variable `fiber_exclusive_correct`: true iff all 200 runs of arm 1 match the reference
exactly. Declared acceptance: the invariant holds iff `fiber_exclusive_correct` is true. The OVERTURN
fires on any mismatch. Verdict `arbitration_needed`: true iff the unarbitrated arm produces wrong
output — expected, and its absence would mean the `none` arbitration paths are paying for nothing.
Verdict `oob_behaviour` per path from arm 3, reported as observed rather than judged.

The exit code is not the verdict: every arm here exits 0 whether right or wrong. The instrument is
the elementwise comparison, and two guards make it able to fail. First, the input must contain
duplicates — the checker fails red if the generated indices are distinct within every fiber, because
a duplicate-free input cannot distinguish correct arbitration from none, and that is precisely how a
scatter bug ships. Second, the reference must itself be validated against a hand-computed case before
it judges anything; a reference with first-write-wins semantics would score the correct kernel as
broken.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. `BOARD: 950PR` records the board upstream's evidence names; the stratum,
not the board field, says who measured. The entry does not establish the invariant — it records
upstream's argument, which is a proof sketch about index arithmetic and not a measurement, and §4 arm
1 is what would test its consequence. It does not establish the Step-3 gates' thresholds (0161), the
thread counts (0160) or the `extentsMatch` requirement (0159). It does not establish behaviour for
out-of-range index values, which the bijection argument does not cover and upstream does not discuss.
It does not cover ScatterNd and its relatives, for which upstream states the invariant is false.
Nothing here is established for 950DT or for any 910-family board.
