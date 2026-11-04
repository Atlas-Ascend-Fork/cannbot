# `simt.cast.fp-int` — per-thread fp32↔int casts (`__cvt_*<ROUND,sat>`, F2I/I2F/F2F single-op)

## HEAD

```yaml
head_schema: pb5/v1
op: simt.cast.fp-int                   # canonical instance: z[i]=__cvt_int32_t<ROUND::R>(x[i]) + i2f roundtrip
paradigm: SIMT
core: AIV
lowering: "__cvt_{int32_t,uint32_t,int64_t,uint64_t}(float) -> 1x SIMT_F2I; __cvt_float(s32/u32/s64/u64) -> 1x SIMT_I2F; __cvt_float(float) -> 1x SIMT_F2F; ROUND+sat are immediates, never extra ops"
dtypes: [f32, s32, u32, s64, u64]      # all five directions errors=0 (884-pt known-answer, 5 modes)
selection_keys:
  - xlate.cuda-1to1
  - control.divergent-per-element
not_for:
  - access.contiguous-elementwise      # → SIMD vcvt family is the bulk-cast path (numeric.dtype-convert)
cuda_pta_analog: "__float2int_rn/rz/ru/rd, __float2uint_*, __int2float_*, __ull2float_*, rintf/truncf"
false_friends: [a_is_half_away_not_away, f2i_saturates_never_wraps, nan_to_int_is_zero,
                u32_cast_returns_signed_int, f2f_flushes_neg0, simd_vcvt_is_not_this_path]
cost_model:
  roofline_run_id: probes/simt_castarith/RESULTS.md     # P-22 dependent-chain (no shape roofline: compute-op)
  binding_resource: UN                 # whole-prog launch-bound at probed N (419 cy); body F2I-cadence-bound
  optimum: {value: 3.27, unit: cycles/elem}        # whole-prog 419 cy / 128 results @ selftest (launch-bound, R-15)
  perf_factor_K: 1.0                   # overhead-bound shape; body cadence is the per-op cost
  latency_cycles:
    F2I_I2F_FADD_dep_iter: 11          # dependent f32->s32->f32+FADD chain; F2I spacing 11 = whole iter (n tracks UNR 16/32/64)
    F2F_FFMA_dep_iter: 9               # f2f quantize + FFMA chain (mode=min=max 9, UNR-invariant)
  elem_per_cycle: UN                   # ILP/II not measured; isolated F2I/I2F/F2F latencies UN (chains measure pairs)
  toolchain:
    bisheng: "clang version 15.0.5 (clang-5c68a1cb1231 flang-5c68a1cb1231) 2026-05-09"
    model: "{model_name: Ascend950PR_9599, cube_cores: 32, vec_cores: 64}"
    configs: [1981_sim_ffts_plus.toml, 1981_model.toml]
verify_cmd: |
  bash ${PROBE_WORKSPACE}/scripts/build.sh k.cpp
  bash ${PROBE_WORKSPACE}/scripts/run.sh k
  bash ${PROBE_WORKSPACE}/scripts/verify.sh
  bash ${PROBE_WORKSPACE}/scripts/profile_simt.sh k   # expect F2I and I2F counts == 1/elem each
sources:
  - probes/simt_castarith/RESULTS.md                   # census + 884-pt known answers + P-22 cadences
  - probes/simt_castarith/cannsim_20260610164643_kca/  # errors=0/884, 5 modes x 5 directions
  - probes/simt_castarith/use_selftest/cannsim_20260610170059_kcast/  # THIS USE one-shot errors=0/128
  - "__clang_cce_simt_dav3510_intrinsic.h:643"         # F2I_CVT_FLOAT (s32/u32; returns int; sat forced)
  - "__clang_cce_simt_dav3510_intrinsic.h:664"         # F2I_B64_CVT (s64/u64; float-only src)
  - "__clang_cce_simt_dav3510_intrinsic.h:688"         # F2F_GENERAL_FP32_CVT (int->f32 + f32->f32)
  - "__clang_dpp_types.h:220"                          # enum class ROUND { R, A, F, C, Z, O, H }
status: piloted
tier_summary:
  - {claim: 5 directions x 5 modes errors=0 (884-pt incl boundaries), tier: T1-sim}
  - {claim: each cast = exactly 1 ISA op (F2I/I2F/F2F), tier: T1-sim}
  - {claim: f->int sat forced RS_ENABLE; only R/A/F/C/Z legal, tier: H}
  - {claim: A = nearest-ties-away; R = nearest-even; NaN->0; -0 f2f flush; NaN f2f -> 0x7FFFFFFF, tier: T1-sim}
  - {claim: cvt roundtrip pair dependent cadence (RESULTS table), tier: T1-sim}
  - {claim: F2I alone latency, tier: UN}
```

