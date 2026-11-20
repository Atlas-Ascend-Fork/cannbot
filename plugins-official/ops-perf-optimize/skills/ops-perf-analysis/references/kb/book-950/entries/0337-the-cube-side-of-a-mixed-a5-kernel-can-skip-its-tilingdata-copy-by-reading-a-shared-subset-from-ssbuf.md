```
ID:        0337-the-cube-side-of-a-mixed-a5-kernel-can-skip-its-tilingdata-copy-by-reading-a-shared-subset-from-ssbuf
LABEL:     knowledge
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/flash_attention/tilingdata_cv_ssbuf_forwarding_design.md:5
           — "针对 `kv_quant_sparse_flash_attention` 在 A5 / arch35 混合 AIC+AIV kernel 启动阶段重复
           拷贝完整 TilingData 的问题，将 full TilingData 拷贝保留在 vector 侧，由 vector 抽取
           cube/vector 共享字段并通过 `__ssbuf__` 转发给 cube，减少 cube 侧启动头开销。"
SOURCE:    same file:20-32 — the AIV/AIC sequence quoted in §3 ; :44 — "`CVSharedParams` 只放 cube
           必需字段，例如 batch、seq、qSeq、group、sparse block count、used core num 和必要 scale
           字段。结构体字段需保持 word-copy 友好。" ; :95 — "该案例未提供具体量化数据，因此不编造
           收益数字；落地时以启动 timeline、cube 侧头开销和主/control shape 精度作为验收。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured mixed AIC/AIV kernel on a named 950 board where removing the cube-side full
           TilingData copy leaves cube-side launch overhead unchanged outside the run spread — the
           copy would then not be on the launch critical path, and the technique would have no
           subject.
```

# 0337 · The cube side of a mixed A5 kernel can skip its TilingData copy by reading a shared subset from `__ssbuf__`

## 1 · Claim
Upstream asserts a launch-overhead technique for mixed AIC+AIV kernels on A5 / arch35. In the
unoptimised form both sides execute `GET_TILING_DATA_WITH_STRUCT` and copy the whole TilingData
struct, although cube and vector need different and smaller subsets of it. In the optimised form the
vector side keeps the full copy, extracts a `CVSharedParams` struct of the fields cube actually
needs, writes it word by word into `__ssbuf__`, and raises a cross-core flag; the cube side is
launched with a null tiling pointer, performs the initialisation that does not depend on shared
parameters, waits on the flag, and reads `CVSharedParams` back out of `__ssbuf__`. Upstream asserts
the field selection rule — `CVSharedParams` carries only cube-necessary fields (batch, seq, qSeq,
group, sparse block count, used core num, the necessary scale fields) and must stay word-copy
friendly. Upstream asserts an ordering benefit: cube's independent initialisation runs before the
wait, hiding part of the vector-side extraction latency. Upstream asserts four disqualifying
conditions and one hard constraint: if the `__ssbuf__` address or the flag id is already used by
another channel it must be reallocated, never shared. Not established here.

Upstream asserts, explicitly, that this case carries **no quantified benefit** and refuses to invent
one.

## 2 · The wrong branch this removes
The launch header is invisible in the usual optimisation loop. A profile shows pipe utilisation
inside the kernel; the cost of getting *to* the kernel body sits before any of it, and on a small
shape it can be a material share. Upstream states the condition under which it matters —
`小 shape 或启动头占比较高时，cube 侧 tiling 初始化会进入关键路径` — which is exactly the regime
where an agent has run out of in-kernel ideas.

The available wrong branch is symmetry: both sides run the same entry macro because that is what the
template does, and neither side's author asked whether the other's fields are needed. Removing one
side's copy requires knowing which fields cube reads, which is a whole-kernel property.

The second wrong branch is what to forward. `CVSharedParams` is a *subset*, chosen by necessity and
constrained to be word-copy friendly. Forwarding the whole struct through `__ssbuf__` would move the
copy rather than remove it, and would consume a scarce channel to do so. Upstream's disqualifier is
explicit: if cube subsequently needs many full-tiling fields, the compression does not pay.

The third is the channel itself, and it is the one that will bite. `__ssbuf__` is a CV message
channel, not a data buffer (`950:0227`), and both its address and the cross-core flag id are shared
resources across the whole kernel. Upstream's rule — reallocate on conflict, never reuse a position
already in use — is a correctness rule, and the failure it prevents is two producers writing one
mailbox, which presents as sporadic wrong tiling rather than as a fault. The example uses flag id 15
and offset 0, both of which are the most likely to be already taken.

