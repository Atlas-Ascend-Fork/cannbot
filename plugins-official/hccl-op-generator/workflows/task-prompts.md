# CCU 兼容调用参数

本文档保留 **CCU 原流程**作为历史参考；CCU Skill 已移除，目前不对外支持，HCCLBot 不得调用本文档。AICPU 的调用模板见 [aicpu-task-prompts.md](aicpu-task-prompts.md)，状态机见 [aicpu-multi-agent-workflow.md](aicpu-multi-agent-workflow.md)。

## CCU 兼容状态与行为门禁

CCU 不采用 AICPU 的产物目录和双轨门禁，但 HCCLBot 必须使用 [流程策略校验器](scripts/workflow_policy.py) 约束旧流程的实际调用顺序：

```text
ENV_READY
  → Architect → DESIGN_READY
  → Developer → IMPLEMENTED
  → Verifier  → VERIFIED
  → Reviewer  → REVIEW_PASS
  → HCCLBot   → COMPLETE
```

每个正常阶段返回后调用 `workflow_policy.py transition --engine CCU ...`。失败进入修复链后，逐角色调用 `workflow_policy.py recovery --engine CCU ...`，禁止跳过 Verifier 或 Reviewer。Review/Test 共用 `repair_round`，最多三轮；测试失败必须区分 `SOURCE` 与 `ENVIRONMENT`，环境失败不得调用 Developer 猜修源码。

---

## Step 2：设计

### Subagent 调用参数

```
{
  "description": "方案设计",
  "subagent_type": "hccl-architect",
  "prompt": "
请为以下算子设计算法模板方案：
- 通信引擎：CCU
- 算子类型：{op_type}
- 算法名称：{algo_name}
- 需求描述：{用户需求}
- 环境信息：${HCCL_ROOT}/src/ops/{op_type}/docs/environment.md

【输出】
- 技术设计：${HCCL_ROOT}/src/ops/{op_type}/docs/DESIGN.md
- 开发计划：${HCCL_ROOT}/src/ops/{op_type}/docs/PLAN.md，参考 workflows/templates/plan-template.md

【验收标准】
- 设计包含：算子类型（HcclCMDType）、双层架构（template/ccu 编排 + template/ccu/kernel 录制）、CCU 模式（CCU_MS/CCU_SCHED）、算法选择（SoleMesh/SoleNHR/PipeLine...）、资源计算（ccuKernelNum/ccuKernelInfos 含 kernelFunc 指针）、注册宏选择
【设计要求】
- algName 前缀 CcuSched/CcuMS，必须与 REGISTER_EXEC_V2 的 name 完全一致
- template 继承 CcuAlgTemplateBase（非 InsAlgTemplateBase），kernel 继承 CcuKernelCtxBase
- CCU REGISTER 行必须双重守卫：#ifndef AICPU_COMPILE + #if CANN_VERSION_NUM >= CANN_VERSION(9,0,0)
- 双层落位：ccu_temp_* 与 ccu_kernel_* 缺一不可；双 CMakeLists（template/ccu + template/ccu/kernel）
- 数据类型约束排除：保序/PROD/64bit/INT8(CCU_MS)/inplace/level2UBG/3层拓扑 → 回退 AICPU
- 必须先读取已有实现（${HCCL_ROOT}/src/ops/{op_type}/template/ccu/）
【推荐 Skill】
- CCU 专属 Skill 已移除；此历史模板不得用于实际任务
- /hccl-doc-search — 需要官方文档支撑时使用
  "
}
```

---

## Step 3：开发

### Subagent 调用参数

