# 设备身份与失败重放证据

本契约用于身份取证及失败诊断，不改变原输出判据，也不授权恢复已暂停的精度诊断。2026-10-13 的案例来源是用户提供的 `objcopy-drift-audit/audit.json`、`baseline8/REPORT_signal11.md` 和 `combined-simulation/{combined-simulation-result.json,precision-pause.json}`；数字仅描述这些 case 与版本。

## 只读 ELF 身份

```bash
python "<本技能>/scripts/device_identity.py" "$actual_loaded_so" \
  --device-section .aicore_binary --require-symbol "$exact_device_symbol" \
  --output "$new_identity_directory"
```

省略 `--output` 仅打印 JSON。工具采用标准库，不执行 objcopy，不加载 ELF；读取输入前后 SHA，输出用独立文件且拒绝已有输出、输入的路径/符号链接/硬链接别名。支持普通 ELF32/ELF64、little/big endian section table；校验表、节、字符串和符号的偏移/长度及重叠。extended numbering、压缩节、无 section table、非 ELF payload 等明确拒绝，不能因为开头是 ELF64 就视为完整受支持格式。

`--device-section` 是精确 outer 节名，可重复；每个指定 payload 必须是真实 nested ELF 并有非空 `.text`。本次 `.aicore_binary` 满足此契约；`__aicore_rel_binary` 是另一个 outer 节，其带前缀的包装格式不能默认作为 nested ELF 解析。工具对所有 outer `aicore` 节保存字节摘要，未解析的包装节不声称具有符号核验。`devices` 内记录 `.text` SHA、实际 `.symtab/.dynsym` 精确符号及 binding/type/visibility/section_index；`--require-symbol` 只接受精确的 defined 符号，不使用 strings/子串近似命中。

host `.dynsym` 与 embedded device `.symtab` 分别取证。host `nm -D` 未找到设备 kernel 不能单独判编译失败；设备符号命中也不能独立证明 launch。完整身份链需结合正常 generated ASC、编译命令、built/live 实际 DSO SHA、device payload/inner `.text`、真实目标 launch 与 DB 的 kernel/PC 映射。host 导出过滤会改变整体 DSO 和 profiling callback，必须披露；只有 device 字节相等时不能宣称 whole DSO 相等。

本次四个 archive 被缺少独立 outfile 的 objcopy dump-section 调用覆写；这是取证工具失误，不是 kernel 或编译失败。原 application01 对应身份失效，clean application02 重建控制证据；历史文件与原 SHA 不回写。身份检查失败须先保留失败证据，再在新目录修工具或重采。

## concrete 入口与原 storage 语义

先保存板上已捕获的 concrete 入口、TensorSpec、tiling、block/核配额、原 owning storage、物理布局、storage_offset、stride 和 alias groups；设备上恢复 owning storage 后重建 view，再调用该 concrete 入口。本次正常板卡是 Ascend950PR_957b，模型是 Ascend950PR_9589/v100。重走 public guard 可能选 fallback，不能伪造型号绕 guard，也不能把 fallback 图标成候选图。调用前核验正常/模型生成 ASC、device payload 与 inner `.text`；built/live SHA 分别核验并记录 whole DSO 差异。

