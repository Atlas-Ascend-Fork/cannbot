# Architecture for Contributors

This document is for contributors who need to change the framework itself, not only author kernels on top of it.

## 1. Repository structure

The main repository areas are:

- `easyasc/`
  - public DSL surface
  - parser and lowering
  - simulator V2 runtime
  - instruction emitters and helpers
- `agent/example/kernels/`
  - curated kernel examples and runnable validation stories (restored on demand by `agent/scripts/init.sh`)
- `agent/scripts/`
  - standalone repository utilities and maintenance scripts
- `doc/`
  - English project and API documentation
- `doc_cn/`
  - Chinese mirror of the documentation set
- `agent/`
  - router-first guidance, catalogs, and implementation maps for repository work
- `agent/example/demo/`
  - manual runners or compile/integration demos grouped by device family

High-level owner files:

- `README.md`, `README_CN.md`
  - top-level project and documentation entry points
- `AGENTS.md`
  - repository-local working rules for agent-style contributors
- `agent/ROUTER.md`
  - router-first entry point: sends you to the smallest useful playbook or reference instead of loading every map up front
- `agent/references/repo-map.md`
  - quick top-level layout and ownership map
- `agent/references/code-paths.md`
  - fast implementation-path lookup
- `agent/references/simulator-v2.md`
  - focused simulator runtime and bridge map

Note: `testcases/` has been removed from the delivered skill bundle. References to it elsewhere in this document describe historical layout only.

## 2. Device family mapping

Before interpreting any hardware-specific branch, keep this mapping straight:

- `device_type == "950"` corresponds to the C310 path
- `device_type.startswith("b")` corresponds to the C220 path
- in `easyasc/resources/tensorutils.h`, `__DAV_C310__` is the `950` branch
- in `easyasc/resources/tensorutils.h`, `__DAV_C220_CUBE__` is the `b*` branch

Several support checks, helper choices, and generated code paths depend on this mapping.
Do not invert it when reading the repository.

## 3. End-to-end control flow

The typical internal path is:

1. a decorated Python function is transformed by `easyasc/pythonic.py`
2. `@kernel` wraps it in `KernelBase`
3. DSL objects emit `Instruction` records into the active kernel or micro context
4. `OpExec` binds runtime inputs and triggers either simulator or generation flow
5. the parser/lowering path or the V2 bridge path consumes those instructions
6. the simulator runtime or generated runtime executes the result
7. `shape_bindings` is used when repeated scalar values make shape inference ambiguous

Key entry modules:

- `easyasc/decorators.py`
- `easyasc/kernelbase/kernelbase.py`
- `easyasc/torchplugin.py`

## 4. Public surface modules

- `easyasc/a2.py`
- `easyasc/a5.py`
- `easyasc/flowcontrol.py`
- `easyasc/utils/Tensor.py`
- `easyasc/utils/var.py`

When changing the public API, start here and determine which surface the behavior belongs to: `a2`, `a5`, or both.
Do not assume every public-API change should land in both surfaces, because they target different architecture styles and instruction sequences.

## 5. Parser and lowering

The parser stack lives under `easyasc/parser/`.

Important roles:

- `asc.py`
  - instruction splitting
  - side classification
  - autosync insertion
  - translation dispatch
- `asc_pruning.py`
  - cleanup and pruning passes
- `asc_autosync.py`
  - event insertion for supported same-side pipe pairs
- `asc_handlers/`
  - per-op lowering handlers

If you add a new instruction family, expect to touch:

1. the stub emitter
2. handler registration or dispatch
3. possibly the simulator bridge/runtime
4. maybe autosync classification if the instruction belongs to a known pipe stage

## 6. Stub emitters

The authoring API mostly emits instructions through stubs under:

- `easyasc/stub_functions/`
- `easyasc/stub_functions/vec/`
- `easyasc/stub_functions/micro/`

These modules define the legal DSL authoring surface that kernels actually call.
They are the first place to inspect when a DSL statement does not behave the way you expected.

## 7. Simulator internals

The active simulator lives under `easyasc/simulator_v2/`.

The highest-value files are:

- bridge selection and simulator entry
  - `easyasc/kernelbase/kernelbase.py`
- runtime entry and configuration
  - `easyasc/simulator_v2/config.py`
  - `easyasc/simulator_v2/base.py`
  - `easyasc/simulator_v2/api.py`
- program bridges
  - `easyasc/simulator_v2/compat/kernel_bridge.py`
  - `easyasc/simulator_v2/compat/control_flow_bridge.py`
  - `easyasc/simulator_v2/compat/op_exec_adapter.py`
