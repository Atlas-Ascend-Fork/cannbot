#!/bin/bash
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

set -e

# --- Color & output helpers ---
if [ -t 1 ]; then
  GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'
  CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
else
  GREEN=''; YELLOW=''; RED=''; CYAN=''; BOLD=''; DIM=''; NC=''
fi

ok()   { echo -e "  ${DIM}${GREEN}✓${NC}${DIM} $*${NC}"; }
warn() { echo -e "  ${YELLOW}⚠${NC}${DIM} $*${NC}"; }
err()  { echo -e "  ${RED}✗${NC}${DIM} $*${NC}"; }
info() { echo -e "  ${DIM}${CYAN}→${NC}${DIM} $*${NC}"; }
step() { echo -e "${DIM}$*${NC}"; }

BRAND="cannbot"
VERSION="1.0.0"

# --- Plugin-specific filters ---
EXCLUDED_SKILL=""
EXCLUDED_PATTERNS=""
# Agent whitelist (single glob pattern) - uses local agents/
# 必须与 tests/unit/install/test-init-install.sh 的单 glob 检查兼容：
# 该测试用 [[ base == $pattern ]] 匹配 agents/*.md，不支持空格分隔多模式。
# 当前 agents/: lingxi-evo, lingxi-partial, ops-evo, ops-partial（均含连字符）
INCLUDED_AGENT_PATTERN="*-*"

show_banner() {
  echo ""
  echo -e "${CYAN}"
  cat << 'BANNER'
   ____    _    _   _ _   _ ____        _
  / ___|  / \  | \ | | \ | | __ )  ___ | |_
 | |     / _ \ |  \| |  \| |  _ \ / _ \| __|
 | |___ / ___ \| |\  | |\  | |_) | (_) | |_
  \____/_/   \_\_| \_|_| \_|____/ \___/ \__|

     ___  ___  ___   ___  _   _  ___ ___  ___
    / _ \| _ \/ __| | _ \ | | | || __| _ \/ __|
   | (_) |  _/\__ \ |  _/ | |_| || _||   /\__ \
    \___/|_|  |___/ |_|   \___/ |___|_|_\|___/
BANNER
  echo -e "${NC}"
  echo -e "  ${BOLD}Ascend C Ops Performance Evolution Team${NC}"
  echo ""
}

show_help() {
    cat << EOF
CANNBot - Ascend C Ops Performance Evolution Environment Installer

Usage: init.sh [level] [tool]

Arguments:
  level   - Installation level: "project" (default) or "global"
  tool    - Target tool: "opencode" (default), "claude", "trae", "cursor", or "codearts"

Options:
  --help                   - Show this help message
  --knowledge-root <dir>   - cannbot-knowledge 仓根（显式绑定，写入 <project>/.cannbot/knowledge.env）
  --knowledge-install      - 自动安装 cannbot-knowledge（默认已开启）
  --no-knowledge-install   - 关闭 knowledge 仓自动安装
  --knowledge-installer <path|url> - 指定知识仓安装脚本（本地路径或 URL）
  --knowledge-repo-url <url> - 指定 cannbot-knowledge 仓 URL（传给知识仓 install.sh）
  --skills-repo <dir>      - cannbot-skills 仓根（显式指定，优先于自动获取）
  --skills-install         - 自动获取 cannbot-skills（默认已开启）
  --no-skills-install      - 关闭 cannbot-skills 自动获取
  --skills-url <url>       - cannbot-skills 仓 URL（默认官方 GitCode）
  --skills-dir <dir>       - 自动克隆目标目录（默认 vendor/ 或 ~/.cannbot/repos/cannbot-skills）
  --offline                - 不访问网络；仅使用已有 --skills-repo / --knowledge-root
  --project <dir>          - 写入知识配置的项目根（默认当前目录）

默认行为：如果找不到 cannbot-skills，先尝试初始化 vendor/cannbot-skills 子模块，
失败则 git clone --depth 1 到 vendor/ 或 ~/.cannbot/repos/；如果找不到
cannbot-knowledge，则调用官方 install.sh 自动 clone/更新并绑定。全程无需手动
git clone，也无需逐步确认。

Examples:
  init.sh                      # Project-level, OpenCode
  init.sh project opencode     # Project-level, OpenCode
  init.sh global claude        # Global-level, Claude Code
  init.sh project claude       # Project-level, Claude Code
  init.sh project trae         # Project-level, Trae
  init.sh project cursor       # Project-level, Cursor
  init.sh global cursor        # Global-level, Cursor

Installation paths (CANNBot brand):
  OpenCode: .opencode/{skills,agents}/  (auto-discovered)
  Claude:   .claude/{skills,agents}/    (per-skill symlinks auto-created)
  Trae:     .trae/{skills,agents}/      (symlinks, project-level only)
  Cursor:   .cursor/{skills,agents}/    (per-skill symlinks auto-created)

After installation, launch directly:
  OpenCode: opencode
  Claude:   claude
  Trae:     通过 CLI 或 IDE 启动
  Cursor:   通过 Cursor IDE 启动
EOF
}

LEVEL="project"
TOOL="opencode"
KNOWLEDGE_ROOT_ARG=""
# 默认自动安装 knowledge 仓；--no-knowledge-install 可关闭
KNOWLEDGE_INSTALL="1"
KNOWLEDGE_INSTALLER="https://raw.gitcode.com/cann/cannbot-knowledge/raw/master/install.sh"
KNOWLEDGE_REPO_URL=""
# 默认自动获取 skills 仓；--no-skills-install 可关闭
SKILLS_INSTALL="1"
SKILLS_URL="https://gitcode.com/cann/cannbot-skills.git"
SKILLS_DIR=""
SKILLS_REPO_ARG=""
PROJECT_ROOT_ARG="$PWD"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$SCRIPT_DIR"
# Agents: use local agents/ directory (migrated with plugin)
LOCAL_AGENT_ROOT="$PLUGIN_ROOT/agents"

