# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Back-ported black-box e2e runtime fixes (HARNESS_FINDINGS #2/#4/#6/#10/#13).

Each test pins one defect the black-box campaign hit on the A5 endpoint:
  #2  collector main() lost its --wrapper CLI parsing (wrapper_arg NameError,
      100% npubench collection failure) — pinned by driving main() end-to-end
      with a fake torch and asserting the wrapper reaches the payload.
  #4  per-rank single-card masks break CANN's renumber-from-0 semantics —
      _resolve_lanes pins the shared lane-group resolution contract.
  #6  msopgen >= 26 ships no cmake/ tree (config.cmake guard) and staged
      multirank copies may miss their own py_ext assets (fallback lookup).
  #13 npu_op_package pins INSTALL_PATH to ${CMAKE_BINARY_DIR} so .install/
      is never generated — the scaffold patch re-points it at
      ${CMAKE_INSTALL_PREFIX}; find_kernel_binary gains the msopgen-26
      ascendc_kernels layout as a second candidate.
  #10 NEEDS_EP_COMM references defer the in-orchestrator CPU probe instead
      of crashing it (publish_mode_reference deferred receipt).
  verify — the _LaunchWatchdog class definition itself: 3cc9973 orphaned the
      kernel-launch use site (verify.py:565) when the class was dropped, so
      every real launch hit a NameError; the black-box worker self-repaired
      the frozen copy mid-run — back-ported here with disarm/timeout pins.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# shared fakes
# ---------------------------------------------------------------------------
def _fake_torch_module() -> types.ModuleType:
    """Minimal torch stand-in: load() returns the payload object it was handed
    at save() time (recorded calls let tests assert on them). The dtype
    constants keep unrelated modules on the import chain (e.g. case_gen's
    module-level `dtype: torch.dtype = torch.float32`) working under the
    patch."""
    mod = types.ModuleType("torch")
    mod.__version__ = "fake-torch"
    mod.dtype = str  # annotation stand-in

    def _device(spec):
        return ("torch-device", spec)

    mod.device = _device  # stand-in
    mod.Tensor = object  # isinstance/annotation stand-in
    mod.float32 = "float32"
    mod.float16 = "float16"
    mod.bfloat16 = "bfloat16"
    mod.float64 = "float64"
    mod.int8 = "int8"
    mod.int16 = "int16"
    mod.int32 = "int32"
    mod.int64 = "int64"
    mod.uint8 = "uint8"
    mod.uint16 = "uint16"
    mod.uint32 = "uint32"
    mod.uint64 = "uint64"
    mod.bool = "bool"
    store: dict[str, object] = {}
    setattr(mod, "_store", store)

    def _save(obj, path, **_kwargs):
        store[str(path)] = obj
        Path(path).write_bytes(b"fake-pt")

    def _load(path, **_kwargs):
        return store.get(str(path))

    mod.save = _save
    mod.load = _load
    return mod


def _fake_torch_npu_module() -> types.ModuleType:
    mod = types.ModuleType("torch_npu")
    mod.__version__ = "fake-torch_npu"
    return mod


# ---------------------------------------------------------------------------
# #2 — collector main(): --wrapper parsing + payload pass-through
# ---------------------------------------------------------------------------
_MINIMAL_TASK_SPEC = """
SPEC = {
    "input_mode": "task_generated",
    "inputs": [],
    "kernel_input_order": [],
}


class Model:
    def __call__(self, *args, **kwargs):
        return 1


def get_init_inputs(rank=0, world_size=1):
    return ()


def get_input_groups(rank=0, world_size=1):
    return ()
"""


def test_collector_main_parses_wrapper_and_reaches_payload(
    tmp_path, monkeypatch
) -> None:
    """The exact black-box failure: endpoint calls the collector with
    --wrapper; main() must parse it (past versions referenced an undefined
    wrapper_arg — NameError on EVERY npubench collection) and inject it into
    the payload for the multiproc forwarder.
    """
    from plugins.multirank import multirank_npu_bench_collect as collector

    spec = tmp_path / "spec.py"
    spec.write_text(_MINIMAL_TASK_SPEC, encoding="utf-8")
    in_pt = tmp_path / "in.pt"
    out_pt = tmp_path / "out.pt"
    fake = _fake_torch_module()
    payload = {"idx": 1, "name": "case1@ws1", "world_size": 1, "mode": "task"}
    getattr(fake, "_store")[str(in_pt)] = payload

    monkeypatch.setitem(sys.modules, "torch", fake)
    monkeypatch.setitem(sys.modules, "torch_npu", _fake_torch_npu_module())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "multirank_npu_bench_collect.py",
            str(spec),
            str(in_pt),
            str(out_pt),
            "--wrapper",
            str(tmp_path / "wrapper.py"),
        ],
    )

    rc = collector.main()

    assert rc == 0
    assert payload.get("wrapper_path") == str(tmp_path / "wrapper.py")
    assert str(out_pt) in getattr(fake, "_store")  # sequential mode saved the output


