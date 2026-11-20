```
ID:        0159-every-scatter-fast-path-must-carry-extentsmatch-and-omitting-it-shipped-a-real-two-element-stride-defect
LABEL:     trap
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     950PR
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scatter/fallback/tiling-flow.md:105-126 —
           "⚠️ **漏掉 `extentsMatch` 是一个已踩过的真实缺陷**：`usePackArb` 少了它，"2 字节 + none +
           starved" 时快路与通用路径**同时成立**，`y` 被重绑到 workspace 视图而通用分支按连续下标写，
           **输出以 2 倍元素步长整体错位**。公开用例往往一条通用路径都不触发 ⇒ **标准集满分也照样挂
           隐藏集**。加任何新快路，第一件事是确认它排除了 `!extentsMatch`。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a case on a named 950 board where a fast path lacking the `extentsMatch` guard produces
           correct output on a `!extentsMatch` shape — the guard would then be unnecessary for that
           path, contrary to upstream's disclosed defect.
```

# 0159 · Every scatter fast path must carry `extentsMatch`, and omitting it shipped a real two-element-stride defect

## 1 · Claim
Upstream asserts that all four fast-path predicates must include `extentsMatch`, and discloses a real
defect from omitting it: `usePackArb` lacking the term made the fast path and the generic path both
true for a "2-byte value + `none` + `starved`" shape, so `y` was rebound to a workspace view while
the generic branch wrote by contiguous linear index, and the output was displaced wholesale by a
two-element stride. Upstream asserts the reason it survived testing: public cases often trigger no
generic path at all, so a full score on the standard set is compatible with failing the hidden set —
`标准集满分也照样挂隐藏集`. Upstream states the rule for future work: when adding any new fast path,
the first thing to confirm is that it excludes `!extentsMatch`. Not established here.

## 2 · The wrong branch this removes
The four fast-path predicates each carry a distinguishing condition — a key width, a value size, a
reduce mode — and `extentsMatch` is the one term they share, which makes it the term a reader treats
as background and an author forgets. Upstream's disclosure is that the forgetting already happened
once, in code, and shipped.

The failure mode is the instructive part. It is not a wrong element or a race: it is the *whole
output* displaced by a constant stride, because two mutually exclusive branches both evaluated true
and disagreed about what `y` pointed at. An error of that shape is trivially visible to anyone who
looks at the output — and invisible to a test suite whose cases never take the generic path. That is
the second and more transferable half of the claim: a test set that exercises only the fast paths
cannot detect a predicate that fails to exclude the slow one, no matter how many cases it has.

The third wrong branch this removes is procedural. An agent adding a seventh path will write its
distinguishing condition and inherit the shape of the neighbouring predicates. Upstream's rule turns
that into a checklist item with a stated first step, which is the only form in which such a rule
survives into someone else's code.

## 3 · Ground / Source
The complete predicate set, `scatter/fallback/tiling-flow.md:105-126`, in full:

```
### 2.2 完整判据（Host 侧，四条快路都必须带 `extentsMatch`）

const bool needScatter = (numFibers > 0 && sIdx > 0);
const bool starved     = (numFibers < coreNum * 1024);

useGeneric   = !extentsMatch && needScatter;

useWarpLast  = (red == NONE) && needScatter && extentsMatch && starved
               && warpKeyFits32 && esize == 4 && numFibers >= 1024;
usePackArb   = (red == NONE) && needScatter && extentsMatch && starved
               && key32 && !useWarpLast;
useWinPass   = (red == NONE) && needScatter && extentsMatch && starved
               && !key32 && !useWarpLast && winnerLinearFits32;
useAtomicEP  = (red == ADD || red == AMIN || red == AMAX || red == MUL)
               && needScatter && extentsMatch && starved;
// 以上全 false ⇒ ① 纤维独占

> ⚠️ **漏掉 `extentsMatch` 是一个已踩过的真实缺陷**：`usePackArb` 少了它，"2 字节 + none + starved" 时快路与通用路径**同时成立**，
> `y` 被重绑到 workspace 视图而通用分支按连续下标写，**输出以 2 倍元素步长整体错位**。
> 公开用例往往一条通用路径都不触发 ⇒ **标准集满分也照样挂隐藏集**。加任何新快路，第一件事是确认它排除了 `!extentsMatch`。
```

`extentsMatch`'s definition, `:42-43`:

```
extentsMatch = ∀i:  indices.size(i) == updates.size(i)
                 && (i == d || indices.size(i) == data.size(i))
```

and why the condition exists at all, `:46-47`:

```
> **合轴只用 `indices` 的 shape**，不是 `data` 的。torch 语义只要求 `index.size(k) ≤ self.size(k)`，
> 非 dim 维 `indices`/`updates` 可以比 `data` 小；用 `data.shape` 合轴会算出错误的 `inner`。
```

So `!extentsMatch` is not an exotic case: torch permits `index` to be smaller than `self` on every
dimension, and whenever it is, `inner` computed from `indices.shape` is no longer the stride the
`data` tensor uses — which is exactly what path ⑥ exists to handle with per-dimension strides. The
fast paths all assume the single shared `inner`, and `extentsMatch` is the predicate that certifies
that assumption.

The field table restates the requirement as a field property,
`scatter/fallback/tiling-fields.md:33`:

```
| `extentsMatch` | bool | 三张量非 dim 维范围是否全等。**四条快路的判据必须全部带它**（详见 tiling-flow §2.2） | 选路 |
```

