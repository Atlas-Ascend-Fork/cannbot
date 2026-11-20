```
ID:        0045-bypass-l2-only-behind-a-provable-no-reuse-predicate
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-05-l2-bypass-one-shot.md:14 — "流式一次性读填充 L2 会驱逐之后真正要复用的数据。对这样的读取设置 bypass，使数据不填入 L2；但若当前 problem 被拆成多个 M tile、多个 wave 或热点专家会被重复处理，L2 命中本身就是收益来源，bypass 会退化"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-05-l2-bypass-one-shot.md:42 — "该手段优化 cache 污染，不会减少 GM 读字节；带宽本已饱和且无热数据被驱逐时通常无收益"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board where marking a provably one-shot weight stream as
           L2-bypass does not improve `aiv_time` or L2 hit rate for the co-resident hot data —
           the eviction pressure would then not be the mechanism the card claims.
```

# 0045 · Bypass L2 only behind a provable no-reuse predicate

## 1 · Claim
Upstream asserts (card mem-05, evidence: three named arch35 commits, no numbers) that a large
one-shot stream — weights, scales, a single-consumption input block — fills L2 and evicts data
that would otherwise be reused, and that setting a bypass hint on such reads
(`SetL2CacheHint(CacheMode::CACHE_MODE_DISABLE)`) protects the hot working set; that the bypass is
admissible only under a runtime predicate proving no later read of the same physical region, and
degrades when the problem is split across M tiles or waves, or when hot experts recur; that
alignment must be judged on physical layout (950 samples validate against a 128-byte cache line,
ND/NZ and scale strides separately); and that the technique reduces cache pollution, not GM bytes.
Not established here.

## 2 · The wrong branch this removes
The failure this card is written against is not using the hint — it is *how* it gets used. The
easy path is empirical: try bypass on the benchmark cases, keep it where the number improves, and
encode the result as a case-ID or shape whitelist. That produces a kernel that is fast on the
measured set and silently degraded elsewhere, with no way to reason about which. The card's rule
is that the condition must be a predicate computed from tiling and schedule — does one wave cover
the expert from first row to last, is there exactly one M tile, is the physical row stride
cache-line aligned, is the total working set below L2 — and that a whitelist is not a substitute.
That generalisation is entry 0046.

## 3 · Ground / Source
`mem-05:6-10` diagnostic: large weight/scale/input blocks consumed once per problem or tile while
hot data's L2 hits are squeezed by those streaming reads; the absence of a later read of the same
physical region provable at runtime from legal shape/schedule predicates rather than guessed from a
benchmark case; the tensor's physical row stride meeting the API's cache-line alignment requirement.

`mem-05:19-29` after-form: `noLaterReuse = coversWholeProblem && m <= tileM`;
`rowAligned = IsPhysicalRowCacheLineAligned(weightLayout)`; `canBypass = noLaterReuse && rowAligned`;
`gmWeight.SetL2CacheHint(canBypass ? CacheMode::CACHE_MODE_DISABLE : CacheMode::CACHE_MODE_NORMAL);`
`mem-05:31` adds that for wave splitting only a wave covering the expert from first to last row with
a single M tile qualifies, that weight and scale layouts must be judged separately, and that a
general MatMul/QBMM predicate should also include the user switch, whether the whole working set is
below L2, whether `baseM` is fully loaded, the sliding-window block count and the L1 slice alignment.

Stop rules, `mem-05:37-42`: no provable no-reuse predicate, no bypass — routing by case ID, a fixed
shape list or a single profiling result is forbidden; alignment by physical layout, with the 128-byte
cache-line note (0041); keep normal caching when a later M tile, another wave, another core or a
recompute path reads the data; and the technique does not reduce GM read bytes at all.

The enumerator itself is corroborated by the installed headers and recorded separately as 0047,
which also records that the enum has four modes where this card names two.

## 4 · Procedure
Later phase, needs a card; device selection per 0010, board token from the driver readout.
1. Build one MatMul-with-weights operator two ways from a common tree: (N) all reads
   `CACHE_MODE_NORMAL`; (B) weight stream `CACHE_MODE_DISABLE` under the predicate. Record
   `md5sum` of both.
2. Run each in two regimes: (I) one wave, one M tile, weights read exactly once — the predicate
   holds; (II) the same problem split into four M tiles so the weights are re-read — the predicate
   fails and B must fall back to normal.
3. Capture `aiv_time`, L2 hit rate and DDR traffic if counters are available; five repetitions,
   median and spread.
4. Force build B to bypass in regime II regardless of the predicate, as a third variant (B!), to
   measure the degradation the predicate exists to prevent.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain(regime)`, `l2_hit(build, regime)`, `ddr_bytes(build, regime)`. Acceptance:
in regime I, `gain > spread` and `l2_hit(B) > l2_hit(N)` for the hot data; in regime II,
`gain ≈ 0` because B falls back; and `ddr_bytes(B) ≈ ddr_bytes(N)` in both regimes, since the card
states GM traffic is unchanged — a bypass that reduces DDR bytes is doing something other than what
is claimed.

Exit code is not the verdict. Which cache mode was actually set is recorded from the build and
asserted against the predicate's value per regime; a fallback that silently did not happen would
otherwise be invisible.

Red input: variant B! in regime II. It must be *slower* than N. If it is not, this operator has no
L2 reuse to lose and the whole comparison is uninformative — reported as `no_reuse_pressure`
rather than as a licence to bypass unconditionally.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured, by us or upstream. No board, no L2 capacity — this book has not established the
L2 size for any 950 board, and the register's C-002 row records a disagreement about a related
capacity. The 128-byte cache line is asserted from "950 historical samples" and is not verified.
It does not establish the predicate for any operator beyond the two sketched, nor the cost of
evaluating it. Nothing here covers the other two cache modes (0047).
