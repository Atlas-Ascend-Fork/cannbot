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
"""Validate changelog fragments and aggregate them at release time."""

import argparse
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import List, Optional, Tuple

FRAGMENT_DIR = "docs/changelog.d"
CHANGELOG = "CHANGELOG.md"
GENERATED_HEADER = (
    "<!-- GENERATED FILE: 由 script/scripts/changelog.py 从 docs/changelog.d 聚合；请勿直接修改。 -->"
)
NAME_PATTERN = re.compile(r"(?P<pr>[1-9]\d*)\.(?P<kind>added|fixed|docs|chore)\.md")
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")
RELEASE_PATTERN = re.compile(
    r"^## (?P<version>\d+\.\d+\.\d+) - (?P<date>\d{4}-\d{2}-\d{2})[ \t]*$",
    re.MULTILINE,
)
UNRELEASED_PATTERN = re.compile(r"^## Unreleased[ \t]*$", re.MULTILINE)
SECTION_PATTERN = re.compile(r"^### (?P<heading>[^#\r\n]+?)[ \t]*$", re.MULTILINE)
CATEGORIES = (
    ("added", "Added"),
    ("fixed", "Fixed"),
    ("docs", "Documentation"),
    ("chore", "Changed"),
)
LOGGER = logging.getLogger(__name__)
GIT = shutil.which("git")
if GIT is None:
    raise RuntimeError("git executable not found")


@dataclass(frozen=True)
class Fragment:
    path: Path
    pr_number: int
    kind: str
    text: str


