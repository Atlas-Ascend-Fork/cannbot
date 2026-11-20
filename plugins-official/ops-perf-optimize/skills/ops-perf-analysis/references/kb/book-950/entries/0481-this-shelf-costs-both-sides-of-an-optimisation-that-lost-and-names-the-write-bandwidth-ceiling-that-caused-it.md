```
ID:        0481-this-shelf-costs-both-sides-of-an-optimisation-that-lost-and-names-the-write-bandwidth-ceiling-that-caused-it
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/scan/templates/cum_tile_resident_scan.md:51-59
           — "> ⚠️ **case 5/10 的 MTE3 占比 74~80% 已是写带宽天花板，不要再尝试通过减少写量来优化** /
           > （如"int32 索引直写 GM + plugin 侧延迟 Cast"）。实测该方向是**净负优化**—— /
           > plugin 侧 `indices.copy_(indicesI32.to(torch::kInt64))` 会启动独立 Cast kernel + /
           > TensorMove kernel，开销（case 5: 5269µs, case 10: 877µs）远超 kernel 侧 MTE3 /
           > 节省（case 5: ~900µs, case 10: ~165µs），总体退化 2.7x / 3.0x。 /
           > **int64 索引输出必须在 kernel 内 UB Cast 后直写 GM** … /
           > 这两个 case 在 tile 常驻 + ping-pong 后已接近 MTE3 带宽上限（~1.2 TB/s）， /
           > 进一步优化应转向 R 轴切核（减少单核负载）而非减少写量。"
SOURCE:    same file:47-49 — "后两个几乎没动——它们加完双缓冲后 `mte3` 单项就占到 74%/80%，是**纯写带宽
           受限**（int64 索引占总写量的 4/5）。所以：**先用「占比之和」决定要不要做，再用「最长单项」
           决定能做到哪**，理想重叠下的耗时 ≈ 总耗时 × 最长那条占比。" ; same shelf,
           templates/usage_guide.md:240-245 — the in-kernel int64 Cast rule with its vreg-alignment
           requirement
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a Cummin case on a named 950 board whose MTE3 share exceeds 74% and at which a further
           write-volume reduction — by any route, not only the plugin-side Cast — still improves
           end-to-end time beyond the variance floor. The "write-bandwidth ceiling" would then not be
           a ceiling, and the stop rule would be premature. Equally: an int32-to-GM plus host-side
           Cast route whose measured total is not 2.7-3.0× worse would falsify the costed figures.
```

# 0481 · This shelf costs both sides of an optimisation that lost, and names the write-bandwidth ceiling that caused it

## 1 · Claim
Upstream asserts that for two Cummin cases, after tile-resident scanning and ping-pong double
buffering, the MTE3 pipe alone occupies 74% and 80% of the time and the kernel is purely
write-bandwidth bound, with the int64 index output accounting for four fifths of the write volume.
Upstream asserts that a further optimisation aimed at that write volume — emitting int32 indices
straight to GM and casting to int64 on the framework side — is a **net-negative optimisation**, and
gives both arms as measured numbers: a plugin-side cost of 5269 µs and 877 µs against a kernel-side
MTE3 saving of about 900 µs and about 165 µs, an overall degradation of 2.7× and 3.0×. Upstream
asserts the mechanism: the plugin-side `indices.copy_(indicesI32.to(torch::kInt64))` launches a
separate Cast kernel plus a TensorMove kernel. Upstream asserts a stop rule and a redirect — do not
attempt to optimise these cases by reducing write volume, and turn instead to splitting the R axis
across cores. Upstream asserts a two-step method underneath: the *sum* of the four pipe occupancies
decides whether to overlap at all, and the *largest single* occupancy decides how far overlap can go.
Not established here.

## 2 · The wrong branch this removes
Without this entry an agent looking at a kernel whose MTE3 share is 80% does the obvious thing: reduce
the writes. Two thirds of the write volume is an int64 index tensor whose values fit in int32, so
emitting int32 and widening later is an obvious four-bytes-per-element saving. It is also, per
upstream, a 2.7-3.0× regression — because the widening does not disappear, it moves to a place where
it costs two extra kernel launches and a full extra pass over the tensor.

The normal checks do not catch it because the kernel-side measurement is *correct and favourable*. The
kernel really does write less. The kernel really is faster by ~900 µs. An agent measuring the thing it
changed sees a win, and the loss is in another process's timeline. This is the boundary-of-measurement
failure this book records at `0410` from the gather family and again at `0418` from this same shelf,
and it is the third instance.

