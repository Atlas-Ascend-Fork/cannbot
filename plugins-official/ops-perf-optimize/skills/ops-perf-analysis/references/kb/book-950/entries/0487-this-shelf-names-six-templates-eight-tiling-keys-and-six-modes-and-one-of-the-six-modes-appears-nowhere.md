```
ID:        0487-this-shelf-names-six-templates-eight-tiling-keys-and-six-modes-and-one-of-the-six-modes-appears-nowhere
LABEL:     boundary
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/scan/templates/usage_guide.md:9-19 —
           the seven-row template roster (`scan_tiling_data` / `scan_tiling` / `scan_base` /
           `cum_streaming_scan` / `cum_tile_resident_scan` / `cum_row_kogge_stone` /
           `cum_oneway_sklansky` / `cum_lane_parallel_scan` / `cum_core_partition_scan`)
SOURCE:    same file:299-300 — "使用 `scan_cummin_tiling.h` 的 `CalcTiling()`（含 6 种 mode 选择 +
           UB 预算自适应 + / 跨核借 R 段数计算）。不要自行编写 tiling 计算，除非有明确的定制需求。" ;
           :162-163 — "**phase A**（mode 3）" and "**phase B**（mode 4）" ; :287-288 —
           "`ScanRowRange`（mode 1/3/4 的核心函数）必须包含 lane 并行条件分支： /
           `gsS > 0 → LaneParallelScan` 和 `gsS == 0 → KoggeStone` 两条分支。" ; :45 —
           "| **mode 0（N>1）加 ping-pong 双缓冲** | 82.41 | 1.92x |" ; :302-305 —
           "### 坑 5：`CalcMode5MFold` k=0 回退 / `CalcMode5MFold` 中 UB 预算不够时 `k` 返回 0，
           `CalcTiling` 自动回退到 mode 1。"
SOURCE:    same file:60 — "UB 内走 §1.2 的 lane 并行顺序扫描" (a §1.2 that does not exist; the file's
           sections are 0, 1.1, 1, 2, 3, 4, 5, 6) ; :198 — "用 `__NPU_ARCH__` 把 arch35 引入" ;
           :217 — "先核对 `--npu-arch=dav-3510`" ; :5 — "保留 `dav310/` 子目录结构"
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read (no device):
           ls upstream/skills-dev-main/ops/ascendc-performance-best-practices/reference/scan/templates/
           grep -rn 'mode [0-9]' upstream/skills-dev-main/ops/ascendc-performance-best-practices/reference/scan/
OVERTURN:  a `mode 2` named anywhere in this shelf, or a `scan_cummin_tiling.h` present in it — the
           roster would then be complete and this entry's absences would be reading failures.
           Equally: a `CalcTiling()` whose mode enumeration is recovered from a shipped implementation
           and turns out to be six contiguous values would close the gap without changing the
           documents.
```

# 0487 · This shelf names six templates, eight tiling keys and six modes, and one of the six modes appears nowhere

## 1 · Claim
Upstream asserts a template roster of nine rows mapping `.template` files to header names and uses.
Upstream asserts a host tiling function `CalcTiling()` containing a **six-mode** selection, located in
a header named `scan_cummin_tiling.h`. Upstream names, across the shelf, modes 0, 1, 3, 4 and 5 —
mode 0 as the `N > 1` path, mode 1 as the Kogge-Stone fallback that a failed mode-5 computation falls
back to, modes 3 and 4 as the two phases of the cross-core R partition, mode 5 as an M-folding path.
**Mode 2 is named nowhere.** The header `scan_cummin_tiling.h` appears in no roster row and in no
directory of the shelf, whose host tiling template is `scan_tiling.template`. Upstream asserts a
runtime gate `gsS` selecting between two scan algorithms inside the core function, and defines it
nowhere. Upstream refers to a `§1.2` that its own section numbering does not contain. Upstream spells
the target architecture three ways in one file: a `dav310/` directory prefix, `arch35`, and
`--npu-arch=dav-3510`. Not established here; this entry records an enumeration state.

