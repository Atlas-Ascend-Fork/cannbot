# 芯片代际与模板分支隔离

准备阶段盘点，分析阶段确定修改范围，实现阶段复制并接线，回集成阶段按原文件映射复核。注册/直调、standard/generalization 均适用；不能等到回集成才隔离。

## 芯片族与精确验证范围

默认 910b 系列与 910_93 系列同族，950 单独一族；具体 SoC/宏名称以工程和 SDK 为证据。非目标族的专属文件、模板、构建输入与传递依赖不得修改。族别不扩大 `TARGET_SOCS`：同族未验证型号仍保持 legacy，不共用未验证的硬件参数或新路由。共享文件中只允许最小目标接线，非目标 legacy 函数体/布局/常量保持原文。

## 修改范围的依据

分析专家从 `extraction-manifest.json`、`source-compatibility.md` 和真实分派追踪每个拟修改点的使用者：SoC → build/host 路由 → TilingKey/模板实例 → kernel → 共享 helper/常量/头文件。用例命中关系要包含 dtype、shape、attrs、布局和边界。没有运行证据时标为待验证，不能把未覆盖分支视为死代码。

每个方案在契约中列出目标 SoC、涉及 case/分支、允许的运行时谓词、原 fallback、复制文件与最小接线点；保留逐 case 分析全覆盖。性能子集之外的模板不是默认优化范围；`TARGET_SOCS` 即使覆盖所有支持芯片，也不授权修改用例不涉及的分支。

## 复制后独立路由

- 一个函数、模板、头文件、常量或 tiling 数据布局被多个代际/分支共用时，先复制到目标实现，再修改副本。仅复制外层工程目录不能解决工程内部共享关系。
- 优先沿用原工程的架构目录、编译宏、SoC 分源、host 分派和 TilingKey 风格。每个代际需要不同代码时分开副本与构建产物；不能用“都在 TARGET_SOCS”作为混用硬件参数的理由。
- 公共文件只允许最小路由接线。共享函数体、模板和常量保持原文；新实现中需要变化的传递依赖也必须复制。原文件混合入口和实现时，保留原函数体，仅在入口接线，或在受控机械拆分中保存逐段一致性证据。
- 新路径只在“目标 SoC ∩ 已验证的 dtype/shape/attrs/模板条件”命中；其他代际以及同代未涉及分支继续原 fallback。禁止按 case ID、CSV 行号或运行环境里的测试标志路由。
- host 的 tiling 计算、TilingData/Key 与 kernel 分派成对隔离。device include、模板实例化和编译 target 也要受正确代际条件控制；仅运行时 fallback 不能阻止非目标芯片编译不兼容 API。
- 未涉及的模板、分支和它们依赖的公共代码不得顺手清理/重构/统一参数；dead-code 审计必须从全部原支持代际及分支入口出发。只有本候选新引入且证明不可达的代码才可清理。

## 冻结可修改范围与机械门禁

分析专家在实施前生成每方案 `source-isolation-<scheme_id>.json`，主 Agent 审阅分派范围并作为 analysis artifact 保存 SHA。实施专家只消费，不能放宽范围或在改动后重新生成免责清单。新一轮基于当前 baseline 重新盘点；回集成针对完整原算子树的独立快照生成对应 scope。

调用 `validate_source_isolation.py snapshot --baseline <source-root> --out <snapshot.json>` 取得源码/构建输入的 SHA 映射，用作 scope 的 `baseline_files`，不手工裁剪。快照和其他证据放在源码目录之外。脚本覆盖 C/C++/AscendC、CMake、Python/Shell、INI、CMake presets 及 config/configs/cmake 内 JSON/YAML，忽略 build/output/docs 等产物目录；准备专家须核对真实编译依赖，若代码位于排除目录或使用其他输入后缀，先补齐脚本识别范围再验收，不能静默忽略。scope 格式：

```json
{
  "schema_version": 1,
  "target_socs": ["Ascend950"],
  "baseline_files": {"op_kernel/kernel.cpp": "<sha256>", "op_kernel/shared.h": "<sha256>"},
  "editable_ranges": {
    "op_kernel/kernel.cpp": [
      {"start": 20, "end": 23, "kind": "routing", "reason": "仅入口分派；原函数体和其他模板不变"}
    ]
  },
  "new_files": {"op_kernel/arch35/optimized.h": {"copied_from": "op_kernel/shared.h"}}
}
```

`baseline_files` 示例省略其他文件，实际必须等于脚本完整快照。`editable_ranges` 是 baseline 中 1-based 闭区间，修改/删除必须完全落在单个区间，插入必须在区间内或紧随区间末行。默认所有文件/行不可修改；`kind=target_private` 仅用于有完整使用者证据的目标专属实现，公共文件只能 `routing`，不得用全文件范围隐藏公共函数改动。`new_files` 是新增源码/构建文件的精确清单，复制来源填写相对 baseline 路径，全新实现填 `copied_from: null`。

候选符合性和回集成安全脚本均必须传 `--isolation-scope <scope.json>`，把范围门禁嵌入原 gate。它核对 baseline 完整身份、目标集合、文件/行范围和复制来源，拒绝路径逃逸、源码软链接/硬链接以及未声明新增/修改/删除。构建 source list、配置、公共 helper 不因位于 `op_host/op_kernel` 之外而豁免。新门禁不能替代调用链审阅、SoC 路由检查或真实构建/回归；目录名、注释和 guard 邻近本身都不能证明未涉及路径不受影响。

## 动态与最终证据

对目标分支运行完整冻结功能验收子集，另验证新旧路由边界和受影响共享依赖的回归用例；补充回归不得替换/删减冻结集合。未涉及模板先证明源码不变且原路径可达；有现成用例时复验。非目标硬件不可用时记录静态证据及动态验证缺口。

最终回集成使用前处理映射，把已验证副本和同一谓词接回原工程，不能将 optimized 副本覆盖 legacy 文件。shared helper、非目标模板和公开接口的保护延续到最终 diff；generalization 的涉及/不涉及用例回归由后处理调用方按其阶段规则执行。