The fourth is ordering. Cube must do its independent initialisation **before** the wait, or the
technique's own latency-hiding benefit is lost and the wait is added to the critical path it was
meant to shorten.

## 3 · Ground / Source
The two forms, `tilingdata_cv_ssbuf_forwarding_design.md:9-32`:

```
### 优化前

AIV: GET_TILING_DATA_WITH_STRUCT(full tiling) -> vector init
AIC: GET_TILING_DATA_WITH_STRUCT(full tiling) -> cube init

问题：cube 和 vector 只需要 TilingData 的不同子集，但两侧都执行 full tiling struct 拷贝。小 shape
或启动头占比较高时，cube 侧 tiling 初始化会进入关键路径。

### 优化后

AIV:
  GET_TILING_DATA_WITH_STRUCT(full tiling)
  fill CVSharedParams
  write CVSharedParams to __ssbuf__
  CrossCoreSetFlag<SYNC_MODE, PIPE_S>(15)

AIC:
  independent cube init
  CrossCoreWaitFlag<SYNC_MODE, PIPE_S>(15)
  read CVSharedParams from __ssbuf__
  continue compute
```

The five modification points, `:36-42`, including the ordering rule
(`cube 先执行不依赖共享参数的初始化，再等待 flag | 隐藏部分 vector tiling 提取延迟`) and the null
tiling pointer on the cube branch.

The field rule, `:44`:

```
`CVSharedParams` 只放 cube 必需字段，例如 batch、seq、qSeq、group、sparse block count、used core
num 和必要 scale 字段。结构体字段需保持 word-copy 友好。
```

The transfer itself, `:65-83`, is a `uint32_t`-granular unrolled copy in both directions:

```cpp
auto ssbuf = reinterpret_cast<__ssbuf__ uint32_t *>(0);
auto src = reinterpret_cast<uint32_t *>(&sharedParams);
#pragma unroll
for (int i = 0; i < sizeof(CVSharedParams) / sizeof(uint32_t); ++i) {
    ssbuf[i] = src[i];
}
CrossCoreSetFlag<SYNC_MODE, PIPE_S>(15);
```

`sizeof(CVSharedParams) / sizeof(uint32_t)` is why "word-copy friendly" is a requirement and not a
preference: a struct with a non-multiple-of-4 size, or with padding the compiler may reorder, is
silently truncated by that loop.

The disqualifiers, `:87-93`:

```
| AIC/AIV 都 full copy TilingData，cube 只用少量字段 | 适用 |
| vector 不在启动关键路径，或 cube 可先做独立初始化 | 适用 |
| cube 后续需要大量 full tiling 字段 | 不适用，压缩收益不足 |
| `CVSharedParams` 过大或字段含复杂非 word-copy 类型 | 不适用 |
| `__ssbuf__` 地址或 flag id 已被其他通道使用 | 必须重新分配，不能复用冲突位置 |
```

The refusal to quantify, `:95`, quoted in full because it is the entry's second reason to exist:

```
效果：减少 cube 侧 full TilingData 拷贝和启动 Scalar 指令。该案例未提供具体量化数据，因此不编造
收益数字；落地时以启动 timeline、cube 侧头开销和主/control shape 精度作为验收。
```

That is a document declining to state a benefit it does not have, and naming the acceptance
criteria a reader should apply instead. In a shelf where the same author elsewhere publishes a
−1.51 % single-case figure with three decimal places (`0336`), this is the more disciplined move,
and it is one of two places in this family where it appears (`0338`).

`__ssbuf__` itself is carried by `950:0227` — a CV message channel new in DAV_3510, replacing GM
workspace for fine-grained synchronisation, with a capacity upstream marks as a public-or-experience
value and no ini field. This entry is that channel's first concrete use in this book; it cites
`950:0227` and does not re-establish the channel. `950:0277` separately records that on A5 the
shared window's data region starts one megabyte past its base address — a neighbouring fact about
the same shared-memory region and not the same one, and this entry does not conflate them.

Nothing here is measured, by upstream or by this book.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. Upstream supplies the
acceptance criteria and no data, so §4 is what would produce the data.

Arm 1 — the launch header, measured where upstream says to look. Baseline and forwarded builds of a
mixed AIC/AIV kernel, at a small shape where the header share is expected to be material and at a
large one where it is not. Readout: the cube side's time from kernel entry to first MMAD, taken from
the launch timeline, plus the cube-side scalar instruction count from disassembly. Kernel time is
secondary — a technique aimed at the header must be measured at the header, or a large-shape null
will be read as the technique not working.

