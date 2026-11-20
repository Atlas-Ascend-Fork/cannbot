```
ID:        0315-on-dav-3510-two-reads-of-one-bank-group-do-not-conflict-and-that-is-the-one-rule-that-differs
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled.
           No second statement of this rule exists anywhere in the repo, and the installed ini set
           carries bank counts but no port count.
BOARD:     family-claimed(unverified)
           # the source names the part "Atlas 350", a product name the repo's own truth source does
           # not carry (C-950bp-011). No board token is named by the evidence.
SOURCE:    ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md:48-54 —
           "| 冲突类型 | NPU 220x | Atlas 350 | | 读写冲突 | 同一 **bank** | 同一 **bank** | |
           写写冲突 | 同一 **bank group** | 同一 **bank group** | | 读读冲突 | 同一 **bank group** |
           同一 **bank**（两个读操作），或**两个以上**读操作同一 bank group |" · "> Atlas 350 的
           bank group 上有两组读口和写口，因此**两次读操作访问同一 bank group 的不同 bank 时不会
           冲突**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a `ResourceConflictRatio` reading on a named 950 board that goes red for exactly two
           concurrent reads landing in two DIFFERENT banks of one group — the two read ports would
           then not exist, DAV_3510's read-read rule would be 220x's, and every layout decision made
           on the strength of the relaxation would need redoing.
```

# 0315 · On DAV_3510 two reads of one bank group do not conflict, and that is the one rule that differs

## 1 · Claim
Upstream asserts three UB bank conflict conditions and states that exactly one of them differs
between the 220x generation and DAV_3510. Read-write conflicts arise on the same **bank**, on both.
Write-write conflicts arise on the same **bank group**, on both. Read-read conflicts arise on the
same bank group on 220x, but on DAV_3510 they arise only when two reads hit the same **bank**, or
when *more than two* reads hit one bank group. Upstream asserts the mechanism it attributes this to:
`Atlas 350 的 bank group 上有两组读口和写口`, i.e. each group carries two read ports, so two reads
in two different banks of one group proceed concurrently. Not established here — nothing was
measured, and no second document in the repository states this rule.

The consequence upstream draws, and it is the operational content: on DAV_3510 a
`Add(dst, src0, src1)` whose two sources land in different banks of one group is *not* a conflict,
where on 220x it is.

## 2 · The wrong branch this removes
The default assumption is that a conflict model carries forward. It does not, and the direction of
the difference makes both errors available.

Carrying the 220x model forward is the expensive one: the agent pads `src0` and `src1` apart to
avoid a read-read conflict that DAV_3510 does not have, spends UB on the padding, and — because
padding shifts *every* subsequent buffer — may create a genuine read-write or write-write conflict
that was not there before. The cost is invisible: nothing is wrong, the operator is just slower and
larger.

Carrying the DAV_3510 relaxation backward, or over-reading it, is the other. The relaxation is
strictly two reads in two different banks. Three reads in one group still conflict (upstream says so
explicitly, `两个以上`), and two reads in the *same* bank still conflict — which is a *tighter*
condition than 220x's group rule, not a looser one. An agent that summarises this as "950 has no
read-read conflicts" has introduced a bug it will diagnose as something else.

The third branch is the one this entry is really placed against. Upstream's own avoidance recipes —
the 256 B padding, the `blk_stride = 1` rewrite, the `64 * 1024 - (4096 * sizeof(float) + 256)`
sizing — are every one of them stated as `220x 官方推荐` (`:96`, `:117`, `:130-137`). The document
that tells you DAV_3510's rules are different hands you only the other generation's fixes. So the
correct posture on DAV_3510 is: use the rule, re-derive the fix (`0316`).

## 3 · Ground / Source
The conflict table in full, `common/ub_resident_design.md:46-54`:

```
**冲突条件差异**（关键区别）：

| 冲突类型 | NPU 220x | Atlas 350 |
|---------|----------|-----------|
| 读写冲突 | 同一 **bank** | 同一 **bank** |
| 写写冲突 | 同一 **bank group** | 同一 **bank group** |
| 读读冲突 | 同一 **bank group** | 同一 **bank**（两个读操作），或**两个以上**读操作同一 bank group |

> Atlas 350 的 bank group 上有两组读口和写口，因此**两次读操作访问同一 bank group 的不同 bank 时
> 不会冲突**，但 220x 上同一 bank group 内的任意多次并发访问都会冲突。
```

The hardware story the whole table rests on, `:29`:

