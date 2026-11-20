```
ID:        0237-a-simt-kernel-must-leave-at-least-32-kb-of-ub-to-dcache-or-the-build-is-rejected
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — two upstream skills state the rule, both `upstream/skills-dev-main`,
           therefore ONE origin (RULES.md Art. 3). The DCache itself is marked by upstream as a
           public-or-experience value with no ini field (0206 row 2). Nothing was compiled.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/simt-arch-guide.md:117-132 — "Unified Buffer 总量 **256KB**，
           从低地址到高地址依次分区：| 静态内存 | 编译期确定 | … | 预留空间 | 固定 8KB | 编译器预留，
           不可使用 | | Data Cache | = 256KB - 静态 - 动态 - 8KB | SIMT 专有 DCache |" …
           "- **SIMT 算子不能使用全部 UB 空间**，需为 DCache 预留 ≥32KB / - 若 DCache < 32KB，编译校验报错"
SOURCE:    ops/ascendc-simt-tiling-design/references/guide.md:63-73 — "SIMT 算子不能使用全部 UB 空间，
           需为 DCache 预留 >=32KB" … "可用 UB = 256KB - 8KB(预留) - 32KB(DCache最低) = **216KB**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a SIMT kernel that compiles and runs correctly with `SetLocalMemorySize` leaving under
           32 KB for DCache — the 编译校验 either does not exist or does not fire.
```

# 0237 · A SIMT kernel must leave at least 32 KB of UB to DCache, or the build is rejected

## 1 · Claim
Upstream asserts that the Unified Buffer on a SIMT-capable core is divided, from low address to high,
into static memory (compile-time `__ubuf__` arrays), dynamic memory (set on the tiling side via
`SetLocalMemory`, or via `dynUBufSize` in a `<<<>>>` launch), a fixed **8 KB** compiler reservation
that is not usable, and whatever remains, which becomes the SIMT-only Data Cache. Upstream asserts
that a SIMT operator may not consume all of UB: at least **32 KB** must remain for DCache, and if
DCache falls below 32 KB the compile-time check reports an error. Not established here: nothing was
compiled and the check was never made to fire.

## 2 · The wrong branch this removes
DCache is what makes SIMT's defining capability work — direct discrete GM access from a thread,
without staging through UB (0243). It is not a nice-to-have buffer; it is the cache line behind every
`__gm__` dereference in a SIMT VF. An agent that treats UB as a budget to be filled, which is exactly
the correct instinct for a SIMD kernel, allocates the whole thing and starves the mechanism it is
relying on.

Upstream says a build check catches this. If that check exists and fires, the failure is loud and this
entry is merely useful. If it does not — or fires only for the static path and not for a
`SetLocalMemorySize` computed at runtime on the host — then the failure is a SIMT kernel with a
few-kilobyte DCache, correct output, and GM access latency that no profile attributes to a partition
decision made in tiling. That asymmetry is why this is filed as a `trap` rather than as `knowledge`,
and why §4 spends its effort on making the check fire rather than on confirming the number.

The second branch is arithmetic and appears in upstream's own documents. The usable figure of 216 KB
is derived as 256 − 8 − 32. The installed ini reports `ub_size = 253952` (248 KB) for every DAV_3510
SKU (0209), and 248 − 8 − 32 = 208, not 216. Whichever base is right, an agent that copies 216 KB and
an agent that copies the subtraction will disagree by 8 KB, and one of them will overflow. That
disagreement is carried separately as 0238; this entry claims only the reservation rule.

## 3 · Ground / Source
`npu-arch/references/simt-arch-guide.md:115-142`, the UB partition section quoted whole, because the
partition and the rule and the sample code are one unit and the reader needs all three:

