# Windows 安装、检查与迁移

Windows 入口安装本仓当前构建的 CANNBot 主插件，其中包含工作区模式、SSH 连接和远端内嵌页面。原有 Linux / WSL、npm、`.tgz` 和工作流源码安装方式见 [主说明](../../README.md)。

## 选择入口

| 入口（位于 `dsh/`） | 用途 |
| --- | --- |
| `CANNBot-Setup.cmd` | 单文件下载后双击；无需代码仓，安装 DSH 和内置的 CANNBot |

安装后首次启动默认进入 **CANNBot**，选择本机工作区或连接服务器。CANNBot 模式使用 CANNBot 品牌；列表顶部提供通用左箭头和 **返回原生工作台**，点击恢复宿主界面。每台服务器按原生项目列表样式显示连接状态，连接成功后可逐层展开工作区和会话。无需安装单独的远端插件。

DeepSeek Harness 恢复原生侧栏列表和工作区下拉，可显示全部会话，包括从 CANNBot 启动的会话；搜索、添加及快捷键继续由 DSH 处理。CANNBot 侧只显示自己的工作区和从 CANNBot 启动并登记的会话，不添加搜索框。CANNBot 选中行使用与 DSH 一致的背景高亮，文字颜色不变。CANNBot 启动页显示“现在，交给CANNBot”，通过工作区下拉框选择已有工作区，只读展示绑定工作流。工作流仅在创建空目录工作区时选择，启动页不再提供工作流下拉框，品牌旁不显示 Preview 标签。

CANNBot 本机和远端列表按原生位置显示工作区 **⋯、新会话** 和会话 **⋯、归档、置顶** 操作，菜单支持重命名、删除工作区、分叉会话及复制 Session ID。删除工作区保留目录和会话，没有现存工作区的会话不再显示在 CANNBot 列表中；顶部 **视图选项** 的归档筛选提供恢复入口。服务器菜单可 **编辑备注**，清空后恢复 SSH 别名，不修改连接配置。

一键安装会先关闭已确认路径的 DSH 窗口；若应用只缩到托盘，会结束记录下来的主进程，再等待其子进程自行退出。无法确认进程归属或仍有残留时会停止安装，提示完全退出 DSH 后重试。请先保存正在进行的操作。

## 当前源码与构建产物

普通用户单独下载 [CANNBot-Setup.cmd](../../CANNBot-Setup.cmd) 并双击即可。双击后打开原生图形窗口，显示步骤、下载百分比、大小和速度；支持日志展开、取消下载及失败重试。安装器内置已构建主插件，无需本地代码仓、Git 或编译环境；DSH 桌面程序和运行依赖按需联网获取。

开发者在仓库根目录执行 `powershell -NoProfile -ExecutionPolicy Bypass -File dsh/scripts/windows/install-all.ps1`，从本仓 `dsh/` 构建并安装。首次源码安装会额外获取构建工具。

`scripts/build-current.mjs` 比较源码和产物内容与 `lib/.cannbot-build.json` 收据。内容一致时复用已有产物；源码变化、产物缺失或损坏、收据不匹配时重建。构建失败会停止后续安装，并恢复先前产物。没有配置构建环境时，工具会在 `dsh/.build-cache/` 准备固定版本的官方 DSH 构建源码与最小依赖。

已配置的 `DSH_SOURCE`、`.dsh-source.json` 或相邻官方源码目录仍可使用。开发环境细节见 [DEVELOPMENT.md](../../DEVELOPMENT.md)。预构建分发目录应保留完整 `lib/` 与收据、安装脚本及其依赖；构建产物匹配时无需再次获取官方源码。

安装的主包放入 Desktop profile 的 `.cannbot-workbench/<内容散列>/` 独立目录，再关联到 profile。相同版本号下的源码变化也会生成新的部署内容。替换前保留原包和 profile 备份；工作流 npm 依赖仍通过包管理器安装。要从当前仓库重新装配工作流资源，请使用主说明中的 `install:source` 流程；这是与 Windows 主插件构建不同的入口。

## 只读检查与修复

在仓库根目录的 PowerShell 中执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\dsh\scripts\windows\install-all.ps1 -Check
powershell -NoProfile -ExecutionPolicy Bypass -File .\dsh\scripts\windows\provision.ps1 -Check
```

第一条同时检查 DSH 安装与已有 Desktop profile；第二条只检查插件部署。两者都不会下载、构建、关闭 DSH 或修改 profile。缺少 DSH、profile、必要文件、启用项，或 profile 带有 UTF-8 BOM 时返回非零状态。`-Check` 不会自动修复问题。

完全退出 DSH 后修复插件与启用项：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\dsh\scripts\windows\provision.ps1 -Repair
```

