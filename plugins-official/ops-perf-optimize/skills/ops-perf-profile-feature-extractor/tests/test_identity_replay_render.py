# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Offline behavior checks; no NPU, toolchain, profiler or simulator execution."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser

# CPU-only verification: avoid torch's registered NPU backend auto-import.
os.environ['TORCH_DEVICE_BACKEND_AUTOLOAD'] = '0'

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


identity = module('device_identity')
replay = module('replay_evidence')
renderer = module('render_pipeline_trace')


def elf(sections, bits=64, endian='<', symbol=False):
    """Build actual section tables, including optional defined GLOBAL FUNC symbol."""
    if symbol:
        strings = b'\0device_kernel\0device_kernel_suffix\0'
        fmt = endian + ('IBBHQQ' if bits == 64 else 'IIIBBH')
        entry = ((1, 0x12, 0, 1, 0, 4) if bits == 64 else (1, 0, 4, 0x12, 0, 1))
        symtab = bytes(struct.calcsize(fmt)) + struct.pack(fmt, *entry)
        sections = list(sections) + [('.strtab', strings, 3, 0, 0),
                                    ('.symtab', symtab, 2, len(sections) + 1, struct.calcsize(fmt))]
    names = b'\0'
    name_offsets = {}
    for name, *_ in sections + [('.shstrtab', b'', 3, 0, 0)]:
        name_offsets[name] = len(names)
        names += name.encode() + b'\0'
    sections = list(sections) + [('.shstrtab', names, 3, 0, 0)]
    hfmt = endian + ('16sHHIQQQIHHHHHH' if bits == 64 else '16sHHIIIIIHHHHHH')
    sfmt = endian + ('IIQQQQIIQQ' if bits == 64 else 'IIIIIIIIII')
    hsize, ssize = struct.calcsize(hfmt), struct.calcsize(sfmt)
    data, headers = bytearray(hsize), [bytes(ssize)]
    for name, payload, kind, link, entsize in sections:
        offset = len(data)
        data += payload
        headers.append(struct.pack(sfmt, name_offsets[name], kind, 0, 0,
                                   offset, len(payload), link, 0, 1, entsize))
    shoff = len(data)
    data += b''.join(headers)
    ident = b'\x7fELF' + bytes((2 if bits == 64 else 1, 1 if endian == '<' else 2, 1)) + bytes(9)
    data[:hsize] = struct.pack(hfmt, ident, 1, 183, 1, 0, 0, shoff, 0,
                               hsize, 0, 0, ssize, len(headers), len(headers) - 1)
    return bytes(data)


def container(bits=64, endian='<'):
    inner = elf([('.text', b'\x01\x02\x03\x04', 1, 0, 0)], bits, endian, symbol=True)
    return elf([('.aicore_binary', inner, 1, 0, 0),
                ('__aicore_rel_binary', b'opaque-wrapper', 1, 0, 0)], bits, endian)


TRACE = {'displayTimeUnit': 'ns', 'traceEvents': [
    {'ph': 'M', 'name': 'process_name', 'pid': 1, 'args': {'name': 'AIC0_MTE2'}},
    {'ph': 'M', 'name': 'process_name', 'pid': 2, 'args': {'name': 'AIV0_SCALAR_LDST'}},
    {'ph': 'X', 'pid': 1, 'ts': 10.0, 'dur': 2.0, 'name': 'LOAD'},
    {'ph': 'X', 'pid': 1, 'ts': 11.0, 'dur': 2.0, 'name': 'LOAD'},
    {'ph': 'X', 'pid': 2, 'ts': 10.5, 'dur': 0.5, 'name': 'LDST'},
]}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(v for k, v in attrs if k in ('href', 'src'))


