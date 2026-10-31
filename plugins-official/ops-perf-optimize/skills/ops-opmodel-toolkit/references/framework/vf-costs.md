# VF 成本与可选预测接口

VF 成本可以来自实测、系数/公式或显式配置的外部预测器。
记录实现、shape/dtype、硬件、单位、来源及适用域；预测值不当作实测样本。

## 常量和公式

```yaml
- vec: {name: measured, cycles: {expr: measured_vf_cycles}, aiv_presplit: true}
- vec: {name: formula, cycles: {expr: rows * cols * vec_factor}}
```

这是两种独立写法，按实际操作选用。第一行假设成本已属于单 AIV；
第二行的 rows/cols 与分摊规则应符合当前模型的 workload。
`costs.yaml` 使用 `source/coefficients/native/vf/sensitivity`，系数说明单位和来源。
公共 VF 成本的 `model: affine` 使用用户声明的系数；未给成本不等于零成本。

## 外部预测输入

使用 VFmodel 时提供独立发行目录、绑定与运行环境。配置示例：

```yaml
root: /absolute/path/to/predictor-version
command: [python3, "{root}/predict.py", fast]
bindings: /absolute/path/project/work/vfmodel/bindings.yaml
work_dir: /absolute/path/project/work/.tmp/vfmodel
hardware_names: [ascend_950PR]
target: dav-c310-vec
prediction_mode: strict
timeout_seconds: 120
```

`work_dir` 位于预测器目录外，包含 `.tmp` 路径段，且不在系统 `/tmp` 下。
配置内路径相对配置文件解析；汇编/ELF 路径相对绑定文件解析。
每个绑定选择 assembly 或 elf，可附加 abi_assembly；文件、符号和 implementation
身份须与实际 VF 一致。数据影响控制流时使用真实输入或经确认的输入假设。
`workload` 的 scalar_registers、arguments、parameters、memory_regions 等按预测器接口填写。

在用户模型中启用：

```yaml
plugins:
  vfmodel: /absolute/path/project/work/vfmodel/config.local.yaml
```

原生 vec 的调用声明为：

```yaml
- vec:
    name: add
    vfmodel: add_u1
    vf_workload:
      elements: {expr: N}
    aiv_presplit: true
```

`cycles` 与 `vfmodel` 互斥。`aiv_presplit` 表示单 AIV 工作量；未预切分时提供该模型要求的
`vec_split_dim`。公共图成本可在 `costs.yaml:vf` 给出 `{model: vfmodel, binding: 绑定名}`。

## 输出和错误

预测周期口径为单 AIV 单次调用的 `rv_full_cycles`；核对时钟、target 和硬件匹配。
`strict` 接受合格的 `conditional_prediction`，显式 estimate 模式才接受相应估计结果。
`needs_input/unsupported/budget_exceeded/functional_only/error` 不作为有效性能值。
显式启用后失败不会自动改用零周期或另一成本来源。

结果中的预测身份、假设、缺口和 calibrated 状态随实验保留。
`prediction_rankable` 不表示已校准或可以直接推荐设备实现。
切换版本、绑定、实现或成本来源后，重新运行基线与候选；不混用旧结果。
关闭预测时先恢复合法 cycles/affine 声明，再移除配置。
