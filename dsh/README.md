# CANNBot 开发工作台

面向昇腾算子开发，提供工作流工作区、交互式初始化和会话管理。[安装指南](INSTALL.md) · [工作台用法](docs/workbench.md) · [算子开发示例](USAGE.md)

| 使用环境 | 创建本机工作流 | SSH 连接 Linux 服务器 | 返回原生工作台 |
| --- | --- | --- | --- |
| Windows、macOS 客户端 | 可创建空白工作区 | 支持 | 支持 |
| Linux 客户端 | 支持 | 支持 | 支持 |
| Linux 服务器版 | 支持 | — | — |

三端安装入口默认安装客户端。客户端连接远端时部署配套的 Linux 服务器版，在当前 DSH 窗口中打开。管理员也可以提前安装服务器版。专用界面仅在安装了服务器版的 DSH profile 中生效。工作流按工作区实际所在的操作系统开放。

## 源码目录

```text
plugin/
  contracts/        工作区、会话、工作流及初始化接口
  frontend/         共享工作台组件、样式及客户端交互
  backend/          工作区、工作流、会话和 SSH 实现
  editions/
    client/         客户端 Host 和 UI 入口
    server/         Linux 服务器版 Host 和 UI 入口
installers/
  common/           发布清单、下载及各平台共用的安装步骤
  windows/          Windows 图形安装器
  linux/            Linux 安装脚本
  macos/            macOS 安装器
legal/              用户协议、隐私政策、开源软件声明
release/            三端安装器从 master 读取的版本清单，插件包通过 npm 分发
tools/              开发、构建、打包与发布工具
packages/           已有 npm 安装入口及短包别名
remote/             客户端随包部署的 SSH 辅助程序
bin/                两版共用的工作流终端初始化入口
tests/              插件、安装与发行测试
```

`src/` 和 `scripts/` 仅保留上层工作流仓正在调用的三个兼容入口。

在本目录执行 `npm run pack:plugin`，会在 `dist/` 生成客户端和服务器版。两者共用一个构建标识，客户端内含同一次构建生成的服务器包。Windows 安装器与插件独立发布。[开发说明](DEVELOPMENT.md) · [发布指南](RELEASE.md) · [许可证](LICENSE) · [第三方声明](THIRD_PARTY_NOTICES.md)
