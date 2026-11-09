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
# Triton plugin skills are excluded from installation
EXCLUDED_PATTERNS="triton"
# Agent whitelist (shell pattern) - uses local agents/
INCLUDED_AGENT_PATTERN="tilelang2ascendc-kernel-generator*"

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
  echo -e "  ${BOLD}Ascend C Ops Developer Team${NC}"
  echo ""
}

show_help() {
    cat << EOF
CANNBot - Ascend C Ops Developer Environment Installer

Usage: init.sh [level] [tool] [target-dir] [--target <dir>]

Arguments:
  level      - Installation level: "project" (default) or "global"
  tool       - Target tool: "opencode" (default), "claude", "codex", "dsh",
               "trae", "cursor", "copilot", or "codearts"
  target-dir - Project-level install destination (default: current directory).
               Can also be passed as --target <dir>. Ignored for global level.

Options:
  --help                       - Show this help message
  --knowledge-root <path>      - Use an existing (or clone a new) cannbot-knowledge
                                 checkout at <path>; default: <repo>/vendor/cannbot-knowledge
  --no-knowledge               - Skip fixed-knowledge installation entirely
  --knowledge-update           - Explicitly fast-forward an existing knowledge checkout
  --knowledge-platform <id>    - Default platform written to .cannbot/knowledge.env
                                 (default: $CANNBOT_KNOWLEDGE_PLATFORM)
  --strict-knowledge           - Exit 2 when fixed or staging knowledge is unavailable

Examples:
  init.sh                              # Project-level, OpenCode, 当前目录
  init.sh project codex                # Project-level, Codex, 当前目录
  init.sh project dsh /path/to/proj    # Project-level, DSH, 指定目录
  init.sh project claude --target /path/to/proj
  init.sh global claude                # Global-level, Claude Code
  init.sh project cursor               # Project-level, Cursor
  init.sh global cursor                # Global-level, Cursor
  init.sh project copilot              # Project-level, Copilot
  init.sh global copilot               # Global-level, Copilot
  init.sh project codearts             # Project-level, CodeArts
  init.sh project trae                 # Project-level, Trae

Existing user-owned symlinks, files and directories at install targets are always
preserved (the installer only replaces entries it created itself).

Installation paths (CANNBot brand, project level installs into <target-dir>):
  OpenCode: .opencode/{skills,agents}/  (auto-discovered)
  Claude:   .claude/{skills,agents}/    (per-skill symlinks auto-created)
  Codex:    .agents/skills/ + .codex/agents/  (skill root and config root differ)
  DSH:      .dsh/{skills,agents}/       (project-dsh discovery root)
  Trae:     .trae/{skills,agents}/      (symlinks, project-level only)
  Cursor:   .cursor/{skills,agents}/    (per-skill symlinks auto-created)
  Copilot:  .github/{skills,agents}/    (per-skill symlinks auto-created)
  CodeArts: .codeartsdoer/{skills,agents}/ (per-skill symlinks auto-created)

Global installation roots:
  OpenCode: ~/.config/opencode        Claude:  ~/.claude
  Codex:    ~/.agents/skills + ~/.codex
  DSH:      $DSH_HOME (default ~/.dsh)
  Cursor:   ~/.cursor                 Copilot: ~/.copilot
  CodeArts: ~/.codeartsdoer

Project root for Codex/DSH: --target / $CANNBOT_PROJECT_ROOT if set, otherwise the
nearest .git ancestor of the current directory, otherwise the current directory.

Knowledge (two independent stores):
  Fixed    - cannbot-knowledge, cloned by default to vendor/cannbot-knowledge
             (read-only; override with --knowledge-root)
  Staging  - plugin knowledge/ bundle, mounted to <config>/knowledge; per-project
             drafts go to <project>/.tilelang2ascendc/knowledge/learned/
  If the fixed knowledge repo is unavailable the installer warns and continues;
  use --strict-knowledge to fail instead.

After installation, launch directly:
  OpenCode: opencode
  Claude:   claude
  Codex:    codex
  DSH:      dsh
  Trae:     通过 CLI 或 IDE 启动
  Cursor:   通过 Cursor IDE 启动
  Copilot:  通过 GitHub Copilot CLI / IDE 启动
  CodeArts: 通过 CodeArts CLI / IDE 启动
EOF
}

LEVEL="project"
TOOL="opencode"
TARGET_DIR=""
TARGET_GIVEN=0

# --- Knowledge configuration (fixed read-only knowledge + plugin staging bundle) ---
KNOWLEDGE_ROOT_ARG=""
KNOWLEDGE_ROOT_EXPLICIT=0
KNOWLEDGE_DISABLED=0
KNOWLEDGE_UPDATE=0
KNOWLEDGE_PLATFORM="${CANNBOT_KNOWLEDGE_PLATFORM:-}"
STRICT_KNOWLEDGE=0

KNOWLEDGE_DIR=""
KNOWLEDGE_STATUS="absent"
KNOWLEDGE_INDEX=""
KNOWLEDGE_INDEX_STATE="absent"
KNOWLEDGE_COMMIT=""
KNOWLEDGE_SKILLS_STATUS="absent"
STAGING_STATUS="absent"
STAGING_PROJECT_DIR=""
STAGING_BUILTIN_DIR=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$SCRIPT_DIR"
# 调用时的原始工作目录：project 级 CLAUDE.md/AGENTS.md 安装在此处；
# asc-devkit 更新步骤会 cd 到 SCRIPT_DIR，健康检查需以此目录为准
INVOCATION_DIR="$PWD"
# Agents: use local agents/ directory (migrated with plugin)
LOCAL_AGENT_ROOT="$PLUGIN_ROOT/agents"
# Skills: 统一由子模块 vendor/cannbot-skills 提供。四个来源根：
#   ops/                                     — 上游官方 Skill
#   community/ops/                           — 社区 Skill
#   plugins-community/cannbot-knowledge/skills/ — knowledge 类 Skill（独立插件内）
#   <plugin>/skills/                         — 插件本地 Skill（暂存知识管理等）
# 兼容旧布局：子模块不存在时回退到仓库根的对应目录。
REPO_ROOT="$(cd "$PLUGIN_ROOT/../.." && pwd)"
SKILLS_VENDOR="$REPO_ROOT/vendor/cannbot-skills"
SKILL_ROOT_LOCAL="$PLUGIN_ROOT/skills"
if [ -d "$SKILLS_VENDOR/ops" ]; then
    SKILL_ROOT_OPS="$SKILLS_VENDOR/ops"
    SKILL_ROOT_COMMUNITY="$SKILLS_VENDOR/community/ops"
    SKILL_ROOT_KNOWLEDGE="$SKILLS_VENDOR/plugins-community/cannbot-knowledge/skills"
else
    SKILL_ROOT_OPS="$REPO_ROOT/ops"
    SKILL_ROOT_COMMUNITY="$REPO_ROOT/community/ops"
    SKILL_ROOT_KNOWLEDGE="$REPO_ROOT/plugins-community/cannbot-knowledge/skills"
fi

# Parse skill dependencies from AGENTS.md and agents/*.md frontmatter
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
        sm = re.search(r'^skills:\n((?:\s+-\s+.+\n?)*)', fm, re.MULTILINE)
        if sm:
            all_skills.update(re.findall(r'^\s+-\s+(.+)$', sm.group(0), re.MULTILINE))

filtered = sorted(s for s in all_skills if not re.search(r'triton', s, re.IGNORECASE))
print(' '.join(filtered))
" 2>/dev/null)
  if [ -z "$INCLUDED_SKILLS" ]; then
    warn "Failed to parse skill dependencies from AGENTS.md, using fallback"
    INCLUDED_SKILLS="npu-arch ascendc-api-best-practices ascendc-docs-search ascendc-tiling-design ascendc-crash-debug tilelang2ascend-case-simplifier tilelang2ascend-operator-project-init ops-profiling ascendc-precision-debug tilelang2ascend-precision-tuning tilelang2ascend-tilelang-designer tilelang2ascend-translator tilelang2ascend-trace-recorder tilelang-op-design tilelang-op-develop tilelang-perf-optimization ascendc-perf-optimize tilelang2ascendc-knowledge"
  fi
else
  err "AGENTS.md not found at $PLUGIN_ROOT/AGENTS.md"
  exit 1
fi

# --- Provision missing dependency skills from the official skills repo ---
# 本地已存在的 skill 绝不覆盖（<repo>/ops 与 <repo>/community/ops 均探测）；
# 仅对 AGENTS.md 声明依赖中缺失的 skill，从
# https://gitcode.com/cann/cannbot-skills 拉取，并按上游结构原样落盘：
# 上游 ops/ 下的 skill → <repo>/ops，上游 community/ops/ 下的 → <repo>/community/ops。
# 幂等：依赖齐全时不访问网络；二次运行直接跳过。可用 CANNBOT_SKILLS_REPO 覆盖仓库地址。
SKILLS_REPO_URL="${CANNBOT_SKILLS_REPO:-https://gitcode.com/cann/cannbot-skills.git}"
SKILLS_CACHE_DIR="$REPO_ROOT/.cannbot-skills"
# 上游仓库缺失 skill 的负缓存（避免每次运行都为已证缺失的 skill 拉取仓库），7 天过期
SKILLS_MISSING_CACHE="$SKILLS_CACHE_DIR/.repo-missing"
MISSING_TTL_DAYS=7

