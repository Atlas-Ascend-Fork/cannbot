---
name: repo-test-develop
description: 基于 CANN Bench 组织 proto、golden、cases.yaml，复用 kernel_eval 执行直调算子的黑盒、白盒及回归测试。设计测试或接入评测工程时使用。
---

# 仓库测试开发

本仓使用 CANN Bench 的 CANN 任务格式与 `kernel_eval` 评测器。测试工程的工作是准备目标任务、补齐用例并接入评测入口，不另建一套 gen_data/run/精度比对框架。已有评测任务与代码可复用，全部需求范围内的用例统一验收。

| 工作 | 参考 |
|------|------|
| 任务目录、用例格式、统一执行入口及证据 | [测试工程](references/test-framework.md) |
| 按规格设计黑盒覆盖与补充用例 | [黑盒设计](references/blackbox-design.md) |
| 将源码分支用例写入现有任务集 | [白盒设计](references/whitebox-design.md) |
| 精度 checker、阈值与评分含义 | [精度与性能](references/precision-and-perf.md) |

任务决定执行代表用例还是全量回归；局部验证通过不能代替正式全量交付。原始评测文件和候选工程分开，禁止改 golden、阈值、评测器或删测掩盖算子错误。
