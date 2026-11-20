```
ID:        0031-repeattimes-stops-at-255-because-its-parameter-is-a-uint8-not-because-a-hardware-limit-is-stated
LABEL:     trap
LEVEL:     L5 (compute & numerics)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-repeat-limits.md:3 — "**核心问题**：repeatTime 为 uint8_t 时最大值 255，超过会溢出导致计算错误"; ibid:20 — "当 `repeatTime` 为 `uint8_t` 类型时，最大值 **255**"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an installed SDK header declares `repeatTimes` wider than `uint8_t` for the listed APIs, or a repeat count above 255 is shown to compute correctly on a named DAV_2201 board.
```

# 0031 · repeatTimes stops at 255 because its parameter is a uint8 — not because a hardware limit is stated

## 1 · Claim
Upstream asserts that when the `repeatTime` parameter is typed `uint8_t`, its maximum value is 255,
and that exceeding it overflows and produces wrong results rather than an error. Upstream lists the
API families this covers: binary ops (Sub, Add, Mul, Div, Max, Min), unary ops (Exp, Log, Sqrt,
Abs, Neg), scalar ops (Muls, Adds, Divs) and bitwise ops (And, Or, Xor, Not). Upstream states the
limit as a property of the parameter's C++ type. **No source in scope states a hardware repeat
limit.** Not established here.

## 2 · The wrong branch this removes
Two branches, and separating them is the whole entry.

The first: an agent computes `repeatTimes = rowCount` from a shape, `rowCount` is 256, and the cast
to `uint8_t` yields 0. Upstream's own worked case is exactly this (line 56: "// 问题：R=256，
rowCount=256 > 255"). Nothing faults; the instruction executes zero times or the wrong number of
times, and the output is partly stale.

The second, subtler and the reason for the `trap` label: an agent that learns "repeatTimes ≤ 255"
files it as an *architectural* fact and reasons from it — about instruction issue, about the vector
pipeline's depth, about what the machine can do per instruction. It cannot support any of that. The
sentence upstream writes is conditional ("当 `repeatTime` 为 `uint8_t` 类型时"), which means it is
a statement about an API signature, not about silicon. A different overload with a wider parameter
would have a different limit and the same hardware. Reading a type width as a hardware capability
is a measurement/inference conflation with the measurement missing entirely.

What survives as a genuine open question — is there ALSO a DAV_2201 hardware repeat ceiling,
independent of the parameter type? — is posed in this book's STANDING_QUESTIONS and is not answered
by this entry.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-repeat-limits.md`, line 3 (the file's own summary):
"> **核心问题**：repeatTime 为 uint8_t 时最大值 255，超过会溢出导致计算错误"; line 20: "当
`repeatTime` 为 `uint8_t` 类型时，最大值 **255**。"

The type table, line 45: `| \`uint8_t\` | 0 ~ 255 | 最多 255 次迭代 |` — note the table has a
column for the type, implying other types occur.

The API list, lines 123-126, verbatim:
```
| 二元运算 | Sub, Add, Mul, Div, Max, Min | `repeatTime` ≤ 255 |
| 一元运算 | Exp, Log, Sqrt, Abs, Neg | `repeatTime` ≤ 255 |
| 标量运算 | Muls, Adds, Divs | `repeatTime` ≤ 255 |
| 其他 | And, Or, Xor, Not | `repeatTime` ≤ 255 |
```
The mitigation upstream ships, lines 74-76: `constexpr uint32_t MAX_REPEAT_TIMES = 255;` /
`R_max = std::min(R_max, MAX_REPEAT_TIMES);  // 确保 R_max <= 255`.

Restated same-repo: `ops/ascendc-api-best-practices/SKILL.md:23` — "| **repeatTime 限制** |
repeatTimes ≤ 255 | ... | 分批处理 |"; `references/api-quickref.md:61` — "**核心限制**：repeatTime
为 uint8_t 时，最大值 255"; `references/api-restrictions.md:113` — "| **repeatTime 限制** | ... |
uint8_t 最大 255，需分批处理 |". Note that SKILL.md and api-restrictions.md drop the "当…为
uint8_t 时" condition and state the limit flatly — the summary layers lose the qualification that
makes the claim true, which is how a type fact becomes a hardware fact in an agent's notes.

**This corrects a survey claim.** `harvest/surveys/DEEPDIVE_20260824_perf-optimize.md` §5.3 lists
"repeatTimes≤255" under "ESTABLISH FROM SCRATCH (no upstream authority)". Upstream authority exists
and is quoted above; what does not exist is authority for a *hardware* limit. The distinction was
not drawn by the survey.

## 4 · Procedure
Proposed, runnable later; not run. Arm 1 needs no card and is the one that matches the claim.

1. Header arm, read-only: `grep -Rn "repeatTimes\|repeatTime" "$ASCEND_HOME_PATH"/*/include` (note
   `-R`; these trees symlink). Record, per API in the §3 list, the declared parameter type, the
   header path and the toolkit version. This is the claim's own level of authority — an SDK
   header, which is also a genuinely independent origin from this repo.
2. Overflow arm, on a named die (occupancy before and after, no substitution): call `Adds` with a
   computed repeat count of 254, 255 and 256 over a destination poisoned to 0xDEADBEEF, and count
   how many elements were actually written. The claim predicts 256 behaves as 0.
3. Hardware-ceiling arm — this is the standing question, not the claim: if any listed API has a
   wider parameter in the installed SDK, drive it past 255 and find where correctness or throughput
   breaks. If every API is `uint8_t`, record that the hardware ceiling is **unreachable from
   AscendC** and therefore not establishable by this route. That is a legitimate and final answer
   to the standing question and should be written as one.

## 5 · Checker — acceptance declared before the run
`param_type` per API: PASS iff `uint8_t`. Red input: any wider type, which does not overturn the
conditional claim but does mean the flat restatements in SKILL.md are wrong for that API — recorded
against those files, not against this entry.
`written(256)`: PASS iff 0 elements were written — the wrap, identified positively. A clean
correct result at 256 overturns. A partial write of some other count is recorded as-is and the
entry is corrected rather than forced.
Positive fixture for arm 2: run with repeat count 0 against the poisoned destination and confirm
the counter reports 0 written. If it reports non-zero with nothing requested, the counting method
is wrong and the 256 reading means nothing.
Exit code is not the verdict; an overflowed count does not fault.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched. **No architecture is involved in the claim at all** — a
parameter type is a software property, identical on every part the SDK targets, and BOARD is
`family-claimed(unverified)` because this book must name one, not because the claim is board-scoped.
No toolkit version is pinned; upstream pins none, and §4 step 1 exists to supply one.
This entry does NOT establish any hardware repeat limit, and explicitly declines to be read as one.
It does not establish that the 255 cap applies to APIs outside the four listed families, nor to the
`mask`-mode overloads, nor to `DataCopy`-family repeat parameters.
