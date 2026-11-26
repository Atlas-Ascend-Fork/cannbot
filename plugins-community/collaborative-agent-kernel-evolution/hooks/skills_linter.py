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

import tiktoken  # 导入 OpenAI 官方 token 计算库
import yaml

from _yaml_utils import (MAX_NAME_LENGTH, NAME_PATTERN, YAMLFixSuggestion,
                         check_name_field, parse_frontmatter, report_frontmatter_error)

logger = logging.getLogger(__name__)

# 配置项（可根据需求调整）
SKILLS_DIR = "./skills"
SKILL_FILENAME = "SKILL.md"
MAX_DESCRIPTION_TOKENS = 150  # SKILL.md frontmatter description token 数量限制
# 指定模型编码（主流模型：gpt-3.5-turbo/gpt-4 均用 cl100k_base）
ENCODING_NAME = "cl100k_base"


def count_tokens(text: str, encoding_name: str = ENCODING_NAME) -> int:
    """计算文本的 token 数（兼容 OpenAI 全系列模型）.

    Args:
        text: 要统计的文本.
        encoding_name: 编码名称（cl100k_base 适配 gpt-3.5/4，p50k_base 适配 davinci）.

    Returns:
        token 数量.
    """
    if not text:
        return 0
    encoding = tiktoken.get_encoding(encoding_name)
    return len(encoding.encode(text))


def check_skill_file(file_path: Path) -> bool:
    """检查单个 SKILL.md 文件的规范.

    Args:
        file_path: SKILL.md 文件的路径.

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

            # 检查 name 与目录名一致性（必须逐字符完全一致）
            skill_dir_name = file_path.parent.name
            if name != skill_dir_name:
                logger.info(f"⚠️ {file_path}: name '{name}' 与目录名不一致（目录: '{skill_dir_name}'）")
                passed = False

        # 检查 description 字段
        if "description" not in data:
            logger.info(f"⚠️ {file_path}: 缺少 'description' 字段")
            passed = False
        else:
            desc = str(data["description"]).strip()
            token_count = count_tokens(desc)

            # 校验 token 数不超过阈值
            if token_count > MAX_DESCRIPTION_TOKENS:
                logger.info(f"⚠️ {file_path}: description token 数超标（{token_count}/{MAX_DESCRIPTION_TOKENS}）")
                passed = False

    except Exception as e:
        report_frontmatter_error(file_path, e)
        passed = False

    return passed


def main():
    """检查 SKILL.md 文件.

    如果提供了命令行参数（文件路径列表），则只检查这些文件。
    这用于 pre-commit hook，只检查 staged 文件。

    如果没有提供参数，则检查整个 skills/ 目录下的所有 SKILL.md 文件。

    Exits:
        0: 所有文件检查通过.
        1: 部分文件不符合规范.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    skills_path = Path(SKILLS_DIR)

    # 如果提供了命令行参数（staged 文件列表），只检查这些文件
    if len(sys.argv) > 1:
        skill_files = [Path(file_path) for file_path in sys.argv[1:]]
        # 过滤出真正的 SKILL.md 文件
        skill_files = [f for f in skill_files if f.name == SKILL_FILENAME and f.exists()]
    else:
        # 否则检查整个目录（向后兼容）
        if not skills_path.exists():
            logger.info(f"ℹ️  {SKILLS_DIR} 目录不存在，跳过检查")
            sys.exit(0)

        skill_files = list(skills_path.glob(f"*/{SKILL_FILENAME}"))

    if not skill_files:
        logger.info(f"ℹ️  没有找到需要检查的 {SKILL_FILENAME} 文件")
        sys.exit(0)

    # 检查每个文件
    all_passed = True
    for file in skill_files:
        if not check_skill_file(file):
            all_passed = False

    # 输出结果并返回对应状态码
    if all_passed:
        logger.info("✅ 所有 SKILL.md 文件检查通过")
        sys.exit(0)
    else:
        logger.info("\n❌ 部分 SKILL.md 文件不符合规范，请修复后重新提交")
        sys.exit(1)


if __name__ == "__main__":
    main()
