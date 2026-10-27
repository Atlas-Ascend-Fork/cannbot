# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""W-multirank (2026-08-19) — multirank mode dispatch tests.

Validates that:
- YAML `phase_o4_initial_state_by_mode` registers multirank → await_worker
- workflow_critic loads YAML and recognizes multirank as a valid mode
"""

from __future__ import annotations

import sys
from pathlib import Path

import _reorg_paths  # reorg ut/it/ct: stable data-path anchors
import yaml

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _reorg_paths.REPO_ROOT
sys.path.insert(0, str(_HERE.parent.parent))


def _load_state_machine_yaml() -> dict:
    yaml_path = _PROJECT_ROOT.parent / "workflows" / "opgen_state_machine.yaml"
    return yaml.safe_load(yaml_path.read_text())


# ---------------------------------------------------------------------------
# YAML mode entry
# ---------------------------------------------------------------------------
def test_yaml_phase_o4_initial_state_by_mode_includes_multirank():
    """Multirank rides the port_a3_to_a5 key (no standalone mode entry);

    the retired opgen_mc2 entry must be gone.
    """
    sm = _load_state_machine_yaml()
    initial = sm.get("phase_o4_initial_state_by_mode", {})
    assert initial.get("port_a3_to_a5") == "await_worker"
    assert "opgen_mc2" not in initial


def test_yaml_o1_mode_enum_includes_multirank():
    """O1 invariants enumerate port_a3_to_a5 (which multirank rides); the

    retired opgen_mc2 literal must be gone.
    """
    sm = _load_state_machine_yaml()
    o1 = sm["phases"]["O1_parse_args"]
    inv_text = " ".join(str(x) for x in o1.get("invariants", []))
    assert "port_a3_to_a5" in inv_text
    assert "opgen_mc2" not in inv_text


def test_yaml_o2_5_branches_includes_multirank():
    """O2_5_reference_provider.branches has an multirank branch with artifacts."""
    sm = _load_state_machine_yaml()
    branches = sm["phases"]["O2_5_reference_provider"]["branches"]
    assert "multirank" in branches, f"multirank missing from branches {list(branches)}"
    branch = branches["multirank"]
    artifacts = branch.get("required_artifacts", [])
    assert artifacts, "multirank branch must declare required_artifacts"
    names = " ".join(str(a.get("path", a)) for a in artifacts)
    assert "golden" in names and "model.py" in names


def test_yaml_critic_recognizes_multirank():
    """workflow_critic loads the state machine without error and it contains multirank."""
    from workflow.state_machine import load_state_machine  # noqa: E402

    sm = load_state_machine()
    import json as _json

    assert "multirank" in _json.dumps(sm), "multirank not found in loaded state machine"


# ---------------------------------------------------------------------------
# SKILL.md drift sentinel
# ---------------------------------------------------------------------------

