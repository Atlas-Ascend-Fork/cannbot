---
id: PRC-MEM-015
name: 同步原语选型：队列自动同步优先，PIPE_ALL 热路径红线
category: MEM
applies_to: 机制通用（各代 AI Core）；kernel 侧；命中判定为结构判定；PIPE_ALL 的代价为机制自明（官方 API 文档明示），收益未单独上板量化
status: ready
---

# PRC-MEM-015：同步原语选型：队列自动同步优先，PIPE_ALL 热路径红线

## 知识点

kernel 内同步原语分三档，按次序选用：

1. **TQue/TQueBind 队列语义（默认）**：`EnQue/DeQue` 在 Alloc/Free 生命周期上自动插入最小精确事件，配合已验证的 bufferNum 获得 double buffer 流水排布（PRC-MEM-003）——标准搬-算-搬数据通路**理论上不需要手写任何 SetFlag/WaitFlag**。
2. **`SetFlag/WaitFlag<HardEvent>` 精确事件对（手排专用）**：仅当流水编排是队列表达不了的（跨阶段共享 UB 的 ping-pong、多生产者/多消费者交织、自定义预取窗口）才使用，事件对必须严格配对。
3. **`PipeBarrier<PIPE_ALL>`（一次性边界专用）**：等待**所有**流水（MTE2/MTE3/V/…）中先前提交的全部指令完成，一条就把并行流水打成串行。官方 API 文档明示"会对性能产生影响，若仅阻塞单条流水线即可解决问题，应避免随意调用"。它常见的来历是**规避同步缺失**——偶发精度/踩内存问题查不到根因，加全栅栏"保平安"，问题被掩盖的同时流水收益全部归零。

两种命中形态：

- **形态① 热路径 PIPE_ALL**：主循环内（或每轮都会调到的函数里）出现 `PipeBarrier<PIPE_ALL>`。每轮一条全栅栏意味着 MTE2 预取、V 计算、MTE3 搬出之间的所有重叠机会清零，double buffer 形同虚设。正确做法是定位真实依赖对（哪两条流水在哪块 buffer 上有先后序），换成对应的精确事件（`SetFlag/WaitFlag<HardEvent::X_Y>`）或单流水栅栏（如 `PipeBarrier<PIPE_V>`），能用队列表达的直接队列化。
- **形态② 该走队列的通路手写事件网**：标准搬-算-搬主通路不用 TQue，而用成片的手工 `SetFlag/WaitFlag` 串联。三重代价：漏配对/错 event id 即卡死或踩数据（正确性风险）；把 MTE2→MTE3 焊死成串行的等效单缓冲（按 PRC-MEM-003 报）；即使配对正确，手工网也难随代码演进维护，且拿不到队列自动的 DB 排布。

## 错误写法

```cpp
// 反例（形态①）：主循环每轮一条全栅栏，所有流水重叠机会清零
for (int64_t i = 0; i < loops; ++i) {
    CopyIn(i);
    AscendC::PipeBarrier<PIPE_ALL>();   // 注释常见"防止同步问题"——掩盖缺失的精确依赖
    Compute(i);
    AscendC::PipeBarrier<PIPE_ALL>();
    CopyOut(i);
}
```

```cpp
// 反例（形态②）：标准搬-算-搬通路手写事件网替代队列
SetFlag<HardEvent::MTE2_V>(EVENT_ID0);
WaitFlag<HardEvent::MTE2_V>(EVENT_ID0);
Add(yLocal, xLocal, zLocal, count);
SetFlag<HardEvent::V_MTE3>(EVENT_ID0);
WaitFlag<HardEvent::V_MTE3>(EVENT_ID0);   // 配对正确也拿不到 DB 排布，见 PRC-MEM-003
```

## 正确写法

```cpp
// 正例：标准通路走队列，buffer 数由 InitBuffer 配置
TQue<TPosition::VECIN, 1> inQueue_;
pipe.InitBuffer(inQueue_, DOUBLE_BUFFER, tileBytes);
// CopyIn: AllocTensor → DataCopy → EnQue；Compute: DeQue → 计算 → FreeTensor
```

