# ops-direct-invoke-flash

Ascend C 算子开发工具 **CANNBot（Flash 版）**。从 CPU 函数、数学公式、代码片段或文本描述出发，端到端构建并验证一个高性能 Ascend NPU 核函数。

## 能力概览

完整工作流覆盖：环境探测 → 定义/设计文档 → 增量实现 → NPU 验证 → 收尾文档。

## 安装

本插件接入统一安装器。安装步骤、参数与验证方式见 [quickstart.md](quickstart.md)；此处只给最短路径：

```bash
# npx 安装（推荐）：在实际要开发算子的工程目录下执行
cd /path/to/your/operator-project
npx @cannbot-plugin/cannbot@latest install ops-direct-invoke-flash --tool opencode

# 源码安装
git clone --recurse-submodules --shallow-submodules https://gitcode.com/cann/cannbot.git
bash /path/to/cannbot/plugins-official/ops-direct-invoke-flash/init.sh project opencode /path/to/your/operator-project
```

`--tool` 可选 `opencode`、`claude`、`codex`、`trae`、`dsh`。统一安装器仅支持项目级安装。

## 使用

安装后在对应工具中触发 skill，并提供算子来源：

```
/ops-direct-invoke-flash 开发一个 Abs 算子
```

默认在算子工程的 `operators/` 目录下开发。插件自带 `add`、`mul`、`sqrt` 三个参考算子作为结构参考，随 skill 一起安装，位于 `${CLAUDE_SKILL_DIR}/operators/`。

## 快速体验

**第 1 步：拉取代码并安装到一个工作目录**

```bash
git clone --recurse-submodules --shallow-submodules https://gitcode.com/cann/cannbot.git
mkdir -p ~/flash-demo
bash cannbot/plugins-official/ops-direct-invoke-flash/init.sh project opencode ~/flash-demo
```

**第 2 步：在工作目录中打开 opencode**

```bash
cd ~/flash-demo
opencode
```

**第 3 步：输入提示词**

给出算子规格即可开始开发：

```
/ops-direct-invoke-flash 快速开发一个算子。
## 算子规格
- 公式：y = a * b + b * c - b / d
- 输入：a、b、c、d，共 4 个，逐元素（elementwise）运算，同 shape
- 输出：y
- 数据类型：float32
```
