---
name: blackbox-tester
description: TTK 黑盒执行技能。使用 ops-test-kit aclnn 模式对当前工作流部署的 vendor 自定义算子做全量黑盒精度执行与结果汇报：按公共标准文件分离 L0/L1 正向套件与 L2 负向套件 → 加载 golden 插件 → 全量跑 ttk aclnn → 解析 result.csv 输出两条门禁结论（L0/L1 数值全绿 + L2 反向全部被拒绝）。当需要对算子进行黑盒精度验收、或驱动 blackbox-tester 执行黑盒时使用。
disable-model-invocation: true
---

# TTK 黑盒精度验收

本技能以 **ops-test-kit（TTK）aclnn 模式** 对当前工作流部署的 vendor 自定义算子做端到端黑盒精度验收。
环境（`$PY` / `$TTK` / CANN）按 [`ttk-env-check`](../ttk-env-check/SKILL.md) 的「环境约定」设定，**勿写死路径**。

TTK 以源码方式使用：需 `cd $TTK` 后 `python3 -m ttk aclnn ...`。

详细命令、环境变量与排障见 [`references/ttk-aclnn-guide.md`](references/ttk-aclnn-guide.md)；TestSpec 编写规范见 TTK 仓 `ttk-how-write-plugin` skill（`$TTK/.claude/skills/ttk-how-write-plugin/SKILL.md`）+ `$TTK/ttk/test_spec/examples/`（6 个官方示例）。
**全量黑盒大规模失败（`561002` / `NO_OUTPUT` / `errcode95`）时先按 guide §8「黑盒失败分诊 SOP」分诊**（最小复现 + `nm -D` 排除 built-in 冲突），再落框架加载修复（Pitfall 9/10，模板见 [`references/sitecustomize_rtld_global.py.templ`](references/sitecustomize_rtld_global.py.templ)）；禁止直接进 kernel/tiling 修复循环。

TTK 通用权威参考见 [`ops-ttk`](../ops-ttk/SKILL.md) 指引的 TTK 仓 4 个标准 skill（`$TTK/.claude/skills/`）：命令参数（`ttk-how-run-test`）、CSV 字段（`ttk-how-write-case`）、TestSpec 插件（`ttk-how-write-plugin`）、精度排障（`ttk-how-diagnose`）。

---

## 核心步骤

**先定义绝对路径变量**（后续步骤都用它们；执行时会 `cd $TTK`，相对路径会失效，故一律用绝对路径）：

```bash
PKG=<operator_package_dir 绝对路径>              # 如 .../operators/{OP}_package
source <绝对路径>/docs/{OP}/develop/env.sh       # TTK 环境验证产物 → $PY / $TTK / ASCEND_*（勿写死）
: "${TTK:?}"; : "${PY:=python3}"
OPTYPE=<OpType>                                  # 驼峰，如 AddCustom
OUTDIR="$PKG/tests/blackbox/ttk"; mkdir -p "$OUTDIR"
MERGED="$OUTDIR/blackbox_all.csv"                # 步骤 1 产物：L0/L1 正向套件（数值精度全绿门禁）
NEG="$OUTDIR/blackbox_l2_neg.csv"               # 步骤 1 产物：L2 负向套件（异常/预期失败，单独跑、反向门禁）
GOLDEN=<docs/{OP}/develop/golden.py 绝对路径>     # TestSpec spec 文件（直接 --plugin 指向，无需包装）
SKILL_DIR=<本 blackbox-tester skill 目录绝对路径>  # 含 preflight.py / parse_result.py / references/
TTK_SKILL=<ops-ttk skill 目录绝对路径>   # 经 skills/ops-ttk 软链解析，含 assets/ 与 scripts/
INPUT_DIST_ARG=$("$PY" "$TTK_SKILL/scripts/derive_input_dist.py" --spec <绝对路径>/docs/{OP}/spec.yaml)  # spec 任一输入 data_distribution: normal → "--input-dist normal"；否则空（TTK 默认 uniform）
```

### 步骤 1：定位并分离 L0/L1（正向）与 L2（负向）

blackbox-designer 直接交付公共 `ascendc-st-design` 的标准文件：
`*_l0_functional.csv`、`*_l1_functional.csv`、`*_l2_exception.csv`。当前工作流的 `*_oversized.csv`
旁表只记录资源超限场景，**不进入设备执行套件**。

L2 是异常/预期失败用例（不支持 dtype、越界维、错 format、shape 不匹配等），算子应拒绝它们；
故 L0/L1 合并为正向套件走数值全绿门禁，L2 单独走反向门禁。L1 非连续用例比 L0 多
`tensor_storage_shapes` 等字段，必须按列名取并集，禁止用 `head/tail` 按文本拼接：

