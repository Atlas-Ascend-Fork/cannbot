# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""ExecEndpoint resolution + truth-tier feasibility (fail-closed) tests.

Covers multirank_endpoint: candidate/source resolution from AscendCEnv
generation blocks, per-exec-mode config completeness, and the
tier x endpoint feasibility check that refuses a declared tier loudly
(endpoints missing or provider unwired) instead of silently degrading the
golden.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest  # noqa: F401

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))
from briefs._common import AscendCEnv, TargetConfig  # noqa: E402
from plugins.multirank import multirank_endpoint as ep  # noqa: E402


def _cfg(arch, **fields):
    return TargetConfig(arch=arch, **fields)


def _remote_candidate_env(monkeypatch) -> AscendCEnv:
    """A complete REMOTE a5 candidate endpoint (mount check mocked out)."""
    monkeypatch.setattr(ep, "verify_stage_mount", lambda e, cfg=None: [])
    return AscendCEnv(
        target="a5",
        targets={
            "a5": _cfg(
                "a5",
                host="a5m",
                container="cjm",
                stage_host_dir="/d",
                stage_container_dir="/cw",
            ),
        },
    )


# ---------------------------------------------------------------------------
# endpoint resolution
# ---------------------------------------------------------------------------
def test_resolve_candidate_and_source():
    env = AscendCEnv(
        target="a5",
        targets={
            "a5": _cfg("a5", host="a5m", container="cjm", exec_mode="remote-container"),
            "a3": _cfg("a3", host="a3m", container="npu", exec_mode="remote-container"),
        },
    )
    cand = ep.resolve_endpoint(env, "candidate")
    assert (cand.arch, cand.host, cand.container) == ("a5", "a5m", "cjm")
    assert cand.is_local is False and cand.block_present is True
    src = ep.resolve_endpoint(env, "source")
    assert (src.arch, src.host) == ("a3", "a3m")


def test_resolve_source_missing_block_is_empty_not_local():
    env = AscendCEnv(target="a5", targets={})  # no blocks at all
    src = ep.resolve_endpoint(env, "source")
    assert src.block_present is False
    # default exec mode is remote-container — an absent block is NOT local
    assert src.is_local is False


def test_resolve_invalid_role_rejected():
    env = AscendCEnv(target="a5")
    with pytest.raises(ValueError, match="candidate.*source"):
        ep.resolve_endpoint(env, "worker")


def test_local_exec_modes():
    for mode, local in (
        ("local", True),
        ("local-container", True),
        ("remote", False),
        ("remote-container", False),
    ):
        env = AscendCEnv(target="a5", targets={"a5": _cfg("a5", exec_mode=mode)})
        assert ep.resolve_endpoint(env, "candidate").is_local is local, mode


# ---------------------------------------------------------------------------
# per-mode config completeness
# ---------------------------------------------------------------------------
def test_config_errors_per_mode():
    # local: complete by definition
    e = ep.ExecEndpoint(
        role="candidate", arch="a5", exec_mode="local", block_present=True
    )
    assert e.config_errors() == []
    # local-container without a container name
    e = ep.ExecEndpoint(role="candidate", arch="a5", exec_mode="local-container")
    assert any("A5_CONTAINER" in x for x in e.config_errors())
    # remote without host
    e = ep.ExecEndpoint(role="candidate", arch="a5", exec_mode="remote")
    assert any("A5_HOST" in x for x in e.config_errors())
    # remote-container missing host / container / stage mapping
    e = ep.ExecEndpoint(role="candidate", arch="a5", exec_mode="remote-container")
    errs = e.config_errors()
    assert any("A5_HOST" in x for x in errs)
    assert any("A5_CONTAINER" in x for x in errs)
    assert any("staging mapping" in x for x in errs)
    # remote-container complete
    e = ep.ExecEndpoint(
        role="candidate",
        arch="a5",
        exec_mode="remote-container",
        host="h",
        container="c",
        stage_host_dir="/d",
        stage_container_dir="/c",
    )
    assert e.config_errors() == []


