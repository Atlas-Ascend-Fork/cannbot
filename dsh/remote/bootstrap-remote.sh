#!/usr/bin/env bash
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

# CANNBot DSH remote bootstrap — idempotent, non-root, everything under $HOME.
#
# Invoked over SSH (stdin) by @cannbot-plugin/cannbot-remote:
#   ssh <alias> 'bash -s -- <remotePort> <dshVersion> <pluginVersion> <registry> <profile> <dryRun>'
# or with CANNBOT_DRY=1 in the environment for a read-only plan.
#
# Empty <dshVersion>/<pluginVersion> mean "reuse whatever is installed".
#
# Phase A is strictly read-only (detection + plan). Phase B mutates the machine.
# Markers on stdout:
#   CANNBOT_STEP=<n>/<total> <text>   CANNBOT_DRYRUN=1   CANNBOT_OK=1
#   CANNBOT_REMOTE_PORT=  CANNBOT_WEB_LOG=  CANNBOT_TOKEN=  CANNBOT_REUSE=
#   CANNBOT_DSH_VERSION=  CANNBOT_PLUGIN_VERSION=  CANNBOT_ASCEND_ENV=
#   CANNBOT_ERROR=<message>
set -uo pipefail

PORT_ARG="${1:-${CANNBOT_PORT:-}}"
DSH_VER="${2:-${CANNBOT_DSH_VERSION:-}}"
PLUGIN_VER="${3:-${CANNBOT_PLUGIN_VERSION:-}}"
REGISTRY="${4:-${CANNBOT_REGISTRY:-}}"
PROFILE="${5:-${CANNBOT_PROFILE:-web}}"
DRY="${6:-${CANNBOT_DRY:-0}}"
MODE="${7:-}"
NODE_VER="${CANNBOT_NODE_VERSION:-24.22.2}"
TOTAL=7

log() { printf '[cannbot] %s\n' "$*"; }
warn() { printf '[cannbot][warn] %s\n' "$*" >&2; }
die() { printf 'CANNBOT_ERROR=%s\n' "$*"; printf '[cannbot][error] %s\n' "$*" >&2; exit 1; }
step() { printf 'CANNBOT_STEP=%s %s\n' "$1" "$2"; }

export PATH="$HOME/.local/bin:$PATH"
STATE_DIR="$HOME/.dsh/cannbot-remote"
PROFILE_PKG="$HOME/.dsh/profiles/$PROFILE/package.json"
PLUGIN_PKG="$HOME/.dsh/profiles/$PROFILE/node_modules/cannbot-dsh/package.json"

node_compare() { # $1 = version string -> exit 0 when >= 24.9
  local v="$1" major minor
  major="${v%%.*}"
  minor="$(printf '%s' "$v" | cut -d. -f2)"
  [ "${major:-0}" -gt 24 ] || { [ "${major:-0}" -eq 24 ] && [ "${minor:-0}" -ge 9 ]; }
}

dsh_native_ok() { # node-pty must actually load (npm may have skipped its install script)
  local dsh_binary global_root
  dsh_binary="$(command -v dsh 2>/dev/null || true)"
  global_root="$(npm root -g 2>/dev/null || true)"
  # Resolve from the actual DSH executable first (including npm/pnpm symlinks),
  # then the active npm prefix. A flat ~/.local/node_modules probe misses the
  # normal nested DSH dependency and wrongly reinstalls a healthy installation.
  node - "$dsh_binary" "$global_root" 2>/dev/null <<'NODE_NATIVE_CHECK'
const { realpathSync } = require('node:fs');
const { createRequire } = require('node:module');
const { join } = require('node:path');
const [executable, globalRoot] = process.argv.slice(2);
const candidates = [];
for (const path of [executable, globalRoot && join(globalRoot, '@deepseek-ai', 'dsh', 'package.json')]) {
  if (!path) continue;
  try { candidates.push(realpathSync(path)); } catch {}
}
for (const entry of candidates) {
  try {
    const pty = createRequire(entry)('node-pty');
    if (pty && typeof pty.spawn === 'function') process.exit(0);
  } catch {}
}
process.exit(1);
NODE_NATIVE_CHECK
}