```bash
"$PY" "$SKILL_DIR/merge_cases.py" "$PKG/tests/blackbox/testcases" \
  --positive-out "$MERGED" --negative-out "$NEG"
```

`merge_cases.py` 只识别上述三个标准精确后缀，天然排除 `_oversized.csv`；它按列名合并、为空字段补空值，
并把公共 Skill 当前逐 Tensor 的单元素 offset 容器适配成 TTK 标准的标量 offset（TensorList 保留分组）。
这是公共产物到执行器的字段接线，不改变用例语义；用例名重复、字段结构歧义或 L0/L1 为空时立即 FAILED。

### 步骤 2：定位 golden spec 文件

`docs/{OP}/develop/golden.py` 是 **TestSpec 格式**（`__spec__` + class，含 `golden`/`third_party`/`tolerance`），直接通过 `--plugin` 传入即可，**无需实例化包装**：

```bash
GOLDEN=<docs/{OP}/develop/golden.py 绝对路径>
[ -f "$GOLDEN" ] || { echo "ERROR: golden.py not found at $GOLDEN" >&2; exit 1; }
```

> **缺 golden.py → 立即报缺失、返回 FAILED**，不继续跑 TTK。
> golden.py 必须为 TestSpec 格式（含 `__spec__` 注册 + class 定义），注册名与 CSV `api_name` 一致。编写规范见 TTK 仓 `ttk-how-write-plugin` skill（`$TTK/.claude/skills/ttk-how-write-plugin/SKILL.md`）。
> ACLNN golden 的可调用参数必须按部署后的 `aclnn<Op>GetWorkspaceSize` 头文件和 TTK 参数计划建模：接收所有真实输入、
> scalar/attr 以及纯输出占位参数，忽略的输出位使用默认值（如 `out=None`）。模块级函数挂到 TestSpec class 时使用
> `staticmethod`，避免 Python 额外绑定 `self`。不得根据某个算子临时追加参数名；以当前部署 header 和 TTK 官方
> plugin skill 为准。

### 步骤 2.5：上设备前预检（fail-fast）

跑 [`preflight.py`](preflight.py) 据部署产物核对合并 CSV，避免上设备后才崩：

```bash
PYTHONPATH="$SKILL_DIR" "$PY" "$SKILL_DIR/preflight.py" "$MERGED" --optype "$OPTYPE"
```

检查 ① `api_name` 来自 vendor `.so`，或是当前 CANN 已安装的公共 ACLNN wrapper；② `attributes` 键名是
对应 aclnn 头文件参数名（Pitfall 6：可选属性带 `Optional` 后缀，如 `axes`→`axesOptional`）。公共 wrapper
只表示接口可调用：若其它 vendor 也定义同名接口头，预检直接失败，避免 TTK 按陈旧签名构参；无歧义时后续 smoke
的 `--require` 来源门禁仍必须通过。非 0 即修环境/用例后重试。

### 步骤 2.6：先跑一条试跑（先解决基础设施问题，再全量）

**不要直接全量跑**——全量很贵，带病全量是浪费。先从 `$MERGED` 读取一条确切的 `testcase_name`，再用
`-t` 按名只跑该用例；不使用 `--ti` 猜测索引基准或调度顺序，且**开 CANN debug 日志**跑——既早暴露
golden / 算子部署 / 环境等**基础设施问题**，又能从日志核对**实际执行的 kernel 二进制真来自自定义算子安装包**
（`vendors/$OPTYPE`），防止跑成内置(built-in)/其它 vendor/陈旧算子的假绿：

