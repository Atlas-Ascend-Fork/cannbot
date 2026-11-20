```
ID:        0381-the-device-side-tensorlist-walker-strides-by-a-runtime-dim-count-over-a-fixed-eight-slot-shape-array
LABEL:     trap
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (ops/ascendc-simt-programming-best-practices), whose own
           layout diagram and whose own shipped walker disagree about the descriptor's stride.
           Nothing was compiled and no descriptor was walked.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-programming-best-practices/references/tensorlist-handling.md:9-18 — the
           declared layout: "ListTensorDesc: / ├── ptrOffset (uint64_t)           // dataPtr 的偏移量 /
           ├── tensorDesc[0] (TensorDesc)      // 第 0 个 tensor 的描述 / │   ├── dim (uint32_t) /
           │   ├── index (uint32_t) / │   └── shape[SHAPE_DIM] (uint64_t[])  // SHAPE_DIM 固定为 8 /
           ├── tensorDesc[1] (TensorDesc) / │   └── ... / └── dataPtr[TENSOR_DESC_NUM] (uintptr_t[])
           // 数据指针数组"
SOURCE:    same file:58-64 — the shipped device-side walker: "__simt_callee__ inline uint64_t
           SimtGetTensorShape(GM_ADDR tensorListPtr, int64_t idx, uint32_t dim) { / uint32_t dimSize =
           *(reinterpret_cast<__gm__ uint64_t*>(tensorListPtr) + 1) & 0xffffffff; / uint32_t
           descStructSize = 1 + dimSize; / __gm__ uint64_t* shapeAddrStart =
           reinterpret_cast<__gm__ uint64_t*>(tensorListPtr) + 1 + descStructSize * idx; / __gm__
           uint64_t* shapePtr = shapeAddrStart + 1 + dim; / return *shapePtr; / }"
SOURCE:    same file:50-55 — the address walker, which uses the ptrOffset field rather than a stride:
           "__gm__ uint64_t* dataAddr = reinterpret_cast<__gm__ uint64_t*>(tensorListPtr); / uint64_t
           tensorPtrOffset = *dataAddr; / __gm__ uint64_t* tensorPtr = dataAddr + (tensorPtrOffset >> 3);
           / return reinterpret_cast<__gm__ T*>(*(tensorPtr + idx));"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `ListTensorDesc` in which every `TensorDesc` occupies `1 + tensorDesc[0].dim` 64-bit words
           rather than `1 + 8` — the descriptor would then be packed to the actual dimension count, the
           layout diagram's `SHAPE_DIM 固定为 8` would be wrong, and the walker would be right. One dump
           of a real two-tensor list with different ranks decides it.
```

# 0381 · The device-side TensorList walker strides by a runtime dim count over a fixed eight-slot shape array

## 1 · Claim
Upstream asserts a memory layout for `ListTensorDesc`: a leading `ptrOffset` word, then an array of
`TensorDesc` records each containing a `dim` field, an `index` field and a `shape` array of **`SHAPE_DIM`
entries, with `SHAPE_DIM` fixed at 8**, then an array of data pointers. Upstream asserts a shipped
device-side shape walker that computes its per-descriptor stride as `descStructSize = 1 + dimSize`, where
`dimSize` is read at run time from the low 32 bits of the second 64-bit word — i.e. from `tensorDesc[0]`'s
`dim` field. Upstream asserts a separate address walker that does not stride at all: it reads `ptrOffset`,
converts it to a word count, and indexes the pointer array directly. Not established here: nothing was
compiled and no descriptor was walked.

The two assertions disagree. A fixed eight-entry shape array makes every `TensorDesc` occupy 1 + 8 = 9
64-bit words; the walker strides by 1 + `dim`. The two agree only when `dim` is 8.

## 2 · The wrong branch this removes
This is a shipped code snippet whose arithmetic contradicts the diagram forty-five lines above it, and the
disagreement is invisible in the case everyone tests first.

