<!-- EXPECT: RULES.md Art. 1 -->
```
ID:        0004-crossbook-board-token
LABEL:     knowledge
LEVEL:     L9 (performance)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     950PR
SOURCE:    ops/example-skill/SKILL.md:10-14 — "double buffering hides copy latency"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a paired run (buffered vs unbuffered, same shape, same die) shows no wall-clock
           difference beyond run variance.
```

# 0001 · A good harvested claim (fixture)

## 1 · Claim
Upstream asserts that double buffering hides copy latency behind compute. Not established here.

## 2 · The wrong branch this removes
An agent that skips buffering on the assumption that copies are cheap.

## 3 · Ground / Source
Full quote and context of the upstream passage would sit here.

## 4 · Procedure
The proposed paired-run procedure, runnable later on a named 910 board, would sit here.

## 5 · Checker — acceptance declared before the run
Verdict variable `dt_ratio`; pass iff ratio exceeds declared threshold; exit code is not the verdict.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
No board touched; no shape probed; the upstream sentence itself may be false.
