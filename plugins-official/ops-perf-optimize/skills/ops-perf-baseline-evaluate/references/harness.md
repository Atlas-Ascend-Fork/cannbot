# 构建入口与 harness 协议

本参考定义 run worktree 内原实现构建的入口选择、runner/harness 规则与构建看门狗（基线评估在 worktree 上构建原实现时适用）。核心原则（A1）：**主体代码存放位置与修改永远留在 git 仓（worktree）内**；仓外只放 harness（runner、打包骨架、采集入口）。

## 1. 构建入口选择（只读探测）

对 worktree 做只读探测（`git_workspace.py probe --code-dir <dir> --out <json>` 提供 `build_entry_hints`）：

| 探测结果 | 入口 | 说明 |
|---|---|---|
| 仓库提供单算子构建/打包入口（`build.sh --ops=<op>` 类、`--pkg` 单算子 target、README/CI 证据） | **repo-native** | 优先路径；必须使用其本地安装选项装到 run 工作区产物目录，禁止系统级安装 |
| 仓库无单算子入口（ops-xxx 之外的研究仓、裸目录） | **sdk-scaffold**（注册输入）/ **direct-harness**（直调输入） | 见第 3 节 |

无论哪种入口，**打包安装严格限定单算子**，并对编译/打包命令设置时长上限看门狗（默认 1800 秒，超时 kill 并报错），防止误触发全仓构建。

## 2. runner/harness 规则

- **注册输入**：runner 通过注册入口执行（aclnn / 框架注册入口），不直接 launch kernel；一般算子补持久 `msprof application` runner；MC²/多 rank 加载 `ascendc-mc2-best-practice` 并沿用 `msprof op` harness。
- **直调输入**：保留原 host launch、参数打包、workspace、stream 和 kernel 入口，不套注册工程、不更换 launch ABI；已有独立 demo 可复制为 harness 并验证。
- harness 不得修改 kernel、Tiling、launch ABI 或功能入口；只做工程接线适配，逐项记录必要差异。

## 3. 无单算子打包入口的仓库（sdk-scaffold / direct-harness）

沿用现行处理方式，叠加 git 原生约束：

1. **注册输入**：脚手架取自目标机本次 CANN 安装的自带模板（两套家族：`tools/op_project_templates/ascendc/customize/`（cmake/config.cmake + opbuild + presets）与 `tools/new_op_project_template/custom_op/`（`find_package(ASC)` + `npu_op_*`）），先只读探测确认家族再实例化；不得沿用旧文档参数或编造命令。
2. **直调输入**：现场搭建最小可运行 harness，保留原 launch ABI。
3. **staging 衔接规则（A1 硬约束）**：骨架/harness 消费的算子源**来自 git worktree**；构建期生成的 staging 副本（骨架要求的目录重排、拷贝等）是**构建派生产物**，记录来源 commit，**禁止在 staging 区直接修改代码**——发现任何修改需求必须回到 worktree 实施后重建。staging 信息记入 workspace-manifest 的 `build.staging` 字段。
4. msprof application 持久 runner、TTK 环境校验与 CSV 转换统一加载 TTK 标准 skill（`ttk-how-run-test` / `ttk-how-write-case` / `ttk-how-write-plugin`）。**TTK 必须从 TTK 安装根目录运行**（`cd /path/to/ops-test-kit && python3 -m ttk ...`）：warmup kernel 编译产物写入 CWD 相对 `kernel_meta/`，而校验读 TTK 根的 `kernel_meta/`，从其他目录运行必然报 `Compile warmup kernel failed`。用绝对路径引用用例 CSV 和输出文件。

## 3.5 构建执行纪律与解释器绑定

- **解释器绑定**：构建/采集脚本必须使用 preflight 登记冻结的 Python 可执行文件（manifest `environments.python`），并在构建证据中记录实际调用的解释器绝对路径与 SHA；预检报告之外的解释器（如系统 `/usr/bin/python3`）出现即身份缺口，先对齐再构建，不得在构建期临时排障装包。

## 4. 构建与加载身份

- 在 worktree（基线 commit 检出）上以真实构建入口构建；构建命令、构建产物与实际加载产物记入 workspace-manifest 与执行身份证据。
- 证明实际加载的是本次构建产物而非系统同名算子：核对加载库绝对路径、SHA、vendor 搜索路径与调用入口；内置同名算子歧义先解决并取证加载顺序。
- 编译、安装到 run 工作区自定义产物目录；不覆盖 SDK/系统 OPP；共享 CANN SDK 只读。
