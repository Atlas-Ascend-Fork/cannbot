# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Unit tests for the task→spec static converter and the task-generated
provision/verify plumbing.

Collector mocked; no NPU.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
_ORCH_DIR = _HERE.parent.parent.parent.parent  # src/scripts/orchestrator/
if str(_ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(_ORCH_DIR))

from plugins.multirank.op_template_gen import task_to_spec  # noqa: E402

torch = pytest.importorskip("torch")

_TASK_SRC = """\
import torch


class Model(torch.nn.Module):
    def forward(self, x, alpha=1.0):
        return torch.mul(x, alpha)


def get_input_groups(rank=0, world_size=1):
    base = torch.arange(8, dtype=torch.float32).view(4, 2)
    return [base + rank]


def get_init_inputs(rank=0, world_size=1):
    return []
"""

_SIDECAR = [
    {
        "name": "base",
        "inputs": [
            {"name": "x", "type": "tensor", "dtype": "float32", "shape": [4, 2]},
            {"name": "alpha", "type": "attr", "value": 1.5},
        ],
        "world_size": 2,
    },
    {
        "name": "single",
        "inputs": [
            {"name": "x", "type": "tensor", "dtype": "float32", "shape": [4, 2]},
            {"name": "alpha", "type": "attr", "value": -0.5},
        ],
    },
]


def _write_pair(tmp_path: Path, task_src=_TASK_SRC, cases=None):
    task = tmp_path / "fused_demo.py"
    task.write_text(task_src)
    sidecar = tmp_path / "fused_demo.jsonl"
    sidecar.write_text("\n".join(json.dumps(c) for c in (cases or _SIDECAR)))
    return task, sidecar


# --- converter ---------------------------------------------------------------


def test_convert_maps_sidecar_and_freezes_task(tmp_path):
    task, _ = _write_pair(tmp_path)
    out = tmp_path / "ws"
    spec_path = task_to_spec.convert_task_to_spec(task, out_dir=out, op="fused_demo")
    assert spec_path == out / "spec.py"
    assert (out / "task.py").is_file() and (out / "fused_demo.jsonl").is_file()
    import importlib.util

    mod = importlib.util.module_from_spec(
        importlib.util.spec_from_file_location("_spec_ut", spec_path)
    )
    mod.__file__ = str(spec_path)
    exec(compile(spec_path.read_bytes(), str(spec_path), "exec"), mod.__dict__)
    spec = mod.SPEC
    assert spec["op_name"] == "fused_demo"
    assert spec["input_mode"] == "task_generated"
    assert spec["truth"] == "npubench"
    assert spec["kernel_input_order"] == ["x"]
    assert [(c["name"], c["world_size"]) for c in spec["cases"]] == [
        ("base", 2),
        ("single", 1),
    ]
    assert spec["world_sizes"] == [1, 2]
    assert len(spec["task_sha256"]) == 64
    assert not spec["needs_ep_comm"]
    assert callable(mod.get_input_groups) and callable(mod.get_init_inputs)


def _load_spec(spec_path: Path) -> dict:
    import importlib.util

    mod = importlib.util.module_from_spec(
        importlib.util.spec_from_file_location("_spec_ut", spec_path)
    )
    mod.__file__ = str(spec_path)
    exec(compile(spec_path.read_bytes(), str(spec_path), "exec"), mod.__dict__)
    return mod.SPEC


def test_convert_maps_sidecar_declared_tolerance_into_spec(tmp_path):
    cases = [dict(c, tolerance={"atol": 2.0, "rtol": 0.02}) for c in _SIDECAR]
    task, _ = _write_pair(tmp_path, cases=cases)
    spec = _load_spec(task_to_spec.convert_task_to_spec(task, out_dir=tmp_path / "ws"))
    assert spec["tolerance"] == {"atol": 2.0, "rtol": 0.02}


def test_convert_without_tolerance_declaration_omits_key(tmp_path):
    task, _ = _write_pair(tmp_path)
    spec = _load_spec(task_to_spec.convert_task_to_spec(task, out_dir=tmp_path / "ws"))
    assert "tolerance" not in spec