Path ⑥'s own description in the overview, `scatter/fallback/index.md:27` and `:39`:

```
| ⑥ 通用逐维 stride | 三张量**非 dim 维范围不等** | 按每维独立 stride 还原坐标，仲裁同 ③/④ | 同上 | 同上 | 同上 |
```
```
| `indices`/`updates` 非 dim 维比 `data` 小 | ⑥ 通用路径 | 沿 dim 步长不再是三者通用的 `inner` |
```

and upstream's own assessment of that path's state, `tiling-flow.md:363`:

```
| ⑥ 通用路径完全未调优 | 索引一律 int64、每元素逐维 `%` + `/`、固定 1024 线程 | 可按 rank 编译期特化消掉运行期循环。生产/隐藏用例走这条的比例可能远高于公开用例 |
```

The last clause is the same observation as the defect note, from the other side: the generic path is
under-exercised by public cases and over-represented in production and hidden ones. So the path most
likely to be taken in the field is the one least tested and least optimised, and the guard that
routes to it is the one that was omitted.

Note also `useWinPass`'s extra term `winnerLinearFits32` (`epTotal < 2^32 - 1`, `:102`): if a
`none` case has more than about 4.3 billion update elements and does not qualify for ⑤ or ②, all four
fast predicates are false and the case falls to ① — which is a correct outcome but arrives by
exhaustion rather than by a stated rule. Recorded rather than adjudicated.

## 4 · Procedure
Proposed, runnable later on Ascend950PR — the board upstream names; a 950DT run is a separate claim.
Never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved.

Arm 1 — reproduce the disclosed defect, a poison arm and the point of this entry. Construct the shape
upstream names: 2-byte value, `reduce=none`, `starved` (`numFibers < coreNum × 1024`), and
`!extentsMatch` (indices smaller than data on a non-`dim` dimension). Build two host tilings with one
compiler pin: the correct predicate set, and `usePackArb` with `extentsMatch` removed. md5 both; host
echo of `extentsMatch`, the selected path and the workspace request. Compare output elementwise
against a CPU reference, and — because upstream describes a whole-output displacement — also compute
the cross-correlation of the output against the reference at shifts of ±1, ±2 and ±4 elements, so a
constant displacement is identified as such rather than reported as "all elements wrong".

Arm 2 — the test-set blindness claim. Assemble two case sets: one in which every case has
`extentsMatch = true` (the "public set" analogue) and one that includes `!extentsMatch` cases. Run the
defective build against both and record the pass rate of each. Upstream predicts a full pass on the
first and a failure on the second; that pair, not either number alone, is the finding.

Arm 3 — predicate closure, host only, no device. Enumerate the four fast predicates over a grid of
`(red, esize, starved, extentsMatch, warpKeyFits32, key32, winnerLinearFits32, numFibers)` and check
that no two of `useGeneric`, `useWarpLast`, `usePackArb`, `useWinPass`, `useAtomicEP` are
simultaneously true, and that the disjunction covers every combination (falling to ① where all are
false). This is the mechanical check whose absence let the defect ship.

Refuses to assume: that a free die stays free; that a die may be substituted; that `coreNum` is a
literal (queried, 0141 — `starved` depends on it); that the defect reproduces (arm 1 tests it, and a
non-reproduction is the OVERTURN); that "all elements wrong" and "output displaced" are the same
observation — the shift correlation separates them.

## 5 · Checker — acceptance declared before the run
Verdict variable `defect_reproduced`: true iff the `extentsMatch`-stripped build produces output whose
best cross-correlation against the reference is at a non-zero shift. Declared acceptance: upstream's
disclosure is confirmed iff `defect_reproduced` is true and the best shift is 2 elements. The
OVERTURN fires iff the stripped build produces correct output. Verdict `blindness_confirmed`: true iff
the defective build passes the `extentsMatch`-only case set and fails the mixed set. Verdict
`predicate_exclusive` and `predicate_total` from arm 3, both booleans over the enumerated grid.

The exit code is not the verdict: a displaced output exits 0. Two guards. First, the case set for arm
2 must be shown to contain at least one `!extentsMatch` case — the checker fails red if it does not,
because a set without one cannot distinguish a guarded predicate from an unguarded one, which is the
exact blindness upstream describes and would otherwise be reproduced by this very checker. Second,
arm 3's grid must cover every combination of its eight inputs that is constructible; a partial
enumeration that happened to miss the overlapping region would report `predicate_exclusive = true`
from a check that never looked, and the checker fails on an incomplete grid rather than reporting a
verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The defect, the two-element
displacement and the standard-set/hidden-set observation are upstream's disclosures about their own
implementation on Ascend950PR; this book has reproduced none of them.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. `BOARD: 950PR` records the board upstream's evidence names; the stratum,
not the board field, says who measured. The entry does not establish that the defect reproduces, does
not establish that the displacement is two elements rather than some other stride, and does not
establish that public case sets in general fail to exercise the generic path — upstream states it for
their case set and names neither the set nor its size. It does not establish that the four predicates
are mutually exclusive and total; arm 3 is what would check that, and it has not been run. It does
not cover path ⑥'s own correctness, which upstream separately describes as completely untuned. It
does not address the `winnerLinearFits32` fall-through noted in §3. Nothing here is established for
950DT or for any 910-family board.