# --- Parse arguments first: --skills-repo / --knowledge-root must take effect before repo lookup ---
while [ $# -gt 0 ]; do
    case "$1" in
        --help)             show_help; exit 0 ;;
        global|project)     LEVEL="$1"; shift ;;
        opencode|claude|trae|cursor|codearts) TOOL="$1"; shift ;;
        --knowledge-root)   KNOWLEDGE_ROOT_ARG="$2"; shift 2 ;;
        --knowledge-install) KNOWLEDGE_INSTALL=1; shift ;;
        --no-knowledge-install) KNOWLEDGE_INSTALL=0; shift ;;
        --knowledge-installer) KNOWLEDGE_INSTALLER="$2"; shift 2 ;;
        --knowledge-repo-url) KNOWLEDGE_REPO_URL="$2"; shift 2 ;;
        --skills-install)   SKILLS_INSTALL=1; shift ;;
        --no-skills-install) SKILLS_INSTALL=0; shift ;;
        --skills-url)       SKILLS_URL="$2"; shift 2 ;;
        --skills-dir)       SKILLS_DIR="$2"; shift 2 ;;
        --skills-repo)      SKILLS_REPO_ARG="$2"; shift 2 ;;
        --offline)          SKILLS_INSTALL=0; KNOWLEDGE_INSTALL=0; shift ;;
        --project)          PROJECT_ROOT_ARG="$2"; shift 2 ;;
        --knowledge-root=*) KNOWLEDGE_ROOT_ARG="${1#*=}"; shift ;;
        --knowledge-installer=*) KNOWLEDGE_INSTALLER="${1#*=}"; shift ;;
        --knowledge-repo-url=*) KNOWLEDGE_REPO_URL="${1#*=}"; shift ;;
        --skills-url=*)     SKILLS_URL="${1#*=}"; shift ;;
        --skills-dir=*)     SKILLS_DIR="${1#*=}"; shift ;;
        --skills-repo=*)    SKILLS_REPO_ARG="${1#*=}"; shift ;;
        --project=*)        PROJECT_ROOT_ARG="${1#*=}"; shift ;;
        *)  echo "Error: Unknown argument '$1'. Valid: global, project, opencode, claude, trae, cursor, codearts, --knowledge-root, --knowledge-install, --no-knowledge-install, --knowledge-installer, --knowledge-repo-url, --skills-install, --no-skills-install, --skills-url, --skills-dir, --skills-repo, --offline, --project, --help." >&2
            exit 1 ;;
    esac
done

# Determine config root directory
if [ "$LEVEL" = "global" ]; then
    if [ "$TOOL" = "opencode" ]; then
        CONFIG_ROOT="$HOME/.config/opencode"
    elif [ "$TOOL" = "trae" ]; then
        echo "Error: Global installation is not supported for Trae. Use project-level instead."
        exit 1
    elif [ "$TOOL" = "cursor" ]; then
        CONFIG_ROOT="$HOME/.cursor"
    elif [ "$TOOL" = "codearts" ]; then
        CONFIG_ROOT="$HOME/.codeartsdoer"
    else
        CONFIG_ROOT="$HOME/.claude"
    fi
else
    if [ "$TOOL" = "opencode" ]; then
        CONFIG_ROOT="$PLUGIN_ROOT/.opencode"
    elif [ "$TOOL" = "trae" ]; then
        CONFIG_ROOT="$PLUGIN_ROOT/.trae"
    elif [ "$TOOL" = "cursor" ]; then
        CONFIG_ROOT="$PLUGIN_ROOT/.cursor"
    elif [ "$TOOL" = "codearts" ]; then
        CONFIG_ROOT="$PLUGIN_ROOT/.codeartsdoer"
    else
        CONFIG_ROOT="$PLUGIN_ROOT/.claude"
    fi
fi

CANNBOT_DIR="$CONFIG_ROOT"

# Clean up legacy cannbot subdirectory from previous installations
if [ -e "$CONFIG_ROOT/$BRAND" ] || [ -L "$CONFIG_ROOT/$BRAND" ]; then
    rm -rf "$CONFIG_ROOT/$BRAND"
fi
# OpenCode: also clean legacy teams link
if [ "$TOOL" = "opencode" ] && [ -L "$CONFIG_ROOT/teams" ]; then
    rm -f "$CONFIG_ROOT/teams"
fi

show_banner
echo "  Tool:      $TOOL"
echo "  Level:     $LEVEL"
echo "  Path:      $CONFIG_ROOT"
echo ""

