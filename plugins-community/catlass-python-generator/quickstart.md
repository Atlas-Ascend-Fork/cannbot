# CANNBot · Catlass Python 算子开发快速入门

## 概述

`catlass-python-generator` 为 Ascend NPU CATLASS Python 算子开发提供完整流程指引，覆盖设计、
编码、基准测试、性能优化与知识管理五个阶段。Skill 本体由 cannbot-skills 仓
`community/ops/catlass-python-*` 维护，静态知识由 cannbot-knowledge 仓
`knowledge/ops/catlass-dsl/` 原位只读供给；两者均由安装器接入，项目中不生成私有知识副本。
design / develop 前必须成功下载 catlass master 归档到 `.catlass-python/references/catlass/`，
下载失败即停止推进。

**本版本是门禁引导工作流**：不包含 `develop_state.py`、`optimize_state.py`、`bench.py`、
`verification.py`、`validate_reference.py`、`record_knowledge.py` 等状态机脚本；阶段推进
由各 `SKILL.md`、`AGENTS.md` 与工作区 `ITERATIONS.md` 中的真实执行记录承担，并由只读门禁
脚本 `skills/catlass-python-workflow/scripts/gate.py` 核对产物与记录。

---

## 一、安装

> 安装前请确认来源可信。`/path/to/workspace` 是开发项目，不是插件源码目录。

### 源码安装（当前可用）

使用官方主仓最新 `master`，安装器从 `vendor/cannbot-skills` 链接 6 个 Skill，并下载
cannbot-knowledge 知识库：

```bash
git clone --branch master https://gitcode.com/cann/cannbot.git /path/to/cannbot
bash /path/to/cannbot/plugins-community/catlass-python-generator/init.sh \
  project codex /path/to/workspace
```

客户端参数可替换为 `opencode`、`claude`、`trae`、`cursor`、`copilot` 或 `codearts`。
不提供目标路径时默认安装到 cannbot 仓根，建议明确目标路径。安装后进入该项目启动客户端。

### 自动安装的依赖

| 仓库 | 资源 |
|---|---|
| `https://gitcode.com/cann/cannbot-skills.git` | `community/ops/` 下 6 个 `catlass-python-*` Skill |
| `https://gitcode.com/cann/cannbot-knowledge.git` | `knowledge/ops/catlass-dsl/` 下的知识卡 |

```text
<workspace>/
├── .agents/skills/catlass-python-*        # Codex / OpenCode 的 6 个 Skill
└── .cannbot/dependencies/catlass-python-generator/
    └── cannbot-knowledge/knowledge/ops/catlass-dsl/
```

6 个 Skill 为 `catlass-python-workflow`、`catlass-python-design`、`catlass-python-develop`、
`catlass-python-bench`、`catlass-python-optimize`、`catlass-python-knowledge`。Claude Code 使用
`.claude/skills/`，其他客户端使用其对应 Skill 目录。项目配置目录下的
`cannbot-plugin.json` 记录知识库依赖路径及已安装 Skill 的路径。

`CANNBOT_KNOWLEDGE_ROOT` 若用于知识读取，指向知识**仓根目录**（不是其 `knowledge/`
子目录），不会改变安装器下载依赖的位置。源码安装的 `--skills <SHA|path>` 可选择共享
Skills 版本，不改变知识库下载位置。

`catlass-python-knowledge-upgrade` 是维护者 Skill，不由安装器装入客户工程；维护者在
cannbot-skills 仓内直接使用。

---

## 二、快速上手

开发新算子只需两步：

> **第一步** — 使用 `catlass-python-design` 生成算子规格、初步设计、Torch
> `reference.py` 精度标杆、`definition.json`、`workload.jsonl` 与
> `workload_dev.jsonl`：

```text
使用 catlass-python-design 设计一个 <算子名称> 算子。
输入、输出、dtype、shape、数值语义和性能目标是：...
```

> **第二步（默认直通，无需批准）** — 产物齐备后自动进入 `develop`，继续完成
> **骨架 → 实现（自然划分版）→ 调试 → full test #1 → merge（仅 `merge_required: true`）
> → full test #2 → optimize → Review → 全量测试验收（kernel 变化时补跑 #3，无融合记 #2）
> → Benchmark/Profiling（仅用户明确要求性能时）**。
> 只有你想先评审设计时才需要额外说一句：

```text
先给我看设计
```

`design` 会暂停并展示产物；回复“继续”即进入开发，不需要“批准”字样。