```cpp
// 正例（确需手排时）：精确事件对，指明流水与 buffer 的真实依赖
SetFlag<HardEvent::V_MTE2>(pingEvt);   // 本轮计算读完 ping buffer
...
WaitFlag<HardEvent::V_MTE2>(pingEvt);  // 下轮搬入复写 ping buffer 前等待
```

## 识别方法

1. **grep 全栅栏**（形态①）：`PipeBarrier<PIPE_ALL>` / `pipe_barrier(PIPE_ALL)`，按调用位置分层——主循环内或每轮调用链上 → 命中；`Init`/收尾等一次性边界 → 记录不报。命中后溯源引入动机（注释、修复偶发问题的历史），finding 里给出真实依赖对与精确替代方案。
2. **盘点主数据通路的同步方式**（形态②）：搬-算-搬是否经 TQue/TQueBind。手工事件网先判"队列能否等价表达"：能 → 命中（等效单缓冲的部分转 PRC-MEM-003 报，其余作队列化建议）；不能（见下方正当场景）→ 检查配对完整性后放行。
3. 形态①的改法排序：能队列化的队列化 > 单流水栅栏（`PIPE_V` 等）> 精确事件对；不得建议"删掉栅栏了事"——它背后可能真有依赖，删除属正确性变更，须给出依赖分析。

误报边界：

- 一次性位置（Init/收尾/跨核 SyncAll 配套、workspace 复用的一次性栅栏）的 PIPE_ALL 记录不报，非热路径头开销可忽略。
- 官方 API/框架文档明确要求的栅栏（含某些 ISASI 调用契约）不报。
- 手排 SetFlag/WaitFlag 用于队列表达不了的编排（跨阶段共享 UB、ping-pong、多生产者消费者）且事件严格配对的，是正当用法不报——判据是"能否用队列等价表达"，不是"有没有手写事件"。
- 调测代码（DumpTensor 等附带的同步）不报。
- MemBase 计算链步间的 `PipeBarrier<PIPE_V>` 是单流水语义，不属本条；连续多步的链去 PRC-VF-001（VF 融合消屏障）。
- MIX/CV 核间同步（CrossCoreSetFlag/WaitFlag、SyncAll）是另一层机制，仅当拿 PIPE_ALL 替代它们的职责时才回到本条。

## 证据要求

finding 必须给出：

- 命中语句的文件:行号与摘录，及其所在循环层级（主循环内的执行次数量级）；
- 形态①需给出依赖分析：该栅栏保护的真实流水对与 buffer，及精确替代（事件对/单流水栅栏/队列化）方案；不得只建议删除；
- 形态②需列出手工事件清单（event 对/配对位置）与队列化改造点，等效单缓冲的部分援引 PRC-MEM-003 的证据格式。

## 参考

- 官方 API 文档：`SIMD-API/basic_api/sync_control/intra_core_sync/PipeBarrier_ISASI.md`——"PipeBarrier<PIPE_ALL>() 会等待所有流水线中所有先前提交的接口完成，这会对性能产生影响。若仅阻塞单条流水线即可解决问题，应避免随意调用"；同目录 `SetFlag_WaitFlag_ISASI.md` 含错误配对触发卡死的反例。
- 官方编程模型：TQue `EnQue/DeQue` 自动同步机制（asc-devkit 编程指南编程模型章）；入门教学样例里的 `PipeBarrier<PIPE_ALL>` 属教学简化写法，不是性能实践基线。
- 关联知识点：PRC-MEM-003（DoubleBuffer 使能与时机；手工事件等效单缓冲）、PRC-MEM-006（纯搬运 TQueBind）、PRC-VF-001（MemBase 链的 PIPE_V 屏障经 VF 融合消除）、PRC-VF-002（VF 内 membar 最小化，寄存器层同步另有其规）。
