---
okf_version: "0.2"
---

# tilelang2ascendc 暂存知识

本 Bundle 保存**尚未固化**的算子生成经验：只在一次或少数任务中验证过，还没有达到
`cannbot-knowledge` 的固定知识标准。固定、权威、跨项目复用的知识仍以
`cannbot-knowledge` 仓为准，本 Bundle 不复制其正文。

- [项目经验（learned）](learned/index.md)：Phase 7 从 trace.md 蒸馏的走偏点、修复配方与成功模式。
- [优化经验（optimization）](optimization/index.md)：可复用的性能优化方法、收益来源与失效边界。
- [调试经验（debug）](debug/index.md)：编译、运行、精度与同步问题的排查路径。

运行期只写项目的 `.tilelang2ascendc/knowledge/learned/`；本插件内置 Bundle 只读。
稳定后通过 `tilelang2ascendc-knowledge` Skill 的 `promote` 动作生成待评审清单，
再由人工提交到插件仓库并最终评审进入 `cannbot-knowledge`。
