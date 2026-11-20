# 会话自蒸馏知识卡片 — prompt 模板

> 规章来源: 本文件所在的知识库目录（`RULES.md`、`form/`、`GOVERNANCE.md`）。
> 用法: 把 <> 占位换成本次会话的真实值, 整段作为一轮输入交给蒸馏 agent。

---

把本次会话及其产物蒸馏成知识卡片。形式与规章遵循
本文件所在的知识库目录。下文路径均相对该目录，运行检查前切换到该目录。

## 输入

- 会话: <会话标识 / 日期>
- 产物: <逐条列出路径 —— 源文件、commit sha、日志、测量输出、脚本>
- 环境 pin: <机器 / 板卡 SKU / 工具链版本 / 仓库 commit>, 每项附一条 re-derive 命令
- 落库位置: <目标目录>

## 先读, 不跳

1. [RULES.md](RULES.md)
2. [form/ENTRY_TEMPLATE.md](form/ENTRY_TEMPLATE.md)、[form/STRATA.md](form/STRATA.md)、[form/CONVENTIONS.md](form/CONVENTIONS.md)
3. 两条现成条目当语气样本: 一条 `harvested`
   (`book-910/entries/0071-*`)、一条 `verified`
   (`book-950/entries/0489-*`)

读完不要复述读了什么, 直接进 Step 1。

## Step 1 · 候选提取 (先不写卡)

逐条列出本次会话里可能成立的主张, 每条写成一句话的句子形态 slug
(例: `a-slot-constant-that-disagrees-with-initbuffer-reads-clean-on-task-zero`),
禁止主题形态 (`notes` / `misc` / `overview` / `性能优化总结`)。

## Step 2 · 准入筛 (多数候选应当在这里死掉)

对每条候选回答: **没有这条, 一个称职的 agent 会走哪一步错路, 为什么常规检查抓不到它。**
答不出来的一律丢弃, 并写进拒绝清单 (候选 + 丢弃理由), 拒绝清单与卡片一起交付。

## Step 3 · 定分层 (会话 → kb 分层的映射)

- **session-observed** (对应 `verified`): 命令与读数在产物里真实存在, 且照着产物能重跑。
  `INDEX:` 填 means / conditions / time, 每项附 re-derive 命令; `BOARD:` 写本次真跑的那块。
- **harvested**: 本次只是在会话里读到了文档或代码, 没有运行。§1 只许写 "upstream asserts",
  `INDEX: none — nothing measured; see SOURCE.`, §6 写 NOT YET RUN。
- **既没跑也没出处, 只是会话里推出来的**: 不建卡, 写进 `STANDING_QUESTIONS.md`,
  格式为 问题一行 · MEASUREMENT · READOUT · POSED · STATE UNANSWERED。

## Step 4 · 写卡

照 `ENTRY_TEMPLATE.md` 的头部字段与七节写, 一卡一主张, 文件名即主张。

## Step 5 · 事后判据的诚实条款 (会话蒸馏独有, 不得省略)

模板的 §5 要求判据先于运行声明。会话蒸馏几乎总是反过来 —— 判据是看完读数才写的。
凡属这种情况, 在 `STRATUM:` 的限定行里原话写明
`predicate declared after the readouts were seen`,
并在 §7 列出它因此没有排除的替代解释。
**不得把事后判据写成事前**; 这一格造假会让整张卡失去判决力。

## Step 6 · 过形式检查

运行 `tools/check_entries.sh <目标目录>`, 修到全 ok。

## Step 7 · 交付

卡片文件 + 拒绝清单 + `STANDING_QUESTIONS.md` 增补, 三项缺一不可。

## 硬约束 (逐条遵守)

- **出处先于主张**, 且出处必须指向会话之外仍然存在的东西: `路径:行号`、commit sha、
  日志文件、可重跑的命令。只存在于对话记录里的东西不能当出处 —— 它不可复核,
  这类主张降一层或进 standing question。
- **范围不超过证据**: 板卡 SKU、工具链版本、shape、commit, 一个字都不许超出本次实际覆盖的。
  在环境 A 上量到的结果不得写成普适结论。
- **测量与推断分句写**, 禁止用"所以 / 因此 / 这说明"把两者接在同一句里。
- **`OVERTURN:` 每张卡必填**, 内容是一条具体观测, 不是"如果以后发现不对"。
- **§7 非空**: 没碰的板子、没扫的形状、这次什么也没测, 都要写出来。
- **保留会话里被推翻的中间结论**: 原文留着, 标注推翻日期与反证; 不要只留最终正确版本。
- **引用已有条目**要注明其分层 (`[910:0071] harvested`)。
- **不为凑数量建卡**。本次会话一张卡也蒸馏不出来是合法输出, 直接说明并只交拒绝清单。
