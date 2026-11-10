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

"""Run a frozen functional case against an isolated candidate's original entry."""

import argparse
import hashlib
import importlib
import json
import logging
import os
from pathlib import Path
import runpy
import sys


def validate_frozen_assets(root, runner, mapping):
    for name, expected in mapping["assets"].items():
        if not name.startswith("functional/") or name == "functional/cases.csv":
            continue
        relative = Path(name).relative_to("functional")
        asset = (runner.parent / relative).resolve(strict=True)
        if not asset.is_relative_to(root):
            raise ValueError("test asset escapes candidate root")
        if hashlib.sha256(asset.read_bytes()).hexdigest() != expected:
            raise ValueError(f"candidate changed frozen test asset: {relative}")


def isolate_imports(root, runner, mapping):
    original = Path(mapping["casebook"]["path"]).parents[3].resolve()
    os.chdir(root)
    search_paths = []
    for item in sys.path:
        if not item:
            continue
        resolved = Path(item).resolve()
        if resolved.is_relative_to(original) or resolved.is_relative_to(root):
            continue
        search_paths.append(item)
    sys.path[:] = [str(root), str(runner.parent), *search_paths]
    os.environ["PYTHONPATH"] = str(root)


def execute(root, mapping_path, case_id, entry, device, error_matcher=None):
    root = root.resolve(strict=True)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    selected = [case for case in mapping["cases"] if case["case_id"] == case_id]
    if len(selected) != 1:
        raise ValueError("case_id must identify exactly one frozen case")
    runner = (root / mapping["runner_relative"]).resolve(strict=True)
    if not runner.is_relative_to(root):
        raise ValueError("runner escapes candidate root")
    validate_frozen_assets(root, runner, mapping)
    isolate_imports(root, runner, mapping)
    if ":" in entry:
        entry_module, entry = entry.split(":", 1)
        if entry_module != mapping["module"]:
            raise ValueError("entry module differs from frozen operator identity")
    os.environ["CANNBOTDSL_OP_MODULE"] = mapping["module"]
    os.environ["CANNBOTDSL_OP_ENTRY"] = entry
    os.environ.pop("CANNBOTDSL_ERROR_MATCHER", None)
    if error_matcher:
        matcher = importlib.import_module(error_matcher)
        if not Path(matcher.__file__).resolve(strict=True).is_relative_to(root):
            raise ValueError("error matcher import escaped candidate root")
        os.environ["CANNBOTDSL_ERROR_MATCHER"] = error_matcher
    module = importlib.import_module(mapping["module"])
    loaded = Path(module.__file__).resolve(strict=True)
    if not loaded.is_relative_to(root):
        raise ValueError("operator import escaped candidate root")
    if not callable(getattr(module, entry, None)):
        raise ValueError("candidate public entry is not callable")
    identity = {
        "candidate_root": str(root),
        "module_path": str(loaded),
        "source_sha256": hashlib.sha256(loaded.read_bytes()).hexdigest(),
        "case_id": case_id,
    }
    evidence = logging.Logger("dsl_performance.candidate", level=logging.INFO)
    evidence.addHandler(logging.StreamHandler(sys.stdout))
    evidence.info("%s", json.dumps(identity))
    arguments = list(selected[0]["arguments"])
    arguments[arguments.index("--device") + 1] = device
    sys.argv = [str(runner), *arguments]
    runpy.run_path(str(runner), run_name="__main__")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--execution-map", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--entry", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--error-matcher")
    args = parser.parse_args()
    try:
        execute(
            args.candidate_root,
            args.execution_map,
            args.case_id,
            args.entry,
            args.device,
            args.error_matcher,
        )
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
