# SIMT Build & Compile Guide

Verified on CANN 9.1.0-beta.3 / bisheng (clang 15.0.5) / Ascend950PR (`dav-3510`).
Every command below was executed on-device; exit codes are real, not inferred.

**Quick recipes and error fixes** → [jump to Quick Reference](#quick-reference)  
**Detailed build walkthroughs** → continue reading below

---

<a id="quick-reference"></a>
## Quick Reference

Copy-paste recipes, error table, and the most common build traps.

### Environment setup

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
A="$ASCEND_HOME_PATH/$(uname -m)-linux"   # x86_64-linux or aarch64-linux
```

### Recipes

**Model B/C — device-only compile** (syntax + codegen check):

```bash
bisheng --asc-aicore-lang --npu-arch=dav-3510 --cce-aicore-only \
  -std=c++17 -O2 -D__NPU_TILING__ \
  -I"$A/include" -I"$A/asc/include" -I"$A/asc/impl" -I. \
  -c my_op.asc -o my_op.o

nm -C my_op.o | grep -c 'simt_'    # must be > 0
```

**Model B/C — standalone executable** (file has its own `main()`):

```bash
bisheng --asc-aicore-lang --npu-arch=dav-3510 \
  -std=c++17 -O2 \
  -I"$A/include" -I"$A/asc/include" -I"$A/asc/impl" -I. \
  MyOp.asc -o myop \
  -L"$A/lib64" -Wl,-rpath,"$A/lib64" -lascendcl -lruntime -lm
```

**Model A — pure SIMT**:

```bash
# Linking build (with main())
bisheng --asc-aicore-lang --npu-arch=dav-3510 -cce-enable-puresimt \
  -std=c++17 -O2 \
  -I"$A/include" -I"$A/asc/include" -I. \
  MyOp.asc -o myop \
  -L"$A/lib64" -Wl,-rpath,"$A/lib64" -lascendcl -lruntime -lm

# Device-only compile (-c)
bisheng --asc-aicore-lang --npu-arch=dav-3510 -cce-enable-puresimt \
  --cce-aicore-only -std=c++17 -O2 \
  -I"$A/include" -I"$A/asc/include" -I. \
  -c MyOp.asc -o MyOp.o
nm MyOp.o | grep -c 'Kernel_Type'   # must be > 0
```

**msopgen full project build**:

```bash
cd {OpName}Custom
source build.sh
BUILD_RC=$?
[ $BUILD_RC -ne 0 ] || ! ls build_out/*.run >/dev/null 2>&1 && echo "BUILD FAILED (rc=$BUILD_RC)"
```

`source` (not `bash`) avoids SIGTTIN stall under docker+tmux, but also means a `set -e` inside the script won't halt your shell — always check explicitly.

### The three traps that cost the most time

**1. `--cce-aicore-only` is mandatory on `-c` compiles, and it fails silently when omitted**

Measured on the same source, only the flag differing:

| Command | exit | size | `simt_*` VF | `Kernel_Type` |
|---|---|---|---|---|
| without `--cce-aicore-only` | **0** | 35376 B | **0** | **0** |
| with `--cce-aicore-only` | 0 | 14368 B | 8 | 2 |

Both "succeed". The first emits the **host half** of the translation unit — no device code, no warnings. Always verify codegen by symbol count, never by exit code:

```bash
nm -C my_op.o | grep -c 'simt_'        # expect: your VF instantiation count
nm -C my_op.o | grep -c Kernel_Type    # expect: >= 1
```

An exit-0 build with `VF=0` is a failed build. Do **not** pass `--cce-aicore-only` to a command that links a `main()` — it fails with `cannot specify -o when generating multiple output files`. The flag combines fine with `-cce-enable-puresimt` on a `-c` compile; the restriction is about the link phase, not the model.
<!-- claim: cce-aicore-only-scope · also in: ../SKILL.md · find with: grep -rn "claim: cce-aicore-only-scope" skills/simt-codegen · edit all sites together -->

**2. Front end must be `--asc-aicore-lang`, not `-x cce`**

`-x cce` is a different dialect that cannot resolve the ASC headers:

```
fatal error: 'kernel_tpipe.h' file not found
```

This is **independent of include paths** — adding more `-I` does not fix it. Also produces `__hif8 is not supported on this target`. Do not combine `-xasc` with `--asc-aicore-lang` — the two conflict.

**3. Model A must omit `KERNEL_TASK_TYPE_DEFAULT` entirely**

Model A requires `-cce-enable-puresimt`; that dialect infers AIV routing on its own, and the macro's header does not parse there. Adding it costs you the object. Model B/C need it. See [§2.3](#kernel-task-type) for measurements.

### Error table

| Error | Cause | Fix |
|---|---|---|
| exit 0 but `nm` shows 0 `simt_*` symbols | `--cce-aicore-only` missing → host-only object | Add `--cce-aicore-only` to the `-c` compile |
| `'kernel_tpipe.h' file not found` | Wrong front end (`-x cce`) | Use `--asc-aicore-lang` |
| `__hif8` / `__fp8e4m3 is not supported on this target` | Wrong front end / dialect | Use `--asc-aicore-lang` |
| `'{op}_custom_tiling.h' file not found` | Kernel's own header not on path | Add `-I.` |
| `use of undeclared identifier 'td'` at `GET_TILING_DATA` | Macro is msopgen-generated | Add the guarded fallback (see get_tiling_data_pattern.md) |
| `call to __host__ function from __global__ __aicore__` | `__NPU_TILING__` undefined | Add `-D__NPU_TILING__` |
| `auto derivate failed` at link | No kernel task type on a **non-puresimt** entry | Add `KERNEL_TASK_TYPE_DEFAULT(...)` (§2.3). Does **not** apply under `-cce-enable-puresimt` — that dialect infers AIV |
| `cannot specify -o when generating multiple output files` | `--cce-aicore-only` on a linking build | Drop the flag, or add `-c` |
| `expecting global function ... requires __aicore__` + `undeclared identifier 'blockIdx'` | Model A in the non-puresimt dialect | Add `-cce-enable-puresimt` |
| `unknown type name '__device__'` | Defined in neither dialect | Use `__simt_callee__` |
| `simt_callee function can only be called by simt_vf/simt_callee` | Warp intrinsic called from unqualified helper | Mark helper `__simt_callee__` |
| `undefined reference to 'exp'` / `'log'` | libm not linked | Add `-lm` |
| `Unsupported NPU architecture or soc` | Bad `--npu-arch` | Only `dav-2002`, `dav-2201`, `dav-3510` are valid |
| `Cannot select: i64 = ctpop` | `ctz`/`ctpop` not instruction-selectable on ascend950 | Use a shift loop |

---

## Detailed Walkthroughs

There are **two** ways a SIMT kernel gets built. Pick the one that matches what you are producing, then follow it exactly.

| You are producing | Path | Section |
|---|---|---|
| A standalone `.asc` you compile and run yourself | **Standalone** | §1 |
| A kernel inside an msopgen `{Op}Custom/` project | **msopgen** | §2 |

**Model A adds a flag.** A pure-SIMT (Model A) kernel needs `-cce-enable-puresimt` on top of whichever recipe you pick. Without it the compiler is in the other dialect and rejects the file:

```
error: expecting global function ... requires the __aicore__ or __aicpu__ qualifier
error: use of undeclared identifier 'blockIdx'
```

This is not a code defect — it is the wrong dialect. See §3. Models B and C must **not** pass the flag.

---

## §1 Standalone build (`.asc`, self-contained, host + device in one file)

This is what `SKILL.md` §Output asks for. The file contains its own `main()`, does its own `aclrtMalloc`/`aclrtMemcpy`, and does **not** use `GET_TILING_DATA`.

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
A="$ASCEND_HOME_PATH/x86_64-linux"      # aarch64-linux on ARM hosts

bisheng --asc-aicore-lang --npu-arch=dav-3510 -std=c++17 -O2 \
  MyOp.asc -o myop \
  -I"$A/include" -I"$A/asc/include" -I"$A/asc/impl" \
  -L"$A/lib64" -Wl,-rpath,"$A/lib64" \
  -lascendcl -lruntime -lm
```

Then `./myop`.

### Flag notes (each one cost a failed build to learn)

| Flag | Why |
|---|---|
| `--asc-aicore-lang` | Selects the ASC front end. **Do not also pass `-xasc`** — the two conflict and the driver errors out. |
| `--npu-arch=dav-3510` | Ascend950PR. Only `dav-2002`, `dav-2201`, `dav-3510` are accepted. `--soc-version` is *not* a bisheng flag. |
| `-lm` | Required whenever the kernel uses `std::exp`, `std::log`, `powf`, etc. Omitting it fails at link, not compile, so it looks like a codegen bug. |
| `-I$A/asc/impl` | Belt-and-braces. Verified: `--asc-aicore-lang` already puts the ASC tree on the search path, and objects built with `-I.` alone are byte-identical to those built with all three paths. Keep it for leaner installs, but if a vendor header comes up missing, suspect the front-end flag (§3), not a missing path. |
| `-I.` | **Load-bearing** whenever the kernel includes its own tiling header — otherwise `'{op}_custom_tiling.h' file not found`. |
| `--cce-aicore-only` | **Required on `-c`, forbidden when linking.** Omitting it on a device-only compile silently yields an object with no device code (rc=0, zero VF instantiations). On a file with a `main()` it fails with `cannot specify -o when generating multiple output files`. See Quick Reference. |

### Compile-only check

To validate codegen without linking (no `main()` needed):

```bash
bisheng --asc-aicore-lang --npu-arch=dav-3510 --cce-aicore-only \
  -std=c++17 -O2 -c MyOp.asc -o myop.o \
  -I"$A/include" -I"$A/asc/include" -I"$A/asc/impl"

nm -C myop.o | grep -c 'simt_'   # must be > 0, or you validated nothing
```

`--cce-aicore-only` is not optional here.

### Host/device separation in a standalone file

`__gm__` is a device address-space qualifier and does not belong in host-side casts in `main()`. On CANN 9.1.0-beta.3 / clang 15.0.5, `reinterpret_cast<__gm__ float*>(devPtr)` on the host is a **warning, not an error** — `'cce_global' attribute ignored [-Wignored-attributes]` — and the link still succeeds. Keep host pointers plain (`void*` / `float*`) and let the kernel signature apply `__gm__`, but don't chase these warnings when diagnosing a build failure: they are not the cause.

---

## §2 msopgen project build (`{Op}Custom/op_kernel/{op}_custom.cpp`)

A kernel that lives inside an msopgen project is **not** self-contained. Three things are supplied by the project's build system, and a kernel that uses them will not compile on its own. This is the single most common cause of a "the reference example doesn't compile" report.

### 2.1 `GET_TILING_DATA` is generated, not shipped

`GET_TILING_DATA` is defined **nowhere in the CANN headers**. It is emitted at build time by:

```
$ASCEND_HOME_PATH/tools/op_project_templates/ascendc/customize/cmake/util/tiling_data_def_build.py
```

which reads the `TILING_DATA_FIELD_DEF(...)` declarations in `op_host/{op}_tiling.h` and writes `{op}_tiling_data.h` containing the struct, an `Init{Struct}()` copier, and finally:

```cpp
#undef GET_TILING_DATA
#define GET_TILING_DATA(tiling_data, tiling_arg) \
    MyOpTilingData tiling_data;                  \
    InitMyOpTilingData(tiling_arg, &tiling_data)
```

**Consequence:** the hand-written `{op}_custom_tiling.h` next to an example only declares the *struct*. It does not define the macro. Compiling such a file outside the project yields:

```
error: use of undeclared identifier 'tilingData'
    GET_TILING_DATA(tilingData, tiling);
```

This is expected, not a bug in the example. Build it through the project, or use the shim in §2.4.

### 2.2 `-D__NPU_TILING__` selects the device copier

The generated header defines `Init{Struct}` twice:

```cpp
#ifdef __NPU_TILING__
inline [aicore] void InitMyOpTilingData(const __gm__ uint8_t*, MyOpTilingData*);
#else
inline void InitMyOpTilingData(uint8_t*, MyOpTilingData*);   // host
#endif
```

Without `-D__NPU_TILING__` the host overload is the only candidate and you get:

```
error: no matching function for call to 'InitMyOpTilingData'
note: candidate function not viable: call to __host__ function from __global__ __aicore__ function
```

The msopgen CMake passes this flag. A manual compile must too.

<a id="kernel-task-type"></a>
### 2.3 The kernel type attribute, and when it is mandatory

In the **non-puresimt** dialect, `REGISTER_TILING_DEFAULT(...)` alone is **not** sufficient. Without an explicit task type the linker cannot infer one:

```
WARNING: kernel type of __global__ func: my_op is not marked. auto type derivate may be failed.
ld.lld: error: Error: the type of kernel function my_op auto derivate failed,
        please manually add the function type attribute
```

Add it as the first statement of the `__global__` entry function. For a vector-core-only kernel in that dialect:

```cpp
extern "C" __global__ __aicore__ void my_op(GM_ADDR x, GM_ADDR y,
                                            GM_ADDR workspace, GM_ADDR tiling)
{
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);   // ← required
    REGISTER_TILING_DEFAULT(MyOpTilingData);
    GET_TILING_DATA(td, tiling);
    ...
}
```

Valid values live in `$A/asc/impl/basic_api/utils/kernel_utils_macros.h`:
`KERNEL_TYPE_AIV_ONLY`, `KERNEL_TYPE_MIX_AIC_1_0`, `KERNEL_TYPE_MIX_AIC_1_1`,
`KERNEL_TYPE_MIX_AIC_1_2`, `KERNEL_TYPE_MIX_AICORE`, `KERNEL_TYPE_MIX_VECTOR_CORE`.
Pick by what the kernel drives, not by model number: vector core only →
`KERNEL_TYPE_AIV_ONLY`; drives the cube unit → one of the `MIX_AIC_*` variants.

**Do not add it to a Model A kernel.** Model A requires `-cce-enable-puresimt` (without it, `blockIdx` is undeclared — see §5), and in that dialect the macro is *unreachable*, while AIV routing is inferred anyway. Note the direction of that implication: Model A ⇒ puresimt. The converse is not established here, so read this as a rule about the dialect, not about model numbers.

Measured on Ascend950PR_9599 / CANN 9.1.0-beta.3 / bisheng clang 15.0.5 / `--npu-arch=dav-3510`, same kernel body each time, compiled with `-cce-enable-puresimt --cce-aicore-only -c`:

| entry form | result |
|---|---|
| bare `__global__` + `blockIdx`, no includes | **3152 B**, `simt_`=1, `Kernel_Type`=1, emits `.AIV_Kernel_Type_probe_op` |
| `+ KERNEL_TASK_TYPE_DEFAULT(...)`, no include | no object — `use of undeclared identifier 'KERNEL_TYPE_AIV_ONLY'` |
| `+ #include "kernel_utils_macros.h"`, `-I .../basic_api/utils` | no object — `kernel_utils_macros.h:35: fatal error: 'kernel_macros.h' file not found` |
| `+ -I .../basic_api -I .../impl` so that header *does* resolve | no object — ≥20 errors (hits `-ferror-limit`): `unknown type name '__simd_callee__'`, `use of undeclared identifier 'PIPE_ALL'`, `__device__ ... not allowed on non-static local variables` |

`kernel_macros.h` **does** exist on disk (`$A/asc/impl/basic_api/kernel_macros.h` and `$A/ascendc/include/basic_api/impl/kernel_macros.h`), so "file not found" is a search-path symptom, not an absent header — and fixing the path only moves the failure deeper, because the header's *contents* do not parse in this dialect. The working combination is the one with no task-type declaration at all:

```cpp
// probe6.asc — minimal Model A entry. No includes, no task type, no __aicore__.
extern "C" __global__ __launch_bounds__(256) void probe_op(int* out, unsigned n)
{
    unsigned tid = blockIdx.x * blockDim.x + threadIdx.x;
    if (tid < n) out[tid] = (int)tid;
}
```

```bash
bisheng --asc-aicore-lang --npu-arch=dav-3510 -cce-enable-puresimt --cce-aicore-only \
  -std=c++17 -O2 -I"$A/include" -I"$A/asc/include" -I. -c probe6.asc -o probe6.o
[ -f probe6.o ] && nm -C probe6.o | grep -c 'simt_'   # 1 — gate on this, not $?
```

The same body with `out[tid] = (int)tid * 2`, linked with a `main()` and run on device, printed `h[0]=0 h[1]=2 h[255]=510 mismatches=0` and exited 0 — so this links and executes, not merely compiles. (That device run is carried forward from the 2026-08-07 session log; the object fingerprints in the table above were re-measured directly.)

**Scope.** Both probes were standalone `.asc` files with their own `main()`. A Model A kernel inside an msopgen project additionally brings host tiling and `GET_TILING_DATA`; that combination is **untested** — do not read this section as clearing it.

**Reading the diagnostic.** For an undefined function-like macro, clang reports only the first unresolved name *inside the parentheses* — a control using an identifier that exists nowhere (`TOTALLY_UNDEFINED_THING(KERNEL_TYPE_AIV_ONLY)`) produces the identical single error. So `use of undeclared identifier 'KERNEL_TYPE_AIV_ONLY'` tells you nothing about whether `KERNEL_TASK_TYPE_DEFAULT` itself is defined; check with `-dM -E` instead (under puresimt, neither name is predefined).

### 2.4 Compiling an msopgen kernel standalone (for a fast syntax check)

To type-check a project kernel without running the whole msopgen build, hand-write the generated tail into a shim header and compile to an object file:

```cpp
// shim_tiling.h  — emulates the generated {op}_tiling_data.h
#include "my_op_custom_tiling.h"          // the struct declaration
#ifdef __NPU_TILING__
inline [aicore] void InitMyOpTilingData(const __gm__ uint8_t* tiling,
                                        MyOpTilingData* const_data)
{
    const __gm__ uint32_t* src = (const __gm__ uint32_t*)tiling;
    uint32_t* dst = (uint32_t*)const_data;
    for (auto i = 0; i < sizeof(MyOpTilingData) / 4; i++) *(dst + i) = *(src + i);
}
#endif
#undef GET_TILING_DATA
#define GET_TILING_DATA(td, ta) MyOpTilingData td; InitMyOpTilingData(ta, &td)
```

```bash
bisheng --asc-aicore-lang --npu-arch=dav-3510 --cce-aicore-only \
  -std=c++17 -O2 -D__NPU_TILING__ \
  -c my_op_custom.cpp -o my_op.o \
  -I"$A/include" -I"$A/asc/include" -I"$A/asc/impl" -I.

nm my_op.o | grep -c 'Kernel_Type'   # must be > 0
```

`-I.` is load-bearing — it is how `my_op_custom_tiling.h` above is found.

This is a **syntax and codegen check only** — the real tiling values still come from `op_host` at runtime. Use it to iterate quickly, then build the project properly before evaluating.

### 2.5 Full project build

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
cd {op_name}Custom
source build.sh            # see the caveat below
```

`--soc ascend950` must have been passed to `gen_project.py` when the project was scaffolded, or CMakePresets.json targets `ascend910b` and the build produces wrong artifacts.

**Caveat on `source build.sh`.** `source` is used because `bash build.sh` creates a new process group that catches SIGTTIN/SIGTTOU under docker+tmux and stops silently. But `source` also means a `set -e` inside the script **does not halt your shell**, so a failed cmake/make can leave `$?` at 0 and the build looks green when it is not. Always check explicitly:

```bash
source build.sh
BUILD_RC=$?
if [ $BUILD_RC -ne 0 ] || [ ! -f build_out/*.run ]; then
    echo "BUILD FAILED (rc=$BUILD_RC)"; fi
```

Do not report a build as passing on the strength of `source build.sh` alone.

---

## §3 Two compiler dialects — Model A vs Models B/C

`-cce-enable-puresimt` does not merely add a flag; it selects a **different preprocessor dialect**. The same identifiers expand to different attributes:

| Spelling | Model A (`-cce-enable-puresimt`) | Models B/C (default) |
|---|---|---|
| header | `__clang_dpp_runtime_wrapper.h` | `__clang_cce_defines.h` (via `__clang_cce_types.h`) |
| `__global__` | `__attribute__((global))` | `__attribute__((cce_kernel))` |
| `__aicore__` | `__attribute__((device))` | `__attribute__((cce_aicore))` |
| `__launch_bounds__(N)` | `__attribute__((launch_bounds(N,1)))` | `__attribute__((cce_launch_bounds(N)))` |
| `LAUNCH_BOUND(N)` | **not defined** | `__attribute__((cce_launch_bounds(N)))` |
| `__simt_callee__` | **not defined** | `__attribute__((cce_simt_callable))` |

Practical consequences:

- **Use `__launch_bounds__`, not `LAUNCH_BOUND`.** `__launch_bounds__` is spelled the same in both dialects; `LAUNCH_BOUND` exists only in the non-puresimt one. Standardising on `LAUNCH_BOUND` would break every Model A kernel.
- **`kernel_operator.h` and the AscendC high-level APIs are unavailable under puresimt.** Model A kernels use only `simt_api/` headers plus ACL on the host. Do not copy a Model B skeleton into a Model A file.
- `__aicore__` exists in both but means different things. A Model A `__global__` entry does not take the Model B `__aicore__` + `asc_vf_call` shape.

### Device-helper qualifier

A helper function that calls a warp intrinsic (`asc_reduce_add`, `asc_shfl_down`, …) must be marked **`__simt_callee__`**:

```cpp
template <typename T>
__simt_callee__ inline T warp_reduce_sum(T v) { return asc_reduce_add(v); }
```

`__device__` is **not** defined in either dialect — it produces `error: unknown type name '__device__'` in both. An unqualified or `__aicore__` helper produces `simt_callee function can only be called by simt_vf/simt_callee function`. `__simt_callee__` functions are callable only from `__simt_vf__` or another `__simt_callee__`.

---

## §4 Environment probing

`ASCEND_HOME_PATH` resolves to an arch-specific subdirectory. On x86 hosts it is `$ASCEND_HOME_PATH/x86_64-linux`; on ARM it is `$ASCEND_HOME_PATH/aarch64-linux`. Derive it rather than hard-coding:

```bash
A="$ASCEND_HOME_PATH/$(uname -m)-linux"
```

SoC auto-detection via `npu-smi` may be unavailable even on a working A950 box (`npu-smi` is a separate driver-side package). A missing `npu-smi` does **not** mean there is no device. If detection returns null, set the target explicitly (`--npu-arch=dav-3510`) rather than concluding the hardware is absent.
