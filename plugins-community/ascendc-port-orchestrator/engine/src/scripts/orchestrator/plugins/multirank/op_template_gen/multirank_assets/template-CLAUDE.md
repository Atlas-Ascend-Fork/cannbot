# CLAUDE.md — MC² operator project conventions

Claude Code auto-loads `cwd/CLAUDE.md` into every agent's context — this file is the convention entity. This directory is a multirank compute-communication fusion operator project (port_a3_to_a5 multirank extension; AscendC opc path: msopgen skeleton + multirank specialization patches). **Layout is NEST**: the msopgen C++ project lives under `prj-<op>/`; reference + this convention file stay at the op root.

## Quick start

All build / install / run **must** go through the fixed entry points below. **Never** hand-roll cmake / source set_env / copy .so (see "Agent constraints").

| op | command | notes |
|---|---|---|
| build + install + py_ext | `cd prj-<op>/ && python3 run.py build` | one command (wraps `multirank_build.py`): op_host three-stage (cust_op_proto / cust_optiling / cust_opapi) + kernel binary + install + py_ext build_ext. **Default warning filter** + **default clean** (wipes `.build`, recompiles) |
| verify (full campaign) | `python3 run.py verify` | every provisioned case, ws ascending; ONE multi-rank launch PER CASE (own HCCL init / golden file / rank logs under `.run/<case>/`); each case's idle cards are probed RIGHT BEFORE its launch and confirmed process-clean right after (npu_probe; wraps `multirank_runner.run_all_groups`). opp env (`ASCEND_CUSTOM_OPP_PATH` / `LD_LIBRARY_PATH` / `ASCEND_RT_VISIBLE_DEVICES`) injected by `multirank_runner._activate_opp_env` — do NOT set yourself |
| verify (run only) | `python3 run.py verify --run-only` | run kernel, **skip golden compare** (diagnostic: output shape/nan/mean) — confirm the kernel runs end-to-end (comm + compute, finite output) without measuring precision |
| provision golden | `python3 run.py provision` | harness truth-collection entry — the engine (O2.5) owns golden provisioning per the spec-declared truth tier (`a3_live`: source-side real operator, multi-rank); workers normally never run this. Products land under `golden/` + `model.py` + `ref_runnable.json`; each case's `world_size` comes from its own `spec.py` declaration |

### Typical dev loop (how to use the script)

`run.py` is the single entry — always run from `prj-<op>/`:

```bash
python3 run.py provision            # 1. gen golden (CPU sim → golden/<case>.pt)
python3 run.py build                # 2. compile + install + py_ext (default filter + clean)
python3 run.py verify --run-only    # 3. sanity: kernel runs end-to-end (no precision check)
python3 run.py verify               # 4. precision verify (compare golden; ALL-rank PASS = PASS)
```

Iterate: edit `op_kernel/<op>.{h,cpp}` → `run.py build` → `run.py verify`. Re-run `provision` only when `spec.py` or world_size changes.

## Options

All via `cd prj-<op>/ && python3 run.py <subcmd> [opts]`:

**build**: `-j N` (parallel jobs, default 8) | `--no-filter-warnings` (show raw output) | `--dump` (enable ASCENDC_DUMP debug prints; never for gate/perf). `.build` always wiped + rebuilt (no `--no-clean`).

