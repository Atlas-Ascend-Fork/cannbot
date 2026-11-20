```
ID:        0302-the-pingpong-cycle-gain-is-attributed-by-its-own-author-to-a-loop-change-not-to-pipeline-overlap
LABEL:     trap
LEVEL:     L9 (performance)
STRATUM:   harvested — one upstream origin (their skills repo); nothing measured, nothing compiled
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-performance-best-practices/reference/matmul/pingpong_design.md:211-227 —
           "**现象**：优化后 cycle 数下降了（42.4k → 30.2k），但未达到理论预期的 ~21k cycles。"
           · "这意味着虽然 L1/L0 地址已经做了 pingpong 分离，但 **事件同步层面仍是串行** — MTE2 与
           MTE1 之间、MTE1 与 CUBE 之间并未真正实现异步流水。性能提升主要来自 kL1 从 1024 调整为
           768 带来的循环结构变化，而非真正的流水并行。"
SOURCE:    same file:5 — "预期 case 总时间缩短至原来的 50%–60%"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired build on a named 950 board in which moving `WaitFlag<MTE2_MTE1>` away from its
           `SetFlag` — the only variable — leaves cycle count unchanged within the run spread. The
           tight coupling would then not be what caps the gain, and upstream's own diagnosis of its
           own measurement would be wrong.
```

# 0302 · The ping-pong cycle gain is attributed by its own author to a loop change, not to pipeline overlap

## 1 · Claim
Upstream asserts a measurement and, in the same passage, refuses the obvious reading of it. The
measurement: converting a naive matmul to the ping-pong double-buffered form took the case from
42.4 k cycles to 30.2 k, against a theoretical target of about 21 k. The refusal: upstream asserts
that the implementation still holds `SetFlag<MTE2_MTE1>` and `WaitFlag<MTE2_MTE1>` adjacent
(likewise `MTE1_M` in the inner loop), so that although L1 and L0 addresses are ping-pong separated,
the *event* layer is still serial and no genuine MTE2/MTE1/CUBE overlap exists — and therefore that
the observed gain came mainly from `kL1` changing 1024 → 768 and the loop structure changing with
it, not from pipelining. Not established here.

Upstream separately asserts, in the same file's §1, an expectation of "总时间缩短至原来的 50 %–60 %".
The measured `30.2 / 42.4 = 71 %` does not reach it, and §7 of this entry records that the two
statements sit in one document without either being withdrawn.

## 2 · The wrong branch this removes
This entry is not about matmul. It is about what a harness agent does with a two-point comparison.

Without it, the agent reads "naive 42.4 k → pingpong 30.2 k" and reports a 29 % win for double
buffering. That sentence is a measurement fused to an inference: the *number* is real, the
*attribution* is not, because two things changed between the builds — the buffering scheme and
`kL1`. A two-point comparison of two different builds carries no attribution at all, and the
agent has no way to know which half it is quoting. It will then recommend double buffering to the
next operator on the strength of a gain that may have come from a loop-count change available
without any buffering work.

The second wrong branch is the mirror image and is worse: an agent that *does* the double-buffering
work, measures a gain, and stops. Upstream's own reading says the pipeline is still serial — so the
remaining 9 k cycles to target are still on the table, and the "success" hides them. The disclosed
signature to look for is stated: `SetFlag` immediately followed by `WaitFlag` on the same event id.
That is a source-level grep, not a profile.

What makes this entry worth a slot rather than a footnote is that upstream did the separation
itself, on its own result, against its own interest. That is the form this book exists to transmit,
and it is rarer in this shelf than any number in it.

## 3 · Ground / Source
`pingpong_design.md:209-227`, the whole item:

```
### 问题 3：MTE2_MTE1 事件同步仍然紧耦合（性能隐患）

**现象**：优化后 cycle 数下降了（42.4k → 30.2k），但未达到理论预期的 ~21k cycles。

**原因**：当前实现中第 194-195 行仍保留了 `SetFlag<MTE2_MTE1>` + `WaitFlag<MTE2_MTE1>` 紧耦合：

AscendC::SetFlag<AscendC::HardEvent::MTE2_MTE1>(l1BufId);
AscendC::WaitFlag<AscendC::HardEvent::MTE2_MTE1>(l1BufId);  // ← 紧跟 Wait，MTE2 搬完后仍需等待才能开始 MTE1

同样，内层循环中 `MTE1_M` 也是紧耦合（第 241-242 行）：
...
这意味着虽然 L1/L0 地址已经做了 pingpong 分离，但 **事件同步层面仍是串行** — MTE2 与 MTE1 之间、
MTE1 与 CUBE 之间并未真正实现异步流水。性能提升主要来自 kL1 从 1024 调整为 768 带来的循环结构
变化，而非真正的流水并行。
```

The prescribed repair, `:229-236`:

```
**解决方案**：要实现真正的流水并行，需将 `WaitFlag` 移到实际消费数据的位置，而非紧跟在 `SetFlag`
后面。参考设计文档第 4.1 节伪代码中的同步模式：

// 正确的流水同步模式：SetFlag 和 WaitFlag 分离
SetFlag<MTE2_MTE1>(l1BufId)     // MTE2 搬完后立即通知
// ... MTE2 可以继续搬下一轮到另一个 buffer ...
WaitFlag<MTE2_MTE1>(l1BufId)    // 在内层循环入口处才等待（此时 MTE2 可能已搬完下一轮）
```

Note that §4.1 of the same file — the *design* pseudocode this item points at as correct — itself
writes `SetFlag<MTE2_MTE1>(l1BufId)` on line 100 and `WaitFlag<MTE2_MTE1>(l1BufId)` on line 101,
adjacent. So the document's own reference pseudocode exhibits the defect the document diagnoses.
That is a second-order finding and is recorded in `harvest/standing/950-bp.md`, not treated as
evidence that either statement is wrong.