# ---------------------------------------------------------------------------
# tier x endpoint feasibility (fail-closed)
# ---------------------------------------------------------------------------
def test_unknown_tier_gets_no_endpoint_waiver():
    """A bogus truth tier is refused upstream (resolver); at the endpoint
    gate it gets NO waiver either — it reports as unwired.
    """
    assert ep.tier_feasibility_errors("bogus_tier", None) is not None
    env = AscendCEnv(
        target="a5", targets={"a5": TargetConfig(arch="a5", exec_mode="local")}
    )
    assert ep.check_truth_tier_feasible("bogus_tier", env) != []


def test_npu_bench_remote_candidate_now_feasible(monkeypatch):
    """Remote primitives are wired: a complete REMOTE candidate endpoint is

    feasible for npubench (staging + remote execution + md5-skipped sync).
    The live docker-inspect mount check is mocked here — its own tests
    cover it.
    """
    env = _remote_candidate_env(monkeypatch)
    assert ep.check_truth_tier_feasible("npubench", env) == []


def test_npu_bench_local_candidate_is_feasible():
    """Wired tier + complete bare-host local endpoint → no errors."""
    env = AscendCEnv(
        target="a5",
        targets={
            "a5": _cfg("a5", exec_mode="local"),
        },
    )
    assert ep.check_truth_tier_feasible("npubench", env) == []


def test_npu_bench_missing_endpoint_reports_config_errors():
    env = AscendCEnv(target="a5", targets={"a5": _cfg("a5")})  # no host
    errs = ep.check_truth_tier_feasible("npubench", env)
    assert any("A5_HOST" in x for x in errs)


def test_a3_live_reports_unwired_until_rewired(monkeypatch):
    """a3_live keeps its tier slot but its source-form provider is not
    wired: feasibility reports it as unwired (the resolver-level refusal
    carries the user-facing explanation).
    """
    env = _remote_candidate_env(monkeypatch)
    errs = ep.check_truth_tier_feasible("a3_live", env)
    assert any("not wired" in e for e in errs)


def test_missing_env_file_is_fail_closed_for_npu_tiers():
    errs = ep.tier_feasibility_errors("npubench", None)
    assert errs and "ascendc_env" in errs[0]


# ---------------------------------------------------------------------------
# staging area mapping (host dir <-> container dir)
# ---------------------------------------------------------------------------
def test_stage_map_explicit_pair_wins():
    cfg = TargetConfig(
        arch="a3",
        host_home="/home/legacy",
        stage_host_dir="/data/ssd/ws",
        stage_container_dir="/workspace",
    )
    assert ep.stage_map(cfg) == ("/data/ssd/ws", "/workspace")


def test_stage_map_falls_back_to_legacy_convention():
    cfg = TargetConfig(arch="a3", host_home="/home/npu_user_opus")
    assert ep.stage_map(cfg) == ("/home/npu_user_opus", "/home/npu_user")
    cfg2 = TargetConfig(arch="a3", host_home="/h", container_home="/cw")
    assert ep.stage_map(cfg2) == ("/h", "/cw")


def test_translate_to_container_prefix_replacement():
    cfg = TargetConfig(
        arch="a3", stage_host_dir="/data/ssd/ws", stage_container_dir="/workspace"
    )
    assert ep.translate_to_container(cfg, "/data/ssd/ws/op/in.pt") == Path(
        "/workspace/op/in.pt"
    )
    assert ep.translate_to_container(cfg, "/data/ssd/ws") == Path("/workspace")
    with pytest.raises(ValueError, match="not under the stage host dir"):
        ep.translate_to_container(cfg, "/elsewhere/x.pt")


def test_endpoint_stage_dir_remote_is_identity():
    end = ep.ExecEndpoint(role="candidate", arch="a5", exec_mode="remote", host="h")
    host, exec_side = ep.endpoint_stage_dir(end)
    assert host == exec_side == "/tmp/multirank_stage"


