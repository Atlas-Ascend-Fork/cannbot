# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------


"""Regression checks for the plugin's external knowledge-card paths."""

import importlib.util
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
SCRIPT = (
    PLUGIN
    / "skills/triton-npu-optimize-state/scripts/state_manage/pattern_recommendations.py"
)
recommendation_spec = importlib.util.spec_from_file_location(
    "pattern_recommendations", SCRIPT
)
recommendations = importlib.util.module_from_spec(recommendation_spec)
recommendation_spec.loader.exec_module(recommendations)


class PatternPathTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.kb = self.root / "cannbot-knowledge"
        self.cards = self.kb / "knowledge/ops/triton/optimizations"
        self.contract = self.root / "symptom-contract.json"

    def card(self, relative):
        path = self.cards / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "## Summary\n\nA real candidate.\n\n## Use When\n\n- Measured evidence.\n"
        )
        return path

    def write_contract(self, routes, paths):
        self.contract.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "max_submitted": 5,
                    "unknown_id": "unknown",
                    "pattern_paths": paths,
                    "symptoms": [
                        {
                            "id": symptom,
                            "summary": symptom,
                            "evidence_hint": "Measured evidence.",
                            "common_non_matches": [],
                            "candidate_patterns": candidates,
                        }
                        for symptom, candidates in routes.items()
                    ],
                }
            )
        )
        self.write_stages({identifier: "kernel" for identifier in paths})

    def write_stages(self, stages):
        lines = []
        for number, stage in enumerate(
            ("structural", "kernel", "refinement", "autotune"), 1
        ):
            lines.append(f"## {number}. {stage.title()}: Test stage")
            lines.extend(
                f"#### `{identifier}`\n- Priority: normal"
                for identifier, value in stages.items()
                if value == stage
            )
        self.contract.with_name("pattern_index.md").write_text(
            "\n\n".join(lines) + "\n"
        )

    def test_index_priority_applies_without_card_metadata(self):
        self.card("patterns/a_normal.md")
        self.card("patterns/z_high.md")
        self.write_contract(
            {"pressure": ["a-normal", "z-high"]},
            {"a-normal": "patterns/a_normal.md", "z-high": "patterns/z_high.md"},
        )
        self.contract.with_name("pattern_index.md").write_text(
            "## 2. Kernel: Test\n#### `a-normal`\n- Priority: normal\n"
            "#### `z-high`\n- Priority: high\n"
        )
        result = self.query(["pressure"])

        self.assertEqual(
            [entry["pattern"] for entry in result],
            ["z-high", "a-normal"],
        )

    def test_prose_applicability_keeps_paragraphs_code_and_bullets(self):
        text = (
            "Measured pressure.\n\n```python\nx = load(ptr)\n```\n\n- Only with reuse."
        )
        card = self.card("patterns/current.md")
        card.write_text("## Summary\n\nCandidate.\n\n## Use When\n\n" + text + "\n")
        self.write_contract(
            {"pressure": ["current"]}, {"current": "patterns/current.md"}
        )
        result = self.query(["pressure"])

        self.assertEqual(result[0]["use_when"], [text])

    def test_stage_order_applies_before_top_three_without_card_metadata(self):
        stages = {
            "a-autotune": "autotune",
            "b-refinement": "refinement",
            "c-kernel": "kernel",
            "z-structural": "structural",
        }
        paths = {identifier: f"patterns/{identifier}.md" for identifier in stages}
        for relative in paths.values():
            self.card(relative)
        self.write_contract({"pressure": list(stages)}, paths)
        self.write_stages(stages)
        result = self.query(["pressure"])

        self.assertEqual(
            [entry["pattern"] for entry in result],
            ["z-structural", "c-kernel", "b-refinement"],
        )

    def test_index_stage_overrides_card_stage_and_later_stage_match_count(self):
        earlier = self.card("patterns/z_earlier.md")
        later = self.card("patterns/a_later.md")
        earlier.write_text(
            "---\noptimization_stage: autotune\npriority: normal\n---\n"
            + earlier.read_text()
        )
        later.write_text(
            "---\noptimization_stage: structural\npriority: high\n---\n"
            + later.read_text()
        )
        self.write_contract(
            {"one": ["z-earlier", "a-later"], "two": ["a-later"]},
            {"z-earlier": "patterns/z_earlier.md", "a-later": "patterns/a_later.md"},
        )
        self.write_stages({"z-earlier": "structural", "a-later": "kernel"})
        result = self.query(["one", "two"])

        self.assertEqual(
            [entry["pattern"] for entry in result],
            ["z-earlier", "a-later"],
        )

    def test_invalid_stage_index_is_an_explicit_retrieval_error(self):
        self.card("patterns/current.md")
        self.write_contract(
            {"pressure": ["current"]}, {"current": "patterns/current.md"}
        )
        index = self.contract.with_name("pattern_index.md")
        cases = (
            None,
            "## 1. Kernel: Test\n",
            "## 1. Kernel: Test\n#### `current`\n#### `current`\n",
            "## 1. Unknown: Test\n#### `current`\n",
            "#### `current`\n",
            "## 1. Kernel: Test\n#### `current`\n- Priority: urgent\n",
            "## 1. Kernel: Test\n#### `current`\n- Priority: normal\n- Priority: high\n",
            "## 1. Kernel: Test\n#### `current`\n#### `unregistered`\n",
        )
        for content in cases:
            with self.subTest(content=content):
                if content is None:
                    index.unlink()
                else:
                    index.write_text(content)
                with self.assertRaisesRegex(
                    recommendations.RetrievalError, "pattern index"
                ):
                    self.query(["pressure"])

    def query(self, symptoms, exclude=None):
        return recommendations.retrieve(
            symptoms,
            contract_path=self.contract,
            patterns_dirs=[path for path in self.cards.iterdir() if path.is_dir()],
            exclude=exclude,
        )

    def test_retrieval_returns_current_pattern_id(self):
        path = self.card("patterns/dot_matmul_rewrite.md")
        self.write_contract(
            {"manual-matmul": ["dot-matmul-rewrite"]},
            {"dot-matmul-rewrite": "patterns/dot_matmul_rewrite.md"},
        )
        result = self.query(["manual-matmul"])

        entry = result[0]
        self.assertEqual(Path(entry["card"]), path)
        self.assertEqual(entry["matched_symptoms"], ["manual-matmul"])
        self.assertEqual(entry["pattern"], "dot-matmul-rewrite")

    def test_moved_technique_is_usable_in_an_edit_claim(self):
        path = self.card("techniques/tiling.md")
        self.write_contract(
            {"capacity": ["tile-footprint-fitting"]},
            {"tile-footprint-fitting": "techniques/tiling.md"},
        )
        result = self.query(["capacity"])

        self.assertEqual(Path(result[0]["card"]), path)
        source = (
            PLUGIN
            / "skills/triton-npu-optimize-state/scripts/state_manage/claim_contract.py"
        )
        spec = importlib.util.spec_from_file_location("claim_contract", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(
            module.claim_includes_optimize_knowledge_pattern(pattern_paths=[str(path)])
        )
        self.assertFalse(
            module.claim_includes_optimize_knowledge_pattern(
                pattern_paths=[
                    str(self.kb / "knowledge/ops/triton/guides/unrelated.md")
                ],
            )
        )

    def test_current_candidates_are_deduplicated_across_symptoms(self):
        self.card("patterns/fusion.md")
        self.card("patterns/visibility.md")
        self.write_contract(
            {"attention": ["fusion", "visibility"], "materialization": ["fusion"]},
            {"fusion": "patterns/fusion.md", "visibility": "patterns/visibility.md"},
        )
        result = self.query(["attention", "materialization"])

        entries = result
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["pattern"], "fusion")
        self.assertEqual(
            entries[0]["matched_symptoms"], ["attention", "materialization"]
        )
        excluded = self.query(["attention", "materialization"], exclude=["fusion"])

        self.assertEqual(
            [item["pattern"] for item in excluded],
            ["visibility"],
        )

    def test_exclusion_uses_the_current_id_without_old_aliases(self):
        self.card("patterns/dot_matmul_rewrite.md")
        self.write_contract(
            {"matmul": ["dot-matmul-rewrite"]},
            {"dot-matmul-rewrite": "patterns/dot_matmul_rewrite.md"},
        )
        for excluded, expected_count in (
            ("dot-matmul-rewrite", 0),
            ("classic-matmul", 1),
        ):
            with self.subTest(excluded=excluded):
                result = self.query(["matmul"], exclude=[excluded])

                self.assertEqual(len(result), expected_count)

    def test_unrouted_symptom_does_not_block_other_symptoms(self):
        self.card("patterns/current.md")
        self.write_contract(
            {"unrouted": [], "routed": ["current"]}, {"current": "patterns/current.md"}
        )
        result = self.query(["unrouted", "routed"])

        payload = {"results": result}
        self.assertEqual([item["pattern"] for item in payload["results"]], ["current"])
        self.assertEqual(self.query(["unrouted"]), [])

    def test_missing_declared_file_is_not_treated_as_unavailable(self):
        self.card("patterns/unrelated.md")
        self.write_contract(
            {"matmul": ["dot-matmul-rewrite"]},
            {"dot-matmul-rewrite": "patterns/missing.md"},
        )
        with self.assertRaisesRegex(
            recommendations.RetrievalError, "patterns/missing.md"
        ):
            self.query(["matmul"])

    def test_mapping_must_be_present_and_cannot_escape_card_directories(self):
        self.card("patterns/current.md")
        for paths in (
            {},
            {"current": "../secret.md"},
            {"current": "patterns/index.md"},
        ):
            with self.subTest(paths=paths):
                self.write_contract({"symptom": ["current"]}, paths)
                with self.assertRaises(recommendations.RetrievalError):
                    recommendations.load_contract(self.contract)

    def test_unknown_and_invalid_symptoms_keep_existing_contract(self):
        self.card("patterns/current.md")
        self.write_contract(
            {"symptom": ["current"]}, {"current": "patterns/current.md"}
        )
        result = self.query(["unknown"])

        self.assertEqual(result, [])
        with self.assertRaisesRegex(
            recommendations.RetrievalError, "unknown symptom ID"
        ):
            self.query(["not-registered"])


