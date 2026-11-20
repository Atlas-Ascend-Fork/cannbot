```
ID:        0420-the-conversion-familys-fastest-measured-implementation-is-not-one-of-its-nine-strategies
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured by us
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/conversion/transpose_n_last.md:262-265 —
           "| 基线 DataCopyPad | 4D 连续写出 | 19.4 | 24.6 | / | N_LAST（未合并） | 6 维 strided 写 |
           58.9 | 124.1 | / | N_LAST（合并后预期） | 3 维连续写 | ~19 | ~25 | /
           | TQueBind 4D | 4D 连续写出 | 13.1 | 15.4 |" ; :267 — "TQueBind 更快是因为它在 4D 空间操作，
           天然利用了输出连续性，且 TilingData 更小（128B vs 972B）。"
SOURCE:    same shelf, conversion/guide.md:42-52 — the nine-strategy table (tilingKeys 10000–10008),
           which does not contain `TQueBind 4D`
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a transpose on a named 950 board at which one of the nine tabled strategies matches or beats
           a `TQueBind`-style 4-D implementation on the same shape, within the variance floor. The
           unrostered implementation would then not be uniquely best, and this entry's claim — that the
           family's own measurement points outside its roster — would be wrong for that shape.
```

# 0420 · The conversion family's fastest measured implementation is not one of its nine strategies

## 1 · Claim
Upstream asserts a nine-strategy transpose roster, tilingKeys 10000 through 10008, each with a template
file, a document and a TilingData structure. Upstream separately publishes a four-row measured table on
one operator, and the fastest row in it — `TQueBind 4D`, at 13.1 µs and 15.4 µs — is not one of the
nine. It beats the `DataCopyPad` baseline (19.4 / 24.6), beats the shipped N_LAST path by 4.5× and 8.1×
(58.9 / 124.1), and beats even the projection upstream gives for N_LAST after its recommended
dimension-merging repair (`~19` / `~25`). Upstream states two reasons — that it operates in a 4-D space
and so inherits output contiguity, and that its TilingData is 128 bytes against 972 — and does not add
it to the roster, give it a tilingKey, or explain its absence. Not established here.

## 2 · The wrong branch this removes
An agent asked to pick a transpose strategy reads the nine-row table, applies the routing conditions,
and emits a tilingKey. Nothing in that procedure can produce the answer the family's own measurement
says is fastest, because that answer has no key. The roster is complete as a *dispatch* enumeration and
incomplete as a *performance* one, and the two are presented as the same table.

The second wrong branch is reading the gap as an oversight and adding `TQueBind 4D` to the roster. It
may not be a strategy at all in the sense the other nine are: the nine share a host tiling entry point
and a `tilingKey_` assignment, and a `TQueBind`-based 4-D implementation may be a different *operator*
formulation — one that never enters the transpose dispatch because the case never reaches it. Upstream
gives no routing condition for it, no template, and no host function, which is consistent with that
reading. So the honest content is narrower and more useful: **on the one case this family measures, the
best implementation is outside the strategy space the family routes over**, and an agent that concludes
"the best of nine is the best available" has drawn a conclusion the evidence does not support.

## 3 · Ground / Source
The roster, `conversion/guide.md:42-52`, is nine rows keyed 10000–10008: `TENSOR_MOVE` (10000),
`SMALL_SHAPE` (10001), `CUT_ONCE` (10002), `CUT_TWICE` (10003), `N_LAST_TRANSPOSE` (10004), `BIG_DIM`
(10005), `GATHER_TRANSPOSE` (10006), `VCONV_TRANSPOSE` 5HD (10007), `VCONV_021_TRANSPOSE` (10008). Each
row carries a condition, a `.template` path, a document and a TilingData type. `TQueBind 4D` appears in
none of them, and `grep` over the family's twelve markdown files finds it only in the one table below.

The table, `conversion/transpose_n_last.md:258-267`:

```
以 batch_to_space 算子（perm=[2,3,0,4,1,5]，6D）为例，在 ascend950 上：

| 实现 | CopyOut 方式 | case2 aiv(us) | case12 aiv(us) |
|------|------------|--------------|---------------|
| 基线 DataCopyPad | 4D 连续写出 | 19.4 | 24.6 |
| N_LAST（未合并） | 6 维 strided 写 | 58.9 | 124.1 |
| N_LAST（合并后预期） | 3 维连续写 | ~19 | ~25 |
| TQueBind 4D | 4D 连续写出 | 13.1 | 15.4 |

> N_LAST 未合并时比基线慢 2-5 倍，根因就是 CopyOut 的 strided 写。合并后预期与基线持平，因为 CopyOut 变为连续写出。TQueBind 更快是因为它在 4D 空间操作，天然利用了输出连续性，且 TilingData 更小（128B vs 972B）。
```

