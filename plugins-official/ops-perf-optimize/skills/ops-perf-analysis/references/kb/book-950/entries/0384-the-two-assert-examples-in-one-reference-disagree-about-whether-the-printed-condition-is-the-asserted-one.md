```
ID:        0384-the-two-assert-examples-in-one-reference-disagree-about-whether-the-printed-condition-is-the-asserted-one
LABEL:     trap
LEVEL:     L7 (verification)
STRATUM:   harvested — one upstream origin (ops/ascendc-simt-api-reference), whose two worked examples
           for one interface print the failed condition two different ways. Nothing was compiled and
           no assertion was fired.
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-simt-api-reference/references/debug-api.md:52-61 — the first example: "int
           assertFlag = 10; / / assert(assertFlag == 10);" followed by "打印信息示例如下：" and
           "[ASSERT] /home/.../add_custom.cpp:44: : Assertion \`assertFlag != 10' failed." — the
           asserted condition is `== 10`; the printed condition is `!= 10`; and the asserted condition
           is TRUE for the stated value, so a true assertion is shown producing a failure message.
SOURCE:    same file:111-123 — the second example: "__simt_vf__ __launch_bounds__(1024) inline void
           AddCustom(__gm__ bool* dst, __gm__ float* x) / { / int idx = threadIdx.x + blockIdx.x *
           blockDim.x; / assert(!isnan(x[idx])); / dst[idx] = x[idx]; / }" followed by "程序运行时会
           触发assert，打印效果如下：" and "[ASSERT] /home/.../add_custom.cpp:44: : Assertion
           \`!isnan(x[idx])' failed." — here the printed condition IS the asserted one, unnegated.
SOURCE:    same file:47 — "在算子Kernel侧的SIMT VF实现代码中，如果assert的内部条件判断不为真，则会输出
           assert条件，并将输入的信息格式化打印在屏幕上，同时算子运行失败。" — the prose says the
           **assert condition** is output when the condition is not true.
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  one fired assertion on a 950 board whose printed text is read directly — it says whether the
           runtime prints the asserted condition or its negation, and one observation settles both
           examples at once.
```

# 0384 · The two `assert` examples in one reference disagree about whether the printed condition is the asserted one

## 1 · Claim
Upstream asserts that a SIMT `assert` whose condition evaluates false outputs **the assert condition**,
formats the supplied information to the screen, and fails the operator run. Upstream then gives two worked
examples of the printed output for the same interface, and they disagree. In the first, the asserted
condition is `assertFlag == 10` with `assertFlag` set to 10, and the printed line reads
``Assertion `assertFlag != 10' failed.`` — the negation. In the second, the asserted condition is
`!isnan(x[idx])` and the printed line reads ``Assertion `!isnan(x[idx])' failed.`` — the condition itself.
The first example additionally asserts a condition that is **true** for the value it just assigned, and
presents that as producing a failure message. Not established here: nothing was compiled and no assertion
was fired.

## 2 · The wrong branch this removes
An assertion message is read exactly once, under pressure, and acted on immediately. Its whole value is
that it names the condition that failed. If the two readings are both in circulation, the message is
ambiguous at the moment it matters most.

