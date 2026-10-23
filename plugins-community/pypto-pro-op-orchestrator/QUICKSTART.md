# pypto-pro-op-orchestrator 快速开始

先准备 Node.js 20.11+、Agent 客户端与可用的 PyPTO-Pro 运行环境（CANN、设备运行时与
测评环境由用户自行配置），详见 [环境要求](README.md#环境要求)。以下以 OpenCode 为例；
使用 Codex 或 Claude Code 时，将命令中的 `opencode` 换成 `codex` 或 `claude`。

## 安装

普通用户：在目标工作区用 npx 安装（推荐）：

```bash
cd /path/to/your-workspace
npx @cannbot-plugin/cannbot@latest install pypto-pro-op-orchestrator --tool opencode
```

开发者：克隆源码后用 init 安装：

```bash
git clone --recurse-submodules --shallow-submodules https://gitcode.com/cann/cannbot.git
cd cannbot/plugins-community/pypto-pro-op-orchestrator
bash init.sh project opencode /path/to/your-workspace
```

两种方式都是 project-scope 安装（init.sh 的 `project` 子命令即项目级），都会在安装时
克隆 cannbot-skills 依赖仓，把 `pypto-pro-kernel` Skill 软链到项目
`.agents/skills/pypto-pro-kernel/`，并把主 agent 提示词装配进项目根 `AGENTS.md`
（claude 客户端为 `CLAUDE.md`），需要网络。详见 [安装](README.md#安装)。

## 触发方式总览

安装后项目根 `AGENTS.md` 中的主 agent 提示词即生效，在已安装的工作区里边对话边开发
即可：

| 触发方式 | 适用场景 | 入口 |
|---|---|---|
| 方式一：自然语言对话（交互式客户端） | 在已安装插件的工作区里边对话边开发 | 项目根 `AGENTS.md` 主 agent 提示词 + `pypto-pro-kernel` Skill |
| 方式二：无头（headless）调用 | 命令行 / CI 脚本化触发 | `opencode run "<提示词>"` |

## 方式一：自然语言对话（交互式客户端）

在已安装本插件的工作区启动客户端，直接对话即可：

```bash
cd /path/to/your-workspace
opencode        # 或 cannbot 等工具
```

### 模板 1：极简提示词

```text
请生成一个 pypto-pro 实现的 sigmoid 算子
```

`pypto-pro` 关键词 + 算子开发意图即命中主 agent 的职责描述；主 agent 随后加载
`pypto-pro-kernel` Skill 并按其技术流程执行，缺失的需求细节会在规划阶段向你澄清或
按语义补定。

### 可选补充：需求细化提示词

极简提示词即可启动；需要显式约束时，在提示词中补充以下要素（格式不限，自然语言
即可）：

- 算子需求信息：算子语义 / 数学公式、输入输出的 name/shape/dtype、精度容差；
- 性能目标：目标耗时（us）或相对 baseline 的加速比，以及调优轮次期望；
- 性能采集方式要求：计时方法（如同一测量程序内 AB/BA、预热与重复次数）、设备与
  设备锁要求、profiling 工具约束；
- benchmark 测评要求：用指定 benchmark 框架/测评脚本做正确性与性能评测，明确
  用例来源、通过判据与结果落盘位置。

完整提示词模板样例（以 sigmoid 算子为例）：

```text
请生成一个 pypto-pro 实现的 sigmoid 算子。

【算子需求信息】
- 算子语义: out[i] = 1 / (1 + exp(-x[i]))，逐元素 sigmoid
- 输入: input0, shape=[1024,1024], dtype=float32
- 输出: output0, shape=[1024,1024], dtype=float32
- 精度要求: 与 PyTorch 参考实现对比, rtol=1e-3, atol=1e-3

【性能目标】
- 目标耗时: <= 2.0 us（device_id=0，Ascend A5）
- 调优期望: 多轮优化直至达标或论证硬件极限

【性能采集方式要求】
- 同一测量程序、同一进程内完成 AB/BA 对比，先预热再计时，取多次重复的最优/均值
- 计时与 profiling 期间独占设备（遵守项目设备锁），数值错误的版本不参与性能比较

【benchmark 测评要求】
- 用 <benchmark 仓/脚本路径> 对本算子做正确性 + 性能评测
- 正确性以全部用例 PASS 为准；性能以 benchmark 输出的实测耗时为准
- 测评原始结果与报告落盘到 <结果目录>，并在交付说明中给出结论
```

### 多 agent 模式

默认由主 agent 自主执行、按需调用 subagent。需要严格的多 agent 分工时，在提示词中
显式开启：

```text
请生成一个 pypto-pro 实现的 sigmoid 算子。本次启用多 agent 模式。
```

主 agent 会先完整阅读 `multi-agent-workflow.md`，随后只做判定、派工和审核：写文件、
跑命令、环境核对全部派给对应 subagent。仅解释、引用或否定该模式不会启用它；要求退出
时主 agent 会先安全停止进行中的子任务再恢复默认执行方式。

## 方式二：无头（headless）调用

不进入交互会话，用客户端的 headless 形态在已安装的工作区直接给提示词：

```bash
cd /path/to/your-workspace
opencode run "请生成一个 pypto-pro 实现的 sigmoid 算子。<可选的需求细化要素，同方式一>"
```

提示词写法与方式一完全相同（模板 1 / 完整模板均可）。多 agent 模式同样在提示词中
显式声明开启。

## 触发后流程

1. 主 agent 加载 `pypto-pro-kernel` Skill（`.agents/skills/pypto-pro-kernel/`），
   技术流程、执行顺序与验收条件以该 Skill 及其参考文档为准；
2. 需求与验收梳理：缺失要素向你澄清或按语义补定，确定验收标准；
3. 按 Skill 流程完成实现、正确性验证与性能优化；启用多 agent 模式时，上述具体工作
   由 planner/coder/verifier/debugger/optimizer/tool 分工执行，主 agent 审核每步
   返回后再派下一任务；
4. 性能优化按轮推进：一轮一个连贯优化思路，含正确性检查与完整性能对比；不达标且
   无提升空间时，按 Skill 要求给出硬件极限论证而非虚报达标；
5. 交付：算子实现、测试与验证证据、性能数据与调优结论，落盘位置按 Skill 流程与
   项目配置约定。

## 产物说明

典型产物（具体目录以 `pypto-pro-kernel` Skill 与项目配置为准）：

- 算子 kernel 实现与调用/测试代码；
- 正确性验证证据（与参考实现的对比结果、测试运行记录）；
- 性能数据（计时原始结果、AB/BA 对比）与调优报告（含达标结论或硬件极限论证）；
- benchmark 测评输出（若提示词要求）。

## 失败恢复与重跑

- **会话中断**：重新打开客户端继续对话即可；主 agent 会基于已落盘的代码、验证记录
  与摘要继续，不从头重做。
- **单步失败**：原因已明确的修复交 coder；原因不明的先交 debugger 定位再修复复查；
  验证失败不会由 verifier 自行改码。
- **上下文接近阈值**（默认 384K tokens）：subagent 在安全点返回并说明交接；主 agent
  审核后携摘要（需求、当前代码与基准版本、验证进度、未解决问题、剩余预算）开新
  会话继续，实验历史与预算不重置。
- **推倒重来**：明确告知主 agent 放弃当前候选；已验证的最佳版本可恢复，数值错误的
  版本不参与性能比较。
