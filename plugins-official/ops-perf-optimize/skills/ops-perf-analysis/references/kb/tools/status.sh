#!/usr/bin/env bash
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

# status.sh — one-screen state of the kb tree. Read-only.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
for b in book-910 book-950; do
  n=$(ls "$ROOT/$b/entries/"*.md 2>/dev/null | wc -l)
  printf '%s: %s entries' "$b" "$n"
  if [ "$n" -gt 0 ]; then
    printf ' ('
    grep -h '^STRATUM:' "$ROOT/$b/entries/"*.md 2>/dev/null | awk '{print $2}' | sort | uniq -c \
      | awk '{printf "%s%s:%s", sep, $2, $1; sep=", "}'
    printf ')'
  fi
  printf '\n'
done
printf 'claim-cards: %s' "$(ls "$ROOT/harvest/claims/"*.md 2>/dev/null | wc -l)"
printf ' · contradictions: %s\n' "$(cat "$ROOT"/harvest/CONTRADICTIONS.md "$ROOT"/harvest/contradictions-*.md 2>/dev/null | grep -cE '^#{2,3} +C-')"
printf 'form check: '
"$ROOT/tools/check_entries.sh" >/dev/null 2>&1 && echo PASS || echo 'FAIL (run tools/check_entries.sh)'
printf 'selftest:   '
"$ROOT/tools/check_entries.sh" --selftest >/dev/null 2>&1 && echo PASS || echo 'FAIL — the checker itself is broken; fix before trusting any PASS above'
echo '--- last 5 LOG lines ---'
