# CANNBot DSH

[安装指南](INSTALL.md) | [使用教程](USAGE.md)

Windows：单独下载 [CANNBot-Setup.cmd](CANNBot-Setup.cmd)，双击完成安装，无需本地代码仓。

CANNBot DSH 是面向昇腾 / CANN 开发的工作台，提供算子开发工作流、昇腾项目工作区和 DSH 内嵌远程开发。它作为独立插件运行在 DeepSeek Harness（DSH）宿主中，支持 Windows 桌面端与 Linux Web 端。

当前源码版本为 **1.0.0-alpha.1**。远端连接与 Windows 一键安装已并入本仓 `dsh/`，无需另装 `cannbot-remote` 插件。原有 npm / `.tgz` 插件安装、Linux / WSL 安装和源码安装入口继续保留。npm 安装使用已发布版本；要安装本仓当前改动，请使用 Windows 一键安装或源码安装。

目录结构、构建与检查步骤见 [DEVELOPMENT.md](DEVELOPMENT.md)，Windows 安装、修复与迁移说明见 [Windows 安装说明](scripts/windows/README.md)，实机验收与验证范围见 [VALIDATION.md](VALIDATION.md)。

## CANNBot 工作台

首次安装默认进入 CANNBot，之后记住用户选择的模式。原生工作台侧栏的“插件 / 自动化任务 / 更多”列表上方提供 **CANNBot** 入口，使用 CANNBot 图标。CANNBot 模式顶部显示 CANNBot 品牌；同一入口位置显示通用左箭头和 **返回原生工作台**，点击后恢复宿主原有界面。DeepSeek Harness 使用原生项目 / 最近列表，可显示当前 DSH 的全部会话，包括从 CANNBot 启动的会话；CANNBot 侧只显示自己的工作区和从 CANNBot 启动并登记的会话。普通历史会话不会仅因目录相同而进入 CANNBot 列表。切换模式时分别保留导航位置，切换工作区时保留尚未发送的需求和附件。

DeepSeek Harness 的侧栏列表、工作区下拉、主页、主会话区和底部工具栏均使用 DSH 原有界面；搜索、添加工作区和原生快捷键继续由 DSH 处理。模式往返切换保留原生列表的搜索和展开状态。CANNBot 侧栏以工作区为单位展示会话，远程工作区的文件夹右下角显示地球标记，不另加搜索框。

在 CANNBot 中点击“工作区”右侧的添加图标，依次选择工作流、服务器、父目录，再填写工作区名。只能新建文件夹，不能添加已有目录。工作流默认留空，必须手动选择。选择三种工作流时，“本机”选项禁用；若此前选中本机，则清空服务器选择。本机只允许“空白工作区：不安装工作流”；Linux 服务器可选空白工作区或三种工作流。工作流选项按“工作流 ID：用途描述”显示：`ops-direct-invoke`、`ops-direct-invoke-flash`、`ops-registry-invoke`。空白工作区不预装工作流，供手动配置昇腾项目，列表仅显示工作区名；其他工作区显示“工作流 ID: 工作区名”。一个物理目录只能绑定一种类型。初始化失败可在同一创建窗口中重试。

DSH 原生列表可查看普通会话和 CANNBot 会话，CANNBot 列表只显示明确登记的记录。已有目录不会通过创建窗口转换为 CANNBot 工作区。

父目录支持下拉浏览、路径输入和 Tab 补全；点击确认或下拉框外部收起列表。创建成功后自动进入新工作区的对话。工作流工作区会询问是否授予当前对话完全权限，用户同意后生效。选择未连接服务器时先确认，再显示固定大小的连接安装日志窗口，顶部可取消连接。首次安装预设“代码与开发”和“完整过程”，跳过模式引导；已有用户设置保留。

