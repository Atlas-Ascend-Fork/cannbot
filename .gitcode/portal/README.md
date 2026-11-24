# portal/ —— CANNBot 官网内容目录

本目录是 CANNBot 官网的**内容源**：首页文案、首页数据与页面外壳都在这里维护。
官网的页面骨架、组件与样式由官网工程提供，本目录**只放内容**——改文案、加减卡片、换链接都不需要改代码。

## 文件一览

| 文件 | 负责的页面区域 |
|---|---|
| `chrome.yaml` | 页面外壳：页脚版权、说明、分栏链接、联系方式 |
| `legal/*.md` | 隐私政策、用户协议等页脚链接指向的站内页面 |
| `docs/workflows/` | 开发者文档的安装指南来源配置、分工作流的快速入门及算子测试说明 |
| `sidebar.yaml` | 首页「开发者文档」和各文档页共用的工作流导航 |
| `home/nav.yaml` | 首页第二行 tab 的站内锚点 |
| `home/download.yaml` | 本地部署的文案、平台和架构按钮的显示顺序 |
| `home/installer-links.yaml` | 整包下载的实际地址，按操作系统和架构填写 |
| `home/agent.yaml` | 首屏 Agent 回放、预设问题、播放状态 |
| `home/hero.yaml` | 首屏（#hero）：主标题、导语、按钮，以及「分类 → 工作流 → 客户端」三层选择面板与安装命令 |
| `home/repos.yaml` | 开源生态（#repo-catalog）的仓库卡片，以及加入生态（#repos）的入口 |
| `home/workflow-aliases.yaml` | 官方工作流 ID 与显示名称的对应关系 |
| `home/install-workflows.yaml` | 插件安装展示的工作流 ID，按显示顺序排列 |
| `home/workflows.yaml` | 工作流屏（#workflows）：区块标题与导语 + 工作流卡片 |

首页自上而下的屏顺序（改顺序需要官网维护方改框架仓，内容侧改不了）：
**在线体验 → 本地部署 → 开源生态 → 能力全景 → 加入CANNBot社区**。

## 生效方式

提交到本目录后，官网在下一次构建时自动同步，无需改动其它文件。

安装指南在 [guide-sources.yaml](docs/guide-sources.yaml) 中引用仓库原文。更新 `dsh/INSTALL.md`、`dsh/USAGE.md` 或教程中的截图后，文档站下次构建会自动读取更新。

工作流说明更新后，在 CANNBot 仓库根目录运行 `node .gitcode/scripts/sync-portal-docs.mjs`。它将官方插件的快速入门（缺少时使用插件 README）和通用工作流指南同步至 `docs/workflows/`，并按 `home/workflow-aliases.yaml` 的别名和 `home/workflows.yaml` 的领域生成侧栏。将变化的归档文档和 `sidebar.yaml` 一起提交即可。「算子系统测试」是公共技能，其门户说明直接维护在此目录的 `ascendc-st-design.md`。
本目录不含站点工程，**本地无法独立预览**；需要预览效果请联系官网维护方。

## 字段说明

### `chrome.yaml` — 页面外壳

```yaml
nav:                      # 可选，顶部导航项；不配则不出现导航
  - text: 文档中心
    href: /docs/index.html
    # external: true       # 外链时填写，省略时按 href 是否以 http 开头判断
    # inFooter: true       # 同时出现在页脚时填写

footer:
  copyright: 版权文案      # 页脚左下；留空不渲染
  note: ''                # 页脚右下说明；留空不渲染
  columns:                # 页脚分栏，数组顺序即渲染顺序
    - title: 文档
      links:
        - text: 仓库架构与维护
          href: /docs/repository-guide.html
  contact:                # 第一项作为主页和文档页共用的反馈入口
    - text: 反馈与建议
      href: https://atomgit.com/cann/cannbot/issues

legal:
  - text: 隐私政策
    href: /legal/privacy.html
  - text: 用户协议
    href: /legal/terms.html
```

