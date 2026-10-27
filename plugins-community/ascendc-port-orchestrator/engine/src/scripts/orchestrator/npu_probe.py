# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""npu_probe — replaceable NPU-info fetch layer for lane allocation.

Single entry point for "which NPUs exist and are they busy". Two sources,
normalized into one shape:

  1. **Custom command** — `.ascendc_env` key, resolved target-first:
     `{TARGET}_NPU_INFO_CMD` > `NPU_INFO_CMD` (see `load_npu_info_cmd`
     below — this repo's `briefs._common.AscendCEnv` does not carry the
     `npu_info_cmd` field, so the minimal reader lives HERE instead of in
     `_common`). Runs LOCALLY via subprocess (ssh-composed execution on a
     remote target is a recorded DEBT — when both an ssh target and a custom
     command are configured, the intended composition is: ssh to the target,
     run the command there; not yet implemented). Use when npu-smi is absent
     or untrustworthy in the deployment environment (cgroup slicing,
     virtualized cards, k8s).
  2. **Default**: local `npu-smi info`, parsed by lane_pool.parse_npu_smi.

Custom command output contract — ONE JSON document on stdout, fields mirror
the `npu-smi info` ascii columns:

  {
    "driver_version": "25.5.2",      // optional — npu-smi header "Version:"
    "soc": "Ascend910B4",            // optional — acl.get_soc_name() equivalent
    "devices": [
      {"id": 0,                       // required — NPU column
       "util_pct": 0,                 // required — AICore(%) column
       "processes": 0,                // required — process-table row count
       "health": "OK",                // optional (default "OK") — Health column
       "name": "910B4",               // optional — Name column
       "mem_used_mb": 0, "mem_total_mb": 0,           // optional — Memory-Usage(MB)
       "hbm_used_mb": 30246, "hbm_total_mb": 32768}   // optional — HBM-Usage(MB)
    ]
  }

Failure semantics (deliberate, do not soften):
  - Custom command configured BUT failing (non-zero exit / timeout / malformed
    JSON / a device missing a required field) → fetch_devices returns None
    and the reason is printed to stderr. NEVER silently falls back to
    npu-smi: a custom command is configured precisely when npu-smi cannot be
    trusted in that environment.
  - No custom command AND npu-smi fails → None (callers keep their existing
    fail-open/fail-loud policy).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_PROBE_TIMEOUT_SEC = 30
_IDLE_UTIL_THRESHOLD = 5  # matches lane_pool.probe_idle_npus


# Raw-format loggers keep the original streams: stderr diagnostics, stdout table.
class _LazyStderrHandler(logging.StreamHandler):
    """Resolves sys.stderr at emit time. The print-based diagnostics this
    module replaced resolved sys.stderr at each call, so per-test capture
    (capsys swaps sys.stderr) saw them; a StreamHandler constructed at import
    time pins the original stderr object and dodges that capture. Emit-time
    resolution keeps the observable stream identical (process stderr)."""

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _value):
        pass  # constructor assignment ignored; emit-time lookup owns it


_LOG = logging.getLogger("npu_probe.diag")
_ERR_H = _LazyStderrHandler()
_ERR_H.setFormatter(logging.Formatter("%(message)s"))
_LOG.addHandler(_ERR_H)
_LOG.propagate = False
_CLI = logging.getLogger("npu_probe.cli")
_OUT_H = logging.StreamHandler(sys.stdout)
_OUT_H.setFormatter(logging.Formatter("%(message)s"))
_CLI.addHandler(_OUT_H)
_CLI.propagate = False
_CLI.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Minimal .ascendc_env reader (owned here, NOT in briefs._common)
# ---------------------------------------------------------------------------
# `npu_info_cmd` is resolved in THIS module, not in briefs._common.AscendCEnv
# (which has no such field): the minimal reading logic (KEY=VALUE parse +
# target-first key resolution, same semantics as _common.load_env's
# generation-block precedence) is inlined here.
# When AscendCEnv later gains `npu_info_cmd`, fetch_devices' duck-typed env
# accepts either carrier unchanged.
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = (
    _HERE.parent.parent.parent.parent
)  # engine/ (same root briefs._common anchors on)
DEFAULT_ASCENDC_ENV = _PROJECT_ROOT / "workspace" / ".ascendc_env"

