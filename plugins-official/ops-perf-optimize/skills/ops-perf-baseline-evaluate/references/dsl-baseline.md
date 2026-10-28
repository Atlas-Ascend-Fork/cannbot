# DSL 基线评估

读取冻结 request.backend/dsl 及原入口、样例 README、原测试。网络调优默认 standard；performance_cases 是实际网络 case，含决定工作量的长度、索引分布、mask、量化和 metadata。功能用例就是性能用例：一套冻结集合同时服务功能判定与性能采集，不另造独立功能验证集。原测试优先使用 existing 库存；只有确有缺口时补必要边界，不默认生成泛化全集。用户明确 generalization 时才保留该模式已有规则。

1. 沿 [输入冻结](input-freezing.md) 调用 preflight 与确定性集合脚本；其中 AscendC ST/TTK 操作不用于本路由。`preflight_dependencies.py` 根据 backend 检查 DSL 包、Python/pytest、CANN/毕昇/msprof 与设备；不能用 --skip-device 的静态报告宣称上板条件已就绪。保存 dsl-environment.json 并登记其身份。
2. 原 pytest/checker 对应 nodeid、golden、容差、seed 和输入分布冻结到功能库存；目录库存需有 cases.csv 和实际测试资产，不能只传一个 .py 文件假装 CSV。冻结集合和停止条件沿原协议，已有授权不重复确认。
3. 加载共享验证 [DSL 共享验证与领域边界](../../ops-perf-acceptance-criteria/references/cannbot-dsl.md)。对原实现实测时先用原执行身份门禁证明 source→build→loaded，再采可比基线。编译与 metadata 初始化按真实入口登记，所有相关 kernel 纳入映射。
4. 用 `build_performance_targets.py` 生成精确 case×SoC 目标。原实现可作为改善参照，但用户给定目标/竞品不能被自基线替换。理论模型缺失时标缺口，不将 Cube/Mix 塞进纯 Vector 模型。

交付原阶段产物及 dsl-environment.json、API/入口/测试引用、实际版本和调用边界。README 性能图只作设计参考；缺公开测量输入时生成并冻结真实库存与采集证据，不能复用图中数字为本次基线。