**Concretely.** An agent finds ``Assertion `n != 0' failed.`` in a log. Under the second example's
reading, `n != 0` was asserted and is false, so `n == 0` — a null length, an empty tile, a division guard
that fired. Under the first example's reading, `n == 0` was asserted and failed, so `n != 0` — an
unexpected non-zero, a leftover count, a tail that should have been empty. **The two readings point at
opposite states of the same variable**, and the agent will pick one and start debugging in that direction.
There is no second signal to correct it: the log line is all there is.

**The first example is doubly broken and the two defects are separable.** Its condition is `assertFlag ==
10` immediately after `int assertFlag = 10;`, so the assertion holds and should print nothing at all. That
is independent of the negation question: even under the negating reading, a true assertion does not fire.
So the example demonstrates a failure that its own code cannot produce, which means an agent cannot use it
to calibrate anything — not the trigger, not the message. The most likely explanation is that the code
block and the output block were edited at different times (an original `assert(assertFlag != 10)` would
produce exactly the shown line under the non-negating reading), and that explanation *supports* the second
example's reading — but it is reconstruction, not evidence, and §7 marks it so.

**The prose does not adjudicate.** `:47` says 会输出 assert 条件 — outputs the assert condition — which is
the second example's behaviour. So two of the three statements in the file agree and the third is the one
with the arresting formatting (a code block showing literal output). Under Art. 7 a majority is not a
resolution: two documents agreeing is one origin agreeing with itself, and the file's own worked output is
the kind of evidence a reader will trust over prose.

**And the file numbers are inconsistent with the code.** Both examples print `add_custom.cpp:44`, but the
first example's snippet is three lines and the second's is six; the same line number appearing for two
different sources is a further sign the output blocks are transcribed rather than captured. That does not
decide the negation question and it does lower the evidential weight of both output blocks equally, which
is why §4's Arm A has to fire a real assertion rather than reason about the file further.

## 3 · Ground / Source
The prose, `debug-api.md:47`:

> 本接口在SIMT VF调试场景下提供assert断言功能。在算子Kernel侧的SIMT VF实现代码中，如果assert的内部条件
> 判断不为真，则会输出assert条件，并将输入的信息格式化打印在屏幕上，同时算子运行失败。

Three commitments: the condition is output; the supplied information is formatted to screen; and the
operator run fails. The third is a behavioural claim carried by 0385 (assert fails the run) and is not
disputed by either example.

The first example, `:51-61`:

> ```
> int assertFlag = 10;
>
> assert(assertFlag == 10);
> ```
>
> 打印信息示例如下：
>
> ```
> [ASSERT] /home/.../add_custom.cpp:44: : Assertion `assertFlag != 10' failed.
> ```

The second, `:110-123`:

> ```
> __simt_vf__ __launch_bounds__(1024) inline void AddCustom(__gm__ bool* dst, __gm__ float* x)
> {
>     int idx = threadIdx.x + blockIdx.x * blockDim.x;
>     assert(!isnan(x[idx]));
>     dst[idx] = x[idx];
> }
> ```
>
> 程序运行时会触发assert，打印效果如下：
>
> ```
> [ASSERT] /home/.../add_custom.cpp:44: : Assertion `!isnan(x[idx])' failed.
> ```

Same file, same interface, same message format `[ASSERT] <file>:<line>: : Assertion \`<expr>' failed.`,
same line number 44 — and the expression inside the backtick-quote is the negation of the asserted
condition in one case and the asserted condition itself in the other.

Note the message format matches the C standard library's `assert` output almost exactly, which prints the
**asserted** expression. Upstream's own note at `:196` says "kernel开发不要包含系统的assert.h，会导致宏
定义冲突" (0387) — so the SIMT `assert` is a distinct macro deliberately shadowing the system one, and its
message format is modelled on the system one. That is circumstantial support for the non-negating reading
and it is inference from a resemblance, not a fact about this implementation.

Recorded as `C-950rem-006`. Both examples are one file in `upstream/skills-dev-main` — one origin (RULES.md
Art. 3), and the disagreement is *within* one document.

The prototype is given at `:68` as `assert(expr)` — a macro form, not the
`void assert(bool condition)` function signature the index table at `:14` shows; that mismatch is 0385's.

## 4 · Procedure
Runnable later on `950PR`. One fired assertion answers the whole question.

Arm A — fire one and read it. Build a SIMT kernel containing `assert(v == 0);` with `v` set to 1, run it,
and record the printed line **verbatim**. If the backtick-quoted expression is `v == 0`, the second example
and the prose are right; if it is `v != 0`, the first example is. One observation, no ambiguity. Repeat
with a second distinctive condition (`assert(n > 7);` with `n` = 3) to confirm the transformation rather
than reading one line.

Arm B — the true-assertion case. Build the first example verbatim — `int assertFlag = 10;
assert(assertFlag == 10);` — and record whether anything is printed and whether the run fails. Predicted:
nothing, and the run succeeds. If it prints, the macro's trigger polarity is inverted and that is a far
larger finding than a documentation slip.

Arm C — the message format, in full. From Arm A, record every field: the `[ASSERT]` prefix, the path, the
line number, the doubled colon-space (`: :` in both examples, which looks like an empty field between two
separators and may be where the "supplied information" from `:47` goes), and the trailing text. The prose
promises 将输入的信息格式化打印 — formatted printing of supplied information — and neither example passes
any information beyond the condition, so what that field carries is unestablished and Arm C is where it
would appear.

Arm D — per-thread behaviour. Fire an assertion whose condition is false for exactly one thread in a
1024-thread launch, and record how many lines are printed and whether the thread is identified. An
assertion that prints once per failing thread and does not say which thread is a different debugging
instrument from one that prints once with an index, and no source in scope says which this is. This also
interacts with 0383's FIFO: 1024 failing threads is 1024 lines.

