# easyasc DSL — pointers to local docs and examples

This file is a **router**, not a guide. It maps "what you need" → "which file in this skill's `references/` to open." Read at most 2 of these per kernel. Do not preload everything.

All paths below are **local** to this skill (`skills/dsl-baseline-generation-easyasc/references/`). They were forked from upstream `${EASYASC_DSL_HOME}` (`ops-easyasc-dsl`) at v2 setup time — see the v2 mirror commit for the exact upstream snapshot. The upstream repo remains the **fallback authority** if anything here looks stale: paths there mirror the layout below under `${EASYASC_DSL_HOME}/doc/`, `${EASYASC_DSL_HOME}/agent/references/constraints/`, etc.

## Concept lookups (forked from upstream `doc/`)

| Need | Local path |
|---|---|
| Quickstart / repo orientation | `docs/01_quickstart.md` |
| Programming model (Tensor/Var/Position/DT) | `docs/02_programming_model.md` |
| First kernel walkthrough | `docs/03_write_your_first_kernel.md` |
| Mixed cube/vec pipeline + sync (relevant for CV/matmul via A2 cube primitives) | `docs/04_mixed_pipeline_and_sync.md` |
| Simulator behavior, traces, debug | `docs/05_simulator_and_trace.md` |
| Codegen + runtime overview (FYI; cake handles this in the next stage) | `docs/06_codegen_and_runtime.md` |
| Kernel topology patterns (online softmax, reduction-fused, etc.) | `docs/07_kernel_patterns.md` |
| Testing & validation conventions | `docs/08_testing_and_validation.md` |
| **API reference (single source of truth for DSL operators)** | `docs/09_api_reference.md` |
| Troubleshooting / common errors | `docs/10_troubleshooting.md` |
| Architecture overview (contributors) | `docs/11_architecture_for_contributors.md` |
| stub → codegen symbol name map | `docs/12_stub_to_codegen_name_map.md` |

Chinese mirror of these docs is NOT mirrored locally; if you need 中文, fall back to `${EASYASC_DSL_HOME}/doc_cn/<same-filename>.md`.

### API reference subfolder (`docs/api/`)

For the per-namespace API breakdown:

| Need | Local path |
|---|---|
| A2 vec math ops (add/sub/mul/div/exp/cadd/cmax/...) | `docs/api/a2_vec_math.md` |
| A2 vec control flow | `docs/api/a2_vec_control.md` |
| Vec data movement | `docs/api/vec_data_movement.md` |
| Cube primitives (matmul, mmad, Position.L1/L0C) — A2 also exposes these | `docs/api/cube.md` |
| Tensor / Buffer / DBuff | `docs/api/tensor_buffer.md` |
| Position enum (UB / L1 / L0C / ...) | `docs/api/position.md` |
| DT enum (float / half / bfloat16 / ...) | `docs/api/datatype.md` |
| Var scalars and Var arithmetic (CeilDiv/Min/Max/var_div) | `docs/api/var.md` |
| OpExec calling convention (shape_bindings etc.) | `docs/api/op_exec.md` |
| `@kernel` / `@vf` / `@func` decorators | `docs/api/decorators.md` |
| pipelines & barriers | `docs/api/pipe.md`, `docs/api/barrier.md`, `docs/api/synchronize.md` |
| A5-only micro APIs (`@vf` register kernels — last resort) | `docs/api/a5_micro_*.md` |

## Authoring playbook (when in doubt)

| Need | Local path |
|---|---|
| Canonical "write a kernel" walkthrough | `playbooks/kernel-authoring.md` |
| Debugging recipes | `playbooks/kernel-debugging.md` |
| Doc authoring style | `playbooks/doc-authoring.md` |
| Tool authoring (codegen scripts) | `playbooks/tool-authoring.md` |
| Clarify-first pattern | `playbooks/clarify-first.md` |

## Targeted constraints (when the kernel is non-trivial)

`constraints/` — focused topic files (forked from `agent/references/constraints/`):

- `tiling.md` — picking tile sizes, UB budget
- `tail-safety.md` — handling the last incomplete tile
- `online-softmax-tail.md` — online softmax with tail rows
- `reduction.md` — reduction APIs and accumulation order
- `precision.md` — float32 compute for bf16 / fp16 IO
- `mask.md` — masked vector ops
- `vec-stride.md` — non-contiguous vector layouts
- `datamove.md` — GM↔UB movement modes
- `autosync.md` — what `auto_sync()` actually inserts
- `vec-reduction-a2.md` — A2-specific reduction semantics
- `a2-device.md` — A2 device characteristics (UB sizes, vec core count, ...)
- `a2-vec-kernel.md` — A2 vec kernel conventions
- `counters.md` — `GetVecIdx`/`GetVecNum`/`GetCubeIdx`/`GetCubeNum` etc.

> Note: A5-only constraints (e.g. `a5-device.md`) are intentionally **not** mirrored — v2 defaults to A2. If you do venture into A5 for a specific feature, consult `${EASYASC_DSL_HOME}/agent/references/constraints/a5-device.md`.

Open one of these only when the playbook or primer tells you to.

## Example kernels

All 22 A2 examples are mirrored locally under `output_example/` — this includes the 6 hand-curated CAKE-flavored ones (with `# Pairs with input_example/...` headers indicating the matching functional PyTorch shape) plus the upstream A2 library (flash-attn variants, matmul, attention backward, sort, fp8 casts):

| Pattern | Local path |
|---|---|
| Elementwise (LeakyReLU) | `output_example/leaky_relu.py` |
| Reduction over a dim | `output_example/sum_reduction_over_a_dimension.py` |
| LayerNorm (Welford) | `output_example/layer_norm.py` |
| Softmax (online) | `output_example/softmax.py` |
| Cumsum | `output_example/cumsum.py` |
| **A2 cube matmul (canonical)** | `output_example/qk_matmul_batched.py` |
| **A2 grouped matmul (canonical, MoE / cross-group RR dispatch)** | `output_example/grouped_matmul.py` |
| Flash attention — prefill (long query) | `output_example/flash_attn_full.py` (+ `_causal` variants) |
| Flash attention — decode / incremental + MTP (tiny query, long KV; full online-softmax, in-kernel normalise) | `output_example/flash_attn_decode.py` |
| Flash attention — decode SPLIT-KV / flash-decoding (BH < #cores; 2-kernel partial→combine) | `output_example/flash_attn_decode_splitkv.py` |
| Flash attention — decode SOFTWARE-PIPELINED (QK[i]‖PV[i-1] overlap; perf variant, low-BH/long-KV niche) | `output_example/flash_attn_decode_pipelined.py` |
| Attention backward | `output_example/attn_backward_*.py` |
| Sort rows | `output_example/sort_rows.py` |
| FP8 cast | `output_example/to_hif8_torch.py` |

For exotic patterns not covered above, fall back to upstream `${EASYASC_DSL_HOME}/agent/example/kernels/a5/` and `${EASYASC_DSL_HOME}/agent/scripts/select_kernel_example.py` (the selector is a runnable script that scans the full upstream library by attribute).

## Reading discipline

1. Open `easyasc_dsl_primer.md` first (already in this skill's references — short).
2. Open at most 2 files from this pointer table.
3. Open exactly 1 close-match from `output_example/`.
4. If that combination is not enough, escalate to `playbooks/kernel-authoring.md`.
5. Stop reading once you can write the kernel. Do not read the entire `docs/` directory.
