# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""310B port-destination behavior pins.

310B is a DOWN-port destination (arch22 → arch30 / dav-m300), mirroring
test_port_destinations_310p.py: keep the silent-wrong-chip class (DEBT-336
family: digit-led ``310B_*`` keys → wrong-chip ``A5_*`` fallback) and the
one-letter 310B/310P family split from regressing.

  1. env resolution never falls back to A5_*; digit-led keys rejected
  2. SoC gates 310b-aware and 310P-mutually-exclusive
  3. target_arch destination-derived (arch30, never a literal arch35/arch20)
  4. KB spec page / platform id mapped independently of 310p and a5
  5. archive namespace a3_to_310b_port
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from _port_dst_env import (  # shared import-time header (fixup + seams live there)
    TARGET_HW_SPEC_MAP, cap, load_env, orch, target_env_prefix,
    _a5_build_cann_path, _a5_build_container, _a5_build_host,
    _inject_migration_metadata, _normalise_target, _port_destination_prefix,
    _seed_port_workspace,
)


def test_target_env_prefix_310b_spellings():
    assert target_env_prefix("310b") == "ASCEND310B"
    assert target_env_prefix("310B") == "ASCEND310B"
    assert target_env_prefix("310b-ds") == "ASCEND310B"


def test_port_destination_prefix_predicate():
    assert _port_destination_prefix("ASCEND310B")
    assert _port_destination_prefix("ASCEND310P")
    assert _port_destination_prefix("A5")
    assert not _port_destination_prefix("A3")
    assert not _port_destination_prefix("A2")


# ---------------------------------------------------------------------------
# 1. destination env resolution — never an A5_* fallback for 310b
# ---------------------------------------------------------------------------
def test_normalise_target_310b_prefix():
    assert _normalise_target({"TARGET": "310b"}) == (
        "310b", "ASCEND310B",
    )
    assert _normalise_target({"TARGET": "310B-DS"}) == (
        "310b", "ASCEND310B",
    )


def test_port_310b_reads_own_keys_never_a5(tmp_path):
    ws = _seed_port_workspace(tmp_path)
    env = {
        "A5_HOST": "a5-host",
        "A5_CONTAINER": "npu_dev3",
        "A5_CANN_PATH": "/a5/cann",
        "ASCEND310B_HOST": "310b-board",
        "ASCEND310B_CONTAINER": "local",
        "ASCEND310B_CANN_PATH": "/usr/local/Ascend/cann-8.5.1",
    }
    assert _a5_build_host(env, ws, "ASCEND310B") == "310b-board"
    assert _a5_build_container(env, ws, "ASCEND310B") == "local"
    assert (
        _a5_build_cann_path(env, ws, "ASCEND310B")
        == "/usr/local/Ascend/cann-8.5.1"
    )

    env_file = tmp_path / "env_310b_remote"
    env_file.write_text(
        "TARGET=310b\n"
        "A5_HOST=a5-host\n"
        "A5_CONTAINER=npu_dev3\n"
        "ASCEND310B_HOST=310b-board\n"
        "ASCEND310B_EXEC=remote\n"
        "ASCEND310B_CONTAINER=local\n"
    )
    loaded = load_env(env_file)
    assert loaded.exec_mode() == "remote"
    assert loaded.host == "310b-board"
    assert loaded.container == ""


def test_port_310b_unconfigured_fails_loud_not_a5(tmp_path):
    """A 310b destination with no ASCEND310B_* keys must resolve EMPTY.

    An A5_* fallback here builds/verifies on the wrong chip.
    """
    ws = _seed_port_workspace(tmp_path)
    env = {
        "A5_HOST": "a5-host",
        "A5_CONTAINER": "npu_dev3",
        "A5_CANN_PATH": "/a5/cann",
    }
    assert _a5_build_host(env, ws, "ASCEND310B") == ""
    assert _a5_build_container(env, ws, "ASCEND310B") == ""
    assert _a5_build_cann_path(env, ws, "ASCEND310B") == ""

    env_file = tmp_path / "env_unconfigured_310b"
    env_file.write_text(
        "TARGET=310b\n"
        "A5_HOST=a5-host\n"
        "A5_CONTAINER=npu_dev3\n"
        "A5_CANN_PATH=/a5/cann\n"
        "A5_SOC_VERSION=Ascend950PR\n"
    )
    loaded = load_env(env_file)
    assert loaded.host == ""
    assert loaded.container == ""
    assert loaded.cann_path == ""
    assert loaded.soc_version == ""


