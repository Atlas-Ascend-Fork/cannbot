#!/usr/bin/env bash
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

PLUGIN_ID="triton-auto-evolve"
VERSION="0.5.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$SCRIPT_DIR"
LOCAL_HOOK_ROOT="$PLUGIN_ROOT/hooks"

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

# Plugin-local control skills source
LOCAL_CTRL_SKILLS_DIR="$PLUGIN_ROOT/skills"

find_ops_root() {
    # 显式指定的共享 skills 仓优先（--skills <path> / CANNBOT_SKILLS_ROOT）
    local override
    for override in "${SKILLS_ARG:-}" "${CANNBOT_SKILLS_ROOT:-}"; do
        [ -n "$override" ] || continue
        if [ -d "$override/ops" ]; then
            cd "$override/ops" && pwd
            return 0
        fi
    done
    # Shared ops directory lives in the vendor/cannbot-skills submodule,
    # resolved relative to the repository root so any clone location works.
    local candidate="$PLUGIN_ROOT/../../vendor/cannbot-skills/ops"
    if [ -d "$candidate" ]; then
        cd "$candidate" && pwd
        return 0
    fi
    return 1
}

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
  echo -e "  ${BOLD}Triton Optimizer — Multi-Agent Orchestrator${NC}"
  echo ""
}

show_help() {
    cat << EOF
CANNBot - Triton Auto Evolve Installer

Usage: init.sh [level] [tool] [install_path] [--skills <path|SHA>]

Arguments:
  level        - Installation level: "project" (default) or "global"
  tool         - Target tool: "claude" (default), "opencode", "trae", "cursor", or "copilot"
  install_path - Project-level installation directory (default: current working directory)
  --skills     - 共享 skills 仓来源：本地工作树路径或 Git SHA。
                 缺省时自动取 CANNBot 当前分支同名分支的远端最新提交（无同名分支回退 master），
                 不再固定使用 vendor/cannbot-skills 的 gitlink 提交。

Examples:
  init.sh project
  init.sh project claude
  init.sh project opencode
  init.sh global claude
  init.sh project cursor /path/to/project

Installed content:
  Skills:     triton-task-extractor, triton-op-designer, triton-op-coding, triton-op-verifier, triton-latency-optimizer, triton-simulator-optimizer, npu-arch, triton-precision-debug
  Knowledge:  knowledge-query / ops-knowledge-ingest tool skills + cannbot-knowledge card repo cloned to <project>/.cannbot/dependencies/triton-auto-evolve/cannbot-knowledge
  Control:    triton-agent-loop (Multi-Agent round dispatch and orchestration)
  Template:   Index computation, math compute, normalization, object detection, quantization, tensor transform, transformer inference (copied per project)
  Hooks:      SessionStart/SessionEnd/PreToolUse
  Config:     AGENTS.md (Orchestrator-only round scheduling; per-round Phase 0-8 runs in isolated sub CLIs)
EOF
}

LEVEL="project"
TOOL="claude"
INSTALL_PATH=""
SKILLS_ARG=""

while [ $# -gt 0 ]; do
    case "$1" in
        --help|-h) show_help; exit 0 ;;
        --skills)
            if [ $# -lt 2 ] || [ -z "$2" ] || [[ "$2" == --* ]]; then
                err "--skills requires <path|SHA>"
                exit 1
            fi
            SKILLS_ARG="$2"
            shift 2
            continue
            ;;
        global|project) LEVEL="$1" ;;
        opencode|claude|trae|cursor|copilot) TOOL="$1" ;;
        --*) err "Unexpected argument: $1"; show_help; exit 1 ;;
        *)
            if [ -n "$INSTALL_PATH" ]; then
                err "Unexpected argument: $1"
                show_help
                exit 1
            fi
            INSTALL_PATH="$1"
            ;;
    esac
    shift
done

REPO_ROOT="$(cd "$PLUGIN_ROOT/../.." && pwd)"
SHARED_SKILLS_PATH="vendor/cannbot-skills"
SKILLS_SELECTION=""
SKILLS_REQUESTED=""
SKILLS_COMMIT=""

# 把共享 skills 仓（vendor/cannbot-skills）解析到"最新"，而不是 gitlink 钉住的提交。
#
# 与统一安装器 script/lib/skills-source.js:prepareSharedSkills 对齐：
#   1) 显式 --skills <path>：用该本地工作树（不联网、不改子模块）
#   2) 显式 --skills <SHA>：本地已有该提交则直接用；完整 SHA 允许向 origin 拉取
#   3) 默认取 CANNBot 当前分支同名分支的远端最新提交；远端无同名分支则回退 master
#   4) 分支查询/拉取失败即失败，不静默回退到 gitlink 旧版本
#
# 这解决"子模块停在 gitlink → 装到旧 skills / 旧 knowledge-query"的问题：安装产物
# 始终跟当前分支远端最新一致。
# 切换提交会留下旧提交登记、新提交已不存在的嵌套子模块目录（未跟踪），
# 使 vendor 仓变脏；统一安装器随后会以 "has uncommitted changes" 拒绝安装。
# 因此切换前快照子模块路径，切换后只清理"新提交不再跟踪"的那些。
CANNBOT_STALE_SUBMODULES=()

