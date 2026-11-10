# 黑盒用例设计

## Tensor API 路线附加覆盖

采用 Tensor API 路线时，用例矩阵在常规 shape、dtype、边界和异常输入之上补充:

1. Layout / 物理布局变体。
2. transA / transB 组合(如接口涉及矩阵乘)。
3. M/N/K 尾块与非对齐。
4. group 为 0、随机 group list 和 M/K 分组(如接口涉及分组)。
5. 连续重复 launch 与资源释放。
6. 空 tensor 与 0 维 tensor。

Golden 必须独立于被测 kernel，并使用最终实际 H2D 物理 bytes;量化输入先按 ABI 合同解码,padding、tail 与对齐填充不参与结果。

以确认规格及任务 `proto.yaml`、`desc.md`、`golden.py`、`cases.yaml` 为输入。核对已有用例与需求范围，补充真正的覆盖缺口；不把已有用例反向当作全部需求，也不盲目展开参数笛卡尔积。

## 覆盖与规模

| 维度 | 设计要点 |
|------|----------|
| 接口 | 参数次序、attrs 默认值、optional、输出数与 dtype |
| shape | rank、广播、归约轴、相等/不等约束、最小值、对齐与非对齐、典型规模 |
| 数值 | 需求范围内的正负、小值、极值、零与适用的 NaN/Inf 语义 |
| 交互 | 对会影响结果的跨参数依赖做代表组合，避免无依据的全组合 |
| 异常 | 只测试规格定义的拒绝行为，正常边界与非法输入分开 |

L0 标记快速代表集，L1 标记常规功能组合，L2 标记边界或异常。它们是测试设计标签，可写在 `note` 和覆盖矩阵中，不改 proto 的算子难度 `L1`～`L4`，也不使用评测器的 `--level` 过滤测试标签。

每个新增 case 保留唯一整数 ID、输入参数、预期语义和覆盖目的。需求中的不适用值域不强加，例如数学定义不接受的负数不能塞进正常精度用例。空 tensor 与 rank=0 标量是不同语义；是否支持依据需求和 golden，而非自动都加进范围。

## 产物

在本轮方案中列出规格→case ID 的覆盖矩阵、golden 函数与版本、逐输出 checker/阈值的实际取值和来源、评测命令及补充测试入口。测试工程将其物化为 `cases.yaml` 和必要测试代码，按 [测试工程](test-framework.md) 的格式与入口执行。

公开原始用例保持只读；新任务或补充用例写入授权测试目录并记录来源。已有 golden 满足规格时直接复用，不为形式完整重新实现。只有资料冲突或无法确定语义时报告待决项，不修改预期结果配合当前 kernel。

## 核对依据

已核对 cann-bench `08d519c503843bce5fd4672ffa2259abeb22fb00`；实际运行记录所用版本。

- [docs/spec/cases_yaml_spec.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/docs/spec/cases_yaml_spec.md)
- [examples/tasks/README.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/tasks/README.md)
