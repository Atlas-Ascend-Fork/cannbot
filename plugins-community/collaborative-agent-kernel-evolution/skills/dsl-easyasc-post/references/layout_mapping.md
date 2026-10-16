# layout_mapping.md — easyasc raw → cake `{Op}Custom/`

This is the concrete mapping the post skill must apply. All paths are relative to
the workspace and the destination `output/{op_name}/`.

```
SOURCE (easyasc raw)                          → DESTINATION (cake {Op}Custom)
output/{op}/easyasc_workspace/{op}_raw/        output/{op}/{Op}Custom/
├── CMakeLists.txt                              ├── CMakeLists.txt        (copy as-is)
├── CMakePresets.json                           ├── CMakePresets.json     (copy as-is)
├── build.sh                                    ├── build.sh              (copy as-is)
├── cmake/                                      ├── cmake/                (copy recursive)
├── framework/                                  ├── framework/            (copy recursive)
├── scripts/                                    ├── scripts/              (copy recursive)
├── op_host/
│   ├── CMakeLists.txt                          │   ├── CMakeLists.txt    (copy; tiny diff*)
│   ├── kernel.cpp                              │   ├── {snake}_custom.cpp  (RENAME + REWRITE)
│   └── kernel_tiling.h                         │   └── {snake}_custom_tiling.h  (RENAME + REWRITE)
├── op_kernel/
│   ├── CMakeLists.txt                          │   ├── CMakeLists.txt    (copy as-is)
│   ├── kernel.cpp                              │   └── {snake}_custom.cpp  (RENAME + REWRITE include lines)
│   ├── kernel_cube.h                           │       (inlined or kept; see "kernel split" below)
│   ├── kernel_vec.h                            │
│   └── tensorutils.h                           │       tensorutils.h kept as-is, just relocated
└── build_out/                                  └── build_out/            (copy: contains .run)
    └── custom_opp_*.run                            └── custom_opp_*.run
```

## Naming conventions

For a user-facing op named `flash_attention`:

| Token | Value |
|-------|-------|
| `{op}`             | `flash_attention`        (snake_case, as in workspace dirname) |
| `{snake}`          | `flash_attention`        (alias of `{op}`) |
| `{Op}`             | `FlashAttention`         (PascalCase: split on `_`, capitalize each word) |
| `{OpCustom}`       | `FlashAttentionCustom`   (`{Op}` + `Custom`) |
| Op class in cpp    | `FlashAttentionCustom`   (in `namespace ops { class ... : public OpDef }`) |
| TilingData class   | `FlashAttentionCustomTilingData` |
| `OP_ADD(...)`      | `OP_ADD(FlashAttentionCustom)` |

easyasc emits all of these as the literal token `Kernel` / `KernelTilingData` /
`OP_ADD(Kernel)`. The transform must replace those tokens.

## Kernel split (`op_kernel/`)

easyasc emits **four files** under `op_kernel/`:
- `kernel.cpp`      — entry point (`extern "C" __global__ __aicore__ void kernel(...)`)
- `kernel_cube.h`   — cube path (`kernel_cube(...)`)
- `kernel_vec.h`    — vec path (`kernel_vec(...)`)
- `tensorutils.h`   — shared helpers

cake's existing flow uses **a single `{snake}_custom.cpp`**. Two strategies are
acceptable for post:

1. **Keep the split** (recommended; minimal rewrite):
   - rename `kernel.cpp` → `{snake}_custom.cpp`
   - leave `kernel_cube.h`, `kernel_vec.h`, `tensorutils.h` in place (they're
     `#include`d locally; cake's `op_kernel/CMakeLists.txt` uses
     `add_kernels_compile()` which globs the `.cpp`, so headers come along).
   - **Rewrite the kernel entry-point symbol** from `void kernel(GM_ADDR` to
     `void {snake}_custom(GM_ADDR`. TBE's op-compilation pipeline derives the
     expected kernel symbol name from the op class; without this rename the
     kernel build fails with `Kernel Compilation Error: OpType {Op}Custom`.
     This is rule 8 in `rewrite_rules.md` and is **always applied** (not
     conditional on `verify.py`).

