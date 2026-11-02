#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------
"""Assemble one workflow design document from the op-design output files."""

import argparse
import logging
import re
from pathlib import Path


def markdown_lines(text):
    """Yield lines with fenced code distinguished from document structure."""
    fence = None
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        in_code = fence is not None or marker is not None
        if marker:
            run, suffix = marker.groups()
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not suffix.strip():
                fence = None
        yield line, in_code


def nested_content(text, title_level):
    lines = []
    for line, in_code in markdown_lines(text):
        heading = re.match(r"^(#{1,6}) (.+)$", line) if not in_code else None
        if heading:
            level = len(heading[1]) + title_level - 1
            if level > 6:
                raise ValueError("design heading nesting exceeds Markdown level 6")
            line = "#" * level + " " + heading[2]
        lines.append(line)
    return "\n".join(lines)


def read_index(index: Path):
    names = []
    entries = []
    linked_branches = set()
    title, section = "算子设计", None
    references = False
    reference_files = {"REQUIREMENTS.md"}
    for line, in_code in markdown_lines(index.read_text(encoding="utf-8")):
        if in_code:
            continue
        if line.startswith("# "):
            title = line[2:].strip().removesuffix("索引").rstrip()
        elif line.startswith("## "):
            section = line[3:].strip()
            references = section.startswith("参考资料")
        if references:
            reference_files.update(
                name
                for name in re.findall(r"\]\(([^)]+\.md)\)", line)
                if len(Path(name).parts) == 1
            )
            continue
        for name in re.findall(r"\]\(([^)]+\.md)\)", line):
            if name in {"INDEX.md", "DESIGN.md", "REQUIREMENTS.md"}:
                continue
            path = Path(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"invalid design link: {name}")
            if len(path.parts) == 1 and path.name not in {"INDEX.md", "DESIGN.md"}:
                if path.name not in names:
                    names.append(path.name)
                    entries.append((section, path.name))
            elif (
                len(path.parts) == 2
                and path.parts[0] == "branches"
                and re.fullmatch(r"DESIGN-BRANCH-[A-Za-z0-9_-]+\.md", path.name)
            ):
                if path.as_posix() not in linked_branches:
                    linked_branches.add(path.as_posix())
                    entries.append((section, path.as_posix()))
            else:
                raise ValueError(f"invalid design link: {name}")
    return title, names, entries, linked_branches, reference_files


def validate_index(design_dir, names, linked_branches, reference_files):
    for name in names:
        if not (design_dir / name).is_file():
            raise ValueError(f"missing {design_dir / name}")
    actual_topics = {
        path.name
        for path in design_dir.glob("*.md")
        if path.name not in {"INDEX.md", "DESIGN.md"} | reference_files
    }
    if set(names) != actual_topics:
        raise ValueError("INDEX.md topic links do not match design files")
    branches = sorted((design_dir / "branches").glob("DESIGN-BRANCH-*.md"))
    if not branches:
        raise ValueError("missing branch design files")
    actual_branches = {path.relative_to(design_dir).as_posix() for path in branches}
    if linked_branches != actual_branches:
        raise ValueError("INDEX.md branch links do not match branch design files")


def render_design(design_dir, title, entries):
    parts = [f"# {title}"]
    previous_section = None
    for section, name in entries:
        path = design_dir / name
        if not path.is_file():
            raise ValueError(f"missing {path}")
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"empty {path}")
        if section != previous_section and section is not None:
            parts.append(f"## {section}")
        previous_section = section
        content = nested_content(content, 3 if section else 2)
        parts.append(f"<!-- design source: {name} -->\n\n{content}")
    return "\n\n---\n\n".join(parts) + "\n"


def assemble(design_dir: Path) -> str:
    index = design_dir / "INDEX.md"
    if not index.is_file():
        raise ValueError(f"missing {index}")
    title, names, entries, branches, references = read_index(index)
    validate_index(design_dir, names, branches, references)
    return render_design(design_dir, title, entries)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == (args.design_dir / "INDEX.md").resolve():
        parser.error("output must not overwrite INDEX.md")
    try:
        text = assemble(args.design_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"design assembly failed: {exc}\n")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("%s", args.output)


if __name__ == "__main__":
    main()
