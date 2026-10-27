# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""FIX-1 (2026-08-20 black-box repro): multirank must route through
`_phase_instructions_block` to its plugin hook.

The mode whitelist at the top of the function only carried
{"port_a3_to_a5", "backward"} while the `plugin.kw_brief_phase_block`
override hook — the ONLY route MultiRankPlugin has — sits at the END of the
function. Every multirank kw spawn died at the whitelist before O4 entry
(O2.5 golden work wasted). Existing tests missed it because they call the
plugin hook directly, bypassing the front-door validation.

These tests pin the END-TO-END path: env.opgen_mode=multirank +
MultiRankPlugin → the multirank worker brief, including the guard that an
attention-NAMED multirank fusion op must NOT be hijacked by the FA-class
template-assembly recipe (multirank routes through its own fusion brief).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_HERE = Path(__file__).resolve()
_ORCH_DIR = _HERE.parent.parent
if str(_ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(_ORCH_DIR))

from briefs.kw_brief import _phase_instructions_block  # noqa: E402
from plugins.multirank import MultiRankPlugin  # noqa: E402


def _mc2_env(target: str = "a2") -> SimpleNamespace:
    # Minimal env: only opgen_mode (routing) + target are consulted on the
    # multirank path — the FA emit is gated off, so no FA workspace probing fires.
    return SimpleNamespace(opgen_mode="port_a3_to_a5", target=target)


def _multirank_ws(tmp_path):
    """A port_a3 workspace flagged multirank (the new durable-state shape)."""
    import json as _json

    (tmp_path / ".opgen_state.json").write_text(
        _json.dumps({"opgen_mode": "port_a3_to_a5", "multirank": True})
    )
    return tmp_path


def test_multirank_mode_reaches_plugin_hook(tmp_path):
    """Whitelist must admit port_a3_to_a5+multirank so the extension hook fires."""
    block = _phase_instructions_block(
        "mc2_all_reduce",
        _multirank_ws(tmp_path),
        3,
        None,
        None,
        env=_mc2_env(),
        plugin=MultiRankPlugin(),
    )
    assert "Multirank compute-communication fusion kernel-worker" in block
    assert "sync_fundamentals.md" in block  # MANDATORY KB load survived routing


def test_attention_named_mc2_op_not_hijacked_by_fa_recipe(tmp_path):
    """FA-class emit runs BEFORE the mode branches and matches on op NAME;

    a multirank attention-fusion op must still fall through to the extension hook.
    """
    block = _phase_instructions_block(
        "mc2_fused_attention",
        _multirank_ws(tmp_path),
        3,
        None,
        None,
        env=_mc2_env(),
        plugin=MultiRankPlugin(),
    )
    assert "Multirank compute-communication fusion kernel-worker" in block
    assert "FA-class template-assembly" not in block


def test_unknown_mode_still_raises(tmp_path):
    env = SimpleNamespace(opgen_mode="bogus_mode", target="a5")
    with pytest.raises(RuntimeError, match="unsupported worker route"):
        _phase_instructions_block(
            "some_op",
            tmp_path,
            3,
            None,
            None,
            env=env,
            plugin=MultiRankPlugin(),
        )


def test_non_ascendc_backend_still_raises(tmp_path):
    env = SimpleNamespace(opgen_mode="port_a3_to_a5", target="a2")
    with pytest.raises(RuntimeError, match="unsupported worker route"):
        _phase_instructions_block(
            "mc2_all_reduce",
            tmp_path,
            3,
            None,
            None,
            env=env,
            backend="cuda",
            plugin=MultiRankPlugin(),
        )
