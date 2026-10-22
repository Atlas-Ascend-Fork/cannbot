#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""按列名合并 ascendc-st-design 的标准 L0/L1/L2 CSV。"""

import argparse
import ast
import csv
import logging
import sys
from pathlib import Path

LOG = logging.getLogger(__name__)


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def offset_leaf(value, case_name):
    """Accept TTK's scalar form and the public Skill's temporary ``(n,)`` form."""
    if value is None or is_int(value):
        return value
    if isinstance(value, (tuple, list)) and len(value) == 1 and is_int(value[0]):
        return value[0]
    raise ValueError(
        f"{case_name}: tensor_view_offsets leaf must be None, int or a singleton int tuple, got {value!r}"
    )


def is_tensor_list_shape(value):
    # A normal Tensor shape is a tuple of dimensions.  A TensorList slot is a
    # tuple of shape tuples (including scalar shapes ``()``).
    return (
        bool(value)
        and isinstance(value, (tuple, list))
        and all(item is None or isinstance(item, (tuple, list)) for item in value)
    )


def normalize_view_offsets(row):
    """Adapt public-case offsets to the TTK ACLNN field contract.

    The public generator currently serializes a Tensor offset as ``(n,)`` at
    each top-level tensor slot, producing ``((n,), (m,))``.  TTK expects one
    integer per Tensor, while a TensorList keeps one tuple of integer offsets.
    Normalize only that representation mismatch and reject ambiguous data.
    """
    raw = (row.get("tensor_view_offsets") or "").strip()
    if not raw:
        return
    case_name = row.get("testcase_name") or row.get("case_name") or "<unknown>"
    try:
        shapes = ast.literal_eval(row.get("tensor_view_shapes") or "")
        offsets = ast.literal_eval(raw)
    except (SyntaxError, ValueError) as exc:
        raise ValueError(
            f"{case_name}: invalid non-contiguous tensor fields: {exc}"
        ) from exc
    if not isinstance(shapes, (tuple, list)) or not isinstance(offsets, (tuple, list)):
        raise ValueError(f"{case_name}: tensor_view_shapes/offsets must be tuple-like")
    if len(shapes) != len(offsets):
        raise ValueError(
            f"{case_name}: tensor_view_offsets count {len(offsets)} != tensor count {len(shapes)}"
        )

    normalized = []
    for shape, offset in zip(shapes, offsets):
        if is_tensor_list_shape(shape):
            if not isinstance(offset, (tuple, list)) or len(offset) != len(shape):
                raise ValueError(
                    f"{case_name}: TensorList offset count does not match its tensor count"
                )
            normalized.append(tuple(offset_leaf(item, case_name) for item in offset))
        else:
            normalized.append(offset_leaf(offset, case_name))
    row["tensor_view_offsets"] = repr(tuple(normalized))


def _append_rows(path, headers, rows, names):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"{path}: missing CSV header")
        for field in reader.fieldnames:
            if field not in headers:
                headers.append(field)
        for row in reader:
            name = row.get("testcase_name") or row.get("case_name")
            if not name:
                raise ValueError(f"{path}: testcase_name is empty")
            if name in names:
                raise ValueError(f"duplicate testcase_name: {name}")
            normalize_view_offsets(row)
            names.add(name)
            rows.append(row)


def read_files(files):
    headers, rows, names = [], [], set()
    for path in files:
        _append_rows(path, headers, rows, names)
    return headers, rows


def write_file(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def merge(testcases_dir, positive_out, negative_out):
    root = Path(testcases_dir)
    positive_files = sorted(root.glob("*_l0_functional.csv")) + sorted(
        root.glob("*_l1_functional.csv")
    )
    negative_files = sorted(root.glob("*_l2_exception.csv"))
    if not positive_files:
        raise ValueError(f"no canonical L0/L1 CSVs under {root}")
    positive_headers, positive_rows = read_files(positive_files)
    if not positive_rows:
        raise ValueError("canonical L0/L1 CSVs contain no cases")
    # Validate the complete input cohort before replacing either output.
    # A malformed L2 file must not leave new positives paired with stale L2.
    negative_count = 0
    negative_path = Path(negative_out)
    if negative_files:
        negative_headers, negative_rows = read_files(negative_files)
        negative_count = len(negative_rows)
    write_file(Path(positive_out), positive_headers, positive_rows)
    if negative_files:
        write_file(negative_path, negative_headers, negative_rows)
    elif negative_path.exists():
        negative_path.unlink()
    return len(positive_rows), negative_count


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("testcases_dir")
    parser.add_argument("--positive-out", required=True)
    parser.add_argument("--negative-out", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    positive, negative = merge(args.testcases_dir, args.positive_out, args.negative_out)
    LOG.info("positive(L0/L1)=%d cases", positive)
    LOG.info("negative(L2)=%d cases", negative)
    return 0


if __name__ == "__main__":
    sys.exit(main())
