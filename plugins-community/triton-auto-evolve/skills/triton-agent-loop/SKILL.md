---
name: triton-agent-loop
description: Multi-Agent 流程控制 Skill。Use when 需要对 Triton Ascend 算子进行多轮迭代优化，并要求主 Claude Code Agent 只负责 round 间调度、每轮由独立子 CLI 执行 Phase 0-8。算法仅限 gene-fusion / mcts / naive 三选一；任何算子请求（含单次生成）都走多轮调度，禁止单 skill 旁路流程（triton-op-coding 等只能由子 agent 在轮内调用）。
---

# triton-agent-loop

Multi-Agent 流程控制 Skill。在 Triton Ascend 算子多轮优化中，主 Claude Code Agent 负责 round 间调度，每轮通过 `dispatch_round.py` 启动独立的子 Claude Code CLI 执行 Phase 0-8。

## 职责

- **主 Orchestrator**：
  - Round 生命周期管理（初始化、恢复、停止）
  - 为每轮决定 `round_strategy` / `analysis_policy` / `hypothesis` / `direction`
  - 生成 `task_manifest.json`
  - 调用 `dispatch_round.py` 启动子 CLI
  - 解析 `round_result.json`
  - 执行 C1/C2 停止/继续判定（C3/D4 已下沉到 Strategy 内部处理）
  - 调用 `transition_next_round.py` 准备下一轮
  - 所有 round 结束后选择全局最优代码并输出最终报告
  - 经验归档（写回 cannbot-knowledge 知识库 `$KB_ROOT`）

- **子 Per-Round Worker**：
  - 读取 `task_manifest.json`
  - 在独立上下文中执行 Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
  - 产出当前 round 的全部产物（`summary.json`、`report.md`、`*_generated.py`、`output/` 等）
  - 写入 `round_result.json` 后退出

## 关键边界

- **入口唯一**：所有 Triton Ascend 算子请求（含"单次生成/快速出一版"）只走本多轮调度流程，算法 gene-fusion / mcts / naive 三选一；禁止以 triton-op-coding / triton-op-designer / triton-latency-optimizer 等单 skill 流程响应用户，禁止向用户提供其他流程选项菜单；轮数用 `config.json` 的 `max_rounds` 控制。
- 子 agent **禁止**读取历史 `round_index.json`、禁止做跨 round 判定。
- 子 agent **禁止**更新 `round_index.json`、项目级经验模板、`.triton-agent/state-{op_name}-{algorithm}-{run_tag}.json`。
- 所有停止/继续/方向切换判定保留在主 agent。

## 核心脚本

- `dispatch_round.py`：生成 manifest、启动子 CLI、等待并解析 `round_result.json`
- `orchestrator_loop.py`：主调度循环参考实现
- `transition_next_round.py`：原子化准备下一轮目录与状态
- `check_local_optimum.py`：局部最优检测
- `check_stop_decision.py`：停止决策门禁
- `submit_round.py`：单轮产物合同校验（Worker 模式下跳过跨 round 检查）

## 引用关系

- 主 agent 读取 `.claude/references/orchestrator-loop.md`
- 子 agent 读取 `task_manifest.json` 中 `algorithm_reference` 指向的算法规范（如 `.claude/references/algorithms/gene-fusion/round.md`、`.claude/references/algorithms/mcts/round.md`、`.claude/references/algorithms/naive/round.md`）
- 子 agent 基于算子分析、瓶颈历史与 Triton/Ascend 最佳实践自主选择优化方向，不再读取固定 pattern 目录
- 知识内容唯一来源是 cannbot-knowledge 仓克隆（`$KB_ROOT` = `<项目>/.cannbot/dependencies/triton-auto-evolve/cannbot-knowledge/knowledge`）：检索经 `knowledge-query` skill，写回经 `ops-knowledge-ingest`（Phase 6），写回限制与路径以 cannbot-knowledge 仓自身规范为准（`CONTRIBUTING.md` + `governance/specs/`）。KB 不可用时自动降级骨架模式（kb_unavailable），不影响主流程；任何 skill 目录不存知识

## 依赖 Skill

- triton-task-extractor
- triton-op-designer
- triton-op-coding
- triton-op-verifier
- triton-latency-optimizer
- triton-simulator-optimizer
- npu-arch
- triton-precision-debug
