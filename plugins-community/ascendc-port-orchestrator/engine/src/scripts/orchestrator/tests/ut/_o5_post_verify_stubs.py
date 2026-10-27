# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the License).
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Shared O5 post-verify seam stubs (fsm/o5-wiring test mock style)."""

import importlib

import events
import finalize_pipeline
import phase_o5
import state_executor


def wire_recorded_transitions(monkeypatch, truth_source: str) -> list:
    """Neutralize the O5 seams and record transition target states."""
    monkeypatch.setattr(importlib, "reload", lambda m: m)
    monkeypatch.setattr(events, "emit", lambda *a, **k: None)
    monkeypatch.setattr(phase_o5, "expected_truth_source", lambda ws: truth_source)
    monkeypatch.setattr(phase_o5, "format_block_message", lambda op, o5: "")
    monkeypatch.setattr(finalize_pipeline, "record_rollback", lambda *a, **k: None)
    recorded: list = []
    monkeypatch.setattr(
        state_executor,
        "record_transition",
        lambda ws, dec: recorded.append(dec.next_state),
    )
    return recorded
