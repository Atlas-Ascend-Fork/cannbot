```
ID:        0452-the-g-query-heads-of-one-kv-head-must-merge-into-one-task-or-the-kv-block-is-moved-g-times
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/flashattention/overview.md:120-127 —
           "### §3.2 I2 — GQA 同 kvHead 同任务不变量 / GQA 子族中,同一 kvHead 下的 G 个 qHead
           **必须在同一个任务内合并处理**(`mEff = curBq × curG`,合并到 Mmad m 维度)。 / 禁止: /
           - 把 G 个 qHead 拆到 G 个独立任务,每个任务各自搬运同一份 KV /
           **违反后果**:KV 重复搬运 G 次,Mte2 / L1 利用率塌陷;性能远低于合并方案。"
SOURCE:    same shelf, subfamilies.md:111-118 — "- **`gMaxPerTask`**:每个 task 合并的 qHead 数,
           `≤ G = Hq / Hkv` / - **`mEff = curBq × curG`**:task 内有效 m 维(Bq 是 Sq 维基本块,
           curG 是当 task 合并的 qHead 数) / - **mEff 行排布约定**(**Bq-major**):
           `row(g, i) = g × Bq + i`,即按 qHead 外、Sq 内排布" ; :57 —
           "| FA / GQA 推理(默认)| 标准 task 级双缓冲 | 标准 task 级双缓冲 | GQA 中 K/V 在同 kvHead
           内复用,标准深度即够 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a GQA case on a named 950 board at which the split-task form (one task per qHead) is not
           slower than the merged form beyond the variance floor, with `Mte2` traffic measured on
           both — the "utilisation collapse" would then be an assertion without a subject at that
           shape, and the invariant would be a design preference rather than a hard rule. Equally,
           a merged form whose measured `Mte2` byte count is G times the split form's would falsify
           the mechanism this entry states even if the merged form is faster.
```

# 0452 · The G query heads of one kv head must merge into one task, or the KV block is moved G times

## 1 · Claim
Upstream asserts that in the GQA subfamily, where `Hq = G × Hkv` and G query heads share one key/value
head, all G query heads under one `kvHead` must be processed inside a single task, merged into the
Mmad `m` dimension as `mEff = curBq × curG`. Upstream asserts the forbidden form explicitly — splitting
the G query heads across G independent tasks, each moving its own copy of the same KV — and names the
consequence as the KV being moved G times, with `Mte2` and L1 utilisation collapsing and performance
far below the merged scheme. Upstream asserts a row-ordering convention for the merged block,
Bq-major: `row(g, i) = g × Bq + i`, query head outer and sequence position inner. Not established here.

## 2 · The wrong branch this removes
Without this entry a harness agent constructing the task-dispatch dimensions does the natural thing:
enumerate every independent output block. In GQA the output is `[B, Sq, Hq, D]`, so `Hq` looks like a
clean dispatch axis — every query head is mathematically independent, the tasks are perfectly balanced,
and the core count divides evenly. That is precisely the split upstream forbids, and it is forbidden
for a reason no correctness check can see: the G tasks produce identical, correct results. They just
each re-read the same `K` and `V` tile from GM.

The normal checks do not catch it because it is not a correctness defect. Precision regression passes.
The output matches the reference. The kernel does not fault. What changes is the byte count on the
MTE2 pipe, by a factor of G — and G is a model-architecture parameter that is typically 4 or 8, so an
agent that never opens a profile sees a kernel that is several times slower than it should be with no
symptom pointing at the cause.

The second wrong branch is the one that appears after the first is fixed: merging G into the task but
laying the rows out `Sq`-major (`row(i, g) = i × curG + g`). Upstream states the opposite convention
and gives three reasons, of which one is a correctness reason and two are efficiency reasons — the
causal mask template is shared across the G heads by translation only when the heads are the outer
axis, so an `Sq`-major layout silently applies the wrong mask pattern to G-1 of the heads while the
G=1 case, which is what an MVP tests, is unaffected.

## 3 · Ground / Source
The invariant, `references/flashattention/overview.md:120-127`:

```
### §3.2 I2 — GQA 同 kvHead 同任务不变量

GQA 子族中,同一 kvHead 下的 G 个 qHead **必须在同一个任务内合并处理**(`mEff = curBq × curG`,合并到 Mmad m 维度)。

禁止:
- 把 G 个 qHead 拆到 G 个独立任务,每个任务各自搬运同一份 KV

**违反后果**:KV 重复搬运 G 次,Mte2 / L1 利用率塌陷;性能远低于合并方案。
```

The merged block's shape and its row order, `subfamilies.md:111-118`:

```
- **`gMaxPerTask`**:每个 task 合并的 qHead 数,`≤ G = Hq / Hkv`
- **`mEff = curBq × curG`**:task 内有效 m 维(Bq 是 Sq 维基本块,curG 是当 task 合并的 qHead 数)
- **mEff 行排布约定**(**Bq-major**):`row(g, i) = g × Bq + i`,即按 qHead 外、Sq 内排布

  **理由**:
  - Causal mask 模板可一份 + 整体平移 curG 次,不同 g 之间 mask 模式相同
  - Q 的 Nd2Nz BSND→NZ 自然连续
  - V2 输出按 (g, i) 二维循环逐行写回(见下条)
```

Two properties of this text are load-bearing and easy to miss. First, `gMaxPerTask ≤ G` — the merge
is bounded above by the group size but is *not required to equal it*, so a task may merge a subset.
The invariant therefore does not say "G heads per task"; it says the G heads must not be split into
tasks that each carry their own KV, which a partial merge with `gMaxPerTask = 2` still partly violates
at `G = 8`. Upstream never states where between 1 and G the collapse becomes acceptable, and gives no
number for the collapse at all. Recorded as `Q-950fin-01` in `harvest/standing/950-fin.md`.

Second, the name `Bq-major` and the formula `row(g, i) = g × Bq + i` describe the *same* layout from
two directions and the label is the confusing one: the formula makes `g` the slow-varying index and
`i` the fast-varying one, which by the usual convention would be called `g`-major. Upstream's prose
resolves it — `按 qHead 外、Sq 内排布`, query head outer, sequence inner — and the prose agrees with
the formula. An agent that reads only the label may implement the transpose. Registered as
`C-950fin-002`, a naming conflict inside one line rather than between two documents.

The third reason upstream gives — `V2 输出按 (g, i) 二维循环逐行写回` — is a separate obligation with
its own failure mode, carried at `0461`.

`subfamilies.md:57` states the L1 rotation consequence: `GQA 中 K/V 在同 kvHead 内复用,标准深度即够`
— the standard double-buffer depth suffices *because* of the reuse this invariant creates. So I2 is
not only a traffic argument; the L1 depth table in the same file is derived on the assumption that I2
holds. An implementation that splits the heads has both G times the traffic and an L1 depth chosen for
a reuse pattern it no longer has.

Two files in one repository are one origin (RULES.md Art. 3); this entry is `harvested`, not `corroborated`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three consecutive idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first: one build, 30 in-process runs and 5
fresh-process runs of the merged arm, IQR over median, reported beside every point.

**Arm 1 — the traffic ratio, which is the mechanism.** One GQA kernel, two task-decomposition
switches, everything else identical: (a) merged, `gMaxPerTask = G`; (b) split, one task per qHead. For
`G ∈ {1, 2, 4, 8}` at fixed `Hkv`, `Sq`, `Sk`, `D`, record `msprof` MTE2 byte counts and `aiv_time` /
`aic_time` for both. The prediction is `bytes(split) / bytes(merged) → G` on the K/V tensors and ≈1 on
Q. `G = 1` is in the sweep as the degenerate point where the two builds must be the same kernel and
must therefore measure the same — the sweep's own control.

**Arm 2 — the partial merge, which upstream does not scope.** At `G = 8`, sweep
`gMaxPerTask ∈ {1, 2, 4, 8}` and record traffic and time at each. This answers the question §3 records
as open: whether the KV traffic scales as `G / gMaxPerTask` as the arithmetic suggests, and whether
time follows traffic or saturates earlier. A partial merge that already recovers most of the benefit
would make `gMaxPerTask` a tuning parameter rather than a constant, which is a result either way.

