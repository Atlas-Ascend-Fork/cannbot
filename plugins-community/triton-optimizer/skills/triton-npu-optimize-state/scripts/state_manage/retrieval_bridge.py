# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Bridge from submit-deep-analysis to the pattern-retrieval skill.

Finds the retrieval skill, invokes its ``retrieve_patterns.py`` as a subprocess
with the uniform argument set, and maps the aligned results onto the
recommendation entries consumed by the submit output. The caller is
mechanism-blind: each skill script takes the inputs it needs from the uniform
set and reports its own errors. Retrieval problems degrade to a skip note;
they never fail the submission.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

# The retrieval skill stages under one stable name regardless of mechanism,
# mirroring PATTERN_RETRIEVAL_STAGED_SKILL in src/helix/skills/selection.py.
# Skill scripts stay self-contained, so the staged-name contract is duplicated
# here instead of shared.
RETRIEVAL_STAGED_SKILL = "triton-npu-retrieve-patterns"
BACKEND_SKILL_DIRS = (".codex", ".claude", ".agents", ".opencode", ".pi", ".openhands", ".trae")
RETRIEVAL_TIMEOUT_SECONDS = 1800
MAX_RECORDED_RECOMMENDATIONS = 3


def find_staged_retrieval_skill(workspace: Path) -> Path | None:
    for backend in BACKEND_SKILL_DIRS:
        candidate = workspace / backend / "skills" / RETRIEVAL_STAGED_SKILL
        if (candidate / "scripts" / "retrieve_patterns.py").is_file():
            return candidate
    return None


def _run_retrieval(argv: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=RETRIEVAL_TIMEOUT_SECONDS,
        )
    except subprocess.SubprocessError as exc:
        raise ValueError(f"pattern retrieval could not run: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()[:300]
        raise ValueError(f"pattern retrieval failed: {detail}")
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"pattern retrieval output is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("pattern retrieval output is not a JSON object")
    return cast(dict[str, Any], parsed)


def run_retrieval(
    skill_dir: Path,
    *,
    symptoms: list[str],
    exclude: list[str],
    code: Path,
    analysis: Path,
    contract: Path,
) -> dict[str, Any]:
    """Invoke the retrieval skill with the uniform argument set.

    Pattern cards resolve from the cannbot-knowledge clone via the contract's
    staged location; no patterns directory is passed.
    """
    argv = [
        sys.executable,
        str(skill_dir / "scripts" / "retrieve_patterns.py"),
        "retrieve",
        "--output-json",
        "--contract",
        str(contract),
        "--code",
        str(code),
        "--analysis",
        str(analysis),
    ]
    for symptom in symptoms:
        argv.extend(["--symptom", symptom])
    for pattern_id in exclude:
        argv.extend(["--exclude", pattern_id])
    return _run_retrieval(argv)


def map_results(payload: dict[str, Any]) -> list[dict[str, object]]:
    """Map aligned retrieval results onto recommendation entries."""
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("pattern retrieval output has no results list")
    entries: list[dict[str, object]] = []
    for item in cast(list[object], raw_results):
        if not isinstance(item, dict):
            raise ValueError("pattern retrieval results contain an invalid entry")
        typed = cast(dict[str, object], item)
        identifier = typed.get("pattern")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("pattern retrieval entry has no pattern id")
        matched = typed.get("matched_symptoms")
        entry: dict[str, object] = {
            "id": identifier,
            "path": typed.get("card"),
            "summary": typed.get("summary", ""),
            "use_when": typed.get("use_when", []),
            "matched_symptoms": matched if isinstance(matched, list) else [],
        }
        probability = typed.get("probability")
        if isinstance(probability, (int, float)):
            entry["probability"] = probability
        entries.append(entry)
    # The durable record and recommendation history stay small and mechanism
    # comparable: drop the none pseudo-option and, for probabilistic results,
    # keep only the top few. The markdown keeps the full returned distribution.
    entries = [entry for entry in entries if entry["id"] != "none"]
    if any("probability" in entry for entry in entries):
        def probability_of(entry: dict[str, object]) -> float:
            value = entry.get("probability")
            return float(value) if isinstance(value, (int, float)) else 0.0

        entries = sorted(
            entries,
            key=lambda entry: (-probability_of(entry), str(entry["id"])),
        )[:MAX_RECORDED_RECOMMENDATIONS]
    return entries