```
{
  "description": "算子开发",
  "subagent_type": "hccl-developer",
  "prompt": "
请根据设计方案实现算法模板代码：
- 通信引擎：CCU
- 算子类型：{op_type}
- 算法名称：{algo_name}
- 技术设计：${HCCL_ROOT}/src/ops/{op_type}/docs/DESIGN.md
- 开发计划：${HCCL_ROOT}/src/ops/{op_type}/docs/PLAN.md

【输出目录】
${HCCL_ROOT}/src/ops/{op_type}/

【输出文件】
- template/ccu/ccu_temp_{op}_{algo}.h / .cc — CCU 模板层（继承 CcuAlgTemplateBase）
- template/ccu/kernel/ccu_kernel_{op}_{algo}.h / .cc — CCU 内核层（CcuKernelArg + Context 继承 CcuKernelCtxBase + Kernel 入口）
- executor/ins_v2_{op}_{algo}_executor.cc — 复用已有 sole executor 追加 REGISTER_EXEC_V2（双重守卫）或新建
- selector/{op}_auto_selector.cc — 修改 SelectCcuMsAlgo() / SelectCcuScheduleAlgo() 添加算法分支
- template/ccu/CMakeLists.txt — 注册 ccu_temp_*.cc
- template/ccu/kernel/CMakeLists.txt — 注册 ccu_kernel_*.cc
- executor/CMakeLists.txt — 注册新增 .cc（仅新建 executor 文件时）
- LOG.md — 开发日志（输出到 docs/）
【开发要求】
1. algName 前缀 CcuSched/CcuMS，必须与 REGISTER_EXEC_V2 的 name 完全一致
2. template 实现纯虚：Describe、CalcRes、KernelRun、FastLaunch、GetThreadNum、GetRes（无 GetNotifyIdx*/CalcScratchMultiple）
3. KernelRun 用 PointerToAddr+GetToken+HcommCcuKernelLaunch+FillCachedArgs+ConvertCcuToHccl
4. kernel 内数据依赖分支必须用 CCU_IF/CCU_WHILE 宏（不可原生 if/while）；taskArgs 顺序与 kernel ccu::LoadArg 的 argId 顺序一致
5. CCU REGISTER 行必须双重守卫：#ifndef AICPU_COMPILE + #if CANN_VERSION_NUM >= CANN_VERSION(9,0,0)
6. 不 include alg_data_trans_wrapper.h；kernel include ccu_kernel_alg_base.h 获取 namespace ccu
7. CalcRes 置 notifyNumOnMainThread=0、slaveThreadNum=0，填 ccuKernelNum + ccuKernelInfos（kernelFunc/setKernelArg/channels）
8. 编码规范：C++14、PascalCase（CcuTemp·/Ccu<Op>Kernel）、camelCase_、120 列、CANN-2.0 头
【推荐 Skill】
- CCU 专属 Skill 已移除；此历史模板不得用于实际任务
- CCU 调试 Skill 待补充；此历史模板不得用于实际任务
【参考实现】
- Broadcast（最简）: ${HCCL_ROOT}/src/ops/broadcast/template/ccu/ccu_temp_broadcast_mesh_1D_mem2mem.cc + kernel/ccu_kernel_broadcast_mesh1d_mem2mem.cc
- AllReduce（含 omnipipe 多模板）: ${HCCL_ROOT}/src/ops/all_reduce/template/ccu/
  "
}
```

---

## Step 4：验证

### Subagent 调用参数

