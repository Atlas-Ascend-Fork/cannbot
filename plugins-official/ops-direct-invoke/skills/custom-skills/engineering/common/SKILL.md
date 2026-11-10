---
name: ops-direct-invoke-engineering
description: 复用通用 AscendC 直调工程模板，完成目标仓的构建、启动和测试接入。
metadata:
  required_skills:
    - ascendc-direct-invoke-template
---

# 通用 AscendC 工程

输入为已确认目标仓、源码目录、芯片/工具链、实现路线及授权范围。读取已有工程；兼容时增量接入，缺少工程时使用已安装 `ascendc-direct-invoke-template` 的目标路线模板，记录真实 Skill 路径与版本，不从省略示例拼造 CMake。

保留模板的 kernel、Host、注册/导出及构建边界，按规格替换算子名、参数、Tiling 和输出。实际编译/运行命令取自所选模板 README，并记录所选 Python、CANN、目标架构、源码和加载产物。不要因默认 Add 能运行而扩大目标算子的支持范围。

Tensor API 路线以 `ascendc-tensor-api-best-practice` 的官方样例与构建合同为准；现有宿主接口有约束时保留该约束。Blaze 路线复用 `ascendc-blaze-best-practice` 的适用模板。这里提供工程接入，不重新选择已经确认的路线。

测试接入沿用目标仓指南及模板已有数据生成、独立 Golden 和校验入口；补齐目标算子用例后才可声明功能通过。源码、构建产物和实际运行版本须对应，记录全量发现数、执行数及原始结果。正式性能结论由安排的性能工作流产生。
