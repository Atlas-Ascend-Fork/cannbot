```
ID:        0145-fp16-topk-computes-in-fp32-and-int64-avoids-the-vendor-b64-path-because-both-carry-verified-defects
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/sort/topk.md:212-232 —
           "Fallback 内统一精确 cast 到 fp32 计算再 cast 回原类型。原因是当前高阶 TopK 的 16 位
           index 收集存在已验证缺陷" · "不要直接调用 vendor b64 TopK，它在目标版本存在 crash 风险。"
           · "range-check 必须逐 chunk 执行，覆盖全窄、全宽、窄宽混合和尾块" ·
           "RADIX_SELECT 返回候选不保证有序，最终写回前必须补排序。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured 16-bit-index TopK on a named 950 board returning correct indices across a
           case set including duplicates and tail blocks, or a vendor b64 TopK call completing
           without crashing on the pinned CANN version — either would retire the corresponding
           workaround.
```

# 0145 · fp16 TopK computes in fp32, and int64 avoids the vendor b64 path, because both carry verified defects

## 1 · Claim
Upstream asserts two dtype workarounds in the TopK fallback, each justified by a defect it says is
verified rather than suspected. For fp16 and bf16, the fallback casts exactly to fp32, computes, and
casts back, because the current high-level TopK's 16-bit index collection has a verified defect —
and upstream states that UB may not be reclaimed by restoring 16-bit computation unless a fresh
precision and performance A/B is completed. For int64, upstream asserts the vendor b64 TopK must not
be called directly because it carries a crash risk on the target version; instead each chunk is
dynamically range-checked, and a chunk whose actual values fit exactly in int32 is cast down and run
through `RADIX_SELECT` while one that does not is fully sorted with b64 `Sort(RADIX_SORT)` and
truncated. Upstream asserts the range check must run per chunk and cover all-narrow, all-wide, mixed
and tail-block cases, and must not be decided from the user's declared value range or from the first
chunk alone. Upstream asserts that `RADIX_SELECT` does not guarantee ordered candidates, so a sort
must be appended before write-back. Upstream asserts a padding rule — fill with the value that can
never be selected in the current direction, `-inf`/dtype-minimum for largest and `+inf`/maximum for
smallest — and a pair invariant: every compare, Gather, Sort, transpose, merge and tail move must
update the value and the original axis index together. Not established here.

## 2 · The wrong branch this removes
Both workarounds cost something visible and buy something invisible, which is exactly the shape of
rule an agent optimises away. Casting fp16 to fp32 doubles the compute buffer and adds two passes; an
agent looking for UB headroom in a `dChunk`/`G` search (0144) will find that promotion the largest
single item it can delete, and deleting it re-enters a path whose index collection is known broken.
Upstream pre-empts the move by name. Similarly, the int64 per-chunk range check looks redundant when
the caller has declared a value range, and skipping it is free until a chunk contains a wide value —
at which point the int32 cast silently truncates and the returned indices point at the wrong
elements.

The `RADIX_SELECT` ordering note removes a third: an agent that trusts a selection primitive to
return sorted output ships an operator that satisfies "the right k elements" and violates "in order",
which is part of this family's declared contract (`有序 TopK`, `sort/topk.md:3`). That failure passes
any test that compares sets rather than sequences.

The pair invariant is the general form of all three. TopK's output is two tensors that must stay
consistent through every transformation, and every stage listed — compare, Gather, Sort, transpose,
merge, tail move — is a place where a value can move without its index. A wrong index with a right
value is the failure mode this whole family keeps guarding against, and it is invisible to a
value-only comparison.

## 3 · Ground / Source
`sort/topk.md:210-232`, §6 in full:

```
## 6. Step 4：dtype、padding 与有序性契约

### 6.1 fp16 / bf16

Fallback 内统一精确 cast 到 fp32 计算再 cast 回原类型。原因是当前高阶 TopK 的 16 位 index 收集
存在已验证缺陷；不能为了节省 UB 直接恢复 16 位计算，除非重新完成精度和性能 A/B。

### 6.2 int64

不要直接调用 vendor b64 TopK，它在目标版本存在 crash 风险。每个 chunk 动态判断实际值能否精确
落入 int32：

- 能：cast 到 int32，走 RADIX_SELECT；
- 不能：该 chunk 走 b64 `Sort(RADIX_SORT)` 全排序后截断。

range-check 必须逐 chunk 执行，覆盖全窄、全宽、窄宽混合和尾块；不能只根据用户 value range 或
首块判断整行。RADIX_SELECT 返回候选不保证有序，最终写回前必须补排序。

### 6.3 padding 与 pair 不变量

padding 必须使用在当前方向下永远不会入选的最差值：largest 填 dtype 最小值或 `-inf`，smallest
填最大值或 `+inf`。NaN 语义必须与接口契约一致。任何 compare、Gather、Sort、transpose、merge、
尾块搬运都必须同时更新 value 和原始 axis index。
```

The int64 interception is also a routing rule, `sort/topk.md:78,85`: `dtype == int64` is the first
fallback-candidate condition, and `int64 则必须提前截获，以避开不稳定的 common 64 位路径` — so the
avoidance is implemented twice, once as a route and once as a per-chunk decision, and both are needed
because the fallback itself still meets int64 data.

The cost consequence is visible in 0144's cost model: `cost(int64) = 2 * chunks - 1`, justified as
`安全路径需要 chunk 选择和 running merge 的两类调用` — the two call classes are precisely the
range-check-and-select and the merge, so the workaround is why int64's cost is `G`-independent.

