# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Synthetic runtime mapping for offline tests; never probes a real NPU."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import device_context as devices
from report_common import receipt


def binding(application=0, physical=0, visible=None, environment=None):
    env = devices.snapshot(os.environ if environment is None else environment)
    if visible is not None:
        env["ASCEND_RT_VISIBLE_DEVICES"] = visible
    entries = devices.visible_list(env["ASCEND_RT_VISIBLE_DEVICES"])
    return {
        "schema_version": 1, "application_device": application,
        "runtime_device": entries[application] if entries else application,
        "physical_device": physical, "visible_count": len(entries) if entries else 8,
        "environment": env, "mapping_api": "aclrtGetPhyDevIdByUserDevId",
        "runtime_library": receipt(__file__), "resolver": receipt(devices.SCRIPT),
        "launcher_python": receipt(sys.executable),
        "host_boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
    }


def bind_plan(plan, **kwargs):
    device = binding(**kwargs)
    plan.setdefault("effect_case_id", "case")
    plan.update(device_binding=device, environment=device["environment"],
                logical_device=device["application_device"], physical_device=device["physical_device"])
    return plan


def process_receipt(root, plan, runner, pid=1234):
    path = root / "target-process.json"
    path.write_text(json.dumps({
        "schema_version": 1, "pid": pid, "start_ticks": 12345,
        "host_boot_id": plan["device_binding"]["host_boot_id"],
        "binding_sha256": devices.digest(plan["device_binding"]),
        "capture_id": devices.capture_id(root / "output"),
        "runner": runner, "environment": plan["device_binding"]["environment"],
    }))
    return receipt(path)


def bare_plan(protocol):
    tool = receipt(__file__)
    return bind_plan({
        "tool": tool, "protocol": dict(protocol),
        "report_context": {"capabilities": {"tool": tool}},
    })


FAKE_TARGET = '''
import hashlib, json
binding=json.loads((root.parent/'device-binding.json').read_text())
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
(root.parent/'target-process.json').write_text(json.dumps({
 'schema_version':1,'pid':os.getpid(),'start_ticks':12345,
 'host_boot_id':binding['host_boot_id'],'binding_sha256':digest(binding),
 'capture_id':digest(str(root.resolve())),'runner':sys.argv[sys.argv.index('--')+1:],
 'environment':binding['environment']}))
physical=binding['physical_device']
'''