port_free() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$port$" && return 1
    return 0
  fi
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1; then
    exec 3>&- 2>/dev/null || true
    return 1
  fi
  return 0
}

# True when something answers HTTP on the port (401 counts: that is our login page).
port_serving() {
  local port="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$port/" >/dev/null 2>&1 && return 0
  fi
  (exec 3<>"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1 || return 1
  exec 3>&- 2>/dev/null || true
  return 0
}

# ==========================================================================
# Phase A — read-only detection
# ==========================================================================
step 1/$TOTAL "detect node"
NODE_CURRENT=""
NODE_OK=0
if command -v node >/dev/null 2>&1; then
  NODE_CURRENT="$(node -p 'process.versions.node' 2>/dev/null || echo 0)"
  if node_compare "$NODE_CURRENT"; then NODE_OK=1; fi
fi
if [ "$NODE_OK" = "1" ]; then log "node v${NODE_CURRENT} (ok)"; else log "node ${NODE_CURRENT:-missing} (< 24.9, will install v${NODE_VER})"; fi

step 2/$TOTAL "detect dsh / pnpm"
DSH_CURRENT=""
command -v dsh >/dev/null 2>&1 && DSH_CURRENT="$(dsh --version 2>/dev/null || echo unknown)"
PNPM_CURRENT=""
command -v pnpm >/dev/null 2>&1 && PNPM_CURRENT="$(pnpm --version 2>/dev/null || echo unknown)"
log "dsh: ${DSH_CURRENT:-missing}   pnpm: ${PNPM_CURRENT:-missing}"

step 3/$TOTAL "detect cannbot-dsh"
PLUGIN_CURRENT=""
if [ -f "$PLUGIN_PKG" ]; then
  PLUGIN_CURRENT="$(node -p "require('$PLUGIN_PKG').version" 2>/dev/null || echo unknown)"
fi
log "cannbot-dsh: ${PLUGIN_CURRENT:-missing}"

step 4/$TOTAL "preflight"
command -v curl >/dev/null 2>&1 || warn "curl missing (needed if node has to be installed)"
command -v python3 >/dev/null 2>&1 || warn "python3 missing (some CANNBot workflows need Python 3 + PyYAML)"
python3 -c 'import yaml' >/dev/null 2>&1 || warn "PyYAML missing: pip3 install pyyaml"
command -v git >/dev/null 2>&1 || warn "git missing (some workflow deps need git)"

ASCEND_ENV=""
if [ -d /usr/local/Ascend ]; then
  for candidate in \
    /usr/local/Ascend/ascend-toolkit/set_env.sh \
    /usr/local/Ascend/ascend-toolkit/latest/set_env.sh \
    /usr/local/Ascend/set_env.sh; do
    if [ -f "$candidate" ]; then ASCEND_ENV="$candidate"; break; fi
  done
  if [ -z "$ASCEND_ENV" ]; then
    warn "Ascend driver present but no CANN toolkit set_env.sh; AscendC/ACLNN workflows need the toolkit"
  fi
else
  warn "/usr/local/Ascend missing (no NPU driver)"
fi
if ! command -v npu-smi >/dev/null 2>&1; then
  warn "npu-smi not on PATH"
elif ! npu-smi info >/dev/null 2>&1; then
  warn "npu-smi failed; try: export LD_LIBRARY_PATH=/usr/local/Ascend/driver/lib64:\$LD_LIBRARY_PATH"
fi
printf 'CANNBOT_ASCEND_ENV=%s\n' "$ASCEND_ENV"

# Decide what phase B would do.
PLAN_DSH="reuse ${DSH_CURRENT}"
if [ -z "$DSH_CURRENT" ]; then
  PLAN_DSH="install ${DSH_VER:-latest}"
elif [ -n "$DSH_VER" ] && [ "$DSH_CURRENT" != "$DSH_VER" ]; then
  PLAN_DSH="reinstall ${DSH_VER} (have ${DSH_CURRENT})"
fi
PLAN_PLUGIN="reuse ${PLUGIN_CURRENT}"
if [ -z "$PLUGIN_CURRENT" ]; then
  PLAN_PLUGIN="install ${PLUGIN_VER:-latest}"
elif [ -n "$PLUGIN_VER" ] && [ "$PLUGIN_CURRENT" != "$PLUGIN_VER" ]; then
  PLAN_PLUGIN="reinstall ${PLUGIN_VER} (have ${PLUGIN_CURRENT})"
fi
printf 'CANNBOT_PLAN_DSH=%s\n' "$PLAN_DSH"
printf 'CANNBOT_PLAN_PLUGIN=%s\n' "$PLAN_PLUGIN"
printf 'CANNBOT_PLAN_NODE=%s\n' "$( [ "$NODE_OK" = "1" ] && echo "reuse v${NODE_CURRENT}" || echo "install v${NODE_VER}" )"

if [ "$DRY" = "1" ]; then
  printf 'CANNBOT_DRYRUN=1\n'
  printf 'CANNBOT_OK=1\n'
  log "dry run complete; nothing was changed"
  exit 0
fi

mkdir -p "$STATE_DIR" >/dev/null 2>&1 || true

# ==========================================================================
# Phase B — mutations
# ==========================================================================

# ---------------------------------------------------------------- install node
step 5/$TOTAL "prepare node"
if [ "$NODE_OK" != "1" ]; then
  command -v curl >/dev/null 2>&1 || die "curl not found; cannot install Node.js automatically"
  case "$(uname -m)" in
    x86_64|amd64) ARCH=x64 ;;
    aarch64|arm64) ARCH=arm64 ;;
    *) die "unsupported arch: $(uname -m)" ;;
  esac
  log "installing Node.js v${NODE_VER} (${ARCH}) into \$HOME/.local"
  curl -fsSL --retry 3 "https://npmmirror.com/mirrors/node/v${NODE_VER}/node-v${NODE_VER}-linux-${ARCH}.tar.xz" -o /tmp/cannbot-node.tar.xz \
    || die "Node.js download failed"
  mkdir -p "$HOME/.local" || die "cannot create ~/.local"
  tar -xJf /tmp/cannbot-node.tar.xz -C /tmp || die "Node.js extract failed"
  cp -a "/tmp/node-v${NODE_VER}-linux-${ARCH}/." "$HOME/.local/" || die "Node.js copy failed"
  rm -rf "/tmp/node-v${NODE_VER}-linux-${ARCH}" /tmp/cannbot-node.tar.xz
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v node >/dev/null 2>&1 || die "node still not on PATH"
log "node $(node -v)"