def test_convert_rejects_inconsistent_case_tolerances(tmp_path):
    first, second = dict(_SIDECAR[0]), dict(_SIDECAR[1])
    first["tolerance"] = {"atol": 2.0, "rtol": 0.02}
    second["tolerance"] = {"atol": 1.0, "rtol": 0.01}
    task, _ = _write_pair(tmp_path, cases=[first, second])
    with pytest.raises(task_to_spec.TaskConversionError, match="disagrees"):
        task_to_spec.convert_task_to_spec(task, out_dir=tmp_path / "ws")


@pytest.mark.parametrize(
    "bad",
    [
        {"atol": -1.0},
        {"atol": "2"},
        {"atol": True},
        {"epsilon": 1e-3},
        {},
    ],
)
def test_convert_rejects_malformed_tolerance(tmp_path, bad):
    cases = [dict(_SIDECAR[0], tolerance=bad)]
    task, _ = _write_pair(tmp_path, cases=cases)
    with pytest.raises(task_to_spec.TaskConversionError, match="tolerance"):
        task_to_spec.convert_task_to_spec(task, out_dir=tmp_path / "ws")


def test_convert_rejects_generator_without_rank_kwarg(tmp_path):
    bad = _TASK_SRC.replace(
        "def get_input_groups(rank=0, world_size=1):", "def get_input_groups():"
    )
    task, _ = _write_pair(tmp_path, task_src=bad)
    with pytest.raises(task_to_spec.TaskConversionError, match="rank"):
        task_to_spec.convert_task_to_spec(task, out_dir=tmp_path / "ws")


def test_convert_requires_sidecar(tmp_path):
    task = tmp_path / "fused_demo.py"
    task.write_text(_TASK_SRC)
    with pytest.raises(task_to_spec.TaskConversionError, match="sidecar"):
        task_to_spec.convert_task_to_spec(task, out_dir=tmp_path / "ws")


def test_is_task_form(tmp_path):
    task, _ = _write_pair(tmp_path)
    assert task_to_spec.is_task_form(task)
    specish = tmp_path / "spec.py"
    specish.write_text("SPEC = {'op': 'x'}\n")
    assert not task_to_spec.is_task_form(specish)


def test_digest_tracks_task_bytes(tmp_path):
    task, _ = _write_pair(tmp_path)
    out1 = tmp_path / "ws1"
    task_to_spec.convert_task_to_spec(task, out_dir=out1)
    task.write_text(_TASK_SRC.replace("torch.mul(x, alpha)", "torch.mul(x, alpha) + 1"))
    out2 = tmp_path / "ws2"
    task_to_spec.convert_task_to_spec(task, out_dir=out2)
    import importlib.util

    def spec_of(d):
        p = d / "spec.py"
        m = importlib.util.module_from_spec(
            importlib.util.spec_from_file_location("_s", p)
        )
        m.__file__ = str(p)
        exec(compile(p.read_bytes(), str(p), "exec"), m.__dict__)
        return m.SPEC

    assert spec_of(out1)["task_sha256"] != spec_of(out2)["task_sha256"]


# --- provision through the mocked task-mode collector -------------------------


def _fake_task_collector(monkeypatch, launched: list):
    """Stand-in for run_collector in task mode: executes the task's own
    Model/get_input_groups per rank in-process (mirrors the sequential
    collector path; the multiprocess HCCL path needs a live endpoint)."""
    import importlib.util
    from plugins.multirank import multirank_endpoint as ep_mod

    def _collector(launch):
        spec_path = launch.spec_path
        in_file, out_file = launch.in_file, launch.out_file
        payload = torch.load(in_file, weights_only=False)
        assert payload.get("mode") == "task"
        m = importlib.util.module_from_spec(
            importlib.util.spec_from_file_location("_s", Path(spec_path))
        )
        m.__file__ = str(spec_path)
        exec(compile(Path(spec_path).read_bytes(), str(spec_path), "exec"), m.__dict__)
        ws = int(payload["world_size"])
        decl = m.SPEC["inputs"]
        tensor_pos = [i for i, d in enumerate(decl) if d.get("type") == "tensor"]
        per_rank, order = {}, None
        for r in range(ws):
            group = m.get_input_groups(rank=r, world_size=ws)
            model = m.Model(*m.get_init_inputs(rank=r, world_size=ws))
            out = model(*group)
            named = {decl[i]["name"]: group[i] for i in tensor_pos}
            order = list(named.keys()) if order is None else order
            per_rank[str(r)] = {
                "inputs": {k: v.clone() for k, v in named.items()},
                "outputs": {"out0": out.cpu()},
            }
        launched.append(ws)
        torch.save(
            {
                "kernel_input_order": order,
                "per_rank": per_rank,
                "canonical_outputs": dict(per_rank["0"]["outputs"]),
            },
            out_file,
        )
        return out_file

    monkeypatch.setattr(ep_mod, "run_collector", _collector)

    def _load_env():
        from briefs._common import AscendCEnv, TargetConfig

        return AscendCEnv(
            target="a5", targets={"a5": TargetConfig(arch="a5", exec_mode="local")}
        )

    monkeypatch.setattr(ep_mod, "load_env_or_none", _load_env)


