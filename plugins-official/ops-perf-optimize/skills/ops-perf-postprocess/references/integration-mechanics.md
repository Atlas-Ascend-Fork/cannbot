# 回写机制：新增模板 + 路由（register-invoke / APT）

面向含 DAV_35xx 的 register-invoke（APT 模板）算子工程。目标：把已验证 target kernel 作为**代际隔离的新模板**挂进去，并让 host tiling 只在**已验证 SoC + 优势场景**把 TilingKey 指向它。四处联动：**SoC/架构隔离**、**模板参数声明**、**kernel 入口分派**、**host 路由 + 新 TilingData**。（对应 `writeback.md` Stage B。）

## 0. 先判定是否必须代际隔离

本参考只展开 APT 注册接线。所有工程都先按 `$PLUGIN_ROOT/workflows/references/source-isolation.md` 复制共享实现并冻结最小修改范围；以下 SoC 检查不能替代同代未涉及模板的保护。工作输入已是自定义注册工程，按 `extraction-manifest.json` 回映原工程，不重新转换调用方式。

先分别取证，不要混为一谈：

| 集合 | 来源 | 含义 |
|---|---|---|
| `TARGET_SOCS` | `run-manifest.json` | 本次完成构建、功能、性能验证的代际 |
| `SUPPORTED_SOCS` | 目标工程 build config、`SocVersion`、架构目录、kernel 入口 | 原工程承诺支持的代际 |

若 `SUPPORTED_SOCS - TARGET_SOCS` 非空，目标实现不得覆盖共享路径。先观察同仓其他算子的既有风格，再选择同一种隔离轴：

1. 已有 `arch35/`、`v35/` 等目录：target kernel/tiling 数据结构放同代目录，共享入口只增加编译期/运行期接线；
2. host 已用 `SocVersion`：在进入 A5 专用 UB/核数/VF 模型前分流，非 target 调用原 legacy 函数；
3. 已有 TilingKey/模板轴：增加 target 专用 key/轴，未命中 target guard 时保持原 key；
4. build config 按 SoC 分源：沿用 config，不另造平行机制。

合格 diff 必须同时证明：target 路由可达、每个非目标 SoC 仍落到 legacy fallback、原公开接口/约束/dtype 零差异。典型不合格形态是“新 kernel 放在 `arch35/`，但公共 tiling 的 UB 模型已经被 A5 版本整体替换”——kernel 文件隔离不能抵消 host 共享逻辑污染。

`integration-safety-scope.json` 最小结构：

```json
{
  "schema_version": 2,
  "target_socs": ["Ascend950"],
  "verified_socs": ["Ascend950"],
  "supported_socs": [
    {"name": "Ascend910B", "evidence": ["op_host/config/ascend910b/op.json"]},
    {"name": "Ascend950", "evidence": ["op_host/tiling.cpp:42"]}
  ],
  "project_isolation_style": {
    "kind": "soc-version-route+arch-directory",
    "target_path_markers": ["arch35", "ascend950"],
    "target_route_tokens": ["ASCEND950", "__NPU_ARCH__ == 3510"],
    "evidence": ["op_kernel/peer/arch35/kernel.h:1"]
  },
  "shared_file_routes": {
    "op_host/tiling.cpp": {
      "target_guard": ["op_host/tiling.cpp:120"],
      "non_target_fallback": ["op_host/tiling.cpp:128"]
    }
  }
}
```

`supported_socs` 和项目风格证据相对 baseline root；双路由证据相对 candidate root。baseline/candidate 必须是同一份完整算子注册树的集成前后副本，不能用带其他脏改动的工作树。安全脚本会自动找出所有改动的共享 `op_host`/`op_kernel` 源文件，漏填任一文件即失败。

scope 不是自报免责：脚本会忽略注释并扫描 baseline 中所有 `AICore().AddConfig("...")`，扫描有结果时 `supported_socs` 必须与之精确一致；每条支持证据的路径或内容也必须出现对应 SoC。每个 `target_guard`/`non_target_fallback` 必须指向它所解释的那个共享变更文件，且每个变更 hunk 必须紧邻包含 route token 的 guard 证据；不能拿其他文件或同文件无关分支充数。自动扫描不适用于非 `AddConfig` 工程时，仍须人工从 build config、`SocVersion` 和架构目录交叉审阅完整性，并把结论写入兼容矩阵。运行门禁还必须传 `--isolation-scope <source-isolation-integration.json>`，检查冻结的完整文件/行范围；guard 邻近和路径命名本身不证明控制流安全。

