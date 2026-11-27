# 源码结构与开发

当前两版插件和短包版本为 **1.0.0-alpha.5**，一键安装器为 **1.0.0**。

目录布局见 [README.md](README.md)。

## 模式界面边界

DeepSeek 模式使用 DSH 原生侧栏工作区列表、工作区下拉、主页及会话界面，不通过插件列表或过滤后的控制器替换这些入口。原生列表允许显示全部会话，包括 CANNBot 会话；搜索、添加工作区和 Mod+K / Mod+O 等原生快捷键继续由 DSH 处理，不再适用早期独立 DeepSeek 列表的快捷键限制。

CANNBot 模式单独显示自己的工作区和服务器树，只展示 Host 明确登记的 CANNBot 工作区及会话。DSH 原生 `WorkspaceBrowser` 始终保持挂载，插件不覆盖 `sidebar.workspaces` 的原生占位组件。CANNBot 树通过 `shell.overlay` 的 portal 显示在公开槽位锚点旁的独立容器中；切换到 CANNBot 时临时隐藏原生锚点并设置 `inert`，返回时还原。模式切换仅改变可见性，不通过卸载、重挂原生列表重放其搜索请求，也不重置用户的搜索和展开状态。

Mod+K / Mod+O 继续使用 DSH 原有动作，插件不为 CANNBot 重定向或阻断这些快捷键。显示方式不会清除 CANNBot 归属记录，也不会把普通会话自动加入 CANNBot。CANNBot 主题覆盖在离开该模式时释放；行选中态使用 DSH 的背景高亮，文字保持普通颜色，相关样式只作用于插件元素。

## 主插件开发与构建

在 `dsh/` 目录使用 Node.js **24.9.0 或更高版本**：

```sh
node tools/build-current.mjs
node tools/package.mjs
node tools/package.mjs --short
```

插件发行打包工具调用 `build-current.mjs`，先核对本仓源码和编译结果。输入指纹包含 `plugin/`（含 CSS）、`remote/`、语言资源、构建脚本和配置、包声明，以及 Host 导入的安装辅助文件；输出指纹覆盖整个 `lib/`。只有两者与 `lib/.cannbot-build.json` 一致才复用产物。修改源码、删除或损坏 bundle、缺少构建凭据都会触发重建，不能直接安装旧 `lib`。

构建预设固定使用官方 **DSH 0.2.1-rc.3**，准确 tag 为 `dsh-v0.2.1-rc.3`；它是构建依赖，运行兼容范围仍见 `package.json`。查找顺序为 `DSH_SOURCE`、本地 `.dsh-source.json`、相邻的 `deepseek-harness/`。没有可用目录时，从官方 GitHub codeload 下载该固定 tag 到 `.build-cache/`，检查根包名和版本，再准备隔离构建工具。ZIP 中的 POSIX 测试符号链接不参与构建，不要求 Windows 创建符号链接的权限。

最小工具仅包含 `tsdown`、`lightningcss`、TypeScript、Zod、React、React DOM、`clsx` 、YAML 和 xterm.js；版本声明来自官方固定源码及本插件。pnpm 版本来自官方根 `packageManager`，缺少时下载到 `.build-cache/`，验证 npm 提供的 SHA-512 后使用。工具安装禁用生命周期脚本，缓存和依赖均留在本仓，不安装 DSH 全部运行依赖，不修改系统 Node.js 或全局 npm/pnpm。第一次自动准备需要网络以及解压 pnpm 包所用的 `tar`（Windows 自带 `tar.exe`）。

已有官方源码和构建依赖时，可以继续显式配置：

```sh
node tools/prepare-dev.mjs /path/to/deepseek-harness --build-only
node tools/build-current.mjs
```

`prepare-dev.mjs` 只建立本地依赖链接并写入忽略的 `.dsh-source.json`；Windows 使用目录 junction。省略 `--build-only` 时保留完整开发模式，要求源码目录已有测试相关依赖。也可通过 `DSH_SOURCE` 指向官方目录；显式指定错误版本会报错，不会悄悄切换来源。

```sh
node tools/build-current.mjs --check  # 只读：0 表示一致，1 表示需要构建
node tools/build-current.mjs --force  # 强制重新编译
```

重建期间保留旧 `lib`，编译失败会恢复旧文件并返回失败，一键安装随即停止。源码在编译期间被修改也会报错，保存编辑后重试即可。构建凭据只有版本和内容哈希，没有时间或本机绝对路径。预构建源码 ZIP 应保留完整 `lib/`（含 `.cannbot-build.json`）；拷贝到新路径后仍可核验并离线复用。普通 npm 安装包不带这些构建脚本，安装时不执行源码构建。

主包打包会先执行上述源码检查/构建，再使用与远程部署相同的确定性 tar 生成器；短包打包不需要 DSH 源码或编译工具。产物位于 `dist/`，重复打包相同输入得到相同哈希。打包只读取 `package.json` 的发布白名单，许可证取仓库根 `LICENSE`，不复制本地缓存、凭据或开发依赖。

运行检查：

