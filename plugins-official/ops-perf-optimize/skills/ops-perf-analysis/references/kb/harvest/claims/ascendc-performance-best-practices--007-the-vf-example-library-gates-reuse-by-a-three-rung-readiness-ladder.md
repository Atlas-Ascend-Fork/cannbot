# CARD · ascendc-performance-best-practices 007 — the VF example library gates reuse by a three-rung readiness ladder

**BOOK: 950 — candidate, deferred by the 950-bp a later harvest pass harvester because the 0351–0399 block owned
by another a later harvest pass agent covers this neighbourhood.**

## The claim, re-verified 2026-08-24
`reference/regbase/README.md:9-13`:

> ## 先看 readiness
>
> | readiness | 能做什么 | 不能做什么 |
> |---|---|---|
> | `compile_verified_skeleton` | 在记录的 SDK、架构、编译契约和实例化范围内作为集成起点 | 不能推导
>   目标工程可编译、精度正确或有性能收益 |
> | `annotated_excerpt` | 离线读取本地真实代码摘录和逐段注解，作为目标工程适配骨架 | 摘录不是独立类；
>   省略上下文必须由目标工程补齐并重验 |
> | `reference_only` | 做算法和 shape/layout 选型 | 在完成目标工程最小编译复核前不能称为实现候选 |

and the same ladder restated as a hard gate in the shelf's own SKILL.md (`:112`):

> 只有 `readiness=compile_verified_skeleton` 才能在其记录范围内作为集成起点；`annotated_excerpt`
> 必须读取摘录和注解、补齐目标上下文，`reference_only` 必须先补编译复核。禁止凭记忆拼写 Reg API，
> 禁止把 `not_run` 状态表述成"已编译验证"。

and the scope limit that goes with the top rung (`SKILL.md:115`):

> 范例的算法结构可以复用，但其声明作用域、VF 入口和构建 flags 只在 `catalog.json` 记录的
> `example_build_contract` 下成立。复制前必须把范例契约与目标 `vf-preflight.json` 对比；契约不同或
> 未知时，条目最多标为"算法可参考/集成边界待验证"，不得标为"✅可直接拷贝使用"。

## Why this is worth an entry eventually
It is a **stratum system**, built by another team, for the same reason this book has one: to stop a
reader confusing "this compiled once, here, under these flags" with "this works". Each rung's
right-hand column is a statement of what the evidence does *not* license — the same shape as
`950:0343`'s build-contract table and as `form/STRATA.md`'s own hard rules. Two independent teams
arriving at "the evidence class must travel with the artifact" is worth recording as a convergence.

The specific content that is not yet in book-950: the three rungs and their names; the prohibition on
reporting `not_run` as verified; the rule that the top rung's *algorithm* transfers while its
declaration scope, VF entry and build flags do not (which is `950:0343`'s claim, applied to reuse rather
than to diagnosis); and the ceiling — an entry whose contract differs from the target's may be
labelled at most "algorithm referenceable, integration boundary unverified" and never
"✅ directly copyable".

## Why it is a card now
`book-950/entries/0351–0385` are being written by another a later harvest pass agent whose brief covers the
regbase and SIMT remainder, and several of its slugs sit directly on this material — `950:0355` (the
three regbase layers as a partition of concerns), `950:0371` (a compatibility case in the regbase tree
whose evidence is not regbase), `950:0372` (queue constructs as MemBase leakage in one file and normal in
another). Entering the readiness ladder from `0301–0349` would risk a duplicate that neither agent
could see at drafting time, which is exactly the failure the anti-duplication rule exists to
prevent.

`950:0343` and `950:0344` were entered from this same `regbase/` directory because they are about the
**compile FAQ** (`cann_version_compat_faq.md`), which no `950:0351`+ slug touches, and because `950:0343`'s
build-contract taxonomy is load-bearing for four other entries in this block.

## What a later pass must check before entering it
Whether `950:0355` already carries the readiness ladder. If it does, this card resolves into it and
nothing further is owed. If it carries only the *layer* partition (design / paradigm / API) and not
the *readiness* partition, they are different axes and both belong.

Also owed and not done: `catalog.json` was never opened. It is the machine-readable index the whole
ladder is expressed in, it records `match_hints`, `example_build_contract` and per-entry validation
state, and reading it would settle how many entries sit at each rung — which is the one quantitative
fact available about this library and costs nothing.

## Guessed level
L8 (toolchain & build), or L7 (verification) — the ladder is about evidence class, which argues L7,
while every rung's distinction is a build-contract distinction, which argues L8.

## Evidence class
recipe-no-numbers, with an unusually explicit statement of what each evidence class does not
support. No measurement anywhere; none is needed for what it claims.

## OVERTURN sketch
A `catalog.json` entry marked `compile_verified_skeleton` whose recorded `example_build_contract` is
absent or `unknown` — the top rung would then be granted without the evidence its own definition
requires, and the ladder would be documentation rather than a gate.

## Disposition
Deferred to avoid a collision. Recorded in `harvest/standing/950-bp.md` Q-950bp-14. Check `950:0355`
first; read `catalog.json` before drafting either way.
