# `simt.ldst.global` — per-thread global loads/stores (`__ldg`/`__stg`, B8–B128, L2 hints)

## HEAD

```yaml
head_schema: pb5/v1
op: simt.ldst.global                   # canonical instance: z[i] = x[i] + 1 via __ldg/__stg, int32, N=4096
paradigm: SIMT
core: AIV
lowering: "__ldg(__gm__ T*) / __stg(__gm__ T*, T) -> SIMT_LDG / SIMT_STG per element (B8..B64 one op, B128 two); L2-hint + cache/uncache templates lower to ld/st_{cache,uncache}_b{8,16,32} builtins"
dtypes: [s8, u8, s16, s32, s64, b128]  # all five widths VERIFIED errors=0; other same-width dtypes share the lowering
selection_keys:
  - access.gather-scatter
  - xlate.cuda-1to1
not_for:
  - move.bulk-copy                     # → DMA (MOV_*_ALIGN) is the bulk path; per-thread ldst is for irregular access
  - access.contiguous-elementwise      # → simd.elementwise.binary
cuda_pta_analog: "CUDA __ldg / plain global deref + __stcg-style cache hints"
false_friends: [ldg_is_not_required_plain_deref_also_lowers, b128_is_two_ops_not_one,
                hints_change_cache_policy_not_count, ub_is_not_shared_cache]
cost_model:
  roofline_run_id: probes/simt_ldst/RESULTS.md          # count law + spans (data-dominant sweep is the standing UN)
  binding_resource: UN          # GM round-trip latency at probed N (overhead-bound whole-prog); body GM-bound
  optimum: {value: 0.102, unit: cycles/elem}            # whole-prog 419 cy @ N=4096 (launch-bound)
  perf_factor_K: 1.0                                    # overhead-bound shape (R-15)
  latency_cycles:
    SIMT_LDG_dep: "~57/iter issue, lsu RTT ~173 (RANGE)"
    SIMT_STG_dep: "~255 lsu RTT (RANGE)"
  elem_per_cycle: "count law: 1 op/elem B8-B64, 2 ops/elem B128; spans cold-flat (RANGE)"
  toolchain:
    bisheng: "clang version 15.0.5 (clang-5c68a1cb1231 flang-5c68a1cb1231) 2026-05-09"
    model: "{model_name: Ascend950PR_9599, cube_cores: 32, vec_cores: 64}"
    configs: [1981_sim_ffts_plus.toml, 1981_model.toml]
verify_cmd: |
  bash ${PROBE_WORKSPACE}/scripts/build.sh k.cpp
  bash ${PROBE_WORKSPACE}/scripts/run.sh k
  bash ${PROBE_WORKSPACE}/scripts/verify.sh
  bash ${PROBE_WORKSPACE}/scripts/profile_simt.sh k   # expect LDG==STG==N/lanes (B128: 2N)
sources:
  - probes/simt_ldst/RESULTS.md                        # count law + 5-width errors=0 + spans
  - probes/simt_isa_cost/RESULTS.md                    # P-22 dependent LDG/STG figures
  - "__clang_cce_simt_dav3510_intrinsic.h:24"          # LD_L2CacheType hints FV/LV/PERS/PREF/NOTALLOC_*
  - "__clang_cce_simt_dav3510_intrinsic.h:206"         # __ldg typed overloads (B8 shown; B16..B128 follow)
status: piloted
tier_summary:
  - {claim: 5 widths build+run errors=0, tier: T1-sim}
  - {claim: 1 LDG + 1 STG per element B8..B64; B128 = 2 ops each, tier: T1-sim}
  - {claim: hint enum changes cache policy not instruction count, tier: H}
  - {claim: dependent LDG ~57/iter issue + RTT ~173; STG ~255, tier: T1-sim}
  - {claim: hint perf effect at data-dominant N, tier: UN}
```

## 0 · SELECT
Bulk regular copy → DMA. Contiguous elementwise → SIMD. Per-thread irregular access inside a SIMT
kernel → here. Intercepts: plain `x[i]` deref also lowers to SIMT_LDG (🟢 ew profile) — `__ldg` adds
hint control, not access; B128 (`int4`) is 2 ops/element; UB never acts as implicit `__shared__`.

## 1 · CONTRACT
`T __ldg(__gm__ T*)` / `void __stg(__gm__ T*, T)` per thread; widths B8–B128 (🧾H :206+). Hint
templates `LD_L2CacheType` (FV default; :24-31). Bit-exact roundtrip across 5 widths (🟢 RESULTS).
B128 = `int4`, lowers 2× ops (🟢 lsu count). Loads return after RTT — overlap by warps (🟢 P-22).

