```
ID:        0018-usable-ub-is-248kb-on-the-950-family-and-doublebuffer-halves-it
LABEL:     boundary
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   verified — §4 Arm 2 run on 950PR 2026-08-25 via §5: `ub_bytes_reported` = 253952 (248 KB, `GetRuntimeUBSize`
           in every probe) ✓; `ub_bytes_double / ub_bytes_single` = 131072 / 262144 = 0.500 ∈ [0.45, 0.55] ✓
           (largest per-buffer `InitBuffer(que, 2, N)` 131072, 131104 refused; single-tensor ceiling 262144 from
           950:0209's identical bisect); red input: a single allocation of reported + 4096 = 258048 is GRANTED on this
           part (262144 is the ceiling, 0209) → **`query_not_binding`** as §5 declared — the 248 KB is the API report,
           the allocator binds at 256 KB. Arm 1 (ini) carried from 0209. Previously harvested.
BOARD:     950PR (measured 2026-08-25); 950DT unverified
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/vec.md:102-103 — "增大 tile 尺寸减少循环次数，降低流水启停开销（UB 容量：192KB / 910B2，248KB / 950） - 使能 DoubleBuffer 时，实际可用 UB 需除以 2"
INDEX:     means=`TQue<VECIN, 2>` with `InitBuffer(que, 2, N)`, both buffers' tails written and read back, fresh
           process per probe, 32-B bisection; `GetRuntimeUBSize()` echoed per probe; single-tensor ceiling from 0209
           conditions=CANN 9.1.0, 950PR, direct launch, plain vector kernel
           readouts: reported 253952; double-buffer per-buffer 131072 / 131104 (total 262144 / 262208); ratio 0.500
           time=2026-08-25
OVERTURN:  a runtime query of UB capacity on a named 950 board — `GetCoreMemSize(CoreMemType::UB)`
           or the platform ini the toolkit ships — returning anything other than 248 KB; or an
           allocation experiment in which a double-buffered queue admits more than half the
           single-buffer maximum, which would falsify the halving rule.
```

# 0018 · Usable UB is 248 KB on the 950 family, and DoubleBuffer halves it

## 1 · Claim
Measured on 950PR: the runtime reports **253952 B (248 KB)** of UB, and a two-buffer queue's largest
per-buffer allocation is **131072 B** — exactly half of the **262144 B** a single tensor can take (950:0209),
so double-buffering halves the usable extent to the byte. Upstream's two statements hold at their own
tiers. What the red input added: an allocation of `reported + 4096` = 258048 B is granted on this part,
so the reported 248 KB is **not the constraint that binds** — the allocator refuses at 262144, 8 KB above
the report (0209's two-tier finding, reached here through this entry's own declared branch,
`query_not_binding`). A budget computed from the report is conservative by 8 KB; a budget computed from
the bank total (256 KB) is exact for a plain kernel and 32 KB too large for a VF-bearing one (950:0238).

## 2 · The wrong branch this removes
Every tile budget in every technique card depends on this number, and it appears in the skill
as a bare literal with no provenance and no query. An agent that hardcodes 248 KB produces a
tiling model that is wrong on any board whose UB differs, and — worse — is wrong *silently*,
because an over-budget tile does not fail at the model, it fails at allocation or, if the model
rounded down elsewhere, produces a slower kernel that still runs. The halving rule compounds it:
a model built at 248 KB and then given DoubleBuffer has 124 KB, and the fusion red lines that
depend on "the intermediate must fit in UB" (0020, 0027) silently move.

The second wrong branch is believing the number *because it is repeated*. It is not consistent
inside this one skill: the reduction family's own measured example calibrates its five template
budgets at 192 KB for the same architecture. Two documents in one repo agreeing would be one
origin; two documents in one repo disagreeing is a live contradiction that only a runtime query
settles.

## 3 · Ground / Source
`vec.md:98-103`, the whole Tiling 修正建议 block, so the parenthesis is seen in its context:

> - 调整 UB 布局以支持更高效的 RegBase 访问模式
> - 调整 tile 粒度匹配 Vector 融合窗口
> - 增大 tile 尺寸减少循环次数，降低流水启停开销（UB 容量：192KB / 910B2，248KB / 950）
> - 使能 DoubleBuffer 时，实际可用 UB 需除以 2

The halving rule is repeated as a stop rule at `nobound-01:35` — PingPong 使能时实际可用 UB 需
除以 2，注意容量 — and as a red line at `vec-01:38` — 中间结果尺寸必须放得下 UB（含
DoubleBuffer 时可用容量减半）. Note that `nobound-02:81` corrects the *mechanism* behind that
rule without touching the number: physical buffer count comes from `InitBuffer`'s `BUFFER_NUM`,
while queue depth constrains only outstanding handles, so "enabling double buffering" and
"increasing queue depth" have different UB costs. That correction is entry 0019.

