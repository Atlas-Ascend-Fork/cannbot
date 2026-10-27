# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Execution-endpoint resolution for the multirank extension.

An endpoint is WHERE + HOW the harness runs NPU work:

- role ``candidate`` — the generation the op is built/verified for (the
  TARGET block, normally A5). The candidate kernel AND the npubench
  reference both execute here, which is what makes their precision/perf
  A/B methodologically symmetric.
- role ``source`` — the reference generation for the a3_live tier (the
  SOURCE block; a live old-generation machine). Currently only consumed by
  the a3_live provider wiring.

Endpoints resolve against .ascendc_env generation blocks
(``briefs._common.TargetConfig``): the ``<PREFIX>_EXEC`` mode is the
authoritative declaration and already folds into the normalized
``(host, container)`` transport view every legacy consumer reads — this
module is the typed view new multirank code consumes (flow layers stay
endpoint-agnostic).

Local execution has NO separate transport today: the local candidate
endpoint's run primitive IS multirank_runner's existing Popen launch, and
sync primitives are no-ops because the engine shares the filesystem. Remote
run/sync primitives serve the a3_live provider (the only flow that must
leave the machine); the truth-tier feasibility check below refuses a
declared tier whose provider is unwired LOUDLY instead of silently
degrading the golden.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Truth tiers whose reference providers are actually wired. A declared tier
# outside this set fails the feasibility check — never a silent downgrade.
WIRED_TIERS = ("npubench",)

# The remote/container launch primitives (remote_exec + sync_up/sync_down)
# exist. Verified against mocks locally; first live ssh exercise happens on
# the real environment.
REMOTE_LAUNCH_WIRED = True

_LOCAL_EXEC_MODES = ("local", "local-container")

# Subprocess timeout for one collector run (all cases of one launch batch).
# NPU init + execution is slow; a hung launch must not wedge provision.
_COLLECT_TIMEOUT_SEC = 3600


@dataclass(frozen=True)
class ExecEndpoint:
    """One resolved execution endpoint (role x generation block)."""

    role: str  # "candidate" | "source"
    arch: str  # "a5" / "a3" / "a2" / ...
    exec_mode: str  # local / local-container / remote / remote-container
    host: str = ""
    user: str = "root"
    password: str = ""  # non-empty → sshpass auth; empty → SSH key auth
    container: str = ""
    cann_path: str = ""
    block_present: bool = False  # an A<n>_* block was actually written
    # Stage mapping (host dir <-> container dir) resolved from the block —
    # the sync/launch primitives use it to place files where the container
    # sees them (empty for bare-local, which needs no staging).
    stage_host_dir: str = ""
    stage_container_dir: str = ""

    @property
    def is_local(self) -> bool:
        """True when the engine executes on the same machine as the NPU

        (local bare host or a local container) — no ssh transport, and the
        filesystem is shared (sync primitives are no-ops).
        """
        return self.exec_mode in _LOCAL_EXEC_MODES

    def config_errors(self) -> list[str]:
        """Fail-closed completeness check for this endpoint's exec mode.

        An empty list means the block is complete enough to launch against.
        """
        prefix = self.arch.upper()
        errors: list[str] = []
        if self.exec_mode == "local":
            return errors  # bare-host local: nothing else required
        if self.exec_mode == "local-container" and not self.container:
            errors.append(
                f"{prefix}_EXEC=local-container requires {prefix}_CONTAINER "
                f"(the local NPU container name)"
            )
        if self.exec_mode.startswith("remote") and not self.host:
            errors.append(
                f"{prefix}_EXEC={self.exec_mode} requires {prefix}_HOST in .ascendc_env"
            )
        if self.exec_mode == "remote-container" and not self.container:
            errors.append(
                f"{prefix}_EXEC=remote-container requires {prefix}_CONTAINER "
                f"in .ascendc_env"
            )
        if self.exec_mode == "remote-container" and not self.stage_host_dir:
            errors.append(
                f"{prefix}_EXEC=remote-container requires a staging mapping "
                f"({prefix}_STAGE_HOST_DIR + {prefix}_STAGE_CONTAINER_DIR, "
                f"or the legacy {prefix}_HOST_HOME) — scp lands on the host "
                f"side, execution sees the container side"
            )
        return errors


