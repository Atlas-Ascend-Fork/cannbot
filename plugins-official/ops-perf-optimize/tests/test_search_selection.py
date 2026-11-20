# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Auto-merge tests for search observations into selection.json."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"
)
sys.path.insert(0, str(SCRIPTS))
import search_selection


def write(path, value):
    path.write_text(json.dumps(value))
    return path


def fixture(tmp_path, outcome="measured"):
    selection = write(tmp_path / "selection.json", {"performance": {"selected_candidate": "baseline"}})
    observation = write(
        tmp_path / "observation.json",
        {
            "comparison": "paired",
            "confirmation_required": False,
            "recommended": "s1",
            "observations": [
                {
                    "scheme_id": "s1",
                    "outcome": outcome,
                    "score_distribution": {"metric": "candidate_over_reference", "samples": [0.9, 0.91, 0.89]},
                    "confidence_interval": {"low": 0.88, "high": 0.92, "confidence": 0.95},
                    "pareto_rank": 1,
                    "race": {"decision": "stop_winner"},
                    "mechanism": {"status": "unknown"},
                    "retry_condition": "paired evidence",
                }
            ],
        },
    )
    gate = write(tmp_path / "gate.json", {"decision": "pass"})
    effect = write(tmp_path / "effect.json", {"effective_improvement_count": 1})
    evidence = write(tmp_path / "acceptance.md", "functional pass")
    return selection, observation, gate, effect, evidence


def test_merge_measured_observation_keeps_selection_choices(tmp_path):
    selection, observation, gate, effect, evidence = fixture(tmp_path)
    merged = search_selection.build(
        selection, observation, None, gate, effect, [evidence], "unknown", [], "new probe"
    )
    assert merged["performance"]["selected_candidate"] == "baseline"
    search = merged["search"]
    assert search["scheme_id"] == "s1"
    assert search["outcome"] == "measured"
    assert search["conformance_gate"]["path"] == str(gate.resolve())
    assert search["effect_summary"]["path"] == str(effect.resolve())
    assert search["score_distribution"]["samples"] == [0.9, 0.91, 0.89]
    assert search["pareto_rank"] == 1
    assert search["race"]["decision"] == "stop_winner"


def test_measured_merge_requires_gate_and_effect(tmp_path):
    selection, observation, gate, effect, evidence = fixture(tmp_path)
    with pytest.raises(ValueError, match="conformance-gate"):
        search_selection.build(selection, observation, None, None, effect, [evidence], "unknown", [], "")
    with pytest.raises(ValueError, match="effect-summary"):
        search_selection.build(selection, observation, None, gate, None, [evidence], "unknown", [], "")


def test_failed_observation_does_not_need_gate(tmp_path):
    selection, observation, gate, effect, evidence = fixture(tmp_path, outcome="implementation_failed")
    merged = search_selection.build(
        selection, observation, None, None, None, [evidence], "unknown", [], "fix build"
    )
    assert merged["search"]["outcome"] == "implementation_failed"
    assert "conformance_gate" not in merged["search"]


def test_existing_search_needs_replace(tmp_path):
    selection, observation, gate, effect, evidence = fixture(tmp_path)
    merged = write(tmp_path / "selection2.json", {"search": {"scheme_id": "old"}})
    with pytest.raises(ValueError, match="already has search"):
        search_selection.build(merged, observation, None, gate, effect, [evidence], "unknown", [], "")


def test_verified_mechanism_needs_evidence(tmp_path):
    selection, observation, gate, effect, evidence = fixture(tmp_path)
    with pytest.raises(ValueError, match="mechanism-evidence"):
        search_selection.build(selection, observation, None, gate, effect, [evidence], "verified", [], "")
