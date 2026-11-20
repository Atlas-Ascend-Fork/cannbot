```
ID:        0136-the-scan-reference-script-emits-the-one-template-its-own-flow-document-forbids-on-a-performance-path
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/scan/fallback/script/scan_tiling.py:36,87 —
           "template: str          # \"streaming\" | \"oneway\" | \"twoway\" | \"core_partition\"" ·
           "template = \"streaming\" if with_index else (\"oneway\" if n * 4 > 256 // 4 else
           \"twoway\")" ; scan/fallback/tiling-flow.md:121 — "| 流式（streaming） | ✅ | 任意 |
           逐 r 切片（不必全载） | 够满核 | 常驻 running-(val,idx)，仅作参考实现，**勿用于性能路径** |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured Cummin/Cummax case on a named 950 board where the streaming template the
           script emits matches the tile-resident or lane-parallel template the flow document
           selects — the script's output would then be a legitimate plan and this trap would not
           exist.
```

# 0136 · The scan reference script emits the one template its own flow document forbids on a performance path

## 1 · Claim
Upstream asserts, in the scan flow document's template table, that the streaming template is a
reference implementation only and must not be used on a performance path
(`仅作参考实现，勿用于性能路径`), routing indexed operators instead to the tile-resident scan
(`N > 1`) or to one of three `N == 1` modes. Upstream's reference script in the same directory
declares exactly four template values — `streaming`, `oneway`, `twoway`, `core_partition` — and
returns `streaming` for every indexed operator that does not trip the cross-core borrow condition.
The tile-resident, lane-parallel and Kogge-Stone templates that the flow document routes indexed
operators to are absent from the script's vocabulary entirely, as are the `mode` field and the
three-level `N == 1` decision. The script's own docstring states the mapping it implements:
`带索引（min/max）→ 流式模板；否则 oneway/twoway`. Not established here.

## 2 · The wrong branch this removes
The script is the executable artifact in this family and the flow document is 345 lines of prose
and pseudocode. An agent asked for a Cummin tiling that runs the script gets `template=streaming`,
which is a legal, complete, plausible answer — and which upstream's own document says is the wrong
answer for a performance path, quantifying the gap elsewhere as `实测慢 8~50 倍` for the
degenerate per-`r` form and `约 230µs` on a million 1D points against a cross-core alternative
(0132, 0134). The agent has no signal that anything is missing: the script has no TODO, no warning,
and its `__main__` demo prints `streaming` for three of its five demonstration cases, including two
labelled as representative cann-bench Cummin cases.

This is the general failure this book calls placement: the rule exists, it is correct, and it lives
in a file that the operation which violates it does not open. The repair is not diligence — an
agent cannot be told to remember a rule it never reads — it is that the script and the document
must not be separately authoritative. Recording it as a claim is the interim measure; the
replacement skill's version of this script must either implement the routing or refuse.

A second wrong branch follows from the same gap: an agent that trusts the script will also trust
its *other* outputs. The script's borrow-R threshold (4096) and segment length (1024) disagree with
the document's (16384, 8192) — 0135 — and its N-width test is the only place the `VREG/4` boundary
appears as executable code. An agent that has accepted `streaming` has no reason to doubt the rest.

## 3 · Ground / Source
The script's template vocabulary, `scan/fallback/script/scan_tiling.py:34-44`:

```python
@dataclass
class ScanTiling:
    template: str          # "streaming" | "oneway" | "twoway" | "core_partition"
    m: int; r: int; n: int
    mBlk: int; nTileLen: int
    mOuter: int; nOuter: int
    totalWork: int
    blockDim: int
    with_index: bool
    rBorrow: int = 0       # core_partition 时的 R 分段数
```

The selection line, `:87`:

```python
    template = "streaming" if with_index else ("oneway" if n * 4 > 256 // 4 else "twoway")
```

The docstring that states the mapping, `:48-51`:

```python
    """
    op_type: 'sum'|'prod'|'min'|'max'|'logcumsumexp'
    带索引（min/max）→ 流式模板；否则 oneway/twoway。并行度不足 + 大 R → core_partition。
    """
```

The demo block, `:93-106`, which prints `streaming` for three of five cases including two
explicitly labelled Cummin representatives:

```python
    demos = [
        ([1024, 1024], -1, "min"),      # M=1024,R=1024,N=1 → streaming 切行满核
        ([16384, 16384], 0, "min"),     # M=1,R=16384,N=16384 → streaming 借 N
        ([1000003], -1, "min"),         # M=1,R=1e6,N=1 → core_partition（借 R）
        ([363, 367, 373], 1, "min"),    # M=363,R=367,N=373 → streaming
        ([2048, 2048], -1, "sum"),      # 无索引 → oneway/twoway
    ]
    for shp, d, op in demos:
        t = select_scan_tiling(shp, d, op, core_num=72, ub_size=192 * 1024)
```

The prohibition, `scan/fallback/tiling-flow.md:121`:

```
| 流式（streaming） | ✅ | 任意 | 逐 r 切片（不必全载） | 够满核 | 常驻 running-(val,idx)，仅作参考实现，**勿用于性能路径** |
```

