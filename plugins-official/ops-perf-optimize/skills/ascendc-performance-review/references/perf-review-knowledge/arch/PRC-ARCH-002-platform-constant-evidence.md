---
id: PRC-ARCH-002
name: 平台参数必须从接口获取并真正参与切分
category: ARCH
applies_to: 机制通用（各代 AI Core）；**host/tiling 侧为主**，kernel 侧看写死的容量常量；是 PRC-MEM-011/012 的前置——先确认切分依据的数从哪来，再谈切分逻辑对不对
status: ready
---

# PRC-ARCH-002：平台参数必须从接口获取并真正参与切分

## 知识点

tiling 要按平台算切分，核数与 UB/L2 容量必须从平台接口取，并且**取到的值要真正出现在决定 blockDim / ubFactor / 模板阈值的表达式里**。三种命中形态：

- **形态① 写死**：核数或容量以字面常量出现，全仓没有 `GetCoreNumAiv()` / `GetCoreMemSize()` 调用。危险性来自同代芯片参数并不唯一——CANN 9.2.0 的 68 个 `Ascend950*.ini` 里 `vector_core_cnt` 有 **8 / 16 / 56 / 64 / 72 五种取值（最大差 9 倍）**，写死任一个值在其余档位上都是错的；`ub_size` / `l2_size` 当前虽全代一致，同样不该赌下一代。
- **形态② 取了不用（假取值）**：调了接口拿到 `ubSize` / `coreNum`，但真正决定切分的是另一套魔数常量表，接口值只用于日志或边角校验。**这是最隐蔽的一种**——grep 能看到接口调用，容易误判成正确写法。
- **形态③ 口径错**：向量算子把 AIC 核数当 AIV 核数用（`GetCoreNum()` vs `GetCoreNumAiv()`）；或忘记扣除保留区就把总容量当可用容量。**AIV-only 算子的核数一律以 `GetCoreNumAiv()` 为唯一口径**：同一 tiling 内 `GetCoreNum()` 与 `GetCoreNumAiv()` 混用，或用 `GetCoreNum()` 并隐式假设其等于 AIV 数，均属命中——AIC:AIV 分离平台上前者可能取到全核数，超发 AIV-only kernel 的核数（在库 posembedding/foreach 类均有此写法实例）。

## 错误写法

```cpp
// 反例①：容量写死，注释自证是按另一代平台推的
static constexpr int32_t MAXBUFFER = 195584;   // (192 - 1) * 1024 byte
Ppipe->InitBuffer(unitBuf, MAXBUFFER);         // 目标平台 UB 更大时恒定闲置，且与 shape 无关
```

```cpp
// 反例②：接口值与决策值两张皮——取到了 ubSize，但决定路由的是魔数表
GetCompileParameters(context, numCore, ubSize);            // 取到了
...
uint32_t ub_factor = (dtypeKey == DTYPE_KEY_FP32) ? UB_FACTOR_B32   // 10240，魔数
                                                  : UB_FACTOR_B16;  // 12288，魔数
if (numCol > ub_factor) { modeKey = MODE_SPLIT_D; }        // 决定切不切列的是魔数，不是 ubSize
```

## 正确写法

```cpp
// TilingPrepare：一次性从平台接口取，落到 compileInfo
compileInfo->totalCoreNum = ascendcPlatform.GetCoreNumAiv();   // 向量算子用 Aiv 口径
ascendcPlatform.GetCoreMemSize(platform_ascendc::CoreMemType::UB, compileInfo->totalUbSize);

// Tiling：扣除预留后，切分因子由它解出，而不是查表
ubSize -= UB_USED;
int64_t maxUbFactor = (ubSize - fixedSize) / linearCoef;
uint32_t blockFactor = CeilDiv(numRow, coreNum);
```

## 识别方法

在 host/tiling 源码中按顺序做，**第 2 步不能省**：

1. grep 平台接口调用：`GetCoreNumAiv` / `GetCoreNum` / `GetCoreMemSize` / `GetSocVersion`。一个都没有 → 形态①，直接命中。
2. **追值去向**：从接口返回的变量出发，逐跳追到决定 `blockDim` / `ubFactor` / 模板选路阈值的表达式。若该链路在某一步被魔数常量取代，或接口值只流向日志/边界校验 → 形态②命中，并记录被取代的位置。
3. 核对口径：向量算子应为 `GetCoreNumAiv()`；UB 可用量应扣除预留（如 `UB_USED`）；L2 用平台查询而非文档示意值 → 不符命中形态③。
4. kernel 侧另看写死的容量常量（`InitBuffer` 的字面量、`MAXBUFFER` 一类）——它们绕过了 host 的平台参数，即使 host 侧写法正确也仍然命中。

误报边界：

- **不得仅凭"grep 到了 GetCoreMemSize"就判正确写法**——必须完成第 2 步追值，形态②正是靠这一步才暴露；
- 常量是**保守下界**（按全代最小档位取值以跨档安全）且有注释或运行期校验佐证的，记录不报，可降级为"可按运行时容量放宽"的提示；
- 该 CANN 版本确实不提供该参数的查询接口，代码已用 ini/规格值并注明来源的，不报；
- UT/桩代码里的固定值不报；
- 形态③的"混用即命中"以 AIV-only 算子为限：MIX/CV 混合算子本就需要 AIC/AIV 两种口径并存，各自用于对应侧的不报；`GetCoreNum()` 仅出现在日志或与核数发放无关的边角校验里的，降级为记录；
- 写死常量但恰等于目标平台真值的，仍按形态①报——换档位即错，与当前是否碰巧正确无关。

## 证据要求

finding 必须给出：

- 平台参数获取处的文件:行号与摘录；若为形态①，给出"全仓无平台接口调用"的 grep 命令与空结果；
- **形态②必须给出追值链**：接口返回变量 → 中间赋值 → 最终决定切分的表达式，并指明在哪一步被魔数取代；
- 写死常量的数值与其对应的平台档位（若可判定），以及与目标平台真值的差额。

检视报告在元信息段注明本次目标平台的参数取值与来源（运行时 `acl.get_soc_name()` / `GetCoreNumAiv()`，或对应 SocVersion 的 ini）。该值**只用于核对代码算出的数**，不替代上述代码级证据，也不单独构成 finding。

**环境取不到时（检视 Agent 常态——1C 不要求 NPU、也未必有 toolkit）**：在元信息段注明"平台数值不可得"即可，**本条与 PRC-MEM-011 / PRC-MEM-012 一律照常判定、不得因此标 blocker 或跳过**。三条的命中形态全部是结构判定（接口调用有无、追值链是否被魔数取代、赋值链顺序与自由度），不需要任何平台数值；数值只影响 finding 的量化描述与排序。

## 参考

- 平台接口：`platform_ascendc::PlatformAscendC` 的 `GetCoreNumAiv()` / `GetCoreMemSize(CoreMemType::UB, ...)` / `GetSocVersion()`。
- 档位差异佐证：`<CANN 安装路径>/<arch>-linux/data/platform_config/<SocVersion>.ini` 的 `vector_core_cnt` / `ub_size` / `l2_size`。
- 关联知识点：PRC-ARCH-001（架构宏门控，同样是"代码怎么看平台"）、PRC-MEM-011（拿到核数之后的切分逻辑）、PRC-MEM-012（拿到 UB 之后的切分逻辑）。
