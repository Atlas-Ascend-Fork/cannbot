# 从实验记录提炼可复用经验

两条语言路径共用。读取所有轮次的 analysis、contract、selection 和其引用证据；不能只处理保留方案。目标是让下一位开发者在不询问原作者的情况下判断何时采用、何时避免、先验证什么。

## 写作单元与证据边界

每条经验围绕一个可执行决策，而非一个轮次名词。正文必须说明：

1. **条件和问题**：实际平台/工具链、原路径、形状与参数谓词；已测条件与待迁移条件分开。
2. **改法和成本**：具体改了什么，保留哪些精度/同步/接口不变量；减少了哪些工作，又新增了哪些转换、搬运、清零、寄存器或调度成本。
3. **事实和归因**：观察逐条引用原文件的 JSON pointer 或行区间，附 SHA。源码结构、生成代码、实测时间分开；因果解释标 `supported|hypothesis|unknown`，并写尚未证明什么。机制发生不等于它解释了全部耗时。
4. **决策和反例**：在什么条件下采用/避免；失败后重试需要哪条新证据或哪项具体改动。一次失败不能否定整个方法族；正收益不能证明统计显著性。
5. **复核和证伪**：离线检查的实际文件/字段、操作和预期结果；哪些验证必须有设备；出现什么可观察结果会推翻或缩小这条经验。

写出复核步骤后，按所列文件/字段实际走一遍：字段必须存在，读数与步骤一致。区分合同的父实现身份、候选构建/加载身份和观察文件的证据身份；不能要求不同角色的文件都含同一 commit 或同名字段。字段缺失时指出可实际追踪的交叉引用，不能把希望存在的字段当作可执行步骤。

沿采集记录复核时，先读尝试的状态，再按冻结协议定位有效记录与其摘要；失败尝试可能没有 summary，不能假定第一个尝试成功，也不能按耗时挑选尝试。正文保留失败记录及其处理依据。

首次出现的专用缩写和布局公式符号在正文就地解释，尤其区分逻辑宽度、物理行距、向量长度和分块高度；不能只留外链让读者猜符号含义。

成功经验要给出边界，失败经验也要给出可重试条件。未测、编译失败、精度失败、证据无效、实测退化分别记录，缺失结果保持缺失。相似方法出现不同结果时，综合原路径/布局/调度/新增成本的差别；不把不同基线的收益连乘。最终原工程结果与实施阶段结果分开。

只有标题、指标表或文件清单不能替代这些正文。证据不足时写具体未知与补证动作，不为补齐栏目编造解释。

## 一个结构化源，生成一份可阅读正文

在 integration/ 下写 `experience-lessons.json`，再用 `$WORKFLOW_SCRIPTS/experience_reflux.py render` 生成 `experience-material.md`。此处脚本变量只在主端可用；派发给子代理的命令必须换成绝对路径。

JSON schema_version=1，字段如下（程序是机械校验真源）：

- `manifest: {path, sha256}`：本次冻结 manifest。
- `producer`：实际编写者/代理任务标识，不冒用账号。
- `context: {platform, toolchain, measurement, time}`：每项为具体文字，含实际实测范围。
- `sources`：`source_id -> {path, sha256}`，绝对路径。只收正文直接需要的原件；失效原件不能改写以配合经验。
- `rounds`：每个已完成轮次一项；`stage` 为状态中的完整保存点名，如 `round1.complete` 或 `gen.round1.complete`；`selection_source` 引用 sources；`outcome` 必须符合 selection，为 `accepted|rejected|implementation_failed|screened|no_candidate`。
  - 有正式候选实测：`performance: {source, geomean_speedup, case_count, comparison}`。source 必须是 `selection.search.effect_summary` 指向的**候选**摘要；comparison 写清候选与哪一父实现比较。不得拿保留基线的1.0掩盖失败候选。
  - 无正式候选实测：`performance: null`，不填估算加速比。历史 selection 无可绑定的候选摘要时另写 `performance_unavailable_reason`。
- `lessons`：经验数组，每项字段见下表。可一条覆盖多轮，但全部已完成轮次都须覆盖，不能遗漏失败。
- `synthesis`：跨轮决策启示的字符串数组，说明相似方法为何不可混为一谈、下一次先检查什么。
- `limitations`：具体未知和迁移限制的字符串数组。
- 无任何已完成尝试时：`rounds: []`、`lessons: []`、`no_attempt_reason`，不能虚构成功/失败经验。

| lesson 字段 | 内容 |
|---|---|
| id / title / rounds | 稳定条目ID、可读标题、对应保存点列表 |
| problem / change / benefit / cost | 原问题、实际改法、减少的工作、新增代价，各为文字 |
| applies_when / does_not_apply / invariants | 条件、反例/不可外推边界、不变量，各为非空字符串数组 |
| observations | `[{statement, evidence: [anchor, ...]}, ...]`，逐条观察绑定证据 |
| reasoning | `{status, statement, unproven, evidence: [anchor, ...]}`，status 为 supported/hypothesis/unknown |
| decision / retry_condition / falsification | 可执行采用/避免规则、重试条件、可观察推翻条件 |
| reproduction | `{offline_steps: [具体操作,...], expected: 预期结果, requires_device: 哪些检查仍需设备}` |

