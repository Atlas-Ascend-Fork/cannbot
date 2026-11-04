# `simt.arith.bit` — per-thread integer bit/mul builtins (`__brev/__clz/__popc/__ffs/__mulhi/__byte_perm`)

## HEAD

```yaml
head_schema: pb5/v1
op: simt.arith.bit                     # canonical instance: brev/clz/popc/ffs/mulhi over boundary patterns
paradigm: SIMT
core: AIV
lowering: "1-op: __brev32 BREV / __popc32 POPC / __byte_perm PRMT / __mulhi __umulhi __mul_i32toi64 IMUL; __clz32 CLZ+zero-guard; __ffs32 ~6-op POPC-based; brev64 2xBREV; popc64 2xPOPC+IADD; clz64/ffs64 divergent sw; __umul64hi ~12-op (4xIMUL+6xIADD_X); __mul64hi ~21-op; __mul24 IMUL+3xSHFI"
dtypes: [s32, u32, s64, u64]
selection_keys:
  - xlate.cuda-1to1
  - control.divergent-per-element
not_for:
  - access.contiguous-elementwise      # → SIMD elementwise path for bulk regular data
cuda_pta_analog: "CUDA __brev/__clz/__popc/__ffs/__mulhi/__umul64hi/__byte_perm/__sad — same names"
false_friends: [ffs_is_not_single_op_popc_based, 64bit_variants_software_expand, sad_diff_wraps_32bit,
                mul24_is_not_hw_op, clz64_ffs64_diverge_the_warp]
cost_model:
  roofline_run_id: probes/simt_castarith/RESULTS.md     # P-22 dependent-chain (compute-op; no shape roofline)
  binding_resource: UN                 # whole-prog launch-bound at probed N; body cadence-bound
  optimum: {value: 1.31, unit: cycles/elem}        # whole-prog 419 cy / 320 results @ selftest (launch-bound, R-15)
  perf_factor_K: 1.0
  latency_cycles:
    POPC_XOR_pair: 9                   # popc^u dep chain; mode 9 UNR-invariant; LOP3=4 => POPC ~5 (IN)
    CLZ_guard_XOR_iter: 9              # 4-op iter (CLZ+ISETP+MOV+LOP3) in 9 cy
    FFS32_XOR_iter: "~33-36"           # 7-op expansion; span/UNR basis (POPC-POPC 27-30 RANGE)
    MULHI_OR_pair: 6                   # IMUL+LOP3 overlap
    BREV64_IADD_iter: 6                # 2xBREV pair; BREV-BREV ~3
    BREV32_dep: UN                     # compiler folds both brev chains (identity)
  elem_per_cycle: UN                   # II unmeasured
  toolchain:
    bisheng: "clang version 15.0.5 (clang-5c68a1cb1231 flang-5c68a1cb1231) 2026-05-09"
    model: "{model_name: Ascend950PR_9599, cube_cores: 32, vec_cores: 64}"
    configs: [1981_sim_ffts_plus.toml, 1981_model.toml]
verify_cmd: |
  bash ${PROBE_WORKSPACE}/scripts/build.sh k.cpp
  bash ${PROBE_WORKSPACE}/scripts/run.sh k
  bash ${PROBE_WORKSPACE}/scripts/verify.sh
  bash ${PROBE_WORKSPACE}/scripts/profile_simt.sh k   # expect BREV 1, CLZ 1, IMUL 1, POPC 2 per elem (ffs adds a POPC; no FFS op exists)
sources:
  - probes/simt_castarith/RESULTS.md                   # census diff table + cadences + 884-pt correctness
  - probes/simt_castarith/cannsim_20260610164643_kca/  # bits+arith errors=0 (within 884)
  - probes/simt_castarith/use_selftest/cannsim_20260610170241_kbits/  # THIS USE one-shot errors=0/320
  - "__clang_cce_simt_dav3510_intrinsic.h:576"         # __brev 32/64
  - "__clang_cce_simt_dav3510_intrinsic.h:588"         # __clz 32 + 64 software (branch + clz32)
  - "__clang_cce_simt_dav3510_intrinsic.h:606"         # __popc 32 + 64 = 2x popc32 + add
  - "__clang_cce_simt_dav3510_intrinsic.h:620"         # __ffs 32 + 64 software
  - "__clang_cce_simt_dav3510_intrinsic.h:524"         # __umulhi/__mulhi/__mul_i32toi64/__umul64hi
  - "__clang_cce_simt_dav3510_intrinsic.h:563"         # __mul64hi = software around __umul64hi
  - "__clang_cce_simt_dav3510_intrinsic.h:391"         # __byte_perm -> prmt
  - "__clang_cce_simt_dav3510_intrinsic.h:796"         # __sad: z + abs(x-y), 32-bit wrap diff
status: piloted
tier_summary:
  - {claim: brev/clz/popc/ffs 32+64 + mulhi/mul64hi/prmt/sad/mul24 errors=0 boundary set, tier: T1-sim}
  - {claim: brev32/popc32/prmt/mulhi/umulhi/mul_i32toi64 = 1 ISA op; ffs32 ~6; umul64hi ~12; mul64hi ~21, tier: T1-sim}
  - {claim: dependent iter cadences (POPC pair 9, CLZ iter 9, MULHI pair 6, FFS ~33-36, BREV64 6), tier: T1-sim}
  - {claim: BREV32 dependent cadence, tier: UN}
  - {claim: __sad diff wraps in 32-bit before abs, tier: T1-sim}
  - {claim: II / data-dominant cost, tier: UN}
```