class ELFTests(unittest.TestCase):
    def test_outer_nested_exact_symbols_and_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.so'
            for bits, endian in [(64, '<'), (64, '>'), (32, '<'), (32, '>')]:
                original = container(bits, endian)
                path.write_bytes(original)
                result = identity.inspect_identity(path, required_symbols=['device_kernel'])
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(result['input_sha256_before'], result['input_sha256_after'])
                self.assertFalse(result['host_symbols'])  # Host nm need not contain device symbol.
                device = result['devices']['.aicore_binary']
                self.assertEqual(device['elf_class'], bits)
                self.assertEqual(device['inner_text']['sha256'], hashlib.sha256(b'\1\2\3\4').hexdigest())
                self.assertEqual(device['required_symbol_matches']['device_kernel'][0]['binding'], 'GLOBAL')
                with self.assertRaises(identity.ELFError):
                    identity.inspect_identity(path, required_symbols=['device_ker'])
                with self.assertRaises(identity.ELFError):
                    identity.inspect_identity(path, device_sections=['__aicore_rel_binary'])
            receipt = identity.inspect_identity(path, output=Path(tmp) / 'out')
            self.assertEqual((Path(tmp) / 'out/device-0.text.bin').read_bytes(), b'\1\2\3\4')
            self.assertTrue(receipt['input_unchanged'])

    def test_reject_bounds_overlap_format(self):
        original = container()
        malformed = [original[:15], original[:-1]]
        for index, value in [(4, 3), (5, 0), (6, 2)]:
            damaged = bytearray(original)
            damaged[index] = value
            malformed.append(damaged)
        shoff = struct.unpack_from('<Q', original, 40)[0]
        # Truncated section, overlapping header, compressed, extended numbering.
        for where, fmt, value in [(shoff + 64 + 32, '<Q', len(original) + 1),
                                  (shoff + 64 + 24, '<Q', 0),
                                  (shoff + 64 + 8, '<Q', 0x800),
                                  (60, '<H', 0)]:
            damaged = bytearray(original)
            struct.pack_into(fmt, damaged, where, value)
            malformed.append(damaged)
        for data in malformed:
            with self.assertRaises(identity.ELFError):
                identity.parse_elf(data)

    def test_refuse_alias_symlink_hardlink_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.so'
            original = container()
            path.write_bytes(original)
            for kind in ('symlink', 'hardlink', 'existing'):
                out = Path(tmp) / kind
                out.mkdir()
                target = out / 'device-0.elf'
                if kind == 'symlink':
                    target.symlink_to(path)
                elif kind == 'hardlink':
                    os.link(path, target)
                else:
                    target.write_bytes(b'evidence')
                with self.assertRaises(identity.ELFError):
                    identity.inspect_identity(path, output=out)
                self.assertEqual(path.read_bytes(), original)
                self.assertFalse((out / 'device-0.text.bin').exists())


class ReplayTests(unittest.TestCase):
    def test_shared_typed_raw_storage_saved_as_independent_exact_cpu_views(self):
        import torch
        typed = torch.tensor([1.25, -4.5, 0.0], dtype=torch.float32)
        raw = typed.view(torch.uint8)
        self.assertEqual(typed.untyped_storage().data_ptr(), raw.untyped_storage().data_ptr())
        expected = raw.clone()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'truth.pt'
            # Verify the actual mixed-dtype shared-storage trap, then preserve truth
            # before a failing original verifier rather than simulating only ordering.
            with self.assertRaises(RuntimeError):
                torch.save({'typed': typed, 'raw': raw}, Path(tmp) / 'shared.pt')
            original = AssertionError('original output FAIL')

            def verifier():
                self.assertTrue(path.is_file())
                raise original
            with self.assertRaises(AssertionError) as exc:
                replay.preserve_truth_then_verify(
                    lambda: replay.save_cpu_observations(path, {'typed': typed, 'raw': raw}), verifier)
            self.assertIs(exc.exception, original)
            saved = torch.load(path, weights_only=True)
            self.assertTrue(torch.equal(saved['typed'].view(torch.uint8), expected))
            self.assertTrue(torch.equal(saved['raw'], expected))
            self.assertNotEqual(saved['typed'].untyped_storage().data_ptr(), saved['raw'].untyped_storage().data_ptr())
            self.assertEqual(typed.untyped_storage().data_ptr(), raw.untyped_storage().data_ptr())
            typed.fill_(7)
            self.assertTrue(torch.equal(saved['raw'], expected))

    def test_truth_before_original_exception_and_phase_failures(self):
        order = []
        original = AssertionError('MM2 failed')

        def verify():
            order.append('verify')
            raise original
        with self.assertRaises(AssertionError) as exc:
            replay.preserve_truth_then_verify(lambda: order.append('saved'), verify)
        self.assertIs(exc.exception, original)
        self.assertEqual(order, ['saved', 'verify'])
        phases = {name: {'status': 'PASS'} for name in replay.PHASES}
        phases['output_validation'] = {'status': 'FAIL', 'exception': 'original AssertionError'}
        phases['db_persistence']['start_overwrites'] = 10
        phases['user_exit'] = {'status': 'PASS', 'returncode': -11}
        phases['record'] = {'status': 'PASS', 'returncode': 1}
        result = replay.phase_summary(phases)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['phases']['user_exit']['returncode'], -11)
        self.assertEqual(result['phases']['db_persistence']['start_overwrites'], 10)
        self.assertEqual(result['phases']['record']['status'], 'FAIL')
        self.assertEqual(replay.phase_summary({'record': {'status': 'PASS', 'returncode': 0}})['status'], 'unknown')
        self.assertEqual(replay.phase_summary({'target_execution': {'status': 'blocked'}})['status'], 'unknown')


