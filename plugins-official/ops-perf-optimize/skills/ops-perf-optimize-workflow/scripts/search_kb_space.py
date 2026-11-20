#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Attach adopted knowledge evidence to an analysis-authored candidate space.

Discovery, retrieval, scope review and governance remain with ops-perf-analysis
and its existing board facts / knowledge-query. This adapter only translates
kb_cards references and retains their receipts; it neither searches a second
store nor infers axes or gains from prose.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from search.candidates import load_space
from search.policy import checked_refs, load, ref, require, verify_ref


def build(space_path, knowledge_path, manifest_path):
    space, *_ = load_space(space_path)
    knowledge = load(knowledge_path)
    manifest = load(manifest_path)
    targets = manifest["configuration"]["target_socs"]
    require(
        knowledge.get("target_socs") == targets,
        "knowledge decision targets differ from frozen manifest",
    )
    dependencies = []
    # Existing adopted built-in facts and analysis evidence use ordinary refs.
    for item in knowledge.get("evidence", []):
        verify_ref(item, dependencies)
    cards = []
    for card in knowledge.get("kb_cards", []):
        require(isinstance(card, dict), "kb_cards entries must be objects")
        if card.get("decision", "adopted") != "adopted":
            continue
        # Concept path is an ID, never a filesystem location.
        reference = {"path": card.get("local_path"), "sha256": card.get("card_sha256")}
        verify_ref(reference, dependencies)
        cards.append(card)
    adopted = bool(dependencies)
    receipts = knowledge.get("receipts", [])
    if cards:
        checked_refs(receipts, "adopted knowledge-query cards")
    for receipt in receipts:
        verify_ref(receipt, dependencies)
    result = dict(space)
    triggers = list(space.get("trigger", []))
    for item in triggers:
        verify_ref(item, [])
    for item in [
        ref(space_path),
        ref(knowledge_path),
        ref(manifest_path),
        *dependencies,
    ]:
        if item not in triggers:
            triggers.append(item)
    result["trigger"] = triggers
    result["provenance"] = {
        **space.get("provenance", {}),
        "target_socs": targets,
        "knowledge_status": "adopted"
        if adopted
        else ("kb_unavailable" if knowledge.get("kb_unavailable") else "gap"),
        "kb_cards": cards,
        "knowledge_evidence": dependencies,
        "knowledge_decision": ref(knowledge_path),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--space",
        type=Path,
        required=True,
        help="candidate axes/bindings already chosen by analysis",
    )
    parser.add_argument(
        "--knowledge",
        type=Path,
        required=True,
        help="analysis decision: target_socs, kb_cards, evidence, receipts",
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        inputs = (args.space, args.knowledge, args.manifest)
        require(
            args.out.resolve() not in {p.resolve() for p in inputs},
            "adapter output must not overwrite its inputs",
        )
        result = build(*inputs)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "status": "adapted",
                    "out": str(args.out.resolve()),
                    "knowledge_status": result["provenance"]["knowledge_status"],
                }
            )
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "invalid", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
