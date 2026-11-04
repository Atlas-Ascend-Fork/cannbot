# `simt.elementwise.binary` — per-thread elementwise binary op on the AIV (SIMT path)

## HEAD

```yaml
head_schema: pb5/v1
op: simt.elementwise.binary            # canonical instance: z[i] = x[i] + y[i], f32, N=1024
paradigm: SIMT
core: AIV
lowering: "__simt_vf__ body dispatched by AscendC::Simt::VF_CALL (KERNEL_TYPE_AIV_ONLY)"
dtypes: [f32]                          # ONLY f32 is verified; other dtypes are header-declared, verify before claiming
selection_keys:
  - access.gather-scatter
  - control.divergent-per-element
  - xlate.cuda-1to1
not_for:
  - access.contiguous-elementwise      # → sibling simd.elementwise.binary: SIMD is primary on 950PR
cuda_pta_analog: "CUDA grid-stride elementwise kernel (threadIdx/blockIdx/blockDim)"
false_friends: [launch_api_is_chevrons_not_aclrtLaunchKernel, host_code_needs_CCE_AICORE_guard,
                warp32_is_not_simd_register64, ub_is_not_shared_cache, no_fp4_mx_casts_on_simt]
cost_model:
  roofline_run_id: probes/rooflines/simt_elementwise/   # full sweep: 14 grid points × 3 reps
  binding_resource: UN          # measured: NO tunable resource binds at N=1024 (cycles flat 419-420
                                # across all knobs); launch_overhead = PROPOSED PB-5 key, 🧠IN cause
  optimum: {value: 0.409, unit: cycles/elem}            # 419 cycles total @ N=1024 f32
  perf_factor_K: 1.0                                    # naive(b8,T256)=419 = best
  latency_cycles:               # per emitted SIMT-ISA op (P-22 dependent-chain cadence, stamp cy; sim figures)
    SIMT_FADD: 3
    SIMT_IMAD_I: 7
    SIMT_LDG_dep: "~57/iter issue, lsu RTT ~173 (RANGE)"
    SIMT_STG_dep: "~255 lsu RTT (RANGE)"
  elem_per_cycle: 0.78          # 1024 / 1315 measured body lsu span (probes/simt_isa_cost/ew_profile; sim figure)
  toolchain:
    bisheng: "clang version 15.0.5 (clang-5c68a1cb1231 flang-5c68a1cb1231) 2026-05-09"
    model: "{model_name: Ascend950PR_9599, cube_cores: 32, vec_cores: 64}"
    configs: [1981_sim_ffts_plus.toml, 1981_model.toml]   # logical aliases -> physical 1982_cloud_config.toml (probes/arch_extract/)
verify_cmd: |
  bash ${PROBE_WORKSPACE}/scripts/build.sh k.cpp
  bash ${PROBE_WORKSPACE}/scripts/run.sh k
  bash ${PROBE_WORKSPACE}/scripts/verify.sh
  bash ${PROBE_WORKSPACE}/scripts/profile_simt.sh k   # body mix + cadence; expect LDG:STG=2:1, FADD/elem
sources:
  - probes/cannsim_20260602091800_entry_use_selftest/  # THIS entry's §USE, as-pasted: errors=0, 419 cycles
  - probes/simt_isa_cost/RESULTS.md                    # P-22 per-op cadences (v2 conformance 2026-06-10)
  - probes/cannsim_20260602083312_p09_test/            # add kernel, errors=0
  - book_samples/ct_A/cannsim_20260602025956_k/        # sibling mutate (mul), errors=0
  - probes/rooflines/simt_elementwise/                 # roofline sweep (SWEEP.md: 14 points x 3 reps)
  - "__clang_cce_simt_dav3510_intrinsic.h:472"         # const int warpSize = 32
  - "tikcpp/tikcfw/impl/utils/kernel_utils_constants.h:172"  # VECTOR_REG_WIDTH = 256
status: piloted
tier_summary:
  - {claim: build+run+bit-exact f32, tier: T1-sim}
  - {claim: VF_CALL programming model, tier: T1-sim}
  - {claim: warpSize=32, tier: H}
  - {claim: SIMD vector reg = 256 B, tier: H}
  - {claim: no __shared__ in simt_api, tier: H}
  - {claim: SIMT auxiliary vs SIMD primary, tier: IN}
  - {claim: K=1.0 and config-invariance 419±1 cycles at N=1024, tier: T1-sim}
  - {claim: invariance caused by launch overhead + memory latency, tier: IN}
```

