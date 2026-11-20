#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Compute explicitly evidenced roofline terms without implicit hardware peaks."""

import argparse
import json
from profile_report import roofline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-us", type=float, required=True)
    parser.add_argument("--bytes", type=float, dest="hbm_bytes")
    parser.add_argument("--flops", type=float)
    parser.add_argument("--peak-bw", type=float)
    parser.add_argument("--peak-flops", type=float)
    parser.add_argument(
        "--json", action="store_true", help="JSON is the default output format"
    )
    args = parser.parse_args()
    try:
        result = roofline(
            args.duration_us, args.hbm_bytes, args.flops, args.peak_bw, args.peak_flops
        )
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
