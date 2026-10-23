---
name: tiling-ut-harness
description: 在 x86 宿主机上构建并运行 CANN TilingFunc 的 gtest 单测（pattern B：registry dlopen 已安装 op_host .so）。用于编写或修改 tests/tiling/ 下的 Tiling UT、伪造 fe::PlatFormInfos 平台参数、构造 OpTilingContextBuilder、链接 libtiling_api、捕获 OP_LOGE 日志锚点；遇到 GetCoreNumAiv/GetCoreMemSize 返回 0、undefined reference to fe::PlatFormInfos 或 CheckLogLevel、cannot find -lbase、DSO missing from command line、gtest 链接失败、日志断言取不到输出时使用。
disable-model-invocation: true
---

# Tiling UT 宿主机 harness（pattern B）

## 心智模型

TilingFunc 由 CANN 框架在真实编译流程中回调。宿主机 UT 要直接调它，必须用三件假货顶替框架：**伪造芯片**（fe::PlatFormInfos 塞平台参数）、**伪造上下文**（OpTilingContextBuilder 拼输入/attr/TilingData/workspace 缓冲）、**伪造注册表**（把已安装 op_host .so 注册进 OpImplSpaceRegistryV2 再取 TilingFunc）。三件假货的写法与算子无关——每个算子的 UT 重复同一套，差异只在 case 矩阵和 oracle。

本 skill 的事实锚定在一个已验证基线：cann-9.2.0 / Ascend950 (arch35)。**先跑自检再干活**：自检约 10 秒，告诉你当前环境是否仍与基线一致；不一致（DRIFT）时按重推导流程走，不要硬套本 skill 的事实。

## 使用规则

1. 写任何 harness 代码之前，先跑一次自检：

   ```bash
   bash skills/tiling-ut-harness/scripts/env_doctor.sh
   ```

   打印 `VERIFIED` → SDK 布局、链接配方、平台 mock 映射三项对当前环境生效，直接引用，**不要再用 nm/objdump/strings 逆向二进制库、不要写 /tmp probe 程序重新推导**——这些手段只属于 DRIFT 之后「重推导」授权的流程。注意 VERIFIED 不覆盖 builder 链 / LogCapture / registry dlopen / run.sh，这些环节的问题按对应 reference 排查。
   打印 `DRIFT: ...` → 按消息里指向的 reference 处理（key 映射问题走 platform-mock.md 的「重推导」节），并把新映射写进 UT 文件头注释。

2. 起点永远是可编译的黄金样例 `assets/golden_probe.cpp`，从它开始改，不从空文件写。
3. 编译/链接报错先查 references/compile-link.md 的错误表再动手，不要试错式增删链接库——目标是报错串在表内一次定位到修法。
4. references 分工：

| 要做什么 | 读哪个 |
|---|---|
| 伪造芯片参数、确认 Get* 读哪个 key、平台自检写法 | references/platform-mock.md |
| g++/CMake 链接配方、gtest_oldabi、编译报错对照 | references/compile-link.md |
| 让 OP_LOGE 可见、按 case 捕获、断言日志锚点 | references/log-capture.md |
| UT 单文件结构、builder 链、LoadTilingKernel、run.sh 四步、隔离安装 | references/harness-layout.md |

## 完成判据

- `env_doctor.sh` 打印 `VERIFIED`（或 DRIFT 已按重推导流程处理并记录）。
- UT 的 run.sh 输出含 `[setup] loading op_host .so: <路径>` 行——这是"测的是已安装包里的哪个 .so"的证据，red baseline 审计要 grep 它。
