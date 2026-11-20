```
ID:        0140-the-topk-fallback-searches-inside-a-240-kib-budget-of-a-248-kib-physical-ub-after-a-32-kib-simt-reserve
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/sort/topk_host_tiling.md:85,207-209 —
           "公共 tiler 和 fixed small-axis 先从物理 UB 预留 32 KiB SIMT 空间。fallback 按 240 KiB
           预算搜索，但不得超过平台 UB 扣除保留区后的可用容量。" · "| SIMT UB reserve | 32 KiB |" ·
           "| fallback UB budget | 240 KiB（DAV_3510 物理 UB 248 KiB） |" ;
           sort/topk.md:161 — "对每个候选找 240 KiB UB 预算内的最大 G"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a runtime capacity query plus an allocation probe on a named 950 board returning a
           physical UB other than 248 KiB, or an allocatable ceiling that makes the 32 KiB reserve
           and the 240 KiB budget mutually inconsistent.
```

# 0140 · The TopK fallback searches inside a 240 KiB budget of a 248 KiB physical UB, after a 32 KiB SIMT reserve

## 1 · Claim
Upstream asserts three related capacity figures for the TopK path and, uniquely in this reference
subtree, attaches an architecture name to one of them: the physical UB is 248 KiB on DAV_3510; the
common tiler and the fixed small-axis path first reserve 32 KiB of it as SIMT space; and the
batched fallback searches its `dChunk`/`G` candidate space inside a 240 KiB budget, while never
exceeding the platform UB minus the reserved region. Upstream also asserts that the dynamic UB
value must be written into the launch attributes and not merely used in host arithmetic. Not
established here.

## 2 · The wrong branch this removes
This is the only place in the whole tiling subtree that separates *physical* capacity from *usable*
capacity and names the chip family for either. Everywhere else a UB number is a bare script literal
— C-006 records four incompatible values across this subtree, and 0131 records the reduction
family's own measured anchor (192 KB) contradicting its own script (248 KB). An agent that has met
only those numbers reads every UB figure as one quantity, and then cannot make sense of two
different values appearing in one family's formulas. Here they are two quantities with a stated
relationship: 248 physical, 32 reserved, 240 budgeted — which does not add up to 248 − 32 = 216,
and that discrepancy is the substance of this entry.

Reading it precisely: the 32 KiB SIMT reserve is stated for the *common tiler and fixed small-axis*
paths, and the 240 KiB budget is stated for the *fallback* path. They are two different routes, so
216 KiB and 240 KiB are not competing values for one thing — but the same sentence then requires
the fallback's 240 KiB not to exceed "the platform UB minus the reserved region". If the reserve
applies to the fallback too, 240 > 216 and the constraint is violated by the constant; if it does
not, the constraint is vacuous for that path. Upstream does not say which. An agent that resolves it
by subtracting 32 KiB from 240 loses 24 KiB of search space on every fallback case; one that
ignores the sentence may overshoot the real ceiling.

The launch-attribute rule removes a separate, quieter branch: computing a dynamic UB on the host
and forgetting to pass it. The kernel then allocates against a default while the host's budget
assumed something else, and the failure is a wrong result or an overflow rather than an error.

## 3 · Ground / Source
The platform-read section, `sort/topk_host_tiling.md:76-86`, in full:

```
### 2.2 平台信息

从 `PlatformAscendC` 读取：

coreNum    = GetCoreNumAiv()
ubSize     = GetCoreMemSize(CoreMemType::UB)
ubBlock    = GetUbBlockSize()，缺失时 DAV_3510 取 32B

公共 tiler 和 fixed small-axis 先从物理 UB 预留 32 KiB SIMT 空间。fallback 按 240 KiB 预算搜索，
但不得超过平台 UB 扣除保留区后的可用容量。动态 UB 必须写入 launch 属性，不能只影响 Host 计算。
```

The constants table, `:205-215`:

```
| 名称 | 值 |
|---|---:|
| `ALIGN_BYTES` / `AGLIN_FACTOR` | 32B |
| SIMT UB reserve | 32 KiB |
| fallback UB budget | 240 KiB（DAV_3510 物理 UB 248 KiB） |
| system workspace | 16 MiB |
| `BIN_NUM` | 256 |
| `TOPK_K_MAX` | 2048 |
| fixed small-axis max tileWidth | 4096 |
| fallback L/S max dChunk | 4096 / 4000 |
| fallback max G | 128 |
```

The budget in use, `sort/topk.md:161`:
`对每个候选找 240 KiB UB 预算内的最大 G。` — and the same figure restated at
`topk_host_tiling.md:161`: `对每个 dChunk 找 240 KiB 内最大的 G。`

The reserve applied elsewhere in the same document, `:389` and `:402`:

```
必须满足 `runtime buffers + API tmp <= ubSize - 32KiB`。修改 Kernel `InitBuffer` 后必须同步修改公式。
```
```
先从 `usableUb = physicalUb - 32KiB` 计算全轴 RadixSort tile：
```

So `ubSize − 32 KiB` is the general rule in two other places, which strengthens the reading that
the reserve is not fallback-exempt and therefore that 240 KiB exceeds the stated usable ceiling by
24 KiB. Registered as C-950tiling-018.

The fixed small-axis path states the reserve as a step in its own tiling, `sort/topk.md:121`:
`5. 平台 UB 先预留 32 KiB SIMT 空间；动态 UB 传剩余值。`

This is also the only chip-scoped UB figure in the entire `references/tiling/` subtree. A prior
survey established that `grep -rn "910"` over this subtree returns nothing and that 12 of 54 files
name a chip, every one naming the 950 family; re-reading confirms `DAV_3510` here as the sole
capacity attribution. `DAV_3510` names an architecture, not a board, so BOARD remains
`family-claimed(unverified)` — 950PR and 950DT are both DAV_3510 and this entry cannot tell them
apart.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT, recorded as whichever ran); never run
in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved.

Query, then probe, then use. Query `GetCoreMemSize(CoreMemType::UB)`, `GetCoreNumAiv()` and
`GetUbBlockSize()` and print all three with the toolkit pin and board id — a runtime query is a
claim the runtime makes about itself, not a measurement. Then probe the allocatable ceiling: walk a
single UB buffer upward in 4 KiB steps from 192 KiB to 256 KiB, at each size launching a kernel that
writes a known pattern across the whole buffer and reads it back, and record the largest size for
which every byte round-trips. Then, with SIMT features in use, repeat the probe to find the
allocatable ceiling *with* the reserve in force — that is what settles whether the reserve is 32 KiB
and whether 240 KiB is reachable on a fallback case.

Fallback-budget arm: take a batched-fallback TopK case (`inner == 1`, L branch, `D` long enough that
`dChunk` search matters) and run the `dChunk`/`G` search at budgets of 216 KiB and 240 KiB, recording
the selected `(dChunk, G)`, whether the resulting kernel builds and runs correctly, and `aiv_time`
for each. If the 240 KiB choice fails to run, the constraint sentence wins and 216 is the real
budget; if it runs, the constant wins and the sentence is loose.

Refuses to assume: that the queried value is the allocatable value (the probe settles it); that
950PR and 950DT share a capacity; that a free die stays free; that a die may be substituted; that
the 32 KiB reserve exists at all when SIMT features are unused — that is the second probe's
question; that a budget that fits is a budget that was used (the host echo of the selected
`dChunk`/`G` and the dynamic UB launch attribute is required).

## 5 · Checker — acceptance declared before the run
Verdict variables `ub_queried`, `ub_allocatable` and `ub_allocatable_simt`, all in bytes, on the
named board with the recorded pin. Declared before the run: the 248 KiB physical figure is supported
iff `ub_allocatable ∈ [244, 252] KiB`; the 32 KiB reserve is supported iff
`ub_allocatable − ub_allocatable_simt ∈ [28, 36] KiB`. The OVERTURN fires iff `ub_allocatable` falls
outside that band, or iff `ub_allocatable_simt < 240 KiB` while a 240 KiB fallback search still
produces a working kernel — the constant and the constraint would then both be describing something
other than what the probe measures. Verdict variable `budget_verdict ∈ {216, 240, both}` from the
fallback arm.

The exit code is not the verdict. Two guards. First, the probe's pattern check: an allocation that
succeeds without being fully backed would report a ceiling that does not exist, so a size counts
only if every byte round-trips, and a size that allocates but fails the pattern is recorded as
failing. Second, the fallback arm requires the host echo of the dynamic UB launch attribute to match
the budget under test — upstream's own warning is that a host-only UB value is a silent mismatch,
and a checker that read only timings would compare two kernels that both allocated the default.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. 248 KiB, 240 KiB and 32 KiB
are upstream's stated constants.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; nothing was queried or probed. The entry does not establish the physical UB
capacity of any board, does not establish the 32 KiB SIMT reserve, and does not resolve whether the
240 KiB fallback budget respects the reserve (C-950tiling-018) — Art. 7 forbids resolving that by
preferring one sentence over another. It does not establish the 16 MiB system workspace, `BIN_NUM`,
`TOPK_K_MAX` or the other constants in the same table; those are separate literals recorded in 0142
as policy rather than capability. `DAV_3510` names an architecture covering both 950PR and 950DT, so
BOARD is `family-claimed(unverified)` even though this is the only chip-scoped capacity figure in the
subtree, and §7 records that no specific board is named. §4 names 950PR/950DT because that is where
our run would happen. Nothing here is established for any 910-family board, and no fact from the
910 book was used.
