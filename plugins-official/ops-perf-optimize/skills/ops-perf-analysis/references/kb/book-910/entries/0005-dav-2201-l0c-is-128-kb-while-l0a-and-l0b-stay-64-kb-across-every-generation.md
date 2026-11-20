```
ID:        0005-dav-2201-l0c-is-128-kb-while-l0a-and-l0b-stay-64-kb-across-every-generation
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:82 — "| L0C | `l0_c_size` | 128 KB (131072) |"; ibid:35-36 — "| L0A | `[AICoreSpec] l0_a_size` | 64 KB (65536) |", "| L0B | ... | 64 KB (65536) |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  `GetCoreMemSize` on a DAV_2201 part returns L0C ≠ 131072, or L0A/L0B ≠ 65536.
```

# 0005 · DAV_2201 L0C is 128 KB, while L0A and L0B stay 64 KB across every generation

## 1 · Claim
Upstream asserts that DAV_2201's Cube accumulator buffer L0C is 128 KB (131072 bytes), and that
the two Cube operand buffers L0A and L0B are 64 KB each on every Ascend architecture upstream
lists — DAV_1001, DAV_2002, DAV_2201, DAV_3002 and DAV_3510 alike. Upstream asserts that DAV_2201
is the *smaller* L0C generation: DAV_1001, DAV_2002 and DAV_3510 all carry 256 KB. Not established
here.

## 2 · The wrong branch this removes
Two distinct wrong branches, which is why the operand and accumulator sizes sit in one entry: an
agent reading "L0 buffers" as one uniform pool. The first branch sizes `baseM × baseN` from a
256 KB accumulator and over-commits L0C by 2× on DAV_2201 — the same generational-regression trap
as 0004 (a *newer* part with a *smaller* buffer than both its predecessor and its successor). The
second branch is the mirror: an agent that learns L0C shrank assumes L0A/L0B shrank too and
under-sizes `baseK`, leaving Cube throughput on the table for no reason. Upstream's own §1 heading
("跨架构一致参数") is the discriminator, and it is easy to miss because it lives in a different
section from the per-arch table.

## 3 · Ground / Source
`ops/npu-arch/references/npu-hardware-params.md` §2.3, line 82: `| L0C | \`l0_c_size\` | 128 KB
(131072) |`.

Same file, §1 跨架构一致参数 ("以下参数在所有已验证的 Ascend NPU 架构上保持一致"), lines 35-37:
```
| L0A | `[AICoreSpec] l0_a_size` | 64 KB (65536) | Cube 左矩阵操作数 |
| L0B | `[AICoreSpec] l0_b_size` | 64 KB (65536) | Cube 右矩阵操作数 |
| Cube MAC 阵列 | `cube_m_size / cube_k_size / cube_n_size` | 16×16×16 | 一个周期完成 4096 次 MAC |
```
followed immediately at line 39 by: "> **注意**：即便以上参数通常一致，代码中仍应通过
`GetCoreMemSize` 获取，避免硬编码." — upstream states the constancy and then declines to let a
reader rely on it. That qualification is inherited by this entry.

Generational row, same file §3, line 149: `| L0C | 256 KB | 256 KB | 128 KB | 128 KB | 256 KB |`.

Restated same-repo (one origin): `ops/ascendc-performance-analysis/references/metrics_reference.md`
lines 119-121 give L0A 64 KB / L0B 64 KB / L0C 128 KB for both 910B1/B2 and 910B3; line 414 of the
same file's §7 constraint table says "| L0C | 128KB (910B) / 256KB (950) | — |".

## 4 · Procedure
Proposed, runnable later; not run. Same single-pass query as 0004 §4 (name the die, occupancy
before and after, no substitution), reading `CoreMemType::L0_A`, `L0_B`, `L0_C` in the same
invocation as UB, L1 and BT, and printing NpuArch on the same line.

The 16×16×16 MAC shape quoted above is deliberately NOT part of this entry's verdict: it is not a
`GetCoreMemSize` field, it comes from a different INI section, and folding it into a capacity
check would let one measurement stand in for a claim it does not cover.

## 5 · Checker — acceptance declared before the run
Verdict variables `l0c_bytes`, `l0a_bytes`, `l0b_bytes`.
PASS iff `l0c_bytes == 131072 && l0a_bytes == 65536 && l0b_bytes == 65536`, with NpuArch 2201 on
the same line.
The three are reported separately and a partial result is a partial verdict — if L0C matches and
L0A does not, the entry is split, not passed. The specific red input: `l0c_bytes == 262144`
(the DAV_1001/DAV_3510 figure). Unwritten out-parameters are INCONCLUSIVE. Exit code is not the
verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; per-arch, so no individual board is established. The
cross-architecture constancy of L0A/L0B is upstream's assertion about "所有已验证的" architectures —
which architectures those are is not enumerated, so the claim's scope is not fully known even as
an assertion. This entry does not establish the L0C accumulation dtype width, nor how L0C capacity
translates into a `baseM × baseN` ceiling (that depends on accumulation precision, which is not
established here). It does not establish the 16×16×16 MAC shape, quoted above only as context.
