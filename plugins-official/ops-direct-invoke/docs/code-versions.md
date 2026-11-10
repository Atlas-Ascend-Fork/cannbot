# DSL 代码版本协议

此协议用于新启动的 DSL 工作流。脚本为 `$OPS_DIRECT_INVOKE_ROOT/tools/code_versions.py`；以下 `CV` 表示该脚本的绝对路径，用 `python "$CV"` 调用。`WORK_DIR` 是 harness 传入的原工作流目录，不能改写。Git 不配置 remote、不推送；不操作宿主项目 Git 或只读示例仓。

## 目录和权限

- 主代码仓：`$WORK_DIR/code`；Unit 工作区：`$WORK_DIR/code-worktrees/<节点ID>`。`status --node <节点ID>` 的 JSON 中 `CODE_DIR` 是实际源码根目录。执行者和验收者都必须读取并设置它。
- 实现、测试、CSV、Golden、辅助脚本在 CODE_DIR 内；设计仍在 `$WORK_DIR/design`，单元报告在 `$WORK_DIR/implementation/<op>`，其他报告沿用任务路径。缓存、Native 产物、profiling 与运行输出必须显式指定到 WORK_DIR 的代码仓外目录。
- Python 字节码与原 runner 固定输出目录 `operators/*/test/testcase_output/` 不纳入 Git。验证封装将原 runner 的本次输出归档到代码仓外的 `versioning/artifacts/<证据ID>/`，保存文件摘要；运行前有残留结果则阻断，不能混用上一轮结果。未知未跟踪文件会阻断，不自动 stash、reset 或 clean；不能把未知资产加入忽略规则绕过检查。
- `--allow` 是相对 CODE_DIR 的字面路径，可重复传入；目录表示该目录下全部文件。不得传 glob、绝对路径或 `..`。权限取任务原有写入范围，Git 管理不增加修改权限。Unit 仅允许原生 scope.source_files；缺少路径时阻断。
- `versioning/state.json` 与日志由脚本管理，不手工修改。`operation.lock` 只覆盖 Git/元数据操作，并发命令默认等待最多 30 秒（可用 --lock-timeout 调整）；测试期间释放全局锁但保留工作区测试状态。仅在确认相关进程已停止后才能清理陈旧锁或恢复中断尝试。

## 每轮修改

创建工作区节点执行 `python "$CV" --work-dir "$WORK_DIR" init`。后续重试 init 只返回现有记录，不清空目录。每个节点采用工作流节点 ID；每轮修改选择新的 attempt ID（如 `a001`）。以下 SHA 都必须是脚本返回的完整值，不用 HEAD~1、短 SHA 或猜测版本。

```bash
python "$CV" --work-dir "$WORK_DIR" status --node "$NODE"
python "$CV" --work-dir "$WORK_DIR" begin --node "$NODE" --attempt a001 \
  --expected-head "$BASE_SHA" --allow operators/my_op/my_op.py
# 在返回的 CODE_DIR 中执行本轮编辑，可改多个授权文件。
python "$CV" --work-dir "$WORK_DIR" checkpoint --node "$NODE" --attempt a001 \
  --expected-head "$BASE_SHA"
python "$CV" --work-dir "$WORK_DIR" verify --node "$NODE" --attempt a001 \
  --expected-head "$CODE_SHA" -- python "$CODE_DIR/operators/my_op/test/test_my_op.py" <原任务测试参数>
```

`verify` 以 CODE_DIR 为 cwd，设置 CODE_DIR、原 WORK_DIR 和 PYTHONPATH=CODE_DIR，以参数数组执行 `--` 后的命令；不支持 shell 拼接。多个测试命令分别执行 verify；若需要汇总脚本，该脚本也必须先纳入本轮提交。命令的退出码、输出日志、日志摘要、原 runner 结果文件及其摘要、代码 SHA 和冻结输入摘要由脚本记录。Python 字节码与默认编译缓存重定向到代码仓外，避免恢复后读取旧工作树缓存。测试失败返回非零，但保留代码提交和原始证据。

再次编辑必须开启新 attempt。失败代码可以直接作为下一轮基线。没有代码变化的验证节点也执行 begin/checkpoint，保存本节点版本与证据；此时 SHA 不变。`--allow` 仍使用本节点原有授权范围，纯验证节点不能因此编辑代码。

黑盒生成与方案设计可能并行，黑盒节点 begin 显式使用 `--input "$WORK_DIR/design/doc/spec.yaml"`，只冻结其真实输入。其余代码阶段默认冻结整个 design 目录；自定义 `--input` 时重复列出全部需要冻结的输入文件或目录。测试资产本身在 Git 内，不需要额外摘要。

各写入节点的范围：黑盒生成仅对应 testcase.csv（还需按原任务检查只变动 blackbox 分组）；测试生成仅 operators/<op>/test；实现与修复仅源码允许路径，不能放宽到整个 operators 目录；性能节点仅 scripts/performance。文档、检视与交付沿用只读代码权限。无代码验证命令的纯文档节点不需要制造一个空测试来获得“通过”。

## 独立验收

执行者不得代替 verifier 登记通过。verifier 通过 status 获取实际 CODE_DIR 与完整记录，按任务检查全部必要测试、原始日志、输入与源码版本、允许路径及业务判据。存在失败必测项时，不得只挑选另一条成功命令登记通过。确认通过后执行：

```bash
python "$CV" --work-dir "$WORK_DIR" verify --node "$NODE" --attempt a001 \
  --expected-head "$CODE_SHA" --accept "$EVIDENCE_ID"
```

