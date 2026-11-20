# Contradictions register — domain `950-arch` (regbase / SIMT / hardware constants / evaluation)

> **TRIAGED 2026-08-25**: every row below has a phase-2 disposition in
> `harvest/TRIAGE_DOMAIN_ROWS_20260825.md` (resolved / assigned-to-round / noted / blocked).

Per-agent register for the 950-arch harvest block (`book-950/entries/0201-0299`), to be merged into
`harvest/CONTRADICTIONS.md` by the controller in wave 2. Row format follows that file.

Same topic, different advice or numbers, across upstream sources — or between an upstream source and
the vendor's installed CANN toolkit read under the phase-1 read-only exception. Recorded here and in
the affected entries' §3; resolved only by a procedure run on a named board (RULES.md Art. 7). Every quote
below was re-verified against the file during this harvest.

Toolkit pin used throughout, where "installed toolkit" appears:
`/usr/local/Ascend/cann-9.0.0-beta.2`, `Version=9.0.0-beta.2`,
`innerversion=V100R001C10SPC001B214`, `timestamp=20260328_213255003`, `arch=aarch64`.
950-era on three independent indications: 32 `Ascend950{PR,DT}_*.ini` files with `NpuArch=3510`;
an `asc/impl/basic_api/reg_compute/dav_c310/` tree; an `asc/impl/c_api/instr_impl/npu_arch_3510/`
tree. Read-only: no execution, no compilation, no device contact.

---

## C-950arch-001 · `arch35` is not a unique architecture in this install
- `npu-arch/references/npu-arch-guide.md:36-43` — "`archXX` = `arch` + DAV 编号前两位。如
  DAV_**35**10 → arch35", with a table listing exactly one NpuArch per directory.
- `npu-arch/references/npu-hardware-params.md:13-21` — the 产品映射表, declared the single truth
  source for the chip list; it has rows for DAV_1001/2002/2201/3002/3510 and **no DAV_3505 row**.
- installed toolkit — `aarch64-linux/data/platform_config/Ascend035.ini`, `Ascend035A.ini`,
  `Ascend035B.ini` all carry `NpuArch=3505`, which maps to `arch35` by upstream's own rule, and
  carry `ub_size` 32768 / 131072 / 262144, `l0_c_size=0`, `l1_size=0`, `vector_core_cnt=0`,
  `core_type_list=AICore`, `cube_m_size=1`.
→ 950 book. Carried by `950:0205`; cited by `950:0202`, `950:0213`.
Not a numeric conflict — a scope defect: the two-digit abbreviation cannot carry a chip scope.

## C-950arch-002 · `MulAddDst` vs `MulDstAdd` is a whitelist gap, not a spelling dispute (resolves B1)
- `ascendc-regbase-best-practice/references/knowledge/api/regbase_api_whitelist.md:76` — lists
  `MulAddDst` in the VF-safe binary row; `MulDstAdd` appears **nowhere** in the file. The file's own
  rule: "If an API is absent from the lists below, treat it as unavailable until you verify it in
  the installed SDK headers".
- `ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-03-fused-instr.md:1,36,51`
  — uses `MulDstAdd` uniformly, including in a precision red line.
- installed toolkit — **both are declared, in two different interface headers**:
  `include/ascendc/basic_api/interface/reg_compute/kernel_reg_compute_vec_binary_intf.h:70-71`
  declares `MulAddDst`; `.../kernel_reg_compute_vec_fused_intf.h:39-40` declares `MulDstAdd`. Both
  `__simd_callee__`, both `(U& dstReg, U& srcReg0, U& srcReg1, MaskReg& mask)`. Implementations
  differ: `MulAddDst` → `vmula`, dtypes {u16,i16,u32,i32,half,float,bf16,i64,u64}; `MulDstAdd` →
  `vmadd`, dtypes {half,float,bf16}.
→ 950 book. Carried by `950:0246`. **B1 outcome: both spellings exist; they are different APIs.**
The upstream defect is the whitelist's incompleteness, and the whitelist's own escape hatch is the
correct procedure.

## C-950arch-003 · the instruction-cost JSON gives `MulDstAdd` its sibling's semantics
- `ascendc-performance-evaluation/references/vector_instruction_types.json`, `instructions.MulAddDst`
  — `"semantic_expr": "dst = src0 * src1 + dst"`.
- same file, `instructions.MulDstAdd` — `"semantic_expr": "dst = dst + src0 * src1"`.
  The two expressions are algebraically identical; the file distinguishes the APIs only by an
  English gloss.
- `ascendc-perf-optimize/.../vec-03-fused-instr.md:51` — "`MulDstAdd(dst, src1, src2, mask)` 语义 =
  `dst = dst*src1 + src2`".
- installed toolkit — `dav_c310/kernel_reg_compute_vec_unary_impl.h:395`
  `vmadd(tmpReg, errReg, resReg, mask, modeValue);  // x2 = x2*err + x1` (a comment, not a
  declaration); and `:388` `vmula(dstRegCopy, regOne, tmpReg, ...)  // x = x + x2*0.5x`.
