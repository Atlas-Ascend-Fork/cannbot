# CANN Bench 评测契约

## 三个路径

| 路径 | 内容 | 使用边界 |
|------|------|----------|
| `bench_root` | cann-bench checkout，含 `src/kernel_eval`、`scripts`、`examples` 与 `tasks` | 记录 commit；评测器、原始 golden 和公开用例不作为候选代码修改对象 |
| `source_dir` | 独立算子源码工程，含根 `build.sh`、`setup.py`、`cann_bench/`、`csrc/` | 构建产出 `dist/cann_bench*.whl`；不得依赖工作区外未交付的代码 |
| `task_dir` | 本次评测任务目录或其集合根 | 必须能发现实际目标算子和非空用例集；新增测试沿用相同格式 |

插件依赖 checkout 位于 `<目标仓>/.cannbot/dependencies/ops-direct-invoke/cann-bench/`；已有用户指定 checkout 可直接使用，以本轮输入记录的绝对路径为准。CANN Bench 的 `kernel_eval` 是算子评测器，与负责 Agent 调度的 harness 不同。

## 任务文件

- `proto.yaml`：`operator.name/category/difficulty/formula/inputs/outputs/attrs/schema`，是接口和输入次序的依据；`desc.md` 补充语义。
- `golden.py`：与算子函数匹配的独立参考实现；评测器构造输入并调用它，候选执行路径不能调用它代算。
- `cases.yaml`：顶层 `cases` 列表，记录 `operator`、整数 `case_id`、`input_shape`、`dtype`、`attrs`、`value_range` 等；当前 CANN loader 读取此文件，只有 `cases.csv` 不足以执行。
- `metadata/<hardware>.json` 与 `metadata/VERSION`：对应硬件的性能锚点及版本。不能把示例 fixture 的零占位值当作真实基线。
- `tasks/level1`～`level4` 是算子难度分层，不是测试设计中的 L0/L1/L2 覆盖标签。

`examples/tasks` 中 Add/Sqrt 用于验证评测链路，生产目标从当前评测任务中选择；名称匹配不证明 shape、dtype 和数学语义都匹配，需核对需求。

## 源码、wheel 与接口

1. 评测器接收已解包的 `source_dir`。没有 `dist/cann_bench*.whl` 时调用根目录 `bash build.sh`，要求返回 0 且生成 wheel。
2. wheel 必须可安装并 `import cann_bench`。本仓使用 `_C.abi3.so` 加载注册、`torch.ops.cann_bench.<schema函数>` 分派，`cann_bench/__init__.py` 必须导出目标同名 callable；只注册 C++ schema 而不导出 Python callable 不完整。
3. schema 的参数次序、类型、默认值与返回结构承接任务；不要把 `cann_bench` 当作任意可改的包名。用户要求另一外部接口时须保留评测适配契约并明确差异。
4. 原有 wheel 会影响评测是否重新构建。源码改变后不得用旧 wheel 冒充当前结果；交付目录中仅保留本次目标架构的有效产物。
5. 一份工程整体构建失败会影响该提交的所有算子；不能以只筛选某算子来掩盖工程其余编译错误。

## 编译、精度与评分

编译、功能精度、性能是不同结论。官方评测包含 HAP 性能评分；`--no-perf` 只证明相应功能精度与编译结果，不证明最终跑分或性能达标。输出报告需要保留实际评测版本、任务版本、目标硬件、源码和 wheel 版本。

精度使用 CANN 后端的 `relative_error` checker，覆盖逐输出结构、整型精确比较、浮点正常值域、小值域和相消判定。指标取值来自当前评测器及算子配置；不得用 `allclose` 冒充整套判定，也不能修改评测器来迎合实现。

性能以真实硬件 metadata 为锚点：`HAP = (T_baseline - T_HW) / ((T_cand - T_HW) + (T_baseline - T_HW))`。HAP 不是加速比；无效或缺失锚点不能推算可信分数。是否采集性能及采用什么交付门槛由任务明确，本 Skill 不擅自增加优化或提交步骤。

网站上传规则与本地评测接口不同；未检查网站规则时不承诺打包目录可直接上传，也不执行 PR、上传或外部 CI。

## 核对依据

已核对 cann-bench `08d519c503843bce5fd4672ffa2259abeb22fb00`；运行时记录实际 checkout 版本，版本变化时核对相关接口。

- [docs/spec/submission_spec.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/docs/spec/submission_spec.md)
- [examples/tasks/README.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/tasks/README.md)
- [src/kernel_eval/benches/cann_loader.py](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/src/kernel_eval/benches/cann_loader.py)
- [README.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/README.md)
