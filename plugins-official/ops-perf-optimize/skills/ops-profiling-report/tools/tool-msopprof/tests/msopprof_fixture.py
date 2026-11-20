# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Synthetic msopprof executable and bound capture shared by tool/integration tests."""
import json
from pathlib import Path
import report_contract
from device_fixture import bind_plan, FAKE_TARGET

backend = report_contract.backend({"provider": "msopprof"})


def fake_tool(tmp_path):
    path = tmp_path / "msopprof"
    path.write_text("""#!/usr/bin/env python3
import csv, os, sys
from pathlib import Path
if '--help' in sys.argv:
 print('--output --warm-up --replay-mode --launch-count --kernel-name --aic-metrics --set');sys.exit(0)
if '--version' in sys.argv: sys.exit(2)
root=Path(next(x.split('=',1)[1] for x in sys.argv if x.startswith('--output=')))
FAKE_TARGET_PLACEHOLDER
root=root/'OPPROF_fixture';root.mkdir()
with (root/'OpBasicInfo.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['Op Name','Op Type','Task Duration(us)','Device Id','Pid','Block Dim','Current Freq','Rated Freq'])
 w.writerow(['A','mix',10,physical,os.getpid(),4,1650,1650]);w.writerow(['B','vector',5,physical,os.getpid(),8,1650,1650])
""".replace('FAKE_TARGET_PLACEHOLDER', FAKE_TARGET))
    path.chmod(0o755)
    return path


def captured(tmp_path, monkeypatch, physical=4, kernel="B", occurrence=None, variant="baseline"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ASCEND_RT_VISIBLE_DEVICES", str(physical))
    tool = fake_tool(tmp_path)
    if occurrence is not None:
        tool.write_text(tool.read_text().replace("['B','vector',5,", "['A','mix',1,"))
    plan = backend.prepare({"tool": str(tool), "launch_count": 2})
    identity = {"runner": ["/unused/app"], "cwd": str(tmp_path), "kernel_name": kernel}
    if occurrence is not None:
        identity["occurrence"] = occurrence
    plan.update(identities={variant: identity}, frequency_policy="record_only", effect_case_id="case")
    bind_plan(plan, physical=physical)
    monkeypatch.setattr(backend.device_context, "probe", lambda *a: plan["device_binding"])
    folder = tmp_path / "capture"
    folder.mkdir()
    attempt = backend.collect_attempt(plan, identity, {"variant": variant, "slot": 0, "sample_index": 0}, folder)
    assert attempt["status"] == "valid", attempt
    plan_path, attempt_path = tmp_path / "plan.json", tmp_path / "attempt.json"
    plan_path.write_text(json.dumps(plan))
    attempt_path.write_text(json.dumps(attempt))
    report = backend.build_bound_report(plan_path, attempt_path, tmp_path / "report")
    return plan, identity, attempt, report
