```
ID:        0322-a-global-kernel-containing-a-simt-vf-must-carry-the-vector-attribute-or-the-linker-fails-far-from-the-cause
LABEL:     trap
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     950PR
SOURCE:    ops/ascendc-performance-best-practices/reference/scatter/precision_and_traps.md:103-115
           — "## 6. 陷阱 3：`__vector__` 不能漏 / 含 SIMT VF 的 `__global__` 核函数**必须显式标
           `__vector__`**（`__attribute__((aiv))`）" · "漏掉时 `ld.lld` 报 `auto derivate failed`，
           报错信息与真因隔得很远。纯 SIMD 核不需要。"
SOURCE:    ops/ascendc-performance-best-practices/reference/scatter/scatter_design.md:137 —
           "| **`__vector__` 是强制的** | 缺失时 `ld.lld` 报 `auto derivate failed` | 含 SIMT VF 的
           `__global__` 核函数必须显式标 `__vector__`（`__attribute__((aiv))`）。纯 SIMD 核不需要。|"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a build on a named 950 board of a `__global__` kernel containing an `asc_vf_call` to a
           `__simt_vf__` function, without `__vector__`, that links successfully — the attribute
           would then not be mandatory on that toolkit, and the diagnostic story would be about a
           version rather than about the language.
```

# 0322 · A `__global__` kernel containing a SIMT VF must carry the `__vector__` attribute, or the linker fails far from the cause

## 1 · Claim
Upstream asserts that a `__global__ __aicore__` kernel function which contains a SIMT vector
function — reached through `asc_vf_call` — must be explicitly marked `__vector__`
(`__attribute__((aiv))`), that omitting it makes `ld.lld` report `auto derivate failed`, and that
the message is far removed from the cause. Upstream asserts the negative half as well: a pure SIMD
kernel does not need the attribute. Upstream states this twice, in two files of the same family, one
of them as a row in the family's measured-regularities table. Not established here — nothing was
compiled.

## 2 · The wrong branch this removes
`auto derivate failed` from `ld.lld` names nothing in the source. It arrives at link time, after
everything compiled, and its vocabulary belongs to type deduction rather than to kernel attributes.
The available responses are all wrong: search the template instantiations for a failing deduction;
suspect the toolkit version; suspect the SIMT headers; simplify the VF until it disappears — which
it will, since deleting the `asc_vf_call` removes the requirement along with the feature.

That last path is the expensive one and it has a documented shape in this shelf. The CANN/Reg VF
FAQ records an agent that met a cluster of build errors, failed to attribute the first one, and
retired an entire VF path on the strength of a misdiagnosis that a minimal reproduction later
disproved (`0345`). `auto derivate failed` is a first-class candidate for that pattern: the message
is opaque, the fix is one attribute, and the plausible-sounding conclusion is that the compiler does
not support the construct.

The second wrong branch is over-application. `纯 SIMD 核不需要` is half the claim, and an agent that
learns "always mark `__vector__`" will mark SIMD kernels too. Upstream does not say what happens
then, and this entry does not either — which is itself the point: the rule has a stated scope and
carrying it past that scope is not supported by anything.

## 3 · Ground / Source
The trap, `scatter/precision_and_traps.md:103-115`, in full:

```
## 6. 陷阱 3：`__vector__` 不能漏

含 SIMT VF 的 `__global__` 核函数**必须显式标 `__vector__`**（`__attribute__((aiv))`）：

template <typename T, typename IDX>
__global__ __aicore__ __vector__ void scatter_warp_last_kernel(...)
{
    asc_vf_call<ScatterWarpLastVF<T, IDX>>(dim3(SCATTER_THREADS), ...);
}

漏掉时 `ld.lld` 报 `auto derivate failed`，报错信息与真因隔得很远。纯 SIMD 核不需要。
```

The same rule as a family regularity, `scatter/scatter_design.md:132-137`, where it sits in the
table headed `## 5. 实测到的硬性规律（Ascend950PR）` alongside three throughput laws:

```
| **`__vector__` 是强制的** | 缺失时 `ld.lld` 报 `auto derivate failed` | 含 SIMT VF 的
`__global__` 核函数必须显式标 `__vector__`（`__attribute__((aiv))`）。纯 SIMD 核不需要。|
```

Two files, one repository, one origin (RULES.md Art. 3) — quoted twice because the placement matters:
the second occurrence is inside a table upstream labels 实测 (measured) on Ascend950PR, which is
how a build fact came to sit among throughput measurements. The board token in this entry's header
comes from that table's heading; the trap file itself names no board.

The scope condition is `__global__` **and** contains a SIMT VF. The family's own detection rule for
"contains a SIMT VF" is stated in the shelf's SKILL.md gating section and is not trivial:
`__simt_vf__` or `Simt::VF_CALL` are direct evidence, but `asc_vf_call` alone is not — it can also
call a SIMD VF, so the target function's decoration or its use of `threadIdx`/`blockIdx`/`blockDim`/
`gridDim` must be checked. So the precondition for this rule is itself a judgement, and getting it
wrong in the permissive direction produces the over-application §2 warns about.