_cannbot_snapshot_submodules() {
    local shared="$1" line
    CANNBOT_STALE_SUBMODULES=()
    [ -f "$shared/.gitmodules" ] || return 0
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        CANNBOT_STALE_SUBMODULES+=("$line")
    done < <(git -C "$shared" config -f .gitmodules --get-regexp '^submodule\..*\.path$' 2>/dev/null | awk '{print $2}')
}

_cannbot_prune_submodules() {
    local shared="$1" path
    for path in ${CANNBOT_STALE_SUBMODULES+"${CANNBOT_STALE_SUBMODULES[@]}"}; do
        [ -n "$path" ] || continue
        [ -e "$shared/$path" ] || continue
        # 新提交仍跟踪该路径（普通文件/目录或 gitlink）就保留
        if git -C "$shared" ls-tree HEAD -- "$path" 2>/dev/null | grep -q .; then
            continue
        fi
        rm -rf "${shared:?}/${path}"
    done
}

prepare_shared_skills() {
    local shared="$REPO_ROOT/$SHARED_SKILLS_PATH"
    local branch="" commit="" rc=0

    # 1) 显式本地路径：直接采用，不触碰子模块
    if [ -n "$SKILLS_ARG" ] && [ -d "$SKILLS_ARG" ]; then
        if ! git -C "$SKILLS_ARG" rev-parse --show-toplevel >/dev/null 2>&1; then
            err "--skills 路径必须是 Git 工作树根目录: $SKILLS_ARG"
            return 1
        fi
        SKILLS_SELECTION="local-path"
        SKILLS_REQUESTED="$SKILLS_ARG"
        SKILLS_COMMIT="$(git -C "$SKILLS_ARG" rev-parse HEAD 2>/dev/null || true)"
        return 0
    fi
    if [ -n "$SKILLS_ARG" ] && ! [[ "$SKILLS_ARG" =~ ^[0-9a-fA-F]{7,64}$ ]]; then
        err "--skills 只接受已存在的本地仓路径或十六进制 SHA: $SKILLS_ARG"
        return 1
    fi

    # 2) 首次 clone 时子模块目录为空，先初始化一次（之后一律用分支最新覆盖）
    if ! git -C "$shared" rev-parse --show-toplevel >/dev/null 2>&1; then
        if [ -f "$REPO_ROOT/.gitmodules" ] && grep -q "$SHARED_SKILLS_PATH" "$REPO_ROOT/.gitmodules"; then
            info "初始化 $SHARED_SKILLS_PATH 子模块 ..."
            git -C "$REPO_ROOT" submodule update --init --depth 1 "$SHARED_SKILLS_PATH" >/dev/null 2>&1 || true
        fi
    fi
    if ! git -C "$shared" rev-parse --show-toplevel >/dev/null 2>&1; then
        err "找不到共享 skills 仓 $SHARED_SKILLS_PATH；"
        err "请在 cannbot 源码树内执行，或用 --skills <path> 指定本地 skills 仓"
        return 1
    fi

    _cannbot_snapshot_submodules "$shared"

    # 3) 本地有未提交修改时不覆盖（与统一安装器同规则）
    if [ -n "$(git -C "$shared" status --porcelain 2>/dev/null || true)" ]; then
        warn "$SHARED_SKILLS_PATH 存在未提交修改，跳过更新（请先提交/清理，或用 --skills <path>）"
        SKILLS_SELECTION="existing-dirty"
        SKILLS_COMMIT="$(git -C "$shared" rev-parse HEAD 2>/dev/null || true)"
        return 0
    fi

    if [ -n "$SKILLS_ARG" ]; then
        # 4) 显式 SHA
        if ! git -C "$shared" rev-parse --verify "${SKILLS_ARG}^{commit}" >/dev/null 2>&1; then
            if [ ${#SKILLS_ARG} -lt 40 ]; then
                err "短 SHA 必须已存在于本地: $SKILLS_ARG（请提供完整 SHA 以便拉取）"
                return 1
            fi
            git -C "$shared" fetch --depth 1 origin "$SKILLS_ARG" >/dev/null 2>&1 || {
                err "无法从 origin 拉取提交 $SKILLS_ARG"; return 1; }
        fi
        git -C "$shared" submodule deinit -f --all >/dev/null 2>&1 || true
        git -C "$shared" checkout --detach "$SKILLS_ARG" >/dev/null 2>&1 || {
            err "checkout $SKILLS_ARG 失败"; return 1; }
        _cannbot_prune_submodules "$shared"
        SKILLS_SELECTION="sha"
        SKILLS_REQUESTED="$SKILLS_ARG"
    else
        # 5) 分支最新
        branch="$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || true)"
        [ -n "$branch" ] || branch="master"
        if [ "$branch" != "master" ]; then
            rc=0
            git -C "$shared" ls-remote --exit-code --heads origin "refs/heads/$branch" >/dev/null 2>&1 || rc=$?
            if [ "$rc" -eq 2 ]; then
                warn "cannbot-skills 远端没有分支 $branch，回退 master"
                branch="master"
            elif [ "$rc" -ne 0 ]; then
                err "查询 cannbot-skills 分支 $branch 失败；为避免装到旧版本，安装中止"
                err "（离线场景请用 --skills <path> 指定本地 skills 仓）"
                return 1
            fi
        fi
        git -C "$shared" fetch --depth 1 origin "refs/heads/$branch" >/dev/null 2>&1 || {
            err "拉取 cannbot-skills 分支 $branch 失败；安装中止"; return 1; }
        commit="$(git -C "$shared" rev-parse --verify FETCH_HEAD 2>/dev/null || true)"
        [ -n "$commit" ] || { err "无法解析 $branch 的提交"; return 1; }
        git -C "$shared" submodule deinit -f --all >/dev/null 2>&1 || true
        git -C "$shared" checkout --detach "$commit" >/dev/null 2>&1 || {
            err "checkout $commit 失败"; return 1; }
        _cannbot_prune_submodules "$shared"
        SKILLS_SELECTION="latest-branch"
        SKILLS_REQUESTED="$branch"
    fi

    # 6) 共享仓自身的子模块
    git -C "$shared" submodule update --init --recursive --depth 1 >/dev/null 2>&1 || \
        warn "$SHARED_SKILLS_PATH 子模块更新不完整"

    SKILLS_COMMIT="$(git -C "$shared" rev-parse HEAD 2>/dev/null || true)"
    return 0
}

if ! prepare_shared_skills; then
    exit 1
fi
if [ -n "$SKILLS_ARG" ] && [ -d "$SKILLS_ARG" ]; then
    export CANNBOT_SKILLS_ROOT="$SKILLS_ARG"
fi

OPS_SKILL_ROOT="$(find_ops_root || true)"
if [ -z "$OPS_SKILL_ROOT" ] || [ ! -d "$OPS_SKILL_ROOT" ]; then
    err "Cannot find shared ops/ directory. Please run init.sh from the cannbot source tree,"
    err "or pass --skills <path> pointing at a cannbot-skills checkout."
    exit 1
fi
if [ -n "$SKILLS_COMMIT" ]; then
    ok "Shared skills: $OPS_SKILL_ROOT"
    ok "  revision ${SKILLS_COMMIT:0:8} (${SKILLS_SELECTION}${SKILLS_REQUESTED:+:$SKILLS_REQUESTED})"
fi

# Skill 清单单一来源：plugin-sources.json（与统一安装器同源）。
#   ops/ 条目                                → INCLUDED_SKILLS（vendor/cannbot-skills/ops 软链）
#   plugins-community/cannbot-knowledge 条目 → KB_SKILLS（知识库工具 skill，源在 KB_SKILL_ROOT）
# 知识内容（卡片）不在此列：卡片由 install_knowledge_base() 克隆 cannbot-knowledge 仓提供。
SKILLS_REPO_ROOT="$(dirname "$OPS_SKILL_ROOT")"
KB_SKILL_ROOT="$SKILLS_REPO_ROOT/plugins-community/cannbot-knowledge/skills"
INCLUDED_SKILLS=""
KB_SKILLS=""
if [ -f "$PLUGIN_ROOT/plugin-sources.json" ] && command -v python3 >/dev/null 2>&1; then
    parsed="$(python3 - "$PLUGIN_ROOT/plugin-sources.json" <<'PY'
import json, sys
from pathlib import Path

sources = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
ops, kb = [], []
for entry in sources.get("skills", []):
    name = entry.rstrip("/").rsplit("/", 1)[-1]
    if entry.startswith("plugins-community/cannbot-knowledge/skills/"):
        kb.append(name)
    else:
        ops.append(name)
print("|".join([" ".join(ops), " ".join(kb)]))
PY
)" && { INCLUDED_SKILLS="${parsed%%|*}"; KB_SKILLS="${parsed#*|}"; } || { INCLUDED_SKILLS=""; KB_SKILLS=""; }
fi
# Fallback：plugin-sources.json 缺失或解析失败时的静态清单（与 plugin-sources.json 保持一致）。
if [ -z "$INCLUDED_SKILLS" ]; then
    warn "plugin-sources.json missing or unparsable; using built-in skill list"
    INCLUDED_SKILLS="triton-task-extractor triton-op-designer triton-op-coding triton-op-verifier triton-latency-optimizer triton-simulator-optimizer npu-arch triton-precision-debug"
    KB_SKILLS="knowledge-query ops-knowledge-ingest"
fi

if [ "$LEVEL" = "project" ]; then
    if [ -n "$INSTALL_PATH" ]; then
        if [ ! -d "$INSTALL_PATH" ]; then
            err "install_path is not an existing directory: $INSTALL_PATH"
            exit 1
        fi
        INSTALL_BASE="$(cd "$INSTALL_PATH" && pwd)"
    else
        INSTALL_BASE="$PWD"
    fi
else
    INSTALL_BASE="$PWD"
fi

if [ "$LEVEL" = "global" ]; then
    case "$TOOL" in
        opencode) CONFIG_ROOT="$HOME/.config/opencode" ;;
        claude) CONFIG_ROOT="$HOME/.claude" ;;
        trae)
            detect_trae_variant
            case "$TRAE_VARIANT" in
                plugin) CONFIG_ROOT="$HOME/.marscode" ;;
                cli) CONFIG_ROOT="$HOME/.traecli" ;;
                *) CONFIG_ROOT="$HOME/.trae-cn" ;;
            esac
            ;;
        cursor) CONFIG_ROOT="$HOME/.cursor" ;;    # "$TOOL" = "cursor"
        copilot) CONFIG_ROOT="$HOME/.copilot" ;;  # "$TOOL" = "copilot"
    esac
