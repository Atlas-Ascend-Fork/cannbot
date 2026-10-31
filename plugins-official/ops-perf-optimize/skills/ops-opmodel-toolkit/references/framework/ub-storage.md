# 存储、缓冲与版本接口

本页说明用户模型需要声明的物理容量和逻辑值。使用实际大小、dtype、owner 和全部消费者，
不能用逻辑名称或版本数量代替物理空间。

## 普通 buffer 和 L0 布局

```yaml
buffers:
  - {name: a, mem: L0A, bytes: 8192, slots: 2}
  - {name: b, mem: L0B, bytes: 8192, slots: 2}
  - {name: c, mem: L0C, bytes: 16384, slots: 1}
```

`name` 与 DAG 的 `pool/use_pools` 对应，`bytes` 是单槽容量，`slots` 是槽数。
有明确独立或共享地址关系时使用 `cube.l0_layout`：

```yaml
cube:
  l0_layout:
    L0A:
      slots: 2
      bindings:
        left: [0, 1]
        right: [2, 3]
```

片段中的 buffer 需在实际模型中声明。配置某个内存的 layout 后，该内存的全部 pool
均应出现在 bindings，映射长度至少满足有效槽数。slots 参数变化时重新检查布局和容量。
名称不同不保证地址独立；没有明确地址关系时不据此宣称可并行。

## 固定 L1/UB

```yaml
storage:
  - {name: local, memory: UB, physical_bytes: 8192, slots: 1, owner: AIV_AGG}
```

`physical_bytes/slots` 为正整数或模型支持的参数表达式。UB 大小按每 AIV 给出，
L1 按 AIC 给出；padding 和对齐空间包含在物理大小内。
同名分配不再重复放入 `buffers`，逻辑版本结束不表示固定空间缩小。

move 操作数可引用固定分配：

```yaml
dst:
  tensor: local_value
  mem: UB
  allocation: local
  version: 0
  shape: [32, 64]
```

vec 用 `storage_reads/storage_writes` 声明读写列表，各项包含
`tensor/allocation/version/shape`，可附加 `slot/region/preserve`。
`storage_inplace: true` 表示用户实现允许原地操作；这项声明不能证明设备代码的读写安全。
`region` 使用各轴半开区间，`preserve: true` 用于保留前一版本未写区域。
读取必须引用已生产的有效区域，未定义区域不等于零。

环形槽须显式给出 slot；每个槽使用自己的版本序列。
例如两槽时可使用 `slot: {expr: ptid % 2}` 与对应槽内的版本编号，
不能直接把不连续的全局 task 编号当成该槽的连续版本。

## 跨 task L0 操作数

L0A/L0B 的 `allocation` 引用相同内存的 buffer，生产 move 的 pool 与之相同。
生产和消费的 tensor/memory/allocation/version 必须一致，版本从零连续编号，不能混用 tile。

```yaml
dst: {tensor: A, mem: L0A, allocation: a, version: 0}
```

MMAD 的 `a` 使用同一引用；额外配套操作数可通过
`operand_reads: [{tensor: Scale, mem: L0A, allocation: scale, version: 0, shape: [32, 4]}]`
声明。每份数据须有真实生产者和容量；该字段不声明量化数学或专用硬件布局。
下一 group 需按自己的输入重新声明值，不能无依据继承内容。

## L0C 累加与区域

L0C 可用 `allocation/version` 标识跨 task 值，累加从明确的 `accumulate_from` 版本读取。
区域形式还须提供 shape 和 region，实际生产、累加和 FIX 搬出覆盖应一致。
同一值不能同时使用旧 tile 与版本引用；最终结果必须有合法消费者。
部分更新、整值发布、UnitFlag 和数值检查并非任意组合均受支持，遇到拒绝时保留原因。

`handoff/use_handoffs` 描述指定区域的交接；物理 engine 的访问使用
`physical_execution.storage` 和 `physical_accesses`，见[物理接口](physical-execution.md)。
普通聚合模型的字段不能直接替换物理模型的 owner/region 声明。

## 检查与限制

使用完整 case 检查容量、缺失生产者、重复版本、尺寸/类型不一致和不支持组合。
至少覆盖单 task、多 task、尾块与槽位回绕，记录失败状态和输入。
这些接口不自动推导任意 offset/stride、寻找共享布局或证明编译器实际分配。
模型检查与设备正确性分别验收。
