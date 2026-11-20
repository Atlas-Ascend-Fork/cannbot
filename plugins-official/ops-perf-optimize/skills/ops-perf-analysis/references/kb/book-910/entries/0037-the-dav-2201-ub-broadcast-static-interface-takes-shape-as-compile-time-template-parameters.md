```
ID:        0037-the-dav-2201-ub-broadcast-static-interface-takes-shape-as-compile-time-template-parameters
LABEL:     knowledge
LEVEL:     L3 (data movement & layout)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/broadcast/ub-broadcast.md:112 — "DAV_2201/DAV_3510 均可使用，但 DAV_3510 建议优先使用动态接口……dim 和 axis 为编译期模板参数，仅支持 1D/2D、axis=0 或 1"; ibid:136 — "| **dtype（DAV_2201）** | int8_t, uint8_t, half, float |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a UB Broadcast on a named DAV_2201 board accepts a runtime-valued `dim` or `axis`, a rank above 2, an `axis` of 2, or a dtype outside {int8_t, uint8_t, half, float}.
```

# 0037 · The DAV_2201 UB Broadcast static interface takes shape as compile-time template parameters

## 1 · Claim
Upstream asserts that the UB Broadcast static interface — the only broadcast path available on
DAV_2201 per 0036 — carries `dim` and `axis` as compile-time template parameters, supports only 1-D
and 2-D shapes with `axis` of 0 or 1, and on DAV_2201 accepts the dtypes `int8_t`, `uint8_t`,
`half` and `float`. Not established here.

## 2 · The wrong branch this removes
Compile-time shape parameters change the shape of the kernel, not just of a call. An agent that
plans a dynamic-shape operator — one kernel serving many broadcast axes, dispatched at runtime —
must instead instantiate one template per (rank, axis) combination and dispatch between them. That
is a structural decision made at design time, and discovering it at implementation time means
rewriting the dispatch layer.

The combination with 0017 is the part worth flagging: template instantiation multiplies code size,
and code size is bounded by a 32 KB instruction cache. An agent that instantiates broadcast
templates across ranks, axes and four dtypes can push the kernel past the cache without ever
writing a large function. Two constraints from two different levels of the machine multiply here,
and neither document mentions the other.

The dtype list is the third branch: bfloat16 is absent from it. A pipeline that has standardised on
bf16 — common in training — has no listed broadcast dtype on DAV_2201 and must cast.

## 3 · Ground / Source
`ops/ascendc-tiling-design/references/broadcast/ub-broadcast.md`, whose title is "Broadcast - UB
Broadcast 静态接口（DAV_2201）", line 112 verbatim: "DAV_2201/DAV_3510 均可使用，但 DAV_3510 建议
优先使用动态接口（见文首链接）。dim 和 axis 为编译期模板参数，仅支持 1D/2D、axis=0 或 1。"

Line 136: `| **dtype（DAV_2201）** | int8_t, uint8_t, half, float |` — the per-architecture dtype
row. Note the column header names DAV_2201 explicitly, implying the DAV_3510 list differs; this
book takes only the row it is scoped to.

The API form is given at
`ops/ascendc-performance-best-practices/reference/broadcast/broadcast_design.md:30`:
`Broadcast<T,R>(dst,src,dstShape,srcShape,&tiling)` — two template parameters, consistent with the
"dim 和 axis 为编译期模板参数" statement. Same repo, one origin, and note the shape arguments are
runtime values while the rank and axis are not, which is the distinction an agent is most likely to
miss.

Availability context: this is the interface DAV_2201 is routed to by
`ops/ascendc-tiling-design/references/broadcast/patterns.md:62`, with a further fallback to plain
data-movement instructions when alignment constraints are unmet — so the static interface is not
guaranteed either, and the constraints that trigger the second fallback are not enumerated in the
sources surveyed for this book. That gap is recorded in §7 rather than filled.

## 4 · Procedure
Proposed, runnable later; not run. Most of this is compile-time and needs no card.

1. Compile arm, no device: attempt instantiations across the parameter space targeting
   `__NPU_ARCH__` 2201 — rank 1, 2, 3; axis 0, 1, 2; dtypes int8_t, uint8_t, half, float, bfloat16,
   int32_t. Record which combinations compile. The claim predicts a specific rectangle of successes,
   and the informative cells are the predicted failures: rank 3, axis 2, bfloat16, int32_t.
2. Header arm, read-only: `grep -Rn "Broadcast" "$ASCEND_HOME_PATH"/*/include` for the template
   declaration and any `static_assert` or enable-if constraints, with the header path and toolkit
   version. This is where the dtype list would be enforced and is a genuinely independent origin
   from this repo.
3. Device arm, on a named die (occupancy before and after, no substitution), only for combinations
   that compile: verify results bitwise against a host reference. A combination that compiles and
   computes wrongly is a worse finding than one that fails to compile and must be looked for
   explicitly rather than assumed away.
4. Code-size arm: record the device `.text` size per instantiation and the total for a dispatch
   layer covering all legal combinations, to be read against 0017's ICache figure.

## 5 · Checker — acceptance declared before the run
Verdict: the compile matrix `compiles(rank, axis, dtype)` and, for compiling cells,
`bitwise_correct(...)`.
PASS iff `compiles` is true exactly on {rank ∈ 1,2} × {axis ∈ 0,1} × {int8_t, uint8_t, half,
float} and false elsewhere, AND every compiling cell is bitwise correct.
The predicted-failure cells are this checker's positive fixtures: rank 3 and bfloat16 must FAIL. If
everything compiles, the constraint is not enforced by the type system and the entry's claim is
about documentation rather than about the API — reported as exactly that, since a consuming agent
then has no compile-time protection and needs the runtime arm.
A cell that compiles but is incorrect is reported separately from a cell that fails to compile;
collapsing them would hide the dangerous case inside the safe one.
Exit code is the observation in arm 1 only.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; per-architecture. This entry does not establish the alignment
constraints that trigger the further fallback to data-movement instructions (§3) — no source in
scope enumerates them, and that gap is the practical limit on using this interface. It does not
establish performance: nothing here says the static interface is fast, only that it is what is
available. It does not establish the DAV_3510 dtype list or the dynamic interface's behaviour. The
ICache interaction in §2 is an inference joining two entries and is not established by either.
