# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Exercise both build CLIs in a relocated CAKE plugin directory."""

from pathlib import Path
import shutil
import subprocess
import sys

import pytest


_PLUGIN = Path(__file__).resolve().parents[1]
_BRIDGE = Path(
    "skills/code-performance-advisor/scripts/analysis_engine/build_operator.py"
)
_EVALUATION = Path("skills/ascendc-evaluation/scripts")
_BUILD_SCRIPT = "#!/bin/sh\n: > operator_build_requested\n"


@pytest.fixture
def relocated_bridge(tmp_path):
    root = tmp_path / "CAKE plugin"
    bridge_file = root / _BRIDGE
    bridge_file.parent.mkdir(parents=True)
    shutil.copy2(_PLUGIN / _BRIDGE, bridge_file)
    return root, bridge_file


def _run_bridge(root, script, op):
    result = subprocess.run(
        [sys.executable, str(script), "--op", op],
        cwd=root.parent,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return result.returncode, result.stdout + result.stderr


def test_find_build_directory_in_plugin_output(relocated_bridge):
    root, bridge = relocated_bridge
    build_dir = root / "output" / "add" / "AddCustom"
    build_dir.mkdir(parents=True)
    (build_dir / "build.sh").write_text(_BUILD_SCRIPT, encoding="utf-8")

    status, log = _run_bridge(root, bridge, "add")

    assert status == 0, log
    assert (build_dir / "operator_build_requested").is_file()


def _prepare_pybind(root, build_script, with_source=True):
    evaluation = root / _EVALUATION
    template = evaluation / "template" / "CppExtension"
    template.mkdir(parents=True)
    shutil.copy2(_PLUGIN / _EVALUATION / "generate_pybind.py", evaluation)
    (template / "setup.py").write_text(build_script, encoding="utf-8")
    output = root / "output" / "Add"
    output.mkdir(parents=True)
    (output / "build.sh").write_text(_BUILD_SCRIPT, encoding="utf-8")
    if with_source:
        (output / "Add.cpp").write_text(
            "// operator binding source\n", encoding="utf-8"
        )
    return output


def test_rebuild_pybind_uses_bundled_cli_and_plugin_output(relocated_bridge):
    root, bridge = relocated_bridge
    output = _prepare_pybind(
        root,
        "from pathlib import Path\n"
        "Path('build_requested').write_text('ok', encoding='utf-8')\n",
    )

    status, log = _run_bridge(root, bridge, "Add")

    assert status == 0, log
    extension = output / "ascend_op_pybind" / "CppExtension"
    assert (extension / "csrc" / "op.cpp").read_text(encoding="utf-8") == (
        "// operator binding source\n"
    )
    assert (extension / "build_requested").read_text(encoding="utf-8") == "ok"
    assert "Pybind rebuild successful" in log


@pytest.mark.parametrize(
    ("with_source", "build_script", "expected"),
    [(False, "", "Add.cpp"), (True, "raise SystemExit(7)\n", "Exit Code: 7")],
    ids=["missing-source", "failed-build"],
)
def test_rebuild_pybind_reports_failures(
    relocated_bridge, with_source, build_script, expected
):
    root, bridge = relocated_bridge
    _prepare_pybind(root, build_script, with_source)

    status, log = _run_bridge(root, bridge, "Add")

    assert status == 0, log
    assert "Pybind rebuild warning (exit 1)" in log
    assert expected in log
