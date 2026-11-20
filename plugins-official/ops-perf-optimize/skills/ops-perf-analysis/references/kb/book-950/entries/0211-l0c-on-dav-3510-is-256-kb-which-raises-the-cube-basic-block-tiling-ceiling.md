```
ID:        0211-l0c-on-dav-3510-is-256-kb-which-raises-the-cube-basic-block-tiling-ceiling
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   corroborated — ops/npu-arch and the installed CANN 9.0.0-beta.2 ini set independently
           carry `l0_c_size=262144`. Both trace to vendor ini data (0204); no device was queried.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:109 — "| L0C | `l0_c_size` | 256 KB (262144) |"
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:259 — "| **L0C Buffer** | Cube 输出
           （**Ascend950PR 扩容**） | 影响基本块 Tiling 上限 |"   # same skill — ONE origin.
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — all 32 `NpuArch=3510` files in
           `aarch64-linux/data/platform_config/` carry `l0_c_size=262144`.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           grep -h '^l0_c_size=' $ASCEND_HOME_PATH/aarch64-linux/data/platform_config/Ascend950*.ini | sort -u
OVERTURN:  `GetCoreMemSize(CoreMemType::L0_C, s)` returning anything but 262144 on a full 950 part,
           or a baseM×baseN basic block sized to fill 256 KB of L0C being rejected at tiling time.
```

# 0211 · L0C on DAV_3510 is 256 KB, which raises the Cube basic-block tiling ceiling

## 1 · Claim
Upstream asserts that the DAV_3510 L0C buffer — the Cube unit's output accumulator — is 256 KB
(262144 B), read from the ini field `l0_c_size`, and upstream names the programming consequence
directly: L0C capacity 影响基本块 Tiling 上限, it sets the ceiling on the basic-block tile. The
installed CANN 9.0.0-beta.2 platform-config set carries `l0_c_size=262144` in all 32 of its
`NpuArch=3510` files, invariant across every core count and L2 size present. Not established here:
`GetCoreMemSize(CoreMemType::L0_C, ...)` was never called and no tiling was built.

## 2 · The wrong branch this removes
L0C holds the accumulator for one Cube basic block, so it bounds `baseM × baseN × sizeof(accum)`.
An agent carrying a smaller figure splits N or M more finely than the hardware requires. The cost is
not a fault: it is an extra FixPipe drain and an extra L0C fill per additional split, plus more
frequent bias reconfiguration — a steady tax on every matmul-shaped operator, with correct results
throughout and nothing in a profile that says "your basic block is half the legal size".

There is a second, sharper branch. L0C is one of only two buffers whose DAV_3510 value differs from
the previous generation in the *upward* direction (the other is BT), and upstream presents it as a
delta — "**Ascend950PR 扩容**". An agent that inherits a Cube tiling template written for an earlier
part gets a template that is *valid* on 950: it fits, it runs, it is half-utilised. Templates that
are merely valid do not announce themselves, which is why this entry names the number rather than
the change.

The number also caps what an L0C→UB direct path (0225) can hand over in one shot, so an under-read
here silently shrinks the fusion window as well as the tile.

## 3 · Ground / Source
`npu-hardware-params.md:103-114`, the DAV_3510 parameter table, gives `| L0C | l0_c_size | 256 KB
(262144) |`. The cross-architecture quick table at `:149` places it: `L0C | 256 KB | 256 KB | 128 KB
| 128 KB | 256 KB`.

`npu-arch-guide.md:251-263` states the programming consequence in its Buffer-hierarchy table, which
is the sentence worth keeping because it is the only place upstream says *why* the number matters:

> | Buffer | 用途 | 编程影响 |
> | **L0A / L0B** | Cube 操作数 | MTE1 搬入目标 |
> | **L0C Buffer** | Cube 输出（**Ascend950PR 扩容**） | 影响基本块 Tiling 上限 |

and `npu-arch-guide.md:180` repeats the capacity in the per-core Buffer table with the same emphasis:
`| **L0C** | 128 KB | **256 KB** | Cube 输出（Ascend950PR 翻倍） |`.

Both files are `ops/npu-arch/` and are therefore one origin (RULES.md Art. 3); they are quoted separately
because the capacity and the consequence live in different files and a reader who opens only one
gets only half.

Second origin — the installed toolkit, read under the phase-1 read-only exception. From
`Ascend950PR_9589.ini`:

```
[AICoreSpec]
l0_a_size=65536
l0_b_size=65536
l0_c_size=262144
l1_size=524288
```

and `l0_c_size=262144` holds in all 32 `NpuArch=3510` files — every 950PR and 950DT variant, at 4,
8, 28, 32 and 36 cube cores. No 3510 ini in this install carries 131072.

A third upstream document states 256 KB and **agrees** — but the agreement is worth less than it looks.
Contradiction **C-003** in `harvest/CONTRADICTIONS.md` records
`ascendc-code-review/references/ascendc-perf.md:578` publishing a chip-agnostic 典型容量 table with UB
**256 KB**, L1 **1 MB**, L0C **256 KB**. Its L0C row matches this entry exactly. Its other two rows do
not match this book's values at all: 256 KB against UB's 248 (0209) and 1 MB against L1's 512 KB (0212).

