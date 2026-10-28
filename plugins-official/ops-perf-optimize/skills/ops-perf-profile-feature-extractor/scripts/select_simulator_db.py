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

"""Inspect simulator SQLite records and link explicitly selected, nonempty DBs."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from cli_output import emit


def inspect_db(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        tables = set()
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            tables.add(row[0])
        count = None
        if 'ExecutedInstructions' in tables:
            count = conn.execute('SELECT COUNT(*) FROM ExecutedInstructions').fetchone()[0]
        info = None
        if 'KernelInfo' in tables:
            info = conn.execute('SELECT * FROM KernelInfo').fetchall()
    return dict(file=path.name, executed_instructions=count, kernel_info=info)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--select', action='append', default=[],
                        help='Exact DB basename; repeat for a known target sequence')
    parser.add_argument('--output', type=Path,
                        help='New directory containing only symlinks to selected DBs')
    args = parser.parse_args()
    if bool(args.select) != bool(args.output):
        parser.error('--select and --output must be supplied together')
    paths = sorted(args.record.glob('*.db'))
    if not paths:
        parser.error('No .db records found in the specified directory')
    inventory = {p.name: inspect_db(p) for p in paths}
    emit(json.dumps(list(inventory.values()), ensure_ascii=False, indent=2))
    if not args.select:
        return
    for name in args.select:
        if name not in inventory:
            parser.error(f'Unknown DB basename: {name}')
        count = inventory[name]['executed_instructions']
        if count is None or count <= 0:
            parser.error(f'{name}: no ExecutedInstructions; cannot report an empty DB')
    # A fresh directory prevents accidental inclusion of an earlier target.
    args.output.mkdir(parents=True, exist_ok=False)
    for name in dict.fromkeys(args.select):
        (args.output / name).symlink_to((args.record / name).resolve())
    emit(f'Selected records: {args.output.resolve()}')


if __name__ == '__main__':
    main()
