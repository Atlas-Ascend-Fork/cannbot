# CANN Bench 最小接入自检

以下接口已按 `08d519c503843bce5fd4672ffa2259abeb22fb00` 核对。使用实际 checkout 时核对版本；不要根据类名猜接口。自检记录按当前节点编号放入工作目录，先跑代表用例，再做正式全量发现与验证。

## 目录、签名与调用

- 工程源码与评测任务分开。任务采用 `tests/cannbench/tasks/levelN/<op>/`；CLI `--task-dir` 指向 tasks 根目录，`--operator` 选择目标。直接使用官方任务时也以其 tasks 目录为根。
- `CannTaskLoader`、`CannCaseLoader`、`GoldenLoader` 均从 `kernel_eval.benches.cann_loader` 导入；当前没有 `CannGoldenLoader`。传任务根目录，方法参数使用 `levelN/<op>`。
- `proto.yaml` 提供 `operator.name`、`schema`、`difficulty`、有序 inputs、attrs 和 outputs；difficulty 使用官方枚举，目录 level 分类与 proto 难度字段分别保留，不凭名称推测。
- golden 函数名与 schema 一致。Tensor 参数必须有含 `Tensor` 的类型注解，例如 `x1: torch.Tensor`；TensorList、Optional 按实际接口标注，属性给出正确类型及默认值。`ParamBuilder.build_call_params` 用签名区分 Tensor 和 attrs，未标注的参数可能漏绑；函数能直接调用不等于 loader 接入成功。
- 用真实 `ParamBuilder` 生成参数并用 `inspect.signature(...).bind(**params)` 检查缺项；再实际调用 golden。输入和输出 dtype、shape、数量及结构按接口核对，FP16 输出合同不要求 FP64 中间结果 bit-exact。CPU 测试不能代替设备精度验收；golden 需要设备能力时记录限制并在相应环境验证。
- 报告冒烟必须包含非空算子条目及真实 `rel_path`，覆盖 JSON、Markdown、HTML 输出；空报告无法暴露 level 路径解析错误。报告中的模拟条目明确标为自检，不计作候选运行或通过证据。

## 可运行的 Add 接入样例

在已准备依赖的环境中，设置 `PYTHONPATH="$bench_root/src"`。下面的 Python 片段保存为当前工作目录下带节点 ID 的自检脚本；参数依次为 `$bench_root/examples/tasks`、本节点新建的自检输出目录、`<节点ID>-接入自检-r<轮次>` 报告前缀。它只调用官方 Add golden 的一个代表用例，并用一个标为 skipped 的占位条目检查报告输出链路（零设备执行），不安装候选包。

```python
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
import inspect
import logging
import sys
from pathlib import Path
from kernel_eval.config import Config, set_config

set_config(Config(device_type="cpu"))
from kernel_eval.benches.cann_loader import CannTaskLoader, CannCaseLoader, GoldenLoader
from kernel_eval.data.data_generator import DataGenerator
from kernel_eval.utils.param_builder import ParamBuilder
from kernel_eval.report.report_generator import EvalReport, EvalResult, OperatorReport, ReportGenerator

logging.basicConfig(level=logging.INFO, format="%(message)s")
root, output, report_id = sys.argv[1:]
rel_path = "level2/add"
task = CannTaskLoader(root).get_task(rel_path)
cases = CannCaseLoader(root).scan_by_rel_path(rel_path)
assert task is not None and cases, "任务或用例未发现"
golden = GoldenLoader(root).get_golden_function(rel_path)
case = cases[0]
inputs = DataGenerator().generate_input_tensors_from_case(
    case.input_shapes, case.dtypes, case.value_ranges, seed=0)
params = ParamBuilder().build_call_params(golden, case, inputs)
inspect.signature(golden).bind(**params)
result = golden(**params)
assert result.device.type == "cpu"
assert result.shape == inputs[0].shape and result.dtype == inputs[0].dtype
logging.info("CPU golden 接入成功：发现 %d 例，执行 1 例；未运行候选 kernel", len(cases))
report = EvalReport(
    framework_version="selfcheck", tasks_version="selfcheck", eval_code=report_id,
    timestamp="selfcheck", device="cpu", total_operators=1, total_cases=1,
    passed_cases=0, failed_cases=0, overall_score=0,
    operators=[OperatorReport(rel_path=rel_path, operator="Add", total_cases=1,
        cases=[EvalResult(rel_path=rel_path, operator="Add", case_id="selfcheck",
                          status="skipped", error_msg="仅报告接口自检，未执行候选")])],
    summary={"pass_rate": 0.0, "purpose": "报告接口自检，无候选执行"})
paths = ReportGenerator(output_dir=output, eval_code=report_id).save_all(report)
assert all(Path(path).stat().st_size for path in paths.values())
logging.info("JSON/Markdown/HTML 生成成功：%s", paths)
```

实际目标任务自检必须替换为目标路径、代表用例及输出合同，不能以 Add 通过证明目标已接入。进一步核对完整用例 ID 和数量；使用同一 checker 做适用的正负对照，确保错误输出会失败，不能只比较 golden 自身得出精度结论。CPU 自检结果与 NPU 评测结果分别记录。

## 核对来源

- [官方 Add 任务](https://gitcode.com/cann/cann-bench/tree/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/tasks/level2/add)
- [加载器](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/src/kernel_eval/benches/cann_loader.py)
- [参数绑定](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/src/kernel_eval/utils/param_builder.py)
- [目录解析](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/src/kernel_eval/utils/path_resolver.py)
- [报告生成](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/src/kernel_eval/report/report_generator.py)