## 0 · SELECT
Bulk contiguous dtype convert → SIMD vcvt (`numeric.dtype-convert`), not here. Per-thread cast inside
a divergent SIMT body, or a 1:1 CUDA port of `__float2int_*` → here. Intercepts (all probed):
`(int)f` ≠ wrap — **950PR fp→int always saturates** (RS_ENABLE forced); NaN→0 not UB; `ROUND::A` =
nearest-ties-AWAY (`std::round`), not C's away-from-zero; `__cvt_uint32_t` returns `int` (bits of u32).

## 1 · CONTRACT
`int __cvt_int32_t<ROUND rnd=Z, sat=RS_ENABLE>(float)` etc. (🧾H :643/664/688) — rnd ∈ {R,A,F,C,Z}
only, sat is forced RS_ENABLE (static_assert). Probed (🟢, errors=0/884): R=nearest-even, A=nearest-ties-away,
F/C/Z floor/ceil/trunc; saturation INT_MIN/MAX, u-types 0/MAX; NaN→0; ±Inf→sat bounds. `__cvt_float(int)`
RNE default; u64/s64 reachable on f32 grid; f32→f32 quantizes per mode, NaN→0x7FFFFFFF, −0→+0.
Default fp→int = `ROUND::Z` (matches C); `<>` empty template OK.

## 2 · USE — paste, build, run, verify
```cpp
// Ascend 950PR SIMT fp<->int cast: z[i] = __cvt_int32_t<ROUND::R>(x[i]) (sat forced) and
// f[i] = __cvt_float<ROUND::R>(z[i]) roundtrip. T=64 boundary inputs, bit-exact host compare.
// Build:
//   source /usr/local/Ascend/ascend-toolkit/set_env.sh
//   bisheng --asc-aicore-lang --npu-arch=dav-3510 k.cpp -o k \
//     -I$ASCEND_HOME_PATH/aarch64-linux/include -L$ASCEND_HOME_PATH/lib64 \
//     -Wl,-rpath,$ASCEND_HOME_PATH/lib64 -lascendcl -lruntime
// Run:  cannsim record ./k -s Ascend950 -g     Pass: RESULT: errors=0/128
#include "kernel_operator.h"
#include "simt_api/asc_simt.h"
using namespace AscendC;
constexpr uint32_t T = 64;

__simt_vf__ LAUNCH_BOUND(T) inline void Body(__gm__ float *x, __gm__ int32_t *z, __gm__ float *f) {
  uint32_t i = Simt::GetThreadIdx<0>();
  int32_t v = __cvt_int32_t<ROUND::R>(x[i]);   // ◀ MUTATE mode: ROUND::A/F/C/Z (sat always ON)
  z[i] = v;
  f[i] = __cvt_float<ROUND::R>(v);             // int -> f32, nearest-even
}
extern "C" __global__ __aicore__ void k(GM_ADDR x, GM_ADDR z, GM_ADDR f) {
  KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);
  Simt::VF_CALL<Body>(Simt::Dim3{T, 1, 1}, (__gm__ float *)x, (__gm__ int32_t *)z, (__gm__ float *)f);
}

#ifndef __CCE_AICORE__
#include "acl/acl.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <cstdint>
#define CK(e) do{aclError _r=(e); if(_r!=ACL_SUCCESS){std::printf("ACL FAIL %s %d\n",#e,(int)_r);std::fflush(stdout);return 1;}}while(0)
static int32_t ref_s32(float s) {                       // R = nearest-even; sat; NaN->0 (probed contract)
  if (std::isnan(s)) return 0;
  double r = std::nearbyint((double)s);                 // host FE_TONEAREST = RNE
  if (r >= 2147483647.0) return INT32_MAX;
  if (r <= -2147483648.0) return INT32_MIN;
  return (int32_t)r;
}
int main() {
  CK(aclInit(nullptr)); CK(aclrtSetDevice(0));
  aclrtStream s = nullptr; CK(aclrtCreateStream(&s));
  float hx[T]; int32_t hz[T]; float hf[T];
  const float edge[12] = {0.5f, -0.5f, 1.5f, 2.5f, -2.5f, 2147483520.0f, 2147483648.0f,
                          -2147483648.0f, -2147483904.0f, NAN, INFINITY, -INFINITY};
  for (uint32_t i = 0; i < T; ++i) hx[i] = i < 12 ? edge[i] : 100.625f - 3.875f * (float)i;
  void *dx, *dz, *df;
  CK(aclrtMalloc(&dx, T*4, ACL_MEM_MALLOC_HUGE_FIRST)); CK(aclrtMalloc(&dz, T*4, ACL_MEM_MALLOC_HUGE_FIRST));
  CK(aclrtMalloc(&df, T*4, ACL_MEM_MALLOC_HUGE_FIRST));
  CK(aclrtMemcpy(dx, T*4, hx, T*4, ACL_MEMCPY_HOST_TO_DEVICE));
  k<<<1, nullptr, s>>>((GM_ADDR)dx, (GM_ADDR)dz, (GM_ADDR)df);
  CK(aclrtSynchronizeStream(s));
  CK(aclrtMemcpy(hz, T*4, dz, T*4, ACL_MEMCPY_DEVICE_TO_HOST));
  CK(aclrtMemcpy(hf, T*4, df, T*4, ACL_MEMCPY_DEVICE_TO_HOST));
  uint32_t e = 0;
  for (uint32_t i = 0; i < T; ++i) {
    int32_t rz = ref_s32(hx[i]);                        // ◀ MUTATE with device mode
    float rf = (float)rz;                               // s32->f32 RNE == host cast
    uint32_t a, b; std::memcpy(&a, &hf[i], 4); std::memcpy(&b, &rf, 4);
    if (hz[i] != rz && e++ < 8) std::printf("s32[%u] x=%g dev=%d ref=%d\n", i, hx[i], hz[i], rz);
    if (a != b && e++ < 8) std::printf("f[%u] dev=%.9g ref=%.9g\n", i, hf[i], rf);
  }
  std::printf("RESULT: errors=%u/%u\n", e, 2 * T); std::fflush(stdout);
  aclrtFree(dx); aclrtFree(dz); aclrtFree(df);
  aclrtDestroyStream(s); aclrtResetDevice(0); aclFinalize(); return e ? 2 : 0;
}
#endif
```
Pass = `errors=0/128` AND `sendStarsSQE ≥ 1` (one-shot evidence: `use_selftest/cannsim_20260610170059_kcast/`).
Mutating mode: device template AND `ref_s32` rounder together (A→`std::round`, F→`floor`, C→`ceil`, Z→`trunc`) — F2I leg ONLY; the I2F roundtrip leg (`__cvt_float`) and its host reference stay nearest-even (`ROUND::R`) unmutated.

