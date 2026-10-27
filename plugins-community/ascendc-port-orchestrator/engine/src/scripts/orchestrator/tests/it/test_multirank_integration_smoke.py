# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""multirank integration smoke — true end-to-end subprocess through the CLI entry.

Covers (host-only, no NPU):
- `python -m orchestrator --multirank --port-a3-ops <dir> --npubench-task <task.py>
  --plan` exits 0 and seeds the op workspace (.opgen_state.json opgen_mode +
  op_classification.json tags=multirank_fusion)
- nonexistent task path is rejected (rc 2) before the workspace is seeded

The subprocess gets ASCENDC_ENV_PATH pointing at a tmp copy of
workspace/.ascendc_env.template (the engine's env preflight is fail-fast),
and the seeded op dir (unique per test run) is removed afterwards.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
# it/x.py → parents: [it, tests, orchestrator, scripts, src, engine]
_ENGINE_DIR = _HERE.parents[5]  # engine/
_SCRIPTS_DIR = _HERE.parents[3]  # engine/src/scripts/
_WORKSPACE_ROOT = _ENGINE_DIR / "workspace"

_OP = "it_mc2_smoke"

# Minimal KernelBench-style task + sidecar pair. Deliberately distinct from
# plugins/multirank/tests/test_task_to_spec.py's fixture (add/beta, different
# shapes and case) so the two smoke inputs do not count as duplicated lines.
_TASK_SRC = """\
import torch


class Model(torch.nn.Module):
    def forward(self, x, beta=0.0):
        return torch.add(x, beta)


def get_input_groups(rank=0, world_size=1):
    base = torch.zeros(6, dtype=torch.float32).view(3, 2)
    return [base + rank]


def get_init_inputs(rank=0, world_size=1):
    return []
"""

_SIDECAR = [
    {
        "name": "it_smoke_case",
        "inputs": [
            {"name": "x", "type": "tensor", "dtype": "float32", "shape": [3, 2]},
            {"name": "beta", "type": "attr", "value": 0.5},
        ],
        "world_size": 2,
    },
]


@pytest.fixture()
def smoke_env(tmp_path):
    """Env dict with ASCENDC_ENV_PATH pointing at a tmp copy of the template.

    A5_EXEC is overridden to local: the template's remote-container placeholder
    fails the tier preflight (A5_HOST/A5_CONTAINER/staging mapping required),
    and a --plan run never touches the target anyway.
    """
    env_file = tmp_path / ".ascendc_env"
    template = _WORKSPACE_ROOT / ".ascendc_env.template"
    lines = template.read_text(encoding="utf-8").splitlines()
    lines = [
        "A5_EXEC=local" if line.startswith("A5_EXEC=") else line for line in lines
    ]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {**os.environ, "ASCENDC_ENV_PATH": str(env_file)}


def _run_cli(args, env):
    return subprocess.run(
        [sys.executable, "-m", "orchestrator", *args],
        cwd=str(_SCRIPTS_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _cleanup_op_workspace(op: str) -> None:
    op_dir = _WORKSPACE_ROOT / op
    if op_dir.exists():
        shutil.rmtree(op_dir)


def _task_pair(tmp_path: Path) -> Path:
    """Task .py + same-stem sidecar in their own clean dir (closure freeze)."""
    root = tmp_path / "task-root"
    root.mkdir()
    (root / f"{_OP}.py").write_text(_TASK_SRC, encoding="utf-8")
    (root / f"{_OP}.jsonl").write_text(
        "\n".join(json.dumps(c) for c in _SIDECAR), encoding="utf-8"
    )
    return root / f"{_OP}.py"


def _ops_nn_dir(tmp_path: Path) -> Path:
    """A minimal arch22 ops-nn source dir (op_host + op_kernel/arch22 .cpp)."""
    op_dir = tmp_path / "ops-nn" / _OP
    (op_dir / "op_host").mkdir(parents=True, exist_ok=True)
    kernel = op_dir / "op_kernel" / "arch22" / f"{_OP}.cpp"
    kernel.parent.mkdir(parents=True, exist_ok=True)
    kernel.write_text("class DemoOp { void Process() {} };\n")
    return op_dir


def test_mc2_plan_subprocess_exits_zero_and_seeds_state(tmp_path, smoke_env):
    """--multirank --port-a3-ops --npubench-task --plan: exit 0, workspace seeded."""
    task = _task_pair(tmp_path)
    ops = _ops_nn_dir(tmp_path)
    try:
        result = _run_cli(
            [
                "--multirank",
                "--port-a3-ops",
                str(ops),
                "--npubench-task",
                str(task),
                "--plan",
            ],
            smoke_env,
        )
        assert result.returncode == 0, (
            f"rc={result.returncode}\nstdout={result.stdout[-2000:]}\n"
            f"stderr={result.stderr[-2000:]}"
        )
        op_dir = _WORKSPACE_ROOT / _OP
        state_file = op_dir / ".opgen_state.json"
        assert state_file.exists(), "plan run must seed .opgen_state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state.get("opgen_mode") == "port_a3_to_a5"
        assert state.get("multirank") is True
        clf_file = op_dir / "op_classification.json"
        assert clf_file.exists(), "plan run must seed op_classification.json"
        clf = json.loads(clf_file.read_text(encoding="utf-8"))
        assert "multirank_fusion" in json.dumps(clf)
    finally:
        _cleanup_op_workspace(_OP)


def test_mc2_missing_task_rejected(tmp_path, smoke_env):
    """Nonexistent task path → rc 2."""
    ops = _ops_nn_dir(tmp_path)
    result = _run_cli(
        [
            "--multirank",
            "--port-a3-ops",
            str(ops),
            "--npubench-task",
            str(tmp_path / "nope.py"),
            "--plan",
        ],
        smoke_env,
    )
    assert result.returncode == 2
    assert "does not exist" in (result.stdout + result.stderr)
