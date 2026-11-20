```
ID:        0341-a-simt-short-vector-names-its-lane-count-not-its-element-width-so-int4-is-four-int32
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   corroborated — the naming convention, INCLUDING this entry's title case. Upstream states
           it; the INSTALLED CANN 9.0.0-beta.2 headers declare `make_int4(int, int, int, int)` and
           `make_float4(float, float, float, float)`, which fix the arity and the scalar type of the
           two types the guide disambiguates, and carry `.x .y .z .w` members. `half4` is absent from
           the toolkit entirely. The PERFORMANCE claim — that widening a per-thread access pays —
           has one origin and no measurement: nothing was compiled and nothing was timed. Neither
           `sizeof` nor `alignof` was evaluated.
BOARD:     950PR, 950DT
SOURCE:    ops/ascendc-performance-best-practices/reference/simt/optimization-guide.md:114 —
           "短向量只扩大单线程一次访问宽度，不能替代相邻线程地址连续这一要求。还要区分"元素位宽"和
           "向量 lane 数"：例如 SIMT 短向量 `int4` 通常表示 4 个 `int32`，不是 4-bit 整数类型。"
SOURCE:    same file:128 — "这里的 `float4` 是由 4 个 `float` 组成的短向量，不是 FP4 数据类型" ;
           :154 — "Ascend 950PR/950DT、CANN 9.1.0 官方资料已确认多种短向量 GM 访存能力及 `float2`、
           `float4`、`half2` 等类型；该列表只是当前版本的已确认示例，不是本文维护的完整类型清单。
           其他类型（包括目标环境中的 `half4`）以对应版本头文件、API 重载和编译结果为准。" ;
           :150 — "例如 `float4` 需要 16 字节对齐，而换成其他类型时应使用该类型自己的对齐要求，
           不能沿用固定的 16 字节条件。"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — `asc/include/simt_api/vector_functions.h`
           declares the constructors that fix each type's arity and scalar:
           `:87` "inline int4 make_int4(int x, int y, int z, int w);" ·
           `:53` "inline float4 make_float4(float x, float y, float z, float w);" ·
           `:93` "inline uint4 make_uint4(unsigned int x, ..., unsigned int w);"
           `asc/impl/simt_api/vector_functions_impl.h:290-295` fills `.x .y .z .w`.
           `asc/include/simt_api/device_functions.h:132-146` declares `asc_ldcg` overloads over
           `long2/4`, `ulong2/4`, `longlong2/4`, `ulonglong2/4`; `asc_fp16.h` over the `half2`
           family. `half4` appears nowhere in the toolkit.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           grep -n 'make_int4\|make_float4' $ASCEND_HOME_PATH/asc/include/simt_api/vector_functions.h
OVERTURN:  a measured SIMT copy on a named 950 board where rewriting a scalar body as a short-vector
           body leaves achieved bandwidth unchanged outside the run spread while the generated code
           confirms the wider access issued — the width would then not be what limits the scalar
           form, and the whole rule would need a condition.
```

# 0341 · A SIMT short vector names its lane count, not its element width — `int4` is four `int32`

## 1 · Claim
Upstream asserts that in the SIMT short-vector types the trailing digit is a **lane count** over a
named scalar type, not a bit width: `int4` denotes four `int32` values and is not a 4-bit integer
type, and `float4` denotes four `float` and is not FP4. Upstream asserts what the types buy and what
they do not: a short vector widens one thread's single access, and it does **not** substitute for
the requirement that neighbouring threads address neighbouring memory. Upstream asserts a selection
procedure — build the candidate set from the target CANN version's type definitions and access-function
overloads, prefer the type carrying more useful elements per access, then fall back by each type's
own natural alignment, handle an alignment prefix and a sub-vector tail separately, and treat the
width as a tuning parameter A/B-tested per case. Upstream asserts an alignment rule with a warning:
`float4` needs 16-byte alignment and another type must use *its own* requirement rather than
inheriting 16. Upstream asserts the confirmed set for Ascend 950PR/950DT under CANN 9.1.0 —
`float2`, `float4`, `half2` among others — while stating that this list is a set of confirmed
examples for one version and not a maintained inventory, and that other types including `half4` are
settled by the target version's headers, overloads and compile result. Not established here.