> ## UB 内存分区
> ### 总量
> Unified Buffer 总量 **256KB**，从低地址到高地址依次分区：
>
> | 区域 | 大小 | 说明 |
> |------|------|------|
> | 静态内存 | 编译期确定 | `__ubuf__` 数组声明，混合编程中用于 SIMD/SIMT 共享数据 |
> | 动态内存 | tiling 侧 `SetLocalMemory` 设置 | TBuf/LocalTensor 申请，混合编程中通过 `<<<>>>` 的 dynUBufSize 指定 |
> | 预留空间 | 固定 8KB | 编译器预留，不可使用 |
> | Data Cache | = 256KB - 静态 - 动态 - 8KB | SIMT 专有 DCache |
>
> ### 关键约束
> - **SIMT 算子不能使用全部 UB 空间**，需为 DCache 预留 ≥32KB
> - 若 DCache < 32KB，编译校验报错
> - 可用 UB = 256KB - 8KB - 32KB = **216KB**
>
> ### Tiling 侧设置
> 定义 `DCACHE_SIZE` 为 128KB，使用 `SetLocalMemorySize` 设置参数为 `ubsize - DCACHE_SIZE`：
> ```cpp
> constexpr uint64_t DCACHE_SIZE = 128 * 1024;
> uint64_t ubsize = 256 * 1024;
> context->SetLocalMemorySize(ubsize - DCACHE_SIZE);
> ```

The partition is a *residual* definition, and that is the load-bearing detail: DCache is not
allocated, it is what is left. So the rule "reserve ≥32 KB" is not something a kernel does — it is a
constraint on what static and dynamic memory may jointly consume. An agent looking for an API to
reserve DCache will not find one, because the reservation is expressed by *not* allocating.

The sample code immediately below the rule reserves 128 KB, not 32 KB, which is four times the stated
minimum and leaves 128 KB usable rather than 216. That is 0239.

`ascendc-simt-tiling-design/references/guide.md:63-73` restates the rule with the same arithmetic:

> ## DCache 与 UB 空间设置
> SIMT 算子不能使用全部 UB 空间，需为 DCache 预留 >=32KB：
> ```cpp
> constexpr uint64_t DCACHE_SIZE = 128 * 1024;
> uint64_t ubsize = 256 * 1024;
> context->SetLocalMemorySize(ubsize - DCACHE_SIZE);
> ```
> 可用 UB = 256KB - 8KB(预留) - 32KB(DCache最低) = **216KB**

and its `SKILL.md:19` compresses it into a comparison row: "| UB 使用 | 全量使用 | 仅核内共享场景使用，
DCache >= 32KB |" — SIMD uses all of UB, SIMT uses it only for intra-core sharing. Both files are
`upstream/skills-dev-main`, so this is **one origin** (RULES.md Art. 3), not two.