`develop` 会按 `ITERATIONS.md` 逐个里程碑推进：含 MMAD 的算子（纯 matmul 与 CV 融合都算）
先把每个 matmul 阶段剥成单 GEMM 骨架，**各自**按时间与流水判据判定（先做解析预筛、实跑
不超过 3 组，骨架同步只用 mutex；骨架直接复制 `templates/skeleton_gemm.py` +
`skeleton_profile.py` + `skeleton_spec.json`，只填 spec 与 kernel 体；不达标可写豁免理由），
再按「正确性 → 边界 → 性能细节」扩展。骨架只是测量工件，不改变最终 kernel 划分。阶段
顺序固定为 focused test → **full test #1** → **merge**（仅 `merge_required: true`，
无融合时记 `not_applicable`）→ **full test #2** → optimize（有目标走模式 A，无目标走模式 B
2~3 轮，上限 3 轮）→ targeted/final review →
全量测试验收（kernel 变化时补跑 **full test #3**，无融合阶段时记 `#2`）→ [benchmark]。
每次进入下一阶段前都要先跑门禁并通过：

> 按结构找参考样例：Cube-only → `tla/kernel/matmul/basic_mmad/basic_matmul.py`；
> Cube-Vector → `experimental/kernel/matmul/matmul_softmax_row_stats/matmul_softmax_row_stats.py`；
> Cube-Vector-Cube → `experimental/kernel/matmul/matmul_add_chain/matmul_add_chain.py`；
> 纯 vector → `tla/kernel/vec/basic_vadd/basic_vadd.py`、`dsl_tutorials/vector_simd_ops/`、
> `dsl_tutorials/vector_simt_ops/`。路径以
> 工作区 `.catlass-python/references/catlass/` 下 `find` 的结果为准。
> 整体结构优先：先选阶段序列、数据流、任务映射、同步方式都接近的主参考；主参考是基线
> 不是约束，偏离写清理由。没有足够契合的主参考时，可以组合多个分步样例，但要显式设计
> 整体结构并照常跑 skeleton DoD。

```bash
python3 skills/catlass-python-workflow/scripts/gate.py <阶段> --workspace <项目根>
```

门禁是只读校验（产物 + `ITERATIONS.md`），跳步、缺少当前 kernel 的全量测试或缺少设计交付物
都会被直接拦下；`FAIL` 时必须补真实证据，不能手改记录绕过。

`DESIGN.md` 的 `性能要求：` 决定是否采集性能：只有用户明确提出性能、时延或加速比时才写
`requested`，此时当前 kernel 全量测试后执行 benchmark 与 profiling；写 `none` 时当前 kernel
全量测试通过后直接 finish，不跑 benchmark、不做 profiling。优化全部未采纳、kernel 未变化时
可复用最近一次全量测试（有融合时为 `full test #2`，无融合时为 `full test #1`）作为交付证据，
采纳改动导致 kernel 变化时才必须补跑 `full test #3`（无融合阶段时记 `#2`）。

执行模式在任务开始时确定并写入 `DESIGN.md` 的 `执行模式：` 行，门禁只读这一行、不做本地
环境探测：

- `remote-detached`：本地生成、当前拿不到远端连接、无本机 NPU，最多推进到代码生成完成，
  focused test 可写 `deferred` 并附精确重跑命令，之后必须先连上远端；
- `remote-connected`：本地生成、远端可连接，全流程真实执行；
- `local`：本地生成并在本机调试，全流程真实执行；
- full test #1 及之后都不接受推迟，`design` 与 `finish` 永不豁免，`finish` 见到任何
  `deferred` 行即 FAIL。

---

## 三、可用技能

| Skill | 用途 | 示例 |
|:------|:-----|:-----|
| `catlass-python-workflow` | 入口：阶段路由、流程约束与证据要求 | 任意 CATLASS Python 算子请求 |
| `catlass-python-design` | 生成规格、Torch 精度标杆和 workload 用例 | `设计一个 float16 masked softmax 算子` |
| `catlass-python-develop` | 按设计完成开发、调试、评审与交付 | `按照 DESIGN.md 实现并完成测试` |
| `catlass-python-bench` | 独立验证正确性与测量性能 | `用 solution、workload 和 definition 执行 benchmark` |
| `catlass-python-optimize` | 独立优化已有算子 | `优化 matmul，目标 mean_ms < 0.5` |
| `catlass-python-knowledge` | 查询或记录 CATLASS Python 知识 | `查询 layout 不一致的排查方法` |

