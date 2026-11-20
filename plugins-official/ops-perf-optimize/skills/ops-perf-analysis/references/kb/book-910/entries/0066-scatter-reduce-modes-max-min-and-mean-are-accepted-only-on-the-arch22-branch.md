```
ID:        0066-scatter-reduce-modes-max-min-and-mean-are-accepted-only-on-the-arch22-branch
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/scatter/scatter_design.md:153 — "注意 **CANN 内置在 950 上只支持 `none/add/mul`**（`REGBASE_DTYPE_SUPPORT_LIST`，host 校验信息明写 `reduction must be in [none, add, mul]`），`max/min/mean` 仅 arch22（910B/910_93）分支接受"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a CANN built-in scatter with `reduction = max`, `min` or `mean` is rejected by host validation on a named DAV_2201 board.
```

# 0066 · Scatter reduce modes max, min and mean are accepted only on the arch22 branch

## 1 · Claim
Upstream asserts that CANN's built-in scatter on the 950 family supports only `none`, `add` and
`mul`, enforced by a host-side check whose message reads `reduction must be in [none, add, mul]`,
and that `max`, `min` and `mean` are accepted only on the **arch22 branch (910B / 910_93)**.
Upstream asserts that the PyTorch-side `scatter_reduce_` has no NPU binding at all in op-plugin and
falls back to CPU for the whole operator. Not established here.

## 2 · The wrong branch this removes
This is a capability the 910 family has and the newer family does not — the same direction as 0010
(4:2 sparsity, present on DAV_2201 and removed on DAV_3510) and the opposite of the direction an
agent expects. Two branches follow.

**Forward:** an agent building a scatter-reduce operator on 910 uses the built-in `max` path, and
the code has no future on 950. That is worth knowing at design time, not at port time — and it is
invisible in the source, because the restriction lives in a host validation list rather than in the
kernel.

**Backward, and the one that wastes more time:** an agent reading upstream's scatter optimisation
material for a 910 target. That document is marked `DAV_3510` in the skill's 適用架構 column and
opens (`:12`) with "适用：**DAV_3510（A5 / Ascend950）**。SIMT（`__simt_vf__` / `asc_vf_call` /
`asc_atomic_*`）是该架构专有能力，**910B 不适用**" — so its six SIMT paths, its measured thresholds
and its throughput figures are all 950-only. This single line at `:153` is the **only** 910-relevant
content in the whole scatter guide, and an agent that mines the document for 910 will otherwise come
away with nothing usable and possibly with 950 thresholds it believes are portable.

