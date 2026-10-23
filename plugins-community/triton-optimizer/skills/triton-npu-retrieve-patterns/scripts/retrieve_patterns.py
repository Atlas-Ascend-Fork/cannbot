# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Retrieve optimization patterns and query the symptom vocabulary.

Subcommands:

    list               every symptom ID with its one-line summary
    info <id>          one full symptom entry
    patterns <id>      the candidate pattern cards for one symptom
    retrieve           map submitted symptom IDs to pattern recommendations

Retrieval is a deterministic, offline mapping through the language knowledge
skill's symptom contract. Symptom submission and recommendation history stay
with the ``triton-npu-optimize-state`` skill; this script only maps IDs to
cards.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import cast

MAX_RECOMMENDATIONS = 3
STAGE_ORDER = ("structural", "kernel", "refinement", "autotune")
DISCLAIMER = "Recommendations only; judge applicability before adopting a pattern."
BACKEND_SKILL_DIRS = (".codex", ".claude", ".agents", ".opencode", ".pi", ".openhands", ".trae")
SYMPTOM_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
KB_ROOT_ENV = "CANNBOT_KNOWLEDGE_ROOT"
_KB_PATTERNS_SUBDIRS = (
    "knowledge/ops/{language}/optimizations/patterns",
    "knowledge/ops/{language}/optimizations/operator_optimization",
)
_SECTION = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
_BULLET = re.compile(r"^(?:-\s+|\d+\.\s+)(?P<item>.+?)\s*$")
_FRONTMATTER = re.compile(r"\A---\n(?P<meta>.*?)\n---\n", re.DOTALL)


class RetrievalError(Exception):
    """A user-facing retrieval failure with an actionable message."""


def resolve_knowledge_dir(language: str, workspace: Path) -> Path:
    """Locate the staged ``<language>-npu-optimize-knowledge`` skill (symptom contract owner)."""
    skill_name = f"{language}-npu-optimize-knowledge"
    for backend in BACKEND_SKILL_DIRS:
        candidate = workspace / backend / "skills" / skill_name
        if (candidate / "references" / "symptom-contract.json").is_file():
            return candidate
    repository_root = Path(__file__).resolve().parents[4]
    fallback = repository_root / "skills" / language / skill_name
    if (fallback / "references" / "symptom-contract.json").is_file():
        return fallback
    raise RetrievalError(
        f"staged {skill_name} skill is unavailable under {workspace}; "
        "pass --language <name> if the session uses another kernel language"
    )


def resolve_kb_root(workspace: Path) -> Path | None:
    """Locate the cannbot-knowledge clone provisioned for this workspace."""
    env_root = os.environ.get(KB_ROOT_ENV)
    if env_root and (Path(env_root) / "knowledge").is_dir():
        return Path(env_root)
    for directory in (workspace, *workspace.parents):
        for candidate in sorted(directory.glob(".cannbot/dependencies/*/cannbot-knowledge")):
            if (candidate / "knowledge").is_dir():
                return candidate
    return None


def resolve_kb_patterns_dirs(workspace: Path, language: str) -> list[Path]:
    """Return the cannbot-knowledge directories holding pattern cards."""
    kb_root = resolve_kb_root(workspace)
    if kb_root is None:
        return []
    dirs = []
    for subdir in _KB_PATTERNS_SUBDIRS:
        candidate = kb_root / subdir.format(language=language)
        if candidate.is_dir():
            dirs.append(candidate)
    return dirs


def _find_card_path(patterns_dirs: list[Path], candidate: str) -> Path | None:
    """Find one pattern card by contract name (kebab-case) or KB file name (snake_case)."""
    for directory in patterns_dirs:
        for name in (f"{candidate}.md", f"{candidate.replace('-', '_')}.md"):
            path = directory / name
            if path.is_file():
                return path
    return None


def load_contract(contract_path: Path) -> tuple[dict[str, dict[str, object]], int, str]:
    """Validate the symptom contract the same way the runtime validator does."""
    payload = _read_contract_payload(contract_path)
    symptoms = payload.get("symptoms")
    if not isinstance(symptoms, list):
        raise RetrievalError("symptom contract must contain a symptoms array")
    result: dict[str, dict[str, object]] = {}
    for item in cast(list[object], symptoms):
        _add_validated_symptom(result, item)
    max_submitted, unknown_id = _contract_settings(payload, result)
    result[unknown_id] = {"id": unknown_id, "summary": "No current symptom matches the evidence."}
    return result, max_submitted, unknown_id