原 [NZ、别名与 tiling 示例](ascend950-dsl-simulation.md#2-上板保存单次重放) 保持其限定范围；没有任意 tensor 的通用设备还原器。CPU clone 只用于已经成功拷回的观测保存，不能将设备输入/输出 clone 成新 buffer 来掩盖 alias 差异。

先保留实际输入、输出、阶段状态及原 D2H/同步返回码，再执行原 verifier：

```python
# replay_evidence.py 作为普通 Python 模块导入；不导入 torch_npu。
receipt = preserve_truth_then_verify(
    lambda: save_cpu_observations(new_truth_path,
                                 {'typed': actual_cpu, 'raw': actual_raw_cpu}),
    original_golden_verifier)
```

CPU 离线测试可在启动进程前设置 `TORCH_DEVICE_BACKEND_AUTOLOAD=0`，避免 torch 入口自动加载已注册 NPU 后端；实际设备 runner 保持其原初始化方式，工具不修改该环境变量。

`save_cpu_observations` 仅接受已经拷回的 strided CPU tensor，并分别 `detach().clone()`。typed/raw 若共享 CPU storage，直接 `torch.save` 会碰到同 storage 不同 dtype 的序列化陷阱；独立 clone 后 load 的两种视图保持原字节，但不要求保持 CPU 观测别名。保存文件采用 exclusive create；原设备 alias、offset/stride 和拷贝 RC 由 runner 收据保留。`preserve_truth_then_verify` 不捕获/替换原异常；应用顶层也须保留原异常退出，不打印成功代替失败 RC。

## 分阶段状态

`replay_evidence.phase_summary` 使用八个独立 receipt，保留额外 counters、evidence、exception、原 `returncode`：

| 字段 | 证明范围 |
|---|---|
| preparation | 输入/布局/入口/身份准备 |
| target_execution | 目标实际执行；全核 END/PC 不证明数值正确 |
| output_validation | 原输出及副作用判据 |
| db_persistence | DB integrity、KernelInfo、记录范围及持久化 |
| user_exit | 用户进程实际退出（含 -11） |
| record | 顶层 record 原 RC |
| report | 目标 DB 解析原 RC |
| visualization | 图可读、标签真实、离线链接可达 |

每阶段状态为 `PASS/FAIL/blocked/notrun/unknown`。非零 RC 必为该阶段 FAIL；RC0 不能补齐缺失的输出或目标门禁。八阶段显式 PASS 才汇总 PASS。DB 的 callback `start_only/end_only/start_overwrites/end_overwrites` 保存原值，不能因为 `status=ok` 删除这些计数，也不能无因果证据将其归因于 SIGSEGV。

## CANN 9.2.0 / DSL 0.7.0 的局部 workaround

RangePop 过滤只适用于已核对导出 `__cannbot_invoke_profile_v1`、普通 `__cannbot_invoke_v9` 及缺可选导出 fallback 的版本/错误。现有[进程内过滤示例](ascend950-dsl-simulation.md#aclprofrangepop-failed-with-status--1)不修改设备代码，但跳过 host profiling callback；正常 generated ASC 与设备 payload/`.text` 的等价证据需另存。不能注入到未核验的其它版本或正式计时入口。

signal11 报告中，已加载的 `libcannsim_helper.so` SHA 为 `656a2c872bb5e93a287588260cfa9e53813b7fab51e7ea94b16211265bbb1d0d`。仅该二进制的导出/机器码和实际 loaded maps 证明 `cannsim_helper_end_launch` 是零参数 void，经 `ctypes.CDLL(None)` 查已 LD_PRELOAD 的实例，并核验实际函数来源；不得额外加载一个 helper、将 void 返回寄存器当 status 或假定所有版本有同一 ABI。本次验收后显式提交救出了 DB，不是长期公开 API，也不是自动执行的通用 helper。本 Skill 不提供未经核验的注入代码。

过滤 RangePop 和显式 end_launch 均未消除 SIG11。日志只将崩溃定界在末尾完成标记之后、正常退出之前；没有 native 栈，根因仍 unknown。Epilogue03/Prologue01 输出通过、完整 DB 通过，但 USER_APP=-11、record RC1，属于失败退出的诊断证据。

综合 model03 没有 SIG11，84 核 END、2231/2231 静态 PC 匹配及 report/图通过，但 MM2 输出 FAIL。只交付带 FAIL 的诊断图，不能作为候选精度通过；原用户暂停记录和恢复点保持不变。外层 index 警告的 [results/core 路径与自建离线 index](ascend950-dsl-simulation.md#报告失败与目标-db-选择) 是索引绕行，不是 npusim 上游修复，也无需重跑 kernel。
