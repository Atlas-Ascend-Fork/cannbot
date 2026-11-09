#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Project-local staging knowledge for tilelang2ascendc-ops-generator.

The fixed, governed knowledge store lives in the cannbot-knowledge repository and is
read-only here.  This tool only manages the plugin's OKF v0.2 staging bundle:

* ``initialize`` copies missing files from the built-in bundle into the project copy.
* ``query`` searches project and/or built-in staging cards.
* ``record`` appends a draft card to ``learned/`` and rebuilds its index.
* ``promote`` prints a review manifest/diff; it never writes a source repository.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

BUNDLE_DIRNAME = ".tilelang2ascendc"
BUNDLE_SUBDIR = "knowledge"
CATEGORIES = ("learned", "optimization", "debug")
RESERVED_FILES = {"index.md"}
FRONTMATTER_RE = re.compile(r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", re.DOTALL)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,80}$")

LOG = logging.getLogger("knowledge_store")


class KnowledgeStoreError(Exception):
    """User-facing error that maps to exit code 2."""


@dataclass(frozen=True)
class QueryRequest:
    """Inputs of a staging knowledge query."""

    project: Path
    builtin: Path | None
    scope: str = "auto"
    category: str | None = None
    type_: str | None = None
    tags: tuple[str, ...] = ()
    status: str | None = None
    text: str | None = None
    limit: int = 10


@dataclass(frozen=True)
class RecordRequest:
    """Inputs of a staging knowledge record operation."""

    project: Path
    title: str
    description: str
    kind: str = "implementation_trap"
    type_: str = "Runbook"
    tags: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    slug: str = ""
    body: str = ""
    force: bool = False


class BelowWarningFilter(logging.Filter):
    """只放行 INFO/DEBUG，避免告警在 stdout 与 stderr 重复输出。"""

    def filter(self, log_record: logging.LogRecord) -> bool:
        return log_record.levelno < logging.WARNING