def _read_contract_payload(contract_path: Path) -> dict[str, object]:
    try:
        raw = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetrievalError(f"invalid symptom contract: {contract_path} ({exc})") from exc
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
        raise RetrievalError(f"symptom contract contains duplicate or invalid ID: {identifier}")
    for key in ("summary", "evidence_hint", "common_non_matches", "candidate_patterns"):
        if key not in typed_item:
            raise RetrievalError(f"symptom contract symptom {identifier} is missing {key}")
    _validate_symptom_text_fields(identifier, typed_item)
    _validate_symptom_list_fields(identifier, typed_item)
    result[identifier] = typed_item


def _validate_symptom_text_fields(identifier: str, typed_item: dict[str, object]) -> None:
    if not isinstance(typed_item["summary"], str) or not isinstance(typed_item["evidence_hint"], str):
        raise RetrievalError(f"symptom contract symptom {identifier} has invalid text fields")


def _validate_symptom_list_fields(identifier: str, typed_item: dict[str, object]) -> None:
    for key in ("common_non_matches", "candidate_patterns"):
        value = typed_item[key]
        if not isinstance(value, list):
            raise RetrievalError(f"symptom contract symptom {identifier} has invalid {key}")
        entries = cast(list[object], value)
        if any(not isinstance(entry, str) or not entry for entry in entries):
            raise RetrievalError(f"symptom contract symptom {identifier} has invalid {key}")


def _contract_settings(
    payload: dict[str, object], symptoms: dict[str, dict[str, object]]
) -> tuple[int, str]:
    max_submitted = payload.get("max_submitted", 5)
    unknown_id = payload.get("unknown_id", "unknown")
    if not isinstance(max_submitted, int) or isinstance(max_submitted, bool) or max_submitted < 1:
        raise RetrievalError("symptom contract max_submitted must be a positive integer")
    if not isinstance(unknown_id, str) or not unknown_id:
        raise RetrievalError("symptom contract unknown_id must be a non-empty string")
    if not SYMPTOM_ID_RE.fullmatch(unknown_id):
        raise RetrievalError(f"symptom contract unknown_id is invalid: {unknown_id}")
    if unknown_id in symptoms:
        raise RetrievalError(f"symptom contract reserves duplicate unknown_id: {unknown_id}")
    return max_submitted, unknown_id


def validate_candidate_patterns(
    symptoms: dict[str, dict[str, object]], patterns_dirs: list[Path]
) -> None:
    for entry in symptoms.values():
        for candidate in cast(list[object], entry.get("candidate_patterns", [])):
            if _find_card_path(patterns_dirs, str(candidate)) is None:
                raise RetrievalError(
                    f"symptom {entry['id']!r} routes to missing pattern card "
                    f"{candidate!r} under {patterns_dirs}"
                )


