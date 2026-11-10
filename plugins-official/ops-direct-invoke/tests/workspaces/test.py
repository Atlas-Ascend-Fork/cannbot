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

"""Real filesystem and public harness integration; no model or device is used."""

import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

sys.dont_write_bytecode = True
PLUGIN = Path(__file__).resolve().parents[2]
REPO = PLUGIN.parents[1]
sys.path.insert(0, str(PLUGIN / "tools"))
from workspace import prepare, prepare_phase, load_context, write_json, metadata, phase_skills, validate_graph_context
from assemble_workflow import assemble, context_path, split_context, publish_workflow, write_template


def skill(path, name):
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: fixture\n---\n{name}\n")


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="direct-invoke-context-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "assets"
        self.source.mkdir()
        for relative in ["agents", "docs", "orchestrations", "tools", "skills/custom-skills"]:
            shutil.copytree(PLUGIN / relative, self.source / relative,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        external = self.root / "external"
        external.mkdir()
        for name in ["ascendc-direct-invoke-template", "cannbot-dsl-best-practice",
                     "cannbot-dsl-test-generator", "cannbot-dsl-env-check", "ops-kirin-simulator",
                     "ascendc-st-design", "fixture-executor", "fixture-verifier"]:
            skill(external / name, name)
        shutil.copytree(REPO / "harness/workflow-orchestrator", external / "workflow-orchestrator",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        performance = self.root / "performance"
        names = ["ops-perf-optimize-workflow", "perf-stage"]
        for name in names + ["knowledge-query"]:
            skill(performance / ".agents/skills" / name, name)
        (performance / ".codex").mkdir()
        write_json(performance / ".codex/cannbot-plugin.json", {
            "schemaVersion": 2, "plugins": [{"plugin": "ops-perf-optimize",
            "skills": [".agents/skills/" + name for name in names]}]})
        (performance / ".cannbot").mkdir()
        (performance / ".cannbot/knowledge.env").write_text(f"KB_ROOT={performance}/knowledge\n")
        identity = performance / ".cannbot/plugins/ops-perf-optimize/AGENTS.md"
        identity.parent.mkdir(parents=True)
        shutil.copy2(REPO / "plugins-official/ops-perf-optimize/AGENTS.md", identity)
        self.config = self.root / ".cannbot/ops-direct-invoke.json"
        self.config.parent.mkdir()
        write_json(self.config, {"schema_version": 1, "repo": "common", "platform": "ascend",
            "chip": "Ascend950", "preferences": {"interaction": "confirm", "review_points": []},
            "tool": "codex", "asset_root": str(self.source), "external_skills_root": str(external),
            "performance_root": str(performance),
            "performance_registry": str(performance / ".codex/cannbot-plugin.json")})
        self.work = self.root / "project with spaces" / "workflow1"

    def freeze(self, **kwargs):
        return prepare(self.config, self.work, kwargs.get("language", "ascendc"), "operator-development",
                       kwargs.get("engineering", "common"), self.root / "operator source", kwargs.get("provider"))

    def entry(self, phase="execute", task="example"):
        return {"task_id": task, "_phase": phase,
                "agent": "ops-direct-invoke-verifier" if phase == "verify" else "ops-direct-invoke-developer",
                "prompt": "phase-visible contract only"}

    def bind(self, names=None, verify=None, role="ops-direct-invoke-developer"):
        workflow = self.work / "workflow.yaml"
        graph, bindings = split_context({"nodes": [{"id": "example", "task_type": "normal", "executor": role,
            "verifier": "ops-direct-invoke-verifier", "context": {
            "execute": {"skills": names if names is not None else ["fixture-executor"]},
            "verify": {"skills": verify if verify is not None else ["fixture-verifier"]}}}]})
        workflow.write_text(yaml.safe_dump(graph))
        context_path(workflow).write_text(yaml.safe_dump(bindings))
        validate_graph_context(workflow, self.work, load_context(self.work))

    def assert_linked_resources(self, visible, expected):
        pending, visited = ["SKILL.md"], set()
        while pending:
            resource = pending.pop()
            if resource in visited:
                continue
            visited.add(resource)
            # Match path.join/resolve: normalize before opening the visible link.
            document = Path(os.path.normpath(visible / resource))
            contents = document.read_text(encoding="utf-8")
            self.assertEqual(contents, (expected / resource).read_text(encoding="utf-8"))
            prose = re.sub(r"^```[^\n]*\n[\s\S]*?^```\s*$", "", contents, flags=re.MULTILINE)
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", prose):
                target = link.strip("<>").split("#", 1)[0]
                if not target or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) or "$" in target:
                    continue
                path = Path(os.path.normpath(document.parent / target))
                self.assertTrue(path.is_relative_to(visible), f"{document}: {target} escapes linked Skill")
                local = path.relative_to(visible)
                self.assertEqual(path.read_bytes(), (expected / local).read_bytes(), str(path))
                if path.suffix == ".md":
                    pending.append(str(local))

    def assert_phase_resource_links(self, platform, language):
        for phase in ["execute", "verify"]:
            result = prepare_phase(self.entry(phase), self.work)
            for family in ["env-check", "doc-templates"]:
                visible = Path(result["cwd"]) / ".agents/skills" / ("ops-direct-invoke-" + family)
                source = self.source / "skills/custom-skills" / family / platform / language
                self.assert_linked_resources(visible, source)

    def test_phase_skills_resolve_resources_from_flat_client_paths(self):
        original = json.loads(self.config.read_text())
        for platform, language, engineering in [("ascend", "ascendc", "common"),
                                                ("ascend", "dsl", "cannbot-dsl"),
                                                ("kirin", "ascendc", "kirin-common")]:
            with self.subTest(platform=platform, language=language):
                write_json(self.config, {**original, "platform": platform, "chip": platform})
                self.work = self.root / f"{platform}-{language}" / "workflow1"
                self.freeze(language=language, engineering=engineering)
                names = ["ops-direct-invoke-env-check", "ops-direct-invoke-doc-templates"]
                self.bind(names=names, verify=names)
                self.assert_phase_resource_links(platform, language)
                leaf = PLUGIN / "skills/custom-skills/doc-templates" / platform / language
                self.assertFalse((leaf.parents[1] / "common").exists())
                for resource in leaf.rglob("*"):
                    self.assertFalse(resource.is_symlink(), f"template resources must be independent: {resource}")

    def assert_blackbox_phase(self, node, platform, phase, role):
        agent = node.get(role)
        self.assertIsNotNone(agent)
        entry = {**self.entry(phase, node["id"]), "agent": agent}
        result = prepare_phase(entry, self.work)
        visible = Path(result["cwd"]) / ".agents/skills/ascendc-st-design"
        expected = platform == "ascend" and phase == "execute"
        self.assertEqual(visible.exists(), expected)
        if expected:
            self.assertEqual(metadata(visible)["name"], "ascendc-st-design")
        self.assertEqual(Path(result["identity"]).read_bytes(),
                         (self.source / "agents" / (agent + ".md")).read_bytes())

    def test_blackbox_task_mounts_test_design_skill_only_for_ascend_execution(self):
        original = json.loads(self.config.read_text())
        for platform, engineering in [("ascend", "common"), ("kirin", "kirin-common")]:
            with self.subTest(platform=platform):
                write_json(self.config, {**original, "platform": platform, "chip": platform})
                self.work = self.root / platform / "workflow1"
                context = self.freeze(engineering=engineering)
                task = self.source / "orchestrations/tasks/ascendc/黑盒测试设计.yaml"
                graph = assemble([task], [], [0])
                workflow = self.work / "workflow.yaml"
                publish_workflow(graph, workflow)
                validate_graph_context(workflow, self.work, context)
                node = graph["nodes"][0]
                for phase, role in [("execute", "executor"), ("verify", "verifier")]:
                    self.assert_blackbox_phase(node, platform, phase, role)

    def test_template_supplemental_skills_reach_only_their_declared_phases(self):
        context = self.freeze()
        task = self.root / "supplemental-task.yaml"
        task.write_text(yaml.safe_dump({
            "task_type": "normal", "title": "supplemental skills", "goal": ["produce evidence"],
            "approach": ["{{var:executor_skills}}"], "procedure": ["{{var:verifier_skills}}"],
            "acceptance": ["evidence exists"], "out_of_scope": ["unrelated work"],
            "executor": "ops-direct-invoke-developer", "verifier": "ops-direct-invoke-verifier",
            "on_exhaust": "exit",
            "variables": {"executor_skills": "无补充 Skill。", "verifier_skills": "无补充 Skill。"},
            "context": {"execute": {"skills": []}, "verify": {"skills": []}}}))
        supplied = {
            "executor_skills": {"text": "执行说明，保存 $WORK_DIR 下的原始证据。\n不修改此说明。",
                                "skills": ["fixture-executor"],
                                "skills_by_platform": {"ascend": ["ops-direct-invoke-engineering"]}},
            "verifier_skills": {"text": "验收说明，独立审查 $WORK_DIR 下的证据。",
                                "skills": ["fixture-verifier"]}}
        template = self.root / "supplemental-template.yaml"
        definition = {"use_when": "supplemental skill fixture", "workflow": "ops-direct-invoke",
                      "max_parallel": 1, "nodes": [{"id": "0", "yaml": task.name,
                      "depends_on": [], "max_retries": 0, "variables": supplied}]}
        template.write_text(yaml.safe_dump(definition))
        workflow = self.work / "workflow.yaml"
        graph = write_template(template, workflow)
        validate_graph_context(workflow, self.work, context)
        node = graph["nodes"][0]
        for phase, field, variable, names in [
                ("execute", "approach", "executor_skills", {"fixture-executor",
                 "ops-direct-invoke-engineering", "ascendc-direct-invoke-template"}),
                ("verify", "procedure", "verifier_skills", {"fixture-verifier"})]:
            declaration = supplied.get(variable)
            self.assertIsNotNone(declaration)
            self.assertEqual(node.get(field), [declaration["text"]])
            result = prepare_phase(self.entry(phase, node["id"]), self.work)
            visible = Path(result["cwd"]) / ".agents/skills"
            self.assertEqual({path.name for path in visible.iterdir()}, names)
            for name in names:
                source = context["skills"].get(name)
                self.assertIsNotNone(source)
                self.assertEqual((visible / name / "SKILL.md").read_bytes(),
                                 (Path(source) / "SKILL.md").read_bytes())
        self.assert_invalid_supplemental_skills(supplied, template, definition)

    def assert_invalid_supplemental_skills(self, supplied, template, definition):
        for name, skills, variants, error in [
                ("missing-skill", ["missing-supplemental-skill"], {"ascend": []},
                 "required Skill is not available.*missing-supplemental-skill"),
                ("unknown-platform", [], {"ascend": [], "asend": ["fixture-executor"]},
                 "unknown Skill platforms.*asend")]:
            with self.subTest(name=name):
                supplied["executor_skills"].update(skills=skills, skills_by_platform=variants)
                template.write_text(yaml.safe_dump(definition))
                self.work = self.root / name
                context = self.freeze()
                workflow = self.work / "workflow.yaml"
                write_template(template, workflow)
                with self.assertRaisesRegex(ValueError, error):
                    validate_graph_context(workflow, self.work, context)

    def test_phases_use_only_declared_skills_and_frozen_sources(self):
        context = self.freeze()
        self.bind()
        execution = prepare_phase(self.entry(), self.work)
        verifier = prepare_phase(self.entry("verify"), self.work)
        self.assertNotEqual(execution["cwd"], verifier["cwd"])
        for result, expected in [(execution, "fixture-executor"), (verifier, "fixture-verifier")]:
            cwd = Path(result["cwd"])
            self.assertEqual(result["env"]["PWD"], str(cwd))
            self.assertEqual(result["env"]["WORK_DIR"], str(self.work))
            self.assertEqual(result["env"]["CODE_DIR"], str(self.root / "operator source"))
            self.assertEqual(result["env"]["PROJECT_ROOT"], str(self.root))
            self.assertEqual({p.name for p in (cwd / ".agents/skills").iterdir()}, {expected})
            self.assertTrue((cwd / "AGENTS.md").is_symlink())
            self.assertTrue((cwd / "AGENTS.md").resolve().is_relative_to(self.work / ".context"))
        advice_entry = self.entry("advice")
        advice_entry["agent"] = "general"
        advice = prepare_phase(advice_entry, self.work)
        self.assertEqual(advice["role"], "ops-direct-invoke-architect")
        self.assertEqual(Path(advice["identity"]).read_bytes(),
                         (self.source / "agents/ops-direct-invoke-architect.md").read_bytes())
        (self.source / "agents/ops-direct-invoke-developer.md").write_text("source updated")
        self.assertEqual(load_context(self.work), context)
        self.assertEqual(prepare_phase(self.entry(), self.work), execution)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.freeze()
        (Path(context["plugin_root"]) / "agents/ops-direct-invoke-developer.md").write_text("tampered snapshot")
        with self.assertRaisesRegex(ValueError, "frozen resources changed"):
            load_context(self.work)

    def test_combinations_dependencies_and_overrides(self):
        with self.assertRaisesRegex(ValueError, "run init with the target client"):
            self.freeze(provider="claude")
        self.assertFalse(self.work.exists())
        config = json.loads(self.config.read_text())
        config.update(platform="kirin", chip="Kirin")
        write_json(self.config, config)
        with self.assertRaisesRegex(ValueError, "does not support"):
            self.freeze(language="dsl", engineering="cannbot-dsl")
        self.assertFalse(self.work.exists())
        with self.assertRaisesRegex(ValueError, "does not support"):
            self.freeze(engineering="common")
        config["repo"] = "cannbench"
        write_json(self.config, config)
        with self.assertRaisesRegex(ValueError, "common repository guide for Kirin"):
            self.freeze(engineering="kirin-common")
        self.assertFalse(self.work.exists())
        config["repo"] = "common"
        override = self.root / "override"
        skill(override, "ops-direct-invoke-repo-guide")
        config["skill_overrides"] = {"ops-direct-invoke-repo-guide": str(override)}
        write_json(self.config, config)
        context = self.freeze(engineering="kirin-common")
        self.bind(names=["ops-direct-invoke-engineering", "ops-direct-invoke-env-check",
                         "ops-direct-invoke-repo-guide"])
        bound = prepare_phase(self.entry(), self.work)
        self.assertIn("ops-kirin-simulator", bound["skills"])
        self.assertIn("overrides", bound["skills"]["ops-direct-invoke-repo-guide"])
        (override / "SKILL.md").write_text("updated after freeze")
        self.assertEqual(load_context(self.work), context)
        self.assertEqual(phase_skills({"skills": [], "skills_by_platform": {"kirin": ["ops-kirin-simulator"]}},
                                     context["selection"]), ["ops-kirin-simulator"])
        with self.assertRaisesRegex(ValueError, "does not support platform"):
            phase_skills({"skills": [], "skills_by_platform": {"ascend": []}}, context["selection"])

    def test_performance_mount_preserves_original_skills_and_dependencies(self):
        context = self.freeze()
        self.bind(names=["ops-perf-optimize-workflow"], verify=[], role="perf-optimize")
        entry = self.entry()
        entry["agent"] = "perf-optimize"
        result = prepare_phase(entry, self.work)
        cwd = Path(result["cwd"])
        self.assertEqual(Path(result["identity"]).read_bytes(),
                         (REPO / "plugins-official/ops-perf-optimize/AGENTS.md").read_bytes())
        self.assertEqual((cwd / "AGENTS.md").resolve(), Path(result["identity"]))
        for name in ["ops-perf-optimize-workflow", "perf-stage", "knowledge-query"]:
            path = cwd / ".agents/skills" / name
            self.assertTrue(path.is_symlink(), name)
            self.assertTrue(path.resolve().is_relative_to(self.work / ".context/performance"))
            self.assertEqual(metadata(path)["name"], name)
        self.assertIn(str(cwd), (cwd / ".cannbot/knowledge.env").read_text())
        runtime = cwd / ".cannbot/workspaces/tool"
        runtime.mkdir(parents=True)
        (runtime / "result.txt").write_text("mutable performance tool output")
        self.assertEqual(load_context(self.work), context)
        self.assertEqual(prepare_phase(entry, self.work), result)
        verifier = prepare_phase(self.entry("verify"), self.work)
        self.assertNotIn("ops-perf-optimize-workflow", verifier["skills"])

    def test_refuse_unknown_skills_role_traversal_and_user_file_overwrite(self):
        self.freeze()
        with self.assertRaisesRegex(ValueError, "not available"):
            self.bind(names=["unknown-skill"])
        self.bind()
        entry = self.entry()
        entry["agent"] = "../../identity"
        with self.assertRaisesRegex(ValueError, "invalid role"):
            prepare_phase(entry, self.work)
        cwd = self.work / "agents/example/execute"
        cwd.mkdir(parents=True)
        (cwd / "AGENTS.md").write_text("user content")
        with self.assertRaisesRegex(ValueError, "refusing to replace"):
            prepare_phase(self.entry(), self.work)
        self.assertEqual((cwd / "AGENTS.md").read_text(), "user content")

    def test_dangling_manifest_and_phase_directory_alias_do_not_write_outside(self):
        self.work.mkdir(parents=True)
        victim = self.root / "must-not-be-created"
        (self.work / "context.json").symlink_to(victim)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.freeze()
        self.assertFalse(victim.exists())
        (self.work / "context.json").unlink()
        self.freeze()
        self.bind()
        outside = self.root / "outside"
        outside.mkdir()
        (self.work / "agents").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "must not traverse a symlink"):
            prepare_phase(self.entry(), self.work)
        self.assertEqual(list(outside.iterdir()), [])

    def test_review_preferences_require_real_approval_gates(self):
        config = json.loads(self.config.read_text())
        config["preferences"]["review_points"] = ["方案完成后给我检视", "delivery"]
        write_json(self.config, config)
        context = self.freeze()
        node = {"id": "design", "task_type": "normal", "executor": "ops-direct-invoke-developer",
                "verifier": "ops-direct-invoke-verifier",
                "context": {"execute": {"skills": []}, "verify": {"skills": []}}}
        graph = {"nodes": [node, {**node, "id": "delivery", "require_approval": True}]}
        workflow = self.work / "workflow.yaml"
        clean, bindings = split_context(graph)
        workflow.write_text(yaml.safe_dump(clean))
        context_path(workflow).write_text(yaml.safe_dump(bindings))
        with self.assertRaisesRegex(ValueError, "not bound to require_approval"):
            validate_graph_context(workflow, self.work, context)
        self.assertFalse((self.work / "run-inputs.json").exists())
        node["require_approval"] = ["方案完成后给我检视"]
        workflow.write_text(yaml.safe_dump(split_context(graph)[0]))
        validate_graph_context(workflow, self.work, context)
        self.assertEqual(json.loads((self.work / "run-inputs.json").read_text())["workflow"], str(workflow))

    def write_harness_graph(self):
        node = {"id": "producer", "task_type": "normal", "title": "fixture", "goal": ["goal"],
                "approach": ["EXECUTOR_ONLY"], "procedure": ["VERIFIER_ONLY"], "acceptance": ["evidence"],
                "out_of_scope": ["real operator work"], "depends_on": [],
                "executor": "ops-direct-invoke-developer", "verifier": "ops-direct-invoke-verifier",
                "max_retries": 0, "on_exhaust": "exit",
                "context": {"execute": {"skills": ["fixture-executor"]}, "verify": {"skills": ["fixture-verifier"]}}}
        child = {"nodes": [{**node, "id": "child"}]}
        graph = {"workflow": "fixture", "max_parallel": 2, "nodes": [node,
                 {"id": "static", "task_type": "subgraph", "file": "static.yaml", "depends_on": []},
                 {"id": "dynamic", "task_type": "subgraph", "file": "generated.yaml", "depends_on": ["producer"]}]}
        workflow = self.work / "workflow.yaml"
        publish_workflow(graph, workflow)
        publish_workflow({"nodes": [{**node, "id": "child", "context": {
            "execute": {"skills": ["fixture-verifier"]},
            "verify": {"skills": ["fixture-executor"]}}}]}, self.work / "static.yaml")
        (self.work / "child-input.json").write_text(json.dumps(child))
        return workflow

    def install_fixture_codex(self):
        binary = self.root / "bin"
        binary.mkdir()
        cli = binary / "codex"
        cli.write_text(f"#!{sys.executable}\n" + r'''
import json, os, pathlib, subprocess, sys
import yaml
cwd = pathlib.Path.cwd()
phase = json.loads((cwd / 'context.json').read_text())
work = pathlib.Path(os.environ['WORK_DIR'])
assert os.environ['PWD'] == str(cwd)
uses_executor = (phase['phase'] == 'execute') != (phase['task_id'] == 'static/child')
expected = 'fixture-executor' if uses_executor else 'fixture-verifier'
assert {p.name for p in (cwd / '.agents/skills').iterdir()} == {expected}
prompt = sys.argv[-1]
assert ('EXECUTOR_ONLY' in prompt) == (phase['phase'] == 'execute')
assert ('VERIFIER_ONLY' in prompt) == (phase['phase'] == 'verify')
if phase['task_id'] == 'producer' and phase['phase'] == 'execute':
    sys.path.insert(0, os.environ['OPS_DIRECT_INVOKE_ROOT'] + '/tools')
    from assemble_workflow import publish_workflow
    publish_workflow(json.loads((work / 'child-input.json').read_text()), work / 'generated.yaml')
with (work / 'dispatches.jsonl').open('a') as out:
    out.write(json.dumps({'task':phase['task_id'], 'phase':phase['phase'], 'cwd':str(cwd)}) + '\n')
if phase['phase'] == 'verify':
    subprocess.run([sys.executable, os.environ['HARNESS_SKILL_DIR'] + '/scripts/verdict_pass.py',
                    '--work-dir',str(work),'--task-id',phase['task_id']],check=True)
''')
        cli.chmod(0o755)
        return binary

    def test_public_harness_static_and_dynamic_nodes_get_distinct_contexts(self):
        context = self.freeze()
        workflow = self.write_harness_graph()
        binary = self.install_fixture_codex()
        command = [sys.executable, str(PLUGIN / "tools/run_workflow.py"), "--yaml", str(workflow),
                   "--work-dir", str(self.work), "--provider", "codex", "--foreground"]
        env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"]}
        result = subprocess.run(command + ["--prompt", "fixture request"], env=env, text=True,
                                capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        dispatches = [json.loads(line) for line in (self.work / "dispatches.jsonl").read_text().splitlines()]
        self.assertEqual({(d["task"], d["phase"]) for d in dispatches},
                         {(task, phase) for task in ["producer", "static/child", "dynamic/child"]
                          for phase in ["execute", "verify"]})
        self.assertEqual(len({d["cwd"] for d in dispatches}), 6)
        state_before = (self.work / ".workflow/status.json").read_bytes()
        resumed = subprocess.run(command, env=env, text=True, capture_output=True, timeout=60)
        self.assertEqual(resumed.returncode, 0, resumed.stdout + resumed.stderr)
        self.assertEqual((self.work / ".workflow/status.json").read_bytes(), state_before)
        self.assertEqual(load_context(self.work), context)
        # Sidecars join the frozen inputs too: neither changing nor deleting one is a valid resume.
        sidecar = context_path(self.work / "generated.yaml")
        original = sidecar.read_bytes()
        sidecar.write_bytes(original + b"\n# changed binding file\n")
        with self.assertRaisesRegex(ValueError, "frozen workflow changed"):
            validate_graph_context(workflow, self.work, context)
        sidecar.unlink()
        with self.assertRaisesRegex(ValueError, "context file missing"):
            validate_graph_context(workflow, self.work, context)
        sidecar.write_bytes(original)
        # A dynamically created graph joins the frozen inputs at first dispatch.
        changed = yaml.safe_load((self.work / "generated.yaml").read_text())
        changed["nodes"][0]["goal"] = ["changed contract"]
        (self.work / "generated.yaml").write_text(yaml.safe_dump(changed))
        with self.assertRaisesRegex(ValueError, "frozen workflow changed"):
            validate_graph_context(workflow, self.work, context)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
