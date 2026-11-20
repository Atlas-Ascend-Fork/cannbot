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

"""Execute a registered independent-capture plan; preserve every attempt."""

from __future__ import annotations

import argparse
import csv
import fcntl
import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path

from profile_evidence import (
    check_receipt,
    raw_sample,
    read,
    receipt,
    require,
    timestamp,
    validate_plan,
)
import report_contract


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False))
    temp.replace(path)


def sample_value(attempt, identity, plan):
    require(
        attempt.get("schema_version") == 1
        and attempt.get("status") == "valid"
        and attempt.get("returncode") == 0
        and all(
            attempt.get(key) == plan[key]
            for key in ("protocol", "physical_device", "logical_device", "environment")
        )
        and attempt["command"][0] == plan["tool"]["path"],
        "capture identity/protocol mismatch",
    )
    require(
        timestamp(attempt["started_at"]) <= timestamp(attempt["ended_at"]),
        "invalid capture time",
    )
    report_contract.check_command(attempt["command"], identity, plan)
    for key in ("run_log", "archive", "import_log", "summary"):
        check_receipt(attempt[key])
    report_contract.validate_publication(
        attempt,
        Path(attempt["archive"]["path"]),
        Path(attempt["summary"]["path"]),
        Path(attempt["run_log"]["path"]).read_text(errors="replace"),
        Path(attempt["import_log"]["path"]).read_text(errors="replace"),
        plan,
    )
    return raw_sample(Path(attempt["summary"]["path"]), identity, plan)


def reused_samples(plan):
    reuse = plan.get("reuse", {})
    require(
        isinstance(reuse, dict) and set(reuse) <= set(plan["identities"]),
        "invalid reuse variants",
    )
    samples, archives, pids = {}, set(), set()
    for variant, source in reuse.items():
        collection = read(check_receipt(source["collection"])["path"])
        previous = read(check_receipt(collection["plan"])["path"])
        require(
            collection.get("schema_version") == 1
            and collection.get("kind") == previous.get("kind") == plan["kind"]
            and previous["identities"][source["variant"]] == plan["identities"][variant]
            and all(
                previous.get(key) == plan.get(key)
                for key in (
                    "effect_case_id",
                    "soc",
                    "physical_device",
                    "logical_device",
                    "device_binding",
                    "tool",
                    "protocol",
                    "environment",
                    "snapshot",
                    "precision_policy",
                    "samples_per_variant",
                )
            )
            and previous.get("frequency_policy", "rated")
            == plan.get("frequency_policy", "rated")
            and previous.get("rated_frequency_mhz") == plan.get("rated_frequency_mhz"),
            "reused measurement identity/conditions differ",
        )
        rows = [
            row for row in collection["samples"] if row["variant"] == source["variant"]
        ]
        require(
            sorted(row["sample_index"] for row in rows)
            == list(range(plan["samples_per_variant"])),
            "reuse requires the complete side's samples",
        )
        for row in rows:
            attempts = row["attempts"]
            require(attempts, "reused sample has no attempts")
            for index, ref in enumerate(attempts):
                attempt = read(check_receipt(ref)["path"])
                require(
                    attempt["sample_index"] == row["sample_index"],
                    "reused sample index differs",
                )
                if index < len(attempts) - 1:
                    require(
                        attempt.get("status") == "failed",
                        "attempt follows a published capture",
                    )
                    log = Path(check_receipt(attempt["run_log"])["path"]).read_text(
                        errors="replace"
                    )
                    report_contract.validate_failure(attempt, log, previous)
            # Version names belong to the collection; the frozen execution
            # identity must match even after candidate -> baseline promotions.
            value, pid = sample_value(
                {**attempt, "variant": source["variant"]},
                previous["identities"][source["variant"]], previous,
            )
            archive = attempt["archive"]["path"]
            require(
                archive not in archives and pid not in pids,
                "reused capture duplicated across slots",
            )
            archives.add(archive)
            pids.add(pid)
            samples[variant, row["sample_index"]] = (
                {"attempts": attempts, "reused_from": source},
                value,
            )
    return samples


