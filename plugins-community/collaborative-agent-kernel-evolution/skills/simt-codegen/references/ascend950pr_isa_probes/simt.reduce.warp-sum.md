# `simt.reduce.warp-sum` — warp-collective sum reduction on the AIV (SIMT path)

> v2 = CANONICAL (2026-06-10): authored under constitution v0.2.5 with the SIMT-ISA cost integers
> (`probes/simt_isa_cost/`) and the headless body profile loop (`profile_simt.sh`).
> v1 ARCHIVED at `acceptance/ab_entry_v2/armA_entry.md` (immutable A/B arm A evidence).

## HEAD

```yaml
head_schema: pb5/v1
op: simt.reduce.warp-sum               # canonical instance: gsum = Σ x[i], int32, N=4096
paradigm: SIMT
core: AIV
lowering: "AscendC::Simt::WarpReduceAddSync<int32_t> -> __reduce_add (native warp-collective reduce); cross-warp/block combine via the sibling atomic primitive AtomicAdd<int32_t> -> atomicAdd; body dispatched by Simt::VF_CALL (KERNEL_TYPE_AIV_ONLY)"
dtypes: [s32]                          # VERIFIED bit-exact. u32 analogous (associative). f16/f32 reduce too but are NON-associative => §HAZARDS, not bit-exact
selection_keys:
  - xlate.cuda-1to1
  - control.divergent-per-element
not_for:
  - pattern.reduction-full             # → SIMD vcadd is the PRIMARY full-array reduction on 950PR; SIMT warp-reduce is auxiliary
cuda_pta_analog: "CUDA __reduce_add_sync(mask,v) / a __shfl_down_sync(...) butterfly warp reduction, then an atomicAdd combine"
false_friends: [shfl_butterfly_is_handrolled_use_native_WarpReduceAddSync,
                warpreduce_broadcasts_to_all_lanes_not_lane0, atomic_from_leader_only_or_overcount_32x,
                fp_reduction_not_bit_exact, collective_must_be_convergent_not_in_divergent_branch,
                reduction_primary_path_is_simd_not_simt]
cost_model:
  roofline_run_id: probes/simt_reduce/SWEEP.md          # whole-program sweep: N × blockDim × threads/block
  binding_resource: UN          # whole-program overhead-bound at swept N (~419 cy flat); body-level binding op is the LDG stream (§PERF)
  optimum: {value: 0.102, unit: cycles/elem}            # 419 cycles total @ N=4096 int32; overhead-bound
  perf_factor_K: 1.0                                    # naive == optimum at this shape; gate (d) non-discriminating here
  latency_cycles:               # per emitted SIMT-ISA op, dependent-chain issue cadence in reg_log stamp cycles (probes/simt_isa_cost/RESULTS.md; sim figures)
    SIMT_IADD_I: 3
    SIMT_FADD: 3
    SIMT_IMAD_I: 7
    SIMT_REDUX: 16
    SIMT_LDG_chain: "~57/iter issue, lsu RTT ~173 (RANGE)"   # dependent GM gather; cold-mem RANGE, not constant
    SIMT_ATOMIC: "~16.9k RTT (RANGE; serializes under contention)"
  elem_per_cycle: 0.77            # 4096 / 5326 measured leader body stamp-span (sim figure; §PERF caveat)
  toolchain:
    bisheng: "clang version 15.0.5 (clang-5c68a1cb1231 flang-5c68a1cb1231) 2026-05-09"
    model: "{model_name: Ascend950PR_9599, cube_cores: 32, vec_cores: 64}"
    configs: [1981_sim_ffts_plus.toml, 1981_model.toml]   # logical aliases -> physical 1982_cloud_config.toml (probes/arch_extract/)
verify_cmd: |
  bash ${PROBE_WORKSPACE}/scripts/build.sh k.cpp
  bash ${PROBE_WORKSPACE}/scripts/run.sh k
  bash ${PROBE_WORKSPACE}/scripts/verify.sh
  bash ${PROBE_WORKSPACE}/scripts/profile_simt.sh k        # body profile (per-op mix + cadence)
sources:
  - probes/simt_reduce/cannsim_20260604082013_kuse/     # §USE verbatim: errors=0, gsum=-2240=ref, sendStarsSQE=17
  - probes/simt_reduce/cannsim_20260604070839_smoke/    # broadcast semantic: all 32 lanes read 496
  - probes/simt_reduce/RESULTS.md
  - probes/simt_reduce/SWEEP.md
  - probes/simt_isa_cost/RESULTS.md                     # SIMT-ISA per-op cadence integers (NEW in v2)
  - probes/simt_isa_cost/kuse_profile/                  # §USE kernel body profile (NEW in v2)
  - "simt_api/cpp/kernel_simt_warp_level_intf.h:42"
  - "asc/impl/simt_api/cpp/dav_3510/kernel_simt_warp_level_impl.h:225"
  - "asc/impl/simt_api/cpp/kernel_simt_warp_level_intf_impl.h:78"
  - "asc/impl/simt_api/cpp/dav_3510/kernel_simt_atomic_impl.h:82"
  - "__clang_cce_simt_dav3510_intrinsic.h:472"          # warpSize = 32
status: established                  # v0.2.6 §8(a) flip; one-shot pass ct_p1_simt_reduce_struct_haiku (attempts=1), discriminating flat-FAIL ab_flat_warpsum
tier_summary:
  - {claim: build+run+bit-exact int32 sum, tier: T1-sim}
  - {claim: WarpReduceAddSync convenes 32-lane warp under VF_CALL, tier: T1-sim}
  - {claim: warp-reduced value broadcasts to ALL 32 lanes (not lane-0), tier: T1-sim}
  - {claim: all-lanes atomic overcounts exactly 32x, tier: T1-sim}
  - {claim: int32 reduction bit-exact (associative; no overflow), tier: T1-sim}
  - {claim: fp32 reduction NOT bit-exact vs sequential host, tier: T1-sim}
  - {claim: "WarpReduceAddSync<T> T in {int32,uint32,half,float}", tier: H}
  - {claim: per-op SIMT-ISA issue cadences (latency_cycles map), tier: T1-sim}
  - {claim: body cost model leader-vs-all-lane atomics, tier: T1-sim}
  - {claim: whole-program overhead-bound ~419 cy at swept N, K=1.0, tier: T1-sim}
  - {claim: reduction PRIMARY path is SIMD (vcadd), SIMT is auxiliary, tier: IN}
```

