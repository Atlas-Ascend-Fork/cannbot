# 源码结构与开发

当前主插件和短包版本为 **1.0.0-alpha.1**；一键安装器为 **1.0.0**。

## 目录

| 路径 | 内容 |
| --- | --- |
| `src/` | 插件 Host、工作台、品牌界面、工作流管理与更新 |
| `runtime/` | 初始化兼容层 |
| `scripts/` | 构建、打包、工作流子包构建工具 |
| `tests/` | 主插件的前后端测试 |
| `packages/short/` | `cannbot-dsh` 短包入口，精确依赖完整包 |
| `packages/install/` | `@cannbot-plugin/cannbot-dsh-install` 一键安装器源码及测试 |

这里不包含 DSH 核心源码。插件使用官方扩展接口，构建时复用官方源码仓的客户端构建预设。
不提交 `node_modules`、构建产物、个人工作区、凭据、运行日志及临时测试环境。

## 主插件开发与构建

准备已经按官方说明安装好依赖的 **DSH 0.2.1-rc.3** 源码目录。该版本是开发构建依赖，不代表用户安装插件时必须使用这个版本；用户兼容范围见 `package.json`。

在 `dsh/` 目录执行，替换示例中的官方源码路径：

```sh
node scripts/prepare-dev.mjs /path/to/deepseek-harness
node scripts/build.mjs
node scripts/package.mjs
```

`prepare-dev.mjs` 仅建立本地开发依赖链接，并写入被 Git 忽略的 `.dsh-source.json`。
也可以通过环境变量 `DSH_SOURCE` 指定源码目录。
打包结果位于 `dist/`，npm 安装包不包含开发依赖和工作流资源。

运行检查：

```sh
node /path/to/deepseek-harness/node_modules/typescript/bin/tsc --noEmit
node /path/to/deepseek-harness/node_modules/vitest/vitest.mjs run
```

## 官方资源及 Host 集成测试

官方资源直接来自指定 CANNBot 工作区及其 `vendor/cannbot-skills`。每次构建都在系统临时目录重新装配，完成后清理；不读取或维护 `assets/` 快照。实际提交和内容散列写入生成包的 `workflow.json`，许可证保留在包的 `resources/` 中。
准备满足声明依赖的源码目录后，生成测试使用的工作流包：

```sh
node scripts/build-workflow-packages.mjs --source /absolute/path/to/cannbot --version 1.0.0 --catalog-version 1.0.0
node --import tsx --test tests/host.test.mjs tests/workflow-context.test.mjs
```

Host 集成测试读取生成的 `dist/workflow-releases/release-1.0.0-report.json`，不能仅运行测试命令而省略构建夹具。
工作流独立发布步骤见 [WORKFLOW_PUBLISHING.md](WORKFLOW_PUBLISHING.md)。

## 短包与一键安装器

短包无编译步骤。发布完整包的新正式版后，同步修改 `packages/short/package.json` 的版本和完整包精确依赖，再打包：

```sh
npm pack ./packages/short --ignore-scripts
```

一键安装器的 `lib/` 是手写源码，必须纳入版本控制。在其目录执行：

```sh
cd packages/install
npm ci
npm test
npm pack --ignore-scripts
```

安装器每次安装时查询主插件和工作流的最新版本，因此主插件发布新版本不要求安装器同步升版。

## 初始化兼容

Windows 上，目录删除后立即复制可能因目录尚未释放而产生 `EIO`。兼容层只在官方初始化器的子进程中对受管目录执行有限重试，不修改 DSH 核心或上游安装器源码。
初始化前备份相关 Skills、agents、插件资源和配置；失败时尝试恢复，进程中断时下次先恢复。持久性权限错误仍会报告，并保留恢复所需备份。

## 本地安装

运行 `npm run install:source` 会从父目录当前源码装配 `workflow-defaults.json` 声明的工作流（当前为 3 个）、构建并安装主插件，然后原子切换工作流缓存。未列入 `workflow-defaults.json` 的工作流不参与打包，也不会出现在目录包中。使用 `--source` 指定其他本地仓库，`--repository` 在临时目录获取远端 HEAD。缓存刷新包含同版本内容修改；所有工作流校验完成前不会切换旧缓存。详见 README 的源码安装说明。
