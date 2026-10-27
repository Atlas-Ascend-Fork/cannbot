# ascendc-port-orchestrator

面向 AscendC 算子的社区编排插件。**跨代际移植推荐优先使用 Lite 版本 `ascendc-cross-gen-migration`**，尤其适合基于已有 A2/A3 算子快速迁移、尚未准备 KernelBench 风格 golden 的场景。Lite 按阶段推进迁移；需要确定性编排、安全网和双层知识库反馈环时，可选择完整版本 `ascendc-cross-gen-port`。

本插件提供三个入口，其中前两个共享完整编排器，Lite 独立执行：
1. **`ascendc-cross-gen-port` — 跨代际移植**：把 arch22 源算子移植到 **arch35 / A5**（如 Ascend910C/V220 → Ascend950PR/V300）。目标架构用自然语言指定，来源架构由代码分析自动识别。另有 **multirank 多卡分支**（通信/通算融合语义触发）：同样以待移植源算子目录为必选输入，迁移计算与跨 rank 集合通信融进同一 kernel 的融合算子（真值默认= task 参考实现在 A5 上的多 rank 执行，`--multirank`）。
2. **`ascendc-backward-gen` — 正向→反向生成**：由可微 PyTorch 正向规格生成并验证 AscendC 反向（梯度）算子。
3. **`ascendc-cross-gen-migration` — 轻量迁移**：`ascendc-cross-gen-port` 的轻量入口。无 KernelBench 风格的 golden 输入，或希望基于已有的 A2/A3 算子修改后快速迁移时使用：按阶段门禁完成 910b/910_93→950/arch35 算子迁移，全程免交互自动推进；精度标杆由 agent 逆向源码自合成并与 A5 实测双向互检。**不经上述编排流水线（设计如此）**。Skill 本体由 cannbot-skills 仓 [`ops/ascendc-cross-gen-migration`](https://gitcode.com/cann/cannbot-skills/tree/master/ops/ascendc-cross-gen-migration) 维护，安装时经 `plugin-sources.json` 从 `vendor/cannbot-skills` 子模块链接，本插件作统一入口。

## 推荐使用 Lite

Lite 的正式入口现为 `ascendc-cross-gen-migration`（原 `ascendc-cross-gen-port-light`）。升级时请同步更新插件与 skills 依赖并重新安装，将已有提示词中的旧命令改为 `/ascendc-cross-gen-migration`；本文继续用 Lite 指代这条轻量迁移路径。

安装并加载轻量入口后，可直接向 Agent 提出任务：

```text
/ascendc-cross-gen-migration 把 <已有 A2/A3 算子目录> 移植到 A5。
目标环境为 <CANN 路径、SoC、可用 NPU 等信息>，请完成编译、精度对齐和性能优化，
保留代码、测试输入、运行命令和原始日志，供我独立验证。
```

Lite 不要求预先准备 KernelBench 风格的 golden，但仍需要可用的目标 NPU 环境。使用时有两项直接影响结果可信度和失败处理的限制：

1. **无法拦截 Agent 在 reward ranking 过程中为追求分数而绕过真实验证的行为，需要用户独立验证。**
   Lite 不具备完整编排器的强制安全网；Agent 自合成的标杆、互检结果或成功报告不能替代独立验收。
   请使用独立准备或复核的参考实现与测试用例，在目标 NPU 上重新验证精度，并按一致的输入、计时范围和运行环境复测性能；核对原始日志和实际执行的算子代码后再采信结果。
2. **缺少完整版本的反馈环，生成失败、精度不对齐或性能未达标时，需要主动指定后续动作。**
   完整版本中依靠反馈环“再跑一遍”的处理方式，不能直接套用到 Lite。可选择以下任一种方式：
   显式提示 Agent 分别提高**编译、精度对齐、性能优化**阶段的迭代次数，并根据失败证据继续修复；
   或执行手头已有的 **debug 工具、脚本或技能**，定位问题后继续修复与验证。

例如，选择增加迭代次数时，可以这样提示（次数按任务需要调整，不是 Lite 的默认配置）：

```text
继续当前 Lite 移植任务：将编译修复、精度对齐、性能优化各阶段的迭代上限，
分别在当前基础上增加 5、5、10 轮。每轮根据编译报错、精度差异或性能测量结果修复；
保持参考实现、精度阈值和性能目标不变，达到上限仍未通过时，保留失败日志并报告阻塞原因。
```

也可提示 Agent 调用已有 debug 能力：

```text
使用我已有的 <debug 工具、脚本或技能及其路径/名称>，结合 <失败日志和当前算子目录>
定位本次生成失败、精度不对齐或性能未达标的原因，修复后重新编译并验证精度和性能。
```

增加迭代次数或执行 debug 后，仍需完成上述独立验证。

以下输入、golden 模式、运行底座、依赖与知识库说明面向**完整编排器**（`ascendc-cross-gen-port` / `ascendc-backward-gen`，其中 golden 约定仅用于跨代移植）。Lite 的具体准备和执行步骤以其 Skill 为准，不继承完整编排器的引擎门禁与反馈环保证。

## 输入：待移植实现 + golden（统一格式）

跨代移植的输入统一为两部分，两种来源形态共用同一 golden 约定。**实现目录必选；参考模式必须且只能二选一**
（npubench 或 a3_live，见下表）：

1. **必选：待移植的算子实现目录**（两个 `--mode` 名称按来源格式分类）
   - 常规：arch22 `ops-nn` 源算子目录（`--mode port-a3-ops`，= CANN ops 仓通用格式）；
   - TileLang2AscendC 工程：`model_new_ascendc.py + kernel/` 目录（`--mode port-a3-tilelang2ascendc`，= TileLang2AscendC 插件输出格式）。
2. **KernelBench 风格 golden** —— task `.py` 与同 stem `.json` / `.jsonl` sidecar 文件对
   （`--reference-source npubench --npubench-task <task.py> [--npubench-root <root>]`）。
   两种来源形态的 golden **完全一致**，原样冻结为精度真值，不做任何格式转换。
   常规 ops-nn 来源下为**推荐**输入（可显式改选 `a3_live`）；TileLang2AscendC 工程来源下为**必需**输入（唯一真值）。

golden 的具体格式可直接查看仓内示例 [`examples/npukernelbench-native/`](examples/npukernelbench-native/)：
task `.py` 暴露 `Model` 与 `get_input_groups()`（可选 `get_init_inputs()`），同 stem sidecar 逐 case 描述输入。
输入尚非该格式时，请先由输入提供方准备为该格式并复核语义。

## 两种 golden 模式

| 选择 | 精度/性能对比基准 | 必要 NPU 环境 |
|---|---|---|
| `npubench`（推荐） | 精度对照 golden 输出；**加速比 = 目标实现 vs golden 参考实现**（同一 A5 环境 W3/R5 msprof 实测） | A5 |
| `a3_live`（显式可选，仅常规 ops-nn 来源） | 精度对照当次 A3 实测输出；**加速比 = 目标实现 vs A3 实现实测** | A3 和独立 A5 |

TileLang2AscendC 工程来源只支持 `npubench` golden。
**两种模式的加速比基准不同（golden 参考实现 vs A3 实现），数值不可直接横向比较。**

多卡迁移在 `--mode port-a3-ops` 上加 `--multirank` 启动，golden 的选择与单卡相同。
多卡 task 的格式约定见 [`docs/USAGE.md`](./docs/USAGE.md) §7。

## 支持的运行底座

插件支持 **Claude Code** 和 **OpenCode** 两条独立运行路径，共用 `engine/` 中的编排器和安全网；启动器会按当前
会话自动选择后端。

| 底座 | 用户入口 | 运行时要求 |
|---|---|---|
| Claude Code | `/ascendc-cross-gen-port`（含 multirank 多卡分支）、`/ascendc-backward-gen` Skills | 可调用的 `claude` CLI 与已配置的认证/模型 |
| OpenCode | 同名 `/ascendc-*` Commands | 可调用的 `opencode` CLI、`node` 或 `bun`、已配置的 provider/model |

## 运行前需要准备什么

控制端需要 Bash、Python 3.10+ 和 `bubblewrap`（worker 沙箱，缺失即 fail-closed）、GNU `timeout`、
`cmake`/`g++` 与 Python 开发头文件；目标环境需要 CANN、`torch`/`torch_npu` 与可用的 `npu-smi`，并在启动前
`source` CANN 的 `set_env.sh`。完整依赖清单与检查命令见 [`docs/USAGE.md`](docs/USAGE.md) §1.5。
NPU 主机/容器、CANN 路径、SoC 等配置写入 `engine/workspace/.ascendc_env`（可能含凭证，已 gitignore，绝不能提交）。
官方 b 层知识必须先由独立 `cannbot-knowledge` 仓的 `install.sh` 以 `consumer` 模式安装到算子项目；它负责准备完整 checkout、索引、查询 Skill 和项目 `.cannbot/knowledge.env`。port 只消费该安装结果，缺失时 fail-closed。
## 文档导航

- [`quickstart.md`](quickstart.md)：最短的 Claude Code / OpenCode 上手路径。
- [`docs/USAGE.md`](docs/USAGE.md)：完整前置条件、配置字段、两种 golden 模式与运行说明、FAQ。
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)：编排器、安全网、双层 KB 和 harness 实现边界（维护者/评审）。
- [`examples/npukernelbench-native/`](examples/npukernelbench-native/)：golden 输入格式示例。

## 知识库

运行时知识优先级为用户本地 KB（c）> 外部 cannbot-knowledge（b）> 社区 Skills（a）。用户 KB 默认位于
`~/.ascendc-port/user_kb/`，可用 `ASCENDC_PORT_USER_KB` 覆盖；官方 b 层只从项目 `.cannbot/knowledge.env` 指向的完整知识仓读取，不回退插件内旧卡。

本插件处于社区维护阶段，源码位于 `plugins-community/ascendc-port-orchestrator/`。