def resolve_endpoint(env, role: str) -> ExecEndpoint:
    """Resolve one endpoint from a loaded AscendCEnv.

    ``env`` is a briefs._common.AscendCEnv (duck-typed: needs
    ``_target_base``/``source_arch`` and ``target_config``). ``role`` is
    "candidate" (TARGET block) or "source" (SOURCE block).
    """
    if role == "candidate":
        arch = getattr(env, "_target_base", None) or env.target
    elif role == "source":
        arch = env.source_arch
    else:
        raise ValueError(f"role must be 'candidate' or 'source'; got {role!r}")
    cfg = env.target_config(arch)
    host_dir, container_dir = stage_map(cfg)
    return ExecEndpoint(
        role=role,
        arch=cfg.arch,
        exec_mode=cfg.exec_mode,
        host=cfg.host,
        user=cfg.user,
        password=cfg.password,
        container=cfg.container,
        cann_path=cfg.cann_path,
        block_present=arch in getattr(env, "targets", {}),
        stage_host_dir=host_dir,
        stage_container_dir=container_dir,
    )


def check_truth_tier_feasible(tier: str, env) -> list[str]:
    """Fail-closed feasibility check binding a declared truth tier to its
    endpoints. Returns a list of user-facing errors (empty = feasible).

    - npubench: the candidate endpoint must resolve complete (the reference
      runs on the same endpoint as the candidate).
    - a3_live: the SOURCE generation block must additionally resolve
      complete (the source-side campaign executes the staged source
      operator there).
    A declared tier whose provider is not wired yet
    fails LOUD — the golden is never silently degraded.
    """
    errors: list[str] = []

    candidate = resolve_endpoint(env, "candidate")
    errors.extend(candidate.config_errors())
    # P129 generalized: a remote-container candidate must really bind the
    # configured stage mapping — checked at feasibility time, before any
    # scp lands on a host path the container cannot see.
    errors.extend(verify_stage_mount(candidate))

    if tier == "a3_live":
        source = resolve_endpoint(env, "source")
        if not source.block_present:
            errors.append(
                "a3_live requires the SOURCE generation block "
                "(e.g. A2_* keys with SOURCE=<arch>) in .ascendc_env"
            )
        else:
            errors.extend(source.config_errors())
            errors.extend(verify_stage_mount(source))
    if tier not in WIRED_TIERS:
        errors.append(
            f"truth tier {tier!r} is declared but its reference provider is "
            f"not wired yet — wired tiers: {'/'.join(WIRED_TIERS)}"
        )
    return errors


def endpoint_stage_dir(endpoint, base: str = "multirank_stage"):
    """(host_side, exec_side) paths of the endpoint's staging directory.

    scp/copy lands on the HOST side; execution sees the EXEC side (identical
    bytes via the stage bind mount for the container forms; the same path
    for bare remote, which has no container to translate through). Bare
    local needs NO staging — callers take the in-process path before here.
    """
    if endpoint.exec_mode == "remote":
        d = f"/tmp/{base}"
        return d, d
    if endpoint.exec_mode == "local":
        raise RuntimeError(
            "bare-local endpoints need no staging — take the in-process path instead"
        )
    host_dir = endpoint.stage_host_dir
    container_dir = endpoint.stage_container_dir
    if not host_dir:
        raise RuntimeError(
            "remote staging requires a staging area — set STAGE_HOST_DIR "
            "(or the legacy host_home) on the generation block"
        )
    return (f"{host_dir.rstrip('/')}/{base}", f"{container_dir.rstrip('/')}/{base}")


@dataclass
class CollectorLaunch:
    """Truth-collector launch request: target endpoint + task files.

    Construct with one keyword per line (CollectorLaunch(endpoint=...,
    spec_path=..., ...)).
    """

    endpoint: object
    spec_path: Path
    in_file: Path
    out_file: Path
    wrapper_path: "object | None" = None
    lanes: "object | None" = None