Four ratios computed here from upstream's own figures, since upstream computes none of them:
`19.4 / 13.1 = 1.48` and `24.6 / 15.4 = 1.60` against the baseline; `58.9 / 13.1 = 4.50` and
`124.1 / 15.4 = 8.06` against the shipped N_LAST; and against the *projected* merged N_LAST,
`19 / 13.1 = 1.45` and `25 / 15.4 = 1.62`. So the family's recommended repair to its own strategy —
the dimension merging that `transpose_n_last.md:171-276` spends a hundred lines specifying — is
projected to reach parity with the baseline and to remain about 1.5× slower than the unrostered
implementation. That is the sharpest reading of this table and upstream does not state it.

Upstream's two stated reasons are worth separating because only one is about the strategy space.
`在 4D 空间操作，天然利用了输出连续性` is a claim about the *formulation*: a 6-D `perm` collapsed to
four dimensions has a contiguous output write by construction, which is exactly what the merging repair
tries to recover by analysis (`inv_perm` adjacency, `transpose_n_last.md:201-211`). `TilingData 更小
（128B vs 972B）` is a claim about *overhead*, and it connects to a measured cost elsewhere in the same
family: `transpose_small_shape.md:295` records that copying a 972-byte TilingData byte-by-byte at kernel
entry cost about 10 µs, reduced to about 4 µs when accessed directly from GM. Against a 13–25 µs total,
a TilingData difference of 844 bytes is not a rounding error, and the family measured it once in a
different strategy and never connected the two. Recorded in `harvest/standing/950-td.md` as
`Q-950td-09`.

Two absences bound how far this goes. `case2` and `case12` are never defined anywhere in the family —
no shape, no dtype, no batch size — so the table's two columns cannot be reconstructed. And no
profiling tool is named in any of the twelve files; the metric column reads `aiv(us)` with no
attribution, no repetition count and no variance. So the comparison is four single figures from an
unnamed instrument on two undefined cases.

Registered as `C-950td-025`: the family's fastest measured implementation is absent from the family's
own strategy roster, and the roster is presented as the selection space.

One structural note supporting the "different formulation" reading of §2. `transpose_n_last.md:265`'s
`TQueBind 4D` row shares its `CopyOut 方式` — `4D 连续写出` — with the baseline row, not with any
N_LAST variant. And `TQueBind<VECIN, VECOUT, 1>` is the construct N_LAST itself uses for its queue
(`transpose_n_last.md:72-88`), so the name denotes a buffer construct rather than a routing decision.
That is consistent with the row being a hand-written alternative implementation of the operator rather
than a tenth strategy, and it is why this entry claims an absence rather than a missing feature.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the case
if the die moved. Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over
median — upstream reports none, and the baseline-versus-`TQueBind` gap is only 1.5×.

**Arm 1 — rebuild the four rows.** Since `case2` and `case12` are undefined, construct a shape spread
for `batch_to_space` with `perm = [2,3,0,4,1,5]`, rank 6, at three sizes and two dtypes, and state
plainly that these are not upstream's cases. Build: the `DataCopyPad` baseline; N_LAST unmerged from
`templates/dav3510/transpose_n_last.template`; N_LAST with the dimension merging of
`transpose_n_last.md:201-211` implemented (upstream ships only a projection for this row); and a 4-D
`TQueBind` formulation per `:265`. One compiler pin, four md5s, host echo of the tilingKey, the
collapsed rank, the TilingData size in bytes, and the `CopyOut` loop depth. Elementwise comparison
against a CPU reference on all four. Record `aiv_time`, ≥10 iterations, first 5 dropped.

**Arm 2 — attribute the gap.** Upstream gives two reasons; separate them. Build a fifth variant:
`TQueBind` 4-D formulation with the 972-byte TilingData deliberately retained. If it lands near the
`TQueBind` row, the gap is the 4-D formulation; if it lands near the baseline, the gap is TilingData
size. Upstream conflates them in one sentence and this arm is what splits the sentence.

