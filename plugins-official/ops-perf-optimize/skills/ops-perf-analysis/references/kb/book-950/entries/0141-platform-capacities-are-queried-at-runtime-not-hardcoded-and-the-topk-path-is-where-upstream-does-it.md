```
ID:        0141-platform-capacities-are-queried-at-runtime-not-hardcoded-and-the-topk-path-is-where-upstream-does-it
LABEL:     procedure
LEVEL:     L0 (launch & host)
STRATUM:   overturned — 2026-08-24, by the entry's own OVERTURN condition: on 950PR the queried
           UB size (253952) differs from the measured allocatable ceiling (262144, every byte
           round-tripping) by 8192, which is 256× the 32 B alignment granularity. The query is
           not a sound substitute for a probe on this board; the discipline needs a probe
           attached. The killing observation is in §6. NOTE what is NOT overturned: querying
           still beats hardcoding — the query erred on the SAFE side (under-report), and every
           hardcoded literal C-006/C-007 record is still wrong.
BOARD:     950PR
SOURCE:    ops/ascendc-perf-optimize/references/tiling/sort/topk_host_tiling.md:78-83 —
           "从 `PlatformAscendC` 读取： coreNum = GetCoreNumAiv(); ubSize =
           GetCoreMemSize(CoreMemType::UB); ubBlock = GetUbBlockSize()，缺失时 DAV_3510 取 32B" ;
           sort/index.md:23 — "Python 输出中的 `sdk_queries` 必须在目标 CANN 中完成，不能用探索
           估计生成生产代码。"
INDEX:     killing run — Ascend950PR (soc Ascend950PR_9579), CANN 9.1.0
           ts 20260730_231653901, driver 25.7.rc1, 2026-08-24. Re-derive: (a) query
           GetCoreMemSize(UB) → 253952; (b) single-`TBuf` kernel, GM pattern → whole buffer →
           GM, host compares every byte: 262144 round-trips fully, 262176 is refused (507035);
           (c) ub_gap = 253952 − 262144 = −8192; ini ubblock_size = 32.
OVERTURN:  a runtime query on a named 950 board returning a UB size or core count that differs from
           the board's allocatable/usable value by more than the alignment granularity — the query
           would then not be a sound substitute for a measurement, and the discipline would need a
           probe attached rather than a query alone.
```

# 0141 · Platform capacities are queried at runtime, not hardcoded, and the TopK path is where upstream does it

## 1 · Claim
Upstream asserts that the TopK host tiling obtains its platform parameters by querying
`PlatformAscendC` rather than by using constants: the AIV core count from `GetCoreNumAiv()`, the UB
size from `GetCoreMemSize(CoreMemType::UB)`, and the UB block size from `GetUbBlockSize()` with a
DAV_3510 fallback of 32 B when the query is unavailable. Upstream further asserts, for the same
family, that the reference script's declared `sdk_queries` must actually be executed against the
target CANN installation and that exploratory estimates must not be used to generate production
code (`不能用探索估计生成生产代码`). Upstream applies the same discipline to API scratch sizes: the
`dChunk`/`G` search first screens candidates with an implementation-derived lower bound and then
re-checks each with the real `GetTopKMaxMinTmpSize` / Sort tmp query, cached in a 32-entry ring to
avoid running hundreds of expensive queries per tiling. Not established here.

## 2 · The wrong branch this removes
Every other family in this domain hardcodes what this one queries. Six scripts default `ub_size` to
`248 * 1024` and `core_num` to `64`; the convolution script uses `262144` and `32`; the scan script
passes `72` and `192 * 1024`; the reduction family's measured anchors assume 72 and 192 KB while its
own script says 64 and 248 KB (0131). Those are the four UB values and five core counts recorded
upstream-wide as C-006 and C-007, cited here and not duplicated. Under 0104's provenance rule all of
them are constraints whose assignment chain ends at a literal in a file, i.e. they are not the chip
specification fields they pretend to be — and every budget, gate and multi-core split built on them
inherits that.

So the wrong branch is not "using the wrong number", it is *having a number at all*. An agent that
substitutes a literal produces a plan that is correct on the machine the literal came from and
silently mis-sized everywhere else, with no marker anywhere in the plan saying which machine that
was. The query converts an unattributable constant into a value with a provenance the consuming
kernel shares.

The `sdk_queries` rule removes a second, sharper branch: treating a reference script's *estimated*
API scratch size as the real one. The script can compute a lower bound; only the SDK knows the
actual `GetTopKMaxMinTmpSize`. A plan built on the estimate fits on paper and overflows in the
kernel. The 32-entry ring cache is the detail that makes the rule practical — the honest version of
this discipline is expensive, and upstream states the cost and the mitigation rather than quietly
skipping the query.

