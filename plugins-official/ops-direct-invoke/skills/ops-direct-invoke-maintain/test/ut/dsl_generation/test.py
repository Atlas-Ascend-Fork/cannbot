# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------
import copy
import csv
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).absolute().parents[1]))
import support
from support import SCRIPTS, run_tests

SCRIPT = SCRIPTS / "assemble_cannbotdsl_design.py"
spec = importlib.util.spec_from_file_location("assemble_cannbotdsl_design", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

contract_spec = importlib.util.spec_from_file_location(
    "validate_unit_contracts", SCRIPTS / "validate_unit_contracts.py"
)
contracts = importlib.util.module_from_spec(contract_spec)
contract_spec.loader.exec_module(contracts)


def unit_fixture(uid, deps=(), files=()):
    return {
        "unit_id": uid,
        "kind": "feature_increment",
        "depends_on": list(deps),
        "scope": {"source_files": list(files)},
        "verification_obligations": [{"id": f"VO-{uid}", "kind": "numerical"}],
    }


class UnitContractTests(unittest.TestCase):
    def test_transitive_capability_and_evidence_references(self):
        native = {
            "U01": unit_fixture("U01"),
            "U02": unit_fixture("U02", ["U01"]),
            "U03": unit_fixture("U03", ["U02"]),
        }
        native["U01"]["provides"] = ["base"]
        native["U03"].update(
            requires=["base"],
            dependency_reasons={"U02": "increment"},
            design_constraints=[
                {
                    "source": "DESIGN",
                    "commitment": "base contract",
                    "obligation_ids": ["VO-U01"],
                }
            ],
        )
        self.assertEqual(contracts.validate_units(native), ["U01", "U02", "U03"])
        native["U03"]["requires"] = ["unprovided"]
        with self.assertRaisesRegex(ValueError, "without dependency provider"):
            contracts.validate_units(native)

    def test_unknown_dependencies_and_cycles_rejected(self):
        for native in (
            {"U01": unit_fixture("U01", ["U02"])},
            {"U01": unit_fixture("U01", ["U02"]), "U02": unit_fixture("U02", ["U01"])},
        ):
            with (
                self.subTest(native=native),
                self.assertRaisesRegex(ValueError, "unknown|cycle"),
            ):
                contracts.validate_units(native)

    def test_unbound_design_rejected_and_review_contract_accepted(self):
        unit = unit_fixture("U01")
        unit["design_constraints"] = [
            {"source": "DESIGN", "commitment": "execution domain"}
        ]
        with self.assertRaisesRegex(ValueError, "requires executable obligations"):
            contracts.validate_units({"U01": unit})
        unit["design_constraints"][0]["review_evidence"] = [
            {
                "artifact": "compiled kernel",
                "check": "execution domain",
                "pass_criteria": "declared domain used",
            }
        ]
        self.assertEqual(contracts.validate_units({"U01": unit}), ["U01"])

    def test_independent_unit_cannot_supply_evidence_reference(self):
        native = {uid: unit_fixture(uid) for uid in ("U01", "U02")}
        native["U02"]["design_constraints"] = [
            {"source": "DESIGN", "commitment": "contract", "obligation_ids": ["VO-U01"]}
        ]
        with self.assertRaisesRegex(
            ValueError, "invalid design_constraints obligation references"
        ):
            contracts.validate_units(native)

    def test_feasibility_checks_need_actionable_evidence(self):
        unit = unit_fixture("U01")
        check = {
            "design_source": "DESIGN",
            "question": "combined data path",
            "before_step": "first compute",
            "on_failure": "return to DESIGN",
        }
        unit["implementation"] = {"feasibility_checks": [check]}
        with self.assertRaisesRegex(ValueError, "requires executable obligations"):
            contracts.validate_units({"U01": unit})
        check["obligation_ids"] = ["VO-U01"]
        self.assertEqual(contracts.validate_units({"U01": unit}), ["U01"])
        check.pop("before_step")
        with self.assertRaisesRegex(ValueError, "actionable contract fields"):
            contracts.validate_units({"U01": unit})

    def test_unit_kind_requires_matching_obligation(self):
        unit = unit_fixture("U01")
        unit["kind"] = "minimal_operator"
        unit["verification_obligations"][0]["kind"] = "semantic"
        with self.assertRaisesRegex(ValueError, "lacks numerical"):
            contracts.validate_units({"U01": unit})

    def test_pipeline_uses_review_evidence_and_executable_behavior(self):
        unit = unit_fixture("U01")
        unit["kind"] = "pipeline_framework"
        with self.assertRaisesRegex(ValueError, "requires structural review_evidence"):
            contracts.validate_units({"U01": unit})
        unit["design_constraints"] = [
            {
                "source": "Kernel.md#pipeline",
                "commitment": "producer/consumer ordering",
                "review_evidence": [
                    {
                        "artifact": "compiled kernel and device timeline",
                        "check": "actual producer/consumer dependency",
                        "pass_criteria": "matches declared synchronization",
                    }
                ],
            }
        ]
        self.assertEqual(contracts.validate_units({"U01": unit}), ["U01"])
        without_behavior = copy.deepcopy(unit)
        without_behavior["verification_obligations"] = []
        with self.assertRaisesRegex(ValueError, "verification_obligations must be a nonempty list"):
            contracts.validate_units({"U01": without_behavior})
        unit["design_constraints"][0]["review_evidence"][0].pop("check")
        with self.assertRaisesRegex(ValueError, "artifact/check/pass_criteria"):
            contracts.validate_units({"U01": unit})

    def test_structural_obligation_requires_explicit_migration(self):
        unit = unit_fixture("U01")
        unit["verification_obligations"][0]["kind"] = "structural"
        with self.assertRaisesRegex(ValueError, "U01/VO-U01.*migrate.*review_evidence"):
            contracts.validate_units({"U01": unit})

    def test_malformed_declarations_report_contract_errors(self):
        original = unit_fixture("U01")
        for key, invalid in (
            ("depends_on", "U02"),
            ("requires", [[], "bad"]),
            ("verification_obligations", ["bad"]),
            ("verification_obligations", [{"id": [], "kind": "numerical"}]),
            ("verification_obligations", [{"id": "VO", "kind": []}]),
        ):
            unit = copy.deepcopy(original)
            unit[key] = invalid
            with self.subTest(key=key, invalid=invalid), self.assertRaises(ValueError):
                contracts.validate_units({"U01": unit})

    def test_duplicate_yaml_keys_cannot_hide_a_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "U01.yaml").write_text(
                "unit:\n  unit_id: U01\n  requires: [missing]\n  requires: []\n"
            )
            with self.assertRaisesRegex(ValueError, "duplicate YAML key"):
                contracts.load_units(tmp)


