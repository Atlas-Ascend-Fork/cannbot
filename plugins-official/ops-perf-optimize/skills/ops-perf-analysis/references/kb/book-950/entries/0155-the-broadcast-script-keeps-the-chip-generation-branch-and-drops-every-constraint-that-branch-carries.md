```
ID:        0155-the-broadcast-script-keeps-the-chip-generation-branch-and-drops-every-constraint-that-branch-carries
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/tiling/broadcast/fallback/script/broadcast_tiling.py:373-374,57,584 —
           "if not is_dav3510: return \"ub_broadcast\", 0" · "is_dav3510: bool = True" ·
           "is_dav3510=True," ; broadcast/fallback/tiling-flow.md:19 —
           "├─ DAV_2201 → UB Broadcast 静态接口 (rank=1/2, 32B对齐约束)"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  finding a rank or alignment check for the non-DAV_3510 path anywhere in
           `broadcast_tiling.py` — the constraints would then be enforced and this entry's reading
           of the script wrong, correcting it in place.
```

# 0155 · The broadcast script keeps the chip-generation branch and drops every constraint that branch carries

## 1 · Claim
Upstream asserts, in the broadcast flow document, that the non-DAV_3510 path uses the UB Broadcast
static interface subject to two constraints: `rank = 1/2` and 32-byte alignment. Upstream's reference
script preserves the chip-generation branch — `if not is_dav3510: return "ub_broadcast", 0` — and
implements neither constraint: nothing in the script checks the collapsed rank against 1 or 2, and
nothing checks 32-byte alignment on that path. The script's `is_dav3510` parameter defaults to `True`
and its demonstration block passes `is_dav3510=True` explicitly, so the non-3510 path is never
exercised by anything shipped in the directory. Not established here.

## 2 · The wrong branch this removes
The script returns a branch name and a schedule mode and nothing else for the non-3510 path — it does
not compute a plan that respects the constraints, and it does not refuse a shape that violates them.
An agent that runs the script on a rank-3 collapsed shape with a non-32-byte-aligned trailing axis and
`is_dav3510=False` receives `("ub_broadcast", 0)` and proceeds to derive a plan the flow document says
the static interface cannot express. The failure surfaces at the API call, not at tiling time.

The `is_dav3510: bool = True` default is the second half. The script's own dataclass makes the newer
architecture the default, and its `__main__` block hardcodes it, so every output anyone will actually
see comes from the 3510 branch. The other branch is present, reachable only by an argument nobody
passes, and unconstrained when reached. That is a worse state than omitting it: an agent auditing the
script for chip-scoping finds the branch and concludes the family is dual-architecture-aware.

The third wrong branch is one this book must avoid itself. It is tempting to read the DAV_2201 arm as
910-family knowledge and file it accordingly. It is not: it is a statement made by a 950-era document
about a path it does not exercise, with constraints its own reference implementation does not
enforce. Art. 1 forbids carrying it into the 910 book, and there is nothing here worth carrying —
the constraints are unverified and the implementation is absent.

## 3 · Ground / Source
The branch as the script implements it,
`broadcast/fallback/script/broadcast_tiling.py:357-390`, in full:

```python
    input_strides: List[List[int]],
    is_dav3510: bool,
    dtype: str,
    force_nddma: bool = False,
) -> Tuple[str, int]:
    """
    Select the broadcast implementation branch.

    Returns: (branch_name, sch_mode)
    """
    if len(output_dims) == 1:
        return "onedim", 0

    if not is_dav3510:
        return "ub_broadcast", 0

    if force_nddma:
        sch_mode = 1 if len(output_dims) <= NDDMA_MAX_DIMS else 2
        return "nddma_broadcast", sch_mode

    if _check_nlast_ub_broadcast(output_dims, input_strides):
        return "dynamic_ub", 0

    dtype_bytes = {"fp16": 2, "bf16": 2, "int8": 1, "fp32": 4, "float": 4}.get(dtype, 2)
    if dtype_bytes <= 2:
        tail_dim = output_dims[-1]
        if (tail_dim * dtype_bytes) % 32 == 0:
            return "dynamic_ub", 0

    sch_mode = 1 if len(output_dims) <= NDDMA_MAX_DIMS else 2
    return "nddma_broadcast", sch_mode
```

The DAV_3510 arm implements the flow document's chain faithfully: `force_nddma` is condition ①,
`_check_nlast_ub_broadcast` is condition ②, the `dtype_bytes <= 2` block with
`(tail_dim * dtype_bytes) % 32 == 0` is condition ③, and the final return is condition ④. The
`not is_dav3510` arm returns immediately with no checks at all.

The defaults, `:57` and `:584`:

```python
    is_dav3510: bool = True
```
```python
        is_dav3510=True,
```

The constraints the flow document attaches to that path,
`broadcast/fallback/tiling-flow.md:19`:

```
      ├─ DAV_2201 → UB Broadcast 静态接口 (rank=1/2, 32B对齐约束)
```

Neither `rank` nor a 32-byte check appears on the non-3510 path in the script. The only 32-byte test
in the selector is inside the DAV_3510 condition ③ and applies to `dtype_bytes <= 2` only. The only
place rank enters is `len(output_dims) == 1` for OneDim and `NDDMA_MAX_DIMS` for `sch_mode`, neither
of which is the `rank = 1/2` bound.

A correction to the 2026-08-24 deep-dive survey of this skill. That survey recorded
"broadcast DAV_2201 constraints stated in .md, dropped unconditionally by broadcast_tiling.py:373".
Re-verified: line 373-374 is `if not is_dav3510: return "ub_broadcast", 0`, which *preserves* the
chip branch and routes the non-3510 case to the branch the document names for it. What is dropped is
not the branch but the two constraints on it. The survey's line number is right and its description
overstates: the branch is not dropped, the constraints are. Reported as a failed re-verification
rather than entered as a contradiction row, and registered against the script as C-950tiling-029
(constraints stated in the document, absent from the reference implementation).

Under 0104's provenance rule, `rank = 1/2` and the 32-byte figure trace to a parenthesis in a markdown
decision tree with no chip-configuration chain, so both are unverified software constraints; the
correct reading is that upstream states an interface limit it does not test.

## 4 · Procedure
Two arms. The first needs no device and is permitted in this phase; it has not been run.

Arm 1 — script closure check, read-only, no device, no execution beyond running the script's own pure
functions on synthetic inputs. Call the selector with `is_dav3510=False` on collapsed shapes of rank
2, 3, 5 and 9, with trailing axes both 32-byte-aligned and not, and record the returned branch and
`sch_mode` for each. The prediction on record before running: all sixteen return
`("ub_broadcast", 0)` regardless of rank and alignment. Then grep the whole script for any rank or
alignment test on that path: `grep -n 'rank\|% 32\|align' broadcast_tiling.py`, read-only.

Arm 2 — consequence on a named 950 board (950PR or 950DT); never run in this phase. Note the
asymmetry: a 950 board cannot exercise the DAV_2201 path, so what is testable here is whether the
*constraints themselves* bind on the static Broadcast interface where that interface exists.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved.

Build UB Broadcast static-interface calls at collapsed rank 1, 2, 3 and 5, with 32-byte-aligned and
misaligned trailing axes, one compiler pin, md5 each, and record for each whether it compiles, whether
it launches, and whether the output matches a CPU reference elementwise. A rank-3 call that compiles
and runs correctly would mean the `rank = 1/2` bound is not an interface limit on this platform; one
that fails to compile would mean it is, and that the script's silence is a real gap.

Refuses to assume: that a free die stays free; that a die may be substituted; that the static
interface on a 950 board behaves as the DAV_2201 arm describes — that is exactly what cannot be
established here, and arm 2's results are scoped to the platform they ran on; that the script's
non-3510 path is dead code (arm 1 exercises it).

## 5 · Checker — acceptance declared before the run
Verdict variable `constraints_enforced`: true iff any call in arm 1 returns something other than
`("ub_broadcast", 0)` on a constraint-violating input, or the grep finds a rank/alignment test on that
path. Declared before the run: this entry is supported iff `constraints_enforced` is false. The
OVERTURN fires iff it is true — the script does enforce them and this entry's reading is wrong.
Verdict `rank_limit_real ∈ {compile-error, launch-error, runs-correctly, unavailable}` per rank from
arm 2, reported per rank rather than collapsed to a boolean.

The exit code is not the verdict. Arm 1's instrument is the sixteen-row selector table, and the
checker fails red if fewer than sixteen rows were produced — a closure check that skipped the inputs
it could not construct would report a flattering result. Arm 2's guard is that a `runs-correctly`
verdict requires an elementwise output comparison, not merely a successful launch: a static Broadcast
call at an unsupported rank could plausibly write partial results and exit 0.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. Arm 1 needs no device and has
not been run either, so no selector table and no grep output is recorded here.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured, and the script was not executed. The entry does not establish that the
`rank = 1/2` or 32-byte constraints are real — upstream states them once, in a parenthesis, and its
own reference implementation does not test them. It does not establish anything about DAV_2201
behaviour: this is a 950-era document's statement about another architecture, it is unverified, and
Art. 1 forbids carrying it into the 910 book, which must establish its own broadcast branch from its
own sources. It does not establish that the non-3510 script path is ever taken in practice. It does
not cover the DAV_3510 chain, which the script implements faithfully (0154). No board token appears
in the script; the flow document names two architectures, not boards, so BOARD is
`family-claimed(unverified)`; §4 arm 2 names 950PR/950DT because that is where our run would happen.
