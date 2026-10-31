#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

"""Run an editable ordinary model with a full case and an optional split plan."""

import argparse
import json
import logging
from pathlib import Path
import sys

import yaml

from accel_model.app.case.native_case import run_native_case

RESULT_KEYS = (
    "total_cycles",
    "main_cycles",
    "reduce_cycles",
    "overhead_cycles",
)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path, help="YAML containing a split mapping")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory for each run")
    shape = yaml.safe_load(args.case.read_text())
    strategy = yaml.safe_load(args.plan.read_text())["split"] if args.plan else None
    result = run_native_case(
        args.model,
        shape,
        output_dir=args.output,
        strategy=strategy,
        derive=True,
        export_trace=True,
    )
    summary = {}
    for key in RESULT_KEYS:
        summary[key] = result[key]
    logging.info("%s", json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
