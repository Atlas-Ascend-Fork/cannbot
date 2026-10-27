# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""multirank canonical verifier contract tests (design §5 Layer 4b).

Covers reference_provider/multirank_verify.py — the harness-tree canonical verifier
executed in place by multirank_runner (never staged into a workspace): it must
import the canonical judge classify_multirank_case (multirank_precision_eval_two_tier —
separation 2026-06-30; the old _rank_pass allclose was removed, tolerance
lives in the orchestrator library; per-case tolerance tests live in
tests/test_multirank_precision_eval_two_tier.py).

No NPU: static source check. (mc2_reference.template.py was removed — the CPU
multi-rank golden simulation is provisioned by the orchestrator's O2.5 phase;
the template carried a stale top-level world_size contract, superseded by
per-case world_size.)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_RP_DIR = (
    Path(__file__).resolve().parent.parent / "reference_provider"
)  # plugins/multirank/reference_provider/


def test_multirank_verify_imports_canonical_judge():
    """multirank_verify (harness-tree canonical verifier) must import

    classify_multirank_case from the orchestrator canonical library
    (multirank_precision_eval_two_tier) — §4e mechanism-gate / §4j hermetic. The
    worker must NOT re-derive tolerance (old _rank_pass removed).
    """
    src = (_RP_DIR / "multirank_verify.py").read_text()
    # The import statement may fold across lines (ruff format); assert the
    # module and the imported name are both wired, not a literal one-liner.
    assert "from multirank_precision_eval_two_tier import" in src
    assert "classify_multirank_case" in src
    # defensive: the old single-threshold allclose must not have been restored
    assert "def _rank_pass" not in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