def _run_collector_local(launch: CollectorLaunch, collector: Path) -> Path:
    """Local bare host: the collector subprocess in this process's python."""
    import os
    import subprocess
    import sys as _sys

    cmd = [
        _sys.executable,
        str(collector),
        str(launch.spec_path),
        str(launch.in_file),
        str(launch.out_file),
    ]
    if launch.wrapper_path is not None:
        cmd += ["--wrapper", str(launch.wrapper_path)]
    env = dict(os.environ)
    if launch.lanes:
        env["MULTIRANK_LANES"] = ",".join(str(x) for x in launch.lanes)
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_COLLECT_TIMEOUT_SEC,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"npubench collector timed out after {_COLLECT_TIMEOUT_SEC}s"
        ) from exc
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "")[-2000:]
        raise RuntimeError(f"npubench collector failed (rc={r.returncode}): {tail}")
    return launch.out_file


def _run_collector_remote(launch: CollectorLaunch, collector: Path) -> Path:
    """Remote/container: stage the executable surface, run remotely, pull
    the output back."""
    endpoint = launch.endpoint
    spec_path, in_file, out_file = launch.spec_path, launch.in_file, launch.out_file
    wrapper_path, lanes = launch.wrapper_path, launch.lanes
    stage_host, stage_exec = endpoint_stage_dir(endpoint)
    remote_exec(endpoint, ["mkdir", "-p", stage_exec])
    in_path = Path(in_file)
    staged = [
        (collector, "multirank_npu_bench_collect.py"),
        (Path(spec_path), "spec.py"),
        (in_path, in_path.name),
    ]
    # The generated spec imports its frozen task module (from task import
    # ...) — the pair must land beside the staged spec or the remote import
    # fails.
    frozen_task = Path(spec_path).parent / "task.py"
    if frozen_task.is_file():
        staged.append((frozen_task, "task.py"))
    if wrapper_path is not None:
        staged.append((Path(wrapper_path), "wrapper.py"))
    sync_up(endpoint, staged, stage_host)
    in_exec = f"{stage_exec}/{in_path.name}"
    spec_exec = f"{stage_exec}/spec.py"
    out_name = Path(out_file).name
    out_exec = f"{stage_exec}/{out_name}"
    remote_cmd = [
        "python3",
        f"{stage_exec}/multirank_npu_bench_collect.py",
        spec_exec,
        in_exec,
        out_exec,
    ]
    if wrapper_path is not None:
        remote_cmd += ["--wrapper", f"{stage_exec}/wrapper.py"]
    if lanes:
        # `env VAR=... cmd` prefix — portable across ssh and container-exec
        # command lists (the staged remote collector cannot import npu_probe,
        # so the lanes MUST arrive via the environment).
        remote_cmd = [
            "env",
            f"MULTIRANK_LANES={','.join(str(x) for x in lanes)}",
            *remote_cmd,
        ]
    r = remote_exec(endpoint, remote_cmd, timeout=_COLLECT_TIMEOUT_SEC)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "")[-2000:]
        raise RuntimeError(
            f"remote npubench collector failed (rc={r.returncode}): {tail}"
        )
    sync_down(endpoint, stage_host, [out_name], Path(out_file).parent)
    return out_file


def run_collector(launch: CollectorLaunch) -> Path:
    """Launch the truth collector subprocess on the endpoint.

    Local bare host: Popen in this process's python (engine co-located with
    the NPU). Remote/container: stage spec + its frozen task pair + (a3_live)
    the source-operator wrapper + collector + input on the endpoint's
    staging area (md5-manifest skip), execute the collector remotely
    (python3 on the endpoint's NPU environment), pull the output back. The
    subprocess isolates the orchestrator from torch_npu: a crash or hang in
    the reference implementation cannot poison the orchestrator.

    ``lanes`` (optional, from pick_idle_npu in the CALLER — this process can
    reach the endpoint's probe, the remote collector subprocess cannot
    import npu_probe) is injected as MULTIRANK_LANES: the collector's rank
    subprocesses then share ONE card-group mask instead of the legacy
    per-rank single-card mask (which CANN renumber semantics break for
    ranks > 0). None → the collector self-resolves (env override or its own
    local probe, with a warned legacy fallback).
    """
    collector = Path(__file__).resolve().parent / "multirank_npu_bench_collect.py"
    if launch.endpoint.exec_mode == "local":
        return _run_collector_local(launch, collector)
    if not REMOTE_LAUNCH_WIRED:
        raise RuntimeError(
            f"launch primitive for exec_mode={launch.endpoint.exec_mode!r} is not "
            f"wired (feasibility should have refused this earlier)"
        )
    return _run_collector_remote(launch, collector)


