# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

from __future__ import annotations

import csv
import json
import subprocess
import sys
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREP = ROOT / "scripts" / "prepare_case_sets.py"
STATE = ROOT / "scripts" / "workflow_state.py"
DISCOVER = ROOT / "scripts" / "discover_references.py"


def _run(tool: Path, *args: str | Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(tool), *(str(a) for a in args)],
        text=True, capture_output=True, check=check,
    )


def _cases(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["case_id", "total_us"])
        w.writeheader()
        w.writerow({"case_id": "1", "total_us": "100"})
        w.writerow({"case_id": "2", "total_us": "200"})


def _prepared_run(tmp_path: Path, intent: str, *, with_reference: bool = False) -> Path:
    code = tmp_path / "code"
    code.mkdir()
    (code / "kernel.cpp").write_text("// k\n", encoding="utf-8")
    cases = tmp_path / "perf.csv"
    _cases(cases)
    req = tmp_path / "req.json"
    extra = ["--optimization-intent", intent]
    if with_reference:
        ref = tmp_path / "ref.csv"
        ref.write_text("case_id,ref_total_us\n1,50\n2,60\n", encoding="utf-8")
        extra += ["--reference-perf", str(ref)]
    _run(
        PREP, "create-request", "--request", req, "--operator-name", "mla_prolog",
        "--code-dir", code, "--target-soc", "Ascend950",
        "--performance-cases", cases, "--functional-mode", "reuse_performance",
        "--python-executable", sys.executable, "--cann-env-command", "inherit", *extra,
    )
    out = tmp_path / "out"
    _run(PREP, "freeze", "--request", req, "--output-dir", out)
    manifest = json.loads((out / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["configuration"]["optimization_intent"] == intent
    if with_reference:
        assert manifest["configuration"]["reference_perf"].endswith("ref.csv")
    _run(STATE, "start", "--state", out / "workflow-state.json", "--manifest", out / "run-manifest.json")
    state = json.loads((out / "workflow-state.json").read_text(encoding="utf-8"))
    assert state["optimization_intent"] == intent
    assert state["structural_directions"] == []
    return out


def test_pursue_optimal_gate_blocks_unresolved_and_allows_after_resolution(tmp_path: Path) -> None:
    out = _prepared_run(tmp_path, "pursue_optimal", with_reference=True)
    st = out / "workflow-state.json"
    _run(STATE, "structural-direction", "--state", st, "--id", "whole-op-fusion",
         "--status", "blocked_by_scope", "--round", "1")
    # success/completed must be rejected while a direction is blocked_by_scope
    rejected = _run(STATE, "finish", "--state", st, "--status", "success",
                    "--reason-code", "completed", "--message", "x", check=False)
    assert rejected.returncode != 0
    assert "unrealized structural directions" in (rejected.stderr + rejected.stdout)
    # resolving to realized clears the structural gate; control then passes to the
    # independently-enforced five-stage completeness gate (see test_five_stage_workflow.py).
    _run(STATE, "structural-direction", "--state", st, "--id", "whole-op-fusion", "--status", "realized")
    after = _run(STATE, "finish", "--state", st, "--status", "success",
                 "--reason-code", "completed", "--message", "done", check=False)
    combined = after.stderr + after.stdout
    assert "unrealized structural directions" not in combined
    assert "incomplete" in combined


def test_pursue_optimal_park_path_is_allowed(tmp_path: Path) -> None:
    out = _prepared_run(tmp_path, "pursue_optimal")
    st = out / "workflow-state.json"
    _run(STATE, "structural-direction", "--state", st, "--id", "fuse", "--status", "not_attempted")
    ok = _run(STATE, "finish", "--state", st, "--status", "awaiting_operator",
              "--reason-code", "structural_headroom_unrealized", "--message", "park")
    assert json.loads(ok.stdout)["status"] == "awaiting_operator"
    report = (out / "性能调优报告.md").read_text(encoding="utf-8")
    assert "结构方向台账" in report and "fuse" in report


def test_operator_decision_reopens_awaiting_workflow(tmp_path: Path) -> None:
    out = _prepared_run(tmp_path, "safe_incremental")
    st = out / "workflow-state.json"
    _run(STATE, "finish", "--state", st, "--status", "awaiting_operator",
         "--reason-code", "workflow_error", "--message", "recoverable gate issue")
    _run(STATE, "decision", "--state", st, "--decision", "resume after gate fix")
    state = json.loads(st.read_text(encoding="utf-8"))
    assert "terminal" not in state
    assert state["operator"]["awaiting"] is False
    assert state["operator"]["last_decision"] == "resume after gate fix"


def test_safe_incremental_does_not_gate(tmp_path: Path) -> None:
    out = _prepared_run(tmp_path, "safe_incremental")
    st = out / "workflow-state.json"
    _run(STATE, "structural-direction", "--state", st, "--id", "fuse", "--status", "blocked_by_scope")
    # safe_incremental never engages the structural gate, even with an unresolved direction;
    # finish only meets the separate five-stage completeness gate, never the structural one.
    res = _run(STATE, "finish", "--state", st, "--status", "success",
               "--reason-code", "completed", "--message", "ok", check=False)
    combined = res.stderr + res.stdout
    assert "unrealized structural directions" not in combined
    assert "incomplete" in combined


def test_discover_references_finds_sibling_dirs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "mla_prolog" / "op_kernel").mkdir(parents=True)
    (repo / "mla_prolog_v3" / "op_kernel").mkdir(parents=True)
    (repo / "mla_prolog" / "op_kernel" / "k.cpp").write_text("//\n", encoding="utf-8")
    self_dir = tmp_path / "self" / "mla_prolog"
    self_dir.mkdir(parents=True)
    out = tmp_path / "refs.json"
    res = _run(DISCOVER, "--operator", "mla_prolog", "--cann-home", tmp_path / "nonexist",
               "--search-root", repo, "--self-dir", self_dir, "--out", out)
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["aclnn_prefix"] == "aclnnMlaProlog"
    names = {Path(c["path"]).name for c in report["sibling_references"]}
    assert {"mla_prolog", "mla_prolog_v3"} <= names
    assert json.loads(res.stdout)["sibling_references"] >= 2