# --- Skill dependencies (needed before repo completeness checks) ---
if [ -f "$PLUGIN_ROOT/AGENTS.md" ]; then
  INCLUDED_SKILLS=$(python3 -c "
import re, sys
from pathlib import Path

plugin_root = Path('$PLUGIN_ROOT')
all_skills = set()

md_files = [plugin_root / 'AGENTS.md']
agents_dir = plugin_root / 'agents'
if agents_dir.is_dir():
    md_files.extend(sorted(agents_dir.glob('*.md')))

for md_file in md_files:
    if not md_file.is_file():
        continue
    content = md_file.read_text()
    m = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if m:
        fm = m.group(1)
        sm = re.search(r'^skills:\n((?:\s+-\s.+\n?)*)', fm, re.MULTILINE)
        if sm:
            all_skills.update(re.findall(r'^\s+-\s+(.+)$', sm.group(0), re.MULTILINE))

print(' '.join(sorted(all_skills)))
" 2>/dev/null)
  if [ -z "$INCLUDED_SKILLS" ]; then
    warn "Failed to parse skill dependencies from AGENTS.md, using fallback"
    INCLUDED_SKILLS="npu-arch ops-profiling ascendc-ops-evaluation ascendc-evolution-report ascendc-evolution-knowledge ascendc-evolution-strategies ascendc-evolution-world-model tilelang2ascend-translator"
  fi
else
  err "AGENTS.md not found at $PLUGIN_ROOT/AGENTS.md"
  exit 1
fi

# --- Skill repo resolution / auto-fetch ---
# 三仓分离后，plugin 不再假定用户已经手工检出 cannbot-skills。
# 解析顺序：--skills-repo > vendor/cannbot-skills 子模块 > 同级 cannbot-skills > 自动 clone。
# 关键：子模块可能钉在旧 commit（缺少 ascendc-evolution-* 等插件 skill），必须按
# AGENTS.md 声明的 skill 列表校验完整性，不完整就跳过并改用完整检出/克隆。
fetch_repo() {
    local url="$1" target="$2"
    if [ -e "$target" ] && [ ! -d "$target" ]; then
        err "目标路径存在但不是目录：$target"
        return 1
    fi
    if [ -d "$target/.git" ]; then
        ok "复用已有检出：$target"
        return 0
    fi
    if [ -d "$target" ] && [ -n "$(ls -A "$target" 2>/dev/null)" ]; then
        err "目标目录非空且不是 git 仓库：$target"
        return 1
    fi
    mkdir -p "$(dirname "$target")" || return 1
    info "git clone --depth 1 $url -> $target"
    GIT_TERMINAL_PROMPT=0 git clone --depth 1 --single-branch "$url" "$target"
}

skills_repo_has_required() {
    local root="$1" missing="" name
    for name in $INCLUDED_SKILLS; do
        if [ -d "$root/community/ops/$name" ] || [ -d "$root/ops/$name" ]; then
            :
        else
            missing="$missing $name"
        fi
    done
    if [ -n "$missing" ]; then
        warn "skills 仓不完整（缺少：$missing）：$root"
        return 1
    fi
    return 0
}

ensure_skills_repo() {
    local repo_root target
    repo_root="$(cd "$PLUGIN_ROOT/../.." 2>/dev/null && pwd || true)"

    if [ -n "$SKILLS_REPO_ARG" ]; then
        SKILLS_REPO_ROOT="$SKILLS_REPO_ARG"
        if ! skills_repo_has_required "$SKILLS_REPO_ROOT"; then
            err "指定的 --skills-repo 不完整：$SKILLS_REPO_ROOT"
            return 1
        fi
    else
        # 1) 先看 vendor 子模块 / 同级检出，但只接受完整仓。
        if [ -d "$PLUGIN_ROOT/../../vendor/cannbot-skills/community/ops" ]; then
            if skills_repo_has_required "$PLUGIN_ROOT/../../vendor/cannbot-skills"; then
                SKILLS_REPO_ROOT="$PLUGIN_ROOT/../../vendor/cannbot-skills"
            fi
        fi
        if [ -z "${SKILLS_REPO_ROOT:-}" ] && [ -d "$PLUGIN_ROOT/../../../cannbot-skills/community/ops" ]; then
            if skills_repo_has_required "$PLUGIN_ROOT/../../../cannbot-skills"; then
                SKILLS_REPO_ROOT="$(cd "$PLUGIN_ROOT/../../../cannbot-skills" && pwd)"
            fi
        fi

        # 2) 仍缺失且允许自动获取：先尝试 submodule，再浅克隆。
        if [ -z "${SKILLS_REPO_ROOT:-}" ] && [ "$SKILLS_INSTALL" = "1" ]; then
            if [ -n "$repo_root" ] && [ -f "$repo_root/.gitmodules" ] && grep -q 'vendor/cannbot-skills' "$repo_root/.gitmodules" 2>/dev/null; then
                step "[0/4] Initializing cannbot-skills submodule..."
                if GIT_TERMINAL_PROMPT=0 git -C "$repo_root" submodule update --init --recursive vendor/cannbot-skills >/dev/null 2>&1; then
                    if skills_repo_has_required "$repo_root/vendor/cannbot-skills"; then
                        SKILLS_REPO_ROOT="$repo_root/vendor/cannbot-skills"
                        ok "cannbot-skills submodule ready: $SKILLS_REPO_ROOT"
                    else
                        warn "vendor/cannbot-skills 子模块版本过旧，缺少插件所需 skill；改用完整检出/克隆"
                    fi
                fi
            fi
            if [ -z "${SKILLS_REPO_ROOT:-}" ]; then
                target="$SKILLS_DIR"
                if [ -z "$target" ]; then
                    if [ -n "$repo_root" ] && [ -d "$repo_root/vendor" ] && [ -w "$repo_root/vendor" ] && [ ! -f "$repo_root/.gitmodules" ]; then
                        target="$repo_root/vendor/cannbot-skills"
                    else
                        target="${HOME:?}/.cannbot/repos/cannbot-skills"
                    fi
                fi
                step "[0/4] Fetching cannbot-skills -> $target ..."
                if fetch_repo "$SKILLS_URL" "$target"; then
                    if skills_repo_has_required "$target"; then
                        SKILLS_REPO_ROOT="$target"
                    else
                        err "克隆的 cannbot-skills 不完整（缺少插件所需 skill）：$target"
                        return 1
                    fi
                else
                    err "无法获取 cannbot-skills：$SKILLS_URL"
                    return 1
                fi
            fi
        fi
    fi

    if [ -z "${SKILLS_REPO_ROOT:-}" ]; then
        err "无法定位可用的 cannbot-skills 仓"
        echo "       可用 --skills-repo <本地路径> 指定已有完整检出；或检查网络/代理后重跑（--skills-url 可换源）。" >&2
        return 1
    fi
    COMMUNITY_SKILL_ROOT="$SKILLS_REPO_ROOT/community/ops"
    SHARED_SKILL_ROOT="$SKILLS_REPO_ROOT/ops"
    # 去重后的 skill 源目录列表（community/ops 优先，避免与 ops/ 同名时被覆盖）
    SKILL_SOURCE_DIRS="$COMMUNITY_SKILL_ROOT $SHARED_SKILL_ROOT"
}

ensure_skills_repo || exit $?

# --- Knowledge repo binding / auto-install (cannbot-knowledge) ---
# 显式绑定优先；缺失时默认调用知识仓 install.sh 自动 clone/更新并绑定。
# 完全未找到时告警但不阻塞 skill 安装；显式 --knowledge-root 无效 => exit 2。
KNOWLEDGE_HELPER="$COMMUNITY_SKILL_ROOT/ascendc-evolution-strategies/scripts/knowledge_root.py"

bind_knowledge() {
    local kr_args=(--project "$PROJECT_ROOT_ARG" --mode consumer --write-env)
    [ -n "$KNOWLEDGE_ROOT_ARG" ] && kr_args+=(--knowledge-root "$KNOWLEDGE_ROOT_ARG")
    python3 "$KNOWLEDGE_HELPER" "${kr_args[@]}"
}

install_knowledge() {
    local installer="$1" target="$2" tmp_script="" tmp_project="" extra=()
    # 知识仓安装器不支持 codearts；此时直接返回让调用方走 clone+bind 兜底。
    case "$TOOL" in
        claude|opencode|trae|cursor) ;;
        *) return 1 ;;
    esac
    if [[ "$installer" =~ ^https?:// ]]; then
        tmp_script="$(mktemp -t cannbot-knowledge-install.XXXXXX.sh)" || return 1
        if command -v curl >/dev/null 2>&1; then
            curl -fsSL -o "$tmp_script" "$installer" || { rm -f "$tmp_script"; return 1; }
        elif command -v wget >/dev/null 2>&1; then
            wget -qO "$tmp_script" "$installer" || { rm -f "$tmp_script"; return 1; }
        else
            rm -f "$tmp_script"; return 1
        fi
        installer="$tmp_script"
    fi
    if [ ! -f "$installer" ]; then
        rm -f "$tmp_script"; return 1
    fi
    # 插件项目的 CLAUDE.md 是 -> AGENTS.md 的软链，知识仓 install.sh 会拒绝修改
    # 软链 prompt；用临时项目根跑安装，只保留知识仓 clone/索引/依赖，丢弃临时 prompt。
    tmp_project="$(mktemp -d -t cannbot-knowledge-project.XXXXXX)" || { rm -f "$tmp_script"; return 1; }
    [ -n "$KNOWLEDGE_REPO_URL" ] && extra+=(--repository-url "$KNOWLEDGE_REPO_URL")
    local install_args=(--knowledge-root "$target")
    grep -q -- '--skip-resources' "$installer" 2>/dev/null && install_args+=(--skip-resources)
    GIT_TERMINAL_PROMPT=0 bash "$installer" "$TOOL" "$tmp_project" consumer \
        "${install_args[@]}" "${extra[@]}"
    local rc=$?
    rm -rf "$tmp_project"
    rm -f "$tmp_script"
    return $rc
}

fetch_knowledge_repo() {
    local target="$1" url="${KNOWLEDGE_REPO_URL:-https://gitcode.com/cann/cannbot-knowledge.git}"
    if [ -d "$target/.git" ]; then
        ok "复用已有检出：$target"
        return 0
    fi
    if [ -e "$target" ] && [ ! -d "$target" ]; then
        err "目标路径存在但不是目录：$target"
        return 1
    fi
    if [ -d "$target" ] && [ -n "$(ls -A "$target" 2>/dev/null)" ]; then
        err "目标目录非空且不是 git 仓库：$target"
        return 1
    fi
    mkdir -p "$(dirname "$target")" || return 1
    info "git clone --depth 1 $url -> $target"
    GIT_TERMINAL_PROMPT=0 git clone --depth 1 --single-branch "$url" "$target"
}

build_knowledge_index() {
    local root="$1" index="$1/.agents/skills/knowledge-query/scripts/knowledge_index.py"
    [ -f "$index" ] || return 0
    step "[0/4] Building knowledge search index..."
    if python3 "$index" --knowledge-root "$root" build >/dev/null 2>&1; then
        ok "knowledge index ready"
    else
        warn "知识索引构建失败；可运行：python3 $index --knowledge-root $root build"
    fi
}

ensure_knowledge() {
    if [ ! -f "$KNOWLEDGE_HELPER" ]; then
        warn "knowledge_root.py 不可用（skills 仓未就绪），跳过知识配置"
        return 0
    fi
    step "[0/4] Binding knowledge repository..."
    if bind_knowledge; then
        ok "knowledge root -> $PROJECT_ROOT_ARG/.cannbot/knowledge.env"
        return 0
    fi
    if [ -n "$KNOWLEDGE_ROOT_ARG" ] && [ "$KNOWLEDGE_INSTALL" != "1" ]; then
        err "指定的 --knowledge-root 无效：$KNOWLEDGE_ROOT_ARG"
        return 2
    fi
    if [ "$KNOWLEDGE_INSTALL" = "1" ]; then
        local target="${KNOWLEDGE_ROOT_ARG:-${HOME:?}/.cannbot/cannbot-knowledge}"
        step "[0/4] Fetching/installing cannbot-knowledge -> $target ..."
        if install_knowledge "$KNOWLEDGE_INSTALLER" "$target"; then
            KNOWLEDGE_ROOT_ARG="$target"
            if bind_knowledge; then
                ok "knowledge root -> $PROJECT_ROOT_ARG/.cannbot/knowledge.env（新安装）"
                return 0
            fi
            warn "知识仓安装完成但绑定失败，请检查 $target 布局"
            return 0
        fi
        warn "官方知识安装脚本失败，尝试直接 git clone 知识仓 ..."
        if fetch_knowledge_repo "$target"; then
            KNOWLEDGE_ROOT_ARG="$target"
            if bind_knowledge; then
                build_knowledge_index "$target"
                ok "knowledge root -> $PROJECT_ROOT_ARG/.cannbot/knowledge.env（直接克隆）"
                return 0
            fi
            warn "知识仓克隆完成但绑定失败，请检查 $target 布局"
            return 0
        fi
        warn "知识仓自动安装失败（installer=$KNOWLEDGE_INSTALLER 或 git clone）；可手动安装后重跑 init.sh"
    else
        warn "未找到 cannbot-knowledge，跳过知识配置（可用 --knowledge-root 或 --knowledge-install）"
    fi
    return 0
}

ensure_knowledge
kr_rc=$?
[ "$kr_rc" -eq 0 ] || exit "$kr_rc"

# --- Step 0: Confirmation before installation ---
step "[0/4] Checking items to be installed..."

# Collect skills to install (from local skills/ + shared ops, dedup by name)
SKILLS_TO_INSTALL=""
SKILL_COUNT=0
_seen_skill_names=""
for src_root in $SKILL_SOURCE_DIRS; do
    [ -d "$src_root" ] || continue
    for skill_dir in "$src_root"/*/; do
        [ -d "$skill_dir" ] || continue
        name=$(basename "$skill_dir")
        echo "$INCLUDED_SKILLS" | tr ' ' '\n' | grep -qxF "$name" || continue
        [ -n "$EXCLUDED_SKILL" ] && [ "$name" = "$EXCLUDED_SKILL" ] && continue
        echo "$_seen_skill_names" | tr ' ' '\n' | grep -qxF "$name" && continue
        _seen_skill_names="$_seen_skill_names $name"
        SKILLS_TO_INSTALL="$SKILLS_TO_INSTALL $name"
        SKILL_COUNT=$((SKILL_COUNT + 1))
    done
done

# Collect agents to install (from local agents/)
AGENTS_TO_INSTALL=""
AGENT_COUNT=0
# 辅助函数：判断 agent 是否在白名单中（单个 glob pattern 匹配）
agent_in_whitelist() {
    local base="$1"
    [[ "$base" == $INCLUDED_AGENT_PATTERN ]]
}

# Translate agent markdown for OpenCode/Trae.
# Claude Code uses Agent(...) for subagent dispatch; OpenCode and Trae use task(...).
# Usage: translate_agent <source_path> <target_path> <tool>
translate_agent() {
    local src="$1"
    local dst="$2"
    local target_tool="$3"
    python3 - "$src" "$dst" "$target_tool" <<'PYEOF'
import sys
import re

src, dst, tool = sys.argv[1:4]

with open(src, 'r', encoding='utf-8') as f:
    content = f.read()

fm_match = re.match(r'^---\n(.*?)\n---\n?(.*)$', content, re.DOTALL)
if not fm_match:
    with open(dst, 'w', encoding='utf-8') as f:
        f.write(content)
    sys.exit(0)

fm_raw = fm_match.group(1)
body = fm_match.group(2)

# Parse frontmatter preserving order. Nested mappings (e.g. lingxi-partial's
# opencode-style `permission:` block) are collected as dicts so they survive
# the round-trip; scalar lists stay lists.
fm_items = []
i = 0
lines = fm_raw.split('\n')
while i < len(lines):
    line = lines[i]
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        i += 1
        continue
    if ':' in line:
        key, val = line.split(':', 1)
        key = key.strip()
        val = val.strip()
        if val == '':
            block_items = []
            i += 1
            while i < len(lines):
                sub = lines[i]
                if not sub.strip():
                    i += 1
                    continue
                if sub.strip().startswith('- '):
                    block_items.append(sub.strip()[2:])
                    i += 1
                    continue
                if sub.startswith((' ', '\t')) and ':' in sub:
                    sk, sv = sub.strip().split(':', 1)
                    block_items.append((sk.strip(), sv.strip()))
                    i += 1
                    continue
                break
            fm_items.append((key, block_items))
            continue
        else:
            fm_items.append((key, val))
    i += 1

# opencode's agent schema rejects unknown permission keys (external_directory
# is a CANNBot convention consumed by hooks, not by opencode) with
# "Configuration is invalid" at startup — drop them during conversion.
_OPENCODE_PERMISSION_KEYS = {
    'read', 'write', 'edit', 'bash', 'glob', 'grep', 'webfetch',
    'websearch', 'task', 'skill',
}

if tool == 'opencode':
    new_items = []
    for key, val in fm_items:
        if key == 'tools':
            if isinstance(val, list):
                tools_list = val
            else:
                tools_list = [t.strip() for t in val.split(',') if t.strip()]
            tool_map = {}
            for t in tools_list:
                if t.startswith('Agent(') and t.endswith(')'):
                    tool_map['task'] = 'true'
                else:
                    tool_map[t.lower()] = 'true'
            # Output as multi-line boolean map (OpenCode convention).
            sorted_tools = '\n'.join([f'  {k}: {v}' for k, v in sorted(tool_map.items())])
            new_items.append(('tools', sorted_tools))
        elif key == 'permission' and isinstance(val, list):
            filtered = [(k, v) for k, v in val
                        if isinstance(k, str) and k in _OPENCODE_PERMISSION_KEYS]
            if filtered:
                block = '\n'.join(f'  {k}: {v}' for k, v in filtered)
                new_items.append(('permission', block))
        elif key == 'permissionMode':
            if val == 'bypassPermissions':
                new_items.append(('permission', 'allow'))
            # Other permissionMode values are dropped.
        elif key == 'model' and val == 'inherit':
            # OpenCode expects an explicit model name; omit to use caller default.
            continue
        else:
            new_items.append((key, val))
    fm_lines = []
    for key, val in new_items:
        if isinstance(val, list):
            fm_lines.append(f'{key}:')
            for item in val:
                fm_lines.append(f'  - {item}')
        elif '\n' in str(val):
            fm_lines.append(f'{key}:')
            fm_lines.append(val)
        else:
            fm_lines.append(f'{key}: {val}')
    new_fm = '\n'.join(fm_lines)
    new_body = re.sub(r'\bAgent\s*\(', 'task(', body)

elif tool == 'trae':
    new_items = []
    for key, val in fm_items:
        if key == 'tools':
            if isinstance(val, list):
                tools_list = val
            else:
                tools_list = [t.strip() for t in val.split(',') if t.strip()]
            trae_tools = []
            seen_tools = set()
            for t in tools_list:
                if t.startswith('Agent(') and t.endswith(')'):
                    t_norm = 'task'
                else:
                    t_norm = t
                if t_norm not in seen_tools:
                    seen_tools.add(t_norm)
                    trae_tools.append(t_norm)
            new_items.append(('tools', ', '.join(trae_tools)))
        elif key == 'permission':
            # Trae frontmatter has no permission concept.
            continue
        elif key == 'permissionMode':
            # Trae frontmatter does not use permissionMode.
            continue
        elif key == 'model' and val == 'inherit':
            # Trae does not support 'inherit' model; omit to use IDE default.
            continue
        else:
            new_items.append((key, val))
    fm_lines = []
    for key, val in new_items:
        if isinstance(val, list):
            fm_lines.append(f'{key}:')
            for item in val:
                fm_lines.append(f'  - {item}')
        else:
            fm_lines.append(f'{key}: {val}')
    new_fm = '\n'.join(fm_lines)
    # Best-effort: Trae's subagent invocation is not documented, but task(...) is
    # the closest equivalent used by OpenCode and other runtimes.
    new_body = re.sub(r'\bAgent\s*\(', 'task(', body)
else:
    new_fm = fm_raw
    new_body = body

with open(dst, 'w', encoding='utf-8') as f:
    f.write('---\n')
    f.write(new_fm)
    f.write('\n---\n')
    f.write(new_body)
PYEOF
}

for agent_entry in "$LOCAL_AGENT_ROOT"/*; do
    [ -e "$agent_entry" ] || continue
    name=$(basename "$agent_entry")
    base="${name%.md}"
    agent_in_whitelist "$base" || continue
    AGENTS_TO_INSTALL="$AGENTS_TO_INSTALL $name"
    AGENT_COUNT=$((AGENT_COUNT + 1))
done

# Display installation plan
echo ""
echo -e "${BOLD}以下内容将被安装/替换：${NC}"
echo ""

if [ "$SKILL_COUNT" -gt 0 ]; then
    echo -e "${CYAN}Skills (${SKILL_COUNT} 项)：${NC}"
    for name in $SKILLS_TO_INSTALL; do
        target="$CANNBOT_DIR/skills/$name"
        if [ -e "$target" ] || [ -L "$target" ]; then
            echo -e "  ${YELLOW}$name${NC}"
        else
            echo -e "  ${GREEN}$name${NC}"
        fi
    done
    echo ""
fi

if [ "$AGENT_COUNT" -gt 0 ]; then
    echo -e "${CYAN}Agents (${AGENT_COUNT} 项)：${NC}"
    for name in $AGENTS_TO_INSTALL; do
        target="$CANNBOT_DIR/agents/$name"
        if [ -e "$target" ] || [ -L "$target" ]; then
            echo -e "  ${YELLOW}$name${NC}"
        else
            echo -e "  ${GREEN}$name${NC}"
        fi
    done
    echo ""
fi

echo -e "${CYAN}配置文件：${NC}"
if [ "$LEVEL" = "project" ]; then
    if [ "$TOOL" = "opencode" ] || [ "$TOOL" = "trae" ] || [ "$TOOL" = "cursor" ] || [ "$TOOL" = "codearts" ]; then
        config_target="$PWD/AGENTS.md"
    else
        config_target="$PWD/CLAUDE.md"
    fi
else
    if [ "$TOOL" = "opencode" ] || [ "$TOOL" = "trae" ] || [ "$TOOL" = "cursor" ] || [ "$TOOL" = "codearts" ]; then
        config_target="$CONFIG_ROOT/AGENTS.md"
    else
        config_target="$CONFIG_ROOT/CLAUDE.md"
    fi
fi
config_src="$PLUGIN_ROOT/AGENTS.md"
if { [ "$TOOL" = "opencode" ] || [ "$TOOL" = "trae" ] || [ "$TOOL" = "cursor" ] || [ "$TOOL" = "codearts" ]; } && [ "$LEVEL" = "project" ] && [ "$PLUGIN_ROOT" = "$PWD" ]; then
    echo -e "  ${GREEN}$(basename "$config_target")${NC} (已存在，无需操作)"
elif [ -e "$config_target" ] || [ -L "$config_target" ]; then
    echo -e "  ${YELLOW}$(basename "$config_target")${NC} (将被替换)"
else
    echo -e "  ${GREEN}$(basename "$config_target")${NC} (将创建)"
fi

echo ""
echo -e "${BOLD}${YELLOW}注意：仅替换上述白名单内的内容，不影响其他已存在的 skills/agents${NC}"
echo ""
ok "开始安装..."
echo ""

# --- Step 1: Create directory symlinks ---
step "[1/4] Setting up CANNBot directory..."
mkdir -p "$CANNBOT_DIR"

step1_summary=""
step1_warns=""
if [ "$TOOL" = "opencode" ]; then
    # OpenCode: per-item symlinks for skills (local skills/ + shared ops, whitelist filtered)
    mkdir -p "$CANNBOT_DIR/skills"
    # Pre-clean existing skill symlinks (only whitelist items)
    for src_root in $SKILL_SOURCE_DIRS; do
        [ -d "$src_root" ] || continue
        for skill_dir in "$src_root"/*/; do
            [ -d "$skill_dir" ] || continue
            name=$(basename "$skill_dir")
            echo "$INCLUDED_SKILLS" | tr ' ' '\n' | grep -qxF "$name" || continue
            target="$CANNBOT_DIR/skills/$name"
            [ -e "$target" ] || [ -L "$target" ] && rm -rf "$target"
        done
    done
    skill_count=0
    _seen_skill_names=""
    for src_root in $SKILL_SOURCE_DIRS; do
        [ -d "$src_root" ] || continue
        for skill_dir in "$src_root"/*/; do
            [ -d "$skill_dir" ] || continue
            name=$(basename "$skill_dir")
            echo "$INCLUDED_SKILLS" | tr ' ' '\n' | grep -qxF "$name" || continue
            [ -n "$EXCLUDED_SKILL" ] && [ "$name" = "$EXCLUDED_SKILL" ] && continue
            echo "$_seen_skill_names" | tr ' ' '\n' | grep -qxF "$name" && continue
            _seen_skill_names="$_seen_skill_names $name"
            ln -sfn "$(realpath "$skill_dir")" "$CANNBOT_DIR/skills/$name"
            skill_count=$((skill_count + 1))
        done
    done
    step1_summary="skills(${skill_count}) "

    # OpenCode: per-item symlinks for agents (from local agents/, whitelist filtered)
    mkdir -p "$CANNBOT_DIR/agents"
    for agent_entry in "$LOCAL_AGENT_ROOT"/*; do
        [ -e "$agent_entry" ] || continue
        name=$(basename "$agent_entry")
        base_name="${name%.md}"
        [[ "$base_name" != $INCLUDED_AGENT_PATTERN ]] && continue
        target="$CANNBOT_DIR/agents/$name"
        [ -e "$target" ] || [ -L "$target" ] && rm -rf "$target"
    done
    agent_count=0
    for agent_entry in "$LOCAL_AGENT_ROOT"/*; do
        [ -e "$agent_entry" ] || continue
        name=$(basename "$agent_entry")
        base_name="${name%.md}"
        [[ "$base_name" != $INCLUDED_AGENT_PATTERN ]] && continue
        translate_agent "$agent_entry" "$CANNBOT_DIR/agents/$name" opencode
        agent_count=$((agent_count + 1))
    done
    step1_summary="${step1_summary}agents(${agent_count}) "

    # OpenCode: per-item symlinks for hooks (from local hooks/)
    mkdir -p "$CANNBOT_DIR/hooks"
    for hook_entry in "$PLUGIN_ROOT/hooks"/*; do
        [ -e "$hook_entry" ] || continue
        name=$(basename "$hook_entry")
        target="$CANNBOT_DIR/hooks/$name"
        [ -e "$target" ] || [ -L "$target" ] && rm -rf "$target"
    done
    hook_count=0
    for hook_entry in "$PLUGIN_ROOT/hooks"/*; do
        [ -e "$hook_entry" ] || continue
        name=$(basename "$hook_entry")
        ln -sfn "$(realpath "$hook_entry")" "$CANNBOT_DIR/hooks/$name"
        hook_count=$((hook_count + 1))
    done
    step1_summary="${step1_summary}hooks(${hook_count})"
    ok "Linked: $step1_summary"
else
    # Trae/Claude/Cursor: create directories
    mkdir -p "$CONFIG_ROOT/skills" "$CONFIG_ROOT/agents" "$CONFIG_ROOT/hooks"
    ok "Prepared: skills/, agents/, hooks/"
fi
[ -n "$step1_warns" ] && echo -e "$step1_warns"

echo ""

# --- Step 2: Install config file (AGENTS.md / CLAUDE.md) ---
step "[2/4] Installing configuration..."

if [ "$LEVEL" = "project" ]; then
    if [ "$TOOL" = "opencode" ] || [ "$TOOL" = "trae" ] || [ "$TOOL" = "cursor" ] || [ "$TOOL" = "codearts" ]; then
        config_target="$PWD/AGENTS.md"
    else
        config_target="$PWD/CLAUDE.md"
    fi
else
    mkdir -p "$CONFIG_ROOT"
    if [ "$TOOL" = "opencode" ] || [ "$TOOL" = "trae" ] || [ "$TOOL" = "cursor" ] || [ "$TOOL" = "codearts" ]; then
        config_target="$CONFIG_ROOT/AGENTS.md"
    else
        config_target="$CONFIG_ROOT/CLAUDE.md"
    fi
fi

config_src="$PLUGIN_ROOT/AGENTS.md"

if { [ "$TOOL" = "opencode" ] || [ "$TOOL" = "trae" ] || [ "$TOOL" = "cursor" ] || [ "$TOOL" = "codearts" ]; } && [ "$LEVEL" = "project" ] && [ "$PLUGIN_ROOT" = "$PWD" ]; then
    ok "$(basename "$config_target") already in current directory"
else
    if [ "$LEVEL" = "global" ]; then
        [ -e "$config_target" ] || [ -L "$config_target" ] && rm -f "$config_target"
        PLUGIN_ROOT_ABS="$(realpath "$PLUGIN_ROOT")"
        ESCAPED_ROOT="$(echo "$PLUGIN_ROOT_ABS" | sed 's/#/\\#/g')"
        sed \
          -e "s#bash workflows/scripts/#bash ${ESCAPED_ROOT}/workflows/scripts/#g" \
          -e "s#](workflows/#](${ESCAPED_ROOT}/workflows/#g" \
          -e "s#\`workflows/#\`${ESCAPED_ROOT}/workflows/#g" \
          "$config_src" > "$config_target"
        ok "$(basename "$config_target") (absolute paths for global mode)"
    else
        ln -sf "$config_src" "$config_target"
        ok "$(basename "$config_target")"
    fi
fi

if { [ "$TOOL" = "opencode" ] || [ "$TOOL" = "trae" ] || [ "$TOOL" = "cursor" ] || [ "$TOOL" = "codearts" ]; } && [ "$LEVEL" = "project" ]; then
    if [ "$CONFIG_ROOT/AGENTS.md" != "$config_target" ]; then
        mkdir -p "$CONFIG_ROOT"
        ln -sf "$config_src" "$CONFIG_ROOT/AGENTS.md"
        ok "AGENTS.md → $(basename "$CONFIG_ROOT")/"
    fi
fi

echo ""

# --- Step 3: Configure tool discovery ---
step "[3/4] Configuring tool discovery..."

if [ "$TOOL" = "opencode" ]; then
    ok "Auto-scan: skills/, agents/"
else
    # Trae/Claude/Cursor: create per-skill discovery symlinks (local skills/ + shared ops, whitelist filtered)
    DISCOVERY="$CONFIG_ROOT/skills"

    for src_root in $SKILL_SOURCE_DIRS; do
        [ -d "$src_root" ] || continue
        for skill_dir in "$src_root"/*/; do
            [ -d "$skill_dir" ] || continue
            name=$(basename "$skill_dir")
            echo "$INCLUDED_SKILLS" | tr ' ' '\n' | grep -qxF "$name" || continue
            target="$DISCOVERY/$name"
            [ -e "$target" ] || [ -L "$target" ] && rm -rf "$target"
        done
    done

    link_count=0
    _seen_skill_names=""
    for src_root in $SKILL_SOURCE_DIRS; do
        [ -d "$src_root" ] || continue
        for skill_dir in "$src_root"/*/; do
            [ -d "$skill_dir" ] || continue
            name=$(basename "$skill_dir")
            echo "$INCLUDED_SKILLS" | tr ' ' '\n' | grep -qxF "$name" || continue
            [ -n "$EXCLUDED_SKILL" ] && [ "$name" = "$EXCLUDED_SKILL" ] && continue
            echo "$_seen_skill_names" | tr ' ' '\n' | grep -qxF "$name" && continue
            _seen_skill_names="$_seen_skill_names $name"
            target="$DISCOVERY/$name"
            ln -sfn "$(realpath "$skill_dir")" "$target"
            link_count=$((link_count + 1))
        done
    done

    for link in "$DISCOVERY"/*/; do
        link="${link%/}"
        [ -L "$link" ] && [ ! -e "$link" ] && rm "$link"
    done

    ok "Skills: $link_count discovery symlinks"

    AGENT_DISCOVERY="$CONFIG_ROOT/agents"

    for agent_entry in "$LOCAL_AGENT_ROOT"/*; do
        [ -e "$agent_entry" ] || continue
        name=$(basename "$agent_entry")
        base="${name%.md}"
        agent_in_whitelist "$base" || continue
        target="$AGENT_DISCOVERY/$name"
        [ -e "$target" ] || [ -L "$target" ] && rm -rf "$target"
    done

    agent_link_count=0
    for agent_entry in "$LOCAL_AGENT_ROOT"/*; do
        [ -e "$agent_entry" ] || continue
        name=$(basename "$agent_entry")
        base="${name%.md}"
        agent_in_whitelist "$base" || continue
        target="$AGENT_DISCOVERY/$name"
        if [ "$TOOL" = "trae" ]; then
            translate_agent "$agent_entry" "$target" trae
        else
            ln -sfn "$(realpath "$agent_entry")" "$target"
        fi
        agent_link_count=$((agent_link_count + 1))
    done

    for link in "$AGENT_DISCOVERY"/*; do
        [ -L "$link" ] && [ ! -e "$link" ] && rm "$link"
    done

    ok "Agents: $agent_link_count discovery symlinks"

    # Trae/Claude/Cursor: create per-hook discovery symlinks (from local hooks/)
    HOOK_DISCOVERY="$CONFIG_ROOT/hooks"

    for hook_entry in "$PLUGIN_ROOT/hooks"/*; do
        [ -e "$hook_entry" ] || continue
        name=$(basename "$hook_entry")
        target="$HOOK_DISCOVERY/$name"
        [ -e "$target" ] || [ -L "$target" ] && rm -rf "$target"
    done

    hook_link_count=0
    for hook_entry in "$PLUGIN_ROOT/hooks"/*; do
        [ -e "$hook_entry" ] || continue
        name=$(basename "$hook_entry")
        target="$HOOK_DISCOVERY/$name"
        ln -sfn "$(realpath "$hook_entry")" "$target"
        hook_link_count=$((hook_link_count + 1))
    done

    for link in "$HOOK_DISCOVERY"/*; do
        [ -L "$link" ] && [ ! -e "$link" ] && rm "$link"
    done

    ok "Hooks: $hook_link_count discovery symlinks"

    # --- Generate .claude/settings.json (Claude tool only) ---
    if [ "$TOOL" = "claude" ] && [ -f "$PLUGIN_ROOT/hooks/hooks.json" ]; then
        SETTINGS_TARGET="$CONFIG_ROOT/settings.json"
        PLUGIN_ROOT_ABS="$(realpath "$PLUGIN_ROOT")"
        python3 -c "
import json
with open('$PLUGIN_ROOT/hooks/hooks.json') as f:
    content = f.read()
content = content.replace('\${CLAUDE_PLUGIN_ROOT}', '$PLUGIN_ROOT_ABS')
config = json.loads(content)
with open('$SETTINGS_TARGET', 'w') as f:
    json.dump(config, f, indent=2)
" 2>/dev/null
        if [ -f "$SETTINGS_TARGET" ]; then
            ok "Generated settings.json (hooks activated)"
        else
            warn "Failed to generate settings.json"
        fi
    fi
fi
echo ""

# --- Step 4: Health check ---
step "[4/4] Running health check..."
health_ok=true
health_errors=""

for sub in skills agents hooks; do
  target="$CANNBOT_DIR/$sub"
  if [ -d "$target" ]; then
    count=$(ls -d "$target"/* 2>/dev/null | wc -l)
    [ "$count" -eq 0 ] && { health_errors="${health_errors}\n  ${YELLOW}⚠${NC} $sub/ is empty"; }
  else
    health_errors="${health_errors}\n  ${RED}✗${NC} $sub/ missing"
    health_ok=false
  fi
done

if [ "$LEVEL" = "project" ]; then
    if [ "$TOOL" = "opencode" ] || [ "$TOOL" = "trae" ] || [ "$TOOL" = "cursor" ] || [ "$TOOL" = "codearts" ]; then
        [ -f "$PWD/AGENTS.md" ] || { health_errors="${health_errors}\n  ${RED}✗${NC} AGENTS.md missing in current directory"; health_ok=false; }
    else
        [ -f "$PWD/CLAUDE.md" ] || { health_errors="${health_errors}\n  ${RED}✗${NC} CLAUDE.md missing in current directory"; health_ok=false; }
    fi
else
    if [ "$TOOL" = "opencode" ] || [ "$TOOL" = "trae" ] || [ "$TOOL" = "cursor" ] || [ "$TOOL" = "codearts" ]; then
        [ -f "$CONFIG_ROOT/AGENTS.md" ] || { health_errors="${health_errors}\n  ${RED}✗${NC} AGENTS.md missing"; health_ok=false; }
    else
        [ -f "$CONFIG_ROOT/CLAUDE.md" ] || { health_errors="${health_errors}\n  ${RED}✗${NC} CLAUDE.md missing"; health_ok=false; }
    fi
fi

# Generate brand manifest
MANIFEST="$CONFIG_ROOT/cannbot-manifest.json"

SKILLS_JSON="[]"
if [ -d "$CANNBOT_DIR/skills" ]; then
  SKILLS_JSON=$(ls -d "$CANNBOT_DIR/skills"/*/ 2>/dev/null | while read d; do
    basename "$d"
  done | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo "[]")