def test_endpoint_stage_dir_local_container_translates():
    """local-container stages through the local bind mount (same mapping as

    remote-container; only the transport differs — local copy vs scp).
    """
    end = ep.ExecEndpoint(
        role="source",
        arch="a3",
        exec_mode="local-container",
        container="c",
        stage_host_dir="/data/ws",
        stage_container_dir="/cw",
    )
    host, exec_side = ep.endpoint_stage_dir(end)
    assert host == "/data/ws/multirank_stage"
    assert exec_side == "/cw/multirank_stage"


def test_endpoint_stage_dir_bare_local_refuses():
    end = ep.ExecEndpoint(role="candidate", arch="a5", exec_mode="local")
    with pytest.raises(RuntimeError, match="no staging"):
        ep.endpoint_stage_dir(end)


# ---------------------------------------------------------------------------
# remote primitives: command assembly + md5-manifest skip (mocked transport)
# ---------------------------------------------------------------------------
def test_remote_exec_command_assembly(monkeypatch):
    calls = []

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    def _run(cmd, **kw):
        calls.append(cmd)
        return _R()

    import subprocess as _sp

    monkeypatch.setattr(_sp, "run", _run)
    end_r = ep.ExecEndpoint(
        role="source", arch="a3", exec_mode="remote", host="h", user="opus"
    )
    ep.remote_exec(end_r, ["python3", "x.py"])
    assert calls[-1][0] == "ssh" and calls[-1][-1] == "x.py"
    assert calls[-1][-2] == "python3"
    end_c = ep.ExecEndpoint(
        role="source",
        arch="a3",
        exec_mode="remote-container",
        host="h",
        user="opus",
        container="npu",
    )
    ep.remote_exec(end_c, ["python3", "x.py"])
    assert "docker" in calls[-1] and "npu" in calls[-1]
    end_l = ep.ExecEndpoint(role="candidate", arch="a5", exec_mode="local")
    with pytest.raises(RuntimeError, match="remote endpoints"):
        ep.remote_exec(end_l, ["x"])


def test_ssh_base_password_selects_sshpass():
    """A non-empty block password selects the sshpass prefix (the single-card

    A5 convention); empty keeps key auth.
    """
    end_pw = ep.ExecEndpoint(
        role="candidate",
        arch="a5",
        exec_mode="remote",
        host="h",
        user="u",
        password="secret",
    )
    base = getattr(ep, "_ssh_base")(end_pw)
    assert base[:3] == ["sshpass", "-p", "secret"]
    assert base[3] == "ssh"
    assert getattr(ep, "_scp_base")(end_pw)[0] == "sshpass"
    end_key = ep.ExecEndpoint(
        role="candidate", arch="a5", exec_mode="remote", host="h", user="u"
    )
    assert getattr(ep, "_ssh_base")(end_key)[0] == "ssh"
    assert getattr(ep, "_scp_base")(end_key)[0] == "scp"


def test_host_port_forms():
    """A<n>_HOST accepts bare host / host:port / [v6]:port."""
    bare = ep.ExecEndpoint(
        role="c", arch="a5", exec_mode="remote", host="10.1.1.5", user="u"
    )
    assert getattr(ep, "_host_port")(bare) == ("10.1.1.5", None)
    assert "-p" not in getattr(ep, "_ssh_base")(bare) and "-P" not in getattr(
        ep, "_scp_base"
    )(bare)
    ported = ep.ExecEndpoint(
        role="c", arch="a5", exec_mode="remote", host="10.1.1.5:2222", user="u"
    )
    assert getattr(ep, "_host_port")(ported) == ("10.1.1.5", "2222")
    ssh_args = getattr(ep, "_ssh_base")(ported)
    assert "-p" in ssh_args and ssh_args[ssh_args.index("-p") + 1] == "2222"
    assert ssh_args[-1] == "u@10.1.1.5"  # target is port-stripped
    scp_args = getattr(ep, "_scp_base")(ported)
    assert "-P" in scp_args and scp_args[scp_args.index("-P") + 1] == "2222"
    v6 = ep.ExecEndpoint(
        role="c", arch="a5", exec_mode="remote", host="[fe80::1]:2222", user="u"
    )
    assert getattr(ep, "_host_port")(v6) == ("[fe80::1]", "2222")
    v6bare = ep.ExecEndpoint(
        role="c", arch="a5", exec_mode="remote", host="fe80::1", user="u"
    )
    assert getattr(ep, "_host_port")(v6bare) == ("fe80::1", None)