## 0 · SELECT

You likely arrived from CUDA elementwise code. Route first:

```
contiguous regular access, no per-element branch  → simd.elementwise.binary (sibling — SIMD is primary)
gather/scatter, divergent branch, 1:1 CUDA port   → stay here (SIMT)
```

**Intercept these CUDA priors** (each verified on 950PR — see EVIDENCE):

| Your CUDA prior | 950PR fact | Tier |
|---|---|---|
| Launch with a runtime call (`cudaLaunchKernel`/`aclrtLaunchKernel`) | **No host launch API. The ONLY verified launch is `k<<<blockDim, l2ctrl, stream>>>(…)`** | 🟢T1-sim |
| Host code compiles standalone | This file compiles **twice** (host + device pass). **Guard ALL host-only code with `#ifndef __CCE_AICORE__`** | 🟢T1-sim |
| warp = vector register width | warp = 32 **threads**; the SIMD datapath register is 256 B = 64 f32 lanes — different machine | 🧾H |
| `__shared__` exists | absent from `simt_api/**` headers; the on-core buffer is UB, not an implicit cache | 🧾H |
| any dtype cast inside a thread | f32↔fp8/hif8 paths exist on SIMT; bf16→fp4/e8m0/e6m2 are **not** on the SIMT scalar path | 🥈T2 |

## 1 · CONTRACT

| Claim | Tier · source |
|---|---|
| `extern "C" __global__ __aicore__ void k(GM_ADDR …)` + `KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY)` pins the kernel to the AIV (vector) core | 🟢T1-sim · `probes/cannsim_20260602083312_p09_test/` |
| Per-thread body: `__simt_vf__ LAUNCH_BOUND(T) inline void Body(__gm__ float*, …, uint32_t)` dispatched with `Simt::VF_CALL<Body>(Simt::Dim3{T,1,1}, args…)` | 🟢T1-sim · same run |
| Indices: `Simt::GetThreadIdx<0>()`, `GetBlockIdx()`, `GetThreadNum<0>()`, `GetBlockNum()`; grid-stride loop covers any N | 🟢T1-sim · same run |
| Host launch: `k<<<blockDim, nullptr, stream>>>(dx, dy, dz, N)` — blockDim = number of blocks | 🟢T1-sim · same run |
| Operands `__gm__ T*` (global memory) | 🟢T1-sim |
| f32 add/mul are IEEE-exact per element ⇒ device == host bitwise | 🟢T1-sim · `RESULT: errors=0` |
| warp width = 32 | 🧾H · `__clang_cce_simt_dav3510_intrinsic.h:472` |
| dtypes beyond f32 declared in headers — NOT yet verified | ❓UN · run §2 with that dtype |

## 2 · USE — paste, build, run, verify

One complete file (`k.cpp`). Device kernel + full host harness. Mutate ONE marked line for sibling ops.

