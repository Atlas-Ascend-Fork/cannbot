# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/ops-perf-optimize-workflow/scripts"))
import experience_portability as port
import experience_reflux as reflux
import rough_bundle as pack
from test_experience_reflux import case, save
from test_search_installed import installed_search, python as installed_python


@pytest.fixture
def delivery(case):
    manifest = reflux.load(case.manifest)
    manifest['configuration']['experience_policy'] = dict(reflux.POLICY)
    save(case.manifest, manifest)
    state = reflux.load(case.root / "workflow-state.json")
    state["manifest"] = reflux.file_ref(case.manifest)
    save(case.root / "workflow-state.json", state)
    case.bundle['manifest'] = reflux.file_ref(case.manifest)
    save(case.bp, case.bundle)
    case.review['bundle'] = reflux.file_ref(case.bp)
    save(case.rp, case.review)
    root = case.root / 'published'
    root.mkdir()
    replacements = {str(case.root): '<archive>'}
    entries = []
    names = {}
    for key, ref in case.bundle['sources'].items():
        data = Path(ref['path']).read_bytes()
        name = 'data/' + key + '.json'
        names[key] = name
        entries.append({'name': name, 'text': data.decode(), 'bytes': len(data), 'sha256': ref['sha256']})
    sanitized = port.sanitize_entries(entries, replacements)
    sources = []
    for n, entry in enumerate(sanitized):
        path = case.root / f'derived{n}.txt'
        path.write_bytes(entry['text'].encode())
        sources.append({'path': str(path), **{k: v for k, v in entry.items() if k != 'text'}})
    card = root / 'r-tester-0001.md'
    pack.pack(
        {"account": "tester", "time": "2026-11-18T00:00:00Z", "title": "Synthetic evidence", "sources": sources}, card
    )
    links = {port.redact(ref['path'], replacements): card.name for ref in case.bundle['sources'].values()}
    rebinding = {entry['original_sha256']: entry['sha256'] for entry in sanitized}
    public = port.HASH.sub(lambda m: rebinding.get(m[0], m[0]), port.redact(case.material.read_text(), replacements))
    for old, new in links.items():
        public = public.replace('](' + old + ')', '](' + new + ')')
    case.card = root / 'material.md'
    case.card.write_text(public)
    contract = {'schema_version': 1, 'root': str(root), 'files': {
        card.name: reflux.file_ref(card)['sha256'], case.card.name: reflux.file_ref(case.card)['sha256']},
        'cards': [card.name], 'replacements': replacements, 'forbidden_literals': ['private-project'],
        'source_entries': names, 'material_file': case.card.name, 'links': links,
        'unavailable': ['No hardware runtime in this synthetic fixture'],
        'review_scope': 'local_review_not_reused_as_public_review'}
    cp = save(case.root / 'portable-delivery.json', contract)
    save(case.export, {'card': reflux.file_ref(case.card), 'experience_material': reflux.file_ref(case.material),
                       'experience_review': reflux.file_ref(case.rp), 'portable_delivery': reflux.file_ref(cp)})
    case.contract, case.cp, case.public, case.payload = contract, cp, root, card
    return case


def test_v2_integration_recomputes_portability(delivery):
    result = reflux.validate(delivery.bp, delivery.manifest, material_path=delivery.material,
                             review_path=delivery.rp, reflux_path=delivery.export)
    assert result['portable_export_verified'] is True
    assert result['public_semantic_review'] == 'not_inherited_from_local_review'
    assert str(delivery.payload) in [v['path'] for v in result['dependencies']]


def test_installed_v2_gate_verifies_export(delivery, installed_search):
    output = installed_python(installed_search,
        "import experience_reflux as e; "
        "print(e.validate(sys.argv[2], sys.argv[3], material_path=sys.argv[4], "
        "review_path=sys.argv[5], reflux_path=sys.argv[6])['portable_export_verified'])",
        delivery.bp, delivery.manifest, delivery.material, delivery.rp, delivery.export)
    assert output.strip() == "True"
    assert (installed_search['skills'] / 'ops-perf-postprocess/references/portable-reflux.md').is_file()


