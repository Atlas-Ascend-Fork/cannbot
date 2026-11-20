# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"))
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from check_experience_archive import verify


class ArchiveChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.files = {}

        def save(name, value):
            data = value if isinstance(value, str) else json.dumps(value)
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(data)
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            self.files[name] = digest
            return {'path': '/unavailable/' + name, 'sha256': digest}

        self.save = save
        before = save('before.csv', 'case_id,total_us\n1,12\n')
        after = save('after.csv', 'case_id,total_us\n1,6\n')
        effect = save('effect.json', {'baseline_path': before['path'], 'candidate_path': after['path'],
                                    'total_case_count': 1, 'effective_geomean_speedup': 2.0,
                                    'cases': [{'case_id': '1', 'speedup': 2.0}]})
        samples = []
        for variant, values in [('baseline', [10, 12, 14]), ('candidate', [5, 6, 7])]:
            for i, value in enumerate(values):
                stem = variant + str(i)
                raw = save(stem + '.csv', f'Task Duration(us)\n{value}\n')
                summary = save(stem + '-summary.json', {'records': [{'source': raw, 'line': 2, 'duration_us': value}]})
                attempt = save(stem + '-attempt.json', {'status': 'valid', 'summary': summary})
                samples.append({'variant': variant, 'sample_index': i, 'attempts': [attempt]})
        failed = save('failed.json', {'status': 'failed'})
        samples[0]['attempts'].insert(0, failed)
        save('collection.json', {'samples': samples})
        save('lessons.json', {'sources': {'effect': effect}, 'lessons': [{
            'observations': [{'evidence': [{'source': 'effect', 'pointer': '/total_case_count'}]}],
            'reasoning': {'evidence': [{'source': 'effect', 'lines': [1, 1]}]}}]})
        self.index = {'schema_version': 1, 'path_roots': {'/unavailable': '.'}, 'files': self.files,
                      'lessons': 'lessons.json', 'effects': ['effect'], 'sampling_effect': 'effect',
                      'samples_per_variant': 3, 'collections': [{'case_id': '1', 'name': 'collection.json'}],
                      'excluded_binary_files': []}
        # Map to a real relative prefix rather than allowing './' path aliases.
        run = self.root / 'run'
        run.mkdir()
        for name in list(self.files):
            (self.root / name).rename(run / name)
        self.index['files'] = {'run/' + n: h for n, h in self.files.items()}
        self.index['path_roots'] = {'/unavailable': 'run'}
        self.index['lessons'] = 'run/lessons.json'
        self.index['collections'][0]['name'] = 'run/collection.json'
        self.write_index()

    def write_index(self):
        (self.root / 'archive-index.json').write_text(json.dumps(self.index))

    def test_offline_success_including_failed_attempt(self):
        result = verify(self.root)
        self.assertEqual((result['valid_samples'], result['failed_attempts'], result['kernel_records']), (6, 1, 6))
        self.assertEqual(result['effects']['effect']['geomean_speedup'], 2.0)

    def test_missing_source(self):
        (self.root / 'run/baseline0.csv').unlink()
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_modified_source(self):
        (self.root / 'run/baseline0.csv').write_text('changed')
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_no_original_path_fallback(self):
        self.index['path_roots'] = {}
        self.write_index()
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_duplicate_collection_rejected(self):
        self.index['collections'] *= 2
        self.write_index()
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_missing_sample_rejected(self):
        p = self.root / 'run/collection.json'
        value = json.loads(p.read_text())
        value['samples'].pop()
        p.write_text(json.dumps(value))
        self.index['files']['run/collection.json'] = hashlib.sha256(p.read_bytes()).hexdigest()
        self.write_index()
        with self.assertRaises(ValueError):
            verify(self.root)


if __name__ == '__main__':
    unittest.main()
