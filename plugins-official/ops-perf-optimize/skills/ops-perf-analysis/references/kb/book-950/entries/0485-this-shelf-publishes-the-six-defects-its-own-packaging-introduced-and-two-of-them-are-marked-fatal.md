```
ID:        0485-this-shelf-publishes-the-six-defects-its-own-packaging-introduced-and-two-of-them-are-marked-fatal
LABEL:     knowledge
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/scan/templates/usage_guide.md:271-274 —
           "## 6. 模板已知问题（从模板化验证中提取的 6 个坑） / > 以下问题来源于将单文件参考实现提取为
           `.template` 体系时发现的提取遗漏。 / > 模板文件中已修复，使用时如遇同类现象按此清单排查。"
SOURCE:    same file:276-283 — "### 坑 1（致命）：`AllocEventID` vs `FetchEventID` / ping-pong 双缓冲的
           事件 ID **必须用 `AllocEventID`**，不能用 `FetchEventID`。 / `FetchEventID` 返回该事件类型的
           「默认」ID，每次调用返回同一个值，导致 ping-pong / 两个 buffer 的事件互相 alias——
           `Wait(buf[0])` 吃掉 `Set(buf[1])` 的 flag，数据在 / 搬运中被覆写，**不报错，只出非确定性
           精度错误**。" ; :285-290 — "### 坑 2（致命）：`ScanRowRange` 缺少 lane 并行路径 …
           若只保留 Kogge-Stone，case 4/6（R=8192, mode 1）走纯 Kogge-Stone 的 / `log2(R)=13` 趟扫描，
           耗时 1786µs；走 lane 并行只要 770µs，差 2.3 倍。" ; :307-310 —
           "### 坑 6：`cum_tile_resident_scan` 重复类定义 / `cum_tile_resident_scan.template` 中可能有
           重复的 `class TileResidentScan {` 行， / 使用前删除重复行。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a fresh extraction of the same single-file reference implementation into templates that
           reproduces none of the six — the defects would then be one packaging run's accidents rather
           than a class the process produces. Equally: a seventh defect of the same kind found in the
           shipped templates would show the list is a snapshot rather than a closed set, which is what
           its own preface ("使用时如遇同类现象按此清单排查") implies and does not say.
```

# 0485 · This shelf publishes the six defects its own packaging introduced, and two of them are marked fatal

## 1 · Claim
Upstream asserts a six-item defect register whose stated origin is its own packaging process:
extraction omissions found while converting a single-file reference implementation into a `.template`
system. Upstream asserts the templates have been fixed and that the list is for diagnosing the same
symptoms in a consumer's own code. Upstream marks two items 致命, fatal. The first is an event-ID
allocation error — using `FetchEventID`, which returns one default ID per event type, instead of
`AllocEventID`, so a ping-pong pair's events alias and a wait on one buffer consumes the other's flag,
producing data overwritten in flight with **no error, only non-deterministic precision failures**. The
second is a missing conditional branch in the core scan function, which silently routes two named
cases down a `log2(R) = 13` Kogge-Stone path at 1786 µs instead of a lane-parallel path at 770 µs, a
factor of 2.3. The remaining four are a missing `Init()` call, a missing host tiling function, a
forced fallback parameter that must not be overridden, and a duplicated class declaration line the
reader must delete. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent takes a template directory as a finished artifact. Templates are packaged
precisely so that they can be copied, and the packaging step is invisible: what a consumer receives is
a `.template` file, not the single-file implementation it was cut from, so the seams are not visible
at the seam.

The specific wrong branch is the first defect. `FetchEventID` and `AllocEventID` both return an event
ID, both compile, and the difference only matters when two buffers need two IDs — which is exactly the
ping-pong case every performance path in this shelf uses. The failure has no error and is
non-deterministic, so a suite that passes once is not evidence, and a bisect over runs will not
converge.

The second wrong branch is reading a `致命` marker as the severity ordering. Defect 2 is marked fatal
and is a **2.3× slowdown**, not a wrong answer; defect 1 is marked fatal and is a silent wrong answer.
An agent triaging by the marker treats them alike. The register's own risk column does not separate
"produces wrong results" from "produces slow results", which is the same flattening this book records
for the matmul template's `[SAMPLE]` register (`0474`).

The third wrong branch is finishing the list. The preface says `使用时如遇同类现象按此清单排查` — if
you meet a similar symptom, work through this list — which is a diagnostic instruction, not a
completeness claim. Six defects found in one packaging run is a sample of what that process produces,
and upstream never says it looked for a seventh.

## 3 · Ground / Source
The register's preface, `templates/usage_guide.md:271-274`:

```
## 6. 模板已知问题（从模板化验证中提取的 6 个坑）

> 以下问题来源于将单文件参考实现提取为 `.template` 体系时发现的提取遗漏。
> 模板文件中已修复，使用时如遇同类现象按此清单排查。
```

**A shelf publishing the defects its own packaging introduced is rare in this corpus**, and the
disclosure is the entry's reason: the defects are not the operator's, they are the *distribution
format's*, and no other family in this repository documents that step at all. The register makes the
packaging step visible as a source of defects, which a consumer of any other family's templates has no
way to know.

The first fatal item, `:276-283`:

```
### 坑 1（致命）：`AllocEventID` vs `FetchEventID`

ping-pong 双缓冲的事件 ID **必须用 `AllocEventID`**，不能用 `FetchEventID`。
`FetchEventID` 返回该事件类型的「默认」ID，每次调用返回同一个值，导致 ping-pong
两个 buffer 的事件互相 alias——`Wait(buf[0])` 吃掉 `Set(buf[1])` 的 flag，数据在
搬运中被覆写，**不报错，只出非确定性精度错误**。

`AllocEventID` 从事件池分配唯一 ID，ping-pong 多 buffer 必须用它。
```

`不报错，只出非确定性精度错误` — no error, only non-deterministic precision errors. That is the
sharpest failure description in the scan shelf and it names the two properties that defeat testing:
silence and non-determinism. This shelf's ping-pong paths use four event pairs per buffer
(`cum_tile_resident_scan.md:82-89`), so the aliasing surface is eight IDs.

The second, `:285-290`:

```
### 坑 2（致命）：`ScanRowRange` 缺少 lane 并行路径

`ScanRowRange`（mode 1/3/4 的核心函数）必须包含 lane 并行条件分支：
`gsS > 0 → LaneParallelScan` 和 `gsS == 0 → KoggeStone` 两条分支。
若只保留 Kogge-Stone，case 4/6（R=8192, mode 1）走纯 Kogge-Stone 的
`log2(R)=13` 趟扫描，耗时 1786µs；走 lane 并行只要 770µs，差 2.3 倍。
```

This one carries a case identity, a shape, a mode, both timings and the ratio — the register's best-
evidenced row. Note `1786 µs` here against `约 1780 µs` at `usage_guide.md:110` for the same
case 4/6 comparison, and `约 770 µs` there against `770µs` here: the same measurement stated once
rounded and once not, in one file. That is not a divergence; it is worth noting only because `0482`
records three genuine divergences in this shelf and this is what a *non*-divergence looks like.

The remaining four, `:292-310`, are of a different kind — three are "you must call the thing the
template provides" (`Init()`, host `CalcTiling()`, and the `k = 0` fallback that must not be forced to
1 because a single row still exceeding UB triggers `device error 507035`), and one is a textual
artifact:

