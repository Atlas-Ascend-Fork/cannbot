# Testing and Validation

The repository's testing style is strongly simulation-oriented. New work should follow the same pattern.

## 1. Main validation loop

A good kernel-development loop in this repository is:

1. write the exact PyTorch reference
2. run the kernel in simulator mode
3. compare against the reference
4. reduce the shape if debugging is needed
5. only after simulator parity, try generated artifacts

This order keeps the number of unknowns small.

## 2. Where tests live

Note: the `testcases/` directory is **no longer part of the delivered skill bundle**. Historical references below describe its previous layout for context only; the files are not shipped.

The main automated suite was previously under `testcases/`.

Its first split was by assertion type:

- `testcases/codegen/`
- `testcases/parser/`
- `testcases/simulator/`

It currently covers topics such as:

- parser behavior
- syntax transformation
- shape binding rules
- cube and vec simulation
- micro runtime behavior
- autosync and event metadata
- flags, barriers, atomics, and cross-core waits
- data movement helpers and layout conversions

## 3. What good runnable kernel files look like

Most kernel files under `agent/example/kernels/` include a `__main__` block that:

1. creates sample inputs
2. computes the PyTorch reference inline
3. calls `OpExec(..., simulator=True)`
4. checks closeness
5. prints a small error summary

That format is worth keeping because it makes each kernel file self-explanatory.

## 4. Tolerance guidance

Typical tolerance behavior in the current repository:

- float-heavy paths: tighter tolerances such as `1e-5`
- half or normalized paths: often around `1e-3`
- fp8 quantized outputs: much looser tolerances

Always match the tolerance to the real precision boundary in the formula. Do not copy one tolerance value blindly across kernels.

## 5. Shape-binding tests

The repository already tests shape-binding behavior in:

- `testcases/simulator/opexec/test_torchplugin_shape_bindings.py`

Use those tests as the reference for:

- strict ambiguity failures
- partial bindings that still leave unique dimensions inferable
- explicit mismatch errors

## 6. Synchronization validation

For synchronization-heavy kernels:

- validate the numerical result first
- if the behavior is still suspicious, run with `trace=...`
- compare the high-level pipeline in the trace with the intended producer/consumer flow

This is often faster than trying to reason about a long mixed kernel from the source alone.

## 7. Suggested checklist before considering a kernel done

- reference formula is written and reviewed
- simulator output matches reference
- tail tiles were exercised
- repeated scalar dimensions were checked for `shape_bindings`
- synchronization was verified for mixed kernels
- at least one focused regression test or runnable reproducer exists

## 8. When to add a new test file

Add or extend a test when:

- the behavior is not already covered by an existing kernel `__main__`
- the change touches parser or simulator semantics
- the bug was caused by synchronization, datamove, or shape inference behavior
- you are adding a new instruction family or lowering path

The historical `testcases/` directory (removed from the delivered bundle) already demonstrated the preferred granularity: small, focused, end-to-end where possible.
