# msprof op InstrTimeline for Triton kernels

This note records the instruction-level pipeline timeline method for a Triton
kernel on an A5-class target. All items are measured behaviors, not assumptions.

## 1. Interpreter compatibility under msprof injection

msprof injects its collection libraries into the child process
(`LD_PRELOAD`-style).  This changes symbol resolution and can break Python
environments that work fine normally: an environment can fail at
`import triton` with `GLIBC_2.36 not found (required by
.../triton/_C/libtriton.so)` only under msprof, while another environment
on the same board imports and runs cleanly.

- Verify the exact interpreter inside the msprof-wrapped run, not just
  interactively.  Symptom: `ImportError` at import time, `Child process
  exited with return value 1`, then `Get profiling data failed`.
- Keep a known-good interpreter for profiling and point the wrapper script
  at it explicitly.

## 2. Application wrapper: no per-app argument passing

`msprof op --application=<file>` execs a single file and does not accept an
application-argument option (an `--application-args` attempt is rejected as
`unexpected argument`).  Pass selection parameters to the app through the
environment variables:

```bash
#!/bin/bash
exec /path/to/profiling-python /abs/path/prof_app.py      # reads $PROF_TARGET
```

```bash
PROF_TARGET=<variant> msprof op --application=prof_app.sh --output=... ...
```

The app should import the operator module from an absolute path and assert
on `module.__file__` before launching (a scratch cwd can silently import a
stale module).  Keep the process alive until the kernels complete
(`torch.npu.synchronize()` after each launch).

## 3. Kernel names carry compiler module suffixes

Triton-Ascend lowers a `@triton.jit` kernel that mixes vector and cube code
into one mixed device kernel named `<base>_mix_aic`.  That single kernel's
trace contains both pipe groups at once: `tid=VECTOR` events on
`pid=coreN.veccoreM` streams and `tid=CUBE` events on `pid=coreN.cubecore`
streams.  No separate `_mix_aiv` device kernel was observed on this
toolchain.  Consequences:

- `--kernel-name` must be a base-name substring (`--kernel-name=_mysplit`),
  not the exact source-level function name; an exact-suffix guess returns
  `No profiling data matched --kernel-name`.
- One matched kernel yields the VECTOR and CUBE streams together; do not
  expect one device kernel per pipe.
- Host-side pre/post kernels in the same call (elementwise casts, fill
  kernels) are skipped with an INFO line naming them:
  `Kernel <name> skipped: not selected via --kernel-name.`  These skip
  lines are the cheapest way to discover the real device kernel names
  before committing to a filter.
- `TRITON_ALWAYS_COMPILE=1` and the session's `TRITON_CACHE_DIR` must be
  exported before launching msprof so the wrapped app compiles/reuses the
  same kernels as the benchmark runs.

## 4. Combined vector+cube capture

For a mixed kernel, capture both pipes in one run by joining them with `|`.
The shell argument must be quoted, or the shell interprets the bar as a
pipe:

```bash
msprof op --application=prof_app.sh --output=... --aic-metrics=InstrTimeline \
  --instr-timeline-pipe='vector|cube' --kernel-name=_mysplit \
  --launch-count=1 --warm-up=0
```

- One capture produces the VECTOR and CUBE streams together in a single
  `trace.json`; separate per-pipe runs are not needed.
- The union is lossless: each tid group's per-class counts match the
  corresponding single-pipe capture up to collection jitter, and the task
  duration is unchanged.
- Pure vector kernels can keep `--instr-timeline-pipe=vector`.  Analyze a
  combined trace by grouping on `tid` first (section 5).

## 5. Event names differ per pipe

Filter by `ph == "X"`, group events by `tid` (`VECTOR` / `CUBE`) first,
then aggregate by `name`.  A parser keyed on a single name will report "no
events" for the other pipe.  Measured vocabulary on A5-class targets:

