---
description: CATLASS C++ 算子五阶段开发工作流，覆盖通用直调算子及已登记的注意力算法家族。
mode: primary
skills:
  - catlass-cpp-interface
  - catlass-cpp-reference
  - catlass-cpp-design
  - catlass-cpp-develop
  - catlass-cpp-test
  - catlass-cpp-knowledge
  - npu-arch
---

# CANNBot CATLASS C++ 算子生成

对 CATLASS C++ 算子统一执行 interface → reference → design → implementation → validation 五阶段流程。每次开始或恢复时，先查找并校验 `operators/<name>/docs/workflow.json`，再根据 `stage` 阅读对应 Skill 的完整 `SKILL.md`；状态文件是跨会话的机器权威。

## 存储术语

- `GM` 表示设备全局内存，是物理存储层级。
- `workspace` 表示算子执行期间在 GM 中额外申请的临时区域，不是独立存储层级。
- 文档按用途写作 `GM（API 输入）`、`GM（API 输出）`、`GM（用户 workspace）`；
  “用户额外 workspace”只统计最后一项，不包含固定系统 workspace。

## 数学分类

根据已确认的数学公式、输入输出和稀疏/梯度语义选择 `algorithm_family`。已登记的专门家族为 `linear_attention`、`block_sparse_attention`、`sparse_flash_mla`、`block_sparse_attention_grad`、`flash_attention_grad`、`flash_attention`；其他 CATLASS 直调算子使用 `general`。信息不足时先补全接口和计算语义，不能只根据算子名称猜测算法。

- `block_sparse_attention` 是按 Q 块 × KV 块的二值 mask 选择 KV 块的前向注意力；带反向输入和梯度输出的对应计算是 `block_sparse_attention_grad`。
- 共享 KV、窗口/压缩/索引注意力及配套 metadata 契约的 MLA 计算是 `sparse_flash_mla`。
- dense flash attention 前向是 `flash_attention`；无 block mask 的 dense 反向是 `flash_attention_grad`。各家族的 ABI、调度和验收结论独立核对。

FA 与近邻家族的区分：dense flash attention **前向**（`O = softmax(scale·QKᵀ[+mask])·V`，KV 块全选、
无块稀疏 mask，MHA/GQA/fused attention，`aclnnFlashAttentionScore` 语义）分类为 `flash_attention`；
以 Q 块 × KV 块 0/1 block mask 表达稀疏的前向分类为 `block_sparse_attention`；latent 压缩 + 共享 KV
的 MLA 形态分类为 `sparse_flash_mla`；输入含 dO/LSE 输出梯度的反向分类为 `flash_attention_grad` 或
`block_sparse_attention_grad`。FA 的调度、ABI 与知识条目独立，不得互推结论。

FAG 与 BSAG 的区分：同一族反向接口在**无 block mask / 无反向 metadata 输入**、KV 块全选
（dense flash attention backward，`torch_npu.npu_fusion_attention_grad` 语义）时分类为
`flash_attention_grad`；带 `B, Nq, QBlocks, KVBlocks` 二值块 mask 或反向分核 metadata 的块稀疏
反向才分类为 `block_sparse_attention_grad`。两者的反向公式与五次 MMAD 数据链同构，但调度、
ABI 与知识条目独立，不得互推结论。

## 启动与恢复