```bash
VENDOR="$ASCEND_OPP_PATH/vendors/$OPTYPE"; cd "$TTK"                       # CWD 必须 == TTK 根
export LD_LIBRARY_PATH="$VENDOR/op_api/lib:$LD_LIBRARY_PATH"           # 不设 ASCEND_CUSTOM_OPP_PATH，走 vendor 源
export ASCEND_GLOBAL_LOG_LEVEL=1 ASCEND_SLOG_PRINT_TO_STDOUT=1        # 开 CANN 日志(INFO)：打印 Op[<OpType>] 实际加载的 bin path
SMOKE_CASE=$("$PY" -c 'import csv,sys; print(next(csv.DictReader(open(sys.argv[1], newline="", encoding="utf-8-sig")))["testcase_name"])' "$MERGED")
[ -n "$SMOKE_CASE" ] || { echo "ERROR: no smoke testcase in $MERGED" >&2; exit 1; }
rm -f "$OUTDIR/result_smoke.csv"; set -o pipefail
if ! env PYTHONPATH="$TTK:$(dirname "$GOLDEN"):$ASCEND_TOOLKIT_HOME/python/site-packages" \
    "$PY" -m ttk aclnn -i "$MERGED" -t "$SMOKE_CASE" \
    --pc=1 --task-prof false --run 1 --warmup false --device-whitelist 0 $INPUT_DIST_ARG \
    --plugin "$GOLDEN" -o "$OUTDIR/result_smoke.csv" \
    2>&1 | tee "$OUTDIR/smoke_debug.log"; then
  echo "ERROR: smoke TTK process did not complete" >&2; exit 1
fi
# 精确按名跑 1 条、--pc=1 单进程；精度 FAIL 可继续，基础设施状态/旧结果/多行结果均阻断
PYTHONPATH="$SKILL_DIR" "$PY" "$SKILL_DIR/parse_result.py" "$OUTDIR/result_smoke.csv" --smoke
# 核对：日志里 Op[<OpType>] 实际加载的 kernel bin 是否真来自自定义算子安装包 vendors/$OPTYPE
PYTHONPATH="$SKILL_DIR" "$PY" "$SKILL_DIR/check_op_binpath.py" "$OUTDIR/smoke_debug.log" \
    --optype "$OPTYPE" --expect-dir "$VENDOR" --require
```

> `check_op_binpath.py` 抓 CANN 日志里三种已实测的 bin-path 行：`Op[<OpType>] … bin path is <P>`、`OpName:[…<OpType>…] … bin file path[<P>]` 与 `Available bin for op <OpType> is <P>`，校验 `<P>` 落在 `vendors/$OPTYPE` 下——aclnn 模式加载的是安装包里预编的 `vendors/<OpType>/…/kernel/<soc>/<op>/<OpType>_<hash>.o`；落在 `built-in/op_impl/…/ops_legacy/…` 即**跑成了内置算子**（真实回退案例），落在别处即别的 vendor/陈旧算子。`ASCEND_GLOBAL_LOG_LEVEL=1`(INFO) 即可打出这些行（不同 CANN 版本请核对）。`--require` 使日志未命中也失败，禁止把未确认来源当作通过。
> **注意**：`--ti` 索引的是 TTK 内部调度顺序（会打乱），**不是 CSV 行序**——补跑/续跑缺失用例必须用 `-t` 按用例名选（实测按 `--ti` 续跑会产生重复+漏跑）。

判读：
- **跑通且算子来源对**（`ttk aclnn` 正常退出、`result_smoke.csv` 有 1 行且 `precision_status` 为 `PASS`/`FAIL`、且 `check_op_binpath.py` 打印 `PASS`）→ 基础设施 OK、跑的确是本算子，进步骤 3 全量。**精度 FAIL 不拦**——那是 kernel 精度问题、本 agent 不修，照常全量并如实汇报。
- **算子来源不对或未证实**（`check_op_binpath.py` 非 0：bin path 落在 `vendors/$OPTYPE` 之外，或日志未命中）→ **当前结果不可信**：先核对日志级别和部署，重跑单例直到来源为 `PASS` 再进全量。
- **跑不通 / 有基础设施问题**（`ttk aclnn` 报错退出、`result_smoke.csv` 缺失或 0 行、`precision_status`=`SOC_NOT_SUPPORT`/skip、或 golden import/语法/签名报错、找不到符号、缺环境依赖、api_name 不符）→ **先诊断解决、再全量**：据报错定位并修（修 `golden.py` / 重新部署算子 / 补环境依赖 / 校 `api_name`），重跑单例直到跑通，**再**进步骤 3。**严禁带着已知基础设施问题直接全量跑。**

### 步骤 3：全量跑 TTK aclnn

单例试跑通过后，才以 `$MERGED`（全量合并）为输入全量执行：

