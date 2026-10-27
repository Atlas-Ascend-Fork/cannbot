# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Common brief sections used by all agent briefs.

Provides templated chunks for: env config (lane env, A5 host, container, CANN
paths), hard floors (current verification.json baseline), exit handoff
options (per agent_type from YAML), schema canonical contract, KB manifest
load list (from op_taxonomy).

Goal: 90% deterministic Python templating + 10% optional LLM-synth for
op-specific deep dives. Per codex C1 we target 100% Python lookup via
op_taxonomy.

Usage:
    from briefs._common import (
        load_env, env_block, hard_floors_block, schema_contract_block,
        kb_manifest_block, exit_handoff_block,
    )
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from briefs.brief_kb import (  # re-export: KB cluster moved to brief_kb (behavior-neutral, 2026-07-05)
    _detect_forced_architecture,  # noqa: F401
    kb_manifest_block,  # noqa: F401
    _FORCED_ARCH_TAGS,  # noqa: F401
    # cannbot c>b>a blocks (re-exported so `from briefs._common import ...` stays stable
    # for the c-tier read-wiring test + any cannbot caller after the 2026-07-05 decomposition).
    _cba_tier_a_routes_block,  # noqa: F401
    _c_tier_lessons_block,  # noqa: F401
    # OKF-only (2026-08): OKF 检索是唯一 b-tier 路径; legacy 注入/开关/逃生门已移除。
    _okf_reference_block,  # noqa: F401
    _kb_discipline_scaffold,  # noqa: F401
)

# Single source of truth for the target → env-key prefix map (see
# briefs/target_env_map.py). Imported name stays re-exported so
# `from briefs._common import TARGET_ENV_PREFIXES` remains valid.
from briefs.target_env_map import TARGET_ENV_PREFIXES


_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parent.parent.parent.parent.parent  # → repo root
DEFAULT_ASCENDC_ENV = _PROJECT_ROOT / "workspace" / ".ascendc_env"


# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------
# Execution modes, one per generation block: connection (local/remote) x
# isolation (bare host / container). `<PREFIX>_EXEC` is the authoritative
# declaration; the normalized (host, container) view below keeps every legacy
# `container == "local"` consumer working unchanged:
#     local            host stays empty, container is local
#     local-container  host stays empty, container is the given name
#     remote           host is the given name, container stays empty
#     remote-container host is the given name, container is the given name
EXEC_MODES = ("local", "local-container", "remote", "remote-container")
DEFAULT_EXEC_MODE = "remote-container"

# Suffixes a generation block may carry (A<n>_<SUFFIX>). Blocks are
# discovered by scanning these suffixes: A2 works today, A6/A7 work the day
# they are written into the env — no code change.
_GENERATION_BLOCK_FIELDS = {
    "HOST": "host",
    "USER": "user",
    "PASSWORD": "password",
    "EXEC": "exec_mode",
    "CONTAINER": "container",
    "CANN_PATH": "cann_path",
    "SOC_VERSION": "soc_version",
    "HOST_HOME": "host_home",
    "HOST_BACKUP": "host_backup",
    "WORKSPACE": "workspace",
    "DEPLOY_STAGE_HOST": "deploy_stage_host",
    "DEPLOY_STAGE_CONTAINER": "deploy_stage_container",
    "STAGE_HOST_DIR": "stage_host_dir",
    "STAGE_CONTAINER_DIR": "stage_container_dir",
    "CONTAINER_HOME": "container_home",
}
_GENERATION_BLOCK_RE = re.compile(r"^A(\d+)_([A-Z][A-Z0-9_]*)$")

# Deprecated process-env host-direct switches, mapped to EXEC=remote at load
# time (the runtime switch keeps winning over the file, its old precedence).
_HOST_MODE_SWITCHES = (("a3", "A3_HOST_MODE"), ("a5", "A5_HOST_MODE"))


@dataclass
class TargetConfig:
    """One generation block (A2_/A3_/A5_/... keys) of .ascendc_env.

    host/container are the NORMALIZED transport view derived from exec_mode
    (see EXEC_MODES). host_home is the HOST-side slice mount point (legacy
    A3_HOST_HOME); the container-side home is a separate convention owned by
    a3_ref_common (`A3_CONTAINER_HOME`) — never conflate the two.
    """

    arch: str
    host: str = ""
    user: str = "root"
    password: str = ""
    exec_mode: str = DEFAULT_EXEC_MODE
    container: str = ""
    cann_path: str = ""
    soc_version: str = ""
    host_home: str = ""
    host_backup: str = ""
    workspace: str = ""
    deploy_stage_host: str = ""
    deploy_stage_container: str = ""
    # Staging area mapping (host dir <-> container dir) for remote-container
    # sync: scp lands on the HOST side, execution sees the CONTAINER side.
    # Explicit STAGE_* pair wins; see multirank_endpoint.stage_map for the
    # legacy fallback (host_home + container_home).
    stage_host_dir: str = ""
    stage_container_dir: str = ""
    container_home: str = ""


def _empty_config(arch: str) -> TargetConfig:
    return TargetConfig(arch=arch)


def _ds(name: str) -> str:
    """Normalized target name: lowercase with any harness -suffix stripped
    (a3-ds → a3; the suffix selects a harness instance, not a chip family)."""
    n = (name or "").strip().lower()
    return n[:-3] if n.endswith("-ds") else n


def _apply_host_mode_switches(targets: dict) -> None:
    """Deprecated A<n>_HOST_MODE env switches → remote (migration warning)."""
    for arch, switch in _HOST_MODE_SWITCHES:
        if str(os.environ.get(switch, "")).strip() == "1":
            cfg = targets.setdefault(arch, _empty_config(arch))
            cfg.exec_mode = "remote"
            print(
                f"[briefs] WARNING: {switch}=1 is deprecated; set "
                f"{arch.upper()}_EXEC=remote in .ascendc_env instead",
                file=sys.stderr,
            )


