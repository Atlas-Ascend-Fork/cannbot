```
ID:        0026-replace-per-row-scalar-round-trips-with-broadcast-and-one-masked-write-back
LABEL:     knowledge
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/vec-04-scalar-roundtrip-vectorize.md:14 — "把「行内 reduce → per-row 标量 `1/scale` → per-row `Muls`」换成「reduce 到 lane0 → `Brcb` 复制到 8 lane → 批量 `Div` → stride-0 广播 `Mul` → masked `Mul` 一次写回」，循环内不再有任何标量拉取，V_S/S_V 同步随之消除"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board in which removing every per-row `GetValue`/
           `SetValue` round trip leaves `aiv_time` unchanged beyond run spread while the
           SCALAR/SCALARLDST lanes empty out — the round trip would then not be on the critical
           path, and the card's premise would be wrong for that operator class.
```

# 0026 · Replace per-row scalar round trips with broadcast and one masked write-back

## 1 · Claim
Upstream asserts (card vec-04, 性能数据 待实测) that a per-row pattern of "pull a scalar with
`GetValue`, compute on it, push it back with `SetValue`" costs a V_S/S_V synchronisation on each
side, repeatedly draining the vector pipeline; and that the pattern should be replaced by
reducing to lane 0, broadcasting with `Brcb` to 8 lanes, doing the division in a batch,
broadcasting with stride 0 across the row, and writing back once under a mask — after which the
loop contains no scalar pull at all. Not established here.

## 2 · The wrong branch this removes
The scalar round trip is invisible in a source review: `temp.GetValue(0)` is one call, and the
arithmetic it feeds is trivial. What it costs is not the call but the two synchronisations that
bracket it, once per row, each of which empties the vector pipeline. An agent profiling such a
kernel sees a busy SCALAR/SCALARLDST lane and a VECTOR lane full of holes, and — following the
scalar diagnosis page — starts looking for redundant scalar arithmetic, of which there is none.
The repair is not "less scalar work"; it is "no crossing between the scalar and vector domains
inside the loop", which is a different move and changes the data layout (an 8-lane broadcast
buffer, a masked write-back to a row slot) rather than the arithmetic.

## 3 · Ground / Source
`vec-04:6-10` diagnostic: SCALAR/SCALARLDST busy with V_S/S_V synchronisation visible; a per-row
`GetValue` … `SetValue` round trip inside the VF or row loop; typical in dynamic-quant and
per-row-scale operators, where a row-wise reduce produces a max and the per-row `1/scale` is then
applied with `Muls`.

`vec-04:18-27`, before and after:
> // before（每行）：Div 出 scale → SetFlag/WaitFlag<V_S> → scale = temp.GetValue(0)
> //                → SetValue(i, 1/scale) → Muls(scalar)   —— 每行一次标量 round-trip
> Brcb(brcbTmp, temp);                                   // lane0 max 广播到 8 lane
> Div(quantScaleTmp, constScale, brcbTmp, 8);            // 批量 const / max
> Mul(tempCast, tempCast, quantScaleTmp /*stride0*/);    // stride-0 把 8 lane 广播到 rowLen
> Mul(scaleLocal[i & ~7], brcbTmp, constInvScale, mask); // masked 一次写回 1/scale 到行号槽位

`vec-04:29` adds two companion moves: the intermediate cast `int32→half` may be narrowed to
`int16→half` because the post-quantisation range is within [-127,127] or [-7,7] and the cast
throughput doubles; and constant initialisation (`DuplicateConst`) should be hoisted to the top
of `Process` so it overlaps MTE2.

Stop rules, `vec-04:36-39`: `Brcb` and `WholeReduceMax` require 64-alignment, so the buffers must
be allocated aligned; narrowing a cast requires proving the value range; multi-dtype paths sink
the dtype difference into `if constexpr (IsSameType<...>)` rather than testing dtype in the hot
loop. Evidence line `vec-04:33`: msprof `aiv_time` plus SCALAR/SCALARLDST occupancy, **待实测**,
expectation that gain grows with row count and round-trip density. Case named at `:43`:
dynamic-quant DB symmetric merge.

## 4 · Procedure
Later phase, needs a card. Board token from the driver readout; device selection per 0010 with
occupancy recorded either side.
1. Build one per-row-scale operator two ways from a common tree: (R) per-row `GetValue`/
   `SetValue` round trip; (V) the broadcast-and-masked-write-back form. Record `md5sum` of both.
2. Sweep the row count over four values spanning a factor of 32 at fixed row length, then sweep
   row length at fixed row count — the card's expectation is that gain scales with row count, so
   the two sweeps separate that from a row-length effect.
3. Capture `aiv_time`, `aiv_scalar_ratio`, `aiv_vec_ratio`, five repetitions, median and spread;
   from the instruction trace, count V_S/S_V synchronisation events per row in each build.
4. Run the precision regression on both, including the narrowed-cast variant separately, so the
   cast narrowing is not bundled into the round-trip result.

## 5 · Checker — acceptance declared before the run
Verdict variables `gain(rows) = (aiv_time(R) − aiv_time(V))/aiv_time(R)` and
`sync_events_per_row(build)`. Acceptance of the mechanism, declared now: `sync_events_per_row(V)`
must be zero, `sync_events_per_row(R)` must be at least one, and `gain` must increase with row
count. A gain without the synchronisation count falling is a gain from something else — most
likely the hoisted constant initialisation — and is reported as unattributed rather than as
confirmation.

Exit code is not the verdict. The trace counter asserts it found the V_S/S_V event type at all
before reporting zero for build V; a counter that matches no event name would otherwise report
the perfect result for both builds, which is the blind-classifier species this book names.

Red input: build R, which must show a non-zero per-row count. If it does not, the counter is not
seeing the events and neither number is usable.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; the card's own evidence line is 待实测. No board, no shape, no dtype is
established. The 64-alignment requirement for `Brcb`/`WholeReduceMax` is asserted and unverified,
and the alignment unit is not stated (elements or bytes) — an ambiguity this entry carries rather
than resolves. The value-range argument for narrowing the cast ([-127,127] or [-7,7]) is specific
to the quantisation case named in the card and does not generalise. The stride-0 broadcast and
masked write-back are described for an 8-lane `Brcb` target; nothing here establishes the
behaviour for other lane counts or for dtypes whose block size differs.
