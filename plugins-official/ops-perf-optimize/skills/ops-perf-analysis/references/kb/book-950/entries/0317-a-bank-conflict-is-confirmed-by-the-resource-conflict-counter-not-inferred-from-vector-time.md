```
ID:        0317-a-bank-conflict-is-confirmed-by-the-resource-conflict-counter-not-inferred-from-vector-time
LABEL:     procedure
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing collected
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md:79-83 —
           "**步骤 3：通过官方工具或实验确认**" · "- **msProf 资源冲突占比分析**：官方提供的 msProf
           工具可以采集资源冲突占比数据，直接定位 bank 冲突。" · "- **Profiling 验证**：如果 Vector
           计算耗时远高于理论值，且 MTE2 不是瓶颈，则极可能存在 bank 冲突。" · "- **实验验证**：对
           疑似冲突的代码添加 256B padding 或调整 `blk_stride` 后重新 profiling，观察周期数是否下降。"
SOURCE:    same file:317 — "| Vector 性能仍低 | bank 冲突未解决 | 使用 msProf 采集资源冲突占比确认；
           按 2.2.5 节场景逐一排查（读写/写写/读读冲突）；确认 padding 后各 buffer 的 DataBlock 不在
           同一 bank/bank group；检查 `blk_stride` 是否导致 8 个 DataBlock 回卷到同一 group |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a case on a named 950 board where the resource-conflict counter reads clean while a
           padding change alone moves Vector repeat cost outside the run spread — the counter would
           then not be sufficient to confirm or exclude a conflict, and the three-step protocol's
           first step would need a fourth.
```

# 0317 · A bank conflict is confirmed by the resource-conflict counter, not inferred from Vector time

## 1 · Claim
Upstream asserts a three-step protocol for establishing that a UB bank conflict exists. Step 1:
identify the concurrently accessed operands — for a `Add(dst, src0, src1)` all three are candidates
within one repeat. Step 2: analyse the address spacings, distinguishing *between* operands (are the
buffer base addresses an integer multiple of the bank size apart) from *within* one operand (does
`blk_stride` make the DataBlock-to-DataBlock bank difference equal the group count or a multiple of
it). Step 3: confirm, by one of three means — the msProf resource-conflict ratio, which upstream
calls a direct localisation; a profiling inference (Vector time far above theory while MTE2 is not
the bottleneck), which upstream qualifies as `极可能`; or an experiment (add 256 B of padding or
change `blk_stride`, re-profile, see whether the cycle count falls). Not established here.

Upstream states the same protocol a second time as a troubleshooting row, and there the ordering is
explicit: collect the conflict ratio first, then walk the three conflict scenarios, then check the
padding actually separated the DataBlocks, then check `blk_stride`.

## 2 · The wrong branch this removes
The available shortcut is: Vector time is high, MTE2 is idle, therefore bank conflict. Upstream
itself offers that inference and marks it `极可能` — probably — and the difference between
"probably" and "confirmed" is where the time goes.

Vector time above theory with MTE2 idle is also the signature of: a scalar-bound inner loop
(`950:0017`), transcendental or cast instructions dominating (`950:0016`), register spill on a
regbase path (`950:0036`), an unrolled loop with a RAW chain (`950:0031`), and a mask ceiling
forcing extra repeats. An agent that jumps to padding on that signature will pad, see no change,
pad differently, see no change, and spend the session on the wrong pipe — with the additional cost
that every padding attempt perturbs the layout, so a later real conflict may be created rather than
removed (`0316`).

The reverse error is subtler and this entry is placed partly against it. The *experiment* step —
pad and see whether cycles drop — reads like the strongest evidence and is the weakest of the three
as a confirmation. A cycle drop after padding is consistent with a conflict having been removed; it
is equally consistent with the padding having changed alignment, changed the tail, or moved a buffer
out of some other contention. It is a two-point comparison of two builds and carries no attribution
on its own. It becomes evidence when the conflict counter moves *with* it, which is precisely the
pairing upstream's step 3 offers and does not require.

So the operational content of this entry is an ordering upstream implies and never states: the
counter is the verdict, the timing is the symptom, and the padding experiment is a manipulation
whose result is only readable through the counter.

## 3 · Ground / Source
The protocol, `common/ub_resident_design.md:68-83`, in full:

```
#### 2.2.4 冲突判断方法

**步骤 1：识别并发访问的数据源**

一个 Vector 指令（如 `Add(dst, src0, src1)`）在同一 Repeat 内会同时读取 `src0`、`src1` 并写入
`dst`。这三个操作数的 DataBlock 是并发访问的候选冲突源。

**步骤 2：分析地址间隔规律**

- **多操作数之间**：若 `dst`、`src0`、`src1` 的 buffer 起始地址在 UB 内连续分配，且间隔恰好是
  bank size 的整数倍，则它们的对应 DataBlock 会周期性地映射到同一 bank/bank group。
- **单操作数内部**：若 `blk_stride` 使 DataBlock 之间的 bank 差等于 group 数（220x: 16，350: 8）
  或其倍数，则多个 DataBlock 会回卷到同一 bank group。

**步骤 3：通过官方工具或实验确认**

- **msProf 资源冲突占比分析**：官方提供的 msProf 工具可以采集资源冲突占比数据，直接定位 bank 冲突。
  具体使用方法参考《算子开发工具》文档。
- **Profiling 验证**：如果 Vector 计算耗时远高于理论值，且 MTE2 不是瓶颈，则极可能存在 bank 冲突。
- **实验验证**：对疑似冲突的代码添加 256B padding 或调整 `blk_stride` 后重新 profiling，观察
  周期数是否下降。
```

Step 2 is the one place in the whole file where the DAV_3510 group count appears inside a decision
rule rather than in a table: `group 数（220x: 16，350: 8）`. That is the operational form of `0314`'s
geometry, and it is what makes step 2 executable at all — without a group count there is no
"multiple of" to test against.

The troubleshooting restatement, `:317`, which supplies the ordering:

```
| Vector 性能仍低 | bank 冲突未解决 | 使用 msProf 采集资源冲突占比确认；按 2.2.5 节场景逐一排查
（读写/写写/读读冲突）；确认 padding 后各 buffer 的 DataBlock 不在同一 bank/bank group；检查
`blk_stride` 是否导致 8 个 DataBlock 回卷到同一 group |
```

`确认 padding 后各 buffer 的 DataBlock 不在同一 bank/bank group` is the check §2 says the
experiment step needs and does not have: it asks whether the padding *achieved* the separation, not
merely whether the timing moved.

The instrument named in the shelf's SIMT guide is more specific —
`simt/optimization-guide.md:233`, `用 ResourceConflictRatio.csv 中的 bank conflict 指标验证` — and
`:402`, `bank conflict 高：检查 UB stride、padding 和线程映射`. Same repo, one origin (RULES.md Art. 3);
quoted because it names the file the ratio lives in, which the resident-buffer document does not.

What the protocol does not supply: any threshold. There is no conflict-ratio value above which a
conflict is declared, no "theoretical" Vector time to compare against in step 3's second bullet, and
no statement of what the ratio is a ratio *of*. `950:0052`'s neighbourhood records that resource
conflict ratios exist only on device and cannot be simulated, which removes the cheapest way to
calibrate a threshold.

Measured/inferred split: **nothing here is measured**. Step 3's first bullet asserts a tool
capability; the second is explicitly probabilistic; the third describes a manipulation and states
what to look at, not what would count.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. This entry is a procedure
claim, so §4 is a procedure *about* a procedure: it asks whether the three confirmation means agree.

Construct four cases, each with a known ground truth from the geometry (`0314`) and the conflict
rules (`0315`), and each echoing its resolved UB addresses so the placement is verified rather than
intended:

- **P** — a placed, genuine conflict (two reads in one bank, `0315` cell 4).
- **N** — a clean layout (all operands in different groups).
- **S** — Vector time far above theory for a *non*-conflict reason: the same shape rewritten so the
  inner loop is scalar-bound, with the operand placement of N.
- **A** — a layout that is clean but whose padding changes alignment, so a padding experiment moves
  the cycle count without any conflict having existed.

For each case record all three of upstream's confirmation means: the resource-conflict ratio; the
Vector-time-versus-theory inference (with "theory" defined before the run as repeats × the clean
cycles-per-repeat from N); and the padding experiment's cycle delta.