# ------------------------------------------------------------ npm prefix + dsh
step 6/$TOTAL "prepare dsh / pnpm"
REGISTRY_EFF="${REGISTRY:-https://registry.npmmirror.com}"
NPM_PREFIX="$(npm config get prefix 2>/dev/null || true)"
case "$NPM_PREFIX" in
  ""|/usr|/usr/local)
    log "npm prefix '$NPM_PREFIX' is not user-writable; switching to \$HOME/.local"
    npm config set prefix "$HOME/.local" >/dev/null 2>&1 || warn "npm config set prefix failed"
    ;;
esac

# npm >=11 blocks dependency install scripts unless allow-listed. DSH needs
# node-pty/koffi/@deepseek-ai/dsh-subprocess-local postinstalls, so retry with the
# exact list npm reports instead of silently producing a half-working install.
npm_install_global() {
  local spec="$1" output status names
  output="$(npm install -g --registry="$REGISTRY_EFF" "$spec" 2>&1)"
  status=$?
  printf '%s\n' "$output" | sed 's/^/  /' | tail -n 12
  if printf '%s\n' "$output" | grep -q 'install scripts not yet covered'; then
    names="$(printf '%s\n' "$output" \
      | sed -n 's/^npm warn install-scripts   \(.*\)@[0-9][^ ]* (.*$/\1/p' \
      | sort -u | paste -sd, -)"
    if [ -n "$names" ]; then
      warn "npm blocked install scripts; retrying with --allow-scripts=${names}"
      output="$(npm install -g --registry="$REGISTRY_EFF" --allow-scripts="$names" "$spec" 2>&1)"
      status=$?
      printf '%s\n' "$output" | sed 's/^/  /' | tail -n 12
    fi
  fi
  return $status
}

