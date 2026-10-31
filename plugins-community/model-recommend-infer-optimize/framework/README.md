# 内置执行框架

本目录是 `model-recommend-infer-optimize` 自带的推荐场景 GE 图模式在线推理框架（GE_SESSION_DEMO），**只服务 onnx 输入路径**；pytorch / HuggingFace 输入不需要它。代码与文档在本插件内维护并随插件提交，**工作流不引用任何外部链接**。

## 目录

| 路径 | 内容 |
| --- | --- |
| `GE_SESSION_DEMO/` | 框架本体：`prepare.sh` / `compile.sh` / `run.sh` / `test.sh` 入口、`src/` C++ 运行层、`tools/` Python 工具链、`models/M001_sample` 样例 |
| `推荐推理GE方案部署指南.md` | 方案总述、图模式接入、精度验证与基准测试方法 |
| `LICENSE` / `NOTICE` | Apache License 2.0（版权归 Huawei Technologies Co., Ltd.） |

## 使用方式

安装时（`bash init.sh <level> <tool>`）自动复制到工程根的 `GE_SESSION_DEMO/`，也可手工复制：

```bash
cp -r <插件目录>/framework/GE_SESSION_DEMO <工程根>/GE_SESSION_DEMO
cd <工程根>/GE_SESSION_DEMO && bash compile.sh   # 产出 ./GEsession_test_acl
```

框架必须位于工程根，与 `docs/`、`data/`、`prof/`、`ops/`、`tmp/` 同级。

## 维护约定

- **唯一真源在本目录**：框架代码在此维护、随插件提交；工程内的是安装副本，新增或修改的组件须回写到 `GE_SESSION_DEMO/` 再提交，避免副本与插件漂移。
- **允许新增**：图融合 pass 等优化组件写在 `src/`，开关默认关闭、可回退，过精度与性能双门禁后合入。
- **不得改写**：框架既有运行逻辑与脚本入口（会破坏跨模型可比性）。
- **运行期产物**：`models/M<id>/{output,report,.cache,sweep}` 由框架写入，不入库、不跨版本保留。
