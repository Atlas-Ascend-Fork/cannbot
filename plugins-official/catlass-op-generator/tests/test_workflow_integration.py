# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the LICENSE file.
# ----------------------------------------------------------------------------------------------------------

"""Integration checks for the CATLASS C++ workflow entry and state routing."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGIN_ROOT.parents[1]
STAGE_SKILLS = {
    "interface": "catlass-cpp-interface",
    "reference": "catlass-cpp-reference",
    "design": "catlass-cpp-design",
    "implementation": "catlass-cpp-develop",
    "validation": "catlass-cpp-test",
    "complete": "catlass-cpp-test",
}


def _skills_root() -> Path:
    configured = os.environ.get("CANNBOT_SKILLS_ROOT")
    root = Path(configured) if configured else REPO_ROOT / "vendor/cannbot-skills"
    return root if root.name == "ops" else root / "ops"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def workflow() -> ModuleType:
    interface = _skills_root() / "catlass-cpp-interface"
    path = interface / "scripts/validate_workflow.py"
    assert path.is_file()
    return _load("catlass_workflow_validator", path)


@pytest.fixture(scope="module")
def transition() -> ModuleType:
    path = _skills_root() / "catlass-cpp-interface/scripts/transition_workflow.py"
    assert path.is_file()
    return _load("catlass_workflow_transition", path)


@pytest.fixture(scope="module")
def validation() -> ModuleType:
    path = _skills_root() / "catlass-cpp-test/scripts/validate_validation.py"
    assert path.is_file()
    return _load("catlass_validation_validator", path)


def _state(
    stage: str,
    issue_type: str | None = None,
    architecture: str = "atlas_a2_a3",
    family: str = "linear_attention",
) -> dict[str, object]:
    return {
        "algorithm_family": family,
        "target_architecture": architecture,
        "stage": stage,
        "issue_type": issue_type,
    }


def test_entry_routes_every_state_to_an_installed_skill() -> None:
    entry = (PLUGIN_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    skills_root = _skills_root()
    assert "target_architecture_reset" in entry
    for stage, skill in STAGE_SKILLS.items():
        assert f"| {stage} | `{skill}` |" in entry
        assert (skills_root / skill / "SKILL.md").is_file()


def test_entry_covers_every_registered_family_and_architecture(
    workflow: ModuleType,
) -> None:
    entry = (PLUGIN_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for family in workflow.ALGORITHM_FAMILIES:
        assert f"`{family}`" in entry
        for architecture in workflow.TARGET_ARCHITECTURES:
            assert (
                workflow.validate_workflow(
                    _state("reference", architecture=architecture, family=family)
                )
                == []
            )


def test_completion_gate_rejects_pending_validation_evidence(
    validation: ModuleType,
) -> None:
    template = (
        _skills_root() / "catlass-cpp-test/templates/validation.md.template"
    ).read_text(encoding="utf-8")
    errors = validation.validate(
        template,
        _state("validation"),
        "validation_accepted",
    )
    assert any("requires passed V1 evidence" in error for error in errors)
    assert any("requires passed V2 evidence" in error for error in errors)


@pytest.mark.parametrize(
    ("initial", "steps"),
    (
        (
            _state("interface", architecture="pending"),
            (
                ("interface_accepted", "atlas_a2_a3", ("reference", None)),
                ("reference_accepted", None, ("design", None)),
                ("design_accepted", None, ("implementation", None)),
                ("implementation_accepted", None, ("validation", None)),
                ("validation_accepted", None, ("complete", None)),
            ),
        ),
        (_state("reference"), (("interface_problem", None, ("interface", None)),)),
        (_state("design"), (("reference_problem", None, ("reference", None)),)),
        (
            _state("implementation"),
            (("design_problem", None, ("design", None)),),
        ),
        (
            _state("validation"),
            (("implementation_problem", None, ("implementation", None)),),
        ),
        (
            _state("validation"),
            (
                (
                    "precision_problem",
                    None,
                    ("implementation", "precision_debug"),
                ),
                ("implementation_accepted", None, ("validation", None)),
            ),
        ),
        (
            _state("validation"),
            (
                ("performance_candidate", None, ("design", "performance_optimize")),
                ("design_accepted", None, ("implementation", None)),
                ("implementation_accepted", None, ("validation", None)),
            ),
        ),
        (
            _state("complete"),
            (("complete_evidence_invalid", None, ("validation", None)),),
        ),
    ),
    ids=(
        "normal",
        "interface-problem",
        "reference-problem",
        "design-problem",
        "implementation-problem",
        "precision-loop",
        "performance-loop",
        "complete-reopen",
    ),
)
def test_workflow_routes(
    transition: ModuleType,
    initial: dict[str, object],
    steps: tuple[tuple[str, str | None, tuple[str, str | None]], ...],
) -> None:
    state = initial
    for event, architecture, expected in steps:
        family = (
            str(state["algorithm_family"]) if event == "interface_accepted" else None
        )
        state = transition.transition_workflow(state, event, architecture, family)
        assert (state["stage"], state["issue_type"]) == expected


def test_interface_acceptance_freezes_selected_family_and_architecture(
    transition: ModuleType,
) -> None:
    state = _state("interface", architecture="pending", family="general")
    state = transition.transition_workflow(
        state,
        "interface_accepted",
        "ascend950",
        "flash_attention_grad",
    )
    assert state == _state(
        "reference",
        architecture="ascend950",
        family="flash_attention_grad",
    )
