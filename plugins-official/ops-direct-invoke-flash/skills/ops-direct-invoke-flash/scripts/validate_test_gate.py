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
"""Validate ops-direct-invoke-flash test gate evidence.

Switch: `harness.test_gate` (on/off, default off) read from the Team AGENTS.md.

When `on`, the gate is bound to the REAL skill artifacts so it cannot be passed
with a hand-written "shadow" result file:

  * cases_paths  — the cases the skills actually generated (the case-id ground
                   truth): blackbox `*_L0/L1/L2_test_cases.csv` (ascendc-st-design),
                   whitebox `S5_mapped_cases_low.json` (ascendc-whitebox-design).
  * result_paths — the real execution results: blackbox ST result JSON
                   ({case_id,status}); whitebox TTK `*_result.csv` (precision_status).
  * log_paths    — a non-empty execution log (proof the cases were actually run).

Binding rule (per branch): every generated case_id must appear in the results
with a passing status; a result that omits a generated case, marks one non-pass,
or references a case_id that is NOT in the generated set fails the gate. The
self-reported `status` in test_gate.json is never trusted.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)
PASSED_VALUES = {"passed", "pass", "success", "ok", "通过", "✅通过"}
ID_KEYS = ("case_id", "testcase_name", "id")
STATUS_KEYS = ("precision_status", "status", "result")
BLACKBOX_PROVENANCE = "test-harness/blackbox/WORKFLOW_PROVENANCE.json"
WHITEBOX_PROVENANCE = "test-harness/whitebox/WORKFLOW_PROVENANCE.json"
TEST_GATE_RESULT = "test-harness/results/test_gate.json"
MAX_LISTED = 20
CONFIG_FILENAMES = ("CLAUDE.md", "AGENTS.md")
PLUGIN_NAME = "ops-direct-invoke-flash"
MARKER_START = re.compile(
    rf"(?m)^<!--\s*cannbot:{re.escape(PLUGIN_NAME)}:start\s*-->[ \t]*$"
)
PROJECT_ROOT_MARKERS = (".git", ".cannbot")


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _frontmatter(text: str) -> str:
    """Return the YAML frontmatter that configures this plugin, or "" when there is none.

    The shared installer appends the plugin's instructions inside a
    `<!-- cannbot:<plugin>:start -->` block, after whatever the project config
    already held, so that block is located first and its frontmatter parsed. A
    file whose frontmatter is at the top (the plugin's own AGENTS.md) still works.
    """
    marker = MARKER_START.search(text)
    if marker is not None:
        text = text[marker.end() :].lstrip("\n")
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end != -1 else ""


def _config_in(directory: Path) -> Path | None:
    """Return the config file in `directory` that declares `harness.test_gate`.

    A file carrying this plugin's marker block wins, because that is the one the
    installer wrote; otherwise filename order breaks the tie.
    """
    candidates = [
        path
        for path in (directory / name for name in CONFIG_FILENAMES)
        if path.is_file() and _read_test_gate_config(path) is not None
    ]
    for candidate in candidates:
        text = _read_text(candidate)
        if text is not None and MARKER_START.search(text):
            return candidate
    return candidates[0] if candidates else None


def _is_within(path: Path, ancestor: Path) -> bool:
    return path == ancestor or ancestor in path.parents


def _find_config_file(start: Path, operator_doc_dir: Path | None = None) -> Path | None:
    """Return the nearest config declaring `harness.test_gate` at or above `start`.

    The walk stops at the project root (the first directory holding `.git` or
    `.cannbot`) so an unrelated config further up — a user-level `CLAUDE.md`, say
    — cannot supply the switch. Anything inside `operator_doc_dir` is ignored:
    that is the tree this workflow writes into, so it must not be able to
    configure the gate that audits it.
    """
    start = start.resolve()
    excluded = operator_doc_dir.resolve() if operator_doc_dir is not None else None
    for directory in (start, *start.parents):
        if excluded is None or not _is_within(directory, excluded):
            found = _config_in(directory)
            if found is not None:
                return found
        if any((directory / marker).exists() for marker in PROJECT_ROOT_MARKERS):
            break
    return None


def _normalize_config_value(value: str) -> str:
    return value.split("#", 1)[0].strip().strip("\"'")


def _read_test_gate_config(config_path: Path) -> str | None:
    """Return the `harness.test_gate` value, or None when the file declares none."""
    text = _read_text(config_path) if config_path.is_file() else None
    if text is None:
        return None
    frontmatter = _frontmatter(text)
    inline = re.search(r"(?m)^harness:\s*\{[^}]*test_gate\s*:\s*([^,}#]+)", frontmatter)
    if inline:
        return _normalize_config_value(inline.group(1))
    in_harness = False
    for raw_line in frontmatter.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if re.match(r"^\S", line):
            if line.startswith("harness:"):
                in_harness = True
                continue
            if in_harness:
                break
        if in_harness:
            m = re.match(r"\s+test_gate\s*:\s*(.+)$", line)
            if m:
                return _normalize_config_value(m.group(1))
    return None


def _first_key(row: dict, keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in row and str(row[k]).strip() != "":
            return row[k]
    return None


def _is_pass(raw: Any) -> bool:
    text = str(raw).strip()
    return text.lower() in PASSED_VALUES or text in PASSED_VALUES


class TestGateValidator:
    def __init__(
        self,
        plugin_root: Path,
        operator_doc_dir: Path,
        config_path: Path | None = None,
    ) -> None:
        self.plugin_root = plugin_root
        self.operator_doc_dir = operator_doc_dir
        self.errors: list[str] = []
        self.summary: dict[str, str] = {}
        self.test_gate_source = (
            config_path if config_path is not None else _config_in(plugin_root)
        )
        value = (
            _read_test_gate_config(self.test_gate_source)
            if self.test_gate_source is not None
            else None
        )
        self.test_gate = value if value is not None else "off"

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def load_json(self, path: Path) -> Any | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self.add_error(f"invalid JSON in {path.name}: {exc}")
            return None

    def validate_provenance(self, rel_path: str, expected_skill: str) -> None:
        path = self._safe_path(rel_path, f"{expected_skill} provenance")
        if path is None:
            return
        data = self.load_json(path)
        if not isinstance(data, dict):
            if data is not None:
                self.add_error(f"{rel_path} must be a JSON object")
            return
        if str(data.get("skill", "")).strip() != expected_skill:
            self.add_error(
                f"{rel_path} skill must be {expected_skill!r}, got {str(data.get('skill', '')).strip()!r}"
            )
        workflow = str(data.get("workflow", "")).strip()
        if expected_skill not in workflow:
            self.add_error(
                f"{rel_path} workflow must reference {expected_skill}, got {workflow!r}"
            )

    def case_ids(self, rel_paths: Any, branch: str) -> set[str]:
        ids: set[str] = set()
        if not isinstance(rel_paths, list) or not rel_paths:
            self.add_error(
                f"{TEST_GATE_RESULT} {branch}.cases_paths must be a non-empty list"
            )
            return ids
        for rel in rel_paths:
            path = self._safe_path(rel, f"{branch} cases")
            if path is None:
                continue
            for row in self._rows(path):
                cid = _first_key(row, ID_KEYS)
                if cid is not None:
                    ids.add(str(cid).strip())
        if not ids:
            self.add_error(
                f"{branch} generated cases yielded no case ids (checked {rel_paths})"
            )
        return ids

    def result_status(self, rel_paths: Any, branch: str) -> dict[str, str]:
        results: dict[str, str] = {}
        if not isinstance(rel_paths, list) or not rel_paths:
            self.add_error(
                f"{TEST_GATE_RESULT} {branch}.result_paths must be a non-empty list"
            )
            return results
        for rel in rel_paths:
            path = self._safe_path(rel, f"{branch} result")
            if path is None:
                continue
            for row in self._rows(path):
                cid = _first_key(row, ID_KEYS)
                status = _first_key(row, STATUS_KEYS)
                if cid is None:
                    self.add_error(f"{branch} result row lacks a case id ({path.name})")
                    continue
                if status is None:
                    self.add_error(
                        f"{branch} result for case {str(cid).strip()} lacks a status ({path.name})"
                    )
                    continue
                results[str(cid).strip()] = str(status).strip()
        return results

    def require_logs(self, rel_paths: Any, branch: str) -> None:
        if not isinstance(rel_paths, list) or not rel_paths:
            self.add_error(
                f"{TEST_GATE_RESULT} {branch}.log_paths must be a non-empty list (execution evidence)"
            )
            return
        for rel in rel_paths:
            self._safe_path(rel, f"{branch} execution log")

    def validate_branch(self, branch: str, branch_data: dict[str, Any]) -> None:
        gen_ids = self.case_ids(branch_data.get("cases_paths"), branch)
        results = self.result_status(branch_data.get("result_paths"), branch)
        self.require_logs(branch_data.get("log_paths"), branch)

        if not gen_ids or not results:
            return  # specific errors already recorded

        missing = sorted(gen_ids - results.keys())
        if missing:
            self.add_error(
                f"{branch} results do not cover generated cases "
                f"(missing {len(missing)}): {missing[:MAX_LISTED]}"
            )
        not_pass = sorted(
            cid for cid in gen_ids & results.keys() if not _is_pass(results[cid])
        )
        if not_pass:
            self.add_error(
                f"{branch} cases did not pass ({len(not_pass)}): "
                + ", ".join(f"{cid}={results[cid]!r}" for cid in not_pass[:MAX_LISTED])
            )
        unknown = sorted(results.keys() - gen_ids)
        if unknown:
            self.add_error(
                f"{branch} results reference case ids NOT in the generated set "
                f"(possible fabricated evidence; {len(unknown)}): {unknown[:MAX_LISTED]}"
            )

    def validate_test_gate_result(self) -> None:
        path = self._safe_path(TEST_GATE_RESULT, "test_gate")
        if path is None:
            return
        data = self.load_json(path)
        if not isinstance(data, dict):
            if data is not None:
                self.add_error(f"{TEST_GATE_RESULT} must be a JSON object")
            return
        for branch in ("blackbox", "whitebox"):
            branch_data = data.get(branch)
            if not isinstance(branch_data, dict):
                self.add_error(f"{TEST_GATE_RESULT} missing {branch} object")
                continue
            self.validate_branch(branch, branch_data)

    def validate_test_gate(self) -> None:
        if self.test_gate_source is None:
            # "I could not find the switch" must not be reported as "the switch is off":
            # a mis-resolved root would otherwise pass the gate having checked nothing.
            self.add_error(
                "no readable harness.test_gate setting found under "
                f"{self.plugin_root}; cannot confirm the gate is off"
            )
            self.summary["test_gate"] = "config_not_found"
            return
        if self.test_gate not in {"on", "off"}:
            self.add_error(
                f"harness.test_gate must be 'on' or 'off', got {self.test_gate!r}"
            )
            return
        if self.test_gate == "off":
            self.summary["test_gate"] = "skipped_by_config"
            return
        self.validate_provenance(BLACKBOX_PROVENANCE, "ascendc-st-design")
        self.validate_provenance(WHITEBOX_PROVENANCE, "ascendc-whitebox-design")
        self.validate_test_gate_result()
        if not self.errors:
            self.summary.update(
                {"test_gate": "passed", "blackbox": "passed", "whitebox": "passed"}
            )

    def print_result(self) -> int:
        LOGGER.info("test_gate: %s", self.test_gate)
        LOGGER.info(
            "test_gate config: %s",
            self.test_gate_source
            if self.test_gate_source is not None
            else f"not found under {self.plugin_root}",
        )
        if self.summary:
            LOGGER.info(
                "summary: %s",
                json.dumps(self.summary, ensure_ascii=False, sort_keys=True),
            )
        if self.errors:
            LOGGER.info("errors:")
            for error in self.errors:
                LOGGER.info("- %s", error)
            LOGGER.info("STATUS: FAILED")
            return 1
        LOGGER.info("STATUS: PASSED")
        return 0

    def _safe_path(self, rel_path: str, label: str) -> Path | None:
        """Resolve rel_path under the operator dir; reject escapes / missing / empty."""
        if not isinstance(rel_path, str) or not rel_path.strip():
            self.add_error(f"{label} contains an invalid path: {rel_path!r}")
            return None
        rel_path = rel_path.strip()
        path = (self.operator_doc_dir / rel_path).resolve()
        try:
            path.relative_to(self.operator_doc_dir.resolve())
        except ValueError:
            self.add_error(f"{label} path escapes operator doc dir: {rel_path}")
            return None
        if not path.is_file():
            self.add_error(f"{label} path is missing: {rel_path}")
            return None
        if path.stat().st_size == 0:
            self.add_error(f"{label} path is empty: {rel_path}")
            return None
        return path

    def _rows(self, path: Path) -> list[dict]:
        """Return a list of record dicts from a .csv or .json file."""
        if path.suffix.lower() == ".csv":
            try:
                with path.open(newline="", encoding="utf-8") as fh:
                    return list(csv.DictReader(fh))
            except (csv.Error, OSError) as exc:
                self.add_error(f"invalid CSV in {path.name}: {exc}")
                return []
        data = self.load_json(path)
        if isinstance(data, dict):
            entries = data.get("cases", data.get("results", []))
        elif isinstance(data, list):
            entries = data
        else:
            entries = []
        if not isinstance(entries, list):
            self.add_error(f"{path.name} must contain a cases/results list")
            return []
        return [e for e in entries if isinstance(e, dict)]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-doc-dir", required=True, type=Path)
    parser.add_argument(
        "--plugin-root",
        type=Path,
        default=None,
        help="directory holding the AGENTS.md/CLAUDE.md that declares harness.test_gate; "
        "defaults to the nearest one at or above --operator-doc-dir, "
        "else the plugin directory this script ships in",
    )
    return parser.parse_args(argv)


def resolve_config_file(
    plugin_root: Path | None, operator_doc_dir: Path
) -> Path | None:
    """Locate the config file whose `harness.test_gate` governs this run.

    An explicit --plugin-root always wins. Otherwise search upward from the
    operator project, so the switch stays editable in an installed project; fall
    back to this script's own plugin directory for an in-repo run. The file is
    returned, not its directory, so discovery and consumption cannot disagree.
    """
    if plugin_root is not None:
        return _config_in(plugin_root.resolve())
    discovered = _find_config_file(operator_doc_dir, operator_doc_dir)
    if discovered is not None:
        return discovered
    return _config_in(Path(__file__).resolve().parents[3])


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    args = parse_args(argv)
    operator_doc_dir = args.operator_doc_dir.resolve()
    config_path = resolve_config_file(args.plugin_root, operator_doc_dir)
    plugin_root = (
        config_path.parent
        if config_path is not None
        else (args.plugin_root or Path(__file__).resolve().parents[3]).resolve()
    )
    validator = TestGateValidator(plugin_root, operator_doc_dir, config_path)
    if not args.operator_doc_dir.is_dir():
        validator.add_error(
            f"operator doc directory does not exist: {args.operator_doc_dir.resolve()}"
        )
    else:
        validator.validate_test_gate()
    return validator.print_result()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
