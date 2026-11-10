# 构建与版本核对

## Tensor API 路线附加契约

采用 Tensor API 路线时:

1. 适用前提：目标芯片须在 Ascend 950PR / 950DT（dav-3510）支持范围内；芯片不在该范围时不应选择该路线，此判定在路线选择阶段完成。
2. bisheng 参数包含 --npu-arch=dav-3510 和 -xasc;direct launch kernel 使用 .cpp。
3. CMake >=3.31 设置 CMAKE_LINK_DEPENDS_USE_LINKER=FALSE。
4. 本地无 NPU / torch_npu 时使用 sim 全量编译与 DEMO_ONLY npu 编译。
5. 详细事实源和排障方法见 ascendc-tensor-api-best-practice Skill。

## 构建输入

记录 `source_dir`、cann-bench commit、Python 环境、CANN 路径和目标 SoC。环境信息来自本轮记录，不重复全面探测。构建在 `$WORK_DIR/<节点ID>-构建工程/` 的源码快照中执行，包含本次未提交代码，排除 `.cannbot/`、本轮工作目录、旧构建目录和二进制；记录与交付源码的对应哈希。算子计算、注册、打包代码、编译配置或工具链变化后更新快照并重建；仅测试用例变化不强制重建候选 wheel，但须记录与当前源码的对应关系。纯许可注释变更须核对完整差异、保留旧构建输入哈希及与当前源码的映射，不将旧 wheel 声称为新源码重新构建。

官方脚本接受 `--soc=ascend910b`、`--soc=ascend910_93`、`--soc=ascend950`；前两者映射 `dav-2201`，950 映射 `dav-3510`。该值是编译平台名，不是性能 metadata 的硬件标签。根 `build.sh` 无参数时会自动检测；若检测无法确定平台，应先修正明确的环境/启动配置，保证评测器执行的 `bash build.sh` 也能复现，不能只验证一个外部手工命令。

## 构建和导入

在已选定的隔离 Python 环境中执行，以下 `build_dir` 为本轮快照绝对路径，`soc` 为已确认编译平台：

```bash
cd "$build_dir"
bash build.sh --soc="$soc"
python3 -m pip install dist/cann_bench*.whl --force-reinstall --no-deps
```

保留退出码和原始日志；wheel 应唯一且对应当前架构。示例 `build.sh --install` 也可安装，但须保证它调用的 pip 与评测 Python 是同一环境。不要在不同任务中并发重装同一个 `cann_bench` 包。

从工程目录之外的新进程检查 `cann_bench.__file__`、`cann_bench._C.__file__`、目标 callable 与 schema，并记录实际加载文件哈希；不要让 `PYTHONPATH` 中旧工程或已安装 golden wheel 抢占导入。golden 自验证包与候选包同名，不能混用。Python 检查脚本使用 logging 输出。

评测器发现预构建 wheel 时可能跳过编译；因此必须保存所用 wheel 的真实编译证据和源码→wheel→加载库的关联；有效复用时引用原构建轮次，不虚构本次编译。仅见到一个 dist 文件不代表它来自当前代码。不要使用 `--skip-install` 掩盖 wheel 更新遗漏。

## 依赖与常见故障

- 软件版本以当前 cann-bench 的 `pyproject.toml`、`uv.lock`、`requirements.txt` 和所选示例为依据；torch/torch_npu 必须匹配，不能单独升级 torch 破坏环境。
- 保留示例 CMake 的 `CMAKE_LINK_DEPENDS_USE_LINKER FALSE`，避免较新 CMake 给 bisheng linker 传入不支持的参数。
- 缺失 symbol、导入错误先核对目标架构、CANN 库路径、Python 环境和实际加载的 `_C`，不要把候选切换成 CPU/Torch 实现“修复”。
- cann-bench 的 `cann_bench_utils` 是独立的评测辅助扩展，不能把它当作候选 `cann_bench` 或删除它；缺失时按其官方构建入口在准备阶段处理。
- 官方评测会写编译日志并安装 wheel；使用快照和独立环境，避免污染交付源码或其它任务。构建失败直接保存原始错误，不临时挪走其它算子掩盖整批失败。

构建记录包含命令、工作目录、环境来源、退出码、源码/测试清单及哈希、wheel 与实际加载库路径及哈希。功能结果另由真实设备评测提供，`test.sh` 的示例 pytest 不是完整验收。

## 核对依据

已核对 cann-bench `08d519c503843bce5fd4672ffa2259abeb22fb00`；运行时记录实际 checkout 版本，版本变化时核对相关接口。

- [examples/direct_launch_example/build.sh](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/direct_launch_example/build.sh)
- [examples/direct_launch_example/setup.py](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/examples/direct_launch_example/setup.py)
- [src/kernel_eval/data/package_manager.py](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/src/kernel_eval/data/package_manager.py)
- [docs/spec/submission_spec.md](https://gitcode.com/cann/cann-bench/blob/08d519c503843bce5fd4672ffa2259abeb22fb00/docs/spec/submission_spec.md)
