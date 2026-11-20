```
ID:        0340-volatile-must-qualify-the-pointee-to-bypass-the-simt-dcache-and-it-is-not-a-synchronisation-primitive
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     950PR, 950DT
SOURCE:    ops/ascendc-performance-best-practices/reference/simt/optimization-guide.md:201-208 —
           "若当前代码使用裸 GM 指针，也可对一次性读取的数据使用 `volatile` 指向类型，使读取旁路
           SIMT DCache：" · "__gm__ volatile T* inputOnce = reinterpret_cast<__gm__ volatile T*>(input);
           T value = inputOnce[idx];" · "注意限定符位置：需要的是"指向 volatile 数据的指针"
           `volatile T*`，不是仅让指针变量本身不可优化的 `T* volatile`。"
SOURCE:    same file:212-214 — "- `volatile` 还会阻止编译器合并、缓存或删除相应读取，可能增加指令数；
           不要用于会重复访问的热点数据。 - 旁路 DCache 不代表旁路所有缓存层级，也不替代原子操作、
           内存屏障或线程同步。 - 官方资料明确支持 `volatile` GM 读取用于获取其他核写入后的最新值；
           本文不推导 `volatile` store 具有完全相同的 cache 语义。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured SIMT kernel on a named 950 board where reading through `__gm__ volatile T*`
           does not bypass the DCache — the generated instruction being identical to the plain load's
           — which would make the whole technique a compiler-optimisation barrier and nothing more.
```

# 0340 · `volatile` must qualify the pointee to bypass the SIMT DCache, and it is not a synchronisation primitive

## 1 · Claim
Upstream asserts that on a SIMT path using raw GM pointers, reading through a pointer to `volatile`
data makes the read bypass the SIMT DCache, giving the `asc_ldcg` effect (`0339`) without the
intrinsic. Upstream asserts the qualifier position is load-bearing: what is required is
`volatile T*`, a pointer to volatile data, and **not** `T* volatile`, which only makes the pointer
variable itself non-optimisable. Upstream asserts three limits. `volatile` additionally prevents the
compiler from merging, caching or eliminating the reads, which may increase instruction count, so it
must not be used for hot data that is read repeatedly. Bypassing the DCache does not bypass every
cache level and does not substitute for an atomic, a memory barrier or thread synchronisation.
Official material supports `volatile` GM *reads* for observing another core's writes, and upstream
explicitly declines to infer that a `volatile` *store* has the same cache semantics —
`本文不推导`. Not established here.

## 2 · The wrong branch this removes
`T* volatile` compiles, reads correctly, and does nothing. It is the qualifier position a C
programmer writes by muscle memory, and there is no diagnostic: the kernel is correct, the DCache is
not bypassed, and the hot data still gets evicted. The failure is a performance null that looks like
"the technique does not work on this part".

The second wrong branch is the one upstream fences twice and it is a correctness matter. `volatile`
is a compiler directive about elision, not a hardware coherence mechanism, and the sentence
`不替代原子操作、内存屏障或线程同步` is doing real work: an engineer who needs another core's write
to be visible reaches for `volatile` because it is the C idiom for exactly that on a CPU. Upstream's
position is careful — reads are documented to see other cores' writes, and it will not extend the
claim to stores. So `volatile` on the reader is supported; `volatile` on the writer is not
established by anything, and using it as the write half of a handshake is inventing a guarantee.

The third is over-application. `volatile` also blocks merging and elimination, so applying it to a
hot table read in a loop converts every access into an instruction — the opposite of what a DCache
strategy is for, and upstream states the exclusion directly: `不要用于会重复访问的热点数据`.

The fourth is redundancy with `0339`. When the intrinsic is available for the type in question,
`asc_ldcg` expresses the intent with no side effects on optimisation. `volatile` is the fallback for
raw-pointer code, and choosing it where the intrinsic exists buys the bypass and pays an
optimisation barrier for it.