provision_skills_from_repo() {
    local need_fetch="" name
    # skills 由 vendor/cannbot-skills 子模块提供：齐全则直接返回；
    # 不齐全时也不联网补取（避免写入子模块工作区），只告警。
    if [ -d "$SKILLS_VENDOR/ops" ]; then
        local vendor_missing=""
        for name in $INCLUDED_SKILLS; do
            [ -n "$EXCLUDED_SKILL" ] && [ "$name" = "$EXCLUDED_SKILL" ] && continue
            echo "$name" | grep -qi "triton" && continue
            [ -d "$SKILL_ROOT_OPS/$name" ] || [ -d "$SKILL_ROOT_COMMUNITY/$name" ] || [ -d "$SKILL_ROOT_KNOWLEDGE/$name" ] || [ -d "$SKILL_ROOT_LOCAL/$name" ] || vendor_missing="$vendor_missing $name"
        done
        [ -z "$vendor_missing" ] && return 0
        warn "skills missing in vendor/cannbot-skills:$vendor_missing (skip network provisioning)"
        return 0
    fi
    for name in $INCLUDED_SKILLS; do
        [ -n "$EXCLUDED_SKILL" ] && [ "$name" = "$EXCLUDED_SKILL" ] && continue
        echo "$name" | grep -qi "triton" && continue
        [ -d "$SKILL_ROOT_OPS/$name" ] && continue
        [ -d "$SKILL_ROOT_COMMUNITY/$name" ] && continue
        [ -d "$SKILL_ROOT_KNOWLEDGE/$name" ] && continue
        [ -d "$SKILL_ROOT_LOCAL/$name" ] && continue
        need_fetch="$need_fetch $name"
    done
    [ -z "$need_fetch" ] && return 0

    # 负缓存命中且未过期 → 跳过网络。
    # 缓存首行为查找逻辑版本标记：查找路径结构变化时 bump 版本号，
    # 使旧缓存（按旧路径结构记录的"缺失"结论）自动失效，避免新路径下被误跳过。
    if [ -f "$SKILLS_MISSING_CACHE" ] && [ "$(head -n 1 "$SKILLS_MISSING_CACHE")" = "#lookup-v2" ]; then
        local age=$(( ($(date +%s) - $(stat -c %Y "$SKILLS_MISSING_CACHE")) / 86400 ))
        if [ "$age" -lt "$MISSING_TTL_DAYS" ]; then
            local still_needed=""
            for name in $need_fetch; do
                grep -qxF "$name" "$SKILLS_MISSING_CACHE" || still_needed="$still_needed $name"
            done
            need_fetch="$still_needed"
            [ -z "$need_fetch" ] && return 0
        fi
    fi

    info "Fetching dependency skills from $SKILLS_REPO_URL"
    if [ -d "$SKILLS_CACHE_DIR/.git" ]; then
        git -C "$SKILLS_CACHE_DIR" pull --quiet --depth 1 2>/dev/null \
            || warn "skills repo update failed, using cached copy"
    else
        rm -rf "$SKILLS_CACHE_DIR"
        if ! git clone --depth 1 --quiet "$SKILLS_REPO_URL" "$SKILLS_CACHE_DIR" 2>/dev/null; then
            rm -rf "$SKILLS_CACHE_DIR"
            err "Failed to clone $SKILLS_REPO_URL (check network/proxy)"
            return 1
        fi
        ok "skills repo cloned → $SKILLS_CACHE_DIR"
    fi

    # 目标目录：与上游 cannbot-skills 结构保持一致——上游 ops/ 下的 skill 拷入
    # <repo>/ops，上游 community/ops/ 下的 skill 拷入 <repo>/community/ops
    # （目标根目录不存在时按需创建）。knowledge 类 skill 上游位于
    # plugins-community/cannbot-knowledge/skills/（独立插件的 skills 目录），
    # 同样归入 community/ops 目标根，安装循环扫描时即可发现。
    local copied=0 missing="" target_root src
    for name in $need_fetch; do
        if [ -d "$SKILLS_CACHE_DIR/ops/$name" ]; then
            src="$SKILLS_CACHE_DIR/ops/$name"
            target_root="$SKILL_ROOT_OPS"
        elif [ -d "$SKILLS_CACHE_DIR/community/ops/$name" ]; then
            src="$SKILLS_CACHE_DIR/community/ops/$name"
            target_root="$SKILL_ROOT_COMMUNITY"
        elif [ -d "$SKILLS_CACHE_DIR/plugins-community/cannbot-knowledge/skills/$name" ]; then
            src="$SKILLS_CACHE_DIR/plugins-community/cannbot-knowledge/skills/$name"
            target_root="$SKILL_ROOT_COMMUNITY"
        else
            missing="$missing $name"
            continue
        fi
        mkdir -p "$target_root"
        rm -rf "$target_root/$name"
        cp -r "$src" "$target_root/$name"
        copied=$((copied + 1))
    done
    [ "$copied" -gt 0 ] && ok "skills provisioned → ops/ + community/ops/ ($copied items)"
    if [ -n "$missing" ]; then
        warn "not found in skills repo:$missing"
        # 写入负缓存（重建整个清单：本次全部 need_fetch 中未拷入的即为缺失）。
        # 首行写入查找逻辑版本标记，路径结构变化时 bump 以使旧缓存失效。
        : > "$SKILLS_MISSING_CACHE"
        echo "#lookup-v2" >> "$SKILLS_MISSING_CACHE"
        for name in $missing; do
            echo "$name" >> "$SKILLS_MISSING_CACHE"
        done
    fi
    return 0
}

# --- Parse arguments (project-level target path defaults to the current directory) ---
while [ $# -gt 0 ]; do
    case "$1" in
        --help|-h)          show_help; exit 0 ;;
        --target)
            [ $# -ge 2 ] && [ -n "$2" ] || { echo "Error: --target requires a directory"; exit 1; }
            [ "$TARGET_GIVEN" -eq 0 ] || { echo "Error: target directory given more than once"; exit 1; }
            TARGET_DIR="$2"; TARGET_GIVEN=1; shift 2; continue ;;
        global|project)     LEVEL="$1" ;;
        opencode|claude|codex|dsh|trae|cursor|copilot|codearts)   TOOL="$1" ;;
        --knowledge-root)
            [ $# -ge 2 ] && [ -n "$2" ] || { echo "Error: --knowledge-root requires a directory"; exit 1; }
            KNOWLEDGE_ROOT_ARG="$2"; KNOWLEDGE_ROOT_EXPLICIT=1; shift 2; continue ;;
        --knowledge-root=*)
            KNOWLEDGE_ROOT_ARG="${1#--knowledge-root=}"
            [ -n "$KNOWLEDGE_ROOT_ARG" ] || { echo "Error: --knowledge-root requires a directory"; exit 1; }
            KNOWLEDGE_ROOT_EXPLICIT=1 ;;
        --no-knowledge)     KNOWLEDGE_DISABLED=1 ;;
        --knowledge-update) KNOWLEDGE_UPDATE=1 ;;
        --knowledge-platform)
            [ $# -ge 2 ] && [ -n "$2" ] || { echo "Error: --knowledge-platform requires a value"; exit 1; }
            KNOWLEDGE_PLATFORM="$2"; shift 2; continue ;;
        --knowledge-platform=*)
            KNOWLEDGE_PLATFORM="${1#--knowledge-platform=}"
            [ -n "$KNOWLEDGE_PLATFORM" ] || { echo "Error: --knowledge-platform requires a value"; exit 1; } ;;
        --strict-knowledge) STRICT_KNOWLEDGE=1 ;;
        -*)  echo "Error: Unknown option '$1'. Valid options: --help, --target <dir>, --knowledge-root <dir>, --no-knowledge, --knowledge-update, --knowledge-platform <id>, --strict-knowledge."; exit 1 ;;
        *)   [ "$TARGET_GIVEN" -eq 0 ] || { echo "Error: unexpected extra argument '$1'"; exit 1; }
             TARGET_DIR="$1"; TARGET_GIVEN=1 ;;
    esac
    shift
done

if [ "$KNOWLEDGE_DISABLED" -eq 1 ] && [ "$KNOWLEDGE_ROOT_EXPLICIT" -eq 1 ]; then
    echo "Error: --no-knowledge cannot be combined with --knowledge-root"
    exit 1
fi

if [ "$LEVEL" = "global" ] && [ "$TARGET_GIVEN" -eq 1 ]; then
    warn "global level ignores the target directory; installing into the user config root"
    TARGET_DIR=""; TARGET_GIVEN=0
fi

# Resolve the install target: project-level installs land in <target>, which
# defaults to the current directory (the historical behaviour).
TARGET_DIR="${TARGET_DIR:-$PWD}"
if [ ! -d "$TARGET_DIR" ]; then
    err "Target directory not found: $TARGET_DIR"
    exit 1
fi
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"
cd "$TARGET_DIR"
INVOCATION_DIR="$TARGET_DIR"