def test_legacy_digit_led_310b_keys_rejected_at_parse_time(tmp_path):
    """R1: a digit-led 310B_* key is silently unparseable — reject loud."""
    env_file = tmp_path / "env_bad_310b"
    env_file.write_text("TARGET=310b\nASCEND310B_HOST=h\n310B_HOST=h\n")
    with pytest.raises(ValueError, match="LEGACY_310B_ENV_KEYS"):
        load_env(env_file)


# ---------------------------------------------------------------------------
# enforce_port_a3_target — the guard and the resolvers must agree
# ---------------------------------------------------------------------------
def test_enforce_accepts_310b_destination():
    assert orch.enforce_port_a3_target("port_a3_to_a5", "310b") == ("310b", None)
    assert orch.enforce_port_a3_target("port_a3_to_a5", "310B") == ("310b", None)


# ---------------------------------------------------------------------------
# 2. SoC gates — 310B family, mutually exclusive with 310P
# ---------------------------------------------------------------------------
def test_soc_version_310b_reads_own_prefix():
    env = {"ASCEND310B_SOC_VERSION": "Ascend310B1", "SOC_VERSION": "Ascend910"}
    assert cap.soc_version_for_target(env, "310b") == "Ascend310B1"


def test_is_supported_310b_soc():
    for ok in ("Ascend310B", "Ascend310B1", "Ascend310B4", "ascend310b", "310B1", "ASCEND310B"):
        assert cap.is_supported_310b_soc(ok), ok
    # One-letter trap and undeclared SKUs are NOT supported 310B SoCs.
    for bad in ("Ascend310P3", "Ascend310B5", "Ascend310Bjunk", "Ascend910", "Ascend950PR", "310p", "", None):
        assert not cap.is_supported_310b_soc(bad), bad


