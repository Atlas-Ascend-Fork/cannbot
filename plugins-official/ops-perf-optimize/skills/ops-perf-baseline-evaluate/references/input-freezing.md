# 输入冻结与集合接入

接收 create-request 生成的已确认 REQUEST（freeze 前 RUN_MANIFEST/WORKFLOW_STATE 为 pending）；先运行依赖预检，再进行源码快照、构建部署或采集，并在 freeze 之前解决 fail 项：

```bash
python3 "$WORKFLOW_SCRIPTS/preflight_dependencies.py" --request <optimization-request.json> \
    [--ttk-root <ops-test-kit>] [--device 0]
```

直调 demo 沿用户指定的现有 C++/比较器验证时，预检显式传 `--validation-runner existing`，不导入或安装 TTK；保持原精度判据。

预检一次性校验通用构建与运行依赖（插件脚本、Python/torch_npu/ml_dtypes、CANN 版本与 opapi 库族、atc、TTK 可导入与多副本漂移、构建工具链、设备可见/可初始化/忙闲、磁盘空间），报告写入 `$OUTPUT_DIR/baseline/preflight-report.json`，不落在运行目录根。存在 **fail 项时禁止 freeze**——修复依赖或重新确认环境后重跑预检；仅 warn 项（如共享设备占用、TTK 多副本漂移）登记原因后可继续。通用依赖问题必须在本步骤暴露；采集后端依赖由报告入口加载后检查，不列入本预检的固定清单。该预检检查通用构建/运行环境；性能测量能力在加载 `ops-profiling-report` 后由其检查，缺能力时不得开始采集或宣称性能就绪。被测实现的源码、构建与加载同源性由 freeze 后的 execution identity 门禁证明，两者不能互相替代。

`code_dir` 可以是仓库内的算子子目录，不要求本层存在 `build.sh`。预检发现上层构建入口仅代表候选路径，需从真实脚本确认单算子 target、工作目录、参数与环境，并将成功命令记录为后续构建依据；不为满足目录检查扩大已确认源码范围。AscendC 后端的预检同时校验 git 可用性与版本（≥2.20）及 `code_dir` 的 git 仓状态：非 git 目录仅 warn，处置方案（原地 `git init` 或终止）已在 request 确认时记录。

无交互运行必须提供已确认的 request JSON，不得自行猜测功能模式、目标或环境。`validate-request` 校验 schema、确认状态、路径和 Python 版本；CANN 选择 `inherit` 时还校验确认时的环境快照。失效时回到用户确认，不静默替换环境。

使用 `$WORKFLOW_SCRIPTS/prepare_case_sets.py freeze --request <optimization-request.json>` 把 request 复制到运行目录，原子生成 `run-manifest.json`（run 级，根目录）和模式对应集合（写入 `baseline/` 阶段文件夹）。manifest 记录 request 路径/SHA、本次源码与用例身份、目标和环境；源码身份在源码树哈希之外附带 git 事实（`head_commit` 与脏文件清单，非 git 目录为 null），供准备期核对基线 commit。standard 使用以下四类集合：

| 集合 | 文件 | 用途 |
|---|---|---|
| 性能全集 | `performance-full-cases.csv` | 最终性能比较 |
| 性能调优子集 | `performance-tuning-cases.csv` | 每轮分析与性能采集，最多 50 条 |
| 功能全集 | `functional-full-cases.csv` 或 `functional-full/` | 最终功能回归 |
| 功能验收子集 | `functional-acceptance-cases.csv` | 预处理与候选快速门禁，最多 40 条 L0 |

脚本记录源路径、数量、SHA、选择算法版本、选中 case 及覆盖标签。全集不超过上限时子集等于全集；超过上限时用稳定的 `coverage-v1` 做覆盖优先选择。性能子集超过 50 条时在 manifest 中标记 `confirmation=pending`，主 Agent把提案展示给用户，确认后调用 `confirm-performance`；禁止默认取前 N、随机抽样或后续重选。

`reuse_performance` 复用性能全集作为功能全集。`existing` 校验并冻结用户库存；库存是 CSV 时脚本直接生成验收子集，目录库存则必须有可枚举 manifest，不能靠遍历顺序猜 case。`generate` 只先冻结性能集合，基线评估代理生成后用 `attach-functional` 一次性接入完整库存和验收子集。

generalization 固定把泛化性能全集复用为功能全集。已有性能用例在 freeze 时直接冻结；没有性能用例时 manifest 将用例准备标为 `pending`，基线评估代理生成性能/功能合一用例后用 `attach-generalization` 接入。已有竞品文件在 freeze 时规范化并校验覆盖；外部采集结果用 `attach-competitor` 接入。竞品性能必须精确覆盖泛化全集 case ID。

库存静态检查结果直接写入 `collections.functional_full.validation`。缺少显式接口、golden 或阈值字段时标 `needs_review`，由主 Agent依据库存框架的可信生成契约补充说明后再验收；不再为此临时编写脚本或生成第二份阶段 JSON。

`confirm-performance`、`attach-functional`、`attach-generalization` 或 `attach-competitor` 合法更新 manifest 后，立即执行 `$WORKFLOW_SCRIPTS/workflow_state.py sync-manifest`，使恢复身份与报告同步；其他未声明的 manifest 变化仍按 stale input 处理。

输入冻结后调用：

```bash
python3 "$WORKFLOW_SCRIPTS/workflow_state.py" start \
  --state "$OUTPUT_DIR/workflow-state.json" \
  --manifest "$OUTPUT_DIR/run-manifest.json"
```