The `GetUbBlockSize()` fallback shows the third correct move: when a query may be unavailable, name
the default *and* name the architecture it is valid for (`缺失时 DAV_3510 取 32B`). That is a scoped
default, which is a different object from a bare literal.

## 3 · Ground / Source
`sort/topk_host_tiling.md:76-86`, in full:

```
### 2.2 平台信息

从 `PlatformAscendC` 读取：

coreNum    = GetCoreNumAiv()
ubSize     = GetCoreMemSize(CoreMemType::UB)
ubBlock    = GetUbBlockSize()，缺失时 DAV_3510 取 32B

公共 tiler 和 fixed small-axis 先从物理 UB 预留 32 KiB SIMT 空间。fallback 按 240 KiB 预算搜索，
但不得超过平台 UB 扣除保留区后的可用容量。动态 UB 必须写入 launch 属性，不能只影响 Host 计算。
```

The `sdk_queries` rule, `sort/index.md:18-23`:

```
TopK Host Tiling 的完整复原对象由两部分组成：

- [topk_host_tiling.md](topk_host_tiling.md)：CANN 接线、精确 ABI、SDK 查询点与 C++ 复原步骤；
- [script/topk_tiling.py](script/topk_tiling.py)：可执行的 case 路由、切分、UB 和 workspace 参考模型。

两者必须一起使用。Python 输出中的 `sdk_queries` 必须在目标 CANN 中完成，不能用探索估计生成生产代码。
```

Restated at `sort/topk.md:21-23` and `:260-261`:
`脚本输出含 sdk_queries 时，必须先在目标 CANN 完成查询再生成生产实现。`

The API-tmp discipline with its cost mitigation, `sort/topk.md:161-163`:

```
对每个候选找 240 KiB UB 预算内的最大 G。先用实现推导的 API tmp 下界粗筛，再用真实
`GetTopKMaxMinTmpSize` / Sort tmp 查询复核；查询结果用 32 项环形缓存，避免 host tiling 重复执行
数百次昂贵查询。
```

The same document's own script does *not* follow the rule for its defaults:
`sort/script/topk_tiling.py:84-85` declares `core_num: int = 64` and `ub_size: int = 248 * 1024`.
Those are the values the query is supposed to replace, present as dataclass defaults in the family
that states the discipline. They are defaults for a reference model rather than production values,
and the `sdk_queries` sentence is precisely the fence around them — but an agent that runs the
script and reads its output has the literals, not the queries. This is the same placement failure as
0136: the rule and the artifact that violates it are different files.

A related instance of the same discipline elsewhere in this skill, outside this domain: the
technique library states that a vector lane count must be derived as
`GetVecLen()/sizeof(dtype)` and never from a borrowed constant. A prior survey identified that as
the one item to adopt as a rule without verification, and noted that another library's own canonical
template does the forbidden thing. This entry is the tiling-domain instance of that rule, and the
generalisation — *every* capacity constant is queried — is what makes it worth an entry rather than
a footnote.

## 4 · Procedure
Two arms. The first needs no device and is permitted in this phase; it has not been run.

Arm 1 — read-only, no device, no execution. Confirm the named accessors exist in an installed
950-era CANN toolkit and record their declaring header, signature and the toolkit pin:
`grep -Rn 'GetCoreMemSize\|GetCoreNumAiv\|GetUbBlockSize\|GetTopKMaxMinTmpSize' ` over the toolkit
include tree. `-R` and not `-r`: these trees contain symlinked directories that `grep -r` will not
follow, which would produce a false absence. If no 950 toolkit is installed, record that and this
entry stays as it is.

Arm 2 — query versus probe on a named 950 board (950PR or 950DT); never run in this phase. This arm
exists because a query is not a measurement: the runtime reports what it believes, and the claim
worth establishing is that what it reports is what a kernel can use.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved.

Print `GetCoreNumAiv()`, `GetCoreMemSize(CoreMemType::UB)` and `GetUbBlockSize()` with the toolkit
pin and board id. Then probe each independently. UB: walk a single buffer upward in 4 KiB steps
around the queried value, at each size launching a kernel that writes a known pattern across the
whole buffer and reads it back; the allocatable ceiling is the largest size where every byte
round-trips. Core count: launch a kernel that records `block_idx` from every block and count the
distinct values actually scheduled. Block size: transfer at 8, 16, 32 and 64 B granularity and
record which are accepted without padding. Then, for one batched-fallback TopK case, run the
`dChunk`/`G` search twice — once with the estimated API tmp lower bound only, once with the real
`GetTopKMaxMinTmpSize` — and record whether the selections differ and whether the estimate-only
selection runs correctly.