and the templates the document routes indexed operators to instead, `:118-120`:

```
| **tile 常驻 + ping-pong** | ✅ | **>1** | 切 rChunk，块间 UB carry | 够满核 | `[R][lane]` 布局，running 常驻寄存器，三条流水重叠 |
| **lane 并行顺序扫描** | ✅ | **==1** | 整行入 UB | 够满核 | gather 虚拟转置，指令条数与 log2(R) 脱钩 |
| 行内 Kogge-Stone | ✅ | ==1 | 整行入 UB | 够满核 | log2(R) 级；R 小到一两个 chunk 时比 lane 并行划算 |
```

The script does disclaim itself, at `:4-5`:
`Scan / Cum 族 Tiling 参考实现（简化版）：合轴 (M,R,N) → 流式选块 → 并行度补偿 → 跨核借 R 判定。
与 kernel 侧 scan_tiling.template 对应。仅用于建模/选型说明，非生产 tiling。` That is an honest
scope statement, and it is in a comment block above the imports — the part of a file an agent
running it for an answer does not necessarily read. It says the script is not production tiling; it
does not say the template it emits is one the sibling document forbids.

Two smaller consistency notes on the same line `:87`. The un-indexed test `n * 4 > 256 // 4`
evaluates to `n * 4 > 64`, i.e. `n > 16` fp32 elements, which matches the document's
`alignN > VREG/4 = 16 元素 fp32` — the one place the two artifacts agree numerically. And the test
hardcodes `4` as the element size, so it is an fp32-only test in a script whose declared dtype
range is FP32/FP16/BF16/INT32 (`scan/fallback/index.md:34`).

Registered as C-950tiling-016.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The
contradiction is between two artifacts, and Art. 7 resolves it by measuring which plan is faster,
not by deciding which file is authoritative.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s
spacing; bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and
discard the case if the die moved. Establish a variance floor first (one build, 30 in-process runs
and 5 fresh-process runs; report the interquartile range over the median).

Run the script's own demo cases on a board. Take the four indexed demos verbatim —
`[1024,1024] dim=-1`, `[16384,16384] dim=0`, `[1000003] dim=-1`, `[363,367,373] dim=1`, all `min`,
at the queried `core_num` — and for each build two kernels with one compiler pin: the template the
script emits, and the template the flow document's tree selects for the same shape. md5 both;
host echo of the template/`mode`, `(M,R,N)`, `blockDim` and any workspace request. Compare both
outputs elementwise against a CPU reference and require bit-identity for min/max — a scan that
differs is a bug, not a tolerance question — reporting the first differing index if any. Record
`aiv_time` under `msprof --aic-metrics=PipeUtilization`, ≥10 iterations, first 5 dropped, per case.

The third demo (`[1000003]`) is the control: both artifacts agree it takes `core_partition`, so its
two arms should be the same plan, and if they are not, the disagreement is wider than this entry
records.

Refuses to assume: that a free die stays free; that a die may be substituted; that `core_num` is 72
or `ub_size` 192 KB merely because the script's demo passes them (both queried and printed); that
the flow document's templates are implementable as written — if one of them cannot be built, that
is the finding and it changes which artifact is wrong; that a bigger gap on one shape generalises
to the family.

## 5 · Checker — acceptance declared before the run
Verdict variable `script_penalty(case)` = script-template median `aiv_time` / document-template
median `aiv_time`, reported with the variance floor beside it. Declared before the run: the
prohibition is supported iff `script_penalty > 1 + variance_floor` on at least three of the four
indexed cases. The OVERTURN fires iff `script_penalty ≤ 1 + variance_floor` on all four — the
script's output would then be a legitimate plan and the document's prohibition over-broad. The
control case's verdict is `control_agrees`, true iff both arms echo the same template and their
times are within the variance floor; a false `control_agrees` invalidates the other three
comparisons and is reported first.

The exit code is not the verdict. Two guards. First, template identity: the two arms must echo
different templates on the three indexed non-control cases; if the build system collapsed them, no
comparison exists and the checker goes red rather than reporting a ratio of 1.00 as an overturn.
Second, the elementwise bit-identity check runs on both arms of every case — the streaming and
tile-resident forms compute the same function, so any difference means one of them is broken and
the timing comparison is void. A checker that read only `aiv_time` would rank a broken kernel first,
which is the failure species this guard exists for.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; neither artifact's plan was built or timed. The entry does not establish that
streaming is slower — upstream asserts it and gives two unconditioned numbers elsewhere (0134). It
does not establish that the flow document's templates exist as code anywhere; the document names
kernel-side template files (`cum_tile_resident_scan`, `cum_row_kogge_stone`,
`cum_core_partition_scan`) that are not in this tree. It does not establish which artifact is
authoritative — that is not a question a board can answer, and this entry deliberately does not
answer it either. It does not cover the script's other divergences from the document (0135) beyond
noting they exist. No chip is named anywhere in the scan family, so BOARD is
`family-claimed(unverified)`; §4 names 950PR/950DT because that is where our run would happen.
Nothing here is established for any 910-family board.