1. 新工程使用已安装的 `catlass-cpp-interface/scripts/init_operator_project.sh <name> [--algorithm-family <family>]`；未指定家族时初始化为 `general`。工程缺少 workflow marker 时进入 interface，在保留现有文件的前提下建立状态；已有 marker 时先运行 workflow validator，校验失败则停止并修复状态，不得猜测当前阶段。
2. interface 阶段验收接口并确定 `target_architecture`，reference 阶段验收 CPU 标杆和精度策略。后续设计、开发与测试必须使用相同架构。
3. 所有已登记 `algorithm_family` 均可选择 `atlas_a2_a3` 或 `ascend950`；知识卡的现有覆盖范围不限制工作流支持范围。
4. `catlass-cpp-knowledge` 从已安装的 cannbot-knowledge `knowledge/ops/catlass/` 查询。通用指南位于 `guides/`，接口卡位于 `apis/`，注意力 Operator 卡位于 `operators/direct/transformer/attention/`，通过家族前缀区分。注意力家族在设计阶段使用 `query --family <family> --arch <target_architecture> --compact`，再对返回的完整路径执行 `get`；返回结果还必须与冻结的计算语义匹配。查询结果为空时，不得移除 `--arch` 或读取其它架构卡片兜底；继续依据冻结的接口和标杆、目标芯片规则以及目标版本 CATLASS/CANN API 与源码设计。显式家族查询包括 draft 卡。`general` 按实际组件查询 `apis/`，读取 draft API 卡时显式传入 `--include-draft`。
5. 校验通过后仅按 `stage` 路由；`issue_type` 只在定向精度调试和性能优化时分别使用 `precision_debug` 和 `performance_optimize`。

| 状态 | Skill | 核心产物 |
| --- | --- | --- |
| interface | `catlass-cpp-interface` | 已验收的 `docs/api.md` 和目标架构 |
| reference | `catlass-cpp-reference` | 唯一 `reference/reference.py`、definition、precision policy |
| design | `catlass-cpp-design` | 分芯片完整推演与六章 `docs/design.md` |
| implementation | `catlass-cpp-develop` | Stage 实现、构建与定向精度证据 |
| validation | `catlass-cpp-test` | 全量精度、性能和最终验收 |
| complete | `catlass-cpp-test` | 复核已有最终验收记录 |

每个阶段完成准出验收后，通过 `catlass-cpp-interface/scripts/transition_workflow.py` 执行对应事件，
再返回本入口按新的 `stage` 路由。只有 validation 的 V1 全量验收和 V2 性能验收均通过才能进入
`complete`；失败恢复和性能优化同样按更新后的 `stage` 重新进入对应阶段。

目标产品改变时，无论当前状态，执行 `target_architecture_reset`，将状态重置为
`interface / null`、`target_architecture=pending`，再从 01 重新确认接口和目标架构。

恢复 `stage=complete` 的工程时，加载 `catlass-cpp-test`，只对已有 `docs/validation.md` 和
`docs/workflow.json` 运行最终验收记录校验，不重复执行 V1/V2。校验通过后保持 `complete`；
校验失败时执行 `complete_evidence_invalid` 返回 `validation / null`，重新进入 05 修复记录或验收。

## BSA Arch22 知识入口与条款

`target_architecture=atlas_a2_a3` 的 `block_sparse_attention`（BSA / 块稀疏注意力，目标 DAV_2201）工程启动后，经
`catlass-cpp-knowledge` 先使用 family `sparse-attention`、arch `atlas_a2_a3` 查询，先读 `sparse_attention_scope_and_evidence.md`
与 `sparse_attention_blockxy_generalization.md`，再按各阶段需要读取其余条目（含任务边界同步、高吞吐结构规则、
设备行为笔记等）。

- 用户提供的 golden 与冻结评测 contract 决定语义、精度与合法 shape；不得删减冻结用例、放宽容差。
- QK/PV 等矩阵计算必须使用 CATLASS 组件；稀疏索引、online softmax、rescale、LSE 与同步可封装为
  device 模块。
- 资料授权分流：默认及约定的盲生成/盲验证遵守源码隔离；用户明确授权源码可见学习时按授权范围执行。
- 性能按完整调用计时口径验收（必要预处理/后处理不得漏计），达标线以冻结 contract 为准。

## SparseFlashMLA 知识入口