Arm 1 — sensitivity. Does the ratio separate P from N, outside the floor?
Arm 2 — specificity, which is the arm that matters. Does the ratio stay clean on S and A, where the
*timing* inference and the *padding experiment* respectively give a false positive?
Arm 3 — the missing threshold. From the P/N pair, report the ratio values themselves, so that a
downstream skill has a calibration point rather than an adjective.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, beside
every ratio and every cycle count. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved. Refuses to assume: that a free die stays free;
that a die may be substituted; that the ratio is UB-bank-specific rather than an aggregate over
resource types (if it is an aggregate, Arm 2 will show it by going red on S, and that outcome is
reported as a property of the instrument, not of the kernel); that "theory" is knowable — it is
*defined* from N before the run, and the definition is part of the record.

**As-run note (2026-08-25, incidental to 950:0489, this §4's four cases were NOT built):** a
lane-parallel `Reg::DataCopyGather` sweep on 950PR produced stride penalties of 1.35×, 2.7×, 5.4×
and 10.7× over the odd-stride floor (device `aiv_total_time`, five launches per point, spread ≤ 1.6 %)
while `aiv_vec_bank_cflt_ratio` — the counter this entry's step 3 calls a direct localisation —
stayed between 0.00034 and 0.00063 at every point, slow or fast. For that access pattern the
counter's sensitivity (Arm 1's question) is nil on this part: a 10.7× penalty is invisible to it,
and the timing inference upstream rates only `极可能` is the instrument that sees it. This is
recorded as a property of the instrument under one access pattern, not as a verdict on this entry
(its §5 needs the P/N/S/A cases); it is the outcome §4's last "refuses to assume" clause named — the
ratio may be a different aggregate than "UB bank" — arriving from the other direction: the counter
did not go red on a non-conflict, it stayed green on a phenomenon that costs 10×. Tables in 0489 §6.

## 5 · Checker — acceptance declared before the run
Verdict `sensitive` = true iff the conflict ratio on P exceeds N's by more than the floor.
Verdict `specific` = true iff the ratio on S and on A is within the floor of N's.
Verdict `timing_fp` = true iff the Vector-time inference declares a conflict on S (a false positive
by construction).
Verdict `padding_fp` = true iff the padding experiment shows a cycle drop on A (a false positive by
construction).

Declared before the run: this entry's ordering claim is **supported** iff
`sensitive ∧ specific ∧ (timing_fp ∨ padding_fp)` — the counter must discriminate where at least one
of the cheaper means does not. The OVERTURN fires iff `sensitive == false`: a counter that cannot
see a placed conflict is not a verdict instrument, and step 3's first bullet would need replacing.
If `specific == false`, the entry is corrected in place — the counter would be an aggregate and
would need the same corroboration it is here being preferred over.

The exit code is not the verdict. Three guards.

First, all four cases are compared elementwise against a CPU reference. P and A place buffers by
address; a mis-placed buffer that aliases produces a fast wrong answer that would read as an
excellent clean case.

Second — the checker must be able to go red, and cases **S** and **A** *are* the fixtures that make
it able to. They are planted positives for the cheap means and planted negatives for the counter,
and the run has no value unless at least one of them fires. A study that only ran P and N could
report "the counter agrees with the timing" and would have shown nothing, because on P and N
everything agrees; that is the known blind species — a check that reads only the lines it expects —
and S and A are what exclude it here.

Third, the ratio values are reported as numbers, not as verdicts, because upstream supplies no
threshold and this run is the only thing that could. A verdict rendered against an undeclared
threshold is not acceptance declared before the run.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No conflict ratio has been
collected, no Vector time compared against any theory, and no padding experiment performed.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the resource-conflict counter
reports UB bank conflicts specifically; upstream asserts it localises them `直接` and names no
field, no unit and no threshold. It supplies no threshold of its own — §4 Arm 3 exists to produce
the first calibration point and has not been run. The Vector-time inference is upstream's own,
hedged by upstream as `极可能`, and this entry neither adopts nor refutes it; it lists five other
causes of the same signature from elsewhere in this book, which is an argument about ambiguity, not
a measurement of frequency. The padding experiment's weakness (§2) is a methodological argument, not
an observation. `《算子开发工具》`, the document upstream defers to for how to use the tool, is not
present in this tree. `950:0052`'s neighbourhood records that these ratios do not exist in a
simulator, so nothing here is establishable off-card at all. BOARD is `family-claimed(unverified)`.
Nothing transfers to the other book (RULES.md Art. 1).