The UB consequence is visible in 0144's accounting list: `fp16/bf16：raw 输入、fp32 cast、回转输出`
and `int64：range-check / b64 Sort scratch` are conditional buffers that exist only because of these
two workarounds, and `条件 buffer 必须同时出现或同时消失`.

Two of the three defect claims are version-scoped without a version. `当前高阶 TopK` and
`它在目标版本存在 crash 风险` name a current and a target version and identify neither; nothing in
this family states a CANN version. The reduction family's case file does state one
(`CANN 9.0.0`, 0131) but that is a different family and a different platform statement, and Art. 2
forbids carrying it across. So both workarounds are justified by defects whose scope cannot be
determined from this tree — which is not a reason to remove them, and is a reason not to state them
as facts about any particular installation.

Upstream's own precedent for retiring such a workaround is stated in the same passage:
`除非重新完成精度和性能 A/B` — the condition is named in advance, which is what makes the rule
falsifiable rather than permanent.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The claims
are correctness claims about a toolchain version, so the procedure pins the version and then probes
the defects directly.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Record the CANN version and compiler pin with every result — these claims are
version-scoped and a result without a version establishes nothing.

Arm 1 — the 16-bit index defect, a poison arm. Build two fp16 fallback kernels: the promoted-fp32
path, and a 16-bit-computation path using the high-level TopK's 16-bit index collection. Run both on
a case set built to stress index collection: values with many duplicates (so ties decide indices),
a case where the selected k all lie in the tail chunk, a case where they are spread one per chunk, and
a case with `k = 1` and `k = 2048`. Compare values *and* indices elementwise against a CPU reference
implementing the declared tie and NaN semantics. The 16-bit arm is expected to produce wrong indices
and is retained in the report whether or not it does; the fraction of wrong indices and the first
wrong position are recorded, plus `aiv_time` for both arms so the UB saving the workaround forgoes is
quantified rather than assumed.

Arm 2 — the b64 crash risk, also a poison arm. Call the vendor b64 TopK directly on int64 input,
under a wall-clock timeout and with the process exit status captured, over 50 runs. Record crashes,
hangs, wrong results and clean completions separately. A clean 50/50 on the pinned version retires
the workaround *for that version only*, and the version is stated in the result.

Arm 3 — the per-chunk range check. Build the int64 path with the range check per chunk, and a variant
that decides once from the first chunk. Run both on four inputs: all-narrow, all-wide, mixed with the
wide values in the first chunk, and mixed with the wide values only in the tail. The first-chunk
variant is expected to fail on the last two and is retained regardless.

Arm 4 — `RADIX_SELECT` ordering. Capture the raw `RADIX_SELECT` output before the appended sort and
check whether it is already ordered; if it is, the appended sort is unnecessary on this version and
its cost is measured as the difference.

Refuses to assume: that a free die stays free; that a die may be substituted; that a defect present
on one CANN version is present on another (the version is recorded and the claim scoped to it); that
a value-correct result is index-correct; that a single run establishes a crash risk (arm 2 fixes 50
runs in advance); that the CPU reference's tie policy is right — it is validated against a
hand-computed case first.

## 5 · Checker — acceptance declared before the run
Verdict variables, all scoped to the recorded CANN version: `idx16_wrong_fraction` from arm 1,
`b64_failures` out of 50 from arm 2, `firstchunk_wrong_cases` out of 4 from arm 3, and
`radix_ordered` from arm 4. Declared before the run: the fp16 promotion is justified iff
`idx16_wrong_fraction > 0`; the b64 avoidance iff `b64_failures > 0`; the per-chunk range check iff
`firstchunk_wrong_cases > 0`; the appended sort iff `radix_ordered = false`. The OVERTURN fires on any
of these coming back clean — that workaround is then unnecessary on the pinned version, and the entry
is corrected in place with the version named. `ub_saving_forgone` reports what the fp16 promotion
costs, so a future A/B has a number to weigh.

The exit code is not the verdict for three of the four arms and *is* part of the observation for arm
2 — a crash is a non-zero exit or a signal, and that distinction is recorded rather than collapsed.
For arms 1, 3 and 4 the instrument is the elementwise comparison of both outputs, and the checker
fails red if only values were compared. Second guard, and the one that matters most here: the CPU
reference must itself be validated on a small hand-computed case with duplicates before it is used to
judge anything, because a reference with the wrong tie policy would report the correct kernel as
broken and score the broken one as fine.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The two defects are
upstream's assertions about unnamed CANN versions; this book has reproduced neither.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured. The entry does not establish that the 16-bit index collection is defective,
that the vendor b64 TopK crashes, or that `RADIX_SELECT` returns unordered candidates — all three are
upstream assertions scoped to `当前` and `目标版本`, versions this tree never names, so none of them
is established for any installation. It does not establish the UB cost of the fp16 promotion or the
time cost of the appended sort. It does not establish that the padding rule is complete for NaN:
upstream says NaN semantics must match the interface contract and does not state the contract. It
does not carry the `CANN 9.0.0` figure from the reduction family — that is a different family's
platform statement and Art. 2 forbids the transfer. `Ascend 950 / DAV_3510` names an architecture, not
a board, so BOARD is `family-claimed(unverified)`; §4 names 950PR/950DT because that is where our run
would happen. Nothing here is established for any 910-family board.
