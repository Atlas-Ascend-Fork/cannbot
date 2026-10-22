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

# Locate the ops-perf-optimize plugin root. The orchestration contract
# travels with the Skill; AGENTS.md is only an agent wrapper.
#
# The entry skill may be reached through several install shapes:
#   - Claude Code plugin install       -> <plugin>/skills/ops-perf-optimize-workflow/
#   - init.sh claude discovery symlink -> ~/.claude/skills/ops-perf-optimize-workflow -> <repo>/.../skills/ops-perf-optimize-workflow
#   - init.sh opencode symlink         -> ~/.config/opencode/cannbot/skills/ops-perf-optimize-workflow -> same
#   - init.sh codex copy               -> <project>/.agents/skills/ops-perf-optimize-workflow (a real copy,
#                                         no symlink trail; init.sh records the plugin root in the
#                                         .cannbot-ops-perf-optimize marker for this case)
#   - unified CLI packaged install     -> <project>/.agents/skills/ops-perf-optimize-workflow (a real copy)
#                                         with the workflow tools copied to
#                                         <project>/.cannbot/plugins/ops-perf-optimize/
# so the plugin root is found by resolving symlinks and walking upward, not by assuming `../..`.
#
# Usage:  bash resolve-plugin-root.sh [start_dir]
# Output: absolute plugin root path on stdout (exit 0), or a diagnostic on stderr (exit 1).

set -uo pipefail

# A directory qualifies as the plugin root only if it carries the plugin
# manifest, canonical Skill entry/contract, and workflow tools.
is_plugin_root() {
    [ -f "$1/.claude-plugin/plugin.json" ] \
        && [ -f "$1/skills/ops-perf-optimize-workflow/SKILL.md" ] \
        && [ -f "$1/skills/ops-perf-optimize-workflow/references/workflow-contract.md" ] \
        && [ -f "$1/scripts/workflow_state.py" ] \
        && [ -f "$1/scripts/prepare_case_sets.py" ] \
        && [ -f "$1/scripts/validate_source_isolation.py" ] \
        && [ -f "$1/skills/ops-perf-acceptance-criteria/SKILL.md" ]
}

# Packaged installs do not ship the source plugin manifest next to the copied
# Skill; the unified CLI copies the workflow tools into the project instead.
# Such a runtime root only needs the tools the contract invokes.
is_runtime_root() {
    [ -f "$1/scripts/workflow_state.py" ] \
        && [ -f "$1/scripts/prepare_case_sets.py" ] \
        && [ -f "$1/scripts/validate_source_isolation.py" ] \
        && [ -f "$1/workflows/task-prompts.md" ]
}

walk_up() {
    local d
    d="$(cd "$1" 2>/dev/null && pwd -P)" || return 1
    while [ "$d" != "/" ] && [ -n "$d" ]; do
        if is_plugin_root "$d"; then
            printf '%s\n' "$d"
            return 0
        fi
        d="$(dirname "$d")"
    done
    return 1
}

# Walk the ancestors of a start directory looking for the unified installer's
# project-local runtime assets (<project>/.cannbot/plugins/<plugin>).
find_runtime_root() {
    local d candidate
    d="$(cd "$1" 2>/dev/null && pwd -P)" || return 1
    while [ "$d" != "/" ] && [ -n "$d" ]; do
        for candidate in "$d/.cannbot/plugins/ops-perf-optimize" "$d/.cannbot/plugins"/*; do
            [ -d "$candidate" ] || continue
            if is_runtime_root "$candidate"; then
                printf '%s\n' "$candidate"
                return 0
            fi
        done
        d="$(dirname "$d")"
    done
    return 1
}

# Candidate start points, most trustworthy first. The script's own resolved location is
# first because it survives every symlink shape above.
self_dir="$(dirname "$(readlink -f "${BASH_SOURCE[0]:-$0}")")"

for start in "${1:-}" "$self_dir" "${CLAUDE_SKILL_DIR:-}" "${CLAUDE_PLUGIN_ROOT:-}" "$PWD"; do
    [ -n "$start" ] || continue
    [ -d "$start" ] || start="$(dirname "$start")"
    [ -d "$start" ] || continue
    if root="$(walk_up "$start")"; then
        printf '%s\n' "$root"
        exit 0
    fi
    # Codex install: the skill directory is a copy, so walking up leaves the plugin.
    # init.sh writes the plugin root into the managed-copy marker at the skill root.
    d="$(cd "$start" 2>/dev/null && pwd -P)" || continue
    while [ "$d" != "/" ] && [ -n "$d" ]; do
        marker="$d/.cannbot-ops-perf-optimize"
        if [ -s "$marker" ]; then
            recorded="$(head -n 1 "$marker")"
            if [ -n "$recorded" ] && is_plugin_root "$recorded"; then
                printf '%s\n' "$recorded"
                exit 0
            fi
        fi
        d="$(dirname "$d")"
    done
    if root="$(find_runtime_root "$start")"; then
        printf '%s\n' "$root"
        exit 0
    fi
done

# Last resort: scan the usual install locations for a matching plugin tree.
for base in "$HOME/.claude/plugins" "$HOME/.claude" "$HOME/.config/opencode" "$HOME/.cannbot"; do
    [ -d "$base" ] || continue
    while IFS= read -r manifest; do
        cand="$(cd "$(dirname "$(dirname "$manifest")")" 2>/dev/null && pwd -P)" || continue
        if is_plugin_root "$cand"; then
            printf '%s\n' "$cand"
            exit 0
        fi
    done < <(find -L "$base" -maxdepth 5 -type f -path '*/.claude-plugin/plugin.json' 2>/dev/null)
done

echo "resolve-plugin-root: cannot locate the ops-perf-optimize plugin root (need the canonical Skill, workflow contract, and workflow tools)." >&2
echo "Ask the user for the plugin directory and pass it as the first argument." >&2
exit 1
