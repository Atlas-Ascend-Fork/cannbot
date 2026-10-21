# example/relu — ReLU 输入样例

一组自包含的 ReLU 算子**输入侧**文件（算子语义 `out[b,d] = max(x[b,d], 0)`，
P0 shape `[16, 16384]`，float32），演示"把需求/提示词写成文件、给 AI 路径
去读取"的用法。

| 文件 | 角色 | 说明 |
|---|---|---|
| `relu/REQUIRE.md` | 输入（需求） | 算子需求文档：功能描述、输入输出 shape/dtype、精度容差、性能目标、接口约定 |
| `relu/task_desc.py` | 输入（用例） | PyTorch 参考实现 + 输入生成（`Model` / `get_inputs()` / `get_init_inputs()` 两段式调用约定）、性能基线 |
| `relu/gen_prompt.md` | 输入（用例事实与桥接约定） | 调用方撰写的用例事实与桥接约定（需求文件预置的三个预写产物之一，内容格式自由） |
| `relu/prompt.md` | 触发提示词样例 | 调用方如何把用例事实写进提示词、并给出 `$OP_DIR` 路径让 agent 读取；格式无关化，仅为写法示范 |

注意：`SPEC.md` / `API_REPORT.md` / `DESIGN.md` 等是工作流运行中由节点 agent
**生成**的产物，不是输入，故未收录。

## 用法 1：交互式（interactive / from-require）

在已安装本插件的工作区启动客户端，直接把需求文件路径告诉 Agent：

> 请按照 <本目录>/relu/REQUIRE.md 生成一个 pypto 实现的 ReLU 算子

`prepare-case` 节点检测到已有 `REQUIRE.md` 时走 `--from-require` 通路，直接以其
为需求输入。

## 用法 2：无头触发（需求文件预置）

调用方先把输入文件预写到 `$OP_DIR`（即 `<work_dir>/custom/<op>/`），再无头触发，
`--prompt` 只携带用例事实（写法示范见 `relu/prompt.md`）：

```bash
# 1. 预写用例产物
mkdir -p <work_dir>/custom/ReLU
cp relu/REQUIRE.md relu/task_desc.py relu/gen_prompt.md <work_dir>/custom/ReLU/

# 2. 无头触发
python3 <cannbot仓>/harness/workflow-orchestrator/scripts/orchestrator.py \
  --yaml <工作区>/.cannbot/plugins/pypto-op-orchestrator/workflows/pypto-op-develop.yaml \
  --work-dir <work_dir> --provider cannbot \
  --prompt "op_name=ReLU op_dir=<work_dir>/custom/ReLU device_id=<设备号> perf_target_us=2.85 tune_rounds=3"
```

`perf_target_us=2.85` 取自该样例的性能基线（见 `task_desc.py` 中
`A2_PERF_BASELINE`），仅为演示硬性目标的写法；无硬性目标时省略该字段即可。
