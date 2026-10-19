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
"""Validate HCCLBot AICPU task artifacts and role write boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)


SCRIPT_DIR = Path(__file__).resolve().parent
WORKFLOW_DIR = SCRIPT_DIR.parent
TEMPLATE_DIR = WORKFLOW_DIR / "templates"

STATES = (
    "ENV_READY",
    "DESIGN_READY",
    "BASELINE_READY",
    "IMPLEMENTED",
    "REVIEW_PASS",
    "TEST_PASS",
    "COMPLETE",
)
PREVIOUS_STATE = {
    "DESIGN_READY": "ENV_READY",
    "BASELINE_READY": "DESIGN_READY",
    "IMPLEMENTED": "BASELINE_READY",
    "REVIEW_PASS": "IMPLEMENTED",
    "TEST_PASS": "REVIEW_PASS",
    "COMPLETE": "TEST_PASS",
}


@dataclass(frozen=True)
class ArtifactSpec:
    path: str
    template: str
    owner: str | None
    accepted_statuses: frozenset[str]
    ready_statuses: frozenset[str]
    required_fields: tuple[str, ...] = ()


ARTIFACTS = {
    "ENVIRONMENT": ArtifactSpec(
        "environment.md",
        "environment-template.md",
        "hcclbot",
        frozenset({"PASS", "FAIL", "BLOCKED"}),
        frozenset({"PASS"}),
        ("checks_pass", "created_at"),
    ),
    "TASK_SPEC": ArtifactSpec(
        "TASK_SPEC.md",
        "aicpu-task-spec-template.md",
        "hccl-architect",
        frozenset({"FROZEN", "DESIGN_ISSUE", "BLOCKED"}),
        frozenset({"FROZEN"}),
        ("artifact_revision", "semantic_tbd_count", "created_at"),
    ),
    "DATAFLOW_SPEC_INDEX": ArtifactSpec(
        "DATAFLOW_SPEC.md",
        "aicpu-dataflow-spec-index-template.md",
        "hccl-architect",
        frozenset({"PASS", "NOT_REQUIRED", "DESIGN_ISSUE", "BLOCKED"}),
        frozenset({"PASS", "NOT_REQUIRED"}),
        (
            "artifact_revision",
            "applicability",
            "spec_count",
            "passed_spec_count",
            "semantic_tbd_count",
            "created_at",
        ),
    ),
    "DESIGN": ArtifactSpec(
        "DESIGN.md",
        "design-template.md",
        "hccl-architect",
        frozenset({"FROZEN", "DESIGN_ISSUE", "BLOCKED"}),
        frozenset({"FROZEN"}),
        ("artifact_revision", "semantic_tbd_count", "created_at"),
    ),
    "PLAN": ArtifactSpec(
        "PLAN.md",
        "plan-template.md",
        "hccl-architect",
        frozenset({"FROZEN", "DESIGN_ISSUE", "BLOCKED"}),
        frozenset({"FROZEN"}),
        ("artifact_revision", "semantic_tbd_count", "created_at"),
    ),
    "TEST_PLAN": ArtifactSpec(
        "TEST_PLAN.md",
        "aicpu-test-plan-template.md",
        "hccl-architect",
        frozenset({"FROZEN", "DESIGN_ISSUE", "BLOCKED"}),
        frozenset({"FROZEN"}),
        ("artifact_revision", "semantic_tbd_count", "created_at"),
    ),
    "BASELINE_REPORT": ArtifactSpec(
        "BASELINE_REPORT.md",
        "aicpu-baseline-report-template.md",
        "hccl-verifier",
        frozenset({"PASS", "FAIL", "BLOCKED"}),
        frozenset({"PASS"}),
        (
            "task_spec_sha256",
            "design_sha256",
            "test_plan_sha256",
            "round",
            "evidence_complete",
            "unresolved_failure_count",
            "install_test_ready",
            "created_at",
        ),
    ),
    "DEVELOPMENT_LOG": ArtifactSpec(
        "LOG.md",
        "log-template.md",
        "hccl-developer",
        frozenset({"PASS", "DESIGN_ISSUE", "BLOCKED"}),
        frozenset({"PASS"}),
        (
            "input_source_identity",
            "output_source_identity",
            "task_spec_sha256",
            "dataflow_index_sha256",
            "design_sha256",
            "plan_sha256",
            "baseline_sha256",
            "round",
            "static_failure_count",
            "updated_at",
        ),
    ),
    "REVIEW": ArtifactSpec(
        "REVIEW.md",
        "aicpu-review-template.md",
        "hccl-reviewer",
        frozenset({"PASS", "REVIEW_FAIL", "BLOCKED"}),
        frozenset({"PASS"}),
        (
            "task_spec_sha256",
            "dataflow_index_sha256",
            "design_sha256",
            "plan_sha256",
            "test_plan_sha256",
            "baseline_sha256",
            "round",
            "blocking_issue_count",
            "created_at",
        ),
    ),
    "TEST_REPORT": ArtifactSpec(
        "TEST_REPORT.md",
        "aicpu-test-report-template.md",
        "hccl-verifier",
        frozenset({"PASS", "TEST_FAIL", "BLOCKED"}),
        frozenset({"PASS"}),
        (
            "review_source_identity",
            "baseline_sha256",
            "review_sha256",
            "test_plan_sha256",
            "round",
            "build_pass",
            "track_a_pass",
            "track_b_pass",
            "identity_match",
            "environment_clean",
            "test_failure_count",
            "estimate_status",
            "estimate_source_identity",
            "estimate_comm_domain",
            "estimate_evidence_path",
            "estimate_evidence_sha256",
            "created_at",
        ),
    ),
    "HANDOFF_LOG": ArtifactSpec(
        "HANDOFF.md",
        "aicpu-handoff-template.md",
        None,
        frozenset(
            {"PASS", "FAIL", "DESIGN_ISSUE", "REVIEW_FAIL", "TEST_FAIL", "BLOCKED"}
        ),
        frozenset({"PASS"}),
        (
            "owner_policy",
            "latest_sequence",
            "latest_owner",
            "latest_status",
            "latest_source_identity",
            "entry_count",
            "updated_at",
        ),
    ),
}

STATE_REQUIREMENTS = {
    "ENV_READY": ("ENVIRONMENT",),
    "DESIGN_READY": (
        "ENVIRONMENT",
        "TASK_SPEC",
        "DATAFLOW_SPEC_INDEX",
        "DESIGN",
        "PLAN",
        "TEST_PLAN",
        "HANDOFF_LOG",
    ),
    "BASELINE_READY": (
        "ENVIRONMENT",
        "TASK_SPEC",
        "DATAFLOW_SPEC_INDEX",
        "DESIGN",
        "PLAN",
        "TEST_PLAN",
        "BASELINE_REPORT",
        "HANDOFF_LOG",
    ),
    "IMPLEMENTED": (
        "ENVIRONMENT",
        "TASK_SPEC",
        "DATAFLOW_SPEC_INDEX",
        "DESIGN",
        "PLAN",
        "TEST_PLAN",
        "BASELINE_REPORT",
        "DEVELOPMENT_LOG",
        "HANDOFF_LOG",
    ),
    "REVIEW_PASS": (
        "ENVIRONMENT",
        "TASK_SPEC",
        "DATAFLOW_SPEC_INDEX",
        "DESIGN",
        "PLAN",
        "TEST_PLAN",
        "BASELINE_REPORT",
        "DEVELOPMENT_LOG",
        "REVIEW",
        "HANDOFF_LOG",
    ),
    "TEST_PASS": tuple(ARTIFACTS),
    "COMPLETE": tuple(ARTIFACTS),
}

EXPECTED_HANDOFF_OWNER = {
    "DESIGN_READY": "hccl-architect",
    "BASELINE_READY": "hccl-verifier",
    "IMPLEMENTED": "hccl-developer",
    "REVIEW_PASS": "hccl-reviewer",
    "TEST_PASS": "hccl-verifier",
    "COMPLETE": "hccl-verifier",
}

CALL_REQUIREMENTS = {
    "DESIGN_READY": (
        "hccl-architect",
        {
            "TASK_SPEC.md",
            "DATAFLOW_SPEC.md",
            "DESIGN.md",
            "PLAN.md",
            "TEST_PLAN.md",
            "HANDOFF.md",
        },
    ),
    "BASELINE_READY": ("hccl-verifier", {"BASELINE_REPORT.md", "HANDOFF.md"}),
    "IMPLEMENTED": ("hccl-developer", {"LOG.md", "HANDOFF.md"}),
    "REVIEW_PASS": ("hccl-reviewer", {"REVIEW.md", "HANDOFF.md"}),
    "TEST_PASS": ("hccl-verifier", {"TEST_REPORT.md", "HANDOFF.md"}),
}

TASK_OWNERS = {
    "hcclbot": {"task-index.json", "environment.md"},
    "hccl-architect": {
        "TASK_SPEC.md",
        "DATAFLOW_SPEC.md",
        "DESIGN.md",
        "PLAN.md",
        "TEST_PLAN.md",
        "HANDOFF.md",
    },
    "hccl-developer": {"LOG.md", "HANDOFF.md"},
    "hccl-reviewer": {"REVIEW.md", "HANDOFF.md"},
    "hccl-verifier": {"BASELINE_REPORT.md", "TEST_REPORT.md", "HANDOFF.md"},
}

DEPENDENCIES = {
    "BASELINE_REPORT": {
        "task_spec_sha256": "TASK_SPEC",
        "design_sha256": "DESIGN",
        "test_plan_sha256": "TEST_PLAN",
    },
    "DEVELOPMENT_LOG": {
        "task_spec_sha256": "TASK_SPEC",
        "dataflow_index_sha256": "DATAFLOW_SPEC_INDEX",
        "design_sha256": "DESIGN",
        "plan_sha256": "PLAN",
        "baseline_sha256": "BASELINE_REPORT",
    },
    "REVIEW": {
        "task_spec_sha256": "TASK_SPEC",
        "dataflow_index_sha256": "DATAFLOW_SPEC_INDEX",
        "design_sha256": "DESIGN",
        "plan_sha256": "PLAN",
        "test_plan_sha256": "TEST_PLAN",
        "baseline_sha256": "BASELINE_REPORT",
    },
    "TEST_REPORT": {
        "baseline_sha256": "BASELINE_REPORT",
        "review_sha256": "REVIEW",
        "test_plan_sha256": "TEST_PLAN",
    },
}

PLACEHOLDER_RE = re.compile(r"(?<!\$)\{[^{}\n]+\}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass
class Problem:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ArtifactSummary:
    owner: Any
    status: Any
    identity: Any


class Validator:
    def __init__(self, task_dir: Path):
        self.task_dir = task_dir.resolve()
        self.problems: list[Problem] = []
        self.index: dict[str, Any] = {}
        self.headers: dict[str, dict[str, Any]] = {}
        self.texts: dict[str, str] = {}
        self.external_evidence_roots: list[Path] = []

    @staticmethod
    def artifact_identity(name: str, header: dict[str, Any]) -> Any:
        if name == "DEVELOPMENT_LOG":
            return header.get("output_source_identity")
        if name == "HANDOFF_LOG":
            return header.get("latest_source_identity")
        return header.get("source_identity")

    @staticmethod
    def _as_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        return None

    @staticmethod
    def _as_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and re.fullmatch(r"\d+", value):
            return int(value)
        return None

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    @staticmethod
    def _nonempty(value: Any) -> bool:
        return (
            isinstance(value, str)
            and bool(value.strip())
            and not PLACEHOLDER_RE.search(value)
        )

    @staticmethod
    def _parse_scalar(value: str) -> Any:
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        if re.fullmatch(r"-?\d+", value):
            return int(value)
        return value

    @staticmethod
    def _positive_finite_number(value: Any) -> bool:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if isinstance(value, float) and not math.isfinite(value):
            return False
        return value > 0

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _template_placeholders(template: str) -> set[str]:
        try:
            text = (TEMPLATE_DIR / template).read_text(encoding="utf-8")
        except OSError:
            return set()
        return set(PLACEHOLDER_RE.findall(text))

    def error(self, code: str, path: str | Path, message: str) -> None:
        self.problems.append(Problem(code, str(path), message))

    def load_index(self) -> None:
        self.external_evidence_roots = []
        path = self.task_dir / "task-index.json"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.error("INDEX_MISSING", path, str(exc))
            return
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            self.error("INDEX_JSON", path, f"invalid JSON: {exc}")
            return
        if not isinstance(data, dict):
            self.error("INDEX_TYPE", path, "root must be an object")
            return
        self.index = data
        self._validate_index_fields(data, path)
        self._validate_external_roots(data, path)
        if not isinstance(data.get("artifacts"), dict):
            self.error("INDEX_ARTIFACTS", path, "artifacts must be an object")
        for key in ("dataflow_specs", "calls", "invalidated_artifacts"):
            if not isinstance(data.get(key), list):
                self.error("INDEX_LIST", path, f"{key} must be an array")
        placeholders = PLACEHOLDER_RE.findall(text)
        if placeholders:
            self.error(
                "PLACEHOLDER",
                path,
                f"unresolved placeholders: {', '.join(sorted(set(placeholders)))}",
            )

    def validate_actor(self, actor: str, changed: list[str]) -> None:
        if not self.index:
            self.load_index()
        if actor not in TASK_OWNERS:
            self.error("ACTOR", actor, "unknown actor")
            return
        if not changed:
            self.error("CHANGED", actor, "--changed requires at least one path")
            return
        source_repo_value = self.index.get("source_repo") if self.index else None
        source_repo = (
            Path(source_repo_value).resolve()
            if isinstance(source_repo_value, str)
            else None
        )

        self._validate_actor_paths(actor, changed, source_repo)

    def validate_state(self, target_state: str) -> None:
        self.load_index()
        if not self.index:
            return
        if self.index.get("pending_action") != "NONE":
            self.error(
                "PENDING_ACTION",
                self.task_dir / "task-index.json",
                "pending_action must be NONE before a state gate can pass",
            )
        current = self.index.get("current_state")
        allowed = {target_state, PREVIOUS_STATE.get(target_state)} - {None}
        if current not in allowed:
            self.error(
                "STATE_TRANSITION",
                self.task_dir / "task-index.json",
                f"current_state={current!r} cannot validate target {target_state}; expected one of {sorted(allowed)}",
            )

        for artifact in STATE_REQUIREMENTS[target_state]:
            self._validate_artifact(artifact, require_ready=True)

        self._validate_dependencies(target_state)
        self._validate_current_identity(target_state)
        self._validate_handoff(target_state)
        self._validate_calls(target_state)
        self._validate_invalidation()

    def _check_hash(self, value: Any, path: Path, code: str) -> None:
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            self.error(code, path, "sha256 must be 64 lowercase hexadecimal characters")
            return
        actual = self._sha256(path)
        if value != actual:
            self.error(code, path, f"sha256 mismatch: indexed={value}, actual={actual}")

    def _expect_bool(
        self, header: dict[str, Any], field: str, expected: bool, path: Path
    ) -> None:
        value = self._as_bool(header.get(field))
        if value is not expected:
            self.error(
                "PASS_INVARIANT",
                path,
                f"{field} must be {str(expected).lower()} for PASS",
            )

    def _expect_int(
        self, header: dict[str, Any], field: str, expected: int, path: Path
    ) -> None:
        value = self._as_int(header.get(field))
        if value != expected:
            self.error(
                "PASS_INVARIANT", path, f"{field} must be {expected} for ready status"
            )

    def _parse_frontmatter(
        self, path: Path, text: str, report_errors: bool = True
    ) -> dict[str, Any] | None:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            if report_errors:
                self.error("FRONTMATTER", path, "file must start with ---")
            return None
        try:
            end = next(
                i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"
            )
        except StopIteration:
            if report_errors:
                self.error("FRONTMATTER", path, "closing --- not found")
            return None
        data: dict[str, Any] = {}
        for number, line in enumerate(lines[1:end], 2):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line[:1].isspace() or ":" not in line:
                if report_errors:
                    self.error(
                        "FRONTMATTER", path, f"unsupported line {number}: {line}"
                    )
                return None
            key, raw = line.split(":", 1)
            key = key.strip()
            if key in data:
                if report_errors:
                    self.error("FRONTMATTER", path, f"duplicate key: {key}")
                return None
            data[key] = self._parse_scalar(raw.strip())
        return data

    def _safe_task_path(self, rel: str, code: str) -> Path | None:
        path = Path(rel)
        if path.is_absolute():
            self.error(code, rel, "path must be relative to task_dir")
            return None
        resolved = (self.task_dir / path).resolve(strict=False)
        if not self._is_within(resolved, self.task_dir):
            self.error(code, rel, "path escapes task_dir")
            return None
        return resolved

    def _validate_actor_paths(
        self, actor: str, changed: list[str], source_repo: Path | None
    ) -> None:
        for raw in changed:
            path = Path(raw)
            if not path.is_absolute():
                if source_repo is None:
                    self.error(
                        "CHANGED_PATH",
                        raw,
                        "relative paths require source_repo in task-index.json",
                    )
                    continue
                path = source_repo / path
            resolved = path.resolve(strict=False)
            if self._is_within(resolved, self.task_dir):
                rel = resolved.relative_to(self.task_dir).as_posix()
                allowed = rel in TASK_OWNERS[actor]
                if (
                    actor == "hccl-architect"
                    and rel.startswith("dataflow/")
                    and rel.endswith(".md")
                ):
                    allowed = True
                if not allowed:
                    self.error(
                        "OWNER_BOUNDARY",
                        raw,
                        f"{actor} cannot write task artifact {rel}",
                    )
                continue
            if (
                actor == "hccl-developer"
                and source_repo
                and self._is_within(resolved, source_repo)
            ):
                continue
            if actor == "hccl-verifier" and any(
                self._is_within(resolved, root) for root in self.external_evidence_roots
            ):
                continue
            self.error(
                "OWNER_BOUNDARY",
                raw,
                f"{actor} cannot write outside its task artifact scope",
            )

    def _validate_artifact(self, name: str, require_ready: bool) -> None:
        if name in self.headers:
            return
        spec = ARTIFACTS[name]
        path = self.task_dir / spec.path
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.error("ARTIFACT_MISSING", path, str(exc))
            return
        header = self._parse_frontmatter(path, text)
        if header is None:
            return
        self.headers[name] = header
        self.texts[name] = text

        self._validate_artifact_header(name, header, path)

        if name == "HANDOFF_LOG":
            if header.get("owner_policy") != "current_stage_agent":
                self.error(
                    "ARTIFACT_OWNER", path, "owner_policy must be current_stage_agent"
                )
            owner = header.get("latest_owner")
            status = header.get("latest_status")
            identity = header.get("latest_source_identity")
        else:
            if header.get("owner") != spec.owner:
                self.error("ARTIFACT_OWNER", path, f"owner must be {spec.owner}")
            owner = header.get("owner")
            status = header.get("status")
            identity = self.artifact_identity(name, header)

        if status not in spec.accepted_statuses:
            self.error("ARTIFACT_STATUS", path, f"invalid status: {status!r}")
        elif require_ready and status not in spec.ready_statuses:
            self.error(
                "ARTIFACT_NOT_READY",
                path,
                f"status {status!r} does not satisfy the gate",
            )
        if not self._nonempty(identity):
            self.error("SOURCE_IDENTITY", path, "source identity must be non-empty")

        self._validate_artifact_placeholders(spec, text, path)
        self._validate_semantics(name, header, path)
        self._validate_index_entry(
            name, path, header, ArtifactSummary(owner, status, identity)
        )

    def _validate_artifact_header(
        self, name: str, header: dict[str, Any], path: Path
    ) -> None:
        common = ("schema_version", "artifact", "engine", "task_id")
        for key in common + ARTIFACTS[name].required_fields:
            if key not in header:
                self.error("ARTIFACT_FIELD", path, f"missing frontmatter field: {key}")
        if header.get("schema_version") != 1:
            self.error("ARTIFACT_SCHEMA", path, "schema_version must be 1")
        if header.get("artifact") != name:
            self.error("ARTIFACT_TYPE", path, f"artifact must be {name}")
        if header.get("engine") != "AICPU":
            self.error("ARTIFACT_ENGINE", path, "engine must be AICPU")
        if header.get("task_id") != self.index.get("task_id"):
            self.error("TASK_ID", path, "task_id does not match task-index.json")

    def _validate_artifact_placeholders(
        self, spec: ArtifactSpec, text: str, path: Path
    ) -> None:
        leftovers = sorted(
            self._template_placeholders(spec.template)
            & set(PLACEHOLDER_RE.findall(text))
        )
        if leftovers:
            self.error(
                "PLACEHOLDER",
                path,
                f"unresolved template placeholders: {', '.join(leftovers)}",
            )

    def _validate_call_entries(
        self, calls: list, source_repo: Path | None
    ) -> dict[str, list[dict[str, Any]]]:
        seen_ids: set[str] = set()
        valid_calls: dict[str, list[dict[str, Any]]] = {}
        for number, call in enumerate(calls, 1):
            label = f"task-index.json:calls[{number}]"
            if not isinstance(call, dict):
                self.error("CALL_RECORD", label, "call must be an object")
                continue
            call_state = self._validate_single_call(call, label, seen_ids, source_repo)
            if call.get("status") == "PASS" and isinstance(call_state, str):
                valid_calls.setdefault(call_state, []).append(call)
        return valid_calls

    def _validate_calls(self, target_state: str) -> None:
        calls = self.index.get("calls")
        if not isinstance(calls, list):
            return
        source_repo_value = self.index.get("source_repo")
        source_repo = (
            Path(source_repo_value).resolve()
            if isinstance(source_repo_value, str)
            else None
        )
        valid_calls = self._validate_call_entries(calls, source_repo)

        target_position = STATES.index(target_state)
        for state, (role, outputs) in CALL_REQUIREMENTS.items():
            if STATES.index(state) > target_position:
                continue
            matching = [
                call for call in valid_calls.get(state, []) if call.get("role") == role
            ]
            if not matching:
                self.error(
                    "CALL_REQUIRED",
                    "task-index.json",
                    f"missing PASS call for {role} -> {state}",
                )
                continue
            latest = matching[-1]
            self._validate_call_outputs(state, latest, outputs, source_repo)
            if state in {"IMPLEMENTED", "REVIEW_PASS", "TEST_PASS"}:
                if latest.get("source_identity") != self.index.get("source_identity"):
                    self.error(
                        "CALL_IDENTITY",
                        "task-index.json",
                        f"{state} call is not bound to current source",
                    )

    def _validate_call_outputs(
        self,
        state: str,
        call: dict[str, Any],
        outputs: set[str],
        source_repo: Path | None,
    ) -> None:
        call_outputs = call.get("outputs")
        if not isinstance(call_outputs, list) or source_repo is None:
            return
        resolved_outputs = {
            (Path(item) if Path(item).is_absolute() else source_repo / item).resolve(
                strict=False
            )
            for item in call_outputs
        }
        required_outputs = {
            (self.task_dir / item).resolve(strict=False) for item in outputs
        }
        if not required_outputs.issubset(resolved_outputs):
            missing = sorted(path.name for path in required_outputs - resolved_outputs)
            self.error(
                "CALL_OUTPUT",
                "task-index.json",
                f"{state} call is missing outputs: {missing}",
            )

    def _validate_current_identity(self, target_state: str) -> None:
        current = self.index.get("source_identity")
        required = set(STATE_REQUIREMENTS[target_state])
        if "DEVELOPMENT_LOG" in required and "DEVELOPMENT_LOG" in self.headers:
            if self.headers["DEVELOPMENT_LOG"].get("output_source_identity") != current:
                self.error(
                    "CURRENT_IDENTITY",
                    ARTIFACTS["DEVELOPMENT_LOG"].path,
                    "output identity is not current",
                )
        if "REVIEW" in required and "REVIEW" in self.headers:
            if self.headers["REVIEW"].get("source_identity") != current:
                self.error(
                    "CURRENT_IDENTITY",
                    ARTIFACTS["REVIEW"].path,
                    "review identity is not current",
                )
        if "TEST_REPORT" in required and "TEST_REPORT" in self.headers:
            header = self.headers["TEST_REPORT"]
            if (
                header.get("source_identity") != current
                or header.get("review_source_identity") != current
            ):
                self.error(
                    "CURRENT_IDENTITY",
                    ARTIFACTS["TEST_REPORT"].path,
                    "test/review identity is not current",
                )

    def _validate_estimate(self, header: dict[str, Any], path: Path) -> None:
        if header.get("estimate_status") != "SUCCESS":
            self.error("ESTIMATE_STATUS", path, "PASS requires estimate_status=SUCCESS")
            return
        current = self.index.get("source_identity")
        if header.get("estimate_source_identity") != current:
            self.error(
                "ESTIMATE_IDENTITY", path, "estimate source identity must be current"
            )

        evidence = self._estimate_file(
            {
                "path": header.get("estimate_evidence_path"),
                "sha256": header.get("estimate_evidence_sha256"),
            },
            path,
            "estimate.json",
        )
        if evidence is None:
            return
        try:
            data = json.loads(evidence.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self.error("ESTIMATE_JSON", evidence, str(exc))
            return
        if not isinstance(data, dict):
            self.error("ESTIMATE_JSON", evidence, "estimate evidence must be an object")
            return
        self._validate_estimate_metadata(data, header, evidence)
        self._validate_estimate_execution(data, evidence)
        self._validate_estimate_files(data, evidence)

    def _validate_estimate_metadata(
        self, data: dict[str, Any], header: dict[str, Any], evidence: Path
    ) -> None:
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            self.error("ESTIMATE_SCHEMA", evidence, "schema_version must be 1")
        if data.get("status") != "SUCCESS":
            self.error("ESTIMATE_STATUS", evidence, "evidence status must be SUCCESS")
        if data.get("source_identity") != self.index.get("source_identity"):
            self.error(
                "ESTIMATE_IDENTITY",
                evidence,
                "evidence source identity must be current",
            )
        for field in (
            "operator",
            "dtype",
            "comm_domain",
            "expected_algorithm",
            "observed_algorithm",
        ):
            if not self._nonempty(data.get(field)):
                self.error(
                    "ESTIMATE_FIELD", evidence, f"{field} must be a non-empty string"
                )
        if str(header.get("estimate_comm_domain")) != data.get("comm_domain"):
            self.error(
                "ESTIMATE_COMM",
                evidence,
                "communication domain differs from TEST_REPORT",
            )
        if data.get("expected_algorithm") != data.get("observed_algorithm"):
            self.error(
                "ESTIMATE_ALGORITHM", evidence, "target algorithm was not matched"
            )
        if not self._positive_finite_number(data.get("makespan_us")):
            self.error(
                "ESTIMATE_TIME",
                evidence,
                "makespan_us must be a finite positive number",
            )

    def _validate_estimate_execution(
        self, data: dict[str, Any], evidence: Path
    ) -> None:
        parameters = data.get("parameters")
        fixed = {
            "np": 1,
            "begin": "1G",
            "end": "1G",
            "warmup": 0,
            "iterations": 1,
            "check": 0,
        }
        for key, value in fixed.items():
            actual = parameters.get(key) if isinstance(parameters, dict) else None
            if type(actual) is not type(value) or actual != value:
                self.error("ESTIMATE_PARAMETERS", evidence, f"{key} must be {value!r}")
        exits = data.get("exit_codes")
        for key in ("start", "mock_comm", "mpirun", "estimate"):
            actual = exits.get(key) if isinstance(exits, dict) else None
            if type(actual) is not int or actual != 0:
                self.error("ESTIMATE_EXIT", evidence, f"{key} exit code must be 0")

    def _validate_estimate_files(self, data: dict[str, Any], evidence: Path) -> None:
        files = data.get("files")
        for key in (
            "candidate_package",
            "cluster",
            "test_log",
            "plugin_log",
            "profiling",
            "trace",
        ):
            record = files.get(key) if isinstance(files, dict) else None
            self._estimate_file(record, evidence, key, external=key != "cluster")

    def _estimate_file(
        self, record: Any, evidence: Path, label: str, external: bool = True
    ) -> Path | None:
        raw = record.get("path") if isinstance(record, dict) else None
        if not self._nonempty(raw) or not Path(raw).is_absolute():
            self.error(
                "ESTIMATE_PATH", evidence, f"{label} needs an absolute file path"
            )
            return None
        resolved = Path(raw).resolve(strict=False)
        if external and not any(
            self._is_within(resolved, root) for root in self.external_evidence_roots
        ):
            self.error(
                "ESTIMATE_PATH",
                resolved,
                f"{label} must be under external_evidence_roots",
            )
            return None
        if not resolved.is_file():
            self.error("ESTIMATE_MISSING", resolved, f"{label} file does not exist")
            return None
        try:
            self._check_hash(record.get("sha256"), resolved, "ESTIMATE_HASH")
        except OSError as exc:
            self.error("ESTIMATE_MISSING", resolved, str(exc))
            return None
        return resolved

    def _validate_dataflow(self, header: dict[str, Any], path: Path) -> None:
        status = header.get("status")
        applicability = header.get("applicability")
        counts = self._validate_dataflow_counts(header, path)
        if counts is None:
            return
        spec_count, passed_count, tbd_count = counts

        entries = self.index.get("dataflow_specs")
        entries = entries if isinstance(entries, list) else []
        if status == "NOT_REQUIRED":
            if (
                applicability != "NOT_REQUIRED"
                or any((spec_count, passed_count, tbd_count))
                or entries
            ):
                self.error(
                    "DATAFLOW_NOT_REQUIRED",
                    path,
                    "NOT_REQUIRED requires applicability=NOT_REQUIRED and zero specs/TBD/index entries",
                )
            return
        if status != "PASS":
            return
        if applicability != "REQUIRED" or spec_count < 1:
            self.error(
                "DATAFLOW_PASS",
                path,
                "PASS requires applicability=REQUIRED and spec_count>=1",
            )
        elif passed_count != spec_count or tbd_count != 0:
            self.error(
                "DATAFLOW_PASS",
                path,
                "PASS requires passed_spec_count=spec_count and semantic_tbd_count=0",
            )
        if len(entries) != spec_count:
            self.error(
                "DATAFLOW_INDEX",
                path,
                "task-index dataflow_specs count does not match spec_count",
            )
            return
        self._validate_dataflow_entries(entries, header, path)

    def _validate_dataflow_counts(
        self, header: dict[str, Any], path: Path
    ) -> tuple[int, int, int] | None:
        counts = tuple(
            self._as_int(header.get(field))
            for field in ("spec_count", "passed_spec_count", "semantic_tbd_count")
        )
        for field, value in zip(
            ("spec_count", "passed_spec_count", "semantic_tbd_count"), counts
        ):
            if value is None or value < 0:
                self.error(
                    "DATAFLOW_COUNT", path, f"{field} must be a non-negative integer"
                )
        if None in counts:
            return None
        return counts

    def _validate_dataflow_entries(
        self, entries: list, header: dict[str, Any], path: Path
    ) -> None:
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                self.error(
                    "DATAFLOW_INDEX",
                    path,
                    "each dataflow_specs entry must be an object",
                )
                continue
            rel = entry.get("path")
            if not isinstance(rel, str) or rel in seen:
                self.error(
                    "DATAFLOW_INDEX", path, f"invalid or duplicate spec path: {rel!r}"
                )
                continue
            seen.add(rel)
            spec_path = self._safe_task_path(rel, "DATAFLOW_PATH")
            if spec_path is None:
                continue
            dataflow_root = self.task_dir / "dataflow"
            if (
                not self._is_within(spec_path, dataflow_root)
                or spec_path.suffix != ".md"
            ):
                self.error(
                    "DATAFLOW_PATH",
                    rel,
                    "spec must be a .md file under task_dir/dataflow/",
                )
                continue
            if not spec_path.is_file():
                self.error("DATAFLOW_MISSING", spec_path, "indexed spec does not exist")
                continue
            self._validate_dataflow_evidence(entry, header, spec_path, path)

    def _validate_dataflow_evidence(
        self, entry: dict[str, Any], header: dict[str, Any], spec_path: Path, path: Path
    ) -> None:
        if entry.get("status") != "PASS" or entry.get("valid") is not True:
            self.error(
                "DATAFLOW_STATUS",
                spec_path,
                "indexed spec must have status=PASS and valid=true",
            )
        if entry.get("source_identity") != header.get("source_identity"):
            self.error(
                "DATAFLOW_IDENTITY",
                spec_path,
                "source_identity differs from DATAFLOW_SPEC.md",
            )
        self._check_hash(entry.get("sha256"), spec_path, "DATAFLOW_HASH")
        rel = entry["path"]
        index_text = self.texts.get("DATAFLOW_SPEC_INDEX", "")
        if rel not in index_text or str(entry.get("sha256")) not in index_text:
            self.error(
                "DATAFLOW_EVIDENCE",
                path,
                f"DATAFLOW_SPEC.md must record the current path and SHA-256 for {rel}",
            )

    def _validate_dependencies(self, target_state: str) -> None:
        required = set(STATE_REQUIREMENTS[target_state])
        for artifact, fields in DEPENDENCIES.items():
            if artifact not in required or artifact not in self.headers:
                continue
            header = self.headers[artifact]
            path = self.task_dir / ARTIFACTS[artifact].path
            for field, dependency in fields.items():
                dep_path = self.task_dir / ARTIFACTS[dependency].path
                if not dep_path.is_file():
                    continue
                expected = self._sha256(dep_path)
                if header.get(field) != expected:
                    self.error(
                        "DEPENDENCY_HASH",
                        path,
                        f"{field} does not match current {ARTIFACTS[dependency].path}",
                    )

    def _validate_external_roots(self, data: dict[str, Any], path: Path) -> None:
        external_roots = data.get("external_evidence_roots")
        if not isinstance(external_roots, list):
            self.error(
                "INDEX_EXTERNAL_ROOT", path, "external_evidence_roots must be an array"
            )
            return
        repo = data.get("source_repo")
        source_repo = (
            Path(repo).resolve()
            if isinstance(repo, str) and Path(repo).is_absolute()
            else None
        )
        for number, value in enumerate(external_roots, 1):
            label = f"external_evidence_roots[{number}]"
            if not isinstance(value, str) or not Path(value).is_absolute():
                self.error(
                    "INDEX_EXTERNAL_ROOT", path, f"{label} must be an absolute path"
                )
                continue
            resolved = Path(value).resolve(strict=False)
            if resolved == Path(resolved.anchor):
                self.error(
                    "INDEX_EXTERNAL_ROOT", path, f"{label} cannot be a filesystem root"
                )
                continue
            task_id = data.get("task_id")
            if not isinstance(task_id, str) or task_id not in resolved.parts:
                self.error(
                    "INDEX_EXTERNAL_ROOT", path, f"{label} must be scoped by task_id"
                )
                continue
            if not resolved.is_dir():
                self.error(
                    "INDEX_EXTERNAL_ROOT", path, f"{label} is not a directory: {value}"
                )
                continue
            if not self._validate_external_root_location(
                resolved, source_repo, label, path
            ):
                continue
            self.external_evidence_roots.append(resolved)

    def _validate_external_root_location(
        self, resolved: Path, source_repo: Path | None, label: str, path: Path
    ) -> bool:
        for name, root in (("source_repo", source_repo), ("task_dir", self.task_dir)):
            if root is not None and (
                self._is_within(resolved, root) or self._is_within(root, resolved)
            ):
                self.error(
                    "INDEX_EXTERNAL_ROOT", path, f"{label} must not overlap {name}"
                )
                return False
        return True

    def _validate_handoff(self, target_state: str) -> None:
        if target_state == "ENV_READY" or "HANDOFF_LOG" not in self.headers:
            return
        header = self.headers["HANDOFF_LOG"]
        expected_owner = EXPECTED_HANDOFF_OWNER[target_state]
        if header.get("latest_owner") != expected_owner:
            self.error(
                "HANDOFF_OWNER",
                ARTIFACTS["HANDOFF_LOG"].path,
                f"latest_owner must be {expected_owner}",
            )
        if header.get("latest_status") != "PASS":
            self.error(
                "HANDOFF_STATUS",
                ARTIFACTS["HANDOFF_LOG"].path,
                "latest_status must be PASS",
            )
        if header.get("latest_source_identity") != self.index.get("source_identity"):
            self.error(
                "HANDOFF_IDENTITY",
                ARTIFACTS["HANDOFF_LOG"].path,
                "latest source identity is not current",
            )

    def _validate_index_entry(
        self,
        name: str,
        path: Path,
        header: dict[str, Any],
        summary: ArtifactSummary,
    ) -> None:
        artifacts = self.index.get("artifacts")
        if not isinstance(artifacts, dict):
            return
        entry = artifacts.get(name)
        if not isinstance(entry, dict):
            self.error(
                "INDEX_ARTIFACT", path, f"task-index artifacts.{name} is missing"
            )
            return
        expected_path = ARTIFACTS[name].path
        if entry.get("path") != expected_path:
            self.error("INDEX_PATH", path, f"indexed path must be {expected_path}")
        if entry.get("owner") != summary.owner:
            self.error(
                "INDEX_OWNER", path, "indexed owner does not match artifact frontmatter"
            )
        if entry.get("status") != summary.status:
            self.error(
                "INDEX_STATUS",
                path,
                "indexed status does not match artifact frontmatter",
            )
        if entry.get("source_identity") != summary.identity:
            self.error(
                "INDEX_IDENTITY",
                path,
                "indexed source_identity does not match artifact frontmatter",
            )
        if entry.get("valid") is not True:
            self.error(
                "INDEX_VALID", path, "required artifact must be marked valid=true"
            )
        self._check_hash(entry.get("sha256"), path, "INDEX_HASH")

    def _validate_index_enums(self, data: dict[str, Any], path: Path) -> None:
        if data.get("schema_version") != 1:
            self.error("INDEX_SCHEMA", path, "schema_version must be 1")
        if data.get("engine") != "AICPU":
            self.error("INDEX_ENGINE", path, "engine must be AICPU")
        if data.get("current_state") not in STATES:
            self.error(
                "INDEX_STATE",
                path,
                f"unknown current_state: {data.get('current_state')!r}",
            )
        repair_round = self._as_int(data.get("repair_round"))
        if repair_round is None or not 0 <= repair_round <= 3:
            self.error(
                "INDEX_REPAIR_ROUND",
                path,
                "repair_round must be an integer from 0 to 3",
            )
        if data.get("pending_action") not in {"NONE", "REPAIR", "REDESIGN", "BLOCKED"}:
            self.error(
                "INDEX_PENDING_ACTION",
                path,
                "pending_action must be NONE, REPAIR, REDESIGN or BLOCKED",
            )
        pending_roles = data.get("pending_roles")
        if not isinstance(pending_roles, list) or not all(
            role in TASK_OWNERS and role != "hcclbot" for role in pending_roles
        ):
            self.error(
                "INDEX_PENDING_ROLES",
                path,
                "pending_roles must be an array of Agent names",
            )
        elif data.get("pending_action") == "NONE" and pending_roles:
            self.error(
                "INDEX_PENDING_ROLES",
                path,
                "pending_roles must be empty when pending_action=NONE",
            )
        elif data.get("pending_action") in {"REPAIR", "REDESIGN"} and not pending_roles:
            self.error(
                "INDEX_PENDING_ROLES",
                path,
                "active recovery requires at least one pending role",
            )

    def _validate_index_fields(self, data: dict[str, Any], path: Path) -> None:
        for key in (
            "schema_version",
            "task_id",
            "engine",
            "requirement",
            "source_repo",
            "source_branch",
            "source_head",
            "source_worktree",
            "source_identity",
            "external_evidence_roots",
            "current_state",
            "repair_round",
            "pending_action",
            "pending_roles",
            "created_at",
            "updated_at",
            "artifacts",
            "dataflow_specs",
            "calls",
            "invalidated_artifacts",
        ):
            if key not in data:
                self.error("INDEX_FIELD", path, f"missing field: {key}")
        self._validate_index_enums(data, path)
        for key in (
            "task_id",
            "requirement",
            "source_branch",
            "source_identity",
            "created_at",
            "updated_at",
        ):
            if not self._nonempty(data.get(key)):
                self.error("INDEX_VALUE", path, f"{key} must be a non-empty string")
        head = data.get("source_head")
        if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{7,64}", head):
            self.error(
                "INDEX_HEAD",
                path,
                "source_head must be a 7-64 character lowercase Git object ID",
            )
        if data.get("source_worktree") not in {"CLEAN", "DIRTY"}:
            self.error("INDEX_WORKTREE", path, "source_worktree must be CLEAN or DIRTY")
        repo = data.get("source_repo")
        if not isinstance(repo, str) or not Path(repo).is_absolute():
            self.error("INDEX_REPO", path, "source_repo must be an absolute path")
        elif not Path(repo).is_dir():
            self.error("INDEX_REPO", path, f"source_repo is not a directory: {repo}")

    def _validate_invalidation(self) -> None:
        artifacts = self.index.get("artifacts")
        invalidated = self.index.get("invalidated_artifacts")
        if not isinstance(artifacts, dict) or not isinstance(invalidated, list):
            return
        for name in ("REVIEW", "TEST_REPORT"):
            path = self.task_dir / ARTIFACTS[name].path
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            header = self._parse_frontmatter(path, text, report_errors=False)
            if header is None:
                continue
            stale = self.artifact_identity(name, header) != self.index.get(
                "source_identity"
            )
            for field, dependency in DEPENDENCIES.get(name, {}).items():
                dep_path = self.task_dir / ARTIFACTS[dependency].path
                if dep_path.is_file() and header.get(field) != self._sha256(dep_path):
                    stale = True
            if not stale:
                continue
            entry = artifacts.get(name)
            if not isinstance(entry, dict) or entry.get("valid") is not False:
                self.error(
                    "INVALIDATION_REQUIRED",
                    path,
                    "stale report must be indexed with valid=false",
                )
            matched = any(
                isinstance(item, dict)
                and item.get("artifact") == name
                and item.get("path") == ARTIFACTS[name].path
                and self._nonempty(item.get("reason"))
                for item in invalidated
            )
            if not matched:
                self.error(
                    "INVALIDATION_REQUIRED",
                    path,
                    "stale report needs an invalidated_artifacts record",
                )

    def _validate_semantics(
        self, name: str, header: dict[str, Any], path: Path
    ) -> None:
        if name == "ENVIRONMENT" and header.get("status") == "PASS":
            self._expect_bool(header, "checks_pass", True, path)
        if (
            name in {"TASK_SPEC", "DESIGN", "PLAN", "TEST_PLAN"}
            and header.get("status") == "FROZEN"
        ):
            self._expect_int(header, "semantic_tbd_count", 0, path)
        if name == "DATAFLOW_SPEC_INDEX":
            self._validate_dataflow(header, path)
        if name == "BASELINE_REPORT" and header.get("status") == "PASS":
            self._expect_bool(header, "evidence_complete", True, path)
            self._expect_int(header, "unresolved_failure_count", 0, path)
            self._expect_bool(header, "install_test_ready", True, path)
        if name == "DEVELOPMENT_LOG" and header.get("status") == "PASS":
            self._expect_int(header, "static_failure_count", 0, path)
        if name == "REVIEW" and header.get("status") == "PASS":
            self._expect_int(header, "blocking_issue_count", 0, path)
        if name == "TEST_REPORT" and header.get("status") == "PASS":
            for field in (
                "build_pass",
                "track_a_pass",
                "track_b_pass",
                "identity_match",
                "environment_clean",
            ):
                self._expect_bool(header, field, True, path)
            self._expect_int(header, "test_failure_count", 0, path)
            self._validate_estimate(header, path)
        if name == "HANDOFF_LOG":
            value = self._as_int(header.get("entry_count"))
            if value is None or value < 1:
                self.error(
                    "HANDOFF_COUNT", path, "entry_count must be a positive integer"
                )

    def _validate_single_call(
        self, call: dict, label: str, seen_ids: set[str], source_repo: Path | None
    ) -> str | None:
        self._validate_call_fields(call, label, seen_ids)
        role = call.get("role")
        if role not in TASK_OWNERS or role == "hcclbot":
            self.error("CALL_ROLE", label, f"invalid Agent role: {role!r}")
        call_state = call.get("target_state")
        if call_state not in CALL_REQUIREMENTS:
            self.error(
                "CALL_STATE", label, f"invalid Agent target_state: {call_state!r}"
            )
        if call.get("status") not in {
            "PASS",
            "FAIL",
            "DESIGN_ISSUE",
            "REVIEW_FAIL",
            "TEST_FAIL",
            "BLOCKED",
        }:
            self.error(
                "CALL_STATUS", label, f"invalid call status: {call.get('status')!r}"
            )
        for field in ("source_identity", "started_at", "ended_at"):
            if not self._nonempty(call.get(field)):
                self.error("CALL_VALUE", label, f"{field} must be a non-empty string")
        outputs = call.get("outputs")
        if (
            not isinstance(outputs, list)
            or not outputs
            or not all(isinstance(item, str) for item in outputs)
        ):
            self.error(
                "CALL_OUTPUT", label, "outputs must be a non-empty array of paths"
            )
        elif role in TASK_OWNERS:
            self._validate_actor_paths(role, outputs, source_repo)
        return call_state if isinstance(call_state, str) else None

    def _validate_call_fields(self, call: dict, label: str, seen_ids: set[str]) -> None:
        for field in (
            "call_id",
            "role",
            "target_state",
            "status",
            "source_identity",
            "started_at",
            "ended_at",
            "outputs",
        ):
            if field not in call:
                self.error("CALL_FIELD", label, f"missing field: {field}")
        call_id = call.get("call_id")
        if not self._nonempty(call_id):
            self.error("CALL_ID", label, "call_id must be a non-empty string")
        elif call_id in seen_ids:
            self.error("CALL_ID", label, f"duplicate call_id: {call_id}")
        else:
            seen_ids.add(call_id)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate AICPU task artifacts before HCCLBot advances state.",
    )
    parser.add_argument(
        "--task-dir", required=True, type=Path, help="AICPU task artifact directory"
    )
    parser.add_argument(
        "--target-state", choices=STATES, help="state whose prerequisites must pass"
    )
    parser.add_argument(
        "--actor",
        choices=tuple(TASK_OWNERS),
        help="actor for write-boundary validation",
    )
    parser.add_argument(
        "--changed",
        nargs="+",
        default=[],
        help="changed paths; absolute or relative to task-index source_repo",
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON result")
    args = parser.parse_args(argv)
    if args.target_state is None and args.actor is None:
        parser.error("at least one of --target-state or --actor is required")
    if args.changed and args.actor is None:
        parser.error("--changed requires --actor")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    validator = Validator(args.task_dir)
    if args.target_state:
        validator.validate_state(args.target_state)
    if args.actor:
        validator.validate_actor(args.actor, args.changed)

    result = {
        "ok": not validator.problems,
        "target_state": args.target_state,
        "actor": args.actor,
        "errors": [problem.__dict__ for problem in validator.problems],
    }
    if args.json:
        logging.info(json.dumps(result, ensure_ascii=False, indent=2))
    elif validator.problems:
        for problem in validator.problems:
            logging.error(f"[{problem.code}] {problem.path}: {problem.message}")
        logging.error(f"FAILED: {len(validator.problems)} error(s)")
    else:
        detail = args.target_state or args.actor
        logging.info(f"PASS: AICPU artifact gate ({detail})")
    return 0 if not validator.problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
