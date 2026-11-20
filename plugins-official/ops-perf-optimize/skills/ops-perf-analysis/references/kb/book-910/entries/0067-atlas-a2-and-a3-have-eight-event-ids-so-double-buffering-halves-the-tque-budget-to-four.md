```
ID:        0067-atlas-a2-and-a3-have-eight-event-ids-so-double-buffering-halves-the-tque-budget-to-four
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-buffer.md:87 — "| Atlas A2/A3 系列 | 8 | 8 |"; ibid:90-91 — "不开启 Double Buffer（num=1）：最多可申请 8 个 TQue / 开启 Double Buffer（num=2）：每个 TQue 占用 2 个 buffer，最多只能申请 4 个 TQue"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a fifth `TQue` with `InitBuffer(que, 2, size)` initialises and works on a named DAV_2201 board, or a ninth single-buffered `TQue` does.
```

# 0067 · Atlas A2 and A3 have eight event IDs, so double buffering halves the TQue budget to four

## 1 · Claim
Upstream asserts that the Atlas A2/A3 series has 8 event IDs and therefore a maximum of 8 `TQue`
objects, and that enabling double buffering (`InitBuffer(que, 2, size)`) makes each `TQue` consume
two buffers so that **at most 4** may be allocated. Upstream gives the earlier Atlas training series
4 event IDs and 4 TQues, and the inference series 8. Not established here.

## 2 · The wrong branch this removes
This is a resource ceiling that no capacity calculation reaches. An agent budgets UB in bytes
(0003: 192 KB) and satisfies itself that five double-buffered queues fit — five 16 KB queues at
`num=2` is 160 KB, comfortably inside. The bytes fit and the allocation still fails, because the
binding constraint is the **event-ID count**, not the memory.

The trap sharpens with double buffering because that is a performance fix an agent applies *late*.
A kernel with six working single-buffered queues is inside the limit of 8; turning on double
buffering to hide copy latency (0042, 0043) silently doubles the demand to 12 and breaks a kernel
that worked. The change that broke it is one parameter in `InitBuffer`, and the error surfaces at
initialisation, far from any statement about queues.

The design consequence, which upstream does not draw: with only four double-buffered queues, an
operator with many distinct inputs must merge queues rather than add them — batching several
same-lifetime tensors into one buffer — or accept single buffering on the less critical paths. That
is a structural decision, not a tuning one, and it wants to be made before the kernel is written.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-buffer.md` §"TQue Buffer 数量限制", lines 82-91,
verbatim in full:
```
| 产品系列 | eventID 数量 | 最大 TQue 数量 |
| Atlas 训练系列 | 4 | 4 |
| Atlas 推理系列 AI Core | 8 | 8 |
| Atlas 推理系列 Vector Core | 8 | 8 |
| Atlas A2/A3 系列 | 8 | 8 |
```
"**注意**：
- 不开启 Double Buffer（num=1）：最多可申请 8 个 TQue
- 开启 Double Buffer（num=2）：每个 TQue 占用 2 个 buffer，最多只能申请 4 个 TQue"

with the worked failure at lines 95-99 — four `InitBuffer(queN, 2, size)` calls marked ✅ and the
fifth marked "❌ 超过限制".

Note the row scoping: "Atlas A2/A3 系列" is exactly DAV_2201 per 0001, and the table separates it
from both the earlier training series (4) and the inference series (8). This is one of the small set
of upstream statements that names our family in its own row.

The mechanism named is the **event ID**, which ties this to the intra-core synchronisation
resource: `ops/ascendc-performance-analysis/references/metrics_reference.md:431` describes
`EventID` as obtained via `AllocEventID`/`FetchEventID` and released immediately after use, and
`:436` reserves TEventID 6 and 7 ("系统预留"). Same repo, one origin. **If 6 and 7 are reserved out
of eight, the usable pool would be six, not eight** — which does not match the table's 8, and
upstream reconciles the two nowhere. The reservation note says 不建议 (not advised) rather than
forbidden, which may be the gap. Recorded rather than resolved; the claim-card
`ascendc-performance-analysis--001` holds the reservation fragment and this tension is why it was
not promoted.

`num` versus `depth` is 0043's claim and this entry depends on it: the count that matters here is
`InitBuffer`'s `num`, not the template `depth`. Same file, line 49: "**注意**：`depth` 与 Double
Buffer 无关。"

## 4 · Procedure
Proposed, runnable later; not run. Most of this needs no measurement — it is a capacity probe.

1. Name the die; occupancy before and after; no substitution.
2. Ladder arm: allocate N `TQue<VECIN,1>` with `InitBuffer(que, 1, small)` for N = 7, 8, 9, and
   record at which N initialisation or launch fails. Keep the total bytes far below UB so that
   memory is never the binding constraint — that separation is the point of the experiment.
3. Double-buffer arm: the same ladder with `InitBuffer(que, 2, small)` for N = 3, 4, 5.
4. Reserved-ID probe, which tests the tension in §3: repeat arm 2 while explicitly consuming
   TEventID 6 and 7 via `AllocEventID`, and see whether the ceiling drops from 8 to 6.
5. Record the exact failure mode at the ceiling — silent, error return, or launch fault — since
   upstream marks it "❌" without saying what happens.

## 5 · Checker — acceptance declared before the run
Verdict variables `max_tque(num=1)` and `max_tque(num=2)`.
PASS iff `max_tque(1) == 8` and `max_tque(2) == 4`.
Gate, run first: total UB consumed at the ceiling must be well under 192 KB. If it is not, the
failure could be memory rather than event IDs and no verdict is issued — this is the check that
stops the experiment from confirming a limit it did not isolate.
Red inputs: a ceiling of 6 (which would mean the reserved TEventIDs come out of the same eight and
the table is wrong), or no ceiling at all below memory exhaustion.
`reserved_effect` from arm 4 is reported with no declared expectation; it is the arm that would
resolve §3's tension, and it is labelled as testing a question upstream does not answer rather than
a claim upstream makes.
Exit code is not the verdict; an allocation ceiling may present as a launch failure whose exit code
does not distinguish causes.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. "Atlas A2/A3 系列" is two product lines spanning six parts, not
a board. This entry does not resolve whether the reserved TEventID 6 and 7 come out of the same
eight (§3) — the two upstream statements are not reconciled and §4 arm 4 is what would settle it.
It does not establish whether `TBuf` consumes event IDs; upstream's table counts `TQue` only, and a
kernel mixing both is not covered. It does not establish the ceiling for queues at `num=3` (triple
buffering), which `double_buffer_design.md:53` mentions for Cube+Vector fusion. It does not say what
happens at the ceiling.