```bash
VENDOR="$ASCEND_OPP_PATH/vendors/$OPTYPE"        # env 与 $MERGED/$GOLDEN/$OPTYPE 均已在开头定义
cd "$TTK"                                        # CWD 必须 == TTK 根
export LD_LIBRARY_PATH="$VENDOR/op_api/lib:$LD_LIBRARY_PATH"   # 不设 ASCEND_CUSTOM_OPP_PATH，走 vendor 源
rm -f "$OUTDIR/result.csv" "$OUTDIR/result_l2.csv"             # 禁止本轮异常退出后误验旧结果
if ! env PYTHONPATH="$TTK:$(dirname "$GOLDEN"):$ASCEND_TOOLKIT_HOME/python/site-packages" \
    "$PY" -m ttk aclnn -i "$MERGED" \
    --pc=1 --task-prof false --run 1 --warmup false --device-whitelist 0 $INPUT_DIST_ARG --plugin "$GOLDEN" -o "$OUTDIR/result.csv"; then
  echo "ERROR: positive TTK suite did not complete" >&2; exit 1
fi
# L2 负向套件（若有）：同样全量跑，结果单独落 result_l2.csv
if [ -s "$NEG" ]; then
  if ! env PYTHONPATH="$TTK:$(dirname "$GOLDEN"):$ASCEND_TOOLKIT_HOME/python/site-packages" \
      "$PY" -m ttk aclnn -i "$NEG" \
      --pc=1 --task-prof false --run 1 --warmup false --device-whitelist 0 $INPUT_DIST_ARG --plugin "$GOLDEN" -o "$OUTDIR/result_l2.csv"; then
    echo "ERROR: negative TTK suite did not complete" >&2; exit 1
  fi
fi
```

**禁止只跑子集**——正向门禁以 `$MERGED`（L0/L1 全量）为输入、负向门禁以 `$NEG`（L2 全量）为输入；步骤 2.6 的单例只是试跑，不能替代全量。
> **`--pc`（`--process-count`，每卡进程数）默认 `--pc=1`**：多卡机器上单卡测试（`--device-whitelist 0`）时并行过高会把多进程挤在同一张卡上，OOM 卡死，稳优先；
> 整机多卡可用、资源充足时可 `--pc=4` 提速（aclnn 瓶颈在 host 侧输入生成+golden 计算，实测 `--pc=4` ~20s/条 vs `--pc=1` ~73s/条）。
> **`--device-whitelist 0`**：多卡机限定单卡，不设则向全部可见 device 分发（设备 ID 越界报 `aclrtSetDevice 107001`）。
> **中断续跑/补跑**：用 `-t <逗号分隔用例名>` 按名补跑缺失用例（`--ti` 为 TTK 内部顺序，勿用）。
> **`$INPUT_DIST_ARG`（数据分布，勿手改）**：由开头 `derive_input_dist.py` 据 `docs/{OP}/spec.yaml` 机械推导——累加类算子（spec `inputs[].data_distribution: normal`）为 `--input-dist normal`，否则为空（TTK 默认 uniform）。**冒烟、全量正向、L2 负向必须带同一份 `$INPUT_DIST_ARG`**，否则试跑/全量数据分布不一致、结论不可比。

### 步骤 4：解析 result.csv → 门禁结论

```bash
# 正向门禁（L0/L1）：数值精度全绿
PYTHONPATH="$SKILL_DIR" "$PY" "$SKILL_DIR/parse_result.py" "$OUTDIR/result.csv" \
    --expect-total "$(( $(wc -l < "$MERGED") - 1 ))" \
    --by-layer "$PKG/tests/blackbox/testcases"     # 可选：L0/L1 分层统计
# 负向门禁（L2，若有）：预期全部被算子拒绝——任何 PASS = 算子未拒绝非法输入 = 真缺陷
if [ -s "$OUTDIR/result_l2.csv" ]; then
  PYTHONPATH="$SKILL_DIR" "$PY" "$SKILL_DIR/parse_result.py" "$OUTDIR/result_l2.csv" \
      --negative --expect-total "$(( $(wc -l < "$NEG") - 1 ))"
fi
```

**两条独立门禁**：
- **正向（L0/L1）**：`precision_status == "PASS"`；退出 0 当且仅当 `pass==total 且 fail==skip==0`。
  状态先忽略大小写与首尾空白，再按完整 token 识别既有成功/跳过别名；`NOT_PASS`、`UNSUCCESSFUL` 等未知状态按 fail 处理，不能靠成功子串通过门禁。
- **负向（L2）`--negative`**：退出 0 当且仅当 `total` 等于 L2 全量条数且 `pass==0`（全部非法输入被拒绝=NO_OUTPUT/FAIL）。**不要**把 L2 混进正向全绿门禁、也**不要**靠改 golden 把 L2 洗成 PASS——L2 就是要"全失败"。
辅助信息：`precision`（如 `100.0%`）、`soc`。result.csv 完整 27 列表头见 [`references/ttk-aclnn-guide.md §6`](references/ttk-aclnn-guide.md#6-判读-resultcsv)。

> **`--by-layer`（分层统计，不影响门禁）**：自动处理 TTK 对重名用例的改名 `<原名>_<api>_dupN`
> （`testcase_manager._rename_duplicate_case_name`，实测触发），按最长前缀归并回原用例；对不上的列 UNMAPPED。
> 不要手写临时脚本做分层——本选项即为此场景提供。
