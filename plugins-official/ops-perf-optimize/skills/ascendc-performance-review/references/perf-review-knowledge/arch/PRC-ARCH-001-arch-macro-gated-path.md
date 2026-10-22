---
id: PRC-ARCH-001
name: 架构门控把目标平台关在快路之外
category: ARCH
applies_to: 多架构共编的 kernel 与公共头；kernel 侧；凡结论依赖 `#if` 架构宏取值时均适用（含其它检查点的识别方法）
status: ready
---

# PRC-ARCH-001：架构门控把目标平台关在快路之外

## 知识点

多架构共编的算子常用 `#if __CCE_AICORE__ == X` / `__NPU_ARCH__ == Y` / `__DAV_*` 在同一函数里并排放"快路"和"兜底路"。宏名与平台名**不是一一对应**：dav-3510 的 `__CCE_AICORE__` 取值是 **310**（与 310P 同值），`__NPU_ARCH__` 才是 3510。因此"目标平台实际走哪条分支"只能打表取证，不能从宏名反推。误判有两个方向，代价都很高：

- **漏报（真实性能损失）**：目标平台确实落在兜底路——快路的一条大 DMA 变成多块搬运，或退化成逐元素标量回填加额外同步——而检视者以为快路已生效；
- **误报（整条 finding 作废）**：检视者以为某分支在目标平台不生效，据此断言"该搬运是空函数体""输出从不写回"，进而把用到该模板的 case 判成不可分析。

## 错误写法

```cpp
// 反例①：用 #if 给编译期常量赋值，随后运行期 if 选路
//         → 目标平台上 isAligned 恒 false，快路成死代码，即便运行期 cols 本就 32B 对齐
#if (defined(__NPU_ARCH__) && __NPU_ARCH__ == 3003)
    bool isAligned = true;
#else
    bool isAligned = false;
#endif
    ...
    if (isAligned) {
        DataCopyCustom<T>(dst, src[off], rows * cols);   // 快路：1 条连续大搬运
    } else {
        DataCopyCustom<T>(dst, src[off], rows, cols);    // 兜底：blockCount=rows，rows 块
    }
```

```cpp
// 反例②：兜底路带逐元素标量回填与额外同步，与快路的一条指令代价差一个量级
#if (defined(__CCE_AICORE__) && (__CCE_AICORE__ == 220 || __CCE_AICORE__ == 310))
    DataCopyPad(dstTensor, srcTensor, copyParams);       // 快路：一条指令处理非对齐尾
#else
    DataCopy(dstTensor, srcTensor, num);
    SetFlag<HardEvent::MTE3_S>(EVENT_ID0);
    WaitFlag<HardEvent::MTE3_S>(EVENT_ID0);
    for (int32_t i = 0; i < numPerBlock; i++) {           // 兜底：逐元素标量搬运
        T v = srcTensor.GetValue(count - numPerBlock + i);
        srcTensor.SetValue(i, v);
    }
    SetFlag<HardEvent::S_MTE3>(EVENT_ID0);
    WaitFlag<HardEvent::S_MTE3>(EVENT_ID0);
    DataCopy(dstTensor[count - numPerBlock], srcTensor, numPerBlock);
#endif
```

## 正确写法

先对目标 SoC 打表，再判每个门控点的真假：

```text
$ printf '' > /tmp/empty.cpp
$ bisheng -x cce --npu-arch=dav-3510 -dM -E /tmp/empty.cpp \
    | grep -E '__CCE_AICORE__|__NPU_ARCH__|__DAV_'
#define __CCE_AICORE__ 310
#define __DAV_C310__ 1
#define __DAV_C310_CUBE__ 1
#define __DAV_C310_VEC__ 1
#define __NPU_ARCH__ 3510
```

→ `__CCE_AICORE__ == 310` 在 dav-3510 上**为真**（快路生效，不构成 finding）；`__NPU_ARCH__ == 3003` 为假。

选路判据本身与架构无关的（如对齐性），改用运行期/tiling 已知量，别绑在架构宏上：

```cpp
// 正例：对齐性由 tiling 决定，不由架构决定
bool isAligned = (numCol % (ONE_BLK_SIZE / sizeof(T)) == 0);
```

## 识别方法

在被检视源码中按顺序做：

1. grep `#if` / `#ifdef` 中出现的 `__CCE_AICORE__`、`__NPU_ARCH__`、`__DAV_*`，列出全部架构门控点及其文件:行号；
2. 对目标 SoC 打表得到宏取值表，逐个门控点判定真假。**禁止从宏名反推平台**（`__CCE_AICORE__ == 310` 不等于"只有 310P"）；
3. 对判为**假**的门控点，比对快路与 `#else`/缺省路的形态差异：快路是一条 `DataCopy`/`DataCopyPad`，兜底路是多块搬运、逐元素 `GetValue/SetValue` 回填、额外 `SetFlag/WaitFlag`，或退化算法——命中；
4. 变体形态：`#if` 只用来给 `bool`/`constexpr` 赋值、随后运行期 `if` 选路的，等价于在目标平台把一条分支变成死代码，同样命中，且要额外说明该判据本可由运行期量决定。

误报边界：

- 门控点在目标平台**判为真**（快路已生效）的不报——这是多数情况，必须先打表再下结论；
- 兜底路是**功能性必需**（目标平台确实不支持该指令/API）的不报，需给出不支持的依据（`/ascendc-docs-search` 或本机 SDK 头文件），不能只凭"写了 `#else`"就断定是遗漏；
- 目标平台落在兜底路、但两条路的指令条数与搬运形态等价的不报；
- **未打表就断言某分支在目标平台"不编译""是空函数体""输出不写回"的，属证据不足，不得报出**，也不得作为其它 finding 的前提。

## 证据要求

finding 必须给出：

- 门控点的文件:行号与 `#if` 条件原文；
- 打表命令与输出中相关的 `#define` 行，据此写明该门控点在目标平台的真假判定；
- 快路与兜底路各自的代码摘录，以及形态差异（指令条数、blockCount、是否含标量循环或额外同步）；
- 若按"功能性必需"排除，附 API 支持性依据的来源。

## 参考

- 打表命令：`bisheng -x cce --npu-arch=<arch> -dM -E <空文件>`。dav-3510 实测取值（CANN 9.2.0）：`__CCE_AICORE__=310`、`__NPU_ARCH__=3510`、`__DAV_C310__/__DAV_C310_VEC__/__DAV_C310_CUBE__=1`。
- 平台与架构代际对应关系：`npu-arch` skill。
- 关联知识点：PRC-MEM-005（兜底路多块搬运的收敛方向）、PRC-SCA-003 / PRC-SCA-006（兜底路标量回填与主尾块分离的头开销）。