def load_fragments(repo: Path, expected_pr: Optional[int] = None) -> List[Fragment]:
    directory = repo / FRAGMENT_DIR
    if not directory.exists():
        return []
    fragments = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.name == "README.md" or path.name.startswith("."):
            continue
        if not path.is_file():
            raise ValueError(f"fragment 目录只允许文件: {path}")
        match = NAME_PATTERN.fullmatch(path.name)
        if not match:
            raise ValueError(
                f"fragment 文件名须为 <PR号>.<added|fixed|docs|chore>.md: {path.name}"
            )
        pr_number = int(match.group("pr"))
        if expected_pr is not None and pr_number != expected_pr:
            raise ValueError(f"fragment PR 号 {pr_number} 与当前 PR {expected_pr} 不一致")
        lines = [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if len(lines) != 1 or not lines[0].startswith("- "):
            raise ValueError(f"fragment 只能包含一条以 '- ' 开头的变更说明: {path.name}")
        text = lines[0]
        if len(text[2:].strip()) == 0:
            raise ValueError(f"fragment 内容不能为空: {path.name}")
        if len(text[2:].strip()) > 200:
            raise ValueError(f"fragment 正文不得超过 200 字: {path.name}")
        fragments.append(Fragment(path, pr_number, match.group("kind"), text))
    return fragments


def changed_files(repo: Path, base: str, head: str) -> List[str]:
    result = subprocess.run(
        [
            GIT,
            "-C",
            str(repo),
            "diff",
            "--no-renames",
            "--name-only",
            f"{base}...{head}",
            "--",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return [line for line in result.stdout.splitlines() if line]


def changed_file_statuses(repo: Path, base: str, head: str) -> List[Tuple[str, str]]:
    result = subprocess.run(
        [
            GIT,
            "-C",
            str(repo),
            "diff",
            "--no-renames",
            "--name-status",
            f"{base}...{head}",
            "--",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    changes = []
    for line in result.stdout.splitlines():
        status, filename = line.split("\t", 1)
        changes.append((status, filename))
    return changes


def restore_tree(repo: Path, commit: str, destination: Path) -> None:
    paths = subprocess.check_output(
        [
            GIT,
            "-C",
            str(repo),
            "ls-tree",
            "-r",
            "--name-only",
            commit,
            "--",
            CHANGELOG,
            FRAGMENT_DIR,
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).splitlines()
    for filename in paths:
        content = subprocess.check_output(
            [GIT, "-C", str(repo), "show", f"{commit}:{filename}"]
        )
        target = destination / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def check_changed_fragment_paths(files: List[str], expected_pr: Optional[int]) -> None:
    for filename in files:
        if not filename.startswith(f"{FRAGMENT_DIR}/"):
            continue
        name = PurePosixPath(filename).name
        if name == "README.md":
            continue
        match = NAME_PATTERN.fullmatch(name)
        if not match:
            raise ValueError(f"变更的 fragment 文件名不合法: {filename}")
        pr_number = int(match.group("pr"))
        if expected_pr is not None and pr_number != expected_pr:
            raise ValueError(
                f"变更的 fragment PR 号 {pr_number} 与当前 PR {expected_pr} 不一致"
            )


def check(repo: Path, base: str, head: str, expected_pr: Optional[int]) -> None:
    files = changed_files(repo, base, head)
    if CHANGELOG in files:
        raise ValueError("禁止直接修改 CHANGELOG.md；请新增 docs/changelog.d fragment")
    check_changed_fragment_paths(files, expected_pr)
    fragments = load_fragments(repo)
    LOGGER.info(f"fragment 校验通过：{len(fragments)} 个；CHANGELOG.md 未被直接修改")


def build_section(
    fragments: List[Fragment], release_date: str, version: str, unreleased_body: str
) -> str:
    """把既有 Unreleased 栏目与 fragments 合入一个版本段，保留未知栏目。"""
    matches = list(SECTION_PATTERN.finditer(unreleased_body))
    preamble_end = matches[0].start() if matches else len(unreleased_body)
    if unreleased_body[:preamble_end].strip():
        raise ValueError("Unreleased 的三级栏目前存在无法迁移的内容")
    sections = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(unreleased_body)
        heading = match.group("heading").strip()
        content = unreleased_body[match.end():end].strip()
        if content:
            sections.setdefault(heading, []).append(content)
    for kind, heading in CATEGORIES:
        entries = [fragment for fragment in fragments if fragment.kind == kind]
        if entries:
            sections.setdefault(heading, []).extend(
                fragment.text
                for fragment in sorted(entries, key=lambda item: item.pr_number)
            )
    lines = [f"## {version} - {release_date}"]
    for heading, contents in sections.items():
        lines.extend(["", f"### {heading}", "", "\n\n".join(contents)])
    return "\n".join(lines).rstrip() + "\n"


def aggregate(repo: Path, release_date: str, version: str) -> bool:
    date.fromisoformat(release_date)
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("版本号须为 x.y.z")
    fragments = load_fragments(repo)
    if not fragments:
        LOGGER.info("没有待聚合 fragment，无需修改")
        return False
    changelog = repo / CHANGELOG
    original = changelog.read_text(encoding="utf-8")
    if version in [match.group("version") for match in RELEASE_PATTERN.finditer(original)]:
        raise ValueError(f"版本 {version} 已存在，拒绝重复聚合")
    text = original
    if GENERATED_HEADER not in text:
        text = f"{GENERATED_HEADER}\n\n{text}"
    unreleased = list(UNRELEASED_PATTERN.finditer(text))
    releases = list(RELEASE_PATTERN.finditer(text))
    if len(unreleased) != 1 or not releases:
        raise ValueError("CHANGELOG.md 须包含唯一的 Unreleased 和至少一个历史版本标题")
    if releases[0].start() < unreleased[0].end():
        raise ValueError("Unreleased 必须位于历史版本之前")
    unreleased_body = text[unreleased[0].end():releases[0].start()]
    section = build_section(fragments, release_date, version, unreleased_body)
    text = (
        f"{text[:unreleased[0].start()]}## Unreleased\n\n"
        f"{section}\n{text[releases[0].start():]}"
    )
    with open(changelog, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    for fragment in fragments:
        fragment.path.unlink()
    LOGGER.info(f"已聚合 {len(fragments)} 个 fragment 及 Unreleased 到 {version}（{release_date}）")
    return True


def verify_release(repo: Path, base: str, head: str) -> None:
    changes = changed_file_statuses(repo, base, head)
    for status, filename in changes:
        if filename != CHANGELOG and not filename.startswith(f"{FRAGMENT_DIR}/"):
            raise ValueError(f"聚合 PR 含范围外改动: {filename}")
        if filename.startswith(f"{FRAGMENT_DIR}/") and status != "D":
            raise ValueError(f"聚合 PR 只能删除已消费 fragment: {filename}")
    if ("M", CHANGELOG) not in changes:
        raise ValueError("聚合 PR 必须修改 CHANGELOG.md")
    deleted = {
        filename
        for status, filename in changes
        if status == "D" and filename.startswith(f"{FRAGMENT_DIR}/")
    }
    if not deleted:
        raise ValueError("聚合 PR 至少要删除一个已消费 fragment，不能裸改 CHANGELOG.md")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        base_repo = root / "base"
        head_repo = root / "head"
        restore_tree(repo, base, base_repo)
        restore_tree(repo, head, head_repo)
        if load_fragments(head_repo):
            raise ValueError("聚合 PR 仍包含未消费 fragment")
        base_text = (base_repo / CHANGELOG).read_text(encoding="utf-8")
        head_text = (head_repo / CHANGELOG).read_text(encoding="utf-8")
        match = RELEASE_PATTERN.search(head_text)
        if not match:
            raise ValueError("聚合后的 CHANGELOG.md 缺少 '## 版本 - 日期' 标题")
        release_version = match.group("version")
        release_date = match.group("date")
        if release_version in [
            item.group("version") for item in RELEASE_PATTERN.finditer(base_text)
        ]:
            raise ValueError(f"版本 {release_version} 已存在于基线")

        base_fragments = load_fragments(base_repo)
        expected_deleted = {
            fragment.path.relative_to(base_repo).as_posix()
            for fragment in base_fragments
        }
        if deleted != expected_deleted:
            raise ValueError("删除的 fragment 集合与基线待聚合集合不一致")
        aggregate(base_repo, release_date, release_version)
        expected = (base_repo / CHANGELOG).read_text(encoding="utf-8")
    if expected != head_text:
        raise ValueError("CHANGELOG.md 与基线重放聚合结果不一致")
    LOGGER.info(f"聚合 PR 校验通过：{release_version}（{release_date}），{len(deleted)} 个 fragment")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check_parser = subparsers.add_parser("check", help="校验 PR fragments 与 CHANGELOG 禁改")
    check_parser.add_argument("--base", required=True)
    check_parser.add_argument("--head", required=True)
    check_parser.add_argument("--pr-number", type=int)
    release_parser = subparsers.add_parser(
        "verify-release", help="重放基线聚合并校验发版 PR"
    )
    release_parser.add_argument("--base", required=True)
    release_parser.add_argument("--head", required=True)
    validate_parser = subparsers.add_parser("validate", help="仅校验当前 fragments")
    validate_parser.add_argument("--pr-number", type=int)
    aggregate_parser = subparsers.add_parser(
        "aggregate", help="聚合 fragments 并清空目录"
    )
    aggregate_parser.add_argument("--date", default=date.today().isoformat())
    aggregate_parser.add_argument("--version", required=True, help="发布版本号，格式 x.y.z")
    for subparser in (check_parser, release_parser, validate_parser, aggregate_parser):
        subparser.add_argument("--repo", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    try:
        if args.command == "check":
            check(repo, args.base, args.head, args.pr_number)
        elif args.command == "verify-release":
            verify_release(repo, args.base, args.head)
        elif args.command == "validate":
            fragments = load_fragments(repo, args.pr_number)
            LOGGER.info(f"fragment 校验通过：{len(fragments)} 个")
        else:
            aggregate(repo, args.date, args.version)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        LOGGER.error(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