**verify**: `--run-only` (run kernel, skip golden compare) | `--filter-ws N` (run ONLY the world_size=N group — declared groups only; verdict printed, verification.json intentionally untouched) | `--perf` (profiler device self-duration, warmup 5 + ACTIVE 10; candidate vs spec's perf_baseline if declared — perf stays N/A without perf_baseline; candidate and baseline run on SEPARATE HCCL groups) | `--op <name>` (default: ROOT dir name). Cards are always auto-probed per case — there is no manual lane flag

**provision**: `--op <name>` (default: ROOT dir name). world_size comes from each case's own `spec.py` declaration — never from a CLI flag.

> Three distinct roles: **provision (gen golden) → run.py build (compile) → run.py verify (launch+compare)**. verify requires a provisioned golden first (else the verifier fails loading the .pt) — use `verify --run-only` if you only need the kernel to run.

### Environment (do NOT set yourself)

Do NOT `source set_env.sh`, do NOT set `LD_LIBRARY_PATH` / `ASCEND_CUSTOM_OPP_PATH`:
- build time: `multirank_build._resolve_env` sources `cann/set_env.sh` internally (probes `ASCEND_CANN_PACKAGE_PATH` → `ASCEND_INSTALL_PATH` → `ASCEND_HOME_PATH` → `/usr/local/Ascend/cann-8.5.1`).
- run time: `multirank_runner._activate_opp_env` probes `prj-<op>/.install/packages/vendors/customize/op_api/lib` and injects opp env.

### Build artifacts (all under `prj-<op>/`)

| artifact | path |
|---|---|
| build dir | `prj-<op>/.build/` (wiped + rebuilt every build) |
| install tree (opp) | `prj-<op>/.install/packages/vendors/customize/` (`op_api/include` + `op_api/lib`) |
| kernel binary | `prj-<op>/.build/op_kernel/binary/<unit>/<op>/<Op>_<md5>.o` |
| py_ext ext | `prj-<op>/py_ext/_C*.so` (loaded by `model_new_ascendc.py` via `glob("prj-*/py_ext/_C*.so")`) |
| `.run` package | `prj-<op>/.install/custom_opp_*.run` |

### Build warning filter

`multirank_build` pipes compile stdout+stderr through the shared harness `filter_build_warnings.py` (**on by default** — not copied per-op): **path whitelist** — a warning passes through iff its file is under a keep root (default: the build cwd = `prj-<op>` under the standard `cd prj-<op>/ && python3 run.py build` entry; `--keep PATH` to override), so CANN / site-packages / catlass / autogen noise is filtered while project-source (`op_kernel/`, `op_host/`, `py_ext/`) warnings survive. Dedups by `(file,line,msg)`; **errors always pass through**; exit code = compile exit code (filter never masks a build failure). `run.py build --no-filter-warnings` disables for raw output.

## File layout

```
workspace/<op>/             root: reference + convention + meta
  CLAUDE.md                 this convention (entity, self-contained)
  model_new_ascendc.py      canonical (OL-160); loads prj-*/py_ext/_C*.so;
                            forward takes the spec input keys + ONE reserved
                            optional kwarg `group=None` — a torch ProcessGroup
                            object (the verifier passes the candidate's
                            isolated subgroup in perf/T2-competitor mode).
                            The wrapper resolves comm name + rank/size from
                            the group object op-side (py_ext.resolve_group);
                            the harness never passes backend comm names.
                            resolve_group is FAIL-LOUD (no fabricated
                            'hccl_world_group'/rank defaults): a standalone
                            __main__ smoke must init a single-rank HCCL group
                            first
  model.py / spec.py / golden/ / ref_runnable.json   reference (provision products; DO NOT modify model.py)
  (the multirank_verify.py verifier is harness-owned — multirank_runner runs it in place from the harness tree; it is never staged here)
  verification.json / knowledge_update.md / PROGRESS.md   meta
  prj-<op>/                 msopgen C++ project + build
    run.py                  unified entry: build | verify | provision (thin, calls harness)
    op_kernel/              kernel body (<op>.h / <op>.cpp / <op>_tiling.h) — edit ONLY here
    op_host/                OpDef + InferShape + TilingFunc + wrapper/aclnn_{op}.cpp
    py_ext/                 torch::Dispatcher pybind11 (ext_<op>.cpp / __init__.py / setup.py / pytorch_npu_helper.hpp)
    scripts/                rename_aclnn_autogen.py (msopgen opbuild; filter_build_warnings.py is harness-shared, not per-op)
    cmake/ + CMakeLists.txt + CMakePresets.json + build.sh + framework/   msopgen-generated, DO NOT modify
```

## Agent constraints (binding)

### Build / run
- **Must** build with `cd prj-<op>/ && python3 <project_root>/src/scripts/orchestrator/plugins/multirank/patches/multirank_build.py .` (default warning filter + default clean wipes `.build`; or equivalently `python3 run.py build`). **Never** bypass it to call `cmake` / `setup.py` / `ascendc_compile_kernel.py` / hand-install `.run`. multirank_build does op_host three-stage + kernel binary + install + py_ext in one command; its internal `cmake --target binary` is the only correct artifact path (hand `cmake --target binary` emits misnamed `_mix_aic_0.o`).
- **Must** launch verify via `multirank_runner.run(...)`. **Never** spawn `multirank_verify.py` yourself / `source set_env.sh` / set `LD_LIBRARY_PATH` / hand-copy `_C*.so` or `op_api` — opp env is injected by `multirank_runner._activate_opp_env`.
- Run multirank_build inside the **C++ project dir `prj-<op>/`** (arg `.`), not at the op root or project root.

### Structural conformance (port mode)
- The staged port source (`.source_arch22/`) IS the structural authority:
  preserve its algorithm, dataflow, block partition, pipelining, and
  in-kernel communication structure — whatever patterns the source uses.
  Code that carries over cleanly is carried; adaptation re-emits the SAME
  structure for arch35 hardware differences only (includes, core-type
  conditionals, instruction/API availability, sync primitives, the A5-side
  communication mapping per P-P110). UB / tiling / double-buffer /
  event_ids are worker-level (replaceable). Swapping the source's
  implementation route for a different A5 idiom requires explaining in
  the handoff BEFORE authoring — do NOT silently swap for a "more
  idiomatic" path.

### Source
- Edit ONLY these op-development files: `prj-<op>/op_kernel/<op>.{h,cpp}` (device compute) + `prj-<op>/op_host/<op>.cpp`, `prj-<op>/op_host/<op>_tiling.h`, `prj-<op>/op_host/wrapper/aclnn_<op>.cpp` (host: tiling + InferShape + aclnn wrapper) + `prj-<op>/py_ext/ext_<op>.cpp` (py_ext dispatcher) + root `model_new_ascendc.py` (Python wrapper). All are part of op development.
- **Never** edit the shared msopgen build framework: `cmake/*`, root `CMakeLists.txt`, `CMakePresets.json`. `op_kernel/CMakeLists.txt` + `op_host/CMakeLists.txt` ARE editable when an external framework / compile flag is needed (e.g. catlass include path, extra `-l`) — but PRESERVE the scaffold patches (`-Wall -Wextra --cce-auto-sync=off`, `.build` binaryDir, c++17); append your additions, do not overwrite.
- `op_kernel/CMakeLists.txt` must call `add_ops_compile_options(ALL OPTIONS ...)` **once**; append extra flags (catlass `-I`/`-D`) to `KERNEL_COMPILE_OPTIONS` instead — a second `add_ops_compile_options(ALL)` overwrites the first.
- Debug dump (`DumpTensor` / `ascendc_assert` prints): compiled **OFF by default** — the scaffold's `op_kernel/CMakeLists.txt` passes `-DASCENDC_DUMP=0` in the `else` branch (CANN's `kernel_macros.h` self-defines `ASCENDC_DUMP=1` when the macro is absent, so without the explicit `=0` prints stay ON). To enable dumps for local debugging, build with `python3 run.py build --dump` (passes `cmake -DASCENDC_DUMP=ON`, selecting the `if(ASCENDC_DUMP)` branch); the next plain `run.py build` reverts to dump-OFF. **Never use `--dump` for gate/perf runs** — dump prints perturb precision and add overhead; G1/G2/G3/perf verdicts must come from a dump-free build.

### Scratch scripts
- **Never** hand-roll bypass scripts under `.tmp/` or workspace (self set_env / copy .so / bare probe). Diagnostics go through harness entry points (multirank_build / multirank_runner); scratch probes are cleaned after use, never sediment into convention, never cross-session.
- **Never** fake a kernel with PyTorch/CANN delegation (calling `torch.*` / `aclnn*` to implement compute = cheating, see project-root CLAUDE.md CRITICAL). Honest FAIL > fake PASS.

### subagent
- Prefer a subagent for expensive compile / install / test, to keep build output out of the main context.
- subagent prompt: single task, no file edits, concise return.
