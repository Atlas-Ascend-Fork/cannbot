---
name: st-verifier
description: ACLNN ST 测试产物验收技能。供 st-verifier 子agent 对「白盒/黑盒用例生成、纳入 ST 框架、批量执行、ST 框架开发」做实质检查:用例结构覆盖度(coverage_audit.py 独立用 build_model 重算期望覆盖)、用例是否符合方案设计(分支验证 / `docs/{OP}/design/Validation.md`「端到端测试用例矩阵」枚举测试点全命中)、用例是否全部纳入框架(生成==manifest==执行条数)、框架正确性(可读全部用例、golden 独立)、执行结果(全量执行/skip/pass 数)。当验收 ST 测试产物任务时使用。
disable-model-invocation: true
---

# ACLNN ST 测试产物验收

本技能供 `st-verifier` 子agent 验收 ST 测试产物,做**实质检查**(而非通用 verifier 的"文件存在 + 退出码")。

## 内容
- `references/coverage_audit.py`:**结构覆盖度审计**——独立用白盒统一入口的 `build_model` 重算该阶段期望的结构覆盖签名集，
  比对交付 `design_doc_cases.json` 里 cases 的实际覆盖(size/align/dtype 须全覆盖、广播分支须有真实广播对)。
  逻辑单一真源在白盒统一入口 `skills/ascendc-whitebox-design/references/whitebox_designer.py`,本脚本薄封装、不复制逻辑。
- `references/README.md`:用法。

## 五类检查（据任务类型选相关项，逐项实质检查，优先可执行命令 + 退出码）

1. **用例结构覆盖度**：跑 `coverage_audit.py <design_doc_cases.json> <design_facts.json> <opspec.json>`，**退出码 0**。
   结构轴(size/align/dtype)全覆盖、广播对齐全；不达标 = 用例缩档 / 手搓绕过统一入口 `gen_cases`。**只信 build_model
   重算的期望，不读 agent 自述的 target_sigs**（独立于被测产物）。
2. **用例符合方案设计**：读该阶段 / 分支的设计章节（分支 `docs/{OP}/design/branches/DESIGN-BRANCH-<key>.md §9 分支验证`、`docs/{OP}/design/Validation.md`「端到端测试用例矩阵」、
   `docs/{OP}/design/BranchRoute.md` 所辖组合），逐条核对 **设计枚举的每个测试点**（基础 shape×dtype、边界、特殊值、Attr 变体…每一类场景）在交付
   cases 里都有对应用例；设计指定却缺失的场景 → FAILED。与 1 **互补**：1 独立于设计文档查结构空间是否扫全，2 查设计文档
   明确枚举的具体场景是否落地。以设计文档为准，不臆造设计没写的、也不放过设计写了却没落地的。
3. **用例是否全部纳入框架**：生成条数(CSV 数据行数) == 框架 manifest(`aclnn_cpp_cases*.json`)`cases` 条数
   == 可被 `test_aclnn` 加载执行的条数；任一环对不上（框架静默丢用例 / 只纳入部分 / 转换漏行）→ FAILED。
4. **框架正确性**：能 build、逐用例驱动 aclnn 精度比对、**golden 独立于被测 kernel**（不自证）、能被 `test_aclnn`
   全量加载跑起来（不因格式不兼容读 0 条、不 skip 整批）。
5. **执行结果**：**全量执行**（禁 `--quick`/`--max-cases`/只跑前 N 条，查日志 `total` 数）；警惕大批 `tensor_too_large`
   skip（= 生成尺寸超框架可执行上限，生成侧须对齐）；按阶段判：TDD 造用例阶段期望红、成品验证阶段期望全绿（`[FAIL]`/`[SKIP]` 为 0）。

6. **输入 shape 合法性(spec 硬约束)**:跑 `shape_audit.py <design_doc_cases.json> <design_facts.json>
   <opspec.json>`,**退出码 0**。校验每条非 error 用例的 per-input `rank_range` 与 `inputs[].shape_rule`
   (从属输入 shape 从锚派生 期望==实际)。违规 = 生成了 spec 不支持的用例(多输入耦合算子常见:
   从属输入被误当成与锚输入同秩)→ FAILED。与结构覆盖互补:覆盖查"扫全没",此项查"合不合法"。

## 硬规则
- 覆盖度只信 `build_model` 重算的期望，**不读 agent 自述字段**（独立于被测产物，同 oracle 独立原则）。
- 设计符合性以设计文档为准；结构覆盖与设计符合性**两者都要过**，缺一不可。
- **失败报告中 tiling_key 标注须用 `GET_TPL_TILING_KEY` 实际位编码值**，不得直接套用 `docs/{OP}/design/BranchRoute.md` 逻辑编号——两者可能不一致。标注格式：`tiling_key=<实际值> (<模板参数名=值>, <分支名>)`。
- **标准产物必须存在**（前置硬门禁）：用例生成类无 `design_doc_cases.json` / 生成 CSV、或执行类无 manifest
  （`aclnn_cpp_cases*.json`）/ `cases` 为空 → **直接 FAILED**；缺输入**不得**静默跳过对应检查。`coverage_audit.py`
  必须**实跑**，退出码非 0（含文件缺失导致的失败）一律判 FAILED —— 手搓内联绕过统一入口 = 不产标准产物，必须在此拦下。
