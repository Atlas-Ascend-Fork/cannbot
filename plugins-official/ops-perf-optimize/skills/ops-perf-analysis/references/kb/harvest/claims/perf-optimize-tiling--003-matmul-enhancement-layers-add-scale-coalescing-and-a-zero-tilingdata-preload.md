# CARD 003 · MatMul enhancement layers: Scale Coalescing adds fields, MTE2 Preload adds none

- **Quote** (`ops/ascendc-perf-optimize/references/tiling/matmul/fallback/tiling-fields.md:110-124`):
  ```
  ### 8.1 Scale 合并载入（增强层 1）

  | 字段 | 数值规则 | 改动类型 |
  |------|---------|---------|
  | `scaleL1BufferNum` | `[16, 8, 4, 2]` 之一 | **新增** |
  | `scaleBufferNum` | 固定 2 | **新增** |
  | `scaleKL1` | `scaleL1BufferNum × kL1` | **重赋值**（基线 = `min(A 侧, B 侧)`） |
  | `nBufferNum` | 可能从 4 回退到 2 | **可能改值**（L1 占用上升） |

  ### 8.2 MTE2 预加载（增强层 2）

  | 字段 | 数值规则 | 改动类型 |
  |------|---------|---------|
  | **所有 TilingData 数值字段** | 沿用上游分支 | **零改动** |
  | `enableMte2Preload` | true / false | **Kernel 调度标志**（不下发 TilingData） |
  ```
- **Guessed book**: 950. `arch35` at `matmul/fallback/tiling-flow.md:9` names a family, not a board.
- **Guessed level**: L6 (tiling & scheduling) / L3 (data movement & layout).
- **Evidence class**: bare. No measurement for either layer.
- **Why a card and not an entry**: the contrast is real and teachable — one enhancement changes the
  tiling data and can force `nBufferNum` down, the other changes nothing in the tiling data and is a
  pure kernel scheduling flag — but the `[16, 8, 4, 2]` ladder's selection formula lives in
  `scale_coalescing_tiling.md §2.2`, which is not in this tree (S6). An entry's §4 cannot be written
  against a fallback ladder whose rule is unreachable. 0116 carries the Scale geometry these fields
  sit on.
- **OVERTURN sketch**: an mxfp4 case on a named 950 board where enabling Scale Coalescing does not
  change `scaleKL1`, or where enabling MTE2 Preload changes any numeric TilingData field.
- **Cross-refs**: entries 0113, 0115, 0116; `harvest/standing/950-tiling.md` S6.
