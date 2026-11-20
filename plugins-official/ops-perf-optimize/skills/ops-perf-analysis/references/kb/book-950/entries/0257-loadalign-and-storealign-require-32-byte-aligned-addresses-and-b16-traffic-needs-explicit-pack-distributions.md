```
ID:        0257-loadalign-and-storealign-require-32-byte-aligned-addresses-and-b16-traffic-needs-explicit-pack-distributions
LABEL:     boundary
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — one upstream origin (ops/ascendc-regbase-best-practice). Nothing was
           compiled; upstream names no enforcement mechanism for the alignment requirement.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-regbase-best-practice/references/paradigms/common/vf-programming-rules.md:15-34
           — "**API 选型**：新代码统一走 `LoadAlign` / `StoreAlign`（地址要求 32B 对齐）。" with the
           four worked calls, and "**约束**： / - 地址非 32B 对齐时用 `LoadUnAlign` / `StoreUnAlign` +
           `UnalignRegFor[Load|Store]` 状态对象配对 / - b16 加载必须 `DIST_UNPACK_B16`，写出必须
           `DIST_PACK_B32` / - int8/uint8 加载 `DIST_UNPACK4_B8`，写出 `DIST_PACK4_B32`"
SOURCE:    same file:21-22 — "// Load b16→f32: DIST_UNPACK_B16 只加载 VL/2 字节 (64 half = 128B)"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `LoadAlign` from a UB address that is not 32-byte aligned producing correct data on a
           950 board — the requirement would then be advice rather than a boundary; or a b16 load
           without `DIST_UNPACK_B16` producing correctly widened values.
```

# 0257 · `LoadAlign`/`StoreAlign` require 32-byte aligned addresses, and b16 traffic needs explicit pack distributions

## 1 · Claim
Upstream asserts that new Regbase code should use `LoadAlign` and `StoreAlign` uniformly for UB↔register
traffic, and that both **require the address to be 32-byte aligned**. Upstream asserts the escape hatch
for unaligned addresses: `LoadUnAlign` / `StoreUnAlign` used in a pair with an
`UnalignRegForLoad` / `UnalignRegForStore` state object. Upstream asserts a separate, mandatory
distribution parameter for sub-32-bit types: a b16 load **must** carry
`LoadDist::DIST_UNPACK_B16` and the corresponding store **must** carry `StoreDist::DIST_PACK_B32`;
int8/uint8 use `DIST_UNPACK4_B8` and `DIST_PACK4_B32`. Upstream asserts that `DIST_UNPACK_B16` loads only
`VL/2` bytes — 64 half values, 128 bytes. Upstream states `LoadAlign` takes no mask while `StoreAlign`
does. Not established here: nothing was compiled and no address was misaligned.

## 2 · The wrong branch this removes
Two independent traps live in one API pair, and they fail in opposite ways.

**Alignment.** A UB pointer offset by a loop index is aligned only if the element stride keeps it so. With
`float` and a VL-stride the offsets are multiples of 256 bytes and alignment is automatic — which is why
the canonical loop (0253) never has to think about it. Change the dtype, introduce a non-VL stride, or
offset into the middle of a tile for a tail, and the address stops being a multiple of 32. Upstream does
not say what happens then: a fault, a silently misaligned read of neighbouring data, or a truncation to
the aligned boundary. Those need different repairs and only the first is loud. The escape hatch exists —
`LoadUnAlign` with a paired state object — so upstream clearly expects the case to arise; what it does
not supply is the symptom.

**The distribution parameter.** This is the sharper one, because the default is *silently wrong for b16*
rather than absent. `LoadAlign(vReg, ptr)` on a `half` buffer without `DIST_UNPACK_B16` will load a full
VL of bytes and interpret them under whatever the default layout is; with the distribution it loads
VL/2 bytes and unpacks 64 half values into 64 32-bit lanes. So the *same call* on the same pointer means
two different things, and only one of them is a b16→f32 widening. An agent that writes the natural
`LoadAlign(vReg, halfPtr + off)` gets a register full of something, and the arithmetic downstream
proceeds on it.