## 2 · The wrong branch this removes
`int4` and `float4` are, in the surrounding low-precision-inference vocabulary, the names of 4-bit
and 4-bit-float **data types**. This shelf's own matmul family is built around MXFP4 (`0301`,
`0311`), so an agent reading a 950 optimisation guide has FP4 in working memory when it meets
`float4`. Upstream disambiguates twice, in two separate paragraphs, which is a fair indication of
how often it is misread.

The failure is not a compile error. `float4` is a real type either way in the reader's mind; the
misreading changes what the code is *believed* to do — a quantisation move rather than a widening
move — and the resulting review, tiling budget and precision reasoning are all built on the wrong
model.

The second wrong branch is treating the short vector as a substitute for coalescing. It is not:
widening one thread's access from 4 bytes to 16 does not make thread `i` and thread `i+1` adjacent.
Upstream says so directly, and the consequence is that a short-vector rewrite applied to a
badly-mapped kernel widens each of many scattered accesses and can move *more* useless bytes.

The third is the alignment inheritance. `float4` needs 16 bytes; the rule an agent extracts is "16",
and it then applies 16 to `half2` (which needs 4) and to `half4` (8) — over-constraining, or worse,
applies 16 to a wider type that needs more. Upstream's phrasing is a warning against exactly this
generalisation.

The fourth is the type list itself. `float2`/`float4`/`half2` are confirmed *examples for one
version*, explicitly not an inventory. An agent that treats the list as closed will not try `half4`;
one that treats it as open will assume `half4` exists. Upstream's instruction is neither — check the
target version's headers, the overload set, and whether the compiler actually emits the intended
width, because a type name that compiles does not prove a wide GM access was generated.

## 3 · Ground / Source
The naming rule, stated twice. `simt/optimization-guide.md:114`:

```
- 短向量只扩大单线程一次访问宽度，不能替代相邻线程地址连续这一要求。还要区分"元素位宽"和"向量
  lane 数"：例如 SIMT 短向量 `int4` 通常表示 4 个 `int32`，不是 4-bit 整数类型。
```

and `:128`, inside the worked example:

```
标量主体可按实际数据类型替换为合适的向量类型。下面仅用 `float4` 演示"向量主体 + 标量尾部"的通用
写法；实际实现可以换成 `float2`、`half2`、目标环境支持的 `half4` 或其他向量类型，并同步调整
`VecT`、lane 数和对齐要求。这里的 `float4` 是由 4 个 `float` 组成的短向量，不是 FP4 数据类型：
```

The vector-body-plus-scalar-tail pattern, `:130-144`, is the shape the whole rule serves:

```cpp
using VecT = float4;                  // 仅作示例，也可选择其他受支持向量类型
constexpr uint32_t kLanes = 4;       // VecT 包含的标量元素数
__gm__ VecT* inputVec = reinterpret_cast<__gm__ VecT*>(input);
uint32_t vecCount = count / kLanes;  // count 表示标量元素数

for (uint32_t i = threadIdx.x; i < vecCount; i += blockDim.x) {
    outputVec[i] = inputVec[i];
}

// 不足一个 VecT 的尾部保持标量处理。
for (uint32_t i = vecCount * kLanes + threadIdx.x; i < count; i += blockDim.x) {
    output[i] = input[i];
}
```

The selection procedure and its alignment caution, `:147-152`:

```
1. 从目标 CANN 版本的类型定义和访存接口重载中建立候选集合；项目自定义的向量类型也必须确认编译器
   能生成目标宽度的 GM load/store，不能只凭类型名判断。
2. 优先尝试一次承载更多有效元素的类型，再结合自然对齐逐级回退。例如 `float4` 需要 16 字节对齐，
   而换成其他类型时应使用该类型自己的对齐要求，不能沿用固定的 16 字节条件。
3. 主体按 `VecT` 的 lane 数处理；对齐前缀和不足一个向量的尾部单独处理，禁止未对齐强转、越界读取
   或越界写入。
4. 将向量宽度作为调优参数，通过代表 case A/B 比较指令数、有效带宽、地址计算、寄存器压力和尾部开销。
```

Item 1's second clause is the sharpest line here — `不能只凭类型名判断` — and it is corroborated
by the header read below in a way upstream could not have intended: the toolkit's naming is regular,
so a type name is a *reliable* guide to lane count and an *unreliable* guide to whether a wide
access is generated. Those are different questions and upstream is warning about the second.

