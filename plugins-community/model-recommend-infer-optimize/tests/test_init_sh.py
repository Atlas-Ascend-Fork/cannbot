#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""init.sh 安装器的行为回归测试（不依赖真实 cannbot-skills 仓，用桩 Skill 目录驱动）。

覆盖以下回归点：
  A --help 不依赖子模块         -> 0，输出 Usage
  B 只找到部分 Skill            -> 1，且不得出现 All checks passed（旧版会静默成功）
  C 18 个 Skill 齐全            -> 0，配置根 skills/ 下 18 项
  D CANNBOT_SKILL_SRC_ROOT 指向仓根 -> 0（自动下沉到 community/model）
  E codex 安装                  -> 0，.codex/agents/ 下 TOML+MD 同级，且源仓文件不被搬走
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LOG = logging.getLogger("test_init_sh")

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "init.sh"


def configure_logging():
    """测试结果按纯文本输出，便于 CI 直接阅读。"""
    if LOG.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOG.addHandler(handler)
    LOG.setLevel(logging.INFO)
    LOG.propagate = False


def included_skills():
    text = INIT.read_text(encoding="utf-8")
    match = re.search(r'(?m)^INCLUDED_SKILLS="([^"]*)"', text)
    assert match, "INCLUDED_SKILLS not found in init.sh"
    return match.group(1).split()


SKILLS = included_skills()


def make_skills(root, names):
    for name in names:
        directory = Path(root) / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "SKILL.md").write_text(
            "---\nname: %s\ndescription: stub for installer regression test\n---\n\n# %s\n"
            % (name, name),
            encoding="utf-8",
        )


def run(args, cwd, extra_env=None):
    env = dict(os.environ)
    env.pop("CANNBOT_SKILL_SRC_ROOT", None)
    if Path("/tmp").is_dir():
        env["TMPDIR"] = "/tmp"
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(INIT)] + list(args),
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
    )


def count_linked(config_dir):
    linked = config_dir / "skills"
    return len(list(linked.iterdir())) if linked.is_dir() else 0


def case_help(work, check):
    """A：--help 不依赖子模块。"""
    help_dir = work / "case-help"
    help_dir.mkdir()
    res = run(["--help"], help_dir)
    check(
        "A --help 无子模块",
        res.returncode == 0 and "Usage:" in res.stdout,
        "exit=%d" % res.returncode,
    )


def case_partial(work, check):
    """B：只有 1 个 Skill 时必须失败，且不得报成功。"""
    partial_root = work / "skills-partial"
    make_skills(partial_root, SKILLS[:1])
    partial_dir = work / "case-partial"
    partial_dir.mkdir()
    res = run(
        ["project", "opencode"],
        partial_dir,
        {"CANNBOT_SKILL_SRC_ROOT": str(partial_root)},
    )
    combined = res.stdout + res.stderr
    ok = (
        res.returncode == 1
        and ("1/%d" % len(SKILLS)) in combined
        and "All checks passed" not in combined
    )
    check("B 缺 Skill 时 exit 1 且不报成功", ok, "exit=%d" % res.returncode)


def case_full(work, full_root, check):
    """C：18 个 Skill 齐全，全部链接到配置根。"""
    full_dir = work / "case-full"
    full_dir.mkdir()
    res = run(
        ["project", "opencode"], full_dir, {"CANNBOT_SKILL_SRC_ROOT": str(full_root)}
    )
    count = count_linked(full_dir / ".opencode")
    check(
        "C 全量安装 18 个 Skill",
        res.returncode == 0 and count == len(SKILLS),
        "exit=%d skills=%d" % (res.returncode, count),
    )


def case_repo_root(work, check):
    """D：环境变量指向仓根时自动下沉到 community/model。"""
    repo_root = work / "repo-root"
    make_skills(repo_root / "community" / "model", SKILLS)
    repo_dir = work / "case-reporoot"
    repo_dir.mkdir()
    res = run(
        ["project", "opencode"], repo_dir, {"CANNBOT_SKILL_SRC_ROOT": str(repo_root)}
    )
    count = count_linked(repo_dir / ".opencode")
    check(
        "D 环境变量指向仓根",
        res.returncode == 0 and count == len(SKILLS),
        "exit=%d skills=%d" % (res.returncode, count),
    )


def case_codex(work, full_root, check):
    """E：codex 安装，TOML 与角色 MD 同级落位，且源仓文件不被搬走。"""
    codex_dir = work / "case-codex"
    codex_dir.mkdir()
    src_md = sorted((ROOT / "agents").glob("*.md"))
    src_toml = sorted((ROOT / "agents" / "codex").glob("*.toml"))
    res = run(
        ["project", "codex"], codex_dir, {"CANNBOT_SKILL_SRC_ROOT": str(full_root)}
    )

    agents_dir = codex_dir / ".codex" / "agents"
    installed = sorted(agents_dir.iterdir()) if agents_dir.is_dir() else []
    installed_md = [p for p in installed if p.suffix == ".md"]
    installed_toml = [p for p in installed if p.suffix == ".toml"]
    source_intact = all(p.exists() for p in src_md + src_toml)
    ok = (
        res.returncode == 0
        and len(installed_toml) == len(src_toml)
        and len(installed_md) == len(src_md)
        and source_intact
    )
    check(
        "E codex 落位 MD 且不改源仓",
        ok,
        "exit=%d toml=%d md=%d 源仓完整=%s"
        % (res.returncode, len(installed_toml), len(installed_md), source_intact),
    )
    if installed_toml:
        body = installed_toml[0].read_text(encoding="utf-8")
        rel = ("`" + installed_toml[0].stem + ".md`") in body
        check("E2 TOML 引用同级 MD", rel and "__CANNBOT_AGENT_SOURCE__" not in body, "")


def main():
    configure_logging()
    failures = 0
    log = []

    def check(name, ok, detail=""):
        nonlocal failures
        failures += 0 if ok else 1
        log.append("%-4s %-46s %s" % ("OK" if ok else "FAIL", name, detail))

    work = Path(tempfile.mkdtemp(prefix="rio-init-"))
    try:
        full_root = work / "skills-full"
        make_skills(full_root, SKILLS)
        case_help(work, check)
        case_partial(work, check)
        case_full(work, full_root, check)
        case_repo_root(work, check)
        case_codex(work, full_root, check)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    for line in log:
        LOG.info(line)
    LOG.info("failures: %d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
