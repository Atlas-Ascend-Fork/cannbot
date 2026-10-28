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
# report.sh - Output layer for the repository gates
# =============================================================================
# The gates under tests/unit/ come from cann/cannbot-skills, where they source
# tests/lib/test-helpers.sh — a 64 KB library whose remaining functions drive a
# CLI-based behaviour suite that this repository does not run. This file
# provides the part those gates use, with the same names and the same output,
# so a gate moves across without an edit beyond its `source` line.
#
# Contract: 11 functions, 4 tracking variables, 3 path variables, 7 colour
# variables. The gates run under `set -euo pipefail`; a missing name aborts
# them, so every name below is defined unconditionally.
# =============================================================================

# Paths. SKILLS_DIR is the repository root and keeps its name from the source
# repository, where the root is the Skill tree itself.
LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="$(cd "$LIB_DIR/.." && pwd)"
SKILLS_DIR="$(cd "$LIB_DIR/../.." && pwd)"

# Test tracking. declare -g so the counters stay global even when this file is
# sourced from inside a function, where a plain assignment would make them local.
declare -g TEST_PASSED=0
declare -g TEST_FAILED=0
declare -g TEST_SKIPPED=0
declare -g TEST_START_TIME=0

# ANSI colour codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

enable_colors() {
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
}

disable_colors() {
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    CYAN=''
    BOLD=''
    NC=''
}

# NO_COLOR wins over FORCE_COLOR; without either, colour follows the terminal.
setup_colors() {
    if [ -n "${NO_COLOR:-}" ]; then
        disable_colors
    elif [ -n "${FORCE_COLOR:-}" ]; then
        enable_colors
    elif [ -t 1 ]; then
        enable_colors
    else
        disable_colors
    fi
}

print_pass() {
    echo -e "  ${GREEN}[PASS]${NC} $*"
}

print_fail() {
    echo -e "  ${RED}[FAIL]${NC} $*"
}

print_info() {
    echo -e "  ${BLUE}[INFO]${NC} $*"
}

print_warn() {
    echo -e "  ${YELLOW}[WARN]${NC} $*"
}

print_error() {
    echo -e "  ${RED}[ERROR]${NC} $*"
}

print_section_header() {
    local name="$1"
    echo ""
    echo -e "${BOLD}${CYAN}=== $name ===${NC}"
    echo ""
}

print_status_passed() {
    echo -e "${GREEN}${BOLD}STATUS: PASSED${NC}"
}

print_status_failed() {
    echo -e "${RED}${BOLD}STATUS: FAILED${NC}"
}

# Usage: print_test_banner "Test Name" ["description"]
print_test_banner() {
    local name="$1"
    local description="${2:-}"

    echo ""
    echo "========================================"
    echo " $name"
    echo "========================================"
    [ -n "$description" ] && echo "" && echo "$description"
    echo ""
}

# Usage: init_test_tracking
init_test_tracking() {
    TEST_PASSED=0
    TEST_FAILED=0
    TEST_SKIPPED=0
    TEST_START_TIME=$(date +%s)
}

# Usage: print_test_summary
# Returns 1 when anything failed, so a gate can end with it.
print_test_summary() {
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - TEST_START_TIME))

    echo ""
    echo "========================================"
    echo -e " ${BOLD}Test Results Summary${NC}"
    echo "========================================"
    echo ""
    echo -e "  ${GREEN}Passed:${NC}  $TEST_PASSED"
    echo -e "  ${RED}Failed:${NC}  $TEST_FAILED"
    echo -e "  ${YELLOW}Skipped:${NC} $TEST_SKIPPED"
    echo "  Duration: ${duration}s"
    echo ""

    if [ "$TEST_FAILED" -gt 0 ]; then
        print_status_failed
        return 1
    else
        print_status_passed
        return 0
    fi
}

setup_colors
