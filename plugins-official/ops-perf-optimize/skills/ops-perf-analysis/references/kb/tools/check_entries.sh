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

# check_entries.sh — form checker for kb book entries (RULES.md Art. 8).
# Usage:
#   ./check_entries.sh                 # check book-910 and book-950
#   ./check_entries.sh <dir> [...]     # check specific book dir(s) containing entries/
#   ./check_entries.sh --selftest      # run against fixtures; FAILS unless every planted
#                                      # defect is FOUND and the good fixture passes (Art. 5)
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAILED=0

check_entry() {  # $1 = entry file, $2 = book tag (910|950|"")
  local f="$1" book="$2" errs=() stratum base id
  base="$(basename "$f" .md)"

  case "$base" in
    *notes*|*misc*|*overview*) errs+=("slug contains banned topic-word (CONVENTIONS)");;
  esac

  for key in ID LABEL LEVEL STRATUM BOARD OVERTURN INDEX; do
    grep -qE "^${key}:" "$f" || errs+=("header key ${key}: missing")
  done

  id="$(grep -m1 -E '^ID:' "$f" | sed 's/^ID: *//; s/ .*//')"
  [ -n "${id:-}" ] && [ "$id" != "$base" ] && errs+=("ID '$id' != filename '$base'")

  grep -qE '^LABEL: *(knowledge|trap|procedure|boundary)\b' "$f" \
    || errs+=("LABEL not in {knowledge,trap,procedure,boundary}")

  stratum="$(grep -m1 -E '^STRATUM:' "$f" | awk '{print $2}')"
  case "${stratum:-}" in
    harvested|corroborated|verified|overturned) : ;;
    *) errs+=("STRATUM '${stratum:-<empty>}' not a known stratum");;
  esac

  grep -m1 -E '^BOARD:' "$f" | grep -qE '910B1|910B2|910B2C|910B4|910_93|910C|950PR|950DT|family-claimed\(unverified\)' \
    || errs+=("BOARD has no accepted token (CONVENTIONS)")
  if [ "$book" = "910" ]; then
    grep -m1 -E '^BOARD:' "$f" | grep -qE '950PR|950DT' && errs+=("950 board token in book-910 (RULES.md Art. 1)")
  elif [ "$book" = "950" ]; then
    grep -m1 -E '^BOARD:' "$f" | grep -qE '910B1|910B2|910B4|910_93|910C' && errs+=("910 board token in book-950 (RULES.md Art. 1)")
  fi

  grep -E '^OVERTURN:' "$f" | grep -qE '[A-Za-z0-9]{8}' || errs+=("OVERTURN empty or vacuous")

  for n in 1 2 3 4 5 6 7; do
    grep -qE "^## ${n} ·" "$f" || errs+=("section ${n} missing")
  done

  # §7 must have content: at least one non-blank line after the heading
  awk '/^## 7 ·/{s=1;next} s&&NF{found=1} END{exit !found}' "$f" \
    || errs+=("section 7 (scope limits) is empty")

  grep -qE '^SOURCE:' "$f" || errs+=("SOURCE: missing (RULES.md Art. 3 — provenance is required at every stratum)")

  # a verified claim must name the board it was measured on, not a placeholder
  if [ "$stratum" = "verified" ]; then
    grep -qE '^BOARD:.*(910B2|910C|950PR|950DT)' "$f" \
      || errs+=("BOARD: names no concrete board at verified stratum (RULES.md Art. 2)")
  fi

  # Art. 1: no entry may lean on the other book, in the header or in the body
  case "$book" in
    book-910) grep -qE '\[950:[0-9]{4}\]' "$f" && errs+=("cites the 950 book (RULES.md Art. 1)") ;;
    book-950) grep -qE '\[910:[0-9]{4}\]' "$f" && errs+=("cites the 910 book (RULES.md Art. 1)") ;;
  esac

  if [ "$stratum" = "harvested" ] || [ "$stratum" = "corroborated" ]; then
    grep -qE '^INDEX: *none' "$f" || errs+=("INDEX must be 'none — nothing measured' at ${stratum} stratum")
    grep -q 'NOT YET RUN' "$f" || errs+=("harvested entry lacks the NOT-YET-RUN line in section 6")
    # newline-tolerant: the property is the voice, not the line layout (2026-08-24, found by 950-arch miner)
    tr '\n' ' ' < "$f" | grep -qiE 'upstream[[:space:]]+asserts' \
      || errs+=("harvested claim (section 1) never says 'upstream asserts'")
  fi

  if [ ${#errs[@]} -gt 0 ]; then
    FAILED=1
    printf 'FAIL %s\n' "$f"
    printf '     - %s\n' "${errs[@]}"
  else
    printf 'ok   %s\n' "$f"
  fi
}

check_tree() {  # $1 = book dir
  local dir="$1" tag=""
  case "$dir" in *book-910*) tag=910;; *book-950*) tag=950;; esac
  local found=0 f
  for f in "$dir"/entries/*.md; do
    [ -e "$f" ] || continue
    found=1
    check_entry "$f" "$tag"
  done
  [ "$found" = 0 ] && printf 'note %s: no entries\n' "$dir"
}

if [ "${1:-}" = "--selftest" ]; then
  # Art. 5: the selftest is a set of PLANTED DEFECTS the checker must FIND, plus one good
  # entry it must pass. If any planted defect goes unflagged, the selftest fails — a checker
  # that can only confirm cleanliness is the blind species this guards against.
  FX="$ROOT/tools/fixtures"
  st_fail=0
  # Art. 5 guard (2026-08-24, audit finding): an ABSENT fixture set must fail the selftest —
  # check_tree on an empty dir leaves FAILED=0, which silently certified nothing.
  ls "$FX/good/book-910/entries/"*.md >/dev/null 2>&1 \
    || { echo "SELFTEST FAIL: good fixtures missing at $FX/good/book-910/entries/"; st_fail=1; }
  out="$(FAILED=0; check_tree "$FX/good/book-910"; exit $FAILED)"; rc=$?
  if [ $rc -ne 0 ]; then st_fail=1; echo "SELFTEST FAIL: good fixture did not pass:"; echo "$out"; fi
  for bad in "$FX"/bad/book-*/entries/*.md; do
    [ -e "$bad" ] || { echo "SELFTEST FAIL: no bad fixtures found"; st_fail=1; break; }
    expect="$(grep -m1 '^<!-- EXPECT: ' "$bad" | sed 's/^<!-- EXPECT: //; s/ -->$//')"
    # sniff the book from the fixture path RELATIVE to the fixtures root — an absolute path
    # may legitimately contain either book name (e.g. when this checker is embedded in a book)
    rel="${bad#$FX/bad/}"
    case "${rel%%/*}" in book-910) tag=910;; book-950) tag=950;; *) tag="";; esac
    out="$(FAILED=0; check_entry "$bad" "$tag"; exit $FAILED)"; rc=$?
    if [ $rc -eq 0 ]; then
      echo "SELFTEST FAIL: planted defect NOT FOUND in $bad (expected: $expect)"; st_fail=1
    elif [ -n "$expect" ] && ! printf '%s' "$out" | grep -qF "$expect"; then
      echo "SELFTEST FAIL: $bad flagged, but not for the planted reason '$expect':"; echo "$out"; st_fail=1
    fi
  done
  if [ $st_fail = 0 ]; then echo "SELFTEST ok — every planted defect was found, good fixture passed"; fi
  exit $st_fail
fi

if [ $# -gt 0 ]; then
  for d in "$@"; do check_tree "$d"; done
elif [ -d "$ROOT/book-910/entries" ] || [ -d "$ROOT/book-950/entries" ]; then
  check_tree "$ROOT/book-910"
  check_tree "$ROOT/book-950"
else
  check_tree "$ROOT"   # embedded copy shipped inside a single book: check that book itself
fi
exit $FAILED
