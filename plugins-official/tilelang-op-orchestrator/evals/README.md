# TileLang 插件 ST

本目录的 8 条 `text` 用例验证插件的路由、角色和流程说明。运行器复用
`cannbot-skills/tests/system` 框架，在独立输出目录生成配置，只发现当前新仓插件，
不修改旧仓配置，也不加载旧仓同名插件。工作流、用例正文和评测标准保持不变。

使用已安装原框架 `scripts/requirements.txt` 依赖的 Python，以及 Node.js 20+。
动态评测还需要 OpenCode 或兼容的 CANNBot 客户端，以及已配置、可用的模型服务：

```bash
python3 plugins-official/tilelang-op-orchestrator/evals/run_st.py \
  --framework /path/to/cannbot-skills/tests/system \
  --output /tmp/tilelang-st-run \
  --client cannbot \
  --model cannbot/glm-5.3
```

`--output` 必须是尚不存在的目录，保留每次运行的配置、输入版本、沙箱、会话和
JSON / JUnit / HTML 报告。ST 安装适配仅给原安装器传入当前仓库
`vendor/cannbot-skills` 的本地路径（`--skills`），不拉取或切换共享 Skill 版本；
每个沙箱检查 13 个共享 Skill 和 6 个角色均已登记。
运行器先确认实际发现路径和全部 8 个用例 ID，再运行 20 项基础检查和 8 项动态评测；
失败、跳过或少收集用例均不算通过。`REPORT_ONLY` 不用于实际测试。

可用 `--phase collect` 只验证发现和收集，`--phase basic` 运行基础检查，
`--phase eval` 运行动态评测；默认 `all`。`--workers 2` 可并行运行隔离用例。
`--eval-id 6` 可单独复跑原始用例；报告记录所选 ID，默认仍运行全部 8 条用例。
不指定 `--model` 时沿用 `EVAL_MODEL` 或 OpenCode 默认模型。
`--client` 默认 `opencode`；选择 `cannbot` 时，仅在本次输出目录创建命令映射，
原 ST 框架的运行及评审逻辑不变，系统客户端和全局配置不变。
也可用客户端的绝对路径，明确选择 PATH 中多个已安装版本中的一个。
客户端启动器仅恢复当前环境中的 Python 动态库和 CANN 路径变量，供真实硬件探测使用，
不传入额外凭据，不伪造探测结果。

这些文本用例与真实 NPU 算子编译、精度、性能及业务 ST 分别验收。
