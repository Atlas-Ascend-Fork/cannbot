# SIMT Debugging Patterns — Failure Symptoms and Diagnosis

> Runtime failures on Ascend 950PR SIMT operators and how to diagnose them.
> Complements the compile-time error table in `SKILL.md`.

---

## 1. UB Addressing Bug (Model C)

**Symptom**: Output data is partially correct but has wrong values scattered across blocks. Or segfault/hang on larger inputs. Correctness check fails with mismatches at block boundaries.

**Root cause**: Using global thread ID instead of `threadIdx.x` for `__ubuf__` writes.

```cpp
// BUG: writes beyond UB buffer bounds (128KB max per block)
gather_output[blockIdx.x * blockDim.x + threadIdx.x] = input[gather_idx];

// FIX: UB is per-block private — use block-local index
gather_output[threadIdx.x] = input[gather_idx];
```

**Why it's hard to catch**: Works for block 0 (where `blockIdx.x * blockDim.x + threadIdx.x == threadIdx.x`). Fails silently on other blocks — writes go out of the block's UB region, corrupting adjacent memory or crashing.

**Diagnosis**: If only block 0's output slice is correct and other blocks produce garbage, this is almost certainly the cause.

---

## 2. Launch Arity Mismatch

**Symptom**: Compile error or, worse, runtime misinterpretation of parameters.

| What you wrote | What the compiler sees |
|---|---|
| `kernel<<<56, 256, 0, stream>>>(...)` for Model B | `blocks=56, dynUBufSize=256, stream=0` — thread count (256) is interpreted as UB size, and the literal `0` as the stream pointer |
| `kernel<<<56, 0, stream>>>(...)` for Model A | `blocks=56, dynUBufSize=0, stream=stream` — missing thread count |

**Root cause**: Model B uses 3-arg `<<<blocks, ubuf, stream>>>` (thread count is in `dim3` inside `asc_vf_call`). Model A uses 4-arg `<<<blocks, threads, ubuf, stream>>>`.

**Diagnosis**: Check the `SIMT_MODEL`. Then count the args in `<<<>>>`:
```bash
grep "<<<" op_kernel/*.asc | awk -F',' '{print NF " args:", $0}'
```

Model B/C must have exactly 3 commas inside `<<<>>>`. Model A must have exactly 4.

---

## 3. dynUBufSize = 0 with LocalMemAllocator

**Symptom**: Silent memory corruption, wrong output, or intermittent crashes. Kernel appears to run but results are non-deterministic.

**Root cause**: `dynUBufSize = 0` in the launch `<<<>>>` when the kernel uses `LocalMemAllocator<Hardware::UB>` to allocate UB buffers (Model C).

```cpp
// BUG: kernel allocates UB, but launch reserves no dynamic UB space
kernel<<<8, 0, stream>>>(args...);

// FIX: reserve enough dynamic UB space
uint32_t dynUBufSize = 2048;  // must be > 0 when kernel uses UB alloc
kernel<<<8, dynUBufSize, stream>>>(args...);
```

**Diagnosis**: Search for `LocalMemAllocator` or `Alloc<` in the kernel. If found, `dynUBufSize` in the launch MUST be > 0.

**Sizing**: `dynUBufSize >= sum of all Alloc sizes * sizeof(type)`. In practice, 2048 works for small allocations; calculate precisely for larger ones.

---

## 4. Missing Pipe Sync (SetFlag/WaitFlag)

**Symptom**: Output is partially correct but contains stale or zeroed values. May appear correct on small inputs but fail on larger ones (timing-dependent data race).

**Root cause**: Missing `SetFlag`/`WaitFlag` synchronization between vector pipe (SIMD compute) and MTE3 (DataCopy to GM).

