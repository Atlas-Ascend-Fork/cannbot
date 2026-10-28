# Ascend 950 DSL 仿真流水图：完整采集经验

本文依据四个 cannbot-dsl demo 在 x86_64、Ascend950PR、CANN 9.2.0 下的实际采集。命令参数已与该版本的 `npusim record/report --help` 核对。技能不依赖采集机器或其历史产物；下面的环境、输入和产物路径均由当前任务指定或发现。设备身份、concrete 入口、真值保存、八阶段状态和版本限定 workaround 见[身份与重放证据契约](identity-and-replay-evidence.md)。包内 API、DB schema 和工具链目录可能随版本变化，兼容处理只在对应错误被证实时使用，不修改已安装包或算子源码。

## 从用例到图的链路

```text
仓库原始用例 → 上板精度/性能 → 保存输入、输出、tiling、布局和别名
                                      ↓
                              单次仿真重放 + 输出校验
                                      ↓
                           找到对应 launch 的目标 DB
                                      ↓
                          npusim report → 原始 trace JSON
                                      ↓
                           PNG/SVG + 离线交互图 + 统计
```

要同时区分三个时间：上板协议测得的耗时、trace 的仿真指令跨度、仿真命令的墙钟秒数。上板 67 µs 的 case 可以花约 127 秒仿真。不能自动用 50/70 µs 或“分钟级”排除用户明确要求的 case；中位数小于 70 µs 也不代表每次样本都小于 70 µs。

筛选/计时继续遵循 `ops-profiling`，本次采用 10 组相邻 256 MiB FP16 ArgMax → target，保留全部样本，取目标 kernel 序列耗时总和的中位数。该协议不要放进仿真 runner；仿真只运行目标一次。波动超过正式性能对比门槛的数据可保留用于筛选，不能冒充稳定的优化基线。

## 1. 环境与采集身份

先激活装有 wheel 的 Python 环境，再 source 用户指定 CANN。若该环境由 conda 管理，可用以下模板；变量由用户或当前任务配置，不填开发者机器的默认值。已有 venv/其它 Python 环境时，使用该环境的激活方式，不强制改用 conda。

```bash
: "${conda_env:?设置装有 DSL wheel 的 conda 环境名}"
: "${cann_setenv:?设置用户指定的 CANN 环境脚本}"
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$conda_env"
source "$cann_setenv"
python -c 'import cannbotdsl, torch, torch_npu'
npusim record --help
npusim report --help
```

后续示例使用以下参数。不要从旧记录猜测或填入固定路径；缺少影响执行的信息时先获取该信息。

| 参数 | 当前任务中的来源 |
|---|---|
| `pipeline_skill` | 实际加载的本技能 `SKILL.md` 所在目录；内部资源均使用相对路径 |
| `trace_runner` | 项目中已验证的单次重放 Python 文件 |
| `trace_run` | 用户选择的本次新输出目录 |
| `trace_archive` | 该次 record 生成的具体 `npusim_*` 目录，不自动取历史最新项 |
| `target_db` | 核对 kernel/launch 后选定的本次 DB 文件 basename |
| `target_trace` | 该目标报告实际生成的单个 trace JSON |
| `trace_time_unit`、`trace_title` | 已核验的时间单位，以及算子/case/核的显示名称 |

示例里的 snapshot、tiling 和 metadata 必须由当前项目准备；文档中的历史用例仅说明结果，不要求读取原采集机器的 runner、权重或图文件。

保留 case ID、全部 shape/dtype/布局/属性、源码与二进制 SHA、CANN/包版本、物理卡、stream 核配额、block_num、tiling、精度结果和实际 launch 序列。仿真兼容处理可能改变 host 导出 ABI，应单独记录；不要声称仿真 `.so` 与上板 `.so` 二进制一致，仅因为计算源码相同。

