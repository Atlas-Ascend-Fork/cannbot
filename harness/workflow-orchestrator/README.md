# 工作流编排器（Workflow Orchestrator）

使用 `/workflow-orchestrator` 运行 YAML 定义的开发工作流。技能会启动工作流、等待运行结束，并返回日志和退出状态。

## 准备输入

调用时提供以下四项信息：

| 输入 | 说明 |
|---|---|
| `workflow.yaml` | 工作流定义文件路径 |
| `work_dir` | 本次运行的工作目录，用于保存产物和进度 |
| `provider` | 执行任务的 Coding Agent CLI，例如 `opencode` |
| `prompt` | 本次开发任务的要求和验收目标 |

缺少输入时，技能会向你询问。

## 调用示例

```text
/workflow-orchestrator

workflow.yaml：/workspace/my-project/workflow.yaml
work_dir：/workspace/my-project/workflow-run
provider：opencode
prompt：实现指定功能，运行测试，并生成结果报告。
```

技能会在后台运行并等待结束，无需手动启动各个任务。完整调用流程见 [SKILL.md](SKILL.md)。

## 准备工作流

已有工作流时，直接提供其 YAML 路径。新建工作流时，从 [带注释的模板](templates/basic_workflow.yaml) 开始，填写每项任务的目标、执行方法、验收标准和依赖关系。

验收标准应能明确判断是否通过，例如“测试全部通过”或“生成非空的结果报告”。

## 查看结果与恢复运行

运行结束后，技能会返回日志和退出状态。完整日志保存在 `<work_dir>/orchestrator.log`，任务产物保存在指定工作目录中。

- **退出码 0**：工作流全部通过。
- **非零退出码**：查看日志中的失败原因或被跳过的任务。

继续已有运行时，再次调用技能并提供相同的工作流路径和 `work_dir`，同时提供 `provider` 和 `prompt`。技能会使用已保存的进度继续运行，未完成的任务可能重跑；已有运行继续使用首次保存的任务提示词。

开始一次独立运行时，使用新的 `work_dir`。

## YAML 配置

工作流文件包含顶层配置和 `nodes` 任务列表：

```yaml
workflow: demo
max_parallel: 2
max_rollbacks: 1          # 可选，默认 1
system_prompt: "统一要求" # 可选

nodes:
  - id: implement
    task_type: normal
    title: 实现功能
    goal:
      - 完成功能实现
    approach:
      - 先实现代码，再运行测试
    procedure:
      - 检查测试结果和生成文件 # 可选，仅提供给 verifier
    acceptance:
      - 测试全部通过
    out_of_scope:
      - 不修改无关模块
    depends_on: []
    executor: general-executor
    verifier: general-verifier
    max_retries: 1
    on_exhaust: exit
```

### 顶层字段

- `workflow`：工作流名称。
- `max_parallel`：允许同时执行或验证的普通任务数，必须是大于等于 1 的整数；所有层级共用此限制。
- `max_rollbacks`：允许的最大回滚次数，可选，默认值为 1。
- `system_prompt`：可选的统一提示词。
- `nodes`：任务节点列表，不能为空。

### 普通任务字段

`task_type: normal` 任务使用以下字段：

- `id`：节点唯一名称；其他节点通过它填写依赖。
- `title`：任务标题。
- `goal`：任务目标列表。
- `approach`：执行建议列表。
- `procedure`：可选的验证步骤列表，只提供给 verifier。
- `acceptance`：验收标准列表。
- `out_of_scope`：明确不做的内容列表。
- `depends_on`：依赖的节点 id；没有依赖时填 `[]`。
- `executor`：执行阶段使用的 agent 名称。
- `verifier`：验证阶段使用的 agent 名称。
- `max_retries`：验证失败后的重试次数，必须大于等于 0。
- `on_exhaust`：重试耗尽后的处理方式：`exit`、`continue` 或 `rollback`。
- `rollback_to`：仅当 `on_exhaust: rollback` 时填写，指向同一节点集合中的传递上游普通任务。
- `require_approval`：可选。设为 `true` 时，任务验证通过后还需人工批准；也可填写非空字符串列表，列出审批时需要核对的事项。审批人可以批准、驳回重做并提供意见，或判定失败并按 `on_exhaust` 处理。默认不需要审批。请在运行前确定是否启用审批；运行中修改此设置不会影响已初始化的任务，但可以修改审批提示内容。

待审批期间，编排器每 1 秒回到调度器检查审批信箱，包括仍有其他执行或验证任务运行的情况。批准、驳回重做或终裁失败均可及时生效；批准后的下游任务仍按 `max_parallel` 限制派发，无需等待独立长任务完成。

### 子图任务字段

子图用于动态生成一组任务，固定使用四个字段：

```yaml
- id: run-details
  task_type: subgraph
  file: details/workflow.yaml
  depends_on:
    - implement
```

`file` 指向另一个仅包含顶层 `nodes` 的 YAML 文件，可以填写绝对路径或相对于 `work_dir` 的路径。子图文件可以同时包含普通任务和嵌套子图；子图节点不填写 `executor`、`verifier`、`max_retries` 或 `on_exhaust`。主工作流也可以只包含子图。

例如，`details/workflow.yaml` 可以继续引用下一层子图：

```yaml
nodes:
  - id: checks
    task_type: subgraph
    file: details/checks.yaml
    depends_on: []
```

在 `details/checks.yaml` 的 `nodes` 中定义普通任务 `verify-result`，其完整任务 ID 就是 `run-details/checks/verify-result`。查看日志或审批该任务时，使用这个完整 ID。

- 每一层 `file` 都相对于同一个 `work_dir`，不是相对于所在 YAML 文件的目录。
- 每一层的 `depends_on` 和 `rollback_to` 都引用当前文件 `nodes` 中的局部 ID；`rollback_to` 仍须指向传递上游的普通任务。
- 子图文件可以提前准备，也可以由上游任务生成；必须在子图依赖全部通过、即将开始执行前准备好。恢复运行时，请保留尚未完成的子图文件。
- 子图内的所有任务（包括嵌套子图中的任务）通过后，才会执行依赖该子图的下游任务。
- 任务配置 `on_exhaust: continue` 时，重试耗尽会跳过该任务及其依赖者，独立分支继续执行。若子图最终包含被跳过的任务，依赖该子图的下游任务也会被跳过。
- 不同子图节点可以复用同一个文件，各自独立执行。不要沿嵌套路径循环引用同一文件，包括通过符号链接引用。

### 配置规则

- 节点 `id` 在同一节点集合中必须唯一，不能包含 `/`。
- `depends_on` 不能形成循环，引用的节点必须存在。
- 每个列表字段至少包含一项非空字符串。
- `rollback_to` 必须指向传递上游节点；不使用回滚时不要填写。
- 未知字段或缺少必填字段都会导致工作流校验失败。