if [ -z "$DSH_CURRENT" ] || { [ -n "$DSH_VER" ] && [ "$DSH_CURRENT" != "$DSH_VER" ]; }; then
  target="${DSH_VER:-latest}"
  log "installing @deepseek-ai/dsh@${target}"
  npm_install_global "@deepseek-ai/dsh@${target}" || die "dsh install failed"
elif ! dsh_native_ok; then
  # Installed earlier while npm blocked dependency install scripts (node-pty etc.):
  # reinstall the same version with the allow-list so the terminal backend works.
  warn "dsh ${DSH_CURRENT} is present but node-pty is not usable; repairing"
  npm_install_global "@deepseek-ai/dsh@${DSH_CURRENT}" || warn "dsh repair failed; terminal features may not work"
else
  log "reusing dsh ${DSH_CURRENT}"
fi
command -v dsh >/dev/null 2>&1 || die "dsh not on PATH after install"
if [ -z "$PNPM_CURRENT" ]; then
  log "installing pnpm"
  npm_install_global "pnpm" || warn "pnpm install failed (dsh plugin commands may still work)"
fi

if [ "$MODE" = 'prepare-only' ]; then
  printf 'CANNBOT_DSH_VERSION=%s\n' "$(dsh --version 2>/dev/null | tr -d '\r')"
  printf 'CANNBOT_ASCEND_ENV=%s\n' "$ASCEND_ENV"
  printf 'CANNBOT_OK=1\n'
  exit 0
fi

# ------------------------------------------------------------------- plugin
step 7/$TOTAL "prepare cannbot-dsh + dsh web"
if [ -n "$PLUGIN_VER" ] && [ "$PLUGIN_CURRENT" != "$PLUGIN_VER" ]; then
  log "dsh plugin --profile ${PROFILE} add cannbot-dsh@${PLUGIN_VER}"
  dsh plugin --profile "$PROFILE" add "cannbot-dsh@${PLUGIN_VER}" ${REGISTRY:+--registry "$REGISTRY"} \
    || die "plugin install failed (network / registry / DSH version range >=0.1.1-rc.1 <0.3.0)"
elif [ -n "$PLUGIN_CURRENT" ]; then
  log "reusing cannbot-dsh ${PLUGIN_CURRENT}"
else
  log "installing cannbot-dsh (latest)"
  dsh plugin --profile "$PROFILE" add "cannbot-dsh" ${REGISTRY:+--registry "$REGISTRY"} \
    || die "plugin install failed (network / registry / DSH version range >=0.1.1-rc.1 <0.3.0)"
fi

# Make sure the plugin is enabled in the profile's bundle list.
if [ -f "$PROFILE_PKG" ]; then
  node -e '
const fs = require("fs");
const [file, bundle] = process.argv.slice(1);
const json = JSON.parse(fs.readFileSync(file, "utf8"));
json.dsh = json.dsh || {};
json.dsh.profile = json.dsh.profile || {};
json.dsh.profile.bundles = json.dsh.profile.bundles || [];
if (!json.dsh.profile.bundles.includes(bundle)) {
  json.dsh.profile.bundles.push(bundle);
  fs.writeFileSync(file, JSON.stringify(json, null, 2) + "\n");
  console.log("enabled bundle: " + bundle);
} else {
  console.log("bundle already enabled: " + bundle);
}
' "$PROFILE_PKG" "cannbot-dsh" || warn "could not verify the enabled bundle list"
else
  warn "profile package.json not found at $PROFILE_PKG"
