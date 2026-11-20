```
ID:        0076-three-different-core-count-attributes-exist-and-the-wrong-one-costs-half-the-machine
LABEL:     trap
LEVEL:     L0 (launch & host)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-host-runtime.md:13-17 — "| **纯向量计算** | `ACL_DEV_ATTR_VECTOR_CORE_NUM` | / | **矩阵计算** | `ACL_DEV_ATTR_CUBE_CORE_NUM` | / | **混合计算** | `ACL_DEV_ATTR_AICORE_CORE_NUM` |"; ibid:19-22 — "**910B3 芯片核数参考**：AI Core: 20 / Cube Core: 20 / Vector Core: 40"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  `ACL_DEV_ATTR_AICORE_CORE_NUM` and `ACL_DEV_ATTR_VECTOR_CORE_NUM` return the same value on a named DAV_2201 board.
```

# 0076 · Three different core-count attributes exist, and the wrong one costs half the machine

## 1 · Claim
Upstream asserts three distinct device attributes for core count and a rule for choosing between
them: `ACL_DEV_ATTR_VECTOR_CORE_NUM` for pure vector operators, `ACL_DEV_ATTR_CUBE_CORE_NUM` for
matrix operators, `ACL_DEV_ATTR_AICORE_CORE_NUM` for mixed. Upstream asserts the three return
different values — for Ascend910B3: AI Core 20, Cube Core 20, Vector Core 40 — and that using
`AICORE_CORE_NUM` for a pure vector operator "未充分利用 Vector Core". Upstream asserts
`aclrtGetDeviceInfo` must be called after `aclrtSetDevice`, or the count is wrong or the call fails.
Not established here.

## 2 · The wrong branch this removes
`ACL_DEV_ATTR_AICORE_CORE_NUM` is the attribute whose name most reads like "how many cores does this
device have". An agent writing a host-side launcher for an elementwise kernel picks it, gets 20 on a
910B3, and launches 20 blocks on a part with 40 Vector cores. **Half the machine idles**, and every
downstream number is consistent with itself: the tiling divides 20 ways correctly, the kernel is
correct, the per-core times are even, and the profile shows no bottleneck — because there isn't one.
The operator is simply half as fast as it could be, and nothing reports that.

This is the same defect class as 0009 (hardcoding a core count) with the query in place — an agent
that has correctly learned "never hardcode, always query" (0011) can still query the wrong thing.
The lesson 0011 teaches is necessary and not sufficient, and this entry is the part that completes
it: *which* accessor, not merely whether to use one.

Two supporting branches:
- **Call ordering.** `aclrtGetDeviceInfo` before `aclrtSetDevice` may return an error *or a wrong
  value*. The second is the dangerous case — an unchecked return with a plausible number in it.
- **The fallback default.** Upstream's own example initialises `int64_t availableCoreNum = 8;`
  before the query. If the query fails and the return is not checked, the launch proceeds at 8
  cores on a 40-core part. That literal is exactly what 0011 forbids, shipped in the reference
  implementation of the API that exists to avoid it — worth noticing, because an agent copying the
  example inherits it.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-host-runtime.md` §1.1 "核数获取 API 选择 ⚠️ **关键**",
lines 13-17, verbatim:
```
| 算子类型 | 使用的 API | 说明 |
| **纯向量计算**（Add/Mul/Div/Reduce等） | `ACL_DEV_ATTR_VECTOR_CORE_NUM` | 使用 Vector Core 数量 |
| **矩阵计算**（MatMul/Conv等） | `ACL_DEV_ATTR_CUBE_CORE_NUM` | 使用 Cube Core 数量 |
| **混合计算** | `ACL_DEV_ATTR_AICORE_CORE_NUM` | 使用 AI Core 数量 |
```
lines 19-22, verbatim: "**910B3 芯片核数参考**：
- AI Core: 20
- Cube Core: 20
- Vector Core: 40（每个 AI Core 有 2 个 Vector Core）"

The ordering rule, line 26: "**规则**：`aclrtGetDeviceInfo` **必须**在 `aclrtSetDevice` 之后调用",
with the reason at line 28 and the negative example at lines 66-72 ("可能返回错误或获取到错误值").

The error table, lines 81-83: "| **调用顺序错误** | … | 获取核数失败或返回错误值 |",
"| **写死核数** | `uint32_t numBlocks = 8;` | 不同设备性能不匹配 | 使用 `aclrtGetDeviceInfo` 动态
获取 |", "| **API 选择错误** | 纯向量算子用 `ACL_DEV_ATTR_AICORE_CORE_NUM` | 未充分利用 Vector
Core |".

The fallback literal, line 43: `int64_t availableCoreNum = 8;  // 默认值`, repeated at line 61 and
line 100.

