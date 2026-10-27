# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License).
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Shared exact npu-smi CLI table texts for the 910B4/910C layout fixtures."""

from __future__ import annotations

# 910B4 host: id+Name share one cell (no '|' between), one chip per NPU.
# Card 5 is busy (util 96 + process).
NPU_SMI_910B4_SINGLE_CELL = """\
+------------------------------------------------------------------------------------------------+
| npu-smi 25.5.2                   Version: 25.5.2                                               |
+---------------------------+---------------+----------------------------------------------------+
| NPU   Name                | Health        | Power(W)    Temp(C)           Hugepages-Usage(page)|
| Chip                      | Bus-Id        | AICore(%)   Memory-Usage(MB)  HBM-Usage(MB)        |
+===========================+===============+====================================================+
| 0     910B4               | OK            | 90.2        43                0    / 0             |
| 0                         | 0000:C1:00.0  | 0           0    / 0          30246/ 32768         |
+===========================+===============+====================================================+
| 3     910B4               | OK            | 87.0        42                0    / 0             |
| 3                         | 0000:02:00.0  | 4           0    / 0          13337/ 32768         |
+===========================+===============+====================================================+
| 5     910B4               | OK            | 94.1        43                0    / 0             |
| 5                         | 0000:41:00.0  | 96          0    / 0          26842/ 32768         |
+===========================+===============+====================================================+
| NPU     Chip              | Process id    | Process name             | Process Memory(MB)      |
+===========================+===============+====================================================+
| No running processes found in NPU 0                                                            |
+===========================+===============+====================================================+
| No running processes found in NPU 3                                                            |
+===========================+===============+====================================================+
| 5                         | 12345         | python                    | 26000                 |
+===========================+===============+====================================================+
"""

# 910C host: id+Name share one cell and each NPU spans TWO chip rows (one
# Name header + one Bus-Id data row per chip). NPU 1 has chip0 at 88% and
# chip1 idle — the NPU must report the busiest chip.
NPU_SMI_910C_MULTICHIP = """\
+------------------------------------------------------------------------------------------------+
| npu-smi 25.5.1                   Version: 25.5.1                                               |
+---------------------------+---------------+----------------------------------------------------+
| NPU   Name                | Health        | Power(W)    Temp(C)           Hugepages-Usage(page)|
| Chip  Phy-ID              | Bus-Id        | AICore(%)   Memory-Usage(MB)  HBM-Usage(MB)        |
+===========================+===============+====================================================+
| 0     Ascend910           | OK            | 172.4       49                0    / 0             |
| 0     0                   | 0000:9D:00.0  | 0           0    / 0          3114 / 65536         |
+------------------------------------------------------------------------------------------------+
| 0     Ascend910           | OK            | -           49                0    / 0             |
| 1     1                   | 0000:9F:00.0  | 0           0    / 0          2889 / 65536         |
+===========================+===============+====================================================+
| 1     Ascend910           | OK            | 161.3       49                0    / 0             |
| 0     2                   | 0000:99:00.0  | 88          0    / 0          3123 / 65536         |
+------------------------------------------------------------------------------------------------+
| 1     Ascend910           | OK            | -           51                0    / 0             |
| 1     3                   | 0000:9B:00.0  | 0           0    / 0          2874 / 65536         |
+===========================+===============+====================================================+
| NPU     Chip              | Process id    | Process name             | Process Memory(MB)      |
+===========================+===============+====================================================+
| No running processes found in NPU 0                                                            |
+===========================+===============+====================================================+
| No running processes found in NPU 1                                                            |
+===========================+===============+====================================================+
"""