def test_collector_main_usage_lists_wrapper(monkeypatch) -> None:
    from plugins.multirank import multirank_npu_bench_collect as collector

    monkeypatch.setattr(sys, "argv", ["x", "a", "b"])
    rc = collector.main()
    assert rc == 2  # usage error BEFORE any torch import — no NameError path


# ---------------------------------------------------------------------------
# #4 — shared lane resolution
# ---------------------------------------------------------------------------
def test_resolve_lanes_env_override_wins(monkeypatch) -> None:
    from plugins.multirank import multirank_npu_bench_collect as collector

    monkeypatch.setenv("MULTIRANK_LANES", "1,2")
    lanes, err = getattr(collector, "_resolve_lanes")(2)
    assert (lanes, err) == ([1, 2], None)


def test_resolve_lanes_env_too_short_is_error(monkeypatch) -> None:
    from plugins.multirank import multirank_npu_bench_collect as collector

    monkeypatch.setenv("MULTIRANK_LANES", "5")
    lanes, err = getattr(collector, "_resolve_lanes")(2)
    assert lanes is None and "needs 2" in err


def test_resolve_lanes_env_malformed_is_error(monkeypatch) -> None:
    from plugins.multirank import multirank_npu_bench_collect as collector

    monkeypatch.setenv("MULTIRANK_LANES", "a,b")
    lanes, err = getattr(collector, "_resolve_lanes")(2)
    assert lanes is None and "not an int list" in err


def test_resolve_lanes_probe_failure_propagates(monkeypatch) -> None:
    """No env override → npu_probe.pick_idle is consulted; its failure
    string must surface so the caller can warn + fall back.
    """
    from plugins.multirank import multirank_npu_bench_collect as collector
    import npu_probe

    monkeypatch.delenv("MULTIRANK_LANES", raising=False)
    monkeypatch.setattr(npu_probe, "pick_idle", lambda env, n: (None, "probe failed"))
    lanes, err = getattr(collector, "_resolve_lanes")(2)
    assert lanes is None and err == "probe failed"


def test_resolve_lanes_probe_success_used(monkeypatch) -> None:
    from plugins.multirank import multirank_npu_bench_collect as collector
    import npu_probe

    monkeypatch.delenv("MULTIRANK_LANES", raising=False)
    monkeypatch.setattr(npu_probe, "pick_idle", lambda env, n: ([1, 2], None))
    lanes, err = getattr(collector, "_resolve_lanes")(2)
    assert (lanes, err) == ([1, 2], None)


# ---------------------------------------------------------------------------
# #4 — endpoint lanes injection (run_collector)
# ---------------------------------------------------------------------------
class _LocalEndpoint:
    exec_mode = "local"


def test_run_collector_local_injects_multirank_lanes(monkeypatch) -> None:
    """The parent (which CAN reach the endpoint probe) injects the resolved
    lanes via MULTIRANK_LANES; local mode forwards them in the subprocess
    env (remote subprocesses cannot import npu_probe).
    """
    from plugins.multirank import multirank_endpoint as ep

    observed = {}

    class _FakeRun:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, capture_output, text, timeout, env):
        observed["cmd"] = cmd
        observed["env"] = env
        return _FakeRun()

    monkeypatch.setattr("subprocess.run", fake_run)
    ep.run_collector(
        ep.CollectorLaunch(
            endpoint=_LocalEndpoint(),
            spec_path=Path("s.py"),
            in_file=Path("i.pt"),
            out_file=Path("o.pt"),
            lanes=[1, 2],
        )
    )
    assert observed["env"]["MULTIRANK_LANES"] == "1,2"
    assert "--wrapper" not in observed["cmd"]  # no wrapper → no flag