def normalize_symptoms(
    symptoms: list[str], contract: dict[str, dict[str, object]], max_submitted: int, unknown_id: str
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
        raise RetrievalError(f"{unknown_id} must be submitted alone when no listed symptom applies")
    return normalized


def _sections(body: str) -> dict[str, str]:
    matches = list(_SECTION.finditer(body))
    return {
        match.group("title").strip(): body[
            match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(body)
        ].strip()
        for index, match in enumerate(matches)
    }


def _bullets(value: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    for raw_line in value.splitlines():
        line = raw_line.strip()
        match = _BULLET.match(line)
        if match:
            if current:
                items.append(" ".join(current))
            current = [match.group("item").strip()]
        elif current and raw_line[:1].isspace() and line:
            current.append(line)
        elif not line and current:
            items.append(" ".join(current))
            current = []
    if current:
        items.append(" ".join(current))
    return items


def _parse_card(path: Path) -> dict[str, object]:
    """Parse one pattern card; mirrors the runtime card parser's contract."""
    text = path.read_text(encoding="utf-8")
    metadata: dict[str, str] = {}
    body = text
    front = _FRONTMATTER.match(text)
    if front is not None:
        body = text[front.end():]
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
        "use_when": _bullets(sections.get("Use When", "")),
        "_priority": metadata.get("priority", "normal"),
        "_stage": metadata.get("optimization_stage", ""),
    }


def retrieve(
    symptoms: list[str],
    *,
    contract_path: Path,
    patterns_dirs: list[Path],
    exclude: list[str] | None = None,
) -> list[dict[str, object]]:
    contract, _max_submitted, unknown_id = load_contract(contract_path)
    normalized = normalize_symptoms(symptoms, contract, _max_submitted, unknown_id)
    if unknown_id in normalized:
        return []
    excluded = {item.replace("_", "-") for item in (exclude or [])}
    candidate_ids = {
        pattern_id
        for symptom in normalized
        for pattern_id in cast(list[str], contract[symptom]["candidate_patterns"])
    }
    candidates: list[dict[str, object]] = []
    for patterns_dir in patterns_dirs:
        for path in sorted(patterns_dir.glob("*.md")):
            if path.name in {"README.md", "index.md"}:
                continue
            card = _parse_card(path)
            # Contract candidate IDs are kebab-case; cannbot-knowledge card files are snake_case.
            card_id = str(card["pattern"]).replace("_", "-")
            if card_id not in candidate_ids or card_id in excluded:
                continue
            matched = sorted(
                symptom
                for symptom in normalized
                if card_id in cast(list[str], contract[symptom]["candidate_patterns"])
            )
            card["matched_symptoms"] = matched
            card["_sort"] = (
                STAGE_ORDER.index(str(card["_stage"])) if str(card["_stage"]) in STAGE_ORDER else 99,
                -len(matched),
                0 if card["_priority"] == "high" else 1,
                card_id,
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


def render_markdown(results: list[dict[str, object]]) -> str:
    lines = ["# Pattern recommendations", ""]
    if not results:
        lines.extend(["No recommendations for the submitted symptoms.", ""])
    for position, entry in enumerate(results, start=1):
        lines.append(f"## {position}. {entry['pattern']}")
        lines.append(f"Card: {entry['card']}")
        lines.append(f"Summary: {entry['summary']}")
        lines.append(f"Matched symptoms: {', '.join(cast(list[str], entry['matched_symptoms']))}")
        lines.append("Use When:")
        for bullet in cast(list[str], entry["use_when"]):
            lines.append(f"  - {bullet}")
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines) + "\n"


def find_entry(
    symptoms: dict[str, dict[str, object]], symptom_id: str, unknown_id: str
) -> dict[str, object]:
    if symptom_id == unknown_id:
        raise RetrievalError(
            f"{unknown_id!r} is the reserved no-match ID; submit it alone, without other symptoms"
        )
    entry = symptoms.get(symptom_id)
    if entry is None:
        raise RetrievalError(f"unknown symptom ID {symptom_id!r}; run 'list' to see accepted IDs")
    return entry


def _first_paragraph(text: str) -> str:
    for part in re.split(r"\n\s*\n", text):
        stripped = part.strip()
        if stripped:
            return " ".join(line.strip() for line in stripped.splitlines())
    return ""


def render_list(symptoms: dict[str, dict[str, object]], unknown_id: str) -> str:
    lines = [
        f"{identifier} - {entry['summary']}"
        for identifier, entry in sorted(symptoms.items())
        if identifier != unknown_id
    ]
    lines.append(
        f"{unknown_id} - reserved: submit alone when no listed symptom matches; never returns recommendations."
    )
    return "\n".join(lines) + "\n"


def render_info(entry: dict[str, object]) -> str:
    lines = [
        "Summary: " + str(entry["summary"]),
        "Evidence: " + str(entry["evidence_hint"]),
        "Non-matches:",
    ]
    lines.extend(f"  - {item}" for item in cast(list[str], entry.get("common_non_matches", [])))
    candidates = [str(item) for item in cast(list[object], entry.get("candidate_patterns", []))]
    lines.append("Candidate patterns:")
    lines.extend(f"  - {item} (cannbot-knowledge pattern library)" for item in candidates)
    return "\n".join(lines) + "\n"


def render_patterns(entry: dict[str, object], patterns_dirs: list[Path]) -> str:
    lines: list[str] = []
    for candidate in [str(item) for item in cast(list[object], entry.get("candidate_patterns", []))]:
        card_path = _find_card_path(patterns_dirs, candidate)
        lines.extend([f"## {candidate}", "", f"Card: {card_path}"])
        if card_path is None:
            lines.extend(["", "Card file is missing from the cannbot-knowledge library.", ""])
            continue
        text = card_path.read_text(encoding="utf-8")
        body = text
        front = _FRONTMATTER.match(text)
        if front is not None:
            body = text[front.end():]
        sections = _sections(body)
        summary = _first_paragraph(sections.get("Summary", ""))
        lines.extend(["", f"Summary: {summary}" if summary else "Summary: (see card)"])
        bullets = _bullets(sections.get("Use When", ""))
        if bullets:
            lines.extend(["", "Use When:"])
            lines.extend(f"  {bullet}" for bullet in bullets)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query the symptom vocabulary and retrieve candidate patterns."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_query_flags(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--language", default="triton")
        sub.add_argument("--contract", type=Path)

    add_query_flags(subparsers.add_parser("list", help="every symptom ID with its one-line summary"))
    for name, help_text in (
        ("info", "one full symptom entry"),
        ("patterns", "the candidate pattern cards for one symptom"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("symptom_id")
        add_query_flags(sub)
    retrieve_parser = subparsers.add_parser("retrieve", help="map symptom IDs to pattern recommendations")
    add_query_flags(retrieve_parser)
    retrieve_parser.add_argument("--symptom", action="append", required=True, metavar="ID")
    retrieve_parser.add_argument("--exclude", action="append", default=[], metavar="PATTERN_ID")
    retrieve_parser.add_argument("--output-json", action="store_true")
    retrieve_parser.add_argument(
        "--code",
        type=Path,
        help="operator source file; accepted for the uniform call interface, ignored by symptom retrieval",
    )
    retrieve_parser.add_argument(
        "--analysis",
        type=Path,
        help="bottleneck evidence file; accepted for the uniform call interface, ignored by symptom retrieval",
    )
    return parser


def _workspace_for_contract(contract_path: Path) -> Path | None:
    """Return the workspace root when the contract sits in a staged skills tree."""
    parts = contract_path.resolve().parts
    for index, part in enumerate(parts[:-1]):
        if part in BACKEND_SKILL_DIRS and parts[index + 1] == "skills":
            return Path(*parts[:index])
    return None


def _resolve_query_paths(args: argparse.Namespace) -> tuple[Path, list[Path]]:
    contract_path = args.contract
    if contract_path is None:
        knowledge_dir = resolve_knowledge_dir(args.language, Path.cwd())
        contract_path = knowledge_dir / "references" / "symptom-contract.json"
    # The staged contract sits at <workspace>/<backend>/skills/<skill>/references/;
    # the provisioned cannbot-knowledge clone always sits at
    # <workspace>/.cannbot/dependencies/<plugin>/cannbot-knowledge/.
    workspace = _workspace_for_contract(contract_path) or Path.cwd()
    patterns_dirs = resolve_kb_patterns_dirs(workspace, args.language)
    if not patterns_dirs:
        raise RetrievalError(
            "cannbot-knowledge pattern library is unavailable under this workspace; "
            "install the plugin so its cannbot-knowledge dependency is provisioned"
        )
    return contract_path, patterns_dirs


def _run_query_command(args: argparse.Namespace, contract_path: Path, patterns_dirs: list[Path]) -> int:
    symptoms, _, unknown_id = load_contract(contract_path)
    validate_candidate_patterns(symptoms, patterns_dirs)
    if args.command == "list":
        print(render_list(symptoms, unknown_id), end="")
        return 0
    entry = find_entry(symptoms, args.symptom_id, unknown_id)
    if args.command == "info":
        print(render_info(entry), end="")
    else:
        print(render_patterns(entry, patterns_dirs), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        contract_path, patterns_dirs = _resolve_query_paths(args)
        if args.command in {"list", "info", "patterns"}:
            return _run_query_command(args, contract_path, patterns_dirs)
        contract, _, _ = load_contract(contract_path)
        validate_candidate_patterns(contract, patterns_dirs)
        results = retrieve(
            list(args.symptom),
            contract_path=contract_path,
            patterns_dirs=patterns_dirs,
            exclude=list(args.exclude),
        )
        markdown = render_markdown(results)
        if args.output_json:
            print(json.dumps({"results": results, "markdown": markdown}, indent=2))
        else:
            print(markdown, end="")
        return 0
    except RetrievalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
