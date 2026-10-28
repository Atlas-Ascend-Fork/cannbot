#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Read-only identity for ordinary ELF32/64 LE/BE section-table containers.

No objcopy, ELF loading, or architecture assumptions. Extended section numbering,
compressed sections and non-ELF device payloads are deliberately unsupported.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from cli_output import emit


class ELFError(ValueError):
    """Unsupported or malformed ELF; no identity may be inferred."""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def out_of_bounds(data, offset, size):
    return offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset


def bounds(data, offset, size, label):
    if out_of_bounds(data, offset, size):
        raise ELFError(f'{label}: offset/length outside file')
    return data[offset:offset + size]


def cstring(data, offset, label):
    if not 0 <= offset < len(data):
        raise ELFError(f'{label}: string offset outside table')
    end = data.find(b'\0', offset)
    if end < 0:
        raise ELFError(f'{label}: unterminated string')
    try:
        return data[offset:end].decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ELFError(f'{label}: non-UTF8 name unsupported') from exc


def parse_elf_header(data):
    if len(data) < 16 or data[:4] != b'\x7fELF':
        raise ELFError('Not an ELF file')
    elf_class, encoding, version = data[4:7]
    if elf_class not in (1, 2) or encoding not in (1, 2) or version != 1:
        raise ELFError('Unsupported ELF class, endianness or version')
    endian = '<' if encoding == 1 else '>'
    header_fmt = endian + ('16sHHIIIIIHHHHHH' if elf_class == 1 else '16sHHIQQQIHHHHHH')
    header_size = struct.calcsize(header_fmt)
    header = struct.unpack(header_fmt, bounds(data, 0, header_size, 'ELF header'))
    if header[3] != 1 or header[8] != header_size:
        raise ELFError('Unsupported ELF header version/size')
    phoff, shoff, phsize, phcount, shsize, count, names_idx = (
        header[5], header[6], header[9], header[10], header[11], header[12], header[13])
    if count == 0 or names_idx == 0xffff or phcount == 0xffff:
        raise ELFError('Extended/missing section numbering unsupported')
    if phcount:
        expected_phsize = 32 if elf_class == 1 else 56
        if phsize != expected_phsize:
            raise ELFError('Unsupported program header size')
        bounds(data, phoff, phsize * phcount, 'program header table')
    layout = dict(phoff=phoff, shoff=shoff, phsize=phsize, phcount=phcount,
                  shsize=shsize, count=count, names_idx=names_idx, header_size=header_size)
    return elf_class, encoding, endian, header, layout


def collect_sections(data, headers, names, occupied):
    sections = []
    for index, h in enumerate(headers):
        name = cstring(names, h[0], f'section {index}')
        if h[2] & 0x800:
            raise ELFError('Compressed sections unsupported')
        # NULL/NOBITS have no file payload. NOBITS offsets need not lie in file.
        payload = b'' if h[1] in (0, 8) else bounds(data, h[4], h[5], name)
        if payload:
            occupied.append((h[4], h[4] + h[5]))
        sections.append(dict(index=index, name=name, type=h[1], flags=h[2],
                             offset=h[4], size=h[5], link=h[6], entsize=h[9], data=payload))
    return sections


def check_section_layout(occupied, sections):
    intervals = sorted(occupied)
    if any(left[1] > right[0] for left, right in zip(intervals, intervals[1:])):
        raise ELFError('Overlapping file sections/header tables unsupported')
    section_names = [s['name'] for s in sections[1:]]
    if len(set(section_names)) != len(section_names):
        raise ELFError('Duplicate section names unsupported')


def build_sections(data, elf_class, endian, layout):
    section_fmt = endian + ('IIIIIIIIII' if elf_class == 1 else 'IIQQQQIIQQ')
    shoff, shsize, count = layout['shoff'], layout['shsize'], layout['count']
    if shsize != struct.calcsize(section_fmt) or not 0 < layout['names_idx'] < count:
        raise ELFError('Unsupported section header size/name table index')
    bounds(data, shoff, shsize * count, 'section header table')
    if shoff < layout['header_size']:
        raise ELFError('Section table overlaps ELF header')
    headers = [struct.unpack_from(section_fmt, data, shoff + i * shsize) for i in range(count)]
    if headers[0][1] != 0:
        raise ELFError('Section zero is not NULL')
    names_header = headers[layout['names_idx']]
    if names_header[1] != 3:
        raise ELFError('Section name table is not STRTAB')
    names = bounds(data, names_header[4], names_header[5], 'section names')
    occupied = [(0, layout['header_size']), (shoff, shoff + shsize * count)]
    if layout['phcount']:
        occupied.append((layout['phoff'], layout['phoff'] + layout['phsize'] * layout['phcount']))
    sections = collect_sections(data, headers, names, occupied)
    check_section_layout(occupied, sections)
    return sections


