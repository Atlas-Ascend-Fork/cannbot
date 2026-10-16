# API Reference

The detailed API reference now lives under [`doc/api/`](api/index.md).

Use this page as the entry point:

- [Detailed API Reference Index](api/index.md)

Recommended reading order:

1. [Decorators](api/decorators.md)
2. [Flow Control](api/flow_control.md)
3. [OpExec](api/op_exec.md)
4. [Shortcuts](api/shortcuts.md)
5. [Shared Scalar Helper Functions](api/scalars.md)
6. [Datatypes](api/datatype.md)
7. [Positions](api/position.md)
8. [Pipes](api/pipe.md)
9. [Var](api/var.md)
10. [Tensor and Buffer Types](api/tensor_buffer.md)
11. [Register and Mask Types](api/register.md)
12. [Synchronization](api/synchronize.md)
13. [Barriers](api/barrier.md)
14. [Atomic Context Managers](api/atomic.md)
15. [Miscellaneous Helpers](api/helpers.md)
16. choose one authoring surface:
   - [A2 Vector Math](api/a2_vec_math.md)
   - [A2 and Shared Vec Data Movement](api/vec_data_movement.md)
   - [A2 Vec Control and Access Helpers](api/a2_vec_control.md)
   - [A2 Vec Sort and Merge Helpers](api/vec_sort.md)
   - [A5 Micro Math](api/a5_micro_math.md)
   - [A5 Micro Data Movement](api/a5_micro_data_movement.md)
   - [A5 Micro Cast](api/a5_micro_cast.md)
   - [A5 Micro Compare and Select](api/a5_micro_compare_select.md)
   - [A5 Micro Mask Operations](api/a5_micro_mask_operations.md)
17. return to [Cube Data Movement and Compute](api/cube.md) when your kernel starts dealing with matmul staging, packed layout conversion, or `DualMode`

The detailed pages include, for each public API entry:

- what the function or object does
- parameter meanings
- important restrictions
- a minimal usage example
