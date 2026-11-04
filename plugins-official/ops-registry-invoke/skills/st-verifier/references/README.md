# st-verifier · 原生校验入口

`st-verifier` 子agent 直接调用已安装 `ascendc-whitebox-design` 的公开脚本，不再加载旧 `whitebox_designer.py`。
`WHITEBOX_SKILL` 为该 skill 目录，`WB_DIR` 为本阶段白盒产物目录；以下仅适用于白盒，黑盒按自身生成技能执行 QA/CSV 校验。

## 依赖预检

生成前执行；任一脚本缺失、接口不兼容或非零退出均停止并报告依赖失败：

```bash
test -r "$WHITEBOX_SKILL/scripts/ttk_validate_csv.py" || exit 1
for script in check_s2p1.py s5_check_mapper_outputs.py ttk_generate_kernel_csv.py; do
    python3 "$WHITEBOX_SKILL/scripts/$script" --help || exit 1
done
```

## 产物校验

```bash
python3 "$WHITEBOX_SKILL/scripts/check_s2p1.py" --whitebox-dir "$WB_DIR"
python3 "$WHITEBOX_SKILL/scripts/s5_check_mapper_outputs.py" --whitebox-dir "$WB_DIR"
python3 "$WHITEBOX_SKILL/scripts/ttk_validate_csv.py" "$WB_DIR/ttk_design_doc_cases.csv"
```

各命令均须退出 0，保留原始输出及 `S2P1_postcheck_report.json`；必需用例集为空仍判 FAILED。
这些脚本只检查产物结构、Schema 和 CSV 格式，**不提供旧 `build_model` 的独立覆盖重算**。
必须继续按 SKILL.md 对照源码/设计逐项核对覆盖，并对照接口/spec 逐例核对 shape 合法性；缺证据或违规均判 FAILED。

## 原生 CSV 导出

需要导出或仅重导出时，在独立输出目录执行：

```bash
python3 "$WHITEBOX_SKILL/scripts/ttk_generate_kernel_csv.py" --op-name "$OP_NAME" \
    --low-cases "$WB_DIR/S5_cases_low.json" --high-cases "$WB_DIR/S5_cases_high.json" \
    --low-csv "$EXPORT_DIR/low.csv" --high-csv "$EXPORT_DIR/high.csv"
```

按阶段设计选取并整合为 `ttk_design_doc_cases.csv`，保留所有必需场景（包括设计要求的 high/特殊值）和原有精度标准。
导出会重新编号 `testcase_name`，用源文件及 `remark` 中的源 ID 核对逐例对应；合并时保持执行 ID 唯一。
复用仍遵守工作流的完整记录多重集、超大 shape 侧表和生成输入指纹规则，导出后重新执行 CSV 校验。

## 其它检查（见 SKILL.md）

用例符合设计、用例全部纳入执行、框架正确性与执行结果，仍由 st-verifier 按原检查清单逐项核对。