def test_resolve_target_shell_rejects_undeclared_310b_soc(tmp_path):
    script = Path(orch.__file__).resolve().parents[1] / "resolve_target.sh"
    env_file = tmp_path / ".ascendc_env"
    for soc in ("Ascend310B1", "Ascend310B4", "Ascend310B5", "Ascend310Bjunk"):
        env_file.write_text(
            "TARGET=310b\n"
            "ASCEND310B_HOST=310b-board\n"
            "ASCEND310B_CONTAINER=local\n"
            "ASCEND310B_CANN_PATH=/opt/cann\n"
            f"ASCEND310B_SOC_VERSION={soc}\n"
        )
        result = subprocess.run(
            ["/bin/bash", str(script)],
            env={"ASCENDC_ENV_FILE": str(env_file), "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert (result.returncode == 0) == (soc in {"Ascend310B1", "Ascend310B4"}), (
            soc, result.stdout, result.stderr
        )


def test_is_limited_soc_target_aware_310b():
    # Anything outside the 310B family is limited — including 310P spellings.
    assert cap.is_limited_soc("Ascend310P3", "310b")
    assert cap.is_limited_soc("Ascend910", "310b")
    assert not cap.is_limited_soc("Ascend310B1", "310b")
    # And symmetrically on the 310p side.
    assert cap.is_limited_soc("Ascend310B1", "310p")
    assert not cap.is_limited_soc("Ascend310P3", "310p")


def test_limited_target_validation_error_310b():
    message = cap.limited_target_validation_error("Ascend310P3", "310b")
    assert ("310" "B_SOC_UNSUPPORTED_FOR_VALIDATION") in message
    assert "Ascend310P3" in message
    # The npu-smi-report guidance is part of the contract (module-SKU trap).
    assert "npu-smi" in message


def test_soc_product_family_keeps_310b_and_310p_distinct():
    assert cap.soc_product_family("Ascend310B1") == "ascend310b"
    assert cap.soc_product_family("310B1") == "ascend310b"
    assert cap.soc_product_family("Ascend310P3") == "ascend310p"
    assert cap.soc_product_family("Ascend950PR") == "ascend950"


# ---------------------------------------------------------------------------
# 3. destination-derived arch metadata (310b → arch30)
# ---------------------------------------------------------------------------
def test_arch_for_target_spellings_310b():
    assert cap.arch_for_target("310b") == "arch30"
    assert cap.arch_for_target("ASCEND310B") == "arch30"
    assert cap.arch_for_target("310B-DS") == "arch30"
    assert cap.arch_for_target("310p") == "arch20"
    assert cap.arch_for_target("a5") == "arch35"


def test_is_destination_target_name_310b():
    assert cap.is_destination_target_name("ASCEND310B")
    assert cap.is_destination_target_name("310b")
    assert not cap.is_destination_target_name("A3")


def _write_state(workspace: Path, **extra) -> None:
    payload = {
        "opgen_mode": "port_a3_to_a5",
        "source_arch": "arch22",
        "target_arch": "arch35",
        "source_arch_detection": {},
    }
    payload.update(extra)
    (workspace / ".opgen_state.json").write_text(json.dumps(payload))


def test_migration_block_310b_uses_arch30(tmp_path):
    _write_state(tmp_path, target="310b", target_arch="arch30")
    (tmp_path / "verification.json").write_text(
        json.dumps({"precision": {"status": "PASS"}})
    )
    _inject_migration_metadata(tmp_path)
    migration = json.loads((tmp_path / "verification.json").read_text())[
        "migration"
    ]
    assert migration["source_arch"] == "arch22"
    assert migration["target_arch"] == "arch30"


def test_migration_block_stale_arches_not_injected_for_310b(tmp_path):
    """A 310b destination with stale arch35/arch20 metadata injects NOTHING."""
    for stale in ("arch35", "arch20"):
        _write_state(tmp_path, target="310b", target_arch=stale)
        (tmp_path / "verification.json").write_text(json.dumps({}))
        _inject_migration_metadata(tmp_path)
        assert "migration" not in json.loads(
            (tmp_path / "verification.json").read_text()
        ), stale


# ---------------------------------------------------------------------------
# 4. KB spec page / platform id mapped independently of 310p and a5
# ---------------------------------------------------------------------------
def test_kb_spec_page_mapped_to_external_canonical_path():
    assert (
        TARGET_HW_SPEC_MAP.get("310b")
        == "knowledge/common/platforms/concepts/target_ascend310b.md"
    )
    # Never shared with the 310p entry, never a silent a5-card fallback.
    assert TARGET_HW_SPEC_MAP["310b"] != TARGET_HW_SPEC_MAP["310p"]
    assert TARGET_HW_SPEC_MAP["310b"] != TARGET_HW_SPEC_MAP["a5"]


def test_kb_platform_id_mapped_310b_and_310p():
    from briefs.external_kb import platforms_for_target

    assert platforms_for_target("310b") == ["310b"]
    assert platforms_for_target("310p") == ["310p"]
    assert platforms_for_target("a5") == ["950", "a3"]


# ---------------------------------------------------------------------------
# 5. archive namespace
# ---------------------------------------------------------------------------
def test_archive_project_destination_scoped(tmp_path):
    """310b ports archive under their own project, not the a5/310p ones."""
    env_file = tmp_path / "env_310b"
    env_file.write_text(
        "\n".join(
            [
                "TARGET=310b",
                "OPGEN_MODE=port_a3_to_a5",
                "ASCEND310B_HOST=310b-board",
                "ASCEND310B_USER=root",
                "ASCEND310B_CONTAINER=local",
                "ASCEND310B_CANN_PATH=/usr/local/Ascend/cann-8.5.1",
                "ASCEND310B_SOC_VERSION=Ascend310B1",
            ]
        )
        + "\n"
    )
    env = load_env(env_file)
    assert env.archive_project == "a3_to_310b_port"


def test_archive_project_claim_yields_a5_namespace_only_for_a5():
    """The plugin claims the a5 archive project ONLY for a5 destinations."""
    from plugins import all_plugins

    port_plugin = next(p for p in all_plugins() if p.name == "port_a3_to_a5")

    class _Env:
        def __init__(self, target):
            self.target = target

    assert port_plugin.archive_project_claim(_Env("a5")) == "a3_to_a5_port"
    assert port_plugin.archive_project_claim(_Env("310b")) is None
    assert port_plugin.archive_project_claim(_Env("310B-DS")) is None


# ---------------------------------------------------------------------------
# capability constants (plan L2.7)
# ---------------------------------------------------------------------------
def test_arch_token_constants_match_toolchain_module():
    """build_ascendc.py and npubench_target_toolchain.py must agree on the
    310B arch token (the only compiler entry — a drift breaks the build).
    """
    patches_dir = Path(orch.__file__).resolve().parents[1] / "patches"
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_ascendc_310b_pin", patches_dir / "build_ascendc.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.ASCENDC_ARCH_TOKEN_BY_TARGET["310b"] == "dav-m300"

    from npubench.npubench_target_toolchain import AICORE_ARCH_BY_TARGET

    assert AICORE_ARCH_BY_TARGET["310b"] == "dav-m300"
