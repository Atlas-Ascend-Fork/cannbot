# 测试框架（直调工程）

## 工程布局

交付根目录：`operators/<op>/`（目标仓内，由需求/环境信息确认；无既有工程时新建）。代码骨架复用 `ascendc-direct-invoke-template` 的 Kirin Vector 模板（`kirin_add_template/`）。

```
operators/<op>/
├── CMakeLists.txt              # FILE_NAME=<op>，模板改造
├── cmake/                      # CCE 编译检测模块（4 Modules + npu/CMakeLists.txt，模板原样复用）
├── data_utils.h                # 文件读写/日志工具（模板原样复用）
├── <op>_custom_tiling.h        # TilingData 结构（按 spec size/字段定义）
├── <op>_custom.cpp             # Kernel 实现
├── main.cpp                    # Host：读 tiling → 参数校验 → ACL 执行 → 写输出
├── run.sh                      # 一键入口：bash run.sh -r sim -v Kirin9030
├── scripts/
│   ├── cases.yaml              # 用例唯一真值定义（见下）
│   ├── gen_data.py             # 数据生成：读 cases.yaml → 复用 golden → 写 input/golden/tiling
│   ├── verify_result.py        # 精度校验：按 dtype 选 np.array_equal / np.isclose
│   ├── run_tests.py            # 测试编排器：gen → run → verify → report
│   └── acl.json                # ACL 初始化配置
├── ext_lib/                    # Simulator 运行库（如 libstdc++.so.6.0.34，需 GLIBCXX_3.4.32）
├── input/                      # 生成的 input_x.bin / tiling.bin（运行产物）
└── output/                     # 生成的 golden.bin（运行产物）
```

不使用 cann-bench 的 `tests/cannbench/tasks/levelN/<op>/` + `proto.yaml` + `desc.md` 结构，也不使用 `kernel_eval` CLI。直调工程的规格来源由需求/环境信息确认（含规格说明与 golden，若有）。

## cases.yaml 格式（直调版）

由 `gen_data.py` 和 `run_tests.py` 统一读取，是测试用例的唯一真值定义。

```yaml
# <op> 黑盒测试用例集
# 来源：$WORK_DIR/<id>-黑盒测试设计.md（architect 产出，已确认需求）
# 精度口径：<dtype> <atol/rtol>，verify_result.py 使用 <checker>
cases:
- case_id: 1              # 目录内唯一整数
  name: L0-1              # 用例编号（与黑盒测试设计.md 一致）
  level: L0               # L0(门槛) / L1(功能) / L2(异常)
  execution: simulator    # simulator(仿真执行) / code_review(同分支论证·代码检视) / validation(参数校验·不进simulator)
  shape: [10, 10]         # 输入 x 的物理 shape
  attrs: {out_h: 6, out_w: 6}  # 算子属性
  dtype: uint8            # 输入数据类型（spec 范围内）
  value_range: [0, 255]   # 像素值域；特殊值 "gradient" 表示确定性梯度
  seed: 42                # 随机种子（确定性输入设 null）
  path: path3             # 算子内部分派路径（设计/覆盖用，可为 null）
  expected: pass          # pass(精度通过) / fail_validation(参数校验拒绝)
  note: 路径3 下采样
```

字段约束：
- `case_id` 全局唯一整数；黑盒用例从 1 起，白盒用例从首个未占用整数起追加。
- `execution=validation` 的 L2 用例不生成 golden、不进 simulator，由 host 参数校验拒绝。
- `execution=code_review` 的大 shape 用例标 SKIP_CODE_REVIEW（依据规格的验证方式声明「大 shape 同分支仅循环更多则不用验证」），由代码检视覆盖。
- `expected=fail_validation` 用例预期 host 返回非 0 error_code，不混入正常精度用例的通过数。

## 执行入口

```bash
# 编译（sim 模式，Kirin9030）
source <ascend-toolkit>/set_env.sh
cmake -B build -DASCEND_PRODUCT_TYPE=Kirin9030 -DASCEND_CORE_TYPE=AiCore \
    -DASCEND_RUN_MODE=sim -DASCEND_INSTALL_PATH=$ASCEND_HOME_PATH
cmake --build build --target <op>_sim

# 一键编译+测试
bash run.sh -r sim -v Kirin9030

# 编排器细粒度控制
/usr/bin/python3 scripts/run_tests.py --no-exec --report ./test_report_noexec.json   # 不执行 kernel 的自检
/usr/bin/python3 scripts/run_tests.py --case-id 1,2,3 --kernel-bin ./<op>_sim --report ./report.json  # 选择性执行
```

Simulator 运行需 `LD_PRELOAD` 加载 `ext_lib/libstdc++.so.6.0.34`（GLIBCXX_3.4.32，授权联网下载到工程 `ext_lib/`）。

## 三件套职责

- **gen_data.py**：遍历 `cases.yaml`，对每条用例按 `value_range`/`seed`/`dtype` 生成输入（随机或确定性梯度），`importlib` 只读加载 `cases/<op>/golden.py` 调 `golden()` 算预期输出、`gen_tiling()` 生成 TilingData，写 `input/input_x.bin`+`tiling.bin`+`output/golden.bin`。`--list` 列出发现用例数。
- **verify_result.py**：按 dtype 读 output/golden，shape 不一致直接判败，逐元素比对（整型 `np.array_equal`，浮点 `np.isclose`），不退回 `allclose`。`--self-check` 对 golden vs golden 自检。
- **run_tests.py**：编排 gen → run(simulator/validation) → verify → JSON 报告。`--no-exec` 跳过 kernel 执行做用例发现/golden 绑定自检；`--case-id` 选择性执行。validation 用例走 host 参数校验（Python 侧与 C++ `ValidateParams` 同逻辑，kernel 编译后可切 host 二进制）。

## 验收边界

- 测试工程准备节点：核对 cases 可发现、golden 可调用、数据生成与断言可用、报告可生成、发现数与设计一致；尚无 kernel 或 kernel 为占位时不能伪报设备精度通过。占位 kernel 的 simulator FAIL 是预期行为，非框架缺陷。
- 白盒接入节点：在 `scripts/cases.yaml` 追加白盒用例，复用同一 gen_data/verify_result/run_tests，运行全量黑盒+白盒。
- 验收者只读证据，不重新构建或运行测试，不替执行者补造日志。

## 核对依据

参考实现来自 `ascendc-direct-invoke-template/references/kirin_add_template/scripts/{gen_data.py,verify_result.py}`。
