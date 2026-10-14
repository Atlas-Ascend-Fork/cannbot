---
name: repo-env-check
description: 为需求对齐提供 conda/Python 与 CANN 候选，检查用户选定的开发环境并记录授权与证据；按环境组合复用有效记录。
---

# 仓库环境检查

由 PM 在当前用户会话执行，不进入节点图。只做只读发现与检查，不安装、升级或修复依赖。先为首次集中问卷提供环境候选，用户选择后再验证该组合；不把当前 shell 的默认环境作为隐式选择。

## 候选与用户选择

轻量读取已有环境记录、`conda env list` 和已知 CANN 安装位置，列明候选环境名、绝对前缀、Python 路径，以及 CANN 根路径、版本和激活脚本。无需递归扫描全机或逐一测试全部解释器。没有候选时将未知项交给调用方，与需求、环境新建及依赖修改权限合并询问；已给出的选择和授权直接沿用。

只有用户指定或明确授权选择的组合才进入正式检查。新建环境时记录目标前缀及允许的依赖版本；使用现有环境时记录允许修改的范围。检查命令在选定环境中运行：使用确认的 conda 激活方式和 CANN 脚本，显式用该解释器运行导入检查，不依赖裸 `python3` 或当前 `PATH`。激活失败、解释器或 CANN 实际路径不符时报告缺口，不自动切换另一套环境。

## 复用与路径

仓库级记录为 `<目标仓>/.cannbot/环境信息.md`。用户选定的 Python/conda、CANN、设备、开发语言及必要依赖与通过记录适用范围一致，且没有变化证据时复用；复制为本轮 `$WORK_DIR/环境信息.md`，记录原始时间及来源，运行中只读。缓存记录事实，不替代本任务的环境选择和修改授权。

空记录、失败记录、环境组合变化或当前语言超出缓存范围时，只补查相关缺项并保留原证据；在已有只读检查授权内不再询问“是否重新检查”。环境选择改变或修复超出授权时才询问受影响事项，更新发生在工作流运行前或整轮退出后。

## 首次检查清单

首次检查或缓存缺项时执行相应项目；结果及原始日志放在 `.cannbot/环境检查/`，按 [环境信息](references/环境信息.md) 记录真实结论。

| 检查项 | 方法与通过依据 |
|--------|----------------|
| 评测源码 | 定位用户指定 checkout，或 `.cannbot/dependencies/ops-direct-invoke/cann-bench/`；记录 commit，确认 direct_launch_example、目标任务格式、kernel_eval CLI 可用 |
| NPU | `npu-smi info` 与所用 torch_npu 的设备信息；记录实际型号、可用设备 ID、状态及与需求目标的关系，不拿需求当检测结果 |
| CANN/编译器 | 已生效的 `ASCEND_HOME_PATH`、CANN 版本、bisheng/g++ 路径；核对当前 checkout 的要求与所选 SoC 映射 |
| Python/依赖 | 记录 Python 环境和版本、torch/torch_npu 的版本与导入；核对当前 pyproject/uv.lock/requirements 和示例依赖，不能盲目升级或重装 |
| 所选语言的依赖 | CANNBot-DSL 须用选定解释器检查 `cannbotdsl` 与必要依赖可导入、版本满足已确认要求，并核对目标 CANN/芯片兼容要求；通用 torch/NPU 检查通过不能替代 DSL 就绪。编译与设备门禁仍由开发节点实际执行 |
| 构建工具 | CMake、build/setuptools/wheel；直调示例要求 CMake ≥ 3.16，保留其新 CMake 链接兼容设置 |
| 评测组件 | 检查 kernel_eval CLI 的 help/任务发现、`cann_bench_utils` 是否可导入及其来源；缺失时报告准备项，不在检查中静默触发安装 |
| 仓库资产 | 记录候选源码目录、任务目录、已有 pytest/评测入口与算子文档线索；不把一次快照当作以后永久现状 |

核对版本的官方快速入门要求 Python 3.10+、CANN 9.1.0+，实际依赖以当前 checkout 为准；torch/torch_npu 组合须按该版本的依赖和平台匹配。上述最低版本不等于任意版本组合都兼容，不宣称本次检查已完成 kernel 编译或设备精度验收。

不要用 `scripts/run_evaluation.sh` 作无副作用探测：它可能构建辅助组件、安装候选包并运行评测。环境准备缺项由调用方安排修复，完成后再按授权复核；不得通过禁用保护组件绕过。

## 完成条件

记录包含 checkout/commit、用户选择及确认依据、Python/conda 与 CANN 的绝对路径和激活方式、修改权限、设备、依赖、支持范围和证据。只有已验证的组合标为通过；缺依赖或新环境尚未创建时如实标为待准备，由调用方在已有授权内编排前置修复并验收后再进入依赖节点，不为可预见缺口先启动必然失败的完整图。后续源码构建、设备测试属于正常开发执行，不属于重复环境调查。

## 核对依据

已核对 cann-bench `08d519c503843bce5fd4672ffa2259abeb22fb00`；按实际 checkout 记录版本和差异。

- [docs/guide/quick_start.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/docs/guide/quick_start.md)
- [requirements.txt](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/requirements.txt)
- [scripts/run_evaluation.sh](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/scripts/run_evaluation.sh)
