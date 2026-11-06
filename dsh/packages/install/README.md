# CANNBot DSH 一键安装器

需要 **Node.js 24.9.0 或更新版本（含 npm/npx）**，且必须在 Linux 或 WSL 终端执行（Windows PowerShell 会被拒绝）：

```sh
npx @cannbot-plugin/cannbot-dsh-install@latest
```

安装官方 **DSH Web**、最新 CANNBot DSH 和目录中全部默认工作流，核验完整后启动 Web 界面。本工具不安装 Windows Electron 桌面客户端，不修改 DSH 核心，不需要管理员权限，也不改动已有 Desktop 或其他 DSH 安装。

本工具使用经过 CANNBot 验证的官方 `@deepseek-ai/dsh@0.2.1-rc.3` 与 `pnpm@11.28.5`。主插件、目录和默认工作流在每次安装时查询所选 registry 的 `latest`，再使用查询得到的确切版本安装；逐项核对实际版本与资源文件。短包与主包发布尚未同步、版本不兼容、网络失败或文件缺失时会报错，不会把旧版或不完整安装报告为成功。

固定版本的运行时依赖优先复用 npm 缓存，缺失时再下载；这不会影响主插件和工作流的 latest 查询。首次下载官方完整依赖可能需要较长时间，请等待各阶段完成。中途失败后可重新执行，只有 npm 安装完整结束的运行时才会被标记为可复用。

所有阶段使用同一个独立用户目录。安装仅调用标准 npm 和 DSH 官方插件命令；工作流确切版本通过该独立 Web profile 的标准 pnpm overrides 指定，不关闭全局发布时间观察期或其他安全策略。主插件安装时一起下载默认工作流，不需要启用后再后台补装。后续仍可在工作流管理中独立更新、回退；已有工作流缓存与固定回退版本由插件保留。

## Linux 服务器

```sh
npx @cannbot-plugin/cannbot-dsh-install@latest --no-open
```

服务仅监听 `127.0.0.1`，保留终端，按 Ctrl+C 停止。默认端口 3080 已占用时自动选择空闲端口，也可用 `--port 3081` 指定。远程访问请使用自己的 SSH 端口转发，并打开 DSH 打印的完整认证链接（包含 token）；工具不公开服务端口、不关闭认证、不安装系统服务。

## 仅安装 / 再次启动

```sh
npx @cannbot-plugin/cannbot-dsh-install@latest --no-start
npx @cannbot-plugin/cannbot-dsh-install@latest --start-only
```

`--no-start` 完成安装与文件验证后退出；`--start-only` 使用已安装环境，不查询新版本。默认命令再次执行会重新查询插件和工作流版本，复用兼容运行时。运行中的该环境需要先在原终端 Ctrl+C 停止，再进行安装更新。

首次打开后由用户配置模型账号或 API Key。工作目录相关的外部依赖在选择工作流时由原版 CANNBot 安装器初始化，仍需要相应网络、Git 和开发环境。

## 目录与安装源

- Linux / WSL：`${XDG_DATA_HOME:-~/.local/share}/cannbot-dsh`
- 运行时位于 `runtime/`，独立 DSH 数据位于 `home/`。
- `--dir <新目录>` 可选择其他路径，后续启动也须传入同一路径。已有非空、非本安装器所有的目录会被拒绝。
- `--registry https://registry.npmmirror.com/` 可指定 HTTPS npm 镜像；此时 latest 来自该镜像，可能比 npm 官方源滞后。默认源为 `https://registry.npmjs.org/`。

工具不写入系统 PATH。保留了 DSH 原生带认证链接的输出及浏览器启动行为。需要卸载时，在停止服务后移除本工具的独立安装目录即可；其中 `home/` 包含此环境的用户配置与会话，删除前请自行备份。

DSH 为 DeepSeek AI 提供的独立开源项目，本工具只编排其公开安装、配置和启动入口。
