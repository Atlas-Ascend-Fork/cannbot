# 新算子建模

编写时按需读[拓扑与固定定义](new-operator/authoring.md)、[并发与生命周期](new-operator/concurrency.md)、
[非均匀工作量](new-operator/advanced.md)及[Python Stage](new-operator/python-stages.md)。
完整字段、调用与使用限制见[框架参考](framework/index.md)。

用于从公式、实现或已有模型建立用户算子，或添加 stage/模板变体。产物为用户项目中的
可编辑模型、完整 case、规格与验证记录。先读[建模指南](modeling.md)和[字段参考](model-reference.md)。

## 从语义形成模型

从用户资料预填[规格模板](../assets/templates/model-spec.md)，确认完整输入、输出、
dtype/layout、尾块、状态、副作用与原数值标准。有实现时区分数学约束与当前实现选择；
无实现时以公式和独立参考作为语义依据，首个可运行模型只作为模型基线。

按以下关系推导拓扑，保留每项的来源：

| 问题 | 模型中要明确的内容 |
| --- | --- |
| 什么工作可以独立分配 | 任务域、原子与顺序约束、可拆维度、输出归属 |
| 什么工作依赖上一块/组 | 状态版本、跨 task 依赖、初始化与最终写回 |
| 数据在哪里驻留 | GM/L1/L0/UB 路径、读写区域、实际加载次数 |
| 哪些计算能重叠 | 阶段划分、发射关系、数据依赖与共享资源 |
| buffer 何时可复用 | pool、slots、全部消费者、最后读取与释放边界 |
| 每条操作如何计费 | 元素数量、dtype、单位、成本来源与适用域 |

不把已有实现的 tile/phase 当作数学约束。模型无法表达某种布局、同步或控制流时，
记录缺口与可表达的范围；不要借零成本或缺失依赖让模型接受方案。

## 在用户目录建立固定定义

复制最接近的可运行模型：简单入门使用[矩阵乘示例](../assets/examples/matmul/README.md)，
其他模型可用 `opmodel-assets export` 导出后检查，并按目标算子调整语义、任务和执行定义。

```text
my_operator/
  __init__.py
  case.yaml
  definition/
    semantic.yaml
    workload.yaml
    split.yaml
    operator.yaml
    dag.yaml
    costs.yaml
  optimize/
    search.yaml
    split.yaml
    dag.yaml
  SPEC.md
```

六份定义的职责与字段见[建模指南](modeling.md)。优先使用声明式 workload/split；
必要时才写 `workload.py`、`split_hooks.py`、`ms_hooks.py`，接口见该指南。
普通模型通过随附 `scripts/run_case.py` 调用 `run_native_case`，输入完整 case 并指定
独立输出目录，保存有效参数和执行结果。

表达式使用当前 schema 的 `expr` 等声明，不能直接放任意 Python 字符串。
任务分配与逐核投影使用实际分配子集，不能对每个核重复生成完整工作量。

## 验证固定 case

按[快速入门](quickstart.md)的完整 case 入口运行新模型，按[仿真说明](simulation.md)
选择普通/物理路径。先保留有效参数、任务分配、结果与 trace，再核对：

- 独立推导的任务数、输出覆盖、计算量和搬运量，与实际模型产物一致。
- 适用的默认点、尾块、相邻 task、多组与核未铺满场景；改变输入后重新派生，
  不强改 `num_groups/num_tasks` 等派生值来制造测试场景。
- 所有真实消费者读取完成后才复用 buffer；逻辑 pool 名不能增加物理容量。
  不能把减少 `use_pools` 当作消除等待的优化。
- 低精度、转换、padding、归约及最终输出次数符合原语义；多 AIV 分摊不重复缩放。
- 动态数值检查采用模型支持的接口和独立输入；没有执行的项目明确为未验证。

可按[数据流图](dag-dataflow-graph.md)核对声明连接，这不代替容量、生命周期、
数值和完整执行验证。模型完成执行或两个后端周期一致也不能证明原数学语义正确。

## 接入搜索与交付

请求包含寻优或完整搜索接入时，按[参数寻优](optimization.md)补充合法参数域和
实验配置，实际运行内置搜索。固定定义先独立可运行，固定 case 不依赖搜索输出。

检查候选参数确实改变工作量、几何、阶段或资源；固定值与不可搜索维度分别说明。
对基线、候选和有辨别力的边界点复核数量、容量和完整 case。搜索同分可能是瓶颈
未改变，也可能是参数未生效，应结合有效参数与 trace 区分。

用户只要求建模时交付模型和适用检查，不强制启动设备实验或所有优化流程。
保存 `SPEC.md`、有效 case、运行命令、结果位置及支持范围；若还需真实实现，
转到[联合寻优](joint-optimization/guide.md)。
