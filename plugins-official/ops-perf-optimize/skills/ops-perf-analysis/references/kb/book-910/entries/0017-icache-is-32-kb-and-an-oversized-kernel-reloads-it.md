```
ID:        0017-icache-is-32-kb-and-an-oversized-kernel-reloads-it
LABEL:     knowledge
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — drafted from one upstream origin; nothing measured, and the architecture the figure applies to is not stated by the source
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-analysis/references/metrics_reference.md:177 — "| ICache | 16K / 32K | 2KB | 代码段缓存，Kernel 过大会频繁加载 |"; ibid:411 — "| ICache | 32KB 限制 | 拆分 TilingKey 或使用模板函数 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an `ICACHELOAD` counter on a named DAV_2201 board stays flat as kernel code size is swept past 32 KB, or rises at a size well below it.
```

# 0017 · ICache is 32 KB and an oversized kernel reloads it

## 1 · Claim
Upstream asserts an instruction cache of 16 K or 32 K with a 2 KB load unit, and separately states
a hard "32KB 限制" whose remedy is splitting the TilingKey or using template functions. Upstream
asserts that frequent `ICACHELOAD` activity means the kernel's code has outgrown the cache. The
architecture these figures apply to is not stated in the source. Not established here.

## 2 · The wrong branch this removes
An agent asked to support many shapes writes one kernel with a large `if/else` or `switch` over
TilingKeys, because a single kernel is simpler to build, test and ship. Code size grows past the
cache and every launch pays repeated instruction fetches — a cost that shows up as SCALAR or
FLOWCTRL time, or as a task duration that does not shrink when the data does. The agent's natural
diagnosis is "small-shape overhead", and the natural fix (fewer cores, bigger tiles) does nothing.
The counter that names the cause, `ICACHELOAD`, is not in the default metric set an agent reads
first.

The reason this entry is `knowledge` and not `trap` despite that: the remedy upstream names
(splitting by TilingKey) has its own cost — more binaries, more dispatch — and the entry's job is
to put the 32 KB number in front of the agent at design time, not to prescribe a fix.

## 3 · Ground / Source
`ops/ascendc-performance-analysis/references/metrics_reference.md` §3.6 缓存结构, lines 175-179:
```
| 缓存 | 大小 | 加载单位 | 说明 |
| ICache | 16K / 32K | 2KB | 代码段缓存，Kernel 过大会频繁加载 |
| DCache | 16K / 32K | 64B (Cache Line) | 数据段缓存（TilingData 等） |
| L2 Cache | 见 3.1 | 128B / 256B / 512B (Cache Line) | 全芯片共享，缓存 GM 数据 |
```
immediately followed at line 181 by: "**ICache 约束**：ICache 硬件规格限制 32KB。如果 Kernel 代码
过大，可通过拆分 TilingKey 或使用模板函数减小代码段。"

Same file §4.3 特殊指标, line 212: "| ICACHELOAD 频繁 | Kernel 代码超出 ICache 容量（32KB），需
简化或拆分 |". §7 硬件约束速查表, line 411: "| ICache | 32KB 限制 | 拆分 TilingKey 或使用模板函数 |".

**An internal tension worth naming**: §3.6 says "16K / 32K" — two values, no rule for which — while
§4.3 and §7 both assert 32 KB flatly. The same ambiguity affects DCache (0018), where it is
sharper because a budget formula divides by it. Neither section says which architecture or which
part takes which value. Filed for DCache as `harvest/contradictions-910.md` C-910-003; for ICache
the practical consequence is smaller (both readings say "split a large kernel") so it is recorded
here rather than as its own row.

**Arch scoping**: §3.6 carries no architecture column and no chip name, unlike §3.1 (which has
910B1/B2 / 910B3 / 950 / 310P3 columns) and §3.5 (whose heading names 910B/950/A2/A3). The
enclosing document is dual-architecture. Under this book's routing rule the mechanism is clearly
910-era-and-later and the entry is carried at `family-claimed(unverified)` with the arch gap
stated in §7 — it is not asserted for DAV_2201 specifically.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. Sweep code size, not data: build one kernel family whose only variation is the number of
   unrolled TilingKey branches, with the executed path identical in every build and the data
   identical. Report the `.text` size of each device binary from the toolchain, so the sweep's
   x-axis is a measured code size and not an assumed one.
3. Per build: `ICACHELOAD` counts, `aic_scalar_ratio`/`aiv_scalar_ratio`, FLOWCTRL time, and task
   duration, five repeats with the first discarded.
4. The executed path must be identical across builds — otherwise the sweep varies two things and
   attributes nothing. Verify by comparing outputs bitwise across builds.

## 5 · Checker — acceptance declared before the run
Verdict variable `icache_knee`: the `.text` size at which `ICACHELOAD` first exceeds three times
its median value over the three smallest builds.
PASS iff `icache_knee` falls in [24 KB, 40 KB] — a window declared now, wide enough to accept
either 32 KB with measurement slop, narrow enough to reject 16 KB.
Red inputs: a knee near 16 KB (which would make §3.6's lower value the operative one and overturn
the 32 KB assertions), or no knee at all across the sweep (INCONCLUSIVE — most likely the counter
is not populated, which must be reported rather than read as "no limit").
The bitwise output comparison from §4 step 4 is a gate, not a metric: if outputs differ across
builds the sweep is VOID, because the code paths were not held constant and the timing difference
has an alternative explanation. Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. **The source states no architecture for this figure** — §3.6
is the one hardware table in that file with no per-chip column — so this entry does not establish
32 KB for DAV_2201 or for any other architecture; it records that upstream asserts it without
scope. It does not resolve 16 K versus 32 K. It does not establish the cost of an ICache miss, nor
whether the 2 KB load unit interacts with code layout. It says nothing about whether AIC and AIV
have separate instruction caches, which matters on a separated-mode part (0008) and which no
source in scope addresses.
