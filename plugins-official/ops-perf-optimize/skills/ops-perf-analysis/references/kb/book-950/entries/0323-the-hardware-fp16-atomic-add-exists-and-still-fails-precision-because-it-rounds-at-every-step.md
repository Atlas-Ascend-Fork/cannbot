```
ID:        0323-the-hardware-fp16-atomic-add-exists-and-still-fails-precision-because-it-rounds-at-every-step
LABEL:     boundary
LEVEL:     L5 (compute & numerics)
STRATUM:   corroborated — the DECLARATION half only. Upstream states where the fp16 GM atomic add is
           and is not declared; the installed CANN 9.0.0-beta.2 headers on this machine are an
           independent origin for exactly that, and they agree. The ROUNDING half — the claim that
           costs the technique its precision — has ONE origin and no measurement here: nothing was
           compiled, no error was computed, and a header cannot show a rounding mode.
BOARD:     950PR
SOURCE:    ops/ascendc-performance-best-practices/reference/scatter/precision_and_traps.md:16-22 —
           "### 为什么硬件原子加救不了 / `asc_atomic_add(__gm__ half*)` **是存在的**——但声明在
           `simt_api/asc_fp16.h`，**不在** `device_atomic_functions.h`，很容易以为没有。真正的问题
           是：**它每次操作都把结果舍回 fp16**。" · "实测把软件版换成硬件原生原子后，MARE **逐位
           重现** `0.020576`，与软件版完全一致 —— 说明误差来源不是软件实现，而是"每步截回 fp16"
           这件事本身。golden 是 fp64 累加，torch CPU 的 half 累加也内部提升到 float。**绕不过去。**"
SOURCE:    same file:10-14 — "| `add` / `multiply`（累积型） | **必须走 fp32 累加器**：`cast in →
           fp32 域累加 → cast out`，整条链只舍入一次 | | `amin` / `amax` | 直接用原生 half/bf16
           原子。**不产生舍入**，绕 workspace 反而白付两趟 cast | | `none` | 只搬比特，不涉及 |"
SOURCE:    installed toolkit CANN `Version=9.0.0-beta.2` — `asc/impl/simt_api/asc_fp16_impl.h:893`
           declares `asc_atomic_add(__gm__ half *address, half val)`; the public header
           `aarch64-linux/asc/include/simt_api/asc_fp16.h:295` declares the same. The neighbouring
           `simt_api/device_atomic_functions.h` declares `asc_atomic_add` for `int32_t`, `uint32_t`,
           `float` (`__ubuf__` and `__gm__`) and `int64_t`, `uint64_t` (`__gm__` only) — and for no
           half or bfloat16 type at all.
INDEX:     none — nothing measured; see SOURCE. The declaration split is re-derivable by file read:
           grep -Rn 'asc_atomic_add' $ASCEND_HOME_PATH/asc/impl/simt_api/ | grep '__gm__'
OVERTURN:  a measured half-precision scatter-add on a named 950 board where the hardware atomic's
           maximum relative error is materially below the software accumulator's on the same input —
           the per-step rounding would then not be the whole error source, and the fp32-accumulator
           requirement would be over-strict.
```

# 0323 · The hardware fp16 atomic add exists and still fails precision, because it rounds at every step

## 1 · Claim
Upstream asserts that `asc_atomic_add(__gm__ half*)` exists on this architecture, that it is
declared in `simt_api/asc_fp16.h` and **not** in `device_atomic_functions.h` — so a search of the
obvious header concludes it is absent — and that using it does not help, because it rounds the
result back to fp16 on every operation. Upstream asserts a measurement in support: replacing the
software accumulator with the hardware atomic reproduced the maximum relative error **bit for bit**
at `0.020576`, identical to the software version, which upstream reads as showing the error source
is the per-step truncation itself rather than any implementation. Upstream asserts the reference
context: the golden accumulates in fp64 and torch's CPU half-accumulation internally promotes to
float, so a per-step-fp16 accumulation cannot match either. Upstream asserts the resulting rule by
reduce mode: `add` and `multiply` must run through an fp32 accumulator with a single rounding at the
end, `amin`/`amax` may use the native half/bf16 atomics because they introduce no rounding at all,
and `none` is bit movement and does not arise. Not established here.

