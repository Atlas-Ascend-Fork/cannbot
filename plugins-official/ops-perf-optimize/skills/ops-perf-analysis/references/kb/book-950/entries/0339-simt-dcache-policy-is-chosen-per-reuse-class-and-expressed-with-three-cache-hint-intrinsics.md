```
ID:        0339-simt-dcache-policy-is-chosen-per-reuse-class-and-expressed-with-three-cache-hint-intrinsics
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   corroborated — the API surface and its lowering, only. Upstream states the triage and the
           three intrinsics; the INSTALLED CANN 9.0.0-beta.2 headers on this machine declare all
           three (and a fourth upstream does not mention) and show what each lowers to. The TRIAGE
           itself — that classifying by reuse protects hot data and pays — has one origin and no
           measurement: nothing was compiled, no hit rate was read.
BOARD:     950PR, 950DT
SOURCE:    ops/ascendc-performance-best-practices/reference/simt/optimization-guide.md:185-199 —
           "| 数据特征 | 推荐策略 | | 每个元素只读取一次 | 旁路 DCache 读取，避免挤出热点数据 | |
           会被同一核重复读取 | 使用 DCache，并尽量提高热点数据命中率 | | 写出后不再被当前核读取 |
           在版本支持时使用显式 non-cacheable store |" · "T value = asc_ldcg(input + idx);
           // 不在 DCache 分配，适合一次性读取 / T hot = asc_ldca(table + tableIdx);  // 使用
           DCache，适合重复访问 / asc_stcg(output + idx, value + hot);  // 不在 DCache 分配，适合
           一次性写出"
SOURCE:    same file:210-216 — "- 旁路 DCache 不代表旁路所有缓存层级，也不替代原子操作、内存屏障或
           线程同步。 - CANN 9.0 与 9.1 对 `asc_ldcg/asc_ldca/asc_stcg` 在纯 SIMT、混合 SIMD+SIMT
           模式下的支持范围不同；集成前必须检查目标版本 API 约束。 - 用生成指令、`DCache Read GM`
           和 kernel 耗时验证旁路是否实际生效及是否有收益。" ; :5 — "本文面向 Ascend 950（DAV_3510）
           上的 Ascend C SIMT 算子"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — `asc/include/simt_api/device_functions.h`
           declares `asc_ldcg` / `asc_ldca` / `asc_stcg` over the integer, float and short-vector
           types, `asc_fp16.h` and `asc_bf16.h` over the half and bfloat16 ones. The implementations
           (`asc/impl/simt_api/asc_fp16_impl.h:941-971`) lower them as
           `__ldg<LD_L2CacheType::L2_CACHE_HINT_NORMAL_FV, L1CacheType::NON_CACHEABLE>` (`asc_ldcg`),
           the same with `L1CacheType::CACHEABLE` (`asc_ldca`),
           `__stg<ST_L2CacheType::…_NORMAL_FV, L1CacheType::NON_CACHEABLE>` (`asc_stcg`), and a
           fourth, `asc_stwt`, as `__stg<…, L1CacheType::CACHEABLE>`.
INDEX:     none — nothing measured; see SOURCE. The API surface is re-derivable by file read:
           grep -Rn 'asc_ldcg\|asc_ldca\|asc_stcg\|asc_stwt' $ASCEND_HOME_PATH/asc/include/simt_api/
OVERTURN:  a measured SIMT kernel on a named 950 board where replacing a plain load of
           single-use streaming data with `asc_ldcg` leaves the hot table's DCache hit rate
           unchanged outside the run spread — the bypass would then not be protecting the resident
           data, which is the whole reason the triage exists.
```

# 0339 · SIMT DCache policy is chosen per reuse class and expressed with three cache-hint intrinsics

## 1 · Claim
Upstream asserts that on Ascend 950 (DAV_3510) SIMT kernels, one-shot streaming input and repeatedly
read hot data compete for the same SIMT DCache, and that the resolution is to classify data by reuse
and express the classification at each access. Upstream asserts three classes and three policies:
data read once per element bypasses the DCache so it does not evict hot data; data re-read by the
same core uses the DCache and should have its hit rate raised; data written and not re-read by the
current core uses an explicit non-cacheable store where the version supports one. Upstream asserts
the intrinsics that express these — `asc_ldcg` (load, do not allocate in DCache), `asc_ldca` (load,
use DCache), `asc_stcg` (store, do not allocate) — and cites CANN 9.1 official SIMT samples as their
source. Upstream asserts three constraints: bypassing the DCache does not bypass every cache level
and does not substitute for an atomic, a barrier or thread synchronisation; CANN 9.0 and 9.1 differ
in where these intrinsics are supported across pure-SIMT and mixed SIMD+SIMT modes, so the target
version's constraints must be checked before integration; and whether a bypass took effect and
whether it paid must be verified from the generated instructions, the `DCache Read GM` counter and
kernel time. Not established here.

