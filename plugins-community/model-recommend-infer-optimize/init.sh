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

# Safe install config file with backup and conflict handling.
# $1 = generated temp file path
# $2 = target file path
# $3 = display name
# $4 = install level (global/project)
safe_install_file() {
    local tmpfile="$1"
    local target="$2"
    local name="$3"
    local level="$4"

    if [ -e "$target" ] && diff -q "$tmpfile" "$target" > /dev/null 2>&1; then
        info "$name already up to date"
        rm -f "$tmpfile"
        return 0
    fi

    if [ -e "$target" ] || [ -L "$target" ]; then
        local backup
        backup="${target}.bak.$(date +%Y%m%d_%H%M%S)"
        cp -a "$target" "$backup"
        warn "$name already exists, backed up to $(basename "$backup")"

        if [ "$level" = "global" ] && [ -t 0 ] && [ -t 1 ]; then
            echo ""
            echo -e "  ${BOLD}${YELLOW}⚠  $name 存在自定义内容，请选择操作：${NC}"
            echo -e "    ${BOLD}[O]${NC} 覆盖      - 用插件内容替换（原内容已备份）"
            echo -e "    ${BOLD}[M]${NC} 合并      - 插件内容置顶，保留原自定义内容"
            echo -e "    ${BOLD}[S]${NC} 跳过      - 保持现有文件不变"
            printf "  ${BOLD}${CYAN}→${NC} ${BOLD}请输入选择 [O/M/S]:${NC} "
            read -r choice < /dev/tty
            case "$choice" in
                [Mm]*)
                    cat "$tmpfile" > "${target}.new"
                    echo "" >> "${target}.new"
                    echo "<!-- === User custom content below === -->" >> "${target}.new"
                    echo "" >> "${target}.new"
                    cat "$target" >> "${target}.new"
                    mv "${target}.new" "$target"
                    ok "$name (merged with backup)"
                    rm -f "$tmpfile"
                    return 0
                    ;;
                [Ss]*)
                    info "$name skipped (backup preserved)"
                    rm -f "$tmpfile"
                    return 0
                    ;;
                *) ;;
            esac
        fi
    fi

    mv "$tmpfile" "$target"
    ok "$name"
}

# Detect TRAE variant by scanning global config directories.
# Sets global: TRAE_VARIANT=(ide|plugin|cli|unknown)
detect_trae_variant() {
    if [ -d "$HOME/.trae-cn" ]; then
        TRAE_VARIANT="ide"
    elif [ -d "$HOME/.marscode" ]; then
        TRAE_VARIANT="plugin"
    elif [ -d "$HOME/.traecli" ]; then
        TRAE_VARIANT="cli"
    else
        TRAE_VARIANT="unknown"
    fi
}

BRAND="cannbot"
VERSION="1.0.0"

# 18 个原子 skill（来自 cannbot-skills 的 community/model，安装时装配到 skills/）
INCLUDED_SKILLS="model-recommend-ascend-env-baseline model-recommend-structure-analysis model-recommend-baseline-run model-recommend-concurrency-strategy-analysis model-recommend-precision-comparison model-recommend-performance-analysis model-recommend-profiling-deep-analysis model-recommend-optimization-loop model-recommend-ge-graph-optimization model-recommend-fusion-operator-adaptation model-recommend-flash-attention-fusion model-recommend-multi-thread-optimization model-recommend-memory-access-optimize model-recommend-fusion-planning-estimation model-recommend-kernel-generation model-recommend-custom-op-development model-recommend-runtime-debug model-recommend-regression-baseline-mgmt"
INCLUDED_AGENT_PATTERN="model-recommend-infer-*"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$SCRIPT_DIR"
LOCAL_AGENT_ROOT="$PLUGIN_ROOT/agents"
# Codex custom agents use standalone TOML definitions.
CODEX_AGENT_ROOT="$LOCAL_AGENT_ROOT/codex"

show_help() {
    cat << EOF
CANNBot - Recommend Model Inference Optimization Installer

Usage: init.sh [level] [tool] [install_path]

Arguments:
  level        - Installation level: "project" (default) or "global"
  tool         - Target tool: "opencode" (default), "claude", "trae", "cursor", "codex", "copilot", "codearts", or "dsh"
  install_path - Project-level installation directory (default: current working directory)

Options:
  --help  - Show this help message

Examples:
  init.sh project opencode
  init.sh project claude
  init.sh project trae
  init.sh project cursor
  init.sh project codex
  init.sh global codex
  init.sh project copilot
  init.sh project codearts
  init.sh global copilot
  init.sh global claude
  init.sh global cursor
  init.sh project opencode /path/to/proj
EOF
}