## 0 · SELECT

**Are you in the right paradigm?** On 950PR the **primary** full-array reduction is **SIMD**
(`vcadd`/`vcgadd`). SIMT warp-reduce is **auxiliary** — use it only inside an existing SIMT kernel
(CUDA 1:1 port, divergent per-element logic) needing a **warp-local** combine.

```
just sum/reduce a contiguous array?           → SIMD vcadd (pattern.reduction-full; SIMD is primary)
already in a SIMT kernel / porting CUDA warp  → stay here (warp-collective reduce + atomic combine)
elementwise z=f(x,y), no cross-lane combine   → simt.elementwise.binary (sibling)
```

**Intercept these CUDA priors** (each verified — §5):

| Your CUDA prior | 950PR fact | Tier |
|---|---|---|
| Hand-roll a `__shfl_down_sync` butterfly | native single call `Simt::WarpReduceAddSync<T>` (→ `__reduce_add`) | 🟢T1-sim |
| Result lands in lane 0 only | **broadcasts to ALL 32 lanes** (every lane reads 496) | 🟢T1-sim |
| Atomic-add from every thread | all 32 lanes hold the sum → **32× overcount**; leader-only (`lane==0`) | 🟢T1-sim |
| fp atomics match host sum | non-associative → NOT bit-exact; int = bit-exact | 🟢T1-sim |
| Collective inside `if (i<n)` ok | warp-synchronous: all 32 lanes call, identity-pad tails | 🧾H + 🧠IN |
| Reduction is SIMT-first | 950PR reduction is SIMD-first; this is auxiliary | 🧠IN |

## 1 · CONTRACT

| Claim | Tier · source |
|---|---|
| `Simt::WarpReduceAddSync<T>(T val)` reduces across 32 lanes, **returns to every lane**; `T ∈ {int32,uint32,half,float}` | 🟢T1-sim smoke; 🧾H intf_impl:78 |
| Lowers to one `SIMT_REDUX` warp-collective (not a shuffle tree); count = warps (kuse profile) | 🟢T1-sim `probes/simt_isa_cost/kuse_profile/` |
| `Simt::AtomicAdd<int32_t>(addr,v)` atomic; returns old | 🧾H atomic_impl:82 |
| warpSize = 32; lane = `GetThreadIdx<0>() % GetWarpSize()` | 🧾H :472 |
| int32 sum bit-exact for any order if no overflow (§2.6a) | 🟢T1-sim reduce run |
| `KERNEL_TYPE_AIV_ONLY` + `__simt_vf__` + `VF_CALL` pin body to AIV | 🟢T1-sim kuse |
| accumulator zero-init H2D before launch | 🧠IN identity |
| f16/f32 non-associative → §HAZARDS | ❓UN re-run per dtype |