def test_run_collector_local_without_lanes_leaves_env(monkeypatch) -> None:
    from plugins.multirank import multirank_endpoint as ep

    observed = {}

    class _FakeRun:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, capture_output, text, timeout, env):
        observed["env"] = env
        return _FakeRun()

    monkeypatch.setattr("subprocess.run", fake_run)
    ep.run_collector(
        ep.CollectorLaunch(
            endpoint=_LocalEndpoint(),
            spec_path=Path("s.py"),
            in_file=Path("i.pt"),
            out_file=Path("o.pt"),
        )
    )
    assert "MULTIRANK_LANES" not in observed["env"]


# ---------------------------------------------------------------------------
# #13 — root CMakeLists INSTALL_PATH patch (msopgen-26 macro style)
# ---------------------------------------------------------------------------
_MSOPGEN26_ROOT_CMAKELISTS = """cmake_minimum_required(VERSION 3.16.0)
project(opp)
find_package(ASC REQUIRED)
set(package_name ${vendor_name})

npu_op_package(${package_name}
    TYPE RUN
    CONFIG
        INSTALL_PATH ${CMAKE_BINARY_DIR}/
)

if(EXISTS ${CMAKE_CURRENT_SOURCE_DIR}/op_host)
    add_subdirectory(op_host)
endif()
"""


def test_install_path_patch_repoints_to_prefix(tmp_path) -> None:
    from plugins.multirank.op_template_gen import multirank_msopgen_scaffold as scaffold

    cm = tmp_path / "CMakeLists.txt"
    cm.write_text(_MSOPGEN26_ROOT_CMAKELISTS, encoding="utf-8")
    getattr(scaffold, "_patch_root_cmakelists_install_path")(tmp_path)
    t = cm.read_text(encoding="utf-8")
    assert "INSTALL_PATH ${CMAKE_INSTALL_PREFIX}/" in t
    assert "INSTALL_PATH ${CMAKE_BINARY_DIR}/" not in t
    assert "npu_op_package(${package_name}" in t  # structure untouched


def test_install_path_patch_legacy_skipped(tmp_path) -> None:
    from plugins.multirank.op_template_gen import multirank_msopgen_scaffold as scaffold

    legacy = "opbuild(...)\nadd_subdirectory(op_host)\n"
    cm = tmp_path / "CMakeLists.txt"
    cm.write_text(legacy, encoding="utf-8")
    getattr(scaffold, "_patch_root_cmakelists_install_path")(tmp_path)
    assert cm.read_text(encoding="utf-8") == legacy  # byte-identical skip


def test_install_path_patch_anchor_drift_raises(tmp_path) -> None:
    from plugins.multirank.op_template_gen import multirank_msopgen_scaffold as scaffold

    drifted = (
        "npu_op_package(${package_name}\n    TYPE RUN\n"
        "    CONFIG\n        INSTALL_PATH somewhere_else\n)\n"
    )
    (tmp_path / "CMakeLists.txt").write_text(drifted, encoding="utf-8")
    with pytest.raises(RuntimeError, match="has drifted"):
        getattr(scaffold, "_patch_root_cmakelists_install_path")(tmp_path)


# ---------------------------------------------------------------------------
# #6 — config.cmake absent guard (msopgen >= 26 has no cmake/ tree)
# ---------------------------------------------------------------------------
def test_config_cmake_missing_is_noop(tmp_path) -> None:
    from plugins.multirank.op_template_gen import multirank_msopgen_scaffold as scaffold

    # no cmake/ tree at all — must not raise (used to FileNotFoundError)
    getattr(scaffold, "_patch_config_cmake")(tmp_path)
    getattr(scaffold, "_patch_cmake_presets")(tmp_path)
    getattr(scaffold, "_patch_func_cmake")(tmp_path)
    getattr(scaffold, "_patch_intf_cmake")(tmp_path)


# ---------------------------------------------------------------------------
# #6 — py_ext assets fallback (staged copy without the multirank subtree)
# ---------------------------------------------------------------------------
def test_py_ext_assets_dir_falls_back_to_single_card_tree() -> None:
    """This repo ships the multirank tree WITHOUT its own py_ext_assets (the
    single-card engine tree holds them) — the fallback must resolve there.
    """
    from plugins.multirank.op_template_gen import multirank_msopgen_scaffold as scaffold

    assets = getattr(scaffold, "_py_ext_assets_dir")()
    assert (assets / "setup.py").is_file()
    assert (assets / "pytorch_npu_helper.hpp").is_file()