LEVEL="project"
TOOL="opencode"
INSTALL_PATH=""

for arg in "$@"; do
    case "$arg" in
        --help) show_help; exit 0 ;;
        global|project) LEVEL="$arg" ;;
        opencode|claude|trae|cursor|codex|copilot|codearts|dsh) TOOL="$arg" ;;
    esac
done

if [ $# -gt 0 ]; then
    last_arg="${!#}"
    case "$last_arg" in
        --help|global|project|opencode|claude|trae|cursor|codex|copilot|codearts|dsh) ;;
        *) INSTALL_PATH="$last_arg" ;;
    esac
fi

# 末位未知参数按 install_path 处理，但路径必须存在，否则给出明确错误而不是 cd 报错
if [ -n "$INSTALL_PATH" ] && [ ! -d "$INSTALL_PATH" ]; then
    err "install_path 不存在或不是目录：$INSTALL_PATH"
    echo "  用法：bash init.sh [project|global] [tool] [install_path]（--help 查看全部参数）"
    exit 1
fi

# 18 个原子 Skill 来自 cannbot-skills 子模块的 community/model（见下方 SKILL_SRC_ROOT）。
# Skill 来源：cannbot-skills 子模块的 community/model（本插件不再自带 skills/）
# 可用 CANNBOT_SKILL_SRC_ROOT 覆盖（便于同仓调试或离线副本）；
# 该变量可指向 cannbot-skills 仓根，也可直接指向 community/model，两种写法都接受。
SKILL_SRC_ROOT="${CANNBOT_SKILL_SRC_ROOT:-}"
if [ -n "$SKILL_SRC_ROOT" ] && [ -d "$SKILL_SRC_ROOT/community/model" ]; then
    SKILL_SRC_ROOT="$SKILL_SRC_ROOT/community/model"
fi
if [ -z "$SKILL_SRC_ROOT" ]; then
    for candidate in \
        "$PLUGIN_ROOT/../../vendor/cannbot-skills/community/model" \
        "$PLUGIN_ROOT/vendor/cannbot-skills/community/model"; do
        if [ -d "$candidate" ]; then
            SKILL_SRC_ROOT="$(cd "$candidate" && pwd)"
            break
        fi
    done
fi
if [ -z "$SKILL_SRC_ROOT" ] || [ ! -d "$SKILL_SRC_ROOT" ]; then
    err "skills not found: 需要 vendor/cannbot-skills 子模块（community/model），或设置 CANNBOT_SKILL_SRC_ROOT"
    err "  git submodule update --init --recursive --depth 1 vendor/cannbot-skills"
    exit 1
fi

if [ "$LEVEL" = "global" ]; then
    if [ "$TOOL" = "opencode" ]; then
        CONFIG_ROOT="$HOME/.config/opencode"
    elif [ "$TOOL" = "trae" ]; then
        detect_trae_variant
        case "$TRAE_VARIANT" in
            plugin) CONFIG_ROOT="$HOME/.marscode" ;;
            cli)    CONFIG_ROOT="$HOME/.traecli" ;;
            *)      CONFIG_ROOT="$HOME/.trae-cn" ;;
        esac
    elif [ "$TOOL" = "cursor" ]; then
        CONFIG_ROOT="$HOME/.cursor"
    elif [ "$TOOL" = "codex" ]; then
        CONFIG_ROOT="$HOME/.codex"
    elif [ "$TOOL" = "copilot" ]; then
        CONFIG_ROOT="$HOME/.copilot"
    elif [ "$TOOL" = "codearts" ]; then
        CONFIG_ROOT="$HOME/.codeartsdoer"
    elif [ "$TOOL" = "dsh" ]; then
        CONFIG_ROOT="$HOME/.dsh"
    else
        CONFIG_ROOT="$HOME/.claude"
    fi
