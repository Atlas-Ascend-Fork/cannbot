```
ID:        0404-the-three-dimensional-split-reduction-caps-its-row-chunk-at-255-with-a-bare-literal-the-neighbouring-flow-document-never-mentions
LABEL:     trap
LEVEL:     L6 (tiling & scheduling)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled.
           Deliberately NOT `corroborated`: the toolkit header quoted in §3 corroborates that 255 is a
           named repeat-times constant, which is not this entry's claim. The claim is that upstream
           clamps to it unexplained and that its own flow document omits the clamp, and no second
           origin speaks to that. See §3's fence.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-tiling-design/references/reduction/ara-rowsplit.md:72-78 —
           "// R_max 计算（注意：与全载模式公式不同，此处为单缓冲，overhead 和除数均不同）
           / constexpr uint32_t a0TileBase = 64;  // FP32 / uint32_t tmpBufSize = 4096;
           / uint32_t overhead = 3 * a0TileBase * sizeof(float) + tmpBufSize;
           / uint32_t R_max = (UB_SIZE - overhead) / (a0TileBase * sizeof(float));
           / R_max = std::min(R_max, 255u); / R_max = std::max(R_max, 1u);"
SOURCE:    /usr/local/Ascend/cann-9.0.0-beta.2/aarch64-linux/ascendc/include/basic_api/impl/utils/
           kernel_utils_constants.h:39 — "const int32_t MAX_REPEAT_TIMES = 255;"
           (installed toolchain, read-only; independent origin of authority)
INDEX:     none — nothing measured; see SOURCE. Re-derivable by file read (no device):
           grep -Rn 'MAX_REPEAT_TIMES *=' /usr/local/Ascend/cann-9.0.0-beta.2/aarch64-linux/ascendc
           grep -n '255u' upstream/skills-dev-main/ops/ascendc-tiling-design/references/reduction/ara-rowsplit.md
OVERTURN:  a 3-D ARA split-load reduction on a named 950 board, built with `R_chunk_size = 256` (one
           past the cap) and a `DataCopyPad` whose `blockCount` therefore exceeds 255, that produces
           correct output and does not fault. The 255 would then not be a hardware ceiling reached by
           this quantity, and the tiling cap would be a software literal a search may cross — which
           is the opposite disposition under 0104 and changes what a tuner is allowed to do with it.
```

# 0404 · The three-dimensional split reduction caps its row chunk at 255 with a bare literal the neighbouring flow document never mentions

## 1 · Claim
Upstream asserts, in the design shelf's ARA split-load branch, a host-side computation of the maximum
number of reduction rows one chunk may hold: a UB-capacity division, then `std::min(R_max, 255u)`,
then a floor of 1. The `255u` carries no name, no comment and no derivation, in a code block whose
immediately preceding comment explains a *different* deviation (`与全载模式公式不同，此处为单缓冲`).
Upstream's analysis shelf applies the same cap in its reference script under the name `REPEAT_MAX = 255`
at two call sites, and states it nowhere in the markdown flow document that a reader of that shelf is
directed to follow — the ARA-Recompute budget there is expressed with `r_bin_size = 128` and has no
upper bound at all. The installed CANN toolchain declares `MAX_REPEAT_TIMES = 255` as a named constant
in its architecture-generic constants header, alongside `MIN_REPEAT_TIMES = 0`, and its DAV_3510
(`dav_c310`) DataCopy implementation splits transfers into `MAX_REPEAT_TIMES`-sized rounds. Upstream
never connects its `255` to that constant. Not established here that the cap is binding on this
quantity on any board.

## 2 · The wrong branch this removes
A magic number in a capacity formula is read as a tuning knob unless something says otherwise, and
`0104` makes that reading operational: a constraint traceable to chip configuration is hard and may
not be relaxed; a hardcoded literal is a software 经验值 that a search may cross. `255u` sitting between
a UB division and a `max(…, 1u)` floor looks exactly like a conservative software clamp — round, small,
undefended. A tuner that treats it as one raises `R_chunk_size` to 256 or 512 to cut the chunk count,
and on the analysis shelf's markdown it would have no reason not to, because that document does not
have the cap.