def test_py_ext_assets_dir_missing_everywhere_raises(monkeypatch, tmp_path) -> None:
    from plugins.multirank.op_template_gen import multirank_msopgen_scaffold as scaffold

    fake_scaffold = tmp_path / "deep" / "staged" / "scaffold.py"
    fake_scaffold.parent.mkdir(parents=True)
    fake_scaffold.write_text("", encoding="utf-8")
    monkeypatch.setattr(scaffold, "__file__", str(fake_scaffold))
    # parents[3] of the fake path has no op_template_gen/py_ext_assets either
    with pytest.raises(RuntimeError, match="py_ext assets not found"):
        getattr(scaffold, "_py_ext_assets_dir")()


# ---------------------------------------------------------------------------
# #13 — find_kernel_binary layout candidates
# ---------------------------------------------------------------------------
def _write_kernel_tree(root: Path, sub: str) -> None:
    op_dir = root / "op_kernel" / sub / "ascend950" / "foo_bar"
    op_dir.mkdir(parents=True)
    (op_dir / "FooBar_abc123.o").write_bytes(b"o")
    (op_dir / "FooBar_abc123.json").write_text("{}", encoding="utf-8")


def test_find_kernel_binary_legacy_layout(tmp_path) -> None:
    from plugins.multirank.patches import multirank_build as mb

    _write_kernel_tree(tmp_path, "binary")
    result = mb.find_kernel_binary(tmp_path, "foo_bar", "ascend950")
    assert result["obj"] == (
        tmp_path / "op_kernel" / "binary" / "ascend950" / "foo_bar" / "FooBar_abc123.o"
    )
    assert result["npu_supported_ops"] == (
        tmp_path
        / "op_kernel"
        / "tbe"
        / "op_info_cfg"
        / "ai_core"
        / "npu_supported_ops.json"
    )


def test_find_kernel_binary_msopgen26_layout(tmp_path) -> None:
    from plugins.multirank.patches import multirank_build as mb

    _write_kernel_tree(tmp_path, "ascendc_kernels/binary")
    result = mb.find_kernel_binary(tmp_path, "foo_bar", "ascend950")
    assert result["obj"] == (
        tmp_path
        / "op_kernel"
        / "ascendc_kernels"
        / "binary"
        / "ascend950"
        / "foo_bar"
        / "FooBar_abc123.o"
    )
    # companions anchor to the SAME kernel tree root (ascendc_kernels/)
    assert result["npu_supported_ops"] == (
        tmp_path
        / "op_kernel"
        / "ascendc_kernels"
        / "tbe"
        / "op_info_cfg"
        / "ai_core"
        / "npu_supported_ops.json"
    )


def test_find_kernel_binary_legacy_candidate_wins(tmp_path) -> None:
    from plugins.multirank.patches import multirank_build as mb

    _write_kernel_tree(tmp_path, "binary")
    _write_kernel_tree(tmp_path, "ascendc_kernels/binary")
    result = mb.find_kernel_binary(tmp_path, "foo_bar", "ascend950")
    assert result["obj"].parent == (
        tmp_path / "op_kernel" / "binary" / "ascend950" / "foo_bar"
    )


def test_find_kernel_binary_missing_lists_both_candidates(tmp_path) -> None:
    from plugins.multirank.patches import multirank_build as mb

    with pytest.raises(FileNotFoundError) as excinfo:
        mb.find_kernel_binary(tmp_path, "foo_bar", "ascend950")
    msg = str(excinfo.value)
    assert "op_kernel/binary/ascend950/foo_bar" in msg
    assert "op_kernel/ascendc_kernels/binary/ascend950/foo_bar" in msg


