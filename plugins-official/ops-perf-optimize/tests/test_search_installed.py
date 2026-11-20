# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Exercise the shipped search workflow through real source/package installs."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]


def command(argv, *, cwd, env=None):
    result = subprocess.run(
        list(map(str, argv)),
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.fixture(scope="module", params=["package", "source"])
def installed_search(request, tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the actual plugin installer")
    root = tmp_path_factory.mktemp("installed-search-" + request.param)
    project = root / "project"
    project.mkdir()
    unrelated = root / "unrelated"
    unrelated.mkdir()
    env = dict(os.environ)
    for key in (
        "CANNBOT_SOURCE_ROOT",
        "CANNBOT_SKILLS_PATH",
        "OPS_THEORETICAL_SKILL",
        "PYTHONPATH",
    ):
        env.pop(key, None)
    env.update(
        CANNBOT_SKIP_CODEX_PLUGIN_ADD="1",
        CANNBOT_SKIP_OPENCODE_PLUGIN_ADD="1",
        CANNBOT_SKIP_DEPENDENCY_REPOS="1",
        CANNBOT_SKIP_OPMODEL_INSTALL="1",
        XDG_CACHE_HOME=str(root / "cache"),
    )
    if request.param == "package":
        package = root / "package"
        package.mkdir()
        for name in ("bin", "lib"):
            shutil.copytree(REPO / "script" / name, package / name)
        shutil.copy2(REPO / "script/package.json", package / "package.json")
        assembler = (REPO / "script/lib/plugin-bundle.js").as_uri()
        code = (
            f"import {{assemblePlugins}} from {json.dumps(assembler)}; "
            "assemblePlugins(process.argv[1], process.argv[2], ['ops-perf-optimize']);"
        )
        command(
            [node, "--input-type=module", "-e", code, REPO, package / "dist"],
            cwd=unrelated,
            env=env,
        )
        cli = package / "bin/cannbot.js"
        extra = []
    else:
        cli = REPO / "script/bin/cannbot.js"
        extra = ["--source", REPO, "--skills", REPO / "vendor/cannbot-skills"]
    command(
        [
            node,
            cli,
            "install",
            "ops-perf-optimize",
            "--tool",
            "codex",
            "--target",
            project,
            *extra,
        ],
        cwd=unrelated,
        env=env,
    )
    skills = project / ".agents/skills"
    workflow = skills / "ops-perf-optimize-workflow"
    assert workflow.is_symlink() == (request.param == "source")
    return {
        "skills": skills,
        "scripts": workflow / "scripts",
        "cwd": unrelated,
        "env": env,
    }


def python(installed, code, *args):
    # A fresh isolated interpreter prevents earlier tests from supplying imports.
    prefix = "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
    return command(
        [sys.executable, "-I", "-c", prefix + code, installed["scripts"], *args],
        cwd=installed["cwd"],
        env=installed["env"],
    )


def test_installed_frontier_document_links_are_available(installed_search):
    from stage_skill_contract import check_skill_layout

    skills = installed_search["skills"]
    check_skill_layout(skills, skills / "ops-perf-optimize-workflow/workflows")
    files = [
        skills / "ops-perf-optimize-workflow/references/workflow-contract.md",
        skills / "ops-perf-analysis/references/analysis-execution.md",
        skills / "ops-perf-implementation/references/selection-and-final.md",
        skills / "ops-perf-acceptance-criteria/references/architecture-search.md",
    ]
    broken = []
    for file in files:
        for target in re.findall(r"\]\(([^)]+)\)", file.read_text()):
            path = target.split("#", 1)[0]
            if not path or "://" in path:
                continue
            resolved = (file.parent / path).resolve()
            if not resolved.is_file():
                broken.append(f"{file.name}: {target}")
    assert not broken, broken


def test_installed_roofline_finds_and_runs_the_installed_engine(installed_search):
    expected = installed_search["skills"] / "ops-theoretical-performance-estimation"
    python(
        installed_search,
        """
import l0_roofline
skill = l0_roofline.default_skill_dir()
assert skill is not None, 'installed Roofline skill was not found'
assert skill.resolve() == Path(sys.argv[2]).resolve(), skill
results, variant = l0_roofline.run_engine(skill, 'rms_norm', skill / 'references/examples/rms_norm_cases.json')
assert results['rms_norm_s_512x4096']['theoretical_time_us'] > 0
assert variant == 'ascend950pr_9589'
""",
        expected,
    )


def test_installed_screening_loads_report_backend_in_a_fresh_process(installed_search):
    expected = (
        installed_search["skills"] / "ops-profiling-report/scripts/report_contract.py"
    )
    python(
        installed_search,
        """
import search_policy
try:
    search_policy.checked_screening({}, {'configuration': {'performance_effect_policy': 'median_v1'}}, {}, {}, {}, [])
except ValueError as error:
    assert 'screening requires the confidence policy' in str(error)
else:
    raise AssertionError('wrong policy must be rejected')
import report_contract
assert Path(report_contract.__file__).resolve() == Path(sys.argv[2]).resolve()
""",
        expected,
    )


def test_installed_cli_entrypoints_load_without_checkout_imports(installed_search):
    names = [
        "search_candidates.py",
        "search_round.py",
        "search_observation.py",
        "search_selection.py",
        "search_kb_space.py",
        "search_prefilter.py",
        "l0_roofline.py",
        "opmodel_rank.py",
        "workflow_state.py",
    ]
    for name in names:
        command(
            [sys.executable, installed_search["scripts"] / name, "--help"],
            cwd=installed_search["cwd"],
            env=installed_search["env"],
        )


def test_installed_stage_workflow_promotes_and_verifies_evidence(
    installed_search, tmp_path, monkeypatch
):
    import test_search_policy as fixtures
    from test_search_frontier import attached_frontier, frontier, observation

    # Only fixture-generated data comes from the tests; every workflow command
    # executes the installed script in its own process.
    monkeypatch.setattr(fixtures, "SCRIPTS", installed_search["scripts"])
    run = fixtures.Run(tmp_path)
    contract, frontier_path = attached_frontier(run, frontier(tmp_path))
    args, _, _ = run.outcome(1, contract, values=(90, 90), selected=True)
    observation(tmp_path / "round1/selection.json")
    run.cli("mark", *args)
    assert "s1" in run.view()["accepted_decisions"]
    assert run.cli("verify")["status"] == "valid"
    frontier_path.write_text(frontier_path.read_text() + " ")
    assert run.cli("verify", ok=False)["status"] != "valid"


def test_installed_round_consumes_evidence_and_keeps_failed_holdout_unselected(
    installed_search, tmp_path
):
    from test_search_evidence import make_index
    from test_search_round import contract_for_frontier, options

    data = options(tmp_path)
    argv = [
        sys.executable,
        installed_search["scripts"] / "search_round.py",
        "--space",
        data.space,
        "--parent",
        data.parent,
        "--trigger",
        data.trigger,
        "--round",
        "round1",
        "--best-us",
        "100",
        "--n",
        "2",
        "--out-dir",
        data.out_dir,
    ]

    def run(*extra):
        output = command(
            [*argv, *extra], cwd=installed_search["cwd"], env=installed_search["env"]
        )
        return json.loads(output.splitlines()[-1])

    planned = run("--dry-run")
    nodes = json.loads(Path(planned["frontier"]).read_text())["nodes"]
    tuning = make_index(
        tmp_path / "tuning", {node["scheme_id"]: [90, 90] for node in nodes}
    )
    manifest = tmp_path / "tuning/manifest.json"
    holdout = make_index(
        tmp_path / "holdout",
        {node["scheme_id"]: [95, 95] for node in nodes},
        cases=("h1", "h2"),
        manifest=manifest,
    )
    evidence_args = ["--evidence-index", tuning, "--holdout-evidence-index", holdout]
    result = run(*evidence_args)
    assert result["ready_for_confirmation"] is True
    assert result["selection"] is None
    make_index(
        tmp_path / "holdout",
        {node["scheme_id"]: [120, 120] for node in nodes},
        cases=("h1", "h2"),
        manifest=manifest,
    )
    result = run(*evidence_args)
    assert result["ready_for_confirmation"] is False
    assert result["confirmation_blocker"] == "holdout_regression"
    assert result["selection"] is None

    # Consume the analysis handoff using only the registered frontier, current
    # contract and real summaries; no generation/model inputs are supplied.
    frontier_path = Path(planned["frontier"])
    original = frontier_path.read_bytes()
    contract = contract_for_frontier(json.loads(original))
    contract_path = tmp_path / "implementation-contract.json"
    contract_path.write_text(json.dumps(contract))
    selected_index = make_index(
        tmp_path / "selected", {contract["scheme_id"]: [90, 90]}
    )
    output = command(
        [
            sys.executable,
            installed_search["scripts"] / "search_round.py",
            "--frontier",
            frontier_path,
            "--contract",
            contract_path,
            "--evidence-index",
            selected_index,
            "--out-dir",
            tmp_path / "implementation",
        ],
        cwd=installed_search["cwd"],
        env=installed_search["env"],
    )
    result = json.loads(output.splitlines()[-1])
    assert result["status"] == "completed"
    assert frontier_path.read_bytes() == original
    assert result["frontier"] == str(frontier_path.resolve())
    measurements = json.loads(Path(result["measurements"]).read_text())
    assert [item["scheme_id"] for item in measurements["candidates"]] == [
        contract["scheme_id"]
    ]
