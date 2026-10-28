# ascend-call-generation-cv 参考示例

本目录收录 Cube+Vector（CV）融合算子的 AscendC 工程脚手架样例，供本 skill 生成
pybind / CMake / host 代码时对照。CV 工程与纯 Vector 工程的差别在于需要 workspace
分配、AIC+AIV 双核派发，以及 Catlass 头文件引用。

每个算子子目录包含一组样例文件：

- `<op>_custom.py` — 算子的 Python 调用封装
- `<op>.cpp` — pybind 桥接代码
- `<op>_project.json` — `gen_project_cv.py` 使用的工程配置

已收录算子：`matmul_gelu/`（matmul + 激活）、`rms_matmul_scale/`（归一化 + matmul + 缩放）、
`quant_matmul/`（int8 量化 matmul 含反量化）。
