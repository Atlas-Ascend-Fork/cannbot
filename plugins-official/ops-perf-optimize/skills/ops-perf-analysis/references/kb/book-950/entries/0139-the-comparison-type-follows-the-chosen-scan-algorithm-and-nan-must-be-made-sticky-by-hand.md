```
ID:        0139-the-comparison-type-follows-the-chosen-scan-algorithm-and-nan-must-be-made-sticky-by-hand
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scan/fallback/tiling-flow.md:88-98,320-321,
           327-343 — "③ 比较类型取什么 —— 取决于 ② 选了哪个算法，不能一概而论" · "16 位的
           DataCopyGather/Scatter 没有全速路径，实测同元素数下 fp16 比 fp32 慢 1.6~1.9 倍；升 fp32
           后 gather 走 32 位快速路径，反超 1.6 倍" · "int16→int64 一步 Cast 编译得过但结果错" ·
           "NaN | **必须显式判**，不能指望 `Compare` 的默认行为"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured 16-bit lane-parallel scan on a named 950 board that matches or beats the
           promoted-fp32 path at the same element count — the "no full-speed 16-bit gather path"
           assertion would then not hold, and the promotion rule with it.
```

# 0139 · The comparison type follows the chosen scan algorithm, and NaN must be made sticky by hand

## 1 · Claim
Upstream asserts that the comparison type in an indexed scan is not a free choice and not a
per-dtype rule, but a consequence of which UB scan algorithm was selected. On the lane-parallel
path the comparison type must be the promoted 4-byte type, because 16-bit
`DataCopyGather`/`DataCopyScatter` have no full-speed path — upstream states that at equal element
count fp16 measures 1.6–1.9× slower than fp32, and that promoting to fp32 puts the gather on the
32-bit fast path for a 1.6× reversal. On the Kogge-Stone path 16-bit comparison is native with 128
lanes per vector register and measures 1.5× faster than promoting, at the cost that the index stays
int32 and the mask must be split with `UnPack<LOWEST/HIGHEST>` to drive the index-side `Select`.
Where a scalar read-back of the carry is needed the promoted type is mandatory because the compiler
does not support 16-bit scalar comparison. Upstream asserts that index width follows the comparison
type so that equal widths avoid mask splitting, and that `int16→int64` in one `Cast` compiles but
produces wrong results. Upstream separately asserts that NaN must be handled with an explicit
predicate rather than relying on `Compare`'s default, and that ties resolve to the last occurrence
via `CMPMODE::LE` for min and `GE` for max. Not established here.

## 2 · The wrong branch this removes
The wrong branch is "use the operand dtype" or its opposite, "always promote". Upstream's point is
that neither is a rule: the same operator at the same dtype wants a different comparison type
depending on whether R was large enough to select lane-parallel scanning. An agent that promotes
uniformly pays 1.5× on every small-R Kogge-Stone case; an agent that keeps 16-bit uniformly pays
1.6–1.9× on every lane-parallel case and then has to split masks anyway. And the third arm — scalar
carry read-back — does not fail slowly, it fails to compile, so an agent that reasons only about
speed will hit it as a build error with no obvious cause.

The `int16→int64` note removes a worse branch: a conversion that compiles and produces wrong
numbers. Nothing catches it but an elementwise comparison.

The NaN rule removes the most expensive one. `Compare<LE>(x, cur)` alone is not enough because
`(real <= NaN)` is false, so a NaN already captured in the running state gets "recovered" back to a
later real value. On a benchmark whose generator mixes NaN with reals — upstream names
`value_range=["nan","nan"]` in cann-bench as producing exactly that — the operator returns plausible
finite numbers and fails precision. The fix costs one extra comparison and one `Or`, and upstream
notes the merged mask also saves a `Select` on both value and index, so it is cheaper than the
two-mask alternative.

## 3 · Ground / Source
The three-way dependency, `scan/fallback/tiling-flow.md:88-98`, in full:

```
③ 比较类型取什么 —— 取决于 ② 选了哪个算法，不能一概而论
   走 lane 并行     → 一律用促进类型 P（4 字节）。16 位的 DataCopyGather/Scatter
                      没有全速路径，实测同元素数下 fp16 比 fp32 慢 1.6~1.9 倍；
                      升 fp32 后 gather 走 32 位快速路径，反超 1.6 倍
   走 Kogge-Stone   → 16 位可原生比较，每 vreg 128 lane，实测比升 fp32 快 1.5 倍；
                      但索引仍是 int32，需 UnPack<LOWEST/HIGHEST> 拆掩码驱动索引侧 Select
   需标量回读进位   → 必须用 P（编译器不支持 16 位标量比较）

   ↑ 索引宽度跟着比较类型走（等宽才不用拆掩码）。走 lane 并行时比较类型恒为 4 字节，
     故索引恒为 int32、出口一步 Cast 到 int64；int16→int64 一步 Cast 编译得过但结果错
```

The tie and NaN rules, `:320-321`:

```
| 并列 tie（Cummin/Cummax） | **last occurrence**（对齐 torch）：min 直接用 `CMPMODE::LE`（`x <= cur` 即取更晚的），max 用 `GE`。写成 `GT`/`LT` 再回头修正只会多一条指令 |
| NaN | **必须显式判**，不能指望 `Compare` 的默认行为。见 §8.1 |
```

The NaN mechanism, `:327-343`, in full:

