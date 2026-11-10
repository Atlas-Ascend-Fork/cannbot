---
name: ops-direct-invoke-repo-guide
description: 提供 CANN Bench 的接口、编码、测试与交付约定；接入评测、编写用例或检视候选时使用。
---

# CANN Bench 仓库指南

支持 Ascend 平台；Kirin 尚未适配，使用通用仓库指南及 Kirin 工程。以下直调源码与构建约定适用于 CANN Bench AscendC 工程；其他语言的源码与构建契约由已选 `ops-direct-invoke-engineering` 提供。

## 仓库领域知识

本仓开发通过 Ascend C `<<<>>>` 启动的算子，提交给 CANN Bench 的 CANN 评测后端。候选源码工程、评测任务数据与评测器是三个独立对象：源码实现算子，任务描述规格与 golden，用例由评测器加载并执行。

源码交付保留 `cann_bench` 包及同名算子命名空间，以 `examples/direct_launch_example` 为工程基础。评测任务按 `proto.yaml`、`golden.py`、`cases.yaml`、`desc.md` 组织；同一评测接口承接黑盒、白盒和回归，不按用例来源划分工作模式。

需要核对目录、接口发现、精度或评分含义时，读取 [评测契约](references/evaluation-contract.md)。本 Skill 只提供工程事实，不决定流程节点或替用户选择技术路线。

## 仓库编码规则

算子计算必须来自本工程的真实 NPU kernel，并符合 CANN Bench 的提交与运行接口。读取 [编码检查表](references/red-lines.md)，按实际代码和证据检视；不要把静态规则套到测试 golden 上，也不把样例结构当作所有算子都适用的算法方案。

违规项给出位置、影响和修正要求。规则只定义代码与交付质量，不持有调度状态、不指定流程回退。

## 仓库测试开发

本仓使用 CANN Bench 的 CANN 任务格式与 `kernel_eval` 评测器。测试工程的工作是准备目标任务、补齐用例并接入评测入口，不另建一套 gen_data/run/精度比对框架。已有评测任务与代码可复用，全部需求范围内的用例统一验收。

| 工作 | 参考 |
|------|------|
| 任务目录、用例格式、统一执行入口及证据 | [测试工程](references/test-framework.md) |
| 按规格设计黑盒覆盖与补充用例 | [黑盒设计](references/blackbox-design.md) |
| 将源码分支用例写入现有任务集 | [白盒设计](references/whitebox-design.md) |
| 精度 checker、阈值与评分含义 | [精度与性能](references/precision-and-perf.md) |

任务决定执行代表用例还是全量回归；局部验证通过不能代替正式全量交付。原始评测文件和候选工程分开，禁止改 golden、阈值、评测器或删测掩盖算子错误。

工程骨架与构建由已选 `ops-direct-invoke-engineering` 提供。环境准备涉及 CANN Bench 时，核对[评测环境依赖](references/environment-dependencies.md)。
