# Environment checklist

What must be set before `dsl-easyasc-codegen` scripts can do their job.

## Always

- **Python environment** with:
  - `torch` (any version compatible with `torchplugin.py`)
  - `numpy` (CANN's `opbuild` invokes `python3` and needs numpy on its PATH)
- **`EASYASC_DSL_HOME`** must point at your easyasc checkout — the directory containing `easyasc/`.
  The library is not distributed with this plugin, and `init_workspace.sh` refuses to guess a path
  (see `docs/EXTERNAL_DEPENDENCIES.md`):
  ```
  export EASYASC_DSL_HOME=/path/to/ops-easyasc-dsl
  ```
- **`PYTHONPATH`** must contain that directory so `import easyasc.a2` / `import easyasc.a5` works.
  `init_workspace.sh` writes it into `<workspace>/env.sh` automatically from `EASYASC_DSL_HOME`.
  Source `env.sh` before running the python scripts manually.

## A2 path only (codegen + build + run)

- **`ASCEND_HOME_PATH`** — points at CANN install root (the dir containing `bin/setenv.bash`). `b.sh` reads this; if missing, build fails with "ASCEND_HOME_PATH is not set".
- **Host device must be 910B** — `check_device.sh --target a2` enforces this. Other devices hard-fail.
- **`ASCEND_CUSTOM_OPP_PATH`** — only set if you have additional custom OPP roots to chain. `init_workspace.sh` exports an empty value to keep `set -u` and CANN's `set_env.bash` happy.
- **`EASYASC_PYTHON_BIN`** — only needed when CANN's bundled `python3` lacks numpy. If set, prepended to `PATH` inside `b.sh`/`r.sh`. Skip if your CANN python already has numpy.

## A5 path

- A5 is simulator-only on a 910B host.
- `ASCEND_HOME_PATH` not strictly needed (no AscendC build), but `check_device.sh --target a5` will warn if missing.
- Host being non-a5 (e.g. 910B) produces a warning, not an error.
- The default a5 flow ends at the `OpExec(simulator=True)` smoke (`run_smoke.py`). To **cycle-profile**
  a compiled a5 kernel you need an A5 simulator host (CANN with populated A5 sim libs) and the
  cannsim / `msprof op simulator` flow — see `a5_simulator.md` (incl. the clean-env discipline).

## Self-check sequence

```bash
bash skills/dsl-easyasc-codegen/scripts/check_device.sh --target a2
# expected: passed=true, host_family=a2

python -c "import easyasc.a2; print('a2 ok')"
python -c "import easyasc.a5; print('a5 ok')"
python -c "import torch; import numpy; print('torch/numpy ok')"
ls "$ASCEND_HOME_PATH/bin/setenv.bash"
```

If `import easyasc.*` fails: `PYTHONPATH` is wrong, or `cannbot-skills` repo hasn't run `bash agent/scripts/init.sh` yet.