The second wrong branch is stopping at the wrong ceiling. Upstream's stop rule is not "this kernel is
finished" — it is "this *dimension* of optimisation is finished", with a named alternative (split the
R axis so each core writes less in total). An agent that reads `不要再尝试` as "this case is done"
leaves the redirect on the table.

## 3 · Ground / Source
The disclosed net-negative, `reference/scan/templates/cum_tile_resident_scan.md:51-59`:

```
> ⚠️ **case 5/10 的 MTE3 占比 74~80% 已是写带宽天花板，不要再尝试通过减少写量来优化**
> （如"int32 索引直写 GM + plugin 侧延迟 Cast"）。实测该方向是**净负优化**——
> plugin 侧 `indices.copy_(indicesI32.to(torch::kInt64))` 会启动独立 Cast kernel +
> TensorMove kernel，开销（case 5: 5269µs, case 10: 877µs）远超 kernel 侧 MTE3
> 节省（case 5: ~900µs, case 10: ~165µs），总体退化 2.7x / 3.0x。
> **int64 索引输出必须在 kernel 内 UB Cast 后直写 GM**（见 usage_guide.md §3
> "索引直接产出 int64"），Cast 与扫描流水重叠、几乎零开销。
> 这两个 case 在 tile 常驻 + ping-pong 后已接近 MTE3 带宽上限（~1.2 TB/s），
> 进一步优化应转向 R 轴切核（减少单核负载）而非减少写量。
```

**A disclosed net-negative with both arms quantified is rare in this corpus.** `0328` records a
falsification list from another family and it carries no costs; this is the only place where a team
publishes an optimisation it tried, the number it saved, the number it paid, and the ratio. Both arms
are per-case, which is what makes the ratio checkable: case 5's `5269 / 900 ≈ 5.9` and case 10's
`877 / 165 ≈ 5.3` are the *arm* ratios, while `2.7×` and `3.0×` are the *end-to-end* degradations —
different quantities, and upstream states both without saying they are different. The arm ratios
exceed the totals because the totals include the unchanged work. Recorded so that a reader does not
read 2.7× as the ratio of the two costed numbers.

The reasoning the stop rule rests on, `:47-49`:

```
后两个几乎没动——它们加完双缓冲后 `mte3` 单项就占到 74%/80%，是**纯写带宽受限**
（int64 索引占总写量的 4/5）。所以：**先用「占比之和」决定要不要做，
再用「最长单项」决定能做到哪**，理想重叠下的耗时 ≈ 总耗时 × 最长那条占比。
```

Two decisions from one profile, and they use different reductions of it — the sum across pipes, then
the maximum over pipes. The second gives a *predicted floor*: `总耗时 × 最长那条占比`, so at 80% MTE3
the best achievable overlap leaves 80% of the current time. That is a falsifiable prediction and
`0488` carries the sum-versus-maximum method itself.

`~1.2 TB/s` is the only absolute bandwidth figure in the scan shelf. It is stated with no board, no
measurement method and no comparison against any published MTE3 figure, and this book's architecture
block carries no MTE3 bandwidth for any 950 board to check it against. Recorded as `Q-950fin-27`.

The alternative route upstream mandates instead, `templates/usage_guide.md:240-245`, is an in-kernel
UB Cast to int64 before the copy out, reusing the int32 work area because the 8-byte write pointer
trails the 4-byte read pointer — with the constraint that the work-area offset must be vreg (256 B)
aligned or an `R` that is not a multiple of 8 triggers `device error type 3, error code 507035`. So
the accepted design *also* saves nothing on write volume; it saves the extra pass.

`case 5` and `case 10` are cann-bench Cummin case identities. The same two cases appear in the
ping-pong table at `:44-45` as `[363,367,373]` and `[16384,16384]` — in `usage_guide.md:141-142` the
same two rows are labelled `10` and `5` respectively, so the case numbering maps and the shapes are
recoverable. Upstream never states the mapping in one place; it is recovered by comparing the two
tables' identical timings (500.7 µs / 2697 µs).

One repository, one origin (RULES.md Art. 3).

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind on three consecutive idle samples only; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Variance floor first, beside every point.

**Arm 1 — both arms, measured on the same clock.** The two named shapes, three builds: (a) in-kernel
int64 Cast per upstream; (b) int32 to GM plus a framework-side widening; (c) int32 to GM with no
widening at all, as a bound on what the kernel side could ever save. Report, per build: kernel time,
MTE3 bytes, MTE3 occupancy, **and end-to-end time including every kernel the framework launches**.
The whole point is that (b)'s cost is invisible to a kernel-scoped measurement, so the end-to-end
figure is the verdict and the kernel figure is the trap.

