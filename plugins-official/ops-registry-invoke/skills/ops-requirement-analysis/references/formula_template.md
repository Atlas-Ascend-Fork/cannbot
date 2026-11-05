# CANN 算子公式推导模板（AscendC kernel → LaTeX）

`formula.md` 的编写规则：从既有 CANN kernel 的 Compute 方法直接提取数学公式（不走 TensorFlow 映射），
让 A5 需求的数学语义锚定 A2/A3 旧代际实现，而非仅凭论文/竞品推断。

## 一、AscendC 指令→数学运算映射

| AscendC 指令 | 数学运算 | AscendC 指令 | 数学运算 |
| :----------- | :------- | :----------- | :------- |
| `Abs(x)` | $\|x\|$ | `Min/Max(x, y)` | $\min/\max(x, y)$ |
| `Muls(x, c)` | $c \cdot x$ | `Mins/Maxs(x, c)` | $\min/\max(x, c)$ |
| `Adds(x, c)` | $x + c$ | `Exp(x)` | $e^x$ |
| `Add/Sub(x, y)` | $x \pm y$ | `Log(x)` | $\ln(x)$ |
| `Mul/Div(x, y)` | $x \cdot y$、$x / y$ | `Sqrt(x)` | $\sqrt{x}$ |
| `Cast(x, dtype)` | 类型转换（影响精度） | `Reciprocal(x)` | $1/x$ |

## 二、推导步骤

1. **定位 Compute 方法**（`op_kernel/*.h` 的 `Compute(`），这是核心计算逻辑
2. **逐条翻译指令**（按上表），识别数值稳定性处理（减 max 防 exp 溢出、epsilon 防除零、Cast 前提升精度）
3. **确定边界条件**：空 tensor、单元素、各 dtype 分支
4. **编写 LaTeX 公式**，每个步骤标注源码 `文件:行号`

## 三、CANN 特有注意

- **多 dtype 分支**：FP32/FP16/BF16 常有不同实现路径（如 BF16 不支持 `Abs`/`Div` 需近似替代），
  formula.md 必须**分别列出**，禁止合并略过。
- **常量系数**：magic number 多为数学常量近似（如 $1/\sqrt{2}\approx0.7071$）、经验值或泰勒系数，
  逐个标注 `op_kernel/{op}_kernel.h:{行号}`。
- **指令链记法**：关键代码写为 `` `指令1(参数)` → `指令2(参数)` `` 的数据流序列。

## 四、报告结构

1. 核心公式（LaTeX）
2. 常量系数表：符号 | 值 | 说明 | 来源（文件:行号）
3. 数值稳定性：逐项标来源
4. 源码位置关联表：公式步骤 | 源码位置 | 指令链
5. 多 dtype 分支说明（有则必列）
6. python 小算子参考实现：与接口语义一致的 golden 表达式或小算子拼接约定（优先竞品接口；
   无竞品算子时用 PyTorch/TF 小算子拼接，禁 numpy），保证与竞品接口调用结果一致；
   用于后续 golden 实现与需求侧公式互证。