def _normalize_block_transports(targets: dict) -> None:
    """Validate EXEC values and normalize each block's transport view.

    Fail-closed on the two ambiguous legacy forms: an unknown EXEC value and
    CONTAINER=local (the retired magic string — the error names the fix)."""
    for arch, cfg in targets.items():
        prefix = arch.upper()
        if cfg.exec_mode not in EXEC_MODES:
            raise ValueError(
                f"{prefix}_EXEC must be one of {'/'.join(EXEC_MODES)}; "
                f"got {cfg.exec_mode!r}"
            )
        if cfg.container.lower() == "local":
            # Legacy local shorthand (master-era templates/scripts write
            # A5_CONTAINER=local as the canonical local form): map it onto
            # EXEC=local with a migration nudge; EXEC stays authoritative.
            print(
                f"[briefs] WARNING: {prefix}_CONTAINER=local is the legacy "
                f"local form — declare {prefix}_EXEC=local and clear the "
                f"container name instead",
                file=sys.stderr,
            )
            cfg.exec_mode = "local"
        # Normalize the transport view from the (now authoritative) exec mode.
        if cfg.exec_mode == "local":
            cfg.host, cfg.container = "", "local"
        elif cfg.exec_mode == "local-container":
            cfg.host = ""
        elif cfg.exec_mode == "remote":
            cfg.container = ""
        # remote-container keeps both as written.


def _parse_generation_blocks(kv: dict) -> dict[str, TargetConfig]:
    """Discover A<n>_* generation blocks generically + normalize transports."""
    targets: dict[str, TargetConfig] = {}
    for key, val in kv.items():
        m = _GENERATION_BLOCK_RE.match(key)
        if m:
            arch, field = f"a{m.group(1)}", m.group(2)
        else:
            # non-A<digit> generation prefixes (e.g. ASCEND310P_ for 310p) are
            # resolved through the explicit target→prefix map, never derived
            # by uppercasing (310P_* is an illegal shell identifier).
            hit = next(
                (
                    name
                    for name, pref in TARGET_ENV_PREFIXES.items()
                    if pref != name.upper() and key.startswith(pref + "_")
                ),
                None,
            )
            if hit is None:
                continue
            _cut = len(TARGET_ENV_PREFIXES[hit]) + 1
            arch, field = hit, key[_cut:]
        attr = _GENERATION_BLOCK_FIELDS.get(field)
        if attr is None:
            continue
        cfg = targets.setdefault(arch, _empty_config(arch))
        setattr(cfg, attr, val.strip())

    _apply_host_mode_switches(targets)
    _normalize_block_transports(targets)
    return targets


