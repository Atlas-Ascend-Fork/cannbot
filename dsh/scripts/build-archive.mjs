/** Read the regular files in GitHub's source ZIP without Windows symlink privileges. */
import { crc32, inflateRawSync } from 'node:zlib'
import { mkdir, writeFile } from 'node:fs/promises'
import { dirname, isAbsolute, join } from 'node:path'

export async function extractSourceZip(bytes, destination) {
  let end = -1
  for (let offset = bytes.length - 22; offset >= Math.max(0, bytes.length - 65557); offset--) {
    if (bytes.readUInt32LE(offset) === 0x06054b50 && offset + 22 + bytes.readUInt16LE(offset + 20) === bytes.length) { end = offset; break }
  }
  if (end < 0 || bytes.readUInt16LE(end + 4) || bytes.readUInt16LE(end + 6)) throw new Error('Invalid or multi-volume source ZIP')
  const count = bytes.readUInt16LE(end + 10), centralSize = bytes.readUInt32LE(end + 12), centralOffset = bytes.readUInt32LE(end + 16)
  if (count === 0xffff || centralOffset + centralSize > end) throw new Error('Unsupported source ZIP layout')
  let offset = centralOffset, root, total = 0
  const entries = [], names = new Set()
  for (let index = 0; index < count; index++) {
    if (offset + 46 > end || bytes.readUInt32LE(offset) !== 0x02014b50) throw new Error('Invalid source ZIP directory')
    const flags = bytes.readUInt16LE(offset + 8), method = bytes.readUInt16LE(offset + 10), crc = bytes.readUInt32LE(offset + 16)
    const compressed = bytes.readUInt32LE(offset + 20), size = bytes.readUInt32LE(offset + 24), length = bytes.readUInt16LE(offset + 28)
    const extra = bytes.readUInt16LE(offset + 30), comment = bytes.readUInt16LE(offset + 32), attributes = bytes.readUInt32LE(offset + 38), local = bytes.readUInt32LE(offset + 42)
    if (offset + 46 + length + extra + comment > end) throw new Error('Truncated source ZIP directory')
    const name = bytes.subarray(offset + 46, offset + 46 + length).toString('utf8'), parts = name.replace(/\/$/, '').split('/')
    if (isAbsolute(name) || /[\\:\0]/.test(name) || parts.some(part => !part || part === '.' || part === '..')) throw new Error('Unsafe source ZIP path')
    root ??= parts[0]
    if (parts[0] !== root || names.has(name.toLowerCase())) throw new Error('Conflicting source ZIP paths')
    names.add(name.toLowerCase())
    offset += 46 + length + extra + comment
    // Upstream POSIX-only fixture links are irrelevant to the client build preset.
    if (name.endsWith('/') || ((attributes >>> 16) & 0o170000) === 0o120000) continue
    if (parts.length < 2 || (flags & 1) || ![0, 8].includes(method) || size > 128 * 1024 * 1024 || (total += size) > 768 * 1024 * 1024) throw new Error('Unsupported or oversized source ZIP entry')
    if (local + 30 > centralOffset || bytes.readUInt32LE(local) !== 0x04034b50) throw new Error('Invalid source ZIP file header')
    const start = local + 30 + bytes.readUInt16LE(local + 26) + bytes.readUInt16LE(local + 28)
    if (start + compressed > centralOffset) throw new Error('Truncated source ZIP file')
    entries.push({ path: join(destination, ...parts.slice(1)), start, compressed, size, method, crc })
  }
  if (!entries.length || offset !== centralOffset + centralSize) throw new Error('Empty or inconsistent source ZIP')
  // Validate all names before creating files. No archive entry may create a link.
  for (const entry of entries) {
    const input = bytes.subarray(entry.start, entry.start + entry.compressed)
    const output = entry.method === 0 ? input : inflateRawSync(input, { maxOutputLength: Math.max(1, entry.size) })
    if (output.length !== entry.size || crc32(output) !== entry.crc) throw new Error('Source ZIP checksum mismatch')
    await mkdir(dirname(entry.path), { recursive: true })
    await writeFile(entry.path, output, { flag: 'wx' })
  }
}