else
    case "$TOOL" in
        opencode) CONFIG_ROOT="$INSTALL_BASE/.opencode" ;;
        claude) CONFIG_ROOT="$INSTALL_BASE/.claude" ;;
        trae)
            detect_trae_variant
            case "$TRAE_VARIANT" in
                plugin) CONFIG_ROOT="$INSTALL_BASE/.marscode" ;;
                cli) CONFIG_ROOT="$INSTALL_BASE/.traecli" ;;
                *) CONFIG_ROOT="$INSTALL_BASE/.trae" ;;
            esac
            ;;
        cursor) CONFIG_ROOT="$INSTALL_BASE/.cursor" ;;    # "$TOOL" = "cursor"
        copilot) CONFIG_ROOT="$INSTALL_BASE/.github" ;;   # "$TOOL" = "copilot"
    esac
fi

CANNBOT_DIR="$CONFIG_ROOT"

if [ "$TOOL" = "claude" ]; then
    CONFIG_FILE_NAME="CLAUDE.md"
else
    CONFIG_FILE_NAME="AGENTS.md"
fi

install_skill_links() {
    local target_root="$1"
    mkdir -p "$target_root"
    local count=0
    local skill src target
    for skill in $INCLUDED_SKILLS; do
        # Plugin-local control skill: linked by install_control_skill_links()
        [ -d "$LOCAL_CTRL_SKILLS_DIR/$skill" ] && continue
        src="$OPS_SKILL_ROOT/$skill"
        target="$target_root/$skill"
        if [ ! -d "$src" ]; then
            warn "Skill not found: $skill"
            continue
        fi
        if [ -e "$target" ] || [ -L "$target" ]; then
            rm -rf "$target"
        fi
        ln -sfn "$(realpath "$src")" "$target"
        count=$((count + 1))
    done
    ok "Skills: $count linked"
}

