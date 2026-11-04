---
name: st-verifier
description: ACLNN ST 测试产物验收技能。供 st-verifier 子agent 对「白盒/黑盒用例生成、纳入 ST 框架、批量执行、ST 框架开发」做实质检查:用例结构覆盖度(对照源码及原生用例独立核对覆盖)、用例是否符合方案设计(分支验证 / `docs/{OP}/design/Validation.md`「端到端测试用例矩阵」枚举测试点全命中)、用例是否全部纳入框架(生成==执行 CSV==结果条数)、框架正确性(可读全部用例、golden 独立)、执行结果(全量执行/skip/pass 数)。当验收 ST 测试产物任务时使用。
disable-model-invocation: true
---

# ACLNN ST 测试产物验收

本技能供 `st-verifier` 子agent 验收 ST 测试产物,做**实质检查**(而非通用 verifier 的"文件存在 + 退出码")。

## 内容
- `references/README.md`：当前白盒技能的公开校验命令及依赖预检；黑盒使用自身生成技能的 QA/CSV 校验入口。
- `scripts/check_runtime_result.py`：按工作流要求检查 OOM / 确定性结果，精度 PASS 不能替代这些检查。

## 六类检查（据任务类型选相关项，逐项实质检查，优先可执行命令 + 退出码）

1. **用例结构覆盖度**：白盒先按 README 实跑原生 S2P1 校验，再独立对照 tiling/kernel 源码检查
   `S2P1_path_list.json`、`S2P1_cases.json` 到 `S5_cases_low.json` 的路径、size/align/dtype 与广播覆盖。
   黑盒按自身测试因子与约束核对覆盖。原生结构校验退出码 0 不等于覆盖达标，缺项 → FAILED。
2. **用例符合方案设计**：读该阶段 / 分支的设计章节（分支 `docs/{OP}/design/branches/DESIGN-BRANCH-<key>.md §9 分支验证`、`docs/{OP}/design/Validation.md`「端到端测试用例矩阵」、
   `docs/{OP}/design/BranchRoute.md` 所辖组合），逐条核对 **设计枚举的每个测试点**（基础 shape×dtype、边界、特殊值、Attr 变体…每一类场景）在交付
   cases 里都有对应用例；设计指定却缺失的场景 → FAILED。与 1 **互补**：1 独立对照源码查结构空间是否扫全，2 查设计文档
   明确枚举的具体场景是否落地。以设计文档为准，不臆造设计没写的、也不放过设计写了却没落地的。
3. **用例是否全部纳入框架**：生成用例逐例对应执行 CSV == runner 实际加载执行的用例
   == 原生结果记录；按本阶段选例范围核对 ID 与内容（白盒导出重编号时用 `remark` 中的源 ID 溯源）；任一环对不上（框架静默丢用例 / 只纳入部分 / 转换漏行）→ FAILED。
4. **框架正确性**：能 build、逐用例驱动 aclnn 精度比对、**golden 独立于被测 kernel**（不自证）、能被任务指定的 runner
   全量加载跑起来（不因格式不兼容读 0 条、不 skip 整批）。
5. **执行结果**：**本阶段指定范围全量执行**（禁 `--quick`/`--max-cases`/只跑前 N 条，查日志 `total` 数）；警惕大批 `tensor_too_large`
   skip（= 生成尺寸超框架可执行上限，生成侧须对齐）；按阶段判：TDD 造用例阶段期望红、成品验证阶段期望全绿（`[FAIL]`/`[SKIP]` 为 0）。

6. **输入 shape 合法性(spec 硬约束)**：白盒按 README 实跑原生 S5 schema 校验；再逐条对照算子接口/spec
   核对非 error 用例的 rank、dtype、从属 shape 与广播关系，schema PASS 不能替代此检查。
   黑盒使用自身 QA/CSV 校验入口，并做相同的接口约束复核；违规 → FAILED。

## 硬规则
- 覆盖度独立对照源码与接口约束，**不以 agent 自述字段或结构校验 PASS 代替覆盖证据**。
- 设计符合性以设计文档为准；结构覆盖与设计符合性**两者都要过**，缺一不可。
- **失败报告中 tiling_key 标注须用 `GET_TPL_TILING_KEY` 实际位编码值**，不得直接套用 `docs/{OP}/design/BranchRoute.md` 逻辑编号——两者可能不一致。标注格式：`tiling_key=<实际值> (<模板参数名=值>, <分支名>)`。
- **标准产物必须存在**（前置硬门禁）：白盒按当前生成技能交付 `S2P1_*`、`S5_cases_low.json` / `S5_cases_high.json` 和 CSV；
  黑盒按自身生成技能交付；执行类必须有本阶段执行 CSV、选例记录和原生结果/日志。缺输入、必需用例集为空 → FAILED。
  README 中适用的校验必须实跑，非零退出或独立覆盖/shape 检查缺证据均判 FAILED，不能跳过。