## 2 · USE — paste, build, run, verify
```cpp
// z[i] = x[i] + 1, int32, N=4096 via __ldg/__stg. Build/run/verify: HEAD verify_cmd.
#include "kernel_operator.h"
#include "simt_api/asc_simt.h"
using namespace AscendC;
constexpr uint32_t T = 256;
__simt_vf__ LAUNCH_BOUND(T) inline void Body(__gm__ int32_t *x, __gm__ int32_t *z, uint32_t n) {
    uint32_t tid = Simt::GetThreadIdx<0>() + Simt::GetBlockIdx() * Simt::GetThreadNum<0>();
    uint32_t stride = Simt::GetBlockNum() * Simt::GetThreadNum<0>();
    for (uint32_t i = tid; i < n; i += stride) {
        int32_t v = __ldg(&x[i]);          // ◀ MUTATE width: int8_t/int16_t/int64_t/int4
        __stg(&z[i], v + 1);
    }
}
extern "C" __global__ __aicore__ void k(GM_ADDR x, GM_ADDR z, uint32_t n) {
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);
    Simt::VF_CALL<Body>(Simt::Dim3{T, 1, 1}, (__gm__ int32_t *)x, (__gm__ int32_t *)z, n);
}
#ifndef __CCE_AICORE__
#include "acl/acl.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#define CHECK(expr) do { aclError _e = (expr); \
    if (_e != ACL_SUCCESS) { std::printf("ACL FAIL %s -> %d\n", #expr, (int)_e); return 1; } } while (0)
int main() {
    constexpr uint32_t N = 4096; const size_t b = N * sizeof(int32_t);
    CHECK(aclInit(nullptr)); CHECK(aclrtSetDevice(0));
    aclrtStream stream = nullptr; CHECK(aclrtCreateStream(&stream));
    int32_t *hx = (int32_t *)std::malloc(b), *hz = (int32_t *)std::malloc(b);
    for (uint32_t i = 0; i < N; ++i) hx[i] = (int32_t)i - 2048;
    void *dx, *dz; CHECK(aclrtMalloc(&dx, b, ACL_MEM_MALLOC_HUGE_FIRST)); CHECK(aclrtMalloc(&dz, b, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK(aclrtMemcpy(dx, b, hx, b, ACL_MEMCPY_HOST_TO_DEVICE));
    k<<<8, nullptr, stream>>>((GM_ADDR)dx, (GM_ADDR)dz, N);
    CHECK(aclrtSynchronizeStream(stream)); CHECK(aclrtMemcpy(hz, b, dz, b, ACL_MEMCPY_DEVICE_TO_HOST));
    uint32_t errors = 0; for (uint32_t i = 0; i < N; ++i) errors += (hz[i] != hx[i] + 1);
    std::printf("RESULT: errors=%u/%u\n", errors, N);
    aclrtFree(dx); aclrtFree(dz); std::free(hx); std::free(hz);
    aclrtDestroyStream(stream); aclrtResetDevice(0); aclFinalize(); return errors ? 2 : 0;
}
#endif
```
Pass = `errors=0` AND `sendStarsSQE ≥ 1`; profile must show LDG==STG==N per grid pass (2N for B128).

## 3 · HAZARDS
| Hazard | Symptom | Repair | Evidence |
|---|---|---|---|
| B128 treated as 1 op in cost math | budget 2× off | count 2 LDG + 2 STG per int4 | 🟢 lsu 256 vs 128 |
| width-mismatch reinterpret | silent wrong bytes | match host/device dtype + size | 🟢 errors=0 only matched |
| hint expected to change result | none (policy only) | hints affect cache, never data/count | 🧾H :24-31 |
| dependent loads (ptr-chase) | RTT-serial ~57/iter | use independent grid-stride; warps overlap | 🟢 P-22 |

## 4 · PERF
Whole-prog 419 cy at probed N (launch-bound; K=1.0, R-15). Body is GM-RTT-bound: LDG dep ~57/iter
issue (RTT ~173), STG ~255 RTT; spans flat across widths ⇒ **wider accesses amortize per byte; B128
halves instructions per byte despite 2 ops/elem**. Closed loop: profile counts = N law. ❓UN: hint
effects + per-width slope at ≥1M.

## 5 · EVIDENCE & EDGES
- 5-width errors=0 + count law + spans: `probes/simt_ldst/RESULTS.md` (rig `simt_ldst.cpp`); ew 2:1 corroboration.
- ❓UN: hint perf at data-dominant N; non-FV hint behaviors.
- Siblings: `simt.elementwise.binary` · `simt.atomic.rmw` (planned) · DMA (bulk).
