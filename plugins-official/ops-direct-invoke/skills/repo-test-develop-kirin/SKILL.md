---
name: repo-test-develop-kirin
description: 面向 Kirin 直调工程的黑盒、白盒及回归测试方法论与测试框架。提供直调工程的用例设计（L0/L1/L2）、cases.yaml 格式、gen_data/verify_result/run_tests 模式、精度校验口径与白盒接入流程。当工作流为 ops-direct-invoke、需要为 Kirin 直调算子设计测试或搭建测试工程时使用本 Skill。
---

# Kirin 直调测试开发

本 Skill 服务 `ops-direct-invoke` 工作流（Kirin <<<>>> 直调），覆盖黑盒测试设计、测试工程开发、白盒测试设计三个阶段的测试层。代码骨架（CMakeLists/main.cpp/kernel/tiling/data_utils.h/cmake）复用 `ascendc-direct-invoke-template`；本 Skill 只负责测试方法论与测试脚本框架，不重复定义代码骨架。

| 工作 | 参考 |
|------|------|
| 工程布局、cases.yaml 格式、执行入口与证据 | [测试框架](references/test-framework.md) |
| 按规格设计黑盒覆盖与补充用例 | [黑盒设计](references/blackbox-design.md) |
| 将源码分支用例写入现有用例集 | [白盒设计](references/whitebox-design.md) |
| 精度校验口径、阈值纪律 | [精度口径](references/precision.md) |

参考实现：`ascendc-direct-invoke-template/references/kirin_add_template/scripts/{gen_data.py,verify_result.py}`（add 样例，按目标算子改造）。

任务决定执行代表用例还是全量回归；穿刺的局部通过不能代替正式全量交付。golden、阈值、校验器与已生成用例保持只读，禁止篡改 golden、放宽阈值或删测掩盖算子错误。
