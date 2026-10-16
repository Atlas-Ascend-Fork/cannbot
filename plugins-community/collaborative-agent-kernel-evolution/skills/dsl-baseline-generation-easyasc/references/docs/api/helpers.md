# Miscellaneous Helpers

This page documents four small but important helper APIs:

- `sim_print`
- `dump_tensor`
- `inline`
- `clean_dcache`

They are grouped together because they are not data-movement primitives, not synchronization primitives, and not math primitives. They exist mainly for debugging, instrumentation, and backend escape hatches.

Availability summary:

- `inline`: exported by both `easyasc.a2` and `easyasc.a5`
- `clean_dcache`: exported by both `easyasc.a2` and `easyasc.a5`
- `sim_print`: exported by `easyasc.a5` only
- `dump_tensor`: exported by `easyasc.a5` only

These helpers also differ sharply between simulator mode and codegen mode, so that distinction is the first thing to keep in mind.

## 1. `sim_print(*args, pipe=Pipe.S)`

- Purpose: print simulator-side debug information associated with one pipe or with the main loop.
- Parameters:
  - `*args`: arbitrary payload items to print
  - `pipe`: `PipeType`, default `Pipe.S`
- Validation:
  - `pipe` must be a `PipeType`
- Instruction emission:
  - emits `Instruction("sim_print", payload=list(args), pipe=pipe)`

### What it does in simulator mode

When the simulator executes the instruction:

- payload items are resolved into printable runtime values where possible
- scalar DSL objects such as `Var` and `Expr` are resolved first
- the final message is built by joining all payload items with spaces

The log prefix depends on the execution side:

- cube:
  - `[cube][core=<core_idx>] ...`
  - if `pipe != Pipe.S`, an extra `[pipe=<pipe>]` segment is added
- vec:
  - `[vec][core=<core_idx>][subblock=<subblock_idx>] ...`
  - if `pipe != Pipe.S`, an extra `[pipe=<pipe>]` segment is added

So a call such as:

```python
sim_print("row_count", row_count, pipe=Pipe.V)
```

might produce a line conceptually like:

```text
[vec][core=0][subblock=1][pipe=V] row_count 32
```

### What it does in codegen mode

`sim_print` is intentionally simulator-only.

Its parser handler is a no-op:

- no backend C++ line is emitted
- no runtime print helper is generated

That means:

- `sim_print` is useful for local simulator debugging
- it should not be treated as part of the generated kernel's observable behavior

### Pipe semantics

`pipe` controls where the print is attached:

- `Pipe.S`:
  - print on the main loop side
  - useful for scalar state, control flow, and synchronization debugging
- non-`S` pipe:
  - print is attached to that pipe queue when possible
  - useful for seeing when a producer/consumer pipe actually reaches a point

Practical interpretation:

- `pipe=Pipe.S` is good for high-level debugging
- `pipe=Pipe.MTE2`, `Pipe.V`, `Pipe.M`, `Pipe.FIX`, and so on are better when you want pipe-local timing context

### What can be printed

The API accepts arbitrary Python objects, but the most useful payloads are:

- strings
- `int`, `float`, `bool`
- `Var` and `Expr`
- `PipeType`
- short tuples/lists of scalar-like values

Printing large tensors is not what `sim_print` is for. Use `dump_tensor` for that.

### Typical use cases

- inspect loop counters or inferred tile sizes
- confirm which pipe reaches a point first
- debug cross-side or event ordering
- inspect scalar values after a reduction or shape calculation

### Example: control-side debugging

```python
sim_print("tile", tile_idx, "valid_m", valid_m, pipe=Pipe.S)
```

Use this when the interesting information is mostly scalar and belongs to the scheduler/main-loop view of the kernel.

### Example: pipe-local debugging

```python
sim_print("issued gm_to_ub for tile", tile_idx, pipe=Pipe.MTE2)
sim_print("starting vec postprocess", tile_idx, pipe=Pipe.V)
```

This is useful when you want the simulator log to carry pipe identity explicitly.

## 2. `dump_tensor(tensor, filename, pipe)`

- Purpose: dump a runtime tensor view to disk during simulation.
- Parameters:
  - `tensor`: source `Tensor`
  - `filename`: output filename string
  - `pipe`: `PipeType`