```cpp
// Ascend 950PR SIMT elementwise binary: z[i] = x[i] OP y[i], f32, N=1024.
// Build:
//   source /usr/local/Ascend/ascend-toolkit/set_env.sh
//   bisheng --asc-aicore-lang --npu-arch=dav-3510 k.cpp -o k \
//     -I$ASCEND_HOME_PATH/aarch64-linux/include -L$ASCEND_HOME_PATH/lib64 \
//     -Wl,-rpath,$ASCEND_HOME_PATH/lib64 -lascendcl -lruntime
// Run:
//   cannsim record ./k -s Ascend950 -g
// Pass: prints "RESULT: errors=0/1024"

// ---------------- device ----------------
#include "kernel_operator.h"
#include "simt_api/asc_simt.h"
using namespace AscendC;

constexpr uint32_t T = 256;  // threads per block

__simt_vf__ LAUNCH_BOUND(T) inline void Body(__gm__ float *x, __gm__ float *y,
                                             __gm__ float *z, uint32_t n) {
    uint32_t stride = Simt::GetBlockNum() * Simt::GetThreadNum<0>();
    for (uint32_t i = Simt::GetThreadIdx<0>() + Simt::GetBlockIdx() * Simt::GetThreadNum<0>();
         i < n; i += stride)
        z[i] = x[i] + y[i];  // ◀── MUTATE for sibling op; mirror in href below
}

extern "C" __global__ __aicore__ void k(GM_ADDR x, GM_ADDR y, GM_ADDR z, uint32_t n) {
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);
    Simt::VF_CALL<Body>(Simt::Dim3{T, 1, 1},
                        (__gm__ float *)x, (__gm__ float *)y, (__gm__ float *)z, n);
}

// ---------------- host (host-only pass: keep the guard) ----------------
#ifndef __CCE_AICORE__
#include "acl/acl.h"
#include <cstdio>
#include <cstdlib>

extern "C" __global__ __aicore__ void k(GM_ADDR x, GM_ADDR y, GM_ADDR z, uint32_t n);

#define CHECK(expr) do { aclError _e = (expr); \
    if (_e != ACL_SUCCESS) { std::printf("ACL FAIL %s -> %d\n", #expr, (int)_e); return 1; } } while (0)

int main() {
    constexpr uint32_t N = 1024;
    const size_t bytes = N * sizeof(float);
    const uint32_t blockDim = 8;

    CHECK(aclInit(nullptr));
    CHECK(aclrtSetDevice(0));
    aclrtStream stream = nullptr;
    CHECK(aclrtCreateStream(&stream));

    float *hx = (float *)std::malloc(bytes), *hy = (float *)std::malloc(bytes);
    float *hz = (float *)std::malloc(bytes), *href = (float *)std::malloc(bytes);
    for (uint32_t i = 0; i < N; ++i) {
        hx[i] = 0.5f * (float)i - 13.0f;           // non-trivial values:
        hy[i] = 1.25f * (float)(i % 17) + 0.375f;  // a broken kernel cannot pass
        href[i] = hx[i] + hy[i];                   // ◀── MUTATE together with device op
    }

    void *dx = nullptr, *dy = nullptr, *dz = nullptr;
    CHECK(aclrtMalloc(&dx, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK(aclrtMalloc(&dy, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK(aclrtMalloc(&dz, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK(aclrtMemcpy(dx, bytes, hx, bytes, ACL_MEMCPY_HOST_TO_DEVICE));
    CHECK(aclrtMemcpy(dy, bytes, hy, bytes, ACL_MEMCPY_HOST_TO_DEVICE));

    k<<<blockDim, nullptr, stream>>>((GM_ADDR)dx, (GM_ADDR)dy, (GM_ADDR)dz, N);

    CHECK(aclrtSynchronizeStream(stream));
    CHECK(aclrtMemcpy(hz, bytes, dz, bytes, ACL_MEMCPY_DEVICE_TO_HOST));

    uint32_t errors = 0;                       // bit-exact compare (§2.6 mode (a))
    for (uint32_t i = 0; i < N; ++i) {
        uint32_t a, b;
        __builtin_memcpy(&a, &hz[i], 4);
        __builtin_memcpy(&b, &href[i], 4);
        if (a != b && errors++ < 8)
            std::printf("  mismatch[%u]: dev=%.9g ref=%.9g\n", i, hz[i], href[i]);
    }
    std::printf("RESULT: errors=%u/%u\n", errors, N);

    aclrtFree(dx); aclrtFree(dy); aclrtFree(dz);
    std::free(hx); std::free(hy); std::free(hz); std::free(href);
    aclrtDestroyStream(stream);
    aclrtResetDevice(0);
    aclFinalize();
    return errors == 0 ? 0 : 2;
}
#endif  // __CCE_AICORE__
```

**Verify ladder** — run the three `verify_cmd` lines in order; `verify.sh` prints `result=` / `sendStarsSQE=` / `cycle:` then a `VERIFY_PASS` or `VERIFY_FAIL` verdict. Pass = `errors=0/1024` **and** `sendStarsSQE ≥ 1` — `errors=0` with no `sendStarsSQE` means the kernel never launched (host-only no-op false pass). Manual extraction (never dump full logs): `grep -h "RESULT: errors" <run_dir>/cannsim.log`.

**Build/run repair table:**

| Symptom | Cause | Fix |
|---|---|---|
| `no aicore arch specified` | missing arch flag | add `--npu-arch=dav-3510` |
| undeclared `aclrtMalloc` … | missing host include | `#include "acl/acl.h"` in host section |
| `aclrtLaunchKernel` undeclared | invented launch API | host launches with `k<<<blocks, l2ctrl, stream>>>(…)` |
| device-pass errors in host code | missing TU guard | wrap host section in `#ifndef __CCE_AICORE__` |
| link error `acl*` / `runtime` | missing libs | `-lascendcl -lruntime` + `-Wl,-rpath,$ASCEND_HOME_PATH/lib64` |
| `errors=N>0` | device/host op differ | mutate BOTH marked lines (device op + `href`) identically |

## 3 · HAZARDS — silent (compiles fine, results wrong)