**Arm 3 — is the merged N_LAST projection right?** Upstream's `~19` / `~25` is a projection, marked as
one. Arm 1's third build is the first measurement of it. Report it against the projection and against
the baseline, since upstream predicts parity.

**Arm 4 — does any of the other eight strategies do better here?** Route the same shapes through
`SMALL_SHAPE`, `CUT_ONCE`, `CUT_TWICE` and `BIG_DIM` where their conditions permit, forcing selection
where necessary and echoing that the force happened. This is the arm that could overturn the entry: if
a rostered strategy matches `TQueBind`, the roster is not deficient at this shape.

Refuses to assume: that a free die stays free; that a die may be substituted; that this shape spread
reproduces `case2`/`case12` (it does not, and the report says so at every point); that `ascend950` is
this board; that a forced strategy is a routed one (the force is echoed and the point is labelled);
that `TQueBind 4D` is implementable for arbitrary `perm` (where it is not, that is reported as a scope
limit of the alternative rather than as a missing measurement).

## 5 · Checker — acceptance declared before the run
Verdict `best(shape)` = the implementation with the lowest median `aiv_time`, with the floor. Declared
before the run: this entry is **supported** iff `best(shape) == TQueBind_4D` on at least one shape and
no rostered strategy ties it within the floor there. The OVERTURN fires iff some rostered strategy
matches or beats `TQueBind_4D` on every shape — the roster would then be adequate and the table's
fourth row would be a redundant alternative rather than a gap.

Verdict `gap_source` from arm 2 ∈ {`formulation`, `tilingdata`, `both`}, decided by where the fifth
variant lands relative to the two it sits between.

Verdict `merged_parity` from arm 3: true iff merged N_LAST is within the floor of the baseline, as
upstream projects.

The exit code is not the verdict: a transpose with a wrong `perm` exits 0 and is fast — faster, in
fact, since it may skip the strided write that makes the correct version slow. Three guards. First,
every build on every shape is compared elementwise against a CPU reference and a build whose comparison
did not execute is `untestable`, never a row in `best`. This guard is load-bearing here rather than
routine: the entry's whole subject is an implementation that is faster because it writes contiguously,
which is also what a wrong implementation does. Second, **the input that makes this checker go red**:
the spread includes an identity `perm`, where every implementation degenerates to a copy and all five
**must** agree within the floor. If `TQueBind_4D` is faster even there, it is not doing the same work,
and every `best` verdict is void. Third, no point is reported without its floor, its md5, its echoed
tilingKey (or `forced`/`unrostered`), and its TilingData byte count — arm 2's verdict is unreachable
without the last of these.

## 6 · Evidence
NOT YET RUN by us — no readout of ours exists. Nothing in this file is our measurement. The four
timings are upstream's, on `ascend950`, for one operator and one `perm`, with no tool named, no
repetition count, no variance, and two undefined case labels; one of the four rows is explicitly a
projection. What was performed here at drafting time is arithmetic on those figures
(`19.4/13.1 = 1.48`, `24.6/15.4 = 1.60`, `58.9/13.1 = 4.50`, `124.1/15.4 = 8.06`,
`19/13.1 = 1.45`, `25/15.4 = 1.62`) and a `grep` over the family's twelve markdown files confirming
`TQueBind 4D` appears in no roster row.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured by us. The entry does not establish that `TQueBind 4D` is fastest on any board, or
on any shape other than the two undefined cases upstream reports. It does not establish that it is a
missing tenth strategy — §2 and §3 give the reading under which it is a different operator formulation
outside the transpose dispatch entirely, and upstream supplies no routing condition, template or host
function that would settle it. It does not establish which of upstream's two stated reasons accounts
for the gap (§4 arm 2 is the split, and upstream states them in one sentence). It does not establish the
`128B vs 972B` TilingData sizes, or that TilingData size costs time here — the ~10 µs figure that makes
that plausible is measured for a *different* strategy in a different file and is not transferred. It
does not establish the merged-N_LAST projection, which is upstream's estimate and has never been run.
It does not resolve `case2` / `case12`, which are undefined upstream, so §4 explicitly does not claim to
reproduce upstream's cases. It says nothing about the other eight strategies' relative performance,
none of which carries any measured figure anywhere in the family. `ascend950` is not a board token this
project recognises and the family's architecture markers are inconsistent (`0421`); BOARD is
`family-claimed(unverified)`. Nothing here is established for any 910-family board.
