---
schema_version: 1
artifact: ENVIRONMENT
engine: "{AICPU|CCU}"
owner: hcclbot
task_id: "{task_id}"
status: "{PASS|FAIL|BLOCKED}"
source_identity: "{目标仓源码身份}"
checks_pass: "{true|false}"
created_at: "{ISO-8601 时间}"
---

# 环境检查报告

**算子**：{op_type}　**状态**：{PASS|FAIL|BLOCKED}

## 字段语义

| 字段 | 值 | 说明 |
|------|-----|------|
| HCCL_ROOT | | HCCL 源码路径（需含 src/ops/） |
| HCOMM_DOCS | | HCOMM 文档路径（需含 comm_op_dev_guide/） |
| CANN_HOME | | CANN Toolkit 安装路径 |
| src/ops 目录 | | src/ops/ 是否存在（标准算子开发目录） |
| build.sh | | HCCL 仓 build.sh 是否存在（编译入口） |

## 检查结果

### HCCL 源码检查

```
（粘贴 hccl-env-check skill 的检查输出）
```

### CANN 环境检查

```
（粘贴 CANN 环境检查输出）
```

## 结论与证据

- 全部检查通过：`status=PASS`。
- 任一错误：`status=FAIL`，列出失败命令、真实退出码和原始输出。
- 权限、网络或外部依赖不可用：`status=BLOCKED`，列出阻塞证据和所需输入。

本文件由 HCCLBot 写入；环境状态不为 PASS 时不得推进后续阶段。