# Codex/DSH project root: explicit target > $CANNBOT_PROJECT_ROOT > nearest .git
# ancestor > $PWD. Only a defaulted target walks up to the repository root, so
# "omit the path" stays predictable.
PROJECT_ROOT="$TARGET_DIR"
if { [ "$TOOL" = "codex" ] || [ "$TOOL" = "dsh" ]; } && [ "$TARGET_GIVEN" -eq 0 ]; then
    if [ -n "${CANNBOT_PROJECT_ROOT:-}" ]; then
        PROJECT_ROOT="$(cd "$CANNBOT_PROJECT_ROOT" 2>/dev/null && pwd)" || {
            err "CANNBOT_PROJECT_ROOT not found: $CANNBOT_PROJECT_ROOT"; exit 1; }
    else
        PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "$PWD")"
    fi
fi

# 子模块自动初始化：用户按文档执行普通 git clone 即可，不需要感知 submodule。
# 失败时保留 provision_skills_from_repo() 的原有仓库兜底逻辑。
if [ ! -d "$SKILLS_VENDOR/ops" ] \
   && git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    info "Initializing vendor/cannbot-skills submodule..."
    git -C "$REPO_ROOT" submodule update --init --recursive vendor/cannbot-skills \
        || warn "submodule init failed, falling back to skills repo provisioning"
fi

provision_skills_from_repo

# Determine config root directory
if [ "$LEVEL" = "global" ]; then
    if [ "$TOOL" = "opencode" ]; then
        CONFIG_ROOT="$HOME/.config/opencode"
    elif [ "$TOOL" = "trae" ]; then
        echo "Error: Global installation is not supported for Trae. Use project-level instead."
        exit 1
    elif [ "$TOOL" = "cursor" ]; then
        CONFIG_ROOT="$HOME/.cursor"
    elif [ "$TOOL" = "copilot" ]; then
        CONFIG_ROOT="$HOME/.copilot"
    elif [ "$TOOL" = "codearts" ]; then
        CONFIG_ROOT="$HOME/.codeartsdoer"
    elif [ "$TOOL" = "codex" ]; then
        # Codex 用户配置根：custom agents / AGENTS.md（技能根另见 SKILL_DISCOVERY_ROOT）
        CONFIG_ROOT="$HOME/.codex"
    elif [ "$TOOL" = "dsh" ]; then
        # DSH 用户数据根：$DSH_HOME，默认 ~/.dsh（其下 skills/ 即 user-dsh 技能根）
        CONFIG_ROOT="${DSH_HOME:-$HOME/.dsh}"
    else
        CONFIG_ROOT="$HOME/.claude"
    fi
else
    if [ "$TOOL" = "opencode" ]; then
        CONFIG_ROOT="$TARGET_DIR/.opencode"
    elif [ "$TOOL" = "trae" ]; then
        CONFIG_ROOT="$TARGET_DIR/.trae"
    elif [ "$TOOL" = "cursor" ]; then
        CONFIG_ROOT="$TARGET_DIR/.cursor"
    elif [ "$TOOL" = "copilot" ]; then
        CONFIG_ROOT="$TARGET_DIR/.github"
    elif [ "$TOOL" = "codearts" ]; then
        CONFIG_ROOT="$TARGET_DIR/.codeartsdoer"
    elif [ "$TOOL" = "codex" ]; then
        CONFIG_ROOT="$PROJECT_ROOT/.codex"
    elif [ "$TOOL" = "dsh" ]; then
        CONFIG_ROOT="$PROJECT_ROOT/.dsh"
    else
        CONFIG_ROOT="$TARGET_DIR/.claude"
    fi
fi

CANNBOT_DIR="$CONFIG_ROOT"

# --- Discovery roots (Codex uses a skill root separate from its config root) ---
SKILL_DISCOVERY_ROOT="$CANNBOT_DIR/skills"
AGENT_DISCOVERY_ROOT="$CANNBOT_DIR/agents"
CODEX_AGENT_TEMPLATE_ROOT="$PLUGIN_ROOT/agents/codex"
if [ "$TOOL" = "codex" ]; then
    if [ "$LEVEL" = "global" ]; then
        SKILL_DISCOVERY_ROOT="$HOME/.agents/skills"
    else
        SKILL_DISCOVERY_ROOT="$PROJECT_ROOT/.agents/skills"
    fi
fi

# Tools whose primary config file is AGENTS.md (Claude uses CLAUDE.md).
AGENTS_MD_TOOL=false
case "$TOOL" in
    opencode|trae|cursor|copilot|codearts|codex|dsh) AGENTS_MD_TOOL=true ;;
esac

# --- Managed-entry helpers ---
# 安装器只允许替换自己创建的条目：链接解析后落在插件/技能源目录下，或由这些
# 路径产生的断链。用户自己的软链、真实文件与目录一律保留（不删用户内容）。
MANAGED_ROOTS=()
for _root in "$PLUGIN_ROOT" "$REPO_ROOT/ops" "$REPO_ROOT/community/ops" \
             "$SKILLS_VENDOR" "$SKILLS_VENDOR/ops" "$SKILLS_VENDOR/community/ops"; do
    if _resolved="$(realpath "$_root" 2>/dev/null)"; then
        [ -n "$_resolved" ] && MANAGED_ROOTS+=("$_resolved")
    fi
done
unset _root _resolved

is_installer_link() {
    local link="$1" raw resolved root
    [ -L "$link" ] || return 1
    raw="$(readlink "$link" 2>/dev/null)" || return 1
    [ -n "$raw" ] || return 1
    if resolved="$(readlink -f "$link" 2>/dev/null)"; then
        for root in "${MANAGED_ROOTS[@]}"; do
            case "$resolved" in "$root"/*) return 0 ;; esac
        done
        return 1
    fi
    # 断链：已无有效目标，可安全清理/重建（例如插件 clone 被移动后重装）
    return 0
}

# Codex Agent TOML 是本安装器生成的真实文件（非软链）
is_installer_generated_file() {
    [ -f "$1" ] && grep -q "This is the Codex custom-agent adapter" "$1" 2>/dev/null
}

# --- Knowledge helpers -------------------------------------------------------
# 固定知识（cannbot-knowledge，只读）与插件暂存知识（plugin/knowledge，项目内可写）
# 是两套独立的知识来源，安装期分别处理，运行期分别检索。

KNOWLEDGE_REPO_URL="${CANNBOT_KNOWLEDGE_REPO_URL:-https://gitcode.com/cann/cannbot-knowledge.git}"

if [ "$KNOWLEDGE_ROOT_EXPLICIT" -eq 1 ]; then
    case "$KNOWLEDGE_ROOT_ARG" in
        "~"/*) KNOWLEDGE_DIR="$HOME/${KNOWLEDGE_ROOT_ARG#\~/}" ;;
        /*)    KNOWLEDGE_DIR="$KNOWLEDGE_ROOT_ARG" ;;
        *)     KNOWLEDGE_DIR="$PWD/$KNOWLEDGE_ROOT_ARG" ;;
    esac
else
    KNOWLEDGE_DIR="$REPO_ROOT/vendor/cannbot-knowledge"
fi

knowledge_repo_ready() {
    [ -d "$1/knowledge" ] && [ -f "$1/governance/schemas/registries.yaml" ]
}

# 读取 registries.yaml 的 platforms 顶层键；不依赖 PyYAML，安装前即可使用。
knowledge_platform_registered() {
    local registry="$1" platform="$2"
    [ -f "$registry" ] || return 1
    awk '
        /^platforms:[[:space:]]*$/ { in_platforms = 1; next }
        in_platforms && /^[^[:space:]]/ { in_platforms = 0 }
        in_platforms && /^  [^[:space:]].*:/ {
            line = $0
            sub(/^  /, "", line)
            sub(/:.*/, "", line)
            gsub(/"/, "", line)
            print line
        }
    ' "$registry" | grep -Fxq -- "$platform"
}

# 只补自己的软链：目标已存在且指向别处时保留用户内容。
link_knowledge_skill() {
    local src="$1" dst="$2" current
    if [ -L "$dst" ]; then
        if [ ! -e "$dst" ]; then
            # 断链（常见于知识仓被移动或重装），可以安全重建。
            ln -sfn "$src" "$dst"
            return 0
        fi
        current="$(readlink -f "$dst" 2>/dev/null || true)"
        [ "$current" = "$(readlink -f "$src" 2>/dev/null || echo "$src")" ] && return 0
        warn "保留已存在条目（非本安装器创建）: $dst"
        return 0
    fi
    [ ! -e "$dst" ] || { warn "保留已存在条目（非本安装器创建）: $dst"; return 0; }
    mkdir -p "$(dirname "$dst")"
    ln -s "$src" "$dst"
}

write_knowledge_env() {
    local target="$1" root="$2" platform="$3" existing current_platform
    mkdir -p "$(dirname "$target")"
    if [ -f "$target" ]; then
        existing="$(sed -n 's/^[[:space:]]*\(export[[:space:]]*\)\{0,1\}CANNBOT_KNOWLEDGE_ROOT=//p' "$target" | tail -n 1 | tr -d "'\"")"
        current_platform="$(sed -n 's/^[[:space:]]*\(export[[:space:]]*\)\{0,1\}CANNBOT_KNOWLEDGE_PLATFORM=//p' "$target" | tail -n 1 | tr -d "'\"")"
        if [ -n "$existing" ] && [ "$existing" != "$root" ] && [ "$KNOWLEDGE_ROOT_EXPLICIT" -eq 0 ]; then
            warn "保留已有知识库绑定（根路径不同）: $target"
            return 0
        fi
        # 默认重复安装不重写；显式 --knowledge-root / --knowledge-platform 才更新绑定。
        if [ "$existing" = "$root" ] \
           && { [ "$KNOWLEDGE_ROOT_EXPLICIT" -eq 0 ] \
                || [ -z "$platform" ] \
                || [ "$current_platform" = "$platform" ]; }; then
            info "knowledge env already bound: $target"
            return 0
        fi
    fi
    {
        printf 'export CANNBOT_KNOWLEDGE_ROOT=%q\n' "$root"
        printf 'export CANNBOT_KNOWLEDGE_PROFILE=%q\n' "consumer"
        [ -n "$platform" ] && printf 'export CANNBOT_KNOWLEDGE_PLATFORM=%q\n' "$platform"
    } > "$target"
    ok "knowledge env → $target"
}