> **提示：** `debug` 和 `review` 已内置在 `develop` 流程中，无需单独调用。冻结后的
> `DESIGN.md` 评测口径不应直接修改；实现方案变化时在 `ITERATIONS.md` 记录设计修订。

---

## 四、独立使用

### Benchmark

三个输入文件的接口定义见 `catlass-python-bench` 的 `SKILL.md`。本版本不提供 `bench.py`，
需要由 Agent 写一次性测量脚本（建议 `tools/bench_local.py`），按以下口径实现：

- 逐例生成输入、分别执行 reference 与 candidate，按 tolerance 比对；
- 同步 warmup 1 次，配对采集 2 次（需要更稳时可到 5 次；`mean_ms` 取算术平均，
  `median_ms`/`all_ms` 作噪声参考）；
- 用 `torch.npu.Event` 记录每个用例的 `run` 到同步完成的耗时；
- 计时边界与 `device_ms`/`host_gap_ms` 分层见 bench 的「算子耗时的边界与分层」；
- 结果写入 `result.json`，至少包含 `performance.candidate.mean_ms`（end2end 口径）、
  逐例 candidate/reference 耗时、`selection.paired` 和 profiling 路径。

### Optimize

调用 optimize 时需提供算子路径、测试命令、benchmark 指标、design 冻结的
`workload_dev.jsonl` 和迭代上限；有明确目标时给出阈值（模式 A），没有目标时省略阈值、
按 2~3 轮执行（模式 B，上限 3 轮）：

```text
使用 catlass-python-optimize 优化 src/matmul.py。
完整测试命令为 ...，benchmark 指标为 performance.candidate.mean_ms，
目标小于 0.5 ms，最多迭代 8 轮。
```

每轮的 bottleneck、改动轴、前后耗时、决策和证据写入 optimize 的 `ITERATIONS.md`。

### Knowledge

知识库是已安装的 cannbot-knowledge `knowledge/ops/catlass-dsl/` 下的 Markdown bundle。
查询时先读 `knowledge/ops/catlass-dsl/index.md`，再读目标分类的 `index.md`，最后只读实际
采用的条目；项目实测经验写入 `<project>/.catlass-python/knowledge/learned/`，按
`catlass-python-knowledge` 的 `SKILL.md` 入库标准手工创建文件。

> 知识涵盖 DSL API、算子样例描述、调试方法、优化技巧及项目实测经验。查询仅读取本地
> 文件；实际样例源码以工作区下载的 catlass 归档为准。

---

## 五、使用要求

- 直接在当前 **Git workspace** 中运行，并明确允许修改的路径；
- 测试、benchmark 和 profiling 命令应能从目标项目直接执行；
- 融合范围由 design 按整体性能确定，NPU 结果应保留 profiling CSV 证据；
- 缺少 CANN、NPU 或 CATLASS Python 环境时，相关结果为 `not_run`，不会被视作通过。

---

## 完整生成与后续调试

develop 先落性能骨架并达标，再扩展主 Python 文件内的全部 kernel、host 编排及完整
`solution.json`。生成阶段只产出文件，不在本地做语法检查、模拟检查或标杆运行；不论
一开始是否有服务器信息、或本来就在服务器上，都先生成再推进。生成完成不代表验证通过。

随后进入 focused test；编译、运行、精度或评审失败时先查知识库、读取采用条目，再增量
修改并重建 `solution.json`，回到验证。本地生成、远端验证时，静态检查、reference 运行、
编译、上板、精度、benchmark、profiling 全部在真实环境完成；环境缺失记录 `blocked` /
`not_run`，保留代码及待执行阶段，环境就绪后直接继续。连接与同步由使用者现有方式处理。

focused test 通过后先跑全量测试 #1；`merge_required: true` 时再走 merge 阶段融合为单 kernel
并跑全量测试 #2，然后进入 optimize（有目标走模式 A，无目标走模式 B 2~3 轮，上限 3 轮），
完成后经 targeted_review / final_review、全量测试验收（kernel 变化时补跑 #3，无融合记 #2，
2~5 片）交付；声明 `性能要求：requested` 时再执行逐例配对 benchmark 与 profiling。每一步
进入前都要通过 `gate.py` 对应门禁。

所有阶段的里程碑、命令、结果和证据路径都记录在工作区 `ITERATIONS.md`；没有执行记录的
结论不进入交付报告。
