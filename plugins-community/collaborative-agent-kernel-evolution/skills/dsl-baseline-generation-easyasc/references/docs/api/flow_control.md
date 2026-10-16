# Flow Control

This page documents the public flow-control helpers shared across the `easyasc` authoring surface.

These helpers are used to express:

- DSL loops
- authoring-time unrolling
- loop exits inside DSL loops
- DSL conditional branches

## 1. `range(*args, name="")`

- Purpose: Emit a DSL loop variable and corresponding loop instructions.
- Parameters:
  - `*args`: 1 to 3 positional values, matching Python `range`
  - `name`: optional loop-variable name override
- Restrictions:
  - accepted argument types are `int` and `Var`
  - `step` cannot be zero
  - this is not the built-in `range`; use it only inside kernel or micro authoring code
- Example:

```python
for m in range(0, M, 128, name="m"):
    ...
```

## 2. `unroll(*args)`

- Purpose: Return the built-in Python `range` for authoring-time expansion rather than DSL loop emission.
- Parameters:
  - `*args`: same meaning as Python `range`
- Restrictions:
  - unlike `range(...)`, this does not emit loop instructions
- Example:

```python
for i in unroll(4):
    regs[i] <<= 0
```

## 3. `break_()` and `continue_()`

- Purpose: Emit loop-exit instructions for the active DSL `range(...)` loop.
- Restrictions:
  - only valid inside kernel or micro code
  - intended for loops created by `easyasc.flowcontrol.range(...)`
  - native Python `break` / `continue` inside transformed DSL `range(...)` loops are rewritten to these helpers automatically
  - native Python `break` / `continue` inside `unroll(...)` loops are rejected during rewrite
- Example:

```python
for m in range(0, M, 128):
    if valid_m == 0:
        break
    if skip_tile:
        continue
```

This emits `break_loop` / `continue_loop` instructions rather than using Python's normal loop control.

## 4. `If(cond)`, `Elif(cond)`, `Else()`

- Purpose: Context managers that encode DSL control flow.
- Parameters:
  - `cond`: condition expression for `If` and `Elif`
- Restrictions:
  - only valid inside kernel or micro code
  - `Elif` and `Else` must directly follow an `If` or previous `Elif`
- Example:

```python
with If(valid_m > 0):
    z[:, :] <<= ub
with Else():
    inline("// no-op")
```

Native Python syntax:

- Inside functions processed by the framework's AST rewrite pass, you can also write normal Python `if` / `elif` / `else`.
- During decorated-function analysis, `easyasc.pythonic` rewrites those native branches into the DSL form based on `If(...)`, `Elif(...)`, and `Else()`.
- In practice, that means the following two styles are equivalent for kernel authoring:

```python
if valid_m > 0:
    z[:, :] <<= ub
else:
    inline("// no-op")
```

and:

```python
with If(valid_m > 0):
    z[:, :] <<= ub
with Else():
    inline("// no-op")
```

For side-effectful condition expressions that emit DSL instructions while being evaluated, native syntax is also supported. This includes patterns such as:

```python
if valid > 0:
    ...
elif GetSubBlockIdx() == 0:
    ...
else:
    ...
```

and:

```python
if valid > 0:
    ...
else:
    if GetSubBlockIdx() == 0:
        ...
```

The rewrite keeps `else: if ...` nested when it is written as a real nested branch, and `elif` conditions are evaluated lazily enough to preserve the required `If -> Elif` chaining in the emitted DSL instructions.

Notes:

- the rewrite applies when the function body is available to the framework's source-to-AST transformation
- `if` / `elif` / `else` is rewritten; this helper page is only documenting the explicit DSL surface that native syntax maps onto
