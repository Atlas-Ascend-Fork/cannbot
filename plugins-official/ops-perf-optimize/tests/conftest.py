# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Archived adapter tests opt in explicitly; production only uses configured plugins."""

import sys
from pathlib import Path

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills/ops-profiling-report/scripts")
)
sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "skills/ops-profiling-report/tests")
)
for path in sorted((Path(__file__).resolve().parents[1] / "skills/ops-profiling-report/tools").glob("*/tests")):
    sys.path.insert(0, str(path))


@pytest.fixture(autouse=True)
def archived_adapter_opt_in(request, monkeypatch):
    if request.node.path.name in {
        "test_npu_compute_evidence.py",
        "test_npu_collection.py",
        "test_profile_reuse_recovery.py",
        "test_report_workflow_compat.py",
        "test_report_backend_boundary.py",
    }:
        import report_contract

        monkeypatch.setitem(
            report_contract._BACKENDS, "npu-compute", "npu_compute_backend"
        )
