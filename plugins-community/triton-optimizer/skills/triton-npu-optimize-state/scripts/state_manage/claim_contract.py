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

import re


"""Structured claim contract.

These strings are injected into the agent's context at the moment the
corresponding command runs (claim-edit validation), so the required answer
formats stay decoupled from the static optimize system prompt.
"""

OPTIMIZE_KNOWLEDGE_PATTERN_INFIXES = (
    "/triton-npu-optimize-knowledge/references/patterns/",
    "/tilelang-npu-optimize-knowledge/references/patterns/",
    "/ascendc-npu-optimize-knowledge/references/patterns/",
    "/torch-npu-optimize-knowledge/references/patterns/",
)

# Pattern cards now live in the cannbot-knowledge repository (provisioned at
# .cannbot/dependencies/<plugin>/cannbot-knowledge/), served read-only.
_KB_PATTERN_PATH_RE = re.compile(
    r"/cannbot-knowledge/knowledge/ops/[^/]+/optimizations/(?:patterns|operator_optimization)/[^/]+\.md$"
)

CLAIM_RESPONSE_REQUIRED = (
    "claim-edit requires a dependency claim. Run it only when the edit hook "
    "denies an operator edit for a missing claim; never call it proactively. "
    "After a denial, choose exactly one of two options (no third case): "
    "1) `--source pattern`: provide at least one `--pattern-path` that names the "
    "exact optimize pattern markdown file that guided this edit, from the "
    "cannbot-knowledge library "
    "(`*/cannbot-knowledge/knowledge/ops/<language>/optimizations/patterns/<name>.md` or "
    "`*/cannbot-knowledge/knowledge/ops/<language>/optimizations/operator_optimization/<name>.md`). "
    "Every path is validated to exist in the provisioned cannbot-knowledge clone. "
    "Optionally "
    "list diagnosis or symptom files that also shaped the edit; those extras do "
    "not replace a pattern path; or "
    "2) `--source self-directed`: you referenced no skill or pattern file, "
    "with only a `--reason`. "
    "`--reason` is always required and must explain the problem you are "
    "solving, why these skills/patterns, and the expected effect."
)


def _is_optimize_knowledge_pattern_path(raw_path: str) -> bool:
    normalized = "/" + raw_path.replace("\\", "/").lstrip("/")
    if not normalized.endswith(".md"):
        return False
    if _KB_PATTERN_PATH_RE.search(normalized):
        return True
    for infix in OPTIMIZE_KNOWLEDGE_PATTERN_INFIXES:
        if infix not in normalized:
            continue
        after = normalized.rsplit(infix, 1)[1]
        if after and "/" not in after:
            return True
    return False


def claim_includes_optimize_knowledge_pattern(*, pattern_paths: list[str]) -> bool:
    """Return whether any claimed path is an optimize-knowledge pattern card."""
    return any(_is_optimize_knowledge_pattern_path(path) for path in pattern_paths)


def optimize_knowledge_pattern_paths(*, pattern_paths: list[str]) -> list[str]:
    """Return the claimed paths that are optimize-knowledge pattern cards."""
    return [path for path in pattern_paths if _is_optimize_knowledge_pattern_path(path)]


EDIT_CLAIM_ERROR_CODE_PATTERN_REQUIRED = "pattern_required"
EDIT_CLAIM_ERROR_CODE_SKILL_DEPENDENCY_INVALID = "skill_dependency_invalid"
EDIT_CLAIM_ERROR_CODE_ROUND_NOT_ACTIVE = "round_not_active"
EDIT_CLAIM_ERROR_CODE_STATE_INCONSISTENT = "state_inconsistent"
EDIT_CLAIM_ERROR_CODE_WRONG_TARGET = "wrong_target"
EDIT_CLAIM_ERROR_CODE_REASON_REQUIRED = "reason_required"
EDIT_CLAIM_ERROR_CODE_UNKNOWN_SOURCE = "unknown_source"
EDIT_CLAIM_ERROR_CODE_LEDGER_UNAVAILABLE = "ledger_unavailable"

EDIT_CLAIM_ERROR_FALLBACK_GUIDELINE = (
    "Repair the claim arguments and retry before editing the operator snapshot."
)

# Map claim-edit error codes (carried by WorkflowError) to actionable
# guidelines for the agent. Codes absent from this table fall back to
# EDIT_CLAIM_ERROR_FALLBACK_GUIDELINE.
EDIT_CLAIM_ERROR_GUIDELINES: dict[str, str] = {
    EDIT_CLAIM_ERROR_CODE_PATTERN_REQUIRED: CLAIM_RESPONSE_REQUIRED,
    EDIT_CLAIM_ERROR_CODE_SKILL_DEPENDENCY_INVALID: CLAIM_RESPONSE_REQUIRED,
    EDIT_CLAIM_ERROR_CODE_ROUND_NOT_ACTIVE: (
        "Use `triton-npu-optimize-state` `start-round` to open the intended round, "
        "then claim the operator edit again."
    ),
    EDIT_CLAIM_ERROR_CODE_WRONG_TARGET: (
        "Pass the active round's optimized operator snapshot through `--target`."
    ),
    EDIT_CLAIM_ERROR_CODE_REASON_REQUIRED: (
        "`--reason` is required and must explain the problem you are solving, "
        "why these skills/patterns, and the expected effect."
    ),
    EDIT_CLAIM_ERROR_CODE_UNKNOWN_SOURCE: (
        "`--source` must be exactly one of `pattern` or `self-directed`; "
        "there is no third case."
    ),
    EDIT_CLAIM_ERROR_CODE_STATE_INCONSISTENT: (
        "The temporary optimize workflow state is inconsistent or invalid. "
        "Stop this attempt and restart the optimize session so the runner "
        "can rebuild the workflow state before claiming an edit."
    ),
    EDIT_CLAIM_ERROR_CODE_LEDGER_UNAVAILABLE: (
        "The pattern-usage ledger is unavailable. Ask the runner to restart "
        "the optimize session so the ledger can be recreated, then claim the "
        "operator edit again."
    ),
}