- 站内地址一律写成 `xxx.html`（不是 `xxx.md`，也不是不带后缀的路径）。
- 主页和开发者文档共用一个页脚。`footer.contact` 的第一项显示在左侧，`footer.copyright` 居中，右侧按顶层 `legal` 数组的顺序展示链接。
- 改页脚链接名称或顺序，编辑 `chrome.yaml` 的 `legal` 条目。改协议正文，直接编辑 `legal/privacy.md` 或 `legal/terms.md`。新增条目时，在 `legal/` 下添加 Markdown 文件，并将条目的 `href` 指向对应的 `/legal/文件名.html`。

### `home/download.yaml` — 本地部署

`install.platforms` 的每一项显示一个操作系统标题；其下的 `packages` 按配置顺序显示各架构的下载入口。

```yaml
install:
  platforms:
    - icon: windows
      label: Windows 版
      packages:
        - { arch: x64 }
        - { arch: ARM64 }
```

`arch` 是架构标识，也用作默认按钮文字。可用 `label` 自定义文字，例如给 Mac 的 ARM64 包显示「Apple 芯片」。

发布安装包时，只需编辑 [home/installer-links.yaml](home/installer-links.yaml)。在平台（`icon`）下找到对应的 `arch`，把空字符串换成完整 HTTPS 下载地址或以 `/` 开头的站内文件路径。站点下次构建后，对应按钮即可下载。留空的架构仍显示为不可点击的按钮。

### 首屏回放与首页素材