Conflicting versions, recorded and not adjudicated here (Art. 7). Inside this same skill,
`references/tiling/reduction/fallback/example/euclidean_norm/experience.md:5` states 平台：
Ascend 950 / arch35（dav-3510）… UB≈192KB under a banner saying its data are msprof on-board
measurements, and the reduction family's template budgets are calibrated at that value. The
tiling subtree's Python solvers default variously to 262144, 248*1024 and 192*1024 bytes with no
chip attached, and `tiling/sort/topk_host_tiling.md:209` gives the only chip-scoped form,
240 KiB usable of 248 KiB physical on DAV_3510 — which is a fourth number and the only one that
distinguishes physical from usable. This is register row C-004, extended by C-006; the tiling
subtree is another agent's scope and no entry is written on it here.

The counsel this book takes from the same skill: `tiling/sort/topk_host_tiling.md:81` uses
`GetCoreMemSize(CoreMemType::UB)` — query it, do not write it down.

## 4 · Procedure
Two arms. The first needs no card at all and should be run first, because it can settle the
number without a device.
```bash
# Arm 1 — installed-toolkit inspection, read-only, no execution on device.
# NOTE grep -r does not follow symlinked dirs in these trees; -R does.
T=/usr/local/Ascend/cann-9.0.0-beta.2
grep -Rn "GetCoreMemSize\|CoreMemType" $T/arm64-linux/asc/include | head
find $T -name "*.ini" -path "*platform*" | head        # platform_config ini files
grep -Rn "UB_SIZE\|ub_size\|Unified_Buffer" $T --include=*.ini | head
```
Arm 2 (later phase, needs a card, board token from the driver readout): in a minimal kernel,
call `GetCoreMemSize(CoreMemType::UB)` and print it; then allocate a single queue with
`InitBuffer(que, 1, N)` and bisect N to the largest value that initialises; repeat with
`InitBuffer(que, 2, N)`. Device selection per 0010: explicit visible-devices, occupancy recorded
either side, no assumption that the die is idle or that the board is 950PR rather than 950DT.

**As run (2026-08-25, job tque950, shared with 950:0019):** Arm 1 was already answered by 0209's ini read
(`ub_size=253952` in every 3510 ini). Arm 2: `GetRuntimeUBSize()` echoed from the kernel in place of the
host-side `GetCoreMemSize` (0209 measured that one: 253952 as well); `InitBuffer(que, 2, N)` bisected with
both buffers' tails touched and read back (fresh process per probe, 32-B steps); `InitBuffer(que, 1, N)`
not re-bisected — 0209's single-tensor bisect on the same allocator (262144 / 262176) is the reference and
the red input is evaluated against it: 253952 + 4096 = 258048 < 262144, therefore granted.

## 5 · Checker — acceptance declared before the run
Verdict variables `ub_bytes_reported` (from the runtime query), `ub_bytes_single` and
`ub_bytes_double` (from bisection). Acceptance, declared now: the upstream claim holds iff
`ub_bytes_reported` is 248 KB within the granularity the query reports, and
`ub_bytes_double / ub_bytes_single` lies in [0.45, 0.55]. Any other outcome is recorded as the
board's answer, and this entry is corrected in place rather than reinterpreted.

Exit code is not the verdict: a failed `InitBuffer` may abort the kernel, and an aborted kernel
is data, not an error — the bisection records the largest N that succeeded and the smallest that
did not, and reports both.

Red input: `InitBuffer(que, 1, ub_bytes_reported + 4096)`, which must fail. If it succeeds, the
query is not reporting the constraint that binds, and the whole arm is reported
`query_not_binding` rather than yielding a number.

## 6 · Evidence
RUN 2026-08-25, 950PR (idle before and after).

| quantity | value | source |
|---|---|---|
| `ub_bytes_reported` (`GetRuntimeUBSize`, plain kernel) | 253952 | every probe of this run |
| `ub_bytes_single` (largest single tensor granted / smallest refused) | 262144 / 262176 | 950:0209 §6, same allocator, same part |
| `ub_bytes_double` (largest per-buffer with BUFFER_NUM 2 / smallest refused) | 131072 / 131104 | this run (depth 2 and depth 4 identical) |
| ratio double / single | 0.500 | — |
| red input: single allocation of reported + 4096 = 258048 | granted (below the 262144 ceiling) | 0209's bisect brackets it |

Verdict: claim holds at its tiers (248 KB reported; halving exact); `query_not_binding` recorded.

## 7 · Scope limits — what this entry does NOT establish
950PR only; plain vector kernel (a kernel containing a SIMT VF sees a different ceiling — the launch grant
+ 8 KB, 950:0238); `TQue<VECIN>` only; the halving is measured at BUFFER_NUM 2 (BUFFER_NUM 3 gives 87360 ×
3 = 262080, 950:0019). Whether `GetCoreMemSize(UB)` and `GetRuntimeUBSize()` can ever differ on this part
is not probed (both read 253952 here and in 0209). Nothing transfers to the 910 book (RULES.md Art. 1).