_KV_LINE = re.compile(r"^([A-Z_][A-Z0-9_]*)=(.*)$")


def _parse_env_kv(text: str) -> dict[str, str]:
    """Parse .ascendc_env shell-style KEY=VALUE lines (mirrors
    briefs._common.load_env's parser: skip blanks/#comments, strip one pair
    of matching quotes). Deliberately minimal — only what the probe needs."""
    kv: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _KV_LINE.match(line)
        if not m:
            continue
        val = m.group(2).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        kv[m.group(1)] = val
    return kv


def load_npu_info_cmd(env_file: Optional[Path] = None) -> str:
    """Resolve the custom NPU-info command from `.ascendc_env`, target-first:

        {TARGET}_NPU_INFO_CMD > NPU_INFO_CMD > A5_NPU_INFO_CMD

    TARGET-SPECIFIC WINS over the generic key (DEBT-227 discipline: a stale
    generic key must never silently shadow the target-specific one — when
    both are set AND differ, warn loudly on stderr, then use the
    target-specific value). `A5_NPU_INFO_CMD` is the last resort, preserving
    the default-to-A5 behavior for envs that only populate the A5 block.

    Returns "" (→ the default local `npu-smi info` path) when the file is
    absent or no key is set — config resolution is fail-soft; it is the
    PROBE execution that must fail loud (see fetch_devices).
    `ASCENDC_ENV_PATH` env var overrides the default file path, same
    precedence rule as briefs._common.load_env.
    """
    if env_file is None:
        override = os.environ.get("ASCENDC_ENV_PATH")
        env_file = Path(override) if override else DEFAULT_ASCENDC_ENV
    if not env_file.exists():
        return ""
    kv = _parse_env_kv(env_file.read_text())
    target = kv.get("TARGET", "a5")
    # a3 → A3 ; a3-ds → A3_DS → base A3 (compound targets share the plain block)
    tp_base = target.upper().replace("-", "_").split("_")[0]
    target_key = f"{tp_base}_NPU_INFO_CMD"
    generic_key = "NPU_INFO_CMD"
    fallback_key = "A5_NPU_INFO_CMD"
    target_val = kv.get(target_key)
    generic_val = kv.get(generic_key)
    if target_val and generic_val and generic_val != target_val:
        _LOG.warning(
            f"[npu_probe] WARNING: both {target_key}={target_val!r} and generic "
            f"{generic_key}={generic_val!r} are set and DIFFER (TARGET={target}). "
            f"Using the target-specific {target_key} — the generic "
            f"{generic_key} is IGNORED (it would silently override; "
            f"DEBT-227 discipline). Remove the generic {generic_key} from "
            f".ascendc_env to silence this."
        )
    return target_val or generic_val or kv.get(fallback_key, "")


@dataclass
class ProbeEnv:
    """Minimal env carrier for the probe layer: everything fetch_devices

    needs from an environment is `.npu_info_cmd`. Exists because this repo's
    briefs._common.AscendCEnv lacks that field; a future AscendCEnv carrying
    it feeds fetch_devices unchanged (duck-typed — only the attribute is
    read).
    """

    npu_info_cmd: str = ""

    @classmethod
    def from_env_file(cls, env_file: Optional[Path] = None) -> "ProbeEnv":
        """Build a ProbeEnv from an .ascendc_env file (default: the standard

        workspace file, ASCENDC_ENV_PATH override honored).
        """
        return cls(npu_info_cmd=load_npu_info_cmd(env_file))


@dataclass
class NpuDevice:
    """One NPU, normalized across the custom-command and npu-smi sources."""

    id: int
    util_pct: int = 0
    processes: int = 0
    health: str = "OK"
    name: str = ""
    mem_used_mb: int = 0
    mem_total_mb: int = 0
    hbm_used_mb: int = 0
    hbm_total_mb: int = 0


@dataclass
class ProbeResult:
    devices: dict[int, NpuDevice]
    source: str  # "custom:<cmd>" | "npu-smi"
    driver_version: str = ""
    soc: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def _fail(msg: str) -> None:
    _LOG.error(f"[npu_probe] {msg}")