## 0 · SELECT
Same names as CUDA — but check the lowering column before budgeting: 32-bit `__brev/__popc/__byte_perm`
+ the mulhi family are single ISA ops; `__clz` adds a zero-guard; `__ffs` is NOT single (POPC-based
~6-op expansion); 64-bit clz/ffs are divergent software (BRANCH+DVG enter the warp), brev64/popc64 = 2 ops;
`__mul64hi`(signed) + `__sad` + `__mul24` are header software. Bulk regular bit-twiddling → SIMD sibling.

## 1 · CONTRACT
Surface 🧾H :391-811: `__brev(u32/u64)`, `__clz(int/ll)→[0,32/64]` (`__clz(0)`=32), `__popc(u32/u64)`,
`__ffs(int/ll)` (1-based, 0→0), `__mulhi/__umulhi` (hi32 of 32×32), `__umul64hi/__mul64hi` (hi64),
`__mul_i32toi64` (full 64 product, 1 IMUL), `__byte_perm(x,y,s)` CUDA-prmt nibble selects + s.b3 sign-ext,
`__sad(x,y,z)` z+|wrap32(x−y)|, `__mul24` masks+mul. All probed bit-exact errors=0/884 incl 0/MSB/all-ones (🟢 kca).

## 2 · USE — paste, build, run, verify
```cpp
// Ascend 950PR SIMT bit ops: per-thread __brev/__clz/__popc/__ffs (u32) + __mulhi over
// 64 boundary patterns; exhaustive-pattern spot set, bit-exact host compare.
// Build:
//   source /usr/local/Ascend/ascend-toolkit/set_env.sh
//   bisheng --asc-aicore-lang --npu-arch=dav-3510 k.cpp -o k \
//     -I$ASCEND_HOME_PATH/aarch64-linux/include -L$ASCEND_HOME_PATH/lib64 \
//     -Wl,-rpath,$ASCEND_HOME_PATH/lib64 -lascendcl -lruntime
// Run:  cannsim record ./k -s Ascend950 -g     Pass: RESULT: errors=0/320
#include "kernel_operator.h"
#include "simt_api/asc_simt.h"
using namespace AscendC;
constexpr uint32_t T = 64;

__simt_vf__ LAUNCH_BOUND(T) inline void Body(__gm__ uint32_t *x, __gm__ uint32_t *z) {
  uint32_t i = Simt::GetThreadIdx<0>();
  uint32_t v = x[i];
  z[0 * T + i] = __brev(v);                       // ◀ MUTATE op family here + in host ref
  z[1 * T + i] = (uint32_t)__clz((int)v);
  z[2 * T + i] = (uint32_t)__popc(v);
  z[3 * T + i] = (uint32_t)__ffs((int)v);
  z[4 * T + i] = (uint32_t)__mulhi((int)v, (int)(v | 1u));
}
extern "C" __global__ __aicore__ void k(GM_ADDR x, GM_ADDR z) {
  KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);
  Simt::VF_CALL<Body>(Simt::Dim3{T, 1, 1}, (__gm__ uint32_t *)x, (__gm__ uint32_t *)z);
}

#ifndef __CCE_AICORE__
#include "acl/acl.h"
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#define CK(e) do{aclError _r=(e); if(_r!=ACL_SUCCESS){std::printf("ACL FAIL %s %d\n",#e,(int)_r);std::fflush(stdout);return 1;}}while(0)
static uint32_t brev(uint32_t x){uint32_t r=0;for(int i=0;i<32;i++)r|=((x>>i)&1u)<<(31-i);return r;}
static uint32_t clz(uint32_t x){for(int i=31;i>=0;i--)if((x>>i)&1u)return 31-i;return 32;}
static uint32_t popc(uint32_t x){uint32_t n=0;while(x){n+=x&1u;x>>=1;}return n;}
static uint32_t ffs(uint32_t x){if(!x)return 0;for(int i=0;i<32;i++)if((x>>i)&1u)return i+1;return 0;}
int main() {
  CK(aclInit(nullptr)); CK(aclrtSetDevice(0));
  aclrtStream s = nullptr; CK(aclrtCreateStream(&s));
  uint32_t hx[T], hz[5 * T];
  const uint32_t edge[8] = {0u, 1u, 0x80000000u, 0xFFFFFFFFu, 0xAAAA5555u, 0x7FFFFFFFu, 2u, 0x00010000u};
  for (uint32_t i = 0; i < T; ++i) hx[i] = i < 8 ? edge[i] : (0x9E3779B9u * (i + 1));
  void *dx, *dz;
  CK(aclrtMalloc(&dx, T*4, ACL_MEM_MALLOC_HUGE_FIRST)); CK(aclrtMalloc(&dz, 5*T*4, ACL_MEM_MALLOC_HUGE_FIRST));
  CK(aclrtMemcpy(dx, T*4, hx, T*4, ACL_MEMCPY_HOST_TO_DEVICE));
  k<<<1, nullptr, s>>>((GM_ADDR)dx, (GM_ADDR)dz);
  CK(aclrtSynchronizeStream(s));
  CK(aclrtMemcpy(hz, 5*T*4, dz, 5*T*4, ACL_MEMCPY_DEVICE_TO_HOST));
  uint32_t e = 0;
  for (uint32_t i = 0; i < T; ++i) {
    uint32_t v = hx[i];
    uint32_t r[5] = {brev(v), clz(v), popc(v), ffs(v),
                     (uint32_t)(int32_t)(((int64_t)(int32_t)v * (int32_t)(v | 1u)) >> 32)};  // ◀ MUTATE with device
    for (int f = 0; f < 5; ++f)
      if (hz[f * T + i] != r[f] && e++ < 8)
        std::printf("f%d[0x%08x] dev=0x%x ref=0x%x\n", f, v, hz[f * T + i], r[f]);
  }
  std::printf("RESULT: errors=%u/%u\n", e, 5 * T); std::fflush(stdout);
  aclrtFree(dx); aclrtFree(dz);
  aclrtDestroyStream(s); aclrtResetDevice(0); aclFinalize(); return e ? 2 : 0;
}
#endif
```
Pass = `errors=0/320` AND `sendStarsSQE ≥ 1` (one-shot evidence: `use_selftest/cannsim_20260610170241_kbits/`).

