# 发布配置

修改 `dsh/release-policy.json`：

| 配置 | 内容 |
| --- | --- |
| `userAgreementUrl` | 法务审定的 CANNBot 用户协议 HTTPS 地址 |
| `privacyPolicyUrl` | 法务审定的 CANNBot 隐私政策 HTTPS 地址 |
| `hostSourceUrl` / `hostLicenseUrl` | 宿主官方源码与 MIT 许可证地址 |
| `hostTermsUrl` / `hostPrivacyUrl` | 宿主官方用户协议与隐私政策地址 |
| `channel` | `development`（测试）或 `public`（公开发布） |

在 `dsh/` 目录构建：

```sh
node scripts/package-windows.mjs          # 开发测试包
node scripts/package-windows.mjs --public # 公开发布包；正式协议链接不可为空
node --test tests/windows-setup.test.mjs tests/release-notices.test.mjs tests/release-policy.test.mjs
```

产物为单文件 `CANNBot-Setup.cmd`。告知页默认不勾选确认项；宿主从官方地址下载，官方安装向导交由用户操作。当前正式协议尚未配置，仅供开发测试。

下载页须在下载前提供 CANNBot 用户协议、隐私政策、第三方软件声明和来源说明。隐私政策应说明模型服务的接收方、SSH 密码的临时处理、可选账号同步后在远端保存的凭据、撤销方式，以及实际的数据采集行为。以法务审定版本为准。

固定开发规则：CANNBot 界面与图标使用 CANNBot 品牌，返回入口保持通用箭头和“返回原生工作台”；原生工作台不改写、不删除，新增扩展退出后还原；宿主名称只用于必要的纯文字来源、兼容要求与许可告知，不暗示官方合作。

根目录 `LICENSE` 保持 CANN-2.0，打包时完整复制。每次变更打包依赖，核对产物中的第三方代码并更新 `THIRD_PARTY_NOTICES.md`；发布前运行解包和许可检查。

## Linux 启动前问卷

新版安装器与主插件发布后，可执行：

```sh
npx @cannbot-plugin/cannbot-dsh-install@latest --workspace /path/to/new-workspace --workflow ops-direct-invoke-flash
```

`--workspace` 与 `--workflow` 必须同时提供，目录须为空；在当前终端回答初始化问卷，成功后才启动工作台，取消或失败会停止启动。开发时可使用 `node packages/install/bin/install.mjs --help` 查看入口参数；安装器仍安装 npm 已发布主插件，不会自动使用本地未发布源码。

已打开的工作台在创建或切换工作流时显示内嵌交互终端。切换前停止该工作区运行中的任务；成功后旧会话冻结，切回同一工作流也不解冻。用户代码与依赖仓库保留，旧工作流受管配置备份在工作流缓存的 `initialized/<工作区哈希>/retired/` 中。