- same JSON, `instructions.Mula` — groups `FusedMulDstAdd` with `Mula`, but
  `kernel_reg_compute_vec_fused_intf_impl.h:64-73` shows `FusedMulDstAdd` and `MulDstAdd` forwarding
  to the same `FusedMulDstAddImpl`.
→ 950 book. Carried by `950:0248`; the operand-order claim itself is `950:0247`.
Decidable in one run: `MulDstAdd(3,5,7)` is 22 under vec-03 and 38 under the JSON.

## C-950arch-004 · `PipeBarrier<PIPE_V>` after a VF — four passages, three positions (B2)
**RESOLVED 2026-08-25 (0259 verified(950PR)):** no `PipeBarrier<PIPE_V>` is needed between two dependent regbase
`__VEC_SCOPE__` segments on 950PR — byte-identical output in 1100+ launches at five shapes, with the compiler's auto-sync ON
and OFF, while the same harness catches a removed V→MTE3 flag pair (stale bytes copied out). Position 2 holds; position 1's
barrier costs 0.22 µs per kernel at 512 fp32 and ~0 at 24576. Position 4's premise is conditional and, on this pin, auto-sync
does not insert the cross-pipe sync a hand-written `DataCopy` after a scope needs. Scope: direct launch, fp32 ≤ 24576, single core.
- `ascendc-perf-optimize/.../vec-03-fused-instr.md:54` — "VF 段后该有的 `PipeBarrier<PIPE_V>()` 要
  保留——VF 内部不替你做同步" (keep it, unconditional).
- `ascendc-regbase-best-practice/references/paradigms/common/sync-and-consistency.md:243` (also
  `:50`, `:302`) — "arch35/Ascend 950 上连续 Vector 计算之间、连续 VF 之间硬件保证顺序，无需手动
  PipeBarrier<PIPE_V>()" (not needed, hardware guarantees).
- `ascendc-regbase-best-practice/references/paradigms/quantization/references/vf-microapi-patterns.md:347`
  — "| `PipeBarrier<PIPE_ALL>()` | `__VEC_SCOPE__` 内不需要（VF 自动调度）…|".
- `ascendc-sync-check/references/sync-mechanism.md:155` — "auto-sync 开启时编译器在 V 操作间自动插入
  `PipeBarrier<PIPE_V>`，开发者无需手工添加" (conditional on auto-sync).
→ 950 book. Carried by `950:0259`. All four are one repo, so this cannot be settled by reading more.
**Two survey corrections logged with the entry**: the third passage is about `PIPE_ALL` *inside* a
scope, not `PIPE_V` after a VF; and positions 2 and 4 are compatible (a hardware guarantee plus a
compiler inserting redundant barriers). The sharp conflict is 1 vs 2.

## C-950arch-005 · no upstream source states an FP32 or INT32 Cube throughput (coverage gap)
- installed toolkit — `Ascend950PR_9589.ini` `[DtypeMKN]`: `DT_FLOAT=16,8,16`, `DT_INT32=16,8,16`,
  i.e. 2048 MAC/cycle against `Default=16,16,16` = 4096.
- `npu-arch/references/npu-arch-guide.md:82-91` — the 算力 table has BF16/FP16, FP8/HiF8/MXFP8 and
  MXFP4 rows and **no FP32 row**; `:123-145` derives only the rows that *widen* the array.
→ 950 book. Carried by `950:0221`. A gap in the declared 真源, not a numeric conflict — but the
available fallback (4096 from `[AICoreSpec]`) is wrong by 2× in the direction that reads as a
kernel defect.

## C-950arch-006 · the SIMT usable-UB budget is derived from a 256 KB base (extends C-005)
- `npu-arch/references/simt-arch-guide.md:94-96` and `:119`, `:132` — "总量 256KB" and
  "可用 UB = 256KB - 8KB(预留) - 32KB(DCache) = **216KB**".
- `ascendc-simt-tiling-design/SKILL.md:41` and `references/guide.md:73` — same arithmetic.
- `npu-arch/references/npu-hardware-params.md:110` — DAV_3510 `ub_size` = 248 KB (253952); installed
  toolkit: `ub_size=253952` in all 32 3510 inis, 262144 in none.
- `ascendc-simt-api-reference/references/overview.md:99` — "Ascend 950PR/Ascend 950DT 架构下，SIMD 与
  SIMT 混合场景中 UB 大小上限为 216KB，非混合场景返回固定值 248KB".
**RESOLVED 2026-08-25 (0238 verified(950PR)):** 253952 = plain-kernel accessor (ini/API); 221184 = 216 KB = the
DYN_UBUF grant cap and the VF-bearing kernel's accessor value; 262144 = plain access ceiling; VF access ceiling =
grant + 8192. Three quantities; the 256−8−32 arithmetic names them in the right order.
→ 950 book. Carried by `950:0238`. **This extends C-005**, which located the 216-vs-248 conflict in
`ascendc-simt-tiling-design` and `ascendc-code-review`: the 256 KB base is *inside `ops/npu-arch`
itself*, the repo's self-declared 真源, in the same skill whose hardware table says 248.
Note the coincidence that makes it undecidable by arithmetic: 256−8−32 = 248−32 = 216.