The register-count consequence is what makes the error hard to see: 64 half values occupy 128 bytes, half
a register (0219). So a correct `DIST_UNPACK_B16` load fills 64 lanes from 128 bytes, and the loop stride
for a b16 path is **64 elements, not 128** — even though 128 half values fit in a register. An agent
computing its repeat count as `VL/sizeof(half)` = 128 (0252's own rule, applied without this entry) will
step twice as far as the load actually consumed and skip half the data.

That is the collision worth stating plainly: 0252 says derive the lane count from `GetVecLen()/sizeof(T)`,
and for a b16→f32 widening path that rule gives the wrong stride. The rule is right for same-width
compute and wrong for a widening load, and neither document says so.

**The asymmetry.** `LoadAlign` takes no mask; `StoreAlign` does. So a tail is handled on the way out, not
on the way in — a load always reads a full register's worth and the mask decides what is written back.
An agent that expects the load to respect a mask will read past its intended extent, which is harmless
inside a padded buffer and is a real over-read at the end of one.

## 3 · Ground / Source
`vf-programming-rules.md:13-34`, the Load/Store section in full — the API choice, the four worked forms,
and the constraints:

> ## 2 Load / Store
>
> **API 选型**：新代码统一走 `LoadAlign` / `StoreAlign`（地址要求 32B 对齐）。
>
> ```cpp
> // Load: UB → 寄存器（无 mask；srcAddr 必须 32B 对齐）
> AscendC::Reg::LoadAlign(vReg, ubPtr + offset);
>
> // Load b16→f32: DIST_UNPACK_B16 只加载 VL/2 字节 (64 half = 128B)
> AscendC::Reg::LoadAlign<T, AscendC::Reg::LoadDist::DIST_UNPACK_B16>(tReg, tPtr + offset);
>
> // Store: 寄存器 → UB（带 mask；dstAddr 必须 32B 对齐）
> AscendC::Reg::StoreAlign(ubPtr + offset, vReg, maskReg);
>
> // Store fp32→b16: DIST_PACK_B32 与 DIST_UNPACK_B16 对称
> AscendC::Reg::StoreAlign<T, AscendC::Reg::StoreDist::DIST_PACK_B32>(ubPtr + offset, vReg, maskReg);
> ```
>
> **约束**：
> - 地址非 32B 对齐时用 `LoadUnAlign` / `StoreUnAlign` + `UnalignRegFor[Load|Store]` 状态对象配对
> - b16 加载必须 `DIST_UNPACK_B16`，写出必须 `DIST_PACK_B32`
> - int8/uint8 加载 `DIST_UNPACK4_B8`，写出 `DIST_PACK4_B32`（详见 [cast-rules.md](cast-rules.md) §5）

必须 on both distribution rules — mandatory, not recommended. And the inline comment carries the
arithmetic that makes the widening intelligible: `只加载 VL/2 字节 (64 half = 128B)`. That is the only
place in this scope where the half-register load is stated, and it is a code comment.

The alignment figure connects to the installed ini: `Ascend950PR_9589.ini` `[AICoreSpec]` carries
`ubblock_size=32` (0219 §3). A 32-byte UB block and a 32-byte alignment requirement are consistent, and
the connection is deliberately **not** claimed here as corroboration — a block size and an API's address
requirement are different quantities, and equating them is the inference this book refuses. It is recorded
because §4 Arm B should check whether the boundary tracks that field.

`LoadDist` and `StoreDist` are listed in the whitelist's VF-safe traits family
(`regbase_api_whitelist.md:83`) alongside `CastTrait`, `CMPMODE`, `RoundMode`, `MaskMergeMode`,
`PostLiteral`, `DataCopyMode`, `ReduceType`, `PairReduce` — so they are template traits on VF-safe
interfaces, and the whitelist's guardrail at `:109` says "Check the VF-capable header first when the code
path uses `RegTensor`, `MaskReg`, `LoadDist`, or `StoreDist`."

`Load`, `Store`, `LoadAlign`, `StoreAlign`, `LoadUnAlignPre`, `LoadUnAlign`, `StoreUnAlign`,
`StoreUnAlignPost`, `Gather`, `Scatter` are the whitelist's "Reg load and store" family
(`:81`), all `VF Function? = Yes`. Note `LoadUnAlignPre` and `StoreUnAlignPost` in that list — the
"paired state object" protocol upstream mentions evidently involves pre/post calls, and
`vf-programming-rules.md` names the state objects without showing the sequence. So the escape hatch is
documented by name and not by form.

All quoted material is `upstream/skills-dev-main` — one origin (RULES.md Art. 3).

What upstream does not supply: what a misaligned `LoadAlign` does; the correct call sequence for the
UnAlign path; whether the distribution parameter is checkable at compile time; and the loop-stride
consequence of the half-register b16 load, which §2 derives and no document states.

## 4 · Procedure
Runnable later on `950PR`. Two independent claims, so two independent arm groups.

Arm A — the alignment boundary, and what a violation does. Build one VF performing `LoadAlign` from a UB
pointer offset by 0, 4, 8, 16, 31, 32 and 33 bytes from an aligned base, storing the loaded register to a
poisoned destination. For each offset record: does it compile; does it fault; does the data match a host
reference; and if not, *how* it differs — shifted, truncated to the aligned boundary, or garbage. The
failure *shape* is the deliverable, since upstream states the requirement and not the symptom.

Arm B — whether the boundary is 32 and whether it tracks `ubblock_size`. Repeat Arm A's sweep at offsets
around 16 and 64 to locate the actual granularity, and compare against the resolved ini's `ubblock_size`.
If the boundary is not 32, the requirement is stated wrongly; if it is 32 and `ubblock_size` were ever
different on another SKU, the relationship would be testable there.

Arm C — the distribution parameter, which is the numerically dangerous half. On a `half` source buffer,
run three builds at identical inputs on the same die in the same session: `LoadAlign` with
`DIST_UNPACK_B16`, `LoadAlign` with no distribution, and a host reference widening. Compare all three
element by element. The predicted result is that the second produces something numerically unrelated;
recording exactly what it produces is what turns 必须 into a diagnosable symptom.

Arm D — the half-register stride, which §2 derives and no source states. With `DIST_UNPACK_B16`, poison
the source beyond the expected extent and count how many *source* bytes the load consumed: 128, not 256.
Then run a full loop over a b16 buffer with the stride computed as `VL/sizeof(half)` = 128 elements and
again as 64, and compare both against a host reference. Under §2, the 128-element stride skips half the
data. This is the arm that makes the collision with 0252's rule concrete.

Arm E — the round trip. `DIST_UNPACK_B16` load followed by `DIST_PACK_B32` store back to a b16 buffer
should be identity for representable values. Any asymmetry between the two distributions shows here and
nowhere else.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared machine,
≤4 dies), and no die is substituted for another. All builds of one comparison run on one named die in one
session.

