#!/usr/bin/env bash
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
set -euo pipefail

BRAND="cannbot"
PLUGIN="ops-qa-suite"
VERSION="0.1.0"
INCLUDED_SKILLS="scan-cmake tool-link-checker scan-op-list scan-ut-test fixer-broken-link tool-reports-to-issue scan-op-api-list scan-ut-analysis scan-examples-analysis scan-repo-docs scan-examples-test cann-error-code-standard ops-error-code-remediation gitcode-toolkit"
LOCAL_SKILLS="scan-cmake tool-link-checker scan-op-list scan-ut-test fixer-broken-link tool-reports-to-issue scan-op-api-list scan-ut-analysis scan-examples-analysis scan-repo-docs scan-examples-test"
EXTERNAL_SKILL_DIRS="cann-error-code-standard:ops ops-error-code-remediation:ops gitcode-toolkit:infra"
OVERLAY_DIRS="commands scripts templates config"
SKILL_COUNT=14

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PLUGIN_ROOT="$SCRIPT_DIR"
LOCAL_SKILL_ROOT="$PLUGIN_ROOT/.opencode/skills"
OVERLAY_ROOT_SRC="$PLUGIN_ROOT/.opencode"
SKILLS_REPO_ARG=""

external_skill_dir() {
  local skill="$1" domain="$2" search_root parent_root
  if [ -f "$PLUGIN_ROOT/skills/$skill/SKILL.md" ]; then
    echo "$PLUGIN_ROOT/skills/$skill"
    return 0
  fi
  if [ -n "$SKILLS_REPO_ARG" ]; then
    if [ -f "$SKILLS_REPO_ARG/$domain/$skill/SKILL.md" ]; then
      echo "$SKILLS_REPO_ARG/$domain/$skill"
      return 0
    fi
    return 1
  fi
  search_root="$PLUGIN_ROOT"
  while true; do
    if [ -f "$search_root/vendor/cannbot-skills/$domain/$skill/SKILL.md" ]; then
      echo "$search_root/vendor/cannbot-skills/$domain/$skill"
      return 0
    fi
    parent_root="$(dirname "$search_root")"
    [ "$parent_root" != "$search_root" ] || break
    search_root="$parent_root"
  done
  return 1
}

has_local_skills() {
  local skill
  for skill in $LOCAL_SKILLS; do
    [ -f "$1/$skill/SKILL.md" ] || return 1
  done
}

has_overlay_dirs() {
  local d
  for d in $OVERLAY_DIRS; do
    [ -d "$1/$d" ] || return 1
  done
}

show_help() {
  cat <<'EOF'
Ops QA Suite 插件安装器

用法：
  init.sh project [opencode|claude|trae|cursor|copilot|codearts] [install_path] [--skills-repo <path>]

参数：
  project       项目级安装（本插件以目标项目为运行单元，仅支持 project 级）
  tool          目标 Agent 工具，默认 opencode
  install_path  目标项目目录；建议传绝对路径，省略时使用当前目录
  --skills-repo 指定本地 cannbot-skills 仓路径；cann-error-code-standard、
                ops-error-code-remediation、gitcode-toolkit 三个共享 Skill 从
                该仓 ops/、infra/ 安装
EOF
}

TOOL="opencode"
INSTALL_PATH="$PWD"

while [ "$#" -gt 0 ]; do
  arg="$1"
  case "$arg" in
    --help|-h) show_help; exit 0 ;;
    --skills-repo)
      if [ "$#" -lt 2 ] || [ -z "$2" ] || [[ "$2" == --* ]]; then
        echo "--skills-repo 需要本地 cannbot-skills 仓路径" >&2
        exit 2
      fi
      SKILLS_REPO_ARG="$2"
      shift
      ;;
    project) ;;
    global) echo "ops-qa-suite 以目标项目为运行单元（.opencode 覆盖层与 reports 输出均在项目内），仅支持 project 级安装" >&2; exit 2 ;;
    opencode|claude|trae|cursor|copilot|codearts) TOOL="$arg" ;;
    codex|dsh) echo "此独立脚本不支持 $arg，请使用 README 中的统一安装器" >&2; exit 2 ;;
    --*) echo "未知参数：$arg" >&2; exit 2 ;;
    *) INSTALL_PATH="$arg" ;;
  esac
  shift
done

# Validate every Skill and overlay asset before touching the target.
if ! has_local_skills "$LOCAL_SKILL_ROOT"; then
  echo "插件目录不完整：缺少 .opencode/skills/ 下完整的 11 个本地 Skill。" >&2
  exit 1
fi
if ! has_overlay_dirs "$OVERLAY_ROOT_SRC"; then
  echo "插件目录不完整：缺少 .opencode/ 下的 commands、scripts、templates、config 覆盖层资产。" >&2
  exit 1
fi
if [ ! -f "$PLUGIN_ROOT/AGENTS.md" ]; then
  echo "插件目录不完整：缺少 AGENTS.md" >&2
  exit 1
fi
declare -A EXTERNAL_SOURCES=()
for entry in $EXTERNAL_SKILL_DIRS; do
  skill="${entry%%:*}"
  domain="${entry##*:}"
  source_dir="$(external_skill_dir "$skill" "$domain")" || {
    echo "缺少共享 Skill：$skill（cannbot-skills $domain/ 下）。" >&2
    echo "请初始化 vendor/cannbot-skills，或使用 --skills-repo <本地仓路径>；发布包自带 skills/ 时优先使用。" >&2
    exit 1
  }
  EXTERNAL_SOURCES["$skill"]="$source_dir"