def _write_state_tier(ws: Path, tier: str) -> None:
    from plugins.multirank import TRUTH_TIER_STATE_KEY

    (ws / ".opgen_state.json").write_text(
        json.dumps(
            {
                "opgen_mode": "port_a3_to_a5",
                "multirank": True,
                TRUTH_TIER_STATE_KEY: tier,
            }
        )
    )


def _task_ws(tmp_path: Path, *, tier: str = "npubench") -> Path:
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    task, _ = _write_pair(src_dir)
    ws = tmp_path / "workspace" / "fused_demo"
    task_to_spec.convert_task_to_spec(task, out_dir=ws, op="fused_demo")
    _write_state_tier(ws, tier)
    return ws


def test_provision_task_form_publishes_stored_ranks(tmp_path, monkeypatch):
    from plugins.multirank import multirank_phase_o25 as p25m

    launched: list = []
    _fake_task_collector(monkeypatch, launched)
    ws = _task_ws(tmp_path)
    rep = p25m.provision_multirank_reference(workspace=ws, op="fused_demo")
    assert rep.verdict == "READY", rep.summary
    assert launched == [2, 1]  # ws=2 case then ws=1 case
    golden_dir = ws / "golden"
    assert (golden_dir / "manifest.json").is_file()
    manifest = json.loads((golden_dir / "manifest.json").read_text())
    assert manifest["n_cases"] == 2
    files = sorted(p.name for p in golden_dir.glob("*.pt"))
    assert len(files) == 2
    rec = torch.load(golden_dir / files[0], weights_only=False)
    assert "ranks" in rec and "full_inputs" not in rec
    rank1 = rec["ranks"]["1"]
    # rank 1's inputs are the generator's rank-shifted tensors (stored as-is)
    assert torch.allclose(
        rank1["inputs"]["x"], torch.arange(8, dtype=torch.float32).view(4, 2) + 1
    )


def test_provision_task_form_rejects_unwired_a3_live(tmp_path, monkeypatch):
    from plugins.multirank import multirank_phase_o25 as p25m

    _fake_task_collector(monkeypatch, [])  # env mock: pass tier feasibility
    from plugins.multirank import multirank_endpoint as ep_mod

    monkeypatch.setattr(
        ep_mod, "tier_feasibility_errors", lambda tier, env: None
    )  # isolate the wrapper gate
    ws = _task_ws(tmp_path, tier="a3_live")
    # a3_live without the pre-handoff wrapper fails closed
    rep = p25m.provision_multirank_reference(workspace=ws, op="fused_demo")
    assert rep.verdict == "REF_UNAVAILABLE"
    assert "wrapper" in rep.summary