def test_sync_up_md5_skip(monkeypatch, tmp_path):
    """Second sync with unchanged bytes transfers nothing (md5 manifest

    hit); changed content transfers again.
    """
    end = ep.ExecEndpoint(
        role="source",
        arch="a3",
        exec_mode="remote-container",
        host="h",
        user="u",
        container="c",
    )
    f1 = tmp_path / "a.pt"
    f1.write_bytes(b"hello")
    state = {"manifest": {}}

    class _Cat:
        returncode = 0

        def __init__(self, out):
            self.stdout = out
            self.stderr = ""

    import json as _json
    import subprocess as _sp

    pushed = []

    def _fake_run(cmd, **kw):
        s = " ".join(cmd)
        if " cat " in s and ".sync_manifest.json" in s:
            return _Cat(_json.dumps(state["manifest"]))
        if cmd[0] == "scp":
            pushed.append(s)
            # simulate the remote adopting the pushed manifest
            if ".sync_manifest.json" in s:
                pass
            return _Cat("")
        return _Cat("")

    monkeypatch.setattr(_sp, "run", _fake_run)
    # first sync: no manifest → transfer
    r1 = ep.sync_up(end, [(f1, "a.pt")], "/remote/stage")
    assert r1["transferred"] == ["a.pt"] and r1["skipped"] == []
    # record what the remote would now have (simulate manifest adoption)
    import hashlib

    state["manifest"]["a.pt"] = [hashlib.md5(b"hello").hexdigest(), "5"]
    r2 = ep.sync_up(end, [(f1, "a.pt")], "/remote/stage")
    assert r2["transferred"] == [] and r2["skipped"] == ["a.pt"]
    # content changed → transfers again
    f1.write_bytes(b"world!")
    r3 = ep.sync_up(end, [(f1, "a.pt")], "/remote/stage")
    assert r3["transferred"] == ["a.pt"]


def test_run_collector_remote_stages_executes_pulls(monkeypatch, tmp_path):
    """The remote collector path: mkdir → sync_up(spec+collector+input) →

    remote python3 collector → sync_down(output).
    """
    end = ep.ExecEndpoint(
        role="candidate",
        arch="a5",
        exec_mode="remote-container",
        host="h",
        user="u",
        container="c",
        stage_host_dir="/data/ws",
        stage_container_dir="/cw",
    )
    seq = []
    monkeypatch.setattr(
        ep,
        "remote_exec",
        lambda e, cmd, **kw: (
            seq.append(("exec", cmd))
            or type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        ),
    )
    monkeypatch.setattr(
        ep,
        "sync_up",
        lambda e, files, d: (
            seq.append(("up", tuple(n for _, n in files), d))
            or {"transferred": list, "skipped": []}
        ),
    )
    monkeypatch.setattr(
        ep,
        "sync_down",
        lambda e, d, names, local: (
            seq.append(("down", tuple(names), str(local)))
            or {"transferred": list(names), "skipped": []}
        ),
    )
    spec = tmp_path / "spec.py"
    spec.write_text("SPEC = {}\n")
    inp = tmp_path / "in_1.pt"
    inp.write_bytes(b"x")
    out = tmp_path / "out_1.pt"
    ep.run_collector(
        ep.CollectorLaunch(endpoint=end, spec_path=spec, in_file=inp, out_file=out)
    )
    kinds = [s[0] for s in seq]
    assert kinds == ["exec", "up", "exec", "down"]
    assert seq[0][1][0] == "mkdir"
    assert seq[2][1][0] == "python3"  # collector executes on the endpoint
    assert "/cw/multirank_stage/" in seq[2][1][2]  # container-side path
    assert seq[3][1] == ("out_1.pt",)


