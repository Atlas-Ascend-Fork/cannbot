# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""FIX-5 (2026-08-20 black-box repro): wire the pp_brief plugin override hook.

`_probe_phase_block` accepted a `plugin` kwarg but never called it —
MultiRankPlugin.pp_brief_phase_block (multi-rank probe protocol + mandatory
sync/comm KB load incl. sync_fundamentals.md) was dead code, so multirank precision
probes ran the generic single-rank brief without the synchronization
knowledge the missing-fence defect family needs. These tests pin the wiring
and the regression guard: non-overriding plugins keep the generic block.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ORCH_DIR = _HERE.parent.parent
if str(_ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(_ORCH_DIR))

from briefs.pp_brief import _probe_phase_block  # noqa: E402
from plugins.base import BasePlugin  # noqa: E402
from plugins.backward import BackwardPlugin  # noqa: E402
from plugins.multirank import MultiRankPlugin  # noqa: E402


def test_mc2_plugin_override_replaces_generic_probe_block():
    block = _probe_phase_block(None, 3, plugin=MultiRankPlugin())
    assert "multirank backend" in block
    # the sync-defect knowledge the repro was missing:
    assert "sync_fundamentals.md" in block
    assert "multirank_communication.md" in block
    # multi-rank reproduction protocol, not the generic single-rank triage
    assert "T1-vs-CPU triage" not in block


def test_mc2_override_carries_worker_handoff():
    block = _probe_phase_block(
        "rank1 mismatch after fence insert", 3, plugin=MultiRankPlugin()
    )
    assert "## Handoff from worker" in block
    assert "rank1 mismatch after fence insert" in block


def test_backward_plugin_keeps_generic_probe_block():
    """Regression guard: plugins without a pp override (backward, port_a3)

    must keep the generic single-rank probe brief unchanged.
    """
    block = _probe_phase_block(None, 3, plugin=BackwardPlugin())
    assert block.startswith("# PHASES (aog-precision-probe)")
    assert "T1-vs-CPU triage" in block
    assert "multirank backend" not in block


def test_plugin_none_keeps_generic_probe_block():
    block = _probe_phase_block(None, 3, plugin=None)
    assert block.startswith("# PHASES (aog-precision-probe)")


def test_base_plugin_pp_hook_defaults_to_none():
    """BasePlugin declares the protocol hook; the neutral default is None

    (no override) so non-overriding plugins route to the generic block.
    """
    assert BasePlugin().pp_brief_phase_block(handoff_str="", iter_cap=1) is None
