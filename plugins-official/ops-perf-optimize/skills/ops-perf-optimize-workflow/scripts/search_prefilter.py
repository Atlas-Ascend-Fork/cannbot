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

"""Run the OpModel L1 prefilter and record coverage/budget/evidence.

The adapter does not rank device candidates. It invokes an installed opmodel
search command, records stdout/stderr and output-file SHA, and writes a
`prefilter.l1` fragment. A missing wheel or failed search is recorded as
`unsupported` with the concrete reason; it never fabricates model coverage.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path


from validate_schedule_contract import ref as reference


def build_command(backend, model, out_dir, extra):
    return [
        sys.executable,
        "-m",
        f"accel_model.app.cli.{backend}",
        str(Path(model).resolve()),
        "--out",
        str(Path(out_dir).resolve()),
        *extra,
    ]


def _output_evidence(out_dir, result_path):
    evidence = []
    for path in sorted(Path(out_dir).rglob("*")):
        if path.is_file() and path.resolve() != Path(result_path).resolve():
            evidence.append(reference(path))
    return evidence


def run_prefilter(
    frontier, *, backend, model, out_dir, extra=(), command=None, timeout=600
):
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "opmodel-prefilter.json"
    if command:
        argv = shlex.split(command.format(out=out_dir))
    else:
        if backend not in ("dag_run", "graph_search", "agent_search"):
            raise ValueError("backend must be dag_run, graph_search or agent_search")
        if not model:
            raise ValueError("--model is required when --command is absent")
        argv = build_command(backend, model, out_dir, extra)
    record = {
        "schema_version": 1,
        "backend": backend,
        "tool": "ops-opmodel-toolkit",
        "command": argv,
    }
    try:
        completed = subprocess.run(
            argv,
            cwd=out_dir,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        record.update(
            {
                "status": "unsupported",
                "reason": f"command not found: {error.filename}",
                "coverage": 0,
                "budget_skipped": 0,
                "evidence": [],
            }
        )
        result_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return record
    except subprocess.TimeoutExpired as error:
        record.update(
            {
                "status": "unsupported",
                "reason": f"opmodel search timed out after {timeout}s",
                "coverage": 0,
                "budget_skipped": 0,
                "evidence": [],
                "timeout_seconds": timeout,
                "stdout": (error.stdout or "")[-4000:],
                "stderr": (error.stderr or "")[-4000:],
            }
        )
        result_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return record
    (out_dir / "opmodel.stdout.log").write_text(completed.stdout, encoding="utf-8")
    (out_dir / "opmodel.stderr.log").write_text(completed.stderr, encoding="utf-8")
    evidence = _output_evidence(out_dir, result_path)
    if completed.returncode == 0:
        record.update(
            {
                "status": "applied",
                "coverage": len(frontier.get("nodes", [])),
                "budget_skipped": 0,
                "evidence": evidence,
                "returncode": 0,
            }
        )
    else:
        record.update(
            {
                "status": "unsupported",
                "reason": f"opmodel search exited with {completed.returncode}",
                "coverage": 0,
                "budget_skipped": 0,
                "evidence": evidence,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        )
    result_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontier", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--backend",
        choices=("dag_run", "graph_search", "agent_search"),
        default="dag_run",
    )
    parser.add_argument("--arg", action="append", default=[])
    parser.add_argument(
        "--command",
        help="override command; {out} expands to --out-dir (for tests or custom wrappers)",
    )
    parser.add_argument("--timeout", type=int, default=600)
    return parser.parse_args()


def main():
    args = parse_args()
    frontier = json.loads(args.frontier.read_text(encoding="utf-8"))
    record = run_prefilter(
        frontier,
        backend=args.backend,
        model=args.model,
        out_dir=args.out_dir,
        extra=args.arg,
        command=args.command,
        timeout=args.timeout,
    )
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