## 1. 模板参数轴 / TilingKey（`op_kernel/<arch>/*_struct.h`）

注册工程用 `ASCENDC_TPL_*` 声明"模板参数轴"，每个取值组合对应一个编译出来的 kernel 特化，host 用 `SetTilingKey(GET_TPL_TILING_KEY(...))` 选。原始通常只有一个轴（如按 rank 分 `RANK_4/RANK_8`）：

```cpp
#define XLOG1PY_RANK_4 4
#define XLOG1PY_RANK_8 8
ASCENDC_TPL_ARGS_DECL(Xlog1py,
    ASCENDC_TPL_UINT_DECL(RANK, 8, ASCENDC_TPL_UI_LIST, XLOG1PY_RANK_4, XLOG1PY_RANK_8));
ASCENDC_TPL_SEL(
    ASCENDC_TPL_ARGS_SEL(ASCENDC_TPL_UINT_SEL(RANK, ASCENDC_TPL_UI_LIST, XLOG1PY_RANK_4)),
    ASCENDC_TPL_ARGS_SEL(ASCENDC_TPL_UINT_SEL(RANK, ASCENDC_TPL_UI_LIST, XLOG1PY_RANK_8)));
```

**加新模板的两种做法：**

- **做法 A（加一个取值，最省事）**：在同一个轴上多加一个不与现值冲突的取值当"优化路径"标记，并在 `TPL_SEL` 里补一条选择。例：
  ```cpp
  #define XLOG1PY_BRC 100          // 优化路径，避开 4/8
  ASCENDC_TPL_UINT_DECL(RANK, 8, ASCENDC_TPL_UI_LIST, XLOG1PY_RANK_4, XLOG1PY_RANK_8, XLOG1PY_BRC)
  // TPL_SEL 里补：ASCENDC_TPL_ARGS_SEL(ASCENDC_TPL_UINT_SEL(RANK, ASCENDC_TPL_UI_LIST, XLOG1PY_BRC))
  ```
  优点：改动最小、门槛低。缺点：把"优化标记"塞进语义是 RANK 的轴里略脏；新路径若自己还要按 rank 分，得在 TilingData 里带 rank。
- **做法 B（加一个正交轴，语义更干净）**：新增一个 `IMPL`/`OPT` 轴（`ORIG=0`/`OPT=1`），与原 `RANK` 轴组合。kernel 入口按两个轴分派。改动多一点但语义清晰、可扩展。

在已经完成 SoC guard 的 target 分支内，优先做法 A（联动点少、不易漏 `TPL_SEL`）。无论哪种，**`TPL_SEL` 必须和 `TPL_ARGS_DECL` 的取值一一对应**，漏一条就编译/选核出错；不得用新增模板值绕过代际 guard。

## 2. kernel 入口分派（`op_kernel/*_apt.cpp`）

入口是模板函数，按模板参数分派到不同 kernel 类：

```cpp
template<int RANK> __global__ __aicore__ void xlog1py(GM_ADDR x, GM_ADDR y, GM_ADDR z,
                                                      GM_ADDR workspace, GM_ADDR tiling) {
    GM_ADDR ins[2] = {x, y}; GM_ADDR outs[1] = {z};
    REGISTER_NONE_TILING; KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_AIV_ONLY);
    if constexpr (RANK == 4) { GET_TILING_DATA_WITH_STRUCT(TilingData4, td, tiling);
        Xlog1pyKernel<DTYPE_X,4> k; k.Init(ins,outs,&td); k.Process(); }
    else if constexpr (RANK == 8) { /* ... TilingData8 ... */ }
    // 新增：
    else /* RANK==XLOG1PY_BRC */ {
        GET_TILING_DATA_WITH_STRUCT(Xlog1pyBrcTilingData, td, tiling);   // 新 TilingData 结构
        Xlog1pyBrcKernel<DTYPE_X> k; k.Init(ins, outs, &td); k.Process();
    }
}
```