class AscendCEnv:
    """Parsed workspace/.ascendc_env.

    Generation blocks (A<n>_*) are discovered generically — the generation
    set is open (A2 today, A6/A7 later), never a hardcoded enum. `target`
    (TARGET key, default a5) selects the candidate-side block; `source_arch`
    (SOURCE key, default a3) selects the reference-side block — env/source.

    The legacy attribute surface (host/user/container/cann_path/soc_version
    + a3_*/a5_*) is preserved as properties over the block views: existing
    consumers and `AscendCEnv(target=..., host=..., ...)` constructions keep
    working unchanged. Migration path (B): callers move to the block
    accessors batch by batch; the properties go last.
    """

    def __init__(
        self,
        target: str = "a5",
        host: str = "",
        user: str = "",
        password: str = "",
        container: str = "",
        cann_path: str = "",
        soc_version: str = "",
        benchmark_root: str = "",
        local_benchmark: str = "",
        local_project: str = "",
        archive_project: str = "",
        build_archive_enabled: bool = False,
        opgen_mode: str = "",
        port_a3_source: str = "",
        # Reference selection for newly created port-a3 workspaces. Empty means
        # "no implicit default": new invocations must pass an explicit
        # --reference-source (npubench, or a3_live for a live A3 capture).
        port_a3_reference_source: str = "",
        a3_host: str = "",
        a3_user: str = "root",
        a3_container: str = "",
        a3_cann_path: str = "",
        a3_soc_version: str = "",
        a3_workspace: str = "",
        a5_host: str = "",
        a5_container: str = "",
        a5_cann_path: str = "",
        a5_soc_version: str = "",
        a3_host_home: str = "",
        a3_host_backup: str = "",
        a3_deploy_stage_host: str = "",
        a3_deploy_stage_container: str = "",
        backend: str = "ascendc",
        subagent_settings: Optional[dict] = None,
        *,
        targets: Optional[dict] = None,
        source_arch: str = "a3",
    ):
        self.target = target or "a5"
        # TARGET may carry a -suffix (a3-ds); the BLOCK it selects is the
        # bare generation (a3) since blocks are keyed A<n>_*.
        _tbase = re.fullmatch(r"(a\d+)(?:-[a-z0-9_]+)?", self.target)
        self._target_base = _tbase.group(1) if _tbase else self.target
        self.source_arch = source_arch
        self.backend = backend
        self.benchmark_root = benchmark_root
        self.local_benchmark = local_benchmark
        self.local_project = local_project
        self.archive_project = archive_project
        self.build_archive_enabled = build_archive_enabled
        # Customer mode is seeded by the scoped CLI and then loaded from
        # durable state. Empty means "not resolved yet", never an implicit
        # third mode.
        self.opgen_mode = opgen_mode
        self.port_a3_source = port_a3_source
        self.port_a3_reference_source = port_a3_reference_source
        self.subagent_settings = subagent_settings
        if targets is not None:
            self.targets: dict[str, TargetConfig] = dict(targets)
            self.targets.setdefault(self._target_base, _empty_config(self._target_base))
            return
        self.targets = self._fold_legacy_blocks(
            self._target_base,
            flat={
                "host": host,
                "user": user,
                "password": password,
                "container": container,
                "cann_path": cann_path,
                "soc_version": soc_version,
            },
            a3_kw=dict(
                host=a3_host,
                user=a3_user or "root",
                container=a3_container,
                cann_path=a3_cann_path,
                soc_version=a3_soc_version,
                workspace=a3_workspace,
                host_home=a3_host_home,
                host_backup=a3_host_backup,
                deploy_stage_host=a3_deploy_stage_host,
                deploy_stage_container=a3_deploy_stage_container,
            ),
            a5_kw=dict(
                host=a5_host,
                container=a5_container,
                cann_path=a5_cann_path,
                soc_version=a5_soc_version,
            ),
        )

    @property
    def a3_cann_path(self) -> str:
        return self.target_config("a3").cann_path

    @property
    def a3_container(self) -> str:
        return self.target_config("a3").container

    @property
    def a3_deploy_stage_container(self) -> str:
        return self.target_config("a3").deploy_stage_container

    @property
    def a3_deploy_stage_host(self) -> str:
        return self.target_config("a3").deploy_stage_host

    # -- legacy per-generation views ------------------------------------------
    @property
    def a3_host(self) -> str:
        return self.target_config("a3").host

    @property
    def a3_host_backup(self) -> str:
        return self.target_config("a3").host_backup

    @property
    def a3_host_home(self) -> str:
        return self.target_config("a3").host_home

    @property
    def a3_soc_version(self) -> str:
        return self.target_config("a3").soc_version

    @property
    def a3_user(self) -> str:
        return self.target_config("a3").user

    @property
    def a3_workspace(self) -> str:
        return self.target_config("a3").workspace

    @property
    def a5_cann_path(self) -> str:
        return self.target_config("a5").cann_path

    @property
    def a5_container(self) -> str:
        return self.target_config("a5").container

    @property
    def a5_host(self) -> str:
        return self.target_config("a5").host

    @property
    def a5_soc_version(self) -> str:
        return self.target_config("a5").soc_version

    @property
    def cann_path(self) -> str:
        return self._active().cann_path or self.target_config("a5").cann_path

    @property
    def container(self) -> str:
        return self._active().container or self.target_config("a5").container

    @property
    def host(self) -> str:
        return self._active().host or self.target_config("a5").host

    @property
    def password(self) -> str:
        return self._active().password or self.target_config("a5").password

    @property
    def soc_version(self) -> str:
        return self._active().soc_version or self.target_config("a5").soc_version

    @property
    def user(self) -> str:
        return self._active().user or self.target_config("a5").user

    @staticmethod
    def _fold_legacy_blocks(
        target_base, flat, a3_kw, a5_kw
    ) -> "dict[str, TargetConfig]":
        """Legacy construction path: fold the flat legacy kwargs into block
        views.

        Per-generation kwargs seed their block first; the active-view fields
        then land on the TARGET block (only into empty slots — the specific
        per-generation key wins, mirroring the load_env target-first
        precedence)."""
        a3 = TargetConfig(arch="a3", **a3_kw)
        a5 = TargetConfig(arch="a5", **a5_kw)
        targets: "dict[str, TargetConfig]" = {"a3": a3, "a5": a5}
        block = targets.setdefault(target_base, _empty_config(target_base))
        for attr, val in (
            ("host", flat["host"]),
            ("user", flat["user"]),
            ("password", flat["password"]),
            ("container", flat["container"]),
            ("cann_path", flat["cann_path"]),
            ("soc_version", flat["soc_version"]),
        ):
            if val and not getattr(block, attr):
                setattr(block, attr, val)
        if not block.user:
            block.user = "root"
        return targets

    def exec_mode(self, arch: Optional[str] = None) -> str:
        return self.target_config(arch or self._target_base).exec_mode

    def get_subagent_settings(self, agent_type: str) -> Optional[str]:
        """Return settings-file path for given agent_type (or None).

        agent_type is e.g. 'aog-kernel-worker' / 'aog-precision-probe'.
        .ascendc_env keys are uppercase + dash→underscore:
            SUBAGENT_SETTINGS_AOG_KERNEL_WORKER=/path/to/settings.json
        """
        if not self.subagent_settings:
            return None
        key = agent_type.upper().replace("-", "_")
        return self.subagent_settings.get(key)

    def replace(self, **changes) -> "AscendCEnv":
        """dataclasses.replace-style copy for the plain-class env.

        Only non-generation fields may be overridden here (the callers this
        exists for tweak opgen_mode/archive_project mid-test); the block
        views are shared by reference, which is fine for read-side use.
        """
        base = dict(
            target=self.target,
            benchmark_root=self.benchmark_root,
            local_benchmark=self.local_benchmark,
            local_project=self.local_project,
            archive_project=self.archive_project,
            build_archive_enabled=self.build_archive_enabled,
            opgen_mode=self.opgen_mode,
            port_a3_source=self.port_a3_source,
            backend=self.backend,
            subagent_settings=self.subagent_settings,
            targets=self.targets,
            source_arch=self.source_arch,
        )
        base.update(changes)
        return AscendCEnv(**base)

    def source_view(self) -> TargetConfig:
        """Reference-side block (SOURCE selector; SOURCE=arch must be a

        configured A<n>_* block for the flows that use it).
        """
        return self.target_config(self.source_arch)

    # -- block accessors (new code reads these) -----------------------------
    def target_config(self, arch: str) -> TargetConfig:
        """Return the generation block for arch (empty config when absent)."""
        return self.targets.get(arch) or _empty_config(arch)

    # -- legacy active-target view (TARGET block, a5 fallback) --------------
    def _active(self) -> TargetConfig:
        return self.target_config(self._target_base)


# Targets allowed to fall back to generic keys (SOC_VERSION/CANN_PATH) and to
# the legacy A5_* block when their own prefix keys are absent. 310p is
# deliberately absent: a 310p env must carry ASCEND310P_* keys — inheriting an
# A5 environment by accident names the WRONG chip (build/verify would target
# 950PR silicon with a 200x toolchain assumption).
_GENERIC_COMPAT_TARGETS = frozenset(("a5", "a3", "a2"))

# Sentinel fallback key that can never exist in a parsed env — used to
# suppress generic/A5 fallback for non-compat targets (310p) without
# special-casing _resolve_target_first's signature.
_NO_KEY = "__NO_SUCH_KEY__"


def target_env_prefix(target: str) -> str:
    """Return the canonical env-key prefix for `target` ("310p" → "ASCEND310P").

    Case-insensitive; "-ds" backend-isolation suffix stripped (it selects a
    harness instance, not a different chip family). Unknown targets raise —
    failing loud here beats resolving against A5_* keys nobody configured.
    """
    normalized = (target or "").strip().lower()
    if normalized.endswith("-ds"):
        normalized = normalized[:-3]
    try:
        return TARGET_ENV_PREFIXES[normalized]
    except KeyError as error:
        raise ValueError(
            f"unknown TARGET {target!r}: supported targets are "
            f"{sorted(TARGET_ENV_PREFIXES)} (case-insensitive, optional -ds suffix)"
        ) from error


