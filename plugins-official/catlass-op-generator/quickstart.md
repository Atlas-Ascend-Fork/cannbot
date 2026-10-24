# CATLASS 算子生成快速开始

通过 CANNBot 安装 `catlass-op-generator`。安装器从 cannbot-skills 的 `ops/` 接入六个 `catlass-cpp-*` Skills，并从 cannbot-knowledge 提供 `knowledge/ops/catlass/`；项目中不生成私有知识副本。

工作区根目录应有 CATLASS 源码 `catlass/include`、`catlass/examples` 和目标算子的 `operators/`。先确定算子的数学语义和目标架构，再使用 `catlass-cpp-interface` 初始化工程：

```bash
bash <installed-catlass-cpp-interface>/scripts/init_operator_project.sh my_operator
bash <installed-catlass-cpp-interface>/scripts/init_operator_project.sh my_attention --algorithm-family flash_attention
```

不指定家族时使用 `general`。初始化后依次完成 interface、reference、design、implementation、validation；每次继续前校验 `operators/<name>/docs/workflow.json`。设计阶段通过 `catlass-cpp-knowledge` 查询 `guides/` 与目标家族的 Operator 卡，按返回的完整路径读取正文。
