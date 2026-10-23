# Shared-Device Benchmark Noise Control

On a shared device, end-to-end benchmark numbers drift a few percent between
runs even when nothing changes (and far more under host load), so promotion
decisions need same-session interleaved A/B against a measured noise floor —
deltas inside the noise band are inconclusive, and under heavy host load only
direct profiler op time is trustworthy.

## When to use

- Comparing a candidate against the current best for promotion.
- A round shows "regressions" on cases whose code path was not touched.
- A sub-5% improvement claim is about to be promoted.

## When not to rely on end-to-end numbers

- Comparing against a perf file captured in an earlier session or a different
  device state.
- Promoting on a single full-run comparison or a single task-duration sample.
- Reading wall-clock or per-call event timing while host load far exceeds core
  count — launch jitter swamps them.

## Signals

- Untouched cases move together (all up or all down by a few percent) between
  reference and candidate runs.
- Two identical-source runs disagree in sign on the same case.
- A full-run geomean captured during a load spike reads multiples away from the
  same binary's calm-window number.

## Procedure

1. Measure the noise floor first: run the reference twice (identical source)
   and compare — if the floor covers the candidate delta, the round is
   inconclusive.
2. Run interleaved pairs on the same device in one session (ref -> cand ->
   ref -> cand); require the direction to be consistent across pairs before
   promoting.
3. When the tooling only accepts operators inside the active round directory,
   build the same-session parent reference by copying the parent source into a
   subdirectory of the active round as a second operator, comparing the two
   perf files, then removing the temporary copy.
4. Under heavy host load, switch to direct profiler op time on both builds
   (interleaved, per case); device-side kernel time is immune to launch
   jitter.
5. Standalone probe kernels: correctness first, then timing through an
   in-kernel repeat loop while the host calls `torch.npu.synchronize()`
   periodically — long unsynchronized back-to-back launch streaks can fault
   (device error 507035) on a shared device. Sweep the sync cadence rather
   than assuming a fixed launch budget.

## Checks before promoting

- Every promoted round cites pairs whose delta exceeds the measured noise
  floor in a consistent direction.
- Untouched-path control cases confirm no collateral regression.