`-Repair` 使用当前主包重新部署，备份 profile，并用无 BOM 的 UTF-8 写入 JSON。需要重新安装或升级 DSH 桌面程序时，可为 `install-all.ps1` 加 `-Upgrade`；普通安装默认复用已有 DSH。

如果安装使用了自定义数据目录，所有检查和修复命令均应设置同一个 `DSH_HOME`：

```powershell
$env:DSH_HOME = 'D:\MyDshData'
powershell -NoProfile -ExecutionPolicy Bypass -File .\dsh\scripts\windows\provision.ps1 -Check
```

维护者可以通过 `provision.ps1 -PackageRoot <目录>` 明确选择已经构建好的主包目录；该模式不运行源码构建，但仍检查并部署所选主包。

## 从独立远端插件迁移

安装时保留其他插件、profile 自定义字段及工作区数据，将 `cannbot-dsh` 短包或旧 `@cannbot-plugin/cannbot-remote` 的启用入口统一为主插件 `@cannbot-plugin/cannbot-dsh`，避免重复注册界面。

以下数据不因安装、修复或卸载被清除：

- `$DSH_HOME/cannbot-remote/servers.json` 与连接状态。
- `$DSH_HOME/cannbot-dsh-workflows/` 中的工作流缓存和模式归属记录。
- DSH 原有会话、登录数据及项目目录。

卸载后重启 DSH。重新安装可继续使用保留的数据；不要把清空 DSH 数据目录当作常规修复步骤。

## 连接服务器

按住服务器行拖动可排序；在“⋯”菜单选择“删除服务器”可移除列表记录并断开本机连接。远端文件、会话和服务保留；本机固定在顶部。

先在本机终端完成 SSH 密钥、主机指纹及跳板配置，确认 `ssh -o BatchMode=yes <别名>` 可登录。CANNBot 读取现有 SSH 配置；连接过程中不会弹出交互式密码输入。

进入 CANNBot 模式后，点击“服务器”标题右侧的“＋”，输入 SSH 命令或已有配置别名；已有服务器可直接点击其连接图标。未连接的服务器不允许展开。连接后展开服务器读取其工作区，再展开工作区查看会话；新增工作区图标位于服务器名称右侧。当前主包会经 SSH 上传并按内容散列校验；远端复用兼容运行时，更新主包后建立仅监听本机地址的 Web 服务和 SSH 隧道。

“同步本机 DeepSeek 登录”默认选中，可在连接前关闭。已有远端登录不会被覆盖；同步状态异常不阻止连接，可在 DSH 内嵌远端页面中登录。此选项同步受支持的平台账号登录，不同步 API Key 或其他凭据。

连接图标仅在悬停服务器行或键盘聚焦时显示。连接成功后再次点击该图标可断开本机 SSH 隧道，远端服务和任务继续运行；断开当前查看的服务器时返回本地。首次工作区读取持续显示加载状态，暂时失败会在 30 秒内自动重试读取，超出窗口才显示错误和重试入口。

打开远端工作区或会话后，内容显示在 DSH 的独立主页面，不再显示底部连接栏。通过本机工作区或模式入口切换页面时，SSH 隧道保持连接。选择目录和初始化工作流发生在远端机器上。若更新提示已有服务归属无法确认或未能退出，应在该服务原终端停止后重连；安装器不会按端口号直接强制终止进程。

## 常见情况

| 提示或现象 | 处理 |
| --- | --- |
| 当前源码需要构建，下载或构建失败 | 查看错误，检查网络或按开发说明配置 `DSH_SOURCE`，然后重新安装 |
| Desktop profile 尚未创建 | 启动 DSH 完成初始化后退出，再安装插件 |
| profile 存在 UTF-8 BOM | 完全退出 DSH 后运行 `provision.ps1 -Repair` |
| DSH 仍在运行或残留子进程 | 完全退出应用与托盘实例后重试 |
| SSH 无法批处理登录 | 先在终端修复密钥、主机指纹或跳板配置 |
| 新工作区目录不为空或工作流冲突 | 新建空目录；已绑定的目录只能使用原工作流 |
| 同版本更新后远端需要重新连接 | 重新连接以部署当前内容，不只比较 npm 版本号 |

本文描述安装与运行行为；真机验收记录由实际测试结果另行维护。