So one row of a three-row table agrees and two disagree, and the table names no architecture. Reading
that single row as corroboration would be selecting the row that agrees — npu-arch's §3 quick table
shows 256 KB is also the correct L0C for DAV_1001 and DAV_2002, so a table written from an older family
would land on 256 here by coincidence while missing the other two. The honest statement is that C-003's
agreement on L0C carries no evidential weight for DAV_3510, and this entry's second origin remains the
installed ini alone.

That matters for what `corroborated` is worth here: both origins are vendor ini data (0204), so the
stratum raises the priority of running §4 and raises nothing else.

Note also what the two origins do *not* jointly establish: `npu-arch-guide.md:184-188` is explicit
that the tabulated buffer figures are 族系典型值 and that `GetCoreMemSize` is authoritative. The
identity between `l0_c_size` and that return value is asserted by upstream and untested here.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion.

Arm A — report the value, and report which file it came from:

```cpp
auto plat = platform_ascendc::PlatformAscendC(context->GetPlatformInfo());
uint64_t l0c = 0, l0a = 0, l0b = 0;
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L0_C, l0c);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L0_A, l0a);
plat.GetCoreMemSize(platform_ascendc::CoreMemType::L0_B, l0b);
std::printf("l0c=%llu l0a=%llu l0b=%llu soc=%s\n", (unsigned long long)l0c,
            (unsigned long long)l0a, (unsigned long long)l0b, /* resolved SoC string */);
```

L0A and L0B are printed alongside deliberately: they are 64 KB on every architecture upstream lists
(0213), so they act as an in-probe control — if all three come back wrong together, the fault is the
probe or the resolved platform info, not L0C.

Arm B — the boundary, which is what establishes the tiling ceiling rather than a reported number.
Build a matmul kernel and sweep `baseM × baseN` upward with fp32 accumulation until host tiling
rejects the block or the launch fails. Record the largest accepted `baseM × baseN × 4` and the
smallest rejected. Under this entry the boundary sits at 262144; under a 128 KB L0C it sits at
131072, and the two are a clean factor of two apart, so the sweep cannot land ambiguously between
them. The sweep is run at a fixed baseK so that only the accumulator footprint varies — L0C is the
one buffer whose occupancy is independent of K, and holding K fixed makes that the tested premise
rather than an assumption.

Arm C — the utilisation arm, which is what makes the entry actionable rather than merely true. Run
one representative matmul at the largest block Arm B accepted and again at half that block, same
shape, same board, same build flags, and record `aiv_time`/`aic_time` for both. This does not
establish the capacity; it establishes whether the capacity is worth having, and it is the arm that
would expose a case where the larger block fits but is slower (bank behaviour, drain cost).
Measurement and inference stay separate here: Arm B measures a limit, Arm C measures a duration, and
neither licenses a sentence about the other.

Device selection is explicit throughout: the operator names the device index, the probe prints it
back with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run
(shared machine, ≤4 dies), and no die is substituted for another.

## 5 · Checker — acceptance declared before the run
Verdict variable `l0c_bytes`, taken from Arm B's largest accepted block — not from Arm A. Arm A can
only show that the API agrees with the ini, and both origins here *are* ini-derived, so Arm A cannot
discriminate; only a boundary can.

Pass is declared now as `l0c_bytes == 262144`. The alternative is named now so it cannot be
reinterpreted later: `l0c_bytes == 131072` overturns this entry and means the 950 ini set and
npu-arch carry a common error. Any third value corrects the entry in place, with the discrepancy
logged rather than rounded away.

Arm A is red if `l0a != 65536 || l0b != 65536` regardless of what `l0c` reads — the control failing
voids the reading it was there to protect.

The blinding test, stated before the run: rerun Arm B with the accumulator dtype changed from fp32
to fp16. The accepted `baseM × baseN` must double. If it does not, the sweep is not bounded by L0C
occupancy at all — it is hitting some other limit — and every value it produced is void. A checker
that only ever confirms "the sweep stopped somewhere" is the known blind species; this is the input
that makes it go red on a known answer.

Process exit code is not the verdict for any arm: a launch that faults *because* an oversized block
was accepted exits non-zero for the opposite of the reason a rejection would.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The ini values in §3 are a
read of installed files under the sanctioned phase-1 read-only exception; a file read cannot call
`GetCoreMemSize`, cannot build a tiling, and cannot distinguish reported capacity from the capacity
a basic block can actually occupy.

## 7 · Scope limits — what this entry does NOT establish
No device was contacted, no matmul was built, and no block was sized. The entry does not establish
that `GetCoreMemSize(L0_C)` returns `l0_c_size`, that all 256 KB is addressable by one basic block,
or that any of it is reserved — a reservation like the one `topk_host_tiling.md` reports for UB would
be invisible to a file read. It does not establish the *consequence* upstream states: that a larger
L0C raises the useful tiling ceiling is a plausible inference from capacity, and Arm C exists
precisely because capacity and benefit are different claims that a single sentence tends to fuse. It
says nothing about L0C behaviour under the new L0C→UB direct path (0225), nor about how L0C is shared
when Cube and Vector are both active. The reading is pinned to toolkit `9.0.0-beta.2`, host directory
`aarch64-linux`, one machine. Nothing transfers to the other book (RULES.md Art. 1): the 128 KB figures in
upstream's comparison columns are quoted as upstream's framing, and "L0C doubled" is upstream's
sentence, not a fact this book carries — this book claims only that DAV_3510 L0C is 256 KB.
