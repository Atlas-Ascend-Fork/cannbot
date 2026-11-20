```
ID:        0031-independent-accumulators-break-the-reduction-raw-chain
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-08-multi-accumulator-unroll.md:13 — "单一累加器 `acc = acc + tmp_i` 的相邻迭代是真依赖，硬件无法乱序/展开，链长 ≈ 归约次数。改成 N 路独立累加器 + 树形归约，链长从 N 降到常数级"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board where four independent accumulators do not reduce
           `aiv_time` against one accumulator at a long reduction axis, with the periodic VECTOR
           bubbles unchanged — the loop-carried dependency would then not be the constraint.
```

# 0031 · Independent accumulators break the reduction RAW chain

## 1 · Claim
Upstream asserts (card vec-08, 性能数据 待实测) that a reduction accumulating into one register
across iterations is a true dependency the hardware cannot reorder, so the chain length equals
the number of iterations; that splitting into N independent accumulators with a tree merge at the
end reduces the chain to a constant and lets N multiplies and the first adds fill the VF
pipeline; and that four accumulators is the common compromise. Not established here.

## 2 · The wrong branch this removes
The signature — periodic VECTOR bubbles with the memory lanes idle — is easy to misread as a
memory stall, because bubbles are usually waiting for data. Here the data is present and the
pipeline is waiting on itself. The card separates this from the neighbouring case explicitly:
`vec-08:9` distinguishes the accumulator RAW chain from register-pressure bubbles, which look
similar in the trace and are repaired by the opposite move (fewer live registers, 0036 — while
this card adds them). An agent that applies the wrong one makes the other worse: unrolling under
register pressure spills, and reducing registers under a dependency chain changes nothing.

## 3 · Ground / Source
`vec-08:6-9` diagnostic: the inner VF loop accumulates into one register across iterations (sum,
dot product); the VECTOR lane shows periodic bubbles from accumulator write-back with the memory
lanes quiet; distinguished from register-pressure bubbles, where the bottleneck is not the chain.

`vec-08:17-31` before/after, with the structure that the stop rules then defend: four
`Duplicate`-zeroed accumulators, a main loop with a *compile-time* step of four and a *runtime*
bound (`i + 4 <= aTimes`), a runtime tail from `aTimes / 4 * 4`, and a three-add tree merge.

Stop rules, `vec-08:40-45`:
> - **循环次数绝不写死成常量**：VF 要对不同 shape 通用，trip count 必须由 shape/tiling 运行期
>   推出。N 路展开 = 「常量步长 N + 运行期主循环界（`i+N<=loops`）+ 运行期尾段」，**不是**把
>   循环展平成 N 条定长直线指令。
> - 展开倍数与归约维耦合：**必须处理归约维尾段**（归约次数 % N ≠ 0 会漏算/越界），或在 tiling
>   侧约束整除。别把「数据维尾段」和「归约维尾段」混为一谈。
> - 多路 + 树形归约**改变浮点累加次序** … 仍需过 `func_cases` 精度回归。
> - 展开倍数过大 → 寄存器翻倍 → 可能 spill 反劣化；寄存器压力大时配合 vec-12。

The first of those is generalised in entry 0032; the third repeats 0030's reordering obligation;
the fourth is the boundary with 0036. Case at `:49`: hc-post A5 multi-accumulator break of a
reduction dependency chain.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one dot-product operator with N ∈ {1, 2, 4, 8} accumulators from a common tree, the
   only difference being N; record `md5sum` of each.
2. Sweep the reduction length `aTimes` over four values spanning 32×, including at least two
   values not divisible by 8 so the runtime tail path is exercised at every N.
3. Capture `aiv_time`, `aiv_vec_ratio`, and — from the instruction trace — the count of
   spill/reload pairs, which is the quantity that should turn the curve at large N.
4. Compare all outputs against a double-precision host reference; record relative error per N.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain(N)` against N=1 and `spills(N)`. Acceptance: `gain(4) > spread`, `gain`
non-decreasing from N=1 to N=4, and — the interesting prediction — `gain(8) <= gain(4)` whenever
`spills(8) > spills(4)`, which ties the diminishing return to its stated cause rather than
asserting it. Correctness gate: every N must be within the dtype threshold of the reference, and
every non-divisible `aTimes` must produce the same value as its divisible neighbour scaled
appropriately — the tail is where this technique loses elements silently.

Exit code is not the verdict. A run whose output differs from the reference by exactly the tail's
contribution is reported as `tail_dropped`, which is a specific diagnosis rather than a generic
precision failure — that mapping is declared now so it cannot be rationalised later.

Red input: N=4 with the runtime tail loop deliberately removed, on a non-divisible `aTimes`. It
must fail the correctness gate. If it passes, the shape set never exercises a tail and no
conclusion about tail handling is admissible.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; 待实测 upstream. Four accumulators is called a common compromise with no
supporting data, and this entry establishes no value of N for any board or shape. It does not
establish the register budget at which unrolling starts to spill — that boundary is what 0036
exists for and is equally unmeasured. Nothing here covers reductions across cores or across
tiles, only the within-VF loop-carried case. Per RULES.md Art. 1, nothing transfers to the 910 book.
