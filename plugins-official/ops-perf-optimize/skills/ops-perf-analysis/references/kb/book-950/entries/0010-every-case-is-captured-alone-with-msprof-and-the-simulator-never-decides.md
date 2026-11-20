```
ID:        0010-every-case-is-captured-alone-with-msprof-and-the-simulator-never-decides
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/metrics.md:17-18 — "**逐 case 采集**：性能优化工作流对 `{cases_csv}` 中**每个 case** 单独采一次 `aiv_time`，禁止只挑代表性用例 … **最终性能结论以上板 msprof `aiv_time` 前后对比为准**，仿真只作定性初判"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-02-stage-order-rescheduling.md:85 — "仿真平台核数可能与实机不同（本例 32 vs 实机 56，单核工作量差 75%）、DDR 模型也非 HBM，绝对 us 系统性偏悲观"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired capture on a named 950 board showing that the simulator's ranking of a
           candidate set matches the board's ranking across shapes — that would license using
           simulation to decide, contradicting "仿真只作定性初判"; or a sampling study showing a
           representative subset reproduces the full per-case result within its spread, which
           would make the per-case rule unnecessary rather than merely expensive.
```

# 0010 · Every case is captured alone with msprof, and the simulator never decides

## 1 · Claim
Upstream asserts a two-path capture discipline: on hardware, msprof produces
`kernel_details.csv` (per-case `aiv_time` and the ratio columns) and `op_summary.csv`; without
hardware, the CANN Simulator produces an instruction-level chrome-trace. Upstream asserts that
every case in the case set is captured individually — picking representative cases is
forbidden — and that the final performance verdict is always the on-board msprof `aiv_time`
before/after comparison, with simulation admitted only as a qualitative first read. Upstream
asserts further that the simulator's absolute microseconds are systematically pessimistic
because its core count and memory model differ from the machine. Not established here.

## 2 · The wrong branch this removes
Two branches, both cheap and both common. The first: an agent under time pressure profiles
three "representative" shapes and generalises. The shape sweep in 0052 is the counter-example
inside upstream's own library — the same change is neutral at T=64 and T=512, −24.6% at T=4096
and −35.3% at T=10752. A three-case sample containing the small shapes would have reported the
change worthless. The second: an agent with no board runs the simulator, reads absolute
microseconds, and reports a speed-up. On upstream's own example the simulated platform had 32
cores against 56 on the machine, a 75% difference in per-core work, and a DDR rather than HBM
memory model — so the simulated number is not a noisy version of the real one, it is a different
quantity. What the simulator is for is the relative shape of the pipeline: who is busy during
the gaps.

## 3 · Ground / Source
`metrics.md:8-19`. The two-path table names, per scenario, the tool, the skill entry point and
the products:

> | 上板实测 | msprof（逐 case `aiv_time`） | `/ops-profiling` | `kernel_details.csv`（含 aiv_time/各 ratio）、`op_summary.csv` |
> | 无硬件仿真 | CANN Simulator | `/ops-simulator` | 仿真流水 trace（chrome trace json）、指令时间线 |

and the two rules:

> - **逐 case 采集**：性能优化工作流对 `{cases_csv}` 中**每个 case** 单独采一次 `aiv_time`，
>   禁止只挑代表性用例；对齐口径见 `workflows/cannbench-a5-baseline-collection.md`。
> - **仿真 trace** 用于在无板环境看流水形态（空泡、泳道占用）；**最终性能结论以上板 msprof
>   `aiv_time` 前后对比为准**，仿真只作定性初判。

The metric vocabulary table (`metrics.md:24-34`) names, per metric, the file it is read from:
`aiv_time`, `aiv_vec_ratio`, `aiv_mte2_ratio`, `aiv_scalar_ratio` from `kernel_details.csv`;
`aiv_mte3_wait_ratio` from `ResourceConflictRatio.csv`; 重叠因子 from `PipeUtilization.csv`;
lane utilisation and IPC from the simulation trace only.

`nobound-02:8-13` adds that the simulator is not merely the no-board fallback — 有板也要起仿真 —
because msprof ratios are time shares and carry no causality, so "who blocked whom" is only
visible in an instruction-level trace; and `:11-12` gives the commands, noting `cannsim 已更名
npusim，两名字同入口`. `nobound-02:85` gives the pessimism caveat quoted in SOURCE, and its own
rule: 本卡全部判据只依赖「空窗里谁在忙」这类相对占用，收益结论一律回上板 msprof.

One dangling reference, recorded and not repaired: `metrics.md:17` cites
`workflows/cannbench-a5-baseline-collection.md` for the alignment convention, and no such file
exists anywhere under `ops/` in the upstream tree.

## 4 · Procedure
Later phase, needs a card for the board arm. Board token from the driver readout.
1. Device selection: `ASCEND_RT_VISIBLE_DEVICES` must be set explicitly; the procedure refuses
   to pick a die for the operator, refuses to assume the die is idle, and records occupancy
   before and after each capture. A die that changes tenancy mid-sweep invalidates that sweep.
2. Board arm: capture every case of the 0005 case set individually with msprof
   (`--ai-core=on --aic-mode=task-based --aic-metrics=PipeUtilization --task-time=on`), one
   launch per case, five repetitions per case; record median and spread of `aiv_time`.
3. Simulator arm: run the same case set under `npusim record`/`npusim report`, recording the
   simulated total per case and the simulated core count as reported by the tool.
4. Sampling arm: draw three "representative" subsets by the three rules an agent would plausibly
   use (largest shape, median shape, first three in the CSV) and compute, for each, what
   conclusion it would have supported.

## 5 · Checker — acceptance declared before the run
Three verdict variables, all declared now.
`sim_rank_agrees` = Spearman correlation between simulated and measured per-case time, reported
with its confidence interval; the discipline "simulation is qualitative only" is *supported*
when the correlation is high but the absolute ratio is far from 1, and *refuted* if both agree.
`sim_bias` = median(simulated / measured), expected > 1 per the pessimism caveat.
`sampling_error` = the number of subsets whose supported conclusion differs in sign from the
full-set conclusion; the per-case rule is vindicated iff this is > 0.

Exit code is not the verdict. Each variable is printed with the data behind it, including the
cases where simulation and board agreed — retained because they did not bite.

Red input: a case set of a single shape. `sampling_error` is then 0 by construction, and the
checker must report `case_set_degenerate` rather than concluding that sampling is safe.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured, no board, no simulator run. It does not establish that msprof's `aiv_time` is
accurate in an absolute sense — only that upstream treats it as the reference. It does not
establish the simulator's fidelity for any lane or any shape, nor that `npusim` and `cannsim`
are the same entry point on any installed toolkit (upstream asserts it; this book has bound no
toolkit). It says nothing about capture on multiple ranks, which has its own protocol and its
own worst-case rule (0057), and nothing about AIC-side metrics, which this table omits.
