# 独立评审与开发入口

AICPU 开发使用 [aicpu-task-prompts.md](aicpu-task-prompts.md)，CCU 开发使用 [ccu-task-prompts.md](ccu-task-prompts.md)。旧 CCU VERIFIED 流程已被包含基线和独立评审的流程替代。

## 独立只读评审

仅用于用户要求审查现有 AICPU template；按用户输入替换占位符，未提供的 base/spec 写“无”。
报告路径优先采用用户指定值，否则使用该算子的 docs/REVIEW.md。复用已确认的输入，不要求环境安装。

```text
subagent_type: hccl-reviewer
prompt:
请使用 hccl-aicpu-best-practice 对以下目标做独立只读评审：
- HCCL 仓路径：{repo_path}
- 目标文件：{target_files}
- 评审模式：{review_mode}
- 增量基线：{base_ref}
- 每个 template 的 spec 路径：{spec_paths}
- 报告路径：{report_path}

从已加载 skill 目录定位脚本，显式传 --repo，不要求 hccl-env.sh。
增量评审将 base ref 固定为 commit，逐个 template 使用对应 spec。
执行脚本检查并完成人工清单，按报告模板写证据和静态结论；无 spec 标注契约层未执行。
只写报告，不修改源码，不安装环境、不构建或运行测试，也不启动修复循环。
如未提供实际验证证据，报告明确写未验证，不给出功能验收通过结论。
```


## CCU 独立只读评审

使用同一个 `hccl-reviewer`，显式传 engine=CCU、HCCL/HCOMM 仓路径、目标文件、基线、已有设计/launch 契约（有则提供）和报告路径。加载 `hccl-ccu-best-practice`，按真实源码独立核对；缺少声明时记录未验证范围，不强制进入开发流程。只写评审报告，不安装、构建或自动修复。
