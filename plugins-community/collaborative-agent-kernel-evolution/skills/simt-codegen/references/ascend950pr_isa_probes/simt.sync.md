# `simt.sync` — block barrier + memory fences (`asc_syncthreads` / `asc_threadfence{,_block}`)

## HEAD

```yaml
head_schema: pb5/v1
op: simt.sync                          # canonical instance: cross-warp stage exchange, 8 warps, N=256
paradigm: SIMT
core: AIV
lowering: "asc_syncthreads() / asc_threadfence() / asc_threadfence_block() free functions -> __syncthreads/__threadfence builtins (block barrier; fences order GM)"
dtypes: [s32]
selection_keys: [order.cross-pipe, xlate.cuda-1to1]
not_for: [order.cross-core]            # cross-core flags/KFC → sync paradigm entry (planned)
cuda_pta_analog: "__syncthreads / __threadfence / __threadfence_block"
false_friends: [warp_collectives_do_not_need_block_barrier, barrier_in_divergent_branch_deadlocks,
                fence_is_ordering_not_barrier]
cost_model:
  roofline_run_id: probes/simt_vote_sync/RESULTS.md
  binding_resource: UN
  optimum: {value: 1.6, unit: cycles/elem}    # whole-prog 419/256 launch-bound (R-15)
  perf_factor_K: 1.0
  latency_cycles: {barrier: UN}        # P-22 extension; not yet microbenched
  elem_per_cycle: UN
  toolchain:
    bisheng: "clang version 15.0.5 (clang-5c68a1cb1231 flang-5c68a1cb1231) 2026-05-09"
    model: "{model_name: Ascend950PR_9599, cube_cores: 32, vec_cores: 64}"
    configs: [1981_sim_ffts_plus.toml, 1981_model.toml]
verify_cmd: |
  bash ${PROBE_WORKSPACE}/scripts/build.sh k.cpp
  bash ${PROBE_WORKSPACE}/scripts/run.sh k
  bash ${PROBE_WORKSPACE}/scripts/verify.sh
sources:
  - probes/simt_vote_sync/RESULTS.md            # barrier 0/256 vs NOSYNC 65/256
  - "simt_api/device_sync_functions.h:20"       # asc_syncthreads/threadfence decls
status: piloted
tier_summary:
  - {claim: barrier makes cross-warp exchange exact (0/256), tier: T1-sim}
  - {claim: removing barrier yields 65/256 stale reads (silent hazard, reproducible), tier: T1-sim}
  - {claim: barrier cost, tier: UN}
```

## 0 · SELECT
Within-warp exchange needs NO barrier (collectives are warp-synchronous). Cross-WARP within block →
here. Cross-core ordering → sync-paradigm flags (planned).

## 1 · CONTRACT
`asc_syncthreads()` block barrier across all warps (🟢 exchange exact only with it). Fences order GM
visibility; not barriers. Free functions, no `Simt::` prefix (🧾H :20-24).

## 2 · USE
```cpp
// stage[i]=3x+1; barrier; z[i]=stage[(i+191)%256] across warps. errors=0 iff barrier present.
#include "kernel_operator.h"
#include "simt_api/asc_simt.h"
using namespace AscendC;
constexpr uint32_t T = 256;
__simt_vf__ LAUNCH_BOUND(T) inline void Body(__gm__ int32_t *x, __gm__ int32_t *st, __gm__ int32_t *z, uint32_t n) {
    uint32_t tid = Simt::GetThreadIdx<0>();
    if (tid >= n) return;
    st[tid] = x[tid] * 3 + 1;
    asc_syncthreads();                                  // ◀ REMOVE = silent stale reads (65/256)
    z[tid] = st[(tid + 191u) % n];
}
extern "C" __global__ __aicore__ void k(GM_ADDR x, GM_ADDR st, GM_ADDR z, uint32_t n) {
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);
    Simt::VF_CALL<Body>(Simt::Dim3{T,1,1}, (__gm__ int32_t*)x, (__gm__ int32_t*)st, (__gm__ int32_t*)z, n);
}
#ifndef __CCE_AICORE__
#include "acl/acl.h"
#include <cstdio>
#include <cstdlib>
#define CHECK(expr) do { aclError _e = (expr); \
    if (_e != ACL_SUCCESS) { std::printf("ACL FAIL %s -> %d\n", #expr, (int)_e); return 1; } } while (0)
int main() {
    constexpr uint32_t N = 256; const size_t b = N * 4;
    CHECK(aclInit(nullptr)); CHECK(aclrtSetDevice(0));
    aclrtStream s = nullptr; CHECK(aclrtCreateStream(&s));
    int32_t *hx=(int32_t*)malloc(b), *hz=(int32_t*)malloc(b), *hr=(int32_t*)malloc(b), *h0=(int32_t*)calloc(N,4);
    for (uint32_t i=0;i<N;++i) hx[i]=(int32_t)i-100;
    for (uint32_t i=0;i<N;++i) hr[i]=hx[(i+191u)%N]*3+1;
    void *dx,*dst,*dz; CHECK(aclrtMalloc(&dx,b,ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK(aclrtMalloc(&dst,b,ACL_MEM_MALLOC_HUGE_FIRST)); CHECK(aclrtMalloc(&dz,b,ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK(aclrtMemcpy(dx,b,hx,b,ACL_MEMCPY_HOST_TO_DEVICE)); CHECK(aclrtMemcpy(dst,b,h0,b,ACL_MEMCPY_HOST_TO_DEVICE));
    k<<<1,nullptr,s>>>((GM_ADDR)dx,(GM_ADDR)dst,(GM_ADDR)dz,N);
    CHECK(aclrtSynchronizeStream(s)); CHECK(aclrtMemcpy(hz,b,dz,b,ACL_MEMCPY_DEVICE_TO_HOST));
    uint32_t errors=0; for (uint32_t i=0;i<N;++i) errors += (hz[i]!=hr[i]);
    std::printf("RESULT: errors=%u/%u\n", errors, N); fflush(stdout);
    return errors ? 2 : 0;
}
#endif
```
Pass = errors=0 AND SQE≥1. fflush after RESULT.

## 3 · HAZARDS
| Hazard | Symptom | Repair | Evidence |
|---|---|---|---|
| missing barrier on cross-warp staging | stale reads — measured 65/256, deterministic | asc_syncthreads() between write/read | 🟢 NOSYNC arm |
| barrier in divergent branch | deadlock/undefined | all threads call (uniform) | 🧾H + 🧠IN |
| fence used as barrier | data still stale | fence orders, barrier waits | 🧾H |

## 4 · PERF
Whole-prog 419 launch-bound; barrier dep cost ❓UN (P-22 ext). Once per stage round; correctness-first.

## 5 · EVIDENCE & EDGES
0/256 vs 65/256 (`probes/simt_vote_sync/RESULTS.md`); decls :20-24. ❓UN: cost. Siblings: vote · shuffle · reduce.warp-sum.