setup_fixed_knowledge() {
    if [ "$KNOWLEDGE_DISABLED" -eq 1 ]; then
        KNOWLEDGE_STATUS="disabled"
        KNOWLEDGE_SKILLS_STATUS="disabled"
        KNOWLEDGE_INDEX_STATE="disabled"
        info "Fixed knowledge disabled (--no-knowledge)"
        return 0
    fi

    local clone_ok=false install_ok=false stage log skill src canonical
    if knowledge_repo_ready "$KNOWLEDGE_DIR"; then
        info "Using fixed knowledge: $KNOWLEDGE_DIR"
    elif [ -e "$KNOWLEDGE_DIR" ]; then
        if [ "$KNOWLEDGE_ROOT_EXPLICIT" -eq 1 ]; then
            err "Not a cannbot-knowledge checkout: $KNOWLEDGE_DIR"
            exit 2
        fi
        warn "Existing path is not a cannbot-knowledge checkout: $KNOWLEDGE_DIR"
        KNOWLEDGE_STATUS="invalid"
        [ "$STRICT_KNOWLEDGE" -eq 1 ] && exit 2
        return 0
    else
        command -v git >/dev/null 2>&1 || {
            warn "git not available; fixed knowledge unavailable"
            KNOWLEDGE_STATUS="degraded"
            [ "$STRICT_KNOWLEDGE" -eq 1 ] && exit 2
            return 0
        }
        mkdir -p "$(dirname "$KNOWLEDGE_DIR")"
        info "Cloning cannbot-knowledge → $KNOWLEDGE_DIR"
        if git clone --depth 1 "$KNOWLEDGE_REPO_URL" "$KNOWLEDGE_DIR" >/dev/null 2>&1; then
            clone_ok=true
        else
            rm -rf "$KNOWLEDGE_DIR"
            warn "cannbot-knowledge clone failed; knowledge features will be degraded"
            KNOWLEDGE_STATUS="degraded"
            [ "$STRICT_KNOWLEDGE" -eq 1 ] && exit 2
            return 0
        fi
    fi

    knowledge_repo_ready "$KNOWLEDGE_DIR" || {
        warn "Invalid cannbot-knowledge checkout: $KNOWLEDGE_DIR"
        KNOWLEDGE_STATUS="invalid"
        [ "$STRICT_KNOWLEDGE" -eq 1 ] && exit 2
        return 0
    }

    if [ "$KNOWLEDGE_UPDATE" -eq 1 ] && [ "$clone_ok" != true ]; then
        if git -C "$KNOWLEDGE_DIR" pull --ff-only >/dev/null 2>&1; then
            ok "Fixed knowledge fast-forwarded"
        else
            warn "cannbot-knowledge update failed; using current checkout"
        fi
    fi

    KNOWLEDGE_COMMIT="$(git -C "$KNOWLEDGE_DIR" rev-parse HEAD 2>/dev/null || true)"
    KNOWLEDGE_INDEX="$KNOWLEDGE_DIR/artifacts/indexes/knowledge.sqlite3"

    # 显式指定平台时按知识仓注册值校验，避免把非法值写进 knowledge.env 后才在检索期失败。
    # 不依赖 PyYAML：首次安装时依赖由知识仓安装器稍后补齐。
    if [ -n "$KNOWLEDGE_PLATFORM" ] \
       && ! knowledge_platform_registered "$KNOWLEDGE_DIR/governance/schemas/registries.yaml" "$KNOWLEDGE_PLATFORM"; then
        err "Unknown knowledge platform: $KNOWLEDGE_PLATFORM"
        exit 2
    fi

    # 知识仓安装器在临时项目目录执行：只借用它安装依赖、建索引、校验知识根，
    # 不向真实工程注入 prompt 块（插件自己的 AGENTS.md 负责编排与检索路由）。
    stage="$(mktemp -d "${TMPDIR:-/tmp}/cannbot-knowledge.XXXXXX")"
    log="$(mktemp "${TMPDIR:-/tmp}/cannbot-knowledge-install.XXXXXX.log")"
    case "$TOOL" in
        dsh|codearts) set -- claude ;;
        *)            set -- "$TOOL" ;;
    esac
    if bash "$KNOWLEDGE_DIR/install.sh" "$1" "$stage" consumer \
        --knowledge-root "$KNOWLEDGE_DIR" \
        --skip-repository-update \
        ${KNOWLEDGE_PLATFORM:+--platform "$KNOWLEDGE_PLATFORM"} >"$log" 2>&1; then
        install_ok=true
    else
        warn "cannbot-knowledge installer failed; knowledge features may be degraded"
        tail -n 3 "$log" 2>/dev/null | sed 's/^/    /' || true
    fi
    rm -rf "$stage" "$log"

    if [ -f "$KNOWLEDGE_INDEX" ]; then
        KNOWLEDGE_INDEX_STATE="ready"
    else
        KNOWLEDGE_INDEX_STATE="missing"
        warn "Knowledge search index missing: $KNOWLEDGE_INDEX"
    fi
    if [ "$install_ok" = true ] && [ "$KNOWLEDGE_INDEX_STATE" = "ready" ]; then
        KNOWLEDGE_STATUS="ready"
    else
        KNOWLEDGE_STATUS="degraded"
    fi

    # 固定知识 Skill 由知识仓提供，插件不复制其实现。
    for skill in knowledge-query ascendc-api-knowledge-query; do
        src="$KNOWLEDGE_DIR/.agents/skills/$skill"
        [ -d "$src" ] || { warn "knowledge skill missing in checkout: $skill"; continue; }
        if [ "$LEVEL" = "global" ]; then
            link_knowledge_skill "$src" "$SKILL_DISCOVERY_ROOT/$skill"
        else
            canonical="$TARGET_DIR/.agents/skills/$skill"
            link_knowledge_skill "$src" "$canonical"
            if [ "$SKILL_DISCOVERY_ROOT" != "$TARGET_DIR/.agents/skills" ]; then
                link_knowledge_skill "$canonical" "$SKILL_DISCOVERY_ROOT/$skill"
            fi
        fi
    done

    KNOWLEDGE_SKILLS_STATUS="ready"
    for skill in knowledge-query ascendc-api-knowledge-query; do
        [ -e "$SKILL_DISCOVERY_ROOT/$skill" ] || KNOWLEDGE_SKILLS_STATUS="degraded"
    done

    # 固定知识检索封装：链接到配置根，供各 Phase 统一调用。
    if [ -f "$PLUGIN_ROOT/scripts/knowledge_search.sh" ]; then
        link_knowledge_skill "$PLUGIN_ROOT/scripts/knowledge_search.sh" \
            "$CONFIG_ROOT/scripts/knowledge_search.sh"
    fi

    if [ "$LEVEL" = "global" ]; then
        write_knowledge_env "$HOME/.cannbot/knowledge.env" "$KNOWLEDGE_DIR" "$KNOWLEDGE_PLATFORM"
    else
        write_knowledge_env "$TARGET_DIR/.cannbot/knowledge.env" "$KNOWLEDGE_DIR" "$KNOWLEDGE_PLATFORM"
    fi

    if [ "$KNOWLEDGE_STATUS" != "ready" ]; then
        warn "Fixed knowledge status: $KNOWLEDGE_STATUS"
        [ "$STRICT_KNOWLEDGE" -eq 1 ] && exit 2
    fi
    return 0
}

setup_staging_knowledge() {
    STAGING_BUILTIN_DIR="$PLUGIN_ROOT/knowledge"
    if [ ! -f "$STAGING_BUILTIN_DIR/index.md" ]; then
        warn "Plugin staging knowledge bundle missing: $STAGING_BUILTIN_DIR"
        STAGING_STATUS="degraded"
        [ "$STRICT_KNOWLEDGE" -eq 1 ] && exit 2
        return 0
    fi

    # 只读挂载：<config>/knowledge → 插件内置 bundle
    if [ -L "$CONFIG_ROOT/knowledge" ]; then
        if [ "$(readlink -f "$CONFIG_ROOT/knowledge" 2>/dev/null || true)" != \
             "$(realpath "$STAGING_BUILTIN_DIR")" ]; then
            warn "保留已存在条目（非本安装器创建）: $CONFIG_ROOT/knowledge"
        fi
    elif [ -e "$CONFIG_ROOT/knowledge" ]; then
        warn "保留已存在目录（非本安装器创建）: $CONFIG_ROOT/knowledge"
    else
        mkdir -p "$CONFIG_ROOT"
        ln -sfn "$(realpath "$STAGING_BUILTIN_DIR")" "$CONFIG_ROOT/knowledge"
        ok "staging knowledge → $CONFIG_ROOT/knowledge"
    fi

    if [ "$LEVEL" = "project" ]; then
        if python3 "$PLUGIN_ROOT/skills/tilelang2ascendc-knowledge/scripts/knowledge_store.py" \
            initialize --project-root "$TARGET_DIR" --builtin-root "$STAGING_BUILTIN_DIR" >/dev/null 2>&1; then
            STAGING_PROJECT_DIR="$TARGET_DIR/.tilelang2ascendc/knowledge"
            STAGING_STATUS="ready"
            ok "project staging knowledge → $STAGING_PROJECT_DIR"
        else
            warn "Project staging knowledge initialization failed"
            STAGING_STATUS="degraded"
        fi
    else
        # 全局安装不写当前目录；首次运行时由 Skill 按项目惰性初始化。
        STAGING_STATUS="ready"
    fi

    if [ "$STAGING_STATUS" != "ready" ]; then
        [ "$STRICT_KNOWLEDGE" -eq 1 ] && exit 2
    fi
    return 0
}