def _parse_env_kv(env_file: Path) -> "dict[str, str]":
    """Parse shell-style KEY=VALUE lines into a dict."""
    kv: dict[str, str] = {}
    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Fail loud on the legacy illegal-key spelling for 310p. Must run
        # BEFORE the KEY regex below: "310P_*" starts with a digit, so it can
        # never match `^([A-Z_]...)` — without this check the line is
        # SILENTLY SKIPPED, the value disappears, and the resolver proceeds
        # with an empty ASCEND310P_* block (the shell-side source fails on
        # such lines, the Python side must fail equally loud).
        if re.match(r"^310P_[A-Za-z0-9_]*=", line):
            raise ValueError(
                f"LEGACY_310P_ENV_KEYS at {env_file}: '310P_*' keys are not "
                "legal; use ASCEND310P_*"
            )
        m = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        # Strip optional matching quotes
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        kv[key] = val
    return kv


def _resolve_env_identity(kv: "dict[str, str]") -> tuple:
    """(target, source_arch, archive_project, base_generation) from the env
    kv — validates TARGET/SOURCE/OPGEN_MODE spellings."""
    target = (kv.get("TARGET") or "a5").strip().lower()
    source_arch = (kv.get("SOURCE") or "a3").strip().lower()
    # TARGET may carry a suffix (a3-ds); the generation BLOCK it selects is
    # the bare generation (a3) — blocks are keyed A<n>_*, so the base wins.
    _tmatch = re.fullmatch(r"(a\d+)(?:-[a-z0-9_]+)?", target)
    if not _tmatch:
        if _ds(target) in TARGET_ENV_PREFIXES:
            _tmatch = re.fullmatch(r"(\w+)", _ds(target))
        else:
            raise ValueError(
                f"TARGET must be a generation (a2/a3/a5/...) or an explicit "
                f"mapped target ({sorted(TARGET_ENV_PREFIXES)}), optionally "
                f"with a -suffix; got {target!r}"
            )
    if not re.fullmatch(r"a\d+", source_arch):
        raise ValueError(
            f"SOURCE must be a generation (a2/a3/a5/...); got {source_arch!r}"
        )
    env_mode = kv.get("OPGEN_MODE", "")
    if env_mode not in ("", "port_a3_to_a5", "backward"):
        raise ValueError(
            f"OPGEN_MODE may only be port_a3_to_a5 or backward; got {env_mode!r}"
        )
    # Archive namespace is DESTINATION-aware: a 310p port archives under its
    # own project (a3_to_310p_port) so the a5 namespace stays the a5-destination contract — mixing destinations in one
    # output tree makes "which chip was this ported for" unanswerable from the
    # archive layout. Must agree with a3_ref_common.PORT_DESTINATIONS and the
    # port_a3 plugin's archive_project_claim.
    _dest = (target or "").strip().lower()
    if _dest.endswith("-ds"):
        _dest = _dest[:-3]
    archive_project = {
        "port_a3_to_a5": "a3_to_310p_port" if _dest == "310p" else "a3_to_a5_port",
        "backward": "backward_ops",
    }.get(kv.get("OPGEN_MODE", ""), "generated_ops")
    return target, source_arch, archive_project, _tmatch.group(1)


def _apply_generic_key_fallback(
    kv: "dict[str, str]", targets: dict, base_generation: str
) -> None:
    """Generic-key compatibility fallback (deprecated write style).

    The generation block always wins; a generic HOST/USER/PASSWORD/CONTAINER/
    CANN_PATH/SOC_VERSION only fills EMPTY active-block fields, with a
    loud migration warning; a conflicting generic key is named and ignored
    (DEBT-227 semantics preserved). Generic keys never reach non-active
    blocks — write A<n>_* keys for those.
    Generic keys are a legacy-compat affordance for a5/a3/a2 only — a 310p
    block (ASCEND310P_*) must NOT inherit generic values: an empty 310p
    field means "misconfigured", not "use whatever generic says" (naming
    the WRONG chip — 950PR silicon with a 200x toolchain assumption)."""
    _generic_compat = base_generation in _GENERIC_COMPAT_TARGETS
    _generic_fallback = (
        ("host", "HOST"),
        ("user", "USER"),
        ("password", "PASSWORD"),
        ("container", "CONTAINER"),
        ("cann_path", "CANN_PATH"),
        ("soc_version", "SOC_VERSION"),
    )
    _base_prefix = base_generation.upper()
    _active_block = targets.get(base_generation) or _empty_config(base_generation)
    targets[base_generation] = _active_block
    for attr, generic_key in _generic_fallback if _generic_compat else ():
        generic_val = (kv.get(generic_key) or "").strip()
        if not generic_val:
            continue
        block_val = getattr(_active_block, attr)
        if block_val:
            if generic_val != block_val:
                print(
                    f"[briefs] WARNING: both {_base_prefix}_{generic_key}="
                    f"{block_val!r} and generic {generic_key}={generic_val!r} "
                    f"are set and DIFFER — the block key wins; remove the "
                    f"generic {generic_key} from workspace/.ascendc_env",
                    file=sys.stderr,
                )
            continue
        if attr == "container" and generic_val.lower() == "local":
            # a generic CONTAINER=local expresses the legacy local intent —
            # the block-local mapping (EXEC=local + warning) already covers
            # it; a generic fill would only alias the container name
            continue
        print(
            f"[briefs] WARNING: generic {generic_key} is deprecated — write "
            f"{_base_prefix}_{generic_key} instead; using it as a fallback "
            f"for this load",
            file=sys.stderr,
        )
        setattr(_active_block, attr, generic_val)


