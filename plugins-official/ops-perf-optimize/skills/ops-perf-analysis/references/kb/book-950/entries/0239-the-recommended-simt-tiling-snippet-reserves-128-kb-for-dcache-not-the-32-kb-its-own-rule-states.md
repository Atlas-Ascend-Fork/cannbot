```
ID:        0239-the-recommended-simt-tiling-snippet-reserves-128-kb-for-dcache-not-the-32-kb-its-own-rule-states
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — the discrepancy is visible by reading two adjacent passages in each of two
           upstream files; both files are `upstream/skills-dev-main`, ONE origin. Nothing was
           compiled and no allocation was attempted.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/simt-arch-guide.md:130-142 — rule "- **SIMT 算子不能使用全部 UB
           空间**，需为 DCache 预留 ≥32KB / - 若 DCache < 32KB，编译校验报错 / - 可用 UB = 256KB - 8KB
           - 32KB = **216KB**" followed nine lines later by
           "constexpr uint64_t DCACHE_SIZE = 128 * 1024;  uint64_t ubsize = 256 * 1024;
            context->SetLocalMemorySize(ubsize - DCACHE_SIZE);"
SOURCE:    ops/ascendc-simt-tiling-design/references/guide.md:63-73 — the same rule and the same
           snippet in the same order, with the 216 KB line placed AFTER the snippet.
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a 950 run showing that a 32 KB DCache performs within run variance of a 128 KB DCache on
           a discrete-access SIMT kernel — the snippet's reservation would then be pure waste rather
           than an unstated recommendation, and the discrepancy is an editing defect only.
```

# 0239 · The recommended SIMT tiling snippet reserves 128 KB for DCache, not the 32 KB its own rule states

## 1 · Claim
Upstream asserts that a SIMT operator must leave at least 32 KB of UB to DCache and that the usable
budget is therefore 216 KB (0237, 0238). Upstream then supplies, as the recommended tiling-side
setting, a code snippet that reserves `DCACHE_SIZE = 128 * 1024` — four times the stated minimum,
leaving 128 KB usable rather than 216. The rule and the snippet appear in the same section of the same
file, nine lines apart, in both places upstream states them. Not established here: nothing was
compiled and no allocation was attempted.

## 2 · The wrong branch this removes
An agent copies the snippet. That is what snippets are for, and this one is presented under the
heading "Tiling 侧设置" as the way to do it. Having copied it, the agent has a tiling routine that
budgets 128 KB of UB while the prose two lines above told it 216 KB — and it will size its buffers
from whichever of the two it happened to internalise.

