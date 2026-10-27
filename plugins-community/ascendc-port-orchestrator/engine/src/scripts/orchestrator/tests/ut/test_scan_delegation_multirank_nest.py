# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""multirank NEST layout support in scan_delegation_cheating.

The multirank layout keeps the C++ project under workspace/<op>/prj-<op>/
(op_host/ + op_kernel/ + .build/autogen/), NOT at the workspace root. Before
the nest fix the scanner resolved the plugin-declared dirs at the root only:
the scan read nothing and the DEBT-211 coverage-gap fired on every multirank op —
a layout-level mismatch no kernel edit could clear, so the delegation marker
could never be produced and finalize was structurally blocked (moe_fused_a8w8).

Covers:
  - declared dirs resolve under prj-<op>/ (scan + coverage-gap both)
  - the op's OWN aclnn surface (opbuild-autogen symbols + the public export
    family derived from header stems) is suppressed — the op_host/wrapper
    glue every custom op ships calls its own aclnn, which is NOT delegation
  - a DIFFERENT op's aclnn (or CANN's public built-in when no autogen tree
    exists) still flags
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPTS_DIR = _HERE.parent.parent.parent  # src/scripts/
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import scan_delegation_cheating as sdc  # noqa: E402


def _mc2_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "ws_mc2"
    ws.mkdir()
    (ws / ".opgen_state.json").write_text(
        json.dumps(
            {
                "op": "mc2demo",
                "opgen_mode": "port_a3_to_a5",
                "multirank": True,
            }
        )
    )
    (ws / "model_new_ascendc.py").write_text("x = 1\n")
    return ws


def _seed_nest_clean(ws: Path) -> None:
    """A clean multirank nest: prj-<op>/op_kernel + op_host/wrapper glue calling
    the op's OWN aclnn + the autogen header that declares that surface."""
    prj = ws / "prj-mc2demo"
    (prj / "op_kernel").mkdir(parents=True)
    (prj / "op_kernel" / "mc2demo.h").write_text("// kernel\n")
    (prj / "op_kernel" / "mc2demo.cpp").write_text(
        'extern "C" __global__ __aicore__ void mc2demo() {}\n'
    )
    (prj / "op_host" / "wrapper").mkdir(parents=True)
    (prj / "op_host" / "wrapper" / "aclnn_mc2demo.cpp").write_text(
        "aclnnMc2demoGetWorkspaceSize(a, b, c, d);\naclnnMc2demo(a, b, c, d);\n"
    )
    (prj / ".build" / "autogen").mkdir(parents=True)
    (prj / ".build" / "autogen" / "aclnn_mc2demo.h").write_text(
        "aclnnInnerMc2demo aclnnInnerMc2demoGetWorkspaceSize\n"
    )


def test_nest_clean_scan_passes(tmp_path):
    """The moe_fused_a8w8 shape: everything under prj-<op>/, wrapper calls

    the op's own aclnn, autogen header declares that surface → 0 violations.
    Before the fix this exact shape was a permanent coverage-gap failure.
    """
    ws = _mc2_ws(tmp_path)
    _seed_nest_clean(ws)
    rep = sdc.scan_op_workspace(ws)
    assert rep["ok"], rep["violations"]


def test_nest_real_delegation_in_op_kernel_flagged(tmp_path):
    ws = _mc2_ws(tmp_path)
    _seed_nest_clean(ws)
    (ws / "prj-mc2demo" / "op_kernel" / "cheat.cpp").write_text(
        "auto y = x.matmul(w);\n"
    )
    rep = sdc.scan_op_workspace(ws)
    assert not rep["ok"]
    assert any("matmul" in v["desc"].lower() for v in rep["violations"]), rep[
        "violations"
    ]


def test_nest_foreign_aclnn_without_autogen_flagged(tmp_path):
    """Without an autogen tree there is no own-surface to suppress — a call

    to any aclnn (here another op's) still flags.
    """
    ws = _mc2_ws(tmp_path)
    _seed_nest_clean(ws)
    autogen_dir = ws / "prj-mc2demo" / ".build" / "autogen"
    for f in autogen_dir.iterdir():
        f.unlink()
    (ws / "prj-mc2demo" / "op_host" / "wrapper" / "aclnn_mc2demo.cpp").write_text(
        "aclnnSomeOtherOp(a, b, c, d);\n"
    )
    rep = sdc.scan_op_workspace(ws)
    assert not rep["ok"]
    assert any("aclnn" in v["desc"] for v in rep["violations"]), rep["violations"]


def test_coverage_gap_when_dirs_absent_everywhere(tmp_path):
    """Declared dirs missing at BOTH the root and under prj-*/ → the honest

    coverage-gap violation (fail-loud), not a silent zero-pass.
    """
    ws = _mc2_ws(tmp_path)  # no op_host/op_kernel anywhere
    rep = sdc.scan_op_workspace(ws)
    assert not rep["ok"]
    assert any(
        v.get("category") == sdc.SCANNER_COVERAGE_CATEGORY for v in rep["violations"]
    ), rep["violations"]


def test_flat_layout_still_scanned(tmp_path):
    """Legacy single-layer layout (op_kernel at the root) keeps working."""
    ws = _mc2_ws(tmp_path)
    (ws / "op_kernel").mkdir()
    (ws / "op_kernel" / "k.cpp").write_text("auto y = x.matmul(w);\n")
    rep = sdc.scan_op_workspace(ws)
    assert not rep["ok"]
    assert any("matmul" in v["desc"].lower() for v in rep["violations"])


def test_own_aclnn_surface_prefix_family(tmp_path):
    """_own_aclnn_surface: autogen identifiers go to the exact set; the

    public export family is derived from the header STEM (aclnn_mc2demo.h →
    aclnnMc2demo*), so the wrapper's public calls suppress even though the
    header only declares the Inner variants.
    """
    ws = tmp_path / "ws"
    (ws / "prj-x" / ".build" / "autogen").mkdir(parents=True)
    (ws / "prj-x" / ".build" / "autogen" / "aclnn_mc2_demo.h").write_text(
        "aclnnInnerMc2Demo aclnnInnerMc2DemoGetWorkspaceSize\n"
    )
    exact, prefixes = getattr(sdc, "_own_aclnn_surface")(ws)
    assert "aclnnInnerMc2Demo" in exact
    assert "aclnnInnerMc2DemoGetWorkspaceSize" in exact
    assert "aclnnMc2Demo" in prefixes  # stem-derived public family


def test_nest_with_npubench_reference_binding(tmp_path):
    """A reference binding in durable state (npubench) must not flip a

    multirank workspace onto the single-card flat ``kernel/`` declaration:
    the candidate stays under prj-<op>/op_kernel, and the scan must BOTH
    pass clean on a clean nest AND still catch delegation planted inside
    the nest (proof the declaration really covers the nest contents).
    """
    ws = _mc2_ws(tmp_path)
    state = json.loads((ws / ".opgen_state.json").read_text())
    state["reference"] = {"source": "npubench"}
    (ws / ".opgen_state.json").write_text(json.dumps(state))
    _seed_nest_clean(ws)
    rep = sdc.scan_op_workspace(ws)
    assert rep["ok"], rep["violations"]
    (ws / "prj-mc2demo" / "op_kernel" / "cheat.cpp").write_text(
        "auto y = x.matmul(w);\n"
    )
    rep = sdc.scan_op_workspace(ws)
    assert not rep["ok"]
    assert any("matmul" in v["desc"].lower() for v in rep["violations"]), rep[
        "violations"
    ]