**Why it passes.** A list of rank-8 tensors makes `dimSize` = 8 and the stride correct. So does a list with
one tensor, where `idx` is 0 and the stride is never applied. So does *any* list whose tensors all have
rank 8. The first failing case is a list of two or more tensors of rank other than 8 — which, for the
dynamic-input operators this file exists to serve, is the normal case: a foreach operator over rank-2
tensors gives `dimSize` = 2, `descStructSize` = 3, and `SimtGetTensorShape(ptr, 1, 0)` reads word 4 of the
descriptor block instead of word 10.

**What it returns.** Not a fault. Word 4 of a rank-8 descriptor block is `shape[3]` of tensor 0 — a
plausible dimension: a positive integer, probably a power of two, of the right order of magnitude. The
kernel takes it as tensor 1's dimension 0, computes a tile count from it, and either under-processes or
over-runs the tensor. Under-processing leaves part of the output untouched; over-running reads past the
allocation. Both present as an operator that works on some shapes and not others, which is
`common_traps.md:128-143`'s "Ignoring hardware and shape constraints" — the agent goes looking for an
alignment or minimum-width constraint that does not exist.

**Which of the two is wrong is not decidable from the file.** If the descriptor really is fixed-size, the
walker should stride by 9 and is wrong. If it is variable-size and packed to the actual rank, the diagram's
`SHAPE_DIM 固定为 8` is wrong and the walker is right. Both are one origin, so this is Art. 7 territory:
one dump of a real list decides it, and until then a generating agent must not "fix" either half.

**And the second walker does not corroborate the first.** `SimtGetTensorAddr` never strides through the
descriptors at all — it reads `ptrOffset` from word 0 and jumps straight to the pointer array. That is a
sound design (the producer records where the pointer array starts, so the consumer needs no stride
arithmetic), and it means the file contains one walker that *avoids* the disputed layout question and one
that *depends on* it. The safe walker's existence is a hint about the descriptor's real nature — you record
an explicit offset when the preceding region's size is not statically known — but it is a hint, not
evidence, and §7 marks it as such.

**A third, quieter assumption.** `dimSize` is read from `*(ptr + 1) & 0xffffffff`. That is the low 32 bits
of the word holding `dim` and `index`, so it is `dim` only if `dim` precedes `index` in memory and the
target is little-endian. The diagram lists `dim` first; nothing states the endianness, and this machine is
aarch64 (little-endian by default). If either assumption fails, `dimSize` is `index` — which for
`tensorDesc[0]` is plausibly 0, making `descStructSize` = 1 and every strided read wrong from the first
descriptor onward.

## 3 · Ground / Source
The layout, `tensorlist-handling.md:9-18`, quoted in SOURCE. The operative line is
`└── shape[SHAPE_DIM] (uint64_t[])  // SHAPE_DIM 固定为 8` — 固定为 8, fixed at 8, stated as a property of
the structure rather than of a particular list.

The shape walker, `:58-64`:

> ```cpp
> // 获取第 idx 个 tensor 的第 dim 维大小
> __simt_callee__ inline uint64_t SimtGetTensorShape(GM_ADDR tensorListPtr, int64_t idx, uint32_t dim) {
>     uint32_t dimSize = *(reinterpret_cast<__gm__ uint64_t*>(tensorListPtr) + 1) & 0xffffffff;
>     uint32_t descStructSize = 1 + dimSize;
>     __gm__ uint64_t* shapeAddrStart = reinterpret_cast<__gm__ uint64_t*>(tensorListPtr) + 1 + descStructSize * idx;
>     __gm__ uint64_t* shapePtr = shapeAddrStart + 1 + dim;
>     return *shapePtr;
> }
> ```

Read against the diagram: `ptr + 1` skips `ptrOffset` and lands on `tensorDesc[0]`'s first word.
`descStructSize * idx` strides by descriptors. `+ 1 + dim` skips the `dim`/`index` word and indexes the
shape array. Every step matches the diagram except the stride's magnitude.