## 2 · The wrong branch this removes
Two, and they pull in opposite directions.

The first is concluding the hardware atomic does not exist. `device_atomic_functions.h` is where an
engineer looks; the fp16 overload is not there; the search terminates. The agent then builds the
fp32-workspace path believing it had no choice — which is the right destination reached by a wrong
route, and the route matters, because the same agent will later conclude other fp16 atomics are
absent on the same non-evidence. `950:0245` states the general rule this instance obeys: an API
absent from a list is checked in the installed headers, not assumed unavailable.

The second is finding it and using it. It compiles, it runs, it is faster than casting through an
fp32 workspace, and it is wrong by a margin that upstream measured. The failure has no signature
other than the precision verdict, and the bit-identical reproduction is what makes it diagnosable
rather than mysterious: identical error from two different implementations means the error is not in
either implementation.

The third, smaller branch is over-correcting to "always use an fp32 accumulator". Upstream's own
table says `amin`/`amax` must not — a min or max introduces no rounding, so routing them through an
fp32 workspace pays two casts for nothing. The rule is per reduce mode, not per dtype.

## 3 · Ground / Source
The mode table, `scatter/precision_and_traps.md:8-14`:

```
### 结论

| reduce | fp16 / bf16 的走法 |
| `add` / `multiply`（累积型） | **必须走 fp32 累加器**：`cast in → fp32 域累加 → cast out`，
  整条链只舍入一次 |
| `amin` / `amax` | 直接用原生 half/bf16 原子。**不产生舍入**，绕 workspace 反而白付两趟 cast |
| `none` | 只搬比特，不涉及 |
```

The finding, `:16-22`:

```
### 为什么硬件原子加救不了

`asc_atomic_add(__gm__ half*)` **是存在的**——但声明在 `simt_api/asc_fp16.h`，**不在**
`device_atomic_functions.h`，很容易以为没有。真正的问题是：**它每次操作都把结果舍回 fp16**。

实测把软件版换成硬件原生原子后，MARE **逐位重现** `0.020576`，与软件版完全一致 —— 说明误差来源
不是软件实现，而是"每步截回 fp16"这件事本身。golden 是 fp64 累加，torch CPU 的 half 累加也内部
提升到 float。**绕不过去。**
```

The same result restated in the family's falsification list, `scatter/scatter_design.md:177`:

```
| 硬件 fp16 原子加 | `asc_atomic_add(__gm__ half*)` **存在**（声明在 `simt_api/asc_fp16.h`，**不在**
`device_atomic_functions.h`），但每次操作都舍回 fp16 —— 换用后 MARE 与软件版**逐位重现**
`0.020576`，精度过不了。累加类必须走 fp32 累加器 |
```

Two files, one repo, one origin (RULES.md Art. 3).

The cost of the correct path, and the optimisation of it, `:24-30`:

```
fp32 workspace 要付两趟 cast（`data → f32`、`f32 → y`）。**优化点不是消掉它，而是别用 SIMT 做它**：

> 把 cast 从 SIMT 标量循环改成 **SIMD 的 MTE 搬运 + `AscendC::Cast`**：
> 某用例 **1565us → 89us**；67M 元素的大用例上两趟 cast 的占比从约 **47% 降到约 21%**
> （640us / 3000us）。

剩下的 21% 绕不过去——硬件没有精度够用的 fp16 原子加。
```

`640 / 3000 = 21.3 %` ✓. `1565 → 89` is `17.6×` and is the same figure `950:0161` carries from the
sibling shelf; cited, not re-entered. The 47 % → 21 % figure and the `640us / 3000us` case are
**new** here — the sibling shelf's copy of this material does not carry them.

The methodological content, which is why this entry is worth a slot beyond the API fact: **two
independent implementations producing a bit-identical error is evidence about the error's source,
not about either implementation.** Upstream draws exactly that inference and states it. It is the
same move this book requires in the other direction — a two-point comparison of two builds carries
no attribution — used here to *gain* attribution, because bit-identity is a much stronger
coincidence than agreement within tolerance.