def _parse_custom_json(text: str) -> Optional[dict[int, NpuDevice]]:
    """Parse + validate the custom-command JSON. Returns None on any contract
    violation (caller treats as probe failure — never falls back)."""
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        _fail(f"custom NPU_INFO_CMD output is not valid JSON: {e}")
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("devices"), list):
        _fail("custom NPU_INFO_CMD JSON must be an object with a 'devices' list")
        return None
    devices: dict[int, NpuDevice] = {}
    for i, d in enumerate(doc["devices"]):
        if not isinstance(d, dict):
            _fail(f"devices[{i}] is not an object")
            return None
        missing = [k for k in ("id", "util_pct", "processes") if k not in d]
        if missing:
            _fail(
                f"devices[{i}] missing required field(s) {missing} "
                f"(id / util_pct / processes mirror the npu-smi NPU, "
                f"AICore%% and process-table columns)"
            )
            return None
        try:
            dev = NpuDevice(
                id=int(d["id"]),
                util_pct=int(d["util_pct"]),
                processes=int(d["processes"]),
                health=str(d.get("health", "OK")),
                name=str(d.get("name", "")),
                mem_used_mb=int(d.get("mem_used_mb", 0)),
                mem_total_mb=int(d.get("mem_total_mb", 0)),
                hbm_used_mb=int(d.get("hbm_used_mb", 0)),
                hbm_total_mb=int(d.get("hbm_total_mb", 0)),
            )
        except (TypeError, ValueError) as e:
            _fail(f"devices[{i}] field type error: {e!r}")
            return None
        devices[dev.id] = dev
    return devices


def fetch_devices(
    env=None, *, timeout_sec: int = _PROBE_TIMEOUT_SEC
) -> Optional[ProbeResult]:
    """Fetch normalized NPU device info. `env` is any object exposing
    `.npu_info_cmd` (ProbeEnv / a future AscendCEnv); None → default npu-smi
    path.

    Returns ProbeResult, or None on failure (reason printed to stderr).
    """
    cmd = getattr(env, "npu_info_cmd", "") if env is not None else ""
    if cmd:
        try:
            r = subprocess.run(
                shlex.split(cmd), capture_output=True, text=True, timeout=timeout_sec
            )
        except subprocess.TimeoutExpired:
            _fail(f"custom NPU_INFO_CMD timed out after {timeout_sec}s: {cmd!r}")
            return None
        except (OSError, ValueError) as e:
            _fail(f"custom NPU_INFO_CMD invocation failed: {e!r} (cmd={cmd!r})")
            return None
        if r.returncode != 0:
            _fail(
                f"custom NPU_INFO_CMD rc={r.returncode}: "
                f"{(r.stderr or '').strip()[:200]} (cmd={cmd!r})"
            )
            return None
        devices = _parse_custom_json(r.stdout)
        if devices is None:
            return None
        try:
            doc = json.loads(r.stdout)
        except json.JSONDecodeError:
            doc = {}
        return ProbeResult(
            devices=devices,
            source=f"custom:{cmd}",
            driver_version=str(doc.get("driver_version", "")),
            soc=str(doc.get("soc", "")),
        )

    # Default: local npu-smi, parsed by the existing text parser.
    npu_smi = shutil.which("npu-smi") or "npu-smi"
    try:
        r = subprocess.run(
            [npu_smi, "info"], capture_output=True, text=True, timeout=timeout_sec
        )
    except subprocess.TimeoutExpired:
        _fail(f"npu-smi info timed out after {timeout_sec}s")
        return None
    except OSError as e:
        _fail(f"npu-smi invocation failed: {e!r}")
        return None
    if r.returncode != 0:
        _fail(f"npu-smi info rc={r.returncode}: {(r.stderr or '').strip()[:200]}")
        return None
    result = probe_result_from_smi_text(r.stdout)
    if result is None:
        _fail("npu-smi info parsed to zero devices")
        return None
    return result


