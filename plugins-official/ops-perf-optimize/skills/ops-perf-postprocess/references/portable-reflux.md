# 回流材料脱离原工作区仍可核对

`experience_policy=evidence_lessons_v2` 将本地验收与公开交付分开。原件、冻结身份和本地评审不改；公开材料先脱敏再交付。历史 v1 继续原协议，不能通过删除策略或改旧 manifest 绕过新门禁。

## 选择与脱敏

从已评经验的直接来源开始，选择支撑结论的最小充分文本集合；性能复算再补相应逐例CSV/采样记录。不要默认上传全部会话、构建目录或运行环境。只掌握私有出处时，可以在原料中如实列为不可达线索，但不能声称该条已完成可移植交付。v2 的直接来源必须有可核验的公开副本；未公开设备依赖单独列缺。

原始本地路径只用于内部证据核对。公开正文、来源、内嵌附件、索引与旧评审副本都要检查：个人工号、用户目录、内部项目标识、凭据不得从附件重新带回。使用不透明令牌（如 `<archive>/run/`、`<environment>/`）替换路径；正式引用用仓内相对链接或不可变版本的可获取材料。仅改正文链接、仅扫凭据正则均不足。自动规则不能识别所有内部名称，贡献者仍须复核选定内容；真正不应公开的条件按接收仓规则降格/删去并重评，不伪装成纯路径替换。

私有计划示例（保留在公开目录以外）：

```json
{
  "replacements": {"/private/task/root": "<archive>/run", "internal-project": "<project>"},
  "forbidden_literals": ["internal-project"],
  "sources": [{"path": "/private/task/root/result.json", "name": "run/result.json", "sha256": "原件64位SHA"}]
}
```

```bash
python3 /absolute/workflow/scripts/experience_portability.py sanitize \
  --plan /private/export-plan.json --out /new/public-snapshots
```

工具保留数值/状态，用声明的路径和标识替换生成副本，并按依赖次序重绑定选定文件间的SHA引用。`original_sha256` 是私有原件身份，`sha256` 是公开副本身份；两者不可混用。循环哈希依赖拒绝导出。未选入文件的历史哈希仍只是出处，不代表该文件可获取。脱敏不证明因果，也不产生新硬件观测。

## 按目标仓格式打包

目标仓允许普通文件时，用相对目录保存；目标仓仅接收原料卡时，可用 `rough_bundle.py pack` 将UTF-8公开副本放入标准原料卡正文的JSON载荷。先阅读目标仓当前规则，不创造附件豁免或擅改其README/门禁。工具留在本插件，数据投稿单独评审。

`pack` 的私有计划字段为 `account/time/title/sources`；每项 source 包含 `path/name/sha256`，对脱敏副本还传 `original_sha256`（从 sanitization-lineage.json 取）。身份必须是实际投稿账号；未获投稿授权仅在本地生成。

```bash
python3 /absolute/workflow/scripts/rough_bundle.py pack \
  --plan /private/pack-plan.json --out /public/r-account-0001.md
python3 /absolute/workflow/scripts/rough_bundle.py extract \
  /public/r-account-0001.md --out /new/extracted
```

每个载荷条目含 `name/text/bytes/sha256`，可选 `original_sha256`；JSON解码得到发布副本字节。接收者也可用标准JSON解析器读取，无需作者工作区。工具不执行材料里的命令，拒绝重复/上跳/绝对目标路径及已有提取目录。设备二进制、私有工具链等缺项应明列，不能把文本算术复核说成设备可复跑。

## integration 出口检查

先将本地已评正文中的私有标识、来源SHA及链接按同一映射迁移，保留完整经验内容。额外解释可放在正文前。内容性改写须重新评审；旧本地语义评分不能自动盖在公开副本上。

`knowledge-reflux.json` 的 `portable_delivery: {path,sha256}` 指向**本地私有** `portable-delivery.json`；其中原路径映射不提交到接收仓。该契约字段：

| 字段 | 含义 |
|---|---|
| schema_version | 1 |
| root | 公开文件集合的绝对根目录，与私有契约分离 |
| files | 公开相对文件名 → SHA256，必须覆盖root内所有文件，无未申报附件 |
| cards | files中作为JSON文本包的原料卡名；普通文件模式为空数组 |
| replacements / forbidden_literals | 本地脱敏映射与禁止进入公开物的项目标识；禁止替换纯数字结果 |
| source_entries | 本地经验每个来源ID → 包内name或普通公开文件名，全部直接来源必须覆盖 |
| material_file | files中完整公开经验卡的相对文件名 |
| links | 脱敏后的旧链接目标 → files中的相对目标，用于迁移证据链接 |
| unavailable | 未发布的二进制、环境等依赖及影响，无缺项时为空数组 |
| review_scope | 固定 `local_review_not_reused_as_public_review` |

```bash
python3 /absolute/workflow/scripts/experience_portability.py check-delivery \
  --contract /private/portable-delivery.json \
  --bundle /private/experience-lessons.json --material /private/experience-material.md
```

integration/verify/finish 会通过 `experience_reflux.py` 重算公开文件哈希、隐私检查、完整正文及全部直接来源与原件之间的声明变换。私有映射留本地不等于公开物仍依赖本地：接收端只使用公开文件及包内相对路径；投稿端才需要原件证明脱敏谱系。

交付前实际复制或克隆公开集合到隔离目录，禁止读取原工作区，不向网络/旧路径回退，运行提取和相应复核。核验CSV算术可使用 `check_experience_archive.py`（消费含files/path_roots/lessons/effects/collections等的归档索引）；其它材料选择对应离线检查。至少检验缺失或篡改证据会失败。报告分别列文本可获取、离线可核验、设备可复跑的范围及缺项，不用单一pass混称。

原料投到rough后仍须另做精炼才能进入book：准备主张、probe、obs与验证记录，按接收仓的独立审读/复验规则处理。数据提交不捆绑仓库工具或收料制度修改；那些改动在各自工程单独评审。
