# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""DEBT-094 phase 1 Layer 1 — protocol conformance.

Every registered plugin MUST satisfy PluginProtocol: have all required
attributes + methods with correct signatures + runtime-isinstance
agreement.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import get_type_hints  # noqa: F401

import pytest

_HERE = Path(__file__).resolve()
_ORCH_DIR = _HERE.parent.parent.parent  # src/scripts/orchestrator/
if str(_ORCH_DIR) not in sys.path:
    sys.path.insert(0, str(_ORCH_DIR))

from plugins import (  # noqa: E402
    all_plugins,
    BasePlugin,
    PluginProtocol,
    get_plugin,
)


REQUIRED_METHODS = (
    "detect",
    "verify_files",
    "forbidden_patterns",
    "scanner_category",
    "check_binary_provenance",
    "check_verify_path_provenance",
    "archive_layout_mapping",
    "archive_project_subdir",
    "resolve_archive_target",
    "check_op_host_completeness",  # DEBT-094 phase 3 (2026-05-18) — PB-33 owned by plugin
    "extra_finalize_checks",  # P87 — option-A extension path
    "kb_subdirs",  # P88 phase 1 — KB reorg foundation
    "kw_brief_phase_a",
    "kw_brief_phase_d",
    "finalize_perf_capture",  # plugin-owned perf capture override (None = engine default)
)

REQUIRED_ATTRS = ("name", "cli_flag")


def test_registry_discovers_required_plugins():
    """The customer registry is an exact allowlist, not an extensible scan.

    `multirank` is an extension plugin (detect() always False); it never
    claims a workspace and is resolved lazily by PortA3Plugin.
    """
    plugins = all_plugins()
    names = [p.name for p in plugins]
    assert names == ["backward", "multirank", "port_a3_to_a5"]


@pytest.mark.parametrize("plugin", all_plugins(), ids=lambda p: p.name)
def test_plugin_has_required_attrs(plugin):
    for attr in REQUIRED_ATTRS:
        assert hasattr(plugin, attr), f"{plugin.name}: missing attribute {attr!r}"
    assert plugin.name, f"plugin name must be truthy, got {plugin.name!r}"


@pytest.mark.parametrize("plugin", all_plugins(), ids=lambda p: p.name)
def test_plugin_has_required_methods(plugin):
    for method_name in REQUIRED_METHODS:
        assert hasattr(plugin, method_name), (
            f"{plugin.name}: missing method {method_name!r}"
        )
        m = getattr(plugin, method_name)
        assert callable(m), f"{plugin.name}.{method_name} is not callable"


@pytest.mark.parametrize("plugin", all_plugins(), ids=lambda p: p.name)
def test_plugin_satisfies_protocol_isinstance(plugin):
    """Runtime-checkable Protocol — every plugin should pass isinstance."""
    assert isinstance(plugin, PluginProtocol), (
        f"{plugin.name} fails isinstance(PluginProtocol) — missing methods?"
    )


@pytest.mark.parametrize("plugin", all_plugins(), ids=lambda p: p.name)
def test_plugin_detect_signature(plugin):
    """detect() must take exactly 1 positional arg (workspace: Path)."""
    sig = inspect.signature(plugin.detect)
    params = []
    ignored_kinds = (
        inspect.Parameter.VAR_POSITIONAL,
        inspect.Parameter.VAR_KEYWORD,
    )
    for parameter in sig.parameters.values():
        if parameter.kind not in ignored_kinds:
            params.append(parameter)
    assert len(params) == 1, (
        f"{plugin.name}.detect signature {sig} should take 1 arg, got {len(params)}"
    )


def test_plugin_names_are_unique():
    """No two plugins may share a name (registry already enforces, but
    pin via test in case discovery order changes).
    """
    plugins = all_plugins()
    names = [p.name for p in plugins]
    assert len(set(names)) == len(names), f"duplicate plugin names: {names}"


# ── finalize_perf_capture hook (plugin-owned perf capture override) ────


def test_protocol_declares_finalize_perf_capture():
    """The runtime_checkable protocol surface itself declares the hook, so
    isinstance(PluginProtocol) now requires it on every conforming plugin.
    """
    assert hasattr(PluginProtocol, "finalize_perf_capture")
    assert callable(PluginProtocol.finalize_perf_capture)


def test_finalize_perf_capture_default_returns_none(tmp_path):
    """BasePlugin default = None, the "not overridden" sentinel: the engine

    keeps its default single-process perf capture path.
    """
    assert BasePlugin().finalize_perf_capture(tmp_path, "some_op") is None


# multirank intentionally OVERRIDES the hook (multi-rank joint perf
# measurement is the protocol's documented override use case); its override
# is covered by plugins/multirank/tests/test_multirank_plugin.py. port_a3_to_a5
# also overrides it as a CONDITIONAL delegation (multirank workspaces → the
# extension's multi-NPU campaign; single-card → super()/engine default) —
# pinned by plugins/port_a3/tests/test_port_a3_plugin.py. This test pins the
# plugin that must keep the engine-default capture path unconditionally.
@pytest.mark.parametrize("plugin_name", ["backward"])
def test_finalize_perf_capture_registered_plugins_not_overridden(plugin_name):
    """backward does not override the hook — it inherits BasePlugin's
    implementation, so its finalize perf behavior (engine default path,
    gated by should_run_phase_o5_perf_capture) is unchanged.
    """
    plugin = get_plugin(plugin_name)
    assert plugin is not None, f"{plugin_name!r} not registered"
    assert type(plugin).finalize_perf_capture is BasePlugin.finalize_perf_capture, (
        f"{plugin.name} unexpectedly overrides finalize_perf_capture"
    )
    assert plugin.finalize_perf_capture(Path("/nonexistent"), "some_op") is None


@pytest.mark.parametrize("plugin", all_plugins(), ids=lambda p: p.name)
def test_finalize_perf_capture_signature(plugin):
    """finalize_perf_capture must take exactly 2 positional args (workspace,

    op) — the core call site invokes `plugin.finalize_perf_capture(workspace,
    op)` positionally.
    """
    sig = inspect.signature(plugin.finalize_perf_capture)
    params = []
    ignored_kinds = (
        inspect.Parameter.VAR_POSITIONAL,
        inspect.Parameter.VAR_KEYWORD,
    )
    for parameter in sig.parameters.values():
        if parameter.kind not in ignored_kinds:
            params.append(parameter)
    assert len(params) == 2, (
        f"{plugin.name}.finalize_perf_capture signature {sig} should take "
        f"2 args (workspace, op), got {len(params)}"
    )


def test_finalize_perf_capture_override_satisfies_protocol(tmp_path):
    """An overriding plugin returns its own dict (used verbatim as the

    performance fragment) and still passes the runtime_checkable check.
    """

    class PerfOverrideProbePlugin(BasePlugin):
        name = "perf_override_probe"
        cli_flag = None

        def finalize_perf_capture(self, workspace, op):
            return {"status": "PAUSE_RESOURCE", "reason": "probe"}

    plug = PerfOverrideProbePlugin()
    assert isinstance(plug, PluginProtocol)
    assert plug.finalize_perf_capture(tmp_path, "some_op") == {
        "status": "PAUSE_RESOURCE",
        "reason": "probe",
    }