What DCache is, from `npu-arch-guide.md:305`: "SIMT DCache（最大 128KB，复用 UB 作 Cacheline，128B
粒度）[¹](#unverified)" — it reuses UB storage as cache lines at 128-byte granularity, with a maximum
of 128 KB. The `[¹]` marks it as a public-or-experience value; `npu-hardware-params.md:167` is row 2
of the table 0206 records. A `grep` over the installed CANN 9.0.0-beta.2 ini set for `dcache` and
`cache_line` returned nothing, which agrees with upstream's statement and establishes nothing.

Note the two figures now in play: a **minimum** reservation of 32 KB and a **maximum** DCache of
128 KB. Nothing upstream in this scope says what a DCache between those bounds buys, which is exactly
what a tiling routine would need to choose a value.

## 4 · Procedure
Runnable later on `950PR`; the decisive arm needs no device and runs first.

Arm A — make the check fire, compile only. Build a SIMT kernel four times with the DCache residual
driven to 64 KB, 32 KB, 31 KB and 0 KB by varying `SetLocalMemorySize` against a fixed static
allocation. Record for each: does it compile, and if not, does the diagnostic name DCache or the 32 KB
minimum. Upstream predicts the 31 KB and 0 KB builds fail. A clean compile at 0 KB is the important
outcome and is the reason this arm is not skippable.

Arm B — the host/device split, which is where a check most plausibly has a hole. Repeat Arm A with the
residual driven not by a compile-time constant but by a host-side computation whose value is unknown
until tiling runs. A compile-time check cannot see a runtime value, so if upstream's 编译校验 is the
only guard, this configuration passes the build and reaches the device under-provisioned. Record what
happens at launch.

Arm C — the consequence arm, on the board, which prices the reservation rather than confirming it.
Build one SIMT kernel with genuinely discrete GM access (a gather over a shuffled index vector, so
DCache is exercised rather than streamed) and run it at DCache residuals of 32 KB, 64 KB and 128 KB,
same shape, same die, same session. Record `aiv_time` for each. This is the arm that would tell a
tiling routine what a larger DCache is worth — the question §3 notes upstream never answers.

Arm D — the granularity arm, if Arm C shows a signal. Repeat the gather with the index stride swept
across 64 B, 128 B and 256 B. Upstream states a 128 B cache-line granularity; a knee at 128 B would be
consistent with it, and its absence would mean Arm C's differences come from capacity rather than from
line structure.

Device selection is explicit for Arms C and D: the operator names the device index, the probe prints
it back with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run
(shared machine, ≤4 dies), and no die is substituted for another. Arms C and D's points run on one
named die in one session, or their comparison attributes nothing.

## 5 · Checker — acceptance declared before the run
Three verdict variables, never aggregated.

`check_fires` (Arm A) — pass iff the 31 KB and 0 KB builds fail **and** at least one diagnostic names
DCache or the minimum. A build that fails for an unrelated reason is recorded as
`NOT ESTABLISHED`, not as a pass: the checker matches diagnostic text, not exit status, because "it
did not compile" and "it did not compile for the stated reason" are different results.

`check_covers_runtime` (Arm B) — pass iff the runtime-driven under-provision is also refused, at build
or at launch. A clean run here does **not** fail this entry; it records that the guard is
compile-time-only, which is the more useful result and is the finding the delivered skill would have to carry.

`dcache_value` (Arm C) — reported as `aiv_time` per residual with run variance, no pass threshold,
because this variable prices the reservation rather than testing it. A difference smaller than the
observed variance is reported as "below variance", never as zero.

The positive fixture, declared before the run: Arm A must be shown to go red on an input whose answer
is known — build the 64 KB variant with the static `__ubuf__` array enlarged by 40 KB, driving the
residual below 32 KB by a different route. It must fail with the same diagnostic. If it compiles, the
check is watching only `SetLocalMemorySize` and not the actual residual, and every `check_fires`
verdict is void. Without this the checker only reads "some builds failed", which is the known blind
species.

Process exit codes are not the verdict anywhere: in Arm A a non-zero exit is the expected outcome for
two of the four builds.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no
check was made to fire, and no device was contacted. The ini search reported in §3 found no DCache or
cache-line field; a search that finds nothing establishes nothing, and it is recorded only because it
agrees with upstream's own statement that no such field exists.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that the 编译校验 exists, that it fires, or
that it covers a residual computed at runtime — Arms A and B are open and the runtime hole in §2 is
the branch with no detector. It does not establish the 8 KB compiler reservation or the 128 KB DCache
maximum; both are upstream assertions and upstream marks the DCache figures as public-or-experience
values with no ini field (0206). There is **no second origin**: both quoted files are one repo, and
the installed toolkit supplies nothing here. It does not adjudicate the UB total the arithmetic starts
from — upstream says 256 KB, the installed ini says 248 KB for every DAV_3510 SKU (0209), and that
conflict is 0238, deliberately kept out of this entry so the reservation rule can stand or fall on its
own. It does not establish what DCache size is *good*, only what upstream says is minimal; §4 Arm C
exists because no source in this scope answers that. It says nothing about mixed SIMD/SIMT kernels
beyond the partition table's mention of shared static memory, and nothing about how DCache interacts
with warp count (0234) or per-thread registers (0236). Nothing transfers to the other book (RULES.md
Art. 1): upstream states SIMT hardware does not exist before DAV_3510.
