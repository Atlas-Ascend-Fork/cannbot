# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Internal symptom recommendations for deep-analysis submission."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import cast

MAX_RECOMMENDATIONS = 3
STAGE_ORDER = ("structural", "kernel", "refinement", "autotune")
SYMPTOM_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
KB_ROOT_ENV = "CANNBOT_KNOWLEDGE_ROOT"
_KB_PATTERNS_SUBDIRS = (
    "knowledge/ops/{language}/optimizations/patterns",
    "knowledge/ops/{language}/optimizations/operator_optimization",
    "knowledge/ops/{language}/optimizations/techniques",
)
_SECTION = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
_FRONTMATTER = re.compile(r"\A---\n(?P<meta>.*?)\n---\n", re.DOTALL)


class RetrievalError(ValueError):
    """A user-facing retrieval failure with an actionable message."""


def resolve_kb_root(workspace: Path) -> Path | None:
    """Locate the cannbot-knowledge clone provisioned for this workspace."""
    env_root = os.environ.get(KB_ROOT_ENV)
    if env_root and (Path(env_root) / "knowledge").is_dir():
        return Path(env_root)
    for directory in (workspace, *workspace.parents):
        for candidate in sorted(
            directory.glob(".cannbot/dependencies/*/cannbot-knowledge")
        ):
            if (candidate / "knowledge").is_dir():
                return candidate
    return None


def resolve_kb_patterns_dirs(workspace: Path, language: str) -> list[Path]:
    """Return the cannbot-knowledge directories holding pattern cards."""
    kb_root = resolve_kb_root(workspace)
    if kb_root is None:
        return []
    dirs: list[Path] = []
    for subdir in _KB_PATTERNS_SUBDIRS:
        candidate = kb_root / subdir.format(language=language)
        if candidate.is_dir():
            dirs.append(candidate)
    return dirs


def _find_card_path(
    patterns_dirs: list[Path], candidate: str, pattern_paths: dict[str, str]
) -> Path:
    """Resolve a current pattern ID to its declared knowledge-card path."""
    relative = Path(pattern_paths[candidate])
    path = next(
        (
            directory / relative.name
            for directory in patterns_dirs
            if directory.name == relative.parent.name
        ),
        None,
    )
    if path is None or not path.is_file():
        raise RetrievalError(
            f"pattern {candidate!r} routes to missing knowledge card {str(relative)!r}"
        )
    return path


def load_contract(
    contract_path: Path,
) -> tuple[dict[str, dict[str, object]], int, str, dict[str, str]]:
    """Validate the symptom contract the same way the runtime validator does."""
    payload = _read_contract_payload(contract_path)
    symptoms = payload.get("symptoms")
    if not isinstance(symptoms, list):
        raise RetrievalError("symptom contract must contain a symptoms array")
    result: dict[str, dict[str, object]] = {}
    for item in cast(list[object], symptoms):
        _add_validated_symptom(result, item)
    max_submitted, unknown_id = _contract_settings(payload, result)
    result[unknown_id] = {
        "id": unknown_id,
        "summary": "No current symptom matches the evidence.",
    }
    paths = payload.get("pattern_paths")
    if not isinstance(paths, dict):
        raise RetrievalError("symptom contract must contain pattern_paths")
    pattern_paths: dict[str, str] = {}
    for candidate, relative in cast(dict[object, object], paths).items():
        if not isinstance(candidate, str) or not isinstance(relative, str):
            raise RetrievalError("pattern_paths must map pattern IDs to card paths")
        if not re.fullmatch(
            r"(?:patterns|operator_optimization|techniques)/[a-z0-9_-]+\.md", relative
        ) or Path(relative).name in {"index.md", "README.md"}:
            raise RetrievalError(
                f"invalid knowledge card path for pattern {candidate!r}"
            )
        pattern_paths[candidate] = relative
    candidates = {
        str(candidate)
        for entry in result.values()
        for candidate in cast(list[object], entry.get("candidate_patterns", []))
    }
    missing = candidates - pattern_paths.keys()
    if missing:
        raise RetrievalError(
            "missing pattern_paths mapping: " + ", ".join(sorted(missing))
        )
    return result, max_submitted, unknown_id, pattern_paths


def _read_contract_payload(contract_path: Path) -> dict[str, object]:
    try:
        raw = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetrievalError(
            f"invalid symptom contract: {contract_path} ({exc})"
        ) from exc
    if not isinstance(raw, dict):
        raise RetrievalError("symptom contract must be a JSON object")
    return cast(dict[str, object], raw)


