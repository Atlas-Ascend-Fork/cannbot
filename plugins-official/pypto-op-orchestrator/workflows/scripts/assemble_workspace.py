#!/usr/bin/env python3
# coding: utf-8
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: CANN-2.0
"""把 pypto-op-orchestrator 插件资产装配进任意目标目录 (如外部调用方的工作区).

本脚本是对安装器 (``cannbot.js install --source``) 的薄封装, 不重复实现安装逻辑:

1. 给定 ``--cannbot-root`` 时, 调用
   ``node <cannbot-root>/script/bin/cannbot.js install pypto-op-orchestrator
   --tool opencode --target <target> --source <cannbot-root>``。
   安装器幂等完成: 克隆/更新 cannbot-skills 到
   ``<target>/.cannbot/dependencies/pypto-op-orchestrator/cannbot-skills``,
   并按其 ``plugin-assets.json`` 把 skills 相对软链进 ``<target>/.agents/skills/``、
   hooks 装配进 ``<target>/.cannbot/plugins/pypto-op-orchestrator/hooks``、
   workflows 与两个通用 agent 拷进 ``<target>/.cannbot/plugins/...`` 与
   ``<target>/.opencode/agents/`` —— 效果与 npx 安装一致。
2. 随后补一层 opencode hooks 接线 (安装器不覆盖该 client 侧布局): 依赖仓 ``hooks/opencode/*`` 拷入 ``<target>/.opencode/plugins/``,
   ``hooks/pypto-op-lint`` 拷入 ``<target>/.opencode/hooks/pypto-op-lint``
   (.ts 按 import.meta.url 相对定位 ../hooks/pypto-op-lint, 不能软链)。

省略 ``--cannbot-root`` 时为 verify-only 模式: 目标目录已装配 (安装记录 +
依赖仓检出在场) 则直接校验通过, 用于 npx 安装后的工作区或断点续跑。

幂等: 重复执行结果相同。失败打印 stderr 诊断, 退出码 2。

用法::

    python3 assemble_workspace.py --cannbot-root /path/to/cannbot --target "$WORK_DIR"
    python3 assemble_workspace.py --target "$WORK_DIR"   # verify-only

成功时向 stdout 打印一行 JSON: ``{"status":"ok","skills":N,"agents":M,"plugins":K}``.
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
DEPENDENCY_NAME = "cannbot-skills"
DEFAULT_HOOKS_REL = ("plugins-official", PLUGIN_NAME, "hooks")


def _fail(msg: str) -> int:
    logger.error("[assemble_workspace] 错误: %s", msg)
    return 2


def _copy_tree(src: Path, dst: Path, merge: bool = False) -> None:
    """幂等整目录拷贝: 目标已存在则跳过; merge=True 时把 src 内容并入已存在的 dst
    (内容同源, 重复拷贝即幂等)."""
    if dst.exists() and not merge:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=merge)


def _run_installer(cannbot_root: Path, target: Path) -> Optional[str]:
    """调用安装器完成依赖拉取与资产装配; 返回错误说明或 None."""
    installer = cannbot_root / "script" / "bin" / "cannbot.js"
    if not cannbot_root.is_dir() or not installer.is_file():
        return "cannbot 仓根或安装器不存在: %s" % installer
    env = dict(os.environ)
    # 工作区装配不需要向 opencode 注册 npm 插件包 (交互客户端另有入口)
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


def _dependency_checkout(target: Path) -> Optional[Path]:
    checkout = target / ".cannbot" / "dependencies" / PLUGIN_NAME / DEPENDENCY_NAME
    return checkout if checkout.is_dir() else None


def _hooks_source(checkout: Path) -> Optional[Path]:
    """依赖仓内 hooks 目录: 优先 plugin-assets.json 声明, 否则默认插件路径."""
    manifest = checkout / "plugins-official" / PLUGIN_NAME / "plugin-assets.json"
    hooks_dir = None
    if manifest.is_file():
        try:
            declared = json.loads(manifest.read_text(encoding="utf-8")).get("hooks")
            if isinstance(declared, dict) and isinstance(declared.get("dir"), str):
                hooks_dir = checkout / declared["dir"]
        except (json.JSONDecodeError, OSError):
            hooks_dir = None
    if hooks_dir is None:
        hooks_dir = checkout.joinpath(*DEFAULT_HOOKS_REL)
    return hooks_dir if hooks_dir.is_dir() else None


def _wire_opencode_hooks(target: Path) -> Tuple[Optional[str], int]:
    """把依赖仓 opencode hooks 接线进目标工作区; 返回 (错误说明或 None, 计数)."""
    checkout = _dependency_checkout(target)
    if checkout is None:
        return "依赖仓检出不存在: %s" % (
            target / ".cannbot" / "dependencies" / PLUGIN_NAME / DEPENDENCY_NAME
        ), 0
    hooks = _hooks_source(checkout)
    if hooks is None:
        return "依赖仓缺少 hooks 目录 (plugin-assets.json 未声明且默认路径不存在)", 0
    opencode_dir = target / ".opencode"
    wired = 0
    hooks_opencode = hooks / "opencode"
    if hooks_opencode.is_dir():
        _copy_tree(hooks_opencode, opencode_dir / "plugins", merge=True)
        wired += 1
    hooks_lint = hooks / "pypto-op-lint"
    if hooks_lint.is_dir():
        _copy_tree(hooks_lint, opencode_dir / "hooks" / "pypto-op-lint")
        wired += 1
    if not wired:
        return "hooks 目录下既无 opencode/ 也无 pypto-op-lint/: %s" % hooks, 0
    return None, wired


def _verify(target: Path) -> Tuple[Optional[str], dict]:
    """校验装配结果并统计; 返回 (错误说明或 None, 统计 dict)."""
    stats = {"skills": 0, "agents": 0, "plugins": 0}
    registry = target / ".opencode" / "cannbot-plugin.json"
    if not registry.is_file():
        return "安装记录不存在 (插件未装配): %s" % registry, stats
    try:
        records = json.loads(registry.read_text(encoding="utf-8")).get("plugins", [])
    except (json.JSONDecodeError, OSError) as exc:
        return "安装记录解析失败 (%s): %s" % (registry, exc), stats
    if not any(r.get("plugin") == PLUGIN_NAME for r in records if isinstance(r, dict)):
        return "安装记录缺少 %s: %s" % (PLUGIN_NAME, registry), stats
    if _dependency_checkout(target) is None:
        return "依赖仓检出不存在: %s/.cannbot/dependencies/%s/%s" % (
            target,
            PLUGIN_NAME,
            DEPENDENCY_NAME,
        ), stats
    skills_dir = target / ".agents" / "skills"
    agents_dir = target / ".opencode" / "agents"
    plugins_dir = target / ".opencode" / "plugins"
    stats["skills"] = sum(1 for p in skills_dir.iterdir()) if skills_dir.is_dir() else 0
    stats["agents"] = len(list(agents_dir.glob("*.md"))) if agents_dir.is_dir() else 0
    stats["plugins"] = (
        sum(1 for p in plugins_dir.iterdir()) if plugins_dir.is_dir() else 0
    )
    return None, stats


def assemble(cannbot_root: Optional[Path], target: Path) -> Tuple[Optional[str], dict]:
    """执行装配; 返回 (错误说明或 None, 统计 dict)."""
    target = target.resolve()
    target.mkdir(parents=True, exist_ok=True)
    if cannbot_root is not None:
        err = _run_installer(cannbot_root.resolve(), target)
        if err:
            return err, {"skills": 0, "agents": 0, "plugins": 0}
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
    # 契约输出: 工作流 preflight 依赖 stdout JSON 的 status=ok;
    # stdout 契约输出, 用 os.write 直写 fd 1 而非 print/logging (修复 G.LOG.02)
    os.write(
        1, (json.dumps({"status": "ok", **stats}, ensure_ascii=False) + "\n").encode()
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