def configure_logging() -> None:
    """输出纯正文日志：正常结果走 stdout，告警与错误走 stderr。"""
    if LOG.handlers:
        return
    formatter = logging.Formatter("%(message)s")
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(BelowWarningFilter())
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(logging.WARNING)
    LOG.addHandler(stdout_handler)
    LOG.addHandler(stderr_handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


def fail(message: str) -> NoReturn:
    raise KnowledgeStoreError(message)


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def project_root(value: str) -> Path:
    root = Path(value).expanduser().resolve(strict=False)
    if not root.is_dir():
        fail(f"project root is not a directory: {root}")
    return root


def bundle_path(root: Path) -> Path:
    return root / BUNDLE_DIRNAME / BUNDLE_SUBDIR


def builtin_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser().resolve(strict=False)
    if not path.is_dir():
        fail(f"builtin bundle is not a directory: {path}")
    return path


def split_csv(values: Sequence[str]) -> list[str]:
    """展开可重复传入、且单项允许逗号分隔的 CLI 参数。"""
    items: list[str] = []
    for value in values:
        for part in value.split(","):
            item = part.strip()
            if item:
                items.append(item)
    return items


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_inline_list(value: str) -> list[str]:
    inner = value[1:-1].strip()
    items: list[str] = []
    for item in split_csv([inner]):
        items.append(unquote(item))
    return items


def append_list_item(line: str, data: dict[str, object], current: str | None) -> bool:
    item = re.match(r"^\s+-\s+(.*)$", line)
    if not item or not current:
        return False
    values = data.get(current)
    if not isinstance(values, list):
        values = []
        data[current] = values
    values.append(unquote(item.group(1)))
    return True


def parse_key_value(line: str, data: dict[str, object]) -> str | None:
    if ":" not in line:
        return None
    key, value = line.split(":", 1)
    key = key.strip()
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        data[key] = parse_inline_list(value)
    elif value == "":
        data[key] = []
    else:
        data[key] = unquote(value)
    return key


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    data: dict[str, object] = {}
    current: str | None = None
    for raw in match.group(1).splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if append_list_item(line, data, current):
            continue
        key = parse_key_value(line, data)
        if key is not None:
            current = key
    return data, text[match.end():]


def as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None or value == "":
        return []
    return [str(value)]


def read_card(path: Path, base: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"cannot read {path}: {exc}")
    frontmatter, body = parse_frontmatter(text)
    return {
        "path": path,
        "relative": path.relative_to(base).as_posix(),
        "category": path.parent.name,
        "title": str(frontmatter.get("title") or path.stem),
        "description": str(frontmatter.get("description") or ""),
        "type": str(frontmatter.get("type") or ""),
        "status": str(frontmatter.get("status") or ""),
        "kind": str(frontmatter.get("kind") or ""),
        "tags": [tag.lower() for tag in as_list(frontmatter.get("tags"))],
        "platforms": as_list(frontmatter.get("platforms")),
        "body": body,
    }


def read_cards(base: Path) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    for category in CATEGORIES:
        directory = base / category
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name in RESERVED_FILES or path.is_symlink():
                continue
            cards.append(read_card(path, base))
    return cards


def copy_builtin_files(builtin: Path, target: Path) -> list[str]:
    copied: list[str] = []
    for source in sorted(builtin.rglob("*")):
        if source.is_symlink() or not source.is_file():
            continue
        relative = source.relative_to(builtin)
        if relative.parts and relative.parts[0] not in (*CATEGORIES, "index.md"):
            continue
        destination = target / relative
        if destination.exists() or destination.is_symlink():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(relative.as_posix())
    return copied


def ensure_bundle_index(target: Path, copied: list[str]) -> None:
    if (target / "index.md").is_file():
        return
    (target / "index.md").write_text(
        '---\nokf_version: "0.2"\n---\n\n# tilelang2ascendc 项目暂存知识\n\n'
        "- [项目经验（learned）](learned/index.md)\n"
        "- [优化经验（optimization）](optimization/index.md)\n"
        "- [调试经验（debug）](debug/index.md)\n",
        encoding="utf-8",
    )
    copied.append("index.md")


def initialize(project: Path, builtin: Path) -> dict[str, object]:
    target = bundle_path(project)
    for category in CATEGORIES:
        (target / category).mkdir(parents=True, exist_ok=True)
    copied = copy_builtin_files(builtin, target)
    ensure_bundle_index(target, copied)
    return {"status": "ready", "bundle": str(target), "copied": copied}


def resolve_query_roots(
    project_bundle: Path,
    builtin: Path | None,
    scope: str,
) -> list[tuple[str, Path]]:
    if scope == "project":
        return [("project", project_bundle)]
    if scope == "builtin":
        return [("builtin", builtin)] if builtin else []
    if scope == "all":
        roots: list[tuple[str, Path]] = []
        if builtin:
            roots.append(("builtin", builtin))
        roots.append(("project", project_bundle))
        return roots
    if project_bundle.is_dir():
        return [("project", project_bundle)]
    if builtin:
        return [("builtin", builtin)]
    return []


def collect_cards(roots: list[tuple[str, Path]]) -> list[dict[str, object]]:
    by_relative: dict[str, dict[str, object]] = {}
    for source_name, root in roots:
        if not root.is_dir():
            continue
        for card in read_cards(root):
            # Project cards override built-in cards with the same relative path.
            existing = by_relative.get(str(card["relative"]))
            if existing is None or source_name == "project":
                card["scope"] = source_name
                by_relative[str(card["relative"])] = card
    return list(by_relative.values())


def card_haystack(card: dict[str, object]) -> str:
    tag_text = " ".join(str(tag) for tag in card["tags"])
    fields = (
        str(card["title"]).lower(),
        str(card["description"]).lower(),
        str(card["relative"]).lower(),
        tag_text,
        str(card["body"]).lower(),
    )
    return " ".join(fields)


def card_metadata_matches(
    card: dict[str, object],
    request: QueryRequest,
    requested_tags: list[str],
) -> bool:
    checks = (
        not request.category or card["category"] == request.category,
        not request.type_ or str(card["type"]).lower() == request.type_.lower(),
        not request.status or str(card["status"]).lower() == request.status.lower(),
        not requested_tags or all(tag in card["tags"] for tag in requested_tags),
    )
    return all(checks)


def card_terms_match(card: dict[str, object], terms: list[str]) -> bool:
    if not terms:
        return True
    haystack = card_haystack(card)
    return all(term in haystack for term in terms)


def score_card(card: dict[str, object], terms: list[str]) -> int:
    if not terms:
        return 0
    title = str(card["title"]).lower()
    description = str(card["description"]).lower()
    path = str(card["relative"]).lower()
    tag_text = " ".join(str(tag) for tag in card["tags"])
    body = str(card["body"]).lower()
    weighted_fields = ((title, 5), (tag_text, 3), (description, 2), (path, 1))
    score = 0
    for term in terms:
        for field, weight in weighted_fields:
            if term in field:
                score += weight
        score += body.count(term)
    return score


def rank_cards(
    cards: list[dict[str, object]],
    request: QueryRequest,
) -> list[dict[str, object]]:
    terms = [term.lower() for term in (request.text or "").split() if term]
    requested_tags = [tag.lower() for tag in request.tags]
    matches: list[dict[str, object]] = []
    for card in cards:
        if not card_metadata_matches(card, request, requested_tags):
            continue
        if not card_terms_match(card, terms):
            continue
        result = dict(card)
        result.pop("body", None)
        result["path"] = str(card["path"])
        result["score"] = score_card(card, terms)
        matches.append(result)
    matches.sort(key=lambda item: (-int(item["score"]), str(item["relative"])))
    return matches


def query(request: QueryRequest) -> dict[str, object]:
    project_bundle = bundle_path(request.project)
    roots = resolve_query_roots(project_bundle, request.builtin, request.scope)
    cards = collect_cards(roots)
    matches = rank_cards(cards, request)
    limit = max(1, request.limit)
    return {
        "scope": request.scope,
        "roots": [str(root) for _, root in roots],
        "matched": min(len(matches), limit),
        "total": len(matches),
        "cards": matches[:limit],
    }


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    return slug[:80]


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def yaml_list(values: Sequence[str]) -> str:
    return "[" + ", ".join(yaml_quote(item) for item in values) + "]"


def atomic_write(path: Path, text: str) -> None:
    """原子写入目标文件，并确保临时文件在成功或异常时都被删除。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as stream:
            temporary_name = stream.name
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        temporary_name = ""
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def rebuild_learned_index(directory: Path) -> None:
    entries: list[tuple[str, str, str]] = []
    for path in sorted(directory.glob("*.md")):
        if path.name in RESERVED_FILES or path.is_symlink():
            continue
        frontmatter, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        title = str(frontmatter.get("title") or path.stem)
        description = str(frontmatter.get("description") or "")
        entries.append((path.name, title, description))
    lines = [
        "# 项目经验（learned）",
        "",
        "本目录由 `tilelang2ascendc-knowledge` Skill 的 `record` 动作维护，只保存",
        "`status: draft` 的项目经验卡。Phase 7 只写项目副本的 `learned/`，不直接写固定知识库。",
        "",
    ]
    if entries:
        for name, title, description in entries:
            suffix = f" — {description}" if description else ""
            lines.append(f"- [{title}]({name}){suffix}")
    else:
        lines.append("- 暂无记录。")
    atomic_write(directory / "index.md", "\n".join(lines) + "\n")


def validate_record(request: RecordRequest) -> None:
    if not request.title.strip():
        fail("--title cannot be empty")
    if not request.description.strip():
        fail("--description cannot be empty")


def resolve_slug(request: RecordRequest) -> str:
    final_slug = slugify(request.slug or request.title)
    if not final_slug:
        # Chinese-only titles produce no ASCII slug; keep it deterministic.
        # 仅用于生成短文件名，不承担安全语义，因此使用 SHA-256 避免弱哈希告警。
        digest = hashlib.sha256(request.title.strip().encode("utf-8")).hexdigest()[:8]
        final_slug = f"entry_{digest}"
    if not SLUG_RE.match(final_slug):
        fail(f"invalid slug: {final_slug!r}")
    return final_slug


def build_card_text(request: RecordRequest) -> str:
    now = today()
    frontmatter = [
        "---",
        'schema_version: "0.1"',
        f"kind: {yaml_quote(request.kind)}",
        f"type: {yaml_quote(request.type_)}",
        f"title: {yaml_quote(request.title.strip())}",
        f"description: {yaml_quote(request.description.strip())}",
        f"tags: {yaml_list(request.tags)}",
        f"created_at: {yaml_quote(now)}",
        f"updated_at: {yaml_quote(now)}",
        'status: "draft"',
        f"platforms: {yaml_list(request.platforms)}",
        f"sources: {yaml_list(request.sources)}",
        "---",
        "",
    ]
    return "\n".join(frontmatter) + request.body.strip() + "\n"


def record(request: RecordRequest) -> dict[str, object]:
    validate_record(request)
    final_slug = resolve_slug(request)
    directory = bundle_path(request.project) / "learned"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{final_slug}.md"
    if destination.exists() and not request.force:
        fail(f"card already exists (use --force to overwrite): {destination}")

    atomic_write(destination, build_card_text(request))
    rebuild_learned_index(directory)
    return {
        "status": "recorded",
        "path": str(destination),
        "relative": destination.relative_to(bundle_path(request.project)).as_posix(),
        "slug": final_slug,
    }


def resolve_card(project: Path, value: str) -> tuple[Path, Path]:
    bundle = bundle_path(project)
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = bundle / candidate
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(bundle.resolve(strict=False))
    except ValueError:
        fail(f"card path escapes the project bundle: {value}")
    if not resolved.is_file() or resolved.name in RESERVED_FILES:
        fail(f"card not found: {value}")
    return resolved, bundle


def promote(project: Path, value: str, target_root: str | None, fmt: str) -> dict[str, object]:
    card, bundle = resolve_card(project, value)
    relative = card.relative_to(bundle)
    if relative.parts[0] not in CATEGORIES:
        fail(f"unsupported category: {relative.parts[0]}")
    text = card.read_text(encoding="utf-8")
    suggested = f"knowledge/{relative.as_posix()}"
    target: Path | None = None
    target_exists = False
    if target_root:
        target = Path(target_root).expanduser().resolve(strict=False) / suggested
        target_exists = target.is_file()
    diff = ""
    if fmt == "patch":
        old = target.read_text(encoding="utf-8").splitlines(keepends=True) if target_exists and target else []
        diff = "".join(
            difflib.unified_diff(
                old,
                text.splitlines(keepends=True),
                fromfile=str(target) if target_exists and target else "/dev/null",
                tofile=str(target) if target else suggested,
            )
        )
    return {
        "status": "review-required",
        "project_card": str(card),
        "suggested_target": suggested,
        "target_root": str(Path(target_root).expanduser().resolve(strict=False)) if target_root else None,
        "target_exists": target_exists,
        "checklist": [
            "确认至少两个项目复现，或用户明确要求提升",
            "补齐 platforms、来源和真实验证记录，status 才能离开 draft",
            "先查重固定知识库和插件暂存库，合并同主题卡片",
            "人工提交插件仓库 PR；固定知识库提升另走 cannbot-knowledge 评审",
        ],
        "diff": diff,
    }


def add_initialize_parser(subparsers) -> None:
    parser = subparsers.add_parser("initialize", help="copy missing built-in files")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--builtin-root", required=True)


def add_query_parser(subparsers) -> None:
    parser = subparsers.add_parser("query", help="search staging cards")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--builtin-root")
    parser.add_argument("--scope", choices=("auto", "project", "builtin", "all"), default="auto")
    parser.add_argument("--category", choices=CATEGORIES)
    parser.add_argument("--type")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--status")
    parser.add_argument("--text")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true")


def add_record_parser(subparsers) -> None:
    parser = subparsers.add_parser("record", help="append a draft card to learned/")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--kind", default="implementation_trap")
    parser.add_argument("--type", default="Runbook")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--platform", action="append", default=[])
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--slug", default="")
    parser.add_argument("--body", default="")
    parser.add_argument("--body-file")
    parser.add_argument("--force", action="store_true")


def add_promote_parser(subparsers) -> None:
    parser = subparsers.add_parser("promote", help="print a review manifest/diff")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--target-root")
    parser.add_argument("--format", choices=("patch", "json"), default="json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    add_initialize_parser(subparsers)
    add_query_parser(subparsers)
    add_record_parser(subparsers)
    add_promote_parser(subparsers)
    return parser


def read_body_file(path_value: str) -> str:
    try:
        return Path(path_value).expanduser().read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"cannot read body file: {exc}")


def make_query_request(args: argparse.Namespace) -> QueryRequest:
    return QueryRequest(
        project=project_root(args.project_root),
        builtin=builtin_path(args.builtin_root),
        scope=args.scope,
        category=args.category,
        type_=args.type,
        tags=tuple(split_csv(args.tag)),
        status=args.status,
        text=args.text,
        limit=max(1, args.limit),
    )


def make_record_request(args: argparse.Namespace) -> RecordRequest:
    body = args.body
    if args.body_file:
        body = read_body_file(args.body_file)
    return RecordRequest(
        project=project_root(args.project_root),
        title=args.title,
        description=args.description,
        kind=args.kind,
        type_=args.type,
        tags=tuple(split_csv(args.tag)),
        platforms=tuple(split_csv(args.platform)),
        sources=tuple(args.source),
        slug=args.slug,
        body=body or args.description,
        force=args.force,
    )


def dispatch(args: argparse.Namespace) -> dict[str, object]:
    if args.action == "initialize":
        builtin = builtin_path(args.builtin_root)
        if builtin is None:
            fail("--builtin-root is required")
        return initialize(project_root(args.project_root), builtin)
    if args.action == "query":
        return query(make_query_request(args))
    if args.action == "record":
        return record(make_record_request(args))
    return promote(project_root(args.project_root), args.path, args.target_root, args.format)


def emit_query_text(result: dict[str, object]) -> None:
    for card in result["cards"]:
        LOG.info("[%s] %s  (score=%s)", card["scope"], card["relative"], card["score"])
        LOG.info("  %s", card["title"])
        if card["description"]:
            LOG.info("  %s", card["description"])
    LOG.info("matched=%s total=%s scope=%s", result["matched"], result["total"], result["scope"])
    if not result["cards"]:
        LOG.info("no matching staging knowledge; fixed knowledge still requires a knowledge-query search")


def emit_result(args: argparse.Namespace, result: dict[str, object]) -> None:
    if args.action == "query" and not args.json:
        emit_query_text(result)
        return
    LOG.info("%s", json.dumps(result, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    try:
        result = dispatch(args)
    except KnowledgeStoreError as exc:
        LOG.error("error: %s", exc)
        return 2
    emit_result(args, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