```
{
  "description": "编译验证与 hccl-vm/UT/ST 测试",
  "subagent_type": "hccl-verifier",
  "prompt": "
请对 CCU 算子进行编译、hccl-vm 验证和 UT/ST 测试：
- 通信引擎：CCU
- 算子类型：{op_type}
- 算法名称：{algo_name}
- 算子代码目录：${HCCL_ROOT}/src/ops/{op_type}/

【验证步骤】
1. 编译构建：
   source {env_file}
   source ${CANN_HOME}/set_env.sh
   cd ${HCCL_ROOT}
   bash build.sh --pkg          # host 包
   bash build.sh --pkg --full   # host + device 全量包（CCU device kernel 符号必需）

2. HCCL-VM 测试（加载 /hccl-test-tool-hvm skill）：
   - 确认 hvm 环境（5 项路径检测）
   - 选择 CCU 通信引擎、算子、数据类型、通信域
   - ★ 默认不跑 Runner（不加 --runner，仅 Checker DAG 校验）；Runner 跑实际数据校验慢且易超时，仅在用户明确要求时启用
   - ★ 固化参数：--timeout 180s（hvm socket 清理慢，60s 会误报 timeout）；数据量至少覆盖小数据(64/256)+大数据(64K/1M)各 2 档；通信域：{comm_domains}（由 HCCLBot 按用户目标 rank 注入；占位符缺失时回退读 DESIGN.md 1.5「目标 rank 数/目标通信域」推导）。规则：目标 rank 为主用例（8p→118，可选 124/141 跨 server 覆盖），另补 112(2r) 作路由防误命中冒烟（验证非目标 dtype 不误路由到新算法）；禁止对 8p 算子仅用 112/114 作主验证
   - ★ 必须含对照组：除 V2 目标 dtype 外，另跑 1 个非目标 dtype 小用例验证路由不误命中（如 V2 为 fp32，则补 fp16 验证应路由到既有算法）
   - 执行 run.sh（清理 /dev/shm → 组装命令 → 运行，不加 | tail 保留完整输出）
   - 从日志 grep「算法:」核对路由算法名与预期一致
   - 解析结果（通过/失败数 + 失败用例列表），区分「timeout」（hvm socket 超时，非算子缺陷）与「Checker Success not found / 数据错误」（真实失败）

3. UT/ST 测试：
   bash build.sh -u             # 编译并运行 UT
   bash build.sh -s             # 编译并运行 ST

【输出】
- 编译结果（成功/失败 + 错误信息）
- hccl-vm 结果（总用例数/通过数/失败数 + result 文件路径 + 失败用例列表，timeout 与真实 FAIL 分别列出 + 路由算法名核对结果）
- UT 结果（通过/失败数）
- ST 结果（通过/失败数）
- LOG.md（补充编译测试日志）

【验证标准】
- 编译成功（build.sh --pkg 无错误）
- hccl-vm Checker 用例 PASS（timeout 若为 hvm socket 清理慢，需 180s 重跑代表性用例确认非算子缺陷；真实 Checker FAIL/路由错误不得通过）
- UT 全部 PASS
- ST 全部 PASS

【失败处理】
- 编译、hccl-vm 或 UT/ST 的源码问题 → 分析原因并记录到 LOG.md，返回 `TEST_FAIL` 且标记 `failure_class=SOURCE`，由 HCCLBot 进入 Developer → Verifier 修复链
- 环境、权限或基础设施问题 → 固化证据并返回 `TEST_FAIL` 且标记 `failure_class=ENVIRONMENT`，由 HCCLBot 阻塞并汇报；不得调用 Developer 猜修源码
- hccl-vm timeout 必须按上述标准区分环境问题和真实源码问题，不能改记 PASS

【推荐 Skill】
- CCU 专属 Skill 已移除；此历史模板不得用于实际任务
- /hccl-test-tool-hvm — HCCL-VM 虚拟机测试执行与结果汇总
- CCU 调试 Skill 待补充；此历史模板不得用于实际任务
  "
}
```

---

## 独立只读评审

仅用于用户要求审查现有 AICPU template；按用户输入替换占位符，未提供的 base/spec 写“无”。
报告路径优先采用用户指定值，否则使用该算子的 docs/REVIEW.md。复用已确认的输入，不要求环境安装。

```text
subagent_type: hccl-reviewer
prompt:
请使用 hccl-aicpu-best-practice 对以下目标做独立只读评审：
- HCCL 仓路径：{repo_path}
- 目标文件：{target_files}
- 评审模式：{review_mode}
- 增量基线：{base_ref}
- 每个 template 的 spec 路径：{spec_paths}
- 报告路径：{report_path}

从已加载 skill 目录定位脚本，显式传 --repo，不要求 hccl-env.sh。
增量评审将 base ref 固定为 commit，逐个 template 使用对应 spec。
执行脚本检查并完成人工清单，按报告模板写证据和静态结论；无 spec 标注契约层未执行。
只写报告，不修改源码，不安装环境、不构建或运行测试，也不启动修复循环。
如未提供实际验证证据，报告明确写未验证，不给出功能验收通过结论。
```

---

## Step 5：审查

### Subagent 调用参数

