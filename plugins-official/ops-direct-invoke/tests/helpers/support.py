# ----------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------

"""Shared fixtures for workflow public-interface tests; no harness internals imported."""
import argparse
import csv
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = PLUGIN_ROOT / 'skills/orchestrator'
SCRIPTS = PLUGIN_ROOT / 'tools'
WORKFLOWS = PLUGIN_ROOT / 'orchestrations/workflows'
HARNESS_SKILL = PLUGIN_ROOT.parents[1] / 'harness/workflow-orchestrator'


def task_fixture():
    return {'task_type': 'normal', 'title': 'fixture', 'goal': ['produce a result'],
            'approach': ['write result'], 'procedure': ['review result'],
            'acceptance': ['result exists'], 'out_of_scope': ['unrelated work'],
            'executor': 'ops-direct-invoke-developer', 'verifier': 'ops-direct-invoke-verifier',
            'on_exhaust': 'exit'}


class StrictLoader(yaml.SafeLoader):
    """Do not let duplicate keys hide mistakes in committed YAML."""


def strict_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ValueError(f'non-string or duplicate YAML key: {key!r}')
        result[key] = loader.construct_object(value_node)
    return result


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, strict_mapping)


def load_yaml(path):
    loader = StrictLoader(path.read_text(encoding='utf-8'))
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


def available_workflows():
    with tempfile.TemporaryDirectory(prefix='workflow-guide-') as temp:
        output = Path(temp) / 'workflow-guide.csv'
        result = subprocess.run([sys.executable, str(SCRIPTS / 'generate_workflow_guide.py'),
                                 '--output', str(output)], cwd=temp, capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise ValueError(result.stdout + result.stderr)
        with output.open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream, strict=True)
            if reader.fieldnames != ['file', 'use_when']:
                raise ValueError('guide requires file and use_when columns')
            return list(reader)


def run_command(case, arguments, cwd):
    command = [sys.executable, *map(str, arguments)]
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=60)
    case.assertEqual(result.returncode, 0,
                     f'Command failed: {command}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}')
    return result


def generate_workflow(case, entry, directory):
    arguments = [SCRIPTS / 'assemble_workflow.py', '--template', WORKFLOWS / entry['file'],
                 '--output', directory / 'workflow.yaml']
    run_command(case, arguments, directory)
    return directory / 'workflow.yaml'


def run_workflow(case, definition_flag, definition, work):
    case.assertTrue((HARNESS_SKILL / 'scripts/orchestrator.py').is_file(),
                    f'harness CLI missing: {HARNESS_SKILL}; pass --harness-skill')
    source = WORKFLOWS / definition if definition_flag == '--template' else Path(definition)
    graph = load_yaml(source)
    for container in (node for node in graph['nodes'] if node.get('task_type') == 'subgraph'):
        path = work / container['file']
        path.parent.mkdir(parents=True, exist_ok=True)
        child = {'id': 'fixture-unit', 'task_type': 'normal', 'title': 'dry-run fixture Unit',
                 'goal': ['simulate one generated Unit'], 'approach': ['dry-run only'],
                 'acceptance': ['dry-run pass'], 'out_of_scope': ['real operator work'],
                 'depends_on': [], 'executor': 'ops-direct-invoke-developer',
                 'verifier': 'ops-direct-invoke-verifier', 'max_retries': 0, 'on_exhaust': 'exit'}
        path.write_text(yaml.safe_dump({'nodes': [child]}, allow_unicode=True), encoding='utf-8')
    arguments = [SCRIPTS / 'run_workflow.py', definition_flag, definition,
                 '--work-dir', work, '--provider', 'codex', '--prompt', 'registry UT simulation only',
                 '--harness-skill', HARNESS_SKILL, '--foreground', '--dry-run']
    # Deliberately launch outside the Skill directory to check resource path resolution.
    run_command(case, arguments, work.parent)


def run_tests():
    """Every category exposes the same CLI, plus normal unittest options."""
    import unittest
    global HARNESS_SKILL
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--harness-skill', type=Path)
    args, remaining = parser.parse_known_args()
    if args.harness_skill:
        HARNESS_SKILL = args.harness_skill.resolve()
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