2. **Inline into one file** (heavier; only do this if the user explicitly asks):
   - concat `tensorutils.h` + `kernel_cube.h` + `kernel_vec.h` + `kernel.cpp`
     contents (in that order), strip the `#include "kernel_*.h"` lines, write
     to `{snake}_custom.cpp`.

`transform.py` defaults to strategy 1. Strategy 2 is gated behind `--inline-kernel`.

## File-content rewrites

### `op_host/{snake}_custom.cpp` (was `kernel.cpp`)

| Line                                              | Rewrite to |
|---------------------------------------------------|------------|
| `#include "kernel_tiling.h"`                      | `#include "{snake}_custom_tiling.h"` |
| `class Kernel : public OpDef`                     | `class {Op}Custom : public OpDef` |
| `explicit Kernel(const char* name)`               | `explicit {Op}Custom(const char* name)` |
| `KernelTilingData tiling;`                        | `{Op}CustomTilingData tiling;` |
| `OP_ADD(Kernel);`                                 | `OP_ADD({Op}Custom);` |

Everything else (TilingFunc body, attribute parsing, AICore config) is kept verbatim.

### `op_host/{snake}_custom_tiling.h` (was `kernel_tiling.h`)

| Line                                              | Rewrite to |
|---------------------------------------------------|------------|
| `BEGIN_TILING_DATA_DEF(KernelTilingData)`         | `BEGIN_TILING_DATA_DEF({Op}CustomTilingData)` |
| `REGISTER_TILING_DATA_CLASS(Kernel, KernelTilingData)` | `REGISTER_TILING_DATA_CLASS({Op}Custom, {Op}CustomTilingData)` |

### `op_kernel/{snake}_custom.cpp` (was `kernel.cpp`)

Strategy 1: rename the entry-point function symbol from `kernel` to `{snake}_custom`
(TBE requires the symbol name to match the op class — see rule 8 in
`rewrite_rules.md`). The cube/vec helper headers remain included by their
original names. Only the *filename* and the entry-point symbol change.

Strategy 2 (inline, opt-in): concatenate as described above and drop the
`#include "kernel_cube.h"` / `#include "kernel_vec.h"` lines.

### `op_host/CMakeLists.txt` (tiny diff*)

easyasc and cake CMakeLists are nearly identical but easyasc uses the older form

```cmake
add_library(cust_op_proto SHARED
    $<$<TARGET_EXISTS:group_proto_src>:${group_proto_src}>
    ${ops_srcs}
    ${ASCEND_AUTOGEN_PATH}/op_proto.cc
)
```

vs cake's

```cmake
add_library(cust_op_proto SHARED
    ${group_proto_src}
    ${ops_srcs}
    ${ASCEND_AUTOGEN_PATH}/op_proto.cc
)
```

and easyasc's

```cmake
if (${fallback_src})
    target_sources(cust_optiling PRIVATE ${fallback_src})
endif()
```

vs cake's

```cmake
list(LENGTH fallback_src fallback_src_len)
if (fallback_src_len GREATER 0)
    target_sources(cust_optiling PRIVATE ${fallback_src})
endif()
```

**Both forms build successfully** under cake's CANN toolchain (we verified the
easyasc form built end-to-end). Therefore: **do not touch `op_host/CMakeLists.txt`**
unless a downstream build error specifically points at one of these patterns.
Treat as copy-as-is.

## Optional: catlass include path

cake's reference op_kernel/CMakeLists.txt adds a CATLASS include path for
CV-fused operators. easyasc does **not** need catlass — it generates the cube
class directly. Therefore the post step does **not** add the catlass include
line; if the kernel uses catlass, the user must have added it manually in the
kernel module (which they wouldn't, since easyasc's kernel.cpp uses
`AscendC::Matmul<...>` from `lib/matmul_intf.h`, not catlass).

## What post does NOT produce

The cake `{op_name}/` parent directory also expects, for ascend-evaluation:
- `{op_name}_reference.py`
- `{op_name}_custom.py` (with `ModelNew`)
- `{op_name}.cpp` (PyBind)
- `test_cases.py`

These are produced by **existing cake skills** (functional-conversion,
reference-generation, ascend-call-generation, ascendc-evaluation), NOT by
dsl-easyasc-post. Post produces only `{Op}Custom/`.