本机和已连接服务器的工作区、会话行按 DSH 原生布局显示操作：工作区右侧依次是 **⋯、新会话**；已有会话悬停时依次显示 **⋯、归档、置顶**，平时显示更新时间和置顶标记。工作区可重命名或删除；删除只移除工作区登记，保留磁盘文件与历史会话，没有现存工作区的会话不再显示在 CANNBot 列表中。会话菜单支持重命名、置顶 / 取消置顶、分叉、归档和复制 Session ID；置顶项优先显示。顶部 **视图选项** 可选择隐藏、显示或仅显示已归档会话。仍有任务运行时，归档会先要求确认停止任务。

启动页标题为“现在，交给CANNBot”，品牌标识不附加 Preview 标签。首页复用 DSH 原生会话输入组件和布局，保留访问权限、模型、推理等级、文件与指令等控件。通过工作区下拉框选择已有工作区，页面只读显示该工作区绑定的工作流；工作流可在创建时选择，也可在工作区菜单中切换；切换成功后旧会话永久冻结，只可查看。工作流示例作为原生输入框的占位提示显示，不添加“例如”前缀，不作为消息自动发送。准备失败会保留需求和文件，可查看原因后重试；发送后进入 DSH 原生会话。工作流更新、回退及日志仍在“插件 → CANNBot DSH”中管理。工作流依赖按所选目录准备，首次初始化可能需要网络、Git、Python 或 Ascend 环境。

CANNBot 侧栏的“自动化任务 / 更多”下方提供“服务器”入口，打开后可新增、连接、断开、改备注、拖动排序和删除服务器。服务器行右侧的添加工作区按钮会预选该服务器。已连接服务器的工作区直接显示在左侧工作区列表中。远端内容在 DSH 内嵌打开，点击本机工作区即可切回本机，SSH 隧道继续保留。

服务器行的 **⋯ → 编辑备注** 可修改显示名称，未连接时也可使用；清空备注后恢复显示 SSH 别名。备注持久保存在服务器清单，不修改 SSH 连接配置，也不会触发连接。

点击“插件”上方的 **返回原生工作台** 恢复宿主原有界面，工作流能力与数据仍保留。较旧 DSH 缺少对应公共接口时，不启用依赖这些接口的新工作台能力。

主程序与工作流包分开发布：主程序负责品牌界面、动态菜单和包管理；每个工作流自己的 npm 包包含 Skills、agents、模板、脚本及初始化入口。更新某个工作流不必更新主程序。

## 从本仓库安装（实时读取源码）

该入口面向当前用户的 DSH Web profile，默认是 `web`。在仓库根目录执行（Node.js >=24.9，先按 DEVELOPMENT.md 配置构建与工作流资源依赖）：

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

本地安装要求共享 Skills 已满足源码声明；不会切换用户工作区的子模块版本。安装后重启 DSH。Windows Desktop profile 由桌面应用管理，请使用下方 Windows 入口，不要将本命令直接改为 `--profile desktop`。直接安装主插件 `.tgz` 或 npm 包使用已发布工作流依赖，不会读取本地源码。

## 安装

### Windows 单文件安装

单独下载 [CANNBot-Setup.cmd](CANNBot-Setup.cmd)，双击安装 DSH 和 CANNBot，无需本地代码仓。首次安装需联网，已有 DSH 自动复用。图形窗口显示安装步骤、下载百分比与速度，可展开日志、取消下载及失败重试，完成后可直接打开工作台。

### Windows 开发者源码安装

在克隆或解压后的仓库根目录执行 `powershell -NoProfile -ExecutionPolicy Bypass -File dsh/scripts/windows/install-all.ps1`。脚本检查并安装 DSH 桌面端、准备 Desktop profile，然后安装本仓当前构建的 CANNBot 主插件。已有 DSH 默认复用；安装前会关闭目标 DSH 实例，请先保存正在进行的操作。

源码与构建收据一致时复用已有产物；源码变化或产物不完整时自动构建。首次构建可自动下载固定版本的官方 DSH 构建依赖，后续使用本地缓存；这一步需要网络。构建失败会停止安装，保留旧产物，不能将旧版本报告为本次源码安装成功。预构建分发目录应包含完整产物及构建收据。

