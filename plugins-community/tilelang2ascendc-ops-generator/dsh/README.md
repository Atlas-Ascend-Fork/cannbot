# DSH 派发协议适配器

把 `tilelang2ascendc-ops-generator` 在 DeepSeek Harness（DSH）上的子代理派发协议，
写入 DSH 的用户级指令文件 `${DSH_HOME:-$HOME/.dsh}/AGENTS.md`。

## 为什么需要它

DSH 没有命名 Agent 注册机制：插件的角色定义随安装落在 `<项目根>/.dsh/agents/`，
但没有任何机制告诉编排者去读取它。缺了这段说明，编排者按名字派发子代理时会拿不到
角色定义正文，工作流 Phase 3–7 的行为会退化。

## 为什么只影响 DSH

本适配器只写 `$DSH_HOME/AGENTS.md`，那是 DSH 专属的用户级指令通道
（`dsh-agent-instructions` 读取 `$DSH_HOME/AGENTS.md` + 项目 `AGENTS.md`/`CLAUDE.md` 链）。
Claude Code / Codex / OpenCode / TRAE 都不读该文件，因此：

- 不修改任何被多客户端共用的文件（插件 `AGENTS.md`、`agents/*.md`、`workflows/**` 一行不动）
- 不需要在任何共享文档里加入客户端分支措辞

## 安装 / 卸载

```bash
# 安装（默认 $DSH_HOME 或 ~/.dsh）
bash dsh/install.sh

# 指定 DSH home
bash dsh/install.sh --dsh-home /path/to/.dsh

# 只检查状态，不写入
bash dsh/install.sh --check

# 卸载（保留文件中的其他内容）
bash dsh/uninstall.sh --dsh-home /path/to/.dsh

# 卸载并清理安装期备份
bash dsh/uninstall.sh --dsh-home /path/to/.dsh --purge
```

安装内容只有一个受管标记块：

```
<!-- cannbot:tilelang2ascendc-ops-generator:dsh-protocol:start -->
...
<!-- cannbot:tilelang2ascendc-ops-generator:dsh-protocol:end -->
```

标记块内容取自同目录的 [`protocol.md`](protocol.md)。

## 行为保证

| 性质 | 说明 |
| --- | --- |
| 幂等 | 重复执行后 `AGENTS.md` 字节不变（受管块先删后写） |
| 可回退 | 首次写入前备份为 `AGENTS.md.bak.<时间戳>`；校验失败自动还原 |
| 可卸载 | 只删受管块；若文件中没有其他内容则删除该文件 |
| 可观察 | 写后校验受管块恰好出现一次且顺序正确，失败即报错退出 |
| 失败安全 | 校验不通过时还原为安装前内容，不影响 DSH 启动 |

## 边界与注意

- **只在用户级生效**：DSH 未提供项目级配置通道（项目级 `.dsh/AGENTS.md` 不被读取），
  因此受管块对本机所有 DSH 会话可见；`protocol.md` 内已限定"仅当项目根存在
  `.dsh/agents/` 时适用"。
- **不是 hook，也不是 preset**：DSH 0.2.0-rc.2 已不再读取
  `$DSH_HOME/.agent-presets/<id>/` 目录，本适配器不使用该路径，也不注册
  `@deepseek-ai/dsh-agent-preset` 声明；未引入任何生命周期 hook。
- **资产位置**：本目录是插件根下的独立资产目录（刻意不放在 `hooks/` 内——`init.sh` 会把
  `hooks/` 的每个条目镜像安装到支持 hook 的客户端，放进去会被当成 hook 条目一起装出去）。
  适配器脚本需要用户在插件目录内手动执行。
- **与 `init.sh global dsh` 共存**：两者共用 `$DSH_HOME/AGENTS.md`。`init.sh global dsh`
  以受管块方式合并写入，会保留本适配器的派发协议块以及文件中原有的用户内容；
  重装后无需再次执行 `install.sh`。
- 卸载后如需重新启用，重新执行 `install.sh` 即可。
