# 独立工作流包的构建与发布

主程序：`cannbot-dsh` / `@cannbot-plugin/cannbot-dsh`。
工作流目录：`@cannbot-plugin/workflow-catalog`。
内容包：`@cannbot-plugin/workflow-<工作流 ID>`，各包独立版本。

## 更新已有工作流

先在 CANNBot 源码仓修改内容，准备该源码仓声明的共享 Skills。构建器每次直接读取指定工作区（包含未提交修改），在系统临时目录装配，不维护 `dsh/assets` 副本。正式发布前应提交源码以便追溯。只构建目标工作流：

```sh
node scripts/build-workflow-packages.mjs --source /path/to/cannbot --id ops-direct-invoke --version 1.0.1
npm publish dist/workflow-releases/cannbot-plugin-workflow-ops-direct-invoke-1.0.1.tgz --access public
```

使用 npm 公共仓库和 `latest` 标签。无需改主程序版本，也无需更新目录包。用户可检查并更新这一项，或更新全部未固定的工作流。发布者先在隔离工作区运行包中的初始化器验证后再发布。

## 新增工作流

工作流目录、清单与 Skill 需符合现有 CANNBot 结构。先构建并发布新内容包；确认可公开下载后，再构建、发布一个新版本的目录包，使用户能够发现它：

```sh
node scripts/build-workflow-packages.mjs --source /path/to/cannbot --id new-workflow --version 1.0.0 --catalog true --catalog-version 1.0.1
```

该命令会分别产生新工作流包和目录包。按“内容包先公开、目录包再公开”的顺序发布。主程序无需更新。

## 包格式 v1

根 `package.json` 声明 `cannbotWorkflow: { "schemaVersion": 1, "id": "..." }`，不声明 npm 安装脚本或额外 npm 依赖。
`workflow.json` 记录版本、原始源码提交、资源路径、Skill 内容散列与初始化入口；`resources/` 包含物化后的 Skills、agents、模板、脚本和许可证。
构建器沿用上游 npm 装配方式，将源码专用的 `plugin-sources.json` 转换为包内资源清单。

带统一安装器的包保留上游 `script/bin/cannbot.js` 和 `script/lib` 代码，Host 显式调用：

```sh
node <工作流包>/upstream/bin/cannbot.js install <ID> --tool dsh --target <工作目录> --plugin-dir <工作流包>/resources
```

这里使用上游安装器支持的包模式；不需要额外克隆 CANNBot 主仓或共享 Skills 仓。
初始化声明的外部依赖仍按上游 `plugin-install.json` 准备，因此某些工作流首次初始化仍需要 Git、网络及其运行环境。
没有统一安装器清单的 `ops-registry-invoke` 保持 Skill 原生自检行为，不伪造 `init.sh`。

## 用户侧的版本与回退

工作流安装在 `$DSH_HOME/cannbot-dsh-workflows`，与 npm 主程序目录分离。
下载由 npm 官方 `pacote` 库处理并校验 registry 提供的 SHA-512 完整性；不运行 npm 生命周期脚本。
新包通过校验后才原子切换该工作流，旧版本目录保留。回退后固定版本，自动同步及“更新全部”不会将它升回去；主动更新这一项即可恢复跟随最新版。
工作区初始化按“工作区、工作流包版本及完整性”记录，更新无关工作流不会重复初始化当前工作流。

仅当主程序界面、加载机制或包格式协议发生不兼容变化时，才需发布新的 DSH 主程序。

## 首次安装依赖

目录包的 `dependencies` 声明全部默认工作流，版本使用 `>=1.0.0`，让新用户在 DSH 标准 npm 安装阶段一次获取当时可解析的最新稳定包，并排除历史占位版本。主插件依赖目录包 `^1.0.4`。发布目录包前必须确保所有工作流已公开；新增默认工作流同时加入目录及其 `dependencies`。已有工作流发布新版本仍不必重发目录包或主插件。

启用时仅从 npm 已安装的依赖准备本地缓存，等待全部完成后才注册工作流能力，不运行 npm 安装脚本，不覆盖缓存内独立升级或固定回退的版本。新版本下载由用户在工作流管理中明确触发。项目级外部依赖依然在选择工作流时按需初始化，不能在未选择项目时提前运行。

## 发布主程序

```sh
npm publish dist/cannbot-plugin-cannbot-dsh-1.0.0-alpha.1.tgz
npm publish dist/cannbot-dsh-1.0.0-alpha.1.tgz
```

发布顺序为完整包、短包、一键安装器：短包精确依赖完整包，完整包未公开时短包安装必然失败。

## 无需发布的源码安装

在 `dsh/` 执行 `npm run install:source`，安装器会实时复制父仓库源码到 DSH 工作流缓存。它使用与发布相同的装配、许可证保留和校验逻辑，但跳过工作流 npm 打包与发布。重新安装以内容散列刷新缓存，无需修改版本号。`--repository <GitURL>` 会在本次安装中获取远端源码。
