# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Git-mode CLI tests: conformance and integration gates over git revisions.

The defining property under test: gates read evidence from the frozen commit,
never from a live worktree, so uncommitted worktree changes cannot sway a gate.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPTS = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "ops-perf-optimize-workflow"
    / "scripts"
)
CONFORMANCE_SCRIPT = SCRIPTS / "validate_implementation_conformance.py"
SAFETY_SCRIPT = SCRIPTS / "validate_integration_safety.py"
sys.path.insert(0, str(SCRIPTS))

from validate_source_isolation import snapshot_from_git  # noqa: E402


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-c", "core.autocrlf=false", "-C", str(repo), *args),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def write(repo: Path, relative: str, content: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD").strip()


def contract() -> dict:
    return {
        "schema_version": 3,
        "scheme_id": "strategy1_global_base",
        "implementation_mode": "exact",
        "substitution_policy": "forbidden",
        "target_socs": ["Ascend950"],
        "safety": {"public_contract": "unchanged", "non_target_socs": "unchanged"},
        "expectations": {"vf": False, "casttrait": False},
        "required_features": [
            {"id": "reg_vf_hot_path", "description": "Keep the hot reduction in Reg VF"},
        ],
    }


def complete_result() -> dict:
    return {
        "schema_version": 3,
        "scheme_id": "strategy1_global_base",
        "implementation_status": "complete",
        "route_changed": False,
        "substitution_used": False,
        "features": {
            "reg_vf_hot_path": {
                "status": "pass",
                "evidence_files": ["compile.json"],
                "source_locations": ["op_kernel/kernel.cpp:2"],
            },
        },
    }


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "tester")
    git(repo, "config", "user.email", "tester@example.com")
    write(repo, "op_kernel/kernel.cpp", "line1\nline2\nline3\n")
    write(repo, "op_kernel/shared.h", "void Shared() {}\n")
    write(repo, "op_host/config/ascend910b/op.json", "{}\n")
    write(repo, "op_host/config/ascend950/op.json", "{}\n")
    write(repo, "op_host/peer_tiling.cpp",
          "if (soc == ASCEND950) { return Arch35Tiling(); }\nreturn LegacyTiling();\n")
    write(repo, "op_kernel/legacy_kernel.hpp", "// legacy stays reachable\n")
    write(repo, "op_host/op_api/aclnn_test.cpp", "supported = {DT_FLOAT16};\n")
    write(repo, ".gitattributes", "* text=auto eol=lf\n")
    commit_all(repo, "baseline")
    return repo


def write_json(path: Path, value) -> Path:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_conformance(tmp_path: Path, repo: Path, baseline_rev: str, candidate_rev: str) -> dict:
    args = [
        sys.executable, str(CONFORMANCE_SCRIPT),
        "--git-repo", str(repo),
        "--baseline-rev", baseline_rev,
        "--candidate-rev", candidate_rev,
        "--contract", str(write_json(tmp_path / "contract.json", contract())),
        "--result", str(write_json(tmp_path / "result.json", complete_result())),
        "--manifest", str(write_json(tmp_path / "manifest.json",
                                     {"configuration": {"target_socs": ["Ascend950"]}})),
        "--isolation-scope", str(tmp_path / "isolation.json"),
        "--out", str(tmp_path / "gate.json"),
    ]
    return args


def isolation_scope_v2(repo: Path, baseline_rev: str, ranges: dict, additions: dict) -> dict:
    from git_tree import tree_sha
    return {
        "schema_version": 2,
        "target_socs": ["Ascend950"],
        "baseline_commit": git(repo, "rev-parse", baseline_rev).strip(),
        "baseline_tree_sha": tree_sha(repo, baseline_rev),
        "editable_ranges": ranges,
        "new_files": additions,
    }


