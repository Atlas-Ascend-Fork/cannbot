```
ID:        0074-a2-and-a3-atomic-add-covers-six-dtypes-and-excludes-fp8-while-max-and-min-are-newer-still
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-atomic.md:129-137 — the "支持的数据类型（A2/A3）" table: float, half, bfloat16_t, int8_t, int16_t, int32_t ✅ and "FP8 类型 | ❌ | 不支持，需先转 BF16/FP32"; ibid:139 — "`SetAtomicMax`/`SetAtomicMin` 仅 950/A3/A2 支持"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  `SetAtomicAdd<T>` for an FP8 type works correctly on a named DAV_2201 board, or one of the six listed dtypes is rejected.
```

# 0074 · A2/A3 atomic add covers six dtypes and excludes FP8, while max and min are newer still

## 1 · Claim
Upstream asserts a per-dtype support table for `SetAtomicAdd` scoped to A2/A3: `float`, `half`,
`bfloat16_t`, `int8_t`, `int16_t` and `int32_t` are supported; FP8 types are not, and an FP8 output
must be converted to BF16/FP32 first or accumulated at L0C and written once. Upstream asserts that
`int8_t` accumulation is available on A2/A3 while "部分更早平台不支持", and that `SetAtomicMax` and
`SetAtomicMin` exist only on 950/A3/A2 — not on 310b, 310p or the earlier 910. Upstream asserts the
template argument `T` must match the output dtype or the result is corrupted. Not established here.

## 2 · The wrong branch this removes
The dtype table is a design-time gate, and the branch it closes is a late discovery. An agent
choosing FP8 output for a bandwidth-bound multi-rank operator — a reasonable choice, since halving
the output halves the write traffic — finds at implementation time that the accumulation strategy
the design depends on is unavailable for that dtype. The workaround is not local: converting to
BF16/FP32 before accumulating restores the very bandwidth the FP8 output was chosen to save, and
accumulating at L0C instead changes which unit does the reduction.

The type-match rule closes a second and quieter branch. `SetAtomicAdd<float>()` against a
`bfloat16_t` output compiles — `T` is an independent template argument, not deduced from the
tensor — and upstream's stated consequence is "位宽和格式不匹配，导致数据损坏". Nothing connects
the two at the call site, so an output dtype changed later in development leaves the atomic
declaration behind.

The `Max`/`Min` platform note is the useful direction for once: those are available on our family
and *not* on earlier ones, so a technique carried forward from 910-era (DAV_1001) code will
under-use the machine rather than break. That is the opposite direction from 0010 and 0066, where
DAV_2201 has capabilities the newer family lost — worth noting that the family sits on both sides
of such boundaries.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-atomic.md` §5.2 "支持的数据类型（A2/A3）",
lines 129-137, verbatim in full:
```
| dtype | SetAtomicAdd | 说明 |
| `float` | ✅ | FP32 累加 |
| `half` | ✅ | FP16 累加 |
| `bfloat16_t` | ✅ | BF16 累加 |
| `int8_t` | ✅ | INT8 累加（A2/A3；部分更早平台不支持） |
| `int16_t` | ✅ | INT16 累加 |
| `int32_t` | ✅ | 整数累加 |
| FP8 类型 | ❌ | 不支持，需先转 BF16/FP32 |
```
line 139: "> 平台差异：310b 无 int8/bf16；`SetAtomicMax`/`SetAtomicMin` 仅 950/A3/A2 支持
（310b/310p/910 等更早产品不支持）。"

The FP8 remedy, line 103: "FP8 类型不支持原子操作。如果输出 dtype 是 FP8，需先转 BF16/FP32 再原子
累加，或在 L0C 级累加后单次写出。"

The type-match rule, lines 86-90: "❌ 错误：T 与输出 dtype 不一致 / `SetAtomicAdd<float>();  //
但输出是 bfloat16_t` / **后果**：原子操作的位宽和格式不匹配，导致数据损坏。"

**Worth noting against 0065.** That entry records upstream asserting "Vector 不支持 bfloat16"
(`npu-arch-guide.md:123`). Here `bfloat16_t` is listed as supported for atomic add. These are not in
conflict: atomic accumulation happens in the DMA/FixPipe path, not in the Vector unit, so a family
whose Vector cannot compute in bf16 can still accumulate bf16 on write. The two statements together
sharpen 0065 — the restriction is about the *Vector unit*, not about bf16 support on the chip — and
that reading is drawn here, not stated upstream. It is one more reason 0065's §4 needs to establish
what "不支持" actually means.

The distinction from communication-layer atomics, lines 94-97: `Hcomm::AtomicFAA` operates at the
UDMA cross-card layer for flag counters (int32/uint32/int64/uint64 only) and "两者作用层不同，不可
互换".

Same repo, one origin. An installed SDK header's overload set would be an independent origin and was
not consulted.

## 4 · Procedure
Proposed, runnable later; not run. Most of this is a compile matrix and needs no card.

1. Compile arm, no device: instantiate `SetAtomicAdd<T>()` for `float`, `half`, `bfloat16_t`,
   `int8_t`, `int16_t`, `int32_t` and an FP8 type, plus `SetAtomicMax<T>`/`SetAtomicMin<T>` for
   `float`, all targeting `__NPU_ARCH__` 2201. Record which compile. The six listed dtypes are the
   positive control: if any of them fails, the harness is wrong.
2. Header arm, read-only: `grep -Rn "SetAtomicAdd\|SetAtomicMax\|DisableDmaAtomic" \
   "$ASCEND_HOME_PATH"/*/include` for the declared overloads and any `static_assert` on `T`, with
   header path and toolkit version. This is where a dtype restriction would actually be enforced.
3. Device arm, on a named die (occupancy before and after, no substitution), per compiling dtype:
   accumulate a known set of partial sums into a pre-zeroed buffer and compare against a host
   reference — exactly for integers, within a stated tolerance for floats (0073: float atomic
   accumulation is not bit-reproducible, so an exact comparison here would be the wrong instrument).
4. Mismatch arm: `SetAtomicAdd<float>()` against a `bfloat16_t` output, deliberately, and record
   what the corruption looks like. Upstream asserts damage without describing it.

## 5 · Checker — acceptance declared before the run
`compiles(api, dtype)`: PASS iff true for all six listed dtypes and false for FP8.
An FP8 instantiation that **compiles** is the informative red input: it would mean the restriction
is undocumented in the type system, so an agent gets no compile-time protection, and arm 3 then
decides whether the result is correct or silently wrong. Those two are reported separately —
compiles-and-correct overturns §1, compiles-and-wrong converts a documented gap into a silent
corruption trap, which is strictly worse news and must not be recorded as a pass.
`accumulate_correct(dtype)`: integers compared exactly; floats within a declared tolerance, with the
tolerance derived from 0073's measured jitter for that dtype and core count, stated before the run.
`mismatch_signature` from arm 4 is reported descriptively with no pass condition.
Exit code is the observation in arm 1 only.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. "A2/A3" is two product lines spanning six parts, not a board.
This entry does not establish which FP8 encodings are meant — upstream writes "FP8 类型" without
naming e4m3, e5m2 or HiF8. It does not establish the dtype support for `SetAtomicMax`/`SetAtomicMin`,
only their platform availability; the table covers `SetAtomicAdd` alone. It does not establish what
"数据损坏" looks like on a type mismatch. The reconciliation with 0065's Vector bf16 restriction
(§3) is this book's reading and is not established by either source. No toolkit version is pinned.
