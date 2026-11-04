# `simt.shuffle` — warp lane-exchange (`WarpShfl{,Up,Down,Xor}Sync`)

## HEAD

```yaml
head_schema: pb5/v1
op: simt.shuffle                       # canonical instance: z[i] = rotate-by-1 within warp, int32, N=4096
paradigm: SIMT
core: AIV
lowering: "AscendC::Simt::WarpShfl{,Up,Down,Xor}Sync<T> -> SIMT_SHFL (one warp-collective per call; no memory traffic)"
dtypes: [s32]                          # VERIFIED bit-exact; u32/f32/half declared (🧾H) — verify per dtype
selection_keys:
  - control.divergent-per-element
  - xlate.cuda-1to1
not_for:
  - pattern.reduction-full             # → use simt.reduce.warp-sum (native REDUX) or SIMD vcadd
cuda_pta_analog: "CUDA __shfl_sync / __shfl_{up,down,xor}_sync"
false_friends: [no_butterfly_needed_for_reduce_use_native_redux,
                out_of_range_up_down_keeps_own_value_not_zero, shuffle_has_no_memory_traffic]
cost_model:
  roofline_run_id: probes/simt_shuffle/RESULTS.md
  binding_resource: UN          # launch-bound whole-prog at probed N; body cost = SHFL collective
  optimum: {value: 0.102, unit: cycles/elem}            # whole-prog 419 cy @ N=4096 (launch-bound)
  perf_factor_K: 1.0
  latency_cycles:
    SIMT_SHFL_dep: 17           # dependent-chain cadence, min=max, UNR-invariant (P-22)
    SIMT_REDUX_dep: 16          # for comparison — a full reduce ≈ one SHFL
  elem_per_cycle: "1 SHFL per element per call; no LDG/STG from the exchange itself"
  toolchain:
    bisheng: "clang version 15.0.5 (clang-5c68a1cb1231 flang-5c68a1cb1231) 2026-05-09"
    model: "{model_name: Ascend950PR_9599, cube_cores: 32, vec_cores: 64}"
    configs: [1981_sim_ffts_plus.toml, 1981_model.toml]
verify_cmd: |
  bash ${PROBE_WORKSPACE}/scripts/build.sh k.cpp
  bash ${PROBE_WORKSPACE}/scripts/run.sh k
  bash ${PROBE_WORKSPACE}/scripts/verify.sh
  bash ${PROBE_WORKSPACE}/scripts/profile_simt.sh k   # expect SHFL count == elements, LDG/STG only from x/z
sources:
  - probes/simt_shuffle/RESULTS.md                     # 4 semantics errors=0 + edge law
  - probes/simt_isa_cost/RESULTS.md                    # SHFL 17 cy dependent
  - "simt_api/cpp/kernel_simt_warp_level_intf.h:33"    # WarpShflSync<T> family decls
status: piloted
tier_summary:
  - {claim: rot/up/down/xor bit-exact vs exact-permutation host ref, tier: T1-sim}
  - {claim: up/down out-of-range lanes keep OWN value, tier: T1-sim}
  - {claim: dependent SHFL cadence 17 cy, tier: T1-sim}
  - {claim: dtypes beyond s32, tier: UN}
```

## 0 · SELECT
Need a full warp sum/max/min → `simt.reduce.warp-sum` (one REDUX=16cy beats a 5-step butterfly ≈85cy).
Need data exchange (rotate/broadcast/prefix shifts/transpose tricks) → here. CUDA `__shfl_*_sync(mask,…)`
maps 1:1 minus the mask arg (whole-warp implicit).

## 1 · CONTRACT
`T WarpShflSync(T v, int srcLane, int width=32)` / `Up(delta)` / `Down(delta)` / `Xor(mask)` (🧾H :33+).
🟢 verified: srcLane rotation exact; Up Δ=1 lane0 keeps own; Down Δ=1 lane31 keeps own; Xor pairs swap.
Convergence: warp-synchronous — call from all 32 lanes.