else
    if [ -n "$INSTALL_PATH" ]; then
        CONFIG_ROOT_BASE="$(cd "$INSTALL_PATH" && pwd)"
    else
        CONFIG_ROOT_BASE="$PWD"
    fi

    if [ "$TOOL" = "opencode" ]; then
        CONFIG_ROOT="$CONFIG_ROOT_BASE/.opencode"
    elif [ "$TOOL" = "trae" ]; then
        detect_trae_variant
        case "$TRAE_VARIANT" in
            plugin) CONFIG_ROOT="$CONFIG_ROOT_BASE/.marscode" ;;
            cli)    CONFIG_ROOT="$CONFIG_ROOT_BASE/.traecli" ;;
            *)      CONFIG_ROOT="$CONFIG_ROOT_BASE/.trae" ;;
        esac
    elif [ "$TOOL" = "cursor" ]; then
        CONFIG_ROOT="$CONFIG_ROOT_BASE/.cursor"
    elif [ "$TOOL" = "codex" ]; then
        CONFIG_ROOT="$CONFIG_ROOT_BASE/.codex"
    elif [ "$TOOL" = "copilot" ]; then
        CONFIG_ROOT="$CONFIG_ROOT_BASE/.github"
    elif [ "$TOOL" = "codearts" ]; then
        CONFIG_ROOT="$CONFIG_ROOT_BASE/.codeartsdoer"
    elif [ "$TOOL" = "dsh" ]; then
        CONFIG_ROOT="$CONFIG_ROOT_BASE/.dsh"
    else
        CONFIG_ROOT="$CONFIG_ROOT_BASE/.claude"
    fi
fi

CANNBOT_DIR="$CONFIG_ROOT"
SKILL_DISCOVERY_ROOT="$CONFIG_ROOT/skills"
AGENT_DISCOVERY_ROOT="$CONFIG_ROOT/agents"
if [ "$TOOL" = "codex" ]; then
    if [ "$LEVEL" = "global" ]; then
        SKILL_DISCOVERY_ROOT="$HOME/.agents/skills"
    else
        SKILL_DISCOVERY_ROOT="$CONFIG_ROOT_BASE/.agents/skills"
    fi
fi

if [ -e "$CONFIG_ROOT/$BRAND" ] || [ -L "$CONFIG_ROOT/$BRAND" ]; then
    rm -rf "$CONFIG_ROOT/$BRAND"
fi
if [ "$TOOL" = "opencode" ] && [ -L "$CONFIG_ROOT/teams" ]; then
    rm -f "$CONFIG_ROOT/teams"
fi

show_banner() {
  echo ""
  echo -e "${CYAN}"
  cat << 'BANNER'
   ____    _    _   _ _   _ ____        _
  / ___|  / \  | \ | | \ | | __ )  ___ | |_
 | |     / _ \ |  \| |  \| |  _ \ / _ \| __|
 | |___ / ___ \| |\  | |\  | |_) | (_) | |_
  \____/_/   \_\_| \_|_| \_|____/ \___/ \__|
BANNER
  echo -e "${NC}"
  echo -e "  ${BOLD}Recommend Model Inference Optimization${NC}"
  echo ""
}

resolve_skill_src() {
    local skill="$1"
    if [ -d "$SKILL_SRC_ROOT/$skill" ]; then
        echo "$SKILL_SRC_ROOT/$skill"
    else
        echo ""
    fi
}

# 优先软链（可随源更新）；软链不可用时降级为复制，避免安装失败
# （Windows / MSYS 环境下 ln -s 可能受权限与路径改写影响）
link_or_copy() {
    local src="$1"
    local dst="$2"
    rm -rf "$dst"
    if ln -sfn "$(realpath "$src")" "$dst" 2>/dev/null && [ -e "$dst" ]; then
        return 0
    fi
    rm -rf "$dst"
    cp -r "$src" "$dst"
    warn "symlink unavailable: $(basename "$dst") copied instead"
    return 0
}

# 单文件版本：软链失败则复制
link_or_copy_file() {
    local src="$1"
    local dst="$2"
    rm -f "$dst"
    if ln -sf "$(realpath "$src")" "$dst" 2>/dev/null && [ -e "$dst" ]; then
        return 0
    fi
    rm -f "$dst"
    cp "$src" "$dst"
    warn "symlink unavailable: $(basename "$dst") copied instead"
    return 0
}

# 覆盖前备份：任何已存在的文件/目录先留一份，返回备份路径到 BACKUP_PATH
backup_path() {
    local target="$1"
    BACKUP_PATH=""
    if [ -e "$target" ] || [ -L "$target" ]; then
        local bak="${target}.bak.$(date +%Y%m%d_%H%M%S)"
        if cp -a "$target" "$bak" 2>/dev/null; then
            BACKUP_PATH="$bak"
            warn "backed up $(basename "$target") -> $(basename "$bak")"
        else
            warn "backup failed for $(basename "$target"); continuing"
        fi
    fi
}