def table_symbols(table, elf_class, symbol_fmt, symbol_size, strings, count):
    result = []
    for offset in range(0, len(table['data']), symbol_size):
        fields = struct.unpack_from(symbol_fmt, table['data'], offset)
        if elf_class == 1:
            nameoff, value, size, info, other, shndx = fields
        else:
            nameoff, info, other, shndx, value, size = fields
        if shndx == 0xffff:
            raise ELFError('Extended symbol section indices unsupported')
        if shndx < 0xff00 and shndx >= count:
            raise ELFError('Symbol section index outside section table')
        name = cstring(strings, nameoff, 'symbol')
        if name:
            binding = {0: 'LOCAL', 1: 'GLOBAL', 2: 'WEAK'}.get(info >> 4, str(info >> 4))
            result.append(dict(name=name, binding=binding, type=info & 15, visibility=other & 3,
                               section_index=shndx, defined=shndx != 0, value=value, size=size,
                               table=table['name']))
    return result


def build_symbols(sections, elf_class, endian, count):
    symbols = []
    symbol_fmt = endian + ('IIIBBH' if elf_class == 1 else 'IBBHQQ')
    symbol_size = struct.calcsize(symbol_fmt)
    for s in sections:
        if s['type'] not in (2, 11):
            continue
        if s['entsize'] != symbol_size or s['size'] % symbol_size:
            raise ELFError('Unsupported/truncated symbol table entry size')
        if not 0 < s['link'] < count or sections[s['link']]['type'] != 3:
            raise ELFError('Symbol table has invalid string table link')
        strings = sections[s['link']]['data']
        symbols.extend(table_symbols(s, elf_class, symbol_fmt, symbol_size, strings, count))
    return symbols


def parse_elf(data):
    elf_class, encoding, endian, header, layout = parse_elf_header(data)
    sections = build_sections(data, elf_class, endian, layout)
    symbols = build_symbols(sections, elf_class, endian, layout['count'])
    return dict(elf_class=32 if elf_class == 1 else 64,
                endian='little' if encoding == 1 else 'big', machine=header[2],
                sections=sections, symbols=symbols)


def device_entry(name, payload, required_symbols):
    inner = parse_elf(payload)
    text = next((s['data'] for s in inner['sections'] if s['name'] == '.text'), None)
    if not text:
        raise ELFError(f'{name}: missing/non-file/empty inner .text')
    matches = {symbol: [s for s in inner['symbols'] if s['name'] == symbol and s['defined']]
               for symbol in required_symbols}
    if any(not value for value in matches.values()):
        raise ELFError(f'{name}: exact defined device symbol missing')
    entry = dict(sha256=sha(payload), bytes=len(payload),
                 elf_class=inner['elf_class'], endian=inner['endian'],
                 machine=inner['machine'],
                 inner_text=dict(sha256=sha(text), bytes=len(text)),
                 symbols=inner['symbols'], required_symbol_matches=matches)
    return entry, text


def collect_devices(device_sections, by_name, required_symbols):
    devices, files = {}, {}
    for i, name in enumerate(device_sections):
        if name not in by_name or not by_name[name]['data']:
            raise ELFError(f'Missing device section: {name}')
        payload = by_name[name]['data']
        devices[name], text = device_entry(name, payload, required_symbols)
        files[f'device-{i}.elf'] = payload
        files[f'device-{i}.text.bin'] = text
    return devices, files


def identity_result(path, before, outer, devices):
    return dict(schema_version=1, supported_format='ordinary ELF32/64 LE/BE section tables',
                path=str(path.resolve()), input_sha256_before=before, whole_so_sha256=before,
                outer_elf_class=outer['elf_class'], outer_endian=outer['endian'],
                host_symbols=outer['symbols'],
                device_sections={s['name']: dict(sha256=sha(s['data']), bytes=len(s['data']))
                                 for s in outer['sections'] if 'aicore' in s['name'] and s['data']},
                devices=devices)


def write_device_files(path, output, files):
    targets = [output / name for name in (*files, 'identity.json')]
    for target in targets:
        if target.resolve() == path.resolve() or (target.exists() and target.samefile(path)):
            raise ELFError('Output aliases input')
        if target.exists() or target.is_symlink():
            raise ELFError(f'Refusing existing output: {target}')
    output.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        with (output / name).open('xb') as handle:
            handle.write(data)


def inspect_identity(path, device_sections=('.aicore_binary',), required_symbols=(), output=None):
    path = Path(path)
    original = path.read_bytes()
    before = sha(original)
    try:
        outer = parse_elf(original)
        by_name = {s['name']: s for s in outer['sections']}
        devices, files = collect_devices(device_sections, by_name, required_symbols)
        result = identity_result(path, before, outer, devices)
        if output is not None:
            output = Path(output)
            write_device_files(path, output, files)
        after = sha(path.read_bytes())
        if after != before:
            raise ELFError('Input changed during inspection')
        result.update(input_sha256_after=after, input_unchanged=True)
        if output is not None:
            with (output / 'identity.json').open('x') as handle:
                json.dump(result, handle, indent=2)
        return result
    finally:
        if sha(path.read_bytes()) != before:
            raise ELFError('Input changed during inspection')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--device-section', action='append', help='Exact outer section name (repeatable)')
    parser.add_argument('--require-symbol', action='append', default=[], help='Exact defined device symbol')
    parser.add_argument('--output', type=Path, help='Independent directory; existing files refused')
    args = parser.parse_args()
    try:
        result = inspect_identity(args.input, args.device_section or ('.aicore_binary',),
                                  args.require_symbol, args.output)
    except (ELFError, OSError) as exc:
        parser.exit(1, f'Identity rejected: {exc}\n')
    emit(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
