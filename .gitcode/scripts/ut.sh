#!/usr/bin/env bash
# Run the repository's CPU-only tests in a private user environment.
set -euo pipefail
umask 077

if [[ $# != 1 ]]; then
  echo "Usage: bash .gitcode/scripts/ut.sh REPORT_DIRECTORY" >&2
  exit 2
fi
repository=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
mkdir -p -- "$1"
report=$(cd "$1" && pwd -P)
if [[ -e "$report/summary.md" ]]; then
  echo "UT report already exists: $report" >&2
  exit 3
fi
summary="$report/summary.md"
printf '# CANNBot PR UT\n\n' > "$summary"
printf 'Started: %s\n\n' "$(date -u +%FT%TZ)" >> "$summary"
sandbox=''
active_pid=''

cleanup() {
  local code=$? cleanup_code=0
  trap - EXIT INT TERM
  if [[ -n "$active_pid" ]]; then
    kill -TERM "$active_pid" 2>/dev/null || true
    wait "$active_pid" 2>/dev/null || true
  fi
  if [[ -n "$sandbox" ]]; then
    # Tests may leave a detached server when their process is interrupted.
    # This server uses only the socket directory created by this invocation.
    if command -v tmux >/dev/null && command -v timeout >/dev/null; then
      env -i PATH="$PATH" HOME="$sandbox/home" TMUX_TMPDIR="$sandbox/tmux" \
        timeout --kill-after=2s 5s tmux kill-server > "$report/tmux-cleanup.log" 2>&1 || {
          # A missing private server is the normal result after test cleanup.
          if [[ -S "$sandbox/tmux/tmux-$(id -u)/default" ]]; then cleanup_code=3; fi
        }
    fi
    if (( cleanup_code == 0 )); then
      rm -rf -- "$sandbox" || cleanup_code=3
    fi
  fi
  if (( code == 0 && cleanup_code != 0 )); then code=$cleanup_code; fi
  printf '\nFinished: %s\n\nWrapper exit: %s; cleanup exit: %s\n' \
    "$(date -u +%FT%TZ)" "$code" "$cleanup_code" >> "$summary"
  exit "$code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

fail_setup() {
  printf 'Setup failed: %s. Tests did not start.\n' "$1" | tee -a "$summary" >&2
  exit 3
}
for tool in node npm python3 git bash tmux timeout mktemp id; do
  command -v "$tool" >/dev/null || fail_setup "missing $tool"
done
sandbox=$(mktemp -d /tmp/cannbot-ut.XXXXXXXX)
mkdir -p "$sandbox"/{home,config,data,cache,tmp,tmux,npm-cache}
touch "$sandbox/npm-user.conf" "$sandbox/npm-global.conf"
clean_env=(env -i PATH="$PATH" LANG=C.UTF-8 HOME="$sandbox/home"
  XDG_CONFIG_HOME="$sandbox/config" XDG_DATA_HOME="$sandbox/data" XDG_CACHE_HOME="$sandbox/cache"
  TMPDIR="$sandbox/tmp" TMUX_TMPDIR="$sandbox/tmux" PYTHONDONTWRITEBYTECODE=1
  GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 GIT_TERMINAL_PROMPT=0
  npm_config_userconfig="$sandbox/npm-user.conf" npm_config_globalconfig="$sandbox/npm-global.conf"
  npm_config_cache="$sandbox/npm-cache" npm_config_offline=true npm_config_audit=false npm_config_fund=false)

cd "$repository"
commit=$("${clean_env[@]}" git rev-parse HEAD) || fail_setup 'repository Git metadata unavailable'
vendor=$("${clean_env[@]}" git rev-parse HEAD:vendor/cannbot-skills) || fail_setup 'vendor gitlink unavailable'
[[ -e vendor/cannbot-skills/.git ]] || fail_setup 'vendor is not initialized'
actual_vendor=$("${clean_env[@]}" git -C vendor/cannbot-skills rev-parse HEAD) || fail_setup 'vendor Git metadata unavailable'
printf 'CANNBot: `%s`\n\nRecorded vendor: `%s`\n\nActual vendor: `%s`\n\n' "$commit" "$vendor" "$actual_vendor" >> "$summary"
[[ "$actual_vendor" == "$vendor" ]] || fail_setup 'vendor HEAD differs from the recorded gitlink'
vendor_status=$("${clean_env[@]}" git -C vendor/cannbot-skills status --porcelain --untracked-files=normal --ignore-submodules=none) \
  || fail_setup 'vendor worktree status unavailable'
[[ -z "$vendor_status" ]] || fail_setup 'vendor worktree contains local changes'

"${clean_env[@]}" node --input-type=module -e \
  'if (Number(process.versions.node.split(".")[0]) < 20 || typeof import.meta.dirname !== "string") process.exit(1)' \
  || fail_setup 'Node must satisfy engines.node and support import.meta.dirname'
"${clean_env[@]}" python3 -c 'import sys, yaml; assert sys.version_info >= (3, 10)' \
  || fail_setup 'Python >=3.10 and PyYAML are required'
{
  "${clean_env[@]}" node --version
  "${clean_env[@]}" npm --version
  "${clean_env[@]}" python3 --version
  "${clean_env[@]}" python3 -c 'import yaml; print("PyYAML", yaml.__version__)'
  "${clean_env[@]}" git --version
  "${clean_env[@]}" bash --version
  "${clean_env[@]}" tmux -V
  "${clean_env[@]}" timeout --version
} > "$report/environment.log" 2>&1
printf '| Command | Start (UTC) | End (UTC) | Exit |\n| --- | --- | --- | --- |\n' >> "$summary"

# One budget for both original entry points; no retries or dependency installation.
deadline=$((SECONDS + 600))
overall=0
run_test() {
  local name=$1 directory=$2 started ended code remaining
  shift 2
  remaining=$((deadline - SECONDS))
  started=$(date -u +%FT%TZ)
  if (( remaining <= 0 )); then
    code=124
    printf 'NOT_RUN: UT time budget exhausted.\n' > "$report/$name.stderr.log"
    : > "$report/$name.stdout.log"
  else
    (
      cd "$directory"
      exec "${clean_env[@]}" timeout --kill-after=10s "${remaining}s" "$@"
    ) > "$report/$name.stdout.log" 2> "$report/$name.stderr.log" &
    active_pid=$!
    code=0
    wait "$active_pid" || code=$?
    active_pid=''
  fi
  ended=$(date -u +%FT%TZ)
  printf '| `%s` | %s | %s | %s |\n' "$*" "$started" "$ended" "$code" >> "$summary"
  printf '%s\t%s\t%s\t%s\n' "$name" "$started" "$ended" "$code" >> "$report/results.tsv"
  cat "$report/$name.stdout.log"
  cat "$report/$name.stderr.log" >&2
  printf '%s exit: %s\n' "$name" "$code"
  if (( overall == 0 && code != 0 )); then overall=$code; fi
}
run_test npm "$repository/script" npm test
run_test harness "$repository" python3 -B -m unittest discover -s harness/workflow-orchestrator/tests -v
printf '\nRaw test summaries, including skipped/todo entries, remain in the original logs.\n' >> "$summary"
exit "$overall"
