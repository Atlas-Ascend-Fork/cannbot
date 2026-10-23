# pypto-pro-op-orchestrator

PyPTO-Pro 算子开发插件：在主会话中完成 PyPTO-Pro 算子的**开发、验证、调试与性能优化**，
按需调度 6 个专职 subagent 分工协作，最终交付算子实现、验证证据与性能报告。
安装与使用见 [QUICKSTART.md](QUICKSTART.md)。

## 功能概览

面向"给我一个 PyPTO-Pro 算子需求"到"拿到可交付算子"的完整过程：

- **开发**：依据算子需求（语义、shape/dtype、精度容差）完成 PyPTO-Pro kernel 实现，
  技术流程与验收条件由 `pypto-pro-kernel` Skill 承载；
- **验证**：与参考实现对比的正确性检查、独立复查，失败先定位再修复；
- **性能优化**：一轮一个连贯优化思路，每轮含正确性检查与完整性能对比；不达标且无
  提升空间时给出硬件极限论证而非虚报达标；
- **交付**：算子实现、测试与验证证据、性能数据与调优报告（落盘位置按 Skill 流程与
  项目配置约定）。

## 主 agent 与 subagent 分工

主 agent 负责理解需求、确定验收标准、判定每一步结果并决定下一步；默认自主执行，
需要分工时可调用以下 subagent（用户显式开启多 agent 模式后，具体工作一律派工，
主 agent 只做判定、派工和审核）：

| subagent | 职责 | 关键约束 |
|---|---|---|
| `pypto-pro-op-planner` | 梳理需求与验收标准，识别待澄清问题 | 只读分析，不落盘 |
| `pypto-pro-op-coder` | 一次实现或一次有明确依据的修复 | 不在同一会话持续排错 |
| `pypto-pro-op-debugger` | 定位一个失败边界，给证据与修复建议 | 不修改交付候选 |
| `pypto-pro-op-verifier` | 独立检查实际候选 | 只读检查，不改被检查文件 |
| `pypto-pro-op-optimizer` | 一个连贯优化思路的实现 + 正确性 + 性能对比 | 不包揽全部优化 |
| `pypto-pro-op-tool` | 环境核对、探针、编译运行、计时采集、交付整理 | 不改交付候选/验收判据/测量协议 |

## 触发方式概览

安装后在目标工作区直接对话即可，例如：

```text
请生成一个 pypto-pro 实现的 sigmoid 算子
```

也支持命令行 headless 触发与显式开启多 agent 模式。提示词模板、需求细化要素与
失败恢复见 [QUICKSTART.md](QUICKSTART.md)。

## 安装

### 环境要求

需要 Node.js 20.11+ 与已安装并配置好的 Agent CLI（目前验证的客户端为 OpenCode、
Codex、Claude Code）。运行算子开发与调优还需要用户自行配置可用的 PyPTO-Pro 环境
（CANN、设备运行时与测评环境）。

### 安装入口

```bash
# npm（npx 统一安装器）
npx @cannbot-plugin/cannbot@latest install pypto-pro-op-orchestrator --tool opencode

# 源码（init.sh 为薄壳，转发统一安装器，等同 --source 安装）
git clone --recurse-submodules --shallow-submodules https://gitcode.com/cann/cannbot.git
cd cannbot/plugins-community/pypto-pro-op-orchestrator
bash init.sh project opencode /path/to/your-workspace
```

两种方式都是 project-scope 安装（init.sh 的 `project` 子命令即项目级），需要网络：
安装时克隆 [cannbot-skills](https://gitcode.com/cann/cannbot-skills) 依赖仓，把
`pypto-pro-kernel` Skill 软链到项目 `.agents/skills/pypto-pro-kernel/`（主 agent 对该
Skill 的引用以此落点为准），并把主 agent 提示词装配进项目根 `AGENTS.md`（claude
客户端为 `CLAUDE.md`）。最短操作步骤见 [QUICKSTART.md](QUICKSTART.md)。

## 目录简介

```text
pypto-pro-op-orchestrator/
├── README.md                        # 插件介绍（本文件）
├── QUICKSTART.md                    # 安装与使用操作指南
├── AGENTS.md                        # 主 agent 提示词
├── agents/                          # 6 个 subagent 定义
├── workflows/references/            # 参考知识：多 agent 协作说明、kernel 性能原则、
│                                    #   PyPTO-Pro + A5 性能落地、同步与 Vector API 参考
├── init.sh                          # 安装入口
├── plugin-install.json              # cannbot-skills 依赖仓声明
├── plugin-sources.json              # 仓内 Skill 声明（本插件为空列表）
└── .claude-plugin/plugin.json       # 客户端插件清单
```