The version scope, `:154`:

```
Ascend 950PR/950DT、CANN 9.1.0 官方资料已确认多种短向量 GM 访存能力及 `float2`、`float4`、`half2`
等类型；该列表只是当前版本的已确认示例，不是本文维护的完整类型清单。其他类型（包括目标环境中的
`half4`）以对应版本头文件、API 重载和编译结果为准。
```

### The installed headers, read

Second origin, under the phase-1 read-only exception, CANN `Version=9.0.0-beta.2`.

The decisive evidence is not the access overloads but the **constructors**, which fix each type's
arity and scalar in their own signatures.
`asc/include/simt_api/vector_functions.h`:

```
:53  __SIMT_DEVICE_FUNCTIONS_DECL__ inline float4 make_float4(float x, float y, float z, float w);
:87  __SIMT_DEVICE_FUNCTIONS_DECL__ inline int4   make_int4(int x, int y, int z, int w);
:93  __SIMT_DEVICE_FUNCTIONS_DECL__ inline uint4  make_uint4(unsigned int x, unsigned int y,
                                                             unsigned int z, unsigned int w);
```

and the implementation, `asc/impl/simt_api/vector_functions_impl.h:290-295`, assigns `.x .y .z .w`.
So `int4` is constructed from four `int` and `float4` from four `float`: the entry's title case is
settled by the toolkit and not only by the guide's prose. Nothing here is a 4-bit type, and no
4-bit type of either name exists in the header set.

The access overloads corroborate the same convention across a wider set:
`asc/include/simt_api/device_functions.h:132-146` declares `asc_ldcg` over `long2/4`, `ulong2/4`,
`longlong2/4`, `ulonglong2/4`, and `asc_fp16.h` over the `half2` family. `long4` is four `long`,
`half2` is two `half`.

One negative result, and it matches upstream's hedge exactly: **`half4` appears nowhere in the
installed toolkit** — not as a constructor, not as an overload, not as a mention. Upstream writes
`其他类型（包括目标环境中的 half4）以对应版本头文件、API 重载和编译结果为准`, i.e. it declines to
claim `half4` exists and defers to the target's headers. On this target it does not, on this
version. An agent that had read the guide as listing `half4` among available types would have been
wrong here, and the guide is careful enough that it would not have been the guide's fault.

What the header read does **not** settle: `sizeof` and `alignof` (no expression was evaluated); the
type *definitions*, which appear nowhere in the tree and are therefore compiler-builtin, so their
layout is not inspectable by reading; and whether a given type's access lowers to a single wide GM
transaction — upstream's item 1, and a compile-and-disassemble question. All three are owed.

Nothing here is measured. Upstream gives no bandwidth figure, no instruction count and no case for
the short-vector rewrite, and the entry carries no magnitude.

## 4 · Procedure
Proposed, runnable later on `950PR` and separately on `950DT`. Never run in this phase.

Arm 0 — the type inventory, `[no-card]` and partially done (§3). Complete it: `grep -Rn` (not `-r`)
the installed SIMT headers for every short-vector type definition, recording each type's scalar,
lane count, `sizeof`, `alignof` and the access overloads that accept it. The `alignof` column is
what settles §2's third wrong branch without anyone reasoning about it.

Arm 1 — lane count against element width, decided by `sizeof`. A device or host `static_assert`
table: `sizeof(int4) == 4 * sizeof(int32_t)` and so on for every type Arm 0 found. This is the
entry's title claim and it is a compile-time fact.

Arm 2 — does the width reach the memory system. Build the copy loop at scalar, `float2` and
`float4`, disassemble each, and confirm the generated GM access widens. Upstream's item 1 says a
type name is not evidence; this is the arm that supplies the evidence, and without it Arm 3's
timings are unattributable.

Arm 3 — the payoff, swept. The same three builds timed on a coalesced access pattern, reporting
achieved bandwidth, instruction count, register pressure (compiler resource report) and tail cost
separately — the four quantities upstream's item 4 names. Report the whole curve; the rule is
"prefer wider, fall back on alignment", and the fallback point is what the curve shows.

Arm 4 — the non-substitution claim, which is the one most likely to be violated in practice. Repeat
Arm 3 on a *scattered* thread-to-address mapping. Upstream predicts the short vector does not
rescue it. If bandwidth improves anyway, the "cannot substitute for coalescing" statement is too
strong and the entry is corrected in place.