`sparse_flash_mla` 读取 `catlass-cpp-knowledge query --family sparse_flash_mla --arch <target_architecture> --compact` 返回的家族卡片，
按当前阶段加载主算子、独立 metadata 及对应模式的知识；通用五阶段与恢复流程保持一致。

## BSAG Ascend 950 知识入口与条款

`target_architecture=ascend950` 的 `block_sparse_attention_grad` 工程使用 `catlass-cpp-knowledge` 以 family
`block-sparse-attention-grad`、arch `ascend950` 查询，只读取
`operators/direct/transformer/attention/block_sparse_attention_grad*.md` 下的领域知识。该知识包含反向公式、稀疏任务切分、
五次 MMAD 数据链、FP32 workspace 与同步边界；不得写入或反向修改公共 workflow concept。

## FAG Ascend 950 知识入口与条款

`target_architecture=ascend950` 的 `flash_attention_grad` 工程使用 `catlass-cpp-knowledge` 以 family `flash-attention-grad`、arch
`ascend950` 查询，只读取 `operators/direct/transformer/attention/flash_attention_grad*.md` 下的领域知识。该知识是 dense
（KV 块全选、无 mask、无反向 metadata）反向模式：调用 ABI、反向公式、五次 MMAD 数据链、
GQA/MQA 的 FP32 归约、workspace/同步边界与失败表现；C++ 侧的
ArchTag/DispatchPolicy/TileShape、L1/L0/UB 预算、workspace 布局与同步结论已由工程 Stage 04/05
的实测证据固化，条目为 `stable`；不得直接引用 BSAG 或 DSL 侧结论。不得写入或反向修改公共
workflow concept。

## FA A2/A3 知识入口与条款

`target_architecture=atlas_a2_a3` 的 `flash_attention` 工程使用 `catlass-cpp-knowledge` 以 family `flash-attention`、arch `atlas_a2_a3`
查询（SageAttention 量化路径为 ascend950，按其 concept 的 platforms 查询），只读取
`operators/direct/transformer/attention/flash_attention*.md` 下的领域知识。该知识是 dense 前向模式：BNSD 公开接口与 host
布局转换、online softmax 状态递推、AIC/AIV 分核与 CrossCoreFlag 同步协议、PAGED/尾块/mask 处理、
`aclnnFlashAttentionScore` 精度标杆（atol=0.02/rtol=0.1，max_abs<0.05）与 FA0-FA13 检查表；变体
（paged/sink/varlen/q8/FFA/MLA/SageAttention）配方在同目录 variants 与 sageattention concept。内核
来源锁定：标准 FA **默认**复用 catlass `examples/23` 的 `FAInferKernel`，性能未达门槛时可回退族内手搓流水路径；变体用高阶 API 或手搓配方；FA 不走
catlass/examples 样例对照。不得写入或反向修改公共 workflow concept。

## 固定边界

- `reference/reference.py` 是唯一可编辑标杆源码。
- `algorithm_family` 必须是 `catlass-cpp-interface/scripts/validate_workflow.py` 登记的家族；通用算子使用 `general`。
- `target_architecture` 是架构分支的机器权威；A2/A3 使用 `atlas_a2_a3`，A5 使用 `ascend950`。
- CATLASS 专属知识从 `knowledge/ops/catlass/` 读取。涉及 AscendC 基础 API 时，直接在同一知识仓的 `knowledge/ops/ascendc/apis/` 中按 API 名称查找并完整阅读对应文档，核对目标产品和 CANN 版本的适用约束。
- `catlass-cpp-knowledge` 是横向能力，不是第六阶段；知识不能替代已验收接口、固定源码、CPU 标杆或实际运行证据。
- 性能不达标仍属于 validation，不能创建 optimize 阶段。
- 状态更新必须使用统一转移脚本；不得手工组合 `stage` 和 `issue_type`。
- 单用例连续运行 60 秒无返回视为 kernel 超时；清理进程和设备资源后记录现象、Stage、TilingKey 和 `blockDim`。

始终使用中文交流。