Arm E — the negation question at the source. Locate the `assert` macro's definition in
`asc/include/utils/debug/asc_assert.h` and read whether it stringises the condition or its negation. This
is a file read, needs no device, and may settle Arms A and B before they are run — and it is deliberately
placed last so it is not treated as a substitute for firing one.

Device selection, for Arms A through D: the operator names the device index, the harness prints it back
with `compiler/version.info` and the resolved SoC string, occupancy is checked before the run (shared
machine, ≤4 dies), and all builds run on one named die in one session. An assertion fails the operator
run by design, so a non-zero exit is expected and the harness must not treat it as a harness failure.

## 5 · Checker — acceptance declared before the run
`printed_expression` (Arm A) — the verbatim backtick-quoted text, for each of the two conditions. The
verdict is three-valued: matches the asserted condition, matches its negation, or matches neither. Recorded
as text rather than as a boolean, because "neither" is a live outcome (a canonicalised or re-associated
expression) and no boolean could carry it.

`true_assert_is_silent` (Arm B) — true iff the always-true assertion prints nothing and the run succeeds.
Pass condition **true**. A false result means the trigger polarity is inverted, which would be a defect in
the implementation rather than in the documentation.

`message_fields` (Arm C) — the parsed message, field by field, including whatever occupies the empty slot
between the two colons. Reported.

`lines_per_failing_thread` (Arm D) — the count of printed lines for a one-failing-thread launch, and
whether any thread identifier appears. Reported; never divided by the thread count into a "rate", because
the interesting outcomes are 1 and 1024 and an average is neither.

`macro_stringises_negation` (Arm E) — true iff the macro definition stringises the negated condition.
Reported alongside `printed_expression` and **not** substituted for it: a macro read is not a fired
assertion, and this book's whole discipline is that a declaration is not a run.

The positive fixture, declared before the run: Arm A must include a **control** assertion that is true
(`assert(1 == 1);`) in the same build, which must print nothing. If it prints, the macro fires
unconditionally and every expression captured in the arm is meaningless. And the capture path must be shown
able to carry an `[ASSERT]` line at all before any conclusion is drawn from an absent one — Arm B's
predicted silence is indistinguishable from a lost stdout, so Arm B is only interpretable after Arm A has
produced a line through the same capture path. Without both, the checker reads only "nothing was printed",
which is the known blind species and is exactly the shape this arm risks.

Process exit codes are not the verdict: a fired assertion fails the run by design, so a non-zero exit is
the expected outcome in Arm A and the printed text is the readout.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement. No kernel was built, no assertion
fired, no message captured, no macro definition read, no die contacted. The two quoted examples are
re-verified file reads of the upstream tree performed during this harvest.

## 7 · Scope limits — what this entry does NOT establish
Nothing was compiled or run. The entry does not establish which reading is correct, and by Art. 7 it must
not: both examples are one origin, and the fact that the prose and the second example agree against the
first is two parts of one document agreeing, not corroboration. One fired assertion settles it and none has
been fired.

**The reconstruction in §2 is not evidence.** That the first example's output block would be correct for an
original `assert(assertFlag != 10)` — making it an editing slip and the non-negating reading right — is a
plausible account of how the file came to say what it says. It is not an observation, and the entry does
not rest on it.

**The resemblance to the C standard library's message is not evidence either.** The format matches, and
0387 records that the SIMT macro deliberately shadows the system `assert.h`; a shadowing macro may or may
not preserve the original's stringisation behaviour, and nothing read here says which.

It does not establish what the empty field between the two colons carries. The prose promises formatted
printing of supplied information and both examples pass none, so the mechanism for supplying it is
undocumented and unexercised in this material.

It does not establish per-thread behaviour, which matters directly for usability at SIMT thread counts and
interacts with the print FIFO (0383). Nothing in scope says whether a failing assertion prints once, once
per thread, or once per warp.

It says nothing about the AI CPU `assert` sibling documented in the same file under the same index row,
whose own example at `:36-42` prints yet a third message format
(``[ASSERT]` assertFlag == 12 ' at /home/.../test.cpp:36``) — a different prefix, different quoting,
different ordering. That is 0385's subject.

BOARD is `family-claimed(unverified)`: upstream's 产品支持情况 table names "Ascend 950PR/Ascend 950DT",
which is upstream reproducing a vendor support matrix rather than a measurement, and no board was
contacted.