要点：
- `DTYPE_X` 是注册框架注入的输入 dtype 宏——**新 kernel 用它做模板实参，别自己判 dtype**。
- 新路径用**自己的 TilingData 结构**（`GET_TILING_DATA_WITH_STRUCT` 换成新结构）。
- 新 kernel 类要提供 `Init(ins, outs, &td)` / `Process()` 同样的接口形态。

## 3. 自定义注册工程 → 原注册工程的映射

两侧均为注册调用，不引入直调桥接。以 `extraction-manifest.json` 区分原源码、工程接线适配和新增优化副本：

- **入口**：保留已验证注册入口和 launch ABI；剥离时的生成器/include 路径适配按映射回接，不能重写计算主体。
- **TilingData**：优化副本的新结构与 host/kernel 一起移植，保持字段顺序、类型、对齐与 TilingKey 对应关系。
- **dtype/cast**：保留已验收的模板实参和 cast 链，不借机扩大原声明支持类型。
- **公共库**：新增优化依赖只复制到目标私有目录，不能覆盖原公共文件；名称变化仅为必要的冲突适配，并记录对照。
- **计算主体**：逐行对照最终归档；回写后通过原注册入口执行规定的功能回归。

## 4. host 路由 + 新 TilingData 填充（`op_host/<arch>/*_tiling*.cpp`）

原 `RunTiling` 形如"取 shape/dtype → 按 rank 选 TilingKey → 填 TilingData"。多代共用时先判目标 SoC，再在 target 分支判优势场景：

```cpp
ge::graphStatus Xlog1pyTiling::RunTiling() {
    GetShapeInfo();                              // 已有：拿 raw shapes、dtype、broadcast 后 rank
    if (socVersion_ == SocVersion::ASCEND950 &&
        ShouldUseOptPath(/* y/out shapes, numel, dtype */)) {
        FillBrcTilingData();                     // 新增：对应已验收工作工程的 tiling 填充
        ctx_->SetTilingKey(GET_TPL_TILING_KEY(XLOG1PY_BRC));
        return GRAPH_SUCCESS;
    }
    // 其他 shape 或任何非 target SoC：维持原路径，原封不动
    ...
}
```

- `FillBrcTilingData()` 把最终工作工程的 tiling 计算（PickBroadcastMode / TryOneDim / 多核切分 / UB 切分 / strides）**照搬**过来，填进新 TilingData。
  - **这是“桶 A”：逐行移植、禁止重写**，包括每一处守卫和分支边界（例如 `PickBroadcastMode` 的 `!lastAxisBrc` 守卫）。只做必要且有映射依据的类型适配；注册接口验收失败时先对照回写版与已验收版路由，不先修改 kernel。
- **别忘 workspace**：`TilingFuncXxx` 里的 `GetWorkspaceSizes` 要覆盖新路径需求。

## 5. 路由谓词的保真

原样保留最终归档中已验收的谓词、字段来源、阈值、优先级和 fallback。性能报告只用于交叉核对，不在回写阶段重新推导阈值或收紧路由。原工程无法提供等价的 tiling 阶段数据时上报主 Agent，不能按 case ID/CSV 行号分派或自行设计替代算法。

## 6. 编译与常见坑

- `op_api/`、op def/proto、infer shape、API 适配头是公开契约面；性能回集成中 SHA 必须不变。不得新增 dtype、放宽 shape/attr 检查或改变参数顺序。
- 编译是**长任务**：放后台或设超时，别前台死等。
- `TPL_SEL` 与 `TPL_ARGS_DECL` 取值必须一一对应（漏条 → 选不到核）。
- 新 TilingData 结构 host/kernel 两侧定义必须一致（字段顺序、类型、对齐）。
- 新 kernel 头文件加算子前缀，避免和原 kernel 的类型/宏重名。
- **kernel 源文件名/符号前缀须与 OpType 一致**（某些构建按 OpType 定位 kernel 源）——否则 kernel 二进制不编译、运行时报 `561000`（`ParseDynamicKernels` 找不到）。改名验证法改 OpType 时，文件名一并对齐。
- `GET_TILING_DATA_WITH_STRUCT` 的结构类型要和 host 实际 `SetTilingKey` 的分支匹配。
- 尾轴广播、对齐、Cast 等是功能验收高发区——用 TTK 标准 skill（`ttk-how-diagnose`）+ `ascendc-precision-debug` 定位。
- **OpType 与 CANN 内置算子同名**（`opp/built-in/.../ops_legacy/<optype>`）：vendor 部署时 aclnn 可能解析到内置 kernel，症状是 TTK aclnn 全 `NO_OUTPUT`/AIcore 崩。Stage B 先做只读早检，再按下文命名四位一致规则建立验证副本；不能依赖环境变量绕过。

