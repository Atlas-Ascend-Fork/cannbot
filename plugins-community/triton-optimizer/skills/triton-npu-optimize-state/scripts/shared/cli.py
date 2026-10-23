# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

from shared.models import OptimizeCheckResult


def build_check_payload(result: OptimizeCheckResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": result.kind,
        "status": result.status,
        "issues": list(result.issues),
        "guideline": result.summary,
    }
    if result.next_option is not None:
        payload["next_option"] = result.next_option
    return payload


def build_workflow_failure_payload(
    *,
    kind: str,
    issue: str,
    guideline: str,
) -> dict[str, object]:
    return {
        "kind": kind,
        "status": "fail",
        "issues": [issue],
        "guideline": guideline,
    }
