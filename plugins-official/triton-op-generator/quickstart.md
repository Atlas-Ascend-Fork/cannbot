# triton-op-generator 快速入门

Triton-Ascend 算子代码生成与优化插件：从算子描述（PyTorch 标杆 / GPU Triton kernel）出发，端到端完成任务构建、算法设计、代码生成、精度验证、性能优化与报告归档（Phase 0-7）。

知识卡片全部由 [cannbot-knowledge](https://gitcode.com/cann/cannbot-knowledge) 知识库供给；Skill 源由 [cannbot-skills](https://gitcode.com/cann/cannbot-skills) 经 vendor submodule 供给。**安装本插件会自动完成两者的准备，用户无需感知这两个仓库。**

## 环境要求

- CANN Toolkit ≥ 9.0.0（`source /usr/local/Ascend/ascend-toolkit/set_env.sh`）
- Ascend 910 / 950 PR 系列 NPU
- Python ≥ 3.8、PyTorch ≥ 2.0、torch_npu、triton-ascend
- Node.js ≥ 18（统一安装器）
- jq（guard hook 依赖；缺失时 hook  fail-open，不影响主流程）

## 安装

### npm 安装（推荐）

```bash
npx @cannbot-plugin/cannbot@latest install triton-op-generator --tool claude
```

### 源码安装

```bash
git clone --recurse-submodules --shallow-submodules https://gitcode.com/cann/cannbot.git
cd cannbot/plugins-official/triton-op-generator
bash init.sh project claude          # 安装到当前项目；--tool 可选 opencode/codex/trae/dsh
```

安装会自动完成：

1. **Skills 安装**：从 `vendor/cannbot-skills` submodule 软链 8 个 triton 系列 Skill + `knowledge-query` / `ops-knowledge-ingest` 到目标项目的工具 skills 目录（npm 安装为复制）；
2. **知识库自举**：浅克隆 cannbot-knowledge 到 `<项目>/.cannbot/dependencies/triton-op-generator/cannbot-knowledge`（断网/离线时告警跳过，agent 以骨架模式运行）；重装时 `git pull --ff-only` 刷新。检索索引 `knowledge/search/okf.index.json` 不在安装期构建，而是在**第一次 `knowledge-query` 检索时惰性构建**（约 50s、7000+ 张卡、约 313MB），建成后即为就绪状态；
3. **guard hook 注册**（仅 claude 工具）：向 `.claude/settings.json` 注册 PreToolUse 基线保护 hook；
4. **主提示词写入**：AGENTS.md 内容以标记块写入项目 `CLAUDE.md`（claude）或 `AGENTS.md`（其他工具）。

安装控制：

| 需求 | 方式 |
|---|---|
| 锁定 cannbot-skills 版本 | `init.sh project claude --skills <SHA>` 或 `--skills <本地 worktree 路径>` |
| 跳过知识库克隆（离线环境） | `CANNBOT_SKIP_DEPENDENCY_REPOS=1 bash init.sh project claude` |
| 使用自己的知识库副本 | 设置 `CANNBOT_KNOWLEDGE_ROOT=<path>` 指向其 `knowledge/` 子目录 |

## 使用

安装完成后在项目根目录启动客户端，直接描述任务：

```
生成一个 Triton-Ascend 框架的 softmax 算子实现，ASCEND_RT_VISIBLE_DEVICES=1
```

三种输入模式：

- **Mode A（标准 torch 标杆）**：提供 PyTorch 参考实现 `.py`（单 case 自动扩展多 shape；含 `get_input_groups` + 同名 `.json` 为多 case 原样透传）；
- **Mode A 优先级 1**：同时提供 torch 标杆 + GPU Triton kernel（kernel 作参考实现，可提供 `gpu_perf.csv` 对比）；
- **Mode B（仅 GPU kernel）**：提供 GPU Triton kernel `.py` + 同名 `.pt`（含 `input_data`，可选 `gpu_output`）。

产出：`triton_ascend_output/op_{name}_{ts}_{rid}/` 下的 `{op_name}_generated.py`（最终代码）、`report.md`、`summary.json`、`session.md`。

## 可用技能

| Skill | 职责 |
|---|---|
| triton-task-extractor | 任务文件构建（单/多 case） |
| triton-op-designer | 算法草图设计 |
| triton-op-coding | kernel 代码生成与修复 |
| triton-op-verifier | 精度验证 + 性能测试（verify.py / benchmark.py / freeze_baseline.py） |
| triton-latency-optimizer | 延迟优化（33 优化点扫描） |
| triton-precision-debug | 精度对齐调试 |
| triton-simulator-optimizer | msprof 采集与瓶颈诊断 |
| npu-arch | Ascend NPU 架构知识 |
| knowledge-query | cannbot-knowledge 知识检索 |
| ops-knowledge-ingest | 经验知识沉淀路由（Phase 7 写回 runbooks/） |

## FAQ

- **知识库克隆失败**：检查网络；离线环境用 `CANNBOT_SKIP_DEPENDENCY_REPOS=1` 安装，agent 仍可运行（仅知识增强缺失）。
- **如何确认知识库就绪**：`python3 .claude/skills/knowledge-query/scripts/knowledge_query.py discover` 应输出 selected root。
- **旧版（cannbot-skills 仓内插件）迁移**：旧版的 `.claude/template/` 经验模板已迁移为 cannbot-knowledge 约束卡（`knowledge/ops/triton/guides/constraints/`），由知识库统一维护。
