# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""G1: MultiRankPlugin.pp_brief_phase_block.

Asserts the probe brief override carries multirank multi-rank commands (run.py verify
/ multirank_runner) and explicitly forbids the single-card deploy_to_a5.sh that the
default probe.md hardcodes (which gives false PASS on multirank).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ORCH_DIR = _HERE.parent.parent
if str(_ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(_ORCH_DIR))

from plugins.multirank import MultiRankPlugin  # type: ignore


def _block():
    return MultiRankPlugin().pp_brief_phase_block(handoff_str="", iter_cap=3)


def test_returns_string_not_none():
    """Plugin override must return content (None = fall back to single-rank default)."""
    block = _block()
    assert block is not None
    assert len(block) > 200


def test_has_multirank_run_py():
    block = _block()
    assert "run.py verify" in block, (
        "multirank probe brief must use run.py verify (multi-rank)"
    )
    assert "multirank_runner" in block, (
        "must reference multirank_runner (multi-process)"
    )


def test_forbids_deploy_to_a5():
    """Must explicitly forbid deploy_to_a5.sh (single-card, false PASS on multirank)."""
    block = _block()
    assert "Do NOT use deploy_to_a5.sh" in block


def test_has_multirank_bug_classes():
    block = _block()
    assert "multirank-multicore-race" in block
    assert "P-P52" in block
    assert "A-P61" in block


def test_handoff_str_injected():
    block = MultiRankPlugin().pp_brief_phase_block(
        handoff_str=" FROM_WORKER", iter_cap=3
    )
    assert "FROM_WORKER" in block