# Clean up legacy cannbot subdirectory from previous installations.
# 只清理安装器自己创建的目录（软链或含 cannbot-manifest.json），不删用户目录。
if [ -L "$CONFIG_ROOT/$BRAND" ]; then
    rm -f "$CONFIG_ROOT/$BRAND"
elif [ -d "$CONFIG_ROOT/$BRAND" ]; then
    if [ -f "$CONFIG_ROOT/$BRAND/cannbot-manifest.json" ]; then
        rm -rf "$CONFIG_ROOT/$BRAND"
    else
        warn "保留已存在的目录（非本安装器创建）: $CONFIG_ROOT/$BRAND"
    fi
fi
# OpenCode: also clean legacy teams link
if [ "$TOOL" = "opencode" ] && [ -L "$CONFIG_ROOT/teams" ]; then
    rm -f "$CONFIG_ROOT/teams"
fi

show_banner
echo "  Tool:      $TOOL"
echo "  Level:     $LEVEL"
if [ "$LEVEL" = "project" ]; then
    echo "  Target:    $TARGET_DIR"
fi
if [ "$TOOL" = "codex" ] || [ "$TOOL" = "dsh" ]; then
    echo "  Project:   $PROJECT_ROOT"
    echo "  Skills:    $SKILL_DISCOVERY_ROOT"
fi
echo "  Path:      $CONFIG_ROOT"
echo ""

# --- Knowledge setup (fixed read-only + plugin staging) ---
setup_fixed_knowledge
setup_staging_knowledge
echo ""

# --- Step 0: Confirmation before installation ---
step "[0/5] Checking items to be installed..."

# Collect skills to install (from shared ops)
SKILLS_TO_INSTALL=""
SKILL_COUNT=0
for skill_dir in "$SKILL_ROOT_COMMUNITY"/*/ "$SKILL_ROOT_OPS"/*/ "$SKILL_ROOT_KNOWLEDGE"/*/ "$SKILL_ROOT_LOCAL"/*/; do
    [ -d "$skill_dir" ] || continue
    name=$(basename "$skill_dir")
    echo "$INCLUDED_SKILLS" | tr ' ' '\n' | grep -qxF "$name" || continue
    [ -n "$EXCLUDED_SKILL" ] && [ "$name" = "$EXCLUDED_SKILL" ] && continue
    SKILLS_TO_INSTALL="$SKILLS_TO_INSTALL $name"
    SKILL_COUNT=$((SKILL_COUNT + 1))
done

