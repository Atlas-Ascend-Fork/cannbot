```
ID:        0013-on-regbase-vf-paths-mte2-and-mte3-carry-only-tilingdata
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/metrics.md:84 — "RegBase（RVEC）范式靠向量 load/store 在 UB↔向量寄存器间搬数，**MTE2/MTE3 几乎只搬 TilingData**。因此 VF 路径的瓶颈判断**不要拿 MTE2/MTE3 当 VF 瓶颈**——先看 VECTOR 空泡与 SCALAR 准备"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an msprof capture of a pure-VF RegBase kernel on a named 950 board whose
           `aiv_mte2_ratio` scales with the input tensor size rather than staying at the
           TilingData floor — that would show MTE2 does carry payload on the VF path and the
           routing exemption is wrong.
```

# 0013 · On RegBase VF paths, MTE2 and MTE3 carry only TilingData

## 1 · Claim
Upstream asserts that in the RegBase (RVEC) paradigm data moves between UB and the vector
registers by vector load/store, so the MTE2 and MTE3 lanes carry almost nothing but TilingData;
and that consequently a bottleneck verdict for a VF path must not be taken from MTE2/MTE3 —
the reader looks first at VECTOR bubbles and SCALAR preparation. Not established here. The
statement is bare: no measurement, no shape, no proportion, and the word 几乎 is not quantified.

## 2 · The wrong branch this removes
The bound routing tree (0005) routes on MTE2 utilisation. On a RegBase VF kernel that routing
question is asked of a lane that, by this claim, is not carrying the workload. Two failures
follow. If MTE2 shows near zero, an agent concludes memory is not a problem and looks no
further — but the loads did happen, as vector loads inside the VF, invisible to the lane it was
watching. If MTE2 shows a moderate share because TilingData transfer is a fixed cost on a small
kernel, the agent routes to `memory.md` and starts merging copies that do not exist. Both
failures are silent: the CSV has values in it, the tree accepted them, a page was reached.

## 3 · Ground / Source
`metrics.md:75` already flags the exception inside the lane table itself — "MTE2 | GM→UB 载入 |
忙且接近跨度 → 访存 bound；VF 路径几乎只搬 TilingData" — and `metrics.md:84` states it as the
section's closing rule:

> RegBase（RVEC）范式靠向量 load/store 在 UB↔向量寄存器间搬数，**MTE2/MTE3 几乎只搬
> TilingData**。因此 VF 路径的瓶颈判断**不要拿 MTE2/MTE3 当 VF 瓶颈**——先看 VECTOR 空泡与
> SCALAR 准备。

The rest of the section (`:69-82`) is the five-lane reading guide: SCALAR = address/branch
preparation, SCALARLDST = scalar load/store and mask setup, MTE2 = GM→UB load, VECTOR = vector
execution and the lane to watch, MTE3 = UB→GM write-back; MTE2+MTE3 appearing in pairs means an
unfused store→load round trip.

The exemption is not propagated: `index.md:22` and `memory.md:5-9` state the MTE2 routing arm
with no VF caveat, and the mapping table at `index.md:62` sends 访存 bound to seven `mem-*`
cards, none of which mentions the VF path. The one place where an MTE2 ratio is explicitly
declared untrustworthy is the MC² pollution check (0060), which is a different mechanism
entirely — communication wait, not paradigm.

A consistent neighbour observation from the same file, `metrics.md:96`: in the RegBase
vocabulary translation table, RVECLD/RVECST map onto MTE2/MTE3 with the gloss 向量访存往返（VF
内为 UB↔寄存器）— i.e. the lane names are reused for a transfer that no longer crosses GM.

## 4 · Procedure
Later phase, needs a card. Board named from the driver readout.
1. Device selection per 0010; explicit visible-devices; occupancy before and after.
2. Build one elementwise kernel two ways over identical inputs: (H) high-level vector API path
   (`Mul`/`Add` over `LocalTensor`), (V) RegBase MicroAPI VF path over raw `__ubuf__` pointers,
   as in 0022's after-form.
3. Sweep the input tensor size over four sizes spanning a factor of 64, keeping the tiling shape
   family fixed.
4. Capture with msprof and record, per build and size: `aiv_mte2_ratio`, `aiv_mte3_ratio`,
   `aiv_vec_ratio`, `aiv_scalar_ratio`, `aiv_time`, and the absolute `aiv_mte2_time`.

## 5 · Checker — acceptance declared before the run
Verdict variable `mte2_is_tilingdata_only`, declared now: for build V, `aiv_mte2_time` must be
approximately constant across the four sizes — specifically, `max/min <= 1.5` over the sweep —
while for build H it must grow at least linearly, `max/min >= 8` over a 64× size range. The
claim is about payload, so the test is the *scaling* of the lane's absolute time with data
volume, not its share, because a share can fall for uninteresting reasons.

Exit code is not the verdict. Both scaling curves are printed in full, and if build V's MTE2
time grows with size the entry is restratified overturned with the curve in §6.

Red input: build H, whose MTE2 time must grow. If both builds look flat, the capture is not
resolving MTE2 at all and the result is `mte2_unresolved`, not a pass. This is the specific
blindness this checker is written against: a lane that reads near zero for want of instrument
rather than for want of traffic.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; the upstream sentence is bare and this entry inherits that. It does not
establish how much TilingData traffic there is, nor at what kernel size the fixed cost becomes
a visible share. It does not establish that VECTOR bubbles and SCALAR preparation are the right
first look — that is upstream's advice, carried untested. It applies only to kernels whose data
path is genuinely VF-resident; a mixed kernel that stages through UB with DataCopy still uses
MTE2 for payload, and nothing here says where the boundary is. No board, no shape, no CANN
version is implicated.