def collect(plan_path, registration_path, output, report_context=None):
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan, _ = validate_plan(plan_path)
    if report_context is None:
        report_context = plan.get("report_context")
    registration = read(registration_path)
    require(
        receipt(plan_path) in registration.get("artifacts", []),
        "register this plan before collecting",
    )
    require(
        timestamp(registration["issued_at"]) < timestamp(now()),
        "registration is not in the past",
    )
    reused = reused_samples(plan)
    output.mkdir(parents=True, exist_ok=True)
    rows, values = [], {v: [] for v in plan["identities"]}
    # Keep one plan's resumption from starting overlapping device captures.
    with (output / ".collector.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        binding = {
            "plan": receipt(plan_path),
            "registration": receipt(registration_path),
        }
        binding_path = output / "collection-binding.json"
        if binding_path.exists():
            require(
                read(binding_path) == binding,
                "collection belongs to another plan or registration",
            )
        else:
            require(
                not any(output.glob("sample-*/attempt-*")),
                "existing attempts have no plan binding; audit before resuming",
            )
            atomic(binding_path, binding)
        for slot in plan["order"]:
            reuse = reused.get((slot["variant"], slot["sample_index"]))
            folder = output / f"sample-{slot['slot']:02d}"
            folder.mkdir(exist_ok=True)
            attempts = []
            complete = None
            identity = plan["identities"][slot["variant"]]
            for directory in sorted(folder.glob("attempt-*")):
                require(reuse is None, "reused slot also has local captures")
                attempt_path = directory / "attempt.json"
                require(
                    attempt_path.is_file(),
                    f"retain/audit interrupted attempt before resuming: {directory}",
                )
                attempt = read(attempt_path)
                require(not complete, "attempt exists after a successful capture")
                require(
                    {k: attempt.get(k) for k in slot} == slot,
                    "existing attempt belongs to another slot",
                )
                check_receipt(attempt["run_log"])
                if attempt.get("status") == "needs_review":
                    check_receipt(plan["tool"])
                    recovery = (
                        directory
                        / f"recovery-{len(attempt.get('recovery_history', [])):02d}"
                    )
                    recovery.mkdir()
                    atomic(recovery / "attempt.json", attempt)
                    history = [
                        *attempt.get("recovery_history", []),
                        receipt(recovery / "attempt.json"),
                    ]
                    attempt = report_contract.recover_attempt(
                        plan, identity, attempt, recovery
                    )
                    attempt["recovery_history"] = history
                    atomic(attempt_path, attempt)
                if attempt.get("status") == "valid":
                    complete = attempt
                else:
                    require(
                        attempt.get("status") == "failed"
                        and not attempt.get("archive"),
                        f"published/ambiguous capture needs review, not resampling: {directory}",
                    )
                    report_contract.validate_failure(
                        attempt, Path(attempt["run_log"]["path"]).read_text(), plan
                    )
                attempts.append(receipt(attempt_path))
            if complete is None and reuse is None:
                for key, value in plan["environment"].items():
                    require(os.environ.get(key) == value, f"frozen environment changed: {key}")
                check_receipt(plan["tool"])
                attempt_dir = folder / f"attempt-{len(attempts):02d}"
                attempt_dir.mkdir()
                try:
                    attempt = report_contract.collect_attempt(
                        plan, identity, slot, attempt_dir, report_context
                    )
                except BaseException:
                    # Pure preflight can fail before creating evidence. Preserve
                    # any partial files, but do not let an empty directory block retry.
                    try:
                        attempt_dir.rmdir()
                    except OSError:
                        pass
                    raise
                atomic(attempt_dir / "attempt.json", attempt)
                attempts.append(receipt(attempt_dir / "attempt.json"))
                require(
                    attempt["status"] == "valid",
                    f"retained {attempt['status']} attempt: {attempt_dir}; inspect before resuming",
                )
                complete = attempt
            if reuse is None:
                value, _ = sample_value(complete, identity, plan)
                row = {"attempts": attempts}
            else:
                row, value = reuse
            values[slot["variant"]].append(value)
            rows.append({**slot, **row})
            atomic(
                output / "collection.partial.json",
                {
                    "schema_version": 1,
                    "kind": plan["kind"],
                    "plan": receipt(plan_path),
                    "samples": rows,
                },
            )
            print(now(), "complete", slot, "us", value, flush=True)
        atomic(
            output / "collection.json",
            {
                "schema_version": 1,
                "kind": plan["kind"],
                "plan": receipt(plan_path),
                "samples": rows,
            },
        )
        for variant, name in [
            (plan["baseline_variant"], "baseline.csv"),
            (plan["candidate_variant"], "candidate.csv"),
        ]:
            require(
                len(values[variant]) == plan["samples_per_variant"],
                "missing independent captures",
            )
            with (output / name).open("w") as stream:
                writer = csv.writer(stream)
                writer.writerow(["case_id", "total_us"])
                writer.writerow(
                    [plan["effect_case_id"], statistics.median(values[variant])]
                )
        print(
            json.dumps(
                {"status": "complete", "collection": str(output / "collection.json")},
                ensure_ascii=False,
            )
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--report-context",
        type=Path,
        help="optional context returned by the report entry",
    )
    args = parser.parse_args()
    try:
        collect(args.plan, args.registration, args.out, args.report_context)
    except (OSError, ValueError, KeyError) as error:
        print(
            json.dumps(
                {"status": "incomplete", "reason": str(error)}, ensure_ascii=False
            )
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
