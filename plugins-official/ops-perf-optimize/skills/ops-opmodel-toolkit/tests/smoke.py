# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

"""Run the shipped documentation against an installed wheel in a new user project.

Usage: python tests/smoke.py --work /absolute/new-directory-outside-tmp
Runs offline with the installed OpModel package; no compiler or device is required.
"""

import argparse
import importlib
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import traceback
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def _check_markdown_link(path, target):
    if "://" in target or target.startswith("mailto:"):
        return 0
    location, separator, anchor = target.partition("#")
    destination = (path.parent / unquote(location)).resolve() if location else path
    if not destination.is_relative_to(ROOT) or not destination.exists():
        raise AssertionError((str(path.relative_to(ROOT)), target))
    if separator and destination.suffix == ".md":
        headings = re.findall(r"^#+ (.+)$", destination.read_text(), re.M)
        anchors = [
            re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
            for heading in headings
        ]
        if unquote(anchor) not in anchors:
            raise AssertionError(
                (str(path.relative_to(ROOT)), target, "missing anchor")
            )
    return 1


def check_links():
    count = 0
    for path in ROOT.rglob("*.md"):
        for target in re.findall(r"\]\(([^\s)]+)\)", path.read_text()):
            count += _check_markdown_link(path, target)
    return dict(local_links=count)


def check_identity():
    installed_version = version("opmodel")
    locations = {}
    for name in ("accel_model", "operators", "hardware"):
        locations[name] = list(importlib.import_module(name).__path__)
        if not all(
            Path(p).resolve().is_relative_to(Path(sys.prefix).resolve())
            for p in locations[name]
        ):
            raise AssertionError(
                (name, "must load from the active environment", locations[name])
            )
    return dict(
        installed_version=installed_version,
        origins=locations,
        dependencies={n: version(n) for n in ("opmodel", "simpy", "PyYAML", "numpy")},
    )


def check_physical(result):
    required = (
        "capacity",
        "assignment_coverage",
        "region_coverage",
        "quantity",
        "runtime",
        "backend_agreement",
    )
    statuses = {name: result["validation"][name]["status"] for name in required}
    if not result["passed"] or any(status != "passed" for status in statuses.values()):
        raise AssertionError(statuses)
    if result["validation"]["assignment_coverage"]["tasks"] != 9:
        raise AssertionError("Expected 3 Cube and 6 AIV tasks in the physical example")
    if result["device_experiment"] or result["model_calibrated"]:
        raise AssertionError(
            "Synthetic example must not claim device or calibrated results"
        )
    return statuses


def _prepare_project(parser, args):
    project = args.work.resolve()
    if (
        project.is_relative_to("/tmp")
        or project.is_relative_to(ROOT)
        or ROOT.is_relative_to(project)
    ):
        parser.error("Choose a separate new user project outside /tmp and the skill")
    project.mkdir(parents=True, exist_ok=False)
    logs = project / "logs"
    logs.mkdir()
    (project / "work").mkdir()
    return project, logs


def _make_environment(project):
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "OPMODEL"))
    }
    env.update(
        PATH=str(Path(sys.executable).parent) + ":/usr/bin:/bin",
        OPMODEL_SKILL_DIR=str(ROOT),
        OPMODEL_WORKSPACE=str(project / "work"),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONNOUSERSITE="1",
    )
    return env


def _command_runner(project, logs, env):
    def command(name, argv):
        result = subprocess.run(
            argv, cwd=project, env=env, capture_output=True, text=True, timeout=180
        )
        (logs / (name + ".log")).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise AssertionError(
                f"{name}: exit {result.returncode}; see {logs / (name + '.log')}"
            )
        return result
    return command


def _document_runner(command):
    def document(relative, select=lambda block: True):
        blocks = re.findall(
            r"^```bash\n(.*?)^```", (ROOT / relative).read_text(), re.M | re.S
        )
        blocks = [block for block in blocks if select(block)]
        if not blocks:
            raise AssertionError(f"No executable examples in {relative}")
        name = relative.replace("/", "-").replace(".md", "")
        for index, block in enumerate(blocks):
            command(f"{name}-{index}", ["/bin/bash", "-euo", "pipefail", "-c", block])
        return dict(executed_blocks=len(blocks))
    return document


def _outcomes(project):
    def outcomes():
        def load(rel):
            return json.loads((project / rel).read_text())

        baseline = load("work/baseline/result.json")
        split = load("work/with_split/result.json")
        tile = load("work/tile64/result.json")
        joint = load("work/joint_reevaluated/result.json")
        for result in (baseline, split, tile, joint):
            if result["total_cycles"] <= 0:
                raise AssertionError("Invalid full-case cycles")
        if baseline["summary"]["active_cores"] != 4:
            raise AssertionError(
                "Tutorial has four output tasks; expected four active cores"
            )
        search = load("work/joint_search/search.json")
        if not search["rows"] or not search["coverage"]["complete"]:
            raise AssertionError("Declared joint-search space was not covered")
        physical = check_physical(load("work/physical/result.json"))
        return dict(
            baseline_cycles=baseline["total_cycles"],
            split_cycles=split["total_cycles"],
            tile_cycles=tile["total_cycles"],
            joint_cycles=joint["total_cycles"],
            joint_coverage=search["coverage"],
            physical_checks=physical,
        )
    return outcomes


def _write_report(project, report):
    (project / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )


def _run_checks(project, checks):
    report = dict(status="running", checks=[])
    for name, function in checks:
        start = time.monotonic()
        try:
            details = function()
            row = dict(name=name, status="passed", details=details)
        except Exception:
            row = dict(name=name, status="failed", error=traceback.format_exc())
        row["seconds"] = round(time.monotonic() - start, 3)
        report["checks"].append(row)
        logging.info("%s %s", name, row["status"])
        if row["status"] == "failed":
            report["status"] = "failed"
            _write_report(project, report)
            logging.error("%s", row["error"])
            return 1
        _write_report(project, report)

    report["status"] = "passed"
    _write_report(project, report)
    logging.info("Report: %s", project / "report.json")
    return 0


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work", type=Path, required=True, help="New project directory, outside /tmp"
    )
    args = parser.parse_args()
    project, logs = _prepare_project(parser, args)
    command = _command_runner(project, logs, _make_environment(project))
    document = _document_runner(command)

    checks = [
        ("links", check_links),
        ("installed-wheel", check_identity),
        ("quickstart", lambda: document("references/quickstart.md")),
        (
            "dag-and-reevaluation",
            lambda: document(
                "references/optimization.md",
                lambda b: "app.cli.dag_run" in b or "case_tile64" in b,
            ),
        ),
        ("hardware-override", lambda: document("references/hardware.md")),
        ("physical", lambda: document("assets/examples/physical/README.md")),
        (
            "joint-search-and-session",
            lambda: document("references/joint-optimization/wheel-commands.md"),
        ),
        ("outcomes", _outcomes(project)),
    ]
    return _run_checks(project, checks)


if __name__ == "__main__":
    raise SystemExit(main())
