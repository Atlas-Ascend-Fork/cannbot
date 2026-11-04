# `simt.vote` — warp predicate collectives (`WarpAllSync`/`WarpAnySync`/`WarpBallotSync`/`WarpActiveMask`)

## HEAD

```yaml
head_schema: pb5/v1
op: simt.vote                          # canonical instance: per-lane predicate (lane<K) → warp votes, N=64
paradigm: SIMT
core: AIV
lowering: "AscendC::Simt::Warp{All,Any,Ballot}Sync(int32 pred) / WarpActiveMask() -> vote_{all,any,uni}/ballot/activemask builtins (one warp-collective per call)"
dtypes: [s32]                          # predicates int32; ballot/mask u32
selection_keys: [control.divergent-per-element, xlate.cuda-1to1]
not_for: [pattern.reduction-full]      # numeric reduce → simt.reduce.warp-sum / SIMD vcadd
cuda_pta_analog: "__all_sync / __any_sync / __ballot_sync / __activemask (mask arg implicit, whole warp)"
false_friends: [no_mask_argument_whole_warp_implicit, ballot_bit_i_is_lane_i,
                result_broadcasts_to_all_lanes, collective_must_be_convergent]
cost_model:
  roofline_run_id: probes/simt_vote_sync/RESULTS.md
  binding_resource: UN
  optimum: {value: 6.5, unit: cycles/elem}     # whole-prog 419 cy / 64 elems (launch-bound, R-15)
  perf_factor_K: 1.0
  latency_cycles:
    collective_class: "16-17 dep (REDUX/SHFL class; vote not separately benched — UN)"
  elem_per_cycle: "1 collective per warp per call"
  toolchain:
    bisheng: "clang version 15.0.5 (clang-5c68a1cb1231 flang-5c68a1cb1231) 2026-05-09"
    model: "{model_name: Ascend950PR_9599, cube_cores: 32, vec_cores: 64}"
    configs: [1981_sim_ffts_plus.toml, 1981_model.toml]
verify_cmd: |
  bash ${PROBE_WORKSPACE}/scripts/build.sh k.cpp
  bash ${PROBE_WORKSPACE}/scripts/run.sh k
  bash ${PROBE_WORKSPACE}/scripts/verify.sh
sources:
  - probes/simt_vote_sync/RESULTS.md             # 12-cell known-answer matrix errors=0
  - "simt_api/cpp/kernel_simt_warp_level_intf.h:19"  # All/Any/Ballot/ActiveMask decls
status: piloted
tier_summary:
  - {claim: All/Any/Ballot/ActiveMask exact on 12-cell matrix, tier: T1-sim}
  - {claim: result broadcasts to all lanes, tier: T1-sim}
  - {claim: per-call cost ≈ collective class 16-17, tier: UN}
```

## 0 · SELECT
Boolean warp decisions / lane masks → here. Numeric combine → reduce.warp-sum. CUDA `*_sync(mask,p)`
drops the mask: whole warp implicit, convergent call required.

## 1 · CONTRACT (all 🟢 verified, every lane reads same value)
All(p): 1 iff all 32 lanes p≠0 (K=32→1; 13→0). Any(p): 1 iff any (K=0→0; else 1).
Ballot(p)→u32: bit i = lane i predicate (K=13→0x1fff; 32→0xFFFFFFFF). ActiveMask→0xFFFFFFFF full warp.

## 2 · USE
```cpp
// Warp votes on p=(lane<13): per-lane writes prove the broadcast. N=64 (2 warps).
#include "kernel_operator.h"
#include "simt_api/asc_simt.h"
using namespace AscendC;
constexpr uint32_t T = 64;
__simt_vf__ LAUNCH_BOUND(T) inline void Body(__gm__ uint32_t *z, uint32_t n) {
    uint32_t tid = Simt::GetThreadIdx<0>();
    if (tid >= n) return;
    int p = (tid % Simt::GetWarpSize()) < 13;
    z[tid] = Simt::WarpBallotSync(p);                 // ◀ MUTATE: WarpAllSync/WarpAnySync/WarpActiveMask()
}
extern "C" __global__ __aicore__ void k(GM_ADDR z, uint32_t n) {
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);
    Simt::VF_CALL<Body>(Simt::Dim3{T, 1, 1}, (__gm__ uint32_t *)z, n);
}
#ifndef __CCE_AICORE__
#include "acl/acl.h"
#include <cstdio>
#include <cstdlib>
#define CHECK(expr) do { aclError _e = (expr); \
    if (_e != ACL_SUCCESS) { std::printf("ACL FAIL %s -> %d\n", #expr, (int)_e); return 1; } } while (0)
int main() {
    constexpr uint32_t N = 64; const size_t b = N * 4;
    CHECK(aclInit(nullptr)); CHECK(aclrtSetDevice(0));
    aclrtStream s = nullptr; CHECK(aclrtCreateStream(&s));
    uint32_t *hz = (uint32_t *)malloc(b);
    void *dz; CHECK(aclrtMalloc(&dz, b, ACL_MEM_MALLOC_HUGE_FIRST));
    k<<<1, nullptr, s>>>((GM_ADDR)dz, N);
    CHECK(aclrtSynchronizeStream(s)); CHECK(aclrtMemcpy(hz, b, dz, b, ACL_MEMCPY_DEVICE_TO_HOST));
    uint32_t ref = 0x1fffu;                            // mirror the MUTATE: All→0, Any→1, ActiveMask→0xFFFFFFFF
    uint32_t errors = 0; for (uint32_t i = 0; i < N; ++i) errors += (hz[i] != ref);
    std::printf("RESULT: errors=%u/%u z0=0x%08x\n", errors, N, hz[0]); fflush(stdout);
    return errors ? 2 : 0;
}
#endif
```
Pass = errors=0 AND SQE≥1. fflush after RESULT (non-zero exit drops stdout).

## 3 · HAZARDS
| Hazard | Symptom | Repair | Evidence |
|---|---|---|---|
| CUDA mask arg habit | compile error / wrong overload | drop mask — whole warp implicit | 🧾H decls |
| vote inside divergent branch | undefined | convergent call; compute predicate first | 🧾H |
| ballot bit order assumed reversed | mask mismatch | bit i == lane i (K=13 → 0x1fff) | 🟢 |
| expecting lane0-only result | all lanes same value | broadcast contract | 🟢 |

## 4 · PERF
One collective/call ≈ REDUX/SHFL class (16-17 dep; vote itself UN — P-22 ext). Launch-bound shape, K=1.0.

## 5 · EVIDENCE & EDGES
12-cell known-answer matrix errors=0 (`probes/simt_vote_sync/RESULTS.md`); decls intf:19-27.
❓UN: vote dep cadence; sub-32 width. Siblings: shuffle · reduce.warp-sum · sync.
