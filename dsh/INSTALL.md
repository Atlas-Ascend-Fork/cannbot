# 安装 CANNBot 昇腾开发工作台

宿主要求：DeepSeek Harness（DSH）`>=0.1.1-rc.1 <0.3.0`。已验证 Windows `0.2.1-rc.5` / `0.2.2-rc.2`、Linux `0.2.2-rc.1`。

## Windows

- 下载单个文件 **[CANNBot-Setup.cmd](CANNBot-Setup.cmd)**，双击打开图形安装窗口，阅读告知并确认后安装；宿主的官方安装向导由用户完成。
- 无需下载代码仓、安装 Git、单独安装 Node.js 或准备编译环境。首次安装需要联网；已有 DSH 会自动复用。
- 窗口显示下载进度、速度和安装步骤，后台完成首次配置，不弹出宿主登录窗口；完成后点击“打开工作台”，首次启动默认进入 **CANNBot**，预设“代码与开发”和“完整过程”，跳过模式引导。

## Linux / WSL（已发布版）

在仓库根目录执行，安装已发布版并启动 Web 界面：

```sh
bash dsh/install.sh
dsh web
```

已有 DSH，仅安装已发布插件：

```sh
dsh plugin --profile web add cannbot-dsh@1.0.0-alpha.1
dsh web
```

## Windows 桌面端连接 Linux 服务器

进入 **CANNBot → 服务器 → ＋**，填写服务器地址、用户名和端口；高级选项可选私钥和跳板机，也可切换到 SSH 命令 / 已有配置。支持 SSH 密钥和密码登录；需要密码时在工作台内输入，仅用于本次连接，不保存。首次连接请先通过 `ssh <服务器>` 确认服务器指纹。左侧工作区列表可直接打开远端工作区和会话，页面在 DSH 内嵌显示。

创建工作区：点击“工作区”右侧添加图标，依次选择工作流、服务器、父目录，再填写工作区名。Windows 本机只可选空白工作区；Linux 本机和远端 Linux 可选四种类型。初始化问卷在内嵌终端中完成。工作区菜单 → 切换工作流；旧会话保留为只读。

macOS：尚未适配。

当前安装包为开发测试版。公开发布前须配置 `release-policy.json` 中的用户协议与隐私政策链接，使用 `node scripts/package-windows.mjs --public` 构建。
