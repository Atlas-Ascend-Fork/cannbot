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
PLUGIN="shmem-ops-generator"
VERSION="0.1.0"
INCLUDED_SKILLS="shmem-ops-dev shmem-ops-design shmem-ops-testcase-gen shmem-ops-code-gen shmem-ops-compile-debug shmem-ops-correctness-eval shmem-ops-code-review shmem-ops-torch-bind shmem-ops-performance-eval shmem-ops-performance-optim"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PLUGIN_ROOT="$SCRIPT_DIR"
LOCAL_SKILL_ROOT="$PLUGIN_ROOT/skills"
SKILLS_REPO_ARG=""

has_required_skills() {
  local skill
  for skill in $INCLUDED_SKILLS; do
    [ -f "$1/$skill/SKILL.md" ] || return 1
  done
}

show_help() {
  cat <<'EOF'
SHMEM Ops 插件安装器

用法：
  init.sh [project|global] [opencode|claude|trae|cursor|copilot|codearts] [install_path] [--skills-repo <path>]

参数：
  project       项目级安装（默认）
  global        全局安装
  tool          目标 Agent 工具，默认 opencode
  install_path  项目级安装的目标项目目录；建议传绝对路径，省略时使用当前目录
  --skills-repo 指定本地 cannbot-skills 仓路径；从 community/ops/ 安装 SHMEM Skills
EOF
}

LEVEL="project"
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
    project|global) LEVEL="$arg" ;;
    opencode|claude|trae|cursor|copilot|codearts) TOOL="$arg" ;;
    codex|dsh) echo "此独立脚本不支持 $arg，请使用 README 中的统一安装器" >&2; exit 2 ;;
    --*) echo "未知参数：$arg" >&2; exit 2 ;;
    *) INSTALL_PATH="$arg" ;;
  esac
  shift
done

if [ -n "$SKILLS_REPO_ARG" ]; then
  LOCAL_SKILL_ROOT="$SKILLS_REPO_ARG/community/ops"
elif ! has_required_skills "$LOCAL_SKILL_ROOT"; then
  search_root="$PLUGIN_ROOT"
  while true; do
    if has_required_skills "$search_root/vendor/cannbot-skills/community/ops"; then
      LOCAL_SKILL_ROOT="$search_root/vendor/cannbot-skills/community/ops"
      break
    fi
    parent_root="$(dirname "$search_root")"
    [ "$parent_root" != "$search_root" ] || break
    search_root="$parent_root"
  done
fi

if ! has_required_skills "$LOCAL_SKILL_ROOT"; then
  echo "缺少完整的 SHMEM Skills：需要 cannbot-skills/community/ops/ 下的全部 10 个 shmem-ops-* Skill。" >&2
  echo "请初始化 vendor/cannbot-skills 并检出包含迁移的版本，或使用 --skills-repo <本地仓路径>；发布包需自带完整 skills/。" >&2
  exit 1
fi
if [ ! -f "$PLUGIN_ROOT/AGENTS.md" ]; then
  echo "插件目录不完整：缺少 AGENTS.md" >&2
  exit 1
fi

# Validate the whole Skill set before creating or replacing any installation.
for skill in $INCLUDED_SKILLS; do
  if [ ! -f "$LOCAL_SKILL_ROOT/$skill/SKILL.md" ]; then
    echo "错误：插件缺少 skill：$skill" >&2
    exit 1
  fi
done

if [ "$LEVEL" = "global" ]; then
  if [ "$TOOL" = "opencode" ]; then
    CONFIG_ROOT="$HOME/.config/opencode"
  elif [ "$TOOL" = "claude" ]; then
    CONFIG_ROOT="$HOME/.claude"
  elif [ "$TOOL" = "trae" ]; then
    if [ -d "$HOME/.traecli" ]; then CONFIG_ROOT="$HOME/.traecli"; else CONFIG_ROOT="$HOME/.trae"; fi
  elif [ "$TOOL" = "cursor" ]; then
    CONFIG_ROOT="$HOME/.cursor"
  elif [ "$TOOL" = "copilot" ]; then
    CONFIG_ROOT="$HOME/.copilot"
  elif [ "$TOOL" = "codearts" ]; then
    CONFIG_ROOT="$HOME/.codeartsdoer"
  fi
else
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
fi

if [ "$TOOL" = "claude" ]; then CONTEXT_FILE="CLAUDE.md"; else CONTEXT_FILE="AGENTS.md"; fi

COLLISIONS=0
FAILED_LINKS=0
safe_link() {
  local src="$1" dst="$2" owned_root="$3" current
  if [ -L "$dst" ]; then
    current="$(readlink -f "$dst" 2>/dev/null || true)"
    case "$current" in
      "$owned_root"/*) ;;
      *) echo "警告：$dst 已链接到其他位置，将替换为 SHMEM Ops 版本" >&2; COLLISIONS=$((COLLISIONS + 1)) ;;
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

mkdir -p "$CONFIG_ROOT/skills"
installed_skills=""
installed_count=0
for skill in $INCLUDED_SKILLS; do
  source_dir="$LOCAL_SKILL_ROOT/$skill"
  if safe_link "$(realpath "$source_dir")" "$CONFIG_ROOT/skills/$skill" "$(realpath "$LOCAL_SKILL_ROOT")"; then
    installed_skills="$installed_skills\"$skill\","
    installed_count=$((installed_count + 1))
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
  "level": "$LEVEL",
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
  echo "SHMEM Ops $VERSION 安装完成"
else
  echo "SHMEM Ops $VERSION 安装未完成：$FAILED_LINKS 项失败，请处理冲突后重试" >&2
fi
echo "  配置目录：$CONFIG_ROOT"
echo "  Skills：$installed_count/10"
echo "  主配置：$CONTEXT_FILE ($context_status)"
if [ "$COLLISIONS" -gt 0 ]; then echo "  冲突：$COLLISIONS（请检查上方警告）"; fi
if [ "$FAILED_LINKS" -gt 0 ]; then exit 1; fi