# ---------------------------------------------------------------------------
# #10 — publish_mode_reference deferred probe receipt
# ---------------------------------------------------------------------------
def _publish_ref_with_fake_torch(workspace: Path, candidate: Path, **overrides) -> None:
    """Run publish_mode_reference under a fake torch with the shared fixed args
    (overrides replace or add kwargs)."""
    import o25_mode_reference

    kwargs = dict(
        op="foo_bar",
        mode="mc2",
        input_cases=[{"idx": 1, "name": "case1", "inputs": {}}],
        dataset_cases=[{"idx": 1, "name": "case1", "inputs": {}, "outputs": {}}],
        source_filename="model.py",
        probe_args=[],
        private_filenames=(),
    )
    kwargs.update(overrides)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setitem(sys.modules, "torch", _fake_torch_module())
    try:
        o25_mode_reference.publish_mode_reference(
            workspace=workspace, candidate_dir=candidate, **kwargs
        )
    finally:
        monkeypatch.undo()


def test_publish_mode_reference_deferred_probe(tmp_path) -> None:
    """NEEDS_EP_COMM references defer the in-orchestrator CPU probe: the
    receipt keeps verdict=RUNNABLE, records the reason, and still binds the
    published source bytes via sha256.
    """
    import hashlib

    workspace = tmp_path / "ws"
    candidate = tmp_path / "cand"
    candidate.mkdir()
    model_src = "class Model:\n    def forward(self):\n        return 1\n"
    (candidate / "model.py").write_text(model_src, encoding="utf-8")

    _publish_ref_with_fake_torch(
        workspace, candidate, deferred_probe="NEEDS_EP_COMM: live HCCL rank groups"
    )

    import json

    receipt = json.loads((workspace / "ref_runnable.json").read_text())
    assert receipt["verdict"] == "RUNNABLE"
    assert receipt["probe_deferred_reason"] == ("NEEDS_EP_COMM: live HCCL rank groups")
    assert receipt["probe_result"] is None
    assert receipt["source_sha256"] == hashlib.sha256(model_src.encode()).hexdigest()


def test_publish_mode_reference_probe_still_default(tmp_path) -> None:
    """deferred_probe=None keeps the in-process active preflight (the CPU
    probe path for non-EP references) — the fake Model must actually run.
    """
    workspace = tmp_path / "ws"
    candidate = tmp_path / "cand"
    candidate.mkdir()
    (candidate / "model.py").write_text(
        "class Model:\n    def forward(self):\n        return 1\n", encoding="utf-8"
    )

    _publish_ref_with_fake_torch(workspace, candidate)

    import json

    receipt = json.loads((workspace / "ref_runnable.json").read_text())
    assert receipt["verdict"] == "RUNNABLE"
    assert "probe_deferred_reason" not in receipt
    assert receipt["probe_result"]["ok"] is True


# ---------------------------------------------------------------------------
# verify — _LaunchWatchdog (kernel-launch hang watchdog, orphaned use site)
# ---------------------------------------------------------------------------
_REF_PROVIDER_DIR = str(
    Path(__file__).resolve().parent.parent.parent
    / "plugins"
    / "multirank"
    / "reference_provider"
)


def _load_verify_module(monkeypatch):
    """Import multirank_verify against a fake torch: the module only binds
    the name at import time and the watchdog under test is pure
    threading/os — importing real torch inside the pytest process is
    avoided (its C-layer re-init under the runner is environment-sensitive)."""
    if _REF_PROVIDER_DIR not in sys.path:
        sys.path.insert(0, _REF_PROVIDER_DIR)
    monkeypatch.setitem(sys.modules, "torch", _fake_torch_module())
    monkeypatch.setitem(sys.modules, "torch_npu", _fake_torch_npu_module())
    import multirank_verify

    return multirank_verify


def test_launch_watchdog_silent_when_disarmed(monkeypatch) -> None:
    """done.set() inside the launch window disarms the watchdog: the rank
    subprocess survives and no rc=2 exit is taken.
    """
    mv = _load_verify_module(monkeypatch)
    exits: list[int] = []
    monkeypatch.setattr(mv.os, "_exit", lambda code: exits.append(code))
    wd = getattr(mv, "_LaunchWatchdog")(timeout_s=30, label="ut-disarm")
    wd.start()
    wd.done.set()
    wd.join(timeout=5)
    assert not wd.is_alive()
    assert exits == []