## 3 · HAZARDS — silent (compiles fine, results wrong)
| Hazard | Symptom | Repair | Evidence |
|---|---|---|---|
| expecting C/CUDA wrap on overflow | INT_MIN/MAX instead of wrapped bits | sat is forced; design ranges for clamp | 🟢 kca 884-pt |
| NaN→int assumed UB/garbage | always 0 | rely on 0 only if intentional | 🟢 kca |
| ROUND::A read as away-from-zero | off-tie values mismatch | A = nearest, ties away (std::round) | 🟢 kca u2f probes |
| `__cvt_uint32_t` typed `int` | sign confusion at >2^31 | cast result to `uint32_t` | 🧾H :646; 🟢 kca |
| f2f NaN payload | dev=0x7FFFFFFF ≠ host NaN | canonical-bits compare | 🟢 kca |
| f2f −0 result | flushed to +0 | normalize zeros in host ref | 🟢 kca |
| SIMD-cast false friend | inventing vcvt ops here | per-thread `__cvt_*` only; vcvt is SIMD | 🧾 simd headers |

## 4 · PERF — measured 🟢T1-sim (sim figures, never hardware rates)
Whole-prog launch-bound 419 cy at selftest N (K=1.0). Body (P-22 stamps, n tracks UNR 16/32/64,
spacing UNR-invariant): dependent f32→s32→f32+FADD roundtrip = **11 cy/iter** (FADD=3 ⇒ F2I+I2F≈8,
~4 each 🧠IN); F2F+FFMA chain = **9 cy/iter** (FFMA=7 ⇒ F2F≈2–4 🧠IN). Every cast = 1 op; all
R/A/F/C/Z + s/u + 32/64 share the op — mode choice never costs. Profile: F2I==I2F==1/elem.
❓UN: isolated F2I/I2F latency · ILP II · data-dominant N.

## 5 · EVIDENCE & EDGES
- Census + semantics + cadence: `probes/simt_castarith/RESULTS.md`; correctness `cannsim_20260610164643_kca/` (errors=0/884: 5 dirs × 5 modes, boundaries, NaN/Inf, ties; bit-exact §2.6(a)).
- Headers: templates `__clang_cce_simt_dav3510_intrinsic.h:643/664/688`; ROUND `__clang_dpp_types.h:220`.
- ❓UN: isolated F2I latency (close: F2I+IADD-mix chain) · A-mode in u64 corner above 2^63 step (sparse).
- Siblings: `simt.arith.bit` · `simt.elementwise.binary` · SIMD vcvt (bulk, planned).
