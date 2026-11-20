```
ID:        0227-ssbuffer-is-a-cv-message-channel-that-replaces-gm-workspace-synchronisation-not-a-data-buffer
LABEL:     boundary
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — one upstream origin, which marks both the 256 KB capacity and the channel
           itself as public-or-experience values with no ini field (0206 row 3, row 4). A search of
           the installed 950 ini set found no SSBuffer field. Nothing was compiled.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:261 — "| **SSBuffer** | **DAV_3510 新增**：CV 间
           消息通路 | 替代 GM workspace 的细粒度同步 |"; :184 — "| **SSBuffer** | — | 256 KB
           [¹](#unverified) | **DAV_3510 新增** AIC↔AIV 核间消息通路 |"
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:168 — "| 3 | SSBuffer 256KB | Guide §3
           Buffer 容量 / SKILL.md §DAV_3510 关键变化 | 公开资料 / 经验值 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an SSBuffer allocation on a 950 board accepting a bulk data tensor and delivering it
           between AIC and AIV — the "message channel, not data buffer" reading would then be wrong;
           or an allocation boundary found at a size other than 256 KB.
```

# 0227 · SSBuffer is a CV message channel that replaces GM-workspace synchronisation, not a data buffer

## 1 · Claim
Upstream asserts that DAV_3510 adds SSBuffer, described in two places as an **inter-core message
channel** between AIC and AIV (`AIC↔AIV 核间消息通路`) whose programming role is 替代 GM workspace 的
细粒度同步 — replacing GM-workspace-mediated fine-grained synchronisation. Upstream states its capacity
as 256 KB and marks that figure, and the channel itself, as public-or-experience values with no
corresponding INI field. Not established here: nothing was compiled, no allocation was attempted, and a
search of the installed 950 ini set for an SSBuffer field returned nothing.

## 2 · The wrong branch this removes
SSBuffer appears in the per-core Buffer table at `npu-arch-guide.md:184`, in the same column as L1, L0A,
L0B, L0C, UB, L2 and BT, with a capacity in kilobytes. Everything about that placement says "another
buffer", and 256 KB is a substantial one — larger than UB. An agent planning a CV fusion sees a quarter
megabyte of new on-chip storage and budgets an intermediate tensor into it.

Two things go wrong. The narrow one: there is no reason to think a message channel accepts a bulk tensor,
so the allocation may simply fail — a loud, cheap error.

The damaging one is the planning error that precedes it. A fusion strategy designed around 256 KB of new
data capacity is a different strategy from one designed around a signalling path, and the two lead to
different tiling. If SSBuffer is a message channel, the thing that eliminates the GM round trip is
L0C→UB and UB→L1 (0225) — the *data* paths — and SSBuffer only removes the synchronisation flag that
used to live in a GM workspace beside the data. An agent that credits SSBuffer with the data movement
has attributed the benefit to the wrong mechanism and will size the wrong resource.

The reverse branch matters too. Dismissing SSBuffer as "just synchronisation" misses that GM-mediated CV
handshakes are exactly what made fine-grained Cube-Vector interleaving expensive: a flag round-tripped
through GM costs a full memory latency per handshake, so the granularity of fusion was bounded by
handshake cost rather than by compute. A channel that removes that bound changes what fusion granularity
is affordable, independently of the data paths.

The honest position is that this entry cannot settle which reading is right. Upstream says 消息通路 in
two places and gives a capacity in the buffer table — a message channel with 256 KB behind it. That could
be a deep queue, a scratch area for message payloads, or a capacity figure inherited from a table
template. §4 is written to distinguish them rather than to assume.

## 3 · Ground / Source
`npu-arch-guide.md:251-263`, the AI Core Buffer hierarchy — SSBuffer's row states its function, and the
neighbouring rows state theirs, which is the contrast that carries the claim:

> ### AI Core Buffer 层级
>
> 决定 LocalTensor 分配位置、DataCopy 路径选择、流水编排。
>
> | Buffer | 用途 | 编程影响 |
> |--------|-----|---------|
> | **L1 Buffer** | Cube 输入缓存 | 矩阵乘左/右矩阵驻留 |
> | **L0A / L0B** | Cube 操作数 | MTE1 搬入目标 |
> | **L0C Buffer** | Cube 输出（**Ascend950PR 扩容**） | 影响基本块 Tiling 上限 |
> | **UB / Unified Buffer** | Vector 工作区 | Vector 计算主战场，SIMT/SIMD 共享 |
> | **SSBuffer** | **DAV_3510 新增**：CV 间消息通路 | 替代 GM workspace 的细粒度同步 |
> | **BT / FP Buffer** | FixPipe 配置 | 量化/重排参数 |
> | **ND-DMA Cache** | NDDMA 缓存 | 离散搬运优化 |

