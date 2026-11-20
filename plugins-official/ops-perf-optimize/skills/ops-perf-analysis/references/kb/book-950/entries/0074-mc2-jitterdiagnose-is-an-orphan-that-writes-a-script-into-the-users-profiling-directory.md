```
ID:        0074-mc2-jitterdiagnose-is-an-orphan-that-writes-a-script-into-the-users-profiling-directory
LABEL:     boundary
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/MC2_JitterDiagnose.md:51 — "将分析脚本写入 profiling 目录下的 `_jitter_analysis.py`，然后执行"
           ops/ascendc-perf-optimize/references/comm-compute/MC2_JitterDiagnose.md:101-103 — "pip install --user -i https://pypi.tuna.tsinghua.edu.cn/simple pandas matplotlib openpyxl / python3 <script_path>"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an inbound reference to this file from any routing artifact in the upstream tree — the
           orphan finding would then be wrong, and the file would be a reachable part of the skill
           whose side effects are intentional rather than stranded.
```

# 0074 · MC2_JitterDiagnose is an orphan that writes a script into the user's profiling directory

## 1 · Claim
Upstream asserts, in a file shipped inside the `comm-compute` reference directory, a performance-jitter
analysis over msprof `op_summary` data — a time dimension (one card across executions) and a space
dimension (cards within one round), with a CV-based severity grading. The file is not a reference page
but a self-contained tool specification: it carries its own frontmatter with `description`,
`allowed-tools: Read, Write, Edit, Bash, Glob, Grep` and `argument-hint`, it instructs the agent to
write a generated Python script named `_jitter_analysis.py` into the user's profiling directory and
execute it, and it instructs a `pip install --user` from an external mirror. No file in the skill
references it. Its analytical content — a time-dimension and space-dimension jitter analysis over
`op_summary` CSV columns, with a CV-based severity grading — appears nowhere else in the skill. Not
established here; nothing was executed, and nothing in this book runs it.

## 2 · The wrong branch this removes
Two, in opposite directions, and the entry exists to keep both visible.

The first is executing it. A reference directory is a place an agent loads for knowledge, and this
file's frontmatter makes it look like a command the agent is entitled to run. Doing so writes a file
into a directory the user owns, installs packages from a third-party mirror into the user's
environment, and does both as a side effect of what the agent believed was reading documentation. A
replacement skill must not ship a reference file that can do this — no tool frontmatter, no writes
into user directories, no installs.

The second is deleting the content with the file. The jitter question is real and is not covered
anywhere else in the MC² chain: the capture protocol (0057) reduces each rank to the mean of five
iterations and then takes the maximum across ranks, which is a point estimate of a distribution whose
spread it never reports. An operator whose CV is 8% and one whose CV is 1% can produce the same
reported number, and the balancing search resolves candidates 5-10 μs apart (0069) — so the spread is
not a curiosity, it is the precision of every comparison the chain makes. What should survive is the
question and the analysis shape, expressed as a procedure over data the harness already has, with no
side effects.

## 3 · Ground / Source
`MC2_JitterDiagnose.md:1-5`, the frontmatter, which is what distinguishes this file from every other
reference page in the skill:

> ---
> description: "分析单卡或多卡中同一算子执行的性能抖动（含 aic/aiv/mte2/mte3），生成含图表的 XLSX 报告。"
> allowed-tools: Read, Write, Edit, Bash, Glob, Grep
> argument-hint: "<profiling_dir> [csv_filename]"
> ---

Side effects: `:51` (quoted in SOURCE) writes `_jitter_analysis.py` into the profiling directory;
`:101-103` (quoted in SOURCE) pip-installs pandas, matplotlib and openpyxl from an external mirror and
runs the script; `:98` writes `jitter_analysis_YYYYMMDD_HHMMSS.xlsx` beside the CSV. `:28` instructs
the agent to ask the user for a directory if none is given — so it expects to be invoked
interactively, as a command.

