# 芯片代际与模板分支隔离

准备阶段盘点，分析阶段确定修改范围，实现阶段在分支 commit 上落地，交付阶段按条件分路复核。注册/直调、standard/generalization 均适用；不能等到交付才隔离。

## 模式与身份基线

源码隔离有两种等价实现，按输入选择：

| 模式 | 适用 | 基线身份 | scope schema |
|---|---|---|---|
| **git 模式**（**两个后端的唯一主路径**） | AscendC 与 DSL 的所有 git 仓输入（非 git 输入经 `GIT_INIT` 询问后原地 `git init` 接入，拒绝即终止） | `baseline_commit` + `baseline_tree_sha`（树哈希机器可证） | **v2** |
| **目录模式**（**validator 对拍 oracle / 测试基线，非交付路径**） | 仅为对拍测试交叉验证 git 模式判定一致性保留；不作为任何后端的交付流程 | `baseline_files` 全量 SHA 快照 | v1 |

两种模式共享同一套语义规则：scope 冻结时序、editable_ranges 行级语义、new_files 声明、公共文件仅 routing、SoC 路由约束。门禁脚本（`validate_source_isolation.py` / `validate_implementation_conformance.py` / `validate_integration_safety.py`）同时支持两种 CLI：git 模式传 `--git-repo/--baseline-rev/--candidate-rev`，目录模式传 `--baseline/--candidate`。对拍测试保证两种模式判定一致。

## 现有设备验证与同族泛化

先识别现有目标设备的 `NpuArch` 和具体型号，在可用设备上验证，原始证据记录实际测试设备。优化面向目标 `NpuArch` 族，同一版实现必须考虑同族芯片的泛化性：核数、UB 等资源按实际平台获取，差异通过能力或资源条件处理，不得新增具体型号或 SKU 白名单门禁。同族泛化通过源码和资源适配审阅，不把未测型号写成已验证。非目标族的专属文件、模板、构建输入与传递依赖不得修改；共享文件中只允许最小目标接线，非目标 legacy 函数体/布局/常量保持原文。

## 修改范围的依据

分析专家从 `workspace-manifest.json`（git 模式）或方案副本映射（DSL）、`source-compatibility.md` 和真实分派追踪每个拟修改点的使用者：SoC → build/host 路由 → TilingKey/模板实例 → kernel → 共享 helper/常量/头文件。用例命中关系要包含 dtype、shape、attrs、布局和边界。没有运行证据时标为待验证，不能把未覆盖分支视为死代码。

每个方案在契约中列出目标 SoC、涉及 case/分支、允许的运行时谓词、原 fallback、修改文件与最小接线点；保留逐 case 分析全覆盖。修改范围依据实现依赖与同族泛化需要确定；验证用例用于检验实现，不定义运行时输入白名单。

## 分支上的复制与独立路由

git 模式下"复制后独立路由"表达为分支 commit 中的**新增文件**（scope 的 `new_files` 声明，`copied_from` 指向基线中的来源路径）：

- 一个函数、模板、头文件、常量或 tiling 数据布局被多个代际/分支共用时，先在 commit 中新增副本，再修改副本；不允许原地修改共享体。
- 优先沿用原工程的架构目录、编译宏、SoC 分源、host 分派和 TilingKey 风格。每个代际需要不同代码时分开副本与构建产物。
- 公共文件只允许最小路由接线（`kind=routing`）。共享函数体、模板和常量保持原文；新实现中需要变化的传递依赖也必须复制。
- 目标 NpuArch 族内，优化实现须适应算子原有的合法输入范围，不得以是否被验证用例覆盖决定启用；族外保持原实现。禁止按 case ID、CSV 行号或运行环境里的测试标志路由。
- host 的 tiling 计算、TilingData/Key 与 kernel 分派成对隔离。device include、模板实例化和编译 target 也要受正确代际条件控制；仅运行时 fallback 不能阻止非目标芯片编译不兼容 API。
- 未涉及的模板、分支和它们依赖的公共代码不得顺手清理/重构/统一参数；只有本候选新引入且证明不可达的代码才可清理。
- **staging 禁改**：无单算子打包入口的仓库经 SDK 骨架构建时，staging 副本是构建派生产物（记录来源 commit），禁止在其中修改代码；修改必须回到 worktree 实施后重建。

## 冻结可修改范围与机械门禁

分析专家在实施前生成每方案 `source-isolation-<scheme_id>.json`，主 Agent 审阅分派范围并作为 analysis artifact 保存内容 SHA。实施专家只消费，不能放宽范围或在改动后重新生成免责清单。新一轮基于当前基线 commit 重新盘点。scope 文件放在源码树之外。

git 模式 scope（schema v2）示例：

```json
{
  "schema_version": 2,
  "baseline_commit": "<resolved full sha>",
  "baseline_tree_sha": "<git tree hash>",
  "target_socs": ["Ascend950"],
  "editable_ranges": {
    "op_kernel/kernel.cpp": [
      {"start": 20, "end": 23, "kind": "routing", "reason": "仅入口分派；原函数体和其他模板不变"}
    ]
  },
  "new_files": {"op_kernel/arch35/optimized.h": {"copied_from": "op_kernel/shared.h"}}
}
```

`baseline_tree_sha` 可选（与 `baseline_commit` 解析出的树哈希一致性校验）；目录模式（DSL）继续使用 v1 的 `baseline_files` 全量快照，用 `$WORKFLOW_SCRIPTS/validate_source_isolation.py snapshot --baseline <源码树> --out <快照.json>` 生成。git 模式的等价快照用 `snapshot-git --git-repo <repo> --rev <commit> --out <快照.json>`。快照和证据放在源码目录之外。

`editable_ranges` 是基线中 1-based 闭区间，修改/删除必须完全落在单个区间，插入必须在区间内或紧随区间末行（`start-1 <= 插入点 <= end`）。默认所有文件/行不可修改；`kind=target_private` 仅用于有完整使用者证据的目标专属实现，公共文件只能 `routing`，不得用全文件范围隐藏公共函数改动。`new_files` 是新增源码/构建文件的精确清单，复制来源填写相对基线路径，全新实现填 `copied_from: null`。

候选符合性和交付安全脚本在 git 模式下传 `--isolation-scope <scope.json>` 与 `--git-repo/--baseline-rev/--candidate-rev`，把范围门禁嵌入原 gate；目录模式（DSL）传 `--baseline/--candidate` 目录。git 模式下 evidence 从候选 commit 读取，活 worktree 的未提交改动不影响门禁。门禁核对基线 commit 身份、目标集合、文件/行范围和复制来源，拒绝路径逃逸、未声明新增/修改/删除与 submodule 变更（报"requires manual adjudication"）。构建 source list、配置、公共 helper 不因位于 `op_host/op_kernel` 之外而豁免。新门禁不能替代调用链审阅、SoC 路由检查或真实构建/回归；目录名、注释和 guard 邻近本身都不能证明未涉及路径不受影响。

## 动态与最终证据

对目标分支运行完整冻结功能验收子集，另验证新旧路由边界和受影响共享依赖的回归用例；补充回归不得替换/删减冻结集合。未涉及模板先证明源码不变且原路径可达；有现成用例时复验。非目标硬件不可用时记录静态证据及动态验证缺口。

最终交付按条件分路：fast-forward 等价（树哈希一致）时复用分析期 scope（交付 diff 即候选 diff），仅并发变更（非 fast-forward）的新身份需要重新冻结对应 scope。shared helper、非目标模板和公开接口的保护延续到最终 commit；generalization 的涉及/不涉及用例回归由交付调用方按其阶段规则执行。