`42.4 / 30.2 = 1.404`; `30.2 / 42.4 = 71.2 %`. The §1 expectation is `50 %–60 %`. Neither figure
carries a repeat count, a variance figure, a board, a tool, a date or a CANN pin. `~21k` is given as
"理论预期" with no derivation shown.

The measured/inferred split, stated at sentence level because this book requires it:
**measured** — 42.4 k, 30.2 k. **not measured** — the ~21 k target, the claim that no real overlap
occurs, and the attribution of the gain to `kL1`. The last of those is an inference from reading the
source (adjacent Set/Wait), which is good evidence and is not a measurement.

## 4 · Procedure
Proposed, runnable later on a named 950 board. Never run in this phase. The design is dictated by
§2: the upstream number cannot be attributed, so the procedure's job is to build the arms that can.

Four builds, one variable between each adjacent pair:

- **B0** naive, `kL1 = 1024` (`L1_BUFFER_NUM = 4`, single L1 slot).
- **B1** naive, `kL1 = 768`. *Isolates the loop-structure change alone.*
- **B2** ping-pong, `kL1 = 768`, `SetFlag`/`WaitFlag` adjacent — upstream's measured build.
- **B3** ping-pong, `kL1 = 768`, `WaitFlag` moved to the inner-loop entry — upstream's prescribed
  repair, barrier placement the only difference from B2.

B0 must be built at `kL1 = 1024` even though `0301` says the ping-pong form overflows there: the
single-slot naive build is exactly half the footprint, so it fits, and that asymmetry is the point.

Measure on one part, one CANN pin, one build flag set: kernel cycles, `mac`, `mte1`, `mte2`,
`fixpipe`, `scalar` segments (`msprof --aic-metrics=PipeUtilization`), and outer-loop trip count
echoed from the kernel. Variance floor first: 30 in-process runs and 5 fresh-process runs per
build, IQR over median, reported beside every difference.

Disassemble B2 and B3 and confirm the barrier really moved and that nothing else did. Without this
step a null result between B2 and B3 is unattributable — the compiler may have hoisted the wait in
B2 or reinserted it in B3, and "we changed the source" is not "the machine changed".

The procedure refuses to assume: that a free die stays free (occupancy sampled three times at 20 s
spacing before binding, re-sampled after, case discarded if the die moved); that a die may be
substituted; that the ~21 k figure means anything until someone shows its derivation — it is
recorded as `unattributed` and no arm is scored against it.

## 5 · Checker — acceptance declared before the run
Verdict variables, all declared now, all with the floor attached:

`loop_share` = `(B0 − B1) / (B0 − B2)` — the fraction of the total gain explained by the `kL1`
change alone. `pipe_share` = `(B1 − B2) / (B0 − B2)` — the fraction explained by ping-pong at fixed
`kL1`. They sum to 1 by construction, which is why both are reported and neither is trusted alone.

Declared before the run: upstream's diagnosis is **supported** iff `loop_share > pipe_share`
outside the floor. It is **contradicted** iff `pipe_share > loop_share` outside the floor — and in
that case this entry is corrected in place, because upstream would have mis-attributed its own
result, and that correction is more valuable than the confirmation.

`barrier_gain` = `(B2 − B3) / B2`, the payoff of the prescribed repair. The OVERTURN fires iff
`barrier_gain` is inside the floor *and* the disassembly confirms the barrier moved: the tight
coupling would then not be what caps the gain.

The exit code is not the verdict. Three guards.

First: all four builds are compared elementwise against one CPU reference. A barrier removal that
produces a fast wrong answer is precisely the failure this family's precision note (`:162`,
"必须通过 `verify_result.py` 的精度校验") exists for, and a timing-only checker would score it as
the best result in the table.

Second — the checker must be able to go red, and here is the input that does it. B1 and B2 are
built from the same source tree with one `#define` different. If `loop_share` and `pipe_share`
are computed and B1's echoed outer-loop trip count is *identical* to B0's, then `kL1` did not
actually change between them, the isolation failed, and every share is void. The trip count is
echoed for exactly this reason: it is a positive fixture the arm must find, not a line the checker
hopes to read.

Third: no share is reported without its floor. A gain decomposition built on differences smaller
than run spread is arithmetic, not attribution — which is the whole subject of this entry.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. 42.4 k, 30.2 k and ~21 k
are upstream's figures on an unnamed part; this book has reproduced none of them, and the
decomposition §5 defines has never been computed for any build.

## 7 · Scope limits — what this entry does NOT establish
Nothing was measured or compiled. The entry does not establish that ping-pong double buffering
helps, does not establish that it does not, and does not establish the size of either half — it
establishes that upstream's own text says the published number cannot be read as the first of
these. Upstream's cycle figures carry no board, no tool, no repeat count, no variance and no CANN
pin, so their precision is not their reliability. The ~21 k "theoretical expectation" has no shown
derivation and is treated here as an unattributed target, not as a bound. The `50 %–60 %`
expectation at `:5` and the measured 71 % at `:211` coexist in one document without either being
withdrawn; this entry records that and does not adjudicate it. The observation that the file's own
§4.1 reference pseudocode contains the defect its §7 diagnoses is a reading of the text, not a
finding about any machine. BOARD is `family-claimed(unverified)`: no file in this family names a
chip (`0347`). Nothing transfers to the other book (RULES.md Art. 1), and nothing here is established for
950DT if a run happens on 950PR or the reverse.