The third thing the line supplies, and the most actionable: the **baseline** question. Upstream's
closing remark — "自研实现不受这些限制，但对比基线时要知道对面跑在哪" — says a custom kernel is not
bound by any of this, but a benchmark against "the built-in" is benchmarking against a different
implementation on each family, and against **CPU** if the comparison goes through PyTorch's
`scatter_reduce_`. A speed-up measured against a CPU fallback is not a speed-up against the NPU.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/scatter/scatter_design.md:151-155`, verbatim in
full:

"- **reduce**：本实现支持 `none/add/multiply/amin/amax`。注意 **CANN 内置在 950 上只支持
`none/add/mul`**（`REGBASE_DTYPE_SUPPORT_LIST`，host 校验信息明写 `reduction must be in [none, add,
mul]`），`max/min/mean` 仅 arch22（910B/910_93）分支接受；torch 侧 `scatter_reduce_` 在 op-plugin 中
**完全没有 NPU 绑定**，会整算子回落 CPU。自研实现不受这些限制，但对比基线时要知道对面跑在哪。"

The document's own scope, `:12`: "> 适用：**DAV_3510（A5 / Ascend950）**。SIMT（`__simt_vf__` /
`asc_vf_call` / `asc_atomic_*`）是该架构专有能力，910B 不适用。" — and the skill index,
`ops/ascendc-performance-best-practices/SKILL.md:39`, marks the Scatter family 適用架構 `DAV_3510`.

So a **DAV_3510-marked document in a DAV_3510-marked family** carries one sentence naming arch22
(= DAV_2201 = 910B / 910_93 per 0001) as the branch where three reduce modes are accepted. Under
this book's routing rule the *document* is not ours; this *sentence* names our family explicitly and
is harvested on that basis. The rest of the file is deliberately not harvested — see §7 and the
final harvest report.

Note the vocabulary: "arch22" is the archXX form defined at `ops/npu-arch/SKILL.md:15` ("取 DAV 编号
前两位"), and `npu-arch/references/npu-arch-guide.md:40` maps it explicitly — "| **arch22** |
DAV_2201 | Ascend910B 系列、Ascend910_93 |". This is the one place in this book's harvest where the
`archXX` spelling carries a claim, and unlike "220x" (0014 §3, Q-910-12) it *is* defined upstream.

Note also the naming inconsistency inside the quoted sentence: the built-in list is written `mul`
and this implementation's list is written `multiply`, with `amin/amax` against `max/min`. Whether
these are the same modes under different spellings is not stated.

## 4 · Procedure
Proposed, runnable later; not run. Most of this is host-side and needs no kernel.

1. Host-validation arm, and the one that matches the claim: call the CANN built-in scatter with
   `reduction` set to each of `none`, `add`, `mul`, `max`, `min`, `mean` on a named DAV_2201 part,
   and record which are accepted and the exact rejection message for those that are not. Name the
   die and check occupancy even though the check is host-side, since a rejected call may still
   initialise the device.
2. Symbol arm, read-only: `grep -Rn "REGBASE_DTYPE_SUPPORT_LIST\|reduction must be in" \
   "$ASCEND_HOME_PATH"` and record the list contents and the guard around it. This is where the
   arch branch would be visible and is an independent origin from this repo.
3. Correctness arm, for accepted modes: compare against a host reference. Acceptance by a validator
   is not correctness, and the two are separate verdicts.
4. Baseline arm, which tests §2's third point: time PyTorch's `scatter_reduce_` on the same input
   and record whether execution lands on NPU or CPU (device placement of the output, or a profiler
   trace showing no kernel launch). Report it explicitly, so any future speed-up claim against this
   baseline carries its own disclosure.
5. A DAV_3510 control would complete the claim, and if no such part is available the arch-branch
   half is not established — record that rather than inferring it.

## 5 · Checker — acceptance declared before the run
`accepted_modes(2201)`: PASS iff it includes `max`, `min` and `mean` in addition to `none`, `add`,
`mul`. Red input: a rejection message on 2201 naming the three-mode list, which would overturn §1.
`accepted_modes(3510)`: PASS iff it excludes the three. Without this arm the *branch* claim is
untested and only the 910 half is established — declared now so a 910-only run is not reported as
confirming an arch difference.
`baseline_device`: recorded in all cases as `npu` or `cpu`, never omitted. This is the verdict most
likely to be dropped as uninteresting and is the one that decides whether any comparison against
this baseline means anything.
The positive fixture for arm 1: submit a deliberately invalid `reduction` string (`"banana"`) and
confirm the validator rejects it with a message. A validator that accepts everything is not
validating, and its acceptance of `max` would then be worthless evidence.
Exit code is not the verdict; the host check's rejection path may raise rather than exit.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; "arch22 (910B/910_93)" is an architecture and two chip families,
not a board. This entry does not establish that the three modes are *correct* on DAV_2201, only that
upstream says the branch accepts them — acceptance by a host validator and numerical correctness are
different claims and §4 separates them. It does not establish whether `multiply`/`mul` and
`amin`/`amax`/`max`/`min` denote the same operations (§3). It does not establish anything else from
the scatter guide, which is DAV_3510-scoped and deliberately not harvested: its six SIMT paths,
threshold tables and throughput figures (12602↔3767 µs, 1565→89 µs, 4.81×, ~600 GB/s) are measured
on Ascend950PR and belong to the other book. It does not establish the op-plugin binding claim,
which is about PyTorch integration rather than about the machine and may change with any release.
