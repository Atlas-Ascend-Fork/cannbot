# 测试 fixtures 说明

本目录存放报告质量 lint 的**合成测试输入**，供单元/集成测试使用，**不是项目文档**。

每个 lint 都有一对 `LEGIT`（应通过，退出码 0）与 `VIOLATING`（应被检出，退出码 2）夹具：

| 夹具 | 关联 lint |
| --- | --- |
| `report_archive_link_legit.md` / `report_archive_link_violating.md` | `report_archive_link_lint.py` |
| `report_jargon_legit.md` / `report_jargon_violating.md` | `report_jargon_lint.py` |
| `report_not_log_legit.md` / `report_not_log_violating.md` | `report_not_log_lint.py` |

对应测试见 `engine/src/scripts/orchestrator/tests/it/test_report_quality_lints.py`。

## 链接为有意占位，请勿“修复”

`report_archive_link_*.md`、`report_jargon_*.md` 中的相对链接（例如
`src/kernels/x_fwd_simd/`、`src/kernels/x_fwd_simd/verification.json`）是**有意构造的占位路径**：

- 它们必须命中 `report_archive_link_lint.py` 的归档链接识别规则（链接 target 包含 `kernels/`
  或以 `verification.json` 结尾），LEGIT 夹具才能通过校验；
- 这些路径在磁盘上**刻意不存在**，因为本仓库并没有真实的 `src/kernels/` 归档目录。

若把这些占位链接改成仓库内真实存在的路径，反而会使其不再匹配归档链接约定，导致
`test_archive_link_legit_passes_no_false_positive` 等用例失败。因此请保留这些链接原样。

## 不参与仓库链接校验

由于上述原因，本目录被仓库级 Markdown 链接校验显式排除：`scripts/md_link_validator.py` 中的
`EXCLUDE_PATH_PARTS = {"fixtures"}` 会跳过相对路径中任一片段为 `fixtures` 的全部 Markdown 文件，
因此这些占位链接不会被判定为死链。在 GitCode 网页中点击这些链接无法跳转属预期行为。