The reason it is probably not a knob is visible only two files away and only if you know what to look
for. In the same branch's kernel code the chunk row count becomes `DataCopyExtParams`'s **blockCount**:

```cpp
DataCopyExtParams copyParams{static_cast<uint16_t>(rCount), ...};
```

`rCount` is `R_chunk_size` or the tail. So `R_max` is not an abstract chunk size — it is a transfer's
repeat count, and the toolchain's arch-generic ceiling on a repeat count is 255. That is the
connection upstream never writes down, and it is the difference between "a number you may tune" and "a
number that faults or silently truncates". The wrong branch this entry removes is raising it.

The second wrong branch is the mirror image, and it is why the toolkit finding is fenced in §3 rather
than raising this entry's stratum: concluding from the header constant that 256 *must* fail here. The header establishes that
a constant named `MAX_REPEAT_TIMES` with value 255 exists and is used by the DAV_3510 DataCopy path to
chunk transfers. It does not establish that `DataCopyPad`'s `blockCount` field is the field that
constant bounds — `blockCount` is a `uint16_t` in `DataCopyExtParams`, so its own type permits 65535,
and this book already records one case in which a transfer parameter's effective ceiling is a field
width rather than a round constant, with a stale in-code comment beside it (`0332`: gather source
offsets stop at 65535 bytes for 8-bit and 131071 for 16-bit) — so "the type permits it" and "the
hardware accepts it" are known to come apart here, in both directions. Two plausible ceilings, one
type-derived and one constant-derived, differing by 257×, is precisely the situation §4 must resolve
by observation rather than by reading.

The third wrong branch is treating the cap's absence from the analysis shelf's markdown as an
oversight to be silently patched. It may be a real difference: the analysis shelf's ARA-Recompute uses
a fixed `r_bin_size = 128`, which is *below* 255 by construction, so that shelf's markdown may simply
never approach the ceiling and therefore never need to state it. If so, the two shelves are not in
conflict — one clamps a computed value, the other fixes a value that cannot reach the clamp. The
honest record is that the flow document a reader follows contains no upper bound while the script
beside it contains one, and that a reader who derives `R_max` from the markdown alone gets a number
the script would clamp.

## 3 · Ground / Source
The design shelf's computation, `ascendc-tiling-design/references/reduction/ara-rowsplit.md:69-89`,
in full:

```cpp
### 3.1 分载判定（Host侧）

// R_max 计算（注意：与全载模式公式不同，此处为单缓冲，overhead 和除数均不同）
constexpr uint32_t a0TileBase = 64;  // FP32
uint32_t tmpBufSize = 4096;
uint32_t overhead = 3 * a0TileBase * sizeof(float) + tmpBufSize;
uint32_t R_max = (UB_SIZE - overhead) / (a0TileBase * sizeof(float));
R_max = std::min(R_max, 255u);
R_max = std::max(R_max, 1u);

if (R > R_max) {
    // ARA-Row-Split 模式
    loadMode = LOAD_SPLIT;

    // R 分 chunk
    uint32_t R_chunks = (R + R_max - 1) / R_max;
    uint32_t R_chunk_size = R_max;
    uint32_t R_last_chunk_size = R - (R_chunks - 1) * R_chunk_size;
}
```

Every other quantity in that block is named or derived: `a0TileBase` is annotated `// FP32`,
`tmpBufSize = 4096` matches the Reduce-API temp floor this book carries at `0129`, `overhead` is spelt
out as a sum. Only `255u` and the `1u` floor arrive bare, and the comment line that could have
explained them is spent on why the divisor differs from full-load mode.

Where the number becomes a transfer parameter, same file, `:160-171`:

```cpp
for (uint32_t chunkIdx = 0; chunkIdx < R_chunks; chunkIdx++) {
    uint32_t rStart = chunkIdx * R_chunk_size;
    uint32_t rCount = (chunkIdx == R_chunks - 1) ? R_last_chunk_size : R_chunk_size;

    // Load R chunk
    DataCopyExtParams copyParams{static_cast<uint16_t>(rCount),
                                  static_cast<uint32_t>(tileA0Len * sizeof(float)),
                                  static_cast<uint32_t>((A0 - tileA0Len) * sizeof(float)),
                                  0, 0};
    DataCopyPadExtParams<float> padParams{false, 0, 0, 0};
    // shape will be [rCount, alignedCols] with `[rCount, tileA0Len]` valid data.
    DataCopyPad(xLocal, xGm[rStart * A0], copyParams, padParams);
```

`rCount` is the first field of `DataCopyExtParams` — the block count — and it is cast to `uint16_t`,
whose range is 65535. So the cap is imposed 90 lines earlier, in host arithmetic, and nothing at the
call site records why.

The analysis shelf's version, `ascendc-perf-optimize/references/tiling/reduction/fallback/script/
reduction_tiling.py:43-47`, where the same value is named:

```python
VECTOR_REG_WIDTH = 256
A0_TILE_UNIT_FP32 = 64
A0_TILE_UNIT_FP16 = 128
REPEAT_MAX = 255
R_BIN_SIZE = 128
```

applied at `:280-282` and `:363-364`:

```python
    overhead = 64 + cfg.tmp_buf
    r_max = (cfg.ub_size - overhead) // (2 * cfg.dtype_bytes)
    r_max = min(r_max, REPEAT_MAX)
    r_max = max(r_max, 1)
```

The same clamp, the same floor, a name that says what it is — and `grep -n 255` over that shelf's
`tiling-flow.md` returns nothing. The markdown that carries the family's five budget formulas
(`0123`) has no upper bound on `r_max` at all. Registered as `C-950td-006`.

The second file, and the fence around it. The installed toolchain corroborates the *number*, not the
claim: it shows 255 is a named constant in this toolkit, and says nothing about why upstream's tiling
formula clamps to it or why one of upstream's two documents omits the clamp. That is why this entry
stands at `harvested` and not at `corroborated` — STRATA calls the stratum word a fence, and a second
origin that speaks to a premise rather than to the claim does not move it. The toolchain,
`/usr/local/Ascend/cann-9.0.0-beta.2/aarch64-linux/ascendc/include/basic_api/impl/utils/kernel_utils_constants.h:36-41`:

```cpp
const uint16_t MAX_HALF_MASK_LEN = 64;
const int32_t DEFAULT_C0_SIZE = 32;
const int32_t DEFAULT_BLOCK_SIZE = 256;
const int32_t MAX_REPEAT_TIMES = 255;
const int32_t MIN_REPEAT_TIMES = 0;
```

This is a different origin of authority — the vendor's installed toolchain rather than a second file
in the skills repo — but what it establishes is narrow and must stay narrow: that 255 is a named
repeat-times ceiling in this toolkit, **not** that upstream's `R_max` is bounded by it and not that
upstream's silence about the clamp is explained. The constants file is architecture-generic (the only
`__NPU_ARCH__` guard nearby is for values 3003 and 3113, neither of which is 3510 — cf. `0352`), and
the DAV_3510-specific consumer is the DataCopy implementation,
`impl/dav_c310/kernel_operator_data_copy_impl.h:415-437`, which splits an oversized transfer into
`repeatCount = nValue / MAX_REPEAT_TIMES` full rounds plus `repeatTail = nValue % MAX_REPEAT_TIMES`
and issues each round with `DataCopyExtParams copyParams = {MAX_REPEAT_TIMES, …}`. So on that path the
toolkit itself never exceeds 255 in one call, and does the splitting rather than faulting — which is a
third possible behaviour at 256 and the reason §4 must observe rather than predict.

This project's own survey listed `repeatTimes ≤ 255` under "establish from scratch — no upstream
authority" (`harvest/surveys/DEEPDIVE_20260824_perf-optimize.md:284-286`). That assessment holds for
the skills repo, where the number appears only as an unexplained clamp; it does not hold for the
installed toolkit, where the constant is named. Recorded in `harvest/standing/950-td.md` as
`Q-950td-01`.

## 4 · Procedure
Proposed, runnable later on a named 950 board (950PR or 950DT); never run in this phase. The claim is
about a *ceiling*, so the procedure must cross it, and crossing a ceiling is exactly the arm most
likely to be quietly repaired by the toolkit rather than to fail — §5's guards are built for that.

Device selection: `npu-smi info -l`; `npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing;
bind only on three idle samples; `ASCEND_RT_VISIBLE_DEVICES=<id>`; re-sample after and discard the
case if the die moved. Variance floor first: one build, 30 in-process runs and 5 fresh-process runs.