def load_env(env_file: Optional[Path] = None) -> AscendCEnv:
    """Parse workspace/.ascendc_env (shell-style KEY=VALUE).

    DEBT-101: `env_file` defaults to None (NOT DEFAULT_ASCENDC_ENV) so that
    `tests.monkeypatch(_common.DEFAULT_ASCENDC_ENV, ...)` is honored by
    `load_env()` callers across the orchestrator (batch.py + multiple
    orchestrator.py call sites previously passed no arg). A function default
    `= DEFAULT_ASCENDC_ENV` would bind the module-level value at def time,
    making monkeypatches no-ops for default-arg callers. Resolving the
    default at call time fixes the test-env-bypass class of bug.

    Subprocess override: `ASCENDC_ENV_PATH` env var, if set, takes precedence
    over DEFAULT_ASCENDC_ENV. Lets subprocess-based tests (the only callers
    where Python-level monkeypatches don't carry across the fork boundary)
    point load_env at a tmp .ascendc_env without depending on the real
    workspace env's contents. No effect on default-arg callers when the
    var is unset.
    """
    if env_file is None:
        override = os.environ.get("ASCENDC_ENV_PATH")
        env_file = Path(override) if override else DEFAULT_ASCENDC_ENV
    if not env_file.exists():
        raise FileNotFoundError(f".ascendc_env not found at {env_file}")
    kv = _parse_env_kv(env_file)
    target, source_arch, archive_project, base_generation = _resolve_env_identity(kv)
    backend = resolve_backend_from_env(kv.get("BACKEND", "ascendc"), None)

    targets = _parse_generation_blocks(kv)
    _apply_generic_key_fallback(kv, targets, base_generation)

    _sub_prefix_len = len("SUBAGENT_SETTINGS_")
    return AscendCEnv(
        target=target,
        benchmark_root=kv.get("BENCHMARK_ROOT", ""),
        local_benchmark=kv.get("LOCAL_BENCHMARK", ""),
        local_project=kv.get("LOCAL_PROJECT", ""),
        archive_project=archive_project,
        build_archive_enabled=kv.get("BUILD_ARCHIVE_ENABLED", "0") == "1",
        opgen_mode=kv.get("OPGEN_MODE", ""),
        port_a3_source=kv.get("PORT_A3_SOURCE", ""),
        port_a3_reference_source=kv.get("PORT_A3_REFERENCE_SOURCE", ""),
        backend=backend,
        subagent_settings={
            k[_sub_prefix_len:]: v
            for k, v in kv.items()
            if k.startswith("SUBAGENT_SETTINGS_")
        }
        or None,
        targets=targets,
        source_arch=source_arch,
    )


def resolve_backend_from_env(backend: str, env) -> str:
    """Validate and return the sole supported kernel-authoring backend."""
    if backend != "ascendc":
        raise ValueError("only the AscendC backend is supported")
    return "ascendc"


def _multirank_state_plugin(state_path: Path):
    """The multirank extension plugin when durable state flags multirank."""
    import json as _json

    try:
        if _json.loads(state_path.read_text()).get("multirank") is True:
            from plugins.multirank import get_plugin_instance

            return get_plugin_instance()
    except (OSError, ValueError):
        pass
    return None


def resolve_plugin_for_brief(
    env: "AscendCEnv",
    workspace: Optional[Path] = None,
    backend_override: Optional[str] = None,
):
    """Resolve a scoped plugin from persisted workspace state only.

    Multirank workspaces (port_a3_to_a5 + `multirank: true` in durable
    state) resolve to the multirank EXTENSION plugin so its pp/ko/layout
    brief-override hooks fire — the extension owns the complete probe and
    optimizer protocols for multi-rank kernels.
    """
    if backend_override not in (None, "ascendc"):
        raise ValueError("only the AscendC backend is supported")
    from plugins import detect_plugin  # avoid import-time cycle

    if workspace is not None and workspace.exists():
        state_path = workspace / ".opgen_state.json"
        if state_path.is_file():
            plugin = _multirank_state_plugin(state_path)
            if plugin is not None:
                return plugin
        return detect_plugin(workspace)
    return None


# ---------------------------------------------------------------------------
# Brief sections (templated)
# ---------------------------------------------------------------------------
def env_block(
    env: AscendCEnv,
    *,
    lane: int,
    op: str,
    workspace: Path,
    deploy_stage_dir: Optional[str] = None,
    build_batch_id: Optional[str] = None,
) -> str:
    """Lane / NPU / target / paths block. Same fields the LLM-orchestrator
    used to write at the top of every brief, but deterministic.
    """
    if deploy_stage_dir is None:
        # Stable per-spawn dir
        import time

        deploy_stage_dir = f"op_{_op_slug(op)}_lane{lane}_{int(time.time())}"
    if build_batch_id is None:
        build_batch_id = f"op_{_op_slug(op)}"

    a3_lines = ""
    if env.target.startswith("a3") or env.a3_host_home or env.a3_deploy_stage_host:
        if env.a3_host_home:
            a3_lines += f"\nA3_HOST_HOME: {env.a3_host_home}"
        if env.a3_host_backup:
            a3_lines += f"\nA3_HOST_BACKUP: {env.a3_host_backup}"
        if env.a3_deploy_stage_host:
            a3_lines += f"\nA3_DEPLOY_STAGE_HOST: {env.a3_deploy_stage_host}"
        if env.a3_deploy_stage_container:
            a3_lines += f"\nA3_DEPLOY_STAGE_CONTAINER: {env.a3_deploy_stage_container}"

    return f"""OP: {op}
WORKSPACE: {workspace}
TARGET: {env.target}
SOC_VERSION: {env.soc_version}
PLATFORM_SIMT: {"true" if env.target == "a5" else "false"}
ARCHIVE_PROJECT: {env.archive_project}
LANE: {lane} (NPU {lane} — A5 has 3 NPUs total IDs 0/1/2)
A5_HOST: {env.host} (user={env.user}, container={env.container}, CANN={env.cann_path})
BENCHMARK_ROOT: {env.benchmark_root}
LOCAL_BENCHMARK: {env.local_benchmark}
DEPLOY_STAGE_DIR: {deploy_stage_dir}
BUILD_BATCH_ID: {build_batch_id}
ASCENDC_WORKSPACE: {workspace}
BUILD_ARCHIVE_ENABLED: {1 if env.build_archive_enabled else 0}{a3_lines}"""


