```
ID:        0333-identical-kernel-source-does-not-reproduce-a-kernel-whose-launch-attributes-were-not-restored
LABEL:     trap
LEVEL:     L0 (launch & host)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/sort/templates/usage_guide.md:120-121 —
           "6. 恢复 launch 资源契约：统一 special/common 分发，恢复 schedule mode 1、动态 UB、mixed
           AIV task type 和用户 workspace 偏移。缺少 launch 属性时，kernel 代码相同也不代表运行条件
           相同。"
SOURCE:    same file:86-88 — "6. special key 900001/900002/900003 先于 common key 分发。
           7. mixed kernel 保留 `KERNEL_TYPE_MIX_AIV_1_0`、`SCHEM_MODE=1` 和动态 UB launch 属性。
           8. 系统 workspace 与用户 workspace 通过 `SetSysWorkspaceForce` / `GetUserWorkspace` 分离。"
           ; :269-277 — the seven-item launch checklist quoted in §3 ; :84 — "4. Host tiling 源使用
           `_GLIBCXX_USE_CXX11_ABI=0`。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a measured DAV_3510 TopK on a named 950 board where dropping `SCHEM_MODE=1` or the
           dynamic-UB launch attribute leaves both correctness and timing unchanged outside the run
           spread — the attributes would then not be part of the running conditions, and the
           migration checklist's insistence on them would be ceremony.
```

# 0333 · Identical kernel source does not reproduce a kernel whose launch attributes were not restored

## 1 · Claim
Upstream asserts that the launch-side resource contract is part of a kernel's running conditions and
that reproducing the kernel source is not sufficient: `缺少 launch 属性时，kernel 代码相同也不代表
运行条件相同`. Upstream asserts five specific attributes to restore when porting the DAV_3510 TopK
template stack: unified special/common dispatch with tiling keys 900001/900002/900003 evaluated
before the common keys; schedule mode 1 (`SCHEM_MODE=1`); the dynamic-UB launch attribute
(`DYN_UBUF_SIZE`) computed by the tiler; the mixed-kernel task type `KERNEL_TYPE_MIX_AIV_1_0`; and
the separation of system from user workspace via `SetSysWorkspaceForce` and `GetUserWorkspace`.
Upstream asserts a further build-side condition — host tiling sources compile with
`_GLIBCXX_USE_CXX11_ABI=0` — and three compile-unit requirements: the kernel, the fallback and the
private transpose translation units are all compiled with the include root at `op_kernel/arch35`,
and the TopK's own transpose file must be used rather than the standalone Transpose operator's
source. Not established here.

## 2 · The wrong branch this removes
The porting mental model is "copy the kernel, adapt the includes, build". Under that model the
launch attributes are invisible: they are not in the kernel source, they produce no compile error
when absent, and the kernel runs. What changes is the resources the kernel is given — how much UB
the launch reserves, whether AIC and AIV are both scheduled, which schedule mode the runtime uses —
and the observable is a performance number that does not reproduce, or a template (mode 8, mixed)
that quietly does not get what it was tiled for.

The diagnosis that follows is the expensive part. A performance gap between a reference
implementation and a port, with byte-identical kernel source, invites a search of the kernel: the
compiler version, the flags, the tiling values. All of them are visible; none of them is the cause.
Upstream's sentence is the shortcut, and it is stated as a general rule rather than as a list — the
list is one family's instance of it.

The second wrong branch is the workspace separation. `SetSysWorkspaceForce` / `GetUserWorkspace`
exist because the runtime's own workspace and the operator's share one allocation; an implementer
who takes the base pointer directly gets a buffer that appears to work until the runtime uses its
part. `0330` §2 already records what a shared TilingData does when a field is read by the wrong
mode; this is the same species one level down, at the allocation.

The third is `_GLIBCXX_USE_CXX11_ABI=0`. It is a host-side ABI flag, it is invisible in every source
file, and getting it wrong produces link errors whose text is about `std::string` and never about
tiling — the same "message far from the cause" shape as `0322`.