**Arm 1 — the ladder across the cap.** A 3-D FP32 ARA split-load ReduceSum, `[A1, R, A0] = [4, R, 64]`
with `tileA0Len = 64` so `alignedCols = 64` exactly and the transfer geometry is the simplest possible.
Build one kernel whose `R_chunk_size` is a host-supplied parameter, not a derived one, and run it at
`R_chunk_size ∈ {128, 254, 255, 256, 257, 512, 1024}`, with `R` fixed large enough (`R = 4096`) that
every setting produces at least four chunks. One compiler pin, one md5, host echo of
`R_chunk_size`, `R_chunks`, `R_last_chunk_size` and the `blockCount` value actually placed in
`DataCopyExtParams`. At every rung: elementwise comparison against a CPU reference, the device return
code, and `aiv_time`.

Three outcomes are possible at 256 and they are not the same finding, so the arm records which:
`ran_correct` (the toolkit split the transfer, as `kernel_operator_data_copy_impl.h:419-423` does on
its own path — the cap is then a host-side conservatism), `ran_wrong` (silent truncation to 255 rows
per chunk, giving a partial sum — the worst case, and the one a correctness test that only checks
"finished" will miss), or `faulted`. The elementwise comparison is what separates the first two and it
is mandatory at every rung.

**Arm 2 — is the bound on `blockCount` or on something else?** Repeat the ladder with
`tileA0Len = 8` (so each block is 32 B, the minimum) and with `tileA0Len = 512` (2 KB blocks). If the
crossover stays at 255 blocks regardless of block size, the ceiling is on the count; if it moves with
total bytes, the count was not the binding quantity and this entry's mechanism is wrong.

**Arm 3 — the 2-D counterpart, which upstream does not clamp.** The design shelf's AR split arm
(`ar-colsplit.md:106`) issues `DataCopyExtParams copyParams{1, …}` — `blockCount` is literally 1, so
no cap applies and `chunkCols` is bounded only by UB. Build a 2-D split-load with
`chunkCols` swept past any plausible ceiling and confirm no analogous limit appears. Retained because
if a limit *does* appear there, the mechanism is not repeat count and both other arms are
misattributed.

Refuses to assume: that a free die stays free; that a die may be substituted; that `UB_SIZE` is a
literal (queried per `0141` and echoed); that the host's requested `R_chunk_size` reached the transfer
(the `blockCount` actually written into `DataCopyExtParams` is echoed from the device, and a rung whose
echoed value differs from the requested one is recorded as a *finding* — that is the silent-clamp
case — not discarded); that a run which returned success computed the right answer.

