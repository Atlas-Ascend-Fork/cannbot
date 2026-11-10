# CANN Bench 测试工程

## 目录与复用

`bench_root` 为已记录版本的 cann-bench checkout；`source_dir` 为候选源码；`task_dir` 为本轮采用的任务根目录（`tests/cannbench/tasks/`），`rel_path` 为 `levelN/<op>`；`bench_root` 不与任务根目录混用。检查已有任务的算子名、schema、规格和用例，复用匹配资产；补充内容写入目标仓授权的 `tests/cannbench/tasks/levelN/<op>/`，使用同一文件格式与同一评测器，不更改上游任务。

```text
tests/cannbench/tasks/levelN/<op>/
├── proto.yaml         # operator、schema、输入输出和属性
├── desc.md            # 数学及接口语义
├── golden.py          # 与 schema 匹配的独立参考函数
└── cases.yaml         # cases 列表：保留原用例并加入黑盒/白盒补充
```

已有任务也保留 `tasks/levelN/<op>` 层次，CLI 的 `--task-dir` 传 tasks 根目录，并用 `--operator` 选择目标；loader 传同一根目录及相对路径。当前 HTML 报告器解析 `levelN/<op>`，不要把裸 `<op>` 目录当评测根目录。N 沿用已有分类或记录新的分类，不由算子名猜测。原始任务根目录可作为只读 `task_dir`；需要补充时创建上述可交付任务目录，保留原有用例 ID 和内容，记录来源 commit、新增 ID 与覆盖映射。没有目标任务时按确认规格创建完整目录。两者使用相同测试契约，不增加工作流分支。`metadata/` 只在确需真实性能锚点时按当前版本格式使用，不制造 baseline。

## 先验证接入

先按 [最小接入自检](cannbench-integration.md) 验证 loader、golden 签名与参数绑定、代表输入和报告生成，再展开全量用例。接入自检通过只证明测试工程能工作，不是 NPU 精度通过。

## cases.yaml

例为双输入 Add 的数据格式，不代表目标算子的完整测试集：

```yaml
cases:
- operator: Add
  case_id: 1
  input_shape: [[17, 33], [17, 33]]
  dtype: [float32, float32]
  attrs: {}
  value_range: [[-1, 1], [-1, 1]]
  note: 黑盒边界；非对齐
```

- `operator` 与 proto 一致，`case_id` 为目录内唯一整数；`input_shape`、`dtype`、`value_range` 按 proto 输入顺序对应。
- optional 缺省使用 `null` 占位；TensorList 用嵌套列表，不能靠省略位置改变参数绑定。
- 当前 loader 读取 `cases.yaml`，不是 `cases.csv`；如保留 CSV 展示文件要同步它，不能只改 CSV。
- 不添加评测器不认识的 `expected_exception` 等字段并假设会执行。异常输入若无法用当前 loader/checker 表达，使用明确的补充 pytest 检查接口异常，单独报告结果，不混入正常精度用例的通过数。
- 使用评测器的数据生成、golden 加载及 checker。特殊确定性输入若不能由现有字段表达，依据当前接口实现必要的补充测试，并复用相同 checker；不得默默退回 `allclose`。

## 执行入口

先确认 Python 环境及 `cann_bench_utils` 已准备好。官方 `scripts/run_evaluation.sh` 会准备辅助组件并安装候选包；本仓记录报告编号时直接使用同仓 CLI。以下路径均为绝对路径，`build_dir` 是位于 `$WORK_DIR` 的当前源码构建快照；`node_id`、`attempt` 和 `device_id` 来自本次任务，设备必须属于授权资源。

```bash
PYTHONPATH="$bench_root/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m kernel_eval.cli eval \
  --bench-name cann --source-dir "$build_dir" --task-dir "$task_dir" \
  --operator "$op" --device npu --device-id "$device_id" \
  --reports-dir "$WORK_DIR/$node_id-评测-r$attempt" \
  --eval-code "$node_id-精度-r$attempt" --eval-seed 0 --no-perf
```

命令完整保留原始日志和退出码；每次使用新报告目录。精度执行不需要性能采集，`--no-perf` 不等于关闭真实性检查。显式传设备避免默认占用全部卡；相同 Python 环境的候选安装不得并发互相覆盖。

开发期可加 `--case-id <整数>` 局部定位，正式全量验收去掉该筛选。先核对实际发现数，再与报告执行数逐项对齐；零用例、漏算子、跳过或部分通过都不能称为全量通过。补充 pytest 也必须记录其数量、结果和日志。

## 不同任务的交付边界

- 测试工程准备：核对 proto/cases 可发现、golden 可调用、数据生成与断言可用，提供入口和用例映射；尚无 kernel 时不能伪报设备精度通过。
- 算子开发：执行完整黑盒，记录当前源码构建与设备结果。
- 白盒接入：在已有 cases 中加入源码分支用例，运行黑盒和白盒；归属明确的算子失败交修复，测试自身错误须修好。
- 修复交付：黑盒、白盒及必要补充测试全量通过；已有有效证据的复用遵从当前 task，不使用旧代码日志证明新代码。

官方 JSON/Markdown/HTML 报告保存原样，阶段记录给出带节点 ID 的结果路径、任务/源码/wheel/加载库版本和哈希、用例计数及失败归属。验收者只读证据，不重新构建或执行。示例 `test.sh` 仅运行示例 pytest，不代表目标算子已通过 cann-bench。

## 核对依据

已核对 cann-bench `08d519c503843bce5fd4672ffa2259abeb22fb00`；实际运行记录所用版本。

- [examples/tasks/level2/add/proto.yaml](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/tasks/level2/add/proto.yaml)
- [examples/tasks/level2/add/cases.yaml](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/tasks/level2/add/cases.yaml)
- [docs/spec/cases_yaml_spec.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/docs/spec/cases_yaml_spec.md)
- [src/kernel_eval/cli.py](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/src/kernel_eval/cli.py)
- [src/kernel_eval/report/report_generator.py](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/src/kernel_eval/report/report_generator.py)
