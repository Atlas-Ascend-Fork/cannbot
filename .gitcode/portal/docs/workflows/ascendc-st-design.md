# 算子系统测试

`ascendc-st-design` 是算子工作流使用的公共 Skill。给它 aclnn 接口文档、输入范围和约束，可以为同一接口设计 L0、L1、L2 三级黑盒用例。

## 准备工作区

在目标工程安装[注册算子开发](/docs/workflows/ops-registry-invoke.html)或[算子性能调优](/docs/workflows/ops-perf-optimize.html)工作流，按对应快速入门启动客户端。准备待测试的接口签名、支持的数据类型和形状、精度判据，以及可以对照的参考实现。

## 提交测试需求

以 Add 为例，可在客户端中输入：

```text
使用 ascendc-st-design，读取工作区内 Add 的 aclnn 接口文档。
先列出两个输入的 dtype、shape 和广播约束。用 L0 验证典型输入能跑通，
用 L1 覆盖文档支持的类型和广播组合，用 L2 覆盖不可广播的形状和不支持的类型。
给出每个用例的预期结果，并标明需在设备上执行的用例。
```

## 检查结果

先检查 L0 的输入和参考输出是否能在目标环境复现，再运行 L1 的参数组合。对 L2 逐个确认无效输入按预期被拒绝。在注册算子工作流中，测试记录按 `*_l0_functional.csv`、`*_l1_functional.csv` 和 `*_l2_exception.csv` 分别交付。运行后可把失败用例、输入和实际输出一起交回客户端定位。

完整的执行与判定规则见[注册算子黑盒验收说明](https://gitcode.com/cann/cannbot/blob/master/plugins-official/ops-registry-invoke/skills/blackbox-tester/SKILL.md)。
