# CANN Bench 评测环境依赖

| 检查项 | 方法与通过依据 |
|--------|----------------|
| 评测源码 | 定位用户指定 checkout，或 `.cannbot/dependencies/ops-direct-invoke/cann-bench/`；记录 commit，确认 direct_launch_example、目标任务格式、kernel_eval CLI 可用 |
| 评测组件 | 检查 kernel_eval CLI 的 help/任务发现、`cann_bench_utils` 是否可导入及其来源；缺失时报告准备项，不在检查中静默触发安装 |

核对版本的官方快速入门要求 Python 3.10+、CANN 9.1.0+，实际依赖以当前 checkout 为准；torch/torch_npu 组合须按该版本的依赖和平台匹配。上述最低版本不等于任意版本组合都兼容，不宣称本次检查已完成 kernel 编译或设备精度验收。

不要用 `scripts/run_evaluation.sh` 作无副作用探测：它可能构建辅助组件、安装候选包并运行评测。环境准备缺项由调用方安排修复，完成后再按授权复核；不得通过禁用保护组件绕过。

## 核对依据

已核对 cann-bench `08d519c503843bce5fd4672ffa2259abeb22fb00`；按实际 checkout 记录版本和差异。

- [docs/guide/quick_start.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/docs/guide/quick_start.md)
- [requirements.txt](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/requirements.txt)
- [scripts/run_evaluation.sh](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/scripts/run_evaluation.sh)
