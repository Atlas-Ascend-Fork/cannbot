# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------


"""Exercise automatic recommendations with staged routing and external cards."""

import importlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import chdir, redirect_stderr
from pathlib import Path
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1]
STATE_SCRIPTS = PLUGIN / "skills/triton-npu-optimize-state/scripts"
sys.path.insert(0, str(STATE_SCRIPTS))
submission = importlib.import_module("state_manage.submit_deep_analysis")
sys.path.pop(0)


class DeepAnalysisPatternTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.state = self.root / ".helix/state.json"
        self.state.parent.mkdir()
        self.state.write_text(json.dumps({"language": "triton"}))
        self.round = self.root / "opt-round-2"
        self.round.mkdir()
        self.operator = self.round / "opt_example.py"
        self.operator.write_text("# Test candidate.\n")
        (self.round / "perf-analysis.md").write_text("Measured capacity pressure.\n")
        self.staged = self.root / ".agents/skills"
        self.contract = (
            self.staged
            / "triton-npu-optimize-knowledge/references/symptom-contract.json"
        )
        self.contract.parent.mkdir(parents=True)
        self.contract.write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "max_submitted": 5,
                    "unknown_id": "unknown",
                    "pattern_paths": {"tile-footprint-fitting": "techniques/tiling.md"},
                    "symptoms": [
                        {
                            "id": "tile-footprint-too-large",
                            "summary": "Capacity pressure.",
                            "evidence_hint": "Measured capacity pressure.",
                            "common_non_matches": [],
                            "candidate_patterns": ["tile-footprint-fitting"],
                        }
                    ],
                }
            )
        )
        self.contract.with_name("pattern_index.md").write_text(
            "## 2. Kernel: Algorithm, Dataflow, And Storage\n\n#### `tile-footprint-fitting`\n- Priority: normal\n"
        )
        self.kb = self.root / ".cannbot/dependencies/triton-optimizer/cannbot-knowledge"
        self.card = self.kb / "knowledge/ops/triton/optimizations/techniques/tiling.md"
        self.card.parent.mkdir(parents=True)
        self.card.write_text(
            "## Summary\n\nFit the tile.\n\n## Use When\n\n- Capacity is exceeded.\n"
        )
        environment = patch.dict(os.environ, {"HELIX_OPTIMIZE_RECOMMEND_PATTERNS": "1"})
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("CANNBOT_KNOWLEDGE_ROOT", None)

    def gather(self, *, symptoms=None, payload=None):
        from state_manage.submit_deep_analysis import _gather_pattern_recommendations

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            history, recommendations = _gather_pattern_recommendations(
                self.state,
                payload or {},
                symptoms or ["tile-footprint-too-large"],
                self.round,
            )
        return history, recommendations, stderr.getvalue()

    def test_external_card_is_recommended_without_bundled_patterns(self):
        self.assertFalse((self.contract.parent / "patterns").exists())
        _, recommendations, warning = self.gather()
        self.assertEqual(
            [entry["id"] for entry in recommendations], ["tile-footprint-fitting"]
        )
        self.assertEqual(Path(recommendations[0]["path"]), self.card)
        self.assertEqual(
            recommendations[0]["matched_symptoms"], ["tile-footprint-too-large"]
        )
        self.assertEqual(warning, "")

    def test_symlinked_knowledge_uses_target_workspace_from_another_directory(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        outside = Path(directory.name).resolve()
        skill = self.contract.parent.parent
        source = outside / "plugin/skills" / skill.name
        source.parent.mkdir(parents=True)
        shutil.move(skill, source)
        skill.symlink_to(
            os.path.relpath(source, skill.parent), target_is_directory=True
        )
        caller = outside / "caller"
        caller.mkdir()
        for competing_knowledge in (False, True):
            with self.subTest(competing_knowledge=competing_knowledge):
                if competing_knowledge:
                    shutil.copytree(self.kb, caller / self.kb.relative_to(self.root))
                with chdir(caller):
                    _, recommendations, warning = self.gather()
                self.assertEqual(warning, "")
                self.assertEqual(
                    [entry["id"] for entry in recommendations],
                    ["tile-footprint-fitting"],
                )
                self.assertEqual(Path(recommendations[0]["path"]), self.card)

    def test_current_ids_from_state_and_prior_rounds_are_excluded(self):
        for source in ("state", "prior-round"):
            with self.subTest(source=source):
                record = {
                    "id": "tile-footprint-fitting",
                    "matched_symptoms": ["tile-footprint-too-large"],
                }
                payload = {"pattern_recommendations": {record["id"]: record}}
                if source == "prior-round":
                    previous = self.root / "opt-round-1"
                    previous.mkdir()
                    (previous / "deep-analysis.json").write_text(
                        json.dumps({"recommendations": [record]})
                    )
                    payload = {}
                history, recommendations, warning = self.gather(payload=payload)
                self.assertIn(record["id"], history)
                self.assertEqual(recommendations, [])
                self.assertEqual(warning, "")

    def test_missing_contract_is_silent_even_when_old_patterns_directory_exists(self):
        self.contract.unlink()
        (self.contract.parent / "patterns").mkdir()
        _, recommendations, warning = self.gather()
        self.assertEqual(recommendations, [])
        self.assertEqual(warning, "")

    def test_recommendations_do_not_require_a_standalone_retrieval_skill(self):
        self.assertFalse((self.staged / "triton-npu-retrieve-patterns").exists())
        self.assertFalse((PLUGIN / "skills/triton-npu-retrieve-patterns").exists())
        _, recommendations, warning = self.gather()
        self.assertEqual(
            [item["id"] for item in recommendations], ["tile-footprint-fitting"]
        )
        self.assertEqual(warning, "")

    def test_missing_knowledge_silently_returns_no_recommendations(self):
        shutil.move(self.kb, self.root / "saved-knowledge")
        _, recommendations, warning = self.gather()
        self.assertEqual(recommendations, [])
        self.assertEqual(warning, "")

    def test_missing_card_silently_returns_no_recommendations(self):
        self.card.unlink()
        _, recommendations, warning = self.gather()
        self.assertEqual(recommendations, [])
        self.assertEqual(warning, "")

    def test_missing_stage_index_silently_skips_recommendations(self):
        self.contract.with_name("pattern_index.md").unlink()
        _, recommendations, warning = self.gather()
        self.assertEqual(recommendations, [])
        self.assertEqual(warning, "")

    @unittest.skipUnless(
        os.environ.get("CANNBOT_KNOWLEDGE_TEST_ROOT"),
        "external knowledge checkout not supplied",
    )
    def test_automatic_recommendations_against_real_knowledge_checkout(self):
        shutil.copyfile(
            PLUGIN
            / "skills/triton-npu-optimize-knowledge/references/symptom-contract.json",
            self.contract,
        )
        shutil.copyfile(
            PLUGIN / "skills/triton-npu-optimize-knowledge/references/pattern_index.md",
            self.contract.with_name("pattern_index.md"),
        )
        with patch.dict(
            os.environ,
            {"CANNBOT_KNOWLEDGE_ROOT": os.environ["CANNBOT_KNOWLEDGE_TEST_ROOT"]},
        ):
            _, recommendations, warning = self.gather(
                symptoms=["on-chip-capacity-exceeded"]
            )
        self.assertIn(
            "tile-footprint-fitting", [entry["id"] for entry in recommendations]
        )
        self.assertTrue(all(Path(entry["path"]).is_file() for entry in recommendations))
        self.assertEqual(warning, "")

    def test_unknown_is_a_silent_empty_result(self):
        _, recommendations, warning = self.gather(symptoms=["unknown"])
        self.assertEqual(recommendations, [])
        self.assertEqual(warning, "")

    def test_disabled_recommendations_do_not_attempt_discovery(self):
        os.environ.pop("HELIX_OPTIMIZE_RECOMMEND_PATTERNS")
        with patch.object(
            submission, "knowledge_dir", side_effect=AssertionError("unexpected lookup")
        ):
            _, recommendations, warning = self.gather()
        self.assertEqual(recommendations, [])
        self.assertEqual(warning, "")

    def test_internal_errors_keep_subprocess_failure_isolation(self):
        for error in (
            OSError("unreadable card"),
            ValueError("bad card"),
            RuntimeError("unexpected matcher error"),
        ):
            with self.subTest(error=error):
                with patch.object(
                    submission.pattern_recommendations, "recommend", side_effect=error
                ):
                    _, recommendations, warning = self.gather()
                self.assertEqual(recommendations, [])
                self.assertEqual(warning, "")

    def test_missing_target_knowledge_never_uses_callers_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            caller = Path(directory).resolve()
            shutil.move(self.kb, caller / self.kb.relative_to(self.root))
            with chdir(caller):
                _, recommendations, warning = self.gather()
            self.assertEqual(recommendations, [])
            self.assertEqual(warning, "")


class DeepManifestTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.artifacts = self.root / "profile/case"
        self.artifacts.mkdir(parents=True)
        self.profiler = self.artifacts / "mindstudio_profiler_output/op_statistic_0.csv"
        self.profiler.parent.mkdir()
        self.profiler.write_text("fixture\n")
        self.manifest = self.artifacts / "manifest.json"
        self.data = {
            "case_id": "case",
            "operator_file": str(self.root / "operator.py"),
            "operator_sha256": "operator-hash",
            "bench_file": str(self.root / "bench.py"),
            "bench_sha256": "bench-hash",
            "artifact_dir": str(self.artifacts),
            "remote": False,
        }
        self.arguments = {
            "artifact_root": self.root / "profile",
            "expected_kind": "profile",
            "operator_path": self.root / "operator.py",
            "operator_sha256": "operator-hash",
            "bench_file": self.root / "bench.py",
            "bench_sha256": "bench-hash",
        }

    def validate(self, data):
        from state_manage.submit_deep_analysis import _validate_deep_manifest

        self.manifest.write_text(json.dumps(data))
        return _validate_deep_manifest(self.manifest, **self.arguments)

    def test_valid_profile_preserves_identity(self):
        self.assertEqual(
            self.validate(self.data),
            {"case_id": "case", "artifact_dir": str(self.artifacts), "remote": False},
        )

    def test_malformed_manifest_and_required_fields_are_rejected(self):
        from state_manage.submit_deep_analysis import _validate_deep_manifest

        self.manifest.write_text("not JSON")
        with self.assertRaisesRegex(ValueError, "invalid profile manifest"):
            _validate_deep_manifest(self.manifest, **self.arguments)
        for data, message in (
            ([], "must be a JSON object"),
            ({**self.data, "case_id": ""}, "missing required identity fields"),
            ({**self.data, "remote": "false"}, "remote must be a boolean"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self.validate(data)

    def test_artifact_ownership_and_profiler_output_are_required(self):
        for directory, message in (
            (self.root, "outside the current round"),
            (self.artifacts.parent, "does not match its parent"),
        ):
            with self.subTest(directory=directory):
                with self.assertRaisesRegex(ValueError, message):
                    self.validate({**self.data, "artifact_dir": str(directory)})
        self.profiler.unlink()
        with self.assertRaisesRegex(ValueError, "missing profiler output"):
            self.validate(self.data)

    def test_mismatched_operator_and_benchmark_are_rejected(self):
        for field in ("operator_file", "operator_sha256", "bench_file", "bench_sha256"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "does not match"):
                    self.validate({**self.data, field: "mismatch"})


if __name__ == "__main__":
    unittest.main()