- runtime layers
  - `easyasc/simulator_v2/runtime/global_runtime.py`
  - `easyasc/simulator_v2/runtime/core_process.py`
  - `easyasc/simulator_v2/runtime/core_runtime.py`
  - `easyasc/simulator_v2/runtime/control_actor.py`
  - `easyasc/simulator_v2/runtime/pipe_worker.py`
- memory and workspace handling
  - `easyasc/simulator_v2/memory/`
- synchronization
  - `easyasc/simulator_v2/sync/`
- trace export
  - `easyasc/simulator_v2/trace/`

Important current fact:

- `KernelBase.run_sim()` always routes to `_run_sim_v2()`
- `simulator=True`, `simulator="v2"`, and `simulator="legacy"` currently all end up on this V2 path

## 8. Bridge model

The simulator does not execute the raw instruction list directly anymore.
It first builds a V2 `KernelProgram`.

Selection order in `KernelBase.build_simulator_v2_program()`:

1. explicit custom program builder
2. prebuilt `KernelProgram`
3. automatic bridge choice

Automatic bridge choice:

- `control_flow_bridge.py` for loops, conditionals, topology queries, `call_micro`, `VarList`, and mixed-lane control flow
- `kernel_bridge.py` for the narrower linear instruction subset

This bridge layer is often the first place to inspect when the simulator behaves differently from a kernel author's expectation.

## 9. Runtime shape

The V2 runtime uses:

- one parent `GlobalRuntime`
- one child `CoreProcess` per simulated core
- one `ControlActor` per active lane inside that core
- one threaded `PipeWorker` per logical pipe in that lane

Planning is resolved by:

- `easyasc/simulator_v2/runtime/execution_plan.py`
- `easyasc/simulator_v2/helpers.py`

Shared tensor storage is handled by:

- `easyasc/simulator_v2/memory/shared_tensor.py`
- `easyasc/simulator_v2/memory/shared_tensor_store.py`
- `easyasc/simulator_v2/memory/workspace.py`

## 10. Micro modules

`@vf` functions are wrapped by `easyasc/micro/micromodule.py`.

Important details:

- micro functions are cached as reusable modules
- temporary register declarations are hoisted into micro scope
- read and write sync keys are collected from the emitted micro instructions
- kernel calls to a micro emit `call_micro` instructions
- micro execution at runtime goes through `easyasc/simulator_v2/ops/micro/runtime.py`
- float `Var` expressions that flow through `call_micro` must keep float semantics in both
  `control_actor.py` and `ops/micro/runtime.py`; runtime-side int coercion will silently
  corrupt scalar scales used inside `@vf()`

Any change to micro dataflow should be checked against both parser lowering and V2 runtime behavior.

## 11. Testing and demos

Note: `testcases/` is no longer part of the delivered skill bundle. The regression-coverage responsibilities described below are historical context; the live sources are kernel self-checks and manual demo programs.

- historical `testcases/` tree (removed from the delivered repository) was organized as:
  - `codegen/` for static generation, tool, and non-runtime checks
  - `parser/` for split, pruning, autosync, and lowering-adjacent checks
  - `simulator/` for runtime semantics, roundtrips, bridge behavior, and V2 invariants
- `agent/example/kernels/` may carry runnable end-to-end self-check assertions for full kernel stories
- `agent/example/demo/` is for manual runners or compile/integration examples that should not run as part of default pytest coverage

If a root-level executable script becomes important, move it under `agent/example/demo/`.

## 12. Synchronization model

The current repository has two synchronization layers:

1. autosync
   - same-side pipeline handshakes inserted during lowering
2. explicit cross-side mutexes and wait/ready paths
   - used when ownership crosses between cube and vec

These changes are high-risk because they affect:

- parser lowering
- bridge behavior
- simulator scheduling
- trace output
- many existing tests

Keep changes small and validate them with focused tests.

## 13. Generated resources

The generation path still depends on template and helper files under:

- `easyasc/resources/`

If you change emitted code shape, check whether host/runtime templates or helper headers also need to change.

## 14. High-level maps and summaries

Use the smallest owner file that answers the question:

- router-first navigation across playbooks and references -> `agent/ROUTER.md`
- top-level layout or ownership -> `agent/references/repo-map.md`
- simulator implementation path -> `agent/references/simulator-v2.md`
- generic implementation-path lookup -> `agent/references/code-paths.md`
- kernel examples and kernel-specific notes -> `agent/references/examples/kernel-catalog.md`

## 15. Contribution checklist

When changing framework internals:

1. identify the authoring API impact
2. update lowering, bridge logic, and simulator runtime consistently
3. add or update a focused test
4. refresh the owner docs that actually describe the changed area
5. if a new kernel is added under `agent/example/kernels/`, update the kernel summaries too

This repository is easiest to maintain when parser, simulator, tests, documentation, and examples evolve together.
