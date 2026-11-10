# 编码检查表

## A 类：候选实现真实性

对应官方 `SUB-BEH-001`～`SUB-BEH-007`，违反时不能作为有效候选交付。适用范围是候选执行路径；独立 golden 和测试输入生成可以使用 Torch，不得因此被误判为候选代算。

| 本仓编号 / 官方规则 | 检视内容 | 修正方向 |
|--------------------|----------|----------|
| A1 / SUB-BEH-001 | 包装层是否把全部或部分计算交给 Torch/torch_npu 内置计算 API | 由提交 kernel 实现；kernel 内 Ascend C 原语不属于包装层代算 |
| A2 / SUB-BEH-002 | 是否在包装层通过 transpose/contiguous/cast 等完成实质性数据或布局变换 | 变换纳入 kernel；参数读取、Tiling 准备和输出分配可以保留 |
| A3 / SUB-BEH-003 | 是否只转发到 CANN 内置同名算子 | 提供自有实现，不把接口包装当开发完成 |
| A4 / SUB-BEH-004 | CPU fallback、没有实际执行提交的 NPU kernel | 在目标设备真实执行并记录证据 |
| A5 / SUB-BEH-005 | 缓存输出、固定结果或按公开 case/data pointer 命中 | 对每次合法输入真实计算；有依据的 shape 分派不是预置答案 |
| A6 / SUB-BEH-006 | 篡改 profiler、同步、计时或安全检查 | 保持评测器及环境接口完整 |
| A7 / SUB-BEH-007 | FakeTensor、伪对象、惰性结果或非法返回结构 | 返回实际计算的 Tensor，符合输出结构与连续性要求 |

自动保护没有报错不代表所有规则都通过；I/O 变换等仍需代码检视。报告应引用具体违规位置，不能只凭关键字命中判定。

## B 类：工程与代码质量

| 检查项 | 要求 |
|--------|------|
| 提交接口 | 根 build.sh 可复现生成 cann_bench wheel，Python callable、schema、C++ 注册与 proto 一致 |
| 版本与载入 | 当前源码、测试、构建 wheel 和实际加载库一致；没有旧包或 golden wheel 冒充候选 |
| 硬件资源 | 核数、UB/Buffer 与分块满足目标平台；动态资源查询或固定参数的适用依据明确，不无依据写死硬件假设 |
| 搬运与边界 | 用目标平台支持的 API 处理对齐、尾块和边界，地址/长度计算无溢出或越界；不以强制 wrapper 拷贝隐藏不支持输入 |
| 并发与同步 | 当前 stream/设备正确，依赖有对应同步，分配与释放、队列生产与消费成对；不把数调用次数当完整正确性证明 |
| 类型与数值 | dtype 分派与计算精度符合规格，未初始化变量、非法转换及未覆盖分支有检查 |
| API 可用性 | 关键 API 及变体有目标版本依据；不凭空推荐不存在的接口，不把一个示例的可用性推广到所有芯片 |
| 代码边界 | kernel 中不使用目标工具链不支持的动态分配、递归或库功能；具体支持情况按平台资料和编译证据核实 |
| 许可与输出 | 新增代码带仓库 license 头，保留上游来源许可；Python 日志使用 logging |
| 测试可信性 | 不改评测器、golden、阈值或删测掩盖失败；公开任务只读，新增用例和来源可追溯 |

检视仅记录本次授权范围的问题与证据，不要求实现照搬知识搜集草稿，也不自行决定回退或放宽标准。

## 核对依据

已核对 cann-bench `08d519c503843bce5fd4672ffa2259abeb22fb00`；按实际 checkout 记录版本和差异。

- [docs/guide/submission_rules.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/docs/guide/submission_rules.md)
- [docs/spec/submission_spec.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/docs/spec/submission_spec.md)
- [examples/direct_launch_example/README.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/direct_launch_example/README.md)
