## CANNBot DSH 派发协议（仅 DSH 生效）

本段由 `tilelang2ascendc-ops-generator` 的 DSH 适配器写入，**只在 DeepSeek Harness 上生效**。

DSH 不提供命名 Agent 注册机制，本插件的角色定义随安装以文件形式提供：

| 指令中出现的称呼 | 角色定义文件 |
| --- | --- |
| `tilelang2ascendc-kernel-generator` | `<项目根>/.dsh/agents/tilelang2ascendc-kernel-generator.md` |

派发规则：

1. 读取目标角色定义文件的**正文**；
2. 将「角色定义正文 + 任务输入」一并作为 `subagent` 工具的 prompt 传入；
3. 子代理的 `description` 使用角色文件名 `tilelang2ascendc-kernel-generator`。

机械拼接角色定义正文**不属于**"编写/改写 Subagent prompt"，与编排约束中"禁止自行编写、删减、改写 Subagent prompt 内容"不冲突；角色定义正文本身仍禁止改写。

适用条件：仅当当前项目根存在 `.dsh/agents/` 目录时适用，其他项目忽略本段。
