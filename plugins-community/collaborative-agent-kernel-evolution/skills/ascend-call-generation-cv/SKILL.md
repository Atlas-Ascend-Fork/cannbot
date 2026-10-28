---
name: ascend-call-generation-cv
disable-model-invocation: true
description: Generate AscendC CV project scaffold (workspace alloc, AIC+AIV dispatch, Catlass headers) from functional PyTorch for Cube+Vector fused operators (matmul+activation, norm+matmul+scale). Use after functional-conversion when operator_type is "cv".
---

## What I do

Generate Ascend operator invocation code and project JSON configuration for **Cube+Vector (CV) fused operators**, then create the initial AscendC project. CV operators differ from pure Vector operators in that they require workspace allocation, use AIC+AIV dispatch, and include Catlass headers.

## Prerequisite: env.json

Read `output/{op_name}/env.json` before selecting Catlass SoC targets and AIC/AIV dispatch counts. Use `soc_version`, `cube_core_cnt`, and `vector_core_cnt`; do not hardcode `Ascend910B2`, AIC=24, or AIV=48 when the fields are available.

## Workflow

1. Read input functional PyTorch code `output/{op_name}/{op_name}_functional.py`
2. Read reference examples by operator pattern:
   - For matmul + activation: `references/matmul_gelu/`
   - For norm + matmul + scale: `references/rms_matmul_scale/`
   - For int8 quantized matmul with dequant: `references/quant_matmul/`
   - For matmul + bias + activation: `references/matmul_bias_relu/`
   - For matmul + add (residual): `references/matmul_add/`
   - For matmul + GLU (SwiGLU/GeGLU): `references/matmul_swiglu/`
   - For matmul + add + normalization (multi-output): `references/matmul_add_rmsnorm/`
   - For FFN (dual matmul): `references/ffn_silu/`
   - For flash attention: `references/flash_attn_basic/`
3. Generate code and save files:
   - project JSON code for msopgen to create the custom AscendC operator project
   - pybind11 C++ binding code (workspace is framework-managed, NOT allocated in pybind)
   - Python code to call the custom AscendC operator
4. Save all files in `output/{op_name}/` directory
5. Create AscendC project (run gen_project_cv.py)
6. Continue to the next step in agent workflow

### Generation Task

Construct operator name as `{op_name}_custom` and convert to PascalCase for operator definition.

#### 1. project_json code

JSON schema defining the custom AscendC operator:
- **inputs**: ND tensors mapping to [module_fn] tensor arguments
- **outputs**: ND tensors mapping to [module_fn] return values
- **attributes**: scalar/config parameters from [module_fn]

**CV-Specific Notes**:
- **⚠️ Workspace is NOT listed as an input/output in project.json**. It is allocated implicitly by the framework via tiling's `GetWorkspaceSizes`. Never add workspace to the JSON schema.
- Input/output data types for CV operators are typically `float16` (half precision), since cube units work with fp16.
- Output tensor shape must match the fused operation's final output shape.
- The `attr` array should only contain attributes that appear in [module_fn] signature. For pure matmul with no extra parameters, `attr` is empty.

**Fixpipe (Cube-Only) Note**:
When the Vector scope only performs fp32→fp16 cast (no GELU, normalization, or other operations), the operator uses fixpipe mode and does **not** need workspace at all:
- The tiling function does NOT call `GetWorkspaceSizes`
- The pybind code remains unchanged (it never passes workspace regardless)
- Input/output data types stay `float16` as usual

Save json code in `{op_name}_project.json`

#### 2. python_bind code

C++ pybind11 code connecting AscendC operator to PyTorch:
- Include headers: `torch/library.h`, `pytorch_npu_helper.hpp`
- Implement `*_impl_npu` function calling `EXEC_NPU_CMD`
- Register with `TORCH_LIBRARY_IMPL`
- Export via `PYBIND11_MODULE`

**CV-Specific Requirements**:
- **⚠️ CRITICAL: Workspace is NOT allocated in pybind code**. Workspace is managed entirely by the framework through the tiling function's `GetWorkspaceSizes()`. Do NOT allocate workspace in the impl function or pass it to `EXEC_NPU_CMD`. Only pass input tensors and output tensors.
  ```cpp
  // WRONG — Do NOT do this:
  // at::Tensor workspace = at::empty({...}, input.options().dtype(at::kFloat));
  // EXEC_NPU_CMD(aclnnOpCustom, input, weight, output, workspace);

  // CORRECT — Only pass inputs and outputs:
  at::Tensor result = at::empty({M, N}, a.options());
  EXEC_NPU_CMD(aclnnMatmulCustom, a, b, result);
  ```
  The workspace (e.g., M*N floats for fp32 matmul accumulation) is allocated by the framework based on `context->GetWorkspaceSizes()` in the host-side tiling function. The kernel receives it as a `GM_ADDR workspace` parameter automatically.
- Output tensor shape is derived from the fused operation (e.g., for matmul: `[M, N]` from `[M,K] @ [K,N]`; for matmul+gelu: same `[M, N]`).
- Use `a.options()` to propagate dtype/device from input to output tensor.

