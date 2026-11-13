# PyPTO 算子开发与调优快速开始

`pypto-op-orchestrator` 用于 PyPTO 算子开发、精度验证和性能调优。
部署完成后，在客户端中通过自然语言提出需求，由 Agent 执行工作流。

## 部署安装

### 环境要求

- Git、Node.js 20.11+ 和 npm/npx。
- Python 3、PyYAML 和 tmux。
- 已配置 CANN、PyPTO 和 NPU 运行环境。
- 已安装 OpenCode 1.x，并完成模型服务配置。

在已激活算子开发环境的终端中执行以下操作。

### 安装方式

选择一种方式，将插件安装到目标工作区。

**npm 安装**

```bash
mkdir -p /path/to/your-workspace
cd /path/to/your-workspace
npx @cannbot-plugin/cannbot@latest install pypto-op-orchestrator --tool opencode
```

**源码安装**

```bash
git clone --recurse-submodules --shallow-submodules \
  https://gitcode.com/cann/cannbot.git /path/to/cannbot

bash /path/to/cannbot/plugins-official/pypto-op-orchestrator/init.sh \
  project opencode /path/to/your-workspace
```

### 启动客户端

```bash
cd /path/to/your-workspace
opencode
```

后续确认任务工作目录时，使用该安装目录。

## 算子开发与调优

### 算子开发

描述算子功能、输入输出、精度要求和目标设备。例如：

```text
请使用 pypto-op-orchestrator 开发一个 relu 算子，
完成精度验证和性能调优。

工作区：当前目录。
功能：逐元素计算 y = max(x, 0)。
输入：x，shape 为 [B, 16384]，dtype 为 float32。
B 为动态 batch 维度，取值范围为 1～16，典型值为 16。
输出：y，与输入的 shape、dtype 相同。
精度要求：rtol=1e-3，atol=1e-3。
设备号：0。

完成后列出交付文件，并说明验证结果、性能数据和使用方式。
```

将设备号替换为实际可用设备。也可以提供需求文档、参考实现或测试文件，
在请求中说明文件位置及用途。

按 Agent 提示确认需求和运行信息后，工作流会完成规划、开发、验证与调优。
如有明确性能要求，可补充目标耗时（微秒）和调优轮次。

### 性能调优

完整开发流程已包含性能调优。对于已完成开发与精度验证、尚待调优的任务，
也可以单独提出调优需求：

```text
请使用 pypto-op-orchestrator，对 /path/to/custom/relu/ 中的
PyPTO relu 算子进行性能调优。

设备号：0。
调优轮次：3。
完成后说明优化前后的耗时、精度回归结果和报告位置。
```

提供本工作流的完整算子目录及已有验证记录，由 Agent 检查前置条件并确认工作区。
如有性能目标，在同一请求中补充。

运行过程中，可直接向 Agent 查询进度、询问结果。中断后回到原工作区，
请求继续原任务，并保留已有运行记录；失败时根据 Agent 报告处理。

## 交付产物

算子产物通常位于工作区的 `custom/<算子名>/`。
以 `relu` 为例，主要交付内容包括：

| 内容 | 主要文件 |
|---|---|
| 算子实现 | `relu_impl.py` |
| 参考实现与精度测试 | `relu_golden.py`、`test_relu.py` |
| 规格与设计 | `SPEC.md`、`API_REPORT.md`、`DESIGN.md` |
| 性能结果 | `GOLDEN_PERF_REPORT.md`、`relu_tuning_report.md`、`relu_tune_result.json` |
| 使用说明与开发记录 | `README.md`、`MEMORY.md` |

验证脚手架、评测适配文件等按任务需要生成。
任务结束后，查看 Agent 提供的实际交付清单、测试结果及性能数据。
如设置了性能目标，同时核对实测耗时和目标达成情况。

## 进阶使用

### 命令行运行

需要脚本化运行时，可直接调用已安装的 harness：

```bash
cd /path/to/your-workspace
WORK_DIR="$PWD"

python3 "$WORK_DIR/.agents/skills/workflow-orchestrator/scripts/orchestrator.py" \
  --yaml "$WORK_DIR/.cannbot/plugins/pypto-op-orchestrator/workflows/pypto-op-develop.yaml" \
  --work-dir "$WORK_DIR" \
  --provider opencode \
  --prompt "请开发 PyPTO relu 算子，输入为 float32[B,16384]，B 为动态 batch 维度，取值范围为 1～16，典型值为 16；输出为逐元素 max(x,0)，设备号为 0。"
```

命令在前台运行，执行信息输出到终端。
`--provider` 使用实际执行任务的 CLI 名称；使用 CANNBot CLI 时设为 `cannbot`。

仅执行性能调优时，将工作流文件改为 `pypto-op-tune.yaml`，
并在 `--prompt` 中提供算子目录及调优要求。

中断恢复时，使用相同的工作流、工作目录和 provider，
省略原命令中的 `--prompt` 及其参数。
