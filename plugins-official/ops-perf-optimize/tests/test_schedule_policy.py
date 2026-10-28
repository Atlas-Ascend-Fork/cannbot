# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Request policy identity is frozen; legacy inputs are not silently upgraded."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_case_sets import load_manifest, load_request
from test_prepare_case_sets import create_request, load, run, write_cases


def request_fixture(tmp_path):
    code = tmp_path / "code"
    code.mkdir()
    (code / "kernel.cpp").write_text("// policy fixture, no hardware claim\n")
    cases = tmp_path / "cases.csv"
    write_cases(cases, 2)
    path = tmp_path / "request.json"
    create_request(path, code, cases)
    return path


def test_new_request_freezes_schedule_policy(tmp_path):
    request = request_fixture(tmp_path)
    expected = {"id": "schedule_contract_v1", "version": 1}
    assert load_request(request)["schedule_policy"] == expected
    run("freeze", "--request", request, "--output-dir", tmp_path / "run")
    manifest = load_manifest(tmp_path / "run/run-manifest.json")
    assert manifest["configuration"]["schedule_policy"] == expected


def test_old_request_is_not_silently_upgraded(tmp_path):
    request = request_fixture(tmp_path)
    body = load(request)
    del body["schedule_policy"]
    request.write_text(json.dumps(body))
    assert "schedule_policy" not in load_request(request)
    run("freeze", "--request", request, "--output-dir", tmp_path / "run")
    assert "schedule_policy" not in load_manifest(tmp_path / "run/run-manifest.json")["configuration"]


@pytest.mark.parametrize("bad", [None, {}, {"id": "unknown", "version": 1},
                                   {"id": "schedule_contract_v1", "version": True},
                                   {"id": "schedule_contract_v1", "version": 2}])
def test_bad_policy_rejected_at_both_input_boundaries(tmp_path, bad):
    request = request_fixture(tmp_path)
    run("freeze", "--request", request, "--output-dir", tmp_path / "run")
    body = load(request)
    body["schedule_policy"] = bad
    request.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="schedule_policy"):
        load_request(request)
    manifest_path = tmp_path / "run/run-manifest.json"
    manifest = load(manifest_path)
    manifest["configuration"]["schedule_policy"] = bad
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="schedule_policy"):
        load_manifest(manifest_path)