## 2 · The wrong branch this removes
The default access has no hint, so every load competes on equal terms and the cache fills with
whatever arrived most recently. On a SIMT scatter or gather that is the streaming input, which is
read once and never again, and the lookup table that every thread needs is what gets evicted. The
symptom is a low hit rate on the hot data with no obvious cause, and the natural response —
make the table smaller, or stage it in UB — attacks the wrong side. The streaming load is the
problem and it is not even slow.

The second wrong branch is applying the bypass everywhere because it sounds like a pure win.
`asc_ldcg` on data that *is* re-read converts every reuse into a GM round trip. The triage is a
triage: the classification has to be done per buffer, and upstream's table is three rows because
there are three answers.

The third is the one upstream flags hardest and it is a correctness matter, not a performance one:
`旁路 DCache 不代表旁路所有缓存层级，也不替代原子操作、内存屏障或线程同步`. An engineer reaching
for a cache hint to make another core's write visible has confused a cache-allocation policy with a
coherence mechanism. The visibility case has its own tool (`0340`), and even that one upstream
scopes narrowly.

The fourth is the version. These three intrinsics' availability differs between CANN 9.0 and 9.1 and
between pure-SIMT and mixed modes — so a technique that compiles in one translation unit may not in
another within the same project, which is the same build-contract hazard `0343` records for Reg
types.

## 3 · Ground / Source
The triage, `simt/optimization-guide.md:179-192`:

```
### Rule 005：按复用特征选择 DCache 策略

- **分类**：缓存优化
- **优先级**：高
- **适用场景**：一次性流式输入与重复访问的热点数据共同竞争 SIMT DCache

按数据复用特征分三类：

| 数据特征 | 推荐策略 |
| 每个元素只读取一次 | 旁路 DCache 读取，避免挤出热点数据 |
| 会被同一核重复读取 | 使用 DCache，并尽量提高热点数据命中率 |
| 写出后不再被当前核读取 | 在版本支持时使用显式 non-cacheable store |
```

The intrinsics, `:193-199`:

```
Ascend 950 的 CANN 9.1 官方 SIMT 样例使用 cache hint 明确表达策略：

T value = asc_ldcg(input + idx);       // 不在 DCache 分配，适合一次性读取
T hot = asc_ldca(table + tableIdx);    // 使用 DCache，适合重复访问
asc_stcg(output + idx, value + hot);   // 不在 DCache 分配，适合一次性写出
```

The constraints, `:210-216`:

```
约束：

- `volatile` 还会阻止编译器合并、缓存或删除相应读取，可能增加指令数；不要用于会重复访问的热点数据。
- 旁路 DCache 不代表旁路所有缓存层级，也不替代原子操作、内存屏障或线程同步。
- 官方资料明确支持 `volatile` GM 读取用于获取其他核写入后的最新值；本文不推导 `volatile` store
  具有完全相同的 cache 语义。
- CANN 9.0 与 9.1 对 `asc_ldcg/asc_ldca/asc_stcg` 在纯 SIMT、混合 SIMD+SIMT 模式下的支持范围不同；
  集成前必须检查目标版本 API 约束。
- 用生成指令、`DCache Read GM` 和 kernel 耗时验证旁路是否实际生效及是否有收益。
```

The third bullet is a scope refusal of the kind `0338` records: upstream has documentation support
for `volatile` on the *load* side and declines to extend it to stores — `本文不推导`. That is a
document marking the edge of its own evidence, and it is why `0340` carries the load case and not
the store case.

The verification instruction in the last bullet is not decorative. `旁路是否实际生效` is a separate
question from whether it helped: a hint the compiler dropped produces the same disappointing timing
as a hint that took effect and did not pay, and only the generated instructions distinguish them.

Upstream names its sources at `:418-419` — `$ASC_DEVKIT_DIR/examples/03_simt_api/03_best_practices/
00_memory_optimizations/cache_hint/README.md` and
`$ASC_DEVKIT_DIR/docs/zh/api/SIMT-API/访存函数/访存函数简介.md`. Neither is present in this tree and
neither was read.

### The installed headers, read

Second origin, under the phase-1 read-only exception, CANN `Version=9.0.0-beta.2`. All three
intrinsics are declared — `asc/include/simt_api/device_functions.h` for the integer, float and
short-vector types, `asc_fp16.h` / `asc_bf16.h` for half and bfloat16 — and their bodies show what
the hints mean:

```
asc/impl/simt_api/asc_fp16_impl.h:941   asc_ldcg  → __ldg<LD_L2CacheType::L2_CACHE_HINT_NORMAL_FV,
                                                          L1CacheType::NON_CACHEABLE>(address)
asc/impl/simt_api/asc_fp16_impl.h:952   asc_ldca  → __ldg<…_NORMAL_FV, L1CacheType::CACHEABLE>
asc/impl/simt_api/asc_fp16_impl.h:963   asc_stcg  → __stg<ST_L2CacheType::…_NORMAL_FV,
                                                          L1CacheType::NON_CACHEABLE>
asc/impl/simt_api/asc_fp16_impl.h:973   asc_stwt  → __stg<…_NORMAL_FV, L1CacheType::CACHEABLE>
```

Three things follow that upstream's prose does not say.

First, the hint is **two-dimensional**: every one of the four passes an L2 hint *and* an L1
cacheability, and all four pass the same L2 value (`L2_CACHE_HINT_NORMAL_FV`). So "bypass the
DCache" is precisely `L1CacheType::NON_CACHEABLE` with L2 left alone — which is exactly upstream's
constraint `旁路 DCache 不代表旁路所有缓存层级`, now visible in the lowering rather than asserted.
The L2 dimension is reachable through `__ldg`/`__stg` directly and is not exposed by any of the four
`asc_*` wrappers.

Second, there is a **fourth** intrinsic upstream never mentions: `asc_stwt`, the cacheable store —
the counterpart of `asc_stcg`, and the store-side answer for output that *will* be re-read by the
same core. Upstream's triage has three rows and the toolkit has four policies; the missing row is
"written and re-read", which is a real case (an accumulator).

Third, all four exist in **9.0.0-beta.2**, not only in 9.1. Upstream attributes the samples to
CANN 9.1 and separately warns that 9.0 and 9.1 differ in *support range across pure-SIMT and mixed
modes*. The headers here settle declaration, not support range: a declaration in a header is not a
guarantee that a given build mode instantiates it, and `0343`'s build-contract taxonomy is the
reason that distinction is not pedantry.

The board scope: the guide opens `本文面向 Ascend 950（DAV_3510）上的 Ascend C SIMT 算子` (`:5`) and
names `Ascend 950PR/950DT` explicitly at `:154` in the short-vector discussion (`0341`), which is the
basis for this entry's BOARD line. No measurement on either board is offered.

Related but distinct, and not to be collapsed: the DCache size is quoted as 128 KB in a single
inline condition in the sibling shelf's gather family (`950:0148`'s neighbourhood records it as
undefined elsewhere), and a SIMT kernel must leave at least 32 KB of UB to DCache or the build is
rejected (`950:0237`). Those are capacity facts about the same cache; this entry is about
allocation policy and asserts nothing about capacity.

Nothing here is measured, by upstream or by this book. There is no hit-rate figure, no timing, and
no case.

## 4 · Procedure
Proposed, runnable later on `950PR` and separately on `950DT`. Never run in this phase.

Arm 0 — the API surface, `[no-card]` and **DONE** (§3): `grep -Rn` (not `-r`) for `asc_ldcg`,
`asc_ldca`, `asc_stcg` and `asc_stwt` over the installed toolkit's include roots, recording each
overload, its header and the toolkit pin. It found all four in 9.0.0-beta.2 and their lowerings.
What it did **not** settle is upstream's actual version claim — the *support range across pure-SIMT
and mixed build modes* — which no header read can answer and which Arm 5 below is for.

Arm 1 — the eviction mechanism, which is the claim. One SIMT kernel with two buffers: a hot lookup
table sized to fit comfortably in DCache, and a streaming input much larger than it. Four builds:
both plain; streaming under `asc_ldcg`; table under `asc_ldca`; both hinted. Readout per build: the
table's DCache hit rate, the `DCache Read GM` counter, and kernel time. The mechanism predicts the
table's hit rate rises when the streaming load bypasses — and that is the primary readout, not the
time.

Arm 2 — did the hint take effect. Disassemble all four builds and confirm the hinted accesses lower
to different instructions from the plain ones. A null result in Arm 1 without this arm is
unattributable: "the compiler ignored the hint" and "the hint did not help" produce identical
timings.

Arm 3 — the misapplication cost, retained whatever it shows. Apply `asc_ldcg` to the *table* — data
that is re-read — and measure. This is the negative arm and it is what tells a consuming skill how
much a wrong classification costs, which upstream never states.