## 2 · USE — paste, build, run, verify

Same canonical kernel as v1 (verbatim §USE rerun in `kuse` run). Mutate marked ops for max/min.

```cpp
// Ascend 950PR SIMT warp reduction: gsum = Σ x[i], int32, N=4096 (bit-exact).
// Build:  source /usr/local/Ascend/ascend-toolkit/set_env.sh
//   bisheng --asc-aicore-lang --npu-arch=dav-3510 k.cpp -o k \
//     -I$ASCEND_HOME_PATH/aarch64-linux/include -L$ASCEND_HOME_PATH/lib64 \
//     -Wl,-rpath,$ASCEND_HOME_PATH/lib64 -lascendcl -lruntime
// Run:   cannsim record ./k -s Ascend950 -g     (pass: errors=0 AND sendStarsSQE >= 1)
// Body profile: profile_simt.sh ./k             (per-op mix + cadence; §PERF)
#include "kernel_operator.h"
#include "simt_api/asc_simt.h"
using namespace AscendC;
constexpr uint32_t T = 256;
__simt_vf__ LAUNCH_BOUND(T) inline void Body(__gm__ int32_t *x, __gm__ int32_t *gsum, uint32_t n) {
    uint32_t tnum = Simt::GetThreadNum<0>();
    uint32_t tid = Simt::GetThreadIdx<0>() + Simt::GetBlockIdx() * tnum;
    uint32_t stride = Simt::GetBlockNum() * tnum;
    int32_t partial = 0;
    for (uint32_t i = tid; i < n; i += stride) partial += x[i];        // per-thread partial
    int32_t warpSum = Simt::WarpReduceAddSync<int32_t>(partial);       // ◀ MUTATE op; UNCONDITIONAL
    if (Simt::GetThreadIdx<0>() % Simt::GetWarpSize() == 0)            // leader only
        Simt::AtomicAdd<int32_t>(gsum, warpSum);                       // ◀ MUTATE combine
}
extern "C" __global__ __aicore__ void k(GM_ADDR x, GM_ADDR gsum, uint32_t n) {
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);
    Simt::VF_CALL<Body>(Simt::Dim3{T, 1, 1}, (__gm__ int32_t *)x, (__gm__ int32_t *)gsum, n);
}
#ifndef __CCE_AICORE__
#include "acl/acl.h"
#include <cstdio>
#include <cstdlib>
#define CHECK(expr) do { aclError _e = (expr); \
    if (_e != ACL_SUCCESS) { std::printf("ACL FAIL %s -> %d\n", #expr, (int)_e); return 1; } } while (0)
int main() {
    constexpr uint32_t N = 4096;
    const size_t xb = N * sizeof(int32_t), sb = sizeof(int32_t);
    const uint32_t blockDim = 8;
    CHECK(aclInit(nullptr)); CHECK(aclrtSetDevice(0));
    aclrtStream stream = nullptr; CHECK(aclrtCreateStream(&stream));
    int32_t *hx = (int32_t *)std::malloc(xb), hgsum = 0;
    long long ref = 0;
    for (uint32_t i = 0; i < N; ++i) { hx[i] = (int32_t)(i % 100) - 50; ref += hx[i]; }
    void *dx = nullptr, *dg = nullptr;
    CHECK(aclrtMalloc(&dx, xb, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK(aclrtMalloc(&dg, sb, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK(aclrtMemcpy(dx, xb, hx, xb, ACL_MEMCPY_HOST_TO_DEVICE));
    CHECK(aclrtMemcpy(dg, sb, &hgsum, sb, ACL_MEMCPY_HOST_TO_DEVICE));   // zero-init (identity!)
    k<<<blockDim, nullptr, stream>>>((GM_ADDR)dx, (GM_ADDR)dg, N);
    CHECK(aclrtSynchronizeStream(stream));
    CHECK(aclrtMemcpy(&hgsum, sb, dg, sb, ACL_MEMCPY_DEVICE_TO_HOST));
    uint32_t errors = (hgsum == (int32_t)ref) ? 0u : 1u;                // §2.6 (a) exact
    std::printf("gsum_dev=%d  ref=%lld\nRESULT: errors=%u/1\n", hgsum, ref, errors);
    aclrtFree(dx); aclrtFree(dg); std::free(hx);
    aclrtDestroyStream(stream); aclrtResetDevice(0); aclFinalize();
    return errors == 0 ? 0 : 2;
}
#endif
```