Both directions are wrong and only one is loud. Sizing buffers for 216 KB while `SetLocalMemorySize`
was called with 128 KB means the dynamic allocation exceeds what was requested: either the allocation
fails, or (under 0237's residual partition) it eats the DCache that the same call was reserving.
Sizing for 128 KB when 216 KB was available means a SIMT kernel running at 59 % of its buffer budget
forever, with nothing in any profile pointing at a constant in a host-side tiling function.

The deeper reason this is a `trap` and not a documentation nit: **the rule is stated and then violated
in executable code within the same screenful.** A reader who checks the rule against the example finds
them disagreeing and has no basis to choose — the prose is normative, the code is operational, and
neither is marked as the exception. This is the failure species where a rule and its violation live in
the same artifact, and the repair is placement, not diligence: whichever value is right, the snippet
and the sentence must be generated from one source.

There is a real possibility the snippet is right and the prose is incomplete: 32 KB is stated as a
*minimum*, and `npu-arch-guide.md:305` gives the DCache *maximum* as 128 KB. A snippet reserving the
maximum would be a defensible default for discrete-access kernels — which is the whole point of SIMT
— and nobody wrote down that it was a recommendation rather than the rule. That reading is a
hypothesis, and §4 is built to test it rather than to assume it.

## 3 · Ground / Source
`npu-arch/references/simt-arch-guide.md:128-142`, the two passages in their actual proximity — the
adjacency is the finding, so it is quoted unbroken:

> ### 关键约束
>
> - **SIMT 算子不能使用全部 UB 空间**，需为 DCache 预留 ≥32KB
> - 若 DCache < 32KB，编译校验报错
> - 可用 UB = 256KB - 8KB - 32KB = **216KB**
>
> ### Tiling 侧设置
>
> 定义 `DCACHE_SIZE` 为 128KB，使用 `SetLocalMemorySize` 设置参数为 `ubsize - DCACHE_SIZE`：
>
> ```cpp
> constexpr uint64_t DCACHE_SIZE = 128 * 1024;
> uint64_t ubsize = 256 * 1024;
> context->SetLocalMemorySize(ubsize - DCACHE_SIZE);
> ```

Nine lines separate "≥32KB … = **216KB**" from a call that yields 128 KB. The prose introducing the
snippet — "定义 `DCACHE_SIZE` 为 128KB" — states the 128 KB deliberately, so this is not a transcription
slip in the code block; the text and the code agree with each other and disagree with the rule above
them.

`ascendc-simt-tiling-design/references/guide.md:63-73` reproduces the same pair, with the ordering
reversed so the 216 KB line lands *after* the snippet:

> ## DCache 与 UB 空间设置
>
> SIMT 算子不能使用全部 UB 空间，需为 DCache 预留 >=32KB：
>
> ```cpp
> constexpr uint64_t DCACHE_SIZE = 128 * 1024;
> uint64_t ubsize = 256 * 1024;
> context->SetLocalMemorySize(ubsize - DCACHE_SIZE);
> ```
>
> 可用 UB = 256KB - 8KB(预留) - 32KB(DCache最低) = **216KB**

Here the snippet sits *between* the rule and the arithmetic, which is worse for a reader: the 216 KB
conclusion reads as though it followed from the code immediately above it, and it does not.

Both files are `upstream/skills-dev-main` — one origin (RULES.md Art. 3). That the same pairing survives in
two skills suggests a shared ancestor rather than two independent errors, which matters for the repair:
fixing the instances would leave the generator intact.

The maximum that would license the snippet, `npu-arch-guide.md:305`: "SIMT DCache（最大 128KB，复用 UB
作 Cacheline，128B 粒度）[¹](#unverified)". So 128 KB is a real figure in this material — it is the
ceiling, marked by upstream as a public-or-experience value with no ini field (0206 row 2). The snippet
reserves the ceiling; the rule states the floor; nothing says which a tiling routine should pick.

Compounding it, both snippets start from `ubsize = 256 * 1024`, which no installed 950 ini reports
(0209, 0238). So the snippet is not merely reserving four times the minimum — it is doing so from a
base 8 KB larger than the part has, and the two errors do not cancel.

Filed as `C-950arch-007` in `harvest/contradictions-950-arch.md`.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion. The question
is not which document to believe — it is what a DCache reservation is worth, which no document
answers.

Arm A — the value curve, which is the arm that decides whether the snippet is a recommendation or a
mistake. Build one SIMT kernel with genuinely discrete GM access — a gather over a shuffled index
vector, working set several times the DCache, so the cache is exercised rather than streamed — and run
it with the DCache residual set to 32, 64, 96 and 128 KB by varying `SetLocalMemorySize` against a
fixed static allocation. Same shape, same die, same session. Record minimum `aiv_time` over 50
repetitions at each point.

If the curve is flat, the snippet wastes 96 KB of buffer for nothing and this entry's §2 second
reading is dead. If it rises steeply toward 32 KB, the snippet is sound and the *rule* is what needs a
sentence added.

Arm B — the cost side of the same trade, which Arm A alone cannot see. The reservation is only free if
the kernel does not need the buffer. Repeat Arm A with a kernel whose tiling genuinely consumes the
available UB (a blocked reduction with a large live footprint), so that a larger DCache forces smaller
tiles and more iterations. Record `aiv_time` against the same four residuals. The two curves together
are the trade; either alone is half of it.

Arm C — the base-constant arm, which tests the second defect in §3. Run the snippet verbatim —
`ubsize = 256 * 1024`, `DCACHE_SIZE = 128 * 1024` — on a part whose `GetCoreMemSize(UB)` returns
253952, and record whether `SetLocalMemorySize(131072)` is accepted, and what the resulting DCache
residual actually is. The snippet requests 128 KB of local memory out of a 248 KB buffer, so the
residual is 120 KB, not 128. Whether anything notices is the question.

Arm D — the interaction with 0237's compile check. Drive the residual to 31 KB by the same route and
confirm the check fires, establishing that the two entries are testing the same mechanism.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All four residuals of one curve run on one
named die in one session — a curve assembled across dies attributes nothing.

## 5 · Checker — acceptance declared before the run
Verdict variable `dcache_curve_slope` from Arm A: the ratio `aiv_time(32 KB) / aiv_time(128 KB)`, with
run variance reported beside it.

The outcomes are named now so neither can be reinterpreted afterwards. A ratio above 1.10 outside
variance means the 128 KB reservation buys real throughput on discrete-access kernels, the snippet is a
defensible default, and the defect is that the *rule* never says so — this entry stands, restated as a
missing-recommendation trap. A ratio within variance of 1.0 means the reservation is waste, and the
defect is the snippet — this entry stands as written. Either way the entry stands; what changes is
which half upstream must fix, and saying that now prevents the run being read as vindication of
whichever answer arrives.

`tradeoff_crossover` from Arm B — the residual at which Arm B's curve overtakes Arm A's benefit. No
pass threshold; it is the number a tiling routine would actually need and no source in this scope
supplies it.

`snippet_residual_bytes` from Arm C — pass iff the observed residual equals `GetCoreMemSize(UB)` minus
131072, i.e. 120 KB rather than the 128 KB the snippet's author intended. This is the verdict that
demonstrates the base-constant error has a consequence rather than being cosmetic.

The positive fixture, declared before the run: run Arm A with the gather's index vector replaced by a
strictly sequential index. The curve **must** flatten, because a streaming access pattern does not
exercise DCache. If the slope survives that substitution, Arm A is measuring something other than
cache residency — capacity pressure on the tiling, most likely — and every `dcache_curve_slope` value
is void. Without this, the checker only reads "times differed across four builds", which is the known
blind species.

Process exit code is not the verdict for any arm; in Arm D a refused build is the expected outcome.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no
`SetLocalMemorySize` was called, and no DCache residual was observed. §3 is a read of two upstream
files; reading a rule beside a snippet that contradicts it does not establish which is right.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish whether 32 KB or 128 KB is the right
reservation — that is §4's whole content and it is open. It does not establish that the snippet is an
error: §2 records a live reading in which it is a sound default for discrete-access kernels and the
rule is merely silent about it, and this entry deliberately does not choose. It does not establish the
128 KB DCache maximum, which upstream marks as a public-or-experience value with no ini field (0206),
nor the 8 KB compiler reservation. There is **no second origin**: both quoted files are one repo, and
the installed toolkit says nothing about DCache. It does not adjudicate the `ubsize = 256 * 1024` base
— that is 0238 — though Arm C measures one consequence of it. It says nothing about whether
`SetLocalMemorySize` accepts a value larger than the physical UB, nor what it does if so. It says
nothing about mixed SIMD/SIMT kernels, where 0238 records a different budget entirely. Nothing
transfers to the other book (RULES.md Art. 1): SIMT is a DAV_3510-era model per upstream.