- Validation:
  - `tensor` must be a `Tensor`
  - `filename` must be a `str`
  - `pipe` must be a `PipeType`
  - `pipe` cannot be `Pipe.ALL`
- Instruction emission:
  - emits `Instruction("dump_tensor", tensor=tensor, filename=filename, pipe=pipe)`

### What gets dumped

At execution time, the simulator:

- resolves the current runtime tensor view
- clones it
- writes it with `torch.save(...)`

So the file contains the resolved runtime tensor contents, not a symbolic DSL object.

Important implications:

- slicing, reinterpret views, transpose metadata, and current offsets have already been applied when the runtime view is built
- the dumped data corresponds to the tensor view visible at that exact program point
- later mutations do not change an already dumped file

### What it does in codegen mode

Like `sim_print`, `dump_tensor` is a no-op during code generation:

- the parser handler emits nothing
- no generated backend code is produced for it

So `dump_tensor` is a simulator debugging tool, not a generated-kernel feature.

### Pipe semantics

`pipe` determines where the dump instruction executes:

- `Pipe.S`:
  - the dump happens from the main loop
- non-`S` pipe:
  - the dump is dispatched into the matching pipe queue when supported

This matters if you are trying to capture a tensor at the moment a specific pipe reaches a point, rather than when the main loop reaches that point.

`Pipe.ALL` is rejected because a tensor dump is a single execution event, not a barrier-style all-pipe operation.

### Simulator behavior details

Both cube and vec simulators support two paths:

- main-loop path:
  - if `pipe == Pipe.S`, the simulator immediately resolves the runtime tensor and calls `torch.save`
- dispatched pipe path:
  - otherwise the instruction is queued on the target pipe
  - when the pipe executes it, it performs the same `torch.save(tensor.detach().clone(), filename)`

If the chosen pipe is unsupported on that simulator side, execution raises an error such as:

- `dump_tensor has unsupported pipe on cube simulator: ...`
- `dump_tensor has unsupported pipe on vec simulator: ...`

### Filename behavior

`filename` is used exactly as passed to `torch.save`.

Practical guidance:

- prefer explicit, unique names
- include tile or stage information in the name when dumping multiple states
- remember that repeated dumps to the same path overwrite the earlier file

### Typical use cases

- inspect intermediate UB data after vec math
- capture L1/UB handoff results around synchronization edges
- compare simulator state against a Python reference implementation
- debug layout-sensitive operations such as reinterpretation or packed transfers

### Example: dump a UB tensor after vec processing

```python
dump_tensor(ub_out, "ub_out_tile0.pt", Pipe.V)
```

Meaning:

- attach the dump to the `V` pipe
- when the `V` pipe executes that point, save the current runtime view of `ub_out`

### Example: dump from the main loop

```python
dump_tensor(ub_mid, "ub_mid_mainloop.pt", Pipe.S)
```

Use this when you want the dump aligned with control flow rather than a specific pipe queue.

## 3. `inline(code)`

- Purpose: inject raw backend code directly into the generated output.
- Parameters:
  - `code`: string containing one or more lines of backend code
- Validation:
  - `code` must be a `str`
  - `inline` is not allowed inside `@vf` context
- Instruction emission:
  - emits `Instruction("inline", code=code)`

`inline` is fundamentally different from `sim_print` and `dump_tensor`:

- it matters only in codegen mode
- the simulator ignores it

### What it does in codegen mode

The parser handler takes the string and emits it line by line into the generated backend output.

Behavior details:

- if `code == ""`, it emits a blank line
- otherwise each line from `code.splitlines()` is passed through directly
- no syntax checking is performed by the DSL layer

So `inline` is a true escape hatch: the framework inserts your text exactly where that instruction lands in the lowered stream.

### What it does in simulator mode

The cube and vec simulators both ignore `inline` completely:

- it does not affect runtime state
- it does not print anything
- it does not change scheduling

So never rely on `inline` for simulator-visible behavior.

### Why `@vf` rejects it

`inline` is blocked in `@vf` context because micro modules are expected to lower through the framework's structured micro API generation path, not by injecting arbitrary backend text from inside the micro DSL.

If you need a missing micro capability, the usual fix is:

- add a proper DSL helper and lowering path
- or inject `inline` from kernel scope only when there is no better structured alternative

### Where it is commonly used

