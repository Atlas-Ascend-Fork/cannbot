# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""310B real-board runtime acceptance (it level).

Runs the O0 target-toolchain probe chain against the REAL 310B board named
by the it-gate environment (CANNBOT_310B_IT_HOST), all ON the board over
SSH: bisheng presence + sha256 fingerprint; arch-token ACCEPT dumping the
``__DAV_M300__`` identity macro; arch-token REJECT control (dav-NOSUCH
refused); npu-smi SoC identity in the configured family.

Gated OFF by default (no hardware in CI): set CANNBOT_310B_IT=1 plus the
board coordinates to run.  The password travels ONLY through the
environment (CANNBOT_310B_IT_PASSWORD) — never a file, never printed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

import _reorg_paths  # reorg ut/it/ct: stable data-path anchors

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1]))
import phase_o5_runner  # noqa: E402,F401  (pre-existing import-cycle order)
from a5_target_transport import _Target  # noqa: E402
from npubench.npubench_target_toolchain import probe_310b_target_toolchain  # noqa: E402

_HOST = os.environ.get("CANNBOT_310B_IT_HOST", "")
_USER = os.environ.get("CANNBOT_310B_IT_USER", "root")
_PASSWORD = os.environ.get("CANNBOT_310B_IT_PASSWORD", "")
_CANN = os.environ.get(
    "CANNBOT_310B_IT_CANN_PATH", "/usr/local/Ascend/ascend-toolkit/latest"
)
_SOC = os.environ.get("CANNBOT_310B_IT_SOC_VERSION", "Ascend310B1")

pytestmark = pytest.mark.skipif(
    os.environ.get("CANNBOT_310B_IT") != "1" or not _PASSWORD,
    reason=(
        "real-board acceptance: set CANNBOT_310B_IT=1 and "
        "CANNBOT_310B_IT_PASSWORD (plus optional _HOST/_USER/_CANN_PATH/"
        "_SOC_VERSION overrides) to run against the 310B board"
    ),
)


def _board_target() -> _Target:
    return _Target(
        name="ASCEND310B",
        host=_HOST,
        user=_USER,
        password=_PASSWORD,
        container="local",
        cann_path=_CANN,
        benchmark_root="/root/AscendOpGenAgent",
        host_mode=True,
        visible_device=0,
        ssh_options=(),
        env={"ASCEND310B_SOC_VERSION": _SOC},
    )


def test_probe_chain_on_real_board() -> None:
    report = probe_310b_target_toolchain(_board_target())
    # Every probe ran ON the board.
    assert report["probe"] == "ssh"
    assert report["host"] == _HOST
    # Compiler fingerprint: 64-hex sha256 for the O0 registration baseline.
    bisheng_sha = report["bisheng_sha256"]
    assert len(bisheng_sha) == 64
    assert all(c in "0123456789abcdef" for c in bisheng_sha)
    # Arch-token accept/reject pair, identity by the __DAV_ macro.
    assert report["arch_token_accept"]["token"] == "dav-m300"
    assert report["arch_token_accept"]["identity_macro"] == "__DAV_M300__"
    assert report["arch_token_reject_control"] == {"token": "dav-NOSUCH", "rejected": True}
    # SoC identity on the same machine, in the configured family.
    assert report["chip_seen"] is True
    assert report["soc_family"] is not None
    assert report["configured_soc"] == _SOC
