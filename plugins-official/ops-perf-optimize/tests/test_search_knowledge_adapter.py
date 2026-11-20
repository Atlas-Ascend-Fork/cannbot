# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Use existing analysis knowledge references; no search-owned knowledge store."""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = (
    Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"
)
sys.path.insert(0, str(SCRIPTS))
# ruff: noqa: E402
import search_kb_space
from search import candidates
from search.policy import ref


def write(path, value):
    path.write_text(json.dumps(value))
    return path


def inputs(tmp_path):
    space = write(
        tmp_path / "axes.json",
        {
            "schema_version": 1,
            "axes": [
                {"name": "tile", "values": [64, 128, 256]},
                {"name": "buffer", "values": [1, 2]},
            ],
            "prior": {"gain": [0.01, 0.1]},
        },
    )
    manifest = write(
        tmp_path / "manifest.json", {"configuration": {"target_socs": ["Ascend910B"]}}
    )
    decision = {"target_socs": ["Ascend910B"], "kb_cards": [], "evidence": []}
    return space, manifest, decision


def test_adapts_external_card_and_builtin_fact_without_copying_knowledge(tmp_path):
    space, manifest, decision = inputs(tmp_path)
    card = tmp_path / "query-card.md"
    card.write_text("full card already read by analysis")
    fact = tmp_path / "board-fact.md"
    fact.write_text("existing board fact")
    receipt = write(tmp_path / "receipt.json", {"decision": "adopted"})
    decision["kb_cards"] = [
        {
            "path": "ops/tiling/concept",
            "local_path": str(card),
            "card_sha256": ref(card)["sha256"],
            "purpose": "direction",
        }
    ]
    decision["evidence"] = [ref(fact)]
    decision["receipts"] = [ref(receipt)]
    knowledge = write(tmp_path / "knowledge.json", decision)
    result = search_kb_space.build(space, knowledge, manifest)
    assert result["axes"] == json.loads(space.read_text())["axes"]
    assert result["prior"] == {"gain": [0.01, 0.1]}
    assert result["provenance"]["knowledge_status"] == "adopted"
    assert all(ref(p) in result["trigger"] for p in (card, fact, receipt))
    # The references survive candidate generation, rather than disappearing at handoff.
    adapted = write(tmp_path / "adapted.json", result)
    parent = {"commit": "a" * 40, "tree": "b" * 40}
    f = candidates.build(adapted, parent, receipt, "round1", 100, 3, 0.5, 64)
    assert all(ref(card) in node["trigger"] for node in f["nodes"])
    card.write_text("changed")
    with pytest.raises(ValueError, match="stale evidence"):
        candidates.build(adapted, parent, receipt, "round1", 100, 3, 0.5, 64)


@pytest.mark.parametrize("unavailable", [False, True])
def test_missing_knowledge_is_nonblocking_and_does_not_invent_axes(
    tmp_path, unavailable
):
    space, manifest, decision = inputs(tmp_path)
    decision["kb_unavailable"] = unavailable
    knowledge = write(tmp_path / "knowledge.json", decision)
    result = search_kb_space.build(space, knowledge, manifest)
    assert result["axes"] == json.loads(space.read_text())["axes"]
    assert result["provenance"]["knowledge_status"] == (
        "kb_unavailable" if unavailable else "gap"
    )
    assert result["provenance"]["knowledge_evidence"] == []


def test_rejects_other_target_and_stale_card_and_missing_receipt(tmp_path):
    space, manifest, decision = inputs(tmp_path)
    knowledge = write(
        tmp_path / "knowledge.json", {**decision, "target_socs": ["Ascend950PR"]}
    )
    with pytest.raises(ValueError, match="targets differ"):
        search_kb_space.build(space, knowledge, manifest)
    card = tmp_path / "card.md"
    card.write_text("old")
    decision["kb_cards"] = [
        {"local_path": str(card), "card_sha256": ref(card)["sha256"]}
    ]
    write(knowledge, decision)
    with pytest.raises(ValueError, match="evidence references"):
        search_kb_space.build(space, knowledge, manifest)
    card.write_text("new")
    with pytest.raises(ValueError, match="stale evidence"):
        search_kb_space.build(space, knowledge, manifest)


def test_refuted_card_does_not_become_a_trigger(tmp_path):
    space, manifest, decision = inputs(tmp_path)
    decision["kb_cards"] = [{"decision": "refuted", "local_path": "/absent"}]
    knowledge = write(tmp_path / "knowledge.json", decision)
    assert (
        search_kb_space.build(space, knowledge, manifest)["provenance"][
            "knowledge_status"
        ]
        == "gap"
    )


def test_zero_hit_receipt_remains_a_knowledge_gap(tmp_path):
    space, manifest, decision = inputs(tmp_path)
    receipt = write(tmp_path / "zero-hits.json", {"results": []})
    decision["receipts"] = [ref(receipt)]
    knowledge = write(tmp_path / "knowledge.json", decision)
    result = search_kb_space.build(space, knowledge, manifest)
    assert result["provenance"]["knowledge_status"] == "gap"
    assert ref(receipt) in result["trigger"]