def _add_validated_symptom(result: dict[str, dict[str, object]], item: object) -> None:
    if not isinstance(item, dict):
        raise RetrievalError("symptom contract contains an invalid symptom")
    typed_item = cast(dict[str, object], item)
    identifier = typed_item.get("id")
    if not isinstance(identifier, str):
        raise RetrievalError("symptom contract contains an invalid symptom")
    if identifier in result or not SYMPTOM_ID_RE.fullmatch(identifier):
        raise RetrievalError(
            f"symptom contract contains duplicate or invalid ID: {identifier}"
        )
    for key in ("summary", "evidence_hint", "common_non_matches", "candidate_patterns"):
        if key not in typed_item:
            raise RetrievalError(
                f"symptom contract symptom {identifier} is missing {key}"
            )
    _validate_symptom_text_fields(identifier, typed_item)
    _validate_symptom_list_fields(identifier, typed_item)
    result[identifier] = typed_item


def _validate_symptom_text_fields(
    identifier: str, typed_item: dict[str, object]
) -> None:
    if not isinstance(typed_item["summary"], str) or not isinstance(
        typed_item["evidence_hint"], str
    ):
        raise RetrievalError(
            f"symptom contract symptom {identifier} has invalid text fields"
        )


def _validate_symptom_list_fields(
    identifier: str, typed_item: dict[str, object]
) -> None:
    for key in ("common_non_matches", "candidate_patterns"):
        value = typed_item[key]
        if not isinstance(value, list):
            raise RetrievalError(
                f"symptom contract symptom {identifier} has invalid {key}"
            )
        entries = cast(list[object], value)
        if any(not isinstance(entry, str) or not entry for entry in entries):
            raise RetrievalError(
                f"symptom contract symptom {identifier} has invalid {key}"
            )


def _contract_settings(
    payload: dict[str, object], symptoms: dict[str, dict[str, object]]
) -> tuple[int, str]:
    max_submitted = payload.get("max_submitted", 5)
    unknown_id = payload.get("unknown_id", "unknown")
    if (
        not isinstance(max_submitted, int)
        or isinstance(max_submitted, bool)
        or max_submitted < 1
    ):
        raise RetrievalError(
            "symptom contract max_submitted must be a positive integer"
        )
    if not isinstance(unknown_id, str) or not unknown_id:
        raise RetrievalError("symptom contract unknown_id must be a non-empty string")
    if not SYMPTOM_ID_RE.fullmatch(unknown_id):
        raise RetrievalError(f"symptom contract unknown_id is invalid: {unknown_id}")
    if unknown_id in symptoms:
        raise RetrievalError(
            f"symptom contract reserves duplicate unknown_id: {unknown_id}"
        )
    return max_submitted, unknown_id


def validate_candidate_patterns(
    symptoms: dict[str, dict[str, object]],
    patterns_dirs: list[Path],
    pattern_paths: dict[str, str],
) -> None:
    for entry in symptoms.values():
        for candidate in cast(list[object], entry.get("candidate_patterns", [])):
            _find_card_path(patterns_dirs, str(candidate), pattern_paths)


def normalize_symptoms(
    symptoms: list[str],
    contract: dict[str, dict[str, object]],
    max_submitted: int,
    unknown_id: str,
) -> list[str]:
    normalized = [item.strip() for item in symptoms]
    if any(not item for item in normalized):
        raise RetrievalError("symptom values must not be empty")
    if len(normalized) != len(set(normalized)):
        raise RetrievalError("symptoms must not contain duplicates")
    if len(normalized) > max_submitted:
        raise RetrievalError(f"at most {max_submitted} symptoms may be submitted")
    unknown_items = [item for item in normalized if item not in contract]
    if unknown_items:
        raise RetrievalError("unknown symptom ID(s): " + ", ".join(unknown_items))
    if unknown_id in normalized and len(normalized) != 1:
        raise RetrievalError(
            f"{unknown_id} must be submitted alone when no listed symptom applies"
        )
    return normalized


def load_pattern_ranks(
    index_path: Path, pattern_ids: set[str]
) -> dict[str, tuple[str, str]]:
    """Read stage and priority from the plugin's synchronized triage tree."""
    try:
        text = index_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RetrievalError(
            f"cannot read pattern index: {index_path} ({exc})"
        ) from exc
    stages: dict[str, str] = {}
    priorities: dict[str, str] = {}
    identifier: str | None = None
    stage: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            heading = re.fullmatch(r"## \d+\. ([A-Za-z]+):.*", line)
            if heading is None or heading[1].lower() not in STAGE_ORDER:
                raise RetrievalError(f"invalid stage heading in pattern index: {line}")
            stage = heading[1].lower()
            identifier = None
        elif line.startswith("#### "):
            entry = re.fullmatch(r"#### `([a-z0-9]+(?:-[a-z0-9]+)*)`", line)
            if entry is None or stage is None:
                raise RetrievalError(
                    f"invalid or ungrouped pattern index entry: {line}"
                )
            identifier = str(entry[1])
            if identifier in stages:
                raise RetrievalError(f"duplicate pattern index entry: {identifier}")
            stages[identifier] = stage
        elif line.startswith("- Priority:"):
            priority = line.removeprefix("- Priority:").strip()
            if (
                identifier is None
                or identifier in priorities
                or priority not in {"high", "normal"}
            ):
                raise RetrievalError(
                    f"invalid or duplicate priority in pattern index: {line}"
                )
            priorities[identifier] = priority
    return _validated_pattern_ranks(stages, priorities, pattern_ids)