Every other row's 编程影响 names a data-placement or tiling consequence — residency, MTE1 target, tiling
ceiling, compute workspace. SSBuffer's names a *synchronisation* consequence. That is the distinction,
stated by upstream in the column designed to state it.

The capacity, `:173-186`, in the per-core Buffer table:

> | Buffer | Ascend910B2 | Ascend950PR | 用途 |
> | **UB** | 192 KB | **248 KB** | Vector 工作区，每 AIV 独立一份 |
> | **SSBuffer** | — | 256 KB [¹](#unverified) | **DAV_3510 新增** AIC↔AIV 核间消息通路 |

Two things to read here. The `—` in the 910B2 column: SSBuffer does not exist on the earlier
architecture, so there is no prior art and no ported kernel that uses it. And the `[¹]` marker, which UB
in the row above does not carry — the neighbouring capacity is ini-backed (0209) and this one is not.

The provenance, `npu-hardware-params.md:164-179`, rows 3 and 4 of the 公开资料/经验值 table:

> | 3 | SSBuffer 256KB | Guide §3 Buffer 容量 / SKILL.md §DAV_3510 关键变化 | 公开资料 / 经验值 |
> | 4 | CV 直通通路：L0C→UB、UB→L1、SSBuffer 消息 | Guide §4 关键数据通路改动 / SKILL.md §DAV_3510 关键变化 | 同上 |

Note that row 4 lists "SSBuffer 消息" alongside the two data paths as one of the three CV additions
(0225), while row 3 lists the capacity separately. So upstream itself keeps the channel and its size as
two facts with the same weak pedigree.

The third statement, `:277-283`, places it among the additions:

> DAV_3510 新增三条通路，使 Cube 与 Vector 可直接交换数据，避免 GM workspace 中转：
> 1. **L0C → UBuffer**：Cube 结果直达 Vector，FixPipe 输出到 UB
> 2. **UBuffer ↔ L1**：Vector 与 Cube 双向直连（UB→L1 为新增方向），避免 GM 中转
> 3. **SSBuffer 消息通路**：CV 间细粒度同步信号

细粒度同步信号 — fine-grained synchronisation *signals*. Items 1 and 2 say 数据 and 直达; item 3 says
信号. Upstream is consistent across all four mentions: SSBuffer carries signals, the other two carry
data. That consistency is the strongest thing this entry has, and it is still one origin restating
itself.

`SKILL.md:61` compresses it to "| CV 直通通路 | 新增 L0C→UB、UB→L1、SSBuffer 消息 |" — and note that a
reader who meets only this line gets "SSBuffer" in a list headed 直通通路 with no indication that one of
the three is different in kind.

**Independent search, installed toolkit** (phase-1 read-only exception): a case-insensitive search of
`Ascend950PR_9589.ini` for `ssbuf` returned nothing, and no `[AICoreSpec]` field corresponds to a
256 KB capacity other than `l0_c_size` (which is L0C). This agrees with upstream's own statement that no
INI field supplies it and establishes nothing further. There is no accessor for it in the
`GetCoreMemSize` enumeration upstream documents (`UB`, `L1`, `L0_A`, `L0_B`, `L0_C`, `L2`, `BT`, and
`FB` per `npu-hardware-params.md:118`) — SSBuffer is absent from that list too, which is a second
absence pointing the same way and is worth recording because it means a kernel cannot query the capacity
at runtime the way 0207 requires for every other buffer.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion. The question is
what kind of resource this is, so the procedure probes its interface before its size.

Arm A — the interface, file read then compile, no device for the first half. Search the installed
toolkit's headers for an SSBuffer API — an allocation, a `QuePosition`, a `CoreMemType` enumerator, or a
message send/receive:

```bash
grep -RIn -i "ssbuffer\|ss_buffer\|SSBUF" "$ASCEND_HOME_PATH/include/ascendc/"
```

`grep -R`, not `-r` — these trees are symlink farms. What comes back determines everything downstream: an
allocation-shaped API supports the buffer reading, a send/receive-shaped API supports the channel
reading, and nothing at all means the resource is not programmer-visible on this toolkit, which would be
the most useful negative available.

Arm B — the data test, which distinguishes the two readings directly. Attempt to place a bulk tensor in
SSBuffer and copy it AIC→AIV. If it compiles and delivers correct data, SSBuffer is at least partly a
data buffer and this entry's framing is wrong. If it is refused, record the diagnostic.

Arm C — the capacity boundary. Whatever unit Arm A reveals — bytes, messages, slots — bisect upward until
allocation refuses, and record the largest success and smallest failure. Under upstream's figure the
boundary is at 256 KB; a boundary expressed in *messages* rather than bytes would be the finding, since
it would mean the tabulated 256 KB is a capacity for something other than what a user allocates.

Arm D — the benefit, which is what makes the channel worth having and is separate from what it is. Build
one fine-grained CV-fused operator two ways at identical shape, same die, same session: one handshaking
through a GM workspace flag, one through SSBuffer. Sweep the handshake granularity — coarse to fine — and
record Task Duration for both. §2's argument is that the GM handshake cost bounds affordable fusion
granularity; this arm measures where the two curves diverge, which is the number a fusion decision needs.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and no die is substituted for another. Arm D's paired builds run on one named die in one
session — SSBuffer is a per-core resource shared between AIC and AIV, so a co-tenant on the same die
would contend for it, and sole-tenancy is confirmed and recorded rather than assumed.

## 5 · Checker — acceptance declared before the run
Verdict variable `ssbuffer_kind`, from Arms A and B, declared as a three-way choice before any readout so
that none can be reinterpreted afterwards: `channel` (an API exists and it is message-shaped; Arm B's
bulk placement is refused), `buffer` (Arm B's bulk placement succeeds and delivers correct data — this
entry's framing is wrong and is corrected in place), or `not-exposed` (Arm A finds no API at all, in
which case the 256 KB figure describes something no kernel can address and every planning use of it is
void).

`capacity_boundary` (Arm C) — the largest successful allocation, **with its unit**. Pass iff it equals
256 KB *and the unit is bytes*. A boundary in messages or slots does not fail the entry; it corrects the
tabulated figure's meaning, which is a more useful outcome than confirming a number.

`handshake_crossover` (Arm D) — the granularity at which SSBuffer handshaking overtakes the GM-workspace
handshake. Reported with run variance, **no pass threshold**: upstream claims a replacement, not a speed
figure, and inventing a band would let a convenient result read as validation.

The positive fixture, declared before the run: Arm D must include a coarse-granularity point where the
handshake happens once per kernel. At that point the two builds **must** be within run variance of each
other, because a single handshake cannot matter. If SSBuffer wins even there, the two implementations
differ in something other than the handshake mechanism — most likely the data path — and every crossover
figure is void. A second fixture for Arm A: search for a deliberately misspelled token (`ssbufferr`) and
require zero hits; if it returns something, the search is matching substrings and its negatives mean
nothing. Without both, the checker reads only "SSBuffer was faster", which is the known blind species.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No header was searched for an
SSBuffer API, no allocation was attempted, and no handshake was timed — Arm A's first half is a file read
and remains open. The ini search reported in §3 covered four spellings in one file and found nothing;
a search that finds nothing establishes nothing, and it is recorded only because it agrees with
upstream's own statement that no such field exists.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish that SSBuffer exists as a programmer-visible
resource, that it is a message channel rather than a data buffer, or that its capacity is 256 KB — Arms
A, B and C are all open, and `not-exposed` is a live outcome. There is **no second origin**: upstream
marks both the channel and the capacity as public-or-experience values with no ini field (0206 rows 3
and 4), the installed ini carries no SSBuffer field, and SSBuffer is absent from the `GetCoreMemSize`
enumerator list upstream documents — so unlike every other buffer in this block (0209-0213, 0218) there
is **no runtime query for it**, and 0207's query-don't-hardcode discipline has nothing to apply. The
"message channel, not data buffer" reading rests entirely on upstream's consistent wording across four
mentions in one skill; that is one origin restating itself, not corroboration. It does not establish the
benefit: 替代 GM workspace 的细粒度同步 is upstream's claim about a mechanism, and no operator, no
granularity and no measurement supports it here. It says nothing about the *data* paths L0C→UB and
UB→L1, which are 0225 and which are the mechanisms that actually eliminate the GM round trip — §2 exists
largely to keep the credit with the right one. It says nothing about BufferID (0228), the other
synchronisation change in the same architecture. Nothing transfers to the other book (RULES.md Art. 1); the
`—` in the 910B2 column is upstream's text and this book claims nothing about SSBuffer's absence there.