Arm 2 — the ordering claim. Three builds: forwarded with cube's independent init before the wait;
forwarded with the wait first; baseline. Upstream asserts the first hides part of the vector-side
extraction latency, which predicts a gap between builds one and two.

Arm 3 — the word-copy requirement, as a deliberate defect. Build with a `CVSharedParams` whose size
is not a multiple of `sizeof(uint32_t)` and confirm the truncation is detectable. See §5.

Arm 4 — channel exclusivity. Build a variant in which another part of the kernel also writes
`__ssbuf__` offset 0 or raises flag 15, and record what happens: silent corruption, a hang, or a
detected conflict. Upstream states the rule and not the failure mode, and the failure mode decides
whether a static allocation table is needed or a convention suffices.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median — the
expected effect is a launch-header share on a small shape, so the floor must be measured on the
header metric and not only on kernel time. `0327`'s same-path sibling check applied to every table.
Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; re-sample after; discard the case if the die moved. Refuses to
assume: that a free die stays free; that a die may be substituted; that `__ssbuf__` offset 0 is
free (Arm 4 exists because it may not be, and the whole kernel's uses are enumerated before the
build); that the cube branch's null tiling pointer is safe — every cube-side read of a tiling field
is enumerated first, because a single missed field dereferences null.

## 5 · Checker — acceptance declared before the run
Verdict `header_delta` = (baseline cube-side header time − forwarded) / baseline, with the floor,
reported separately for the small and large shapes. Declared before the run: the technique is
**supported** iff `header_delta` is positive and outside the floor on the small shape; a null on the
large shape is expected and is not a failure.

Verdict `scalar_instr_delta` = the cube-side scalar instruction count difference from disassembly.
This is a static readout with no variance, and it is the one figure that cannot be contaminated by
the machine — which at this effect size matters more than usual.

Verdict `ordering_gain` = build 1 against build 2 from Arm 2.
Verdict `truncation_detected` and `channel_conflict_mode` from Arms 3 and 4.

The exit code is not the verdict. Three guards.

First, correctness is compared elementwise against a reference for the whole output on both the main
and the control shapes — upstream names `主/control shape 精度` as an acceptance criterion, and the
reason is that a truncated or stale `CVSharedParams` produces a plausible kernel with wrong batch or
sequence counts.

Second — the input that makes this checker go red — Arm 3 is the planted positive: a
`CVSharedParams` sized at, say, 18 bytes **must** be caught. The unrolled copy loop transfers
`18 / 4 = 4` words and drops the last two bytes silently, so a build that passes correctness with a
misaligned struct proves the test data does not depend on the truncated field, and every green in
the run is void for this defect class. The fixture is mandatory because the failure is arithmetic in
the copy loop rather than anything the compiler can see.

Third, `header_delta` is never reported from kernel time. A technique whose whole subject is launch
overhead, measured by total time on a large shape, will always read as zero — and that null would be
about the measurement, not the technique.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. **Upstream reports no
quantified benefit for this technique and explicitly declines to supply one**, so there is nothing
here to reproduce — only a mechanism to test and an acceptance protocol upstream itself named.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled, and there is no upstream measurement either: the entry carries a
mechanism with no magnitude, and a consuming skill must not attach a benefit figure to it. It does
not establish that the cube-side TilingData copy is on any critical path — that is the premise, and
§4 Arm 1 is what would test it. It does not establish that `__ssbuf__` offset 0 and flag id 15 are
available in any real kernel; upstream uses them in an example and warns they may conflict.
`CVSharedParams`'s actual field set, `SYNC_MODE`, `KvQuantSparseFlashAttentionTilingDataMla` and the
`__ssbuf__` capacity are named without definitions; the capacity is marked by upstream's own truth
source as a public-or-experience value with no ini field (`950:0227`). The technique is stated for
one operator (`kv_quant_sparse_flash_attention`, A5 MLA path) and its transferability to other mixed
kernels is asserted by placement, not by evidence. Nothing establishes what happens when the
word-copy requirement is violated, or when the channel is shared. BOARD is
`family-claimed(unverified)`: the document names "A5 / arch35" and no board token. Nothing transfers
to the other book (RULES.md Art. 1) — `__ssbuf__` is stated by upstream's truth source to be new in
DAV_3510.
