```
ID:        0238-the-simt-usable-ub-budget-is-computed-from-a-256-kb-total-that-no-installed-950-ini-reports
LABEL:     trap
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 run on 950PR 2026-08-25 (direct launch, DYN_UBUF grant), via §5's declared
           variables: (`runtime_ub_nonmixed`, `runtime_ub_mixed`) = **(253952, 221184)** — the first-named
           outcome; `alloc_bound[nonmixed] − alloc_bound[mixed]` = 262144 − 229376 = **32768 = 32 KB exactly**
           (§5's declared relation, ± one 32-B block); positive fixture: a 16 KB buffer allocated ahead of
           the probed one moves both bounds by 16384 / 16384 B (declared 16384 — green).
           Arm C not run (§6). Previously harvested (three files vs one file + ini).
BOARD:     950PR (measured 2026-08-25); 950DT unverified
SOURCE:    ops/npu-arch/references/simt-arch-guide.md:94-96 — "- 总量 256KB，按分区使用 …
           - 可用 UB = 256KB - 8KB(预留) - 32KB(DCache) = **216KB**"; :119 "Unified Buffer 总量 **256KB**"
SOURCE:    ops/ascendc-simt-tiling-design/SKILL.md:41 and references/guide.md:73 —
           "可用 UB = 256KB - 8KB - 32KB = 216KB"
SOURCE:    ops/ascendc-simt-api-reference/references/overview.md:99 — "Ascend 950PR/Ascend 950DT
           架构下，SIMD 与 SIMT 混合场景中 UB 大小上限为 216KB，非混合场景返回固定值 248KB。"
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:110 — DAV_3510 "| UB | `ub_size` |
           248 KB (253952) |"; installed CANN 9.0.0-beta.2: `ub_size=253952` in all 32 3510 inis (0209).
INDEX:     means=direct-launch probes (`aclrtLaunchKernelWithHostArgs` + `ACL_RT_LAUNCH_KERNEL_ATTR_DYN_UBUF_SIZE`),
           `GetRuntimeUBSize()` echoed from a plain vector kernel and from a VF-bearing kernel under grants
           0/4096/65536/131072/196608/221184; UB access bound bisected at 32-B steps by touching the probed
           buffer's last 32 B (fresh process per probe; markers on their own 64-B GM line)
           conditions=CANN 9.1.0, `-xasc --npu-arch=dav-3510`, 950PR, device idle
           readouts: plain 253952 (all grants); VF = grant; grant ceiling 221184 (221216 → rc 107000);
           bounds plain 262144/262176, VF@221184 229376/229408; +16 KB-ahead shifts 16384 (VF) / 16384 (plain);
           probed-buffer UB address 0 → 16384
           time=2026-08-25
OVERTURN:  `GetRuntimeUBSize()` returning 262144 in a non-mixed SIMT kernel on a 950 part — the
           256 KB base is then real and 0209's ini reading describes something narrower.
```

# 0238 · The SIMT usable-UB budget is computed from a 256 KB total that no installed 950 ini reports

## 1 · Claim
Measured on 950PR (direct launch, CANN 9.1.0): `GetRuntimeUBSize()` returns **253952** (248 KB, the
ini `ub_size`) in a vector kernel that contains no VF, whatever the launch's UB grant, and returns
**exactly the launch's dynamic-UB grant** in a kernel that contains a `__simt_vf__` — 0, 4096, 65536,
131072, 196608 or 221184 — and the largest grant the launch accepts is **221184 = 216 KB** (221216 is
refused at submission). The UB address a VF-bearing kernel may touch extends to **229376 = 224 KB**
under the maximal grant (229408 refused), against **262144** for the plain kernel (262176 refused,
950:0209 reproduced); the difference is 32768 = 32 KB, the DCache minimum upstream states. So upstream's
`216 KB` is real — it is the launch-grant ceiling and what the accessor reports under it — and its
derivation `256 − 8 − 32` names the right terms in the right places: 256 KB is the access ceiling of the
plain kernel (262144), 32 KB is what the VF regime gives up (262144 − 229376), and 8 KB is the gap between
the VF regime's access ceiling and its grant ceiling (229376 − 221184), which is the VF-stack reserve
950:0209 §7 names. Nothing here contradicts 248 KB: 253952 is the ini/API figure the plain kernel
reports, and it is neither ceiling.

Inference, stated separately: the three numbers are three different quantities — an API report, a
grant cap and an access ceiling — and the "contradiction" between 216, 248 and 256 KB was three
documents each naming one of them without saying which. The trap this entry keeps is the one in §2:
copy the *method* `total − 8 − 32` onto the 248 KB API figure and you under-budget by 8 KB; copy 256 KB
as an allocation total and you overrun the plain access ceiling by nothing but the VF regime's by
32 KB.

