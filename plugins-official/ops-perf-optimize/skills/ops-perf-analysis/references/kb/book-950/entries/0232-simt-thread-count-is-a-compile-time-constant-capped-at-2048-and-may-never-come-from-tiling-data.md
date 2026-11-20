```
ID:        0232-simt-thread-count-is-a-compile-time-constant-capped-at-2048-and-may-never-come-from-tiling-data
LABEL:     trap
LEVEL:     L0 (launch & host)
STRATUM:   harvested — three upstream files state it, all `upstream/skills-dev-main`, therefore ONE
           origin (RULES.md Art. 3). Nothing was compiled; the prohibition's enforcement mechanism is
           unknown.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/simt-arch-guide.md:26-31 — "- 单核最大支持 **2048** 线程 /
           - **必须在编译期确定**（使用 `constexpr` 或字面量）/ - 禁止从 tiling 数据动态获取 /
           - `LAUNCH_BOUND(N)` 和 `Simt::Dim3(N)` 必须使用同一个编译期常量 / - 默认值: 1024"
SOURCE:    ops/ascendc-simt-tiling-design/references/guide.md:53-59 — "### 错误写法（严禁）" with
           "// 线程数从 tiling 数据获取（运行时变量）
            int32_t threadNum = static_cast<int32_t>(tilingData_->threadNum);
            Simt::VF_CALL<OpComputeSimt<T>>(Simt::Dim3(threadNum), args...);"
SOURCE:    ops/ascendc-simt-api-reference/references/overview.md:59 — "threadNums | 输入 | dim3 结构
           {dimx,dimy,dimz}，指定 SIMT 线程块内线程数量。线程总数=dimx*dimy*dimz，必须<=2048"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a SIMT kernel that compiles and runs correctly with its thread count taken from a
           runtime tiling field, or one that launches more than 2048 threads per core.
```

# 0232 · SIMT thread count is a compile-time constant capped at 2048 and may never come from tiling data

## 1 · Claim
Upstream asserts four things about the SIMT per-core thread count: a single core supports at most
**2048** threads; the count must be fixed at compile time, via `constexpr` or a literal; taking it
from tiling data at runtime is forbidden; and `LAUNCH_BOUND(N)` and `Simt::Dim3(N)` must name the
same compile-time constant. Upstream states the default as 1024. `asc_vf_call`'s parameter
documentation states the cap as a property of the `dim3` product: 总数 = dimx·dimy·dimz ≤ 2048. Not
established here: nothing was compiled and no launch was attempted.

## 2 · The wrong branch this removes
Thread count is exactly the kind of quantity a tiling routine expects to own. Every other launch
parameter in this programming model — block count, per-core element count, buffer sizes — is computed
on the host from the shape and passed down in `TilingData`. An agent generalising that pattern writes
`Simt::Dim3(tilingData_->threadNum)`, which is upstream's explicitly 严禁 example, and it is the
natural thing to write rather than a careless thing.

What makes it a trap rather than a mistake is that upstream does not say what happens. Three
outcomes are possible and they differ enormously: a compile error naming the constexpr requirement
(harmless); a compile error somewhere unrelated, because `LAUNCH_BOUND` is a template or attribute
argument and the diagnostic surfaces as a substitution failure (confusing but safe); or a silent
acceptance in which the launch uses a different count than the register allocation was computed for
(0236) — which would mean threads running with fewer registers than their frames need, and spilling
to stack with no error at all.

The second half of the trap is the pairing rule. `LAUNCH_BOUND(N)` sets the register budget per
thread; `Simt::Dim3(N)` sets how many threads actually launch. Two different literals compile fine —
they are separate expressions in separate places — and the mismatch is invisible. A kernel declared
`LAUNCH_BOUND(512)` and launched at `Dim3(1024)` has been register-allocated for 64 registers per
thread (0236) and is running 1024 threads that are entitled to 32.

The cap has its own quiet direction: an agent tuning upward from the 1024 default to hide memory
latency (upstream recommends 2048 for copy-bound operators) is at the ceiling, and any further
increase is not merely ineffective but out of contract.

