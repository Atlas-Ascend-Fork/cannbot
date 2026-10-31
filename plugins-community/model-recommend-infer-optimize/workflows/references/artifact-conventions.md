# 产物目录与交付件结构

违反本文件约定的产物视为未交付。判定原则：人读文档 → `docs/`；机器可读 → `data/`；算子工程 → `ops/`；可再生 → `tmp/`。

## 1. 目录约定（全局强制）

| 目录 | 用途 | 举例 |
| --- | --- | --- |
| `docs/{model_name}/{skill}/` | 人读交付件：结构档案、方案、分析与验收报告、台账 | `docs/M100/performance-analysis/report.md` |
| `data/{model_name}/...` | 机器可读交付件：基线、性能/精度对比数据、台账、动作表 | `data/M100/optimization_log/perf_ledger.json` |
| `prof/{model_name}/{case}/` | profiling 归档：完整 `PROF_*` 目录 + kernel 汇总 csv | `prof/M100/serial-b1/` |
| `ops/{op_name}/` | 算子工程（源码 / golden / 测试 / benchmark / 集成产物） | `ops/se_pool_hd/` |
| `tmp/{model_name}/{skill}/` | 全部中间产物，可随时清理 | `tmp/M100/baseline-run/` |

`{model_name}` 取工作区标识：onnx 输入为 GE_SESSION_DEMO 编号 `M<id>`；pytorch/hf 输入为工作区模型名。`{skill}` 取 skill 目录名去掉 `recommend-` 前缀（如 `performance-analysis`）；与模型无关的交付件可省 `{model_name}` 层（如 `docs/env-baseline/`、`data/env-baseline/`）。

三个跨 skill 共享目录不按 `{skill}` 命名，属于约定例外：`data/{model_name}/baseline/`（条目 2 首基线，条目 4/5/14 共用）、`data/{model_name}/performance/`（条目 5 性能数据，条目 14 汇总）、`data/{model_name}/optimization_log/`（循环台账与状态，条目 5→14 全程读写）；`docs/{model_name}/performance-reports/`（每轮 `round{k}.md`）同理。

**禁止**：中间产物写入 `docs/` / `data/` / `ops/`；交付件散落在 `tmp/` 或工作目录根；挪动 GE_SESSION_DEMO 框架自管理目录（`models/M<id>/{output,report,.cache,sweep}`）。

## 2. perf_ledger.json（逐条目强制）

路径 `data/{model_name}/optimization_log/perf_ledger.json`，schema 见 `templates/perf-ledger-schema.json`。每条记录字段：

| 字段 | 说明 |
| --- | --- |
| `step` | 工作流条目号 + 动作简述；循环轮次标注在 `note`（如「循环第 2 轮」） |
| `timestamp` | ISO 8601 |
| `action` | 具体改动（开关名/参数/文件/算子包），禁止空话 |
| `type` | 手段类型（shape策略/编译选项/图融合pass/等价改写/并发限核/访存优化/自定义算子/精度模式/运行时修复/分析），供贡献分解归类 |
| `perf_before` / `perf_after` | 同口径主指标；含时延与吞吐两组时用对象分列 |
| `delta_pct` | 主指标变化百分比（正 = 变差，负 = 变快，需在报告中统一约定并声明） |
| `noise_band_pct` | 本轮判定所用噪声带（典型 2.0～5.0），分析类动作填 `null` |
| `precision` | `pass` / `fail` + 最大误差指标；分析类动作填 `null` |
| `profiling` | 归档路径（`prof/{model_name}/{case}/`） |
| `reverted` | 是否回退；`true` 时 `note` 必写原因 |
| `note` | 归因说明、用户确认记录、重试条件 |

写入时机：条目 2 写首基线；条目 6-12 每实施一项追加一条；条目 14 汇总收口。分析类条目各性能字段填 `null` 并在 `note` 注明。

## 3. next_actions.json（下一步动作表，循环唯一输入）

路径 `data/{model_name}/regression-baseline-mgmt/next_actions.json`。每项字段：

```json
{
  "id": "A003",
  "priority": "P0",
  "action": "对 attention 链启用 FA 融合 pass（开关 FA_PASS=1），单并发验证后测目标并发",
  "type": "图融合pass",
  "basis": "docs/M200/performance-analysis/report.md#kernel表 + prof/M200/serial-b1",
  "expected_gain": {"metric": "latency_avg_ms", "range": [-18, -10], "method": "A 项 3 因子累加：launch 开销 + GM 往返 + dtype 转换"},
  "confidence": "medium",
  "workflow_entry": "条目7 / model-recommend-flash-attention-fusion",
  "depends_on": ["自定义算子包已部署"],
  "status": "pending",
  "loop_status": "pending"
}
```

`status`：`pending` / `in_progress` / `done` / `rejected_by_user` / `blocked`（附条件）。`priority`：P0 立即执行 / P1 排队 / P2 条件触发（须写触发条件）。排序依据 = 预期收益 × 置信度 ÷ 实施成本。

来源六类逐类核对（缺失须说明）：① 条目 10 未实施候选；② 台账回退项（含重试条件）；③ 未实施机会；④ 条目 5 四项专项 findings；⑤ 条目 7 未适配项；⑥ 框架需求（标 `transfer`，不入执行队列）。空表必须给理由。

## 4. workflow_status.md（执行状态矩阵）

路径 `data/{model_name}/optimization_log/workflow_status.md`，模板见 `templates/workflow-status-template.md`。五节：① 逐轮 × 全条目执行矩阵；② 逐条目判断与产物明细；③ 轮次总览；④ 遗留待办；⑤ 收口核验清单。

**硬规则**：每轮必须覆盖全部条目 0-14，未触达的条目也要落表并写明判断（`not_applicable` 无触发 / `skipped` 有判断未做 + 理由 / `blocked` 外部受阻）。**表中无记录即视为未执行。**

## 5. 每轮性能报告

路径 `docs/{model_name}/performance-reports/round{k}.md`，按 `templates/performance-report-template.md` 八章齐全，性能汇总须含时延与吞吐双口径。当轮完成即落盘，禁止事后批量补写。

## 6. 最终优化报告

路径 `docs/{model_name}/final_optimization_report.md`，必含：

1. 优化手段总表（含回退项，标注条目来源/类型/启用状态/精度判定）
2. 逐步性能记录表（按时间线 before/after/增量，与 ledger 对账）
3. 累计收益表（基线 = 条目 2 首基线）
4. 各项贡献分解（单独开启增益 + 叠加交叉影响）
5. 精度总结（逐输出结论 / 阈值 / max_rel_err / 用户裁定记录）
6. 未实施项与遗留风险
7. 下一步动作表（与 next_actions.json 一致）
8. 循环轨迹（每轮一行：轮次 / 动作 / 条目 / before / after / 收益 / 落地 / 计数 / 交付件指针）
9. 环境信息（可复现：NPU 型号 + CANN 版本 + 框架 + 实测锚定）

## 7. 状态文件写者分工

| 文件 | 唯一写者 | 其他角色 |
| --- | --- | --- |
| `loop_state.json` / `workflow_status.md` / `next_actions.json` | primary | 只读 |
| `perf_ledger.json` | 当轮执行者写入，reviewer 复核 | 只读 |
| `round{k}.md` | 当轮执行者起草，primary 汇总 | 只读 |
| `final_optimization_report.md` | primary 收口汇总 | 只读 |

三者互不复制：看轮次状态查 `loop_state`，看动作归因查 `perf_ledger`，看执行覆盖查 `workflow_status`，看下步计划查 `next_actions`。