**Arm 2 — the ceiling's prediction.** Upstream predicts the best achievable time under ideal overlap
is `总耗时 × 最长那条占比`. For the two cases, compute that prediction from (a)'s profile, then apply
the redirect — split R across cores per `cum_core_partition_scan` — and see whether the result lands
near the prediction, below it, or not at all. This is where a stop rule becomes a testable claim
rather than advice.

**Arm 3 — the bandwidth figure.** Measure achieved MTE3 bytes per second for build (a) at the two
cases and compare against the `~1.2 TB/s` upstream states (`Q-950fin-27`). Report the method used to
derive it, since upstream gives none.

**Arm 4 — the vreg-alignment trap, retained because it is expected to bite.** Build (a) with the
int32 work-area offset unaligned to 256 B, at `R` not a multiple of 8, and record whether
`error code 507035` appears. If it does not, the constraint is either wider or narrower than
`usage_guide.md:245` states, which is a correction either way.

Refuses to assume: that a free die stays free, or that a die may be substituted; that kernel time is
end-to-end time (arm 1's whole design); that MTE3 occupancy means what its name suggests (`0317`'s
species — the metric name is reported); that the two case identities map to the shapes §3 recovers
(each run echoes its shape and its case id); that `~1.2 TB/s` is measurable the same way upstream
measured it; that a faster kernel is a faster program.

## 5 · Checker — acceptance declared before the run
Verdict `end_to_end_ratio(case) = t_total(b) / t_total(a)`, declared before the run with its floor.
Acceptance for upstream's figures: `end_to_end_ratio` in `[2.4, 3.3]` for the two cases — a band
around the stated 2.7× and 3.0×, written down now so a 1.5× result cannot later be reported as
agreement. The OVERTURN's second half fires iff `end_to_end_ratio ≤ 1 + floor`.

Verdict `kernel_saving(case) = t_kernel(a) − t_kernel(b)`, reported separately and **never combined
with the above into one number** — the two arms are the entry's subject and merging them destroys it.

Verdict `ceiling_prediction_error` from arm 2: `(t_after_redirect − 总耗时 × max_occupancy) / 总耗时`.
The OVERTURN's first half fires iff any write-volume reduction improves `t_total` beyond the floor at
an MTE3 share above 74%.

Verdict `achieved_mte3_bandwidth` from arm 3, with its derivation stated.

The exit code is not the verdict: build (b) is correct and its kernel is faster, which is exactly the
misleading result. Guards: (1) every build reports end-to-end time measured outside the process's own
kernel timers, and a build reported with only a kernel time is `untestable`, never faster — this is
the guard that would have caught the failure upstream is disclosing; (2) **the input that makes this
checker go red**: a case whose MTE3 share is *low* (one of the four cases in the ping-pong table that
improved by 25-31%), where reducing write volume should help and `end_to_end_ratio` should be below 1
— if (b) loses there too, the framework-side path is broken rather than merely expensive, and the two
headline cases prove nothing; (3) no point is reported without its case id, its shape, its dtype, its
occupancy metric names, its floor and the CANN pin.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The net-negative note with its
four costed numbers and two ratios, the write-bandwidth reasoning, the two-step method, the bandwidth
figure and the in-kernel Cast rule are file reads performed at drafting time. The arithmetic in §3 —
that `5269/900 ≈ 5.9` and `877/165 ≈ 5.3` are arm ratios distinct from the stated 2.7×/3.0×
end-to-end degradations — is a calculation over upstream's own numbers, not a measurement. The case-id
to shape mapping is recovered by matching identical timings across two of upstream's tables, and is
an inference from those tables rather than a statement upstream makes.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish any of the four costed figures, nor the
2.7×/3.0× degradations — upstream states them with a tool (`cann-bench`) and case identities but no
board, no repetition count and no variance. It does not establish the 74-80% MTE3 shares nor the
`~1.2 TB/s` ceiling (`Q-950fin-27`). It does not establish that no write-volume reduction can help;
upstream tested exactly one route and generalised the stop rule to all of them, which §4 arm 1's
build (c) is the bound for. It does not establish that the R-axis redirect works — that is
`cum_core_partition_scan`'s material and is `0482`'s neighbourhood. It does not establish the
`4/5` write-volume share of the index tensor. It does not cover the vreg-alignment constraint beyond
quoting it. The case identities are cann-bench's, and this book has no independent access to that
suite. No board token appears anywhere in the scan shelf except one mention of `72 核的 A5` in a
different file describing a different operator's defect (`0487`), so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT only as where our run would happen. Nothing here is
established for any 910-family board.