install_control_skill_links() {
    local target_root="$1"
    mkdir -p "$target_root"
    if [ ! -d "$LOCAL_CTRL_SKILLS_DIR" ]; then
        info "No control skills to install (skills/ not found)"
        return 0
    fi
    local count=0
    local entry name target
    for entry in "$LOCAL_CTRL_SKILLS_DIR"/*; do
        [ -d "$entry" ] || continue
        name="$(basename "$entry")"
        target="$target_root/$name"
        if [ -e "$target" ] || [ -L "$target" ]; then
            rm -rf "$target"
        fi
        ln -sfn "$(realpath "$entry")" "$target"
        count=$((count + 1))
    done
    ok "Control skills: $count linked"
}

install_kb_skill_links() {
    # knowledge-query / ops-knowledge-ingest 只是操作知识库的工具 skill（内部无任何知识卡片），
    # 与算子 skill 一样从 cannbot-skills vendor 树软链。
    local target_root="$1"
    [ -n "$KB_SKILLS" ] || return 0
    if [ ! -d "$KB_SKILL_ROOT" ]; then
        warn "Knowledge tool skills root not found: $KB_SKILL_ROOT"
        return 0
    fi
    mkdir -p "$target_root"
    local count=0 skill src target
    for skill in $KB_SKILLS; do
        src="$KB_SKILL_ROOT/$skill"
        target="$target_root/$skill"
        if [ ! -d "$src" ]; then
            warn "Knowledge tool skill not found: $skill"
            continue
        fi
        if [ -e "$target" ] || [ -L "$target" ]; then
            rm -rf "$target"
        fi
        ln -sfn "$(realpath "$src")" "$target"
        count=$((count + 1))
    done
    ok "Knowledge tool skills: $count linked"
}

install_knowledge_base() {
    # 知识内容（卡片）唯一来源：cannbot-knowledge 仓的 knowledge/ 目录。
    # 克隆到 <项目>/.cannbot/dependencies/<plugin>/<name>，与统一安装器
    # （cannbot.js provisionDependencies）的路径约定一致；仓库地址等均从
    # plugin-install.json 读取，不在脚本里硬编码。
    KB_DEP_ROOT=""
    if [ "${CANNBOT_SKIP_DEPENDENCY_REPOS:-0}" = "1" ]; then
        info "Skipping knowledge base clone (CANNBOT_SKIP_DEPENDENCY_REPOS=1)"
        return 0
    fi
    if [ "$LEVEL" != "project" ]; then
        info "Global install: knowledge base not provisioned (project-level only)"
        return 0
    fi
    local dep_json="$PLUGIN_ROOT/plugin-install.json"
    if [ ! -f "$dep_json" ] || ! command -v python3 >/dev/null 2>&1; then
        warn "plugin-install.json unavailable; skip knowledge base clone"
        return 0
    fi
    local dep_line
    dep_line="$(python3 - "$dep_json" <<'PY'
import json, sys
from pathlib import Path

for d in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")).get("dependencies", []):
    if d.get("name") and d.get("repository"):
        print(f'{d["name"]}\t{d["repository"]}\t{d.get("ref", "")}')
        break
PY
)"
    if [ -z "$dep_line" ]; then
        warn "No valid dependency in plugin-install.json; skip knowledge base clone"
        return 0
    fi
    local name repository ref dep_parent
    name="$(printf '%s' "$dep_line" | cut -f1)"
    repository="$(printf '%s' "$dep_line" | cut -f2)"
    ref="$(printf '%s' "$dep_line" | cut -f3)"
    dep_parent="$INSTALL_BASE/.cannbot/dependencies/$PLUGIN_ID"
    KB_DEP_ROOT="$dep_parent/$name"
    if [ -d "$KB_DEP_ROOT/.git" ]; then
        if git -C "$KB_DEP_ROOT" pull --ff-only >/dev/null 2>&1; then
            ok "Knowledge base updated: $KB_DEP_ROOT"
        else
            warn "Knowledge base update failed; using existing checkout: $KB_DEP_ROOT"
        fi
    elif [ -e "$KB_DEP_ROOT" ]; then
        warn "Knowledge base path exists but is not a Git checkout; clone skipped: $KB_DEP_ROOT"
    else
        mkdir -p "$dep_parent"
        local clone_args=(clone --depth 1)
        [ -n "$ref" ] && clone_args+=(--branch "$ref")
        if git "${clone_args[@]}" "$repository" "$KB_DEP_ROOT" >/dev/null 2>&1; then
            ok "Knowledge base cloned: $KB_DEP_ROOT"
        else
            warn "Knowledge base clone failed (offline?); agent runs in skeleton mode"
            KB_DEP_ROOT=""
        fi
    fi
}

# ---------------------------------------------------------------------------
# 安装后置步骤：知识库索引预热 / 项目级 config.json
# ---------------------------------------------------------------------------

# 知识库装好后立刻把检索索引建出来（首次约 50s，之后复用）。
# 此前安装器只 clone 卡片不建索引，首次检索才懒构建：老版本直接报
# "does not look ready" 不可用；现在安装阶段就把这一步做掉，agent 一上手即可检索。
prime_knowledge_index() {
    if [ "$LEVEL" != "project" ]; then
        return 0
    fi
    if [ "${CANNBOT_SKIP_KNOWLEDGE_INDEX:-0}" = "1" ]; then
        info "Knowledge index skipped (CANNBOT_SKIP_KNOWLEDGE_INDEX=1)"
        return 0
    fi
    local kb_root="${KB_DEP_ROOT:-}/knowledge"
    if [ ! -d "$kb_root" ]; then
        kb_root="$INSTALL_BASE/.cannbot/dependencies/$PLUGIN_ID/cannbot-knowledge/knowledge"
    fi
    if [ ! -d "$kb_root" ]; then
        warn "Knowledge index skipped: knowledge base not found"
        return 0
    fi
    local index="$kb_root/search/okf.index.json"
    if [ -f "$index" ] && [ "${CANNBOT_REBUILD_KNOWLEDGE_INDEX:-0}" != "1" ]; then
        ok "Knowledge index ready: $kb_root/search/okf.index.json"
        return 0
    fi
    local query="$INSTALL_BASE/.claude/skills/knowledge-query/scripts/knowledge_query.py"
    [ -f "$query" ] || query="$SKILLS_REPO_ROOT/plugins-community/cannbot-knowledge/skills/knowledge-query/scripts/knowledge_query.py"
    if [ ! -f "$query" ] || ! command -v python3 >/dev/null 2>&1; then
        warn "Knowledge index skipped: knowledge_query.py unavailable"
        return 0
    fi
    local log_file="${TMPDIR:-/tmp}/cannbot-kb-index.$$"
    local started=$SECONDS
    info "Building knowledge index (first run, ~50s) ..."
    if timeout 1800 python3 "$query" --knowledge-root "$kb_root" build >"$log_file" 2>&1; then
        ok "Knowledge index built in $((SECONDS - started))s"
        rm -f "$log_file"
    else
        warn "Knowledge index build failed; the first query will retry (log: $log_file)"
    fi
    return 0
}

# 生成项目级 config.json：不生成时 orchestrator 用 DEFAULT_CONFIG
# （max_rounds=10，npu_idle.hbm=10 → 共享机上所有卡都判"忙"，第一轮直接失败）。
# 阈值按本机实测占用自适应，装完即可跑。
write_project_config() {
    if [ "$LEVEL" != "project" ]; then
        return 0
    fi
    local cfg="$INSTALL_BASE/config.json"
    if [ -f "$cfg" ]; then
        info "config.json already exists; kept unchanged"
        return 0
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        warn "python3 unavailable; skipped config.json generation"
        return 0
    fi
    python3 - "$cfg" "$PLUGIN_ROOT/config.json" <<'PYCFG'
import json, pathlib, sys

cfg_path = pathlib.Path(sys.argv[1])
plugin_cfg = pathlib.Path(sys.argv[2])
base = {}
try:
    base = json.loads(plugin_cfg.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    pass

out = {
    "target_mfu": 60,
    "target_speedup": 60,
    "max_rounds": 2,
    "initial_worker_timeout": base.get("initial_worker_timeout", 7200),
    "max_worker_timeout": base.get("max_worker_timeout", 28800),
    "npu_device_id": None,
    "npu_idle": {"aicore": 5.0, "aivector": 5.0, "npu_util": 10.0, "hbm": 95.0},
    "algorithms": base.get("algorithms"),
}

cfg_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("  -> config.json: target_mfu=60, max_rounds=2, npu_device_id=null"
      "（安装期不写死卡，运行时按 npu_idle 阈值现场选；需固定时设 TRITON_NPU_DEVICE_ID）")
PYCFG
    [ -f "$cfg" ] && ok "config.json: $cfg"
    return 0
}

install_template_links() {
    local target_root="$1"
    if [ -d "$PLUGIN_ROOT/template" ]; then
        # Avoid copying the template directory onto itself when installing into
        # the plugin root (self-install). Use realpath -s so symlinks are NOT
        # followed; otherwise an old symlink install would be mistaken for a copy.
        local src_real target_real
        src_real="$(realpath -s "$PLUGIN_ROOT/template" 2>/dev/null || echo "")"
        target_real="$(realpath -s "$target_root/template" 2>/dev/null || echo "")"
        if [ -n "$src_real" ] && [ -n "$target_real" ] && [ "$src_real" = "$target_real" ]; then
            tpl_count=$(find "$PLUGIN_ROOT/template" -maxdepth 1 -name '*.md' | wc -l)
            ok "Template: $tpl_count files in place"
            return 0
        fi

        # Old installs used a symlink. Remove it first so cp -R creates an
        # independent copy instead of following the link.
        if [ -L "$target_root/template" ]; then
            rm -f "$target_root/template"
        fi

        # Backup any per-project template already accumulated, rather than
        # silently deleting it with rm -rf.
        if [ -d "$target_root/template" ]; then
            local backup_name="template.backup.$(date +%Y%m%d_%H%M%S)"
            mv "$target_root/template" "$target_root/$backup_name"
            info "Existing template backed up to $target_root/$backup_name"
        fi

        if [ -e "$target_root/template" ] || [ -L "$target_root/template" ]; then
            rm -rf "$target_root/template"
        fi
        cp -R "$PLUGIN_ROOT/template" "$target_root/template"
        tpl_count=$(find "$PLUGIN_ROOT/template" -maxdepth 1 -name '*.md' | wc -l)
        ok "Template: $tpl_count files copied"
    else
        warn "Template dir not found, skip"
    fi
}

install_references_links() {
    local target_root="$1"
    local ref_src="$PLUGIN_ROOT/references"
    if [ -d "$ref_src" ]; then
        # If installing into the plugin root itself, references are already at the
        # target location (realpath resolves the symlink back to the source).
        # Do NOT symlink them onto themselves, which would delete the source directory.
        local src_real target_real
        src_real="$(realpath "$ref_src" 2>/dev/null || echo "")"
        target_real="$(realpath "$target_root/references" 2>/dev/null || echo "")"
        if [ -n "$src_real" ] && [ -n "$target_real" ] && [ "$src_real" = "$target_real" ]; then
            ref_count=$(find "$ref_src" -type f -name '*.md' 2>/dev/null | wc -l)
            ok "References: $ref_count files/dirs in place"
            return 0
        fi
        if [ -e "$target_root/references" ] || [ -L "$target_root/references" ]; then
            rm -rf "$target_root/references"
        fi
        ln -sfn "$ref_src" "$target_root/references"
        ref_count=$(find "$ref_src" -type f -name '*.md' 2>/dev/null | wc -l)
        ok "References: $ref_count files/dirs linked"
    else
        warn "References dir not found, skip"
    fi
}

install_hook_links() {
    local target_root="$1"
    mkdir -p "$target_root"
    local count=0
    local hook_entry name target
    for hook_entry in "$LOCAL_HOOK_ROOT"/*; do
        [ -e "$hook_entry" ] || continue
        name="$(basename "$hook_entry")"
        # Skip Python cache directories and other non-hook entries
        if [ "$name" = "__pycache__" ] || [ "$name" = ".DS_Store" ]; then
            continue
        fi
        target="$target_root/$name"
        if [ -e "$target" ] || [ -L "$target" ]; then
            rm -rf "$target"
        fi
        ln -sfn "$(realpath "$hook_entry")" "$target"
        count=$((count + 1))
    done
    ok "Hooks: $count linked"
}

install_config() {
    mkdir -p "$CONFIG_ROOT"
    local config_src="$PLUGIN_ROOT/AGENTS.md"
    local config_target
    if [ "$LEVEL" = "project" ]; then
        config_target="$INSTALL_BASE/$CONFIG_FILE_NAME"
    else
        config_target="$CONFIG_ROOT/$CONFIG_FILE_NAME"
    fi

    if [ "$LEVEL" = "project" ] && [ "$PLUGIN_ROOT" = "$INSTALL_BASE" ] && [ "$CONFIG_FILE_NAME" = "AGENTS.md" ]; then
        ok "$CONFIG_FILE_NAME already in current directory"
    else
        ln -sf "$config_src" "$config_target"
        ok "$CONFIG_FILE_NAME"
    fi

    local config_root_target="$CONFIG_ROOT/$CONFIG_FILE_NAME"
    if [ "$config_root_target" != "$config_target" ]; then
        ln -sf "$config_src" "$config_root_target"
        ok "$CONFIG_FILE_NAME -> $(basename "$CONFIG_ROOT")/"
    fi
}

activate_hooks_settings() {
    if [ "$TOOL" != "claude" ] && [ "$TOOL" != "cursor" ]; then
        info "Hooks linked but settings activation is only configured for Claude/Cursor"
        return 0
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        warn "python3 not found; hooks linked but settings.json was not generated"
        return 0
    fi

    local settings_target="$CONFIG_ROOT/settings.json"
    local plugin_root_abs
    plugin_root_abs="$(realpath "$PLUGIN_ROOT")"
    python3 - "$LOCAL_HOOK_ROOT/hooks.json" "$settings_target" "$plugin_root_abs" <<'PY'
import json
import sys
from pathlib import Path

hooks_path = Path(sys.argv[1])
settings_path = Path(sys.argv[2])
plugin_root = sys.argv[3]

new_hooks = json.loads(
    hooks_path.read_text(encoding="utf-8").replace("${CLAUDE_PLUGIN_ROOT}", plugin_root)
)

if settings_path.exists():
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(settings, dict):
            settings = {}
    except json.JSONDecodeError:
        settings = {}
else:
    settings = {}

settings_hooks = settings.setdefault("hooks", {})
for event, entries in new_hooks.get("hooks", {}).items():
    dest = settings_hooks.setdefault(event, [])
    existing = {json.dumps(item, sort_keys=True, ensure_ascii=False) for item in dest}
    for entry in entries:
        key = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        if key not in existing:
            dest.append(entry)
            existing.add(key)

settings_path.parent.mkdir(parents=True, exist_ok=True)
settings_path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
    ok "settings.json hooks activated"
}

write_manifest() {
    local manifest="$CONFIG_ROOT/cannbot-manifest.json"
    local skills_json agents_json hooks_json deps_json

    # Combine operator skills + knowledge tool skills with plugin-local control skills
    local combined_skills=""
    for s in $INCLUDED_SKILLS $KB_SKILLS; do combined_skills="$combined_skills $s"; done
    if [ -d "$LOCAL_CTRL_SKILLS_DIR" ]; then
        local name
        for entry in "$LOCAL_CTRL_SKILLS_DIR"/*; do
            [ -d "$entry" ] || continue
            name="$(basename "$entry")"
            case " $combined_skills " in *" $name "*) continue ;; esac
            combined_skills="$combined_skills $name"
        done
    fi
    skills_json=$(printf '%s\n' $combined_skills | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo "[]")

    agents_json="[]"
    hooks_json=$(find "$LOCAL_HOOK_ROOT" -mindepth 1 -maxdepth 1 -exec basename {} \; | sort | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))" 2>/dev/null || echo "[]")
    deps_json="[]"
    if [ -n "$KB_DEP_ROOT" ] && [ -d "$KB_DEP_ROOT" ]; then
        deps_json="[\".cannbot/dependencies/$PLUGIN_ID/$(basename "$KB_DEP_ROOT")\"]"
    fi
    cat > "$manifest" << EOF
{
  "brand": "CANNBot",
  "version": "$VERSION",
  "team": "$PLUGIN_ID",
  "level": "$LEVEL",
  "tool": "$TOOL",
  "installed_skills": $skills_json,
  "installed_agents": $agents_json,
  "installed_hooks": $hooks_json,
  "dependencies": $deps_json,
  "brand_dir": "$CONFIG_ROOT",
  "install_time": "$(date -u +%Y%m%dT%H%M%SZ)"
}
EOF
    ok "Manifest: $manifest"
}

show_banner
echo "  Tool:      $TOOL"
echo "  Level:     $LEVEL"
echo "  Path:      $CONFIG_ROOT"
echo "  Skills:    $OPS_SKILL_ROOT"
echo ""

if [ "$TOOL" = "trae" ]; then
    detect_trae_variant
    info "TRAE variant: $TRAE_VARIANT"
    echo ""
fi

step "[1/6] Installing operator skills..."
mkdir -p "$CANNBOT_DIR"
install_skill_links "$CANNBOT_DIR/skills"
install_kb_skill_links "$CANNBOT_DIR/skills"
echo ""

step "[2/6] Installing control skills, template and references..."
install_control_skill_links "$CANNBOT_DIR/skills"
install_template_links "$CANNBOT_DIR"
install_references_links "$CANNBOT_DIR"
echo ""

step "[3/6] Installing knowledge base (cannbot-knowledge)..."
install_knowledge_base
echo ""

step "[4/6] Installing hooks..."
install_hook_links "$CANNBOT_DIR/hooks"
activate_hooks_settings

# 生成插件自身 .claude/settings.json（从 hooks/hooks.json 模板替换 ${CLAUDE_PLUGIN_ROOT} 为真实路径）
if [ -f "$LOCAL_HOOK_ROOT/hooks.json" ]; then
    plugin_root_abs="$(realpath "$PLUGIN_ROOT")"
    mkdir -p "$PLUGIN_ROOT/.claude"
    sed "s|\${CLAUDE_PLUGIN_ROOT}|${plugin_root_abs}|g" \
        "$LOCAL_HOOK_ROOT/hooks.json" > "$PLUGIN_ROOT/.claude/settings.json"
    ok "Plugin .claude/settings.json generated from hooks.json"
fi

# 保护 hooks/ 目录下的脚本，防止被 Agent 删除或篡改。
# 注意：开发调试期间如需修改这些文件，必须先执行
#   chattr -i -R <path>
# 解除不可变属性，否则编辑/保存会报 EPERM。
if command -v chattr >/dev/null 2>&1; then
    for _hf in "$LOCAL_HOOK_ROOT"/*.py "$LOCAL_HOOK_ROOT"/*.json; do
        [ -f "$_hf" ] && chattr +i "$_hf" 2>/dev/null || true
    done
    for _hrf in "$LOCAL_HOOK_ROOT"/hook_runtime/*.py; do
        [ -f "$_hrf" ] && chattr +i "$_hrf" 2>/dev/null || true
    done
    ok "Hooks: immutable flag set ($(ls -1 "$LOCAL_HOOK_ROOT"/*.py "$LOCAL_HOOK_ROOT"/*.json "$LOCAL_HOOK_ROOT"/hook_runtime/*.py 2>/dev/null | wc -l) files)"
else
    warn "chattr not available, skip setting immutable flag on hooks (less secure)"
fi

# 保护 skills/triton-agent-loop/ 控制技能，防止被 Agent 删除。
# 注意：开发调试期间如需修改这些文件，必须先执行
#   chattr -i -R skills/triton-agent-loop
# 解除不可变属性，否则编辑/保存会报 EPERM。
if command -v chattr >/dev/null 2>&1; then
    if [ -d "$PLUGIN_ROOT/skills/triton-agent-loop" ]; then
        find "$PLUGIN_ROOT/skills/triton-agent-loop" -type f -exec chattr +i {} \; 2>/dev/null || true
        find "$PLUGIN_ROOT/skills/triton-agent-loop" -type d -exec chattr +i {} \; 2>/dev/null || true
        ok "Control skills: immutable flag set"
    fi
else
    warn "chattr not available, skip setting immutable flag on control skills (less secure)"
fi
echo ""

step "[5/6] Installing configuration..."
install_config
echo ""

step "[6/6] Writing manifest..."
write_manifest
echo ""

step "Health check..."
health_ok=true
[ -d "$CANNBOT_DIR/skills" ] || { err "skills/ missing"; health_ok=false; }
[ -d "$CANNBOT_DIR/hooks" ] || { err "hooks/ missing"; health_ok=false; }
[ -d "$CANNBOT_DIR/template" ] || warn "template/ missing (optional, skip)"
if [ "$LEVEL" = "project" ] && [ "${CANNBOT_SKIP_DEPENDENCY_REPOS:-0}" != "1" ]; then
    [ -d "$INSTALL_BASE/.cannbot/dependencies/$PLUGIN_ID/cannbot-knowledge/knowledge" ] \
        || warn "knowledge base missing (.cannbot/dependencies/$PLUGIN_ID/cannbot-knowledge); agent runs in skeleton mode"
fi
[ -f "$CONFIG_ROOT/cannbot-manifest.json" ] || { err "manifest missing"; health_ok=false; }
if [ "$LEVEL" = "project" ]; then
    [ -f "$INSTALL_BASE/$CONFIG_FILE_NAME" ] || { err "$CONFIG_FILE_NAME missing in project directory"; health_ok=false; }
else
    [ -f "$CONFIG_ROOT/$CONFIG_FILE_NAME" ] || { err "$CONFIG_FILE_NAME missing"; health_ok=false; }
fi

if [ "$health_ok" = true ]; then
    ok "All checks passed"
else
    exit 1
fi

echo ""
step "Post-install preparation"
prime_knowledge_index
write_project_config

echo ""
echo -e "  ${GREEN}${BOLD}✓ triton-auto-evolve installed successfully!${NC}"
echo ""
echo -e "  ${BOLD}Quick Start:${NC}"
echo -e "  ${CYAN}1.${NC} 在目标 Triton Ascend NPU 算子项目中启动工具"
echo -e "  ${CYAN}2.${NC} 优化输入：${GREEN}${BOLD}请优化当前目录的 Triton Ascend 算子，从 baseline 开始按多轮迭代优化${NC}"
echo -e "  ${CYAN}3.${NC} 主 agent 负责多轮调度，每轮启动独立子 CLI 执行 Phase 0-8"
echo -e "  ${CYAN}4.${NC} 查看流程文档：${BOLD}cat .claude/references/orchestrator-loop.md${NC} 与 ${BOLD}cat .claude/references/algorithms/index.md${NC}（以及 algorithm 对应的 round.md）"
echo ""
