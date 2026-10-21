# pypto-op-orchestrator 快速开始

先准备 Node.js 20.11+、Python 3（含 PyYAML）、Agent 客户端与 PyPTO/NPU 运行环境，
详见 [环境要求](README.md#环境要求)。以下以 OpenCode / cannbot CLI 为例；使用
Codex 或 Claude Code 时，将命令中的 `opencode` 换成 `codex` 或 `claude`。

## 安装

普通用户：在目标工作区用 npx 安装（推荐）：

```bash
cd /path/to/your-workspace
npx @cannbot-plugin/cannbot@latest install pypto-op-orchestrator --tool opencode
```

开发者：克隆源码后用 init 安装：

```bash
git clone --recurse-submodules --shallow-submodules https://gitcode.com/cann/cannbot.git
cd cannbot/plugins-official/pypto-op-orchestrator
bash init.sh project opencode /path/to/your-workspace
```

两种方式都会在安装时克隆 cannbot-skills 依赖仓并把 pypto Skills/hooks 软链或装配进
目标工作区，需要网络。装配细节见 [安装详解](README.md#安装详解)。

## 触发方式总览

本插件有两条 agent flow，提示词写法（模板 1 / 模板 2）在两条 flow 中通用：

| 触发方式 | 适用场景 | 入口 |
|---|---|---|
| 方式一：自然语言调用（交互式客户端） | 在已安装插件的工作区里边对话边开发 | 入口 skill `pypto-op-orchestrator` 语义分流 |
| 方式二：无头（headless）调用 | 命令行 / CI 脚本化触发 | 直接调用 harness 编排器 `orchestrator.py` |

## 方式一：自然语言调用（交互式客户端）

在已安装本插件的工作区启动客户端，直接对话即可：

```bash
cd /path/to/your-workspace
opencode        # 或 cannbot等工具
```

交互链路：自然语言 → 入口 skill `pypto-op-orchestrator` 命中分流 →
`workflow-orchestrator` skill 接管，收集四项输入（workflow.yaml，默认
`.cannbot/plugins/pypto-op-orchestrator/workflows/pypto-op-develop.yaml`；
work_dir；provider；prompt）并向你确认 → 确认后经 `link_agent_config.py` 接线并
后台拉起 harness 工作流，按 yaml 节点逐任务派生 `general-executor` /
`general-verifier` 子 agent 执行。

### 模板 1：直接提示词

```text
请生成一个 pypto 实现的 relu 算子
```

**`pypto` 关键词是入口 skill 语义分流的命中点**：入口 skill 的 description 以
"生成/开发/实现 PyPTO 算子"为触发场景，提示词只要含 `pypto` + 算子开发意图即可
稳定命中，无需点名 skill 名或工作流名。

### 可选补充：目标细化提示词

极简提示词即可跑通全流程；未给出的要素由工作流的 `prepare-case` 节点按语义自动填充（算子名
自动拟定、`device_id` 缺省按 `TILE_FWK_DEVICE_ID` 或默认设备、无硬性性能目标）。
需要显式约束时，在提示词中补充以下要素（格式不限，自然语言即可）：

- 功能描述：算子语义 / 数学公式（如 `out[i] = max(x[i], 0)`）；
- 输入输出：name、shape、dtype（如 `输入 x0, shape=[16,16384], dtype=float32`）；
- 精度要求：rtol / atol（可缺省）；
- 性能目标：`perf_target_us`（硬性目标，单位 us）、`tune_rounds`（调优轮次，默认 3）；
- 设备：`device_id=<N>`。

示例：

```text
请生成一个 pypto 实现的 relu 算子。
算子语义: out[i] = max(x[i], 0)，逐元素 ReLU
输入: input0, shape=[1024,1024], dtype=float32
输出: output0, shape=[1024,1024], dtype=float32
精度要求: rtol=1e-3, atol=1e-3
性能目标: perf_target_us=2.85, tune_rounds=3
device_id=0
```

### 模板 2：需求写在文件里，给 AI 路径

需求较长或需要复用时，可以把需求写成文件，在提示词里给出路径。完整输入文件样例见
[example/relu/](example/relu/)（自包含的 ReLU 用例输入：

- `REQUIRE.md`：算子需求文档（功能描述、shape/dtype、容差、性能目标、接口约定）
- `task_desc.py`：PyTorch Golden参考实现（可选）

```text
请按照 <路径>/example/relu/REQUIRE.md 生成一个 pypto 实现的 ReLU 算子
<路径>/example/relu/task_desc.py 是算子的gloden，可参考
```

`prepare-case` 节点检测到既有 `REQUIRE.md` 时走 `--from-require` 通路，直接以其为
需求输入。

### 对话中触发独立调优

算子开发与精度验证已完成（已有 `<op>_impl.py` + `test_<op>.py` + 精度证据），
只想做性能调优时，直接在对话里说明调优意图即可，入口 skill 会分流到仅调优工作流
`pypto-op-tune.yaml`（而不是完整开发流程）：

```text
请对 <算子产物目录> 下的 pypto relu 算子做性能调优，目标 2.85us，device_id=0
```

提示词要素：算子产物目录（必填，调优对象）、性能目标 `perf_target_us`、设备号
`device_id`（缺省按 `TILE_FWK_DEVICE_ID` 或默认设备）、可选调优轮次
`tune_rounds`。实证链路：入口 skill 命中 → `workflow-orchestrator` 接管并确认
四项输入（workflow.yaml 正确选为 `pypto-op-tune.yaml`）→ 确认后拉起调优工作流
（`tune-preflight` 校验前置产物 → `stage7-tune`）。产物目录不存在或前置产物不齐时，
入口会在确认阶段指出，不会盲目启动。无头等价命令见方式二场景三。

## 方式二：无头（headless）调用

不经过交互客户端，直接调用 harness 编排器。安装态下 yaml 位于
`<工作区>/.cannbot/plugins/pypto-op-orchestrator/workflows/`。

### 场景一：直接提示词触发（对应模板 1）

模板 1 的提示词同样可用于 `--prompt`：

```bash
python3 <cannbot仓>/harness/workflow-orchestrator/scripts/orchestrator.py \
  --yaml <工作区>/.cannbot/plugins/pypto-op-orchestrator/workflows/pypto-op-develop.yaml \
  --work-dir <工作区>/.cannbot/relu/pypto-op-orchestrator \
  --provider cannbot \
  --prompt "请生成一个 pypto 实现的 relu 算子"
```

`--prompt` 也可换成目标细化写法（要素见方式一的可选补充）。`prepare-case` 节点
会把需求文本落盘为 `custom/<op>/REQUIRE.md` 并合成 `prepared_case.json`
（`mode: "interactive"`）。预期产物：`custom/<op>/` 下的 SPEC.md、golden、
DESIGN.md、`<op>_impl.py`、test、`<op>_tuning_report.md` 等全流程产物，
Stage 1-7 全 completed。

### 场景二：需求文件触发（对应模板 2）

调用方在触发前把三个产物预写到 `$OP_DIR`（即 `<work_dir>/custom/<op>/`），
输入文件写法参考 [example/relu/](example/relu/)：

| 产物 | 内容 |
|---|---|
| `REQUIRE.md` | 算子需求文档（格式由调用方自定，插件不解析） |
| `task_desc.py` | 参考用例（输入生成 + 参考 Model） |
| `gen_prompt.md` | 用例事实与桥接约定（内容由调用方负责，插件不渲染） |

随后无头触发，`--prompt` 携带用例事实（格式不限，插件由节点 agent 按语义解析）：

```bash
# 1. 准备输入
mkdir -p <work_dir>/custom/ReLU
cp <插件目录>/example/relu/{REQUIRE.md,task_desc.py,gen_prompt.md} <work_dir>/custom/ReLU/

# 2. 无头触发
python3 <cannbot仓>/harness/workflow-orchestrator/scripts/orchestrator.py \
  --yaml <工作区>/.cannbot/plugins/pypto-op-orchestrator/workflows/pypto-op-develop.yaml \
  --work-dir <work_dir> --provider cannbot \
  --prompt "op_name=ReLU op_dir=<work_dir>/custom/ReLU device_id=0 perf_target_us=2.85 tune_rounds=3"
```

`prepare-case` 节点只做核对：`prepare_case.py --verify` 确认三产物存在且非空后合成
`prepared_case.json`（模式字段记为 `staged`，即需求文件预置）。预期产物：同场景一的全流程产物，外加按
gen_prompt.md 桥接契约产出的 `<op>_pypto_impl.py`（ModelNew）；注入硬性
`perf_target_us` 时 Stage 7 达标断言生效（达标或硬件极限论证均判 pass，详见
[Stage 7 性能达标与自动重试](README.md#stage-7-性能达标与自动重试)）。

### 场景三：已有产物工作区的独立调优

算子开发与精度验证已完成（`<op>_impl.py` + `test_<op>.py` + 精度证据齐备，可来自
本插件的一次生成，也可来自其他任何流程），只想跑性能调优时，换用仅调优工作流：

```bash
python3 <cannbot仓>/harness/workflow-orchestrator/scripts/orchestrator.py \
  --yaml <工作区>/.cannbot/plugins/pypto-op-orchestrator/workflows/pypto-op-tune.yaml \
  --work-dir <工作目录> --provider cannbot \
  --prompt "op_dir=<算子产物目录> device_id=<N> perf_target_us=<F> tune_rounds=<I>"
```

`tune-preflight` 节点校验环境与前置产物（精度证据缺失时重跑 `test_<op>.py` 取证；
MEMORY.md 缺失时按模板生成最小占位），随后进入 `stage7-tune`。预期产物：
`<op>_tuning_report.md`、`<op>_tune_result.json`（含 `optimized_us` 与
`hw_limit_reached`）与 Stage 7 completed 状态。

## 运行中查看进度

工作流状态由 harness 维护在 `<工作目录>/.workflow/status.json`，每个节点记录
status（pending/running/executed/verifying/pass/fail）、重试次数与会话位置：

```bash
python3 -c "import json; s=json.load(open('<工作目录>/.workflow/status.json')); \
print('\n'.join('%s: %s (retries=%s)' % (k, v['status'], v.get('retries', 0)) \
for k, v in s['tasks'].items()))"
```

各节点的 agent 会话记录归档在 `.workflow/` 下；算子侧的阶段进度另见
`custom/<op>/.orchestrator_state.json`（Stage 1-7 状态，由 state_transition hook
维护）。

## 失败恢复与重跑

- **中断/崩溃恢复**：用同一条命令重跑即可（同一 `--yaml`、同一 `--work-dir`，
  **不要再传 `--prompt`**），编排器检测到已有 `status.json` 后自动恢复执行，瞬态
  状态（running/verifying）会被重置后继续。
- **节点失败**：编排器按节点的 `max_retries` 自动重试，重跑 prompt 携带上轮失败
  摘要；无需人工干预。
- **重试耗尽**：工作流整体失败退出。修复输入或环境后，用同一命令（不带
  `--prompt`）从失败点续跑；需要推倒重来时换一个新的 `--work-dir` 并重新带上
  `--prompt`。

## 运行产物说明

约定工作目录为 `<工作区>/.cannbot/<任务名>/pypto-op-orchestrator/`，一次运行的
典型内容：

```text
<工作目录>/
├── .workflow/                 # harness 状态：status.json、会话归档（只读，勿手改）
├── .cannbot/dependencies/     # 安装时克隆的 cannbot-skills 依赖仓
├── .agents/skills/            # pypto Skills 软链
├── env.json                   # preflight 定位记录（cannbot_root / device_id）
├── prepared_case.json         # 用例输入记录（后续节点的唯一权威输入）
└── custom/<op>/               # 算子产物目录（$OP_DIR）
    ├── REQUIRE.md             # 需求文档（from-desc 落盘或调用方预写）
    ├── SPEC.md / API_REPORT.md / DESIGN.md / eval/
    ├── <op>_golden.py / GOLDEN_PERF_REPORT.md
    ├── <op>_impl.py / README.md / MEMORY.md / test_<op>.py
    ├── <op>_pypto_impl.py     # 仅需求文件预置场景（ModelNew 桥接产物）
    ├── <op>_tuning_report.md  # 调优报告（硬件极限放行时含论证节）
    ├── <op>_tune_result.json  # 性能机检数据（optimized_us / target_met / hw_limit_reached）
    └── .orchestrator_state.json  # Stage 1-7 阶段状态
```

这些运行产物不随插件入库（插件 `.gitignore` 已排除 `.cannbot/`）。