## 3 · Ground / Source
`npu-arch/references/simt-arch-guide.md:19-39`, the thread-hierarchy section, quoted with the
surrounding levels because the three-level structure is what makes the constraint make sense:

> | 层级 | 概念 | 对应 CUDA | 设置方式 |
> | 启动核数 | Block 数量 | Grid 中的 Block 数 | tiling 侧 `SetBlockDim` |
> | 启动线程数 | 单核线程数 | 单 Block 线程数 | kernel 侧 `constexpr` 常量 |
> | Warp | 32 线程分组 | Warp | 硬件自动分组 |
>
> ### 线程数
> - 单核最大支持 **2048** 线程
> - **必须在编译期确定**（使用 `constexpr` 或字面量）
> - 禁止从 tiling 数据动态获取
> - `LAUNCH_BOUND(N)` 和 `Simt::Dim3(N)` 必须使用同一个编译期常量
> - 默认值: 1024，建议范围根据数据量和计算复杂度调整

The table row is the design reason: block count is a *tiling-side* setting and thread count is a
*kernel-side* one. They live on opposite sides of the host/device boundary, and the prohibition is
a consequence of that split rather than an arbitrary rule.

`ascendc-simt-tiling-design/references/guide.md:41-61` gives both forms side by side — this is the
passage worth cloning, because it shows the correct shape and the forbidden one in the same view:

```cpp
// ### 正确写法
constexpr uint32_t THREAD_NUM = 512;
__simt_vf__ __aicore__ LAUNCH_BOUND(THREAD_NUM) inline void OpComputeSimt(...);
Simt::VF_CALL<OpComputeSimt<T>>(Simt::Dim3(THREAD_NUM), args...);

// ### 错误写法（严禁）
int32_t threadNum = static_cast<int32_t>(tilingData_->threadNum);
Simt::VF_CALL<OpComputeSimt<T>>(Simt::Dim3(threadNum), args...);
```

and `:61` states the remedy, which is the operative half and is easy to miss:

> > 如果数据量较小导致线程空转过多，应通过调整**核数**（`SetBlockDim`）来适配，而不是减少线程数。

So the answer to "my shape is small and most threads idle" is to change the block count on the tiling
side, not the thread count on the kernel side. That is the sentence that makes the prohibition
livable.

`ascendc-simt-api-reference/references/overview.md:55-60` states the cap on the other launch path,
`asc_vf_call`, as a property of the `dim3` product rather than of a scalar:

> | threadNums | 输入 | dim3结构{dimx,dimy,dimz}，指定SIMT线程块内线程数量。线程总数=dimx*dimy*dimz，必须<=2048 |

and `:39` adds two adjacent restrictions on the same call: the SIMT entry function may not be a class
member function, and only raw pointers and common scalar types may be passed — no structs, no arrays.

`simt-arch-guide.md:275-285` restates the pairing rule under `LAUNCH_BOUND` and gives the syntax:
`__simt_vf__ __aicore__ LAUNCH_BOUND(512) inline void YourKernel(...);`, with "`LAUNCH_BOUND(thread_num)`
可选，默认 1024" and "参数必须是 `constexpr` 常量或字面量".

All three files are `upstream/skills-dev-main` — **one origin** (RULES.md Art. 3). The repetition across
three skills is evidence that the rule is believed, not that it is confirmed.

Upstream's selection guidance, `simt-arch-guide.md:288-291`, is recorded because §2's ceiling argument
depends on it: 搬运类算子 2048/1024 ("内存带宽受限，更多线程隐藏延迟"), 计算类算子 512/1024
("寄存器压力较大，需平衡并行度和寄存器").

## 4 · Procedure
Runnable later on `950PR`; the decisive arms need no device and should run first.

Arm A — the prohibition, compile only. Build three translation units, identical but for the thread
count expression: (i) `constexpr uint32_t N = 512;` used in both `LAUNCH_BOUND` and `Dim3`;
(ii) the literal `512` in both; (iii) a runtime `int32_t` read from a tiling struct, passed to
`Dim3`, with `LAUNCH_BOUND(512)`. Record for each: does it compile, and if not, what does the
diagnostic name. Outcome (iii) compiling clean is the important case and is the reason this arm is
not skippable.

