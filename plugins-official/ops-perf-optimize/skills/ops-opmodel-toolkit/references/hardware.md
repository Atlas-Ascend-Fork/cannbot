# 硬件配置

硬件 YAML 描述可用内存、流水线、搬运路由、数据类型、时钟和核数。模型必须使用
与目标硬件相符的配置，不能只修改设备名称来切换硬件行为。

教程的 `operator.yaml` 默认选择安装包内的 `matmul/ascend_950DT_streaming` profile。
另附[可编辑硬件示例](../assets/examples/matmul/hardware.yaml)，用于演示显式覆盖。
其中的共享服务参数为假设，不是设备实测标定。

| 字段 | 用途及单位 |
| --- | --- |
| `name` | 配置标识 |
| `clock_ghz` | 时钟 GHz，影响周期到时间的换算 |
| `usedCoreNum` | 配置核数；实际活跃核数还受任务数量影响 |
| `memories` | 存储层及 `size_kb` 容量 |
| `dtypes` | 每种元素占用字节数 |
| `pipelines` | 可用流水线 |
| `mov_routes` | `src/dst/pipe` 搬运路径，`bw` 为 byte/cycle |
| `compute.vec.aiv_per_aic` | 每个 AIC 对应的 AIV 数量 |
| `shared_services` | 共享带宽、容量及假设来源 |

共享带宽是显式参数；修改核数不会自动推导新的整机带宽。
改变数据类型时，也要检查元素字节数、缓冲区大小、搬运工作量和计算语义。

## 当前支持的覆盖入口

固定配置仿真和 DAG 搜索接受 `--hardware`：

```bash
python -m accel_model.app.cli.dag_run work/my_matmul \
  --config work/my_matmul/optimize/dag.yaml \
  --hardware work/my_matmul/hardware.yaml --out work/dag_hardware
```

`--hardware` 可为安装包内 profile 名或存在的 YAML 文件路径。
物理完整 case 也支持硬件覆盖。普通完整 case 的 `run_native_case` 当前不支持
`hardware_path` 覆盖；分核 CLI 没有通用 `--hardware` 参数。
因此不能假定在某个入口覆盖后，其他运行或搜索也自动使用了相同硬件。

需要比较结果时，先确认各入口实际加载的 profile、核数、时钟和带宽假设一致。