```cpp
// BUG: DataCopy starts before SIMD finishes writing to UB
asc_vf_call<simd_adds>(ub_output, ub_input, ...);
AscendC::DataCopy(gm_tensor, ub_tensor, count);  // race condition!

// FIX: sync V pipe → MTE3 before DataCopy
asc_vf_call<simd_adds>(ub_output, ub_input, ...);
AscendC::SetFlag<AscendC::HardEvent::V_MTE3>(0);
AscendC::WaitFlag<AscendC::HardEvent::V_MTE3>(0);
AscendC::DataCopy(gm_tensor, ub_tensor, count);
```

**Diagnosis**: In msprof profiling, `aiv_mte3_wait_ratio` near 0 (should be high, ~90%) means the sync is missing. If MTE3 is never waiting, it's likely reading stale UB data.

**Note**: Between sequential `asc_vf_call` invocations (e.g., SIMT → SIMD), NO sync is needed — `asc_vf_call` is synchronous.

---

## 5. Missing MTE2→V Sync (UB Pre-Staging)

**Symptom**: SIMT threads read uninitialized or partially copied data from UB. Output looks like random memory.

**Root cause**: Missing `asc_sync_notify`/`asc_sync_wait` between `asc_copy_gm2ub_align` (MTE2 pipe) and `asc_vf_call` (V pipe).

```cpp
// BUG: SIMT threads start before DMA finishes writing to UB
asc_copy_gm2ub_align(input_buf, input, size);
asc_vf_call<simt_kernel>(dim3(N), input_buf, ...);  // reads stale UB!

// FIX: sync MTE2 → V
asc_copy_gm2ub_align(input_buf, input, size);
if ASC_IS_AIV {
    asc_sync_notify(PIPE_MTE2, PIPE_V, EVENT_ID0);
    asc_sync_wait(PIPE_MTE2, PIPE_V, EVENT_ID0);
}
asc_vf_call<simt_kernel>(dim3(N), input_buf, ...);
```

**Diagnosis**: If output looks like the input was all zeros or has garbage in place of pre-staged data, check for missing MTE2 sync.

---

## 6. Wrong Architecture Flag

**Symptom**: Compiler crashes with "Unsupported NPU architecture" or kernel runs but hits "Illegal instruction" (aivec error 0x10) on hardware.

**Root cause**: Wrong `--npu-arch` value or deploying a dav-3510 binary on non-A950 hardware.

| Scenario | Error |
|---|---|
| `--npu-arch=dav-3101` (typo) | Compile: "Unsupported NPU architecture" |
| `--npu-arch=dav-2201` (910B arch) | Compile succeeds, but kernel fails on 950 |
| dav-3510 binary run on 910B | Runtime: "Illegal instruction", aivec error 0x10 on all cores |

**Valid values** (CANN 9.0.0-beta.2 / 9.1.0-beta.1):

| Target | `--npu-arch` |
|---|---|
| Ascend310P | `dav-2002` |
| Ascend910B | `dav-2201` |
| **Ascend950PR** | **`dav-3510`** |

**For Model A (Pure SIMT)**: Uses `--cce-aicore-arch=dav-c310-vec` instead (bisheng `-x dpp` mode). Different flag namespace, same underlying 950PR target.

**Diagnosis**: Check the CMakeLists.txt or build command for the arch flag. Verify hardware with `npu-smi info`.

---

## 7. VF as Class Member

**Symptom**: Compile error: `asc_vf_call` target is not a valid function.

**Root cause**: `__simt_vf__` function defined as a class method instead of a free function.

```cpp
// BUG: class member VF
class GatherKernel {
    __simt_vf__ __launch_bounds__(256) inline void gather(...) { ... }
    __global__ __vector__ void entry(...) {
        asc_vf_call<gather>(dim3(256), ...);  // compile error
    }
};

// FIX: extract VF as free function
__simt_vf__ __launch_bounds__(256) inline void simt_gather(...) { ... }

__global__ __vector__ void entry(...) {
    asc_vf_call<simt_gather>(dim3(256), ...);
}
```

