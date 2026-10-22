---
id: PRC-SIMT-001
name: 离散访存/分支逻辑选 SIMT，连续规则访存留 SIMD（选路边界）
category: SIMT
applies_to: dav-3510（Ascend 950PR/950DT）kernel 侧；含离散寻址（Gather/Scatter/索引查表）或逐元素分支判断的算子
status: ready
---

# PRC-SIMT-001：离散访存/分支逻辑选 SIMT，连续规则访存留 SIMD（选路边界）

## 知识点

SIMD（MTE+Vector）对数据连续/对齐要求严格：离散寻址只能退化为标量 GetValue 逐元素循环，分支逻辑要用 Compare/Select/MaskAnd 等多条矢量 API 拼接。SIMT 允许每线程独立寻址 GM、if-else 直接表达分支，靠硬件 warp 调度掩盖访存延迟，天然适合这两类场景（官方 floor_mod 案例：SIMD 版约 49 行 → SIMT 版约 16 行，4.03→3.444us，-14.6%）。但选路有硬边界：**SIMT 线程读 GM 的有效带宽低于 SIMD MTE2**——"访 GM 粒度 128B、每次常只用 4B"的利用率论证只针对非合并的离散访问；相邻线程访问连续地址时硬件会做访存合并、利用率改善（PRC-SIMT-005），但连续大包场景 MTE2 批量搬运实测仍占优。只有"离散小包"（如 moe_init_routing Gather 的 H 小场景）SIMT 占优；行内连续段大（H 大）时多 Buffer SIMD 批量搬运更好。moe Step5 的 msprof 佐证：改 SIMT 后 scalar 23→4us、mte2 16.5→0.5us，但 vec 0.6→15us——访存压力转嫁到了 Vector 单元，连续大包场景该项会反超。

SIMT 有两种形态，约束分开核对（检视 SIMT 代码前先辨形态）：①**纯 SIMT kernel**（`__global__` 无 `__aicore__`，`<<<grid, block, dynUB, stream>>>` 启动，见 PRC-SIMT-002）：单 Block ≤2048 线程；一个 AIV 跑一个 Block；DCache 需 ≥32KB；函数内 MTE 搬运与 TPipe/TQue 不可用。②**mix 模式 VF 形态**（`__simt_vf__` + `Simt::VF_CALL`，宿主是普通 `__aicore__` kernel）：VF 入参仅支持裸指针（`__gm__`/`__ubuf__`）与基本类型，不支持引用/结构体传值/LocalTensor；该入参约束只属于本形态，不得套到纯 SIMT kernel 上。

## 错误写法

```cpp
// 反例：离散/分支逻辑硬走 MTE+Scalar，逐元素 GetValue+分支+SetValue 串行
// simt_histogram_story/src/0_serial_scalar.asc:158-167（cann-samples@6e6260c8）
for (int32_t i = 0; i < TILE_DATA_LENGTH; i++) {
    XType val = xLocal.GetValue(i);
    if (val >= minVal && val <= maxVal) {
        int32_t idx = static_cast<int32_t>(static_cast<float>(val - minVal) * bins / minMaxRange);
        if (idx == bins) { idx = bins - 1; }
        yLocal.SetValue(idx, yLocal.GetValue(idx) + 1);
    }
}
```

## 正确写法

```cpp
// 正例：SIMT 线程按索引独立寻址 GM，分支直接 if 表达
// 1_Features/hardware_features/simt/main.asc:30-45（cann-samples@6e6260c8）
inline __simt_vf__ __aicore__ __launch_bounds__(MAX_THREADNUM) void gather_function(
    __gm__ DATA_TYPE *x, __gm__ INDICES_TYPE *indices, __gm__ DATA_TYPE *y, ...) {
    for (INDEX_SIZE_TYPE idx = threadIdx.x + blockIdx.x * blockDim.x; idx < outNum;
         idx += ...) {
        INDICES_TYPE indicesValue = indices[gatherI];
        INDEX_SIZE_TYPE xIndex = outerI * gatherDimSize * innerDimSize + indicesValueI * innerDimSize + innerI;
        bool indexOutOfBound = indicesValue < 0 || indicesValue >= gatherDimSize;
        ...  // 越界分支直接 if 处理，合法索引直读 x[xIndex]
    }
}
```

## 识别方法

- 看什么：kernel 中的标量 `GetValue`/`SetValue` 逐元素循环、`Compare`+`Select`+掩码 API 拼出来的分支语义、按运行期索引跳址的搬运；反向看 SIMT 代码（两种形态都要搜：`__simt_vf__`/`asc_vf_call`/`Simt::VF_CALL`，以及无 `__aicore__` 的 `__global__` kernel、`<<<` 启动、`--enable-simt` 编译选项）出现在什么数据形态上。
- 命中条件（建议改 SIMT）：访存地址由数据决定（索引/排序结果驱动）且单次连续段小（数十到数百字节量级）；或逐元素条件逻辑用 ≥3 条矢量 API 模拟一个 if。
- 命中条件（建议改回/保持 SIMD）：SIMT 代码（任一形态）内是纯连续规则访存（地址 = 基址 + 线性函数），无分支无索引——这是误用；依据是连续大包实测 SIMD 占优（moe Step5 vec 15us 反超、官方 10026 混合方案），而非 4B/128B 利用率推算（合并访存下该推算不成立）。
- 误报边界：①连续规则访存的 elementwise/reduce 别推 SIMT；②离散但行内连续段大（如 Gather 的 inner 维成千上万元素）时，多 Buffer SIMD 逐行 DataCopy 可能更优，需给出行长评估而非直接判 SIMT；③混合方案存在——数据量小可先 SIMD 搬 UB 再 SIMT 读 UB（官方 10026，gather 4.56→3.57us），不要把"SIMT 读 GM 慢"直接等同"不能用 SIMT"。

## 证据要求

- 命中处 文件:行号 与摘录（离散寻址的标量循环，或 SIMT 函数内的纯连续访存模式）。
- 定量依据：单次连续访问的字节数估算（据 shape/tiling 推导），据此说明落在 SIMT 占优区还是 SIMD 占优区。
- 排除误报：确认该循环不可被现有矢量 API 直接覆盖（如 Gather 类硬件指令）；若建议 SIMT，需确认满足纯 SIMT 环境约束（线程数/参数类型）。

## 参考

- cann-samples：`Samples/1_Features/hardware_features/simt/`（Gather）、`Samples/2_Performance/moe_init_routing_story/src/5_simt.asc`（选路边界实测）
- 官方文档：atlas_ascendc_best_practices_10_10028（SIMT 实现分支判断）、10_10026（UB 预加载 + SIMT 读 UB 混合方案）
- 关联：并行化写法见 PRC-SIMT-002；二维布局/整除优化见 PRC-SIMT-005；写冲突见 PRC-SIMT-003