**Verify ladder** — the four `verify_cmd` lines. Pass = `errors=0/1` AND `sendStarsSQE ≥ 1`
(host-only no-op is a false pass). Extract single lines, never dump logs. The 4th line prints
the body's per-op mix + cadence; expected for this kernel: `SIMT_REDUX n = warps`, `LDG n ≈ N`.

**Build/run repair:** same table as v1 (`armA_entry.md`); unchanged.

## 3 · HAZARDS — silent (compiles fine, results wrong)

| Hazard | Symptom | Repair | Evidence |
|---|---|---|---|
| **Atomic from every lane** | gsum exactly **32×** | leader-only (`lane==0`) | 🟢 `…_hz_alllane/` 32.000 |
| **fp expected bit-exact** | low-bit drift (abs_diff 4088 @1e8) | int32 exact; fp = §2.6(b/c) | 🟢 `…_hz_fp32/` |
| **Collective in divergent branch** | partial/undefined reduce | unconditional + identity-pad | 🧾H+🧠IN |
| **Wrong accumulator identity** | clamped/shifted result | 0/INT_MIN/INT_MAX per op | 🧠IN |
| **int32 overflow** | wraps mod 2³² | bound inputs / widen | 🧠IN |

## 4 · PERF — measured cost model (🟢T1-sim, sim figures)

**Whole-program**: launch-bound ~419 cy flat at swept N (SWEEP.md) ⇒ K=1.0, gate (d)
non-discriminating; fuse to amortize launches at N ≲ 10⁴.

**Body cost (NEW in v2) — per-op SIMT-ISA cadences** (dependent-chain issue spacing, reg_log
stamp cycles; `probes/simt_isa_cost/RESULTS.md`; UNR-grid-validated; sim figures, never a
hardware rate — constitution §6.1 caveat):

| op | cadence (cy) | role here |
|---|---|---|
| SIMT_IADD_I | 3 | per-element accumulate |
| SIMT_LDG dependent | ~57/iter issue, lsu RTT ~173 (RANGE) | GM gather (RANGE, cold) |
| SIMT_REDUX | 16 | once per warp |
| atomic add (GM) | ~16.9k RTT (RANGE; serializes under contention) | once per LEADER warp |
| SIMT_FADD / FMUL / FFMA | 3 / 4 / 7 | (fp mutate) |
| ILP: 8 indep chains | FADD II 1-2 cy | II per op (IADD/FADD) |

**Closed loop:** `profile_simt.sh ./k` ⇒ mix must show `n(LDG) ≈ N/grid-stride trips`,
`n(REDUX) = warps`, atomics = warps (leader-only). All-lane atomic mutate ⇒ atomics = threads (32×) — measured: all-lane lsu span 127,926 cy vs leader 5,326 cy = 24× body slowdown (atomic serialization); RED count sampling-limited.

**Cost model (directly evaluable)**: leader-only body span = **5,326 cy measured** (LDG stream dominates;
one overlapped atomic/warp ≈ free). All-lane = leader × **24 measured** (127,926 cy; atomics serialize,
RTT ≈16.9k, linear in chain length — slope 2.14/2.0). elem/cy = 4096/5326 ≈ **0.77** leader. Predict a
variant by scaling the atomic count (leader = warps; all-lane = threads = 32×warps).

## 5 · EVIDENCE & EDGES

- correctness: kuse (errors=0, gsum −2240, SQE 17); smoke broadcast; hazards `_hz_alllane/`, `_hz_fp32/`.
- body costs: `probes/simt_isa_cost/{RESULTS.md, *.cpp, sweep.sh}`; §USE profile `kuse_profile/`.
- API 🧾H: intf:42, impl:225, intf_impl:78, atomic:82, warpSize:472. Recon `probes/simt_reduce/RESULTS.md`.
- ❓UN: ≥1M data-dominant resweep; dtypes beyond int32; absolute clock (count-vs-clock split, v0.2.5).
- Siblings: simt.elementwise.binary · SIMD vcadd (planned) · simt.atomic.add (planned).