def test_conformance_git_mode_passes_and_ignores_live_worktree(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    baseline_rev = git(repo, "rev-parse", "HEAD").strip()
    write(repo, "op_kernel/kernel.cpp", "line1\nline2  /* optimized */\nline3\n")
    write(repo, "compile.json", "{}\n")
    candidate_rev = commit_all(repo, "candidate")

    scope = isolation_scope_v2(repo, baseline_rev, {
        "op_kernel/kernel.cpp": [{"start": 2, "end": 2, "kind": "routing", "reason": "hot path"}],
    }, {})
    args = run_conformance(tmp_path, repo, baseline_rev, candidate_rev)
    args[args.index("--isolation-scope") + 1] = str(write_json(tmp_path / "isolation.json", scope))

    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    gate = json.loads((tmp_path / "gate.json").read_text())
    assert gate["decision"] == "pass"
    assert gate["source_isolation"]["decision"] == "pass"
    assert gate["candidate_safety"]["decision"] == "pass"
    assert gate["evidence_identity"]["candidate"]["commit"] == candidate_rev

    # Dirty the live worktree: gates must still read the frozen commit only.
    write(repo, "compile.json", '{"tampered": true}\n')
    write(repo, "op_kernel/kernel.cpp", "totally different\n")
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads((tmp_path / "gate.json").read_text())["decision"] == "pass"


def test_conformance_git_mode_rejects_out_of_scope_edit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    baseline_rev = git(repo, "rev-parse", "HEAD").strip()
    write(repo, "op_kernel/kernel.cpp", "line1\nline2  /* optimized */\nline3\n")
    write(repo, "op_kernel/shared.h", "void Shared() { optimized; }\n")
    write(repo, "compile.json", "{}\n")
    candidate_rev = commit_all(repo, "candidate")

    scope = isolation_scope_v2(repo, baseline_rev, {
        "op_kernel/kernel.cpp": [{"start": 2, "end": 2, "kind": "routing", "reason": "hot path"}],
    }, {})
    args = run_conformance(tmp_path, repo, baseline_rev, candidate_rev)
    args[args.index("--isolation-scope") + 1] = str(write_json(tmp_path / "isolation.json", scope))

    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode == 1, result.stdout + result.stderr
    gate = json.loads((tmp_path / "gate.json").read_text())
    assert gate["decision"] == "fail"
    assert any("edit outside frozen scope" in message for message in gate["source_isolation"]["failures"])


def integration_scope(routes: bool) -> dict:
    value = {
        "schema_version": 2,
        "target_socs": ["Ascend950"],
        "verified_socs": ["Ascend950"],
        "supported_socs": [
            {"name": "Ascend910B", "evidence": ["op_host/config/ascend910b/op.json"]},
            {"name": "Ascend950", "evidence": ["op_host/config/ascend950/op.json"]},
        ],
        "project_isolation_style": {
            "kind": "soc-version-route+arch-directory",
            "target_path_markers": ["arch35", "ascend950"],
            "target_route_tokens": ["ASCEND950", "arch35"],
            "evidence": ["op_host/peer_tiling.cpp:1"],
        },
        "shared_file_routes": {},
    }
    if routes:
        value["shared_file_routes"] = {
            "op_kernel/kernel.cpp": {
                "target_guard": ["op_kernel/kernel.cpp:1"],
                "non_target_fallback": ["op_kernel/kernel.cpp:3"],
            }
        }
    return value


def test_integration_safety_git_mode_guards_shared_changes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    baseline_rev = git(repo, "rev-parse", "HEAD").strip()
    write(repo, "op_kernel/kernel.cpp", "if (soc == ASCEND950) { return Opt(); }\nline2\nreturn Legacy();\n")
    candidate_rev = commit_all(repo, "candidate")

    isolation = isolation_scope_v2(repo, baseline_rev, {
        "op_kernel/kernel.cpp": [{"start": 1, "end": 3, "kind": "routing", "reason": "target dispatch"}],
    }, {})
    args = [
        sys.executable, str(SAFETY_SCRIPT),
        "--git-repo", str(repo),
        "--baseline-rev", baseline_rev,
        "--candidate-rev", candidate_rev,
        "--manifest", str(write_json(tmp_path / "manifest.json",
                                     {"configuration": {"target_socs": ["Ascend950"]}})),
        "--scope", str(write_json(tmp_path / "scope.json", integration_scope(routes=True))),
        "--isolation-scope", str(write_json(tmp_path / "isolation.json", isolation)),
        "--out", str(tmp_path / "gate.json"),
    ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    gate = json.loads((tmp_path / "gate.json").read_text())
    assert gate["decision"] == "pass"
    assert gate["auto_discovered_add_config_socs"] == {}

    args[args.index("--scope") + 1] = str(write_json(tmp_path / "scope-noroutes.json",
                                                     integration_scope(routes=False)))
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode == 1, result.stdout + result.stderr
    gate = json.loads((tmp_path / "gate.json").read_text())
    assert gate["decision"] == "fail"
    assert any("lacks SoC-isolation evidence" in message for message in gate["failures"])


def test_git_mode_rejects_mixed_cli_modes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    head = git(repo, "rev-parse", "HEAD").strip()
    args = run_conformance(tmp_path, repo, head, head)
    args += ["--baseline", str(tmp_path), "--candidate", str(tmp_path)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    assert result.returncode == 2
    assert "choose either" in result.stderr