## 5 · Checker — acceptance declared before the run
Verdict `cap_behaviour(n)` for each rung `n` ∈ {`correct`, `wrong`, `faulted`, `clamped`}, where
`clamped` means the echoed `blockCount` was 255 although `n` was requested. Declared before the run:
this entry's cap is **supported as binding** iff `cap_behaviour(255) == correct` and
`cap_behaviour(256) ∈ {wrong, faulted, clamped}`. The OVERTURN fires iff
`cap_behaviour(n) == correct` for every `n` up to 1024 with the echoed `blockCount` equal to `n` — the
255 is then a host-side software literal, `0104` classifies it searchable, and this entry is corrected
in place to say so.

Verdict `crossover_invariance` from Arm 2: true iff the first non-`correct` rung is the same
`R_chunk_size` at all three `tileA0Len` values. False means the binding quantity is bytes, not blocks,
and the entry's mechanism is wrong even if the number 255 happens to appear.

Verdict `two_d_clean` from Arm 3: true iff no ceiling appears in the 2-D sweep. Expected true; a false
result voids the attribution in both other arms.

The exit code is **not** the verdict, and this is the entry where that matters most: the most
dangerous outcome — silent truncation — is the one that exits 0, returns quickly, and produces a
number that is smaller than it should be but not obviously so. Three guards. First, every rung is
compared elementwise against a CPU reference computed in float64 over the same float32 inputs, and the
checker fails red if any rung's comparison did not execute; "the kernel returned" is never accepted as
a rung result. Second, **the input that makes this checker go red**: the ladder includes `n = 254`, one
below the cap, which **must** come out `correct` with echoed `blockCount == 254`. If 254 is reported
`wrong` or `clamped`, the instrument is failing for a reason unrelated to the ceiling — a bad tail, a
mis-sized buffer — and every rung above it is void. That planted positive is mandatory because a
ladder whose only possible verdict is "everything above some point breaks" cannot distinguish a real
ceiling from a broken harness. Third, no rung is reported without its echoed `blockCount`, its return
code and its elementwise result; the three together are what make `clamped` distinguishable from
`correct`, and a rung missing any of them is untestable, not agreement.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. The header constant quoted in
§3 is a file read of the installed toolkit performed at drafting time, re-derivable by the `grep` in
INDEX; reading a constant is not measuring a limit, and no transfer was issued. The chain from
`R_max` to `DataCopyExtParams.blockCount` is traced by reading upstream's own two code blocks in one
file; nothing was compiled to confirm the cast or the field order.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that 255 is a hardware limit on any
board; it establishes that upstream clamps to it without saying why, that a sibling shelf clamps to
the same value under a name, that the markdown a reader of that shelf follows has no such clamp, and
that the installed toolkit declares a like-named constant of the same value. It does not establish that
`MAX_REPEAT_TIMES` bounds `DataCopyExtParams.blockCount` — that identification is §2's argument and
§4 arm 2 is what tests it; the field's own type permits 65535. It does not establish what happens at
256 (three behaviours are enumerated and none observed), and in particular does not establish that
silent truncation occurs — that possibility is why the checker refuses exit code as a verdict, not a
finding. It does not establish `UB_SIZE`, `a0TileBase = 64`, `tmpBufSize = 4096` or the `3 ×` overhead
multiplier in the `R_max` formula; the first is recorded as disputed at `0131`, the second matches the
FP32 vector length recorded at `0219` from a different source and is not re-derived here, the third is
`0129`'s floor. It does not establish that the analysis shelf's `r_bin_size = 128` never reaches the
cap, only that 128 < 255. It says nothing about the 2-D split arm's `chunkCols`, which upstream does
not clamp (Arm 3 exists to check that absence is real). The toolkit constant is architecture-generic
and its DAV_3510 consumer is the DataCopy path only; nothing here establishes the ceiling for Vector
repeat parameters, for which this book has no entry. BOARD is `family-claimed(unverified)`: no board
token appears in the design shelf's reduction family, and the toolkit header names none. Nothing here
is established for any 910-family board — the toolkit ships `dav_c220` alongside `dav_c310` and this
entry read neither for that purpose (RULES.md Art. 1).