def rollback_context_block(workspace: Path) -> str:
    """P0abe (2026-05-07): inject prior-rollback signature into next brief.

    When a finalize-rollback gate fires (P0abd coverage / P0aax KB / P0aba
    audit / P0ee pass-count / P0ff persist-without-evidence), the rollback
    reason is recorded in `.rollback_history.jsonl`. Without injecting it
    into the next worker's brief, kw-N+1 reads the same generic Phase D
    text kw-N already ignored → emits same shape → infinite loop until
    TOTAL_SPAWN_CAP_PER_OP fires.

    This block surfaces the LAST rollback signature with concrete remediation
    so the next worker spawn knows EXACTLY what kw-N got rejected for.

    Returns empty string if no rollback history (cold start path).
    """
    history = workspace / ".rollback_history.jsonl"
    if not history.exists():
        return ""
    try:
        lines = [
            json.loads(ln)
            for ln in history.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
    except (json.JSONDecodeError, OSError):
        return ""
    if not lines:
        return ""
    last = lines[-1]
    sig = last.get("signature", "?")
    repeats = sum(1 for e in lines if e.get("signature") == sig)
    gate = last.get("gate", "<unknown>")
    rollback_state = last.get("rollback_state", "<unknown>")
    reason = last.get("reason", "")
    repeat_hint = ""
    if repeats >= 2:
        repeat_hint = (
            f"\n**THIS IS YOUR {repeats}TH ATTEMPT WITH SAME SIGNATURE**. "
            f"The next finalize attempt that produces the same gap will route "
            f"to `await_user_decision` (loop-break, P0abe) instead of looping. "
            f"You must produce a DIFFERENT shape this spawn — re-read the "
            f"gate's remediation hint below carefully and act on it."
        )
    body = f"""# CRITICAL: Previous spawn rejected by finalize gate (P0abe)

The orchestrator's finalize gate REJECTED the prior worker's handoff and rolled
the FSM back to {rollback_state}. You are the next spawn; the same workspace
is loaded but the prior gate REASON is below. Do NOT emit the same shape.

**Gate that fired**: `{gate}`
**Signature** (normalized): `{sig}`
**Reason given to prior worker**:

{reason}
{repeat_hint}

## Concrete remediation (act on this BEFORE Phase D verify)

The reason text above contains the exact remediation. Common cases:
- **P0abd_pass_a_coverage** — your prior `precision.pass_a.total` was less
  than the benchmark `<op>.json` JSONL line count. Either:
  (a) re-run verification iterating ALL benchmark cases (line count =
      `wc -l workspace/{{op}}/{{op}}.json` — use Path-A `get_input_groups()`
      that loads `<op>.json` and yields one input group per JSONL line);
  (b) populate `precision.pass_a.skipped_cases` as a list of
      `{{case_idx, reason}}` entries (one per skipped case) with explicit
      hardware/CANN-rejection reason.
  Bare reduction of `total` is silent coverage fraud — gate will reject again.

- **P0aax_kb_missing / kb_thin** — write/expand `knowledge_update.md` per
  Phase E required structure (Findings, KB-promotable patterns with scope
  tags, Cited KB, Anti-patterns).

- **P0aba_audit** — `audit_self_critic_post_worker.md` /
  `.delegation_scan_passed` / explicit Pass-B + perf re-measure status
  missing. Orchestrator produces audit doc + scan automatically; ensure your
  verification.json sets `precision.pass_b.status` and
  `performance.independent_re_measure` to concrete values (or N/A with
  reason).

- **P0ee_pass_count** — claimed `precision.status=PASS` but
  `pass_a.tier1_pass < pass_a.total`. Either reconcile the counts or change
  status to PARTIAL_PERSIST + emit Tier-2 evidence per OL-109.

If the gate's reason text doesn't match the patterns above, treat the
verbatim reason as your authoritative remediation hint.
"""
    return body


def _no_edge_cases(workspace: Path) -> bool:
    """Check if --no-edge-cases flag is active for this op."""
    return (workspace / ".no_edge_cases").exists()


def hard_floors_block(workspace: Path) -> str:
    """Read current verification.json, emit "preserve these floors" block.

    For cold-start ops (no verification.json), emits the goal floor instead.
    When .no_edge_cases marker exists, Pass B is marked N/A.
    """
    no_ec = _no_edge_cases(workspace)
    pass_b_line = (
        "- Pass B: N/A (edge cases disabled)"
        if no_ec
        else "- Pass B (edge_dataset): bit-exact vs CPU truth"
    )

    vj_path = workspace / "verification.json"
    if not vj_path.exists():
        return f"""# Hard gate floors (cold start — no prior baseline)

GOAL:
- Pass A: 50/50 OVERALL_T1 (or OVERALL_T2 with documented evidence per OL-109)
{pass_b_line}
- Det: 50/50 (DET_POLICY=required satisfied)
- Perf: ≥ 0.6× CANN ratio (V3.8.4 escalation rule)"""

    try:
        vj = json.loads(vj_path.read_text())
    except Exception:
        return "# Hard floors: verification.json malformed; cold-start defaults apply."

    prec = vj.get("precision", {}) or {}
    perf = vj.get("performance", {}) or {}
    pa = prec.get("pass_a", {}) or {}
    pb = prec.get("pass_b", {}) or {}
    det = vj.get("determinism", {}) or {}

    ratio = (
        perf.get("ratio")
        or perf.get("ratio_mean")
        or perf.get("overall_speedup")
        or perf.get("sum_ratio")
        or perf.get("ratio_median")
        or perf.get("median_ratio")
    )

    pa_pass = pa.get("tier1_pass", pa.get("n_pass", "?"))
    pa_total = pa.get("total", pa.get("n_total", "?"))
    if no_ec:
        pb_pass = "N/A"
        pb_total = "N/A"
        pb_status = "SKIPPED"
    else:
        pb_pass = pb.get("tier1_pass", pb.get("n_pass", "?"))
        pb_total = pb.get("total", pb.get("n_total", "?"))
        pb_status = pb.get("status", "?")
    det_id = det.get("n_identical_cases", det.get("n_identical", "?"))
    det_total = det.get("n_cases_checked", det.get("n_total", "?"))

    return f"""# Hard gate floors (DO NOT REGRESS — preserve byte-identical or beat)

- Pass A: {pa_pass}/{pa_total} {pa.get("status", "?")} (kw baseline preserved)
- Pass B: {pb_pass}/{pb_total} {pb_status}
- Det: {det_id}/{det_total} policy_satisfied={det.get("policy_satisfied", "?")}
- Perf: ratio={ratio} (V3.8.4: < 0.6× → ko escalation)

Top-level precision.status: {prec.get("status", "?")} (V3.8.3 fallback applies if absent)"""


def env_quirks_block(target: str) -> str:
    """P0aas (2026-05-07): per-TARGET infra-quirks preamble for kw/ko/pp/ar briefs.

    Reads `src/scripts/env_quirks_<target>.json` (DS-shipped, msg
    DISCORD_ID_REDACTED). Returns the file's `preamble_text` formatted as a
    brief section, so the worker frontloads target-environment-specific
    infrastructure quirks instead of rediscovering them each spawn (DS
    finding 2026-05-07: workers spent 70%+ wall-clock on infra
    rediscovery — sandbox/LOCAL_TASK/SSH-permission patterns).

    Empty string when no JSON exists for the target — the function is
    a no-op for targets without a quirks catalog (e.g. `a5` currently).
    """
    if not target:
        return ""
    # Resolve repo root from this file's location: briefs/ → orchestrator/ → scripts/ → root
    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    # File-naming convention: env_quirks_<target>.json with target normalized to
    # underscores (e.g. TARGET=a3-ds → env_quirks_a3_ds.json). Try both forms.
    target_norm = target.replace("-", "_")
    quirks_file = repo_root / "src" / "scripts" / f"env_quirks_{target_norm}.json"
    if not quirks_file.exists():
        # Fall back to literal target name (legacy)
        quirks_file = repo_root / "src" / "scripts" / f"env_quirks_{target}.json"
        if not quirks_file.exists():
            return ""
    try:
        data = json.loads(quirks_file.read_text())
    except (json.JSONDecodeError, OSError):
        return ""
    preamble = data.get("preamble_text", "").strip()
    if not preamble:
        return ""
    quirks = data.get("quirks", [])
    quirks_summary = ""
    if quirks:
        lines = []
        for q in quirks:
            cat = q.get("category", "?")
            rule = q.get("rule", "").strip()
            if rule:
                lines.append(f"  - [{cat}] {rule}")
                # Surface the most actionable workaround field if present
                wa = (
                    q.get("workaround")
                    or q.get("export_cmd")
                    or q.get("wrapper_usage")
                    or ""
                )
                if wa:
                    lines.append(f"    → {wa}")
        if lines:
            quirks_summary = "\n\n## Quirks (full catalog)\n" + "\n".join(lines)
    return f"""# ENV QUIRKS — {target}

{preamble}{quirks_summary}

(See `src/scripts/env_quirks_{target}.json` for the canonical structured catalog.)"""


# ---------------------------------------------------------------------------
# NODE-21 Phase C (2026-05-28): tag-aware KB injection for brief construction.
# ---------------------------------------------------------------------------


# Forced-architecture markers in op_classification.json. The architecture
# (SIMT / SIMD) is FIXED at classification time and is carried through
# forced-SIMT classification before `orch --port`); kw must HONOR it and
# implement only — it must NOT run the SIMT_VS_SIMD decision tree itself nor
# override the forced choice during Phase A authoring. Architecture-change is
# a ko-stage (optimizer) decision, AFTER precision passes, for performance.
#
# Lives here (the lower-level module) — NOT in kw_brief — because both
# `kb_manifest_block` (this module) and `kw_brief._forced_architecture_block`
# need it. Defining it in kw_brief and importing it back here would form a
# circular import (_common↔kw_brief), which caused an order-dependent
# ImportError under combined pytest collection (review 2026-06-16). The
# dependency edge is one-way: kw_brief → _common.
#
# Marker robustness for pre-injected classification:
#   1. explicit `force_simt: true` / `force_simd: true` boolean key (preferred)
#   2. explicit `forced_arch: "SIMT" | "SIMD"` string key
#   3. forced-arch convention: a bare "SIMT" / "SIMD" tag in op_class_tags
#      (the merge preserves an explicit "SIMT" classification tag)


def fixed_layout_block() -> str:
    """PB-33 (2026-05-14): canonical complete-NPU-op layout contract.

    Every agent that produces or modifies op output (kw / ko / fo / probe-fix
    iteration / researcher-directive-emit) MUST conform to this layout.
    finalize_pipeline._check_port_a3_op_host_completeness() enforces; agents
    that ship incomplete op_host/ get ROLLBACK.

    This is the SAME layout for the two scoped modes (port_a3_to_a5 and
    backward) — the input source differs but
    the OUTPUT shape is invariant. A complete AscendC NPU op IS the full
    PR4778 mirror. Patches and snippets are review-aid, not ship artifacts.
    """
    return """# FIXED OUTPUT LAYOUT CONTRACT (PB-33, 2026-05-14)

Every produced AscendC op MUST ship a COMPLETE PR4778 mirror in
`workspace/{op}/`. Patches alone are insufficient — they lose context once
detached from the master they were generated against, and downstream
consumers (CANN team, reviewers, finalize pipeline) cannot apply them
without the original anchor.

Required structure (workspace-relative paths):

  op_host/
    <op>_def.cpp           # MANDATORY — complete file, NOT patch
    <op>_tiling.cpp        # MANDATORY — host tiling implementation
    <op>_tiling.h          # MANDATORY — host tiling header
    CMakeLists.txt         # MANDATORY — build registration
    config/
      ascend950/
        <op>_binary.json   # MANDATORY — A5 binary registration
        <op>_simplified_key.ini  # MANDATORY — A5 simplified-key map
    # Optional (only if upstream has them):
    <op>_infershape.cpp    # if op has bespoke shape-inference
    op_api/
      <op>.cpp             # if op needs aclnn L0 wrapper
      <op>.h
    # Optional (review-aid, NOT ship artifact):
    <op>_def.cpp.patch     # diff vs upstream — for review trail only

  op_kernel/
    arch35/
      <op>.h               # MANDATORY — A5 kernel implementation
      <op>.cpp             # if upstream has cpp dispatcher in arch35/
      <sibling_variants>.h # if multi-variant (per OL-153 L2+L3 hybrid)
    <op>_apt.cpp           # MANDATORY — A5 entry-point wrapper

Hard rules:
- For port_a3_to_a5 mode: independently author the required op_host files
  from the detector-admitted, top-level arch22 host interfaces and repository
  templates, plus the config/ascend950 additions. Never recursively mirror
  `<port_source>/op_host/`; target subdirectories are not inputs.
  finalize_pipeline checks count ≥ 3 non-config / non-patch files.
- For backward mode: the same layout is the target. If the forward spec doesn't
  provide op_host scaffolding, GENERATE the minimum required set:
  <op>_def.cpp + <op>_tiling.{cpp,h} + CMakeLists.txt + binary.json +
  simplified_key.ini per PR4778 template.
- Patches CAN be produced as review-aids in addition to complete files,
  but NEVER as a substitute. finalize_pipeline.OP_HOST_COMPLETENESS gate
  rolls back ops that ship patches instead of complete files.
- Cross-agent consistency: kw writes the initial layout. ko / fo / probe
  iter editors MUST preserve every file kw produced; deletions of any
  layout file is REJECT.
"""


def schema_contract_block() -> str:
    """Canonical schema contract — every brief should remind the worker."""
    return """# OUTPUT SCHEMA CONTRACT (V3.8.x canonical — DO NOT improvise)

verification.json:
- top-level `precision.status` ∈ {PASS, PASS_WITHIN_TOLERANCE, PARTIAL, FAIL}
  RECOMMENDED. If absent, V3.8.3 fallback derives it: pass_a ∈ {PASS, N/A} +
  pass_b == PASS → PASS (Path A / OL-68 case A pattern)
- per-pass: `precision.pass_a.{status, tier1_pass, total}` +
  `precision.pass_b.{status, tier1_pass, total}` (legacy `n_pass`/`n_total`
  also accepted via fallback but `tier1_pass`/`total` is canonical)
- top-level `performance.ratio` (NOT `overall_speedup` — schema_norm aliases
  but canonical is `ratio`)
- `determinism.{policy_satisfied, n_identical_cases, n_cases_checked}`
  (legacy `n_identical`/`n_total` also accepted via fallback)

state_transitions.jsonl is OWNED BY THE ORCHESTRATOR — you do NOT write to it.
The orchestrator records your handoff line + computes the routing transition.
If you OBSERVE entries (e.g. read prior workspace state), the canonical schema is:
- keys: `from_state`, `to_state`, `handoff`, `matched_transition_index`,
  `rationale`, `iter_counts_snapshot`, `ts`
- valid `to_state` values: await_worker / await_optimizer / await_probe /
  await_fused_optimizer / await_researcher / await_det_analyzer / finalize / abort

Your handoff line in stdout (and in PROGRESS.md tail) MUST be one of the
EXIT HANDOFF OPTIONS listed in your agent's brief. Do NOT improvise free-form
state names like `done` / `partial_persist` / `await_orchestrator` — those
are not YAML states; the orchestrator's schema_norm will REJECT or DROP them."""


def self_introspection_block() -> str:
    """P0qq (2026-05-06): IN-CONTEXT self-introspection checkpoint.

    User correction (2026-05-06): the previous aog-self-critic skill was
    spawned as a SEPARATE process — fresh model, no access to the agent's
    reasoning trace. That's "post-hoc audit" not introspection. Real
    self-critic = same model in same context reflecting on its own work
    BEFORE emitting decisions.

    This block goes into every agent brief. Agents must execute it AS
    PART OF their own reasoning, not as a separate spawn. Output goes
    to PROGRESS.md `## Self-introspection` section. Schema validator
    rejects `done` / `PARTIAL_PERSIST` handoffs that lack this section.
    """
    return """# SELF-INTROSPECTION CHECKPOINT (mandatory before terminal handoff)

Before emitting `→ orchestrator: done` OR `→ orchestrator: PARTIAL_PERSIST`,
you MUST write a `## Self-introspection` section in PROGRESS.md tail
with at minimum these subsections:

```
[[H2]] Self-introspection ({{your-slug}})

### Pressure modes I felt
List which P1-P8 from ANTI_PRESSURE_PROTOCOLS.md you experienced during
this spawn. Be honest — naming them in-context is the actual mechanism;
hiding them is P5 + P7 in costume. Format:
  - **Px (Name)**: <one sentence on when/where it pulled at you>

### Decisions I almost rationalized
For each pressure, name a decision you almost made under it that would
have violated the rule. Format:
  - Almost: <bad action>. Rule that stopped me: <Px counter-instruction>

### Verifications I might have skipped
List concrete steps I ran that the urge said to skip:
  - <verification step>: ran (or: skipped because <legitimate reason>)

### Confidence calibration
Rate my own confidence in this handoff being correct, on:
  - precision: HIGH | MEDIUM | LOW (cite Tier-2 evidence file or
    reasoning if MEDIUM/LOW)
  - perf: HIGH | MEDIUM | LOW
  - architectural fit: HIGH | MEDIUM | LOW
LOW on any axis without a probe / researcher / KB cite is a smell —
state it explicitly so reviewer sees the gap.
```

This is NOT a separate spawn. NOT a tool call. Write it in the SAME
context where you've been reasoning about this op. It's reflection on
your own trace.

If you skip this section before a terminal handoff, schema_norm
rejects the handoff (P0qq) and routes you back to await_<state>.
""".replace("[[H2]]", "##")


def safety_block(env: AscendCEnv) -> str:
    return """# SAFETY (CLAUDE.md rules)

- NO torch_npu / aclnn delegation in kernel — pure AscendC primitives only
- NO CANN op_impl source reading (source-isolation rule)
- After each iter: independent perf re-measure per CLAUDE.md "Independent
  Performance Verification" rule
- Build via deploy_to_npu_lane.sh (sets BUILD_BATCH_ID)
- Lane release best-effort at exit (wrap in try/except; if lane_release.py
  not present, that's OK — orchestrator handles release on its side)
- NPU IDs available: 0, 1, 2 only (lane 3 = phantom; A5 has 3 real NPUs).
  If your script tries to use ASCEND_VISIBLE_DEVICES≥3, that's a bug."""


def _op_slug(op: str) -> str:
    """Convert workspace dir name to G7-compliant slug.

    G7 regex: ^[a-z][a-z0-9_]*-(kw|pp|ko|fo|ar|da|bs|td|tt|cl)-\\d+\\b
    The slug is the leading portion (before -kw-1 etc.).
    Strip numeric prefix; lowercase; preserve underscores.
    """
    s = op.lower()
    # Strip leading "<digits>_"
    s = re.sub(r"^\d+_", "", s)
    # Replace remaining hyphens with underscore (G7 allows _ but not -)
    s = s.replace("-", "_")
    # Drop chars not in [a-z0-9_]
    s = re.sub(r"[^a-z0-9_]", "", s)
    # Must start with letter
    if not s or not s[0].isalpha():
        s = "op_" + s
    return s


def g7_slug(op: str, agent_type: str, spawn_index: int) -> str:
    """Build G7-compliant agent name slug: {op_slug}-{code}-{N}.

    Keep the codes in lockstep with `workflow_critic._AGENT_NAME_PATTERN` so
    post-hoc audits don't reject spawns.
    """
    code = {
        "aog-kernel-worker": "kw",
        "aog-precision-probe": "pp",
        "aog-kernel-optimizer": "ko",
        "aog-fused-optimizer": "fo",
        "aog-researcher": "ar",
        "aog-determinism-analyzer": "da",
        "aog-cann-learner": "cl",
    }.get(agent_type)
    if code is None:
        raise ValueError(f"unknown agent_type for G7 slug: {agent_type}")
    return f"{_op_slug(op)}-{code}-{spawn_index}"
