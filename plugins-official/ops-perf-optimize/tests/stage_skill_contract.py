# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Validate stage loading boundaries in both source and installed layouts."""

from pathlib import Path
import re


def require(condition: object, message: object = "contract check failed") -> None:
    """Fail the check without using a production assert statement."""
    if not condition:
        raise AssertionError(message)


STAGE_SKILLS = {
    "baseline": "ops-perf-baseline-evaluate",
    "preparation": "ops-perf-preparation",
    "analysis": "ops-perf-analysis",
    "implementation": "ops-perf-implementation",
    "integration": "ops-perf-postprocess",
}


def _linked_targets(path: Path, root: Path, main: Path) -> list[Path]:
    targets: list[Path] = []
    prose = re.sub(r"```[^\n]*\n.*?```", "", path.read_text(), flags=re.S)
    for link in re.findall(r"\]\(([^)]+)\)", prose):
        if "://" in link or link.startswith("#") or link.startswith("skill:"):
            continue
        target = (path.parent / link.split("#")[0]).resolve()
        require(target.exists(), (path, link))
        require(main.resolve() not in target.parents, (path, link))
        if target.suffix == ".md" and root in target.parents:
            targets.append(target)
    return targets


def _check_skill(root: Path, entry: Path, main: Path, name: str) -> None:
    pending, reachable = [entry], set()
    while pending:
        path = pending.pop()
        if path in reachable:
            continue
        require(path.is_file(), path)
        reachable.add(path)
        pending.extend(_linked_targets(path, root, main))
    # The intentionally unlinked knowledge template is an authoring asset.
    docs = set(root.rglob("*.md")) - {
        root / "references/perf-review-knowledge/_template.md"
    }
    require(docs <= reachable, (name, docs - reachable))
    if name in STAGE_SKILLS.values():
        require("阶段内不加载主编排 Skill" in entry.read_text())
        require("ops-perf-acceptance-criteria" in entry.read_text())


def check_skill_layout(skills: Path, workflows: Path) -> None:
    main = skills / "ops-perf-optimize-workflow"
    require({p.name for p in (main / "references").iterdir()} == {
        "workflow-contract.md",
        "request-intake.md",
        "migration.md",
    })
    require((workflows / "references/state-reporting.md").is_file())
    for name in (
        *STAGE_SKILLS.values(),
        "ops-perf-acceptance-criteria",
        "ascendc-performance-review",
    ):
        root = (skills / name).resolve()
        _check_skill(root, root / "SKILL.md", main, name)
