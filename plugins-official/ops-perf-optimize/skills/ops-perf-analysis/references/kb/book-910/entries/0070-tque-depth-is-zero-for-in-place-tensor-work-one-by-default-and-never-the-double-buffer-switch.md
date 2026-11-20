```
ID:        0070-tque-depth-is-zero-for-in-place-tensor-work-one-by-default-and-never-the-double-buffer-switch
LABEL:     knowledge
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-api-best-practices/references/api-buffer.md:43-47 — "| `depth=1` | **默认推荐**，非 Tensor 原地操作 | 编译器有特殊优化，性能更好 | / | `depth=0` | **Tensor 原地操作** | 需要设置 | / | `depth=2` | 连续 2 次 EnQue 场景 | 与 InitBuffer 的 num 参数独立 |"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an in-place tensor operation works correctly through a `TQue` with `depth = 1` on a named DAV_2201 board, or `depth = 1` shows no compiler advantage over `depth = 2` at equal `num`.
```

# 0070 · TQue depth is zero for in-place tensor work, one by default, and never the double-buffer switch

## 1 · Claim
Upstream asserts three values for the `TQue` template's `depth` parameter with distinct meanings:
`depth = 1` is the default recommendation for non-in-place tensor operations and receives a special
compiler optimisation making it faster; `depth = 0` is required for in-place tensor operations; and
`depth = 2` serves the case of two consecutive `EnQue` calls and is independent of `InitBuffer`'s
`num`. Upstream asserts `depth` is unrelated to double buffering. Not established here.

## 2 · The wrong branch this removes
0043 established the headline — double buffering is `InitBuffer`'s `num`, not the template `depth`
— and closed the branch where an agent sets `depth = 2` expecting two buffers. This entry closes
what 0043 left open: **what `depth` is actually for**, which 0043 §7 explicitly recorded as
unestablished ("no source in scope gives a case where a depth above 1 is needed").

Two wrong branches follow from not knowing:
- **In-place work silently needs `depth = 0`.** An agent writing a kernel that reads and writes the
  same tensor through a queue leaves `depth` at the recommended 1 and, per upstream, has the wrong
  setting. Nothing in the phrase "queue depth" suggests that zero is a legal or meaningful value,
  and an agent reasoning from the name will never try it. Upstream does not say what goes wrong,
  which is why §4 is built to find out rather than to confirm.
- **`depth = 1` is not merely a safe default; it is the optimised path.** An agent that raises
  `depth` "to be safe" — a common instinct with buffer-shaped parameters — loses a compiler
  optimisation upstream says exists. The cautious choice is the slower one.

Note the interaction with 0067: `depth` does not consume additional buffers, so it does not affect
the four-queue ceiling under double buffering. `num` does. Two parameters, one of which is a
resource and one of which is not.

## 3 · Ground / Source
`ops/ascendc-api-best-practices/references/api-buffer.md` §"depth 参数关键说明", lines 43-49,
verbatim in full:
```
| depth 值 | 适用场景 | 说明 |
| `depth=1` | **默认推荐**，非 Tensor 原地操作 | 编译器有特殊优化，性能更好 |
| `depth=0` | **Tensor 原地操作** | 需要设置 |
| `depth=2` | 连续 2 次 EnQue 场景 | 与 InitBuffer 的 num 参数独立 |
```
"**注意**：`depth` 与 Double Buffer 无关。Double Buffer 由 `InitBuffer` 的 `num` 参数控制。"

The template declaration, line 32: `template <TPosition pos, int32_t depth, auto mask = 0> class
TQue;`, with the parameter table at 35-39 giving `depth` as "队列深度，表示可连续 EnQue/DeQue 的
次数" and `mask` as "数据格式转换（ND↔NZ）或编译期优化参数". Note `depth` is `int32_t`, so 0 is
representable and negative values are too — upstream says nothing about those.

The 常见误区 table, lines 229-234, states the same three points as errors to avoid, including
"| depth 越大越好 | 模板 depth 通常设为 1，性价比最高 |".

Same claim reached from the A2-verified practice side, same repo (one origin):
`ops/ascendc-performance-best-practices/reference/sort/radix_sort.md:309` — "| `TQue<VECIN, 1>` +
`InitBuffer(que, 2, size)` | 支持真正并行 | double buffer 由 InitBuffer num=2 控制，depth=1 即可 |",
which is 0043's source and confirms `depth = 1` in a measured context — but says nothing about 0.

**What is missing.** No source in scope defines what a "Tensor 原地操作" is in this API's terms,
says what happens if `depth = 1` is used for one, or names the compiler optimisation that `depth = 1`
enables. Three assertions, no mechanism for any of them. That is why this entry is `knowledge`
rather than `trap`: the in-place case has the shape of a trap, and without knowing the failure mode
this book cannot claim one.

## 4 · Procedure
Proposed, runnable later; not run.

1. Name the die; occupancy before and after; no substitution.
2. In-place arm, the substance: one kernel performing an in-place operation through a queue —
   `AllocTensor`, `DataCopyPad` in, compute writing to the same `LocalTensor`, `EnQue` the same
   tensor, `DeQue`, copy out — built at `depth = 0` and at `depth = 1`, md5-confirmed to differ only
   in the template argument. Destination poisoned; verify every element against a host reference.
3. Record the failure mode at `depth = 1` if there is one: wrong data, hang, or launch failure.
   These are three different findings and upstream names none of them.
4. Optimisation arm: a non-in-place kernel at `depth = 1` and `depth = 2`, identical `num`,
   identical work, comparing `aiv_time` and the device `.text` size. Upstream claims a compiler
   advantage at 1; the `.text` comparison is what would show a different code path rather than
   merely a different time.
5. Five repeats each, first discarded, arms interleaved.

## 5 · Checker — acceptance declared before the run
`inplace_correct(depth)`: PASS for the claim iff correct at `depth = 0` and NOT correct at
`depth = 1`. Both clauses required — if both are correct, the `depth = 0` requirement is not
load-bearing on this path and the entry is narrowed, which is a useful result and must not be
reported as a pass.
`depth1_advantage`: `(t(depth=2) − t(depth=1)) / t(depth=1)`, with the run-to-run spread of the
`depth = 1` arm against itself established FIRST from its five repeats and stated as the threshold
before the arms are compared. The claim is upheld iff the advantage exceeds that spread.
The `.text` comparison is a gate on interpretation, not a metric: if the two builds are
byte-identical, any timing difference is run variance and the arm is VOID. **A performance claim
certified from two builds that produce identical code carries no attribution** — that check runs
first.
Exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured; no board touched; no architecture stated by the source — a template parameter's
semantics are a software property and may differ between CANN releases, none pinned. This entry does
not establish what "Tensor 原地操作" means in this API's terms, nor what goes wrong without
`depth = 0` — §4 exists because upstream does not say. It does not establish the compiler
optimisation's nature or size. It does not cover `depth` above 2, or the `mask` template parameter,
which upstream describes as serving both format conversion and compile-time optimisation without
elaborating either. The interaction with the four-queue ceiling of 0067 is reasoned in §2 and is
not established.
