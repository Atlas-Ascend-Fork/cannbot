# 统一性能采集协议

一般算子显式使用 `profiler=msprof`、`aic_metrics=PipeUtilization` 和一个持久 application 会话覆盖整个调优子集。每例连续执行 10 组 `warmup → target`；每次 target 的全部 kernel `total_us` 先求和，再取 10 组中位数。`validation.json` 使用 schema v3，expected/parsed/mapped relevant launches 必须相等，warmup 不计时。

采集前记录源码、加载二进制、case、Device、CANN、频率和 warmup 身份。源码与二进制 SHA 并列记录不构成血缘证明：被测源码、本次构建产物和实际加载产物必须形成同源链。原实现基线使用 `$WORKFLOW_SCRIPTS/validate_execution_identity.py`；候选和回集成实现使用各阶段的构建/加载身份门禁。

现成 ops warmup 先实际 probe（通常 ArgMax；ArgMax 家族用 Max），probe 失败才构建后备 warmup；两侧身份必须一致。身份与覆盖完全相同时复用已有证据。

MC²/多 rank 必须加载 `ascendc-mc2-best-practice`，完全遵循其 `msprof op`、预热、取值、多 rank 聚合和归档协议，不套 application 的 10 组协议。MC² 基线采集还须一并产出 TilingData 打印证据（baseM/baseN/baseK/usedCoreNum）和 tileCnt=1 隔离测试证据（T_comm/T_compute/R 值），并登记进采集 manifest；分析阶段只消费已登记证据，缺失时退回采集阶段补采（由同一诊断代理在专用探针副本完成，原基线不变）。

各阶段都先请求主 Agent 授予设备排他采集时段；同一设备不并发测性能。基线与候选必须使用同一协议；精度与序列门禁未通过的候选不得采集可比较性能。修改源码的诊断探针使用独立源码和加载身份；上板前按实际采集路径核对缓冲区偏移/容量、预期记录覆盖、溢出和解析边界。诊断结果只有在身份、覆盖与目标计算/调度条件均成立时才可用于因果判断。无效证据先重解析或修复采集路径，必要时再补采，不据此否定方案；插桩和仿真周期不参与正式性能比较。

## 长采集执行纪律

超过单命令可靠时长的采集（多 case 全集、20 slot 确认、A/B 配对轮）由驱动脚本以 `setsid`/`nohup` 脱离会话进程组后台执行，逐 case/slot 写进度日志与独立证据目录；脚本必须跳过已存在的 case/slot 证据目录，中断恢复只补缺失部分，不重采已完成样本、不替换成功样本；外部终止产生的失败 attempt 记录后保留其目录，重采走新编号。禁止把整段采集放在代理前台单命令内执行。

## 事前配对确认与证据复用

效果判定版本、计划和proof见 [performance-jitter-policy.md](performance-jitter-policy.md)。新请求默认confidence；单次canonical10是初筛，强变化case可按已注册方法由两侧各一次原canonical10样本进行独立median-bootstrap确认，无需重复轮；小变化待确认case可在结果前登记固定轮数、统计方法、seed/draws、AB/BA顺序后采一次完整对照。每版每轮仍10样本，warmup/preparation/prime只计完整launch拓扑而不计target median；不得合并成任意100样本协议。该计划是一次新证据采集，不是对已有同身份收据重采择优。不得看到结果后补轮、删样本或选择会话；原始精度/10%spread/频率/身份/expected=parsed=mapped全部保留。证据不足时待确认，不宣称无收益或终验无回退。