**Diagnosis**: `grep -B10 "__simt_vf__" *.asc | grep "class\|struct"` — if VF is inside a class body, extract it.

---

## 8. Warp Functions Outside VF (Model B/C Only)

**Symptom**: Compile error or undefined behavior when warp functions are called in the wrong context.

**Root cause**: `asc_shfl_*`, `asc_reduce_*`, `asc_all`/`asc_any`/`asc_ballot` used outside the correct SIMT context.

**Rule for Model B/C**: Warp/sync/atomic SIMT functions are ONLY available inside `__simt_vf__`. They are NOT available in:
- `__global__ __vector__` entry functions
- `__simd_vf__` functions

**Model A exception**: Warp/sync/atomic functions ARE available directly in Model A `__global__` kernels. This is verified in SDK examples (`histogram.asc`, `sobel_warp_shfl.asc`, `insert_hash_table.asc`, `matrix_transpose.asc`).

**Diagnosis**: If Model B/C (source contains `__simt_vf__` or `asc_vf_call`), grep for warp function calls and check if they're inside a `__simt_vf__` function block. If Model A (no `__simt_vf__`), warp calls in `__global__` are valid.

---

## 9. dim3 Confusion (SIMT vs SIMD dispatch)

**Symptom**: `__simd_vf__` function runs as multi-threaded SIMT (wrong behavior) or `__simt_vf__` runs as single SIMD invocation (no thread parallelism).

**Root cause**: Presence/absence of `dim3()` as the first arg to `asc_vf_call` determines dispatch mode.

```cpp
// SIMT dispatch — has dim3:
asc_vf_call<simt_func>(dim3(THREAD_COUNT), args...);

// SIMD dispatch — NO dim3:
asc_vf_call<simd_func>(args...);
```

| Error | Result |
|---|---|
| `asc_vf_call<simd_func>(dim3(N), ...)` | SIMD function runs multi-threaded — likely crashes |
| `asc_vf_call<simt_func>(args...)` without `dim3` | Runs as single invocation — only one "thread" |

**Diagnosis**: Check every `asc_vf_call` — if calling a `__simt_vf__`, it MUST have `dim3`. If calling a `__simd_vf__`, it MUST NOT.

---

## 10. Thread Count Not Multiple of 32

**Symptom**: Compile warning or warp alignment issues. May cause `asc_shfl_*` and `asc_reduce_*` to produce wrong results for the last partial warp.

**Root cause**: SIMT execution is warp-based (32 threads per warp). Non-multiple-of-32 thread counts create a partial warp at the end.

**Fix**: Always round thread count to a multiple of 32:
```cpp
uint32_t threads = ((desired_threads + 31) / 32) * 32;
```

The excess threads hit the bounds check (`if (idx >= total_length) return;`) and exit immediately.

---

## 11. CPU Debug Mode Differences

**Symptom**: Code works in CPU debug mode but fails on NPU, or vice versa.

**Common causes**:

| Issue | CPU debug | NPU |
|---|---|---|
| Missing `SetKernelMode` | No SIMT threads run | N/A (only for CPU debug) |
| `<<<>>>` launch syntax | Not used | Required |
| `ICPU_RUN_KF` macro | Required | Not used |
| Memory alignment | Relaxed | Strict (32-byte UB alignment) |
| Timing races | Deterministic (serial) | Non-deterministic (parallel) |

**Always gate with `#if defined(ASCENDC_CPU_DEBUG)`**:
```cpp
#if defined(ASCENDC_CPU_DEBUG)
    AscendC::SetKernelMode(KernelMode::AIV_MODE);  // Model B/C only
    ICPU_RUN_KF(kernel, num_blocks, args...);
#else
    kernel<<<blocks, ubuf, stream>>>(args...);
#endif
```

**Note**: Pure SIMT (Model A) does NOT need `SetKernelMode` — it has no AscendC kernel operator context.

---

## Diagnostic Checklist

When a SIMT operator produces wrong results, check in this order:

1. **Correctness first**: Does block 0's output match golden? If yes but other blocks don't → UB addressing bug (#1)
2. **All zeros / garbage**: Check sync barriers — missing MTE2→V (#5) or V→MTE3 (#4)
3. **Non-deterministic**: Changes between runs → data race. Check `dynUBufSize` (#3) and pipe syncs (#4, #5)
4. **Illegal instruction**: Check `--npu-arch` (#6) and target hardware
5. **Compile fails**: Check launch arity (#2), VF placement (#7), includes, arch flags
6. **Works small, fails large**: Timing-sensitive race — sync issue that's hidden when execution is fast
7. **Works on CPU, fails on NPU**: Check CPU debug differences (#11), especially alignment and sync

---

## Profiling Hints

Use `msprof` to diagnose performance and correctness issues:

| Metric | Normal range | If abnormal |
|---|---|---|
| `aiv_vec_simt_vf_ratio` | 0.90–0.99 | < 0.80 → excessive scalar overhead, check kernel complexity |
| `aiv_mte3_wait_ratio` | 0.85–0.95 (Model C) | Near 0 → missing SetFlag/WaitFlag before DataCopy |
| `aiv_mte2_ratio` | Near 0 | High → unexpected DMA activity, check for accidental bulk copies |
| Block time variance | < 1.3x | > 1.5x → significant load imbalance, consider dynamic block sizing |
| `aiv_vec_vf_ratio` | Near 0 (Model A/B) | Non-zero → traditional SIMD instructions running (expected for Model C) |

**False positive**: msprof always flags "MTE2 bandwidth utilization lower than 80%" for SIMT kernels. This is expected — SIMT bypasses DMA engines for per-thread memory access.

---

## 12. OPP Workspace Buffer SIMT Write

**Symptom**: `error code = 334: The data returned by the BIU to the VEC is incorrect. subErrType: 0x4`. Occurs on any SIMT write to the workspace buffer — even a single thread, even a single store.

**Root cause**: The OPP workspace buffer (4th `GM_ADDR` parameter in `__aicore__` kernels, allocated via `GetWorkspaceSizes()`) is in a runtime-managed memory region with restricted BIU access modes. SIMT VF threads cannot write to it.

**What works vs what doesn't**:
| Memory region | SIMT read | SIMT write |
|---|---|---|
| Input tensor (`GM_ADDR x`) | ✅ | ✅ |
| Output tensor (`GM_ADDR values/indices`) | ✅ | ✅ |
| Workspace (`GM_ADDR workspace`) | ✅ (pointer passing) | ❌ (BIU error 334) |
| Tiling (`GM_ADDR tiling`) | ✅ (via `GET_TILING_DATA`) | Not tested |

**Fix**:
1. Set `workspace[0] = 0` in `TilingFunc` (no workspace allocation)
2. For SIMT scratch memory, use one of:
   - Reserved tail of an input/output tensor
   - A dedicated scratch tensor added to the operator definition
   - UB (`__ubuf__`) via Model C hybrid pattern
3. Never pass the workspace pointer to a `__simt_vf__` function for writing

**Diagnosis**: If a kernel crashes with error 334 immediately on launch, grep for any dereference of the workspace pointer inside `__simt_vf__` functions.

---

## 13. `set_flag(PIPE_V, PIPE_S)` Invalid Event ID on Ascend950

**Symptom**: Compile error or runtime failure when using `set_flag(PIPE_V, PIPE_S)` or `set_flag(PIPE_S, PIPE_V)` in SIMD/scaler operators compiled for `ascend950` target.

**Root cause**: The `set_flag`/`wait_flag` event ID system differs between Ascend 910B and Ascend 950. Some pipe combinations that work on 910B produce invalid event IDs on 950.

**Fix**: Replace `set_flag`/`wait_flag` pairs with `pipe_barrier(PIPE_ALL)` — a heavier but universally safe synchronization.

```cpp
// ❌ May fail on ascend950
set_flag(PIPE_V, PIPE_S, EVENT_ID0);
wait_flag(PIPE_V, PIPE_S, EVENT_ID0);

// ✅ Works on all targets
pipe_barrier(PIPE_ALL);
```

**Diagnosis**: If a previously-working 910B operator fails to compile or crashes on ascend950, check for `set_flag` calls.

---

## 14. torch_npu SoC Mismatch on Ascend950PR

**Symptom**: `Unsupported soc version: Ascend950PR 9579` when attempting to use `torch_npu` for evaluation.

**Root cause**: `torch_npu` does not support Ascend950PR hardware. Its SoC registry doesn't include the 950PR device ID (9579). This affects all operators, not just SIMT.

**Fix**: Use standalone C++ test binaries with the ACL API for A950 evaluation. All successful A950 experiments in this project use this approach. Follow the `test_topk.cpp` / `test_scatter_add.cpp` pattern:
- `aclInit` → `aclrtSetDevice` → `aclrtMalloc` → `aclrtMemcpy H2D` → kernel launch → `aclrtSynchronizeStream` → `aclrtMemcpy D2H` → verify → cleanup

**Diagnosis**: If `import torch_npu` works but `torch_npu.npu.set_device(0)` fails with the SoC error, this is the cause. Switch to standalone binary.

---

## 15. SyncAll Does Not Serialize Two VF Passes Across Cores

**Symptom**: Multi-VF kernel (e.g., copy VF followed by scatter VF) produces nondeterministic output — ~15% of cells have wrong values that change run-to-run. Adding `SyncAll<true>()` between the two `asc_vf_call`s does not fix it.

**Root cause**: `asc_vf_call` dispatches VF sub-tasks **asynchronously relative to the SIMD entry**. `SyncAll<true>()` is a barrier in the entry's SIMD context, but it does not wait for VF-worker completion on other cores. With `SetBlockDim > 1`, core A's VF-2 (scatter) can start before core B's VF-1 (copy) has finished, reverting cells that the copy already wrote.

**Verified on**: A5 (Ascend950PR), CANN 9.0.0-beta.2. **This is a durable, hardware-level finding — do not re-test.**

**Fix**: Do not rely on two `asc_vf_call`s in one entry for cross-core ordering. Use one of:
1. **Two separate kernel launches**: Register a phase attr, dispatch two `EXEC_NPU_CMD` calls from the wrapper. Stream ordering serializes them.
2. **`SetBlockDim(1)`**: Makes all VF calls sequential on one core. Only viable for small data.

**Note:** The wrapper must NOT do data movement — no `data.clone()`, `data.copy()`, or `torch.zeros_like()` (strict wrapper rule). The kernel owns every output element (SKILL.md rule 13). See SKILL.md rule 7.

---

## 16. Stale Installed .o (False Path Divergence)

**Symptom**: aclnn path fails while pybind passes on the same kernel. Or: rebuilt kernel behaves identically to the old version despite source changes.

**Root cause**: `build_run.sh`'s `find dist -name '*.run' | head -1` keeps a pre-existing stale `.run` and deletes the fresh CPack output. The opp `.run` installer skips overwriting hash-named `*_*.o` files that already exist on disk. Together, these cause the OLD kernel binary to silently persist through a rebuild.

**Fix**: Before every rebuild:
1. `rm -f dist/*.run`
2. `rm -rf` the installed vendor kernel directory + `custom_ops_impl/dynamic/<op>`
3. After installing, md5-verify that the built `.o` matches the installed `.o`

**Diagnosis**: If aclnn fails broadcast cases while pybind passes (or vice versa), and the kernel source looks correct, check whether the installed binary is stale.

---

## 17. env-probe Returns null for Ascend950PR

**Symptom**: `soc_version=null` in env.json after running the auto-detection probe. Downstream scripts fail on missing SoC version.

**Root cause**: The auto-mapper does not recognize the Ascend950PR SKU. The npu-smi chip name is `Ascend950PR` but the probe's regex/lookup table does not include it.

**Fix**: Manually write env.json from `npu-smi info -t board -i 0` Chip Name. The canonical string is `Ascend950PR` (via `tikicpulib/Ascend950PR_9599`), build compute-unit is `ascend950`.

**Diagnosis**: Run `cat shared/env.json` (or `best/env.json`). If `soc_version` is null or empty, this is the cause.

---

## 18. `set -u` + `source set_env.bash` Silent Abort

**Symptom**: eval script exits silently with no error message. No output, no log, no build artifacts.

**Root cause**: `set -u` (treat unset variables as errors) trips on unset `LD_LIBRARY_PATH`-style variables inside the vendor-provided `set_env.bash`. The script aborts at the source line before reaching any operator-specific code.

**Fix**: Remove `set -u` from the eval script, or insert `set +u` immediately before `source .../set_env.bash` and re-enable after.

**Diagnosis**: If a script produces zero output and the last successful line in `bash -x` trace is the `source set_env.bash` call, this is the cause.

---

## 19. Thermal Skew (~5% Between Sessions)

**Symptom**: Variant rankings flip between sessions. A variant that appeared 3% faster yesterday is 2% slower today. Winners are not reproducible across separate timing runs.

**Root cause**: Approximately 5% thermal drift between sessions on A5 hardware. This magnitude exceeds most real performance wins from tuning.

**Fix**: Re-time all variants back-to-back in one session. For deltas below approximately 1.5x, interleave A/B in round-robin order within the same session to cancel thermal drift.

**Diagnosis**: If two independent timing runs of the same kernel differ by 3-6% with no code changes, this is the cause.

---

## 20. Promoted `final/` Must Be Rebuilt and Re-Gated

**Symptom**: `final/` directory has no `pybind_lib` or contains stale binaries. Running eval on `final/` fails or produces different results from the per-variant directory that was promoted.

**Root cause**: Evolution records 20/20 from per-variant build directories. When a variant is promoted to `final/`, only the source files are copied — the directory was never independently built or correctness-gated.

**Fix**: Always rebuild the promoted `final/` directory from source and re-run the full 20/20 correctness gate before trusting it. Promotion = copy source + rebuild + re-gate.

**Diagnosis**: Check `ls final/pybind_lib/`. If empty or missing, the directory was never built.

---

## Failure-Signature Quick Lookup

| Symptom | Likely cause | First check |
|---------|--------------|-------------|
| Local 20/20 but benchsite 0/20 | VF calls a device helper (A14 silent drop) | Is every VF fully self-contained? No calls to helper functions? |
| 507035 on some dtypes only | `__ubuf__` + `asc_syncthreads` on non-fp32/int64 | Switch to Direct-GM, or bitcast-dodge if pure data-movement (see `memory_optimization_guide.md` §9) |
| 507035 on large cases only | grid >= ~65536 blocks | Cap numBlocks at 32768 (SKILL.md Rule 8) |
| 507035 immediately on any input | `dim3()` given grid size instead of threads-per-block, or tpb > launch_bounds | `dim3` = threads/block; `SetBlockDim` = grid |
| All-zero or flaky wrong output | Per-launch metadata via `__gm__` globals (cross-core stale) | Pass tiling struct pointer to VF (SKILL.md Rule 12) |
| aclnn fails, pybind passes (identical kernel) | Stale installed `.o` (#16) | `rm -f dist/*.run`, `rm -rf` vendor kernel dir, md5-verify |
| EZ1001 at bundle build | VF calls a device helper | Inline all helper logic into the VF |
| `Cannot select: i64 = ctpop` | ctz/popcount builtin not selectable on ascend950 bisheng | Remove; use shift-loop |
| Two code paths overwrite same output cell | No-clone cross-core race | Route special branch first + `return` (F3 single-owner partition) |