```
{
  "description": "代码审查",
  "subagent_type": "hccl-reviewer",
  "prompt": "
请审查以下算子的实现代码：
- 通信引擎：CCU
- 算子类型：{op_type}
- 算法名称：{algo_name}
- 代码目录：${HCCL_ROOT}/src/ops/{op_type}/

【审查范围】
- template/ccu/ccu_temp_{op}_{algo}.h / .cc
- template/ccu/kernel/ccu_kernel_{op}_{algo}.h / .cc
- executor/ins_v2_{op}_{algo}_executor.cc（REGISTER 行）
- selector/{op}_auto_selector.cc（SelectCcuMsAlgo/SelectCcuScheduleAlgo 修改部分）
- template/ccu/CMakeLists.txt + template/ccu/kernel/CMakeLists.txt
【审查清单（8 类）】
1. 代码规范（CcuTemp·/Ccu<Op>Kernel 类名；kernel 签名 CcuResult Ccu<Op>Kernel(CcuKernelArg arg)）
2. 注册机制（algName == REGISTER name 含 CcuSched/CcuMS 前缀；REGISTER 行双重守卫 #ifndef AICPU_COMPILE + #if CANN_VERSION_NUM >= CANN_VERSION(9,0,0)）
3. 继承关系（template 继承 CcuAlgTemplateBase 非 InsAlgTemplateBase；kernel context 继承 CcuKernelCtxBase；纯虚 Describe/CalcRes/KernelRun/FastLaunch 已实现，无 GetNotifyIdx*）
4. include 规范（不 include alg_data_trans_wrapper.h；kernel include ccu_kernel_alg_base.h；template .cc include \"ccu/ccu_temp_*.h\"）
5. 资源管理（CalcRes 置 notifyNumOnMainThread=0/slaveThreadNum=0；填 ccuKernelNum+ccuKernelInfos 含 kernelFunc/setKernelArg/channels；GetThreadNum 返回 1）
6. 数据搬运逻辑（kernel 内数据依赖分支用 CCU_IF/CCU_WHILE 非原生 if/while；taskArgs 顺序 == ccu::LoadArg argId 顺序；KernelRun 用 PointerToAddr/GetToken/HcommCcuKernelLaunch/ConvertCcuToHccl）
7. CMakeLists（双注册：template/ccu + template/ccu/kernel；executor CMakeLists 仅新建 executor 时改）
8. 边界场景（保序/PROD/64bit/INT8(CCU_MS)/inplace/level2UBG/3层拓扑 → 回退 AICPU 的 NOT_MATCH 分支）

【输出】
${HCCL_ROOT}/src/ops/{op_type}/docs/REVIEW.md

【评审结论】
- PASS：无严重问题，一般问题 ≤ 5
- PASS_WITH_NOTES：无严重问题，一般问题 > 5 或有重要建议
- FAIL：存在严重问题

【推荐 Skill】
- CCU 专属 Skill 已移除；此历史模板不得用于实际任务
  "
}
```

---

## Step 6：修复循环

### 6a — Developer 修复

```
{
  "description": "代码修复",
  "subagent_type": "hccl-developer",
  "prompt": "
请根据审查报告修复代码问题：
- 通信引擎：CCU
- 算子类型：{op_type}
- 算法名称：{algo_name}
- 代码目录：${HCCL_ROOT}/src/ops/{op_type}/
- 审查报告：${HCCL_ROOT}/src/ops/{op_type}/docs/REVIEW.md

【修复要求】
1. 逐条修复 REVIEW.md 中的严重问题
2. 尽量修复一般问题
3. 修复后更新 LOG.md 记录修复内容
4. 重新编译验证修复是否有效

【禁止】
- 禁止推翻重写，只针对性修复审查指出的问题
  "
}
```

### 6b — Reviewer 复审

```
{
  "description": "代码复审",
  "subagent_type": "hccl-reviewer",
  "prompt": "
请对修复后的代码进行复审：
- 通信引擎：CCU
- 算子类型：{op_type}
- 算法名称：{algo_name}
- 代码目录：${HCCL_ROOT}/src/ops/{op_type}/
- 原审查报告：${HCCL_ROOT}/src/ops/{op_type}/docs/REVIEW.md

【复审重点】
1. 确认原严重问题已修复
2. 检查修复是否引入新问题
3. 更新 REVIEW.md 末尾追加本轮复审结果

【输出】
在 REVIEW.md 末尾追加 ## 第{N}轮复审 章节，给出 PASS/FAIL 结论
  "
}
```