The architecture scope: `scatter_design.md:144` states `__simt_vf__` / `asc_vf_call` /
`LAUNCH_BOUND` / `asc_atomic_*` / `asc_shfl_*` as `该架构专有` for DAV_3510, so the construct that
triggers the requirement does not exist on the other family at all.

Nothing here is measured in the sense of a number. The claim is a build outcome, upstream reports
having met it, and that is strong evidence about one build — not a measurement.

## 4 · Procedure
Proposed, runnable later on a named 950 board — though the decisive part is a *build*, which the
phase-1 rule permits no more than a run does, so nothing below has been executed. Never run in this
phase.

Arm 1 — the requirement. One `__global__ __aicore__` kernel whose body is a single `asc_vf_call` to
a `__simt_vf__` function, compiled twice: with `__vector__` and without. Capture full unclipped
stderr and the real exit code (`set -o pipefail`, `tee`, record `PIPESTATUS`) — the FAQ's own
protocol (`0345`), and it matters here because the claim is precisely about the *text* of a
diagnostic. Verdict is whether the no-attribute build reaches `ld.lld` and whether its first
uncut error contains `auto derivate failed`.

Arm 2 — the negative half. A pure SIMD kernel (no `__simt_vf__`, no SIMT builtins), compiled with
and without `__vector__`. Upstream asserts the attribute is unnecessary; it says nothing about it
being harmless. Both outcomes are recorded, and "harmless" is not assumed.

Arm 3 — the boundary case the detection rule creates. A kernel calling `asc_vf_call` on a **SIMD**
VF, without `__vector__`. By upstream's scope this needs no attribute; by a naive reading of
"contains `asc_vf_call`" it does. This arm is what tells an implementer which reading the toolchain
enforces, and no upstream document answers it.

Arm 4 — version sensitivity, because the OVERTURN is version-shaped. Repeat Arm 1 on every CANN
toolkit available on the machine, recording each pin. A rule that holds on one toolkit and not
another is a compatibility fact, not a language fact, and the two must not be conflated.

Toolchain provenance is recorded rather than assumed: the exact `bisheng` invocation, `--npu-arch`,
the include roots resolved from `compile_commands.json`, and the toolkit pin
(`compiler/version.info`). No SDK file is modified (the shelf's own P0 red line, and this project's
read-only rule). No device is needed for Arms 1–3, which are marked `[no-card]` in
`harvest/standing/950-bp.md`: they are answerable in this phase and have **not** been run, and that
is part of the record.

## 5 · Checker — acceptance declared before the run
Verdict `attr_required` = true iff Arm 1's no-attribute build fails **and** its first uncut `error:`
line contains `auto derivate failed`. Both halves are required, declared now: a failure with a
different first error is a *different* defect and is recorded as `void`, not as confirmation. This
is the guard against the failure the FAQ documents — accepting any failure as evidence for the
hypothesis you arrived with.

Verdict `attr_message` = the verbatim first error line, recorded whatever it says. It is the
deliverable an agent will actually match against.

Verdict `simd_unaffected` = true iff Arm 2's two builds both succeed.
Verdict `simd_vf_case` ∈ {required, not required} from Arm 3.
Verdict `pins` = the set of toolkit pins on which `attr_required` holds.

The exit code **is** part of the verdict here, unusually, and is declared so: this is a build
experiment, the process exit code is the primary observable, and it is recorded together with the
unclipped stderr so that a zero exit with error text and a non-zero exit with none are both visible.
What is *not* the verdict is any grep of the log: the FAQ's protocol forbids judging root cause from
a filtered log, and the first-error rule is applied to the whole captured stream.

The checker must be able to go red, and here is the input that does it: Arm 1 is run a third time
with the `__vector__` attribute present **and** a deliberate syntax error in the VF body. The build
**must** fail with that syntax error as its first uncut `error:`, not with `auto derivate failed`.
If the harness reports `auto derivate failed` for a build whose real first error is elsewhere, then
the harness is not reading the first error and every `attr_required` verdict is void. That planted
positive is the whole reason the verdict has two halves.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was compiled, no
linker was invoked, and the string `auto derivate failed` has not been observed by this book.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled. The entry establishes what upstream reports, not what a toolchain does. It is
pinned to no CANN version at all: upstream states the rule without a toolkit pin, and the scatter
family's own provenance note gives its evidence as Ascend950PR without naming a compiler — so the
rule may be a property of one bisheng release, which §4 Arm 4 is what would tell. It does not
establish what happens when `__vector__` is applied to a pure SIMD kernel (Arm 2), nor which reading
of "contains a SIMT VF" the toolchain enforces (Arm 3); both are gaps upstream leaves and this entry
does not fill. It does not establish that `auto derivate failed` has no *other* causes — an agent
matching on that string alone may attribute a different defect to this one, which is the mirror of
the failure §2 describes. BOARD is `950PR` because the table that carries the second statement is
headed with that part; the trap file itself names no board, and nothing here is established for
950DT. Nothing transfers to the other book (RULES.md Art. 1) — the construct that triggers the rule is
stated by upstream to be DAV_3510-only.
