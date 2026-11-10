---
name: ops-direct-invoke-engineering
description: 创建和构建 CANN Bench AscendC 直调工程，核对源码、wheel 与实际加载版本。
---

# CANN Bench 工程

## 算子工程模板

工程来源为 cann-bench 的 `examples/direct_launch_example/`，保留它的构建、接口注册和 Python 导出约定。目标仓已经有兼容工程时就地扩展，不重建或覆盖已有代码。

| 工作 | 参考 |
|------|------|
| 取得官方模板、建立工程骨架 | [工程骨架](references/project-skeleton.md) |
| 添加 kernel、launch、注册和 Python 接口 | [算子模板](references/operator-template.md) |

模板是可运行工程的起点，不证明其 Add/Sqrt 的算法、dtype 或精度适合目标算子；按已确认规格完成实现。

## 仓库构建指南

本仓采用 cann-bench `examples/direct_launch_example` 工程：bisheng 编译 kernel，g++ 编译注册包装，链接 `_C.abi3.so` 并生成 `dist/cann_bench*.whl`。评测器可从源码根目录调用 `bash build.sh`。

读取 [构建与验证](references/build-guide.md)，按当前环境、源码快照和目标芯片构建。构建成功、wheel 可导入与算子功能通过分别记录，不混为一个结论。