# ---------------------------------------------------------------------------
# Staging area mapping (host dir <-> container dir)
# ---------------------------------------------------------------------------
_DEFAULT_STAGE_CONTAINER_DIR = "/home/npu_user"


def stage_map(cfg) -> tuple[str, str]:
    """(host_dir, container_dir) of a generation block's staging area.

    The explicit STAGE_* pair wins; the fallback keeps the legacy
    A3_HOST_HOME + container_home (default /home/npu_user) convention, so
    existing deployments behave identically.
    """
    host_dir = cfg.stage_host_dir or cfg.host_home
    container_dir = (
        cfg.stage_container_dir or cfg.container_home or _DEFAULT_STAGE_CONTAINER_DIR
    )
    return host_dir, container_dir


def translate_to_container(cfg, path) -> Path:
    """Deterministic prefix replacement: host-side staging path → the same
    physical location as seen INSIDE the container.

    Fail-closed on paths outside the staging area — a path the mapping
    cannot translate must never be guessed at.
    """
    host_dir, container_dir = stage_map(cfg)
    p = str(path)
    if not host_dir:
        return Path(path)
    host_prefix = host_dir.rstrip("/")
    if p == host_prefix:
        return Path(container_dir.rstrip("/"))
    if p.startswith(host_prefix + "/"):
        _cut = len(host_prefix) + 1
        return Path(container_dir.rstrip("/")) / p[_cut:]
    raise ValueError(
        f"path {p!r} is not under the stage host dir {host_dir!r} — the "
        f"container-side path cannot be derived; fix "
        f"STAGE_HOST_DIR/STAGE_CONTAINER_DIR"
    )


def _bind_covers_stage(binds, host_dir: str, container_dir: str) -> bool:
    """True when a docker Bind maps host_dir to exactly container_dir.

    A bind covers the stage area when the host dir sits AT or UNDER the
    bind's host side AND the bind maps it to exactly the declared container
    dir: exact bind, or suffix-mapped through an ancestor mount (stage
    /h/agent-dir under bind /h:/h — files copied to the host dir appear at
    the declared container path)."""
    host_r = host_dir.rstrip("/")
    cont_r = container_dir.rstrip("/")
    for b in binds or []:
        parts = str(b).split(":")
        if len(parts) < 2:
            continue
        bh, bc = parts[0].rstrip("/"), parts[1].rstrip("/")
        if host_r == bh:
            if cont_r == bc:
                return True
        elif host_r.startswith(bh + "/"):
            _bh = len(bh)
            if cont_r == bc + host_r[_bh:]:
                return True
    return False