| Hazard | Symptom | Repair | Evidence |
|---|---|---|---|
| missing `i < n` guard in grid-stride | OOB writes corrupt neighbors | always `i < n; i += stride` | 🟢 entry's verify ladder |
| D2H before `aclrtSynchronizeStream` | stale output buffer | sync, then `aclrtMemcpy` | 🟢 harness order |
| host/device op mismatch | persistent `errors>0` | mutate both marked lines | 🟢 run evidence |
| fp8/hif8/fp4 conversions on SIMT path | fp4 not reachable: compile error; fp8 = silent range loss | conversions live in SIMD vcvt | 🥈 `probes/simd_fp4_probe.cpp` |
| HiF8 ROUND::H upward bias | round-trip drift ≈ +½ ULP | use bit-exact harness | 🟢 `probes/cannsim_20260602015237_fp_layout_probe/` |
| trusting sim self-check | none exists | host reference compare only | 🧠 toolchain census |

## 4 · PERF — measured cost model (🟢T1-sim)

**Roofline** (`probes/rooflines/simt_elementwise/SWEEP.md` — 14 grid points × 3 reps, all errors=0):
- **419 cycles total at N=1024 f32 — flat (±1 cycle) across blocks 1→64, T 64→1024, divergent branch, strided permutation.** Optimum = naive = **0.409 cycles/elem** ⇒ **K = 1.0**. 🟢T1-sim.
- Binding resource: **none of the tunables binds at this shape** (`UN` in HEAD). The flatness itself is measured; its cause — fixed launch + memory-path latency — is 🧠IN (no analyzer cycle-breakdown decoded yet). Same plateau for SIMD vadd (419–420) ⇒ SIMD-vs-SIMT **not resolvable** at N=1024.

**Body cost (v2 conformance 2026-06-10, 🟢T1-sim, sim figures — never hardware rates):** the per-thread
body is invisible to cannsim's trace but measured on msprof-sim reg_log/lsu (P-22). Per element: 2×LDG
(dep ~57/iter issue, RTT ~173) + 1 FADD (3) + 1 STG (~255 RTT) — GM round-trips dominate; compute is ~2%.
Measured §USE body: LDG=2N/threads, STG=N/threads per warp (lsu 64:32 = 2:1), span 1315 cy ⇒ ~0.78 elem/cy.
Closed loop: `profile_simt.sh ./k` must show LDG:STG = 2:1 and FADD count = elems/lane.

What this means for you:
```
1. N ≲ 10^3 elementwise → launch overhead dominates. Don't tune; eliminate launches (fuse kernels).
2. The body is GM-latency-bound (LDG/STG RTT ≫ FADD 3) — coalesce + enough warps to overlap RTT;
   occupancy toward ≤64 warps/core; divergence costs nothing here (uniform body); SIMD sibling for contiguous.
3. After mutating: run verify_cmd (incl. profile line); LDG:STG ratio off ⇒ wrong loads/stores per element.
```
❓UN: knob effects at data-dominant N (≥1 M) — SWEEP.md closing experiment.

## 5 · EVIDENCE & EDGES

- Build+run+verify (f32 add): `probes/cannsim_20260602083312_p09_test/`. Sibling mutate (mul): `book_samples/ct_A/cannsim_20260602025956_k/`. Toolchain pin: HEAD `cost_model.toolchain`.
- Headers: warp 32 — `__clang_cce_simt_dav3510_intrinsic.h:472`; vector reg 256 B — `kernel_utils_constants.h:172`; `__shared__` absent in `simt_api/**` (0 matches).
- 🧠IN "SIMT auxiliary": datapath sizes f32 — SIMD 64 lanes vs warp 32. The N=1024 cycle compare (`probes/rooflines/{simd_vadd,simt_elementwise}/`) did NOT resolve it (both 419–420, overhead-bound); stays 🧠IN until a data-dominant-N compare.
- 🟢T1-sim: cost model — roofline `probes/rooflines/simt_elementwise/` (K=1.0, overhead-bound at N=1024).
- Body costs (v2): `probes/simt_isa_cost/RESULTS.md` (P-22 cadences) + `ew_profile` run (LDG 64 : STG 32, span 1315 cy).
- ❓UN: knob effects at N ≥ 1M (re-sweep) · dtypes beyond f32 (T-ref per dtype).
- Siblings: `simd.elementwise.binary` (the SIMD-primary contiguous path) · `simt.reduce.warp-sum` (warp combine) · `simt.ldst.global` / `simt.atomic.rmw` (planned, census P1).
