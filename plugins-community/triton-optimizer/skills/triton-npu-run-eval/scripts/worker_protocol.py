# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Line protocol shared by the unified worker and its parent supervisor.

One compact JSON object per stdout line. ``data`` carries the payload; any
line that does not decode is passthrough output (banners, CANN logs) and is
forwarded but not parsed.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional, TypedDict, cast

KIND_CASE = "case"
KIND_PROGRESS = "progress"
KIND_FINAL = "final"

PHASE_TEST = "test"
PHASE_BENCH = "bench"
PHASE_PROFILE = "profile"

_KINDS = (KIND_CASE, KIND_PROGRESS, KIND_FINAL)


class ProtocolMessage(TypedDict):
    kind: str
    phase: str
    data: "dict[str, Any]"


def encode_message(kind: str, phase: str, data: Mapping[str, Any]) -> str:
    return json.dumps({"kind": kind, "phase": phase, "data": dict(data)}, separators=(",", ":"))


def encode_case(phase: str, record: Mapping[str, Any]) -> str:
    return encode_message(KIND_CASE, phase, dict(record))


def encode_progress(phase: str, event: str, detail: Optional[Mapping[str, Any]] = None) -> str:
    payload: dict[str, Any] = {"event": event}
    if detail:
        payload.update(dict(detail))
    return encode_message(KIND_PROGRESS, phase, payload)


def encode_final(phase: str, payload: Mapping[str, Any]) -> str:
    return encode_message(KIND_FINAL, phase, dict(payload))


def decode_message(line: str) -> Optional[ProtocolMessage]:
    text = line.strip()
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    envelope = cast(dict[str, object], parsed)
    kind = envelope.get("kind")
    phase = envelope.get("phase")
    data = envelope.get("data")
    if kind not in _KINDS or not isinstance(phase, str) or not isinstance(data, dict):
        return None
    return ProtocolMessage(kind=str(kind), phase=phase, data=cast(dict[str, Any], data))
