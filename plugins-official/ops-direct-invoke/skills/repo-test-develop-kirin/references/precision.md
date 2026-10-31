# 精度口径（直调工程）

## 判定原则

直调工程使用自建 `verify_result.py`（不使用 cann-bench `relative_error` checker），按 dtype 选择判定方式：

| dtype | 判定方式 | 阈值 | 适用场景 |
|-------|----------|------|----------|
| 整型（uint8/int8/...） | `np.array_equal(output, golden)` 逐字节精确 | atol=0.0, rtol=0.0（0 容差，不允许任何字节差异） | 整型输出算子 |
| 浮点（float16/float32/bfloat16） | `np.isclose(output, golden, atol=..., rtol=...)` | 按 spec 声明 | 浮点输出算子 |

判定流程（`verify_result.py`）：
1. `np.fromfile(output_path, dtype=<dtype>)` / `np.fromfile(golden_path, dtype=<dtype>)` 读 output 与 golden。
2. shape 不一致直接判败（返回 False），不进入逐元素比对。
3. 整型用 `np.array_equal`；浮点用 `np.isclose`，逐元素记录不匹配数与位置（前若干个用于调试）。
4. 不退回 `np.allclose`（除非与 spec 阈值等价并显式声明）；不使用 `error_ratio`。

## 纪律

- 阈值不放宽：本地判定与权威源逐项一致，无差异、无放宽。
- golden 不篡改：`gen_data.py` 用 `importlib` 只读加载 `cases/<op>/golden.py`，不复制、不修改；golden 与权威实现交叉验证一致的声明直接复用，方案记录来源。
- 校验器不改：`verify_result.py` 的判定逻辑在测试工程开发阶段固化，后续白盒/修复节点不修改以掩盖失败。
- 用户标准更严格时另做附加断言；与 spec 冲突时在需求阶段明确差异，不放宽标准换取通过。
- 占位 kernel 的 simulator FAIL 是预期行为（output≠golden 被 `verify_result.py` 正确检测），非框架缺陷；不通过篡改 golden/阈值使占位 kernel 假装通过。

## 性能

直调工程本轮交付范围通常为功能验证（Kirin9030 Simulator 小 shape 逐字节精度 + 大 shape 同分支论证），不涉及性能跑分。需求未安排性能测量时仅声明功能验证与可评测工程交付，不宣称性能达标。
