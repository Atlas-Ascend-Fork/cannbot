# add 算子 — 进度与验证状态

## 需求
- 算子：`add`（FP32 逐元素向量加，`out[i] = x[i] + y[i]`）
- 来源：用户文字需求「开发一个add算子」
- 目标芯片：Ascend 950PR（`device=Ascend950PR`，host 容器 `[NPU host]`）
- 复杂度档位：**simple**（纯逐元素、无 Cast 链、无规约、无 UB-to-UB 拷贝）
- `harness.review`：未在 Team `AGENTS.md` 中配置，默认 `auto` → simple 档下按配置跳过子 Agent 文档评审（由主 Agent 自行完成校验与 API 检查）

## 执行路径
本工作区无本地 CANN / torch_npu，按工作区 `AGENTS.md` 的约定走受限 demo runner，
由 runner 在远端 NPU 主机物化 demo kernel、用 CANN 构建、执行并与 NumPy golden 比对。
本地不产出/不改写 kernel 源码工程（`.asc` / `CMakeLists.txt` / `pytest` 套件均由 runner 侧提供）。

## 阶段状态
- [x] 阶段 0 需求与环境对齐（算子、芯片、受限 runner 路径）
- [x] 阶段 1 状态记录（本文件）
- [x] 阶段 2 骨架/构建：由 runner 侧完成（`Built target add_custom`）
- [x] 阶段 3 定义文档：语义明确（逐元素加，float32），随本记录归档
- [x] 阶段 4 设计校验：single-tile 32768 元素，32B DMA 约束与 UB 预算由 runner 侧固定配置满足
- [x] 阶段 5 测试：runner 内置 32768 元素 NumPy golden 比对（等价黑盒全量用例）
- [x] 阶段 6 实现：runner 物化 kernel 并编译通过
- [x] 阶段 7 真机验证：**PASSED**，`Max diff: 0.0`
- [x] 阶段 7.5 黑/白盒门禁：`harness.test_gate` 未配置（默认 `off`），跳过
- [x] 阶段 8 收尾

## 验证结论
| 项 | 值 |
|---|---|
| device | Ascend950PR |
| shape / dtype | (32768,) / float32 |
| golden | NumPy `x + y` |
| 比对结果 | PASSED |
| 最大绝对误差 | 0.0 |
| 退出码 | 0 |

原始输出见 [1-NPU验证日志.log](npu-validation.log)。

## 限制
- 该 runner 仅支持 `add` / `sub` 两个 FP32 demo，其他算子可在此起草但无法用其验证。
- 本地工作区未保留 kernel 源码副本，因此本记录不声称对本地代码做过任何编辑或测试。
