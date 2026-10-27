---
name: workflow-dispatch
description: 算子开发工作流的架构路由分发
disable-model-invocation: true
---

# 工作流架构路由

`$SKILL_ROOT` = 本 SKILL.md 所在目录的绝对路径。

本技能只做一件事：识别用户需求是否为已有算子的增量开发；若是，转交
`ops-incremental` skill；否则按本机 NPU 架构选择工作流，并通过
workflow-orchestrator skill 启动它。

## 增量开发识别

若用户需求明确是**已有算子的有界增量开发**（例如功能补齐、修复、兼容性、
测试或文档变更，且目标算子已存在、改动范围有界），加载
ops-incremental skill 的 `SKILL.md` 并原样交接：

- `prompt` — 用户的算子增量需求，原样保留；
- `work_dir`、`provider` — 用户已提供则透传；
- `mode` — `execute` 或 `plan-only`，按用户需求或上游指令确定。

不要在 dispatch 中继续做需求分析、接口检查或硬件探测；这些由
`ops-incremental` skill 和其生成的 `workflow.yaml` 负责。

## 路由规则

以本机 NPU 架构号决定路由：

| NPU arch | 平台代际 | 工作流 YAML |
|---|---|---|
| `2201`（DAV_2201，如 Ascend 910B） | A2/A3 | ops-registry-invoke skill 的 `workflows/a2-a3-op-develop.yaml` |
| `>= 3510`（DAV_3510 及更新，如 Ascend 950） | A5 及更新 | ops-registry-invoke skill 的 `workflows/op-develop.yaml` |

用户显式指定路线时以用户为准。其余 arch 值（早于 2201、介于两代之间、
无法判定）不猜测：报告检测结果并请用户选择路线。

## 步骤

1. **获取 NPU 架构号。**
   在 CANN 环境已生效的前提下（如先 source toolkit 的 `set_env.sh`）
   运行 `asys info -r hardware`，读取 `Arch Info` 行给出的四位架构号
   （如 `2201`、`3510`）。架构号由工具负责提供，本技能不从 SoC 芯片名
   推测。用户在需求中明确指定 SoC 型号（如 Ascend910B）时，通过
   npu-arch skill 的产品映射表查询该型号对应的架构号。无法取得明确
   架构号时，报告已收集的证据（命令输出、报错信息）并请用户澄清，
   不自行推断、不默认任何一条路线。
2. **选定工作流 YAML。** 按路由规则选定后，对所选 YAML 运行 `realpath -m`
   并确认文件存在。派发前向用户报告检测到的架构号与所选路线。
3. **派发至 workflow-orchestrator。** 加载 workflow-orchestrator skill 并
   交接其四个入参：
   - `workflow.yaml` — 步骤 2 选定的 realpath；同时说明检测结果（架构号与
     路线）。
   - `prompt` — 用户的算子开发需求，原样保留。
   - `work_dir` — 用户已提供则透传；否则交由 workflow-orchestrator skill
     按其自身规则提议。
   - `provider` — 用户已提供则透传；未提供则交由 workflow-orchestrator skill
     按其自身规则提议确认。
   此后运行期间由 workflow-orchestrator skill 全权接管：其输入确认、启动、轮询
   与审批循环照常生效。本技能不在所选工作流之上叠加任何内容，也不得改变
   任何一个工作流的行为。