def _validated_pattern_ranks(
    stages: dict[str, str],
    priorities: dict[str, str],
    pattern_ids: set[str],
) -> dict[str, tuple[str, str]]:
    missing = pattern_ids - stages.keys()
    extra = stages.keys() - pattern_ids
    if missing or extra:
        raise RetrievalError(
            f"pattern index differs from pattern_paths: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    if stages.keys() != priorities.keys():
        raise RetrievalError(
            "pattern index must declare one priority for every pattern"
        )
    return {
        identifier: (stage, priorities[identifier])
        for identifier, stage in stages.items()
    }


def _sections(body: str) -> dict[str, str]:
    matches = list(_SECTION.finditer(body))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group("title").strip()] = body[start:end].strip()
    return sections


def _use_when(value: str) -> list[str]:
    # Preserve prose and code blocks while keeping the plugin's list-shaped API.
    return [value.strip()] if value.strip() else []


def _parse_card(path: Path) -> dict[str, object]:
    """Parse one pattern card; mirrors the runtime card parser's contract."""
    text = path.read_text(encoding="utf-8")
    metadata: dict[str, str] = {}
    body = text
    front = _FRONTMATTER.match(text)
    if front is not None:
        body_start = front.end()
        body = text[body_start:]
        for line in front.group("meta").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()
    identifier = path.stem
    declared = metadata.get("id")
    if declared is not None and declared != identifier:
        raise RetrievalError(
            f"pattern card {path.name} declares id {declared!r} which differs "
            f"from its file stem; rename the card or drop the id"
        )
    sections = _sections(body)
    summary = sections.get("Summary", "").split("\n\n", 1)[0].strip().replace("\n", " ")
    return {
        "pattern": identifier,
        "card": str(path),
        "summary": summary,
        "use_when": _use_when(sections.get("Use When", "")),
    }


def retrieve(
    symptoms: list[str],
    *,
    contract_path: Path,
    patterns_dirs: list[Path],
    exclude: list[str] | None = None,
) -> list[dict[str, object]]:
    contract, _max_submitted, unknown_id, pattern_paths = load_contract(contract_path)
    validate_candidate_patterns(contract, patterns_dirs, pattern_paths)
    normalized = normalize_symptoms(symptoms, contract, _max_submitted, unknown_id)
    if unknown_id in normalized:
        return []
    ranks = load_pattern_ranks(
        contract_path.with_name("pattern_index.md"), set(pattern_paths)
    )
    excluded = set(exclude or [])
    candidate_ids = {
        pattern_id
        for symptom in normalized
        for pattern_id in cast(list[str], contract[symptom]["candidate_patterns"])
    }
    candidates: list[dict[str, object]] = []
    for candidate_id in sorted(candidate_ids - excluded):
        path = _find_card_path(patterns_dirs, candidate_id, pattern_paths)
        card = _parse_card(path)
        card["pattern"] = candidate_id
        matched = sorted(
            symptom
            for symptom in normalized
            if candidate_id in cast(list[str], contract[symptom]["candidate_patterns"])
        )
        card["matched_symptoms"] = matched
        card["_sort"] = (
            STAGE_ORDER.index(ranks[candidate_id][0]),
            -len(matched),
            0 if ranks[candidate_id][1] == "high" else 1,
            candidate_id,
        )
        candidates.append(card)
    candidates.sort(key=lambda item: cast(tuple[object, ...], item["_sort"]))
    results: list[dict[str, object]] = []
    for card in candidates[:MAX_RECOMMENDATIONS]:
        results.append(
            {
                "pattern": card["pattern"],
                "card": card["card"],
                "summary": card["summary"],
                "use_when": card["use_when"],
                "matched_symptoms": card["matched_symptoms"],
            }
        )
    return results


def recommend(
    *,
    workspace: Path,
    language: str,
    contract_path: Path,
    symptoms: list[str],
    exclude: list[str],
) -> list[dict[str, object]]:
    """Read external cards for the owning workspace without resolving skill links."""
    patterns_dirs = resolve_kb_patterns_dirs(workspace, language)
    if not patterns_dirs:
        raise RetrievalError("cannbot-knowledge pattern library is unavailable")
    results = retrieve(
        symptoms,
        contract_path=contract_path,
        patterns_dirs=patterns_dirs,
        exclude=exclude,
    )
    return [
        {
            "id": item["pattern"],
            "path": item["card"],
            "summary": item["summary"],
            "use_when": item["use_when"],
            "matched_symptoms": item["matched_symptoms"],
        }
        for item in results
    ]
