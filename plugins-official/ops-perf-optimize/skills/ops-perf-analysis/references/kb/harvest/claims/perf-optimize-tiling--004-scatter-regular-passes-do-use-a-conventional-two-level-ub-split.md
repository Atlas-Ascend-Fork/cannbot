# CARD 004 · Scatter's regular passes DO use a conventional two-level UB split

- **Quote** (`ops/ascendc-perf-optimize/references/tiling/scatter/fallback/tiling-flow.md:248-263`):
  ```
  `y = data` 的整块 clone 与半精度 cast 是**规则顺序流量，必须走 SIMD 的 MTE**（用 SIMT 标量循环实测慢一个数量级：某用例 **1565us → 89us**）。这部分是常规的两级切分：

  // clone：(numBlocks, blockLength, tileSize)
  numBlocks   = min(coreNum, ceil(totalLength / 1024));        // MIN_ELEMS_PER_CORE = 1024
  blockLength = ceil(totalLength / numBlocks);
  tileSize    = floor(ubSize / PIPELINE_DEPTH(2) / BUFFER_NUM(2) / 512) * 512;   // 512B 对齐

  两个工程简化：

  - **按定宽整型实例化，不按 dtype**：`uint16_t`（2 字节）/ `uint32_t`（4 字节），**int64 按 2× 元素数走 4 字节版本** ⇒ 5 种 dtype 只需两份实例
  - cast pass 用固定 `TILE = 16384` 元素，每核连续分片
  - `tileSize` **必须 512B 对齐**，否则 `DataCopyPad` 起址/长度不对齐
  ```
- **Guessed book**: 950. `Ascend950PR` is named for this family's thresholds
  (`scatter/fallback/tiling-flow.md:9`), so a promoted entry would carry `BOARD: 950PR`.
- **Guessed level**: L2 (memory hierarchy & residency) / L3 (data movement & layout).
- **Evidence class**: measured-unscoped — `1565us → 89us` (17.6×, re-derived) with no case identity.
- **Why a card and not an entry**: it qualifies 0157's headline claim ("scatter tiling does not tile
  UB") rather than standing alone — the *scatter* passes do not tile UB, and the clone/cast passes
  around them do, conventionally. 0157 §3 records that distinction; a separate entry would need the
  UB capacity (S3) and the `PIPELINE_DEPTH`/`BUFFER_NUM`/512 constants scoped before its §4 could size
  anything. Held as a card until S3 is answered.
- **OVERTURN sketch**: a scatter on Ascend950PR where the clone pass run as a SIMT scalar loop matches
  the SIMD MTE version — the order-of-magnitude claim would then not reproduce.
- **Cross-refs**: entries 0157, 0160, 0161; `harvest/standing/950-tiling.md` S3, S8.