def test_provision_a3_live_runs_source_collector(tmp_path, monkeypatch):
    """a3_live with the wrapper present: the campaign runs on the SOURCE
    endpoint with the wrapper threaded through to the collector.
    """
    from plugins.multirank import multirank_phase_o25 as p25m
    from plugins.multirank import multirank_endpoint as ep_mod
    from briefs._common import AscendCEnv, TargetConfig

    calls = {}

    def _collector(launch):
        import torch as th

        calls["wrapper"] = launch.wrapper_path
        in_file, out_file = launch.in_file, launch.out_file
        payload = th.load(in_file, weights_only=False)
        ws = int(payload["world_size"])
        per_rank = {
            str(r): {
                "inputs": {"x": th.ones(2) + r},
                "outputs": {"out0": th.ones(2) * (r + 1)},
            }
            for r in range(ws)
        }
        th.save(
            {
                "kernel_input_order": ["x"],
                "per_rank": per_rank,
                "canonical_outputs": dict(per_rank["0"]["outputs"]),
            },
            out_file,
        )
        return out_file

    monkeypatch.setattr(ep_mod, "run_collector", _collector)
    monkeypatch.setattr(
        ep_mod,
        "load_env_or_none",
        lambda: AscendCEnv(
            target="a5",
            source_arch="a2",
            targets={
                "a5": TargetConfig(arch="a5", exec_mode="local"),
                "a2": TargetConfig(arch="a2", exec_mode="local"),
            },
        ),
    )
    monkeypatch.setattr(ep_mod, "tier_feasibility_errors", lambda tier, env: None)

    ws = _task_ws(tmp_path, tier="a3_live")
    (ws / "wrapper.py").write_text(
        "def run(rank_inputs, rank, world_size, comm=None):\n"
        "    return {k: v for k, v in rank_inputs.items()}\n"
    )
    rep = p25m.provision_multirank_reference(workspace=ws, op="fused_demo")
    assert rep.verdict == "READY", rep.summary
    assert calls["wrapper"] == ws / "wrapper.py"


# --- verify: stored-ranks branch + tolerance ----------------------------------


def test_verify_build_cases_reads_stored_ranks(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).parent.parent / "reference_provider"))
    import multirank_verify as mv
    from types import SimpleNamespace

    x = torch.arange(8, dtype=torch.float32).view(4, 2)
    y = x * 1.5
    golden = {
        "op": "fused_demo",
        "idx": 1,
        "name": "base@ws2",
        "case": 0,
        "profile": "task",
        "world_size": 2,
        "ranks": {
            "0": {"inputs": {"x": x}, "outputs": {"out0": y}},
            "1": {"inputs": {"x": x + 1}, "outputs": {"out0": y + 1.5}},
        },
    }
    p = tmp_path / "golden_base.pt"
    torch.save(golden, p)
    args = SimpleNamespace(rank=1, world_size=2, filter_case=None)
    cases = getattr(mv, "_build_cases")(args, golden, p, None)
    assert len(cases) == 1
    share = cases[0]["ranks"]["1"]
    assert torch.allclose(share["inputs"]["x"], x + 1)
    assert torch.allclose(share["outputs"]["out0"], y + 1.5)


def test_classify_with_declared_tolerance():
    from plugins.multirank import multirank_precision_eval_two_tier as pe

    ref = torch.zeros(4)
    m = pe.classify_multirank_case(
        torch.full([4], 1.5), ref, tolerance={"atol": 2.0, "rtol": 0.02}
    )
    assert m["verdict"] == "PASS_T1" and m["tier1_pass"] is True
    m = pe.classify_multirank_case(
        torch.full([4], 3.0), ref, tolerance={"atol": 2.0, "rtol": 0.02}
    )
    assert m["verdict"] == "FAIL" and m["tier1_pass"] is False


# --- #8: a collector crash keeps the rank logs on disk ------------------------


def test_provision_task_form_keeps_rank_logs_on_failure(tmp_path, monkeypatch):
    """A collector crash must keep the scratch dir (full rank logs) on disk
    and the failure report must name its path — no more root causes
    swallowed by an 800-char tail (black-box finding #8).
    """
    from plugins.multirank import multirank_endpoint as ep_mod
    from plugins.multirank import multirank_phase_o25 as p25m

    def _boom(*_args, **_kwargs):
        raise RuntimeError("collector exploded")

    monkeypatch.setattr(ep_mod, "run_collector", _boom)

    def _load_env():
        from briefs._common import AscendCEnv, TargetConfig

        return AscendCEnv(
            target="a5", targets={"a5": TargetConfig(arch="a5", exec_mode="local")}
        )

    monkeypatch.setattr(ep_mod, "load_env_or_none", _load_env)

    ws = _task_ws(tmp_path)
    rep = p25m.provision_multirank_reference(workspace=ws, op="fused_demo")
    assert rep.verdict == "COMPUTE_FAILED"
    assert "full rank logs kept at" in rep.summary
    leftovers = sorted(ws.glob(".npu_bench_task.*"))
    assert leftovers, "failure must keep the scratch dir with rank logs"
