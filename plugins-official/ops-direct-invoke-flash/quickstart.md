# ops-direct-invoke-flash 快速入门

`ops-direct-invoke-flash` 从 CPU 函数、数学公式、代码片段或文本描述出发，端到端构建并验证一个全新的 Ascend C 核函数；目标芯片为 Ascend950 / `dav-3510` 时默认生成原生 `AscendC::Reg` 计算代码。工作流覆盖环境探测 → 定义/设计文档 → 增量实现 → NPU 验证 → 收尾文档。

本文面向使用者，说明如何安装、发起任务和验证安装。机器执行规则以 `skills/ops-direct-invoke-flash/SKILL.md` 为准。

## 触发边界

只有用户明确要求「构建/开发一个新的核函数」时才触发。会触发：「根据 relu.py 开发一个 relu 核函数」、「按这个公式写一个 Ascend C 算子」。不会触发：对已完成算子的单点修改、性能调优（用 `ops-perf-optimize`）、精度排障、安装与使用咨询。

## 1. 安装

### npx 安装（推荐）

**必须在实际要开发算子的工程目录下执行**，安装器会把 Skills、`AGENTS.md` 和 `.cannbot/` 资产写入当前目录。

```bash
cd /path/to/your/operator-project
npx @cannbot-plugin/cannbot@latest install ops-direct-invoke-flash --tool opencode
```

### 源码安装

```bash
git clone --recurse-submodules --shallow-submodules https://gitcode.com/cann/cannbot.git
bash /path/to/cannbot/plugins-official/ops-direct-invoke-flash/init.sh project opencode /path/to/your/operator-project
```

`--tool` / 第二个位置参数可选 `opencode`（默认）、`claude`、`codex`、`trae`、`dsh`。统一安装器**仅支持项目级安装**；源码安装可用 `--skills <SHA|本地仓路径>` 锁定共享 Skill 版本。命令可幂等重跑，用于刷新插件或复查安装。

各客户端通用参数与安装控制详见[插件安装与工作流](../../script/docs/cannbot-workflows.md)。

## 2. 安装内容

1. **Skills**：插件自带的入口 Skill `ops-direct-invoke-flash`（含 `hooks/`、`references/`、`scripts/`、`operators/` 三个参考算子），以及从 `vendor/cannbot-skills` 获取的 `ascendc-st-design`、`ascendc-whitebox-design` 两个共享 Skill，共 3 个，装到目标项目的工具 skills 目录：opencode/codex 为 `.agents/skills/`，claude 为 `.claude/skills/`，trae 为 `.trae/skills/`，dsh 为 `.dsh/skills/`。
2. **主 Agent 与主提示词**：`AGENTS.md` 作为 `direct-invoke-flash` 主 Agent 安装到客户端 agents 目录，并以标记块写入项目 `CLAUDE.md`（claude）或 `AGENTS.md`（其他工具）。
3. **评审 subagent**：`ops-direct-invoke-flash-reviewer` 安装到客户端 agents 目录（codex 下自动生成为 `.toml`）。

该 Skill 声明了 `disable-model-invocation: true`，需显式以 `/ops-direct-invoke-flash` 调用，模型不会自行触发。

### 可选依赖

入口 Skill 的 `PostToolUse` 钩子 `post-edit-reminder.sh` 使用 `jq` 解析工具事件；缺少 `jq` 时钩子会打印一条告警并跳过，不阻断工作流。建议安装 `jq` 以获得完整的编辑后自检提示。

工作流在编译与真机测试阶段会运行 `cmake` / `make` / `pytest`。若希望免交互执行，请在客户端自行授予相应的 bash 权限。

## 3. 发起任务

在安装目录下打开客户端，显式调用 Skill 并给出算子来源（文件路径、公式或文字描述均可）：

```
/ops-direct-invoke-flash 开发一个 Abs 算子
```