def verify_stage_mount(endpoint, cfg=None) -> list[str]:
    """P129 generalized: docker inspect must show host_dir -> container_dir

    as an actual bind mount of the endpoint's container (fail-closed before
    any scp writes to a host path the container cannot see). Runs on the
    HOST side via _ssh_base (host:port + sshpass aware — the single-card
    P129 helper parses neither). Returns a list of user-facing errors
    (empty = verified).
    """
    import json as _json
    import subprocess

    if endpoint.exec_mode != "remote-container":
        return []
    host_dir, container_dir = (
        stage_map(cfg)
        if cfg is not None
        else (endpoint.stage_host_dir, endpoint.stage_container_dir)
    )
    if not (endpoint.host and endpoint.container and host_dir):
        return []
    cmd = _ssh_base(endpoint) + _quote_remote(
        [
            "docker",
            "inspect",
            endpoint.container,
            "--format",
            "{{json .HostConfig.Binds}}",
        ]
    )
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return [f"stage-mount check: docker inspect timed out on {endpoint.host}"]
    if r.returncode != 0:
        return [
            f"stage-mount check could not run docker inspect on "
            f"{endpoint.host} (rc={r.returncode}: "
            f"{(r.stderr or '')[:120]}) — verify the ssh target "
            f"(host:port supported) and the container name"
        ]
    try:
        binds = _json.loads(r.stdout.strip())
    except Exception:
        binds = [s for s in r.stdout.strip().strip('"[]').split(",") if s]
    if _bind_covers_stage(binds, host_dir, container_dir):
        return []
    return [
        f"stage mount mismatch: {endpoint.container} must expose "
        f"{host_dir} as {container_dir}; actual Binds: {binds}. Fix the "
        f"container mount or STAGE_HOST_DIR/STAGE_CONTAINER_DIR"
    ]


# ---------------------------------------------------------------------------
# Remote transport primitives (ssh/scp). Auth mirrors the single-card A5
# convention (phase_o5_runner): a non-empty block password selects sshpass;
# empty falls back to SSH key auth (a3_ref convention).
# ---------------------------------------------------------------------------
def _auth_prefix(endpoint) -> list:
    if endpoint.password:
        return ["sshpass", "-p", endpoint.password]
    return []


def _host_port(endpoint) -> tuple:
    """Split `A<n>_HOST` into (host, port|None). Accepted forms: bare host,
    `host:port`, `[v6]:port`. Single-card paths (a3_ref/phase_o5_runner) do
    NOT parse this — they take a bare host or an ~/.ssh/config alias."""
    h = endpoint.host
    if h.startswith("[") and "]:" in h:  # [v6]:port
        host, _, port = h.rpartition("]:")
        return host + "]", port or None
    if h.count(":") == 1:  # v4:port
        host, _, port = h.rpartition(":")
        return host, port or None
    return h, None  # bare v4/v6, no port (22)


def _ssh_base(endpoint) -> list:
    host, port = _host_port(endpoint)
    args = _auth_prefix(endpoint) + [
        "ssh",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
    ]
    if port:
        args += ["-p", port]
    args.append(f"{endpoint.user}@{host}")
    return args


def _quote_remote(cmd: list) -> list:
    """Quote each token of a command sent THROUGH ssh: the ssh client joins
    the remote command into a single string that the remote login shell
    re-parses, so any token containing spaces or shell metacharacters (e.g.
    a docker --format template) must be single-quoted to survive the round
    trip. Local argv execution (docker exec without ssh) must NOT quote."""
    import shlex

    return [shlex.quote(t) for t in cmd]


def _scp_base(endpoint) -> list:
    host, port = _host_port(endpoint)
    args = _auth_prefix(endpoint) + [
        "scp",
        "-q",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
    ]
    if port:
        args += ["-P", port]  # scp's port flag is -P (capital), not -p
    return args


def remote_exec(endpoint, cmd: list, timeout: int = 1800):
    """Run cmd ON the endpoint (any non-local-bare form).

    remote = ssh direct; remote-container = ssh + docker exec;
    local-container = docker exec on THIS machine (engine co-located with
    the NPU container). Commands receive CONTAINER-side paths — the caller
    translates (translate_to_container); bare-local endpoints never reach
    here (in-process Popen is the bare-local primitive).
    """
    import subprocess

    if endpoint.exec_mode == "remote":
        full = _ssh_base(endpoint) + _quote_remote(cmd)
    elif endpoint.exec_mode == "remote-container":
        full = _ssh_base(endpoint) + _quote_remote(
            ["docker", "exec", endpoint.container, *cmd]
        )
    elif endpoint.exec_mode == "local-container":
        full = ["docker", "exec", endpoint.container, *cmd]
    else:
        raise RuntimeError(
            f"remote_exec is for container/remote endpoints; got "
            f"exec_mode={endpoint.exec_mode!r} (bare-local launches are "
            f"in-process Popen)"
        )
    try:
        return subprocess.run(full, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"remote command timed out after {timeout}s: {cmd[:3]}..."
        ) from exc


