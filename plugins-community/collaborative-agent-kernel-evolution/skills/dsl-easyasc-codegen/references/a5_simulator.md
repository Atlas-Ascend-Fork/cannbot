# A5 hardware-simulator profiling (cannsim / msprof op simulator)

How to **cycle-profile a compiled a5 AscendC kernel** on an A5 simulator host. This is distinct
from the easyasc software simulator:

| | easyasc `OpExec(simulator=True)` | CANN A5 hardware simulator |
|---|---|---|
| What | software model, runs the DSL kernel | cycle-accurate model of the A5 AI Core |
| Used by | `run_smoke.py` (correctness smoke) | this doc (performance profiling) |
| Needs | just the easyasc Python env | an A5 simulator host + compiled AscendC |

Use this once a kernel is correct and you need real cycle/instruction data (it backs the
profiler step in `micro_perf_rules.md` §3). Requires the `gen_only` AscendC output (the
`<op>_raw_aclnn_test/` test binary) built on an A5-sim host.

> The skill's default a5 path stops at the OpExec smoke (`next_step=report-only`). This
> hardware-sim profiling is an **optional deeper step** available only on a host that has the
> CANN A5 simulator installed.

---

## 1. Host requirement

- A CANN version whose **A5 simulator libraries are actually populated**. Some older ARM beta
  packages ship as empty shells (the `camodel` dir is missing) — verify before trusting a run.
- Sanity-check on a fresh host:
  ```bash
  which cannsim          # should resolve under $ASCEND_HOME_PATH/bin
  which msprof
  ls $ASCEND_HOME_PATH/<arch>-linux/simulator/<A5_variant>/lib/*.so | wc -l   # expect a non-trivial count
  ```

## 2. Clean-env discipline (the #1 source of failures)

A stale `ASCEND_HOME_PATH` injected by an outer `~/.bashrc` / `/etc/profile.d` repeatedly pulls
the simulator back to a wrong (often empty) CANN version. In **every new shell**:

```bash
# 1. clear anything an outer profile may have injected
unset ASCEND_HOME_PATH ASCEND_TOOLKIT_HOME ASCEND_OPP_PATH ASCEND_AICPU_PATH \
      ASCEND_CUSTOM_OPP_PATH LD_LIBRARY_PATH PYTHONPATH \
      BASE_LIBS_PATH ASCEND_BASE_LIBS_PATH ASCEND_INSTALL_PATH

# 2. rebuild PATH (include the right Python)
export PATH=<python_bin>:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# 3. source the A5 CANN set_env
source <CANN_A5_ROOT>/set_env.sh

# 4. belt-and-suspenders: force re-export (set_env occasionally reverts to an older active install)
export ASCEND_HOME_PATH=<CANN_A5_ROOT>
export ASCEND_TOOLKIT_HOME=<CANN_A5_ROOT>
```

The symptom of getting this wrong: cannsim reports a `CAModel path does not exist ...camodel`
pointing at the *old* version.

## 3. cannsim — recommended for iteration (fast)

```bash
cd <op>_raw_aclnn_test
# cannsim finds its libs internally — no LD_LIBRARY_PATH needed
cannsim record ./test_aclnnop -s Ascend950 --gen-report
```

- **Output**: `cannsim_<ts>_test_aclnnop/` with `report/trace_core0.json` (Chrome-trace format,
  drag into `chrome://tracing`), plus per-core instruction dumps.
- **End-to-end wall_cycles**: parse `report/trace_core0.json` and take
  `max(ts + dur) − min(ts)` across all `(pid, tid)`.
- Most of the wall time is framework startup + report generation, not the hardware sim itself —
  don't mistake launch overhead for kernel cost.

## 4. msprof op simulator — for instruction-level analysis (slow)

```bash
cd <op>_raw_aclnn_test
# MUST point LD_LIBRARY_PATH at the CONCRETE variant lib dir
export LD_LIBRARY_PATH=$ASCEND_HOME_PATH/<arch>-linux/simulator/<A5_variant>/lib:$LD_LIBRARY_PATH

msprof op simulator \
    --soc-version=<A5_variant> \      # concrete variant, NOT bare "Ascend950"
    --kernel-name=<KernelName> \
    --output=$PWD/msprof_out \
    ./test_aclnnop
```

