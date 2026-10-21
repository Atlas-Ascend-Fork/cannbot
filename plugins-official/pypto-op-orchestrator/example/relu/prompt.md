# prompt.md — 基于需求文件的提示词样例

> cannbot 入口**对提示词格式不作任何要求**：节点 agent 按语义解析，本文只是
> 一种写法示范，字段名、顺序、排版均可自由调整。
>
> 占位符约定：`<工作区>` = 插件安装的工作区根目录；`<work_dir>` = 本次运行
> 工作目录；`<设备号>` = NPU 设备号。

## 用法

1. 触发前把输入文件（`REQUIRE.md` / `task_desc.py` / `gen_prompt.md`，本目录
   即样例）预写到 `$OP_DIR`（即 `<work_dir>/custom/ReLU/`）；
2. 用下面的提示词触发（无头 `--prompt`，或在交互客户端里直接发给 Agent），
   把 `$OP_DIR` 路径告诉 agent 去读取：

```text
op_name=ReLU
op_dir=<work_dir>/custom/ReLU
device_id=<设备号>
perf_target_us=2.85
tune_rounds=3

需求与用例文件位于 op_dir 下：REQUIRE.md（算子需求）、task_desc.py（参考实现与
输入生成）、gen_prompt.md（用例事实与桥接约定）。请按 REQUIRE.md 开发一个
pypto 实现的 ReLU 算子，并完成精度验证与性能调优。
```

对应的无头命令完整写法见 [../README.md](../README.md) 用法 2。
