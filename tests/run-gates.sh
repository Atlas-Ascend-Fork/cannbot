#!/usr/bin/env bash
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------
# =============================================================================
# run-gates.sh - Run the repository gates
# =============================================================================
# Usage:
#   bash tests/run-gates.sh [gate ...]
#
# With no argument every registered gate runs. An argument selects one gate by
# the name it is registered under.
#
# Exit codes:
#   0  every gate that ran passed and every prerequisite was met
#   1  a gate failed
#   2  every gate that ran passed, but a prerequisite was missing and the gates
#      needing it were skipped
#
# A gate whose prerequisite is missing is skipped rather than run: without the
# vendored Skill repository the dependency graph gate would report every
# submodule-provided skill as absent, which says nothing about the change under
# test and buries anything that does.
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/report.sh"

REPO_ROOT="$SKILLS_DIR"
SKILLS_SUBMODULE="vendor/cannbot-skills"

# 判定范围与 CI 中的激活范围一致：只有这些路径下的发现判红，其余照常打印
# 但记为告警。marketplace.json 计入，因为 cake 自身的登记就写在那里；
# 代价是该文件中与 cake 无关的错误也会判红。
export DG_ERROR_SCOPE="plugins-community/collaborative-agent-kernel-evolution/:tests/:.claude-plugin/marketplace.json"

# Registered gates, in run order: <name>:<path relative to tests/>
GATES=(
    "dependency-graph:unit/test-dependency-graph.sh"
)

# Gates that cannot run without the vendored Skill repository checked out.
GATES_NEEDING_SKILLS_SUBMODULE=(
    "dependency-graph"
)

# Gates that cannot run without python3 and PyYAML.
GATES_NEEDING_PYYAML=(
    "dependency-graph"
)

contains() {
    local needle="$1"
    shift
    local item
    for item in "$@"; do
        [ "$item" = "$needle" ] && return 0
    done
    return 1
}

skills_submodule_present() {
    [ -e "$REPO_ROOT/$SKILLS_SUBMODULE/.git" ]
}

pyyaml_present() {
    python3 -c "import yaml" >/dev/null 2>&1
}

missing_prerequisite() {
    local name="$1"
    if contains "$name" "${GATES_NEEDING_SKILLS_SUBMODULE[@]}" && ! skills_submodule_present; then
        echo "$SKILLS_SUBMODULE is not checked out; run: git submodule update --init --recursive --depth 1"
        return 0
    fi
    if contains "$name" "${GATES_NEEDING_PYYAML[@]}" && ! pyyaml_present; then
        echo "python3 cannot import yaml; run: pip install PyYAML"
        return 0
    fi
    return 1
}

selected=("$@")
prerequisite_missing=0

print_test_banner "CANNBot Repository Gates" "Repository root: $REPO_ROOT"
init_test_tracking

for entry in "${GATES[@]}"; do
    name="${entry%%:*}"
    path="${entry#*:}"

    if [ "${#selected[@]}" -gt 0 ] && ! contains "$name" "${selected[@]}"; then
        continue
    fi

    reason="$(missing_prerequisite "$name")"
    if [ -n "$reason" ]; then
        print_section_header "$name"
        print_warn "skipped: $reason"
        TEST_SKIPPED=$((TEST_SKIPPED + 1))
        prerequisite_missing=1
        continue
    fi

    print_section_header "$name"
    if bash "$SCRIPT_DIR/$path"; then
        TEST_PASSED=$((TEST_PASSED + 1))
        print_pass "$name"
    else
        TEST_FAILED=$((TEST_FAILED + 1))
        print_fail "$name"
    fi
done

if [ "${#selected[@]}" -gt 0 ]; then
    for name in "${selected[@]}"; do
        registered=0
        for entry in "${GATES[@]}"; do
            [ "${entry%%:*}" = "$name" ] && registered=1
        done
        if [ "$registered" -eq 0 ]; then
            print_error "no such gate: $name"
            TEST_FAILED=$((TEST_FAILED + 1))
        fi
    done
fi

# print_test_summary reports only the gates that ran, so the verdict below it is
# what the caller should read.
summary_rc=0
print_test_summary || summary_rc=1

if [ "$summary_rc" -ne 0 ]; then
    print_error "run-gates: a gate failed"
    exit 1
fi

if [ "$prerequisite_missing" -ne 0 ]; then
    print_error "run-gates: a prerequisite was missing; the gates needing it did not run"
    exit 2
fi

print_pass "run-gates: every registered gate passed"
exit 0