# ---------------------------------------------------------------------------
# stage-mount verification (docker inspect Binds coverage)
# ---------------------------------------------------------------------------
class _InspectResult:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def _mount_endpoint():
    return ep.ExecEndpoint(
        role="candidate",
        arch="a5",
        exec_mode="remote-container",
        host="h:2222",
        user="u",
        password="pw",
        container="cont",
        stage_host_dir="/hs/agent-dir",
        stage_container_dir="/cs/agent-dir",
    )


def test_stage_mount_exact_bind(monkeypatch):
    e = _mount_endpoint()
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: _InspectResult(stdout='["/hs/agent-dir:/cs/agent-dir"]'),
    )
    assert ep.verify_stage_mount(e) == []


def test_stage_mount_ancestor_bind_covers(monkeypatch):
    """A stage dir under an ancestor bind is covered: files copied to

    /hs/agent-dir appear at /cs/agent-dir via bind /hs:/cs (docker Binds
    report ancestor mounts, not per-subdir).
    """
    e = _mount_endpoint()
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: _InspectResult(
            stdout='["/usr/local/dcmi:/usr/local/dcmi", "/hs:/hs"]'
        ),
    )
    assert ep.verify_stage_mount(e) != []  # /hs:/hs maps to /hs/agent-dir, not /cs
    e2 = ep.ExecEndpoint(
        role="candidate",
        arch="a5",
        exec_mode="remote-container",
        host="h:2222",
        user="u",
        password="pw",
        container="cont",
        stage_host_dir="/hs/agent-dir",
        stage_container_dir="/hs/agent-dir",
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: _InspectResult(
            stdout='["/usr/local/dcmi:/usr/local/dcmi", "/hs:/hs"]'
        ),
    )
    assert ep.verify_stage_mount(e2) == []


def test_stage_mount_ancestor_bind_wrong_container_side(monkeypatch):
    e = _mount_endpoint()
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: _InspectResult(stdout='["/hs:/other"]')
    )
    errs = ep.verify_stage_mount(e)
    assert errs and "stage mount mismatch" in errs[0]


def test_stage_mount_unrelated_binds(monkeypatch):
    e = _mount_endpoint()
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: _InspectResult(stdout='["/usr/local/dcmi:/usr/local/dcmi"]'),
    )
    errs = ep.verify_stage_mount(e)
    assert errs and "actual Binds" in errs[0]


def test_sync_down_remote_creates_local_parent_dirs(monkeypatch, tmp_path):
    """Remote-form pull must create the local parent dirs before scp.

    Rank artifacts land under .run/<slug>/ — a subpath the caller does not
    pre-create; a missing parent makes scp itself fail with "No such file
    or directory" while the remote copy is intact.
    """
    end = ep.ExecEndpoint(
        role="candidate", arch="a5", exec_mode="remote", host="h", user="root"
    )

    def _run(cmd, **kw):
        if cmd and cmd[0] == "scp":
            dst = Path(cmd[-1])
            assert dst.parent.is_dir(), f"scp target parent missing: {dst.parent}"
            dst.write_text("rank log\n")
            return _InspectResult(returncode=0)
        # md5sum probe (via ssh): empty stdout → no skip candidates
        return _InspectResult(returncode=0)

    monkeypatch.setattr("subprocess.run", _run)
    local_dir = tmp_path / "ws"
    res = ep.sync_down(
        end,
        "/remote/stage/ws",
        [".run/slug/rank_0.log", ".run/slug/rank_0.rc"],
        local_dir,
    )
    assert res["transferred"] == [".run/slug/rank_0.log", ".run/slug/rank_0.rc"]
    assert (local_dir / ".run/slug/rank_0.log").read_text() == "rank log\n"
