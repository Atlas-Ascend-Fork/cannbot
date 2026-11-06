# 精度与评分口径

## Tensor API 路线附加要求

采用 Tensor API 路线时:

1. 冻结输入 dtype、累加 dtype、转换顺序、公式顺序、舍入、clamp/saturation 和非有限值处理。
2. 明确 mismatch_count 是 bitwise 差异数还是超过误差门的元素数,不得混用。
3. 设备侧与 Golden 累加 dtype 不一致时,必须提供支持域内的等价性证据。
4. 任何 device error、越界或 crash 均为阻断项。
5. 性能报告记录 shape、命令、有效字节数、目标、基线、瓶颈维度分解、多轮采样中位数与离散度;改变数值路径的优化必须附精度回归结论。

## 精度执行

本仓用 CANN 后端注册的 `relative_error` checker。标准来源是所用版本的 `src/kernel_eval/utils/thresholds.py`、`compare.py`、`checkers/relative_error_checker.py` 及算子 proto 中的 `precision_thresholds` 配置；在测试方案中记录实际生效配置，不另写近似判定器。

已核对版本的正常浮点值域采用 MERE 与 MARE 双条件，MARE 门槛是 threshold 的 10 倍，均使用严格小于；常用 dtype 基础 threshold 如下，算子覆写和实际配置必须另行核对：

| dtype | threshold |
|-------|-----------|
| float16 | `2**-10` |
| bfloat16 | `2**-7` |
| float32 | `2**-13` |
| 整型 | 精确匹配 |

这张表不构成完整判定。checker 还处理输出结构/连续性、小值域、相消、NaN/Inf 等；不能只实现上述两个指标或 `torch.allclose` 就宣布等价。浮点判定使用评测器提供的高精度 golden 与需要时的同精度 CPU 对照，输入生成和 dtype 处理交给现有实现。

逐输出保留实际生效的指标、阈值、实测统计与 pass/fail；保留原始机器可读报告，不把内部 checker 结果改写为更宽松的自建结论。用户标准更严格时另做附加断言；与正式评测契约冲突时在需求阶段明确差异，不放宽 cann-bench 标准以换取通过。

## 性能与跑分

`--no-perf` 适用于功能验证；不能据此报告 HAP、性能通过或最终综合分达标。任务明确要求跑分时，使用同版本评测器开启性能采集，保留硬件标签、metadata 版本、每例候选耗时、baseline 与硬件锚点及真实报告。

`metadata/<hardware>.json` 保存 `baseline_perf_us` 和 `t_hw_us`。`examples/tasks` 的零值 fixture 不能用于真实性能比较，补充黑盒/白盒缺少锚点时不能伪造得分；官方原始任务的跑分与扩展用例回归分别记录，不能用扩展集合冒充官方分数。

HAP 是硬件锚定评分而非 speedup，不能擅自给所有算子添加 HAP ≥ 0.5、带宽差 20% 等门槛。是否有性能硬目标由需求决定，流程未安排性能测量时仅声明功能验证与可评测工程交付，不宣称性能达标。

## 核对依据

已核对 cann-bench `08d519c503843bce5fd4672ffa2259abeb22fb00`；实际运行记录所用版本。

- [src/kernel_eval/utils/thresholds.py](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/src/kernel_eval/utils/thresholds.py)
- [src/kernel_eval/utils/compare.py](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/src/kernel_eval/utils/compare.py)
- [src/kernel_eval/checkers/relative_error_checker.py](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/src/kernel_eval/checkers/relative_error_checker.py)
- [docs/design/precision_comparison_design.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/docs/design/precision_comparison_design.md)
- [README.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/README.md)
