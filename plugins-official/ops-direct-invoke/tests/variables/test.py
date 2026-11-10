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

"""Exercise task-local prompt binding through the assembler CLI."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).absolute().parents[1] / "helpers"))
from support import SCRIPTS, load_yaml, run_tests, task_fixture


class VariableTests(unittest.TestCase):
    def skill_task(self):
        task = task_fixture()
        task['variables'] = {'executor_skills': '无补充 Skill。', 'verifier_skills': '无补充 Skill。'}
        task['approach'] = ['{{var:executor_skills}}']
        task['procedure'] = ['{{var:verifier_skills}}']
        task['context'] = {
            'execute': {'skills': ['base-skill'], 'skills_by_platform': {'ascend': ['ascend-base'], 'kirin': []}},
            'verify': {'skills': ['review-base']},
        }
        return task

    def source_task(self):
        task = task_fixture()
        task['variables'] = {'message': None, 'suffix': 'default'}
        for field in ['goal', 'approach', 'procedure', 'acceptance', 'out_of_scope']:
            task[field] = ['{{id}}: {{var:message}} / {{var:suffix}}']
        return task

    def compile(self, folder, task, nodes):
        (folder / 'task.yaml').write_text(yaml.safe_dump(task, allow_unicode=True))
        source, output = folder / 'template.yaml', folder / 'workflow.yaml'
        source.write_text(yaml.safe_dump({'workflow': 'variables', 'max_parallel': 2, 'nodes': nodes}))
        result = subprocess.run([sys.executable, str(SCRIPTS / 'assemble_workflow.py'),
                                 '--template', str(source), '--output', str(output)],
                                cwd='/', capture_output=True, text=True, timeout=60)
        return result, output

    def test_node_isolation_defaults_multiline_and_literal_values(self):
        with tempfile.TemporaryDirectory(prefix='workflow-vars-') as temp:
            folder = Path(temp)
            literal = '中文: "quoted"\n$WORK_DIR $(false) `false` \\1 {{var:suffix}} {{id}}'
            nodes = [
                {'id': '0.0', 'yaml': 'task.yaml', 'depends_on': [], 'max_retries': 0,
                 'variables': {'message': literal}},
                {'id': '0.1', 'yaml': 'task.yaml', 'depends_on': [], 'max_retries': 2,
                 'variables': {'message': 'second', 'suffix': 'override'}}]
            result, output = self.compile(folder, self.source_task(), nodes)
            self.assertEqual(result.returncode, 0, result.stderr)
            generated = load_yaml(output)['nodes']
            for node, expected in zip(generated, [f'0.0: {literal} / default', '0.1: second / override']):
                self.assertNotIn('variables', node)
                for field in ['goal', 'approach', 'procedure', 'acceptance', 'out_of_scope']:
                    self.assertEqual(node[field], [expected])
            self.assertEqual(load_yaml(folder / 'task.yaml')['variables']['message'], None)
            self.assertEqual(load_yaml(folder / 'template.yaml')['nodes'], nodes)


    def test_invalid_bindings_are_rejected_before_output(self):
        cases = [
            ('missing', {'suffix': 'x'}, None),
            ('empty_required', {'message': '  '}, None),
            ('non_string', {'message': 12}, None),
            ('unknown_assignment', {'message': 'ok', 'typo': 'x'}, None),
            ('not_mapping', [], None),
            ('undeclared_reference', {'message': 'ok'}, '{{var:typo}}'),
            ('malformed', {'message': 'ok'}, '{{var:message'),
        ]
        for name, values, prompt in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory(prefix='workflow-vars-') as temp:
                task = self.source_task()
                if prompt is not None:
                    task['approach'] = [prompt]
                result, output = self.compile(Path(temp), task, [
                    {'id': '0', 'yaml': 'task.yaml', 'depends_on': [], 'max_retries': 1, 'variables': values}])
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('variable', result.stderr)
                self.assertFalse(output.exists())

    def test_invalid_declarations_and_empty_prompt_are_rejected(self):
        for declarations, prompt in [
            ({'bad-name': 'x'}, 'ok'), ({'message': 1}, 'ok'),
            ({'message': ''}, '{{var:message}}'), (None, 'ok')]:
            with self.subTest(variables=declarations), tempfile.TemporaryDirectory(prefix='workflow-vars-') as temp:
                task = self.source_task()
                task['variables'] = declarations
                task['approach'] = [prompt]
                result, output = self.compile(Path(temp), task, [
                    {'id': '0', 'yaml': 'task.yaml', 'depends_on': [], 'max_retries': 0}])
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertFalse(output.exists())

    def test_supplemental_skills_bind_each_phase_without_changing_instructions(self):
        with tempfile.TemporaryDirectory(prefix='workflow-vars-') as temp:
            folder = Path(temp)
            text = '候选条件：证据命中时加载。\n$WORK_DIR `literal` {{var:verifier_skills}}\n'
            values = {
                'executor_skills': {'text': text, 'skills': ['extra-skill', 'base-skill', 'extra-skill'],
                                    'skills_by_platform': {'ascend': ['ascend-extra', 'ascend-base'], 'kirin': []}},
                'verifier_skills': {'text': '只读检视', 'skills': ['verify-extra']},
            }
            nodes = [
                {'id': '0.0', 'yaml': 'task.yaml', 'depends_on': [], 'max_retries': 0, 'variables': values},
                {'id': '0.1', 'yaml': 'task.yaml', 'depends_on': [], 'max_retries': 0},
            ]
            task = self.skill_task()
            result, output = self.compile(folder, task, nodes)
            self.assertEqual(result.returncode, 0, result.stderr)
            generated = load_yaml(output)['nodes']
            self.assertEqual(generated[0]['approach'], [text])
            self.assertEqual(generated[0]['procedure'], ['只读检视'])
            self.assertEqual(generated[1]['approach'], ['无补充 Skill。'])
            self.assertTrue(all('context' not in node and 'variables' not in node for node in generated))
            contexts = load_yaml(Path(str(output) + '.contexts.yaml'))
            self.assertEqual(contexts['0.0'], {
                'execute': {'skills': ['base-skill', 'extra-skill'],
                            'skills_by_platform': {'ascend': ['ascend-base', 'ascend-extra'], 'kirin': []}},
                'verify': {'skills': ['review-base', 'verify-extra']},
            })
            self.assertEqual(contexts['0.1'], task['context'])
            self.assertEqual(load_yaml(folder / 'task.yaml'), task)
            self.assertEqual(load_yaml(folder / 'template.yaml')['nodes'], nodes)

    def test_ambiguous_or_invalid_skill_declarations_fail_before_publishing(self):
        valid = {'text': '按条件加载', 'skills': ['extra-skill']}
        cases = [
            '必须加载 `ascendc-simt-tiling-design` Skill。',
            {}, {'text': '未列技能'}, {'skills': []},
            {**valid, 'text': ''}, {**valid, 'text': 1},
            {**valid, 'skills': 'extra-skill'}, {**valid, 'skills': ['../other']},
            {**valid, 'skills': [False]}, {**valid, 'skill': ['typo']},
            {**valid, 'skills_by_platform': []},
            {**valid, 'skills_by_platform': {'asend': []}},
            {**valid, 'skills_by_platform': {'ascend': 'extra-skill'}},
        ]
        for value in cases:
            with self.subTest(value=value), tempfile.TemporaryDirectory(prefix='workflow-vars-') as temp:
                result, output = self.compile(Path(temp), self.skill_task(), [
                    {'id': '0', 'yaml': 'task.yaml', 'depends_on': [], 'max_retries': 0,
                     'variables': {'executor_skills': value}}])
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn('executor_skills', result.stderr)
                self.assertFalse(output.exists())
                self.assertFalse(Path(str(output) + '.contexts.yaml').exists())


if __name__ == '__main__':
    run_tests()