**A fourth upstream statement on 910B3's core counts**, and the one that adds a new fact: this file
gives AI Core 20 *and* Cube Core 20 *and* Vector Core 40, where
`ops/ascendc-performance-analysis/references/metrics_reference.md:131` gives only the pair
(AIC 20 / AIV 40) — entry 0009. So "AI Core" and "Cube Core" are equal at 20 on this part, which
means the mixed-operator attribute returns the Cube figure rather than a sum. All same repo: one
origin. Consistent with `ops/npu-arch/references/npu-arch-guide.md:76`, which puts both 910B3 and
910B4 at 20 cores (entry 0062).

The kernel-side counterparts are `GetCoreNumAic()` / `GetCoreNumAiv()`
(`npu-arch-guide.md:198-199`, entry 0011); this file covers the **host** side under Kernel 直调
mode, and upstream names no host-side accessor for the buffer capacities.

## 4 · Procedure
Proposed, runnable later; not run. Host-side; a device must be present but no kernel need run.

1. Name the die; record `npu-smi info -t board -i <n>`; occupancy before and after; no substitution.
2. Attribute arm: after `aclInit` and `aclrtSetDevice`, query all three attributes and print them on
   one line with the board string. The claim predicts VECTOR = 2 × CUBE and AICORE = CUBE.
3. Ordering arm: query `ACL_DEV_ATTR_VECTOR_CORE_NUM` **before** `aclrtSetDevice`, capturing both
   the return code and the out-parameter. The informative case is a success return with a wrong
   value, so the out-parameter must be pre-set to a sentinel (not 8, and not any plausible core
   count) and reported whatever the return code says.
4. Cross-check against the kernel-side accessors: launch a trivial kernel printing
   `GetCoreNumAic()` / `GetCoreNumAiv()` and confirm they agree with the host attributes. Host and
   device disagreeing about the same machine would be the most valuable finding available here.
5. Utilisation arm, which tests §2's cost claim rather than the counts: an elementwise kernel
   launched at `AICORE_CORE_NUM` blocks and at `VECTOR_CORE_NUM` blocks, same total work, five
   repeats with the first discarded. Predicted: roughly 2× on the second.

## 5 · Checker — acceptance declared before the run
`counts` = (aicore_n, cube_n, vector_n), tagged with the board string.
PASS iff all three are non-zero, `vector_n == 2 × cube_n`, and `aicore_n == cube_n`.
The third clause is the one that makes this checker informative: if `aicore_n` equals `vector_n`
instead, the attribute-selection rule in §1 is about naming rather than about numbers, and the
"未充分利用" hazard does not exist on this part. Reported as a correction, not a failure.
`preset_ordering`: the out-parameter's value from arm 3. Three outcomes kept separate — error
return / success with the sentinel untouched / **success with a wrong value written**. The third is
the dangerous one and a boolean return-code check would miss it entirely, which is why the sentinel
is pre-set.
`host_device_agree` from arm 4 is a gate on the whole entry: a disagreement voids the attribute
verdicts, because two authorities on one machine cannot both be right.
`speedup` from arm 5: reported against the run-to-run spread of the 40-block arm, established from
its own repeats before the arms are compared.
Exit code is not the verdict; `aclrtGetDeviceInfo` returns a status separately from its output.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. The core counts are stated for **Ascend910B3**, a part
`form/CONVENTIONS.md` has no board token for (Q-910-08), so BOARD is `family-claimed(unverified)`
and under-states the source — the honest reading is in §3. This entry does not establish the counts
for any other DAV_2201 part (Q-910-07), and 0062 shows they differ. It does not establish what
`ACL_DEV_ATTR_AICORE_CORE_NUM` means physically on a part where Cube and Vector cores are separate
(0008) — that it equals the Cube count on 910B3 is upstream's number, not an explanation. It does
not cover the Kernel 直调 mode's applicability outside `.asc` `main()`, which is the file's declared
scope. It says nothing about vNPU-partitioned instances, where `npu-arch-guide.md:76` warns the
visible values are lower still.
