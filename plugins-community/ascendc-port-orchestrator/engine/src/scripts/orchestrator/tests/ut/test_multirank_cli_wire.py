# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""multirank CLI dispatch wire tests — `--multirank` threads args into `_cmd_multirank`.

Covers the CLI wiring contract for the third scoped start mode:

- flag conflicts: `--multirank` is mutually exclusive with the other start
  modes (`--port-a3` / `--backward`), positional lifecycle input, `--resume`,
  and the migration-only `--precision-standard`;
- lane semantics: a comma-list `--lane` is inert for multirank (loud warning +
  dropped; the primary id stays as the .opgen_state.json bookkeeping lane);
- `_cmd_multirank` seed behavior: canonical spec copy, REQUIRED architecture.md
  check, op_classification.json (tags=mc2_fusion) + .opgen_state.json
  (opgen_mode/mc2_spec/target/lane/invocation_count) field assertions, and
  the run_single_op call shape (mirrors _cmd_port_a3/_cmd_backward);

Hermetic pattern mirrors test_port_a3_cli.py (fake engine on `commands._orch`
/ `cli._orch`; no live backend, no real workspace).
"""

from __future__ import annotations

import json
import os  # noqa: F401
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Import order matters for module identity: `orchestrator` must resolve to
# orchestrator.py (the MODULE), not the sibling package dir. Pinning it FIRST
# (same convention as test_p0u_cold_start.py) keeps orchestrator_cmds' lazy
# `orchestrator.logging_config` fallback from binding the package instead.
import orchestrator as orch  # noqa: E402,F401
import orchestrator_coldstart
import orchestrator_cli as cli
import orchestrator_cmds as commands


@pytest.fixture
def ascendc_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".ascendc_env"
    env_file.write_text(
        "\n".join(
            [
                "TARGET=a5",
                "A5_EXEC=local",
                "A5_CANN_PATH=/opt/cann",
                "A5_SOC_VERSION=Ascend950PR_9579",
                "LOCAL_PROJECT=/tmp/project",
            ]
        )
        + "\n"
    )
    from briefs import _common

    monkeypatch.setattr(_common, "DEFAULT_ASCENDC_ENV", env_file)
    return env_file


_SPEC_BODY = "SPEC = {'op': 'demo_fusion', 'truth': 'npubench'}\n"


def _mc2_workspace(tmp_path: Path, *, op: str = "mc2_demo_fusion") -> Path:
    """Create a canonical multirank pre-handoff layout: spec at the conventional
    workspace/<op>/spec.py location plus the REQUIRED architecture.md."""
    ws_root = tmp_path / "workspace"
    op_ws = ws_root / op
    op_ws.mkdir(parents=True)
    (op_ws / "spec.py").write_text(_SPEC_BODY)
    (op_ws / "architecture.md").write_text("# design doc\n")
    return ws_root


def _fake_engine(tmp_path: Path, *, run_rc: int = 0):
    calls = []

    def _run(*args, **kwargs):
        calls.append((args, kwargs))
        return run_rc

    return (
        SimpleNamespace(
            WORKSPACE_ROOT=tmp_path / "workspace",
            run_single_op=_run,
        ),
        calls,
    )


def _wire_mc2_cli(monkeypatch, *argv: str) -> list:
    """Wire a recording multirank engine + sys.argv; returns recorded calls."""
    calls: list = []
    engine = SimpleNamespace(
        _refuse_if_detached=lambda: None,
        _detect_max_lane=lambda: 2,
        _parse_bump_caps=lambda raw: {},
        _cmd_multirank=lambda **kwargs: calls.append(kwargs) or 0,
    )
    monkeypatch.setattr(cli, "_orch", lambda: engine)
    monkeypatch.setattr(sys, "argv", ["orchestrator", *argv])
    return calls


def _run_cmd_multirank(
    task: Path, ops_dir: Path, *, lane: int = 0, cold_start: bool = False
):
    """Invoke commands._cmd_multirank through the shared plan-only defaults."""
    return getattr(commands, "_cmd_multirank")(
        task=task,
        port_a3_dir=ops_dir,
        lane=lane,
        plan_only=True,
        cold_start=cold_start,
        cap_bumps={},
    )


def _ops_nn_dir(tmp_path: Path, *, name: str = "mc2_demo_fusion") -> Path:
    """A minimal arch22 ops-nn source dir (op_host + op_kernel/arch22 .cpp).

    The name defaults to the same op name `_mc2_workspace` seeds so the
    staged-source op-name rule (dirname, single-card rule) keeps resolving
    to the fixture workspace.
    """
    op_dir = tmp_path / "ops-nn" / name
    (op_dir / "op_host").mkdir(parents=True, exist_ok=True)
    kernel = op_dir / "op_kernel" / "arch22" / f"{name}.cpp"
    kernel.parent.mkdir(parents=True, exist_ok=True)
    kernel.write_text("class DemoOp { void Process() {} };\n")
    return op_dir


# ---------------------------------------------------------------------------
# CLI: flag conflicts + threading
# ---------------------------------------------------------------------------
_MC2_ARGV_BASE = [
    "--multirank",
    "--port-a3-ops",
    "/tmp/op",
    "--npubench-task",
    "/tmp/spec.py",
]


@pytest.mark.parametrize(
    "argv",
    [
        [*_MC2_ARGV_BASE, "--backward", "/tmp/fwd.py"],
        [*_MC2_ARGV_BASE, "--backward", "/tmp/fwd.py"],
        [*_MC2_ARGV_BASE, "demo"],
        [*_MC2_ARGV_BASE, "--resume"],
        [*_MC2_ARGV_BASE, "--precision-standard", "ecosystem"],
    ],
)
def test_multirank_flag_conflicts_are_rejected(monkeypatch, argv):
    calls = _wire_mc2_cli(monkeypatch, *argv)
    assert cli.main() == 2
    assert calls == []


def test_resolve_multirank_truth_tier_spec_driven(tmp_path):
    """SPEC['truth'] field > --reference-source > a3_live default — the
    spec is the durable declaration point; a CLI value may confirm it but
    never override it (same case-controlled principle as world_size).
    """
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "spec.py").write_text("SPEC = {}\n")
    # nothing declared -> default
    assert (
        getattr(commands, "_resolve_multirank_truth_tier")(plain / "spec.py")
        == "a3_live"
    )
    # spec-declared tier lands verbatim
    declared = tmp_path / "declared"
    declared.mkdir()
    (declared / "spec.py").write_text("SPEC = {'truth': 'npubench'}\n")
    assert (
        getattr(commands, "_resolve_multirank_truth_tier")(declared / "spec.py")
        == "npubench"
    )
    # a bogus declared value fails closed (raises; never reaches state)
    bogus = tmp_path / "bogus"
    bogus.mkdir()
    (bogus / "spec.py").write_text("SPEC = {'truth': 'npu_py'}\n")
    with pytest.raises(ValueError, match="not a multirank truth tier"):
        getattr(commands, "_resolve_multirank_truth_tier")(bogus / "spec.py")


def test_resolve_multirank_truth_tier_cli_agreement(tmp_path):
    """The CLI --reference-source value maps onto the tier names
    (npubench→npubench, a3_live→a3_live), declares the tier when the
    spec is silent, and must agree with a spec declaration.
    """
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "spec.py").write_text("SPEC = {}\n")
    resolve = getattr(commands, "_resolve_multirank_truth_tier")
    # CLI declares when the spec is silent
    assert resolve(plain / "spec.py", cli_reference="npubench") == "npubench"
    assert resolve(plain / "spec.py", cli_reference="a3_live") == "a3_live"
    # agreement with a matching declaration
    declared = tmp_path / "declared"
    declared.mkdir()
    (declared / "spec.py").write_text("SPEC = {'truth': 'npubench'}\n")
    assert resolve(declared / "spec.py", cli_reference="npubench") == "npubench"
    # disagreement fails closed (never silently overrides the spec)
    with pytest.raises(ValueError, match="durable declaration point"):
        resolve(declared / "spec.py", cli_reference="a3_live")


def test_multirank_without_port_a3_ops_is_rejected(monkeypatch, tmp_path):
    """The migration source is REQUIRED under --multirank — the same single-card

    input constraint; a task-only invocation fails closed at the CLI gate.
    """
    engine = SimpleNamespace(
        _refuse_if_detached=lambda: None,
        _detect_max_lane=lambda: 2,
        _parse_bump_caps=lambda raw: {},
    )
    monkeypatch.setattr(cli, "_orch", lambda: engine)
    spec = tmp_path / "spec.py"
    monkeypatch.setattr(
        sys,
        "argv",
        ["orchestrator", "--multirank", "--npubench-task", str(spec)],
    )
    assert cli.main() == 2


def test_cmd_multirank_missing_source_dir_is_rejected(tmp_path, monkeypatch):
    engine, calls = _fake_engine(tmp_path)
    monkeypatch.setattr(commands, "_orch", lambda: engine)
    task = tmp_path / "task.py"
    task.write_text(_TASK_FORM)
    assert _run_cmd_multirank(task, tmp_path / "no_such_ops_dir") == 2
    assert calls == []
    assert not engine.WORKSPACE_ROOT.exists()


def test_multirank_threads_spec_lane_and_cap_bumps(monkeypatch, tmp_path):
    spec = tmp_path / "spec.py"
    calls = _wire_mc2_cli(
        monkeypatch,
        "--multirank",
        "--port-a3-ops",
        "/tmp/op",
        "--npubench-task",
        str(spec),
        "--timing",
    )
    assert cli.main() == 0
    assert len(calls) == 1
    kwargs = calls[0]
    assert kwargs["task"] == spec
    assert kwargs["cap_bumps"] == {}  # no --bump-cap → {} (wire regression guard)
    assert kwargs["lane"] == 0  # default single lane = bookkeeping primary
    assert kwargs["timing"] is True


def test_multirank_lane_list_warns_and_drops(monkeypatch, tmp_path, capsys):
    spec = tmp_path / "spec.py"
    calls = _wire_mc2_cli(
        monkeypatch,
        "--multirank",
        "--port-a3-ops",
        "/tmp/op",
        "--npubench-task",
        str(spec),
        "--lane",
        "0,1",
    )
    assert cli.main() == 0
    out = capsys.readouterr().out
    assert "auto-allocates" in out and "--lane" in out
    kwargs = calls[0]
    assert kwargs["lane"] == 0  # primary kept for bookkeeping; list dropped
    assert "lane_list" not in kwargs


def test_multirank_single_lane_is_silent(monkeypatch, tmp_path, capsys):
    spec = tmp_path / "spec.py"
    calls = _wire_mc2_cli(
        monkeypatch,
        "--multirank",
        "--port-a3-ops",
        "/tmp/op",
        "--npubench-task",
        str(spec),
        "--lane",
        "1",
    )
    assert cli.main() == 0
    assert "auto-allocates" not in capsys.readouterr().out
    assert calls[0]["lane"] == 1


def test_lane_malformed_value_is_rejected(monkeypatch):
    engine = SimpleNamespace(_refuse_if_detached=lambda: None)
    monkeypatch.setattr(cli, "_orch", lambda: engine)
    monkeypatch.setattr(
        sys, "argv", ["orchestrator", "--port-a3-ops", "/tmp/op", "--lane", "abc"]
    )
    assert cli.main() == 2


# ---------------------------------------------------------------------------
# _cmd_multirank: spec validation + workspace seeding
# ---------------------------------------------------------------------------
def test_cmd_multirank_missing_spec_is_rejected(tmp_path, monkeypatch):
    engine, calls = _fake_engine(tmp_path)
    monkeypatch.setattr(commands, "_orch", lambda: engine)
    assert (
        getattr(commands, "_cmd_multirank")(
            task=tmp_path / "nope.py",
            port_a3_dir=_ops_nn_dir(tmp_path),
            lane=0,
            plan_only=True,
            cold_start=False,
            cap_bumps={},
        )
        == 2
    )
    non_py = tmp_path / "spec.txt"
    non_py.write_text(_SPEC_BODY)
    assert (
        getattr(commands, "_cmd_multirank")(
            task=non_py,
            port_a3_dir=_ops_nn_dir(tmp_path),
            lane=0,
            plan_only=True,
            cold_start=False,
            cap_bumps={},
        )
        == 2
    )
    assert calls == []
    assert not engine.WORKSPACE_ROOT.exists()


def test_cmd_multirank_declared_npu_tier_fails_early(
    tmp_path, monkeypatch, ascendc_env, capsys
):
    """SPEC['truth']=a3_live is refused BEFORE the workspace state is

    seeded — the provider is unwired, and the run must not silently fall
    back to another tier.
    """
    ws_root = tmp_path / "workspace"
    op_ws = ws_root / "a3_live_op"
    op_ws.mkdir(parents=True)
    (op_ws / "spec.py").write_text("SPEC = {'op': 'demo', 'truth': 'a3_live'}\n")
    (op_ws / "architecture.md").write_text("# design\n")
    engine, calls = _fake_engine(tmp_path)
    monkeypatch.setattr(commands, "_orch", lambda: engine)

    assert (
        getattr(commands, "_cmd_multirank")(
            task=op_ws / "spec.py",
            port_a3_dir=_ops_nn_dir(tmp_path, name="a3_live_op"),
            lane=0,
            plan_only=True,
            cold_start=False,
            cap_bumps={},
        )
        == 2
    )
    out = capsys.readouterr().out
    assert "not satisfiable" in out and "a3_live" in out
    # state must NOT be seeded (the tier never reaches durable state)
    assert not (op_ws / ".opgen_state.json").exists()
    assert calls == []


def test_cmd_multirank_seeds_classification_and_state(
    tmp_path, monkeypatch, ascendc_env
):
    ws_root = _mc2_workspace(tmp_path)
    engine, calls = _fake_engine(tmp_path)
    monkeypatch.setattr(commands, "_orch", lambda: engine)
    spec = ws_root / "mc2_demo_fusion" / "spec.py"

    assert (
        getattr(commands, "_cmd_multirank")(
            task=spec,
            port_a3_dir=_ops_nn_dir(tmp_path),
            lane=2,
            plan_only=True,
            cold_start=False,
            cap_bumps={},
        )
        == 0
    )
    op_ws = ws_root / "mc2_demo_fusion"
    state = json.loads((op_ws / ".opgen_state.json").read_text())
    assert state["opgen_mode"] == "port_a3_to_a5"
    assert state["multirank"] is True
    assert state["multirank_truth_source"] == "npubench"  # declared in the fixture spec
    assert state["op"] == "mc2_demo_fusion"
    # staged migration source: single-card arch22 snapshot fields
    assert state["graybox_sandbox"] is True
    assert state["source_arch"] == "arch22"
    assert state["port_a3_source"] == str(op_ws / ".source_arch22")
    assert state["source_stage_digest"]
    assert (op_ws / ".source_arch22" / "op_host").is_dir()
    assert state["spec"] == str(spec.resolve())
    assert state["target"] == "a5"
    assert state["lane"] == 2
    assert state["schema_version"] == 1
    assert state["invocation_count"] == 1
    assert state["started_ts"] and state["last_seen_ts"]
    classification = json.loads((op_ws / "op_classification.json").read_text())
    assert classification["op_class_tags"] == ["multirank_fusion"]
    assert classification["source"] == "cli_flag_multirank"
    assert classification["schema_version"] == 1
    assert calls == []  # --plan never enters the state machine


_TASK_FORM = """import torch