## 2 · The wrong branch this removes
Without this entry an agent treats the roster as the shelf's index and the mode numbers as a
contiguous enumeration. Neither holds, and the failure is in what an agent *concludes from the gap*.
Seeing modes 0, 1, 3, 4, 5 and a claim of six, the natural inference is that mode 2 exists and is
documented elsewhere — so an agent implementing `CalcTiling()` leaves a branch for it, or worse,
guesses what it does. The alternative inference, that the count is stale and there are five, is
equally available and equally unsupported.

The normal checks do not catch it because a mode number is a tiling key: it selects a device path at
runtime, and an unreachable case in a switch is not an error. A wrong guess about mode 2 produces a
kernel that routes some shape to a path that does not exist, and the symptom is whatever the default
branch does.

The second wrong branch is `gsS`. It gates the choice between the lane-parallel scan and Kogge-Stone
inside `ScanRowRange` — the shelf's single most consequential runtime decision, worth 2.3× by the
shelf's own measurement (`0485`) — and no document says what it is, how it is computed, or what units
it has. It is `gsS_` in the templates and `gsS` in the guide. This book already records two members of
the same species from this family (`0138`: `VLC` and `VREG` are never defined or given units); `gsS`
is a third, and unlike those two it selects an algorithm.

The third wrong branch is the architecture spelling. `dav310/` is a **directory name** carried into a
consumer's project (`保留 dav310/ 子目录结构`), while the compiler flag is `--npu-arch=dav-3510` and
the macro-guarded include is `arch35`. An agent that reads the directory as the target reads `310`
where the flag says `3510`.

## 3 · Ground / Source
**The roster**, `templates/usage_guide.md:9-19`, is nine rows: three infrastructure
(`scan_tiling_data`, `scan_tiling`, `scan_base`) and six device templates — `cum_streaming_scan`,
`cum_tile_resident_scan`, `cum_row_kogge_stone`, `cum_oneway_sklansky`, `cum_lane_parallel_scan`,
`cum_core_partition_scan`. Each of the six has a `.md` document in the same directory.

**The mode enumeration** is not coextensive with it. `:299-300`:

```
使用 `scan_cummin_tiling.h` 的 `CalcTiling()`（含 6 种 mode 选择 + UB 预算自适应 +
跨核借 R 段数计算）。不要自行编写 tiling 计算，除非有明确的定制需求。
```

Six modes claimed. The modes actually named, all in this one file: `mode 0` at `:45`
(`mode 0（N>1）加 ping-pong 双缓冲`); `mode 1` at `:287` and `:304` (the Kogge-Stone core and the
fallback target); `mode 3` and `mode 4` at `:162-163` (`phase A（mode 3）`, `phase B（mode 4）`);
`mode 5` at `:302` (`CalcMode5MFold`). Five values. **No `mode 2` anywhere in the shelf.** Registered
as `C-950fin-028`.

Nor do the six modes map onto the six templates: `cum_oneway_sklansky` and `cum_streaming_scan` are
templates with no mode number named for them, and `mode 5` is an M-folding computation with no
template of its own.

**A third enumeration**, `guide.md:88-99`, is neither of the first two — eight Cumsum tiling keys,
constructed as a product of three binary choices:

```
对应到 Cumsum 的 8 个浮点模板（`inner ∈ {oneway, twoway}` × `是否 UbChunk` × `是否 CorePartition`）：

| tiling key | 模板 | 层级 | 触发 |
|-----------|------|------|------|
| 1001 | oneway_ss | Inner | R 全量入 UB，切 M（或借 N）够满核 |
| 1002 | twoway_ss | Inner（折叠） | 窄 N（`alignN ≤ VREG/4`）折叠多个 R 位置进向量道 |
| 1011 | ub_ss_oneway_ss | Inner+UbChunk | R 超 UB，切 M 够满核，单核串行多 chunk |
| 1012 | ub_ss_twoway_ss | Inner(折叠)+UbChunk | 同上，窄 N 折叠 |
| 1101 | core_ss_oneway_ss | Inner+CorePartition | M/N 并行度不足，跨核借 R，单核 R 段入 UB |
| 1102 | core_ss_twoway_ss | Inner(折叠)+CorePartition | 同上，窄 N 折叠 |
| 1111 | core_ss_ub_ss_oneway_ss | 全三层 | 跨核借 R 后单核 R 段仍超 UB |
| 1112 | core_ss_ub_ss_twoway_ss | 全三层（折叠） | 同上，窄 N 折叠 |
```