**Arm 3 — the row-order trap, which is a correctness arm.** The merged build with `causal` on, at
`curG > 1`, compared against a CPU reference, in two layouts: Bq-major per upstream, and `Sq`-major.
Record elementwise agreement per query head separately, not aggregated. Upstream's first stated reason
predicts that the `Sq`-major build applies a translated mask to the wrong rows, so heads other than
`g = 0` disagree while `g = 0` agrees. Retained even though it is expected to bite, because *which*
heads disagree is the evidence that the mechanism is the mask translation and not something else.

**Arm 4 — the L1 depth coupling, retained because it may not bite.** Repeat arm 1(b) with the L1
rotation depth raised one slot. If the split form's traffic is unchanged but its time improves, the
depth table's dependence on I2 (`subfamilies.md:57`) is real and separable from the traffic argument.
If nothing changes, that dependence is not observable at this shape and §7 records it as untested.

Refuses to assume: that a free die stays free, or that a die may be substituted; that MTE2 byte counts
are available without checking that the profiling metric names what we think it names (`0317`'s
species); that time and traffic move together; that `G = 1` and `G = 8` are the same code path (arm 1
verifies they are); that a fast result is a correct one — every arm carries its elementwise check.

## 5 · Checker — acceptance declared before the run
Verdict `kv_traffic_ratio(G) = MTE2_kv_bytes(split) / MTE2_kv_bytes(merged)`, declared before the run,
and `i2_supported := kv_traffic_ratio(G) ≥ 0.8 × G for all G ≥ 2`. The 0.8 is a declared slack for
cache effects on the second and later reads; it is stated now rather than chosen after the readout.

Verdict `merged_is_faster := median aiv_time(merged) < median aiv_time(split) − floor`, reported per
G. The OVERTURN fires iff `merged_is_faster` is false at any `G ≥ 2` **while** `kv_traffic_ratio ≥ 2`
— traffic multiplied G times without a time cost would mean the collapse upstream names does not
occur at that shape, and the invariant is a preference there.

Verdict `row_order_breaks_mask` from arm 3 ∈ {`g0_only_agrees`, `all_agree`, `none_agree`}. Only the
first supports upstream's stated reason; `all_agree` would mean the mask is not shared by translation
in this build and arm 3 tested nothing.

The exit code is not the verdict: both task decompositions produce correct output by construction, so
a suite that only checks correctness cannot separate them and would report success for the forbidden
form. Guards: (1) every point carries its variance floor, its MTE2 counter name and its md5s, and a
point missing any is untestable rather than agreeing; (2) **the input that makes this checker go red**
is `G = 1`, where merged and split are the same decomposition — if `kv_traffic_ratio(1) ≠ 1 ± floor`,
the two builds differ in something other than the merge and every ratio in the sweep is an artifact;
(3) arm 3's per-head reporting is mandatory, because an aggregated error metric over all G heads
cannot distinguish "one head is wrong" from "everything is slightly wrong".

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The invariant, the
`gMaxPerTask ≤ G` bound, the `Bq-major` formula with its three stated reasons, and the L1 depth row
are file reads performed at drafting time. The observation that `gMaxPerTask ≤ G` leaves the partial
merge unscoped, and the observation that the label `Bq-major` and the formula `row(g, i) = g × Bq + i`
point opposite ways, are readings of upstream's own lines, not observations of a build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that the split form is ever slower, nor
by how much — upstream gives no number, and "utilisation collapse" is upstream's word, not a readout.
It does not establish that `Mte2` and L1 are the pipes that suffer, only that upstream names them. It
does not establish where between `gMaxPerTask = 1` and `= G` the invariant starts to bind; §3 records
that as open and §4 arm 2 is the procedure that would close it. It does not establish the Bq-major
convention as necessary — upstream gives three reasons, of which this entry tests only the first. It
covers the GQA subfamily; MHA is `G = 1` and the invariant is vacuous there (`subfamilies.md:146`),
MLA forces `kvHeadNum = 1` and has a different task structure (`0454`'s neighbourhood), and the
split-KV-reduce parallel strategy replaces the task model entirely. No board token appears in either
quoted passage, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT only as where our run
would happen. Nothing here is established for any 910-family board.
