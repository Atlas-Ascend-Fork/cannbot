# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Regression: compute_next_actions must accept a relative workspace root.

`batch_dispatcher.py plan --workspace-root workspace` passed the discovered
relative workspace path to Path.relative_to() against the absolute project
root, raising an uncaught ValueError before any plan was emitted. The fix
resolves the workspace root, each discovered workspace, and the project root
before computing the relative output path.
"""
from __future__ import annotations

import pathlib
import sys

_HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))
import batch_dispatcher as bd  # noqa: E402


def test_relative_workspace_root_does_not_crash(tmp_path, monkeypatch):
    """Relative --workspace-root resolves against cwd and yields one action."""
    engine = tmp_path / "engine"
    op_dir = engine / "workspace" / "01_demo_op"
    op_dir.mkdir(parents=True)
    (op_dir / "PROGRESS.md").write_text("# demo\n", encoding="utf-8")

    monkeypatch.setattr(bd, "PROJECT_ROOT", engine)
    monkeypatch.setattr(bd, "LANES_STATE_DIR", engine / "src" / "workspace" / ".lanes")

    monkeypatch.chdir(engine)
    actions = bd.compute_next_actions(pathlib.Path("workspace"))

    assert [a.op for a in actions] == ["01_demo_op"]
    assert actions[0].workspace == str(pathlib.Path("workspace") / "01_demo_op")