This one is well-formed — the four bits of each key are a decodable product, and the naming convention
is stated at `:101`. But it is a **Cumsum** enumeration, while the six modes and the six templates are
**Cummin/Cummax**, and no document maps the two onto each other. So the shelf carries two disjoint
routing systems for one operator family, one of which is complete and decodable and one of which is
missing a member. `twoway` appears only in the Cumsum keys and in `guide.md:264-275`'s technique table
(`oneway/twoway_ss`, `twoway 系`); it has neither a `.md` document nor a `.template` in the roster.

Three enumerations of one family — six templates, six-claimed modes, eight tiling keys — none
coextensive with another, and the one gap is in the enumeration that is claimed complete.

**The missing header.** `scan_cummin_tiling.h` is named at `:299` as the location of `CalcTiling()`.
It is in no roster row; the roster's host-side tiling entry is `scan_tiling.template` → `scan_tiling.h`
`（host 侧流式 tiling 选型）`. So the document that says "do not write your own tiling computation"
points at a file the shelf does not ship. Registered as `C-950fin-029`.

**`gsS`.** `:26` lists `gsS_` among the member variables a consumer must add to its own class; `:288`
uses `gsS` as the gate (`gsS > 0 → LaneParallelScan` 和 `gsS == 0 → KoggeStone`);
`cum_row_kogge_stone.md:109-110` uses `gsS_` for the same gate and adds a reason for the `== 0` branch
(`R 很小时 log2(VLC) 固定开销更划算`). Nowhere is it computed, typed, or given a unit. Its name
suggests "gather-scan S" — the segment length `S` of `0483` — but that is a guess and this entry does
not promote it. Recorded as `Q-950fin-31`.

**Two more dangling references.** `:60` cites `§1.2 的 lane 并行顺序扫描`; the file's headings are
`## 0.`, `## 1.1`, `## 1.`, `## 2.` … `## 6.` — there is no `§1.2`, and the lane-parallel material is
under `### 第三层` inside `## 1.1`. And `cum_tile_resident_scan.md:121-123` sends the reader to
`cum_core_partition_scan.md` for an `N > 1` generalisation; that file's trigger condition is stated
`（N == 1 分支内）` at `:27` and it contains no `N > 1` section. Three dangling references in one
family, plus the missing header, plus `0466`'s two bad section pointers in the FA family — the corpus
carries six.

**Three architecture spellings**, all in one file: `dav310/` as a directory prefix to be preserved in
the consumer's tree (`:5`, `:13-19`), `arch35` as the macro-guarded include scope (`:198`), and
`--npu-arch=dav-3510` as the compiler flag to verify (`:217`). This book's `0421` records a conversion
family spelling its architecture four ways with a fifth naming a chip that exists nowhere, and `0346`
records the same species; `dav310` against `dav-3510` is a fourth instance and the only one where the
mismatched spelling is a **path** that a consumer copies. Recorded against `C-950fin-009`'s
neighbourhood as `C-950fin-030`.

One repository, one origin (RULES.md Art. 3).

## 4 · Procedure
This entry is about a document set's enumerations. Its verification is a document procedure plus one
device arm; neither is run here.

**Arm 1 — the three enumerations, mechanically (no device).** A script that extracts, from the whole
scan shelf: every `.template` and `.md` basename; every `mode <n>` occurrence with its file and line;
every four-digit tiling key; every technique name in `guide.md`'s tables; and every path referenced but
absent. Report the sets and their pairwise differences. Expected: six device templates, five distinct
mode values against a claim of six, eight tiling keys forming a complete 2×2×2 product, `twoway` with
no file, `scan_cummin_tiling.h` absent.

