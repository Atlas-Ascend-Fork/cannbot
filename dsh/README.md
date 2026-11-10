# CANNBot DSH

CANNBot DSH 是安装在原版 DeepSeek Harness（DSH）中的独立插件，支持 Windows 桌面端与 Linux Web 端，不修改 DSH 核心。

当前源码版本为 **1.0.0-alpha.1**。本仓库包含主插件、`packages/short` 短包和 `packages/install` 一键安装器的完整源码；目录结构、构建与检查步骤见 [DEVELOPMENT.md](DEVELOPMENT.md)。

## CANNBot 工作台

本插件提供 CANNBot 定制工作台，包含三个工作流入口（算子开发、Ascend C Flash 核函数开发、ACLNN / GEIR 注册算子开发）、工作区继承与路径展示、文件输入及原生对话衔接。也可在 DSH 的“插件 → 添加插件 → 本地安装包”中选择对应 `.tgz` 文件；请勿同时安装短包和完整包两个入口。

启用 CANNBot DSH 后，左侧新增“CANNBot工作台”，首页不显示“管理工作流”按钮。工作台沿用当前对话所属的工作区并展示真实路径，手动选择优先；无法识别当前工作区时要求明确选择，避免默认使用列表第一项。“选择工作区”使用 DSH 的目录浏览接口，可浏览 Host 目录或输入完整路径；已登记的目录直接复用，选择和取消均不启动任务。目录读取或登记失败在选择窗口内显示并重试。点击工作流卡片会勾选并聚焦输入框，保留已有文字与文件。首页不展示额外输入提示、自动应用说明和工作流数量，正常待机时不展示准备状态。

点击“开始”后按实际进展显示工作区准备、工作流依赖准备、文件上传与进入对话；没有文件时跳过上传步骤。准备失败时保留需求和文件，可展开原因并重试。发送后的模型运行错误由原生 DSH 展示，需求保留在草稿或对话记录中。工作流的独立更新、回退及日志在“插件 → CANNBot DSH”中管理。

工作流依赖由官方 CANNBot 初始化器按工作区准备，可能需要网络。依赖准备失败会显示错误并保留需求。当前工作台使用 DSH 0.2 系列的公开主面板与会话接口；不具备对应接口的旧版继续显示既有的品牌对话界面。关闭界面开关会移除定制入口，恢复原界面。

主程序与工作流包分开发布：主程序负责品牌界面、动态菜单和包管理；每个工作流自己的 npm 包包含 Skills、agents、模板、脚本及初始化入口。更新某个工作流不必更新主程序。

## 从本仓库安装（实时读取源码）

在仓库根目录执行（Node.js >=24.9，先按 DEVELOPMENT.md 配置 DSH 构建依赖）：

```sh
npm --prefix dsh run install:source
```

每次安装直接读取当前仓库的 `plugins-official/`、`harness/` 和 `vendor/cannbot-skills/`，包含未提交的内容修改。`dsh/` 不保存这些目录的资源副本。工作流在系统临时目录装配、校验后复制到 `$DSH_HOME/cannbot-dsh-workflows`（默认 `~/.dsh/cannbot-dsh-workflows`），临时文件随后清理。

更新源码后重新执行此命令即可，不需要手工同步资源或发布工作流 npm 包。内容散列决定是否刷新缓存及工作区初始化；同版本内容修改也会生效。明确执行源码安装会替换对应工作流的旧缓存及回退固定状态，全部资源校验成功后一次切换；缺少依赖则报错并保留原工作流。

也可以指定其他本地源码，或在安装时获取远端仓库当前 HEAD 及其声明的子模块：

```sh
node dsh/scripts/install-source.mjs --source /path/to/cannbot
node dsh/scripts/install-source.mjs --repository https://gitcode.com/cann/cannbot.git
```

本地安装要求共享 Skills 已满足源码声明；不会切换用户工作区的子模块版本。安装后重启 DSH。直接安装主插件 `.tgz` 或 npm 包使用下面的已发布工作流依赖机制，不会读取本地源码。

## 安装

### 一键安装（bash）

Linux / WSL 终端在仓库根目录执行：

```sh
bash dsh/install.sh
```

脚本依次完成：

1. 检查 Node.js 和 npm；缺少 Node.js 或版本低于 `24.9.0` 时，自动下载并安装 Node.js 24 LTS（默认 `v24.22.2`，从 npmmirror 下载；root 安装到 `/usr/local`，普通用户安装到 `~/.local`）；
2. 检查 `dsh` 命令，未安装时通过 `npm install --global @deepseek-ai/dsh` 安装（默认 `latest`），已安装时直接复用；
3. 检查 `pnpm`，缺少时通过 npm 全局安装；
4. 将 `cannbot-dsh@latest` 安装到 DSH 的 `web` profile，并确认插件已加入启用列表。

插件要求 DSH `>=0.1.1-rc.1 <0.3.0`。如果已有 DSH 不在该范围，请先切换版本，或用 `--dsh-version` 指定安装版本。

完成后执行 `dsh web` 启动。常用选项：

```sh
bash dsh/install.sh --check                         # 只检查当前状态，不做修改
bash dsh/install.sh --plugin-version 1.0.0-alpha.1  # 固定插件版本
bash dsh/install.sh --node-version 24.22.2          # 缺少 Node.js 时安装指定版本
bash dsh/install.sh --profile web --registry https://registry.npmmirror.com
```

完整选项见 `bash dsh/install.sh --help`。该脚本使用当前用户的全局 npm 前缀和现有 `DSH_HOME`（默认 `~/.dsh`），不会创建独立运行时；需要隔离安装时使用 `packages/install` 下的 Node.js 一键安装器。