上板物理卡由本次调度决定，不能写死卡号；仿真前清理继承的物理卡映射，例如 `unset ASCEND_RT_VISIBLE_DEVICES`，runner 中设置 `torch.npu.set_device(0)`。其它可见性变量按当前环境检查。共享卡经用户允许可以使用；记录频率/占用及性能波动，不将共享环境的抖动归因于仿真错误。CPU 仿真会占用大量线程、内存和磁盘，可按当前主机资源设置 `OMP_NUM_THREADS` / `MKL_NUM_THREADS`，它们不限制模型内部线程数。

可设置 `CANNBOTDSL_DUMP_ASCENDC=1`、`CANNBOTDSL_DUMP_DIR` 指向本次输出目录下的生成源码目录，`CANNBOTDSL_CACHE_DIR` 指向本次缓存目录；`CANNBOTDSL_AUTO_BUFFER_SYNC=1` 保持自动 buffer 同步。不要为了消除等待而随意关闭同步，否则会改变计算路径或引入精度问题。记录这些开关及实际 runner 版本，仿真时的 disk cache 禁用见下文。

## 2. 上板保存，单次重放

从对应 `test/<op>/test_<op>.py` 中选原始 case，先与仓库 golden 校验。保存输入 snapshot 和一次上板输出，后续仿真对照同一个 snapshot。输入准备、metadata、格式转换尽量在上板完成，避免在模型中重复模拟大权重 Cast/TransData、padding、清零或不支持的辅助任务。