# AGENTS.md / CLAUDE.md 用 marker 块合并，避免覆盖用户或其它插件的指令
MARK_BEGIN="<!-- CANNBOT-BEGIN model-recommend-infer-optimize -->"
MARK_END="<!-- CANNBOT-END model-recommend-infer-optimize -->"

install_markdown_block() {
    local src="$1"
    local target="$2"
    local name="$3"
    local block
    block="$(mktemp)"
    { echo "$MARK_BEGIN"; cat "$src"; echo "$MARK_END"; } > "$block"

    if [ ! -e "$target" ]; then
        mv "$block" "$target"
        ok "$name"
        return 0
    fi

    local mode="append"
    grep -qF "$MARK_BEGIN" "$target" 2>/dev/null && mode="replace"

    # 追加会改动用户原有内容，先备份；替换是幂等的，不产生备份噪音
    if [ "$mode" = "append" ]; then
        backup_path "$target"
    fi

    python3 - "$target" "$block" "$MARK_BEGIN" "$MARK_END" "$mode" << 'PYEOF'
import sys

target, block_path, begin, end, mode = sys.argv[1:6]
with open(target, encoding="utf-8") as fh:
    current = fh.read()
with open(block_path, encoding="utf-8") as fh:
    block = fh.read().rstrip("\n")

if mode == "replace":
    i = current.find(begin)
    j = current.find(end, i + len(begin)) if i >= 0 else -1
    if i >= 0 and j > i:
        merged = current[:i] + block + current[j + len(end):]
    else:  # 标记残缺：去掉孤立标记后追加
        cleaned = current.replace(begin, "").replace(end, "")
        merged = cleaned.rstrip("\n") + "\n\n" + block + "\n"
else:
    merged = current.rstrip("\n") + "\n\n" + block + "\n"

if not merged.endswith("\n"):
    merged += "\n"
with open(target, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(merged)
PYEOF
    local rc=$?
    rm -f "$block"
    if [ $rc -ne 0 ]; then
        err "$name 合并失败（未修改原文件）"
        return 1
    fi
    ok "$name ($mode)"
}

install_skill_links() {
    local target_root="$1"
    mkdir -p "$target_root"
    local count=0
    for skill in $INCLUDED_SKILLS; do
        local src
        src=$(resolve_skill_src "$skill")
        if [ -n "$src" ]; then
            link_or_copy "$src" "$target_root/$skill"
            count=$((count + 1))
        else
            warn "Skill not found: $skill"
        fi
    done
    local expected
    expected=$(echo $INCLUDED_SKILLS | wc -w | tr -d ' ')
    if [ "$count" -lt "$expected" ]; then
        err "Skills: $count/$expected linked —— 缺失项不会安装，检查 SKILL_SRC_ROOT=$SKILL_SRC_ROOT"
        SKILLS_INCOMPLETE=1
    else
        ok "Skills: $count linked"
    fi
}

install_agent_links() {
    local target_root="$1"
    local count=0
    if [ "$TOOL" = "codex" ]; then
        # Codex may ignore symlinked custom-agent TOML files (openai/codex#15345).
        # Install regular TOML files so that multiple plugins can coexist in the same
        # .codex/agents/ directory. The canonical role Markdown is installed next to
        # the TOML, so the adapter never falls back to the source repository path.
        mkdir -p "$target_root"
        for agent_entry in "$CODEX_AGENT_ROOT"/*.toml; do
            [ -f "$agent_entry" ] || continue
            local name base canonical_agent tmpfile
            name=$(basename "$agent_entry")
            base="${name%.toml}"
            [[ "$base" != $INCLUDED_AGENT_PATTERN ]] && continue
            canonical_agent="$LOCAL_AGENT_ROOT/$base.md"
            # safe_install_file 以 mv 消费入参，必须传临时副本，否则会把源仓文件搬走
            tmpfile=$(mktemp)
            cp "$agent_entry" "$tmpfile"
            safe_install_file "$tmpfile" "$target_root/$name" "$name" "$LEVEL"
            if [ -f "$canonical_agent" ]; then
                tmpfile=$(mktemp)
                cp "$canonical_agent" "$tmpfile"
                safe_install_file "$tmpfile" "$target_root/$base.md" "$base.md" "$LEVEL"
            fi
            count=$((count + 1))
        done
        ok "Agents: $count compatible TOML files (+ role Markdown)"
    else
        mkdir -p "$target_root"
        for agent_entry in "$LOCAL_AGENT_ROOT"/*; do
            [ -e "$agent_entry" ] || continue
            local name base
            name=$(basename "$agent_entry")
            base="${name%.*}"
            [[ "$base" != $INCLUDED_AGENT_PATTERN ]] && continue
            rm -f "$target_root/$name"
            if ! ln -sfn "$(realpath "$agent_entry")" "$target_root/$name" 2>/dev/null || [ ! -e "$target_root/$name" ]; then
                rm -f "$target_root/$name"
                cp "$agent_entry" "$target_root/$name"
                warn "symlink unavailable: $name copied instead"
            fi
            count=$((count + 1))
        done
        ok "Agents: $count linked"
    fi
}

install_config() {
    mkdir -p "$CONFIG_ROOT"
    local config_src="$PLUGIN_ROOT/AGENTS.md"
    local config_target
    if [ "$LEVEL" = "project" ]; then
        if [ "$TOOL" = "opencode" ] || [ "$TOOL" = "trae" ] || [ "$TOOL" = "cursor" ] || [ "$TOOL" = "codex" ] || [ "$TOOL" = "copilot" ] || [ "$TOOL" = "codearts" ]; then
            config_target="$CONFIG_ROOT_BASE/AGENTS.md"
        else
            config_target="$CONFIG_ROOT_BASE/CLAUDE.md"
        fi
    else
        if [ "$TOOL" = "opencode" ] || [ "$TOOL" = "trae" ] || [ "$TOOL" = "cursor" ] || [ "$TOOL" = "codex" ] || [ "$TOOL" = "copilot" ] || [ "$TOOL" = "codearts" ]; then
            config_target="$CONFIG_ROOT/AGENTS.md"
        else
            config_target="$CONFIG_ROOT/CLAUDE.md"
        fi
    fi

    if { [ "$TOOL" = "opencode" ] || [ "$TOOL" = "trae" ] || [ "$TOOL" = "cursor" ] || [ "$TOOL" = "codex" ] || [ "$TOOL" = "copilot" ] || [ "$TOOL" = "codearts" ]; } && [ "$LEVEL" = "project" ] && [ "$(realpath "$PLUGIN_ROOT")" = "$(realpath "$CONFIG_ROOT_BASE")" ]; then
        ok "$(basename "$config_target") already in current directory"
    else
        install_markdown_block "$config_src" "$config_target" "$(basename "$config_target")"
    fi

    if [ "$LEVEL" = "project" ] && [ "$config_target" != "$CONFIG_ROOT/$(basename "$config_target")" ]; then
        install_markdown_block "$config_src" "$CONFIG_ROOT/$(basename "$config_target")" "$(basename "$config_target")"
    fi
}

install_workflows() {
    if [ -d "$PLUGIN_ROOT/workflows" ]; then
        mkdir -p "$CONFIG_ROOT"
        if [ -e "$CONFIG_ROOT/workflows" ] || [ -L "$CONFIG_ROOT/workflows" ]; then
            local cur
            cur="$(realpath "$CONFIG_ROOT/workflows" 2>/dev/null || echo "")"
            if [ "$cur" != "$(realpath "$PLUGIN_ROOT/workflows")" ]; then
                backup_path "$CONFIG_ROOT/workflows"
                warn "workflows/ 为插件独占目录；若与其它插件共存，合并后请改用命名空间"
            fi
        fi
        link_or_copy "$PLUGIN_ROOT/workflows" "$CONFIG_ROOT/workflows"
        ok "workflows"
    fi
}

install_hooks() {
    if { [ "$TOOL" = "claude" ] || [ "$TOOL" = "cursor" ]; } && [ -d "$PLUGIN_ROOT/hooks" ]; then
        local hook_target_root="$CONFIG_ROOT/hooks"
        mkdir -p "$hook_target_root"
        for hook_file in "$PLUGIN_ROOT/hooks"/*.py; do
            [ -f "$hook_file" ] || continue
            link_or_copy_file "$hook_file" "$hook_target_root/$(basename "$hook_file")"
        done

        local hooks_abs_dir
        hooks_abs_dir="$(cd "$PLUGIN_ROOT/hooks" && pwd)"
        # 已有 settings.json 时按 JSON 合并（保留其他插件/用户配置），不再整体跳过
        if [ -f "$CONFIG_ROOT/settings.json" ]; then
            backup_path "$CONFIG_ROOT/settings.json"
        fi
        python3 - "$CONFIG_ROOT/settings.json" "$hooks_abs_dir" << 'PYEOF'
import json, os, sys

path, hooks_dir = sys.argv[1], sys.argv[2]
hooks_dir = hooks_dir.replace("\\", "/")

data = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON is not an object")
    except Exception as exc:  # 解析失败：不动原文件，交由调用方告警
        sys.stderr.write("PARSE_FAIL %s\n" % exc)
        sys.exit(2)

hooks = data.get("hooks")
if not isinstance(hooks, dict):
    hooks = {}
    data["hooks"] = hooks

spec = {
    "SessionStart": ("startup|resume|clear|compact", "session_start.py"),
    "PreToolUse": ("Edit|Write|MultiEdit", "pre_tool_use.py"),
}
for event, (matcher, script) in spec.items():
    command = 'python3 "%s/%s"' % (hooks_dir, script)
    kept = []
    for entry in hooks.get(event) or []:
        if not isinstance(entry, dict):
            kept.append(entry)
            continue
        inner = [h for h in (entry.get("hooks") or []) if script not in str((h or {}).get("command", ""))]
        if inner:
            entry["hooks"] = inner
            kept.append(entry)
    kept.append({"matcher": matcher, "hooks": [{"type": "command", "command": command}]})
    hooks[event] = kept

tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
os.replace(tmp, path)
PYEOF
        if [ $? -eq 0 ]; then
            ok "settings.json (hooks merged)"
        else
            err "settings.json 解析失败，未写入 hooks；请手工合并 $hooks_abs_dir 下的两个 hook"
        fi
    fi
}

install_framework() {
    local src="$PLUGIN_ROOT/framework/GE_SESSION_DEMO"
    local dst
    if [ ! -d "$src" ]; then
        warn "bundled framework missing: $src"
        return 0
    fi
    if [ "$LEVEL" = "global" ]; then
        info "global install: framework not copied; copy it into each project root:"
        info "  cp -r $src <project>/GE_SESSION_DEMO && cd <project>/GE_SESSION_DEMO && bash compile.sh"
        return 0
    fi
    dst="$CONFIG_ROOT_BASE/GE_SESSION_DEMO"
    FRAMEWORK_DIR="$dst"
    if [ -d "$dst" ]; then
        ok "GE_SESSION_DEMO (existing kept): $dst"
        return 0
    fi
    mkdir -p "$dst" 2>/dev/null || { warn "cannot create $dst"; FRAMEWORK_DIR=""; return 0; }
    cp -R "$src/." "$dst/" 2>/dev/null || { warn "copy failed: $src -> $dst"; FRAMEWORK_DIR=""; return 0; }
    ok "GE_SESSION_DEMO: $dst"
}

write_manifest() {
    local manifest="$CONFIG_ROOT/cannbot-manifest.json"
    local skills_json agents_json
    skills_json=$(ls -d "$SKILL_DISCOVERY_ROOT"/*/ 2>/dev/null | while read d; do d="${d%/}"; echo "${d##*/}"; done | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo "[]")
    agents_json=$(ls -d "$AGENT_DISCOVERY_ROOT"/* 2>/dev/null | while read d; do echo "${d##*/}"; done | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo "[]")
    cat > "$manifest" << EOF
{
  "brand": "CANNBot",
  "version": "$VERSION",
  "team": "model-recommend-infer-optimize",
  "level": "$LEVEL",
  "tool": "$TOOL",
  "installed_skills": $skills_json,
  "installed_agents": $agents_json,
  "brand_dir": "$CONFIG_ROOT",
  "skills_dir": "$SKILL_DISCOVERY_ROOT",
  "agents_dir": "$AGENT_DISCOVERY_ROOT",
  "framework_dir": "${FRAMEWORK_DIR:-}",
  "install_time": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
    ok "Manifest: $manifest"
}

show_banner
echo "  Tool:      $TOOL"
echo "  Level:     $LEVEL"
echo "  Path:      $CONFIG_ROOT"
if [ "$TOOL" = "codex" ]; then
    echo "  Skills:    $SKILL_DISCOVERY_ROOT"
    echo "  Subagents: $AGENT_DISCOVERY_ROOT"
fi
echo ""

if [ "$TOOL" = "trae" ] && [ "$LEVEL" = "project" ]; then
    case "$TRAE_VARIANT" in
        ide)     info "Detected: TRAE IDE (.trae-cn / .trae)" ;;
        plugin)  info "Detected: TRAE Plugin (.marscode)" ;;
        cli)     info "Detected: TRAE CLI (.traecli)" ;;
        unknown) warn "TRAE variant not detected; defaulting to IDE path" ;;
    esac
    echo ""
