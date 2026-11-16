# PyPTO-Pro 算子开发与调优快速入门

`pypto-pro-op-orchestrator` 用于 PyPTO-Pro 算子的开发、精度验证、调试和性能调优。

## 准备环境

- Git、Python 3.10+ 和 Node.js 20.11+；运行测试需要 pytest，npm 安装还需要 npm/npx。
- 可用的昇腾 NPU，以及版本配套的 CANN、驱动、固件、PyTorch 和 `torch_npu`。
- PyPTO 环境：优先使用 10 月 30 日后的源码编译版本；10 月 30 日前的版本可能存在兼容性问题，影响算子生成和性能。参考[源码仓库](https://gitcode.com/cann/pypto)和[编译安装指南](https://pypto.gitcode.com/install/build_and_install.html)。
- 已安装并配置好所选客户端。

## 安装与启动

在算子开发环境的终端中进入项目目录；新项目可先创建工作区：

```bash
mkdir -p pypto-workspace
cd pypto-workspace
```

展开对应客户端，在当前工作区选择一种方式安装，然后启动客户端。

<details>
<summary>OpenCode</summary>

**npm 安装**

```bash
npx @cannbot-plugin/cannbot@latest install pypto-pro-op-orchestrator --tool opencode
```

**源码安装**

```bash
git clone --recurse-submodules --shallow-submodules \
  https://gitcode.com/cann/cannbot.git ../cannbot
bash ../cannbot/plugins-community/pypto-pro-op-orchestrator/init.sh \
  project opencode "$PWD"
```

**启动**：运行 `opencode`。

</details>

<details>
<summary>Claude Code</summary>

当前 npm 安装可能有 Skill 加载问题，优先使用源码方式。

**npm 安装**

```bash
npx @cannbot-plugin/cannbot@latest install pypto-pro-op-orchestrator --tool claude
```

**源码安装**

```bash
git clone --recurse-submodules --shallow-submodules \
  https://gitcode.com/cann/cannbot.git ../cannbot
bash ../cannbot/plugins-community/pypto-pro-op-orchestrator/init.sh \
  project claude "$PWD"
```

**启动**：运行 `claude`。

</details>

<details>
<summary>Codex</summary>

**npm 安装**

```bash
npx @cannbot-plugin/cannbot@latest install pypto-pro-op-orchestrator --tool codex
```

**源码安装**

```bash
git clone --recurse-submodules --shallow-submodules \
  https://gitcode.com/cann/cannbot.git ../cannbot
bash ../cannbot/plugins-community/pypto-pro-op-orchestrator/init.sh \
  project codex "$PWD"
```

**启动**：运行 `codex`。

</details>

<details>
<summary>CodeArts</summary>

**源码安装**

```bash
git clone --recurse-submodules --shallow-submodules \
  https://gitcode.com/cann/cannbot.git ../cannbot
bash ../cannbot/plugins-community/pypto-pro-op-orchestrator/init.sh \
  project codearts "$PWD"
```

**启动**：运行 `codearts`，或用 CodeArts IDE 打开工作区并进入智能体对话。

</details>

## 算子开发与调优

### 算子开发

```text
请使用 PyPTO-Pro 开发一个 softmax 算子，完成精度验证和性能测试。

输入：连续存储的二维 float16 张量，行数为 1～32，列数为 128～4096。
功能：沿最后一维计算 softmax，支持尾块。
输出：形状、数据类型和布局与输入相同。
精度要求：与 CPU 上的 FP32 参考结果比较，rtol=1e-3，atol=1e-3。
交付目录：./custom/softmax/。

完成后列出交付文件，并说明测试结果、性能数据和使用方式。
```

可补充设备信息、参考实现、测试用例和性能目标。

### 性能调优

```text
请优化 ./custom/softmax/ 中的 PyPTO-Pro 算子，
沿用现有测试用例、精度标准和性能测量方式。

完成后说明优化前后的性能、精度回归结果和交付位置。
```

### 可选模式

- **多 agent 模式**：在提示词中加入“启用多 agent 模式”，由主 agent 协调子 agent 分工完成任务。
- **Coverage 模式**：在提示词中加入“启用 coverage 模式，使用内置性能知识卡片”，检查已知优化方向并报告覆盖结果和未完成项。

## 交付产物

以下为 `pypto-gym` 的 Python/JIT 源码交付目录，以 `softmax` 为例：

```text
custom/softmax/
├── README.md                    # 算子说明与调用方法
├── DESIGN.md                    # 实现设计
├── RESULTS.md                   # 用例、精度与性能结果
├── op_kernel/
│   └── softmax.py               # kernel 与公开调用入口
└── tests/
    ├── test_softmax.py          # 功能与精度测试
    └── assets/
        ├── gen_golden.py        # 参考数据生成
        └── softmax_precision.py # 精度比较
```

如需保留现有目录或采用项目交付规范，请在提示词中说明。
