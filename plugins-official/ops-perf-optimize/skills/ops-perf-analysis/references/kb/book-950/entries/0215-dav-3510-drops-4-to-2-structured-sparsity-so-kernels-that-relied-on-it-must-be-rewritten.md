```
ID:        0215-dav-3510-drops-4-to-2-structured-sparsity-so-kernels-that-relied-on-it-must-be-rewritten
LABEL:     boundary
LEVEL:     L5 (compute & numerics)
STRATUM:   corroborated — ops/npu-arch states the removal; the installed CANN 9.0.0-beta.2 ini set
           independently carries `sparsity=0` in every `NpuArch=3510` file. Both trace to vendor
           ini (0204); no compile was attempted to see how a sparse kernel actually fails.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-hardware-params.md:112 — "| 稀疏 | `sparsity` | 0（不再支持 4:2）|"
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:349 — "> 注：DAV_3510 不再支持 4:2 稀疏矩阵计算，
           原依赖该特性提速的 kernel 需要改为稠密或其他支持的稀疏策略。"  # same skill — ONE origin.
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — all 32 `NpuArch=3510` files in
           `aarch64-linux/data/platform_config/` carry `sparsity=0`.
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read:
           grep -h '^sparsity=' $ASCEND_HOME_PATH/aarch64-linux/data/platform_config/Ascend950*.ini | sort -u
OVERTURN:  a 4:2 structured-sparse MMAD that compiles and delivers above-dense throughput on a
           950PR or 950DT part.
```

# 0215 · DAV_3510 drops 4:2 structured sparsity, so kernels that relied on it must be rewritten

## 1 · Claim
Upstream asserts that DAV_3510 no longer supports 4:2 structured sparse matrix computation, that the
ini field `sparsity` is 0 rather than 1, and that kernels which relied on the feature for speedup
must be converted to dense or to another supported strategy. The installed CANN 9.0.0-beta.2
platform-config set carries `sparsity=0` in all 32 of its `NpuArch=3510` files. Not established
here: nothing was compiled, so how the loss manifests — a build error, a silent dense fallback, or
a wrong result — is unknown.

## 2 · The wrong branch this removes
This is a *removal*, and removals are the hardest deltas for an agent to act on, because nothing in
the new material mentions the missing feature. An agent porting a matmul that carried a 4:2 sparse
path does not see a warning; it sees a kernel that already works. If the toolchain silently falls
back to dense, the port succeeds, the results are correct, and the operator is roughly 2× slower
than its predecessor with no defect anywhere to point at. The team then spends its optimisation
budget on the dense path's tiling, which is not where the regression came from.

The second branch is planning rather than porting: a performance model that budgets a sparse
speedup on a 950 target produces a target latency nothing can reach, and every implementation
attempt reads as a failure to optimise.

Which of these happens depends entirely on the failure mode, and that is precisely what neither
origin states. §4 is written to find it, and until it runs, the honest posture is: assume the
fallback is silent, because that is the branch with no detector.

## 3 · Ground / Source
`npu-hardware-params.md:103-114` (§2.5, DAV_3510) carries the field:

> | 稀疏 | `sparsity` | 0（不再支持 4:2）|

and the cross-architecture quick table at `:152` puts the change on the record:

> | 稀疏 4:2 | — | — | 支持 | 支持 | 不支持 |

`npu-arch-guide.md:349`, in the data-format section, states the consequence — this is the sentence
that makes it actionable rather than a table cell:

> > 注：DAV_3510 不再支持 4:2 稀疏矩阵计算，原依赖该特性提速的 kernel 需要改为稠密或其他支持的稀疏
> > 策略。

Both files are `ops/npu-arch/` and are therefore one origin (RULES.md Art. 3). The removal appears in no
other upstream skill: `ascendc-perf-optimize`'s 24 technique cards contain no sparsity card, and the
matmul tiling family names no sparse template. So an agent working from the card library alone would
never learn either that the feature existed or that it is gone.

Second origin — the installed toolkit, read under the phase-1 read-only exception. From
`Ascend950PR_9589.ini`:

```
[AICoreSpec]
bt_size=4096
...
sparsity=0
```

`sparsity=0` holds in all 32 `NpuArch=3510` files, across every core count (4/8/28/32/36) and every
L2 size present. No 3510 ini in this install carries `sparsity=1`.

Note what the field is and is not. `sparsity=0` is a capability bit in a configuration file; it is
not a compiler diagnostic and not a runtime check. Whether anything in the toolchain reads it and
refuses, or whether it is advisory metadata that only the tiling layer consults, is not visible from
the file. That gap is the whole of §4.

