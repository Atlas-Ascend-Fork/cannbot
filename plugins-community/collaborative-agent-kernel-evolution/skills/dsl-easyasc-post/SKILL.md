---
name: dsl-easyasc-post
disable-model-invocation: true
description: Post-process easyasc's native AscendC codegen output (op_host/, op_kernel/, build_out/) into cake's expected `output/{op}/{Op}Custom/` layout so ascend-evaluation can consume it. Reads codegen_status.json from dsl-easyasc-codegen; refuses to run on a5 path or when ascendc_generated=false.
---

# dsl-easyasc-post

Companion to `dsl-easyasc-codegen`. After easyasc has emitted AscendC sources
under `output/<op>/easyasc_workspace/<op>_raw/`, this skill rewrites the tree
into cake's expected `output/<op>/<Op>Custom/` layout and rebuilds the .run
package so `ascend-evaluation` can consume it.

```
output/<op>/easyasc_workspace/<op>_raw/         output/<op>/<Op>Custom/
├── op_host/                                    ├── op_host/
│   ├── kernel.cpp                  ────────►   │   ├── <op>_custom.cpp
│   └── kernel_tiling.h             ────────►   │   └── <op>_custom_tiling.h
├── op_kernel/                                  ├── op_kernel/
│   ├── kernel.cpp                  ────────►   │   ├── <op>_custom.cpp
│   ├── kernel_cube.h, kernel_vec.h, ...        │   ├── kernel_cube.h, ...   (kept)
│   └── tensorutils.h                           │   └── tensorutils.h
└── build_out/custom_opp_*.run     (rebuilt) →  └── build_out/custom_opp_*.run
```

The rewrite is rule-based and idempotent. The full mapping is in
`references/layout_mapping.md`; the token rules are in `references/rewrite_rules.md`;
a worked example is in `references/migration_examples/flash_attention/`.

## Preconditions

This skill **only** runs when:
- `codegen_status.json.target_device == "a2"` (a5 path is simulator-only — no AscendC to post-process)
- `codegen_status.json.ascendc_generated == true`
- `codegen_status.json.raw_dir` points at a populated `<op>_raw/` tree

If `target_device == "a5"`, the skill exits immediately and tells the user
ascend-evaluation cannot consume this op on the current host.

## Workflow (script-first)

### Step 1 — pre-check

```bash
python ${CLAUDE_SKILL_DIR}/scripts/diff_layout.py <op_name> --mode pre
```

Validates target_device, next_step, raw_dir, and required source files. Refuses
on a5. Exit code `0` → continue. Exit code `2` from a5 refusal → tell the user
to use the simulator validation results from `dsl-easyasc-codegen` and stop.

### Step 2 — transform

```bash
python ${CLAUDE_SKILL_DIR}/scripts/transform.py <op_name> [--force] [--inline-kernel]
```

Copies `<op>_raw/` to `<Op>Custom/`, renames the three kernel sources, and
applies the 8 token rewrites listed in `references/rewrite_rules.md` (op-class
name, tiling-data class, kernel entry symbol). `--force` overwrites any
existing destination. `--inline-kernel` collapses the cube/vec headers into a
single `.cpp` (uncommon; default keeps the split).

**In the standard cake integration flow, `--force` is mandatory**, because
`ascend-call-generation` (which runs before this skill) already creates
`output/{op}/{Op}Custom/`. Without `--force`, transform.py will refuse to
overwrite the existing directory. Always pass `--force` when invoking this
skill from the cake pipeline.

On success: updates `codegen_status.json.next_step = "rebuild"` and writes
`post.dst_dir` and `post.op_class`.

> **transform.py 自动处理项**（无需手动干预）：
> - 文件名重命名：`kernel.cpp` → `{snake}_custom.cpp`、`kernel_tiling.h` → `{snake}_custom_tiling.h`
> - 8 条 token 重写规则：`class Kernel` → `class {Op}Custom`、`KernelTilingData` → `{Op}CustomTilingData` 等
> - **Step A**：snake_case 内核入口修正 — 若 easyasc 生成的 `extern "C"` 函数名不是
>   `{snake}_custom`（如驼峰形式 `BatchNorm_custom`），自动替换为 `{snake}_custom`
> - **Step B**：vec-only 算子 PipeBarrier 清除 — 若 `kernel_cube.h` 无实质 Cube 操作
>   （BlockMmad/Mmad），自动移除 `PipeBarrier<PIPE_ALL>()` 防止 AIV 死锁

