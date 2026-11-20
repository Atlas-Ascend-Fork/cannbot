# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Exercise the report boundary with distinct raw formats and legacy receipts."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_npu_compute_evidence import evidence, fixture, text, write
import npu_compute_backend as backend
import report_contract


def rebind_plan(paths, plan, collection):
    bound = write(paths[0], plan)
    registration = json.loads(paths[1].read_text())
    registration["artifacts"] = [bound]
    write(paths[1], registration)
    collection["plan"] = bound
    write(paths[2], collection)


def test_existing_backend_kind_preserves_archived_proof_format(tmp_path):
    from performance_effect_evidence import build_proof, verify_proof

    paths = fixture(tmp_path)
    plan, collection = (
        json.loads(paths[0].read_text()),
        json.loads(paths[2].read_text()),
    )
    plan["kind"] = collection["kind"] = "npu_compute10_independent_v1"
    rebind_plan(paths, plan, collection)
    proof = build_proof(*paths, "case")
    assert proof["kind"] == "npu_compute10_independent_v1"
    destination = tmp_path / "legacy-proof.json"
    write(destination, proof)
    assert verify_proof(destination, paths[3], paths[4]) == proof


def test_workflow_proof_accepts_another_raw_format_via_report_adapter(
    tmp_path, monkeypatch
):
    from performance_effect_evidence import build_proof, verify_proof

    paths = fixture(tmp_path)
    plan, collection = (
        json.loads(paths[0].read_text()),
        json.loads(paths[2].read_text()),
    )
    protocol = {"profiler": "fixture-meter", "unit": "ns"}
    plan["protocol"] = protocol
    plan["tool"] = text(tmp_path / "fixture-meter", "synthetic adapter test")
    for identity in plan["identities"].values():
        identity["target"] = identity.pop("kernel_name")
        identity.pop("block_dim")
    for row in collection["samples"]:
        attempt_path = Path(row["attempts"][0]["path"])
        attempt = json.loads(attempt_path.read_text())
        identity = plan["identities"][row["variant"]]
        raw = Path(attempt["summary"]["path"])
        prior = json.loads(raw.read_text())
        attempt["summary"] = write(
            raw,
            {
                "target": identity["target"],
                "elapsed_ns": prior["Task Duration(us)"] * 1000,
                "process": prior["Pid"],
                "device": 0,
                "clock_mhz": 1650,
            },
        )
        attempt["protocol"] = protocol
        attempt["command"] = [plan["tool"]["path"], *identity["runner"]]
        attempt["run_log"] = write(
            Path(attempt["run_log"]["path"]), {"artifact": attempt["archive"]["path"]}
        )
        attempt["import_log"] = write(
            Path(attempt["import_log"]["path"]), {"directory": str(raw.parent)}
        )
        row["attempts"][0] = write(attempt_path, attempt)
    rebind_plan(paths, plan, collection)
    calls = []

    def validate_measurement(value):
        assert value["protocol"] == protocol
        assert Path(value["tool"]["path"]).name == "fixture-meter"

    def raw_sample(path, identity, value):
        record = json.loads(Path(path).read_text())
        assert record["target"] == identity["target"]
        assert record["device"] == value["logical_device"]
        assert record["clock_mhz"] == value["rated_frequency_mhz"]
        calls.append(path)
        return record["elapsed_ns"] / 1000, record["process"]

    def check_command(command, identity, plan=None):
        assert command[1:] == identity["runner"]

    def validate_publication(attempt, archive, summary, log, import_log, plan=None):
        assert json.loads(log)["artifact"] == str(archive)
        assert Path(json.loads(import_log)["directory"]) == summary.parent
        assert attempt["import_returncode"] == 0

    adapter = SimpleNamespace(
        validate_measurement=validate_measurement,
        raw_sample=raw_sample,
        check_command=check_command,
        validate_publication=validate_publication,
    )
    monkeypatch.setitem(
        report_contract._BACKENDS, "fixture-meter", "fixture_meter_adapter"
    )
    monkeypatch.setitem(sys.modules, "fixture_meter_adapter", adapter)
    proof = build_proof(*paths, "case")
    assert proof["kind"] == "profile10_independent_v1"
    assert proof["statistics"]["ci_us"][1] < 0 and len(calls) == 20
    destination = tmp_path / "proof.json"
    write(destination, proof)
    assert verify_proof(destination, paths[3], paths[4]) == proof
    assert len(calls) == 40
    # Different protocols cannot silently fall back to a supported parser.
    with pytest.raises(ValueError, match="unsupported"):
        report_contract.validate_measurement(
            {"protocol": {"profiler": "unknown-meter"}}
        )


def test_measurement_preparation_only_queries_capabilities(tmp_path, monkeypatch):
    executable = tmp_path / "npu-compute"
    executable.write_text("synthetic CLI")
    monkeypatch.setattr(backend.shutil, "which", lambda name: str(executable))
    monkeypatch.setattr(backend, "tool_skill", lambda context: tmp_path)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(
            returncode=0, stdout="--cache-control PipeUtilization", stderr=""
        )

    monkeypatch.setattr(backend.subprocess, "run", run)
    binding = backend.prepare()
    assert commands == [
        [str(executable), "--help"],
        [str(executable), "--list-sections"],
    ]
    assert binding["tool"]["sha256"] == evidence.receipt(executable)["sha256"]
    assert binding["protocol"] == backend.PROTOCOL
    monkeypatch.setattr(
        backend.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=0, stdout="unsupported set", stderr=""
        ),
    )
    with pytest.raises(ValueError, match="capability"):
        backend.prepare()
