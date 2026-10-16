# flash_attention migration — before/after

This is the worked example for the `flash_attention` op. The `before/` directory
captures easyasc's `flash_attention_raw/op_host/` exactly as `OpExec(simulator=False)`
emitted it; the `after/` directory captures the same files after running

```
python scripts/transform.py flash_attention --output-root output --force
```

## Concrete diff (op_host)

| File | Before                  | After                                     |
|------|-------------------------|-------------------------------------------|
| 1    | `kernel.cpp`            | `flash_attention_custom.cpp`              |
| 2    | `kernel_tiling.h`       | `flash_attention_custom_tiling.h`         |

### Token rewrites in (1) `kernel.cpp` → `flash_attention_custom.cpp`

```
- #include "kernel_tiling.h"
+ #include "flash_attention_custom_tiling.h"

- KernelTilingData tiling;
+ FlashAttentionCustomTilingData tiling;

- class Kernel : public OpDef {
+ class FlashAttentionCustom : public OpDef {

- explicit Kernel(const char* name) : OpDef(name)
+ explicit FlashAttentionCustom(const char* name) : OpDef(name)

- OP_ADD(Kernel);
+ OP_ADD(FlashAttentionCustom);
```

### Token rewrites in (2) `kernel_tiling.h` → `flash_attention_custom_tiling.h`

```
- BEGIN_TILING_DATA_DEF(KernelTilingData)
+ BEGIN_TILING_DATA_DEF(FlashAttentionCustomTilingData)

- REGISTER_TILING_DATA_CLASS(Kernel, KernelTilingData)
+ REGISTER_TILING_DATA_CLASS(FlashAttentionCustom, FlashAttentionCustomTilingData)
```

That's the entire op_host transform. Tiling body, attribute registration,
Input/Output declarations, AICore config — all carried over verbatim.

## op_kernel diff (strategy 1, default)

Only `kernel.cpp` is renamed to `flash_attention_custom.cpp`. The headers
`kernel_cube.h`, `kernel_vec.h`, `tensorutils.h` stay in place; the renamed
`.cpp` still `#include`s them by their original names. cake's
`add_kernels_compile()` globs the `.cpp` and the headers come along.

If you pass `--inline-kernel`, the three headers are stripped of `#pragma once`
and self-references, concatenated in order
(`tensorutils.h` → `kernel_cube.h` → `kernel_vec.h`) into the renamed `.cpp`,
and removed. The default does NOT inline because ascend-evaluation does not
require single-file kernels and inlining loses the cube/vec source-level
separation that's useful for code review.

## CMakeLists, build_out, scripts, framework, cmake/

Copied verbatim. easyasc's CMakeLists differs from cake's reference in two
trivial spots (`$<$<TARGET_EXISTS:...>>` vs bare expansion; `if (${fallback_src})`
vs `list(LENGTH ...)` length check) — both forms build successfully under cake's
CANN, so no rewrite is performed.