fi

step "[1/6] Installing skills and agents..."
mkdir -p "$CANNBOT_DIR"
install_skill_links "$SKILL_DISCOVERY_ROOT"
install_agent_links "$AGENT_DISCOVERY_ROOT"
echo ""

step "[2/6] Installing configuration..."
install_config
install_workflows
echo ""

step "[3/6] Installing hooks..."
install_hooks
echo ""

step "[4/6] Installing framework (bundled GE_SESSION_DEMO)..."
install_framework
echo ""

step "[5/6] Writing manifest..."
write_manifest
echo ""

step "[6/6] Health check..."
health_ok=true
[ -d "$SKILL_DISCOVERY_ROOT" ] || { err "skills/ missing"; health_ok=false; }
if [ "${SKILLS_INCOMPLETE:-0}" = "1" ]; then
    err "skills/ incomplete: $SKILL_SRC_ROOT 下缺少部分 Skill（清单见上方告警），安装不完整"
    health_ok=false
fi
[ -d "$AGENT_DISCOVERY_ROOT" ] || { err "agents/ missing"; health_ok=false; }
[ -f "$CONFIG_ROOT/cannbot-manifest.json" ] || { err "manifest missing"; health_ok=false; }
[ -d "$CONFIG_ROOT/workflows" ] || { err "workflows/ missing"; health_ok=false; }
# hooks 只对 claude / cursor 注册；注册失败必须让健康检查失败，避免"静默不生效却显示通过"
if [ "$TOOL" = "claude" ] || [ "$TOOL" = "cursor" ]; then
    if [ -f "$CONFIG_ROOT/settings.json" ] && grep -q "pre_tool_use.py" "$CONFIG_ROOT/settings.json"; then
        ok "hooks registered in settings.json"
    else
        err "hooks not registered in settings.json"; health_ok=false
    fi
