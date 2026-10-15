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

"""Read-only validation of an Agent-created Git baseline; emit the checked asset snapshot as JSON."""

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

SHEETS = ("blackbox", "whitebox", "tdd")
IGNORED = {".git", "__pycache__", "testcase_output", ".pytest_cache"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    files = {}
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED for part in path.relative_to(root).parts):
            continue
        if path.is_symlink():
            raise ValueError(f"baseline does not follow symlinks: {path}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = digest(path)
    return files


def committed_files(check, commit):
    committed = {}
    for entry in check.git("ls-tree", "-rz", commit, binary=True).split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, blob = metadata.split()
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            raise ValueError("baseline must contain regular files only")
        committed[name.decode("utf-8")] = hashlib.sha256(
            check.git("show", blob.decode("ascii"), binary=True)
        ).hexdigest()
    return committed


class BaselineCheck:
    def __init__(self, work):
        self.work = Path(work).resolve()
        spec = yaml.safe_load((self.work / "design/doc/spec.yaml").read_text())
        self.op = spec["op"]["name"]
        if not isinstance(self.op, str) or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", self.op
        ):
            raise ValueError("spec.op.name must be a Python identifier")
        self.operator = self.work / "operators" / self.op
        if self.operator.resolve() != self.operator:
            raise ValueError("operator work tree must not traverse a symlink")
        self.test = self.operator / "test"
        self.root = self.work / "review-fix"

    @staticmethod
    def results(folder, baseline):
        statuses = []
        for sheet in SHEETS:
            path = folder / sheet / f"verify_result_{sheet}.csv"
            if not path.is_file():
                return "UNVERIFIED"
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            ids = [row["case_id"] for row in rows]
            invalid_ids = len(ids) != len(set(ids)) or set(ids) != set(
                baseline["cases"][sheet]
            )
            invalid_context = any(
                row["sheet"] != sheet or row["device"] != baseline["device"]
                for row in rows
            )
            invalid_status = any(
                row["status"] not in {"passed", "failed"} for row in rows
            )
            if invalid_ids or invalid_context or invalid_status:
                return "UNVERIFIED"
            statuses.extend(row["status"] for row in rows)
        return "PASS" if all(status == "passed" for status in statuses) else "FAIL"

    def git(self, *args, binary=False):
        if args[0] not in {"rev-parse", "ls-tree", "show"}:
            raise ValueError("baseline checker only permits read-only Git commands")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        result = subprocess.run(
            [
                shutil.which("git") or "/usr/bin/git",
                f"--git-dir={self.root / 'git'}",
                f"--work-tree={self.operator}",
                *args,
            ],
            cwd=self.operator,
            env=env,
            capture_output=True,
            text=not binary,
            check=True,
        )
        return result.stdout if binary else result.stdout.strip()

    def cases(self):
        with (self.test / "testcase.csv").open(
            encoding="utf-8-sig", newline=""
        ) as stream:
            rows = list(csv.DictReader(stream))
        keys = [(r["sheet"], r["case_id"]) for r in rows]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate case IDs")
        cases = {
            sheet: [
                r["case_id"]
                for r in rows
                if r["sheet"] == sheet and r["status"] == "active"
            ]
            for sheet in SHEETS
        }
        if not all(cases.values()):
            raise ValueError("all three logical sheets must be nonempty")
        return cases

    def baseline(self):
        files = inventory(self.operator)
        if f"{self.op}.py" not in files:
            raise ValueError("missing public operator module")
        commit = self.git("rev-parse", "--verify", "baseline^{commit}")
        committed = committed_files(self, commit)
        if committed != files:
            raise ValueError(
                "baseline commit does not match all current source and test assets"
            )
        result_root = self.test / "testcase_output"
        with (result_root / "blackbox/verify_result_blackbox.csv").open(
            encoding="utf-8-sig", newline=""
        ) as stream:
            devices = {r["device"] for r in csv.DictReader(stream)}
        if len(devices) != 1 or next(iter(devices)).split(":")[0] == "cpu":
            raise ValueError("baseline requires one real accelerator device")
        baseline = {
            "commit": commit,
            "cases": self.cases(),
            "device": next(iter(devices)),
            "operator_files": files,
            "inputs": {},
            "runtime": {
                "module": f"operators.{self.op}.{self.op}",
                "entry": os.environ.get("CANNBOTDSL_OP_ENTRY", "run"),
                "error_matcher": os.environ.get("CANNBOTDSL_ERROR_MATCHER", ""),
            },
        }
        if self.results(result_root, baseline) != "PASS":
            raise ValueError("baseline full-case evidence is incomplete or failed")
        for directory in ("design/doc", "design/units", "environment", "precision"):
            root = self.work / directory
            for name, sha in inventory(root).items():
                baseline["inputs"][f"{directory}/{name}"] = sha
        for name in (
            "precision/execution.yaml",
            "precision/execution.log",
            "precision/precision-report.md",
        ):
            if name not in baseline["inputs"]:
                raise ValueError(f"missing baseline evidence: {name}")
        return baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("baseline",))
    parser.add_argument("--work-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        snapshot = BaselineCheck(args.work_dir).baseline()
    except (
        OSError,
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        yaml.YAMLError,
    ) as error:
        parser.error(str(error))
    logger = logging.getLogger("review_fix")
    logger.addHandler(logging.StreamHandler(sys.stdout))
    logger.setLevel(logging.INFO)
    logger.info(json.dumps(snapshot, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