Refuses to assume: that the queried value is the usable value (that is the whole arm); that a free
die stays free; that a die may be substituted; that 950PR and 950DT agree on any of the three; that
the estimate-only arm will fail — it is retained in the report whether or not it bites.

## 5 · Checker — acceptance declared before the run
Verdict variables `ub_gap = ub_queried − ub_allocatable`, `core_gap = core_queried − core_scheduled`,
and `block_ok`. Declared before the run: the query discipline is sound iff
`|ub_gap| ≤ GetUbBlockSize()`, `core_gap = 0`, and the probed block size equals the queried one. The
OVERTURN fires iff `|ub_gap|` exceeds the block granularity — a query that over- or under-reports by
more than an alignment unit is not a substitute for a probe, and the discipline would then need a
probe attached. Verdict variable `tmp_estimate_suffices`: true iff the estimate-only search selects
the same `(dChunk, G)` as the real-query search on every tested case; a false value with a working
kernel is a weaker finding (the estimate is conservative) than a false value with a failing kernel
(the estimate is unsafe), and the two are reported separately.

The exit code is not the verdict: `grep` exits 1 on no match, which is the finding "not installed",
and a host that prints a plausible capacity exits 0 whether or not the number is usable. Two guards.
First, the UB probe's pattern check — an allocation that succeeds unbacked would report a ceiling
that does not exist, so a size counts only if every byte round-trips. Second, the core-count probe
must observe distinct `block_idx` values rather than trusting the launch parameter; a launch that
requested N blocks and scheduled fewer would otherwise make `core_gap = 0` by construction. Without
that, this checker would be reading only the lines it expects.

## 6 · Evidence
**KILLING OBSERVATION (2026-08-24, 950PR, CANN 9.1.0 — identity in INDEX):** Arm 2's UB half was
run to this entry's own standard. Queried: `GetCoreMemSize(UB) = 253952`. Probed: a kernel filling
ONE `TBuf` allocation from a GM pattern and copying every byte back out — `FULL-ROUNDTRIP
n=253952` ok, `FULL-ROUNDTRIP n=262144 every byte ok`, `REFUSED n=262176 sync=507035`; the
32 B-granularity bisect places the boundary at exactly 262144/262176, and the declared blinding
pass (64 KiB reserved first) moved the boundary by exactly 65536. So `ub_gap = −8192` against a
32 B granularity: the §5 OVERTURN clause fires. Direction matters and is recorded: the query
UNDER-reports the allocatable ceiling — budgeting by the query is safe and wastes up to 8 KiB;
the query is simply not a measurement of the ceiling, which is what this entry claimed it could
substitute for. (Full three-tier picture: 950:0209 §6.)

**Arm 1 (accessor existence, same installation):** all four named accessors exist —
`GetCoreMemSize`/`GetCoreNumAiv` (`platform_ascendc.h`), `GetUbBlockSize` in BOTH host
(`op_common/op_host/util/platform_util.h:75`) and kernel (`op_common/op_kernel/platform_util.h:30`,
`__aicore__ inline constexpr`) forms, and `GetTopKMaxMinTmpSize`
(`include/ascendc/include/adv_api/sort/topk_tiling.h:41,62`, two overloads). The first sweep
falsely reported the last one absent — the fault was the sweep's own output filter, not the
search scope; recorded in harvest/RUNS_20260824.md as an instrument self-report.

**Not run:** core_gap (block_idx scheduling census), block_ok (8/16/32/64 B transfer granularity),
tmp_estimate_suffices (TopK dChunk/G double search). They gate the PASS this entry can no longer
reach; they remain open questions for the successor discipline ("query for the floor, probe for
the ceiling"), not for this entry.

## 7 · Scope limits — what this overturn does NOT establish
The killing run is ONE part (950PR_9579), ONE pin (CANN 9.1.0), ONE allocation shape (a single
TBuf). It does not establish the gap's mechanism (reservation the runtime fails to enforce, or
capacity the API deliberately holds back — 950:0209 §7 carries that open safety question), does
not establish that the extra 8 KiB is safe to USE, and does not measure 950DT — the family-scoped
discipline died on a 950PR counterexample, as universals do; a 950DT run could only change the
successor rule's scope, not resurrect this entry. It does NOT rehabilitate hardcoding: every
literal in C-006/C-007 remains wrong, and the query remains the correct source for a BUDGET
(floor). What died is only the claim that the query substitutes for a measurement of the CEILING.
The unrun arms (core counts, block granularity, TopK tmp search) establish nothing either way
here. Nothing transfers to any 910-family board (RULES.md Art. 1).