fi

# GE_SESSION_DEMO 是 onnx 输入路径的执行入口，内置框架已随插件安装（project 级自动复制）
if [ "$LEVEL" = "project" ] && [ ! -d "$CONFIG_ROOT_BASE/GE_SESSION_DEMO" ]; then
    warn "GE_SESSION_DEMO not found at $CONFIG_ROOT_BASE; copy it from $PLUGIN_ROOT/framework/GE_SESSION_DEMO"
    warn "  then: cd GE_SESSION_DEMO && bash compile.sh"
fi

if [ "$health_ok" = true ]; then
    ok "All checks passed"
else
    exit 1
fi

echo ""
echo -e "  ${GREEN}${BOLD}✓ model-recommend-infer-optimize installed successfully!${NC}"
echo ""
echo -e "  ${BOLD}Quick Start:${NC}"
RIO_PROMPT='帮我优化 <model_name> 推荐模型的 NPU 推理性能'
if [ "$TOOL" = "codearts" ]; then
  echo -e "  ${CYAN}1.${NC} 通过 CodeArts CLI / IDE 启动"
  echo -e "  ${CYAN}2.${NC} 输入：${GREEN}${BOLD}${RIO_PROMPT}${NC}"
elif [ "$TOOL" = "copilot" ]; then
  echo -e "  ${CYAN}1.${NC} 通过 GitHub Copilot CLI / IDE 启动"
  echo -e "  ${CYAN}2.${NC} 输入：${GREEN}${BOLD}${RIO_PROMPT}${NC}"
elif [ "$TOOL" = "codex" ]; then
  echo -e "  ${CYAN}1.${NC} 启动 CLI: ${GREEN}codex${NC}"
  echo -e "  ${CYAN}2.${NC} 输入：${GREEN}${BOLD}${RIO_PROMPT}${NC}"
else
  echo -e "  ${CYAN}1.${NC} 在目标模型仓中启动工具"
  echo -e "  ${CYAN}2.${NC} 输入：${GREEN}${BOLD}${RIO_PROMPT}${NC}"
fi
echo ""
