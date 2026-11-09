# AutoResearch 插件快速开始

AutoResearch 按独立工作区安装，完整保留 `scripts/`、`src/`、`.claude/`、`.opencode/`、`ar_examples/` 与原有优化流程。需要 Node.js >= 20（安装器）和 Python >= 3.10（运行时）。当前支持 Claude Code、OpenCode 的项目级安装。

## 源码安装

在 cannbot 仓库根目录执行，目标建议使用一个独立目录：

```bash
bash plugins-community/autoresearch/init.sh project claude /path/to/project
cd /path/to/project
python -m pip install -e .
claude
```

使用 OpenCode 时，将 `claude` 替换为 `opencode`。此插件不引用共享 Skills，源码安装不需要初始化 `vendor/cannbot-skills` 或另行克隆技能仓。省略目标路径会使用 cannbot 仓库根目录，因工作区与源码重叠而拒绝安装，因此请始终显式传入独立目标目录。

## npm 安装

发布包含此插件的版本后，可直接使用统一安装器：

```bash
npx @cannbot-plugin/cannbot@latest install autoresearch --tool claude --target /path/to/project
cd /path/to/project
python -m pip install -e .
```

若当前发布版本尚未包含 `autoresearch`，请使用上面的源码安装。仅需要启动 HTTP worker 时，将依赖安装命令改为 `python -m pip install -e ".[worker]"`。PyTorch / torch_npu、CANN 和相应 DSL 编译器仍按目标设备单独准备。

## 安装行为

- `init.sh` 只委托统一安装器，安装清单由 `plugin-install.json` 声明。
- 运行时按原有路径逐文件复制，不移动工作流或重写命令；两个客户端适配目录均保留，供批跑脚本调用。
- 已有 `config.yaml`、`package.json`、`.gitignore` 和 `README.md` 保持不变。合并项目指令与 Claude hooks，不覆盖用户的其他配置，也不自动放宽权限。
- 同名运行时文件内容变化时，旧内容备份为 `.cannbot-backup`（后续冲突追加编号）；未变化文件不重复备份。任务状态目录不清理。
- 安装前拒绝源目标重叠、越界路径、符号链接及非法设置。旧版全局指导安装和其他客户端没有完整适配，不再宣称支持。
- 目标已有项目配置时，请确认 Python 依赖和 OpenCode 模块配置与该工作区兼容；推荐先在独立目录验证。

## 使用

安装后从目标项目根目录启动客户端，不要在插件源码目录运行任务。把 reference 和 seed kernel 放入 `workspace/`：

```text
/autoresearch --ref workspace/<op>_ref.py --kernel workspace/<op>_kernel.py --op-name <op> --devices 0
/autoresearch --resume
```

评测走远端 worker 时，用 `--worker-url host:port` 替代本地设备参数。所有运行态保留在目标项目：`workspace/`、`ar_tasks/`、`.session_tasks/`、`.task_dir_pointers/` 与 `config.yaml`。

完整流程、批处理与 worker 用法见 [AUTORESEARCH.md](AUTORESEARCH.md)。