def test_v2_rejects_legacy_path_only_export(case):
    with pytest.raises(ValueError, match='portable_delivery'):
        reflux.validate_export(case.export, case.material, case.rp, bundle=case.bundle, portable=True)


@pytest.mark.parametrize(
    "kind", ["source_omitted", "missing_file", "changed_file", "unlisted_file", "old_review_scope"]
)
def test_bad_public_delivery_rejected(delivery, kind):
    if kind == 'source_omitted':
        delivery.contract['source_entries'].pop('observation')
    elif kind == 'missing_file':
        delivery.payload.unlink()
    elif kind == 'changed_file':
        delivery.card.write_text('truncated material')
    elif kind == 'unlisted_file':
        (delivery.public / 'private-plan.json').write_text('{}')
    else:
        delivery.contract['review_scope'] = 'old_score_is_public_score'
    save(delivery.cp, delivery.contract)
    with pytest.raises(ValueError):
        port.validate_delivery(delivery.cp, delivery.bundle, delivery.material)


def test_rehashed_truncated_prose_still_rejected(delivery):
    delivery.card.write_text('only an evidence inventory')
    delivery.contract['files'][delivery.card.name] = reflux.file_ref(delivery.card)['sha256']
    save(delivery.cp, delivery.contract)
    with pytest.raises(ValueError, match='reviewed experience'):
        port.validate_delivery(delivery.cp, delivery.bundle, delivery.material)


@pytest.mark.parametrize('text', ['/home/user/run/file', '/Users/user/run', r'C:\Users\user\run',
                                  'employee h12345678', '[source](/tmp/private.json)', 'private-project'])
def test_personal_paths_and_project_names_rejected(text):
    with pytest.raises(ValueError):
        port.check_public(text, ['private-project'])


def test_redaction_rebinds_transitive_hashes():
    first = '{"path":"/home/user/project/file", "duration":12.75}'
    second = json.dumps({'path': '/home/user/project/first.json', 'sha256': port.sha(first.encode())})
    entries = [{'name': name, 'text': text, 'bytes': len(text.encode()), 'sha256': port.sha(text.encode())}
               for name, text in [('first.json', first), ('second.json', second)]]
    result = port.sanitize_entries(entries, {'/home/user/project': '<archive>'})
    assert result[0]['sha256'] != result[0]['original_sha256']
    assert json.loads(result[1]['text'])['sha256'] == result[0]['sha256']
    assert json.loads(result[0]['text'])['duration'] == 12.75
    assert entries[0]['text'] == first


def test_redaction_cannot_replace_numeric_results():
    with pytest.raises(ValueError):
        port.redact('speedup 1.03', {'1.03': '1.30'})


def test_public_source_cannot_be_changed_under_new_hash(delivery):
    text = delivery.payload.read_text()
    front, body = text[4:].split('---\n', 1)
    data = json.loads(body.split(pack.MARKER)[1][:-len(pack.END)])
    entry = next(e for e in data['files'] if e['name'] == 'data/observation.json')
    entry['text'] = entry['text'].replace('64', '96')
    entry['sha256'] = port.sha(entry['text'].encode())
    entry['bytes'] = len(entry['text'].encode())
    body = body.split(pack.MARKER)[0] + pack.MARKER + json.dumps(data, ensure_ascii=False, indent=2) + pack.END
    import re
    front = re.sub(r'content_sha256: [0-9a-f]{64}', 'content_sha256: ' + port.sha(body.encode()), front)
    delivery.payload.write_text('---\n' + front + '---\n' + body)
    delivery.contract['files'][delivery.payload.name] = reflux.file_ref(delivery.payload)['sha256']
    save(delivery.cp, delivery.contract)
    with pytest.raises(ValueError, match='beyond declared redaction'):
        port.validate_delivery(delivery.cp, delivery.bundle, delivery.material)