## 7. 构建成可部署 vendor 包（Stage B 的关键一步）

Stage B 的"编译通过"编出的是算子仓内部 `.so`；TTK aclnn 要的是**部署到 `opp/vendors/` 的 vendor 包**。**必须用算子仓自带的打包工具链，禁止自己拼 CMake/staging/部署脚本**。

- **先发现工具链**：不同算子仓不一样（`build.sh --pkg` / `Makefile` / `msopgen` / README 里的打包命令…）。先在仓库根 `build.sh --help`、看 README/CI，找到打包入口再用。
- **构建与部署范围**：只使用该版本工具链实际支持的单算子目标和本地安装选项。共享 SDK/系统 OPP 不可写；必要清理先解析并核实本次受管 build/vendor 的精确路径，不用通配符删除共享部署。不支持工作区安装时上报环境约束，不自行改系统配置。
- **可选快速上板 smoke**：算子自带例子可以快速确认部署链，但不能替代冻结功能验收子集的完整执行。

## 8. 改名验证法的「命名四位一致」约束与 staging 陷阱

> 改名验证法有个易踩的坑：**「就地只给 OpType 加后缀」在 ops-math 类工程会打不出包**。根因是打包工具链对命名有一条**四位一致**硬约束，改名必须四处一起改。

**约束**：ops-math 打包工具强制
```
optype_snake(OpType) == 算子目录 basename == opFile 去掉 _apt == __global__ 入口函数名
```
四者必须完全一致。因为：`kernel_src_copy` 把 kernel 源 staging 到 `build/tbe/ascendc/<目录basename>/`，而生成的 opc `.py` 按 `build/tbe/ascendc/<optype_snake(OpType)>/` 去**找** cce 源。

**失败特征**（就地只改了 OpType、没改目录名时）：
```
[ERROR] input cce file is not exists, file name:
  .../build/tbe/ascendc/<optype_snake>/<op>_apt.cpp
[ERROR] Opc tool compile failed → build kernel FAILED → gmake Error 2
```
例：目录仍 `cdist`、OpType 改成 `CdistCustom` → opc 找 `.../cdist_custom/cdist_apt.cpp`，但 staging 写的是 `.../cdist/` → 文件不存在。**注意 host 全量编译能到 100%，卡的是最后 kernel opc 阶段**，别被"编到 100%"误导。

**正确做法 = 用完全对齐的同级副本目录验证，不就地改交付目录的 OpType**：
1. 复制出一个**独立同级算子目录** `<op>_custom/`，四位一起改：目录 basename=`<op>_custom`、OpType=`<Op>Custom`、opFile=`<op>_custom_apt.cpp`、入口 `__global__` 函数=`<op>_custom`，config json / op_def / proto / aclnn 一并对齐。在这个副本上打包、部署并跑注册接口功能验收子集。
2. **交付目录 `<op>/` 的 OpType 全程保持原名**（优化就地集成在其中），**无需 OpType 往返改回**——省掉"还原 OpType"这步的风险；交付态用 `build.sh --pkg --ops=<op>` 重编确认通过即可。
3. 验证完**删除临时副本 `<op>_custom/`**（它只是验证载体，别混进交付/PR）。

**副本与真算子共存时的 op_api 链接冲突**（副本进了聚合 `libcust_opapi.so` 会 ODR 撞）：
- 把副本 op_api 的 `ACLNNTYPE` 设回 `aclnn_exclude` + 手写 `aclnn_<op>.cpp`，避免 autogen 与手写的 `aclnn<Op>Custom` 重复定义；
- 把 `l0op::<Op>` 改名 `l0op::<Op>Custom`、给 `InferShape*` 内部链接（`static`/匿名 ns）、include guard 唯一化，避免和真算子在聚合 `.so` 里 ODR 冲突。

> 一句话：**改名验证法 ≠ 只改 OpType 字符串**。ops-math 类工程要么四位一起改（且最省心是造对齐的同级副本目录去验证），要么根本打不出包。
