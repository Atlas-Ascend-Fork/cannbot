# 白盒用例接入

## Tensor API 路线附加覆盖

采用 Tensor API 路线时，按源码枚举并覆盖:

1. Tensor API / C API 分支。
2. Layout 分支。
3. 尾块与非对齐分支。
4. 多核切分分支。
5. 同步 owner 与事件配对分支。
6. 量化 / scale 分支(如适用)。
7. group 分支(如适用)。
8. buffer 复用与生命周期分支。

从当前 kernel、Tiling 和 dispatch 源码出发，记录有效分支的文件、函数、条件与版本；覆盖尾核/尾块、对齐、dtype、多核划分及适用的 tilingkey。知识搜集草稿不约束实际分支。

1. 对每个分支反推需求范围内的输入，采用阈值两侧、整除/非整除等代表参数；已有黑盒命中时复用 ID，不为凑数量重复造例。
2. 把新增正常用例写入同一授权任务目录的 `cases.yaml`，使用未占用的整数 ID，在 `note` 和阶段覆盖记录中注明源码条件。沿用原 proto、golden 与 checker，不另建数据生成/比对框架。
3. 需求定义的异常或无法由 YAML 表达的输入按 [测试工程](test-framework.md) 接入补充测试；必须进入统一回归清单，不只提交设计文档。
4. 运行当前任务要求的黑盒与白盒，记录实际执行数、结果和证据。区分源码推导可覆盖、执行中实际命中和因缺陷受阻，不能把推导当实测覆盖。

测试或接入错误由测试工作修复；正确用例暴露 kernel 缺陷时记录失败 ID、复现命令和证据，保留用例及失败结果，供代码修复使用。源码修改后复核受影响分支与用例映射，最终交付必须通过全量回归。

测试文件是目标仓交付件；分支映射和运行报告按本节点 ID 写入 `$WORK_DIR`。不修改被测算子、原始评测任务、golden 或阈值掩盖失败。

## 核对依据

已核对 cann-bench `08d519c503843bce5fd4672ffa2259abeb22fb00`；实际运行记录所用版本。

- [docs/spec/cases_yaml_spec.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/docs/spec/cases_yaml_spec.md)
- [src/kernel_eval/benches/cann_loader.py](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/src/kernel_eval/benches/cann_loader.py)