**Arm 2 — the shipped tiling, if reachable (no device).** Locate `CalcTiling()` in any implementation
the repository ships and read its mode enumeration. This is the only thing that resolves
`C-950fin-028` without a run: either mode 2 exists and the documents omit it, or five is the count and
`6 种` is stale.

**Arm 3 — `gsS`, recovered (no device).** Read `scan_tiling.template` and `scan_tiling_data.template`
for the field's declaration, type and computation. `Q-950fin-31` is closed by a file read if the field
is there and stays open if it is not — and if it is not, a consumer cannot implement the gate at all,
which is a stronger finding.

**Arm 4 — the gate's consequence (device, named 950 board 950PR or 950DT).** Build `ScanRowRange` with
the gate forced to each branch and run the shapes the shelf names, reporting time for each. Upstream's
own defect register puts the gap at 2.3× on case 4/6 (`0485`); this arm establishes what a wrongly
computed `gsS` costs, which is what makes an undefined gate a hazard rather than a documentation gap.
Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; re-sample after and discard if the die moved.

Refuses to assume: that a free die stays free, or that a die may be substituted; that a mode number
absent from the documents is absent from the code (arm 2); that `gsS` means what its name suggests
(arm 3 reads rather than infers); that a dangling reference is harmless (arm 4 measures the one whose
target gate is undefined); that the three architecture spellings denote one target — each build echoes
the flag it compiled with.

## 5 · Checker — acceptance declared before the run
Verdict `mode_values_found` from arms 1 and 2, a set. Acceptance for `C-950fin-028` as read:
`|mode_values_found| == 5` in the documents and either 5 or 6 in the code. The OVERTURN fires iff a
`mode 2` is found in the documents.

Verdict `dangling_references` from arm 1, a list with source and target.

Verdict `gsS_defined` from arm 3 ∈ {`declared_and_computed`, `declared_only`, `absent`}.

Verdict `gate_cost(shape)` from arm 4, the ratio between the two forced branches.

The exit code is not the verdict: arm 1's script exits 0 whatever it finds, and arm 4's builds are both
correct. Guards: (1) the script fails red if it found fewer than six device templates or zero mode
occurrences — a regex that matched nothing would report empty differences, which is the blind-checker
species, and the six templates are the positive fixture it must find; (2) **the input that makes this
checker go red**: `mode 1`, which appears twice in the shelf and must be found by arm 1 — if the mode
scan misses it, the absence of mode 2 carries no information; (3) every result records the upstream
revision read, since an enumeration is a property of a revision.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement, and no script was run. The
roster's nine rows, the six-mode claim, the five mode values with their locations, the missing header,
the `gsS` gate in its three appearances, the two dangling references and the three architecture
spellings are file reads performed at drafting time, each re-verified against its file. The observation
that the templates, the modes and the technique names are three enumerations none of which is
coextensive with another is a comparison of upstream's own lists, not an observation of any tool's
behaviour. **That `mode 2` appears nowhere is a search result over this shelf at this revision, not a
proof that it does not exist elsewhere in the repository.**

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or run. The entry does not establish that mode 2 does not exist — only
that no document in this shelf names it while one claims six modes (`C-950fin-028`); arm 2 is what
would settle it. It does not establish that `scan_cummin_tiling.h` is absent from the wider repository
(`C-950fin-029`), only from this shelf's roster and directory. It does not establish what `gsS` is
(`Q-950fin-31`) or what a wrong value costs. It does not establish that `dav310` and `dav-3510` denote
different targets — they plausibly denote the same one under two spellings, which is exactly the
hazard `0421` and `0346` record and is why it is registered rather than resolved (`C-950fin-030`). It
does not evaluate any template's content; the six device templates' substance is carried at `0481`,
`0483`, `0484`, `0485`, `0486` and, from the analysis shelf, `0132`-`0139`. It does not check whether
the roster's file-to-header mapping is correct. No board token appears anywhere in the shelf except one
mention of `72 核的 A5` in `cum_core_partition_scan.md:77`, which describes another operator's core
truncation rather than any measurement's platform, so BOARD is `family-claimed(unverified)`; §4 arm 4
names 950PR/950DT only as where our run would happen. Nothing here is established for any 910-family
board.