## 3 · HAZARDS — silent (compiles fine, results wrong)
| Hazard | Symptom | Repair | Evidence |
|---|---|---|---|
| `__ffs` budgeted as 1 op | ~6× op-count drift | ffs32 = POPC-based expansion (census) | 🟢 census diff |
| 64-bit clz/ffs assumed branch-free | BRANCH+DVG enter warp | budget divergence; prefer 32-bit | 🟢 fam14/18 |
| `__sad` 64-bit diff intuition | INT_MIN−INT_MAX → 1 wrap then abs | wrap32 before abs (probed) | 🟢 kca f9 |
| `__mul24` assumed hw 24-bit mul | IMUL + 3 SHFI masks | use plain 32-bit mul unless masking wanted | 🟢 fam25 |
| `__umul64hi`/`__mul64hi` assumed 1 op | ~12 / ~21 ops | 64-bit hi-mul is software — budget it | 🟢 fam21/22 |
| `__clz(0)`=32 / `__ffs(0)`=0 | off-by-one on zero | probed contract | 🟢 kca |

## 4 · PERF — measured 🟢T1-sim (sim figures, never hardware rates)
Whole-prog launch-bound 419 cy at selftest N (K=1.0). Dependent body cadences (P-22 stamps; anchor n
tracks UNR 16/32/64; spacing invariant): POPC+XOR pair **9**; CLZ+guard+XOR 4-op iter **9**;
MULHI+OR pair **6** (IMUL/LOP3 overlap); FFS32 7-op iter **~33–36** — i.e. ffs ≈ 4–6× a popc;
BREV64 pair iter **6**. BREV32 dep ❓UN — both brev chains compiler-fold (count law verified instead).
SIMD costs do NOT transfer (P-22). ❓UN: isolated single-op latencies (chains measure pairs/iters) · II.

## 5 · EVIDENCE & EDGES
- Census diff table + cadence table: `probes/simt_castarith/RESULTS.md`; correctness within errors=0/884 kca run.
- Headers: surfaces+expansions `__clang_cce_simt_dav3510_intrinsic.h:391/524/563/576-639/796/805`.
- ❓UN: isolated POPC/CLZ latency · 64-bit op cadence · data-dominant N.
- Siblings: `simt.cast.fp-int` · `simt.elementwise.binary` · `simt.intminmax` (census, planned).
