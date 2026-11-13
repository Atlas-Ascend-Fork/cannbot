#!/usr/bin/env python3
# coding: utf-8
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: CANN-2.0
"""装配并校验 pypto-op-orchestrator 的工作区资产。

安装模式调用 cannbot 的统一安装器。统一安装器负责把工作流所需的 Skills、
workflows、agents 和 hooks 放入目标工作区；本脚本再把 OpenCode 专用 hooks
接线到客户端目录。

verify-only 模式不执行安装，只校验已经装配的工作区。脚本只读取
``.cannbot/plugins/pypto-op-orchestrator/hooks``，不访问旧的 dependency
checkout，也不保留旧路径 fallback。

用法::

    python3 assemble_workspace.py --cannbot-root /path/to/cannbot --target "$WORK_DIR"
    python3 assemble_workspace.py --target "$WORK_DIR"   # verify-only

成功时向 stdout 打印一行 JSON: ``{"status":"ok","skills":N,"agents":M,"plugins":K}``。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

PLUGIN_NAME = "pypto-op-orchestrator"
LEGACY_DEPENDENCY_ROOT = (".cannbot", "dependencies", PLUGIN_NAME)
ASSET_ROOT = (".cannbot", "plugins", PLUGIN_NAME)
EXPECTED_SKILLS = frozenset(
    {
        "pypto-op-orchestrator",
        "workflow-orchestrator",
        "pypto-api-explore",
        "pypto-docs-search",
        "pypto-general-debug",
        "pypto-golden-generate",
        "pypto-intent-understand",
        "pypto-memory-template",
        "pypto-op-design",
        "pypto-op-develop",
        "pypto-op-knowledge",
        "pypto-op-perf-tune",
        "pypto-op-plan",
        "pypto-op-review",
        "pypto-op-verify",
        "pypto-orchestration-manual",
        "pypto-op-perf-panko-manual",
        "pypto-precision-compare",
        "pypto-precision-debug",
    }
)
REQUIRED_HOOK_FILES = (
    Path("opencode/pypto-op-lint.ts"),
    Path("opencode/pypto-state-transition.ts"),
    Path("opencode/lib/state-transition-core.ts"),
    Path("pypto-op-lint/pypto_op_lint.py"),
    Path("pypto-op-lint/rules.json"),
)


def _fail(msg: str) -> int:
    logger.error("[assemble_workspace] 错误: %s", msg)
    return 2


def _copy_tree(src: Path, dst: Path) -> None:
    """幂等整目录拷贝；目标内容由同一份插件资产覆盖。"""
    if not src.is_dir():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _run_installer(cannbot_root: Path, target: Path) -> Optional[str]:
    """调用统一安装器完成入口 Skill、共享 Skill 和插件资产安装。"""
    installer = cannbot_root / "script" / "bin" / "cannbot.js"
    if not cannbot_root.is_dir() or not installer.is_file():
        return "cannbot 仓根或安装器不存在: %s" % installer
    env = dict(os.environ)
    # 工作区装配不需要向 opencode 注册 npm 插件包。
    env["CANNBOT_SKIP_OPENCODE_PLUGIN_ADD"] = "1"
    node = shutil.which("node")
    if not node:
        return "node 可执行文件不在 PATH 中"
    result = subprocess.run(
        [
            node,
            str(installer),
            "install",
            PLUGIN_NAME,
            "--tool",
            "opencode",
            "--target",
            str(target),
            "--source",
            str(cannbot_root),
        ],
        env=env,
        check=False,
    )
    if result.returncode != 0:
        return "安装器执行失败 (exit %d): %s" % (result.returncode, installer)
    return None


def _asset_root(target: Path) -> Path:
    return target.joinpath(*ASSET_ROOT)


def _legacy_root(target: Path) -> Path:
    return target.joinpath(*LEGACY_DEPENDENCY_ROOT)


def _remove_legacy_root(target: Path) -> None:
    """清理旧安装生成的本插件 dependency 目录，不读取其内容。"""
    legacy = _legacy_root(target)
    if not legacy.exists() and not legacy.is_symlink():
        return
    if legacy.is_symlink() or legacy.is_file():
        legacy.unlink()
    else:
        shutil.rmtree(legacy)
    parent = legacy.parent
    if parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()


def _hooks_source(target: Path) -> Optional[Path]:
    hooks = _asset_root(target) / "hooks"
    return hooks if hooks.is_dir() else None


def _wire_opencode_hooks(target: Path) -> Tuple[Optional[str], int]:
    """把插件资产中的 OpenCode hooks 接线到目标客户端目录。"""
    hooks = _hooks_source(target)
    if hooks is None:
        return "插件资产缺少 hooks 目录: %s" % (_asset_root(target) / "hooks"), 0
    missing = [str(path) for path in REQUIRED_HOOK_FILES if not (hooks / path).is_file()]
    if missing:
        return "hooks 目录缺少必需文件: %s" % ", ".join(missing), 0
    opencode_dir = target / ".opencode"
    _copy_tree(hooks / "opencode", opencode_dir / "plugins")
    _copy_tree(hooks / "pypto-op-lint", opencode_dir / "hooks" / "pypto-op-lint")
    return None, 2


def _read_registry(target: Path) -> Tuple[Optional[str], list[dict]]:
    registry = target / ".opencode" / "cannbot-plugin.json"
    if not registry.is_file():
        return "安装记录不存在 (插件未装配): %s" % registry, []
    try:
        records = json.loads(registry.read_text(encoding="utf-8")).get("plugins", [])
    except (json.JSONDecodeError, OSError) as exc:
        return "安装记录解析失败 (%s): %s" % (registry, exc), []
    if not isinstance(records, list):
        return "安装记录的 plugins 字段不是数组: %s" % registry, []
    return None, [record for record in records if isinstance(record, dict)]


def _verify(target: Path) -> Tuple[Optional[str], dict]:
    """校验安装记录、Skills、插件资产和 OpenCode 接线。"""
    stats = {"skills": 0, "agents": 0, "plugins": 0}
    err, records = _read_registry(target)
    if err:
        return err, stats
    record = next((row for row in records if row.get("plugin") == PLUGIN_NAME), None)
    if record is None:
        return "安装记录缺少 %s" % PLUGIN_NAME, stats
    if record.get("dependencies") not in ([], None):
        return "安装记录仍包含旧 dependencies: %s" % record.get("dependencies"), stats
    if record.get("dependencyAssets") not in ([], None):
        return "安装记录仍包含旧 dependencyAssets: %s" % record.get("dependencyAssets"), stats

    legacy = _legacy_root(target)
    if legacy.exists() or legacy.is_symlink():
        return "发现旧 dependency 目录，必须清理后再验收: %s" % legacy, stats

    assets = _asset_root(target)
    hooks = assets / "hooks"
    if not assets.is_dir():
        return "插件资产目录不存在: %s" % assets, stats
    missing = [str(path) for path in REQUIRED_HOOK_FILES if not (hooks / path).is_file()]
    if missing:
        return "插件资产 hooks 不完整: %s" % ", ".join(missing), stats
    if not (assets / "workflows").is_dir():
        return "插件资产 workflows 不存在: %s" % (assets / "workflows"), stats

    skills_dir = target / ".agents" / "skills"
    installed = {
        path.name
        for path in skills_dir.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    } if skills_dir.is_dir() else set()
    stats["skills"] = len(installed)
    missing_skills = sorted(EXPECTED_SKILLS - installed)
    if missing_skills:
        return "缺少必需 Skill (%d): %s" % (len(missing_skills), ", ".join(missing_skills)), stats

    agents_dir = target / ".opencode" / "agents"
    expected_agents = ("general-executor.md", "general-verifier.md")
    missing_agents = [name for name in expected_agents if not (agents_dir / name).is_file()]
    stats["agents"] = len(list(agents_dir.glob("*.md"))) if agents_dir.is_dir() else 0
    if missing_agents:
        return "缺少通用 agent: %s" % ", ".join(missing_agents), stats

    opencode_plugins = target / ".opencode" / "plugins"
    opencode_hooks = target / ".opencode" / "hooks" / "pypto-op-lint"
    if not (opencode_plugins / "pypto-op-lint.ts").is_file():
        return "OpenCode lint hook 未接线: %s" % (opencode_plugins / "pypto-op-lint.ts"), stats
    if not (opencode_plugins / "pypto-state-transition.ts").is_file():
        return "OpenCode state hook 未接线: %s" % (opencode_plugins / "pypto-state-transition.ts"), stats
    if not (opencode_plugins / "lib" / "state-transition-core.ts").is_file():
        return "OpenCode state hook core 未接线", stats
    if not (opencode_hooks / "pypto_op_lint.py").is_file():
        return "OpenCode pypto-op-lint 目录未接线: %s" % opencode_hooks, stats
    stats["plugins"] = sum(1 for path in opencode_plugins.iterdir()) if opencode_plugins.is_dir() else 0
    return None, stats


def assemble(cannbot_root: Optional[Path], target: Path) -> Tuple[Optional[str], dict]:
    """执行装配；返回 (错误说明或 None, 统计 dict)。"""
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    if cannbot_root is not None:
        # 这是旧安装生成的单一插件目录，只清理它，不触碰其他依赖。
        _remove_legacy_root(target)
        err = _run_installer(cannbot_root.resolve(), target)
        if err:
            return err, {"skills": 0, "agents": 0, "plugins": 0}
    # source 和 npx 安装都会把 hooks 放入插件资产目录；无论是否由本次调用
    # 执行安装，都需要把它们接线到 OpenCode 客户端目录。
    err, _ = _wire_opencode_hooks(target)
    if err:
        return err, {"skills": 0, "agents": 0, "plugins": 0}
    return _verify(target)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把 pypto-op-orchestrator 插件资产装配进目标 opencode 工作区"
    )
    parser.add_argument(
        "--cannbot-root",
        type=Path,
        default=None,
        help="cannbot 仓根 (含 script/bin/cannbot.js); 省略时为 verify-only 模式",
    )
    parser.add_argument(
        "--target",
        required=True,
        type=Path,
        help="装配目标目录 (一般是工作流 $WORK_DIR 或调用方工作区)",
    )
    args = parser.parse_args()

    err, stats = assemble(args.cannbot_root, args.target)
    if err:
        return _fail(err)
    os.write(
        1, (json.dumps({"status": "ok", **stats}, ensure_ascii=False) + "\n").encode()
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