- temporary backend experiments
- custom comments or markers in generated code
- bridging a backend feature that does not yet have a first-class DSL helper

The framework itself also uses `inline` internally for generated markers around auto-inserted declarations.

### Risks and limitations

- your string is backend-specific
- the DSL does not validate semantics
- the simulator cannot help you verify behavior
- injected code may become stale if the generated surrounding structure changes later

That is why `inline` should be a last resort rather than a normal authoring tool.

### Example: add a backend comment marker

```python
inline("// custom marker before manual backend fragment")
```

This is the safest style of use because it does not change runtime semantics.

### Example: multi-line injection

```python
inline(
    "int local_debug_value = 3;\n"
    "(void)local_debug_value;"
)
```

The handler will emit those two lines exactly into the generated output.

## 4. `clean_dcache(dst, entire_type=EntireType.single, dcci_dst=DcciDst.all, mode="all")`

- Purpose: emit an explicit backend data-cache clean-and-invalidate request for a GM tensor target.
- Parameters:
  - `dst`: destination `GMTensor`
  - `entire_type`: `EntireTypeValue`, default `EntireType.single`
  - `dcci_dst`: `DcciDstType`, default `DcciDst.all`
  - `mode`: `str`, default `"all"`, must be one of `"all"`, `"vec"`, or `"cube"`
- Validation:
  - `dst` must be a `GMTensor`
  - `entire_type` must be an `EntireTypeValue`
  - `dcci_dst` must be a `DcciDstType`
  - `mode` must be a `str`
  - `mode` must be one of `"all"`, `"vec"`, or `"cube"`
- Instruction emission:
  - emits `Instruction("clean_dcache", dst=dst, entire_type=entire_type, dcci_dst=dcci_dst, mode=mode)`

### What it does in codegen mode

The parser lowering emits a backend call in the form:

```text
DataCacheCleanAndInvalid<{dst_dtype}, AscendC::CacheLine::{entire_type}, AscendC::DcciDst::{dcci_dst}>({dst_expr});
```

For example:

```python
clean_dcache(global_out, EntireType.entire, DcciDst.atomic)
```

can lower conceptually to:

```text
DataCacheCleanAndInvalid<float, AscendC::CacheLine::ENTIRE_DATA_CACHE, AscendC::DcciDst::CACHELINE_ATOMIC>(global_out);
```

The dtype comes from `dst.dtype`, and the final argument is the lowered GM tensor expression for `dst`.

The `mode` parameter controls which split-side code receives the emitted backend call:

- `mode="all"`: emit on both cube and vec sides
- `mode="vec"`: emit on vec side only
- `mode="cube"`: emit on cube side only

### What it does in simulator mode

The simulator ignores `clean_dcache` completely:

- it does not mutate tensor payloads
- it does not change scheduling
- it does not simulate cache state

So `clean_dcache` is currently a codegen-only helper.

### Typical use cases

- bridge an exposed backend cache-maintenance primitive that the DSL needs to call explicitly
- choose cache-line scope with `EntireType.single` vs `EntireType.entire`
- choose destination policy with `DcciDst.all`, `DcciDst.ub`, `DcciDst.out`, or `DcciDst.atomic`

## 5. Choosing Between Them

Use `sim_print` when:

- you want lightweight simulator log output
- the thing you care about is mostly scalar or textual

Use `dump_tensor` when:

- you need the actual runtime tensor contents
- you want to inspect values offline with `torch.load`

Use `inline` when:

- you need a backend escape hatch during code generation
- the DSL does not already expose the operation you need

Use `clean_dcache` when:

- you need the generated kernel to emit an explicit cache clean/invalidate call
- you want that call to stay structured rather than handwritten through `inline`

## 6. Common Pitfalls

- Do not expect `sim_print` or `dump_tensor` to appear in generated backend code. Their handlers are no-ops in codegen.
- Do not expect `inline` to affect simulator behavior. The simulator explicitly ignores it.
- Do not expect `clean_dcache` to affect simulator results. It is intentionally skipped in simulation.
- Do not use `dump_tensor(..., pipe=Pipe.ALL)`. Dumps are single execution actions, not all-pipe barriers.
- Do not put `inline` inside `@vf`. The stub rejects it before instruction emission.
- Do not use `sim_print` for large tensor payloads. It is for small debug payloads; use `dump_tensor` for actual tensor data.