# Collect agents to install (from local agents/; Codex uses TOML custom agents)
AGENTS_TO_INSTALL=""
AGENT_COUNT=0
if [ "$TOOL" = "codex" ]; then
    for agent_entry in "$CODEX_AGENT_TEMPLATE_ROOT"/*.toml; do
        [ -f "$agent_entry" ] || continue
        name=$(basename "$agent_entry")
        base="${name%.toml}"
        [[ "$base" != $INCLUDED_AGENT_PATTERN ]] && continue
        AGENTS_TO_INSTALL="$AGENTS_TO_INSTALL $name"
        AGENT_COUNT=$((AGENT_COUNT + 1))
    done
else
    for agent_entry in "$LOCAL_AGENT_ROOT"/*; do
        [ -e "$agent_entry" ] || continue
        name=$(basename "$agent_entry")
        base="${name%.md}"
        [[ "$base" != $INCLUDED_AGENT_PATTERN ]] && continue
        AGENTS_TO_INSTALL="$AGENTS_TO_INSTALL $name"
        AGENT_COUNT=$((AGENT_COUNT + 1))
    done
fi

# Display installation plan
echo ""
echo -e "${BOLD}以下内容将被安装/替换：${NC}"
echo ""

if [ "$SKILL_COUNT" -gt 0 ]; then
    echo -e "${CYAN}Skills (${SKILL_COUNT} 项)：${NC}"
    for name in $SKILLS_TO_INSTALL; do
        target="$SKILL_DISCOVERY_ROOT/$name"
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
        target="$AGENT_DISCOVERY_ROOT/$name"
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
    if [ "$AGENTS_MD_TOOL" = true ]; then
        if [ "$TOOL" = "codex" ] || [ "$TOOL" = "dsh" ]; then
            config_target="$PROJECT_ROOT/AGENTS.md"
        else
            config_target="$TARGET_DIR/AGENTS.md"
        fi
    else
        config_target="$TARGET_DIR/CLAUDE.md"
    fi
else
    if [ "$AGENTS_MD_TOOL" = true ]; then
        config_target="$CONFIG_ROOT/AGENTS.md"
    else
        config_target="$CONFIG_ROOT/CLAUDE.md"
    fi
fi
config_src="$PLUGIN_ROOT/AGENTS.md"
if [ "$AGENTS_MD_TOOL" = true ] && [ "$LEVEL" = "project" ] && [ "$config_target" = "$config_src" ]; then
    echo -e "  ${GREEN}$(basename "$config_target")${NC} (已存在，无需操作)"
elif { [ "$TOOL" = "codex" ] || [ "$TOOL" = "dsh" ]; } && [ "$LEVEL" = "project" ] && { [ -e "$config_target" ] || [ -L "$config_target" ]; }; then
    echo -e "  ${YELLOW}$(basename "$config_target")${NC} (已存在，将保留原文件)"
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
step "[1/5] Setting up CANNBot directory..."
mkdir -p "$CANNBOT_DIR"

step1_summary=""
step1_warns=""
if [ "$TOOL" = "opencode" ]; then
    # OpenCode: per-item symlinks for skills (from shared ops, whitelist filtered)
    mkdir -p "$CANNBOT_DIR/skills"
    skill_count=0
    skill_skipped=0
    for skill_dir in "$SKILL_ROOT_COMMUNITY"/*/ "$SKILL_ROOT_OPS"/*/ "$SKILL_ROOT_KNOWLEDGE"/*/ "$SKILL_ROOT_LOCAL"/*/; do
        [ -d "$skill_dir" ] || continue
        name=$(basename "$skill_dir")
        echo "$INCLUDED_SKILLS" | tr ' ' '\n' | grep -qxF "$name" || continue
        [ -n "$EXCLUDED_SKILL" ] && [ "$name" = "$EXCLUDED_SKILL" ] && continue
        target="$CANNBOT_DIR/skills/$name"
        if [ -e "$target" ] || [ -L "$target" ]; then
            if is_installer_link "$target"; then
                rm -f "$target"
            else
                warn "保留已存在条目（非本安装器创建）: $target"
                skill_skipped=$((skill_skipped + 1)); continue
            fi
        fi
        ln -sfn "$(realpath "$skill_dir")" "$target"
        skill_count=$((skill_count + 1))
    done
    step1_summary="skills(${skill_count}) "
    [ "$skill_skipped" -gt 0 ] && step1_warns="${step1_warns}\n  ${YELLOW}⚠${NC} 保留 ${skill_skipped} 个非本安装器创建的 skill 条目"

    # OpenCode: per-item symlinks for agents (from local agents/, whitelist filtered)
    mkdir -p "$CANNBOT_DIR/agents"
    agent_count=0
    agent_skipped=0
    for agent_entry in "$LOCAL_AGENT_ROOT"/*; do
        [ -e "$agent_entry" ] || continue
        name=$(basename "$agent_entry")
        base_name="${name%.md}"
        [[ "$base_name" != $INCLUDED_AGENT_PATTERN ]] && continue
        target="$CANNBOT_DIR/agents/$name"
        if [ -e "$target" ] || [ -L "$target" ]; then
            if is_installer_link "$target"; then
                rm -f "$target"
            else
                warn "保留已存在条目（非本安装器创建）: $target"
                agent_skipped=$((agent_skipped + 1)); continue
            fi
        fi
        ln -sfn "$(realpath "$agent_entry")" "$target"
        agent_count=$((agent_count + 1))
    done
    step1_summary="${step1_summary}agents(${agent_count}) "
    [ "$agent_skipped" -gt 0 ] && step1_warns="${step1_warns}\n  ${YELLOW}⚠${NC} 保留 ${agent_skipped} 个非本安装器创建的 agent 条目"

    # OpenCode: per-item symlinks for hooks (from local hooks/)
    mkdir -p "$CANNBOT_DIR/hooks"
    hook_count=0
    hook_skipped=0
    for hook_entry in "$PLUGIN_ROOT/hooks"/*; do
        [ -f "$hook_entry" ] || continue
        name=$(basename "$hook_entry")
        target="$CANNBOT_DIR/hooks/$name"
        if [ -e "$target" ] || [ -L "$target" ]; then
            if is_installer_link "$target"; then
                rm -f "$target"
            else
                warn "保留已存在条目（非本安装器创建）: $target"
                hook_skipped=$((hook_skipped + 1)); continue
            fi
        fi
        ln -sfn "$(realpath "$hook_entry")" "$target"
        hook_count=$((hook_count + 1))
    done
    step1_summary="${step1_summary}hooks(${hook_count})"
    [ "$hook_skipped" -gt 0 ] && step1_warns="${step1_warns}\n  ${YELLOW}⚠${NC} 保留 ${hook_skipped} 个非本安装器创建的 hook 条目"
    ok "Linked: $step1_summary"
else
    # Trae/Claude/Cursor/Copilot/CodeArts/Codex/DSH: create discovery directories
    mkdir -p "$SKILL_DISCOVERY_ROOT" "$AGENT_DISCOVERY_ROOT"
    if [ "$TOOL" = "codex" ] || [ "$TOOL" = "dsh" ]; then
        ok "Prepared: ${SKILL_DISCOVERY_ROOT} , ${AGENT_DISCOVERY_ROOT}"
    else
        mkdir -p "$CONFIG_ROOT/hooks"
        ok "Prepared: skills/, agents/, hooks/"
    fi
fi
[ -n "$step1_warns" ] && echo -e "$step1_warns"

# Copy attention-patterns reference from translator to tilelang-designer.
# 该派生文件只写旧布局（<repo>/ops 与 <repo>/community/ops）；skills 来自
# vendor/cannbot-skills 子模块时绝不写入，避免脏化子模块工作区。
if [ -d "$SKILLS_VENDOR/ops" ]; then
    info "skills 来自子模块，跳过 attention-patterns 派生复制（不写子模块）"
else
    ATTN_SRC="$SKILL_ROOT_COMMUNITY/tilelang2ascend-translator/references/attention-patterns"
    ATTN_DST="$SKILL_ROOT_COMMUNITY/tilelang2ascend-tilelang-designer/references/attention-patterns"
    if [ -d "$ATTN_SRC" ]; then
        mkdir -p "$(dirname "$ATTN_DST")"
        rm -rf "$ATTN_DST"
        cp -r "$ATTN_SRC" "$ATTN_DST"
        ok "attention-patterns → tilelang-designer/references/"
    else
        warn "attention-patterns source not found, skipping copy"
    fi
fi

echo ""

# --- Step 2: Install config file (AGENTS.md / CLAUDE.md) ---
step "[2/5] Installing configuration..."

if [ "$LEVEL" = "project" ]; then
    if [ "$AGENTS_MD_TOOL" = true ]; then
        if [ "$TOOL" = "codex" ] || [ "$TOOL" = "dsh" ]; then
            config_target="$PROJECT_ROOT/AGENTS.md"
        else
            config_target="$TARGET_DIR/AGENTS.md"
        fi
    else
        config_target="$TARGET_DIR/CLAUDE.md"
    fi
else
    mkdir -p "$CONFIG_ROOT"
    if [ "$AGENTS_MD_TOOL" = true ]; then
        config_target="$CONFIG_ROOT/AGENTS.md"
    else
        config_target="$CONFIG_ROOT/CLAUDE.md"
    fi
fi

config_src="$PLUGIN_ROOT/AGENTS.md"
CONFIG_SKIPPED=false

if [ "$AGENTS_MD_TOOL" = true ] && [ "$LEVEL" = "project" ] && [ "$config_target" = "$config_src" ]; then
    ok "$(basename "$config_target") already in current directory"
else
    if [ "$LEVEL" = "global" ]; then
        PLUGIN_ROOT_ABS="$(realpath "$PLUGIN_ROOT")"
        ESCAPED_ROOT="$(echo "$PLUGIN_ROOT_ABS" | sed 's/#/\\#/g')"
        RENDERED_AGENTS="$(mktemp)"
        sed \
          -e "s#bash workflows/scripts/#bash ${ESCAPED_ROOT}/workflows/scripts/#g" \
          -e "s#](workflows/#](${ESCAPED_ROOT}/workflows/#g" \
          -e "s#\`workflows/#\`${ESCAPED_ROOT}/workflows/#g" \
          "$config_src" > "$RENDERED_AGENTS"

        if [ "$TOOL" = "dsh" ]; then
            # DSH 全局 AGENTS.md 常被用户自定义指令占用：只替换本插件的受管块，
            # 保留用户内容与 dsh/ 派发协议的受管块。
            # 写前先备份（命名与 dsh/install.sh 一致，便于 uninstall.sh --purge 统一清理），
            # 使旧版整份写入的正文被替换时，用户内容仍可从备份回退。
            if [ -f "$config_target" ]; then
                DSH_AGENTS_BACKUP="${config_target}.bak.$(date +%Y%m%d%H%M%S)"
                cp -p "$config_target" "$DSH_AGENTS_BACKUP" \
                    || { err "cannot back up $config_target"; exit 1; }
                info "backup : $DSH_AGENTS_BACKUP"
                # 旧版整份写入的特征是文件以插件 frontmatter 的 "---" 开头。受管块以 <!-- 开头，
                # 但合并后的受管块正文里也含同样的 name 行，故必须同时判断首行，重复安装才不会误报。
                if head -n 1 "$config_target" | tr -d '\r' | grep -qx -- '---' \
                    && head -n 5 "$config_target" | grep -q 'name: tilelang2ascendc-ops-generator'; then
                    warn "检测到旧版整份写入的插件正文：将替换为受管块（原文件已备份，可回退）"
                fi
            fi
            python3 - "$config_target" "$RENDERED_AGENTS" <<'PY'
import os, pathlib, re, sys

target, rendered = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
instr_begin = "<!-- cannbot:tilelang2ascendc-ops-generator:instructions:start -->"
instr_end = "<!-- cannbot:tilelang2ascendc-ops-generator:instructions:end -->"
proto_begin = "<!-- cannbot:tilelang2ascendc-ops-generator:dsh-protocol:start -->"
proto_end = "<!-- cannbot:tilelang2ascendc-ops-generator:dsh-protocol:end -->"

def pattern(begin, end):
    return re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)

existing = target.read_text(encoding="utf-8") if target.exists() else ""
proto = pattern(proto_begin, proto_end).search(existing)
proto_block = proto.group(0).strip("\n") if proto else ""
rest = pattern(proto_begin, proto_end).sub("", existing)
rest = pattern(instr_begin, instr_end).sub("", rest).strip("\n")

# 旧版本整份写入的插件 AGENTS.md（无受管块）：直接替换，不当作用户内容保留
if "name: tilelang2ascendc-ops-generator" in rest[:400]:
    rest = ""

new_block = f"{instr_begin}\n{rendered.read_text(encoding='utf-8').strip()}\n{instr_end}"
target.parent.mkdir(parents=True, exist_ok=True)
new_text = (
    (rest + "\n\n" if rest else "") + new_block + "\n"
    + ("\n" + proto_block + "\n" if proto_block else "")
)
# 原子写：同目录临时文件 + os.replace，避免中途失败留下半写文件
tmp = target.with_name(target.name + f".tmp.{os.getpid()}")
tmp.write_text(new_text, encoding="utf-8")
os.replace(tmp, target)
PY
            ok "$(basename "$config_target") (merged, absolute paths for global mode)"
        else
            [ -e "$config_target" ] || [ -L "$config_target" ] && rm -f "$config_target"
            cp "$RENDERED_AGENTS" "$config_target"
            ok "$(basename "$config_target") (absolute paths for global mode)"
        fi
        rm -f "$RENDERED_AGENTS"
    elif [ "$TOOL" = "codex" ] || [ "$TOOL" = "dsh" ]; then
        # 项目级 Codex/DSH：绝不覆盖项目已有的 AGENTS.md（可能是用户自己的规范）
        if [ -L "$config_target" ] && [ "$(readlink "$config_target")" = "$config_src" ]; then
            ok "$(basename "$config_target") already linked"
        elif [ -e "$config_target" ] || [ -L "$config_target" ]; then
            CONFIG_SKIPPED=true
            warn "$config_target 已存在，未覆盖（保留原文件）"
            info "插件编排协议（AGENTS.md）未加载：如需启用请手动合并 $config_src，或改用 init.sh global $TOOL"
        else
            ln -sf "$config_src" "$config_target"
            ok "$(basename "$config_target")"
        fi
    else
        ln -sf "$config_src" "$config_target"
        ok "$(basename "$config_target")"
    fi
fi

if [ "$AGENTS_MD_TOOL" = true ] && [ "$LEVEL" = "project" ]; then
    if [ "$CONFIG_ROOT/AGENTS.md" != "$config_target" ]; then
        mkdir -p "$CONFIG_ROOT"
        ln -sf "$config_src" "$CONFIG_ROOT/AGENTS.md"
        ok "AGENTS.md → $(basename "$CONFIG_ROOT")/"
    fi
fi

# Link workflows directory
if [ -d "$PLUGIN_ROOT/workflows" ]; then
    mkdir -p "$CONFIG_ROOT"
    ln -sfn "$(realpath "$PLUGIN_ROOT/workflows")" "$CONFIG_ROOT/workflows"
    ok "workflows"
else
    warn "workflows/ not found, skipping"
fi
echo ""

# --- Step 3: Configure tool discovery ---
step "[3/5] Configuring tool discovery..."

if [ "$TOOL" = "opencode" ]; then
    ok "Auto-scan: skills/, agents/"
else
    # Trae/Claude/Cursor/Copilot/CodeArts/Codex/DSH: per-skill discovery symlinks
    DISCOVERY="$SKILL_DISCOVERY_ROOT"

    link_count=0
    link_skipped=0
    for skill_dir in "$SKILL_ROOT_COMMUNITY"/*/ "$SKILL_ROOT_OPS"/*/ "$SKILL_ROOT_KNOWLEDGE"/*/ "$SKILL_ROOT_LOCAL"/*/; do
        [ -d "$skill_dir" ] || continue
        name=$(basename "$skill_dir")
        echo "$INCLUDED_SKILLS" | tr ' ' '\n' | grep -qxF "$name" || continue
        [ -n "$EXCLUDED_SKILL" ] && [ "$name" = "$EXCLUDED_SKILL" ] && continue
        target="$DISCOVERY/$name"
        if [ -e "$target" ] || [ -L "$target" ]; then
            if is_installer_link "$target"; then
                rm -f "$target"
            else
                warn "保留已存在条目（非本安装器创建）: $target"
                link_skipped=$((link_skipped + 1)); continue
            fi
        fi
        ln -sfn "$(realpath "$skill_dir")" "$target"
        link_count=$((link_count + 1))
    done

    for link in "$DISCOVERY"/*/; do
        link="${link%/}"
        [ -L "$link" ] && [ ! -e "$link" ] && is_installer_link "$link" && rm -f "$link"
    done
    [ "$link_skipped" -gt 0 ] && warn "保留 ${link_skipped} 个非本安装器创建的 skill 条目"

    ok "Skills: $link_count discovery symlinks"

    AGENT_DISCOVERY="$AGENT_DISCOVERY_ROOT"

    if [ "$TOOL" = "codex" ]; then
        # Codex custom agents: standalone TOML files (agents/codex/*.toml) with
        # __CANNBOT_AGENT_SOURCE__ resolved to the canonical .md role definition.
        # 写真实文件而非符号链接（Codex 可能忽略被链接的 agent TOML）。
        agent_link_count=0
        agent_skipped=0
        for agent_entry in "$CODEX_AGENT_TEMPLATE_ROOT"/*.toml; do
            [ -f "$agent_entry" ] || continue
            name=$(basename "$agent_entry")
            base="${name%.toml}"
            [[ "$base" != $INCLUDED_AGENT_PATTERN ]] && continue
            target="$AGENT_DISCOVERY/$name"
            if [ -e "$target" ] || [ -L "$target" ]; then
                if [ -L "$target" ] && [ ! -e "$target" ]; then
                    rm -f "$target"            # 断链（clone 移动等）→ 重建
                elif is_installer_generated_file "$target"; then
                    rm -f "$target"
                else
                    warn "保留已存在的 Agent 文件（非本安装器生成）: $target"
                    agent_skipped=$((agent_skipped + 1)); continue
                fi
            fi
            canonical="$(realpath "$LOCAL_AGENT_ROOT/$base.md" 2>/dev/null || echo "$LOCAL_AGENT_ROOT/$base.md")"
            escaped_agent="$(echo "$canonical" | sed 's/[&|\\]/\\&/g')"
            tmpfile=$(mktemp)
            sed "s|__CANNBOT_AGENT_SOURCE__|$escaped_agent|g" "$agent_entry" > "$tmpfile"
            mv "$tmpfile" "$AGENT_DISCOVERY/$name"
            chmod 644 "$AGENT_DISCOVERY/$name"
            agent_link_count=$((agent_link_count + 1))
        done
        [ "$agent_skipped" -gt 0 ] && warn "保留 ${agent_skipped} 个非本安装器生成的 Agent 条目"
        ok "Agents: $agent_link_count Codex TOML custom agent(s)"
    else
        agent_link_count=0
        agent_skipped=0
        for agent_entry in "$LOCAL_AGENT_ROOT"/*; do
            [ -e "$agent_entry" ] || continue
            name=$(basename "$agent_entry")
            base="${name%.md}"
            [[ "$base" != $INCLUDED_AGENT_PATTERN ]] && continue
            target="$AGENT_DISCOVERY/$name"
            if [ -e "$target" ] || [ -L "$target" ]; then
                if is_installer_link "$target"; then
                    rm -f "$target"
                else
                    warn "保留已存在条目（非本安装器创建）: $target"
                    agent_skipped=$((agent_skipped + 1)); continue
                fi
            fi
            ln -sfn "$(realpath "$agent_entry")" "$target"
            agent_link_count=$((agent_link_count + 1))
        done

        for link in "$AGENT_DISCOVERY"/*; do
            [ -L "$link" ] && [ ! -e "$link" ] && is_installer_link "$link" && rm -f "$link"
        done
        [ "$agent_skipped" -gt 0 ] && warn "保留 ${agent_skipped} 个非本安装器创建的 agent 条目"

        if [ "$TOOL" = "dsh" ]; then
            ok "Agents: $agent_link_count role reference file(s) (DSH subagents are prompt-driven)"
        else
            ok "Agents: $agent_link_count discovery symlinks"
        fi
    fi

    # Codex/DSH 不安装 hook：本插件 hook 层为 Claude Code 形态
    # （hooks/hooks.json + doc_gate.py / skill_script_hook.py），Codex/DSH 的工具名、
    # 载荷字段与事件覆盖均不同；门禁由 AGENTS.md / Agent 定义 / SKILL.md 的 prompt 约束兜底。
    if [ "$TOOL" != "codex" ] && [ "$TOOL" != "dsh" ]; then
        # Trae/Claude/Cursor/Copilot/CodeArts: create per-hook discovery symlinks
        HOOK_DISCOVERY="$CONFIG_ROOT/hooks"

        hook_link_count=0
        hook_skipped=0
        for hook_entry in "$PLUGIN_ROOT/hooks"/*; do
            [ -f "$hook_entry" ] || continue   # hooks/ 下只链 hook 文件，忽略子目录
            name=$(basename "$hook_entry")
            target="$HOOK_DISCOVERY/$name"
            if [ -e "$target" ] || [ -L "$target" ]; then
                if is_installer_link "$target"; then
                    rm -f "$target"
                else
                    warn "保留已存在条目（非本安装器创建）: $target"
                    hook_skipped=$((hook_skipped + 1)); continue
                fi
            fi
            ln -sfn "$(realpath "$hook_entry")" "$target"
            hook_link_count=$((hook_link_count + 1))
        done

        for link in "$HOOK_DISCOVERY"/*; do
            [ -L "$link" ] && [ ! -e "$link" ] && is_installer_link "$link" && rm -f "$link"
        done
        [ "$hook_skipped" -gt 0 ] && warn "保留 ${hook_skipped} 个非本安装器创建的 hook 条目"

        ok "Hooks: $hook_link_count discovery symlinks"

        # --- Generate .claude/settings.json (Claude tool only) ---
        if [ "$TOOL" = "claude" ]; then
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
fi
echo ""

# --- Step 4: Setup asc-devkit ---
step "[4/5] Setting up asc-devkit..."
ASC_DEVKIT_DIR="$SCRIPT_DIR/asc-devkit"

if [ -d "$ASC_DEVKIT_DIR" ]; then
    cd "$ASC_DEVKIT_DIR"
    git checkout . 2>/dev/null || true
    git pull --quiet 2>/dev/null || warn "git pull failed, using existing version"
    cd "$SCRIPT_DIR"
    ok "asc-devkit updated"
else
    git clone --quiet https://gitcode.com/cann/asc-devkit.git "$ASC_DEVKIT_DIR" 2>/dev/null || warn "git clone failed, skipping asc-devkit"
    [ -d "$ASC_DEVKIT_DIR" ] && ok "asc-devkit cloned"
fi

if [ -d "$ASC_DEVKIT_DIR" ]; then
    python3 "$SKILL_ROOT_OPS/ascendc-docs-search/scripts/clean_markdown.py" --dir "$ASC_DEVKIT_DIR" --no-backup --quiet > /dev/null 2>&1 || warn "markdown cleanup failed"
fi

if [ "$LEVEL" = "global" ] && [ -d "$ASC_DEVKIT_DIR" ]; then
    ln -sfn "$(realpath "$ASC_DEVKIT_DIR")" "$CONFIG_ROOT/asc-devkit"
    ok "asc-devkit → $CONFIG_ROOT/"
fi
echo ""

# --- Step 5: Health check ---
step "[5/5] Running health check..."
health_ok=true
health_errors=""

for sub in skills agents hooks; do
  case "$sub" in
    skills) target="$SKILL_DISCOVERY_ROOT" ;;
    agents) target="$AGENT_DISCOVERY_ROOT" ;;
    *)      target="$CANNBOT_DIR/hooks" ;;
  esac
  if [ "$sub" = "hooks" ] && { [ "$TOOL" = "codex" ] || [ "$TOOL" = "dsh" ]; }; then
    continue
  fi
  if [ -d "$target" ]; then
    count=$(ls -d "$target"/* 2>/dev/null | wc -l)
    [ "$count" -eq 0 ] && { health_errors="${health_errors}\n  ${YELLOW}⚠${NC} $sub/ is empty"; }
  else
    health_errors="${health_errors}\n  ${RED}✗${NC} $sub/ missing"
    health_ok=false
  fi
done

# 依赖 Skill 可达性：缺失或断链即视为安装失败（避免"少装但全绿"）
MISSING_SKILLS=""
for name in $INCLUDED_SKILLS; do
  echo "$name" | grep -qi "triton" && continue
  [ -n "$EXCLUDED_SKILL" ] && [ "$name" = "$EXCLUDED_SKILL" ] && continue
  [ -e "$SKILL_DISCOVERY_ROOT/$name" ] || MISSING_SKILLS="$MISSING_SKILLS $name"
done
if [ -n "$MISSING_SKILLS" ]; then
  health_errors="${health_errors}\n  ${RED}✗${NC} missing or broken skills:$MISSING_SKILLS"
  health_ok=false
fi

if [ ! -d "$ASC_DEVKIT_DIR" ]; then
  health_errors="${health_errors}\n  ${YELLOW}⚠${NC} asc-devkit not available"
fi
if [ "$LEVEL" = "global" ] && [ ! -d "$CONFIG_ROOT/asc-devkit" ]; then
  health_errors="${health_errors}\n  ${YELLOW}⚠${NC} asc-devkit symlink missing in $CONFIG_ROOT"
fi

# 知识不可用只降级，不改变安装退出码（--strict-knowledge 已在 setup 阶段 exit 2）。
if [ "$KNOWLEDGE_DISABLED" -eq 0 ]; then
  [ "$KNOWLEDGE_STATUS" = "ready" ] || health_errors="${health_errors}\n  ${YELLOW}⚠${NC} fixed knowledge: $KNOWLEDGE_STATUS"
  [ "$KNOWLEDGE_INDEX_STATE" = "ready" ] || health_errors="${health_errors}\n  ${YELLOW}⚠${NC} knowledge index: $KNOWLEDGE_INDEX_STATE"
  [ "$KNOWLEDGE_SKILLS_STATUS" = "ready" ] || health_errors="${health_errors}\n  ${YELLOW}⚠${NC} knowledge skills: $KNOWLEDGE_SKILLS_STATUS"
fi
[ "$STAGING_STATUS" = "ready" ] || health_errors="${health_errors}\n  ${YELLOW}⚠${NC} staging knowledge: $STAGING_STATUS"

if [ "$LEVEL" = "project" ]; then
    if [ "$AGENTS_MD_TOOL" = true ]; then
        if [ "$TOOL" = "codex" ] || [ "$TOOL" = "dsh" ]; then
            if [ "$CONFIG_SKIPPED" = true ]; then
                health_errors="${health_errors}\n  ${YELLOW}⚠${NC} 项目 AGENTS.md 未替换：插件编排协议未加载（skills/agents 已安装）"
            elif [ ! -f "$PROJECT_ROOT/AGENTS.md" ]; then
                health_errors="${health_errors}\n  ${RED}✗${NC} AGENTS.md missing in project root"; health_ok=false
            fi
        else
            [ -f "$INVOCATION_DIR/AGENTS.md" ] || { health_errors="${health_errors}\n  ${RED}✗${NC} AGENTS.md missing in current directory"; health_ok=false; }
        fi
    else
        [ -f "$INVOCATION_DIR/CLAUDE.md" ] || { health_errors="${health_errors}\n  ${RED}✗${NC} CLAUDE.md missing in current directory"; health_ok=false; }
    fi
else
    if [ "$AGENTS_MD_TOOL" = true ]; then
        [ -f "$CONFIG_ROOT/AGENTS.md" ] || { health_errors="${health_errors}\n  ${RED}✗${NC} AGENTS.md missing"; health_ok=false; }
    else
        [ -f "$CONFIG_ROOT/CLAUDE.md" ] || { health_errors="${health_errors}\n  ${RED}✗${NC} CLAUDE.md missing"; health_ok=false; }
    fi
fi

# Generate brand manifest
MANIFEST="$CONFIG_ROOT/cannbot-manifest.json"

SKILLS_JSON="[]"
if [ -d "$SKILL_DISCOVERY_ROOT" ]; then
  SKILLS_JSON=$(ls -d "$SKILL_DISCOVERY_ROOT"/*/ 2>/dev/null | while read d; do
    d="${d%/}"; echo "${d##*/}"
  done | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo "[]")