done

mkdir -p "$INSTALL_PATH"
PROJECT_ROOT="$(cd "$INSTALL_PATH" && pwd)"

if [ "$TOOL" = "opencode" ]; then
  CONFIG_ROOT="$PROJECT_ROOT/.opencode"
elif [ "$TOOL" = "claude" ]; then
  CONFIG_ROOT="$PROJECT_ROOT/.claude"
elif [ "$TOOL" = "trae" ]; then
  CONFIG_ROOT="$PROJECT_ROOT/.trae"
elif [ "$TOOL" = "cursor" ]; then
  CONFIG_ROOT="$PROJECT_ROOT/.cursor"
elif [ "$TOOL" = "copilot" ]; then
  CONFIG_ROOT="$PROJECT_ROOT/.github"
elif [ "$TOOL" = "codearts" ]; then
  CONFIG_ROOT="$PROJECT_ROOT/.codeartsdoer"
fi
OVERLAY_ROOT="$PROJECT_ROOT/.opencode"

if [ "$TOOL" = "claude" ]; then CONTEXT_FILE="CLAUDE.md"; else CONTEXT_FILE="AGENTS.md"; fi

COLLISIONS=0
FAILED_LINKS=0
safe_link() {
  local src="$1" dst="$2" owned_root="$3" current
  if [ -L "$dst" ]; then
    current="$(readlink -f "$dst" 2>/dev/null || true)"
    case "$current" in
      "$owned_root"/*) ;;
      *) echo "警告：$dst 已链接到其他位置，将替换为 Ops QA Suite 版本" >&2; COLLISIONS=$((COLLISIONS + 1)) ;;
    esac
    rm -f "$dst"
  elif [ -e "$dst" ]; then
    echo "错误：$dst 是真实文件或目录，为避免覆盖已跳过；请先手动处理" >&2
    COLLISIONS=$((COLLISIONS + 1))
    FAILED_LINKS=$((FAILED_LINKS + 1))
    return 1
  fi
  if ! ln -sfn "$src" "$dst"; then
    FAILED_LINKS=$((FAILED_LINKS + 1))
    return 1
  fi
}

mkdir -p "$CONFIG_ROOT/skills" "$OVERLAY_ROOT"
installed_skills=""
installed_count=0
for skill in $LOCAL_SKILLS; do
  if safe_link "$(realpath "$LOCAL_SKILL_ROOT/$skill")" "$CONFIG_ROOT/skills/$skill" "$(realpath "$LOCAL_SKILL_ROOT")"; then
    installed_skills="$installed_skills\"$skill\","
    installed_count=$((installed_count + 1))
  fi
done
for entry in $EXTERNAL_SKILL_DIRS; do
  skill="${entry%%:*}"
  if safe_link "$(realpath "${EXTERNAL_SOURCES[$skill]}")" "$CONFIG_ROOT/skills/$skill" "$(realpath "${EXTERNAL_SOURCES[$skill]}")"; then
    installed_skills="$installed_skills\"$skill\","
    installed_count=$((installed_count + 1))
  fi
done

overlay_count=0
for d in $OVERLAY_DIRS; do
  if safe_link "$(realpath "$OVERLAY_ROOT_SRC/$d")" "$OVERLAY_ROOT/$d" "$(realpath "$OVERLAY_ROOT_SRC")"; then
    overlay_count=$((overlay_count + 1))
  fi
done

if safe_link "$(realpath "$PLUGIN_ROOT/AGENTS.md")" "$CONFIG_ROOT/$CONTEXT_FILE" "$(realpath "$PLUGIN_ROOT")"; then
  context_status="installed"
else
  context_status="skipped"
fi

installed_skills="${installed_skills%,}"
if [ "$FAILED_LINKS" -eq 0 ]; then install_status="complete"; else install_status="partial"; fi
cat > "$CONFIG_ROOT/cannbot-manifest.json" <<EOF
{
  "brand": "$BRAND",
  "version": "$VERSION",
  "team": "$PLUGIN",
  "level": "project",
  "tool": "$TOOL",
  "status": "$install_status",
  "context_status": "$context_status",
  "installed_skills": [$installed_skills],
  "installed_agents": [],
  "brand_dir": "$CONFIG_ROOT",
  "install_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

if [ "$FAILED_LINKS" -eq 0 ]; then
  echo "Ops QA Suite $VERSION 安装完成"
else
  echo "Ops QA Suite $VERSION 安装未完成：$FAILED_LINKS 项失败，请处理冲突后重试" >&2
fi
echo "  配置目录：$CONFIG_ROOT"
echo "  Skills：$installed_count/$SKILL_COUNT"
echo "  覆盖层：.opencode/（$overlay_count/$OVERLAY_DIRS 个目录）"
echo "  主配置：$CONTEXT_FILE ($context_status)"
if [ "$COLLISIONS" -gt 0 ]; then echo "  冲突：$COLLISIONS（请检查上方警告）"; fi
if [ "$FAILED_LINKS" -gt 0 ]; then exit 1; fi
