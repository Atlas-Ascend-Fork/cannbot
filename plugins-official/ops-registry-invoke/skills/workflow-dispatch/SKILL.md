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

| 平台 | 判定值 | 工作流 YAML（相对 ops-registry-invoke skill） |
|---|---|---|
| 昇腾 A2/A3 | 架构号 `2201`（如 Ascend 910B） | `workflows/a2-a3-op-develop.yaml` |
| 昇腾 A5+ | 架构号 `>= 3510`（如 Ascend 950） | `workflows/op-develop.yaml` |
| 麒麟 | KirinX90/Kirin9030 等端侧麒麟芯片 | `workflows/kirin-op-develop.yaml` |

用户显式指定平台或 YAML 时以用户为准。

## 步骤

1. **判定平台与架构号。**
   - 昇腾：有 SoC 型号（如 Ascend910B）时经 npu-arch skill 的产品映射表查架构号；
     否则先 source toolkit 的 `set_env.sh`，运行 `asys info -r hardware`，以
     `Arch Info` 行的四位架构号为准。
   - 麒麟：用户提及麒麟/麒麟芯片型号或端侧/鸿蒙（如 KirinX90/Kirin9030）时
     判定为麒麟平台。

   完成判据：能按路由表确定平台与判定值；否则报告已收集的证据并请用户澄清，
   然后停止。
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
