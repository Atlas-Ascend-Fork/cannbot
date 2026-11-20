# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""msopprof packaging and workflow integration tests."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
import report_contract
from device_fixture import bind_plan, FAKE_TARGET
from msopprof_fixture import backend, fake_tool

ROOT = Path(__file__).resolve().parents[1]


def test_private_tool_stays_inside_parent_without_skill_discovery(tmp_path):
    repository = tmp_path / "repo"
    plugin = repository / "plugins-official/demo"
    plugin.mkdir(parents=True)
    (repository / "plugins-official/LICENSE").write_text("fixture license")
    (plugin / ".claude-plugin").mkdir()
    (plugin / ".claude-plugin/plugin.json").write_text(json.dumps({"name": "demo"}))
    (plugin / "plugin-sources.json").write_text(
        json.dumps({"skillsRepository": "vendor/skills", "skills": []})
    )
    shared = repository / "vendor/skills"
    shared.mkdir(parents=True)
    (shared / ".git").mkdir()
    (shared / "LICENSE").write_text("fixture license")
    source = ROOT / "skills/ops-profiling-report"
    shutil.copytree(source, plugin / "skills/ops-profiling-report")
    module = ROOT.parents[1] / "script/lib/plugin-bundle.js"
    js = (
        f"import {{assemblePlugins}} from {json.dumps(module.as_uri())}; "
        "assemblePlugins(process.argv[1],process.argv[2],['demo']);"
    )
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            js,
            str(repository),
            str(tmp_path / "bundle"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    dest = tmp_path / "bundle/plugins/demo"
    manifest = json.loads((dest / ".claude-plugin/plugin.json").read_text())
    assert manifest["skills"] == ["./skills/ops-profiling-report"]
    parent = dest / "skills/ops-profiling-report"
    assert list(parent.rglob("SKILL.md")) == [parent / "SKILL.md"]
    assert not any(p.is_symlink() for p in parent.rglob("*"))
    assert (parent / "tools/tool-msopprof/TOOL.md").is_file()
    context = tmp_path / "context.json"
    context.write_text(json.dumps({"tools": ["msopprof"], "tool": str(fake_tool(tmp_path))}))
    binding_path = tmp_path / "binding.json"
    prepared = subprocess.run(
        [
            sys.executable,
            "-B",
            str(parent / "scripts/report_contract.py"),
            "--prepare",
            "--context",
            str(context),
            "--out",
            str(binding_path),
        ],
        capture_output=True,
        text=True,
    )
    assert prepared.returncode == 0, prepared.stdout + prepared.stderr
    binding = json.loads(binding_path.read_text())
    assert binding["provider"] == "msopprof"
    assert Path(binding["report_context"]["tool_skill"]).is_relative_to(parent)
    assert Path(binding["report_context"]["tool_skill"]).name == "TOOL.md"


@pytest.mark.parametrize("external_comparator", [False, True])
@pytest.mark.parametrize("selector", ["kernel_name", "report_op_name"])
def test_generic_collector_accepts_msopprof_and_reuses_all_independent_samples(
    tmp_path, monkeypatch, external_comparator, selector
):
    from test_npu_compute_evidence import evidence, fixture, write
    import collect_profile

    paths = fixture(tmp_path, external_comparator=external_comparator)
    executable = tmp_path / "msopprof"
    executable.write_text("""#!/usr/bin/env python3
import csv, os, sys
from pathlib import Path
if '--help' in sys.argv:
 print('--output --warm-up --replay-mode --launch-count --aic-metrics');sys.exit(0)
if '--version' in sys.argv: print('msopprof fixture build');sys.exit(0)
variant=sys.argv[-1]
root=Path(next(x.split('=',1)[1] for x in sys.argv if x.startswith('--output=')))
FAKE_TARGET_PLACEHOLDER
with (root/'OpBasicInfo.csv').open('w',newline='') as f:
 w=csv.writer(f);w.writerow(['Op Name','Op Type','Task Duration(us)','Device Id','Pid','Block Dim','Current Freq','Rated Freq'])
 w.writerow([variant,'mix',16 if variant=='baseline' else 8,0,os.getpid(),32,1650,1650])
 w.writerow(['other','vector',3,0,os.getpid(),4,1650,1650])
""".replace('FAKE_TARGET_PLACEHOLDER', FAKE_TARGET))
    executable.chmod(0o755)
    binding = report_contract.prepare({"tools": ["msopprof"], "tool": str(executable), "launch_count": 2})
    plan = json.loads(paths[0].read_text())
    plan.update(binding)
    monkeypatch.setenv("ASCEND_HOME_PATH", "/example/cann")
    bind_plan(plan)
    monkeypatch.setattr(backend.device_context, "probe", lambda *a: plan["device_binding"])
    for variant, identity in plan["identities"].items():
        identity["runner"].append(variant)
        if selector == "report_op_name":
            identity["report_op_name"] = identity.pop("kernel_name")
    updated_plan = write(paths[0], plan)
    registration = json.loads(paths[1].read_text())
    registration["artifacts"] = [updated_plan]
    write(paths[1], registration)
    monkeypatch.setenv("ASCEND_HOME_PATH", "/example/cann")
    out = tmp_path / "msopprof-captures"
    collect_profile.collect(paths[0], paths[1], out)
    proof_paths = (
        paths[0],
        paths[1],
        out / "collection.json",
        out / "baseline.csv",
        out / "candidate.csv",
    )
    proof = evidence.build_profile_proof(*proof_paths, "case", "baseline", "candidate")
    assert proof["statistics"]["ci_us"][1] < 0
    # A completed checkpoint must also notice later changes to a raw CSV.
    import workflow_state
    raw = next(out.rglob("OpBasicInfo.csv"))
    assert backend.receipt(raw) in proof["dependencies"]
    summary_path = tmp_path / "completed-summary.json"
    summary_path.write_text(json.dumps({"baseline_path": str(proof_paths[3]),
        "candidate_path": str(proof_paths[4]), "dependencies": proof["dependencies"]}))
    dependencies = {item["path"] for item in proof["dependencies"]}
    dependencies.update(map(str, (summary_path, proof_paths[3], proof_paths[4])))
    record = {"performance": {"round_summary": str(summary_path), "cumulative_summary": str(summary_path)},
              "artifacts": [workflow_state.artifact_identity(path) for path in dependencies]}
    workflow_state.recorded_performance(record)
    original_raw = raw.read_bytes()
    raw.write_bytes(original_raw + b"\n")
    with pytest.raises(ValueError, match="performance source changed"):
        workflow_state.recorded_performance(record)
    raw.write_bytes(original_raw)
    before = (out / "collection.json").read_bytes()
    with monkeypatch.context() as offline:
        offline.setenv("ASCEND_RT_VISIBLE_DEVICES", "7")
        offline.setattr(
            backend.device_context, "probe", lambda *a: pytest.fail("offline collection must not probe devices")
        )
        collect_profile.collect(paths[0], paths[1], out)
    assert (out / "collection.json").read_bytes() == before
    policy = json.loads(Path(plan["precision_policy"]["path"]).read_text())
    comparator = policy["comparator"]
    assert comparator in proof["dependencies"]
    Path(comparator["path"]).write_text("# changed comparator after proof\n")
    with pytest.raises(ValueError, match="changed"):
        evidence.build_profile_proof(*proof_paths, "case", "baseline", "candidate")
