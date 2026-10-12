#!/usr/bin/env bash

# Source adapter for the hccl-op-generator plugin.

set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${PLUGIN_DIR}/../../script/bin/source-plugin-init.sh" ]]; then
  exec bash "${PLUGIN_DIR}/../../script/bin/source-plugin-init.sh" "${PLUGIN_DIR}" "$@"
fi
exec bash "${PLUGIN_DIR}/../../../bin/source-plugin-init.sh" "${PLUGIN_DIR}" "$@"