## 3 · Ground / Source
The rule, `templates/usage_guide.md:120-121`:

```
6. 恢复 launch 资源契约：统一 special/common 分发，恢复 schedule mode 1、动态 UB、mixed AIV task
   type 和用户 workspace 偏移。缺少 launch 属性时，kernel 代码相同也不代表运行条件相同。
```

The contract as build requirements, `:76-88`:

```
1. 设备侧同时编译 `op_kernel/arch35/top_k_kernel.cpp`、`op_kernel/arch35/fallback/top_k_fallback.cpp`
   和 `op_kernel/arch35/transpose/top_k_transpose_kernel.cpp`，kernel include 根目录设为
   `op_kernel/arch35`。TopK 必须使用自己的 Transpose 文件，不得直接 include 或编译独立 Transpose
   算子源码。
...
4. Host tiling 源使用 `_GLIBCXX_USE_CXX11_ABI=0`。
5. `arch35/fallback/top_k_fallback.cpp` 保留 `TopKLaunchParams`、`calc_topk_params`、`launch_topk`
   三个编译期重命名。
6. special key 900001/900002/900003 先于 common key 分发。
7. mixed kernel 保留 `KERNEL_TYPE_MIX_AIV_1_0`、`SCHEM_MODE=1` 和动态 UB launch 属性。
8. 系统 workspace 与用户 workspace 通过 `SetSysWorkspaceForce` / `GetUserWorkspace` 分离。
```

The same set as a pre-submission checklist, `:269-277`:

```
## 12. Launch 与 workspace 检查表

- [ ] special key 900001/900002/900003 在 common key 前分发。
- [ ] mixed kernel 使用 `KERNEL_TYPE_MIX_AIV_1_0`。
- [ ] launch 属性包含 `SCHEM_MODE=1`。
- [ ] launch 属性包含 tiler 计算的 `DYN_UBUF_SIZE`。
- [ ] `SetSysWorkspaceForce` 后通过 `GetUserWorkspace` 获取用户区。
- [ ] block dim、dynamic UB、workspaceBytes 与 host params 完全一致。
- [ ] common modeType 与实际模板实例一致，未链接到旧 `.so`。
```

Seven items, and — unusually for this shelf — every one of them can fail. The last is the sharpest:
`未链接到旧 .so` is a check against the failure where the source is right, the build succeeds, and
the binary loaded is the previous one. That is a check on the *experiment*, not on the code, and it
belongs to the same family as `0327`'s contamination discriminant: both exist because a result was
once attributed to a change that had not reached the machine.

The refusal to bend the contract to the target project, `:71-72`:

```
不得改写上游 Host 路由、TilingData ABI、Kernel 相对 include、fallback 编译宏或 launch 属性来
迁就框架。
```

The first migration step, `:94-96`, is the record-keeping that makes any of this diagnosable:

```
1. 先冻结行为和基线：固定设备、CANN、编译选项、输入生成、warmup 和计时方式，保存每个 case 的
   values/indices 精度、耗时、tilingKey、modeType、kernel symbol、核数、UB 和 workspace。没有逐
   case 路由记录时，后续很难区分"kernel 变慢"与"tiler 选错"。
```

That paragraph is the best statement of measurement hygiene anywhere in this shelf, and it names
exactly the confound this entry is about — a slowdown that is a routing change wearing a kernel's
clothes.

Nothing here is measured. No attribute is given a cost, and upstream never states what any single
omission does.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. The claim is that a set of
launch-side attributes has observable effect, so the procedure removes them one at a time.

Baseline: the full stack with every attribute in §3 present, run over the `0330` Arm 1 case set,
with the per-case record upstream's step 1 demands — `tilingKey`, `modeType`, kernel symbol, block
dim, dynamic UB, workspace bytes, core count, values/indices accuracy and time.

Then five single-omission builds, kernel source byte-identical in every one:
(a) `SCHEM_MODE=1` dropped; (b) `DYN_UBUF_SIZE` replaced by a static default;
(c) `KERNEL_TYPE_MIX_AIV_1_0` replaced by a non-mixed type; (d) special keys dispatched *after* the
common keys; (e) the user workspace taken from the base pointer without `GetUserWorkspace`.

