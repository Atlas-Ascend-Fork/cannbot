# 安装与环境

默认安装兼容当前 Python 和平台的最新 OpModel 包，包括预发布版本。
Python 范围以包声明的 `Requires-Python` 为准，操作系统、架构和 ABI 支持
以发布的 wheel 标签为准。下面使用 Linux shell；运行前核对已安装包的实际接口。
软件仿真无需 NPU 或 C/C++ 编译器。

## 安装完整 skill

从 cannbot-skills 取得整个 `ops/ops-opmodel-toolkit/` 目录，复制到客户端支持的
技能目录，保留 `SKILL.md`、`references/`、`scripts/`、`assets/` 等子目录。
例如可复制到用户算子项目的 `.agents/skills/ops-opmodel-toolkit/`；使用其他技能
目录的客户端按其目录约定安装。已有目标目录时先比较用户改动。

客户端发现 skill 后，通过 `ops-opmodel-toolkit` 同名入口调用；也可以要求代理
读取本目录的 `SKILL.md`。Python 包需另外安装，pip 不会安装这些文档和示例。

`ops-perf-optimize` 的 `init.sh` 会在 Skill 安装成功后自动准备一个项目专用的
OpModel 虚拟环境，安装兼容的最新 `opmodel` 预发布 wheel，并验证 Python 模块与
`opmodel-assets` 入口。默认位置为
`<项目>/.cannbot/dependencies/ops-perf-optimize/opmodel-venv`，生成的环境文件为
`<项目>/.cannbot/opmodel.env`。在项目根目录执行以下命令即可加载
`OPMODEL_SKILL_DIR`、`OPMODEL_PYTHON` 和 `OPMODEL_WORKSPACE`：

```bash
source .cannbot/opmodel.env
python -c "from importlib.metadata import version; print(version('opmodel'))"
opmodel-assets list
```

可用 `CANNBOT_OPMODEL_PYTHON` 指定创建虚拟环境的 Python，使用
`CANNBOT_OPMODEL_WHEELHOUSE=/path/to/wheelhouse` 从离线目录安装，或用
`CANNBOT_OPMODEL_VENV=/path/to/venv` 指定环境目录。`CANNBOT_SKIP_OPMODEL_INSTALL=1`
跳过自动安装；默认安装失败只告警，不阻断主插件安装，设置
`CANNBOT_OPMODEL_STRICT=1` 可让 `init.sh` 在失败时退出。

## 设置资料路径和用户项目

代理从本次读取的 `SKILL.md` 定位 skill 的绝对目录，设置 `OPMODEL_SKILL_DIR`。
下面示例假设 skill 安装在当前用户项目的 `.agents/skills/`；安装在其他位置时，
将第一行替换为真实的绝对路径。后续所有命令从用户项目目录执行，勿在 skill
目录内创建模型、虚拟环境或结果。

```bash
export OPMODEL_SKILL_DIR="$PWD/.agents/skills/ops-opmodel-toolkit"
test -f "$OPMODEL_SKILL_DIR/SKILL.md"
export OPMODEL_WORKSPACE="$PWD/work"
mkdir -p "$OPMODEL_WORKSPACE"
```

完整 case 输出不能位于系统 `/tmp` 下；搜索会话必须位于 `OPMODEL_WORKSPACE`
的子目录。相对的 `work/` 均指当前用户项目中的目录。每次实验使用新的输出目录。

## 联网安装 wheel

以下命令适用于不使用插件自动安装、需要手工准备环境的场景。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade --pre --index-url https://pypi.org/simple opmodel
python -c "from importlib.metadata import version; print(version('opmodel'))"
opmodel-assets list
```

`python3` 须为受支持的版本，可改用 `python3.12` 等解释器。缺少 `venv/ensurepip`
时使用包含 venv 的解释器或补齐系统对应支持。新终端重新激活环境并设置上述路径。
`--upgrade` 会检查并升级已有安装，`--pre` 将开发版和其他预发布版本纳入选择；
pip 根据环境兼容性与依赖约束选择版本，说明见 [pip 安装文档](https://pip.pypa.io/en/stable/cli/pip_install/#pre-release-versions)。
运行依赖由 pip 按包声明安装。保存命令输出中的实际版本，便于复现和排查问题。

教程使用随 skill 提供的 `assets/examples/matmul/`，见[快速入门](quickstart.md)。
也可以用 `opmodel-assets export --output models` 向尚不存在的目录导出模型、
hooks 和硬件资源。仅编辑用户副本，安装包和 skill 目录均可只读。

## 离线安装

在与目标 Python/平台相同的联网环境中，下载当前兼容的最新 OpModel wheel 及其依赖：

```bash
python -m pip download --pre --index-url https://pypi.org/simple --only-binary=:all: \
  --dest wheelhouse opmodel
```

将完整 skill 和 `wheelhouse` 复制到离线机器，创建并激活对应 Python 环境，设置
上述路径后安装。pip 从本地目录选择兼容版本；该目录中的包版本以下载时为准。

```bash
python -m pip install --upgrade --pre --no-index --find-links wheelhouse opmodel
python -c "from importlib.metadata import version; print(version('opmodel'))"
```

## 保存本次环境以便复现（可选）

完成项目验证后，在该项目专用的虚拟环境中记录实际安装的包及依赖，并下载对应
wheel。记录文件和 wheelhouse 保存在用户项目中，由本次环境生成。

```bash
python -m pip freeze > requirements-opmodel.txt
python -m pip download --index-url https://pypi.org/simple --only-binary=:all: \
  -r requirements-opmodel.txt --dest wheelhouse-repro
```

将记录文件、wheelhouse 和项目输入一同保留。需要复现时，在相同 Python/平台的
机器上创建并激活新的虚拟环境，再安装保存的包：

```bash
python -m pip install --no-index --find-links wheelhouse-repro --only-binary=:all: \
  -r requirements-opmodel.txt
python -c "from importlib.metadata import version; print(version('opmodel'))"
```

环境记录只对应本次验证；后续升级后重新运行项目检查并保存新的记录。
安装后进入[快速入门](quickstart.md)。