EVIDENCE_ID 引用本轮成功验证记录；它不替代 verifier 对全部证据的审查。脚本复核 HEAD、干净工作树、输入摘要、依赖是否仍有效以及日志摘要。验收动作由角色契约区分，不是工具级身份认证。修改版本后先前验收不能继续使用。

## 并行 Unit 与汇合

test-generator 验收后，其 SHA 是全部 Unit 的共同测试基线。执行者从 versioning 记录读取该已验收 SHA，不从当前主仓 HEAD 推测。每个 Unit 首先执行：

```bash
python "$CV" --work-dir "$WORK_DIR" init --node implement-u01 --base "$TEST_BASE_SHA"
```

基线记录和独立工作区在重试时复用，不覆盖。对生成节点列出的所有依赖，按列表顺序读取其已验收 SHA，在本 Unit 工作区调用 integrate（无依赖则跳过）：

```bash
python "$CV" --work-dir "$WORK_DIR" integrate --node implement-u02 --attempt deps001 \
  --expected-head "$UNIT_HEAD" --allow <依赖源码路径> --allow <本单元源码路径> \
  --dependency implement-u01="$U01_SHA"
```

集成命令允许路径是所汇合依赖和当前 Unit 的源码路径并集，不包括冻结测试。依赖汇合不算 Unit 功能验收；之后开启新的编辑 attempt，使用当前 Unit 自己的允许路径。脚本自动继承该工作区已记录依赖，不能通过省略参数绕过失效检查。Unit 的 verifier 用 implement-uXX 节点 ID 验收最后一个实现 attempt。

全部 Unit 完成后，implementation-fix 在主代码仓按生成列表的拓扑顺序 integrate 所有已验收 SHA。允许路径是所有 Unit 源码路径并集。已存在的祖先自动跳过，不重置主分支，保留此前修复。之后按原任务完成检查或修改、验证和验收；unit-integration 在同一主代码仓重新验证组合版本。

发生冲突会保留 Git 合并状态并返回失败，不选 ours/theirs。读取 state 中的 conflict attempt，仅在授权源码范围解决冲突，然后以 status 返回的实际 HEAD 调用同一 attempt 的 checkpoint；脚本完成当前合并并继续未完成的依赖。冲突涉及冻结测试、Golden 或设计时终止节点并报告，不通过扩大 allow 解决。解决冲突不等于通过，仍须重新验证。

## 中断与恢复

编辑中断：重用原 node、attempt、基线、allow 和依赖调用 begin，核对现有修改，再 checkpoint；不会丢弃未提交内容。验证中断或验证脚本误改代码：先确认验证进程停止，检查现场，再用同一 attempt 的 `checkpoint --recover --expected-head <该次checkpoint SHA>` 保存现状，重新验证。旧证据继续保留，恢复事件另行记录。

Git 操作失败、HEAD 漂移、未登记提交、仓库路径改变或未知文件出现时，脚本阻断；记录实际状态并人工核对归属，不用删除状态文件“重新开始”。

## 精准恢复与交付

检视修复子图同样使用统一代码仓。baseline 节点从 `precision-validation` 的已验收提交及归档结果生成 `review-fix/baseline.json`，通过 `review_fix.py baseline --work-dir "$WORK_DIR" --code-dir "$CODE_DIR" --commit <完整SHA> --results-dir "$WORK_DIR/review-fix/baseline-results"` 只读核验，不再创建第二个 Git 仓库。该检查器未传代码根参数的旧接口仅供旧运行兼容。

修复节点使用 Git 节点 ID `review-fix`，保留原意见清单、harness 重试预算与最后一轮基线托底语义。托底通过要求恢复提交的全量复验，不把原基线 SHA 的结果直接登记给新提交。`selected.json` 记录实际 HEAD，`baseline_commit` 另记恢复目标；检视报告与失败证据留在代码仓外。性能节点新增受管采集脚本后，保存选定算子子树未变的证据，并对最终完整 SHA 补齐冻结测试复验。

`rollback_to` 只控制 harness 返工，不触发 Git 恢复。需要放弃某个版本时，先保存当前修改并确保无活动尝试，再执行：

```bash
python "$CV" --work-dir "$WORK_DIR" restore --node "$NODE" \
  --expected-head "$CURRENT_SHA" --target "$TARGET_FULL_SHA" --reason "放弃本轮尝试的原因"
```

恢复的是该工作区完整受管代码树，包含新增/删除/重命名；脚本创建恢复提交，不重写历史。恢复后 tree ID 必须与目标相同。未知未跟踪文件、受影响的被忽略资产会阻断恢复。恢复提交未验收；开启新 attempt、重新验证并由 verifier 登记。恢复后依赖旧版本的下游证据失效，应交既有工作流重新验证，不能直接恢复旧 PASS 状态。

交付前复核最终 SHA 与全部有效报告，并导出历史：

```bash
python "$CV" --work-dir "$WORK_DIR" status --bundle /absolute/delivery/code-history.bundle
git clone /absolute/delivery/code-history.bundle /absolute/recovered-code
git -C /absolute/recovered-code switch --detach <DELIVERY中记录的完整SHA>
```

bundle 包含主分支、Unit 分支及持久检查点引用，失败版本不会随分支前进而丢失。配套 JSON 记录 bundle 摘要、tree、文件清单和版本映射。交付时复制 versioning 日志和原始验收证据，DELIVERY.md 写明实际执行命令、最终 SHA、依赖版本、恢复方法与限制；不得将 JSON 中的路径当作交付目录仍可用的证据链接。

本机制不拦截编辑工具，不能证明模型从未产生未登记中间编辑；它校验已登记检查点、实际恢复结果与验收时的版本一致性。
