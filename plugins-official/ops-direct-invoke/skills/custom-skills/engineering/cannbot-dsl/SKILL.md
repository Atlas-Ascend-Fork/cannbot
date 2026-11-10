---
name: ops-direct-invoke-engineering
description: 以官方 CANNBot-DSL samples 和既有工程为依据，完成 DSL 源码、公开入口、构建与测试接入。
metadata:
  required_skills:
    - cannbot-dsl-best-practice
    - cannbot-dsl-test-generator
---

# CANNBot-DSL 工程

以本轮固定版本的官方 [cannbot-dsl](https://gitcode.com/cann/cannbot-dsl) `samples/` 为工程参考。调用方提供只读参考仓绝对路径；记录 remote、commit、所选样例与其 README。核对当前目录和命令后再复用，不假定 samples 内固定层级，也不修改或构建参考仓来代替候选。

1. 从与当前规格、芯片和执行方式匹配的实际样例提取最小工程；已有目标工程优先保留入口与布局。无可用样例或关键 API 依据时报告缺口，不生成猜测的构建命令。
2. 读取 `cannbot-dsl-best-practice` 的整体实现与编译启动资料，保留完整公开入口及 `@export` 合同。源码交付位置由需求冻结，进入节点 cwd 后不重新解释相对路径。
3. 使用已确认 Python/CANN 与环境门禁的能力结论。JIT/AOT 是实际工程执行方式，full/compile_only 是环境能力，两者分别记录。调用当前版本的真实构建和启动入口，保留翻译、编译与加载来源。
4. 按 task 的 DSL 代码版本协议操作 CODE_DIR，WORK_DIR 仅放本轮证据。冻结测试、Golden 与已验收设计不因工程适配被改写；单元代码汇合后验证完整公开入口。
5. 用 `cannbot-dsl-test-generator` 的原 runner/用例契约接入测试；测试命令、case 身份、设备和结果保留原格式。运行、Native/AOT 导出与交付必须对应同一实现，CPU/编译自检不代替设备功能验证。

本 Skill 不复制 DSL API 手册、设定算子算法或另写测试执行器。API 与样例来源保持本轮固定版本；性能优化继续通过原工作流入口接入。
