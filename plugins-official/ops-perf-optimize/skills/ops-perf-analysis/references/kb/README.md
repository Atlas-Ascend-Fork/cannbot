# kb — 板卡事实库

按板卡组织的单条事实库，供 `ops-perf-analysis` 在搜索优化策略时检索，与瓶颈诊断和分析方法互补。

检索入口：[910 册索引](book-910/INDEX.md)、[950 册索引](book-950/INDEX.md)；先按目标板卡检索对应册，再阅读全文并按[治理规则](GOVERNANCE.md#1-引用)引用。该库随技能提供，不依赖外部 `KB_ROOT` 或 Query 索引。

- `book-910/entries/` — 910B2 → 910C，77 条
- `book-950/entries/` — 950PR / 950DT，359 条

每个条目只放一条主张，并注明出处（写在主张之前）、适用范围（具体到板卡 SKU，不超过证据覆盖的范围）、
推翻条件，以及验证分层：`verified` 在具名板卡上实测复现，`corroborated` 有独立来源旁证，
`harvested` 仅来自文档或代码、尚未上板，`overturned` 已被反证推翻（原文保留）。
两册事实互不通用。

引用格式 `[910:NNNN]` / `[950:NNNN]`，引用时注明分层。每册的 `INDEX.md` 按编号列出分层与主张，
可以先读索引再打开条目；条目文件名即该条主张，结论被更正时文件名与索引一起更新（见 `RULES.md` 第 9 条）。

本目录初始迁自 `skills-dev/ops/ascendc-perf-optimize/references/kb/`，当前按 `kb-session-distill-20261028.tar.gz` 更新。条目里的 *upstream* 指该条 `SOURCE:` 引用的原始文档，多为来源仓 `ops/` 下的参考资料，或厂商 SDK 头文件与手册。迁移保留条目、索引、采集记录、模板及校验工具；历史来源路径与证据按原文保留，不表示这些外部文件也已迁入本仓。

新建条目、补证晋升、申诉与推翻见 `GOVERNANCE.md`，条目规则见 `RULES.md`，模板与命名约定见 `form/`，
形式检查脚本在 `tools/`。`harvest/` 是条目 `SOURCE:` 链引用的原始材料与矛盾清单。

从调优会话续写知识条目时，使用随版本提供的[会话蒸馏模板](session-distill-prompt.md)，按本库规则提取主张、核对证据和验证分层，并运行形式检查。

## 与 `ops/npu-arch` 的关系

来源仓的 `ops/npu-arch` 是整理好的每代参数参考，读它就能拿到一个数；本目录是逐条证据台账，
记录某个数是谁说的、在哪块板上验过、什么观测会推翻它。两处对同一参数给出不同答案时，
以带 `verified` 证据的条目为准，并给 `npu-arch` 提 issue 或 PR 更正，不要只改一边。

## 谁能补充，怎么补充

`harvested` 与 `corroborated` 条目只需要文档或代码来源，任何人都可以按 `GOVERNANCE.md`
新增或申诉。升到 `verified` 需要在具名板卡上实测复现，因此实际由有对应硬件的人推进；
当前 436 条里 `verified` 28 条、`corroborated` 32 条、`overturned` 2 条，其余为 `harvested`。

编号只增不重用：已撤下的条目号（950 册 0001-0004、0114）不再分配，
`ls entries/` 中的空号是撤号，不是遗漏。