## 5 · Checker — acceptance declared before the run
Four verdict variables, never aggregated — alignment and distribution are separate claims and one holding
must not cover the other.

`align_boundary_bytes` (Arms A, B) — the smallest offset granularity at which `LoadAlign` produces
correct data. Pass iff 32. A boundary of 16 or 64 corrects the entry in place and is logged with the
observed value.

`misalign_symptom` (Arm A) — fault, shifted data, truncated data, or garbage. **Reported, not gated**:
upstream states no symptom, so there is nothing to pass against, and this is the field a debugging agent
actually needs. "Correct data at every offset" is a live outcome and would demote the requirement to
advice.

`b16_requires_dist` (Arm C) — pass iff the no-distribution build differs from the reference **and** the
`DIST_UNPACK_B16` build matches it. Both clauses in one predicate: a checker asserting only the second
would go green on a toolchain where the distribution is defaulted, which is exactly the hypothesis under
test.

`b16_source_bytes` (Arm D) — pass iff the load consumed 128 source bytes, not 256. This is the verdict
that establishes §2's stride consequence, and it is separated from `b16_requires_dist` because a correct
widening with a wrong byte count would still break every loop built on it.

The positive fixture, declared before the run: Arm C must include a `float` buffer loaded with plain
`LoadAlign` and no distribution, which **must** match its reference exactly. If it does not, the harness's
reference or its poison discipline is wrong and every b16 verdict is void — the no-distribution path is
correct for same-width types by construction, so a failure there is a harness failure, not a finding. A
second fixture for Arm A: offset 0 must always produce correct data; if it does not, the sweep is
measuring something other than alignment. Without both, the checker reads only "some loads were wrong",
which is the known blind species.

Process exit codes are not the verdict for any arm: in Arm A a fault is a possible expected outcome and is
the informative one.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No VF was compiled, no address was
misaligned, and no register was loaded. The `ubblock_size=32` field noted in §3 is a file read under the
sanctioned phase-1 read-only exception and is explicitly **not** claimed as corroboration of the API's
32-byte requirement — a UB block size and an address alignment rule are different quantities.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry does not establish the 32-byte requirement, what a misaligned access does,
or that the distribution parameters are mandatory — Arms A-E are all open, and upstream states the rules
with **no symptom for any violation**. There is **no second origin**: one upstream file, and no installed
header was read for `LoadAlign`'s declaration or for the `LoadDist` enumeration — a cheap file read that
would at least confirm the spellings and was not performed. It does not establish the `LoadUnAlign` /
`StoreUnAlign` protocol: upstream names the state objects and never shows the call sequence, and the
whitelist's `LoadUnAlignPre` / `StoreUnAlignPost` entries suggest a pre/post form that no document in this
scope demonstrates. It does not establish the int8/uint8 distributions (`DIST_UNPACK4_B8`,
`DIST_PACK4_B32`), which upstream states in one line and defers to a `cast-rules.md` §5 that this harvest
did not mine. The **half-register stride consequence** in §2 — that a b16 widening path steps 64 elements
rather than 128, contradicting a naive application of 0252's `GetVecLen()/sizeof(T)` rule — is derived
here from upstream's `只加载 VL/2 字节` comment and is stated by no source; Arm D is what would establish
it, and until then it is reasoning. It says nothing about `Load`/`Store` (the non-Align forms) or about
`Gather`/`Scatter`, which sit in the same whitelist family with different contracts. BOARD is
`family-claimed(unverified)` — the file names no board token this book recognises and none was contacted.