### npm 安装

以下 npm 安装方式需对应版本已发布；本地源码安装使用上面的 `install:source` 命令。

在 DSH **插件 → 添加插件** 中输入：

```text
cannbot-dsh@1.0.0-alpha.1
```

完整包名为 `@cannbot-plugin/cannbot-dsh@1.0.0-alpha.1`。请只选择一种入口安装。
兼容范围为 DSH `>=0.1.1-rc.1 <0.3.0`，Node.js 24.9 或更新版本；图形包管理依赖 DSH 提供官方认证 Fetch 路由与插件管理接口。

目录包将默认工作流声明为标准 npm 必需依赖。DSH 的安装过程会一次下载主插件、目录包与全部 3 个默认工作流包，目前提供 53 个 Skills；任一依赖下载失败，安装阶段就会报错。首次启用只准备本地已安装资源，全部准备完成后插件才启用，不会在后台补装子包。首次安装需要网络；安装完成后可离线加载。

Linux 可使用同一个包：

```sh
dsh plugin --profile web add cannbot-dsh@1.0.0-alpha.1
dsh web
```

## 独立更新工作流

插件详情页的 **工作流管理** 为每个工作流显示包名、已安装版本和最新版本，可逐项安装、更新、回退，也可 **更新全部工作流**。
程序启用时加载已经安装的工作流；下载新版本通过详情页明确触发。回退后固定该版本，批量更新不会将它升回去；主动更新这一项即可恢复跟随最新版。

目录包是 `@cannbot-plugin/workflow-catalog`；工作流包统一为 `@cannbot-plugin/workflow-<ID>`。默认工作流集合由 `dsh/workflow-defaults.json` 决定，未列入的工作流不会被打包，也不会出现在目录包中；「检查更新」同样只保留该集合内的工作流。发布已有工作流的新版本只需更新对应小包；新增工作流先发布内容包，再更新小型目录包，无需发布主程序。维护者操作见 [独立工作流发布说明](WORKFLOW_PUBLISHING.md)。

主程序提供 **检查更新** 按钮，并支持 Host 后台一键升级：使用 DSH 官方更新接口，旧版 DSH 通过官方安装、卸载接口串联，失败时尝试恢复原版本。

## 使用与初始化

- 启用后默认显示 CANNBot DSH 品牌与红白主题。左下角的 **CANNBot DSH** 开关可恢复原版界面，工作流 Skills 不受影响。
- 选择工作区和工作流后，Host 自动准备该工作区。统一安装器工作流直接调用包内保留的上游 Node.js 安装器，指定 `--tool dsh --target <工作目录> --plugin-dir <包内资源目录>`；不需要另外克隆 CANNBot 主仓或共享 Skills 仓。
- 初始化按工作区、工作流包版本和完整性记录，相同版本不重复执行；更新其他工作流不会重复初始化当前工作流。外部依赖仍按上游 `plugin-install.json` 准备，可能需要 Git、网络及声明的运行环境。没有统一安装器的 `ops-registry-invoke` 保持原生 Skill 自检行为。
- 准备期间可以继续编辑需求，但该工作流准备完成前不会发送任务。失败时保留原选择，并在插件详情提供日志与重试入口。
- 用户输入框不会显示或加入 `/工作流名称`。发送时通过 DSH 官方 `agent/pre-step` 加载工作流上下文，用户消息、引用和附件保持原样。
- 本插件不提供 SSH 或远程连接控件；Linux 使用 DSH 自身的 Web 界面。

## 缓存、校验与回退

工作流缓存默认位于 `$DSH_HOME/cannbot-dsh-workflows`，未设置时为 `~/.dsh/cannbot-dsh-workflows`；可用 `CANNBOT_DSH_WORKFLOW_ROOT` 指定其他目录。
资源包通过 npm 官方 `pacote` 库下载并校验 SHA-512，安装时不运行 npm 生命周期脚本。每个版本安装到独立目录，通过格式与资源检查后原子切换；下载失败继续使用旧版。已安装内容可离线加载，首次工作区初始化仍须满足上游依赖条件。

卸载主插件不会自动删除工作流缓存或项目内由上游安装器生成的文件。

## 构建

主程序复用官方 DSH 开源仓库的 Client 构建预设，通过 `DSH_SOURCE` 或开发配置指定官方源码目录，然后运行 `npm run build`、`npm test`、`npm run pack:plugin`。不修改上游核心。
工作流小包可使用标准 Node.js/npm 构建与发布，具体命令和包格式见 [WORKFLOW_PUBLISHING.md](WORKFLOW_PUBLISHING.md)。

## Python 编排与 DSH 原生执行

使用 `harness/workflow-orchestrator` 的工作流通过 `cannbot_workflow_run` 启动：传入工作流包 ID、YAML、需求和可选工作目录。Python 保留依赖调度、并发、重试、回退和裁决逻辑；每个节点由 DSH 原生子 Agent loop 执行并继承会话模型，无需选择 Coding Agent CLI provider。用 `cannbot_workflow_status` 查询，用 `cannbot_workflow_cancel` 停止；审批仍使用 Python 工作流的审批脚本。

插件通过 `python3 -c` 导入工作流资源中的 `orchestrator.py`，向其通用函数接口注入执行回调；管道适配代码随插件编译，不增加 Python 入口文件或编排器命令行参数。安装时获取 Python 编排器，`dsh/` 不保存其副本。运行要求 Python 3 和 PyYAML，以及 DSH 的原生 spawn 子 Agent 能力。
