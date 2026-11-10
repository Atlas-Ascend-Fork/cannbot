---
name: ops-direct-invoke-env-check
description: 检查选定 Ascend 与 CANNBot-DSL 环境，保留原环境 Skill 的编译门禁、设备选择和产物语义。
metadata:
  required_skills:
    - cannbot-dsl-env-check
---

# Ascend / CANNBot-DSL 环境检查

先核对[环境选择与复用](references/environment-policy.md)，读取已确认的 Python/CANN、目标设备及修改权限。使用已安装 `cannbot-dsl-env-check` 的真实入口，以选定解释器设置 `PYTHON`、以 `$WORK_DIR` 传 `--output-dir`，不以节点 cwd 作为产物根。

保留原 Skill 生成的 `environment/environment.yaml` 与 `environment/env_selected_soc.yaml` 及其 schema。核对导入、翻译、编译门禁与 NPU 可用性，记录 full/compile_only/blocked 的原生结论；环境检查不执行 DSL kernel，也不证明精度/性能。compile_only 不能被改写成 full，工作流额外的继续/停止政策由 task 表达。

核对默认选中的逻辑设备与本轮授权目标一致；不一致时作为选择缺口交调用方，不默默覆盖用户目标。参考仓和样例来源、版本与工程依赖按已选 `ops-direct-invoke-engineering` 核对，不能用单纯 torch/NPU 通过替代 DSL 编译门禁。

在[环境信息](references/环境信息.md)引用原生 YAML 和检查日志，不改名、覆盖或另造一份相互矛盾的能力状态。缺依赖由调用方在已有授权内准备后复核。
