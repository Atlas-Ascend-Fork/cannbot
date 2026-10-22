# 性能分析任务模板

仅在 `ROLE=analysis` 时读取。每轮只派发一次分析任务，按 `ops-perf-analysis` 的固定过程生成一份可审阅报告和最多三份实施契约。

```text
ROLE: analysis
TASK_KIND: round-analysis
PLUGIN_ROOT: <resolved absolute plugin root>
REQUEST: <optimization-request.json absolute path>
RUN_MANIFEST: <run-manifest.json absolute path>
WORKFLOW_STATE: <workflow-state.json absolute path>
TUNING_MODE: <standard|generalization>
TARGET_SOCS: <exact list from RUN_MANIFEST>
ROUND: <N>
CODE_DIR: <current baseline absolute path>
KB_ROOT: <cannbot-knowledge knowledge root for analysis/implementation, or absent>
INPUT_ARTIFACTS:
  <standard: performance-tuning-cases.csv absolute path>
  <generalization: roundN/generalization-tuning-cases.csv, competitor-performance.csv and current ratio-analysis.json absolute paths>
  <current baseline profiling and validation evidence absolute paths, or collection pending>
  <performance-targets.json and 性能目标.md absolute paths>
  <previous selection absolute path, or absent>
  <source-compatibility.md absolute path>
  <extraction-manifest.json absolute path>
OUTPUT_ARTIFACTS:
  <roundN/analysis.md absolute path>
  <roundN/implementation-contract-<scheme_id>.json absolute paths>
  <roundN/source-isolation-<scheme_id>.json absolute paths>
ACCEPTANCE:
  <profiling and artifact identities valid; every frozen tuning case appears exactly once; each case reports MBU/MFU/cost_bound/ceiling_us/headroom/verdict via ops-profiling compute_efficiency (cost model registered or --flops/--bytes; peaks per TARGET_SOCS, not defaults); fixed analysis process completed; proposed schemes respect the verdict (no non-quant reshuffle candidates padded under NEAR-BANDWIDTH-CEILING / NEAR-COMPUTE-CEILING); each case ALSO reports the operator's intrinsic-minimum-cost roofline (weights crossed HBM once + necessary IO + minimal FLOP, excluding current-impl intermediate round-trips and precision-compensation FLOP) alongside the current-impl roofline; when measured > ceiling_intrinsic*1.5 or behind REFERENCE_PERF, the report MUST include >=1 structural/architecture-level direction (fuse-away intermediates / data layout / precision scheme / internal format conversion; public contract & invocation unchanged) as a candidate or an evidence-based infeasibility argument (hard gate under OPTIMIZATION_INTENT=pursue_optimal, else record direction + estimated gain for user decision); zero schemes require explicit convergence_eligible yes/no, evidence for each infeasible direction and bounded next evidence when no; every strategy maps bidirectionally to non-empty required features; target SoCs, public contract, non-target SoCs and uninvolved templates preserved; copy/route plan and complete baseline-bound source isolation scope ready for main-agent review and SHA freeze>
CONDITIONAL_SKILLS:
  <skills required by confirmed operator routes, or absent>
```

输入中的 standard/generalization 两行是互斥分支，只保留与 manifest 一致的一行。先复用或采集一次当前基线，再只读分析；分析不得重采性能、重选 case 或修改源码。

MC²/多 rank 和各特殊算子族的路由按阶段 Skill 与共享验证规则执行，不得降级为通用 application 分析。
