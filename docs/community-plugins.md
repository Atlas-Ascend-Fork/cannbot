# 社区插件

社区插件属实验孵化性质：在社区中持续孵化演进，由贡献者看护；经充分使用验证并满足 SIG [准入标准](https://gitcode.com/cann/cannbot-skills/blob/master/docs/CONTRIBUTING.md)后，可申请升级为官方插件。本页是社区插件的清单与介绍；各插件的完整安装与使用步骤见其目录内的 `quickstart.md` 或 `README.md`，贡献入口见 [plugins-community/](../plugins-community/)。

| 插件 | 场景 |
|------|------|
| [`ascendc-port-orchestrator`](../plugins-community/ascendc-port-orchestrator/) | AscendC 算子跨代际移植与反向算子生成 |
| [`model-train-precision-diagnose`](../plugins-community/model-train-precision-diagnose/) | PyTorch on Ascend NPU 训练精度异常诊断 |
| [`tilelang2ascendc-ops-generator`](../plugins-community/tilelang2ascendc-ops-generator/) | Ascend C 算子自动生成（双路径设计表达 + AscendC 转译） |
| [`triton-auto-evolve`](../plugins-community/triton-auto-evolve/) | Triton-Ascend 算子多轮自动优化 |
| [`triton-optimizer`](../plugins-community/triton-optimizer/) | Triton Ascend NPU 算子优化与 PyTorch 算子转换 |

## ascendc-port-orchestrator

面向 AscendC 算子的移植编排插件，提供三个入口：

- **跨代际移植**（`ascendc-cross-gen-port`）：把已有算子移植到不同代际目标架构（如 Ascend910C/V220 → Ascend950PR/V300，或 → Atlas 300I Duo / Ascend310P3）。目标架构用自然语言指定，来源架构由代码分析自动识别。
- **轻量迁移**（`ascendc-cross-gen-migration`）：无 golden 输入或希望基于已有算子修改后快速迁移时使用，全程免交互自动推进。
- **正向→反向生成**（`ascendc-backward-gen`）：由可微 PyTorch 正向规格生成并验证 AscendC 反向（梯度）算子。

安装见 [quickstart.md](../plugins-community/ascendc-port-orchestrator/quickstart.md)。

## model-train-precision-diagnose

定位 PyTorch on Ascend NPU 训练过程中的精度异常：先确认复现条件与运行环境，再缩小问题范围、定位首个差异或异常，最后由独立 Reviewer 复核证据闭环，输出 Node / Rank / Step / Module / API / Tensor 级证据。

### 适用症状

| 症状 | 是否依赖外部标杆 |
| --- | --- |
| 正向 Loss、Logits 或激活出现有限值偏差 | 是 |
| 正向基本一致，反向梯度或 GradNorm 出现有限值偏差 | 是 |
| 前向、反向、Optimizer 或 Scaler 出现 NaN / Inf / Overflow | 否 |
| 固定输入、权重、Seed 与确定性设置后，两次运行仍不一致 | 否 |

### 不适用

推理精度、OOM、性能优化、非 PyTorch 训练、Checkpoint 续训轨迹对齐。

### 安装

```bash
npx @cannbot-plugin/cannbot@latest install model-train-precision-diagnose \
  --tool opencode --target /path/to/training-project
```

源码安装与各客户端（OpenCode / Codex / Claude Code / TRAE / DSH）参数见 [quickstart.md](../plugins-community/model-train-precision-diagnose/quickstart.md)。

## tilelang2ascendc-ops-generator

Ascend C 算子自动生成：双路径（ops-direct-invoke / TileLang）设计表达与 AscendC 转译优化，端到端完成算子开发。简单算子（Index / Gather / Scatter 等）走 ops-direct-invoke 工作流（Architect 设计 → Developer 实现 → Reviewer 审查）；复杂算子（Attention / MatMul / Norm / Sort 等）走 TileLang 设计表达 → AscendC 转译，内置 7 Phase 端到端工作流（含知识演进闭环）。

前置条件：Python ≥ 3.8、PyTorch ≥ 2.0、tilelang-ascend、CANN Toolkit（建议 ≥ 9.0.0）及可用 NPU 设备（Ascend 910 / 950 PR 等）。

安装（当前面向 Claude Code）：

```bash
cd plugins-community/tilelang2ascendc-ops-generator && bash init.sh project claude
```

各客户端安装参数与使用方式见 [quickstart.md](../plugins-community/tilelang2ascendc-ops-generator/quickstart.md)。

## triton-auto-evolve

Triton-Ascend 算子多智能体优化：主 Agent 多轮调度，每轮在隔离上下文中执行完整的优化流程（Phase 0-8），最终统一判定停止并输出全局最优结果。

安装（当前面向 Claude Code）：

```bash
cd plugins-community/triton-auto-evolve && bash init.sh project claude
```

使用方式与配置见 [README.md](../plugins-community/triton-auto-evolve/README.md)。

## triton-optimizer

Triton Ascend NPU 算子优化与转换工作流：优化入口 `triton-npu-optimize` 按 canonical baseline + 多轮 round 迭代，经过正确性与性能门禁推进；转换入口 `triton-npu-convert` 以 spec-first 方式将 PyTorch 算子转换为 Triton Ascend NPU 实现并完成验证。16 个 Skills 自包含于插件内，附带 workflow 状态 hooks（`.helix/`，仅 Claude Code 生效）。

安装（hooks 当前面向 Claude Code）：

```bash
cd plugins-community/triton-optimizer && bash init.sh project claude
```

各客户端安装参数与使用方式见 [quickstart.md](../plugins-community/triton-optimizer/quickstart.md)。
