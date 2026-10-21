---
name: pypto-op-orchestrator
description: PyPTO 算子开发与性能调优的工作流总入口。触发：生成/开发/实现 PyPTO 算子（如"生成一个 pypto 实现的 xxx 算子"）；对已有 PyPTO 算子做性能调优/性能优化/提速（如"对 xxx 算子做性能调优，目标 xx us"）；或明确要求使用 pypto-op-develop / pypto-op-tune 工作流时。凡是完整的算子开发任务或独立的算子调优任务，先经本入口分流到对应工作流，再按工作流节点按需加载专项技能。
---

使用 workflow-orchestrator skill 启动对应工作流：

- 开发/生成算子：`workflows/pypto-op-develop.yaml`
- 性能调优：`workflows/pypto-op-tune.yaml`

安装态下 yaml 位于 `<工作区>/.cannbot/plugins/pypto-op-orchestrator/workflows/`；仓内开发态位于 `plugins-official/pypto-op-orchestrator/workflows/`。