The address walker, `:50-55`, quoted in SOURCE. `tensorPtrOffset >> 3` converts a byte offset to a 64-bit
word count, so `ptrOffset` is in bytes and is measured from the start of the structure. No stride
arithmetic appears.

The external-parse alternative, `:70-83`, uses the vendor's own `ListTensorDesc` class
(`kernel_operator_list_tensor_intf.h`, `GetDataPtr<T>(i)`, `GetDesc(desc, i)`, `desc.GetShape(0)`) and does
none of this arithmetic. So the file offers a supported API and a hand-rolled walker for the same job, and
the disputed arithmetic lives only in the hand-rolled one. The selection guidance at `:87-90` routes by
tensor count — "有限且已知" to host-side shape passing, "不限或大量" to kernel-side parsing — so the
hand-rolled path is the one taken precisely when the list is large, i.e. when a stride error compounds.

Recorded as `C-950rem-005`. Both passages are one file in `upstream/skills-dev-main` — one origin (RULES.md
Art. 3), and the disagreement is *within* one document.

`TENSOR_DESC_NUM` appears in the diagram's last line and is defined nowhere in the file. `SHAPE_DIM` is
given as 8; the installed toolkit defines `K_MAX_SHAPE_DIM 8` in `asc/impl/utils/sys_macros.h:53-55`,
which is a neighbouring constant of the same value — deliberately **not** equated here, because a maximum
shape rank and a fixed descriptor array width are different quantities and equating them is the inference
this book refuses. It is recorded because §4 Arm C should check whether the two track.

## 4 · Procedure
Runnable later on `950PR` with a real dynamic-input operator. One dump settles the central question.

Arm A — the descriptor stride, read from a real list. Build a dynamic-input operator, invoke it with a
list of **three tensors of different ranks** — say 2, 4 and 8 — and dump the first 512 bytes of the
`ListTensorDesc` region from the host. Locate each tensor's shape values by their known contents (use
distinctive dimension sizes, e.g. 17, 19, 23) and read off the actual per-descriptor stride. That number
decides which of the two upstream statements holds, and it decides it in one observation.

Arm B — the walker, run against the same list. Call `SimtGetTensorShape(ptr, idx, dim)` for every valid
(`idx`, `dim`) pair and compare against the known shapes. Under §2 the rank-mixed list produces wrong
values from `idx` = 1 onward. Record *which* values it returns, not merely that they are wrong: whether
they are other tensors' dimensions, `index` fields, or pointer bytes tells a debugging agent what it is
looking at.

Arm C — the fixed-width question, at the source. Locate the producer-side definition of `ListTensorDesc`
and `TensorDesc` in the installed toolkit (`kernel_operator_list_tensor_intf.h` and whatever it includes)
and read the declared array width. This is a file read and may settle the contradiction without a device;
it also answers whether `SHAPE_DIM` and `K_MAX_SHAPE_DIM` are the same constant.

Arm D — the endianness and field-order assumption. From Arm A's dump, read the second 64-bit word directly
and compare its low 32 bits against the known `dim` of tensor 0. If they differ, `dimSize` is reading
`index` and the walker is wrong for a second, independent reason.

Arm E — the supported API as a control. Parse the same list with the vendor's `ListTensorDesc` class
(`GetDataPtr<T>`, `GetDesc`, `GetShape`) and compare every value against Arm A's ground truth. If the
supported path is correct where the hand-rolled walker is not, the guidance at `:87-90` — which routes
large lists to the hand-rolled path — is pointing at the broken one, and that is the recommendation
the delivered skill must invert.

Device selection is explicit: the operator names the device index, the harness prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and all arms of one comparison run on one named die in one session. Arm B may read past the
descriptor region: the allocation is over-sized and poisoned so an over-read is visible rather than a
fault.

## 5 · Checker — acceptance declared before the run
`observed_desc_stride_words` (Arm A) — the measured per-descriptor stride in 64-bit words. Pass iff it
equals 9 (`1 + SHAPE_DIM`), which confirms the diagram and refutes the walker. A stride of `1 + dim` per
descriptor is the OVERTURN and confirms the walker instead. Any third value refutes both and is the most
informative outcome.