def test_launch_watchdog_fires_os_exit_2_on_timeout(monkeypatch) -> None:
    """A launch window outliving timeout_s takes the runner's device-hang
    exit (os._exit(2) -> rc=2) instead of parking the rank forever.
    """
    mv = _load_verify_module(monkeypatch)
    exits: list[int] = []

    def _fake_exit(code):
        exits.append(code)
        wd.done.set()  # end the wait loop like the real _exit ends the process

    monkeypatch.setattr(mv.os, "_exit", _fake_exit)
    wd = getattr(mv, "_LaunchWatchdog")(timeout_s=0.05, label="ut-timeout")
    wd.start()
    wd.join(timeout=5)
    assert not wd.is_alive()
    assert exits == [2]


# ---------------------------------------------------------------------------
# #5 — remote idle probing shares npu_probe's criteria (no local re-derivation)
# ---------------------------------------------------------------------------
def test_pick_idle_npu_remote_shares_npu_probe_criteria(monkeypatch) -> None:
    """The remote branch delegates parse + idle filtering to npu_probe —
    the old copy re-derived `util<=5` inline and would silently drift from
    _IDLE_UTIL_THRESHOLD.
    """
    from types import SimpleNamespace

    from plugins.multirank import multirank_endpoint as ep
    import npu_probe

    probe = npu_probe.ProbeResult(
        devices={
            0: npu_probe.NpuDevice(id=0, util_pct=0, processes=0),
            1: npu_probe.NpuDevice(id=1, util_pct=7, processes=0),
        },
        source="npu-smi(endpoint)",
    )
    monkeypatch.setattr(
        ep,
        "remote_exec",
        lambda endpoint, cmd, timeout=90: SimpleNamespace(
            returncode=0, stdout="smi-text", stderr=""
        ),
    )
    monkeypatch.setattr(
        npu_probe, "probe_result_from_smi_text", lambda text, source: probe
    )

    ids, err = ep.pick_idle_npu(SimpleNamespace(exec_mode="ssh"), 1)
    assert (ids, err) == ([0], None)  # util 7 > threshold 5 → only card 0


# ---------------------------------------------------------------------------
# verify — npubench reference perf baseline (the task Model IS the baseline)
# ---------------------------------------------------------------------------
def test_build_reference_baseline_mirrors_collector_convention(monkeypatch) -> None:
    """The npubench fallback baseline builds the task Model via its init
    inputs (npu() when available) and a comm namespace whose fields match
    the collector's _run_rank_task invocation exactly.
    """
    mv = _load_verify_module(monkeypatch)
    built = {}

    class _Ref:
        def __init__(self, *init):
            built["init"] = init

        def npu(self):
            built["npu"] = True
            return self

    spec_mod = types.SimpleNamespace(
        Model=_Ref,
        get_init_inputs=lambda rank, world_size: (rank, world_size),
        get_input_groups=lambda rank, world_size: ["g"],
    )

    class _BG:
        @staticmethod
        def _get_backend(dev):
            built["dev"] = dev
            return types.SimpleNamespace(get_hccl_comm_name=lambda r: f"hcomm{r}")

    model, comm = getattr(mv, "_build_reference_baseline")(spec_mod, 3, 8, _BG())
    assert built["init"] == (3, 8)
    assert built["npu"] is True
    assert built["dev"] == mv.torch.device("npu")
    assert comm.hcomm_info == "hcomm3"
    assert comm.rank == 3 and comm.world_size == 8 and comm.device == 3
    assert isinstance(model, _Ref)


def test_build_reference_baseline_none_without_task_impl(monkeypatch) -> None:
    """A spec without the task reference trio (Model/init/groups) gets no
    fallback baseline — honest N/A, never a crash or a silent substitute.
    """
    mv = _load_verify_module(monkeypatch)
    assert (
        getattr(mv, "_build_reference_baseline")(
            types.SimpleNamespace(Model=lambda *a: None), 0, 1, object()
        )
        is None
    )
    assert (
        getattr(mv, "_build_reference_baseline")(
            types.SimpleNamespace(), 0, 1, object()
        )
        is None
    )
    # a Model without .npu() is still usable (placement is the task's own)

    class _BG:
        @staticmethod
        def _get_backend(dev):
            return types.SimpleNamespace(get_hccl_comm_name=lambda r: "h")

    spec_mod = types.SimpleNamespace(
        Model=lambda *a: object(),
        get_init_inputs=lambda rank, world_size: (),
        get_input_groups=lambda rank, world_size: (),
    )
    pair = getattr(mv, "_build_reference_baseline")(spec_mod, 0, 2, _BG())
    assert pair is not None and pair[1].hcomm_info == "h"