class RendererTests(unittest.TestCase):
    def test_sources_scope_fail_offline_links_and_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            trace = tmp / 'raw.json'
            trace.write_text(json.dumps(TRACE))
            original = trace.read_bytes()
            cases = [('Board', 'full', 'PASS'), ('Simulation', 'cropped', 'FAIL'),
                     ('unknown', 'unknown', 'unknown')]
            for source, scope, status in cases:
                out = tmp / source / 'nested'
                command = [sys.executable, str(SCRIPTS / 'render_pipeline_trace.py'),
                           '--trace', str(trace), '--output', str(out), '--title', 'CPU offline fixture',
                           '--time-unit', 'us', '--source', source, '--scope', scope,
                           '--output-status', status, '--recorded-cores', '0-2', '--reported-cores', '0',
                           '--tool', 'fixture', '--tool-version', '1', '--soc', 'test-soc', '--model', 'test-model',
                           '--case', 'T1', '--kernel', 'device_kernel']
                subprocess.run(command, check=True, capture_output=True, text=True)
                stats = json.loads((out / 'pipeline_stats.json').read_text())
                self.assertEqual(stats['span'], 3.0)  # displayTimeUnit ns does not rescale us.
                self.assertEqual(stats['pipelines'][0]['busy_time'], 3.0)
                self.assertEqual(stats['pipelines'][1]['pipeline'], 'AIV0_SCALAR_LDST')
                self.assertEqual(stats['provenance']['source'], source)
                self.assertEqual(stats['provenance']['output_status'], status)
                for name in ('index.html', 'timeline.html', 'pipeline.svg', 'pipeline_analysis.md'):
                    text = (out / name).read_text()
                    self.assertIn(source, text)
                    self.assertIn('OUTPUT ' + status, text)
                    self.assertIn('scope ' + scope, text)
                if status == 'FAIL':
                    self.assertIn('diagnostic only', (out / 'pipeline.svg').read_text())
                links = Links()
                links.feed((out / 'index.html').read_text())
                self.assertTrue(links.links)
                self.assertTrue(all((out / link).is_file() for link in links.links))
                from PIL import Image
                with Image.open(out / 'pipeline.png') as image:
                    self.assertGreater(image.width, 500)
                    self.assertGreater(len(image.getcolors(image.width * image.height)), 30)
                self.assertEqual((out / 'trace_original.json').read_bytes(), original)
                self.assertEqual(trace.read_bytes(), original)

    def test_scope_subset_reject_unknown_and_legacy_default(self):
        import argparse
        defaults = dict(source='Simulation', tool='unknown', tool_version='unknown', soc='unknown',
                        model='unknown', case='unknown', kernel='unknown', scope='unknown', output_status='unknown')
        with self.assertRaises(ValueError):
            renderer.provenance(argparse.Namespace(**defaults, recorded_cores='0', reported_cores='1'))
        info = renderer.provenance(argparse.Namespace(**defaults, recorded_cores='unknown', reported_cores='all'))
        self.assertTrue(info['core_coverage'].startswith('unknown'))
        self.assertEqual(info['source'], 'Simulation')


if __name__ == '__main__':
    unittest.main()
