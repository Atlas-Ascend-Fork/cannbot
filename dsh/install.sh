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
#
# 在当前用户环境中安装 DSH 和 CANNBot DSH 插件。
#
# 行为：
#   1. 检查 Node.js，缺少或低于 24.9.0 时自动下载并安装 Node.js 24 LTS；
#   2. 检查 dsh 命令，未安装时通过 npm 全局安装官方 DSH；
#   3. 检查 pnpm，缺少时通过 npm 全局安装；
#   4. 通过 `dsh plugin --profile <profile> add cannbot-dsh@<version>` 安装插件。
#
# 与 packages/install 下的 Node.js 一键安装器不同，本脚本使用当前用户的全局 npm
# 前缀和现有的 DSH_HOME（默认 ~/.dsh），不会创建独立的运行时目录。
#
set -euo pipefail

PLUGIN_NAME='cannbot-dsh'
DEFAULT_PROFILE='web'
DEFAULT_PNPM_VERSION='11.28.5'
DEFAULT_NODE_VERSION='24.22.2'
DEFAULT_NODE_MIRROR='https://npmmirror.com/mirrors/node'

PROFILE="${DSH_PROFILE:-${DEFAULT_PROFILE}}"
DSH_VERSION="${DSH_VERSION:-latest}"
PLUGIN_VERSION="${CANNBOT_DSH_PLUGIN_VERSION:-latest}"
PNPM_VERSION="${PNPM_VERSION:-${DEFAULT_PNPM_VERSION}}"
NODE_VERSION="${NODE_VERSION:-${DEFAULT_NODE_VERSION}}"
NODE_MIRROR="${NODE_MIRROR:-${DEFAULT_NODE_MIRROR}}"
NODE_PREFIX="${NODE_PREFIX:-}"
REGISTRY="${NPM_CONFIG_REGISTRY:-}"

CHECK_ONLY=0
INSTALL_DSH=1
INSTALL_PNPM=1
INSTALL_NODE=1

NODE_PATH_ADDED=0
NODE_TMP=''

log() { printf '[cannbot-dsh] %s\n' "$*"; }
warn() { printf '[cannbot-dsh] 警告：%s\n' "$*" >&2; }
die() {
    printf '[cannbot-dsh] 错误：%s\n' "$*" >&2
    exit 1
}

cleanup() {
    if [[ -n "${NODE_TMP}" ]]; then
        rm -rf "${NODE_TMP}"
    fi
}
trap cleanup EXIT

usage() {
    cat <<'EOF'
用法：bash dsh/install.sh [选项]

在当前用户环境中安装 DSH 和 CANNBot DSH 插件。缺少 Node.js、npm、pnpm 或 dsh
时会自动安装；已安装的 DSH 会直接复用，不会被升级或改动。

选项：
  --profile <name>        安装插件的 DSH profile（默认：web）
  --plugin-version <ver>  cannbot-dsh 版本（默认：latest）
  --dsh-version <ver>     缺少 DSH 时安装的版本（默认：latest）
  --pnpm-version <ver>    缺少 pnpm 时安装的版本（默认：11.28.5）
  --node-version <ver>    缺少 Node.js 时安装的版本（默认：24.22.2）
  --node-mirror <url>     Node.js 下载源（默认：https://npmmirror.com/mirrors/node）
  --node-prefix <path>    Node.js 安装目录（默认：root 为 /usr/local，其他用户为 ~/.local）
  --registry <url>        使用 HTTPS npm 源，同时用于 DSH、pnpm 和插件安装
  --check                 只输出当前 Node.js、DSH、pnpm 和插件状态，不做任何修改
  --no-install-node       缺少 Node.js 时直接报错，不自动安装
  --no-install-dsh        未检测到 dsh 时直接报错，不自动安装
  --no-install-pnpm       未检测到 pnpm 时直接报错，不自动安装
  -h, --help              显示本帮助

环境变量：
  DSH_HOME                DSH 数据目录（默认：~/.dsh）
  DSH_PROFILE             同 --profile
  DSH_VERSION             同 --dsh-version
  CANNBOT_DSH_PLUGIN_VERSION 同 --plugin-version
  PNPM_VERSION            缺少 pnpm 时安装的版本（默认：11.28.5）
  NODE_VERSION            缺少 Node.js 时安装的版本（默认：24.22.2）
  NODE_MIRROR             Node.js 下载源
  NODE_PREFIX             Node.js 安装目录
  NPM_CONFIG_REGISTRY     同 --registry

示例：
  bash dsh/install.sh
  bash dsh/install.sh --check
  bash dsh/install.sh --profile web --registry https://registry.npmmirror.com
  bash dsh/install.sh --plugin-version 1.0.0-alpha.1
EOF
}

