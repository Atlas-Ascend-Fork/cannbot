# GE / ACL 错误与故障分层（强相关细节）

> 供 `model-recommend-runtime-debug` 与 `model-recommend-adaptation` 引用。通用排查纪律在 skill，具体错误样本在此。

## 1. 故障分层定位

| 层 | 典型症状 | 证据 | 处理 |
| --- | --- | --- | --- |
| 模型语义 | 输出错误、精度异常 | 参考输出、golden | 对齐语义/版本 |
| 图解析 | parse 失败、算子/属性未知 | parser 日志、节点名 | 插件/Pass/改写 |
| shape/dtype | infershape 失败、广播/轴不一致 | 输入 shape、节点属性 | 修正输入/契约 |
| 资源环境 | OOM、超时、设备占用 | 设备监控、进程信息 | 等待/隔离/降载 |
| 工具链 | 编译失败、依赖缺失 | 编译日志、版本 | 修复环境/版本匹配 |

方法：最小复现 → 单变量修改 → 对比日志 → 记录结论。

## 2. 常见 GE/ACL 错误样本

```text
[ERROR] [pre_checker.cc] CheckTypeSupported: ... type[<domain>::<version>::<OpType>] failed, it is not supported.
[ERROR] [onnx_parser.cc] aclgrphParseONNX: ... failed.
[ERROR] parse model failed, status=4294967295
```

```text
[ERROR] [dnnengine_manager.cc] GetDNNEngineName: ErrorNo: 1343242282(assign engine failed)
  [Check][OpSupported] Op type <OpType> ... is unsupported, reason :
  [tbe-custom]: op type <OpType> is not found in this op store.
  [Dynamic shape check]: data type <dtype> of input [<input>] is not supported.
```

## 3. 症状 → 处置

| 症状 | 处置 |
| --- | --- |
| `GEInitialize failed` | 检查 `PYTHONPATH`（numpy/tbe）与 CANN `set_env.sh` |
| onnx 解析失败 / 非标 domain | 非标 domain 折叠或 ONNX 插件（`ge-custom-dev-routing.md`） |
| `Invalid tensor data type` | 对照 dtype 支持集合，`inspect_config.py` 校验 |
| aicore timeout 507014 | 二分定位阶段（建图/编译/执行）→ 节点 → 算子约束 |
| OOM / HBM 超限 | 降 `GRAPH_MAX_PARALLEL`/`THREAD_NUM`/batch 或转静态 shape |
| Shape 不匹配 | parser_shape vs runtime_shape / `output_overrides` |
| aclnn 错误码（161xxx/361xxx/561xxx） | 环境配置 / Tiling / Kernel 三类归因 |

## 4. 现场与日志

- `run.sh --info`（plog 等级 2）/ `--debug`（等级 0），日志落 `models/M<id>/report/run_debug_<ts>.log`。
- GE 产物：`.cache/run`（fusion_result/kernel_meta）、`.cache/dump_graph`、`.cache/dump_data`（各保留 3 份）。
- 卡死/崩溃：plog 解析 + memcheck；先查残留进程，再按 npu-smi 状态判定（有进程+HBM不变+CPU高=编译；CPU 0=hang；0 进程=crash）。
