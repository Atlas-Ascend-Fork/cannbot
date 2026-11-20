```
ID:        0053-buffer-reuse-safety-rests-on-a-tque-fifo-order-no-document-guarantees
LABEL:     trap
LEVEL:     L4 (synchronisation)
STRATUM:   harvested — drafted from one upstream origin; nothing measured
BOARD:     family-claimed(unverified)
SOURCE:    ops/ascendc-perf-optimize/references/single-core-pipeline/techniques/nobound-02-stage-order-rescheduling.md:84 — "**buffer 复用安全性依赖 TQue 的 FIFO 分配**（`CopyIn` 取到的是上一轮释放的那块，而非计算正在读的那块）。这一点文档无保证，须用「结果与改前逐位一致」实测坐实"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  a run on a named 950 board in which a delayed-write-back kernel returns results that are
           not bit-identical to the unreordered build — the FIFO allocation assumption would then
           be false at that toolkit pin, and every kernel relying on it is unsafe rather than
           merely unverified.
```

# 0053 · Buffer-reuse safety rests on a TQue FIFO order no document guarantees

## 1 · Claim
Upstream asserts that the reordered loop of 0052 is safe only if `TQue` hands out buffers in FIFO
order — so that a `CopyIn` receives the block released last round rather than the block the
in-flight computation is still reading — and upstream asserts plainly that no document guarantees
this, so the assumption must be underwritten empirically by results that are bit-identical to the
unreordered build. Not established here; nothing was run.

## 2 · The wrong branch this removes
An agent applying the reordering of 0052 will treat the queue as an allocator: ask for a buffer,
get a buffer, write into it. With three tiles live at once — pending write-back, in-flight compute,
prefetch — the identity of the buffer returned is load-bearing, and the failure mode if it is wrong
is that a copy overwrites data a running computation is reading. That does not raise an error, does
not appear in any ratio, and does not reproduce reliably: it depends on how far the asynchronous
computation has progressed, so it can pass every test on a fast build and corrupt results on a slow
one, or vice versa.

What this entry adds to 0052 is the shape of the obligation. The technique is admissible with an
undocumented dependency *because* the dependency has a cheap, decisive test — bit-identity against
the pre-change build — and that test must be run for every kernel that adopts the pattern, not once
for the pattern. A performance claim can be transferred between operators; an
undocumented-invariant claim cannot.

## 3 · Ground / Source
`nobound-02:84`, quoted in full in SOURCE, is one of eight stop rules on the card. Its context is
the support requirements at `:61` — output queue depth 2 (`Compute` EnQue 时上一拍还挂着未 DeQue),
and a cross-tile index/metadata window wide enough for three tiles — and the two blocking mechanisms
at `:29-30`.

Nothing else in this scope discusses `TQue` allocation order. `mem-02:53` states the adjacent
requirement in event terms — 复用 buffer 前必须等原消费者完成，事件类型和 event ID 必须成对 — which
is a discipline about waiting, not about which buffer is returned. `mem-04:39` states the same for UB
reuse: the previous consumer's read must have completed, and identical `LocalTensor` type is not a
licence to alias. So the library twice states "wait for the consumer" and once states "and also
assume FIFO, which is unguaranteed" — the third is the one with no mechanism behind it.

Two further observations, recorded because a consumer must weigh them. First, `nobound-02:81`
distinguishes queue depth from physical buffer count (0019); if the two are coupled on some toolkit,
the number of physical buffers in flight changes and the FIFO question changes with it. Second, the
card's own evidence (`:65`) reports md5-checked rebuilds and three timing conventions but does not
report the bit-identity check as a readout — it states it as an obligation. So even upstream's
strongest measured card leaves this assumption asserted rather than shown.

## 4 · Procedure
Later phase, needs a card. This is a correctness experiment with an adversarial arm; timing is
recorded only to detect the schedules under which the hazard is reachable.
1. Device selection per 0010: explicit visible-devices, occupancy read before and after, board token
   from the driver readout.
2. Build three kernels from one source tree: (U) unreordered — `CopyIn(next); Compute(cur);
   CopyOut(cur)`; (D) the 0052 reordering with output queue depth 2; (D+) the same reordering with
   the computation artificially lengthened per tile (an added dependent chain) so the in-flight
   computation is still running when the next `CopyIn` is issued. Record `md5sum` of each.
3. Run each over at least sixteen shapes including the smallest that forms a pipeline
   (`T ≈ coreNum × ubFactor`) and the largest that fits, five repetitions.
4. Compare D and D+ outputs to U bit-for-bit, element by element, per shape and per repetition —
   not against a tolerance, and not against a host reference, since the question is whether the two
   builds compute the same thing.
5. Instrument the queue if the toolkit exposes it: record, per iteration, the buffer address returned
   by `AllocTensor`, and check that the sequence is the release order.

## 5 · Checker — acceptance declared before the run
Verdict variables `bitexact(D)`, `bitexact(D+)` — booleans over the whole shape set and all
repetitions — and `fifo_order` from the address trace when available. Acceptance for adopting the
pattern on this kernel: both `bitexact` values true across every shape and repetition. A single
mismatch, in a single repetition, is a failure: the hazard is schedule-dependent, so a rare
mismatch is the signal, not noise, and the checker must not average over repetitions.

Exit code is not the verdict. The comparison is over full output buffers; a checksum or a norm would
hide a corrupted tile, which is exactly the expected footprint (one tile's worth of wrong data at a
position that varies between runs). The number of elements compared is asserted equal to the output
size before any verdict is printed — a comparison that silently compared nothing would otherwise
report perfect agreement.

Red input: build D+, whose whole purpose is to make the hazard reachable. If D+ is bit-exact on
every shape, this experiment has not demonstrated that it could ever have detected the problem, and
the correct report is `hazard_not_provoked` — not "FIFO confirmed". A checker pinned to "D must come
up clean" is the known blind species and would have passed here.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured. It does not establish that `TQue` allocation is FIFO, nor that it is not — it
records that a shipped technique depends on it and that upstream found no documentation either way.
A bit-exact result on one kernel establishes nothing for another kernel, and nothing for another
toolkit pin: allocation order is a property of the queue implementation, so the obligation returns
whenever the toolkit changes. No board is implicated; the reordering card's own measurement is
950PR (0052) but this assumption is about software, not silicon. Nothing here covers queues bound to
L1/L0, or `TBuf`-based allocation, which is a different path.
