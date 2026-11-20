```
ID:        0047-the-l2-cache-hint-enum-carries-four-modes-and-upstream-names-two
LABEL:     boundary
LEVEL:     L2 (memory hierarchy & residency)
STRATUM:   corroborated — upstream text plus a second, independent origin (the installed CANN
           9.0.0-beta.2 headers, read-only); nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/mem-05-l2-bypass-one-shot.md:27-28 — "gmWeight.SetL2CacheHint(canBypass ? CacheMode::CACHE_MODE_DISABLE : CacheMode::CACHE_MODE_NORMAL);"
           INSTALLED TOOLKIT (independent origin, read-only): /usr/local/Ascend/cann-9.0.0-beta.2/arm64-linux/asc/impl/basic_api/utils/kernel_utils_macros.h:235-240 — "enum class CacheMode { CACHE_MODE_DISABLE = 0, CACHE_MODE_NORMAL = 1, CACHE_MODE_LAST = 2, CACHE_MODE_PERSISTENT = 4 };"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a header read at another toolkit pin in which the enum has a different membership, or a
           run on a named 950 board in which `CACHE_MODE_LAST` or `CACHE_MODE_PERSISTENT` is
           rejected or behaves identically to `CACHE_MODE_NORMAL` — the two unnamed modes would
           then be vestigial rather than unexplored.
```

# 0047 · The L2 cache-hint enum carries four modes and upstream names two

## 1 · Claim
Upstream asserts an L2 residency control with two settings: `CACHE_MODE_DISABLE` for a provably
one-shot stream and `CACHE_MODE_NORMAL` otherwise. The installed CANN 9.0.0-beta.2 headers declare
`enum class CacheMode` with four enumerators — `CACHE_MODE_DISABLE = 0`, `CACHE_MODE_NORMAL = 1`,
`CACHE_MODE_LAST = 2`, `CACHE_MODE_PERSISTENT = 4` — and a companion `enum class CacheRwMode`
with `READ = 1`, `WRITE = 2`, `RW = 3`. The two enumerators upstream uses exist; two more exist and
appear nowhere in the skill. Both origins are documents; nothing was compiled or measured.

## 2 · The wrong branch this removes
A knowledge base built only from upstream's prose would tell a consuming agent that L2 policy is a
binary — cache or do not cache. Faced with data that is reused but only once more, or with a
working set that should stay resident across an operator boundary, the agent has no vocabulary for
the question and will either force it into the binary or invent an API. Recording the whole enum
costs nothing and is honest: two of the four modes are unexplored territory with names that suggest
their purpose (a last-level-only hint and a persistent-residency hint), and neither this book nor
upstream can say what they do.

This is also the shape of a general check on any harvested API claim: read the enum, not only the
usage. A document that shows two values of a four-valued type has told you about the document's
scope, not the type's.

## 3 · Ground / Source
Origin 1: `mem-05:19-29`, where the two named modes appear in the after-form, with the preceding
comment `SetL2CacheHint 的可用枚举以当前 CANN 头文件为准` — upstream explicitly defers the
enumeration to the header, which is what makes this entry a completion of their instruction rather
than a correction of their text. The card's stop rules (`:37-42`) discuss only bypass-or-not.

Origin 2, independent per `form/STRATA.md` S2, read-only:
`kernel_utils_macros.h:235-246` (same content also at
`arm64-linux/ascendc/include/basic_api/impl/utils/kernel_utils_macros.h` and
`arm64-linux/tikcpp/tikcfw/impl/utils/kernel_utils_macros.h` — copies within one installation, not
extra origins), plus the interface declaration
`arm64-linux/asc/include/interface/kernel_tensor.h:259` — `__aicore__ inline void
SetL2CacheHint(CacheMode mode);` — and the default `:270` — `CacheMode cacheMode_ =
CacheMode::CACHE_MODE_NORMAL;`, i.e. normal caching is the state a `GlobalTensor` starts in.

Two observations about the values that a consumer should not over-read: the enumerators are 0, 1,
2 and 4, which is a bit-pattern-shaped set rather than a dense sequence, and
`impl/basic_api/kernel_tensor_impl.h:1159-1191,1574` branches on `== CACHE_MODE_NORMAL` — so the
implementation distinguishes normal from everything else at those points, which says nothing about
how the other three differ from each other.

## 4 · Procedure
Arm 1 is read-only and already re-derivable; arm 2 needs a card and is the only way to learn what
the two unnamed modes do.
```bash
# read-only; -R follows symlinked dirs, -r does not
T=/usr/local/Ascend/cann-9.0.0-beta.2
grep -RIn "enum class CacheMode" -A6 $T --include=*.h | head -20
grep -RIn "CACHE_MODE_LAST\|CACHE_MODE_PERSISTENT" $T --include=*.h | head
```
Arm 2 (later phase, needs a card; device selection per 0010, board token from the driver readout):
build the mem-05 experiment of 0045 four times, once per mode, on the same problem in both regimes
(one-shot and re-read), and record `aiv_time`, L2 hit rate and DDR bytes for each mode.

## 5 · Checker — acceptance declared before the run
For arm 1, verdict variable `enum_members` — the corroborated claim of this entry is that it has
exactly four members with the values quoted. For arm 2, verdict variable
`mode_distinguishable(m)` = true iff mode m's L2 hit rate differs from `CACHE_MODE_NORMAL`'s by
more than spread in at least one regime. A mode that is indistinguishable in both regimes is
reported as such — that is a real result about the toolkit, not a failed experiment.

Exit code is not the verdict. A build that fails to compile with a given enumerator is recorded as
`mode_unavailable` with the diagnostic text, not treated as an error to be worked around.

Red input: `CACHE_MODE_DISABLE` in the one-shot regime, where 0045 predicts a visible difference.
If even that mode is indistinguishable, the counters are not resolving L2 behaviour and no
statement about the other modes follows.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing compiled, run or measured. It establishes the enum's membership at one toolkit pin on one
machine and nothing about any board — a hint is a request to a cache, and what the cache does with
it is not visible in a header. It does not establish what `CACHE_MODE_LAST` or
`CACHE_MODE_PERSISTENT` mean; the names are suggestive and are not evidence. It says nothing about
`CacheRwMode`'s interaction with these values, about which modes are legal on which tensor
positions, or about the 910 family.