## 3 · Ground / Source
The technique and the qualifier rule, `simt/optimization-guide.md:201-208`:

```
若当前代码使用裸 GM 指针，也可对一次性读取的数据使用 `volatile` 指向类型，使读取旁路 SIMT DCache：

__gm__ volatile T* inputOnce = reinterpret_cast<__gm__ volatile T*>(input);
T value = inputOnce[idx];

注意限定符位置：需要的是"指向 volatile 数据的指针"`volatile T*`，不是仅让指针变量本身不可优化的
`T* volatile`。
```

The three limits, `:212-216`:

```
- `volatile` 还会阻止编译器合并、缓存或删除相应读取，可能增加指令数；不要用于会重复访问的热点数据。
- 旁路 DCache 不代表旁路所有缓存层级，也不替代原子操作、内存屏障或线程同步。
- 官方资料明确支持 `volatile` GM 读取用于获取其他核写入后的最新值；本文不推导 `volatile` store
  具有完全相同的 cache 语义。
- 用生成指令、`DCache Read GM` 和 kernel 耗时验证旁路是否实际生效及是否有收益。
```

The third bullet is the entry's second reason to exist. It is a document stating the boundary of its
own evidence in one clause — reads are supported by cited material, stores are not derived — and it
is the same restraint `0338` records in this shelf's FlashAttention family. The source upstream
cites for the read case, `:422`, is
`$ASC_DEVKIT_DIR/docs/zh/guide/算子实践参考/优秀实践/SIMT实现InsertHashTable算子案例.md`, not present
in this tree and not read.

Note what upstream does **not** claim: that `volatile` and `asc_ldcg` are equivalent. `0339` §3
records that `asc_ldcg` lowers to
`__ldg<LD_L2CacheType::L2_CACHE_HINT_NORMAL_FV, L1CacheType::NON_CACHEABLE>` in the installed
9.0.0-beta.2 headers — an explicit L1 cacheability *and* an L2 hint. `volatile` is a
source-language qualifier whose lowering is the compiler's business, and nothing in this tree states
which L1/L2 hint pair it produces, or whether it produces one at all. Treating the two as
interchangeable is an inference this entry does not make; the fourth bullet's instruction to check
the *generated instructions* is precisely how they would be compared.

The verification instruction is the same three-part one as `0339` and is worth repeating because the
failure mode here is different: with `volatile`, "did the bypass take effect" and "did the compiler
merely stop optimising" are distinct outcomes that a timing comparison cannot separate.

Nothing here is measured. There is no timing, no hit rate, no instruction listing, and no case.

## 4 · Procedure
Proposed, runnable later on `950PR` and separately on `950DT`. Never run in this phase.

Arm 1 — the qualifier position, settled by disassembly. Three builds of one SIMT streaming read:
plain `__gm__ T*`, `__gm__ volatile T*`, and `__gm__ T* volatile`. Disassemble all three. The claim
predicts builds 1 and 3 generate the same load and build 2 a different one. No timing is needed for
this arm and none should be trusted in place of it.

Arm 2 — the bypass, measured. The `0339` Arm 1 apparatus (hot table plus large streaming input),
with the streaming read done four ways: plain, `volatile` pointee, `asc_ldcg`, and `T* volatile`.
Readout: the table's DCache hit rate, `DCache Read GM`, kernel time and streaming-read instruction
count. This arm answers both "does `volatile` bypass" and "does it cost instructions" in one table.

Arm 3 — equivalence with the intrinsic, which upstream never claims and a reader will assume. From
Arm 1's disassembly, compare the instruction `volatile` produces against the one `asc_ldcg`
produces. If they differ, the two are different mechanisms and the entry says so; if they agree, the
`volatile` route is the intrinsic under another spelling and the optimisation-barrier warning is the
only remaining difference.

Arm 4 — the misapplication cost. `volatile` on the hot table — data read repeatedly — against plain.
Upstream predicts more instructions and worse time. Retained whatever it shows.

