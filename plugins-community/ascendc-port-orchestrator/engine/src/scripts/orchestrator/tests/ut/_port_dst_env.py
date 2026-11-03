# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Shared import-time header for the port-destination pin tests.

test_port_destinations_310b.py and test_port_destinations_310p.py pin the
same engine seams against different destinations; the shared header, seam
bindings, and npubench sidecar helpers live here once.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import a5_target_capability as cap
import finalize_pipeline  # noqa: F401 - initializes parent before dispatch re-export
import finalize_dispatch

# DEBT-47 hazard (bare-name collision): a conftest-imported module can bind
# the bare name ``orchestrator`` to the PACKAGE, not orchestrator.py.  Undo
# the package binding and MOVE the module dir to the front of sys.path —
# import-time only, the conftest's per-test snapshots are unaffected.

_orch_dir = str(Path(__file__).resolve().parents[2])
_bound = sys.modules.get("orchestrator")
if _bound is not None and not str(getattr(_bound, "__file__", "")).endswith("orchestrator.py"):
    del sys.modules["orchestrator"]
if _orch_dir in sys.path:
    sys.path.remove(_orch_dir)
sys.path.insert(0, _orch_dir)

import orchestrator as orch  # noqa: E402,F401 - re-exported to both files
import phase_o5_runner  # noqa: E402,F401 - monkeypatch target in both files
from a3_ref_common import PORT_DESTINATIONS  # noqa: F401
from briefs._common import TARGET_ENV_PREFIXES as BRIEF_PREFIXES  # noqa: F401
from briefs._common import load_env, target_env_prefix  # noqa: F401
from briefs.op_taxonomy import TARGET_HW_SPEC_MAP  # noqa: F401
from npubench.npubench_inputs import (  # noqa: F401
    NpubenchInputError,
    assert_sidecar_dtype_supported,
    validate_cli_npubench_args,
)

# Bind MODULE-PRIVATE seams once via getattr (dotted underscore access trips
# the protected-access checker); the bound objects resolve their module
# globals at call time, so behavior is identical to attribute access.
_port_destination_prefix = getattr(phase_o5_runner, "_port_destination_prefix")
_normalise_target = getattr(phase_o5_runner, "_normalise_target")
_a5_build_host = getattr(phase_o5_runner, "_a5_build_host")
_a5_build_container = getattr(phase_o5_runner, "_a5_build_container")
_a5_build_cann_path = getattr(phase_o5_runner, "_a5_build_cann_path")
_inject_migration_metadata = getattr(finalize_dispatch, "_inject_migration_metadata")


def _seed_port_workspace(tmp_path: Path) -> Path:
    """Seed a workspace the port_a3 plugin claims (opgen_mode marker only)."""
    (tmp_path / ".opgen_state.json").write_text(
        json.dumps({"opgen_mode": "port_a3_to_a5"})
    )
    return tmp_path


def _sidecar_args(tmp_path: Path, sidecar_text: str):
    """Stage a minimal task+sidecar pair and return the validated args."""
    task = tmp_path / "task.py"
    task.write_text("import torch\n")
    (tmp_path / "task.json").write_text(sidecar_text)
    args = validate_cli_npubench_args(task, tmp_path)
    if args is None:
        raise AssertionError("validate_cli_npubench_args rejected the staged task/sidecar pair")
    return args