fi

AGENTS_JSON="[]"
if [ -d "$AGENT_DISCOVERY_ROOT" ]; then
  AGENTS_JSON=$(ls -d "$AGENT_DISCOVERY_ROOT"/* 2>/dev/null | while read d; do
    echo "${d##*/}"
  done | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo "[]")
fi

HOOKS_JSON="[]"
if [ -d "$CANNBOT_DIR/hooks" ]; then
  HOOKS_JSON=$(ls -d "$CANNBOT_DIR/hooks"/* 2>/dev/null | while read d; do
    echo "${d##*/}"
  done | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo "[]")
fi

KNOWLEDGE_JSON=$(python3 - \
  "$KNOWLEDGE_STATUS" "$KNOWLEDGE_DIR" "$KNOWLEDGE_COMMIT" "$KNOWLEDGE_INDEX" \
  "$KNOWLEDGE_INDEX_STATE" "$STAGING_BUILTIN_DIR" "$STAGING_PROJECT_DIR" \
  "$STAGING_STATUS" "$KNOWLEDGE_PLATFORM" "$KNOWLEDGE_SKILLS_STATUS" <<'PY'
import datetime
import json
import sys

(status, root, commit, index, index_state, builtin, project,
 staging_status, platform, skills_status) = sys.argv[1:]
print(json.dumps({
    "fixed": {
        "root": root or None,
        "commit": commit or None,
        "index": index or None,
        "indexState": index_state,
        "status": status,
    },
    "staging": {
        "builtin": builtin or None,
        "project": project or None,
        "status": staging_status,
    },
    "skills": skills_status,
    "platform": platform or None,
    "checkedAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
}, ensure_ascii=False))
PY
) || KNOWLEDGE_JSON='{"status":"unknown"}'

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
  "knowledge": $KNOWLEDGE_JSON,
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
if [ "$health_ok" != true ]; then
  echo -e "  ${RED}${BOLD}✗ CANNBot tilelang2ascendc-ops-generator 安装未通过健康检查，请先处理上面的错误${NC}"
  echo ""
  exit 1
