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

"""Validate cross-reference markers in the simt-codegen docs.

A *claim marker* tags a factual assertion that is stated in more than one place,
so that an editor changing one site can find the others:

    <!-- claim: <slug> · also in: <paths>
         · find with: grep -rn "claim: <slug>" skills/simt-codegen
         · edit all sites together -->

Three rules are enforced, all learned the hard way:

1. **No orphans.** A slug appearing in only one file is either a claim that got
   consolidated (delete the marker) or a site whose siblings were never tagged
   (tag them). A one-directional pointer does not give you traceability.

2. **No line numbers in the `also in:` list.** Line numbers go stale on the very
   next edit — we shipped markers pointing at `SKILL.md:349` when the row had
   already moved to 356. Name the file and let `grep` find the marker.

3. **The `also in:` list must match the siblings on disk**, no omissions and no
   ghosts. An incomplete list looks authoritative and sends the editor to a
   subset of the sites.

Markers inside fenced code blocks are ignored: the docs explain this convention
by showing a marker, and counting that example as a live site inflated a real
slug by a file that does not state the claim at all.

A marker means "this fact is deliberately written out in full in more than one
place." It is not for a site that merely *links* to the canonical statement —
links cannot drift, so they need no bookkeeping. If a claim ends up with one
substantive home and N links, delete its markers rather than keeping one.

Run standalone (`--self-test` exercises the checker on synthetic inputs).
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER = re.compile(r"<!--\s*claim:\s*([a-z0-9][a-z0-9-]*)(.*?)-->", re.S)
# a path-like token carrying an explicit line number, e.g. SKILL.md:349 or foo.md:83,90
LINENUM = re.compile(r"\.md:\d+")
SKIP_DIRS = {"ascend950pr_isa_probes"}  # these use a literal "claim:" table column
FENCE = re.compile(r"^\s*(```|~~~)")


def strip_fences(text: str) -> str:
    """Blank out fenced code blocks, preserving line count so line numbers stay true.

    The "Editing these docs" section documents the marker convention by showing one.
    Treating that example as a live site made `atomic-add-dtypes` look like it spanned
    five files when the fifth only quoted the syntax.
    """
    out, in_fence = [], False
    for line in text.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
            out.append("")
        else:
            out.append("" if in_fence else line)
    return "\n".join(out)


def collect(root: Path) -> dict[str, list[tuple[str, int, str]]]:
    """slug -> [(relpath, lineno, also_in_text)]"""
    sites: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for path in sorted(root.rglob("*.md")):
        if SKIP_DIRS & set(path.parts):
            continue
        text = strip_fences(path.read_text(encoding="utf-8"))
        rel = path.relative_to(root).as_posix()
        for match in MARKER.finditer(text):
            lineno = text.count("\n", 0, match.start()) + 1
            sites[match.group(1)].append((rel, lineno, match.group(2)))
    return sites


def check(root: Path) -> list[str]:
    errors: list[str] = []
    sites = collect(root)
    for slug, entries in sorted(sites.items()):
        files = {rel for rel, _, _ in entries}
        if len(files) < 2:
            where = ", ".join(f"{r}:{n}" for r, n, _ in entries)
            errors.append(
                f"orphan claim '{slug}': only in {where}. Either tag the sibling "
                f"sites that state the same thing, or drop the marker."
            )
        for rel, lineno, also in entries:
            stale = LINENUM.findall(also)
            if stale:
                errors.append(
                    f"{rel}:{lineno} claim '{slug}' pins line numbers "
                    f"({', '.join(stale)}) — name the file only; line numbers rot."
                )

            # Rule 3: the "also in:" list must match the siblings actually on disk.
            # A marker that under-reports its siblings sends an editor to a subset of
            # the sites and lets the rest drift — the exact failure the marker exists
            # to prevent. Compare basenames: the list is written relative to the file
            # doing the pointing, so full paths differ between siblings.
            expected = {Path(o).name for o in files if o != rel}
            listed = {Path(tok).name for tok in re.findall(r"[\w./-]+\.md", also)}
            missing = expected - listed
            if missing:
                errors.append(
                    f"{rel}:{lineno} claim '{slug}' omits sibling(s) "
                    f"{', '.join(sorted(missing))} from its 'also in:' list. "
                    f"An incomplete list is worse than none — it looks authoritative."
                )
            spurious = listed - expected - {Path(rel).name}
            if spurious:
                errors.append(
                    f"{rel}:{lineno} claim '{slug}' lists {', '.join(sorted(spurious))} "
                    f"in 'also in:', but no marker for this slug exists there."
                )
    return errors


SELF_TEST_CASES = [
    (
        "orphan",
        {"a.md": "<!-- claim: solo · also in: (none) -->"},
        "orphan claim 'solo'",
    ),
    (
        "linenum",
        {
            "a.md": "<!-- claim: dup · also in: b.md:12 -->",
            "b.md": "<!-- claim: dup · also in: a.md -->",
        },
        "pins line numbers",
    ),
    (
        "clean",
        {
            "a.md": "<!-- claim: dup · also in: b.md -->",
            "b.md": "<!-- claim: dup · also in: a.md -->",
        },
        None,
    ),
    (
        "omits_sibling",
        {
            "a.md": "<!-- claim: t · also in: b.md -->",
            "b.md": "<!-- claim: t · also in: a.md -->",
            "c.md": "<!-- claim: t · also in: a.md, b.md -->",
        },
        "omits sibling(s) c.md",
    ),
    (
        "spurious_sibling",
        {
            "a.md": "<!-- claim: t · also in: b.md, ghost.md -->",
            "b.md": "<!-- claim: t · also in: a.md -->",
        },
        "lists ghost.md",
    ),
    (
        "relative_paths_ok",
        {
            "SKILL.md": "<!-- claim: t · also in: references/g.md -->",
            "references/g.md": "<!-- claim: t · also in: ../SKILL.md -->",
        },
        None,
    ),
    (
        "isa_probes_ignored",
        {"ascend950pr_isa_probes/p.md": "| claim: x | y |"},
        None,
    ),
    (
        # A marker shown as an example inside a fence is documentation, not a site.
        # Before this rule, the example in SKILL.md's own "Editing these docs" section
        # counted as a fifth site for atomic-add-dtypes.
        "fenced_example_ignored",
        {
            "a.md": "<!-- claim: t · also in: b.md -->",
            "b.md": "<!-- claim: t · also in: a.md -->",
            "c.md": "How to write one:\n\n```html\n<!-- claim: t · also in: a.md -->\n```\n",
        },
        None,
    ),
    (
        # ...but a fence must not hide a marker that follows it, and the line number
        # reported for that marker must still be right.
        "marker_after_fence_still_seen",
        {
            "a.md": "```\ncode\n```\n\n<!-- claim: t · also in: b.md:9 -->",
            "b.md": "<!-- claim: t · also in: a.md -->",
        },
        "a.md:5 claim 't' pins line numbers",
    ),
]


def self_test() -> int:
    import tempfile

    failures = 0
    for name, files, expect in SELF_TEST_CASES:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, body in files.items():
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")
            errors = check(root)
            if expect is None:
                ok = not errors
            else:
                ok = any(expect in e for e in errors)
            logger.info("  %s  %s", "PASS" if ok else "FAIL", name)
            if not ok:
                failures += 1
                logger.info("        expected %r, got %s", expect, errors)
    logger.info(
        "self-test: %d/%d passed", len(SELF_TEST_CASES) - failures, len(SELF_TEST_CASES)
    )
    return 1 if failures else 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parent.parent),
        help="directory to scan (default: the simt-codegen skill)",
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    root = Path(args.root)
    if not root.is_dir():
        logger.error("error: %s is not a directory", root)
        return 2

    errors = check(root)
    sites = collect(root)
    total = sum(len(v) for v in sites.values())
    if errors:
        for e in errors:
            logger.error("FAIL: %s", e)
        logger.error("%d problem(s) across %d markers.", len(errors), total)
        return 1
    logger.info(
        "OK: %d claim markers across %d slugs, all multi-site, no pinned lines.",
        total,
        len(sites),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