class DesignAssemblyTests(unittest.TestCase):
    def test_assembles_linked_topics_and_branches(self):
        with tempfile.TemporaryDirectory() as tmp:
            design = Path(tmp)
            (design / "INDEX.md").write_text(
                "# Index\n[Overview](Overview.md)\n[B0](branches/DESIGN-BRANCH-B0.md)\n",
                encoding="utf-8",
            )
            (design / "Overview.md").write_text("# Overview\nMath\n", encoding="utf-8")
            (design / "branches").mkdir()
            (design / "branches/DESIGN-BRANCH-B0.md").write_text(
                "# B0\nPath\n", encoding="utf-8"
            )
            result = module.assemble(design)
            self.assertIn("design source: Overview.md", result)
            self.assertIn("design source: branches/DESIGN-BRANCH-B0.md", result)
            self.assertLess(result.index("Math"), result.index("Path"))
            self.assertNotIn("design source: INDEX.md", result)
            self.assertIn("## Overview", result)

    def test_index_sections_order_and_code_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            design = Path(tmp)
            (design / "INDEX.md").write_text(
                "# Operator\nNavigation only\n## Layout\n```text\n"
                "[example](unused.md)\n```\n## Execution\n"
                "[B1](branches/DESIGN-BRANCH-B1.md)\n"
                "[Overview](Overview.md)\n"
                "## Appendix\n[B0](branches/DESIGN-BRANCH-B0.md)\n",
                encoding="utf-8",
            )
            code = "```python\n# Keep this comment\n```\n~~~text\n## Keep this too\n~~~"
            (design / "Overview.md").write_text(
                "# Overview\n## Detail\n" + code, encoding="utf-8"
            )
            (design / "branches").mkdir()
            for name in ("B0", "B1"):
                (design / f"branches/DESIGN-BRANCH-{name}.md").write_text(
                    f"# {name}\n", encoding="utf-8"
                )
            result = module.assemble(design)
            self.assertNotIn("Navigation only", result)
            self.assertNotIn("## Layout", result)
            self.assertNotIn("design source: INDEX.md", result)
            self.assertIn("### Overview\n#### Detail", result)
            self.assertIn(code, result)
            headings = [
                line
                for line, in_code in module.markdown_lines(result)
                if not in_code and line.startswith("#")
            ]
            self.assertEqual(
                headings,
                [
                    "# Operator",
                    "## Execution",
                    "### B1",
                    "### Overview",
                    "#### Detail",
                    "## Appendix",
                    "### B0",
                ],
            )

    def test_reference_documents_are_not_assembled(self):
        with tempfile.TemporaryDirectory() as tmp:
            design = Path(tmp)
            (design / "branches").mkdir()
            (design / "INDEX.md").write_text(
                "# add 设计索引\n## 1. 设计\n[Overview](Overview.md)\n"
                "[P0](branches/DESIGN-BRANCH-P0.md)\n## 参考资料\n"
                "[说明](Notes.md)\n[环境](../../environment/notes.md)\n",
                encoding="utf-8",
            )
            for name in ("Overview.md", "branches/DESIGN-BRANCH-P0.md"):
                (design / name).write_text("# Topic\nbody", encoding="utf-8")
            (design / "REQUIREMENTS.md").write_text(
                "requirements sentinel", encoding="utf-8"
            )
            (design / "Notes.md").write_text("reference sentinel", encoding="utf-8")
            result = module.assemble(design)
            self.assertTrue(result.startswith("# add 设计\n"))
            self.assertNotIn("sentinel", result)
            self.assertNotIn("## 参考资料", result)
            self.assertNotIn("design source: INDEX.md", result)

    def test_unlisted_branch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            design = Path(tmp)
            (design / "INDEX.md").write_text(
                "[Overview](Overview.md)\n", encoding="utf-8"
            )
            (design / "Overview.md").write_text("# Overview\n", encoding="utf-8")
            (design / "branches").mkdir()
            (design / "branches/DESIGN-BRANCH-B0.md").write_text(
                "# B0\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "branch links do not match"):
                module.assemble(design)

    def test_missing_linked_topic_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            design = Path(tmp)
            (design / "INDEX.md").write_text(
                "[Overview](Overview.md)\n[B0](branches/DESIGN-BRANCH-B0.md)\n",
                encoding="utf-8",
            )
            (design / "branches").mkdir()
            (design / "branches/DESIGN-BRANCH-B0.md").write_text(
                "# B0\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "missing .*Overview.md"):
                module.assemble(design)


class UnitSubgraphTests(unittest.TestCase):
    def generate_graph(self, native, work):
        (work / "design/doc").mkdir(parents=True)
        (work / "design/units").mkdir()
        (work / "operators/add/test").mkdir(parents=True)
        (work / "design/doc/spec.yaml").write_text("op: {name: add}\n")
        (work / "design/doc/DESIGN.md").write_text("# add\n")
        for uid, unit in native.items():
            (work / f"design/units/{uid}.yaml").write_text(
                yaml.safe_dump({"unit": unit})
            )
        with (work / "operators/add/test/testcase.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["sheet", "case_id", "unit_id", "status", "obligation_ids"],
            )
            writer.writeheader()
            for uid in native:
                writer.writerow(
                    {
                        "sheet": "tdd",
                        "case_id": f"TD-{uid.lower()}-main",
                        "unit_id": uid.lower(),
                        "status": "active",
                        "obligation_ids": f"VO-{uid}",
                    }
                )
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "build_implementation_subgraph.py"),
                "--output-dir",
                str(work),
                "--harness-script",
                str(support.HARNESS_SKILL / "scripts/get_task.py"),
            ],
            capture_output=True,
            text=True,
        )
        return result

    def test_conflict_order_follows_dependencies_instead_of_file_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            native = {
                "U01": unit_fixture("U01", ["U02"], ["operators/add/add.py"]),
                "U02": unit_fixture("U02", files=["operators/add/add.py"]),
            }
            result = self.generate_graph(native, work)
            self.assertEqual(result.returncode, 0, result.stderr)
            nodes = yaml.safe_load(
                (work / ".workflow/implementation-tasks.yaml").read_text()
            )["nodes"]
            self.assertEqual(
                [node["id"] for node in nodes[:2]], ["implement-u02", "implement-u01"]
            )
            self.assertEqual(nodes[0]["depends_on"], [])
            self.assertEqual(nodes[1]["depends_on"], ["implement-u02"])

    def test_disjoint_writes_parallel_and_unknown_writes_serial(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            native = {
                "U01": unit_fixture("U01", files=["operators/add/a.py"]),
                "U02": unit_fixture("U02", files=["operators/add/b.py"]),
                "U03": unit_fixture("U03"),
            }
            result = self.generate_graph(native, work)
            self.assertEqual(result.returncode, 0, result.stderr)
            nodes = yaml.safe_load(
                (work / ".workflow/implementation-tasks.yaml").read_text()
            )["nodes"]
            self.assertEqual(nodes[0]["depends_on"], [])
            self.assertEqual(nodes[1]["depends_on"], [])
            self.assertEqual(nodes[2]["depends_on"], ["implement-u01", "implement-u02"])

    def test_path_aliases_still_serialize_shared_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            native = {
                "U01": unit_fixture("U01", files=["operators/add/add.py"]),
                "U02": unit_fixture(
                    "U02", files=[str(work / "operators/add/../add/add.py")]
                ),
            }
            result = self.generate_graph(native, work)
            self.assertEqual(result.returncode, 0, result.stderr)
            nodes = yaml.safe_load(
                (work / ".workflow/implementation-tasks.yaml").read_text()
            )["nodes"]
            self.assertEqual(nodes[1]["depends_on"], ["implement-u01"])

    def test_invalid_planning_contract_blocked_before_scheduling(self):
        for invalid in ("capability", "evidence"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                unit = unit_fixture("U01")
                if invalid == "capability":
                    unit["requires"] = ["missing"]
                else:
                    unit["design_constraints"] = [
                        {"source": "DESIGN", "commitment": "execution domain"}
                    ]
                result = self.generate_graph({"U01": unit}, work)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(
                    (work / ".workflow/implementation-tasks.yaml").exists()
                )

    def test_native_unit_without_hash_generates_implementation_graph(self):
        self.check_unit_graph()

    def test_excluded_cases_do_not_block_active_obligation_coverage(self):
        self.check_unit_graph(excluded=True)

    def test_excluded_cases_cannot_replace_active_obligation_coverage(self):
        self.check_unit_graph(excluded=True, active=False)

    def check_unit_graph(self, excluded=False, active=True):
        script = SCRIPTS / "build_implementation_subgraph.py"
        harness = support.HARNESS_SKILL / "scripts/get_task.py"
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "design/doc").mkdir(parents=True)
            (work / "design/units").mkdir()
            (work / "operators/add/test").mkdir(parents=True)
            (work / "design/doc/spec.yaml").write_text(
                "op: {name: add}\n", encoding="utf-8"
            )
            (work / "design/doc/DESIGN.md").write_text("# add\n", encoding="utf-8")
            unit = {
                "unit": {
                    "unit_id": "U01",
                    "kind": "minimal_operator",
                    "design_sources": [{"file": "Kernel.md", "section": "Compute"}],
                    "depends_on": [],
                    "scope": {"source_files": ["operators/add/add.py"]},
                    "verification_obligations": [{"id": "VO-U01", "kind": "numerical"}],
                }
            }
            (work / "design/units/U01.yaml").write_text(
                yaml.safe_dump(unit), encoding="utf-8"
            )
            with (work / "operators/add/test/testcase.csv").open(
                "w", encoding="utf-8", newline=""
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "sheet",
                        "case_id",
                        "unit_id",
                        "status",
                        "obligation_ids",
                        "exclude_reason",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "sheet": "tdd",
                        "case_id": "TD-u01-main",
                        "unit_id": "u01",
                        "status": "active" if active else "excluded",
                        "obligation_ids": "VO-U01",
                        "exclude_reason": "" if active else "fixture exclusion",
                    }
                )
                if excluded:
                    writer.writerow(
                        {
                            "sheet": "tdd",
                            "case_id": "TD-u01-excluded",
                            "unit_id": "u01",
                            "status": "excluded",
                            "obligation_ids": "VO-U01",
                            "exclude_reason": "fixture exclusion",
                        }
                    )
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--output-dir",
                    str(work),
                    "--harness-script",
                    str(harness),
                ],
                capture_output=True,
                text=True,
            )
            if not active:
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(
                    (work / ".workflow/implementation-tasks.yaml").exists()
                )
                return
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(
                "TD-u01-excluded",
                (work / ".workflow/implementation-tasks.yaml").read_text(),
            )
            graph = yaml.safe_load(
                (work / ".workflow/implementation-tasks.yaml").read_text(
                    encoding="utf-8"
                )
            )
            implementation = graph["nodes"][0]
            self.assertEqual(implementation["id"], "implement-u01")
            self.assertIn("TD-u01-main", "\n".join(implementation["approach"]))
            self.assertIn(
                "design/units/U01.yaml", "\n".join(implementation["approach"])
            )
            self.assertNotIn("<op>", yaml.safe_dump(graph))
            fix = next(
                node for node in graph["nodes"] if node["id"] == "implementation-fix"
            )
            self.assertIn("implement-u01", fix["depends_on"])


if __name__ == "__main__":
    run_tests()
