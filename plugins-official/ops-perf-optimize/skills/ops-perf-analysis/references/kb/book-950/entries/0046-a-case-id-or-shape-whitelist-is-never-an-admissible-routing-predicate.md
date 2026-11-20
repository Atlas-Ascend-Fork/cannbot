```
ID:        0046-a-case-id-or-shape-whitelist-is-never-an-admissible-routing-predicate
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-05-l2-bypass-one-shot.md:39 — "**没有可证明的无复用谓词就不能开 bypass**；禁止按 case ID、固定 shape 列表或一次 profiling 结果硬路由"
           ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-07-identity-pure-copy.md:44 — "必须保留 general fallback 并让 tiling 以运行时谓词路由，不能用 CSV 行号或测试 shape 白名单"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a routing rule expressed as a shape whitelist that is shown, over a case set drawn
           independently of the one that produced it, to select the fast path exactly when the
           semantic predicate would — the whitelist would then be a compressed predicate rather
           than an overfit, for that operator.
```

# 0046 · A case-ID or shape whitelist is never an admissible routing predicate

## 1 · Claim
Upstream asserts, in two independent cards of this library, the same prohibition: a fast path may
be entered only under a predicate that can be proved from the shape, layout, axes, attributes and
schedule at run time, and never by case ID, by a fixed shape list, by a CSV row number, or by a
single profiling result. Upstream asserts the corollary that a general fallback must always remain
and that tiling does the routing. Not established here; the prohibition is a discipline, and what
this entry adds is a way to test whether a given predicate obeys it.

## 2 · The wrong branch this removes
Whitelists arise from success. A team measures the benchmark set, finds the fast path wins on
eleven of twenty cases, and encodes those eleven. Every check then passes: the benchmark improves,
no case regresses, the diff is small and readable. What has been built is a lookup table of one
experiment's results, and its failure mode is invisible by construction — it can only be seen on
inputs nobody measured, where the fast path is either missed (a silent loss) or taken wrongly (a
silent error, since the fast path usually omits the general path's checks).

The distinguishing question is stated in the cards and is easy to apply: can the condition be
evaluated for an input the author never saw? "M ≤ tileM and one wave covers the expert" can.
"case_id ∈ {3,7,11}" cannot. A shape list is the ambiguous middle — admissible only if the shapes
are the enumeration of a semantic property, in which case the property should be written instead.

## 3 · Ground / Source
`mem-05:39`, the L2-bypass card's first stop rule, quoted in SOURCE, in the context of `:31`, which
shows the alternative: a predicate assembled from `coversWholeProblem`, `m <= tileM`, physical row
alignment, the user switch, working set against L2, `baseM` full load, sliding-window block count
and L1 slice alignment.

`mem-07:44`, the identity-fast-path card's third stop rule, quoted in SOURCE, in the context of
`:21-22`, where the predicate is
`isIdentity = SameLogicalIndexMapping(inputShape, outputShape, axes, layout)` and the tiling key is
selected from it.

The same discipline in weaker form elsewhere in the library: `mem-06:41` requires the contiguity
predicate to cover destination monotonicity, absence of holes, absence of aliasing and completeness
of this round's result rather than "logical token contiguity"; `mem-01:41` forbids judging
contiguity from logical shape; `vec-06:37` notes that a kernel branch is useless unless the host
dispatch threshold admits traffic to it — the same routing layer, from the other direction.

Recorded here as a rule because it is stated twice, in cards written by different hands (their
evidence style differs), about different mechanisms, with the same shape. It is also the one place
where this library's discipline exceeds its own practice: the MC² search's P4 predicate (0066) is
a semantic predicate that excludes every case it was meant to admit, which is the opposite defect —
a predicate so general it is vacuous.

## 4 · Procedure
This is a rule about predicates, so its procedure is a static audit plus a generalisation test.
Arm 1 needs no device.
```bash
# Arm 1 — find routing decisions that mention case identity or literal shapes.
grep -rn "case_id\|caseId\|csv\|CSV_ROW\|shape == \|shapeList\|kWhitelist" <kernel-and-tiling-src>
grep -rn "TILING_KEY\|tilingKey" <tiling-src> | head -40   # then read each key's condition
```
Arm 2 (later phase, needs a card; device selection per 0010, board token from the driver): for a
given fast-path predicate, build the operator and evaluate it over two disjoint case sets — the set
the predicate was developed on, and a second set generated independently by sampling the shape
space (including shapes no benchmark contains). Record, per case, which path ran and whether it
was the faster of the two.

## 5 · Checker — acceptance declared before the run
Verdict variables `route_correct(set)` = the fraction of cases where the path taken is the faster
one, computed separately for the development set and the held-out set. Acceptance:
`route_correct(held-out) >= route_correct(development) − spread`. A predicate that generalises
loses nothing off its development set; a whitelist collapses. Second verdict `unsafe_routes` = the
number of held-out cases where the fast path ran and produced a wrong result — this must be zero,
and it is reported separately because a wrong answer is not a slow answer.

The exit code is not the verdict. Both path selection and correctness are recorded per case, so a
predicate that is never true on the held-out set — a fast path effectively dead — is reported as
`fast_path_unreached` instead of scoring a perfect routing accuracy by abstention.

Red input: a deliberately constructed whitelist predicate over the development set. It must show
the collapse. If it does not, the held-out set is not independent of the development set and the
audit is void.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. It does not establish that any particular predicate in this library generalises —
only how to find out. It does not settle the ambiguous middle case where a shape list enumerates a
genuine semantic property. The static arm's patterns are illustrative and will miss a whitelist
expressed as a lookup table or a hash. No board, operator or shape space is implicated; the rule is
about the form of a condition, not about hardware.
