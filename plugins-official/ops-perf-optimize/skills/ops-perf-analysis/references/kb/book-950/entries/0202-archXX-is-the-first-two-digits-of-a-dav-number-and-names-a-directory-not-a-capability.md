```
ID:        0202-archXX-is-the-first-two-digits-of-a-dav-number-and-names-a-directory-not-a-capability
LABEL:     boundary
LEVEL:     L8 (toolchain & build)
STRATUM:   harvested — one upstream origin (ops/npu-arch) states the naming rule; nothing was
           compiled or queried to show that two chips sharing an archXX directory share anything.
BOARD:     950PR, 950DT
SOURCE:    ops/npu-arch/references/npu-arch-guide.md:36-43 — "算子仓中按架构划分的目录使用 `archXX`
           命名，取 `DAV_XXXX` 前两位数字" … "命名规则：`archXX` = `arch` + DAV 编号前两位。
           如 DAV_**22**01 → arch22，DAV_**35**10 → arch35。"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  two `NpuArch` values sharing the same first two digits — hence the same `archXX`
           directory by upstream's own rule — that differ in any hardware constant an operator
           depends on. One such pair falsifies "archXX scopes a claim".
```

# 0202 · `archXX` is the first two digits of a DAV number and names a directory, not a capability

## 1 · Claim
Upstream asserts that `archXX` is a purely lexical abbreviation: take the `DAV_XXXX` number and
keep its first two digits, so `DAV_3510` becomes `arch35`. Upstream introduces it as an operator-repo
**directory** naming convention. Upstream nowhere asserts that `archXX` is a scope in which
hardware constants are constant. Not established here.

## 2 · The wrong branch this removes
Without this entry an agent reads `arch35` in a path, a card header, or a `#if` and treats it as a
chip scope — the same way `DAV_3510` is one. It then labels a measurement "arch35" and reuses the
number on any target whose directory is `arch35`. That is a scope widening performed by a string
operation. Nothing catches it: the code compiles into the right directory, the number looks
plausible, and there is no assertion anywhere that would fire. See 0205 — this machine's own
toolkit ships a second `NpuArch` whose first two digits are `35` and which shares almost nothing
with `DAV_3510`.

## 3 · Ground / Source
`ops/npu-arch/references/npu-arch-guide.md:34-43`, quoted in full:

> ### 架构目录简写（archXX）
> 算子仓中按架构划分的目录使用 `archXX` 命名，取 `DAV_XXXX` 前两位数字：
>
> | 目录 | 对应 NpuArch | 芯片 |
> |------|-------------|------|
> | **arch22** | DAV_2201 | Ascend910B 系列、Ascend910_93 |
> | **arch35** | DAV_3510 | Ascend950DT / Ascend950PR |
>
> > 命名规则：`archXX` = `arch` + DAV 编号前两位。如 DAV_**22**01 → arch22，DAV_**35**10 → arch35。

The table lists exactly one `NpuArch` per directory, which is what makes the substitution look
safe. The table is a list of the arch directories that exist in the operator repo, not a statement
that the mapping is injective. `SKILL.md:16` states the abbreviation again and immediately attaches
the repo-wide warning to its sibling macro: `__DAV_C310__` … **不可按数值推断** — see 0203.

Downstream, the whole 950 card library is scoped this way and only this way:
`ascendc-perf-optimize/references/single-core-pipeline/techniques/INDEX.md:5` — "卡片代码统一 A5
（arch3510）RegBase；非 A5 平台用 `#if defined(__NPU_ARCH__) && (__NPU_ARCH__ == 3510)` 编译期隔离".
Note that the *fence* is written on the four-digit `__NPU_ARCH__`, which is exact, while the
*label* is written on `arch3510`/`arch35`, which is not. The fence is the correct construct; this
entry exists so the label is not mistaken for one.

## 4 · Procedure
Runnable later on `950PR`. This claim is falsified by enumeration, not by timing, so the procedure
is a read plus a build, and it names its own refusals.

Step 1 — enumerate. Over the platform-config directory of the pinned toolkit, print
`(file, NpuArch)` for every `.ini`, then group by the first two digits of `NpuArch`:

```bash
D="$ASCEND_HOME_PATH/$(uname -m)-linux/data/platform_config"
for f in "$D"/*.ini; do
  a=$(grep -m1 '^NpuArch=' "$f" | cut -d= -f2)
  printf '%s\t%s\t%s\n' "${a:0:2}" "$a" "$(basename "$f")"
done | sort
```

Step 2 — for every group with more than one distinct `NpuArch`, diff the fields an operator
actually depends on (`ub_size`, `l1_size`, `l0_c_size`, `bt_size`, `core_type_list`,
`vector_core_cnt`, `cube_m_size`).

Step 3 — on the board, compile one kernel under `#if __NPU_ARCH__ == 3510` and confirm the branch
is taken; then compile the same source with the archXX-shaped guard the operator repo uses and
confirm what it selects. The procedure refuses to assume that the directory a file lives in has any
effect on the preprocessor: that link, if it exists, is a build-system convention and must be shown,
not assumed.

## 5 · Checker — acceptance declared before the run
Verdict variable `archxx_is_a_scope`. It is declared FALSE-on-any-hit: `archxx_is_a_scope` is false
as soon as Step 2 finds one two-digit group containing two `NpuArch` values that differ in any
listed field. Process exit code is not the verdict — `grep` exiting 1 on an ini with no `NpuArch`
line must not read as "no collision".

The checker can go red in the direction that matters and it is a positive fixture by construction:
it must FIND a collision, not confirm the absence of one. Its blindness case is stated: if the
enumeration silently skips files (unreadable, symlinked directory not followed — use `grep -R`, not
`grep -r`, in these trees), it will report a clean group that is not clean. So Step 1 additionally
asserts that the file count it processed equals `ls "$D"/*.ini | wc -l`, and a mismatch is red.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured; no board was contacted and no kernel was built. This entry establishes only
that upstream defines `archXX` lexically and never claims it bounds hardware behaviour; it does not
establish that upstream *believes* `archXX` is safe, nor that any specific downstream skill has
actually widened a claim through it. It does not enumerate which `NpuArch` values collide in a
two-digit group — that is 0205, which uses a different origin (the installed ini set). It says
nothing about `arch22` or any other directory belonging to the other book (RULES.md Art. 1): the
`DAV_2201` row is quoted only as part of upstream's verbatim table. And it does not establish that
the operator repo's directory layout actually drives compilation on this toolkit; §4 Step 3 is
written precisely because that link is assumed everywhere and demonstrated nowhere.