- Vector pipe: instruction issue (`VF`, `VF_SIMT`, both with `pc_addr`)
  plus sync/data-movement classes `SET_FLAGI_V`, `SET_INTRA_BLOCKI_V`,
  `WAIT_INTRA_BLOCKI_V`, `MOV_UB_TO_UB`.
- Cube pipe: multiply-accumulate (`MMAD`) plus flag synchronization
  (`SET_FLAG`, `SET_FLAGI`, `WAIT_FLAG`, `WAIT_FLAGI`).  The MMAD duration
  fraction of the wall is the cube's useful-occupancy signal; a WAIT-dominated
  mix means the cube is starved by the vector chain rather than short of work.

This cube view is exactly what decides "feed the cube more work" vs "the
vector chain is the floor", and it is available for Triton kernels even
though the companion document's PC-mapping section is not.

## 6. Durations overlap: do not report busy% or raw gaps

Per-instruction `dur` values overlap (an instruction's recorded duration
spans its pipeline latency, and events on one stream interleave), so
`sum(dur) / wall` can exceed 100% several-fold and the gap formula
`next.ts - (ts + dur)` can go negative.  Robust views that survived
measurement:

- Wall span and event count per core.
- Issue-interval distribution `next.ts - ts` between consecutive issue-class
  events (`VF`, `VF_SIMT`, `MMAD`) on one stream (p10 / p50 / p90) - intervals
  near the per-op floor with a long-tail p90 mean the stream is bound by
  long-duration ops, not idle gaps.
- Per-event-class duration share (acknowledging overlap) - e.g. MMAD vs
  WAIT_FLAG on the cube pipe.
- Distinct `pc_addr` count and per-PC hit counts: a Triton tile loop shows
  a tiny distinct-PC set (the loop body) with near-uniform hit counts, and
  the counts track the loop iteration counts.

The bundled `scripts/instr_timeline_summary.py` computes the per-stream
spans, per-class duration shares, `VF`/`VF_SIMT`/`MMAD` issue-interval
percentiles, and the distinct-`pc_addr` count; it does not compute per-PC
hit counts or bubbles.

## 7. Core sampling is partial

Dynamic instrumentation captured the cube-core streams together with only a
subset of the vector-core streams on kernels with many programs, consistent
with the companion document's many-sub-block data-loss warning.  Every
captured stream's span covers the full kernel wall, so treat any single
stream as a representative sample, and prefer metrics that survive sampling
(intervals, class mix) over whole-kernel totals.

## 8. PC->source mapping is unavailable on the Triton path

The dumped `aicore_binary.o` for a Triton-compiled kernel carries no DWARF
line table (`llvm-dwarfdump --debug-line` yields no address rows) and the
ISA is private (`llvm-objdump -d` prints `<not available>` per
instruction).  The companion document's `-g` build step is an AscendC CMake
workflow and does not apply.  Practical substitutes:

- Event-class attribution (above) for "which machinery dominates".
- msprof logging `Failed to parse pc to code` during collection is this
  same limitation surfacing in the log; expected on the Triton path, do not
  chase it.
- Cross-referencing distinct-PC counts with the kernel's source-level loop
  body size to confirm the capture covers the hot loop.
- When the question is a compile-time wall rather than a timeline, use the
  plan-stage failure dumps the Triton toolchain already prints
  (`--mlir-print-ir-after-failure` output on stderr) - they carry the exact
  rejection reason (for example an explicit unified-buffer bit demand).

## 9. Run hygiene

- Each capture takes on the order of minutes; wrap msprof in a hard
  timeout and run it in the background with a log file - a stalled capture
  is distinguishable from a slow one only by the log.
- `--launch-count=1 --warm-up=0` with `--kernel-name` gives one clean
  capture of the wanted kernel even when the operator call launches several
  kernels around it.
- Artifacts land under the output OPPROF_* directory: `trace.json`,
  `OpBasicInfo.csv` (kernel name, duration, block dims), and `dump/`
  (`pc_start_addr.txt`, `aicore_binary.o`, `DeviceProf*.bin`).
