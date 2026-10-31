# Python Stage 接口

声明式 DAG 优先。需要用户 Python 在构建时组织不规则指令序列时，可在模型目录提供
Stage 类。它不是设备代码生成器，也不会自动模拟任意数据相关 Python 分支。
使用前核对已安装包的接口签名；混合模型须按实际后端分别验证。

## 注册与输入输出

```python
from accel_model.kernel.core.types import StageIO
from accel_model.kernel.resources.pipeline import GM, UB
from accel_model.kernel.stages_base import Stage

class CopyStage(Stage):
    def execute(self, inputs: StageIO) -> StageIO:
        p = self.config["params"]
        shape = (p["rows"], p["cols"])
        src = self.t("src", GM, shape, "bf16")
        local = self.t("local", UB, shape, "bf16")
        dst = self.t("dst", GM, shape, "bf16")
        with self.chain(after=inputs.signals.events.get("upstream_done")) as chain:
            chain.mov(src, local)
            store = chain.mov(local, dst)
        output = StageIO()
        output.tensors["output"] = dst
        output.signals.events["copy_done"] = store.done_event
        return output

# 模型 __init__.py 中导出；若类在另一文件，先相对导入该类。
STAGES = {"Copy": CopyStage}
```

这是 Stage 接口片段，需放入具有硬件、参数及 pipeline 声明的完整模型。
同一模型中，在 `dag.yaml` 声明的 stage 使用 DAG，其他名称由 `STAGES` 提供类。
模型使用受限的声明式物理入口时，不能假定会导入这些 Python 类。

## 指令与事件 helpers

| 调用 | 含义 |
| --- | --- |
| `self.t(name, mem, shape, dtype)` | 创建带 stage/task 前缀的 Tensor |
| `self.mov(src, dst, after=..., transfer=...)` | 搬运；默认从 shape/dtype 得到两端字节 |
| `self.vec(name, cycles, after=...)` | 显式 VEC 服务周期，来源由模型负责 |
| `self.mmad(a, b, c, M, K, N, after=..., accumulate=False, unitflag=False)` | Cube 指令及可选提前就绪 |
| `self.all_of(*items)` | 合取事件；忽略 None，空输入返回 None |
| `self.events(*items)` | 将指令/事件转成事件列表 |
| `instr.acquires(buffer)` | 取得池槽 |
| `instr.releases(buffer, on=event)` | 按指定事件释放；缺省为该指令完成 |
| `instr.signals_token(self.token)` | 关联 token 完成 |

`after` 接受 Instruction、SimPy Event、None 或它们的列表；Instruction 转成
`done_event`。`wait_for` 列表不会自动转换 Instruction，通常使用 `after` 更清楚。
`mov` **不接受 `bytes=`**；底层也不接受 `data_bytes=` 输入。需要显式数量时使用
`TransferQuantities`，同时声明完整量、成本量及来源，见[搬运数量契约](../framework/performance-manifest.md)。
不要把整 tensor 形状和子块字节混写；普通分块优先创建正确大小的 tensor/view。

## 线性链与 fork/join

`with self.chain(after=...) as chain` 中每条指令等待前一条完成，`chain.first/last`
指向首尾。链的 `mov/vec/mmad` 接受额外 `after`；chain 的 `mmad` 接受 accumulate，
不提供 Stage.mmad 的全部参数。只在真实串行段使用 chain，fork/join 用独立指令与
`self.all_of`。把整条搬运/计算/写回链包进 chain 会禁止其中的重叠，不能据此声称双缓冲。

循环的槽位取得、各子块上游依赖、每 task 释放及跨组保护见[并发指南](concurrency.md)。
不要按一份示例假定所有 Vector stage 都需要相同槽数或固定 AIV 配比。

## Cube 与 Vector 的生命周期

Cube 常见顺序是 L1→L0A/B、MMAD、L0C→目标层。K 循环首块初始化、后续累加，
输出版本最后一次使用后才释放。Python Stage 与 YAML 的存储声明各有使用范围，不直接混用字段。

Vector 常见为载入、计算和写回，输入与输出池可以有不同的释放点。token 是否限制
首条搬运取决于实际软件顺序；最后有效计算或合法空路径都要闭合 token。

```text
self.token_placeholder(name, after=None, releases=None,
                       releases_on_last_task=None, signal_token=True)
```

该 helper 发出 **1 cycle VEC** 控制占位；`releases_on_last_task` 只在全程最后 task
生效，不是组尾释放。不能拿它为未知 VF 赋值，也不能用它绕过真实数据生产。

## 可用上下文与验证

Stage 可读取 `config`、`token`、`group`、`ptid`、`is_last_task` 和 `is_last_in_group`。
`execute()` 返回 `StageIO`；Python 分支基于本次模型输入，不自动表示任意运行时分支。
需要控制值时使用支持的[控制协议](../framework/control-state.md)。

先验证导入和完整固定 case，再用真实公开输入覆盖尾块、条件空路径、多组与槽回绕。
声明式 DAG 可用的 Replay、变换或数值回放能力不会自动扩展到任意自定义 Python Stage。