anchor 为 `{source: source_id, pointer: "/field/0/value"}` 或 `{source: source_id, lines: [起始行, 结束行]}`，二选一。锚点存在只证明定位有效，是否支持断言仍须语义核对。脚本从相邻 workflow-state.json 的完成轮次登记核对覆盖，不从作者自报的轮数判断。

```bash
python3 /absolute/workflow/scripts/experience_reflux.py render \
  --manifest /absolute/run/run-manifest.json \
  --bundle /absolute/run/integration/experience-lessons.json \
  --out /absolute/run/integration/experience-material.md
```

## 独立阅读验收

新请求默认冻结 `experience_policy={"id":"evidence_lessons_v2","version":2}`。原策略缺省的历史请求可离线采用本检查，不能改写旧 manifest 或追溯否定旧任务。

主 Agent 把实际正文和原件交给**未参与该正文编写的通用 subagent**；不给预期答案、期望分数或作者自评。先只读正文回答至少4道真实决策题，覆盖 apply/reject/retry/uncertainty，所有经验条目都须涉及；之后才沿来源核对事实。这只是文档行为评测，不代表独立设备作证。

输出 `experience-review.json`：

- `schema_version: 1`；`bundle`、`material` 各为精确 `{path,sha256}`；`reviewer` 为实际独立任务标识，不能等于 producer；`method` 说明评审输入、顺序和独立性的局限。
- `critical_errors: []`：无严重事实错误才可通过。有问题如实列出，不可删掉错误来过门。
- `dimensions` 的7个键：`conditions`, `changes_costs`, `evidence_reasoning`, `decisions`, `reproduction`, `coverage_synthesis`, `readability`。各为 `{score:0..4, reason, evidence:[anchor,...]}`。anchor 可引用 sources，或 `source:"material"`＋正文行区间。
- `reader_tests: [{id,category,question,answer,score:0..2,dangerous:false,lesson_ids:[...],evidence:[anchor,...]},...]`。问题要能区分“会用”和“背出结果”，并包含不满足条件的负例。

共同评分锚点：0缺失/错误；1仅名词或泛泛建议；2有细节但不能操作或边界/证据不足；3独立读者能作出具体且有依据的决策；4另有精确定位、边界反例和可观察证伪条件。每维≥3，总分≥85/100；阅读题≥87.5%，0个危险建议。评分必须引用实际内容，不按字数或栏目打分。字符串身份只能辅助核验，主端必须确保评审实际分离。

```bash
python3 /absolute/workflow/scripts/experience_reflux.py check \
  --manifest /absolute/run/run-manifest.json \
  --bundle /absolute/run/integration/experience-lessons.json \
  --material /absolute/run/integration/experience-material.md \
  --review /absolute/run/integration/experience-review.json \
  --out /absolute/run/integration/experience-quality.json
```

`structure_pass` 只表示结构、出处和数值核验通过；只有绑定当前正文的独立阅读评审合格才是 `pass`。主端在 phase.integration 显式登记 bundle/material/review 和 `knowledge-reflux.json`；状态脚本重算质量门禁并登记证据闭包，不能仅注册一个自报 pass 文件。

## RSI 修正与回流

先冻结量表、读者题及原产物快照，再改工作流。每次改动用新目录保存流程 diff、正文、评分、反例结果和修正理由；只修已暴露的缺口。改尺须明确版本并对基线和候选同时重评，不能降门限保候选。达到门槛后停止。

评测未通过时修正文或来源定位；真正缺失的工程证据必须保持未知。文档修正不触发 NPU 重测，除非用户授权的任务仍需要它。复盘内容回填未来轮次的 analysis/selection，不能修改已冻结历史记录。

通过后的 `experience-material.md` 是本地评审正文，允许含本地证据路径，但不能直接当公开回流卡发布。新请求的 `evidence_lessons_v2` 还必须完成 [可移植回流交付](portable-reflux.md)：选择最小充分证据、生成脱敏副本、重绑定哈希和仓内链接、隔离目录核验。正文内容保留完整；个人工号、用户目录、内部项目名不得随证据包重新泄露。旧 `evidence_lessons_v1` 与缺省策略保持历史行为，不静默改写冻结记录。

`knowledge-reflux.json` 继续以实际 `{path,sha256}` 绑定原料卡、本地已评正文与评审；v2 增加 `portable_delivery` 引用本地私有交付契约。检查器证明公开正文只经过声明的路径/标识替换、哈希重绑定和证据链接迁移，逐项校验全部直接来源的公开副本。公开副本字节改变后，原语义分数仍只属于原本地评审，不能当作新公开版本的评审；投稿端按接收仓规则等待独立审阅。

REFINERY_ROOT 不可用时也在 integration/knowledge-reflux/ 下交付可携带的材料。任务内身份文件和含原路径的映射留在本地私有目录；只将明确列入公开集合的文件写到原料区。旧卡被既有验收绑定时追加修订，不覆盖历史。不冒用账号、不自动 commit/push，不把 rough 当作 book 知识。

原料数据与通用工具、收料规则分别交付：数据投稿不夹带接收仓工具/README约定修改，工作流工具随本插件维护。rough 到 book 需要独立精炼：拆主张、补 probe/obs、登记验证事件并审读/复验；书内证据自足。性能分析读取 book 不会自动消费新 rough，报告应分别说明“原料已交付”和“知识已精炼/已被使用”。