```
### 8.1 NaN 必须显式粘滞（精度失败的头号原因）

cann-bench 的 `value_range=["nan","nan"]` 生成的是 **NaN 与实数混合**的输入。
只写一路 `Compare<LE>(x, cur)` 不够：`(实数 <= NaN)` 为 false，会把已经取到的 NaN
"恢复"成后面的实数。正解是再加一路判 NaN 并 `Or` 成一个掩码：

leMask  = (x <= cur)        # LE 直接实现 last-occurrence
nanMask = (x != x)          # 判 NaN
takeB   = leMask | nanMask  # 合并成一个掩码，值和索引各省一条 Select
cur     = takeB ? x : cur
idx     = takeB ? r : idx

`Or` 合并掩码还有个附带好处：16 位比较配 32 位索引时只需拆一次掩码而不是两次。

1. **并列语义**：`LE`/`GE` 配合上面的掩码合并直接得到 torch 的 last occurrence。
```

The algorithm selection that decision ③ depends on, `:84-86` and `:194-197`, is 0134's and 0138's
subject; the operative point here is that `R > 2*VLC` (or `R > 2*guardC`) selects lane-parallel and
therefore forces the 4-byte comparison type, so a threshold on `R` propagates into a numerics
decision.

Four unconditioned measurements appear in this passage: `1.6~1.9 倍`, `反超 1.6 倍`, `快 1.5 倍`,
and `每 vreg 128 lane` (a structural claim, not a measurement, and consistent with the 256-byte
register of 0138 at 2 bytes per element). None of the three ratios carries a board, shape, core
count, tool or repetition count, and the first is a range.

Two claims here are about the toolchain rather than the hardware and are worth separating for that
reason: `编译器不支持 16 位标量比较` and `int16→int64 一步 Cast 编译得过但结果错`. Both are
compiler-version-scoped statements with no version given, so they are pinned to nothing.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs;
report the interquartile range over the median.

Arm 1 — the gather-path claim. Fix a Cummin with `N == 1`, `M` large enough to fill the machine, and
`R` large enough to select lane-parallel. Build four kernels with one compiler pin, recording the
pin: fp16 operand with 16-bit comparison; fp16 operand promoted to fp32 comparison; fp32 operand
native; and the same fp16-promoted build at Kogge-Stone-selecting R. md5 all four. Host echo of
`mode`, `gsS`, `cBytes` and the comparison type actually compiled. Compare at *equal element count*,
which is the comparison upstream states — not equal bytes — and record `aiv_time` plus MTE2 bytes
under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

Arm 2 — the Kogge-Stone reversal. Fix `R` below the lane-parallel threshold and build 16-bit-native
against promoted-fp32, same protocol. Upstream predicts the ordering flips between arms 1 and 2;
that flip, not either ratio alone, is the claim.

Arm 3 — NaN stickiness, a correctness arm with a poison variant. Generate input mixing NaN with
reals as cann-bench's `value_range=["nan","nan"]` does. Build two kernels: `leMask` only, and
`leMask | nanMask`. Compare both elementwise against a CPU reference implementing torch semantics
(NaN sticky, ties to last occurrence). The `leMask`-only arm is expected to be wrong and is retained
in the report whether or not it bites; the fraction of wrong elements and the first wrong index are
recorded.

Arm 4 — the two toolchain claims, build-only, no device needed. Attempt a 16-bit scalar comparison
and attempt `int16→int64` in one `Cast`; record whether each compiles, and for the second, whether
the result matches a two-step conversion elementwise. Record the compiler version — these claims are
pinned to nothing upstream and this arm is what pins them.

Refuses to assume: that a free die stays free; that a die may be substituted; that "equal element
count" and "equal bytes" give the same comparison — only the first is upstream's claim and only it
is measured; that a build that compiles is correct (arm 4's second half exists because upstream says
it is not); that the compiler in reach is the compiler upstream used.

## 5 · Checker — acceptance declared before the run
Verdict variables `lane_ratio` (fp16-16bit / fp16-promoted median `aiv_time` on the lane-parallel
arm) and `ks_ratio` (fp16-16bit / fp16-promoted on the Kogge-Stone arm), each reported with the
variance floor. Declared before the run: upstream's rule is supported iff `lane_ratio > 1.3` and
`ks_ratio < 0.8` — i.e. promotion wins on lane-parallel and loses on Kogge-Stone. The OVERTURN
fires iff `lane_ratio ≤ 1 + variance_floor`. Verdict variable `nan_wrong_fraction(arm)`: the rule is
supported iff the merged-mask arm is 0 and the `leMask`-only arm is greater than 0.
`cast_correct` and `scalar16_compiles` are booleans from arm 4, reported with the compiler version.

The exit code is not the verdict, and here it is doubly misleading: a wrong-NaN kernel exits 0, and
a broken `int16→int64` Cast compiles and exits 0. The instruments are the elementwise comparisons.
Two guards. First, comparison-type identity: the host echo of `cBytes` must differ between the two
arms of arms 1 and 2 — if the toolchain promoted both, the ratio is 1.00 from one experiment run
twice, which would read as a clean overturn. Second, the NaN reference must itself be checked: the
CPU reference is validated against a known torch result on a small hand-computed case before it is
used to judge the device output, because a reference with the wrong tie or NaN policy would score
the correct kernel as broken.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The 1.6–1.9×, 1.6× and 1.5×
figures are upstream's, all unconditioned.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish any of the three ratios, does not establish that
16-bit gather lacks a full-speed path, and does not establish the 128-lanes-per-register figure. It
does not establish the two toolchain claims — no compiler version is given upstream, so they are
scoped to nothing and §4 arm 4 is what would scope them. It does not establish that last-occurrence
ties match torch on any version of torch; upstream asserts the alignment and this book has not
checked it. It does not cover the un-indexed operators, which have no comparison type. The
`UnPack<LOWEST/HIGHEST>` mask-splitting requirement is recorded, not verified. No chip is named
anywhere in the scan family, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT because
that is where our run would happen. Nothing here is established for any 910-family board.
