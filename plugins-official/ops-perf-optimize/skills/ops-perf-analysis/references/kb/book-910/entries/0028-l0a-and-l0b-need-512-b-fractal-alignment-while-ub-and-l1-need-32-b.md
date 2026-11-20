```
ID:        0028-l0a-and-l0b-need-512-b-fractal-alignment-while-ub-and-l1-need-32-b
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured, and no architecture is stated
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-analysis/references/metrics_reference.md:144-150 — "| UB (Unified Buffer) | **32B** | ONE_BLK_SIZE = 32 |", "| L0A / L0B Buffer | **512B** | 分形格式（Fractal）对齐 |", "| L0C Buffer | **64B** |", "| BT Buffer | **64B** |", "| FP Buffer | **128B** |", "| GM 搬运（最优） | **512B** |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a Cube path on a named DAV_2201 board is shown to accept an L0A or L0B operand at a non-512 B-aligned base without error or penalty.
```

# 0028 · L0A and L0B need 512 B fractal alignment, while UB and L1 need 32 B

## 1 · Claim
Upstream asserts six different alignment requirements across the memory hierarchy in one table:
UB 32 B (`ONE_BLK_SIZE`), L1 32 B, L0A and L0B 512 B (fractal format), L0C 64 B (fractal format),
BT 64 B, FP 128 B, and a 512 B optimum for GM movement reaching peak bandwidth at ≥ 16 KB. No
architecture is stated for the table. Not established here.

## 2 · The wrong branch this removes
An agent learns "32 B alignment" from the DataCopy documentation — where it is stated loudly and
repeatedly, because violating it corrupts data (0021) — and generalises it to the whole machine.
Every buffer then gets 32 B treatment, and the Cube operand buffers, which want 16× that, are
silently under-aligned. The consequence is not a data error but a FixPipe or MTE1 penalty that
appears as "Cube is slow"; upstream's own diagnosis table (§4.2, line 206) says
"| FixPipe 极高 | 随路处理受限 | 检查地址 512B 对齐 |", which is a fix for a symptom two layers
away from its cause.

The single-number generalisation is the trap because 32 B is the number an agent meets first, is
correct for the buffers it touches most, and is wrong for exactly the buffers it touches through a
high-level API where it never sees the address.

## 3 · Ground / Source
`ops/ascendc-performance-analysis/references/metrics_reference.md` §3.3 对齐要求, lines 142-150,
verbatim in full:
```
| 存储单元 | 对齐要求 | 备注 |
| UB (Unified Buffer) | **32B** | ONE_BLK_SIZE = 32，DataBlock 对齐 |
| L1 Buffer | **32B** | 标准 |
| L0A / L0B Buffer | **512B** | 分形格式（Fractal）对齐 |
| L0C Buffer | **64B** | 分形格式对齐 |
| BT Buffer | **64B** | |
| FP Buffer | **128B** | |
| GM 搬运（最优） | **512B** | ≥16KB 数据量时可达峰值带宽 |
```
The companion layout table, §3.4 lines 154-160, gives the fractal formats these alignments serve:
L0A `FRACTAL_ZZ`, L0B `FRACTAL_ZN`, L0C `FRACTAL_NZ`, L1 `FRACTAL_NZ` ("搬运到 L0A/L0B 时格式转换
开销最低"), UB "无特殊要求".

Diagnostic consequence, §4.2 line 206: "| FixPipe 极高 | 随路处理受限 | 检查地址 512B 对齐 |".
BT's 64 B restated at line 415 (see 0006).

Arithmetic worth noting, performed here: a 512 B fractal at fp16 is 256 elements = a 16×16 block
of 2-byte values, which matches the 16×16×16 Cube MAC shape of
`ops/npu-arch/references/npu-hardware-params.md:37`. That coherence is a plausibility check on the
number, not evidence for it.

One origin (this repo). The GM row's 512 B is the same figure 0020 and 0024 carry from a different
skill; the two together are still one origin.

## 4 · Procedure
Proposed, runnable later; not run. Six alignments are six claims, so §4 is a template applied
per buffer rather than one experiment, and a run that covers only L0A establishes only L0A.

1. Name the die; occupancy before and after; no substitution.
2. Per buffer, two arms differing only in the base offset of the tensor within that buffer —
   aligned to the stated requirement, and offset by half of it. One binary where possible, offset
   as a runtime argument; md5-compare builds where it is not.
3. Record three outcomes per arm, because the claim does not say which one to expect: whether it
   builds, whether the result is bitwise correct against the aligned arm, and the relevant pipe
   ratio (`aic_mte1_ratio` for L0A/L0B, `aic_fixpipe_ratio` for L0C, `aiv_mte2_time` for UB/L1).
4. Establish the run-to-run spread of the aligned arm against itself, five repeats, BEFORE
   comparing arms. Without that there is no threshold and no honest verdict.
5. L0A/L0B and L0C are usually reached through the Matmul high-level API, which may not expose the
   base address. If it does not, record that the arm could not be constructed — that is a finding
   about the API surface, not a failed experiment, and it is a likely outcome.

## 5 · Checker — acceptance declared before the run
Per buffer, verdict triple `(builds, bitwise_equal, ratio_delta)`.
The alignment requirement is upheld for a buffer iff the misaligned arm fails to build, OR is not
bitwise equal, OR shows a `ratio_delta` exceeding three times the aligned arm's own spread.
It is OVERTURNED for that buffer iff the misaligned arm builds, matches bitwise, and shows no
ratio change beyond the spread — all three, since any one alone is consistent with the requirement
being a performance preference rather than a correctness rule, and the entry does not currently
distinguish those.
The spread-first construction is what makes this able to go red: a threshold taken from the run's
own quiet arm cannot be tuned after the fact to make a null result look positive.
No verdict is issued for a buffer whose arm could not be constructed (§4 step 5); it is recorded
as NOT ATTEMPTED, never as PASS.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. **The source table states no architecture**; it sits in a
dual-architecture document, and routing to this book rests on the buffer set (L0A/L0B/L0C/BT/FP
with a separate UB) matching DAV_2201's, not on a marker. This entry does not establish whether
each alignment is a hardware requirement or a performance preference — §5 is explicitly built to
tell them apart and currently cannot. It does not establish the FP Buffer's role beyond its name;
`ops/npu-arch/references/npu-hardware-params.md:118` describes FB as FixPipe quantisation scale
storage, and whether that is the same thing as this table's "FP Buffer" is not established. The
16×16 fractal correspondence in §3 is arithmetic, not evidence.