fi
echo -e "  ${GREEN}${BOLD}✓ CANNBot tilelang2ascendc-ops-generator installed successfully!${NC}"
echo ""
echo -e "  ${BOLD}Quick Start:${NC}"
if [ "$TOOL" = "opencode" ]; then
  echo -e "  ${CYAN}1.${NC} 启动 CLI: ${GREEN}opencode${NC}"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}生成ascendC算子，npu=0，算子描述文件为 /path/to/op.py，输出到 /path/to/output/${NC}"
elif [ "$TOOL" = "codex" ]; then
  echo -e "  ${CYAN}1.${NC} 在项目根启动: ${GREEN}codex${NC}"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}生成ascendC算子，npu=0，算子描述文件为 /path/to/op.py，输出到 /path/to/output/${NC}"
  echo -e "  ${DIM}自定义 Agent: $AGENT_DISCOVERY_ROOT/tilelang2ascendc-kernel-generator.toml${NC}"
elif [ "$TOOL" = "dsh" ]; then
  echo -e "  ${CYAN}1.${NC} 启动: ${GREEN}dsh${NC}"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}生成ascendC算子，npu=0，算子描述文件为 /path/to/op.py，输出到 /path/to/output/${NC}"
  echo -e "  ${DIM}子 Agent 为 prompt 驱动；角色定义参考: $AGENT_DISCOVERY_ROOT/tilelang2ascendc-kernel-generator.md${NC}"
  echo -e "  ${DIM}派发协议适配器（可选）: bash dsh/install.sh${NC}"
elif [ "$TOOL" = "trae" ]; then
  echo -e "  ${CYAN}1.${NC} 通过 CLI/IDE 启动${NC}"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}生成ascendC算子，npu=0，算子描述文件为 /path/to/op.py，输出到 /path/to/output/${NC}"
elif [ "$TOOL" = "cursor" ]; then
  echo -e "  ${CYAN}1.${NC} 启动 Cursor IDE"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}生成ascendC算子，npu=0，算子描述文件为 /path/to/op.py，输出到 /path/to/output/${NC}"
elif [ "$TOOL" = "copilot" ]; then
  echo -e "  ${CYAN}1.${NC} 通过 GitHub Copilot CLI / IDE 启动${NC}"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}生成ascendC算子，npu=0，算子描述文件为 /path/to/op.py，输出到 /path/to/output/${NC}"
elif [ "$TOOL" = "codearts" ]; then
  echo -e "  ${CYAN}1.${NC} 通过 CodeArts CLI / IDE 启动${NC}"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}生成ascendC算子，npu=0，算子描述文件为 /path/to/op.py，输出到 /path/to/output/${NC}"
else
  echo -e "  ${CYAN}1.${NC} 启动 CLI: ${GREEN}claude${NC}"
  echo -e "  ${CYAN}2.${NC} 输入需求: ${GREEN}${BOLD}生成ascendC算子，npu=0，算子描述文件为 /path/to/op.py，输出到 /path/to/output/${NC}"
fi
echo ""
exit 0