`walker_correct_by_index` (Arm B) — per (`idx`, `dim`) pair, correct or not, reported as a grid and never
as a pass rate. The prediction is specifically that `idx` = 0 is always right and `idx` ≥ 1 is wrong on a
rank-mixed list; a pass rate of "67% correct" would be consistent with that and with several other things,
and the grid is what distinguishes them.

`declared_array_width` (Arm C) — the width read from the producer-side declaration, plus whether
`SHAPE_DIM` and `K_MAX_SHAPE_DIM` are the same symbol. Reported.

`dimsize_reads_dim` (Arm D) — true iff the low 32 bits of word 1 equal tensor 0's rank. Pass condition
**true**; false means a second independent defect.

`supported_api_correct` (Arm E) — true iff the vendor class returns every shape correctly. Pass condition
**true**. Reported separately from Arm B: if both paths are wrong, the ground truth in Arm A is suspect and
everything else is void.

The positive fixture, declared before the run: Arm A's list must include one tensor whose dimensions are
**distinctive primes** (17, 19, 23) so that a located value cannot be confused with a length, an index, a
count, or a pointer byte. If the dump cannot locate those primes at all, it is not reading the descriptor
region and every stride measurement is an artefact. And Arm B must include a control call with `idx` = 0
on a **uniform rank-8 list**, which must return the correct shape; if it does not, the walker is broken
independently of the stride question and the rank-mixed results attribute nothing. Without both, the
checker reads only "some numbers came back wrong", which is the known blind species — and here it would be
especially misleading, because wrong-but-plausible dimensions are exactly what this defect produces.

Process exit codes are not the verdict for any arm: Arm B expects wrong values from a process that exits
zero.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No operator was built, no list
constructed, no descriptor dumped, no walker called, no die contacted. The quoted passages are re-verified
file reads of the upstream tree performed during this harvest; the `K_MAX_SHAPE_DIM 8` observation is a
file read of the installed CANN 9.0.0-beta.2 tree under the phase-1 read-only exception and is explicitly
**not** claimed as corroboration of `SHAPE_DIM`.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish the descriptor's real stride, that the walker
returns wrong values, or that the diagram is right — Arms A through E are all open, and the contradiction
is stated by one origin, which Art. 7 forbids resolving by preferring the more official-looking half.

It does not establish which half is wrong. §2 states the two possibilities symmetrically on purpose: a
fixed-width descriptor makes the walker wrong, a packed descriptor makes the diagram wrong, and one dump
decides. A generating agent must not "correct" either half before that dump exists.

**The second walker is a hint, not evidence.** `SimtGetTensorAddr` avoids the stride question by reading an
explicit `ptrOffset`, and §2 notes that an explicit offset is what one records when the preceding region's
size is not statically known. That is an argument from design habit and it is not an observation about this
structure.

It does not establish the endianness or field-order assumption behind `& 0xffffffff`. The diagram lists
`dim` before `index`; nothing states either the field order in memory or the target's endianness, and Arm D
is what would confirm both.

It does not equate `SHAPE_DIM` with the toolkit's `K_MAX_SHAPE_DIM`. Both are 8 in this pin; a maximum
shape rank and a fixed descriptor array width are different quantities, and equating them on a coincidence
of value is the inference this book exists to refuse.

It says nothing about `TENSOR_DESC_NUM`, which the diagram names and no source in scope defines, nor about
how the producer writes the structure, nor about whether the layout is stable across CANN versions — a
hand-rolled walker over a vendor structure is version-coupled by construction and no source in scope says
what the compatibility contract is.

It says nothing about the host-side API table at `:39-44`, which names `GetDynamicInputDataType` while the
worked host code at `:32` calls `GetDynamicInputDesc(...)->GetDataType()` — a separate small mismatch in
the same file, noted here and not claimed.

BOARD is `family-claimed(unverified)`: a memory layout is not board-dependent, the file names no board
token this book recognises, and no board was contacted.