class PublishedCatalogTests(unittest.TestCase):
    references = PLUGIN / "skills/triton-npu-optimize-knowledge/references"

    @unittest.skipUnless(
        os.environ.get("HELIX_PATTERN_TEST_ROOT")
        and os.environ.get("CANNBOT_KNOWLEDGE_TEST_ROOT"),
        "fixed Helix snapshot and external knowledge checkout not supplied",
    )
    def test_catalog_and_recommendations_match_fixed_helix_snapshot(self):
        from itertools import combinations

        source_root = Path(os.environ["HELIX_PATTERN_TEST_ROOT"])
        source = source_root / "skills/triton/triton-npu-optimize-knowledge/references"
        knowledge = Path(os.environ["CANNBOT_KNOWLEDGE_TEST_ROOT"])
        cards = knowledge / "knowledge/ops/triton/optimizations"
        contract = json.loads((self.references / "symptom-contract.json").read_text())
        paths = contract.pop("pattern_paths")
        self.assertEqual(
            contract, json.loads((source / "symptom-contract.json").read_text())
        )
        self.assertEqual(
            set(paths), {file.stem for file in (source / "patterns").glob("*.md")}
        )
        self.assertTrue(all(path.startswith("patterns/") for path in paths.values()))
        self.assert_card_bodies_match(source, cards, paths)

        modules = []
        for name, script in (
            ("plugin_retrieve", SCRIPT),
            (
                "helix_retrieve",
                source_root
                / "skills/common/ascend-npu-optimize-state/optimize-extensions/scripts/symptom_recommendations.py",
            ),
        ):
            spec = importlib.util.spec_from_file_location(name, script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules.append(module)
        plugin, helix = modules
        ids = [entry["id"] for entry in contract["symptoms"]]
        cases = [[identifier] for identifier in ids] + [
            list(pair) for pair in combinations(ids, 2)
        ]
        for symptoms in cases:
            with self.subTest(symptoms=symptoms):
                self.assert_recommendations_match(
                    plugin, helix, source, cards, symptoms
                )

    def assert_card_bodies_match(self, source, cards, paths):
        for identifier, relative in paths.items():
            with self.subTest(pattern=identifier):
                original = (
                    (source / "patterns" / (identifier + ".md"))
                    .read_text()
                    .split("---", 2)[2]
                )

                def rewrite(match):
                    target = Path(match[1]).stem
                    if target == "tiling":
                        target = "tile-footprint-fitting"
                    return "](" + Path(paths[target]).name + ")"

                expected = re.sub(r"\]\(([^)]+\.md)\)", rewrite, original).strip()
                actual = (cards / relative).read_text().split("---", 2)[2]
                actual = actual.split("\n## Related Knowledge\n", 1)[0].strip()
                self.assertEqual(actual, expected)

    def assert_recommendations_match(self, plugin, helix, source, cards, symptoms):
        expected = helix.retrieve(
            symptoms,
            contract_path=source / "symptom-contract.json",
            patterns_dir=source / "patterns",
        )
        actual = plugin.retrieve(
            symptoms,
            contract_path=self.references / "symptom-contract.json",
            patterns_dirs=[cards / "patterns"],
        )
        self.assertEqual(
            [x["pattern"] for x in actual], [x["pattern"] for x in expected]
        )
        for a, e in zip(actual, expected):
            self.assertEqual(a["summary"], e["summary"])
            self.assertEqual(a["matched_symptoms"], e["matched_symptoms"])
            # Helix unwraps prose lines; the plugin retains their Markdown layout.
            self.assertEqual(
                " ".join("\n\n".join(a["use_when"]).split()),
                " ".join(e["use_when"].split()),
            )
        excluded = [x["pattern"] for x in expected]
        expected_next = helix.retrieve(
            symptoms,
            contract_path=source / "symptom-contract.json",
            patterns_dir=source / "patterns",
            exclude=excluded,
        )
        actual_next = plugin.retrieve(
            symptoms,
            contract_path=self.references / "symptom-contract.json",
            patterns_dirs=[cards / "patterns"],
            exclude=excluded,
        )
        self.assertEqual(
            [x["pattern"] for x in actual_next],
            [x["pattern"] for x in expected_next],
        )

    def test_stage_index_uses_the_same_paths_as_the_contract(self):
        contract = json.loads((self.references / "symptom-contract.json").read_text())
        blocks = (self.references / "pattern_index.md").read_text().split("#### `")[1:]
        self.assertEqual(
            {block.split("`")[0] for block in blocks}, set(contract["pattern_paths"])
        )
        for block in blocks:
            identifier = block.split("`")[0]
            actual = re.findall(
                r"Source: cannbot-knowledge `knowledge/ops/triton/optimizations/([^`]+)`",
                block,
            )
            self.assertEqual(
                actual, [contract["pattern_paths"][identifier]], identifier
            )

    @unittest.skipUnless(
        os.environ.get("CANNBOT_KNOWLEDGE_TEST_ROOT"),
        "external knowledge checkout not supplied",
    )
    def test_all_published_symptoms_against_real_knowledge_checkout(self):
        contract_path = self.references / "symptom-contract.json"
        contract = json.loads(contract_path.read_text())
        for symptom in contract["symptoms"]:
            with self.subTest(symptom=symptom["id"]):
                knowledge = Path(os.environ["CANNBOT_KNOWLEDGE_TEST_ROOT"])
                results = recommendations.retrieve(
                    [symptom["id"]],
                    contract_path=contract_path,
                    patterns_dirs=[
                        knowledge / "knowledge/ops/triton/optimizations/patterns"
                    ],
                )
                expected = {
                    contract["pattern_paths"][identifier]
                    for identifier in symptom["candidate_patterns"]
                }
                self.assertEqual(bool(results), bool(expected))
                for entry in results:
                    self.assertIn(entry["pattern"], symptom["candidate_patterns"])
                    path = Path(entry["card"])
                    self.assertTrue(path.is_file())
                    self.assertIn(path.parent.name + "/" + path.name, expected)


if __name__ == "__main__":
    unittest.main()