```
### 坑 6：`cum_tile_resident_scan` 重复类定义

`cum_tile_resident_scan.template` 中可能有重复的 `class TileResidentScan {` 行，
使用前删除重复行。
```

`可能有` — may have. The register's last item is hedged about whether the defect is present, in a
document that says the templates have been fixed. So the preface's `模板文件中已修复` and item 6's
`可能有` disagree about the state of the shipped artifact. Registered as `C-950fin-027`.

Item 4 also names a file the shelf does not contain: `使用 scan_cummin_tiling.h 的 CalcTiling()`
(`:299`) — `scan_cummin_tiling.h` appears in no roster row (`:9-19`) and in no directory listing of
this shelf, whose host-side tiling template is `scan_tiling.template` → `scan_tiling.h`. That is a
dangling reference and is carried with the shelf's other two at `0487`.

One repository, one origin (RULES.md Art. 3).

## 4 · Procedure
Two arms need no device; two need a named 950 board (950PR or 950DT). None is run in this phase.

**Arm 1 — the register against the artifact (no device).** For each of the six items, check the
shipped `.template` files for the defect: grep for `FetchEventID`, for a `ScanRowRange` without the
`gsS` branch, for a missing `Init()`, for a `CalcTiling` reference, for a forced `k = 1`, and for a
duplicated `class TileResidentScan {`. Report which are present. The preface says all six are fixed
and item 6 says one `可能有` — this arm settles `C-950fin-027` by reading, and it is the cheapest arm
in the entry.

**Arm 2 — a seventh (no device).** Diff the `.template` files against whatever single-file reference
implementation is reachable, and report every difference not accounted for by the six items. The
register is a sample of one extraction run; this arm is where its completeness is tested rather than
assumed.

**Arm 3 — the fatal one, made observable (device).** Build the ping-pong path twice, with
`AllocEventID` and with `FetchEventID`, and run each ≥200 times on identical input, reporting the
**fraction of runs that disagree** with a fixed reference and the distribution of the disagreement.
Upstream says non-deterministic; a fraction is the only honest measurement of a non-deterministic
defect, and a single run — pass or fail — establishes nothing.

**Arm 4 — the second fatal one (device).** Build `ScanRowRange` with and without the `gsS` branch and
time case 4/6 (`R = 8192`, mode 1). Upstream predicts 1786 µs versus 770 µs. Retained even though it
is expected to reproduce, because it is the register's only row with both arms measured and it is
therefore the row that calibrates how much of the shelf's timing transfers to this board at all.

Refuses to assume: that a free die stays free, or that a die may be substituted; that the templates
are in the state the preface claims (arm 1 checks); that six is the number of defects (arm 2); that a
green run means the event IDs are right (arm 3 reports a fraction over ≥200 runs, because that is what
non-determinism requires); that `gsS` has a defined meaning (`0487` — it is echoed, not assumed);
that a fatal marker orders severity (arms 3 and 4 measure two different kinds of failure).

## 5 · Checker — acceptance declared before the run
Verdict `present_in_shipped(item)` from arm 1, boolean per item, declared before the run. Acceptance
for the preface: all six absent. Any present item resolves `C-950fin-027` against the preface.

Verdict `undocumented_differences` from arm 2, a count and a list.

Verdict `disagreement_fraction(build)` from arm 3, over ≥200 runs. Declared now: the defect is
confirmed iff `FetchEventID`'s fraction is strictly between 0 and 1 — a fraction of exactly 1 would
mean the failure is deterministic and upstream's description is wrong in a way that matters, because a
deterministic failure is findable by a single test.

Verdict `kogge_vs_lane_ratio` from arm 4, against upstream's 2.3.

The exit code is not the verdict: the `FetchEventID` build exits 0 on most runs, which is the defect's
definition. Guards: (1) arm 3's verdict is a fraction and the checker fails red if fewer than 200 runs
were completed — a pass/fail on a non-deterministic defect is the blind-checker species, and the run
count is the positive fixture this arm must produce; (2) **the input that makes this checker go red**:
the `AllocEventID` build in arm 3, which must have a disagreement fraction of exactly 0 over the same
200 runs — if it does not, the harness has a second source of non-determinism and the `FetchEventID`
fraction measures both; (3) no result is reported without its run count, its shape, its dtype, the
echoed event IDs, the CANN pin and the compiler command.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement, and no template file was
diffed. The preface, the two fatal items with their mechanisms and timings, the four remaining items
and the dangling `scan_cummin_tiling.h` reference are file reads performed at drafting time. The
observation that the preface claims the templates are fixed while item 6 says a defect `可能有` is a
reading of two of upstream's own lines. The observation that `1786µs`/`770µs` here and `约 1780 µs`/
`约 770 µs` at `:110` are the same measurement stated twice with different rounding is a comparison of
two of upstream's own lines, offered as a contrast to the genuine divergences at `0482`.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, compiled or diffed. The entry does not establish that any of the six defects is
present or absent in the shipped templates (`C-950fin-027`); arm 1 is a file read and it has not been
performed. It does not establish that six is the complete set — the register is one packaging run's
output and upstream makes no completeness claim. It does not establish the `FetchEventID` mechanism or
its non-determinism, nor the 1786/770 µs pair, on any board; the scan shelf names none. It does not
establish that `AllocEventID` is the right API beyond upstream saying so; the installed toolkit was not
consulted for either symbol, which is a cheap next step this entry does not take. It does not cover
the `device error 507035` in item 5, which appears three times in this shelf under three different
causes and is not reconciled anywhere. It does not evaluate the templates' correctness beyond the six
named items. No board token appears in any cited passage, so BOARD is `family-claimed(unverified)`;
§4 names 950PR/950DT only as where our device arms would run. Nothing here is established for any
910-family board.