Analytical content worth preserving, and unavailable elsewhere in the skill: the two analysis axes at
`:10` — 时间维度（同一张卡不同执行次数）and 空间维度（不同卡同一轮次）; the row-correspondence
convention at `:16-18` (Device 0's row *n* and Device 1's row *n* are the same round); the warm-up
detection rule at `:57` — 若首次执行 aicore_time > 后续均值的 3 倍，标记为 warm-up 并从图表中剔除,
which is a *data-driven* warm-up test where the capture protocol of 0057 uses a fixed count of five;
the statistics at `:88` — Count, Min, Max, Mean, Std, CV(%), Max-Min Range per device per metric; and
the severity grading at `:112` — CV < 2% 为「低」，2%~5% 为「中」，> 5% 为「高」. The metric set at
`:34` names the columns the analysis reads: `Task Duration(us)`, `aicore_time`, `aic_mte2_time`,
`aic_mte3_time`, `aiv_time`, `aiv_mte2_time`, `aiv_mte3_time` — the same `op_summary` file the MC²
capture protocol already produces.

Orphan status: no file in `ascendc-perf-optimize` links to it, and the routing table at
`comm-compute/index.md:184-193` lists five analysis documents, not this one. Recorded as
C-950core-017. The replacement's obligation is stated in the delivered skill's contract
as defect F6.

## 4 · Procedure
Two arms, neither of which runs the file. Arm 1 is artifact-level and needs no device.
```bash
UP=upstream/skills-dev-main/ops/ascendc-perf-optimize
sha256sum $UP/references/comm-compute/MC2_JitterDiagnose.md
  # a3a02b364756b4ea84aa12624ede4cd98326050292bbd2eafb34b63b56d59466
# inbound references anywhere in the upstream tree:
grep -rn "MC2_JitterDiagnose\|JitterDiagnose\|jitter" upstream/skills-dev-main --include=*.md \
  --include=*.json --include=*.yaml | grep -v "MC2_JitterDiagnose.md:"
# side-effect surface, enumerated rather than executed:
grep -n "allowed-tools\|pip install\|写入\|Write" $UP/references/comm-compute/MC2_JitterDiagnose.md
```
Arm 2 — the jitter question, without the file (later phase, needs cards on all ranks): from the
ten-iteration multi-rank capture the protocol of 0057 already performs, retain all rows rather than
only the last five, and compute per rank and per metric: Count, Min, Max, Mean, Std, CV, range; then
the cross-rank spread of the per-rank means for the same round index. No script is written into the
user's tree and no package is installed; the computation runs in the analysis workspace on a copy of
the CSV.

## 5 · Checker — acceptance declared before the run
Arm 1 verdict variables `inbound_refs` (count, expected 0) and `side_effects` (the enumerated list of
write and install instructions, expected non-empty). Both are reported; the F6 obligation is
discharged only when a replacement contains no file with a non-empty `side_effects` list.

Arm 2 verdict variables `cv(rank, metric)` and `cross_rank_spread(round)`. The declared acceptance
threshold for treating a candidate comparison as meaningful: the measured difference between two
candidates must exceed `max(cv) × T` over the ranks — i.e. jitter bounds the resolution of every
comparison in 0058, 0068, 0069 and 0073, and a comparison inside that bound is reported as
`indistinguishable` rather than decided.

Exit code is not the verdict in either arm. In arm 1, `grep` exiting 1 on no inbound match is the
confirming observation, and the count is printed explicitly.

Red input, arm 1: `grep` for a file that *is* referenced — for example `local_matmul.md`, which the
routing table lists. It must return a non-zero count. Without that control, "zero inbound references"
could mean the search pattern was wrong.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured, and nothing executed — this book does not run the file, so it establishes nothing
about whether the analysis it describes is correct, only what the file instructs and that nothing
references it. The CV bands (2%, 5%) have no derivation, no board and no case identity, and the
3× warm-up rule is asserted. No board token is established. It does not establish that jitter is
material for any operator; arm 2 exists to find out, and it has not been run. The orphan status is
recorded at one pinned blob and can change upstream at any time.
