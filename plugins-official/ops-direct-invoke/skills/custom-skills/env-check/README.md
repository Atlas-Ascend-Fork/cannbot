# 环境检查

| 末级目录 | 支持 | 不支持 |
|---|---|---|
| ascend/ascendc/ | Ascend 与 AscendC 环境 | Kirin、DSL |
| ascend/dsl/ | Ascend 与 DSL 原环境检查 | Kirin、独立 AscendC 工程 |
| kirin/ascendc/ | Kirin mobile-station CANN 与 Simulator | Ascend、DSL |

platform.json 声明语言支持；references/ 只保存共用检查纪律和记录格式，各实现从自己的 references/ 入口访问。链接末级实现，具体型号/工具链/工程组合仍须核验。