Arm 4 — the store side, now four-way rather than two. `asc_stcg` (non-cacheable) against `asc_stwt`
(cacheable) against a plain store, on write-once output and on an accumulator that *is* re-read,
recording DCache occupancy and time. Upstream's triage has no row for the re-read output and the
toolkit has an intrinsic for it; this arm is what would fill that row.

Arm 5 — the version claim, which §3 shows a header read cannot settle. Compile a translation unit
using all four intrinsics under each build contract `0343` enumerates (`device_only`,
`xasc_combined`) and on each CANN package available, recording which combinations resolve. Upstream
asserts 9.0 and 9.1 differ in support across pure-SIMT and mixed modes, and only a build can say.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, with
`0327`'s same-path sibling check applied before any table is read. Device selection:
`npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three
idle samples; re-sample after; discard the case if the die moved. Refuses to assume: that a free die
stays free; that a die may be substituted; that a hint written is a hint executed (Arm 2 exists for
that); that `DCache Read GM` measures what its name suggests — its definition is recorded from the
profiling tool's own documentation before it is used as a verdict, and if that documentation is not
available the counter is reported as context and the hit rate carries the verdict.

## 5 · Checker — acceptance declared before the run
Verdict `hit_rate_gain` = the hot table's DCache hit rate under `asc_ldcg`-streaming minus its rate
under plain streaming, with the floor. Declared before the run: the triage is **supported** iff
`hit_rate_gain` is positive and outside the floor. The OVERTURN fires iff it is inside the floor
while Arm 2 confirms the hint lowered to a distinct instruction.

Verdict `hint_lowered[b]` for each build from Arm 2 — a boolean per hinted access, from
disassembly, with no timing involved.

Verdict `misapply_cost` = the time penalty of Arm 3, reported unconditionally: it is the number that
makes "classify per buffer" a rule rather than advice.

Verdict `stcg_available` from Arm 4 and Arm 0.

The exit code is not the verdict. Three guards.

First, every build is compared elementwise against a CPU reference. A cache hint should not change
results, and if one does, the hint is doing something other than what its name says — which is a
finding, not a nuisance.

Second — the input that makes this checker go red — Arm 1 includes a fifth build in which the
streaming buffer is *smaller* than the DCache, so no eviction can occur. `hit_rate_gain` **must** be
inside the floor there. If the hint appears to raise the hit rate even when there is nothing to
evict, the hit-rate measurement is not measuring eviction and every positive verdict in the run is
void. That planted negative-control is the fixture: a cache study whose metric moves under a
condition where the mechanism cannot operate has an instrument problem, not a result.

Third, no verdict is issued from timing alone. Upstream's own instruction is to check the generated
instructions, the counter **and** the time; a verdict from any one of the three is exactly the
single-line reading this book's checkers are built to refuse.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No SIMT kernel was built, no
hit rate was read, no instruction was disassembled, and no cache was observed to evict anything.

Arm 0 **was** performed, as a file read under the phase-1 read-only exception, and its output is
§3's second-origin block: four intrinsics located in CANN 9.0.0-beta.2, with their L1/L2 hint
lowerings. That establishes what is *declared* and what each name *means to the header*. It
establishes nothing about the hardware, nothing about whether a hint survives compilation, nothing
about hit rates, and nothing about the support range upstream's version warning is actually about —
a declaration is not an instantiation.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. Upstream supplies **no number at all** for this rule — no hit
rate, no timing, no case — so the entry carries a mechanism and a triage, not a magnitude, and the
`corroborated` stratum covers only the API surface and its lowering, never the triage. The header
read establishes that the four intrinsics are declared in one toolkit on one machine and what their
template arguments are; it does not establish that a build instantiates them, that the compiler
preserves the hint, or that `L1CacheType::NON_CACHEABLE` is the SIMT DCache rather than some other
L1 structure — that last identification is this book's reading of the name and is not stated
anywhere. The two official sources upstream cites are not present in this tree. The 9.0-versus-9.1
support difference is asserted without either version's constraint set being stated, and the header
read cannot address it. Upstream's triage has no row for output that is written and re-read, and
`asc_stwt` — which appears to be that row's answer — is undocumented by upstream and untested here. The entry says nothing about DCache
capacity, which is a separate quantity carried inconsistently elsewhere in this repository, and
nothing about how a hit rate should be raised beyond the instruction to raise it. Nothing here
covers UB-resident alternatives, which are Rule 006's subject and this book's `0318`. BOARD is
`950PR, 950DT` because the guide scopes itself to those parts by name; no run has occurred on either
and nothing is established for one by the other. Nothing transfers to the other book (RULES.md Art. 1) —
the SIMT programming model is stated by upstream to be DAV_3510-era.
