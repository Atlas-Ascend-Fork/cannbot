# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

"""prepare_case 黑盒测试共享 fixture：脚本路径与带 front matter 的 relu 需求文本。"""

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
PREPARE_SCRIPT = SCRIPTS / "prepare_case.py"

REQUIRE_CONTENT = """\
---
schema_version: 1
op_name: relu
---

# relu 算子需求规格

## 算子语义

out[i] = max(x[i], 0)

## 输入输出规格

输入 input0: shape=[1024], dtype=float32; 输出 output0 同输入。

## 精度要求

rtol=1e-3, atol=1e-3
"""
