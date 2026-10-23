---
name: ops-registry-invoke
description: ACLNN 算子开发工作流入口
---

# ACLNN 算子开发工作流入口

`$SKILL_ROOT` = 本 SKILL.md 所在目录的绝对路径。

本 skill 负责把依赖 skills 装齐，然后经 workflow-dispatch 分发并启动工作流。

## 步骤

1. **预检。** 读取 `$SKILL_ROOT/skills.json`（skills 分 native / external 两组，
   安装源即其 sources）。逐项检查 `$SKILL_ROOT/../<name>/SKILL.md`，得到缺失
   清单；无缺失则直接进入步骤 3。
2. **补装缺失项。** 向用户报告缺失清单，经确认后按组执行——每个缺失 skill 一条
   `--skill`（逗号写法无效）：

   ```bash
   npx --yes skills@latest add <该组的 source> --skill <name> ... --agent <agent-id> -y
   ```

   `--agent` 取当前会话的 Agent CLI：claude → claude-code，codex → codex，
   opencode / cannbot → opencode，pi → pi。命令失败则如实报告并终止本次启动；
   装完复检，仍有缺失则报告并终止。
3. **分发。** 加载 workflow-dispatch skill，交接用户上下文：`prompt` = 用户的
   算子开发需求，原样保留；`work_dir`、`provider` — 用户已提供则透传。
   workflow-dispatch 检测 NPU 架构、选定工作流并启动 workflow-orchestrator，
   此后由其全权接管。

用户要求刷新已装依赖时：`npx skills update`。