## 2 · The wrong branch this removes
The two readings diverge by 8 KB, and which one an agent picks depends on whether it copies the
number or the subtraction.

An agent that copies `216 KB` and the API sentence is fine — that figure has an accessor behind it and
upstream says the accessor returns it.

An agent that copies the *method* — "usable = total − 8 KB reserved − 32 KB DCache" — and correctly
substitutes the total it has verified, 248 KB, computes **208 KB** and quietly under-allocates by
8 KB. That is the safe direction and costs a little throughput forever.

An agent that keeps the 256 KB base because three documents state it, and then allocates against a
part whose UB is 248 KB, overruns by 8 KB. Under 0237's partition, the overrun does not land in
unallocated space — it eats into the DCache residual, which is defined as whatever is left. So the
symptom is not a fault: it is a SIMT kernel whose DCache silently shrinks below the stated 32 KB
minimum, exactly the failure 0237 §2 describes, arriving through a base constant rather than through
a deliberate allocation.

That is the branch this entry removes: the numbers 216 and 256 travel together in the source, and only
216 has an accessor behind it. The subtraction is not reusable.

## 3 · Ground / Source
**Side A — the 256 KB base, three files.**

`npu-arch/references/simt-arch-guide.md:91-96`, in the memory-space section:

> ### Unified Buffer (UB)
> - 核内共享的本地内存
> - 总量 256KB，按分区使用（详见 `ub_partition.md`）
> - SIMT 算子不能使用全部 UB 空间，需为 DCache 预留 ≥32KB
> - 可用 UB = 256KB - 8KB(预留) - 32KB(DCache) = **216KB**

and again at `:117-132` as the UB-partition table's total ("Unified Buffer 总量 **256KB**") with the
same arithmetic at `:132`.

`ascendc-simt-tiling-design/SKILL.md:38-42`:

> ### 3. DCache 与 UB 空间分配
> - SIMT 算子 DCache 必须 >= 32KB
> - 可用 UB = 256KB - 8KB - 32KB = 216KB
> - tiling 侧通过 `SetLocalMemorySize` 设置

and `references/guide.md:73`: "可用 UB = 256KB - 8KB(预留) - 32KB(DCache最低) = **216KB**".

**Side B — 248 KB, one upstream file and the installed toolkit.**

`npu-hardware-params.md:110` gives DAV_3510 `| UB | ub_size | 248 KB (253952) |`, with `:116`
asserting that this field *is* what `GetCoreMemSize(CoreMemType::UB, ...)` returns. The installed CANN
9.0.0-beta.2 set carries `ub_size=253952` in every one of its 32 `NpuArch=3510` files, across all core
counts and L2 sizes, and 262144 in none (0209 §3).

**The reconciling passage, and the reason this is not a simple error.**
`ascendc-simt-api-reference/references/overview.md:93-99`:

> ### GetRuntimeUBSize
> 获取运行时UB空间的大小，单位为byte。开发者根据UB的大小来计算循环次数等参数值。
> **函数原型**: `__aicore__ inline uint32_t GetRuntimeUBSize()`
> **返回值**: 运行时UB空间的大小（字节）。Ascend 950PR/Ascend 950DT架构下，SIMD与SIMT混合场景中UB大小
> 上限为216KB，非混合场景返回固定值248KB。

This is the most specific statement in the set: it names both boards, distinguishes mixed from
non-mixed, and gives an accessor. Read against side B, it says the 950 UB is 248 KB and that a mixed
SIMD/SIMT kernel gets 216 KB of it — a 32 KB reduction, which matches the DCache minimum exactly and
leaves the 8 KB compiler reservation inside the 248. Under that reading the arithmetic is
`248 − 32 = 216`, and the "256 − 8 − 32" formulation reaches the right answer from a wrong base by a
compensating error of 8 KB.

That is a hypothesis, not a finding: this entry does not assert it, because 216 = 256 − 8 − 32 =
248 − 32 is exactly the kind of coincidence that makes a wrong derivation look confirmed, and
distinguishing the two requires the accessor. It is stated because it is the most likely shape of the
resolution and because it predicts a specific outcome for §4 — a non-mixed kernel should see 248 KB,
not 216 and not 256.

This extends contradiction **C-005** in `harvest/CONTRADICTIONS.md`, which recorded the 216-vs-248
disagreement as living in `ascendc-simt-tiling-design` and `ascendc-code-review`. The 256 KB base is
*inside `ops/npu-arch` itself* — the repo's self-declared 真源, in the same skill whose hardware table
says 248. Filed as `C-950arch-006`.