## 2 · USE
```cpp
// z = warp-rotate-by-1(x), int32, N=4096; mutate the marked line for Up/Down/Xor.
#include "kernel_operator.h"
#include "simt_api/asc_simt.h"
using namespace AscendC;
constexpr uint32_t T = 256;
__simt_vf__ LAUNCH_BOUND(T) inline void Body(__gm__ int32_t *x, __gm__ int32_t *z, uint32_t n) {
    uint32_t tid = Simt::GetThreadIdx<0>() + Simt::GetBlockIdx() * Simt::GetThreadNum<0>();
    uint32_t stride = Simt::GetBlockNum() * Simt::GetThreadNum<0>();
    uint32_t lane = Simt::GetThreadIdx<0>() % Simt::GetWarpSize();
    for (uint32_t i = tid; i < n; i += stride) {
        int32_t v = x[i];
        z[i] = Simt::WarpShflSync(v, (int32_t)((lane + 1) & 31), 32);   // ◀ MUTATE: Up/Down(1u,32) | Xor(1,32)
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
#define CHECK(expr) do { aclError _e = (expr); \
    if (_e != ACL_SUCCESS) { std::printf("ACL FAIL %s -> %d\n", #expr, (int)_e); return 1; } } while (0)
int main() {
    constexpr uint32_t N = 4096; const size_t b = N * 4;
    CHECK(aclInit(nullptr)); CHECK(aclrtSetDevice(0));
    aclrtStream s = nullptr; CHECK(aclrtCreateStream(&s));
    int32_t *hx = (int32_t *)malloc(b), *hz = (int32_t *)malloc(b), *hr = (int32_t *)malloc(b);
    for (uint32_t i = 0; i < N; ++i) hx[i] = (int32_t)(i * 31 + 7);
    for (uint32_t i = 0; i < N; ++i) { uint32_t lane = i & 31u, base = i & ~31u;
        hr[i] = hx[base + ((lane + 1) & 31)]; }                       // mirror the MUTATE here
    void *dx, *dz; CHECK(aclrtMalloc(&dx, b, ACL_MEM_MALLOC_HUGE_FIRST)); CHECK(aclrtMalloc(&dz, b, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK(aclrtMemcpy(dx, b, hx, b, ACL_MEMCPY_HOST_TO_DEVICE));
    k<<<8, nullptr, s>>>((GM_ADDR)dx, (GM_ADDR)dz, N);
    CHECK(aclrtSynchronizeStream(s)); CHECK(aclrtMemcpy(hz, b, dz, b, ACL_MEMCPY_DEVICE_TO_HOST));
    uint32_t errors = 0; for (uint32_t i = 0; i < N; ++i) errors += (hz[i] != hr[i]);
    std::printf("RESULT: errors=%u/%u\n", errors, N); fflush(stdout);
    return errors ? 2 : 0;
}
#endif
```
Pass = errors=0 AND SQE≥1. (fflush after RESULT — a non-zero exit drops unflushed stdout.)

## 3 · HAZARDS
| Hazard | Symptom | Repair | Evidence |
|---|---|---|---|
| Up/Down edge assumed 0 | edge lanes wrong | edges KEEP OWN value — host ref must mirror | 🟢 SH1/2 errors=0 + ref law |
| call in divergent branch | undefined exchange | warp-synchronous — call from all lanes | 🧾H |
| butterfly for reduce | ~5×17 cy wasted | native REDUX = 16 cy | 🟢 P-22 |
| width<32 semantics assumed | unverified | ❓UN — T-ref a width slice | ❓UN |

## 4 · PERF
SHFL dep 17 cy; no GM traffic. Whole-prog launch-bound at probed N (K=1.0, R-15). Closed loop:
profile_simt → SHFL count == elements/lane, no extra LDG/STG. ❓UN: ≥1M, sub-32 width, dtypes.

## 5 · EVIDENCE & EDGES
4 semantics errors=0/4096 (`probes/simt_shuffle/RESULTS.md`); SHFL 17 (`probes/simt_isa_cost`); decls 🧾H :33+.
Siblings: simt.reduce.warp-sum (native reduce) · simt.vote (mask collectives).
