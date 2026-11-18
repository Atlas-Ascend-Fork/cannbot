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
"""CCU artifact gate, sharing role/identity checks with the AICPU gate.

The Skill owns launch ABI, synchronization and arithmetic checks; this adapter
binds their declarations and source inventory to the frozen design. It does not
parse C++ or run hardware. Rebind modes only report owner work and stale bindings.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

sys.dont_write_bytecode = True

BASE = importlib.import_module("validate_aicpu_artifacts")


CCU_FILES = {"source-report.json", "launch-contract.json"}
SYNC_FILE = "sync-contract.json"
SOURCE_REPORT_RE = re.compile(r"source-report(?:-r[1-9][0-9]*)?\.json")
KNOWLEDGE_BASELINE = "knowledge-baseline.json"


class Validator(BASE.Validator):
    def __init__(self, task_dir: Path, skill_dir: Path):
        super().__init__(task_dir, engine="CCU")
        self.skill_dir = skill_dir.resolve()
        self.artifacts = {
            name: replace(spec, template=spec.template.replace("aicpu-", "ccu-"))
            for name, spec in BASE.ARTIFACTS.items()
        }
        self.artifacts["DESIGN"] = replace(
            self.artifacts["DESIGN"], template="ccu-design-template.md"
        )
        self.task_owners = {
            role: set(paths) for role, paths in BASE.TASK_OWNERS.items()
        }
        self.task_owners["hccl-architect"].update(CCU_FILES)
        self.task_owners["hccl-architect"].add(SYNC_FILE)
        self.task_owners["hccl-architect"].add("checker-plan.json")
        self.task_owners["hccl-architect"].add(KNOWLEDGE_BASELINE)
        self.knowledge_baseline = None
        self.baseline_blocked = False
        self.call_requirements = dict(BASE.CALL_REQUIREMENTS)
        role, outputs = self.call_requirements["DESIGN_READY"]
        self.call_requirements["DESIGN_READY"] = (role, outputs | CCU_FILES)

    def rebind_graph(self):
        artifacts, dependencies = super().rebind_graph()
        artifacts = dict(artifacts)
        dependencies = {name: dict(fields) for name, fields in dependencies.items()}
        design = self._design_header()
        files = {
            "SOURCE_REPORT": (
                self._source_report_file(design) or "source-report.json",
                "source_report_sha256",
            ),
            "LAUNCH_CONTRACT": ("launch-contract.json", "launch_contract_sha256"),
        }
        if (
            self.index.get("ccu_contract_version", 1) in (2, 3)
            or "sync_contract_sha256" in design
        ):
            files["SYNC_CONTRACT"] = (SYNC_FILE, "sync_contract_sha256")
        if (
            "knowledge_baseline_sha256" in design
            or (self.task_dir / KNOWLEDGE_BASELINE).exists()
        ):
            files["KNOWLEDGE_BASELINE"] = (
                KNOWLEDGE_BASELINE,
                "knowledge_baseline_sha256",
            )
            dependencies["SOURCE_REPORT"] = {"baseline_sha256": "KNOWLEDGE_BASELINE"}
        dependencies.setdefault("DESIGN", {}).update(
            {field: name for name, (_, field) in files.items()}
        )
        for name, (filename, _) in files.items():
            artifacts[name] = replace(artifacts["DESIGN"], path=filename)
        plan = self._safe_task_path("TEST_PLAN.md", "REBIND_PATH")
        header = (
            self._parse_frontmatter(plan, plan.read_text())
            if plan and plan.is_file()
            else {}
        )
        if (
            "checker_plan_sha256" in (header or {})
            or (self.task_dir / "checker-plan.json").exists()
        ):
            artifacts["CHECKER_PLAN"] = replace(
                artifacts["TEST_PLAN"], path="checker-plan.json"
            )
            dependencies.setdefault("TEST_PLAN", {})["checker_plan_sha256"] = (
                "CHECKER_PLAN"
            )
        return artifacts, dependencies

    def rebind_header(self, name, path):
        if name == "SOURCE_REPORT":
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("source report must be a JSON object")
            return (
                data.get("knowledge") if isinstance(data.get("knowledge"), dict) else {}
            )
        return super().rebind_header(name, path)

    def validate_state(self, target_state: str) -> None:
        super().validate_state(target_state)
        if target_state == "ENV_READY" or "DESIGN" not in self.headers:
            return
        design = self.headers["DESIGN"]
        self._validate_knowledge_baseline(design)
        mode = design.get("ccu_mode")
        if mode not in {"CCU_SCHED", "CCU_MS"}:
            self.error("CCU_MODE", "DESIGN.md", "ccu_mode must be CCU_SCHED or CCU_MS")
        if self.headers.get("TEST_PLAN", {}).get("ccu_mode") != mode:
            self.error(
                "CCU_MODE", "TEST_PLAN.md", "ccu_mode must match the frozen design"
            )
        # Optional executable plan: its binding travels through the existing TEST_PLAN hash chain.
        # Historical tasks without this attachment retain their original requirements.
        if self.index.get("ccu_contract_version", 1) == 3:
            self._validate_checker_plan()
        if design.get("hcomm_source_identity") != self.index.get(
            "hcomm_source_identity"
        ):
            self.error(
                "HCOMM_IDENTITY",
                "DESIGN.md",
                "HCOMM dependency changed; refresh the design and downstream evidence",
            )
        self._validate_design_attachments(design)
        if self.knowledge_baseline is not None:
            self._check_hash(
                design.get("knowledge_baseline_sha256"),
                self.knowledge_baseline,
                "CCU_BASELINE_HASH",
            )

    def validate_launch_contract(self, path: Path) -> None:
        """Validate an explicit launch contract using the installed Skill checker."""
        self._validate_launch_contract(path)

    def _design_header(self):
        if "DESIGN" in self.headers:
            return self.headers["DESIGN"]
        path = self._safe_task_path("DESIGN.md", "CCU_PATH")
        if path is None or not path.is_file():
            return {}
        return self._parse_frontmatter(path, path.read_text(encoding="utf-8")) or {}

    def _source_report_file(self, design):
        filename = design.get("source_report_file", "source-report.json")
        if not isinstance(filename, str) or not SOURCE_REPORT_RE.fullmatch(filename):
            self.error(
                "CCU_SOURCE_REPORT_PATH",
                "DESIGN.md",
                "source_report_file must be source-report.json or source-report-r<positive revision>.json",
            )
            return None
        return filename

    def _validate_actor_paths(self, actor, changed, source_repo):
        if actor == "hccl-architect":
            for raw in changed:
                path = Path(raw)
                resolved = (
                    path
                    if path.is_absolute()
                    else (source_repo or self.task_dir) / path
                ).resolve()
                if not self._is_within(resolved, self.task_dir):
                    continue
                rel = resolved.relative_to(self.task_dir).as_posix()
                if SOURCE_REPORT_RE.fullmatch(rel):
                    self.task_owners[actor].add(rel)
        super()._validate_actor_paths(actor, changed, source_repo)

    def _validate_index_enums(self, data: dict, path: Path) -> None:
        super()._validate_index_enums(data, path)
        version = data.get("ccu_contract_version", 1)
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version not in (1, 2, 3)
        ):
            self.error(
                "CCU_CONTRACT_VERSION",
                path,
                "ccu_contract_version must be 1, 2 (historical) or 3",
            )
        if isinstance(version, int) and not isinstance(version, bool) and version >= 2:
            role, outputs = self.call_requirements["DESIGN_READY"]
            self.call_requirements["DESIGN_READY"] = (role, outputs | {SYNC_FILE})
        design = self._design_header()
        source_report = self._source_report_file(design)
        role, outputs = self.call_requirements["DESIGN_READY"]
        if source_report:
            outputs = (outputs - {"source-report.json"}) | {source_report}
        if (
            "knowledge_baseline_sha256" in design
            or (self.task_dir / KNOWLEDGE_BASELINE).exists()
        ):
            outputs = outputs | {KNOWLEDGE_BASELINE}
        self.call_requirements["DESIGN_READY"] = (role, outputs)
        root = data.get("hcomm_repo")
        if not isinstance(root, str) or not Path(root).is_absolute():
            self.error(
                "HCOMM_ROOT", path, "hcomm_repo must be an explicit absolute path"
            )
        if not self._nonempty(data.get("hcomm_source_identity")):
            self.error("HCOMM_IDENTITY", path, "hcomm_source_identity is required")

    def _validate_design_attachments(self, design):
        files = {"launch-contract.json"}
        source_report = self._source_report_file(design)
        if source_report:
            files.add(source_report)
        if self.index.get("ccu_contract_version", 1) in (2, 3):
            files.add(SYNC_FILE)
        for filename in sorted(files):
            self._validate_design_attachment(filename, source_report, design)

    def _validate_design_attachment(self, filename, source_report, design):
        path = self._safe_task_path(filename, "CCU_PATH")
        if path is None:
            return
        if not path.is_file():
            self.error(
                "CCU_ARTIFACT_MISSING", filename, "required design artifact is missing"
            )
            return
        field = (
            "source_report_sha256"
            if filename == source_report
            else filename.removesuffix(".json").replace("-", "_") + "_sha256"
        )
        self._check_hash(design.get(field), path, "CCU_DEPENDENCY_HASH")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            self.error("CCU_JSON", filename, str(exc))
            return
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            self.error("CCU_SCHEMA", filename, "expected a schema_version=1 object")
            return
        if filename == source_report:
            self._validate_source_report(data, path)
        elif filename == SYNC_FILE:
            self._validate_sync_contract(path)
        else:
            self._validate_launch_contract(path)

    def _validate_knowledge_baseline(self, design):
        if (
            "knowledge_baseline_sha256" not in design
            and not (self.task_dir / KNOWLEDGE_BASELINE).exists()
        ):
            return
        path = self._safe_task_path(KNOWLEDGE_BASELINE, "CCU_PATH")
        if path is None or not path.is_file():
            self.error(
                "CCU_BASELINE_MISSING",
                KNOWLEDGE_BASELINE,
                "reviewed knowledge baseline is missing",
            )
            self.baseline_blocked = True
            return
        before = len(self.problems)
        self._check_hash(
            design.get("knowledge_baseline_sha256"), path, "CCU_BASELINE_HASH"
        )
        self.baseline_blocked = len(self.problems) != before
        if not self.baseline_blocked:
            self.knowledge_baseline = path

    def _validate_estimate_metadata(
        self, data: dict, header: dict, evidence: Path
    ) -> None:
        super()._validate_estimate_metadata(data, header, evidence)
        if data.get("engine") != self.engine:
            self.error("ESTIMATE_ENGINE", evidence, "estimate engine must be CCU")
        mode = self.headers.get("DESIGN", {}).get("ccu_mode")
        if mode not in {"CCU_SCHED", "CCU_MS"} or data.get("ccu_mode") != mode:
            self.error(
                "ESTIMATE_CCU_MODE",
                evidence,
                "estimate mode must match the frozen CCU design",
            )
        if data.get("hcomm_source_identity") != self.index.get("hcomm_source_identity"):
            self.error(
                "ESTIMATE_HCOMM_IDENTITY",
                evidence,
                "estimate HCOMM dependency must be current",
            )

    def _validate_checker_plan(self) -> None:
        path = self._safe_task_path("checker-plan.json", "CCU_PATH")
        if path is None:
            return
        header = self.headers.get("TEST_PLAN", {})
        expected = header.get("checker_plan_sha256")
        if not path.exists() and expected is None:
            return
        if not path.is_file():
            self.error(
                "CCU_CHECKER_PLAN", path, "TEST_PLAN binds a missing executable plan"
            )
            return
        self._check_hash(expected, path, "CCU_CHECKER_PLAN_HASH")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or data.get("schema_version") != 1
                or not data.get("batches")
            ):
                raise ValueError(
                    "expected schema_version=1 and nonempty batches; run hvm plan.py check for format validation"
                )
        except (OSError, ValueError) as exc:
            self.error("CCU_CHECKER_PLAN", path, str(exc))

    def _validate_source_report(self, data: dict, path: Path) -> None:
        if self.knowledge_baseline is not None:
            knowledge = data.get("knowledge")
            if not isinstance(knowledge, dict) or knowledge.get(
                "baseline_sha256"
            ) != self._sha256(self.knowledge_baseline):
                self.error(
                    "CCU_BASELINE_SOURCE",
                    path,
                    "source report must use the baseline bound by DESIGN",
                )
        repositories = data.get("repositories")
        if not isinstance(repositories, dict):
            self.error("CCU_SOURCES", path, "missing repository inventory")
            return
        for name, key in (("hccl", "source_repo"), ("hcomm", "hcomm_repo")):
            repo = repositories.get(name)
            if not isinstance(repo, dict):
                self.error("CCU_SOURCES", path, f"missing {name} repository")
                continue
            root, expected = repo.get("root"), self.index.get(key)
            if (
                not isinstance(root, str)
                or not isinstance(expected, str)
                or Path(root).resolve() != Path(expected).resolve()
            ):
                self.error(
                    "CCU_SOURCE_ROOT", path, f"{name} root differs from task index"
                )
            if not self._nonempty(repo.get("head")):
                self.error("CCU_SOURCES", path, f"missing {name} HEAD")
        sources = data.get("sources")
        if not isinstance(sources, list) or not sources:
            self.error("CCU_SOURCES", path, "source inventory must not be empty")
            return
        for entry in sources:
            if not isinstance(entry, dict) or (
                entry.get("status") not in {"unchanged", "changed"}
                and not (
                    entry.get("required") is False and entry.get("status") == "missing"
                )
            ):
                self.error(
                    "CCU_SOURCES",
                    path,
                    "source inventory contains unavailable evidence",
                )

    def _validate_launch_contract(self, path: Path) -> None:
        self._run_skill_check("check_launch_contract.py", path, "CCU_CONTRACT_CHECK")

    def _validate_sync_contract(self, path: Path) -> None:
        if self.baseline_blocked:
            return
        root = self.index.get("hcomm_repo")
        if isinstance(root, str):
            args = ["--hcomm-root", root]
            if self.knowledge_baseline is not None:
                args += ["--baseline", str(self.knowledge_baseline)]
            self._run_skill_check(
                "check_sync_contract.py", path, "CCU_SYNC_CHECK", *args
            )
            if self.index.get("ccu_contract_version", 1) == 3:
                self._run_skill_check(
                    "check_arith_ops.py", path, "CCU_ARITH_CHECK", *args
                )

    def _run_skill_check(self, name: str, path: Path, code: str, *args: str) -> None:
        script = self.skill_dir / "scripts" / name
        if not (self.skill_dir / "SKILL.md").is_file() or not script.is_file():
            self.error(
                "CCU_SKILL_MISSING",
                self.skill_dir,
                "install hccl-ccu-best-practice with its scripts",
            )
            return
        try:
            result = subprocess.run(
                [sys.executable, str(script), str(path), *args],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.error(code, path, str(exc))
            return
        if result.returncode:
            self.error(code, path, (result.stdout + result.stderr).strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", required=True, type=Path)
    parser.add_argument(
        "--ccu-skill-dir",
        type=Path,
        help="required for state/actor gates; not needed by read-only rebind reports",
    )
    parser.add_argument("--target-state", choices=BASE.STATES)
    parser.add_argument("--actor", choices=tuple(BASE.TASK_OWNERS))
    parser.add_argument("--changed", nargs="+", default=[])
    parser.add_argument("--json", action="store_true")
    BASE.add_rebind_arguments(parser)
    args = parser.parse_args(argv)
    reporting = args.rebind_report is not None or args.verify_rebind
    if reporting and any((args.target_state, args.actor, args.changed)):
        parser.error("rebind reporting cannot be combined with a state/actor gate")
    if not reporting and args.ccu_skill_dir is None:
        parser.error("--ccu-skill-dir is required for state/actor gates")
    if not any((args.target_state, args.actor, reporting)):
        parser.error("at least one of --target-state or --actor is required")
    if args.changed and not args.actor:
        parser.error("--changed requires --actor")
    validator = Validator(args.task_dir, args.ccu_skill_dir or Path(__file__).parent)
    report_status = BASE.handle_rebind_cli(args, validator)
    if report_status is not None:
        return report_status
    if args.target_state:
        validator.validate_state(args.target_state)
    if args.actor:
        validator.validate_actor(args.actor, args.changed)
    result = {
        "ok": not validator.problems,
        "engine": "CCU",
        "target_state": args.target_state,
        "actor": args.actor,
        "errors": [problem.__dict__ for problem in validator.problems],
    }
    if args.json:
        BASE.emit_json(result, indent=2)
    else:
        BASE.emit_text(result)
    return 1 if validator.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