安装后启动 DSH，点击“插件”上方的 CANNBot 入口进入 CANNBot 模式，再选择本机工作区或连接服务器。原独立远端插件的 bundle 注册会被移除，服务器配置与连接状态继续保留。检查、修复及自定义 `DSH_HOME` 见 [Windows 安装说明](scripts/windows/README.md)。

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

## 在 DSH 中连接 Linux 服务器

按住服务器行拖动可排序；“⋯ → 删除服务器”移除本机列表记录并断开连接，保留远端文件和会话。本机工作区在工作区列表中显示，不参与服务器排序。

1. 配置本机 OpenSSH，使用已有服务器别名或 SSH 命令连接，支持端口和跳板设置。支持密钥与密码认证；需要密码时在 DSH 内输入，仅供本次连接使用，不保存。首次主机指纹确认仍需先在终端执行 `ssh <服务器>`。
2. 在 CANNBot 侧栏点击“服务器”，再点击管理页右上角“＋”，输入 SSH 命令或已有配置别名，并保存连接；也可直接点击已有服务器的连接图标。默认读取本机 `~/.ssh/config`，共享清单保存在 `$DSH_HOME/cannbot-remote/servers.json`。
3. 首次连接会准备远端 Node.js / DSH、上传当前主插件的构建包并安装所需工作流依赖，然后建立本机 SSH 隧道。远端服务只监听 `127.0.0.1`。源码内容变化即使版本号相同也会同步，不能仅凭旧 npm 包版本相同跳过更新。
4. 连接成功后，在侧栏直接展开工作区选择会话。首次读取工作区时显示加载状态，并在 30 秒内自动重试暂时失败的读取；持续失败才显示错误和重试入口。服务器行右侧的添加图标打开统一创建窗口，并预选该服务器。页面始终内嵌于 DSH，可通过本机工作区或模式入口切换页面，隧道保持连接。
5. 鼠标移到服务器行时显示连接图标；已连接时点击同一图标即可断开 SSH 隧道。断开正在查看的服务器会返回本地，远端 DSH 服务和后台任务继续运行；断开其他服务器不切换当前页面。

“同步本机 DeepSeek 登录”默认开启，可以在连接前取消。本机存在受支持的 DeepSeek 平台账号登录时，通过 SSH 同步到远端；已有远端登录会保留，不覆盖。API Key 和其他账号凭据不在这项同步范围内。同步不可用或失败会显示状态，连接可继续，随后可在内嵌远端页面登录。

远端更新只会优雅停止能够核实归属的 DSH Web 进程。若提示服务归属无法确认、同一数据目录存在多个实例或进程未退出，应在该服务原来的终端停止后重连。断开操作关闭本机隧道；远端服务与项目数据保留。Linux Web 直接使用者继续通过原有安装和启动入口工作，桌面内嵌连接入口要求支持原生浏览器服务的 DSH 桌面端。

## 独立更新工作流

插件详情页的 **工作流管理** 为每个工作流显示包名、已安装版本和最新版本，可逐项安装、更新、回退，也可 **更新全部工作流**。
程序启用时加载已经安装的工作流；下载新版本通过详情页明确触发。回退后固定该版本，批量更新不会将它升回去；主动更新这一项即可恢复跟随最新版。

目录包是 `@cannbot-plugin/workflow-catalog`；工作流包统一为 `@cannbot-plugin/workflow-<ID>`。默认工作流集合由 `dsh/workflow-defaults.json` 决定，未列入的工作流不会被打包，也不会出现在目录包中；「检查更新」同样只保留该集合内的工作流。发布已有工作流的新版本只需更新对应小包，无需发布主插件。新增默认工作流时，必须更新 `workflow-defaults.json`，依次发布内容包、目录包及包含新集合的主插件；用户升级主插件后才能发现新增项。维护者操作见 [独立工作流发布说明](WORKFLOW_PUBLISHING.md)。

主程序提供 **检查更新** 按钮，并支持 Host 后台一键升级：使用 DSH 官方更新接口，旧版 DSH 通过官方安装、卸载接口串联，失败时尝试恢复原版本。