> **需手动确认项**（transform 完成后、rebuild 前检查一遍）：
> 1. `op_kernel/{snake}_custom.cpp` 的 `extern "C"` 函数名确实是 `{snake}_custom`
>    （若 Step A 已处理则直接跳过）
> 2. 若算子支持 fp16/bfloat16，`{op}_project.json` 的 `"type"` 数组包含所有 dtype
> 3. ACLNN 参数顺序：查阅 `build_out/autogen/aclnn_{snake}_custom.h` 的
>    `GetWorkspaceSize` 签名，确认 `out` 参数位置（通常在 int scalar 参数之后）；
>    据此更新 PyBind `{op}.cpp` 中 `EXEC_NPU_CMD` 的传参顺序

### Step 3 — rebuild the .run package

```bash
bash ${CLAUDE_SKILL_DIR}/scripts/rebuild_if_modified.sh <op_name>
```

Runs `bash <Op>Custom/build.sh` to produce the new `.run`. The .run from the
codegen step is **always stale** because the op-class symbol was just renamed,
so this step is mandatory unless `--skip-rebuild` is passed (only useful for
dry-runs that won't be evaluated).

On success: updates `codegen_status.json.post.run_package` and sets
`next_step = "verify"`. On failure: sets `next_step = "human-intervention"`
and surfaces `<Op>Custom/build.log`.

### Step 4 — verify

```bash
python ${CLAUDE_SKILL_DIR}/scripts/verify.py <op_name>
```

Final guard:
1. `<Op>Custom/build_out/custom_opp_*.run` exists.
2. `libcust_opapi*.so` exists and exports a symbol containing
   `aclnn{Op}Custom` (PascalCase) or the snake-case kernel entry.
3. `aclnn_<op>_custom.h` was emitted (warning only — aclnn dispatch can work
   without it).
4. `diff_layout.py --mode post` reports no leaked `Kernel` / `KernelTilingData`
   tokens in the rewritten files.

On success: `next_step = "ascend-evaluation"`. On failure:
`next_step = "human-intervention"`.

### Step 5 — hand off

After Step 4, the op is ready for `ascendc-evaluation`. Note that
ascend-evaluation also expects the existing cake artifacts in `output/<op>/`:

- `<op>_reference.py`
- `<op>_custom.py` (with `ModelNew`)
- `<op>.cpp` (PyBind)
- `test_cases.py`

These come from existing cake skills (`functional-conversion`,
`reference-generation`, `ascend-call-generation`, `ascendc-evaluation`'s own
test_cases.py exemplars), NOT from this skill. Tell the user "post complete;
run ascendc-evaluation next" and report `<Op>Custom/` and the .run path.

## Reference index

- `references/layout_mapping.md` — source-to-destination file map and naming conventions
- `references/rewrite_rules.md` — the 8 token-level rewrites (with file globs)
- `references/migration_examples/flash_attention/` — a fully worked before/after

## Hard contracts (do not break)

1. **Skill is a no-op on a5.** Never attempt to rewrite or rebuild for the a5 path.
2. **Status file is the only handoff channel.** Read `codegen_status.json` before
   Step 1; update it after each successful step.
3. **Rebuild is mandatory.** The op-class symbol is renamed during transform, so
   the codegen-step .run is stale. Skipping rebuild produces an opp package that
   ascend-evaluation cannot dispatch.
4. **`<Op>Custom/` must contain everything ascend-evaluation needs.** Don't strip
   `framework/`, `cmake/`, or `scripts/` from the copy — they're consumed by
   `build.sh` and the install layout.
5. **Don't touch `op_host/CMakeLists.txt`.** Trivial easyasc-vs-cake differences
   exist but both forms build successfully under cake's CANN. Modifying CMake is
   out of scope.