fi

# ------------------------------------------------------------------ dsh web
# Port choice: an already-serving instance ALWAYS wins (a second dsh web on the
# same machine is slow to start and pointless); otherwise reuse the remembered
# port if free, otherwise take the first free port.
PORT=""
if [ -n "$PORT_ARG" ]; then
  PORT="$PORT_ARG"
elif [ -f "$STATE_DIR/port" ]; then
  remembered="$(cat "$STATE_DIR/port" 2>/dev/null | tr -dc '0-9')"
  if [ -n "$remembered" ] && port_serving "$remembered"; then PORT="$remembered"; fi
fi
if [ -z "$PORT" ]; then
  for candidate in $(seq 17633 17700); do
    if port_serving "$candidate"; then PORT="$candidate"; log "found a running dsh web on port ${candidate}"; break; fi
  done
fi
if [ -z "$PORT" ]; then
  for candidate in $(seq 17633 17700); do
    if port_free "$candidate"; then PORT="$candidate"; break; fi
  done
fi
[ -n "$PORT" ] || die "no free port in 17633..17700"
printf '%s' "$PORT" > "$STATE_DIR/port" 2>/dev/null || true
WEB_LOG="$HOME/.dsh/web-${PORT}.log"

TOKEN=""
REUSE=0
if port_serving "$PORT"; then
  REUSE=1
  log "an instance already serves port ${PORT}; reusing it"
  # The token of a running instance only lives in its startup log.
  for candidate in "$WEB_LOG" "$HOME"/.dsh/web-*.log; do
    [ -f "$candidate" ] || continue
    found="$(grep -oE 'token=[A-Za-z0-9._-]+' "$candidate" 2>/dev/null | tail -1 | cut -d= -f2 || true)"
    if [ -n "$found" ]; then TOKEN="$found"; break; fi
  done
  [ -n "$TOKEN" ] || warn "login token not found in the existing instance logs"
else
  mkdir -p "$HOME/.dsh"
  log "starting dsh web on 127.0.0.1:${PORT} (log: $WEB_LOG)"
  # </dev/null is essential: a daemon that inherits our stdin keeps the SSH
  # channel (and therefore this script, and the host plugin's ssh call) open.
  if command -v setsid >/dev/null 2>&1; then
    cd "$HOME" && setsid nohup dsh web --host 127.0.0.1 --port "$PORT" </dev/null >"$WEB_LOG" 2>&1 &
  else
    cd "$HOME" && nohup dsh web --host 127.0.0.1 --port "$PORT" </dev/null >"$WEB_LOG" 2>&1 &
  fi
  for _ in $(seq 1 90); do
    TOKEN="$(grep -oE 'token=[A-Za-z0-9._-]+' "$WEB_LOG" 2>/dev/null | tail -1 | cut -d= -f2 || true)"
    [ -n "$TOKEN" ] && break
    sleep 1
  done
  [ -n "$TOKEN" ] || warn "login token not found yet in $WEB_LOG"
fi
printf '%s' "$TOKEN" > "$STATE_DIR/token-${PORT}" 2>/dev/null || true

printf 'CANNBOT_REMOTE_PORT=%s\n' "$PORT"
printf 'CANNBOT_WEB_LOG=%s\n' "$WEB_LOG"
printf 'CANNBOT_TOKEN=%s\n' "$TOKEN"
printf 'CANNBOT_REUSE=%s\n' "$REUSE"
printf 'CANNBOT_DSH_VERSION=%s\n' "$(dsh --version 2>/dev/null | tr -d '\r' || echo unknown)"
printf 'CANNBOT_PLUGIN_VERSION=%s\n' "$(node -p "require('$PLUGIN_PKG').version" 2>/dev/null || echo unknown)"
printf 'CANNBOT_ASCEND_ENV=%s\n' "$ASCEND_ENV"
printf 'CANNBOT_OK=1\n'
log "ready: http://127.0.0.1:${PORT}/"
