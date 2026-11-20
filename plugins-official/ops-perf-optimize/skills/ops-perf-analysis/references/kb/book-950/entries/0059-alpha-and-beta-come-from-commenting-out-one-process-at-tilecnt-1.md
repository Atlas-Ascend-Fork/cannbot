```
ID:        0059-alpha-and-beta-come-from-commenting-out-one-process-at-tilecnt-1
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/comm-compute/bound_diagnosis.md:33-38 — "Step 0 — 复制源码到临时目录（如 {code_dir}_diag/） Step 1 — 注释计算 process，仅保留通信 → 测得纯通信耗时 T_comm Step 2 — 注释通信 process，仅保留计算 → 测得纯计算耗时 T_compute Step 3 — 计算 R = T_compute / T_comm"
           ops/ascendc-perf-optimize/references/comm-compute/index.md:182 — "MC-C3 | **隔离测试须在源码副本中进行**，不修改用户原目录。测试产物保留供分析，代码副本测完丢弃"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured case on a named 950 board where the communication-only and compute-only builds
           sum to materially less than the full `tileCnt=1` build — the two phases would then already
           interact at tileCnt=1, and neither isolated time is the phase's cost inside the operator.
```

# 0059 · α and β come from commenting out one process at tileCnt=1

## 1 · Claim
Upstream asserts an isolation procedure for obtaining the two phase costs an MC² analysis needs:
copy the source to a temporary directory; at `tileCnt=1`, comment out the compute process and
measure pure communication time T_comm; comment out the communication process and measure pure
compute time T_compute; compute R = T_compute / T_comm; and derive per-row costs α = T_comm / M and
β = T_compute / M. Upstream asserts the isolation must happen in a source copy, leaving the user's
directory untouched, with the profiling products kept and the code copy discarded. Not established
here; nothing was built or measured.

## 2 · The wrong branch this removes
Without an isolation test the two phase costs have to be inferred from the fused profile, where they
overlap — and the MTE2 ratio, the obvious proxy for communication cost, is polluted by communication
wait in exactly this operator class (0060). So an agent reasoning from the fused profile alone gets
a ratio that mixes both phases with a synchronisation artefact, and every downstream number (R, ρ,
the search range, the theoretical time model) inherits it. The isolation test is crude — comment out
half the operator — and it is the only measurement in the chain that separates the two phases at all.

The wrong branch inside the procedure is where the edit happens. Commenting out a process in the
user's tree leaves a kernel that computes nothing or communicates nothing; if the copy discipline
slips, that state can be committed, shipped, or measured later as if it were the real operator. The
rule is stated as a hard constraint (MC-C3) for that reason, and the products — the profiling data —
are what is kept, not the code.

## 3 · Ground / Source
`bound_diagnosis.md:23-46`. The 隔离测试法 preamble states the condition — 在 **tileCnt=1**（无流水线）
的条件下，通过注释算子中的通信或计算 process 代码，直接隔离测试纯通信耗时和纯计算耗时 — followed by
the copy warning (`:29`) and the capture warning (`:31`), which routes the measurement through the
multi-rank protocol of 0057: all ranks comment out the same process, at least ten iterations, first
five as warm-up, mean of the last five per rank, maximum across ranks as T_comm or T_compute.

The four steps are quoted in SOURCE. α and β follow at `:42-46`.

MC-C3 at `comm-compute/index.md:182` is quoted in SOURCE; `SKILL.md:68` states the same requirement
from the workflow side and makes it a gate: 在 tileCnt=1 下分别注释通信/计算 process，实测 T_comm 和
T_compute，计算 R 值判定 Bound 类型 — with 缺失任何一项须返回数据采集阶段补采 (0061).

What upstream does not say, and what this entry records as the procedure's own assumption: that
removing one phase does not change the other's cost. Both phases contend for the same memory system
and the same synchronisation primitives, and a compute-only build has no `BarrierAll` traffic while
a communication-only build has no cube occupancy. So T_comm + T_compute need not equal the serial
`tileCnt=1` total — and the masking-ratio ceiling of 0055 assumes it does. The procedure below adds
that check, which upstream's does not contain.

## 4 · Procedure
Later phase, needs one card per rank. Capture per 0057; board token per rank from the driver readout.
1. Copy the operator source to a scratch directory. Record the `sha256sum` of every file changed and
   the diff of each isolation edit, so what was removed is recoverable from the record rather than
   from memory. The user's tree is never edited; the procedure refuses to proceed if the working
   directory is not the copy.
2. Build three configurations at `tileCnt=1`: full, communication-only, compute-only. Record `md5sum`
   of each kernel object.
3. Measure all three per the ten-iteration multi-rank protocol; record per-rank steady means and the
   cross-rank maximum for each.
4. Compute R, α, β. Then compute the closure check: `T_comm + T_compute` against the full
   `tileCnt=1` time.
5. Repeat at three problem sizes, since the closure error may be size-dependent.

## 5 · Checker — acceptance declared before the run
Verdict variables `R`, `alpha`, `beta`, and `closure_error` =
(T_comm + T_compute − T_full) / T_full. Acceptance of the isolation test as a decomposition:
`|closure_error|` within 10% at every problem size. Beyond that, the two isolated times are not the
phases' costs inside the operator, and R is a ratio of two different experiments rather than a
property of the operator — which does not make it useless, but it must then be labelled as such
wherever it is used.

Exit code is not the verdict. All three per-rank tables are published, plus the closure error per
size. A configuration whose kernel object hash matches another configuration's is reported
`isolation_edit_ineffective` — that is the failure where the commented-out process was inside a
branch the compiler kept, and it would otherwise produce two identical measurements and an R of 1.

Red input: the compute-only build measured for communication volume, or equivalently a check that
the communication-only build performs no cube work. Each isolated build must show the *absence* of
the removed phase in its profile (near-zero cube occupancy, or near-zero communication traffic); if
both builds look alike in the profile, the edits did not take effect and no R is admissible.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. No board, no operator, no rank count. The decomposition's validity — whether
either phase's isolated cost equals its cost in the fused operator — is not established, and
upstream does not raise the question. α and β are per-row averages, so they assume cost is linear in
M, which is untested and is the assumption the whole theoretical time model of 0069 rests on. The
procedure says nothing about operators where the two phases cannot be separated by commenting out a
process, for instance where communication is embedded inside the compute loop.