Arm 5 — the visibility question, kept separate and scoped narrowly. One core writes, another reads
through `__gm__ volatile T*` with no barrier and no atomic. Record whether the reader observes the
write, and how often across many iterations. This arm does **not** establish a guarantee whatever it
shows: observing a write is not being promised one, and upstream's own claim rests on external
documentation. Its purpose is the reverse — if the reader *fails* to observe, the documented read
support does not hold on this configuration and that is worth knowing before anyone relies on it.

Variance floor first for the timed arms: one build, 30 in-process runs, 5 fresh-process runs, IQR
over median, with `0327`'s same-path sibling check applied. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved. Refuses to assume: that a free die stays free;
that a die may be substituted; that source text implies generated code (Arm 1 is disassembly for
exactly that reason); that Arm 5's outcome licenses removing a barrier — it cannot, by construction,
and the arm's report says so in its own line.

## 5 · Checker — acceptance declared before the run
Verdict `qualifier_distinguished` = true iff Arm 1's build 2 disassembles differently from builds 1
and 3, **and** builds 1 and 3 disassemble identically. Declared before the run: both halves are
required. Build 3 differing from build 1 would mean `T* volatile` also changes the load, and the
qualifier-position rule as stated would be incomplete.

Verdict `bypass_effective` = the hot table's hit-rate gain under `volatile` streaming, with the
floor. The OVERTURN fires iff it is inside the floor while `qualifier_distinguished` is true — the
qualifier would change the instruction without changing the cache behaviour.

Verdict `instr_cost` = the streaming-read instruction count under `volatile` minus plain, reported
unconditionally: it is the price upstream warns about and never quantifies.

Verdict `matches_intrinsic` from Arm 3.
Verdict `hot_penalty` from Arm 4.
Verdict `visibility_observed` from Arm 5, reported with the explicit note that it is an observation
and not a guarantee.

The exit code is not the verdict. Three guards.

First — the input that makes this checker go red — Arm 2 includes a control in which the streaming
buffer is smaller than the DCache, where `bypass_effective` **must** be inside the floor because
there is nothing to evict. A hit rate that improves where the mechanism cannot operate means the
metric is not measuring eviction, and every positive verdict is void. This is the same planted
negative-control as `0339` §5 and it is required here for the same reason.

Second, every arm is compared elementwise against a CPU reference. `reinterpret_cast` to a
differently-qualified pointer type is an operation that can silently change nothing *or* silently
change aliasing assumptions, and only a result comparison distinguishes those.

Third, Arm 5's verdict is never phrased as support for a synchronisation practice. A run in which
the reader always observes the write establishes that it did on that configuration, in that
interleaving, on that toolkit — and upstream's own limit (`不替代原子操作、内存屏障或线程同步`)
survives any number of such observations. The report states this in the same line as the number.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No build was disassembled,
no hit rate was read, no instruction was counted, and no cross-core write was observed. The
`asc_ldcg` lowering quoted in §3 comes from `0339`'s header read and is a fact about a header, not
about `volatile`.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that `volatile` bypasses anything —
upstream asserts it and cites a document not present in this tree, and no instruction listing exists
here. It does not establish that `volatile` and `asc_ldcg` produce the same access; upstream never
claims it and §4 Arm 3 is what would compare them. The instruction-count cost is warned about and
never quantified. The read-visibility claim rests entirely on external official material that was
not read, and this entry carries it at that strength and no higher; the store side upstream
explicitly refuses to derive, and this entry refuses it too. Nothing here licenses using `volatile`
in place of an atomic, a fence or a barrier, and no run could — the limit is about what is
*guaranteed*, and observation does not establish guarantees. The technique is scoped by upstream to
raw-GM-pointer SIMT code; nothing is established for `LocalTensor`-mediated access or for SIMD
paths. BOARD is `950PR, 950DT` from the guide's own scope line; no run has occurred on either.
Nothing transfers to the other book (RULES.md Art. 1).