fi

AGENTS_JSON="[]"
if [ -d "$CANNBOT_DIR/agents" ]; then
  AGENTS_JSON=$(ls -d "$CANNBOT_DIR/agents"/* 2>/dev/null | while read d; do
    basename "$d"
  done | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo "[]")
fi

HOOKS_JSON="[]"
if [ -d "$CANNBOT_DIR/hooks" ]; then
  HOOKS_JSON=$(ls -d "$CANNBOT_DIR/hooks"/* 2>/dev/null | while read d; do
    basename "$d"
  done | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo "[]")
fi

cat > "$MANIFEST" << MANIFEST_EOF
{
  "brand": "CANNBot",
  "version": "$VERSION",
  "team": "$(basename "$SCRIPT_DIR")",
  "level": "$LEVEL",
  "tool": "$TOOL",
  "installed_skills": $SKILLS_JSON,
  "installed_agents": $AGENTS_JSON,
  "installed_hooks": $HOOKS_JSON,
  "brand_dir": "$CONFIG_ROOT",
  "install_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
MANIFEST_EOF

[ -f "$MANIFEST" ] || { health_errors="${health_errors}\n  ${RED}✗${NC} Manifest generation failed"; health_ok=false; }

if [ "$health_ok" = true ] && [ -z "$health_errors" ]; then
  ok "All checks passed"
else
  echo -e "$health_errors"
  [ "$health_ok" = true ] && warn "Some warnings, see above" || err "Some checks failed, see above"
fi

# --- Summary & Quick Start ---
echo ""
echo -e "  ${GREEN}${BOLD}✓ CANNBot ascendc-ops-perf-evolution installed successfully!${NC}"
echo ""
echo -e "  ${BOLD}Quick Start:${NC}"
if [ "$TOOL" = "opencode" ]; then
  echo -e "  ${CYAN}1.${NC} 启动 CLI: ${GREEN}opencode${NC}"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}对基线内核进行进化优化，npu=0，基线内核路径为 /path/to/baseline/kernel/，目标加速比 3x，进化轮数 3，并行数 5${NC}"
elif [ "$TOOL" = "trae" ]; then
  echo -e "  ${CYAN}1.${NC} 通过 CLI/IDE 启动${NC}"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}对基线内核进行进化优化，npu=0，基线内核路径为 /path/to/baseline/kernel/，目标加速比 3x，进化轮数 3，并行数 5${NC}"
elif [ "$TOOL" = "cursor" ]; then
  echo -e "  ${CYAN}1.${NC} 启动 Cursor IDE"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}对基线内核进行进化优化，npu=0，基线内核路径为 /path/to/baseline/kernel/，目标加速比 3x，进化轮数 3，并行数 5${NC}"
elif [ "$TOOL" = "codearts" ]; then
  echo -e "  ${CYAN}1.${NC} 通过 CodeArts CLI / IDE 启动${NC}"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}对基线内核进行进化优化，npu=0，基线内核路径为 /path/to/baseline/kernel/，目标加速比 3x，进化轮数 3，并行数 5${NC}"
else
  echo -e "  ${CYAN}1.${NC} 启动 CLI: ${GREEN}claude${NC}"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}对基线内核进行进化优化，npu=0，基线内核路径为 /path/to/baseline/kernel/，目标加速比 3x，进化轮数 3，并行数 5${NC}"
fi
echo ""