## 使用与初始化

- 点击“插件”上方的 **CANNBot** 进入昇腾开发工作台，点击左箭头 **返回原生工作台** 恢复宿主界面。切换不删除工作流 Skills 或历史数据。
- 创建 CANNBot 工作区时选定工作流，Host 自动准备该目录；后续会话沿用该工作流。统一安装器工作流直接调用包内保留的上游 Node.js 安装器，指定 `--tool dsh --target <工作目录> --plugin-dir <包内资源目录>`；不需要另外克隆 CANNBot 主仓或共享 Skills 仓。
- 初始化按工作区、工作流包版本和完整性记录，相同版本不重复执行；更新其他工作流不会重复初始化当前工作流。外部依赖仍按上游 `plugin-install.json` 准备，可能需要 Git、网络及声明的运行环境。没有统一安装器的 `ops-registry-invoke` 保持原生 Skill 自检行为。
- 准备期间可以继续编辑需求，但该工作流准备完成前不会发送任务。失败时保留原选择，并在插件详情提供日志与重试入口。
- 用户输入框不会显示或加入 `/工作流名称`。发送时通过 DSH 官方 `agent/pre-step` 加载工作流上下文，用户消息、引用和附件保持原样。
- 本机与远端使用相同的工作区绑定规则；远端目录选择、初始化和会话执行发生在所连接的 Linux 服务器上。

## 缓存、校验与回退

工作流缓存默认位于 `$DSH_HOME/cannbot-dsh-workflows`，未设置时为 `~/.dsh/cannbot-dsh-workflows`；可用 `CANNBOT_DSH_WORKFLOW_ROOT` 指定其他目录。
资源包通过 npm 官方 `pacote` 库下载并校验 SHA-512，安装时不运行 npm 生命周期脚本。每个版本安装到独立目录，通过格式与资源检查后原子切换；下载失败继续使用旧版。已安装内容可离线加载，首次工作区初始化仍须满足上游依赖条件。

卸载主插件不会自动删除工作流缓存或项目内由上游安装器生成的文件。

## 构建

主程序复用官方 DSH 开源仓库的 Client 构建预设。`node scripts/build-current.mjs` 检查当前源码与产物内容，必要时准备构建依赖并重建；`--check` 只检查，`--force` 强制重建。也可通过 `DSH_SOURCE` 或开发配置指定官方源码目录，使用原有 `npm run build`。开发、检查和打包命令见 [DEVELOPMENT.md](DEVELOPMENT.md)。不修改上游核心。
工作流小包可使用标准 Node.js/npm 构建与发布，具体命令和包格式见 [WORKFLOW_PUBLISHING.md](WORKFLOW_PUBLISHING.md)。

## Python 编排与 DSH 原生执行

使用 `harness/workflow-orchestrator` 的工作流通过 `cannbot_workflow_run` 启动：传入工作流包 ID、YAML、需求和可选工作目录。Python 保留依赖调度、并发、重试、回退和裁决逻辑；每个节点由 DSH 原生子 Agent loop 执行并继承会话模型，无需选择 Coding Agent CLI provider。用 `cannbot_workflow_status` 查询，用 `cannbot_workflow_cancel` 停止；审批仍使用 Python 工作流的审批脚本。

插件通过 `python3 -c` 导入工作流资源中的 `orchestrator.py`，向其通用函数接口注入执行回调；管道适配代码随插件编译，不增加 Python 入口文件或编排器命令行参数。安装时获取 Python 编排器，`dsh/` 不保存其副本。运行要求 Python 3 和 PyYAML，以及 DSH 的原生 spawn 子 Agent 能力。

工作流问卷使用内嵌交互终端；完成前不会进入可用会话。Linux 本机可直接使用工作流。初始化失败恢复受管 Skills 和配置，项目源文件保留。服务器账号授权同步默认关闭，需对目标服务器明确勾选同意。

公开发布配置与验收见 [RELEASE.md](RELEASE.md)。
