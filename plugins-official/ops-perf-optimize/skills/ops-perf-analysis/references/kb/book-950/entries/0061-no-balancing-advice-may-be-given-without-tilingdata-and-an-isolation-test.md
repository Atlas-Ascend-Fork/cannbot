```
ID:        0061-no-balancing-advice-may-be-given-without-tilingdata-and-an-isolation-test
LABEL:     boundary
LEVEL:     L0 (launch & host)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/index.md:180-182 — "| MC-C1 | **缺失 TilingData 时不得进行流水配平分析** … | MC-C2 | **流水配平方案必须通过系统搜索确定切分参数**（四条剪枝 + Top-N 候选），禁止仅取 1-2 个经验值（如 longMSize=512）不做搜索就交付 | | MC-C3 | **隔离测试须在源码副本中进行**，不修改用户原目录 |"
           ops/ascendc-perf-optimize/SKILL.md:65 — "若算子为 MC² 通算融合算子（存在 fork 多 rank + CrossCoreFlag 同步），在进入流水配平分析前**必须**完成以下两项数据采集，缺失任何一项须返回数据采集阶段补采，不得在缺少数据的情况下凭经验给出切分方案"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a harness run in which an MC² operator reaches a balancing recommendation with either
           TilingData or the isolation test missing, and the recommendation is then shown by
           measurement to be the best of the candidate set — the gate would then be protecting
           against a failure that does not occur for that operator class.
```

# 0061 · No balancing advice may be given without TilingData and an isolation test

## 1 · Claim
Upstream asserts a hard data gate on MC² operators, stated twice. In the workflow: before entering
pipeline-balancing analysis, two collections are mandatory — TilingData (baseM/baseN/baseK/
usedCoreNum, printed from host code) and an isolation test at `tileCnt=1` yielding T_comm,
T_compute and R — and if either is missing the work returns to the collection stage; giving a split
recommendation from experience without the data is forbidden. In the reference: three hard
constraints, MC-C1 (no TilingData, no balancing analysis), MC-C2 (the split must come from the
systematic search with its four pruning rules and Top-N candidates, not from one or two remembered
values such as longMSize=512), MC-C3 (isolation in a source copy). Not established here; this is a
governance claim about a workflow, and nothing was run.

## 2 · The wrong branch this removes
This gate exists because the wrong branch is so cheap and looks so competent. An MC² operator with a
known shape invites an answer from memory: "use longMSize=512 with tileCnt=4" — a value that appears
in upstream's own R-value table as a typical configuration (0073) and will therefore look sourced.
It costs nothing, it is plausible, and it is unfalsifiable in the conversation. What it skips is the
two measurements that make the recommendation mean anything: without `baseM`/`baseN`/`usedCoreNum`
the core-utilisation pruning cannot be evaluated at all (0068), so the search cannot know whether the
recommended split leaves cores idle; and without R the direction of the search is unknown (0058).

The gate's form is what makes it usable: it names the two artifacts, states where each comes from,
and says what to do when they are absent — return to collection. A gate that said "be sure you have
enough data" would not be a gate.

## 3 · Ground / Source
`SKILL.md:65-68`, the pre-check quoted in SOURCE, with its two items:

> 1. **TilingData 采集**：从 host 代码打印获取 baseM/baseN/baseK/usedCoreNum。若 host 代码未打印，
>    须在源码副本中启用 PrintTilingData 后重新运行。
> 2. **隔离测试**：在 tileCnt=1 下分别注释通信/计算 process，实测 T_comm 和 T_compute，计算 R 值
>    判定 Bound 类型。

`comm-compute/index.md:176-182`, the 硬约束 table, quoted in SOURCE. The reason attached to MC-C1
appears twice: `index.md:145` — 缺少 baseM/baseN/usedCoreNum 将导致核利用率计算失真，搜索算法无法
正确剪枝 — and `pipeline_balancing.md:270` — 不得在无 TilingData 数据的情况下进行搜索——缺少
baseM/baseN 将导致核利用率计算失真，搜索结果不可靠.

Phase mapping, `index.md:147-160`: Step 0 (TilingData) and Step 2 (isolation) belong to the
data-collection phase, Steps 1/3/4/5 to the analysis phase, and 若分析阶段发现 TilingData 或隔离
测试数据缺失，须返回数据采集阶段补采. Per-case recording, `:162-174`: each case records its own
TilingData (long and short block separately), its own isolation result, and its own `aiv_time` and
bound type — 不得仅归组汇总.

Note that the gate is stated in the routing file and in the reference index, and that the
consuming harness is a different artifact again — so whether the gate is *enforced* depends on the
consumer, not on these files. That is the gap the procedure below targets.

## 4 · Procedure
Artifact-and-harness level; no device is needed to test the gate itself, though a card is needed to
produce the data the gate demands.
```bash
UP=upstream/skills-dev-main/ops/ascendc-perf-optimize
sha256sum $UP/SKILL.md $UP/references/comm-compute/index.md
  # 9d964c369d3a2c03e70c5d8fb2787ecf99ebb0fdbbf648f04f1891832a5171e8  SKILL.md
grep -n "MC-C1\|MC-C2\|MC-C3\|必须\|须返回数据采集" $UP/references/comm-compute/index.md
grep -rn "longMSize=512\|longMSize = 512" $UP/references/comm-compute/   # the value MC-C2 names
```
Harness arm (no device): drive the skill three times with an MC² operator — once with both artifacts
supplied, once with TilingData withheld, once with the isolation result withheld — and record, for
each, whether the output contains a split recommendation and whether it contains the
return-to-collection instruction.

## 5 · Checker — acceptance declared before the run
Verdict variable `gate_holds` = for both withheld-artifact runs, the output contains no concrete
split recommendation (no `longMSize` value, no `tileCnt` value) and does contain a
return-to-collection instruction. Second verdict `search_evidenced` = when both artifacts are
supplied, the output contains a candidate list of more than two entries, which is MC-C2's
requirement.

Exit code is not the verdict; the skill exits successfully in all three runs. The verdict is computed
from the emitted text by searching for recommendation-shaped content, and the search patterns are
declared before the runs.

Red input: the both-supplied run. It must produce a recommendation. If no run produces one, the
harness is not reaching the balancing stage at all and the gate has not been shown to be doing
anything — reported as `stage_unreached`, not as a pass.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board, no operator. It does not establish that the gate is enforced anywhere —
these are statements in reference files, and the enforcing artifact is the consuming harness, which
this entry does not examine. It does not establish that TilingData and R are *sufficient*; MC-C2's
search additionally needs the pruning thresholds (0068) and the theoretical time model (0069), whose
own inputs are unverified. It says nothing about non-MC² communication operators, for which no such
gate is stated.