Upstream's phrase 其他支持的稀疏策略 ("other supported sparse strategies") is left undefined — no
upstream document in this scope names one. That is recorded here rather than filled in.

## 4 · Procedure
Runnable later on `950PR`; `950DT` needs its own run and BOARD is narrowed at promotion. The claim
is a negative — a capability is absent — so the procedure must attempt the capability, not confirm
its absence by reading.

Arm A — the compile arm, which needs no device and should run first. Write an MMAD invocation using
whatever 4:2 structured-sparse interface the pinned toolkit exposes (locate it by header search
under `$ASCEND_HOME_PATH/include/ascendc/`, recording the search as a file read) and compile it for a
3510 target. Record exactly one of three outcomes: (i) the interface does not exist for this target
— a compile error naming the symbol; (ii) it exists and the build fails with a diagnostic naming
sparsity; (iii) it exists and builds clean. Outcome (iii) is the one that matters and is the reason
this arm is not skippable.

Arm B — the behaviour arm, run only if Arm A reaches outcome (iii). Execute the sparse kernel and a
dense kernel of identical logical shape on the same die in the same session, and compare results
bit-for-bit *and* compare `aic_time`. Bit-identical results with equal timing means a silent dense
fallback — the branch §2 identifies as undetectable — and that is a finding, not a null result.
Different results means the sparse path executed and produced something, which would overturn the
entry.

Arm C — the model arm. Take one matmul whose published sparse speedup is known and record achieved
throughput against the dense baseline at the same shape. A ratio at or below 1.0 is consistent with
the entry; a ratio above 1.0 falsifies it. This arm is a two-point comparison and therefore carries
no attribution on its own — it is retained because it is the arm a performance team will actually
run, and stating its weakness here is cheaper than discovering it later.

Device selection is explicit: the operator names the device index, the probe prints it back with
`compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and no die is substituted for another. Arms B and C must run on the same die in
the same session or their comparisons attribute nothing.

## 5 · Checker — acceptance declared before the run
Verdict variable `sparse_42_unavailable`, and it is deliberately not satisfiable by Arm A alone.

Pass requires: Arm A reaching outcome (i) or (ii); OR Arm A reaching outcome (iii) with Arm B showing
bit-identical output and timing within run variance of the dense arm. That second clause is the
important one — it says a silent fallback still counts as "unavailable", and it names the evidence
that distinguishes a fallback from a working sparse path.

Fail — meaning the entry is overturned — is declared now: Arm B producing output that differs from
dense, or Arm C producing a throughput ratio above 1.0 outside run variance. Neither is reinterpreted
after the fact.

The checker must be able to go red and the input that does it is stated: run Arm B with the *dense*
kernel substituted for the sparse one on both sides. It must then report bit-identical, equal-timed —
and the harness must flag that configuration as a self-test pass, confirming the comparison is live.
If the harness cannot tell that case apart from a real fallback, it is reading only for equality and
every "silent fallback" verdict it issues is unsupported. That is the positive fixture.

Process exit code is not the verdict: in Arm A a compile failure is the *expected* result, and
treating a non-zero exit as failure would invert the whole check.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The ini values in §3 are a
read of installed files under the sanctioned phase-1 read-only exception; a configuration field does
not establish what the compiler or the hardware does with it, and no header search for a sparse MMAD
interface was performed.

## 7 · Scope limits — what this entry does NOT establish
No device was contacted and nothing was compiled. The entry does not establish how the loss
manifests — build error, silent dense fallback, or wrong result — which is the one thing a porting
agent most needs and the reason §4 Arm A exists. It does not establish that any toolchain component
reads the `sparsity` field, nor that a sparse interface still exists in the pinned SDK. It does not
establish what upstream's 其他支持的稀疏策略 refers to; no source in this scope names one, and none is
invented here. It does not quantify what is lost: no upstream document in this scope states the
speedup 4:2 sparsity delivered, so "roughly 2×" in §2 is reasoning from the ratio's name, not
evidence. Nothing transfers to the other book (RULES.md Art. 1) — the 支持 entries in upstream's quick
table belong to other architectures and are carried as quotation only, and this book makes no claim
about whether any 910-family part supports 4:2. The reading is pinned to toolkit `9.0.0-beta.2`,
host directory `aarch64-linux`, one machine; a later toolkit could reintroduce the capability bit.