def _file_md5(path) -> str:
    import hashlib

    # change-detection fingerprint only (never a security primitive)
    h = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _remote_manifest(endpoint, remote_dir: str):
    """Read the remote .sync_manifest.json ({name: [md5, size]}), {} on any
    failure (a missing manifest simply means 'transfer everything')."""
    import json as _json

    r = remote_exec(
        endpoint, ["cat", f"{remote_dir.rstrip('/')}/.sync_manifest.json"], timeout=60
    )
    if r.returncode != 0:
        return {}
    try:
        data = _json.loads(r.stdout)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _sync_up_local_container(endpoint, files: list, remote_dir: str) -> dict:
    """local-container: local copy into the bind mount with md5 skip."""
    import shutil

    transferred: list = []
    skipped: list = []
    for local_path, name in files:
        dst = Path(remote_dir.rstrip("/")) / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_file() and _file_md5(dst) == _file_md5(local_path):
            skipped.append(name)
            continue
        shutil.copy2(local_path, dst)
        transferred.append(name)
    return {"transferred": transferred, "skipped": skipped}


def _push_sync_manifest(endpoint, new_manifest: dict, remote_dir: str) -> None:
    """Publish the updated md5 manifest atomically-ish (write local, push)."""
    import json as _json
    import subprocess
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
        tf.write(_json.dumps(new_manifest, sort_keys=True))
        manifest_local = tf.name
    try:
        target = (
            f"{endpoint.user}@{_host_port(endpoint)[0]}:"
            f"{remote_dir.rstrip('/')}/.sync_manifest.json"
        )
        r = subprocess.run(
            _scp_base(endpoint) + [manifest_local, target],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            raise RuntimeError(f"sync manifest push failed: {r.stderr[-500:]}")
    finally:
        Path(manifest_local).unlink(missing_ok=True)


def sync_up(endpoint, files: list, remote_dir: str) -> dict:
    """Push files to the endpoint's host-side staging dir with md5 skip.

    files = [(local_path, remote_name)]; remote_dir is the HOST-side staging
    dir (container endpoints see the same bytes at the translated path).
    bare-local: no-op (shared filesystem). local-container: local copy into
    the bind mount. remote forms: scp with the md5 manifest.
    Returns {"transferred": [...], "skipped": [...]}. Correctness has no
    precondition: md5+size equal means byte-equal, skipping is lossless.
    """
    import subprocess

    if endpoint.exec_mode == "local":
        return {"transferred": [], "skipped": [n for _, n in files]}
    if endpoint.exec_mode == "local-container":
        return _sync_up_local_container(endpoint, files, remote_dir)
    manifest = _remote_manifest(endpoint, remote_dir)
    transferred: list = []
    skipped: list = []
    new_manifest = dict(manifest)
    for local_path, name in files:
        entry = [_file_md5(local_path), str(local_path.stat().st_size)]
        if manifest.get(name) == entry:
            skipped.append(name)
            new_manifest[name] = entry
            continue
        target = (
            f"{endpoint.user}@{_host_port(endpoint)[0]}:{remote_dir.rstrip('/')}/{name}"
        )
        r = subprocess.run(
            _scp_base(endpoint) + [str(local_path), target],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if r.returncode != 0:
            raise RuntimeError(f"scp push failed for {name}: {r.stderr[-500:]}")
        new_manifest[name] = entry
        transferred.append(name)
    _push_sync_manifest(endpoint, new_manifest, remote_dir)
    return {"transferred": transferred, "skipped": skipped}


def _sync_down_local_container(
    endpoint, remote_dir: str, names: list, local_dir: Path
) -> dict:
    """local-container: local copy out of the bind mount with md5 skip."""
    import shutil

    transferred: list = []
    skipped: list = []
    for name in names:
        src = Path(remote_dir.rstrip("/")) / name
        dst = local_dir / name
        if not src.is_file():
            raise RuntimeError(f"sync_down: missing {src}")
        if dst.is_file() and _file_md5(dst) == _file_md5(src):
            skipped.append(name)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        transferred.append(name)
    return {"transferred": transferred, "skipped": skipped}


def _remote_md5_map(endpoint, remote_dir: str, names: list) -> dict:
    """{name: md5} of the remote files (empty when the md5sum call fails)."""
    r = remote_exec(
        endpoint,
        ["md5sum", *[f"{remote_dir.rstrip('/')}/{n}" for n in names]],
        timeout=300,
    )
    remote_md5: dict = {}
    if r.returncode == 0:
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) == 2:
                remote_md5[parts[1].rsplit("/", 1)[-1]] = parts[0]
    return remote_md5


def sync_down(endpoint, remote_dir: str, names: list, local_dir) -> dict:
    """Pull files with md5 skip (files already present locally with the same

    md5 are not re-pulled — serves resume/retry; fresh outputs differ by
    content and transfer normally). bare-local: no-op; local-container:
    local copy out of the bind mount; remote forms: scp.
    """
    import subprocess

    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    if endpoint.exec_mode == "local":
        return {"transferred": [], "skipped": list(names)}
    if endpoint.exec_mode == "local-container":
        return _sync_down_local_container(endpoint, remote_dir, names, local_dir)
    remote_md5 = _remote_md5_map(endpoint, remote_dir, names)
    transferred: list = []
    skipped: list = []
    for name in names:
        local = local_dir / name
        want = remote_md5.get(name)
        if want is not None and local.is_file() and _file_md5(local) == want:
            skipped.append(name)
            continue
        src = (
            f"{endpoint.user}@{_host_port(endpoint)[0]}:{remote_dir.rstrip('/')}/{name}"
        )
        local.parent.mkdir(parents=True, exist_ok=True)
        rr = subprocess.run(
            _scp_base(endpoint) + [src, str(local)],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        if rr.returncode != 0:
            raise RuntimeError(f"scp pull failed for {name}: {rr.stderr[-500:]}")
        transferred.append(name)
    return {"transferred": transferred, "skipped": skipped}


def pick_idle_npu(endpoint, n: int):
    """Probe the endpoint's idle cards: (ids, None) or (None, reason).

    bare-local: npu_probe's local probe. Container/remote: run npu-smi on
    the endpoint and parse the text with npu_probe's shared smi-text
    parser — the idle criteria stay single-sourced in npu_probe.idle_ids
    instead of a per-call-site re-derivation.
    """
    import npu_probe

    if endpoint.exec_mode == "local":
        return npu_probe.pick_idle(None, n)
    r = remote_exec(endpoint, ["npu-smi", "info"], timeout=90)
    if r.returncode != 0:
        return None, (f"npu-smi rc={r.returncode}: {(r.stderr or '')[:120]}")
    probe = npu_probe.probe_result_from_smi_text(r.stdout, source="npu-smi(endpoint)")
    if probe is None:
        return None, "endpoint npu-smi parsed to zero devices"
    idle = npu_probe.idle_ids(probe)
    if len(idle) < n:
        return None, (
            f"only {len(idle)} idle NPU(s) {idle} on the endpoint "
            f"for world_size={n} (probe source: {probe.source})"
        )
    return idle[:n], None


def load_env_or_none():
    """Best-effort env load for provision-time checks (None when the env

    file is absent/unreadable — itself a fail-closed fact for NPU tiers).
    """
    try:
        from briefs._common import load_env

        return load_env()
    except Exception:
        return None


def tier_feasibility_errors(tier: str, env) -> Optional[list[str]]:
    """check_truth_tier_feasible with the missing-env case folded in."""
    if env is None:
        return [
            f"truth tier {tier!r} requires a resolvable .ascendc_env "
            f"(generation blocks + exec modes) — the env file is missing "
            f"or unreadable"
        ]
    return check_truth_tier_feasible(tier, env)