## C-950arch-007 · the SIMT tiling snippet reserves 128 KB nine lines after stating a 32 KB minimum
- `npu-arch/references/simt-arch-guide.md:130-132` — "需为 DCache 预留 ≥32KB / 若 DCache < 32KB，
  编译校验报错 / 可用 UB = 256KB - 8KB - 32KB = **216KB**".
- same file `:138-142` — `constexpr uint64_t DCACHE_SIZE = 128 * 1024; uint64_t ubsize = 256 * 1024;
  context->SetLocalMemorySize(ubsize - DCACHE_SIZE);` → 128 KB usable, not 216.
- `ascendc-simt-tiling-design/references/guide.md:63-73` — same pair, snippet placed *between* the
  rule and the 216 KB arithmetic.
→ 950 book. Carried by `950:0239`. Note `npu-arch-guide.md:305` gives the DCache *maximum* as 128 KB,
so the snippet may be reserving the ceiling as an unstated recommendation; nothing marks it as such.
The rule is stated and violated in executable code in the same section — repair is placement (one
generator for rule and snippet), not diligence.

## C-950arch-008 · the vector register width is labelled in bits by one source and bytes by three
- `ascendc-performance-evaluation/references/hardware/ascend950pr.json`, `common.vector_core_spec` —
  `"vector_reg_width_bits": 256`, `"predicate_reg_width_bits": 32`, `"wide_reg_width_bits": 768`.
- installed toolkit — `Ascend950PR_9589.ini` `[AICoreSpec]`: `vector_reg_width=256`,
  `predicate_reg_width=32`, `wide_reg_width=768` — **no unit given**.
- `npu-arch/references/npu-arch-guide.md:303` — "多条 VL=256 B 矢量寄存器".
- `ascendc-regbase-best-practice/.../vf-programming-rules.md:9` — "向量寄存器，VL=256B。b16→128 元素，
  b32→64 元素".
- same JSON's sibling file `vector_instruction_types.json` — `"bytes_per_instruction": 256`, with
  `units.bytes_per_instruction = "B/instruction"`.
→ 950 book. Carried by `950:0273`; the width claim itself is `950:0219`. Under the bits reading
VL_FP32 would be 8, not 64 — an 8× error in every VF loop bound, arriving through a field name.
The JSON's own sibling file contradicts its suffix.

## C-950arch-009 · the canonical VF loop template hardcodes the capacity its own repo forbids borrowing
- `ascendc-perf-optimize/.../vec-03-fused-instr.md:52` — "lane 数用 `GetVecLen()/sizeof(dtype)`，
  **不要借** `B32_DATA_NUM_PER_REPEAT(=64)` 或 `ONE_BLK_SIZE/sizeof(dtype)`——换 dtype/换代会全错。"
- `ascendc-regbase-best-practice/references/paradigms/common/vf-programming-rules.md:98` — the canonical
  `## 7 VF 循环范式` template opens `constexpr uint32_t kRepF32 = 256 / sizeof(float);  // = 64`.
- same file `:9` states "向量寄存器，VL=256B。b16→128 元素，b32→64 元素" and `:43` states
  "内部自动递减 VL_T（float:64，half:128）" — so the file knows the value is dtype-dependent.
- same file `:122` uses a bare `VL` identifier that the document never defines — a fourth spelling of
  one quantity inside one file (`256` literal, `kRepF32`, prose `VL=256B`, undefined `VL`).
→ 950 book. Carried by `950:0253`; the rule itself is `950:0252`. The two libraries have essentially no
coupling (2026-08-24 deep-dive: one shared line ≥40 chars), so neither sees the other's version, and a
hardcoded capacity is invisible to both gates — perf-optimize gates on msprof thresholds, regbase on
compile/correctness. **Open question that changes the repair**: if `GetVecLen()` is `__simd_callee__`
rather than `constexpr`, the substitution is ill-formed and the literal is forced, not careless
(`Q-950arch-15`).

---

### Rows checked and NOT opened
- DAV_3510 UB / BT / L0C / L1 / L0A / L0B / sparsity / core ratio: the installed ini **agrees** with
  `npu-arch` on every one (`950:0209`-`0216`). C-002 (BT 1 KB vs 4 KB) and the 950 half of C-003 /
  C-004 / C-006 are now one-sided rather than open — the ini is a second document, not a run, so
  they are not closed. See each entry's §5 for the declared pass condition.
- `ascendc-performance-evaluation` cites `Ascend/cann-9.1.0/...` ini paths in
  `hardware/ascend950pr.json`; that toolkit is **not installed on this machine**, so its 957b / 9589
  rows could not be re-verified against their own source. Its values match the 9.0.0-beta.2 ini
  where comparable. Recorded as an unverified provenance, not a contradiction.