```
Vector 计算单元在一个 Repeat 周期内会并行发出多个 DataBlock 的读写请求。理想情况下，这些请求被
分发到不同的 bank/bank group 上并发执行，1 个 Repeat 周期完成全部访问。当多个请求因地址映射关系
落到**同一 bank 或同一 bank group** 时，硬件仲裁逻辑会将其串行化，导致单 Repeat 从 1-2 拍退化到
多拍（具体拍数因芯片和冲突 DataBlock 数量而异）。
```

Note what the cost figure is: `1-2 拍` clean, `多拍` conflicted, `具体拍数因芯片和冲突 DataBlock
数量而异`. That is a direction, not a number, and no number appears anywhere in the file. The
headline table at `:11` says `计算速度提升数倍` for the fix, equally unquantified.

The scenario that instantiates the read-read rule, `:110-117`:

```
**场景 3：读读冲突 —— 双 src 落入同一 bank group（220x），或同一 bank（350）**

// 220x：x 和 y 起始地址差为 bank size 整数倍，DataBlock 0 同时读同一 bank group
Add(zLocal, xLocal, yLocal, ...);

**规避**：在 `xBuf` 后增加 256B padding，打破地址周期性，使 `x` 和 `y` 的 DataBlock 分散到不同
bank group。对于 350，还需确保两个 src 不在同一 bank。
```

`对于 350，还需确保两个 src 不在同一 bank` — the DAV_3510 requirement is stated as an *addition*
to a 220x fix, which is exactly the presentation that invites the wrong branch §2 names.

Nowhere else in the upstream repository is a DAV_3510 read-read condition stated. The installed
CANN 9.0.0-beta.2 `platform_config` set corroborates the bank and group counts (`0314`,
`ubbank_num=16`, `ubbank_group_num=8`) and carries **no port count field** — a read of all 32
`NpuArch=3510` files finds no `read_port`, `write_port` or equivalent. So the two-read-port
mechanism, which is the entire reason for the relaxation, has one statement in the world as far as
this harvest can see. Recorded as `C-950bp-006` and in `harvest/standing/950-bp.md`.

Measured/inferred split: **nothing here is measured**. The rules are asserted; the port count is
asserted; the cost is given as a range with no units.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. The claim is a truth table,
so the procedure enumerates it.

The instrument is one kernel with three UB buffers whose base addresses are set independently, so
that any (bank, group) placement of `src0`, `src1` and `dst` can be requested. Bank id is derived
from the geometry `0314` establishes — address-adjacent 32 B rows map to adjacent banks, cycling
through 16 — and the derivation is *checked* by `0314` §4 Arm A before this entry's arms are
believed. If that check fails, every placement below is nominal and this procedure reports `void`.

Six cells, one build each, everything else held:

1. read-write, same bank — predicted **conflict**.
2. read-write, different banks, same group — predicted clean.
3. write-write, same group, different banks — predicted **conflict**.
4. read-read, same bank — predicted **conflict**.
5. read-read, different banks, same group — predicted **clean**. *This is the discriminating cell.*
6. read-read, three sources, same group, three different banks — predicted **conflict**
   (`两个以上`).