Arm 5 — alignment, at the boundary. Run `float4` on a 16-byte-aligned base and on a base offset by
4 bytes. The second must fail or must be handled by the prefix path; a silent success would mean the
alignment requirement is not enforced, which is worth knowing before someone relies on it not being.

Variance floor first for Arms 3–4: one build, 30 in-process runs, 5 fresh-process runs, IQR over
median, with `0327`'s same-path sibling check. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved. Refuses to assume: that a free die stays free;
that a die may be substituted; that a type name implies a wide access (Arm 2); that alignment is 16
for anything but `float4` (Arm 0's `alignof` column); that `count` is a multiple of the lane count —
the tail path is exercised by construction in every timed arm.

## 5 · Checker — acceptance declared before the run
Verdict `lane_semantics` = true iff every type in Arm 0's table satisfies
`sizeof(T) == lanes × sizeof(scalar)`. Declared before the run: any failure overturns the naming
convention for that type and the entry names it.

Verdict `width_reaches_memory[T]` from Arm 2, per type, from disassembly only.
Verdict `bandwidth_gain[T]` from Arm 3, with the floor, reported only for types where
`width_reaches_memory` is true — a bandwidth number for a type whose access did not widen is
measuring something else.
Verdict `scatter_null` = true iff Arm 4's gain is inside the floor.
Verdict `align_enforced` from Arm 5.

The exit code is not the verdict. Three guards.

First, every copy build verifies a checksum of what it copied. A vector copy loop with a wrong
`vecCount` or a dropped tail produces excellent bandwidth over the wrong number of bytes, and
`vecCount = count / kLanes` is integer division — the tail is where this pattern breaks.

Second — the input that makes this checker go red — Arm 3 is run with `count` deliberately **not** a
multiple of `kLanes`, and the checksum **must** still match. If it does, the tail path works; if the
harness never runs a non-multiple `count`, the tail loop was never executed and every green in the
run says nothing about the pattern upstream actually publishes. That fixture is a planted positive:
the tail is the half of the idiom that is easy to get wrong and impossible to see in a
round-number benchmark.

Third, `bandwidth_gain` is never reported without `width_reaches_memory` beside it. Separating "the
type is wider" from "the access is wider" is the whole content of upstream's item 1, and a checker
that reports only the timing collapses them.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no
access was disassembled, no bandwidth was measured, and no alignment was violated.

A header read **was** performed (§3), against CANN 9.0.0-beta.2: `make_int4(int, int, int, int)` and
`make_float4(float, float, float, float)` at `vector_functions.h:87,53`, with `.x .y .z .w` assigned
in the implementation; `asc_ldcg` overloads over `long2/4`, `ulong2/4`, `longlong2/4`,
`ulonglong2/4` and the `half2` family; and no occurrence of `half4` anywhere in the toolkit. That
establishes what these names denote in one toolkit's declarations. It does not establish `sizeof`,
`alignof`, the types' layout (they are compiler-builtin and undefined in the tree), or that any of
these lowers to a wide GM transaction.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The naming convention is corroborated for `int4`, `uint4` and
`float4` by their constructors and for eight further types by their access overloads; `half4` was
searched for and is absent from this toolkit, which corroborates upstream's refusal to claim it
rather than contradicting anything. No `sizeof` or `alignof` was evaluated, and the types'
definitions are compiler-builtin and absent from the tree, so their layout is asserted by their
constructors' signatures and not by any struct this book has read. Nothing establishes that any
short-vector access lowers to a single wide GM transaction, which is upstream's own stated caution
and the load-bearing half of the technique. Upstream supplies **no performance figure** — no
bandwidth, no instruction count, no case — so the entry carries a rule and no magnitude. The
confirmed type list is scoped by upstream to CANN 9.1.0 and is declared not to be an inventory; this
book read 9.0.0-beta.2, a different version. The alignment requirement is stated for `float4` only.
The non-substitution claim (short vectors do not replace coalescing) is asserted and untested.
BOARD is `950PR, 950DT` because upstream's type-confirmation sentence names those parts; no run has
occurred on either. Nothing transfers to the other book (RULES.md Art. 1) — the SIMT programming model is
stated by upstream to be DAV_3510-era.
