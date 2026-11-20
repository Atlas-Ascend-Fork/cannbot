# 统一性能采集协议

性能证据统一由 `ops-profiling-report` 产出。调用方提供目标、身份、输入、环境与测量目标，报告入口选择工具和解释原始数据。计划与采集接口见 [性能证据](profile-evidence.md)。

交付耗时为一次目标调用中 1 个或 n 个目标 kernel 的设备 duration 之和，不含 host、kernel 间隙、同步/标记或初始化等非目标任务；无需程序计时。每版分别描述目标组成，保留重复同名 launch，数量从组成推导。工具耗时另计：从启动工具到取得所需可用数据，含必要解析/导出。

建议的默认口径：

- 单 kernel 测量尽可能预热并清 L2。目前 msopprof 的最小计时默认是 `--replay-mode=kernel --warm-up=3 --aic-metrics=BasicInfo --launch-count=1`。工具参数可按任务选择；记录实际条件，清理请求不等于成功证据。
- 多 kernel 目前建议 msprof 最小采集，无额外预热、自然缓存状态，不要求清 L2或增加 runner/标记。基础观测后可用适合的 kernel 级工具深入诊断。
- 同一正式比较保持选定工具绑定和计时/缓存口径一致。任一方多 kernel 时建议双方用 msprof，包括候选融合成单 kernel 的情况；组成变化不自动切换测量口径。精采诊断可使用不同工具，分别解释。

比较前冻结计时边界和统计单位，明确目标覆盖。MC²/多 rank 等无法由当前适配器确认完整覆盖的范围保持 unsupported/pending。

MC² 的 TilingData 打印证据（baseM/baseN/baseK/usedCoreNum）及 tileCnt=1 隔离测试证据（T_comm/T_compute/R 值）登记进采集 manifest；缺失时退回采集阶段补采，由原诊断角色在专用副本完成。

采集前核对源码、加载二进制、case、Device、CANN、频率、缓存及调用边界。原实现由 `$WORKFLOW_SCRIPTS/validate_execution_identity.py` 验证构建/加载链，候选和集成沿用阶段门禁。身份与覆盖完全相同时复用已有证据。

每版首次按原 comparator 验证精度；同源码、二进制和输入的后续性能运行使用 `--dry-run` 或等价纯性能路径并复用精度收据。

## 探索与确认

探索在代表 case 通过原 golden 冒烟后短测，标记 `screening_only`；拟保留版本完成冻结功能子集，序列测试按改动风险选择。

默认 `median_v1` 按预定样本的中位数比较，保留原件与离散度。显式置信策略见 [性能证据](profile-evidence.md)，分类见 [效果策略](performance-jitter-policy.md)，暂定参考见 [搜索决策](architecture-search.md)。

诊断探针使用独立源码/加载身份并遵守用户规格，插桩与采样流水用于其记录范围内的诊断。采集条件由报告入口统一传给工具子 Skill。

## 执行与恢复

长采集用 `setsid`/`nohup` 后台运行，逐 slot 保存 attempt 与进度，恢复时复用成功样本。已有 archive 优先重解析；无已发布报告且无 export 原件的失败可重试。未完成收据先审计，等待使用阶段通知或长等待。

没有设备绑定的旧采集只用于原始诊断；正式采集及恢复遵循[设备契约](../../ops-profiling-report/references/device-context.md)。
