# 安装 CANNBot开发工作台

在 CANNBot 下载页的 **整包安装** 中选择对应平台。默认安装客户端版。

| 系统 | 安装 | 启动 |
| --- | --- | --- |
| Windows x64 | 双击 `CANNBot-Setup.exe`，阅读协议并按向导安装 | 从桌面快捷方式或开始菜单打开 |
| Linux x64 / arm64 | 在终端运行 `sh CANNBot-Setup.sh`，阅读协议并输入 `AGREE` | 运行 `~/.local/share/cannbot/bin/cannbot` |
| macOS Intel / Apple 芯片 | 双击 `CANNBot-Setup.pkg`，阅读并确认协议 | 从个人“应用程序”打开 CANNBot |

首次使用按界面提示配置模型账号。客户端可在 **服务器** 中建立 SSH 连接，使用与当前客户端匹配的服务器版。

**单独部署 Linux 服务器版**

```sh
sh CANNBot-Setup.sh --edition server
~/.local/share/cannbot/bin/cannbot-cannbot-server
```

默认安装到 `cannbot-server` profile。指定其他专用 profile 可加 `--profile <名称>`，启动命令以安装器输出为准。