Second origin — the installed toolkit, read under the phase-1 read-only exception, CANN
`Version=9.0.0-beta.2`. Upstream's declaration claim is exactly right, and more so than it says:

```
asc/impl/simt_api/asc_fp16_impl.h:893
  __SIMT_DEVICE_FUNCTIONS_DECL__ inline half asc_atomic_add(__gm__ half *address, half val)
  { atomicAdd(address, val); return *address; }

aarch64-linux/asc/include/simt_api/device_atomic_functions.h:24-38
  asc_atomic_add(__ubuf__|__gm__ int32_t*) · (uint32_t*) · (float*) · (__gm__ int64_t*) · (__gm__ uint64_t*)
```

`device_atomic_functions.h` carries five integer/float overloads and **no half or bfloat16 type at
all**; the half overloads live in `asc_fp16.h` (`:291-325`) and the bfloat16 ones in the parallel
`asc_bf16_impl.h` (`:873`). So the trap upstream describes is real in the installed tree: an
engineer who opens the file named "device atomic functions" finds a complete-looking atomic-add
family with no fp16 in it. This is a concrete instance of the rule `950:0245` states in general —
an API absent from a list is checked in the installed headers, not assumed unavailable — and it is
the second time in this book that following that rule changed an answer.

Two further observations from the same read, neither of them upstream's:
the `__gm__ half` overload returns `*address` **after** the atomic rather than returning the
atomic's own result (the `half2` overload does return it), so its return value is a separate
non-atomic read and is not the pre- or post-value of this thread's update;
and `asc_atomic_max` / `asc_atomic_min` for `__gm__ half` do exist (`asc_fp16.h:311,319`), which is
the availability the `amin`/`amax` exemption in §1 depends on and which upstream asserts without
citing.

Measured/inferred split at sentence level: **measured** — MARE `0.020576`, bit-identical across two
implementations; the cast-share figures 47 % → 21 % on a 67 M-element case; `1565 → 89 µs`.
**read, not measured** — the declaration split, from the installed headers.
**not measured** — that the hardware atomic rounds every step (this is inferred *from* the
bit-identity, plus the header's location; the header body shows a delegation to `atomicAdd` and
says nothing about rounding); that no route around it exists (`绕不过去` is a conclusion, not an
enumeration).

## 4 · Procedure
Proposed, runnable later on `950PR` — the board upstream's family names — and separately on 950DT.
Never run in this phase.

Arm 1 — the declaration, which needs no device and was marked `[no-card]`. **This arm has been
run**, and its result is in §3 and §6: `grep -Rn` (not `-r`: these trees contain symlinked
directories) for `asc_atomic_add` over the installed toolkit, recording every overload, its header
path and the toolkit pin. It settles "does it exist" and "where" without building anything. What it
cannot settle is anything about behaviour, which is why Arms 2–5 remain owed.

Arm 2 — the rounding behaviour, isolated. A minimal kernel that atomically adds the same small
half-precision value `n` times to one address, for `n = 1 … 4096`, compared against an fp64 sum of
the same terms. Per-step rounding predicts error growing with `n` in a characteristic staircase;
a single final rounding predicts error bounded by one ULP. This arm establishes the *mechanism*,
which upstream infers rather than measures.

Arm 3 — the bit-identity, reproduced. The same scatter case built two ways (software fp32
accumulator versus hardware half atomic) and both compared against an fp64 reference, reporting MARE
to full precision. Upstream's claim is not "similar" but "bit-identical", and that is checkable
exactly.

Arm 4 — the `amin`/`amax` exemption, which is the half most likely to be over-corrected. Native
half atomic min/max against an fp32-workspace version on the same input, comparing both error and
time. Upstream predicts identical error and a time penalty for the workspace route.

Arm 5 — the cast-share figures, retained whatever they show. On a 67 M-element case, time the two
cast passes as SIMT scalar loops and as SIMD MTE + `AscendC::Cast`, reporting each as a share of
kernel time against upstream's 47 % and 21 %.