class Model(torch.nn.Module):
    def forward(self, x):
        return x * 2


def get_input_groups(rank=0, world_size=1):
    return [torch.arange(4, dtype=torch.float32)]


def get_init_inputs(rank=0, world_size=1):
    return []
"""

_TASK_SIDECAR = (
    '{"name": "c0", "world_size": 1, "inputs": '
    '[{"name": "x", "type": "tensor", "dtype": "float32", '
    '"shape": [4]}]}\n'
)


def test_cmd_multirank_converts_noncanonical_task_into_workspace(
    tmp_path, monkeypatch, ascendc_env
):
    ws_root = tmp_path / "workspace"
    (ws_root / "my_fusion_op").mkdir(parents=True)
    (ws_root / "my_fusion_op" / "architecture.md").write_text("# design\n")
    elsewhere = tmp_path / "elsewhere" / "my_fusion_op.py"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_text(_TASK_FORM)
    elsewhere.with_suffix(".jsonl").write_text(_TASK_SIDECAR)
    engine, _ = _fake_engine(tmp_path)
    monkeypatch.setattr(commands, "_orch", lambda: engine)

    assert (
        getattr(commands, "_cmd_multirank")(
            task=elsewhere,
            port_a3_dir=_ops_nn_dir(tmp_path, name="my_fusion_op"),
            lane=0,
            plan_only=True,
            cold_start=False,
            cap_bumps={},
            reference_source="npubench",
        )
        == 0
    )
    canonical = ws_root / "my_fusion_op" / "spec.py"
    assert "input_mode" in canonical.read_text()
    assert (canonical.parent / "task.py").is_file()
    state = json.loads((ws_root / "my_fusion_op" / ".opgen_state.json").read_text())
    assert state["spec"] == str(canonical.resolve())
    # Startup-time reference binding (finding #3): bound at run creation, so
    # a crash before O2.5 completes still leaves a resolvable binding.
    assert state["reference"]["source"] == "npubench"
    from reference_source import resolve_reference_binding

    assert resolve_reference_binding(state)["source"] == "npubench"


def test_cmd_multirank_rebinding_a_different_task_fails_closed(
    tmp_path, monkeypatch, ascendc_env
):
    """Finding #3 follow-up: a re-run that swaps the task under the same
    workspace must NOT silently rebind — the prior binding travels through
    the fold and bind_npubench_state rejects the differing bundle.
    """
    task_dir = tmp_path / "inputs"
    task_dir.mkdir()
    task = task_dir / "fused_demo.py"
    task.write_text(_TASK_FORM)
    task.with_suffix(".jsonl").write_text(_TASK_SIDECAR)
    engine, _ = _fake_engine(tmp_path)
    monkeypatch.setattr(commands, "_orch", lambda: engine)

    kwargs = dict(
        task=task,
        port_a3_dir=_ops_nn_dir(tmp_path),
        lane=0,
        plan_only=True,
        cold_start=False,
        cap_bumps={},
        reference_source="npubench",
    )
    assert getattr(commands, "_cmd_multirank")(**kwargs) == 0
    # Same workspace, DIFFERENT task bytes → the startup bind must fail closed
    task.write_text(_TASK_FORM.replace("x * 2", "x * 3"))
    task.with_suffix(".jsonl").write_text(_TASK_SIDECAR)
    assert getattr(commands, "_cmd_multirank")(**kwargs) == 2


def test_cmd_multirank_rejects_derived_spec_form(tmp_path, monkeypatch, ascendc_env):
    ws_root = tmp_path / "workspace"
    (ws_root / "my_fusion_op").mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere" / "my_fusion_op.py"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_text(_SPEC_BODY)
    engine, _ = _fake_engine(tmp_path)
    monkeypatch.setattr(commands, "_orch", lambda: engine)

    rc = _run_cmd_multirank(elsewhere, _ops_nn_dir(tmp_path, name="my_fusion_op"))
    assert rc == 2
    assert not (ws_root / "my_fusion_op" / "spec.py").exists()


def test_cmd_multirank_preserves_started_ts_and_counts_invocations(
    tmp_path, monkeypatch, ascendc_env
):
    ws_root = _mc2_workspace(tmp_path)
    engine, _ = _fake_engine(tmp_path)
    monkeypatch.setattr(commands, "_orch", lambda: engine)
    spec = ws_root / "mc2_demo_fusion" / "spec.py"

    assert _run_cmd_multirank(spec, _ops_nn_dir(tmp_path)) == 0
    first = json.loads((ws_root / "mc2_demo_fusion" / ".opgen_state.json").read_text())
    assert _run_cmd_multirank(spec, _ops_nn_dir(tmp_path)) == 0
    second = json.loads((ws_root / "mc2_demo_fusion" / ".opgen_state.json").read_text())
    assert second["invocation_count"] == 2
    assert second["started_ts"] == first["started_ts"]


def test_cmd_multirank_cold_start_resets_before_seeding(
    tmp_path, monkeypatch, ascendc_env
):
    ws_root = _mc2_workspace(tmp_path)
    engine, _ = _fake_engine(tmp_path)
    monkeypatch.setattr(commands, "_orch", lambda: engine)
    resets = []
    monkeypatch.setattr(
        commands, "_cold_start_reset_workspace", lambda ws: resets.append(ws)
    )

    assert (
        _run_cmd_multirank(
            ws_root / "mc2_demo_fusion" / "spec.py",
            _ops_nn_dir(tmp_path),
            cold_start=True,
        )
        == 0
    )
    assert resets == [ws_root / "mc2_demo_fusion"]
    _st = json.loads((ws_root / "mc2_demo_fusion" / ".opgen_state.json").read_text())
    assert _st["opgen_mode"] == "port_a3_to_a5" and _st["multirank"] is True


def test_cmd_multirank_live_entry_invokes_run_single_op(
    tmp_path, monkeypatch, ascendc_env
):
    ws_root = _mc2_workspace(tmp_path)
    engine, calls = _fake_engine(tmp_path, run_rc=19)
    monkeypatch.setattr(commands, "_orch", lambda: engine)

    assert (
        getattr(commands, "_cmd_multirank")(
            task=ws_root / "mc2_demo_fusion" / "spec.py",
            port_a3_dir=_ops_nn_dir(tmp_path),
            lane=1,
            plan_only=False,
            cold_start=False,
            cap_bumps={"worker": 1},
            timing=True,
        )
        == 19
    )
    args, kwargs = calls[0]
    assert args[0] == "mc2_demo_fusion"
    assert kwargs["workspace"] == ws_root / "mc2_demo_fusion"
    assert kwargs["lane"] == 1
    assert kwargs["plan_only"] is False
    assert kwargs["cap_bumps"] == {"worker": 1}
    assert kwargs["timing"] is True


# ---------------------------------------------------------------------------
# print-design-guide dispatch
# ---------------------------------------------------------------------------
def test_cold_start_wipes_mc2_nest_build_trees(tmp_path, monkeypatch):
    """prj-<op>/ build trees + py_ext .so are restore sources — a cold-start

    must wipe them in EVERY base (op root + each prj-*), not just the root.
    """
    monkeypatch.setenv("COLD_START_BACKUP_ROOT", str(tmp_path / ".bkp"))
    ws = tmp_path / "ws" / "mc2_demo_fusion"
    nest = ws / "prj-mc2_demo_fusion"
    for sub in (".install", ".build", ".build_ext", "op_kernel"):
        (nest / sub).mkdir(parents=True)
    (nest / "py_ext").mkdir()
    built_so = nest / "py_ext" / "_Cdemo.so"
    built_so.write_text("ELF")
    root_kernel = ws / "kernel"
    root_kernel.mkdir()
    # Pre-handoff inputs must survive the reset (allowlist delete).
    (ws / "spec.py").write_text(_SPEC_BODY)
    (ws / "architecture.md").write_text("# design\n")

    getattr(orchestrator_coldstart, "_cold_start_reset_workspace")(ws)

    assert not (nest / ".install").exists()
    assert not (nest / ".build").exists()
    assert not (nest / ".build_ext").exists()
    assert not built_so.exists()
    assert not root_kernel.exists()
    assert (ws / "spec.py").read_text() == _SPEC_BODY
    assert (ws / "architecture.md").is_file()


def test_cmd_multirank_preserves_existing_classification(
    tmp_path, monkeypatch, ascendc_env
):
    """A completed O1.7 classification carries source_sha256 (the content-hash

    cache key). Seeding the initial classification on EVERY start would clobber
    it, break the cache, and force a fresh multi-minute LLM re-classification
    per engine restart — the seed must be written only when the file is
    absent.
    """
    ws_root = _mc2_workspace(tmp_path)
    engine, calls = _fake_engine(tmp_path)
    monkeypatch.setattr(commands, "_orch", lambda: engine)
    op_ws = ws_root / "mc2_demo_fusion"
    spec = op_ws / "spec.py"
    (op_ws / "op_classification.json").write_text(
        json.dumps(
            {
                "op": "mc2_demo_fusion",
                "op_class_tags": ["multirank_fusion", "matmul", "reduction"],
                "kb_recommendations": [{"path": "KB_INDEX.md", "reason": "done"}],
                "source": "aog-op-classify",
                "source_sha256": "deadbeef" * 8,
                "schema_version": 3,
            }
        )
    )

    assert _run_cmd_multirank(spec, _ops_nn_dir(tmp_path)) == 0
    preserved = json.loads((op_ws / "op_classification.json").read_text())
    assert preserved["source_sha256"] == "deadbeef" * 8
    assert preserved["source"] == "aog-op-classify"
    assert preserved["kb_recommendations"][0]["path"] == "KB_INDEX.md"
