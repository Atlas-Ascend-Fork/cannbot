#!/usr/bin/env python3
# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------

"""Generate a CSV guide from workflow template filenames and use_when metadata."""

import argparse
import csv
import logging
import sys
from pathlib import Path

import yaml

from assemble_workflow import load_yaml, template_use_when

LOGGER = logging.getLogger(__name__)


def workflow_entries(root, labels=None):
    """Scan templates under root; label files relative to labels, defaulting to root."""
    if not root.is_dir():
        raise ValueError(f"workflow directory not found: {root}")
    labels = root if labels is None else labels
    entries = []
    for path in sorted(root.rglob("*")):
        if (
            not path.is_file()
            or path.suffix not in {".yaml", ".yml"}
            or path.name.endswith(".graph-preview.yaml")
        ):
            continue
        try:
            use_when = template_use_when(load_yaml(path))
        except (ValueError, yaml.YAMLError) as error:
            raise ValueError(f"{path}: {error}") from error
        entries.append(
            {"file": path.relative_to(labels).as_posix(), "use_when": use_when}
        )
    if not entries:
        raise ValueError("no workflow templates found")
    return entries


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "orchestrations/workflows",
        help="template root; defaults to the plugin orchestrations/workflows directory",
    )
    parser.add_argument(
        "--language",
        choices=("ascendc", "cannbot-dsl"),
        help="development language; scans only workflows/<language>",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="CSV guide path in the current work directory",
    )
    args = parser.parse_args()
    try:
        root = args.workflows_dir.resolve()
        output = args.output.resolve()
        if output.is_relative_to(root):
            raise ValueError(
                "write the guide in the work directory, outside the shared workflow templates"
            )
        entries = workflow_entries(
            root / args.language if args.language else root, labels=root
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["file", "use_when"])
            writer.writeheader()
            writer.writerows(entries)
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.error(str(error))
    LOGGER.info("%s (%s templates)", output, len(entries))


if __name__ == "__main__":
    main()
