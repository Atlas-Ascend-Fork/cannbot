# 发行 CANNBot 开发工作台

## 下载入口

在 GitCode 发行版上传 Windows、Linux 和 macOS 安装包，社区主页「整包安装」链接到对应附件。三个安装包共用 `master` 分支的 [发布清单](https://api.gitcode.com/api/v5/repos/cann/cannbot/raw/dsh/release/manifest.json?ref=master)。Windows 缺少 DeepSeek Harness 时从官方地址下载安装。

## 协议与声明

在 `master` 中替换以下 UTF-8 文本，安装器下次打开时会读取新正文。社区下载页也应提供这三个文件及软件来源说明。

| 安装器显示 | 替换文件 |
| --- | --- |
| 用户协议 | [user-agreement.txt](legal/user-agreement.txt) |
| 隐私政策 | [privacy-policy.txt](legal/privacy-policy.txt) |
| 开源软件声明 | [open-source-notices.txt](legal/open-source-notices.txt) |

首次公开下载前填入正式协议和隐私政策。开源软件声明中保留 CANN-2.0 和随包第三方软件的完整许可文本。

## 构建安装器

从本目录运行。Windows EXE 在 Windows 构建，macOS PKG 在 macOS 构建。安装器输出到 `dist/`。

```sh
npm run package:windows
npm run package:linux
npm run package:macos
```

三个交付文件分别是 `CANNBot-Setup.exe`、`CANNBot-Setup.sh` 和 `CANNBot-Setup.pkg`。

## 更新插件

1. 同步更新 `package.json`、`packages/short/package.json`、`packages/short-server/package.json` 的版本，以及两个短包对插件本体的精确版本依赖。
2. 运行 `npm run pack:plugin`、`node tools/package.mjs --short` 和 `node tools/package.mjs --short-server`。在 `dist/` 中取本次生成的四个归档。
3. 用 `npm publish <归档路径> --access public --tag next` 先发布两个 `@cannbot-plugin/` 插件本体，再发布 `cannbot-dsh` 和 `cannbot-dsh-server` 短包。
4. 确认四个固定版本均可下载后，运行 `npm run release:feed`。将生成的 `release/manifest.json` 通过 PR 合入 `master`，现有安装器就会从 npm 下载指定版本。安装验证完成后可单独切换 npm 的 `latest` 标签。

客户端在用户点击更新后安装。下次连接 SSH 时，使用当前客户端自带的 Linux 服务器版。兼容的历史 npm 包入口仍可单独使用。

## 品牌与许可证

CANNBot 使用自有标识。客户端的返回入口使用通用左箭头和“返回原生工作台”。软件来源、版本要求和条款可使用 DSH 名称。保留仓库原有 CANN-2.0 许可证和完整第三方声明。