Arm B — the pairing rule, compile only. Build `LAUNCH_BOUND(512)` with `Dim3(1024)` and record
whether anything objects. Upstream states they must match; nothing in the syntax forces it, so this
arm determines whether the rule is enforced or merely stated.

Arm C — the cap, on the board. Launch at `Dim3(2048)` and at `Dim3(2049)` and record the outcome of
each: accepted, rejected at build, rejected at launch, or accepted-and-wrong. A cap that is enforced
and a cap that is documented are different things and only a launch tells them apart.

Arm D — the consequence arm, which is what makes Arms A and B matter. If Arm B compiled, run the
mismatched build against a matched `LAUNCH_BOUND(1024)`/`Dim3(1024)` build at identical shape on the
same die in the same session, and compare output bits and `aiv_time`. A correct-but-slower mismatched
build is the silent-spill hypothesis from §2 and would be the finding; differing bits would be worse
and would be a different finding.

Device selection is explicit for Arms C and D: the operator names the device index, the probe prints
it back with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run
(shared machine, ≤4 dies), and no die is substituted for another. Arms C and D's paired runs occur on
one named die in one session, or their comparison attributes nothing.

## 5 · Checker — acceptance declared before the run
Four verdict variables, never aggregated — the four arms test four independent assertions and one
passing must not cover another failing.

`constexpr_required` (Arm A) — pass iff (i) and (ii) compile AND (iii) fails with a diagnostic that
names the constexpr or compile-time requirement. A failure of (iii) for an *unrelated* reason is
recorded as `NOT ESTABLISHED`, not as a pass: the checker matches diagnostic text, not exit status,
because "it did not compile" and "it did not compile for the stated reason" are different results.

`pairing_enforced` (Arm B) — pass iff the mismatched build is rejected. A clean compile does **not**
fail this entry; it records that upstream's rule is a convention with no enforcement, which is a more
useful result than a confirmation and changes what the delivered skill must say.

`cap_enforced` (Arm C) — pass iff 2048 is accepted and 2049 is rejected. 2049 being accepted
overturns the cap; 2048 being rejected narrows it and the entry is corrected in place.

`mismatch_is_silent` (Arm D) — reported, no pass condition. Bit-identical output with a measurable
`aiv_time` penalty is the outcome that confirms §2's spill hypothesis.

The positive fixture, declared before the run: Arm A must be shown to go red on an input whose answer
is known — compile variant (i) with `constexpr` replaced by plain `const int` initialised from
`std::rand()`. That must fail with the constexpr diagnostic. If it compiles, the harness cannot detect
a runtime thread count at all and every `constexpr_required` verdict it issued is void. Without this,
the checker only reads "three builds behaved differently", which is the known blind species.

Process exit codes are not the verdict anywhere: in Arm A a non-zero exit is the expected outcome for
variant (iii).

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No translation unit was
compiled, no kernel was launched, and no thread was counted.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish how the prohibition is enforced, or whether
it is — Arm A exists precisely because a rule stated in three documents may still have no mechanism
behind it, and the silent-acceptance branch in §2 is the one with no detector. It does not establish
that the 2048 cap is a hardware limit rather than a toolchain one; upstream states the number and no
source in this scope explains it. It does not establish that the `dim3` product form and the scalar
`Dim3(N)` form share the same cap, though upstream states the cap on the product. It says nothing
about the *register* consequence of the thread count — that is 0236, on separate upstream evidence,
and the two are deliberately not fused: this entry is about where the number may come from, not about
what it costs. It says nothing about `SetBlockDim` on the tiling side (0240) beyond quoting upstream's
remedy. All three sources are one repo, so the threefold repetition adds locatability and not
independence. Nothing transfers to the other book (RULES.md Art. 1): SIMT is a DAV_3510-era programming
model and upstream states the hardware does not exist on earlier architectures.