```
/ops-direct-invoke-flash 按以下规格开发算子。
## 算子规格
- 公式：y = a * b + b * c - b / d
- 输入：a、b、c、d，共 4 个，逐元素（elementwise）运算，同 shape
- 输出：y
- 数据类型：float32
```

默认在算子工程的 `operators/{OP}/` 目录下开发，文档产物落在 `docs/{OP}/`。插件自带的 `add`、`mul`、`sqrt` 三个参考算子位于 `${CLAUDE_SKILL_DIR}/operators/`，供结构照抄——`mul` 是 `dav-3510` Reg 路径的最小参考，`add`/`sqrt` 走经典 AscendC 计算 API。

## 4. 工作流开关

两个开关写在插件根 `AGENTS.md` 的 frontmatter 里：

| 开关 | 取值 | 含义 |
|---|---|---|
| `harness.review` | `auto`（默认）/ `on` / `off` | 阶段 3/4/6 是否发起并行文档评审 Agent；`auto` 时按算子复杂度档位决定 |
| `harness.test_gate` | `off`（默认）/ `on` | 阶段 7.5 是否执行黑盒/白盒测试门禁并校验证据 |

**改开关的位置**，三种方式，优先级从低到高：

1. **改项目根的 `CLAUDE.md`（claude）或 `AGENTS.md`（其他工具）**——安装时插件的 `AGENTS.md` 会以 `<!-- cannbot:ops-direct-invoke-flash:start -->` 标记块写入该文件，直接改块内的 `harness:` 即可，立即生效。标记块在文件中的位置不限（安装器把它追加在已有内容之后，装多个插件时也只认本插件自己的标记）。注意**重跑安装会用插件的 `AGENTS.md` 重写整个标记块**，用户改动不保留。
2. **在项目内放一份带 `harness.test_gate` 的 `AGENTS.md`/`CLAUDE.md`**，位置比项目根更靠近算子目录——校验器从 `--operator-doc-dir` 向上查找、取最近的一份，所以这种设置能跨重装保留。两条边界：查找**到项目根（首个含 `.git` 或 `.cannbot` 的目录）为止**，不会越过它去读用户级配置；`docs/{OP}` 及其子目录**被有意忽略**——那是工作流自己写文档的地方，不允许它配置审计自己的门禁。
3. **运行校验器时显式传 `--plugin-root <含 AGENTS.md 或 CLAUDE.md 的目录>`**——优先级最高，覆盖前两者。

校验器会打印 `test_gate config: <实际读取的文件>`。**找不到配置文件时门禁直接失败**（`summary` 记 `config_not_found`，退出码 1），不会按 `off` 静默放过——只有确实读到了写着 `off` 的配置，才会记 `skipped_by_config` 并以 0 退出。客户端 agents 目录下那份 agent 文件不是校验器读取的对象；codex 下安装的是 `.toml`，本身不携带 frontmatter。

## 5. 验证安装

统一安装器输出 `Installed ops-direct-invoke-flash@1.2.2 for <tool>` 及 skills/agents 数量即表示安装完成。也可在目标项目确认：

```bash
ls .agents/skills/            # opencode/codex；claude 为 .claude/skills/
ls .opencode/agents/          # claude/codex 为对应 agents 目录
```

应能看到 `ops-direct-invoke-flash`、`ascendc-st-design`、`ascendc-whitebox-design` 三个 Skill，以及 `direct-invoke-flash` 与 `ops-direct-invoke-flash-reviewer` 两个 Agent。

测试门禁校验器自带 8 个单元测试。在本仓库的插件目录（`plugins-official/ops-direct-invoke-flash/`）下运行：

```bash
python3 -m unittest discover -s skills/ops-direct-invoke-flash/test -v
```

## 6. 更新

用与首次相同的方式重跑安装命令即可；同一方式重复安装是幂等的，不会产生重复的 Agent 注册。不要在同一个项目目录混用 npx 安装与源码安装——两者的 Skill 落地方式不同（拷贝 vs 软链），混装后第二次安装可能因目标已是实体目录而失败。
