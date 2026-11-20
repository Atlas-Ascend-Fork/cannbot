```
ID:        0014-on-dav-2201-any-concurrent-accesses-to-one-bank-group-conflict
LABEL:     knowledge
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md:54 — "Atlas 350 的 bank group 上有两组读口和写口，因此**两次读操作访问同一 bank group 的不同 bank 时不会冲突**，但 220x 上同一 bank group 内的任意多次并发访问都会冲突"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired sweep on a named DAV_2201 board shows two reads addressing different banks of one bank group proceeding without a conflict-counter rise — i.e. the read-read rule matches the later architecture rather than the stated 220x rule.
```

# 0014 · On DAV_2201, ANY concurrent accesses to one bank group conflict

## 1 · Claim
Upstream asserts that DAV_2201 (which it calls 220x) has a stricter bank-conflict rule than the
later Atlas 350 generation: on 220x, any number of concurrent accesses inside one bank group
conflict, whereas on 350 two reads to different banks of the same group do not, because that
generation's groups carry two read ports and two write ports. Upstream states the rule as a
three-way table: read-write conflicts on the same **bank** in both generations; write-write
conflicts on the same **bank group** in both; read-read on the same **bank group** for 220x but
on the same **bank** for 350. Not established here.

## 2 · The wrong branch this removes
An agent carries a bank-conflict avoidance recipe backwards from newer material — the 350 rule is
the one written down in the same table, one column over — and concludes that placing its two
source operands in different banks of one group is safe. On DAV_2201 that is a read-read conflict
and the Vector repeat serialises. The failure is invisible in every correctness check and appears
only as an inflated `aiv_vec_ratio`, which points at the arithmetic rather than at the addresses.
The direction matters: the newer part is more permissive, so knowledge transferred forward is
safe and knowledge transferred backward is not — the opposite of the usual assumption, and the
same reversal 0004 and 0005 show for capacities.

## 3 · Ground / Source
`ops/ascendc-performance-best-practices/reference/common/ub_resident_design.md` §2.2.2, the
conflict table at lines 48-52:
```
| 冲突类型 | NPU 220x | Atlas 350 |
| 读写冲突 | 同一 **bank** | 同一 **bank** |
| 写写冲突 | 同一 **bank group** | 同一 **bank group** |
| 读读冲突 | 同一 **bank group** | 同一 **bank**（两个读操作），或**两个以上**读操作同一 bank group |
```
and the explanation at line 54, verbatim: "> Atlas 350 的 bank group 上有两组读口和写口，因此
**两次读操作访问同一 bank group 的不同 bank 时不会冲突**，但 220x 上同一 bank group 内的任意多次
并发访问都会冲突。"

The scope of "220x" is pinned at line 34 of the same file: "> **注意**：不同芯片的 bank 结构和冲突
条件不同，必须查阅对应硬件文档。下文以 NPU 架构版本 220x（Atlas A2/A3 系列）和 Atlas 350 为例说明。"
— so 220x means Atlas A2/A3, which per 0001 is exactly DAV_2201. Note that "220x" is a fourth
spelling for this architecture alongside DAV_2201, `__NPU_ARCH__` 2201 and arch22; upstream's own
vocabulary map (`ops/npu-arch/references/npu-hardware-params.md` §0) does not define it. Recorded
as a vocabulary gap in STANDING_QUESTIONS, not resolved by assumption — though the parenthetical
"（Atlas A2/A3 系列）" makes the intent unambiguous in this one file.

The mechanism (three operands of one Vector instruction are the concurrent accesses) is stated at
lines 68-70: "一个 Vector 指令（如 `Add(dst, src0, src1)`）在同一 Repeat 内会同时读取 `src0`、
`src1` 并写入 `dst`。这三个操作数的 DataBlock 是并发访问的候选冲突源。"

"Atlas 350" is not a token in this book's vocabulary and no claim about it is carried here; it is
quoted only because the 220x rule is stated by contrast with it.

## 4 · Procedure
Proposed, runnable later; not run. The read-read arm is the one that discriminates, so it is the
one built.

1. Name the die; occupancy before and after; no substitution.
2. Three arms, identical except for UB start addresses, verified by md5 to differ only there:
   - A (control): `Add(z, x, y)` with `x` and `y` placed in different bank GROUPS.
   - B (test): `x` and `y` in different banks of the SAME group — 220x predicts a conflict, 350
     predicts none. This is the discriminating arm.
   - C (positive fixture): `x` and `y` at addresses differing by a multiple of the group stride,
     landing on the same bank — every generation predicts a conflict here. If C does NOT show a
     conflict, the instrument is not working and arms A and B carry no information.
3. Collect `aiv_vec_bankgroup_cflt_ratio`, `aiv_vec_bank_cflt_ratio` and `aiv_vec_ratio` per arm,
   five repeats, first discarded, on device (simulation cannot produce these counters — 0052).

## 5 · Checker — acceptance declared before the run
Verdict: the triple of `aiv_vec_bankgroup_cflt_ratio` medians `(rA, rB, rC)`.
Gate first, before any verdict is read: `rC` must exceed `rA` by more than three times A's spread.
If it does not, the run is VOID and no verdict is issued — arm C is the planted positive this
checker is required to find, and a checker that cannot see a conflict it constructed on purpose
cannot be trusted to report its absence elsewhere.
Given the gate passes: the claim is upheld iff `rB` is close to `rC` (conflict present); it is
overturned iff `rB` is close to `rA` (no conflict), which would mean DAV_2201 behaves like the
later generation on reads.
"Close to" is defined before the run as within three times arm A's spread of the respective
reference. A result between the two is recorded as intermediate and the entry is corrected in
place rather than forced to a side. Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; per-arch. This entry does not establish the cycle penalty of a
conflict — upstream says only "多拍" ("several cycles", line 30) and explicitly declines to
quantify: "具体拍数因芯片和冲突 DataBlock 数量而异". It does not establish the read-write or
write-write rows of the table; §4 builds only the read-read arm, so a run of this procedure
verifies one third of the quoted claim and §1 would have to be narrowed accordingly. It says
nothing about Atlas 350 / DAV_3510, and nothing about whether the rule differs across DAV_2201
sub-models.