def probe_result_from_smi_text(
    text: str, source: str = "npu-smi"
) -> Optional[ProbeResult]:
    """Parse npu-smi text output into a ProbeResult.

    Shared by the local default probe and remote endpoints running the
    same npu-smi binary — the idle criteria stay single-sourced in
    idle_ids() instead of being re-derived per call site. None when the
    text parses to zero devices.
    """
    # Flat top-level import, same convention as every sibling module in this
    # package (orchestrator/ is put on sys.path by the runtime bootstrap in
    # __main__.py and by the test conftest). Lazy, like the source version,
    # to keep `import npu_probe` free of subprocess-module side effects.
    import lane_pool

    # valid_ids=None: accept every parsed card id — the caller must see all
    # cards on the host, however many there are.
    statuses = lane_pool.parse_npu_smi(text, valid_ids=None)
    if not statuses:
        return None
    devices = {
        nid: NpuDevice(
            id=nid, util_pct=s.util_pct, processes=1 if s.has_running_process else 0
        )
        for nid, s in statuses.items()
    }
    return ProbeResult(devices=devices, source=source)


def idle_ids(
    result: ProbeResult, *, util_threshold: int = _IDLE_UTIL_THRESHOLD
) -> list[int]:
    """Idle NPUs: util ≤ threshold AND no running process (mirrors lane_pool.probe_idle_npus semantics)."""
    return [
        nid
        for nid, d in sorted(result.devices.items())
        if d.util_pct <= util_threshold and d.processes == 0
    ]


def pick_idle(env=None, n: int = 1) -> "tuple[list[int] | None, str | None]":
    """Probe and pick `n` idle cards. Returns (lanes, None) or (None, error).

    Probe failure or fewer than `n` idle cards is a HARD error string —
    callers must never degrade to unprobed or busy cards.
    """
    probe = fetch_devices(env)
    if probe is None:
        return None, (
            "NPU probe failed (reason on stderr) — refusing to select unprobed cards"
        )
    idle = idle_ids(probe)
    if len(idle) < n:
        return None, (
            f"only {len(idle)} idle NPU(s) {idle} but {n} needed "
            f"(probe source: {probe.source})"
        )
    return idle[:n], None


def confirm_idle(
    env, lanes: list[int], *, settle_sec: float = 10.0, poll_sec: float = 2.0
) -> "str | None":
    """Post-run confirmation: every card in `lanes` must show processes==0.

    Polls for up to `settle_sec` (the process table can lag a few seconds
    behind rank-subprocess exit). Returns None when clean, else an error
    string naming the cards still showing processes. Catches leaked/lingering
    rank processes; a foreign process that came AND left inside the window is
    NOT detectable — documented honest boundary.
    """
    import time

    deadline = time.monotonic() + settle_sec
    while True:
        probe = fetch_devices(env)
        if probe is None:
            return "post-run NPU probe failed (reason on stderr)"
        busy = [
            ln
            for ln in lanes
            if ln in probe.devices and probe.devices[ln].processes > 0
        ]
        if not busy:
            return None
        if time.monotonic() >= deadline:
            return (
                f"post-run check: card(s) {busy} still show "
                f"running processes after the group finished "
                f"(possible leaked rank process)"
            )
        time.sleep(poll_sec)


if __name__ == "__main__":
    # Contract viewer / validator:
    #   python3 npu_probe.py                       → default npu-smi path
    #   python3 npu_probe.py -- /path/probe.sh --json
    #       → run the custom command, validate its stdout against the JSON
    #         contract, print the parsed device table + idle list.
    # A contract violation exits non-zero with the reason on stderr.
    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    if argv:
        _env: Optional[ProbeEnv] = ProbeEnv(npu_info_cmd=" ".join(argv))
    else:
        _env = None
    res = fetch_devices(_env)
    if res is None:
        sys.exit(1)
    _CLI.info(f"source: {res.source}")
    if res.driver_version:
        _CLI.info(f"driver_version: {res.driver_version}")
    if res.soc:
        _CLI.info(f"soc: {res.soc}")
    _CLI.info(
        f"{'id':>4} {'util%':>6} {'procs':>6} {'health':>7} "
        f"{'hbm_used':>9} {'hbm_total':>10}"
    )
    for d in res.devices.values():
        _CLI.info(
            f"{d.id:>4} {d.util_pct:>6} {d.processes:>6} {d.health:>7} "
            f"{d.hbm_used_mb:>9} {d.hbm_total_mb:>10}"
        )
    _CLI.info(f"idle: {idle_ids(res)}")
