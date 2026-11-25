#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

import logging
import sys
from pathlib import Path

import yaml

from _yaml_utils import (MAX_NAME_LENGTH, NAME_PATTERN, YAMLFixSuggestion,
                         check_name_field, parse_frontmatter, report_frontmatter_error)

logger = logging.getLogger(__name__)

# 配置项
AGENTS_DIR = "./agents"
SKILLS_DIR = "./skills"


def _check_skills_field(file_path: Path, skills) -> bool:
    """校验 agent 的 skills 字段，返回是否通过."""
    if not isinstance(skills, list):
        logger.info(f"⚠️ {file_path}: skills 字段必须是列表")
        return False
    skills_path = Path(SKILLS_DIR)
    if not skills_path.exists():
        logger.info(f"⚠️  {file_path}: 无法验证 skills，{SKILLS_DIR} 目录不存在")
        return False
    available_skills = {d.name for d in skills_path.iterdir() if d.is_dir()}
    passed = True
    for skill in skills:
        skill_name = str(skill).strip()
        if skill_name not in available_skills:
            logger.info(f"⚠️ {file_path}: skill '{skill_name}' 在 {SKILLS_DIR} 目录下不存在")
            passed = False
    return passed


def check_agent_file(file_path: Path) -> bool:
    """检查单个 agent .md 文件的规范.

    Args:
        file_path: agent .md 文件的路径.

    Returns:
        是否通过检查（True 表示通过，False 表示失败）.
    """
    passed = True
    try:
        # 读取文件内容
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 解析 YAML frontmatter
        data = parse_frontmatter(content)

        # 检查 name 字段（存在性、格式、长度由共用函数校验）
        name_ok, name = check_name_field(file_path, data)
        if not name_ok:
            passed = False
        if name is not None:

            # 检查 name 与文件名一致性（文件名去掉 .md 后缀应与 name 一致）
            file_name_without_ext = file_path.stem  # 去掉 .md 后缀
            if name != file_name_without_ext:
                logger.info(f"⚠️ {file_path}: name '{name}' 与文件名不一致（文件名: '{file_name_without_ext}.md'）")
                passed = False

        # 检查 skills 字段（如果存在）
        if "skills" in data and not _check_skills_field(file_path, data["skills"]):
            passed = False

    except Exception as e:
        report_frontmatter_error(file_path, e)
        passed = False

    return passed


def main():
    """检查 agent .md 文件.

    如果提供了命令行参数（文件路径列表），则只检查这些文件。
    这用于 pre-commit hook，只检查 staged 文件。

    如果没有提供参数，则检查整个 ./agents/ 目录下的所有 .md 文件。

    Exits:
        0: 所有文件检查通过.
        1: 部分文件不符合规范.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    agents_path = Path(AGENTS_DIR)

    # 如果提供了命令行参数（staged 文件列表），只检查这些文件
    if len(sys.argv) > 1:
        agent_files = [Path(file_path) for file_path in sys.argv[1:]]
        # 过滤出真正的 .md 文件
        agent_files = [f for f in agent_files if f.suffix == '.md' and f.exists()]
    else:
        # 否则检查整个目录（向后兼容）
        if not agents_path.exists():
            logger.info(f"ℹ️  {AGENTS_DIR} 目录不存在，跳过检查")
            sys.exit(0)

        agent_files = list(agents_path.glob("*.md"))

    if not agent_files:
        logger.info(f"ℹ️  没有找到需要检查的 agent .md 文件")
        sys.exit(0)

    # 检查每个文件
    all_passed = True
    for file in agent_files:
        if not check_agent_file(file):
            all_passed = False

    # 输出结果并返回对应状态码
    if all_passed:
        logger.info("✅ 所有 agent .md 文件检查通过")
        sys.exit(0)
    else:
        logger.info("\n❌ 部分 agent .md 文件不符合规范，请修复后重新提交")
        sys.exit(1)


if __name__ == "__main__":
    main()
