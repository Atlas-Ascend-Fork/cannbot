# `simt.atomic.rmw` — global-memory atomics (`Simt::Atomic{Add,Sub,Max,Min,And,Or,Xor,Inc,Dec,Exch,Cas}`)

## HEAD

```yaml
head_schema: pb5/v1
op: simt.atomic.rmw                    # canonical instance: leader-only AtomicAdd combine, int32, N=4096
paradigm: SIMT
core: AIV
lowering: "AscendC::Simt::Atomic{Add,Sub,Max,Min,And,Or,Xor,Inc,Dec,Exch,Cas}<T>(__gm__ T*, ...) -> atomic* builtins -> lsu SIMT_RED ops; 11 ops × {s32,u32,s64,u64,f32} = 55 lowerings (one entry, dtype table)"
dtypes: [s32]                          # VERIFIED bit-exact via warp-sum combine; u32 analogous; f32 NON-deterministic order => §2.6(c)
selection_keys: [control.divergent-per-element, xlate.cuda-1to1]
not_for: [pattern.reduction-full]      # full reduce → REDUX + ONE leader atomic; never per-thread atomics
cuda_pta_analog: "CUDA atomicAdd/atomicMax/...; returns old value"
false_friends: [atomic_per_thread_kills_throughput_x24, all_lane_combine_overcounts_32x,
                fp32_atomics_not_bit_exact, atomic_returns_old_value]
cost_model:
  roofline_run_id: probes/simt_isa_cost/RESULTS.md
  binding_resource: UN          # GM atomic RTT serializes dependent chains; launch-bound whole-prog
  optimum: {value: 0.102, unit: cycles/elem}
  perf_factor_K: 1.0
  latency_cycles:
    ATOMIC_GM_dep: "~16.9k RTT (RANGE; linear in chain length 2.14x at 2x)"
    contention_alllane_vs_leader: "x24 measured (5,326 -> 127,926 body span)"
  elem_per_cycle: "overlap by warps; one leader atomic per warp costs ~0 extra"
  toolchain:
    bisheng: "clang version 15.0.5 (clang-5c68a1cb1231 flang-5c68a1cb1231) 2026-05-09"
    model: "{model_name: Ascend950PR_9599, cube_cores: 32, vec_cores: 64}"
    configs: [1981_sim_ffts_plus.toml, 1981_model.toml]
verify_cmd: |
  bash ${PROBE_WORKSPACE}/scripts/build.sh k.cpp
  bash ${PROBE_WORKSPACE}/scripts/run.sh k
  bash ${PROBE_WORKSPACE}/scripts/verify.sh
  bash ${PROBE_WORKSPACE}/scripts/profile_simt.sh k   # lsu RED count == leaders (warps); all-lane mutate => x32
sources:
  - probes/simt_isa_cost/RESULTS.md                # atomic RTT + x24 serialization
  - probes/simt_reduce/cannsim_20260604082013_kuse/  # leader AtomicAdd bit-exact
  - probes/simt_reduce/RESULTS.md                  # 32x overcount hazard run
  - "asc/impl/simt_api/cpp/dav_3510/kernel_simt_atomic_impl.h:82"  # AtomicAdd -> atomicAdd; family decls
status: piloted
tier_summary:
  - {claim: leader AtomicAdd combine bit-exact int32, tier: T1-sim}
  - {claim: all-lane combine overcounts 32x AND serializes x24, tier: T1-sim}
  - {claim: dependent atomic ~16.9k cy RTT linear, tier: T1-sim}
  - {claim: 11 ops x 5 dtypes surface, tier: H}
  - {claim: f32 atomic order non-deterministic, tier: T1-sim}
```

## 0 · SELECT
Cross-warp/block combine of a few values → here (leader-only). Full-array reduce → REDUX (16cy) per
warp + ONE atomic. Per-element atomics on shared counters = ×24 serialization measured — restructure.

## 1 · CONTRACT
`Simt::AtomicAdd<int32_t>(__gm__ addr, v)` adds atomically, returns OLD (🧾H :82; 🟢 used in warp-sum
kuse, gsum=-2240 exact). Family Add/Sub/Max/Min/And/Or/Xor/Inc/Dec/Exch/Cas × {s32,u32,s64,u64,f32}
(🧾H). int ops order-free bit-exact; f32 non-associative ⇒ §2.6(c).

## 2 · USE
The canonical leader-only combine §USE lives in `simt.reduce.warp-sum` §2 (Atomic mutate marked).
Mutate `AtomicAdd→AtomicMax/Min` with the matching identity per HAZARDS.

## 3 · HAZARDS
| Hazard | Symptom | Repair | Evidence |
|---|---|---|---|
| atomic from all 32 lanes | 32× value; ×24 wall | leader only | 🟢 hz_alllane + spans |
| dependent atomic chain | 16.9k cy/link serial | independent atomics; overlap warps | 🟢 P-22 |
| fp32 atomic expected exact | low-bit drift | int dtypes or §2.6(c) tolerance | 🟢 hz_fp32 |
| identity mismatch on Max/Min | clamped result | INT_MIN / INT_MAX | 🟢 warp-sum |

## 4 · PERF
RTT ~16.9k dep, overlap by warps; leader pattern = 1 RED/warp visible in lsu (closed loop:
profile RED count == warps; all-lane mutate ⇒ ×32 count + ~×24 span). Whole-prog launch-bound K=1.0.

## 5 · EVIDENCE & EDGES
P-22 spans+slope; warp-sum kuse + hazard runs; impl :82. ❓UN: per-dtype T-ref (u32/s64/u64/f32); RTT @≥1M.
Siblings: reduce.warp-sum (leader pattern) · ldst.global.