调用前后 `torch.npu.synchronize()`，将实际输入/输出、原拷贝返回码和阶段状态持久化后执行原校验。CPU typed/raw 观测分别 clone 后保存，避免共享 storage 的不同 dtype 序列化陷阱；原设备 alias 不变，见[真值保存](identity-and-replay-evidence.md#concrete-入口与原-storage-语义)。完全相同的确定性路径，本次用 `torch.equal(actual.view(torch.uint8), expected.view(torch.uint8))` 比较字节；其它路径用原用例支持的精度判据，并记录判据。不要仅打印成功字符串或只比较 tuple 的公共前缀：检查输出数量、shape、dtype 及每个有效输出，必要时还检查原地修改的 cache。本次历史 runner 对返回输出做了字节对照；这不等同于完整检查所有副作用。

### NZ 格式不能用普通 CPU tensor 代替

`.cpu()` 或 `format_cast` 得到逻辑 ND 内容后再 `.npu()`，不能保证恢复 NZ 的物理布局；直接以 ND 内容作为 NZ 参数会改变计算语义。普通 `.cpu()` 也可能因非 ND 格式失败。

本次的 int8 NZ 权重在上板保存：逻辑 shape、dtype、`torch_npu.get_npu_format(x)`、完整 physical storage bytes；在仿真恢复同格式 storage，直接 H2D 拷贝，避开转换 kernel。

```python
import ctypes
import torch
import torch_npu

acl = ctypes.CDLL('libascendcl.so')
acl.aclrtMemcpy.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                          ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
acl.aclrtMemcpy.restype = ctypes.c_int

def snapshot_int8_nz(x):
    # 此示例仅用于本次 owning、零 storage_offset 的 int8 NZ 权重。
    assert x.dtype == torch.int8 and x.storage_offset() == 0
    torch.npu.synchronize()
    size = x.untyped_storage().nbytes()
    raw = torch.empty(size, dtype=torch.uint8)
    status = acl.aclrtMemcpy(raw.data_ptr(), size, x.data_ptr(), size, 2)  # D2H
    assert status == 0, status
    return dict(shape=list(x.shape), dtype='int8',
                acl_format=torch_npu.get_npu_format(x), raw=raw)

def restore_int8_nz(snapshot):
    assert snapshot['dtype'] == 'int8'
    x = torch_npu.empty_with_format(snapshot['shape'], dtype=torch.int8,
                                   device='npu:0',
                                   acl_format=snapshot['acl_format'])
    raw = snapshot['raw']
    assert raw.dtype == torch.uint8 and raw.is_contiguous()
    size = raw.numel()
    assert x.untyped_storage().nbytes() == size
    status = acl.aclrtMemcpy(x.data_ptr(), size, raw.data_ptr(), size, 1)  # H2D
    assert status == 0, status
    return x
```

不是任意 tensor 的通用序列化器。其它 dtype 需按原 dtype 正确分配物理 storage；非零 offset、view、stride、别名需保存并按 owning storage 恢复，不能从 view 的 data_ptr 拷整个 storage。先在真实设备上做 snapshot → restore → 调用的回环校验，再交给仿真。

### 恢复 buffer 别名

独立的 `x.cpu()` / `x.npu()` 会让原本共享 storage 的多个参数变成独立 buffer。本次 prologue 的 `run_args[16]` 是 scale buffer 的 view，`run_args[17]` 是原 buffer；原 kernel 写入后，公开输出通过同一 storage 读取。

```python
# 仅适用于已核对的本次 PreparedAttnPrologue 参数排列。
arguments[17] = arguments[16].view(arguments[17].shape)
```

别名丢失时计算 kernel 可执行完，但输出校验会报 `simulator / hardware byte mismatch`。先排查 snapshot/replay 语义，再判断算子计算是否有错。通用重放应保存 alias group、offset、stride，恢复 owning buffer 后重建 view；不要把本次索引硬编码到其它算子。

### 保持核数与 tiling

仿真默认平台 quota 不一定等于上板 stream quota。本次上板为 28 AIC，仿真默认可给 32 AIC；Epilogue 的 28/32 核会选不同 tiling。`record -n all` 只是记录范围，不能修正这个差异。

- Prologue：保存 `dataclasses.asdict(prepared.tiling)` 与 `prepared.args`；恢复 `AttnPrologueTiling(**snapshot)`，构造 `PreparedAttnPrologue` 重放，保留输出 buffer 视图，避开 host prepare 中的 padding/辅助任务。
- Epilogue：在重放进程中按原 `performance.csv` 的 block_num（本次 28）恢复 `core_budget` 返回值，然后调用原 `_attn_epilogue_out`；算子文件和安装包不改动。

```python
# 核数来自该 case 的上板证据；28 不是 Ascend950 的通用常量。
blocks = measured_block_num
sample.core_budget = lambda ref: (ref.device.index, blocks, blocks * 2)
```

若模型 SKU guard 与板上入口不同，恢复原 spec/storage/tiling 后使用板上已捕获 concrete 入口，并校验 generated/device payload/inner `.text`；不要伪造型号或将 fallback 图标为候选图。兼容 hook 仅适用于对应 sample API；同时核对编译参数、template、tile shape 和输出语义。保持默认平台配置采到的图可作为另一配置的诊断结果，但不能标为原上板 launch 的图。本次 32 核尝试被中止并保留，最终出图来自 28 核成功尝试，不能据此断言 32 核 kernel 必然失败。

## 3. 本次确认的环境兼容处理

### `aclprofRangePop failed with status -1`

FP8 attention 和 MLA 首次仿真的栈落在 wheel 的 host runtime invoke，报上述错误。它不是 kernel 数学错误的证据。本次 CANN 9.2.0 / DSL 0.7.0 在仿真进程中隐藏可选 host profiling 导出符号，让 runtime 使用普通 invoke ABI；计算源码不变，过滤后输出与上板一致。这是 RangePop 的局部兼容处理，不能称为 SIG11 修复；host callback/导出变化及 device payload 等价需分别披露。其它版本先核对实际 API 和 fallback，见[版本限定证据](identity-and-replay-evidence.md#cann-920--dsl-070-的局部-workaround)。

```python
import os
from cannbotdsl.core.toolchain.ascendc import AscendCCompiler

original_compile = AscendCCompiler.compile_ascendc_to_so
def compile_without_tensor_profile(self, source, **kwargs):
    kwargs['exported_symbols'] = tuple(
        s for s in kwargs.get('exported_symbols', ())
        if not s.endswith('__cannbot_invoke_profile_v1'))
    return original_compile(self, source, **kwargs)
AscendCCompiler.compile_ascendc_to_so = compile_without_tensor_profile
os.environ['CANNBOTDSL_CACHE_DISK_DISABLE'] = '1'
```

应在编译目标之前安装 hook；禁用 disk cache 避免加载仍带 profiling 入口的旧产物。先检查当前 wheel 的导出和 fallback 路径，不能将其它版本的 profiler 错误统一套用此处理。不要给正式上板性能采集禁用 profiling，也不要修改安装包后影响其他用户。

### MLA metadata 编译找不到 `cstdint`

已验证的失败来自 wheel 的 AICPU flags 与所选 CANN 的 HCC/sysroot/C++ 头文件布局不一致。先读取当前 `AicpuToolchain.aicpu_compile_flags()` 和编译日志，再在用户指定的 CANN 安装内核实 sysroot、目标架构 include、C++ include 及其版本目录。不要把某台机器的 HCC 根目录或版本替换写进通用规则。

需要进程内适配时，可由当前任务创建 JSON 参数映射文件，通过 runner 自定义配置 `TRACE_AICPU_FLAG_MAP` 传入；该配置不是 CANN 内置变量。映射的键是日志中的完整旧 flag（或独立路径参数），值是已核实的实际 flag/路径，未列出的参数保持原值：

```python
import json
import os
from pathlib import Path
from cannbotdsl.aicpu.toolchain import AicpuToolchain

flag_map = json.loads(Path(os.environ['TRACE_AICPU_FLAG_MAP']).read_text())
assert isinstance(flag_map, dict)
assert all(isinstance(k, str) and isinstance(v, str) and k and v
           for k, v in flag_map.items())
original_flags = AicpuToolchain.aicpu_compile_flags
def actual_cann_flags(self):
    return [flag_map.get(flag, flag) for flag in original_flags(self)]
AicpuToolchain.aicpu_compile_flags = actual_cann_flags
```

建立映射时要验证 `--cce-aicpu-sysroot=...` 的目录及每个 `-isystem` 后的头文件目录真实存在，保存映射和修改前后的编译参数。这里只处理匹配日志的路径错误，不自动升级编译器或猜测缺失的目录。metadata 在硬件上预生成并作为输入快照；本次 MLA 流水图只覆盖主 AI Core kernel，不覆盖 metadata AICPU，不要声称完成了 AICPU 仿真。

### SDMA / 准备过程慢

Prologue 前期在模型中重复恢复格式或 prepare；部分日志有 `unsupported task type: SDMA`，部分运行内存持续增长且未完成，最后由 agent 发送 SIGTERM。记录为“中止”，不能将 `signal 15` 说成算子自然崩溃，也不能仅凭慢或 warning 断言死锁。恢复物理 NZ storage、硬件 tiling 和别名后，最终单次重放成功。若仍出现不支持的任务，定位是哪一个准备动作触发，移到 snapshot 阶段，而不是任意跳过计算或清零。

## 4. 执行与状态判定

每次使用新目录并保留日志。使用当前 Python 构造应用命令，runner 路径按 shell 参数引用，避免空格或特殊字符使命令解析错误：

```bash
unset ASCEND_RT_VISIBLE_DEVICES
: "${trace_runner:?设置项目的单次重放 runner}"
: "${trace_run:?设置本次新输出目录}"
trace_app=$(python -c 'import shlex, sys; from pathlib import Path; print(shlex.join([sys.executable, str(Path(sys.argv[1]).resolve())]))' "$trace_runner")
mkdir -p "$trace_run"
npusim record "$trace_app" -s Ascend950 -n all \
  -o "$trace_run/record" > "$trace_run/record.log" 2>&1
```

也可用 `-n 0` 限制日志量，但要在采集前决定覆盖范围。内部延迟/调试开关按当前安装工具核验，不将历史机器的未公开环境变量当作成功必要条件。

检查用户程序退出成功、日志中 `Simulation SUCCESS`、输出校验通过及 record 存在。heartbeat、CPU busy、cycle count 和 DB 增长用于判断进展，不代表已完成。等待期间持续更新进度。若用户没有设置硬超时，不因两分钟或上板耗时稍大自动停掉；配置错误、重复准备、明确不支持任务或资源异常时才针对原因处理，并保留尝试。

分别记录八阶段状态：`preparation`、`target_execution`、`output_validation`、`db_persistence`、`user_exit`、`record`、`report`、`visualization`，保留各层原始 RC、异常及 helper 起止/覆盖计数。输出/DB 通过不能覆盖 USER_APP=-11、record RC1；原[分阶段契约](identity-and-replay-evidence.md#分阶段状态)用于机械汇总。输出验证失败的 trace 可保留供排障，但不能冒充正确 case 的最终结果。仿真成功而 report 失败时，重做报告即可。

## 报告失败与目标 DB 选择

本次 FP8 public API 会产生 9 个准备 kernel 和 1 个主 DSL kernel。最初自动 report 报 `No report backend succeeded / Please install Python report dependencies`，进一步的 `report/results/runner.py.log` 才显示真实原因：`No executed instructions found`、`ascend950_scalar_ipc_analyzer ... division by zero`。

已验证的采集中，前三个 DB 的 `ExecutedInstructions` 为 0，主核 DB 有 11,801 条指令。后面的准备 DB 也有真实指令，不能把所有准备核都称为空记录。这个数量用于说明失败原因，不是其它 case 的验收常量，也不能只因外层报依赖错误就盲目安装包。

```bash
# 查看数量、KernelInfo；只读打开 SQLite。
: "${pipeline_skill:?设置实际加载的技能目录}"
: "${trace_archive:?设置本次 record 的 archive 目录}"
python "$pipeline_skill/scripts/select_simulator_db.py" --record "$trace_archive/record"
# 查源码/launch manifest/npusim.log/cannsim_helper.log，确认 target_db 是目标。
: "${target_db:?设置本次目标 DB 的准确 basename}"
python "$pipeline_skill/scripts/select_simulator_db.py" --record "$trace_archive/record" \
  --select "$target_db" --output "$trace_run/selected_record"
npusim report -e "$trace_run/selected_record" -n 0 -o "$trace_run/report"
```

文件序号、后缀 hash 会随运行变化，必须使用本次实际名称；`acl_kernel` 也只是已验证 DSL 的命名模式，不是通用身份规则。不能将历史文件名作为默认 target。辅助脚本只筛除空指令 DB，不代替语义匹配；目标目录需为新目录，重试解析可直接复用已选定的目录。多个目标 launch 应分别报告、标明各阶段。

目标 DB 报告成功后，本次工具仍提示 `No *_reports/ directories found`：实际报告嵌套于 `report/results/*_reports/core_0/`，聚合 index 错找外层。按真实 trace 路径创建自己的索引，不重跑 kernel。`DispatchTime` 未实现、Issue Queue unavailable 等警告表示该指标没有数据，不代表整张指令图无效，也不能据此画出未采到的 queue utilization。

## 5. 出图与统计

```bash
python "$pipeline_skill/scripts/render_pipeline_trace.py" \
  --trace "$target_trace" --output "$trace_run/visualization" \
  --title "$trace_title" --time-unit "$trace_time_unit" \
  --source Simulation --tool npusim --tool-version "$trace_tool_version" \
  --soc "$trace_soc" --model "$trace_model" --case "$trace_case" --kernel "$trace_kernel" \
  --recorded-cores "$trace_recorded_cores" --reported-cores "$trace_reported_cores" \
  --scope "$trace_scope" --output-status "$trace_output_status"
```

上述变量来自本次收据；缺失写 unknown，不根据单核图推断全核。`--scope` 为 full/cropped/unknown，描述 case 是否裁剪，不证明全核报告覆盖；`--output-status` 为 PASS/FAIL/unknown。旧调用默认 Simulation；板上调用必须显式 `--source Board`。PNG/SVG/HTML/index/统计共享同一 provenance；输出 FAIL 显式水印为 diagnostic only。明确 reported IDs 必须为 recorded IDs 子集，all/unknown 不作为具体覆盖证明。缺记录不代表硬件空闲。

脚本需要 matplotlib、plotly，使用当前 Python 环境；如已安装则无需重复安装。输出：原始 trace 的字节副本、单独 normalized trace、PNG、SVG、离线 `timeline.html`、`pipeline_stats.json`、统计 Markdown、`index.html`。输入仅为已核对的单个目标 trace，不自动遍历旧尝试并猜选图。

- 原 JSON 不改写；用 `process_name` 元数据取流水名，去除 ` (scalar_instr)` 等说明后缀；保留 AIC/AIV0/AIV1 身份，兼容副本中再把 `SCALAR_LDST` 映射为旧 parser 的 `SCALARLDST`。
- 排除零时长 X 占位事件再统计；负时长视为异常。正时长 X 指令只按流水聚合，保留指令详情用于 hover，不把 utilization 计数事件当成指令。
- 同一流水的重叠区间先合并再算 busy；span = 最后正时长指令结束 − 第一条正时长指令开始。内部 gap 不包含头尾空闲，SCALAR/SCALAR_LDST 不报气泡。各流水 busy share 可以重叠，不能相加当总利用率或据此直接判定瓶颈。
- 本次 CANN 9.2 `ts/dur` 是 µs，即使 `displayTimeUnit` 写 ns。其它工具版本先核验来源，再传 `--time-unit`，不要把 cycles 标签替换成 µs 而不核对输入。
- 静态图为合并的流水 busy 区间，交互图保留逐指令条；全核 record、本次 core 0 report，均应写清覆盖范围。单核图不能证明所有核负载均衡。

生成后实际查看 PNG，检查标题、时间轴和流水标签可读、非空，并验证 HTML 相对链接可达。正文向用户交付 PNG 预览及交互链接，不只给复杂的原始目录。

## 6. 已验证用例与交付记录

| 算子 / case | 上板中位数 µs | core 0 仿真指令 span µs | 仿真墙钟秒 | 最终结果 |
|---|---:|---:|---:|---|
| attn_epilogue / T=1 out-buffer | 67.6465 | 56.1752 | 126.74 | 28 AIC 重放，输出字节一致 |
| attn_prologue / decode-b1-s1-t1 | 46.2350 | 41.7370 | 77.42 | NZ、tiling、scale 别名恢复后通过 |
| flash_attn_fp8_fullquant / on_tiny，Q=[1,1,128]、KV=1 | 31.7165 | 5.0042 | 27.52 | 输出通过，单独报告主核后出图 |
| flash_mla_with_kvcache / tnd_bbnd_page128_tail，Q=[1,64,576]、KV=193 | 9.2085 | 9.4752 | 30.49 | metadata 预生成，主核输出与 LSE 通过 |

FP8 的上板数值包含 public API 的准备 kernel 序列，图中 5.0042 µs 只对应主 DSL kernel；两者不能直接比较。FP8、MLA 复测 spread 分别约 43.61%、40.55%，只作为筛选数据；Prologue 正式所选样本 spread 约 7.56%。Epilogue 样本范围 66.718–70.776 µs，中位数小于 70，并非全部样本小于 70。

交付记录按本次任务产物组织，所有路径来自当前输出目录；以上数值和历史尝试用于经验说明，不要求用户拥有原始采集目录。建议保留：

- 本次 snapshot/重放 runner、输入/输出、tiling/别名描述、环境身份和实际编译产物；正式性能采集对应的源码/runner/二进制 SHA 单独归档，后续修复不能覆盖历史身份。
- 结果清单和图索引，分别写清上板耗时、仿真指令 span、墙钟秒数与输出验证结果。
- 每次仿真、报告的目录和日志，包括失败、中止及成功尝试；清单引用本次实际路径，不假定固定重试目录名。
- PNG/SVG/离线交互图、原始与 normalized trace、流水统计；按相对路径链接本次产物，便于整体搬迁。

Prologue 原有三次中止、一次别名导致的校验失败，FP8/MLA 各有一次 host profiling 失败；Epilogue 补采另有一次 quota 不一致的中止。汇总要将尝试与最终结果对应，不能只列成功让人误以为其它算子仍失败。