**Mixed-Type Operators (e.g., int8 input → fp16 output)**:
- When input and output dtypes differ, do NOT use `a.options()` to create output tensors — it inherits the input dtype (e.g., int8).
- Instead, use explicit TensorOptions: `at::TensorOptions().dtype(at::kHalf).device(a.device())`
- project.json `type` must match the actual dtype (use `"int8"` for int8 inputs, `"float16"` for fp16 outputs).
- When B is stored as [N, K] (transposed weight), use `N = b.size(0)` (not `b.size(1)`).
- See `references/quant_matmul/` for a complete int8 quantized matmul example.

Save C code in `{op_name}.cpp`

#### 3. model code

`ModelNew(nn.Module)` class that:
- Replicates original `Model` functionality
- Calls custom AscendC operator via `custom_ops_lib.{op_name}_custom`
- Maintains same `__init__` and `forward` signatures
- Imports: `torch`, `torch.nn`, `torch_npu`, `custom_ops_lib`

**Note**: Weight initialization in `ModelNew` must exactly match `Model` (same seed, same tensor creation).

Save python code in `{op_name}_custom.py`

### Create AscendC Project

Use `gen_project_cv.py` to create the AscendC project with Catlass support.

**⚠️ CRITICAL: 必须使用 `--output-dir` 指定输出目录为 `output/{op_name}`**，否则项目会生成到 `output/` 根目录下，需要手动搬移。

```shell
python3 ${CLAUDE_SKILL_DIR}/scripts/gen_project_cv.py <op_name> <json_file_path> --output-dir output/<op_name>
```

Example:
```shell
python3 ${CLAUDE_SKILL_DIR}/scripts/gen_project_cv.py MatmulGelu output/MatmulGelu/MatmulGelu_project.json --output-dir output/MatmulGelu
```

This generates the project at `output/{op_name}/{OpNameCustom}/` and additionally:
- Adds Catlass include paths to CMakeLists.txt
- Generates kernel template with `ASCEND_IS_AIC` / `ASCEND_IS_AIV` dispatch structure

Check if the project was generated successfully. If not, analyze the error and retry.

### Extended Pattern Support

#### Multi-Input Operators

For operators with 3+ input tensors (e.g., FFN with X, W1, W2; Flash Attention with Q, K, V):

**project.json**: List all input tensors in `inputs` array. Each gets its own ND tensor entry.
```json
{
  "inputs": [
    {"name": "q", "dtype": "float16", "format": "ND"},
    {"name": "k", "dtype": "float16", "format": "ND"},
    {"name": "v", "dtype": "float16", "format": "ND"}
  ]
}
```

**pybind**: Pass all input tensors to `EXEC_NPU_CMD` in same order as project.json.
```cpp
at::Tensor result = at::empty({M, D}, q.options());
EXEC_NPU_CMD(aclnnFlashAttnCustom, q, k, v, result);
```

#### Optional Input (Bias)

When bias is optional (may or may not be present in [module_fn]):

**project.json**: Include bias as a regular input. The pybind code handles the optional logic.

**pybind**: Check if bias is provided, create zero tensor if not:
```cpp
void op_impl_npu(const at::Tensor& a, const at::Tensor& b,
                 const c10::optional<at::Tensor>& bias, at::Tensor& result) {
    at::Tensor bias_tensor = bias.has_value() ? bias.value()
        : at::zeros({b.size(1)}, a.options());
    EXEC_NPU_CMD(aclnnOpCustom, a, b, bias_tensor, result);
}
```

#### Multi-Output Operators

For operators that return multiple tensors (e.g., MatMul + Add + RmsNorm returning both normalized output and pre-norm sum):

**project.json**: List all output tensors in `outputs` array:
```json
{
  "outputs": [
    {"name": "y", "dtype": "float16", "format": "ND"},
    {"name": "x_add", "dtype": "float16", "format": "ND"}
  ]
}
```

**pybind**: Allocate and return all output tensors:
```cpp
at::Tensor y = at::empty({M, N}, x.options());
at::Tensor x_add = at::empty({M, N}, x.options());
EXEC_NPU_CMD(aclnnOpCustom, x, weight, residual, gamma, y, x_add);
return std::make_tuple(y, x_add);
```

**model code**: Unpack multiple returns:
```python
def forward(self, x, residual):
    y, x_add = custom_ops_lib.op_custom(x, self.weight, residual, self.gamma)
    return y, x_add
```

#### Attribute Types

Beyond simple `float` (eps), CV operators may need:

| Attribute Type | Example | project.json |
|---|---|---|
| `float` | eps=1e-6 | `{"name": "eps", "type": "float", "defaultValue": "1e-6"}` |
| `int` | num_heads=32 | `{"name": "num_heads", "type": "int"}` |
| `int` | head_dim=128 | `{"name": "head_dim", "type": "int"}` |
| `string` | activation_type="silu" | `{"name": "activation_type", "type": "string"}` |

#### FFN / Multi-MatMul Workspace

For FFN-type operators with multiple matmul stages:
- Workspace is still **NOT** listed in project.json (framework-managed)
- Workspace allocation happens in tiling function, not pybind
- Multiple workspace segments are allocated as one contiguous block
- Tiling function computes: `ws_total = ws1_size + ws2_size + ws3_size + sysWorkspaceSize`