```sh
node --test tests/build-current.test.mjs tests/package-current.test.mjs
node node_modules/typescript/bin/tsc --noEmit
node node_modules/vitest/vitest.mjs run
```

构建/打包测试使用临时假目录和注入的下载器，不连接网络，也不操作用户 DSH。完整类型检查及 Host/UI 测试仍需官方 SDK 的编译声明和运行依赖；自动准备的最小构建环境不承诺提供完整 SDK 测试环境。

正式 `vitest.config.mts` 包含全部 `tests/**/*.spec.ts` / `.spec.tsx`，无需 `_scratch` 配置。先用上述完整开发模式配置官方 DSH `0.2.1-rc.3` 源码和测试依赖；也可设置 `DSH_SOURCE`。StateDot、Toast、菜单、弹窗和布局测试读取该源码的真实组件与 CSS，slot 授权测试使用已安装的官方 SDK。仓库不复制 DSH 原生 UI 模块，测试不读取本机 DSH 安装或用户 profile。

## 官方资源及 Host 集成测试

官方资源直接来自指定 CANNBot 工作区及其 `vendor/cannbot-skills`。每次构建都在系统临时目录重新装配，完成后清理；不读取或维护 `assets/` 快照。实际提交和内容散列写入生成包的 `workflow.json`，许可证保留在包的 `resources/` 中。
准备满足声明依赖的源码目录后，生成测试使用的工作流包：

```sh
node tools/build-workflow-packages.mjs --source /absolute/path/to/cannbot --version 1.0.0 --catalog-version 1.0.0
node --import tsx --test tests/host.test.mjs tests/workflow-context.test.mjs
```

Host 集成测试读取生成的 `dist/workflow-releases/release-1.0.0-report.json`，不能仅运行测试命令而省略构建夹具。
工作流独立发布步骤见 [WORKFLOW_PUBLISHING.md](WORKFLOW_PUBLISHING.md)。

也可以验证当前主插件与**已发布工作流包**的兼容性，省去从 master 重新装配全部资源：

```powershell
node tools/prepare-host-fixture.mjs --installed-package C:\path\to\installed\cannbot-dsh
$env:CANNBOT_TEST_HOST_PACKAGE = '上一步输出的 host 路径'
node --test tests/host.test.mjs
```

准备脚本只读已安装包，从其真实依赖目录复制 catalog 和工作流至 `_scratch/acceptance-host-published/`，再放入当前本仓 `lib` 并连接现有 SDK。测试状态与初始化输出均使用仓内临时目录，不修改用户 profile；测试执行不从 npm 补包。该模式明确输出已发布包来源，只验证主插件行为，不能替代 master 工作流资源重新打包的验收。上游 Python 调度器使用 POSIX `fcntl`，相关集成测试在 Windows 标注平台前置，应在 Linux 执行；Node Host、包初始化、目录规则及进程超时测试仍照常执行。

## 短包与一键安装器

短包无编译步骤。同步修改 `packages/short/package.json` 和 `packages/short-server/package.json` 的版本及完整包精确依赖，在 `dsh/` 目录打包：

```sh
node tools/package.mjs --short
node tools/package.mjs --short-server
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
初始化前备份相关 Skills、agents、工作流资源和配置；失败时尝试恢复，进程中断时下次先恢复。持久性权限错误仍会报告，并保留恢复所需备份。


## 安装器与发布

三端安装器构建与插件发布清单见 [发布指南](RELEASE.md)。

## 从本仓库安装（实时读取源码）

该入口面向当前用户的 DSH Web profile，默认是 `web`。在仓库根目录执行（Node.js >=24.9，先按 DEVELOPMENT.md 配置构建与工作流资源依赖）：

```sh
npm --prefix dsh run install:source
```

每次安装直接读取当前仓库的 `plugins-official/`、`harness/` 和 `vendor/cannbot-skills/`，包含未提交的内容修改。`dsh/` 不保存这些目录的资源副本。工作流在系统临时目录装配、校验后复制到 `$DSH_HOME/cannbot-dsh-workflows`（默认 `~/.dsh/cannbot-dsh-workflows`），临时文件随后清理。

更新源码后重新执行此命令即可，不需要手工同步资源或发布工作流 npm 包。内容散列决定是否刷新缓存及工作区初始化；同版本内容修改也会生效。明确执行源码安装会替换对应工作流的旧缓存及回退固定状态，全部资源校验成功后一次切换；缺少依赖则报错并保留原工作流。

也可以指定其他本地源码，或在安装时获取远端仓库当前 HEAD 及其声明的子模块：

```sh
node dsh/tools/install-source.mjs --source /path/to/cannbot
node dsh/tools/install-source.mjs --repository https://gitcode.com/cann/cannbot.git
```

本地安装要求共享 Skills 已满足源码声明；不会切换用户工作区的子模块版本。安装后重启 DSH。Windows Desktop profile 由桌面应用管理，请使用下方 Windows 入口，不要将本命令直接改为 `--profile desktop`。直接安装主插件 `.tgz` 或 npm 包使用已发布工作流依赖，不会读取本地源码。