- **Output**: per-lane `core{N}.{cubecore,veccore}/` dirs with `*_instr_exe.csv` (per-instruction
  cycles + us) and `*_code_exe.csv` (source-line ↔ cycle, when debug info is present), plus a
  `visualize_data.bin` for MindStudio Insight.
- Substantially slower and far larger output than cannsim; reserve it for instruction-level stall
  analysis and source-line attribution.

## 5. Which simulator to use

| Need | Use |
|---|---|
| "how many cycles did the kernel take", A/B optimization iteration | **cannsim** (fast, Chrome trace) |
| per-instruction stall / source-line attribution | **msprof op simulator** + MindStudio Insight |

Iterate with cannsim; drop to msprof only when you need instruction-level detail.

## 5b. Software smoke vs cannsim — which is authoritative for a5

There are **two different "simulators"** and they are NOT equivalent in fidelity:

| | easyasc `OpExec(simulator=True)` (software smoke) | cannsim / `msprof op simulator` (this doc) |
|---|---|---|
| What | a Python model of the DSL semantics | cycle-accurate model of the A5 AI Core running the **generated AscendC** |
| Speed | seconds (fast pre-check) | minutes (build + run) |
| Fidelity | **advisory** — has known false negatives | **authoritative** for a5 correctness & perf |

**Known software-smoke false negative — `compare → select`**: a reg kernel that builds a mask with
`compare(...)` and consumes it with `select(...)` (bitonic sort, set-intersection, compaction, …)
**fails the software smoke even when it is correct**. Cause: in `simulator_v2`, `compare` writes its
result mask to the register store while `select` reads from `ctx.masks` (which holds the all-true
declaration default) — so `select` sees an all-true mask. The **generated AscendC `MicroAPI::Compare`/
`Select` are correct**; only the software model is wrong. (Full write-up in `error_recipes.md`.)

**Rule of thumb for a5**:
- Treat the software smoke as a **fast advisory pre-check**, not a verdict.
- A smoke **PASS** doesn't guarantee real correctness (UInt16/float8/cycle gaps — see report).
- A smoke **FAIL on a `compare→select` (or other mask-driven) reg kernel** is **suspect** — validate
  on cannsim before concluding the kernel is wrong. **cannsim is the ground truth for a5.**

## 6. Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `CAModel path does not exist ...<old_version>/camodel` | outer env pulled `ASCEND_HOME_PATH` back to a wrong CANN | use the §2 clean-env block in every new shell; force re-export after `source` |
| `--soc-version=Ascend950 is invalid` | bare SoC name not accepted | use a concrete variant (e.g. `Ascend950PR_<n>`); list them under `$ASCEND_HOME_PATH/<arch>-linux/simulator/` |
| msprof `dlopen` can't find `libcamodel.so` | msprof doesn't auto-find sim libs | manually export `LD_LIBRARY_PATH` to the concrete variant `lib/` dir (§4) |
| `build.sh` fails "Makefile: No such file" | cmake generate failed with polluted env | delete `build_out/`, `unset BASE_LIBS_PATH`, re-source the A5 CANN, rebuild |
| an unused `@vf` still adds wall cycles | the parser allocates regs/slots for every `@vf`, even uncalled ones | delete experimental/unused `@vf` definitions from the file — don't leave them in |
| moving an unconditional `@vf` into a `Var`-conditional branch breaks precision | parser mishandles unconditional vf nested under a runtime-`Var` condition inside `auto_sync` | keep a linear structure; don't nest an unconditional vf under a `Var` branch |
| `cannprof ... GLIBC_2.38 not found` warning | benign tail warning of `--gen-report` | harmless — it falls back and still emits `trace_core0.json` |
| startup banner "no l3 cache / no media unit / no dvpp" | A5 sim model doesn't model non-AI-Core units | harmless for AI-Core kernels |

---

*Placeholders: `<CANN_A5_ROOT>` = the A5 CANN install root; `<A5_variant>` = a concrete simulator
variant name; `<arch>` = host arch (e.g. `aarch64`); `<op>` = the operator name; `<KernelName>` =
the kernel entry symbol. Substitute for your host — do not hard-code one machine's paths.*