在 `home/agent.yaml` 的 `replay` 中配置回放入口、固定问题和播放按钮。原生 DSH 客户端和录制的会话来自 [原站 FP32 add 案例](https://cann.cannbot.cn/dsh-native-replay-v3/)，随 `static/native-replay/` 一起发布。会话事件在 `replay-transport-download.js` 内，`portal-controls.js` 控制只读启动与重播，运行状态沿用原生计时。

| 位置（相对本目录） | 在这里维护 |
|---|---|
| `static/replay/` | 原生回放提供下载的验证日志和状态文件 |
| `static/img/` | 品牌标志、GitCode 图标和平台图标 |
| `chrome.yaml` | 品牌、账户按钮、页脚链接、版权和法律条目 |
| `home/download.yaml` 的 `install` | 安装区标题、按钮、平台和命令面板标签 |
| `home/repos.yaml` 的 `actions` | 生态区入口；源码按钮的名称和链接与顶栏共用 |

`static/` 内的素材以 `/portal/` 为站内路径前缀。框架负责排版与播放，案例在访客浏览器中运行。

### `home/hero.yaml` — 首屏

```yaml
hero:
  name: 现在，交给 CANNBot          # 主标题
  text: ''                         # 副标题，留空不渲染
  tagline: 一句话导语
  actions:                         # 首屏按钮
    - theme: brand                 # brand = 主按钮，alt = 次按钮
      text: 查看安装说明
      link: ./docs/pre-commit_guide.html

clients:                           # 客户端身份表：只写显示名与标识，不写命令
  - label: OpenCode
    tool: opencode

showCategories: false              # 安装区直接展示所选 Harness 支持的工作流

categories:                        # 分类 → 工作流 → 客户端命令
  - title: 官方工作流
    workflows:
      - id: ops-direct-invoke
        clients:                   # 键是 clients 里的 tool；值是该客户端在此工作流下的完整命令
          opencode: 'npx @cannbot-plugin/cannbot@latest install ops-direct-invoke --tool opencode'
```

- `id` 在同一文件内唯一，用于定位工作流，客户不需要展示它。
- 某个客户端在此工作流下**不提供**命令时，留空串（`''`）：该客户端会置灰、不可点击。
- 新增客户端 = `clients` 加一行 + 在每个工作流的 `clients` 下补对应命令。

### `home/nav.yaml` — 首页第二行 tab

```yaml
- text: 下载
  link: /index.html#download
- text: 安装
  link: /index.html#install
```

`#` 后是首页内的区块锚点：`download`、`agent`、`install`、`repos`、`workflows`。

`install` 对应第 3 屏首屏 hero（主标题 + 插件/客户端选择面板 + 安装命令），所以 tab 叫「安装」。
hero 由框架仓的 VitePress 渲染、自身没有 id，官网工程在各主题的 `#home-hero-before` 插槽末尾
埋了一个零高锚点来承接这个跳转。

**不要**把它写成不带 `#hash` 的 `/index.html`：那会跳回页面顶部（第 1 屏），和第 3 屏对不上。

### `home/workflows.yaml` — 能力全景

```yaml
head:
  title: 能力全景
  lede:
    - 区块导语，可写多行

cards:                             # 写几条就渲染几张，顺序即显示顺序
  - id: ops-direct-invoke
    category: 算子领域
    link: https://gitcode.com/cann/cannbot/tree/master/plugins-official/ops-direct-invoke
    desc: 编写 Ascend C 核函数，在调用端直接启动算子，并验证计算结果。
```

### `home/repos.yaml` — 开源生态与社区入口

```yaml
catalogHead:
  title: 开源生态
  lede:
    - 区块导语

repos:
  - name: cannbot
    role: 应用仓
    slug: cann/cannbot             # 用于实时取 Star；不确定就留空
    desc: 卡片描述
    stars: '1068'                   # 静态兜底值，取不到实时数据时才用
    link: https://gitcode.com/cann/cannbot
```

- `catalogHead` 和 `repos` 配置仓群卡片区，`head` 和 `actions` 配置页尾的「加入CANNBot社区」。
- `stars` 是第三级兜底：页面优先实时取数，其次构建期快照，最后才用这里。
- `slug` 填仓库的「组织/仓库名」。**不要填不存在的 slug**：实时取数是并发请求、任一仓库失败就整体放弃，假 slug 会让同一页所有仓库的星数一起退回兜底值。不确定就留空——空值会被跳过，该卡不参与实时取数（若同时没写 `stars`，就不显示星数）。

## 修改须知

1. **工作流显示名称**统一取自 `home/workflow-aliases.yaml`，使用官方插件文件夹名作为 ID。
2. **结构字段不要增删**：只改值、加减数组条目；需要新增字段或新板块，先联系官网维护方。
3. **删文件不等于下线**：内容同步是覆盖式的，删掉某个文件后旧内容可能继续渲染。下线内容请同时通知官网维护方清理。
4. **站内链接统一带 `.html`**：写成 `.md` 或省略后缀会导致死链。
5. **屏的顺序与屏的数量改不了**：首页有哪几屏、先后顺序由官网工程的 `index.md` 与各主题的 Layout 决定。
   内容侧能做的是改每屏的文案、按钮、图片与卡片，**不能增删屏、不能调换屏的次序**。
   `nav.yaml` 里调整 tab 顺序是安全的（纯展示顺序），但要让 tab 顺序与屏顺序一致，否则读者会觉得跳转错位。

## 更新官方工作流

在 `home/workflow-aliases.yaml` 修改一个 ID 的别名，插件安装和能力全景会在下次构建时同时更新。

在 `home/install-workflows.yaml` 增删或移动工作流 ID，即可调整插件安装的选项和顺序。各工作流支持的客户端及命令在 `home/hero.yaml` 维护，DSH 插件市场包名在 `home/download.yaml` 维护。

能力全景的卡片、顺序和介绍由 `home/workflows.yaml` 管理。新增官方插件时，在别名配置中填写中文名，在卡片配置中填写同一 ID 的源码链接与简介。

## 维护与反馈

- 最后更新：2026-11-20（新增 `home/download.yaml`、`home/agent.yaml` 两屏）
- 问题与改进建议：https://atomgit.com/cann/cannbot/issues