For each: does it build, does it launch, is it correct, and how does the per-case record differ from
the baseline's. The primary readout is **the record**, not the time — an attribute whose omission
changes which template runs has produced a routing change, and reporting only the time would record
it as a kernel regression, which is the confound.

Arm 6 — the ABI flag, separately: build the host tiling with and without
`_GLIBCXX_USE_CXX11_ABI=0` and record whether it links and what the first uncut error says
(`0345`'s protocol).

Arm 7 — the stale-`.so` check, run as an experiment on the experiment: after building (a), delete
the output and re-run the harness without rebuilding. It **must** fail to load or must be detectably
the old binary. This is the checklist's last item turned into a procedure, and it validates the
whole run's attribution.

Variance floor first: one build, 30 in-process runs, 5 fresh-process runs, IQR over median, with
`0327`'s sibling check applied to every table. Device selection: `npu-smi info -l`;
`npu-smi info -t usages -i <id> -c <chip>` ×3 at 20 s spacing; bind only on three idle samples;
re-sample after; discard the case if the die moved. Refuses to assume: that a free die stays free;
that a die may be substituted; that the binary under test is the binary just built (Arm 7 exists
because that assumption has failed before); that an attribute reached the launch — block dim,
dynamic UB and workspace bytes are echoed from the runtime and compared against the host params, per
the checklist's sixth item.

## 5 · Checker — acceptance declared before the run
Verdict `effect[x]` for each omission `x` ∈ {a…e}, one of: `build-fail`, `launch-fail`,
`wrong-answer`, `route-change`, `time-change`, `none`. Declared before the run: upstream's rule is
**supported** iff at least one omission produces something other than `none` while the kernel source
is byte-identical. The OVERTURN fires iff every omission yields `none`.

`route-change` is declared as a distinct outcome from `time-change` and is checked first, because
the two are confusable and only the per-case record separates them.

Verdict `abi_link` from Arm 6, with the first uncut error line recorded verbatim.
Verdict `stale_so_detected` from Arm 7 — this **must** be true.

The exit code is not the verdict. Three guards.

First — the input that makes this checker go red — Arm 7 *is* the fixture. If a deliberately stale
binary is not detected, then every `none` verdict in the run is void: the harness may have been
running the baseline binary throughout, which is the single most efficient way to produce five clean
"no effect" results. A launch-attribute study that cannot tell it is running the build it thinks it
is has measured nothing, and this is the known blind species in its most literal form.

Second, correctness is checked with the index fetch-back (`0330` §5), not values alone: omission (e)
corrupts a workspace region and a values-only comparison can survive it.

Third, no `time-change` is reported for a case whose `tilingKey` or `modeType` differs from the
baseline's. Those cases are `route-change` and their times are not comparable — which is precisely
the distinction upstream's step 1 exists to preserve.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No attribute was omitted, no
kernel was launched, and no per-case record was produced. Upstream states the rule and gives no
measurement for any single attribute, so there is nothing here to reproduce — only a structure to
test.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. Upstream supplies **no cost figure for any launch attribute**, so
this entry carries a checklist and a general rule, not a magnitude; a consuming skill must not
attach a benefit to restoring any of them. It does not establish what any single omission does — the
five outcomes in §5 are declared, not observed. `SCHEM_MODE`, `DYN_UBUF_SIZE`,
`KERNEL_TYPE_MIX_AIV_1_0` and the 900001/900002/900003 key values are named without their
definitions, valid ranges or defaults, none of which appears anywhere in the document. The three
compile-time renames in `top_k_fallback.cpp` are required without a reason. Whether
`_GLIBCXX_USE_CXX11_ABI=0` is a property of this stack or of the surrounding CANN release is not
stated and is not established. The whole contract is pinned to no toolkit version. BOARD is
`family-claimed(unverified)`: the document targets Ascend 950 / DAV_3510 and names no board.
Nothing transfers to the other book (RULES.md Art. 1).