while (($# > 0)); do
    case "$1" in
        --profile)
            (($# >= 2)) || die '--profile 缺少参数'
            PROFILE="$2"
            shift 2
            ;;
        --plugin-version)
            (($# >= 2)) || die '--plugin-version 缺少参数'
            PLUGIN_VERSION="$2"
            shift 2
            ;;
        --dsh-version)
            (($# >= 2)) || die '--dsh-version 缺少参数'
            DSH_VERSION="$2"
            shift 2
            ;;
        --pnpm-version)
            (($# >= 2)) || die '--pnpm-version 缺少参数'
            PNPM_VERSION="$2"
            shift 2
            ;;
        --node-version)
            (($# >= 2)) || die '--node-version 缺少参数'
            NODE_VERSION="$2"
            shift 2
            ;;
        --node-mirror)
            (($# >= 2)) || die '--node-mirror 缺少参数'
            NODE_MIRROR="$2"
            shift 2
            ;;
        --node-prefix)
            (($# >= 2)) || die '--node-prefix 缺少参数'
            NODE_PREFIX="$2"
            shift 2
            ;;
        --registry)
            (($# >= 2)) || die '--registry 缺少参数'
            REGISTRY="$2"
            shift 2
            ;;
        --check)
            CHECK_ONLY=1
            shift
            ;;
        --no-install-node)
            INSTALL_NODE=0
            shift
            ;;
        --no-install-dsh)
            INSTALL_DSH=0
            shift
            ;;
        --no-install-pnpm)
            INSTALL_PNPM=0
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            die "未知参数：$1"
            ;;
    esac
done

[[ -n "${PROFILE}" ]] || die '--profile 不能为空'
[[ "${PROFILE}" =~ ^[A-Za-z0-9._-]+$ ]] || die "--profile 含非法字符：${PROFILE}"
[[ -n "${DSH_VERSION}" ]] || die '--dsh-version 不能为空'
[[ -n "${PLUGIN_VERSION}" ]] || die '--plugin-version 不能为空'
[[ -n "${PNPM_VERSION}" ]] || die '--pnpm-version 不能为空'

NODE_VERSION="${NODE_VERSION#v}"
[[ "${NODE_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "--node-version 应为完整版本号，例如 24.22.2"
NODE_MIRROR="${NODE_MIRROR%/}"
[[ "${NODE_MIRROR}" =~ ^https:// ]] || die '--node-mirror 必须是 HTTPS 地址'
if [[ -n "${NODE_PREFIX}" ]]; then
    [[ "${NODE_PREFIX}" = /* ]] || die '--node-prefix 必须是绝对路径'
fi

if [[ -n "${REGISTRY}" ]]; then
    [[ "${REGISTRY}" =~ ^https:// ]] || die '--registry 必须是无凭据的 HTTPS 地址'
    [[ "${REGISTRY}" =~ ^https://[^/]*@ ]] && die '--registry 不能包含用户名或密码'
    [[ "${REGISTRY}" == *\?* || "${REGISTRY}" == *\#* ]] && die '--registry 不能包含查询参数或片段'
    REGISTRY="${REGISTRY%/}"
fi

download_file() {
    local url="$1" dest="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 --connect-timeout 20 --max-time 600 -o "${dest}" "${url}"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "${dest}" "${url}"
    else
        return 127
    fi
}

node_usable() {
    command -v node >/dev/null 2>&1 || return 1
    command -v npm >/dev/null 2>&1 || return 1
    npm --version >/dev/null 2>&1 || return 1
    node -e '
const [major, minor] = process.versions.node.split(".").map(Number)
process.exit(major > 24 || (major === 24 && minor >= 9) ? 0 : 1)
' >/dev/null 2>&1
}

install_node() {
    [[ "$(uname -s)" == 'Linux' ]] \
        || die '自动安装 Node.js 仅支持 Linux/WSL；请手动安装 Node.js >=24.9.0。'
    command -v tar >/dev/null 2>&1 || die '自动安装 Node.js 需要 tar 命令。'
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
        die '自动安装 Node.js 需要 curl 或 wget。'
    fi

    local platform
    case "$(uname -m)" in
        x86_64 | amd64) platform='linux-x64' ;;
        aarch64 | arm64) platform='linux-arm64' ;;
        *) die "不支持的 CPU 架构：$(uname -m)" ;;
    esac

    local prefix="${NODE_PREFIX}"
    if [[ -z "${prefix}" ]]; then
        if ((EUID == 0)); then
            prefix='/usr/local'
        else
            prefix="${HOME}/.local"
        fi
    fi

    local tarball="node-v${NODE_VERSION}-${platform}.tar.gz"
    local base="${NODE_MIRROR}/v${NODE_VERSION}"
    NODE_TMP="$(mktemp -d)" || die '无法创建临时目录。'

    log "下载 Node.js v${NODE_VERSION}（${platform}）：${base}/${tarball}"
    if ! download_file "${base}/${tarball}" "${NODE_TMP}/${tarball}"; then
        die "Node.js 下载失败，请检查网络或使用 --node-mirror 指定可用源。"
    fi

    if command -v sha256sum >/dev/null 2>&1; then
        if download_file "${base}/SHASUMS256.txt" "${NODE_TMP}/SHASUMS256.txt"; then
            local expected actual
            expected="$(awk -v file="${tarball}" '$2 == file { print $1; exit }' "${NODE_TMP}/SHASUMS256.txt")"
            actual="$(sha256sum "${NODE_TMP}/${tarball}" | awk '{ print $1 }')"
            [[ -n "${expected}" ]] || die '无法从 SHASUMS256.txt 读取校验值。'
            [[ "${expected}" == "${actual}" ]] || die 'Node.js 安装包 SHA-256 校验失败。'
            log 'Node.js 安装包 SHA-256 校验通过'
        else
            warn '无法下载 Node.js 校验文件，跳过 SHA-256 校验。'
        fi
    else
        warn '系统缺少 sha256sum，跳过 Node.js 安装包校验。'
    fi

    mkdir -p "${prefix}" || die "无法创建 Node.js 安装目录：${prefix}"
    case ":${PATH}:" in
        *":${prefix}/bin:"*) ;;
        *) NODE_PATH_ADDED=1 ;;
    esac
    tar -xzf "${NODE_TMP}/${tarball}" -C "${prefix}" --strip-components=1 --no-same-owner \
        || die "Node.js 解压失败：${prefix}"

    export PATH="${prefix}/bin:${PATH}"
    export npm_config_prefix="${prefix}"
    hash -r
    node_usable || die "Node.js 已解压到 ${prefix}，但 node/npm 仍不可用，请检查该目录是否在 PATH 中。"
    log "Node.js 安装完成：$(node --version)（${prefix}）"
    if [[ "${NODE_PATH_ADDED}" == '1' ]]; then
        log "提示：${prefix}/bin 已加入本次执行的 PATH；新终端如找不到 node 或 dsh，请把该目录写入 PATH。"
    fi
}

ensure_node() {
    if node_usable; then
        log "Node.js：$(node --version)（npm $(npm --version)）"
        return 0
    fi
    if ((INSTALL_NODE == 0)); then
        die '未找到可用的 Node.js（>=24.9.0）。请手动安装，或去掉 --no-install-node 后重试。'
    fi
    log '未找到可用的 Node.js（>=24.9.0），正在自动安装…'
    install_node
    node_usable || die 'Node.js 安装后仍不可用，请检查 PATH 后重试。'
}

npm_global_install() {
    local spec="$1"
    if [[ -n "${REGISTRY}" ]]; then
        npm install --global --no-fund --no-audit --registry="${REGISTRY}" "${spec}"
    else
        npm install --global --no-fund --no-audit "${spec}"
    fi
}

ensure_pnpm() {
    if command -v pnpm >/dev/null 2>&1 && pnpm --version >/dev/null 2>&1; then
        log "已安装 pnpm：$(pnpm --version 2>/dev/null)"
        return 0
    fi
    if ((INSTALL_PNPM == 0)); then
        die '未找到可用的 pnpm。DSH 安装插件依赖 pnpm，请先安装 pnpm 后重试。'
    fi
    log "未找到 pnpm，正在通过 npm 安装 pnpm@${PNPM_VERSION}…"
    if ! npm_global_install "pnpm@${PNPM_VERSION}"; then
        die 'pnpm 安装失败。请检查 npm 全局目录权限或使用 --registry 指定可用的 npm 源。'
    fi
    hash -r
    command -v pnpm >/dev/null 2>&1 || die 'pnpm 已安装但不在 PATH 中，请把 npm 全局 bin 目录加入 PATH 后重试。'
    log "已安装 pnpm：$(pnpm --version 2>/dev/null)"
}

dsh_version() {
    local output
    output="$(dsh --version 2>/dev/null | head -n 1 | tr -d '\r' || true)"
    printf '%s' "${output}"
}

detected_dsh=''
detect_dsh() {
    detected_dsh=''
    if command -v dsh >/dev/null 2>&1; then
        detected_dsh="$(dsh_version)"
        if [[ -n "${detected_dsh}" ]]; then
            log "已检测到 DSH：${detected_dsh}（$(command -v dsh)）"
        else
            warn '检测到 dsh 命令，但无法读取版本。'
        fi
    fi
}

profile_dep() {
    local dir="$1" name="$2"
    [[ -f "${dir}/package.json" ]] || return 0
    node -e '
const fs = require("node:fs")
const manifest = JSON.parse(fs.readFileSync(process.argv[1], "utf8"))
process.stdout.write(manifest.dependencies?.[process.argv[2]] ?? "")
' "${dir}/package.json" "${name}" 2>/dev/null || true
}

profile_has_bundle() {
    local dir="$1" name="$2"
    [[ -f "${dir}/package.json" ]] || return 1
    node -e '
const fs = require("node:fs")
const manifest = JSON.parse(fs.readFileSync(process.argv[1], "utf8"))
process.exit((manifest.dsh?.profile?.bundles ?? []).includes(process.argv[2]) ? 0 : 1)
' "${dir}/package.json" "${name}" 2>/dev/null
}

if ((CHECK_ONLY == 1)); then
    if node_usable; then
        log "Node.js：$(node --version)（npm $(npm --version)）"
        detect_dsh
        if [[ -z "${detected_dsh}" ]]; then
            log 'DSH：未安装'
        fi
    else
        log 'Node.js：未安装或版本低于 24.9.0'
        log 'DSH：无法检查（需要 Node.js >=24.9.0）'
    fi

    if command -v pnpm >/dev/null 2>&1 && pnpm --version >/dev/null 2>&1; then
        log "pnpm：$(pnpm --version 2>/dev/null)"
    else
        log 'pnpm：未安装'
    fi

    profile_dir="${DSH_HOME:-${HOME}/.dsh}/profiles/${PROFILE}"
    log "profile：${profile_dir}"
    if ! node_usable; then
        log 'cannbot-dsh：无法检查（需要 Node.js >=24.9.0）'
    else
        short_version="$(profile_dep "${profile_dir}" "${PLUGIN_NAME}")"
        full_version="$(profile_dep "${profile_dir}" "@cannbot-plugin/${PLUGIN_NAME}")"
        if [[ -n "${short_version}" && -n "${full_version}" ]]; then
            log "cannbot-dsh：短包 ${short_version} + 完整包 ${full_version}（建议只保留一个）"
        elif [[ -n "${short_version}" ]]; then
            if profile_has_bundle "${profile_dir}" "${PLUGIN_NAME}"; then
                log "cannbot-dsh：${short_version}（短包，已启用）"
            else
                log "cannbot-dsh：${short_version}（短包，未启用）"
            fi
        elif [[ -n "${full_version}" ]]; then
            if profile_has_bundle "${profile_dir}" "@cannbot-plugin/${PLUGIN_NAME}"; then
                log "cannbot-dsh：${full_version}（完整包，已启用）"
            else
                log "cannbot-dsh：${full_version}（完整包，未启用）"
            fi
        elif [[ -f "${profile_dir}/package.json" ]]; then
            log 'cannbot-dsh：未安装'
        else
            log 'cannbot-dsh：未安装（profile 尚未初始化）'
        fi
    fi
    exit 0
fi

ensure_node
detect_dsh

if [[ -z "${detected_dsh}" ]]; then
    if ((INSTALL_DSH == 0)); then
        die '未检测到 dsh 命令。请先安装官方 DSH，或去掉 --no-install-dsh 后重试。'
    fi
    log "未检测到 DSH，正在通过 npm 全局安装 @deepseek-ai/dsh@${DSH_VERSION}…"
    if ! npm_global_install "@deepseek-ai/dsh@${DSH_VERSION}"; then
        die 'DSH 安装失败。请检查 npm 全局目录权限；可执行 npm config get prefix 查看安装位置。'
    fi
    hash -r
    detected_dsh="$(dsh_version)"
    if [[ -z "${detected_dsh}" ]]; then
        prefix="$(npm config get prefix 2>/dev/null || true)"
        die "DSH 已安装但 dsh 命令不可用。请确认 ${prefix}/bin 在 PATH 中，然后重新执行本脚本。"
    fi
    log "DSH 安装完成：${detected_dsh}"
fi

profile_dir="${DSH_HOME:-${HOME}/.dsh}/profiles/${PROFILE}"
short_version="$(profile_dep "${profile_dir}" "${PLUGIN_NAME}")"
full_version="$(profile_dep "${profile_dir}" "@cannbot-plugin/${PLUGIN_NAME}")"
if [[ -n "${full_version}" ]]; then
    if [[ -n "${short_version}" ]]; then
        warn "检测到短包 ${PLUGIN_NAME}@${short_version} 与完整包 @cannbot-plugin/${PLUGIN_NAME}@${full_version} 同时安装，请只保留一个入口。"
        exit 0
    fi
    log "已检测到完整包 @cannbot-plugin/${PLUGIN_NAME}@${full_version}，插件已安装，跳过短包安装。"
    if ! profile_has_bundle "${profile_dir}" "@cannbot-plugin/${PLUGIN_NAME}"; then
        warn '完整包已安装但未出现在 profile 的启用列表中，请在 DSH 插件管理中启用，或移除后重试。'
    fi
    exit 0
fi

ensure_pnpm

log "正在把 ${PLUGIN_NAME}@${PLUGIN_VERSION} 安装到 DSH profile「${PROFILE}」…"
plugin_args=(plugin --profile "${PROFILE}" add "${PLUGIN_NAME}@${PLUGIN_VERSION}" --save-exact)
if [[ -n "${REGISTRY}" ]]; then
    plugin_args+=(--registry="${REGISTRY}")
fi
if ! dsh "${plugin_args[@]}"; then
    cat >&2 <<EOF

[cannbot-dsh] 插件安装失败。请根据上方错误排查，常见原因：
  - 当前 DSH 版本不在插件兼容范围（>=0.1.1-rc.1 <0.3.0），可安装兼容版本：
      npm install --global @deepseek-ai/dsh@<兼容版本>
  - npm 源不可达或版本尚未同步，可加 --registry https://registry.npmmirror.com
  - pnpm 版本不兼容，可升级 pnpm 后重试
EOF
    exit 1
fi

installed_version="$(profile_dep "${profile_dir}" "${PLUGIN_NAME}")"
if [[ -z "${installed_version}" ]]; then
    warn "未在 ${profile_dir}/package.json 中找到 ${PLUGIN_NAME} 依赖，请检查上方安装输出。"
    exit 1
fi
if ! profile_has_bundle "${profile_dir}" "${PLUGIN_NAME}"; then
    warn "插件已下载，但未出现在 profile 的启用列表中。请重新执行本脚本，或运行 dsh plugin --profile ${PROFILE} remove ${PLUGIN_NAME} 后重试。"
    exit 1
fi

log "安装完成：${PLUGIN_NAME} ${installed_version}（profile：${PROFILE}）"
log "启动 DSH：dsh web"
log '首次启动后请在界面中配置模型账号或 API Key。'
