# rewrite_rules.md — token-level transforms applied by `transform.py`

Each rule is a `(file_glob, pattern, replacement)` triple. They are applied in
order; later rules see the output of earlier ones. The replacement parameters
`{Op}` (PascalCase) and `{snake}` (snake_case) are computed from `op_name`:

```python
snake = op_name                                     # "flash_attention"
Op    = "".join(w.capitalize() for w in snake.split("_"))  # "FlashAttention"
```

## Rule list (apply in this order)

| # | File (relative to dest `{Op}Custom/`)        | Find                                             | Replace with                                       |
|---|----------------------------------------------|--------------------------------------------------|----------------------------------------------------|
| 1 | `op_host/{snake}_custom_tiling.h`            | `BEGIN_TILING_DATA_DEF(KernelTilingData)`        | `BEGIN_TILING_DATA_DEF({Op}CustomTilingData)`      |
| 2 | `op_host/{snake}_custom_tiling.h`            | `REGISTER_TILING_DATA_CLASS(Kernel, KernelTilingData)` | `REGISTER_TILING_DATA_CLASS({Op}Custom, {Op}CustomTilingData)` |
| 3 | `op_host/{snake}_custom.cpp`                 | `#include "kernel_tiling.h"`                     | `#include "{snake}_custom_tiling.h"`               |
| 4 | `op_host/{snake}_custom.cpp`                 | `KernelTilingData tiling;`                       | `{Op}CustomTilingData tiling;`                     |
| 5 | `op_host/{snake}_custom.cpp`                 | `class Kernel : public OpDef`                    | `class {Op}Custom : public OpDef`                  |
| 6 | `op_host/{snake}_custom.cpp`                 | `explicit Kernel(const char* name)`              | `explicit {Op}Custom(const char* name)`            |
| 7 | `op_host/{snake}_custom.cpp`                 | `OP_ADD(Kernel);`                                | `OP_ADD({Op}Custom);`                              |
| 8 | `op_kernel/{snake}_custom.cpp`               | `void kernel(GM_ADDR`                            | `void {snake}_custom(GM_ADDR`                      |

Rule 8 is required: TBE's op-compilation pipeline derives the kernel entry-symbol
name from the op class (PascalCase → snake_case). easyasc names the entry
function `kernel`, so without rule 8 the kernel-binary build fails with
`Kernel Compilation Error: OpType {Op}Custom Kernel File {snake}_custom.cpp`.

## File rename map

These are not regex rewrites — they're filesystem renames done by `transform.py`
*before* the rules above are applied:

| From                              | To                                |
|-----------------------------------|-----------------------------------|
| `op_host/kernel.cpp`              | `op_host/{snake}_custom.cpp`      |
| `op_host/kernel_tiling.h`         | `op_host/{snake}_custom_tiling.h` |
| `op_kernel/kernel.cpp`            | `op_kernel/{snake}_custom.cpp`    |

Headers in `op_kernel/` (`kernel_cube.h`, `kernel_vec.h`, `tensorutils.h`) are
**not renamed** in strategy 1 (default). The `op_kernel/{snake}_custom.cpp`
still `#include "kernel_cube.h"` etc.; `add_kernels_compile()` in cake's CMake
is permissive about the file basename.

## Strategy 2 (`--inline-kernel`) — extra rules

If the user passes `--inline-kernel`, the transform additionally:

1. Reads `op_kernel/tensorutils.h`, `op_kernel/kernel_cube.h`, `op_kernel/kernel_vec.h`.
2. Strips their `#include` self-references and any `#pragma once`.
3. Strips from `op_kernel/{snake}_custom.cpp` the lines:
   ```
   #include "tensorutils.h"
   #include "kernel_cube.h"
   #include "kernel_vec.h"
   ```
4. Concatenates: `[remaining-cpp-includes]` + `tensorutils.h` body + `kernel_cube.h` body + `kernel_vec.h` body + `[rest of cpp]` into the final `op_kernel/{snake}_custom.cpp`.
5. Removes the original `tensorutils.h`, `kernel_cube.h`, `kernel_vec.h` files.

This strategy is only useful if a downstream tool (e.g. an automated diff or a
single-file extractor) requires single-file kernels. ascend-evaluation does not.

## Idempotency

Each rule's `find` string is uniquely written by easyasc and not present in the
post-transform output. Re-running `transform.py` on an already-transformed
`{Op}Custom/` is therefore a no-op for rules 1–7 (they won't match), but file
renames will fail because the source files no longer exist. `transform.py`
detects an already-transformed destination and refuses unless `--force` is set.

## Why these are the only rules we need

Empirically (see `migration_examples/flash_attention/`):

- `TilingFunc` body, attribute layout, `Input/Output/Attr` declarations, AICore
  config — all carried over verbatim. easyasc's `Input("q") / Output("out")`
  format matches what cake's flow accepts.
- `op_kernel/kernel.cpp` body — the `extern "C" __global__ __aicore__ void
  kernel(...)` symbol is consumed by aclnn dispatch under the registered op
  name. Renaming the C symbol is not required.
- CMakeLists.txt minor differences (TARGET_EXISTS guard, fallback_src
  expansion) — both build successfully under cake's CANN.

If a future easyasc release diverges further, extend this table — do not bake
new rules into `transform.py` without updating this file.