## 4 · Procedure
Runnable later on `950PR` and separately on `950DT` — upstream's reconciling sentence names both, and
a run on one establishes only that one.

Arm A — the accessor, in both regimes, which is the arm that decides the question. Build two SIMT
kernels, identical except that one also contains a SIMD VF (making it a mixed kernel) and one does
not. In each, call `GetRuntimeUBSize()` and store the result:

```cpp
__aicore__ inline void Probe(__gm__ uint32_t* out) { out[0] = AscendC::GetRuntimeUBSize(); }
```

Print alongside `GetCoreMemSize(CoreMemType::UB, ...)` from the tiling side and the resolved SoC
string, so all three numbers are compared on the same part (0204 §4 Step 3).

Arm B — the boundary, which establishes what is *allocatable* rather than what is reported. In each
regime, bisect the static-plus-dynamic UB allocation upward until the build or the launch refuses,
recording the largest success and smallest failure at 32-byte granularity (`ubblock_size=32`, 0219).
Under the reconciling hypothesis the non-mixed boundary sits near 248 KB minus the DCache residual and
the mixed boundary 32 KB lower. This arm is what would expose the 8 KB, because it is the only one
that can see the compiler reservation.

Arm C — the overrun arm, which tests §2's silent failure directly. Allocate against a 256 KB base —
that is, request `256KB − 8KB − 32KB` of static plus dynamic memory — and record whether the build is
refused (0237's check firing), the launch is refused, or it runs. If it runs, measure the DCache
residual's effect with the discrete-gather kernel from 0237 §4 Arm C and compare against a correctly
budgeted build at the same shape on the same die in the same session.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. All regimes for one comparison run on one
named die in one session.

**As run (2026-08-25, ub238 → ub238d with the verification run; four jobs because the instrument was
wrong twice):** Arm A as written, but on direct launch: the "mixed" regime is a kernel containing a
`__simt_vf__` (a SIMT VF beside classic vector code), and the grant is the launch attribute
`ACL_RT_LAUNCH_KERNEL_ATTR_DYN_UBUF_SIZE` rather than an op-framework `SetLocalMemorySize`; the grant
was swept (0, 4096, 65536, 131072, 196608, 221184) and its ceiling bisected at 32-B steps (221184 /
221216, refusal code 107000 at submission). Arm B as written with one substitution: "static-plus-
dynamic allocation … until the launch refuses" was instantiated as `TPipe::InitBuffer(bytes)` plus a
touch of the buffer's last 32 B (VF regime: eight `uint32_t` written from the VF; plain regime: eight
`SetValue`), fresh process per probe, 32-B bisection between 32768 and 270336; a probe counts as
granted only if the eight marker words read back from GM. Deviations recorded before the bounds were
read: (i) the refusal (507035) keys on the touched ADDRESS, not the allocation total — an untouched
16 KB buffer allocated after the probed one moved neither bound (shift 0 / 0), so the §5 fixture was
re-run with the 16 KB buffer allocated FIRST (probed buffer's UB address 0 → 16384); the
shifts reported in §6 are from that run; (ii) Arm C (allocate against a 256 KB base and measure the
DCache residual's effect with 950:0237's gather) was NOT run — the access ceilings make its first
half a foregone reading (a VF-regime allocation of 216 KB is granted, 224 KB + 32 B is refused) and
its second half needs 0237's instrument, which is not built; (iii) two instrument defects, both
mine and both pre-verdict: a GM marker written from the VF or by `DataCopy` onto the same 64-B line
as the kernel body's scalar echo words was clobbered (5/6, 0/2, then 0/all launches) — moving the
markers to their own line made them land in 100 % of probes (harvest/RUNS_20260824.md, "Same-64-B-line
clobber"); and the first fixture placed the extra buffer where it could not move the probed address.

## 5 · Checker — acceptance declared before the run
Three verdict variables, never aggregated — the entry is about a disagreement between a reported
number, a derived number and an allocatable extent, and collapsing them would hide the thing under
test.

`runtime_ub_nonmixed` and `runtime_ub_mixed` (Arm A) — the two `GetRuntimeUBSize()` values. The
outcomes are named now so none can be reinterpreted afterwards. `(253952, 221184)` confirms upstream's
reconciling sentence and means the 256 KB base is a wrong base reaching a right answer — this entry
stands as a trap about the derivation. `(262144, 221184)` overturns this entry: the 256 KB base is
real and 0209's ini reading describes something narrower than the SIMT-visible UB. Any other pair
corrects both entries in place and is logged.

`alloc_bound` (Arm B) — largest successful allocation per regime. This is the verdict that matters for
a tiling routine, and it is deliberately kept separate from Arm A: a reported size and an allocatable
size are different quantities, and the 8 KB compiler reservation is precisely the gap between them.
No pass threshold is declared for the absolute value; what is declared is the *relation* —
`alloc_bound[nonmixed] − alloc_bound[mixed]` must equal 32 KB ± one 32-byte block. A different
difference means the mixed-mode reduction is not the DCache minimum and the reconciling hypothesis is
wrong regardless of Arm A.

The positive fixture, declared before the run: rerun Arm B with the static `__ubuf__` array enlarged by
a known 16 KB. `alloc_bound` must fall by exactly 16 KB in both regimes. If it does not move, the
bisection is not measuring UB occupancy at all and every bound it produced is void. Without this the
checker only reads "the allocation stopped somewhere", which is the known blind species.

Process exit codes are not the verdict anywhere: in Arms B and C a refused build is the expected
outcome at the boundary.

## 6 · Evidence
RUN 2026-08-25, 950PR, CANN 9.1.0, device idle before and after every job.

**Arm A — `GetRuntimeUBSize()` (device echo, own 64-B line):**

| grant (DYN_UBUF attr) | plain vector kernel | VF-bearing kernel |
|---|---|---|
| none (no cfg) | 253952 | 0 |
| 4096 | 253952 | 4096 |
| 65536 | 253952 | 65536 |
| 131072 | 253952 | 131072 |
| 196608 | 253952 | 196608 |
| 221184 | 253952 | 221184 |
| 221216, 229344, 229376, 245760, 253952, 262144 | — | launch refused, rc 107000 |

`(runtime_ub_nonmixed, runtime_ub_mixed)` = (253952, 221184) at the maximal grant — §5's first-named
outcome. The VF-bearing kernel's value is the grant, not a constant: 216 KB is where the grant stops.

**Arm B — access bounds (largest granted / smallest refused, 32-B steps, fresh process each):**

| regime | grant | extra 16 KB ahead? | largest granted | smallest refused (507035) |
|---|---|---|---|---|
| plain | none | no | 262144 | 262176 |
| plain | 221184 | no | 262144 | 262176 |
| plain | none | yes | 245760 | — |
| VF | 221184 | no | 229376 | 229408 |
| VF | 221184 | yes | 212992 | — |
| VF | 65536 | no | 73728 | 73760 |
| VF | 131072 | no | 139264 | 139296 |

`alloc_bound[nonmixed] − alloc_bound[mixed]` = 262144 − 229376 = **32768**, the declared relation
(32 KB ± 32 B) — green. `alloc_bound[mixed] − grant` = 8192 at EVERY grant tested (65536 → 73728, 131072 → 139264, 221184 → 229376): the VF regime may touch exactly the grant plus 8 KB.

**Positive fixture** (a 16 KB buffer allocated FIRST, probed buffer's UB start address 0 → 16384):
VF bound fell by **16384** B, plain bound by **16384** B (declared: exactly 16384 both).
Green: the bisection measures UB address occupancy.
The first fixture placement (extra buffer allocated AFTER the probed one, never touched) moved neither
bound (0 / 0) — recorded, because it is what showed the refusal keys on the touched address.

**Arm C — not run** (§4 as-run ii).

**Instrument events (all before any verdict):** same-64-B-line clobber of GM markers by the kernel's
scalar stores (three jobs to isolate; fix = separate lines, then 100 %); first fixture placement
inert. Logs: verification run's log area ub238, ub238b, ub238c, ub238d.

## 7 · Scope limits — what this entry does NOT establish
One board (950PR), one pin (9.1.0), direct launch only: the op-framework path (`SetLocalMemorySize` /
`SetDynUBufSize` at tiling time) was not exercised, and whether it can grant more than 221184 B, or
reports the same accessor values, is not measured. "Mixed" here means a kernel containing a
`__simt_vf__`; a kernel mixing classic vector code with regbase `__VEC_SCOPE__` segments was not
probed as a regime (950:0489's regbase kernels ran on plain launch with no grant and allocated up to
~130 KB without refusal, which says they are the plain regime, not that they were bounded). The 8 KB
between the VF regime's grant ceiling and its access ceiling is measured as a difference; that it is
the VF-stack reserve is 950:0209 §7's code reading, not shown behaviourally here. The 32 KB is measured
as a difference of access ceilings; that the DCache occupies it is upstream's statement. Arm C (the
DCache-residual effect on a gather) is not run. 950DT untouched; vNPU slices untouched (950:0207).
Nothing transfers to the other book (RULES.md Art. 1).