Variance floor first for the timed arms: one build, 30 in-process runs, 5 fresh-process runs, IQR
over median. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved — and this family's own trap 4 (`0327`) is the
reason that discipline is not optional here: a co-tenant inflated one of its cases by 18×.
Refuses to assume: that a free die stays free; that a die may be substituted; that the reference is
adequate — it is fp64 on the host, and torch's own half accumulation is *not* used as the reference
because upstream records that it promotes internally, which would hide the effect being measured.

## 5 · Checker — acceptance declared before the run
Verdict `hw_exists` = the set of `asc_atomic_add` half overloads Arm 1 finds, with header paths and
toolkit pin. No pass condition; it is the deliverable, and its value is that it replaces a search of
one header with a search of the tree.

Verdict `mare_identical` = true iff Arm 3's two MARE values agree to every printed digit. Declared
before the run: agreement within tolerance is **not** a pass — the claim is bit-identity, and
"close" would mean the two implementations differ, which is a different and less interesting world.

Verdict `error_growth` = the exponent of Arm 2's error-versus-`n` fit. Per-step rounding is supported
by growth; a flat curve overturns the mechanism while leaving the measurement intact, and the entry
is corrected in place to say the error has some other source.

Verdict `minmax_exempt` = true iff Arm 4's native and workspace errors agree and the workspace route
is slower.

The exit code is not the verdict. Three guards. First, every arm's correctness comparison is against
an fp64 host reference computed in the same accumulation order as the kernel where order matters —
a scatter's atomic interleaving is nondeterministic, so the reference for `add` is bounded (a
best/worst-order envelope) rather than a single value, and a result outside that envelope is a
correctness failure rather than a precision reading. Second — the input that makes this checker go
red — Arm 3 additionally builds a version with the fp32 accumulator's final cast **omitted** (leaving
fp32 output where half is expected). The comparison **must** fail. If it passes, the comparison is
not reading the output dtype it claims to and every MARE in the run is void. Third, no timing figure
from Arm 5 is reported without the die-occupancy samples that preceded and followed it, and no share
is reported without its floor.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. `0.020576`, the 47 % → 21 %
cast share, `640us / 3000us` and `1565 → 89 µs` are upstream's readouts on Ascend950PR; this book has
computed no error and timed no cast.

The one thing that *was* done is a file read, and it is not a measurement either: §4 Arm 1 was
executed against the installed CANN 9.0.0-beta.2 tree under the phase-1 read-only exception, and the
overload locations in §3 are its output. A header read establishes where a symbol is declared. It
cannot establish that the function rounds, cannot establish the MARE, and cannot distinguish an
implementation that truncates every step from one that does not — the body at
`asc_fp16_impl.h:893` delegates to `atomicAdd` and reveals nothing about rounding. The claim in this
entry's title therefore remains untested.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The header search *was* performed and establishes only the
declaration split — one toolkit (`9.0.0-beta.2`), one host-architecture directory (`aarch64-linux`),
one machine; no other toolkit was enumerated, and upstream's own evidence is on CANN 9.1.0-era
runners (`0325`), which was not available here. The per-step-rounding
mechanism is upstream's *inference* from bit-identity plus a header location; §4 Arm 2 is the only
thing here that would measure it directly. `绕不过去` is a conclusion about a search upstream does
not enumerate — a different route (a wider native atomic, a two-level accumulation, an ordering
constraint) is not excluded by anything stated. The MARE figure carries no shape, no element count,
no repeat count and no tolerance context beyond "精度过不了", so it is not portable to another case.
The `amin`/`amax` exemption is asserted and never measured. The cast-share figures come from one
67 M-element case with no dtype or shape given. `simt_api/asc_fp16.h` and
`device_atomic_functions.h` are named by upstream and were not opened here. BOARD is `950PR`, the
board the family's provenance note names; nothing is established for 950DT. Nothing transfers to the
other book (RULES.md Art. 1) — the atomic surface named here is stated by upstream to be DAV_3510-only.