Readout per cell: UB bank-conflict ratio from `msprof --aic-metrics=ResourceConflictRatio`, and
cycles per Vector repeat from `PipeUtilization`, both against a seventh control cell with all three
operands in different groups. Cells 5 and 6 together are the entry: 5 clean and 6 conflicted is the
two-port model; 5 conflicted is the 220x model and fires the OVERTURN; 5 clean and 6 clean means
more than two ports and the rule is understated.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, reported
beside every ratio. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
`ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after; discard the case if the die moved. Refuses to
assume: that a free die stays free; that a die may be substituted; that the requested placement is
the achieved placement — each build echoes the resolved UB base address of all three tensors, and a
cell whose addresses do not land where intended is discarded, not reinterpreted; that
`ResourceConflictRatio` reports UB bank conflicts specifically rather than an aggregate (if the
counter is an aggregate, the cycles-per-repeat readout is the verdict and the ratio is recorded as
context).

**As-run note (2026-08-25, incidental to 950:0489; this entry's own §4 arms were NOT run):** with a
128-lane `Reg::DataCopyGather` at base stride 512 B, splitting the lanes into pairs offset by 8, 16,
32 or 64 B halves the penalty exactly (0.500), while offsets of 128 or 256 B leave it unchanged
(1.000) — the class that serialises is the address modulo 128 B. Under the address→bank mapping this
book has NOT established (16 banks × 8 B would make a 64-B offset "bank + 8", i.e. the other bank of
one group under upstream's `bank_id % 8` rule), the full relief at 64 B is consistent with this entry's
claim that two reads in different banks of one group do not conflict. It is consistent with it, not a
measurement of it: the mapping is inferred and the conflict counter read ≈0 throughout (0489 §6/§7).

**As-run note 2 (2026-08-25, pad950):** the classic-vector instrument (upstream's own three-buffer
`Add(z, x, y)` and an `Adds` stride sweep, ported from the 910 bank job) was run on 950PR and cannot reach
this entry's cells: `aiv_vec_bank_cflt_ratio` reads 0.0 at every stride S = 1..32 and ≈ 0.32 (constant, no
separation) across the three pad layouts, and the 950 `ai_core_metrics` schema has no bank-GROUP column at
all (the 910 CSV's `aiv_vec_bankgroup_cflt_ratio` is 910-only). No placement of classic-vector operands
fires a conflict counter on this part, so cells 1–6 are unadjudicable by it; the read-read discriminating
cell needs the per-lane gather (0489), whose 64-B pair-offset relief is the only evidence and is
consistent-with, not a measurement-of, the two-port claim. This entry stays harvested.

## 5 · Checker — acceptance declared before the run
Verdict `cell_verdict[i]` ∈ {conflict, clean, void} for `i = 1…6`, where `conflict` means the
cycles-per-repeat exceeds the control by more than the floor **and** the conflict ratio exceeds the
control, `clean` means both are within the floor, and any disagreement between the two readouts is
`void` — not a judgement call made afterwards.

Declared before the run: the entry is **supported** iff the six verdicts are
`conflict, clean, conflict, conflict, clean, conflict` in order. The OVERTURN fires on
`cell_verdict[5] == conflict`. `cell_verdict[6] == clean` does not overturn but corrects the entry
in place — the group would have more than two read ports and upstream's `两个以上` bound would be
wrong in the permissive direction.

The exit code is not the verdict. Three guards.

First, every cell's output is compared elementwise against a CPU reference. Placing operands by
address is exactly the operation that produces a fast, aliased, wrong result, and a conflict study
that measures only counters would rank the aliased build best.

Second — the checker must be able to go red, and here is the input that does it. Cell 1
(read-write, same bank) is upstream's least controversial conflict and is used as the instrument's
positive fixture: it **must** come out `conflict`. If cell 1 reads clean, the placement machinery is
not placing anything, the counter is not counting, or the geometry derivation is wrong — and every
`clean` verdict in the table, including the one this entry wants, is void. A conflict study whose
only possible outcome is "no conflict detected" is the known blind species; cell 1 is what excludes
it, and it is chosen precisely because it is the cell nobody disputes.

Third, no verdict is reported from the conflict ratio alone. The ratio is the counter the
experimenter most wants to be informative, and `950:0052`'s neighbourhood records that resource
conflict ratios exist only on device and cannot be simulated — so the wall-clock readout is carried
alongside, and disagreement between them is reported rather than resolved.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The truth table in §3 is
upstream's assertion; no conflict has been observed, no repeat has been timed, and the two-read-port
mechanism has been read about and never seen.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The two-read-port mechanism has exactly one statement in the
upstream repository and no ini field anywhere in the installed toolkit, so it is the least
corroborated load-bearing claim in this block — `C-950bp-006` records that as a single-source
finding rather than as a disagreement, which is a different and in some ways worse condition. The
entry establishes no *cost*: upstream's `1-2 拍` versus `多拍` is a direction with the pitch count
explicitly left variable, and the `计算速度提升数倍` headline has no case at all. It does not
establish the address→bank mapping, which `0314` carries and which this procedure depends on — if
that mapping is wrong every cell here is mis-placed. It says nothing about UB accesses issued by
anything other than a Vector repeat (MTE2/MTE3 traffic, SIMT thread loads, `LoadAlign`/`StoreAlign`
from a VF), none of which upstream's table scopes itself to or against. The avoidance recipes in the
same file are all stated for 220x and are treated here as not carried (`0316`). BOARD is
`family-claimed(unverified)`: the source names "Atlas 350", which the repo's own truth source does
not define (`C-950bp-011`). Nothing transfers to the other book (RULES.md Art. 1) — the 220x column in §3
is upstream's text, quoted for contrast, and no fact from it is carried.
