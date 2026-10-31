# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
"""Install only the selected new-repository team with read-only local Skill sources."""

import json
import os
from pathlib import Path
import shutil
import subprocess

from sandbox_manager import SandboxManager


def _create_tilelang_sandbox(manager, team_name, eval_id, repo_root, team_dir):
    plugin = Path(os.environ["TILELANG_ST_PLUGIN"]).resolve()
    if team_name != plugin.name or Path(team_dir).resolve() != plugin:
        raise ValueError("TileLang ST must install the selected new-repository plugin")
    bash = shutil.which("bash")
    if not bash:
        raise ValueError("Bash executable not found")
    sandbox = manager.create_sandbox(team_name, eval_id)
    command = [str(Path(bash).resolve()), str(plugin / "init.sh"), "project", "opencode", str(sandbox),
               "--skills", os.environ["TILELANG_ST_SKILLS"]]
    try:
        result = subprocess.run(command, cwd=repo_root, capture_output=True, text=True,
                                timeout=300, check=False)
        if result.returncode:
            raise RuntimeError(f"TileLang ST installation failed: {result.stderr[-2000:]}")
        registry = json.loads((sandbox / ".opencode" / "cannbot-plugin.json").read_text())
        records = registry.get("plugins", [])
        if len(records) != 1 or records[0].get("plugin") != team_name:
            raise ValueError("ST sandbox must register exactly the selected TileLang plugin")
        record = records[0]
        if len(record.get("skills", [])) != 13 or len(record.get("agents", [])) != 6:
            raise ValueError("ST sandbox must install all 13 shared Skills and 6 roles")
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        manager.cleanup_sandbox(sandbox)
        raise
    return sandbox


def pytest_configure(config):
    SandboxManager.create_team_sandbox = _create_tilelang_sandbox
