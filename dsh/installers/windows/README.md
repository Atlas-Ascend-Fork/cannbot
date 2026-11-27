# Windows 安装器

在 `dsh/` 运行 `node tools/package-windows.mjs`，输出 `dist/CANNBot-Setup.exe`。安装时从 GitCode 的 `master` 分支读取当前版本和三份协议与声明。

| 文件 | 用途 |
| --- | --- |
| `setup.nsi`、`setup-worker.ps1` | 品牌、协议选择框、目录、进度、日志和桌面快捷方式 |
| `release.ps1` | 选用 DSH 自带的 Node 或从官网取得 Node，读取三端共用的发布清单 |
| `install-all.ps1` | 检测 DSH、下载并运行官方安装程序、准备 Desktop profile |
| `provision.ps1`、`ensure-workbench.mjs` | 从所选版本的客户端安装包安装，保留已有 profile 和历史配置 |

插件发行清单、下载源和协议文件配置见 [发布说明](../../RELEASE.md)。双击使用见 [安装指南](../../INSTALL.md)。
