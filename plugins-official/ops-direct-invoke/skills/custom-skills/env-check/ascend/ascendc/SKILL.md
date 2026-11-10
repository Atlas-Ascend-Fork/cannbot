---
name: ops-direct-invoke-env-check
description: 为需求对齐提供 conda/Python 与 CANN 候选，检查用户选定的开发环境并记录授权与证据；按环境组合复用有效记录。
---

# Ascend / AscendC 环境检查

遵循[环境选择、检查与复用](references/environment-policy.md)。首次检查或缓存缺项时执行相应项目；结果及原始日志放在 `.cannbot/环境检查/`，按 [环境信息](references/环境信息.md) 记录真实结论。

| 检查项 | 方法与通过依据 |
|--------|----------------|
| NPU | `npu-smi info` 与所用 torch_npu 的设备信息；记录实际型号、可用设备 ID、状态及与需求目标的关系，不拿需求当检测结果 |
| CANN/编译器 | 已生效的 `ASCEND_HOME_PATH`、CANN 版本、bisheng/g++ 路径；核对当前 checkout 的要求与所选 SoC 映射 |
| Python/依赖 | 记录 Python 环境和版本、torch/torch_npu 的版本与导入；核对当前 pyproject/uv.lock/requirements 和示例依赖，不能盲目升级或重装 |
| 构建工具 | CMake、build/setuptools/wheel；直调示例要求 CMake ≥ 3.16，保留其新 CMake 链接兼容设置 |
| 仓库资产 | 记录候选源码目录、任务目录、已有 pytest/评测入口与算子文档线索；不把一次快照当作以后永久现状 |
| Blaze 源码依赖 | Blaze 路线能力调查依赖 ops-tensor 源码；检查依赖目录或缓存中是否可用，缺失时报告准备项，不在检查中静默拉取 |

仓库专用依赖按已选 `ops-direct-invoke-repo-guide` 和工程检查。
