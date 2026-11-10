// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// Licensed under the CANN Open Software License Agreement Version 2.0.
import { execFile } from 'node:child_process'
import { cp, readFile, readdir, realpath, unlink, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

/** Keep this adapter with the run snapshot; the host continues to own native children. */
export async function prepareRun(options) {
  const work = await realpath(options.cwd)
  const context = await readFile(join(work, 'context.json'), 'utf8').then(JSON.parse).catch(error => {
    if (error.code === 'ENOENT') throw new Error('Prepare context.json with ops-direct-invoke tools/workspace.py before starting this workflow')
    throw error
  })
  if (context.plugin !== 'ops-direct-invoke' || options.workflow !== context.plugin) throw new Error('Workflow directory belongs to another plugin')
  const root = await realpath(context.plugin_root)
  if (root !== join(work, '.context/plugin')) throw new Error('Frozen plugin root must stay inside this workflow')
  const adapter = join(root, 'tools/dsh-native.mjs')
  if (await realpath(fileURLToPath(import.meta.url)) !== adapter) {
    return (await import(pathToFileURL(adapter).href)).prepareRun(options)
  }
  const invoke = (args, request, signal) => new Promise((accept, reject) => {
    const child = execFile('python3', ['-B', join(root, 'tools/dsh_context.py'), '--work-dir', work, ...args],
      { encoding: 'utf8', maxBuffer: 4 * 1024 * 1024, signal }, (error, stdout, stderr) => {
        if (error) { reject(new Error(stderr.trim() || error.message)); return }
        try { accept(JSON.parse(stdout)) } catch (failure) { reject(failure) }
      })
    child.stdin.on('error', () => {})
    child.stdin.end(request ? JSON.stringify(request) : '')
  })
  const { runner } = await invoke(['--yaml', options.yaml], null, options.signal)
  return { runner, prepareNode: (request, signal) => invoke([], request, signal) }
}

/** Independent DSH packages carry the original performance plugin for local initialization. */
export async function bundleResources({ assets, directory }) {
  const target = join(directory, 'upstream/dist/plugins/ops-perf-optimize')
  await cp(join(assets, 'ops-perf-optimize'), target, { recursive: true })
  await unlink(join(target, 'plugin-sources.json')).catch(error => { if (error.code !== 'ENOENT') throw error })
  const path = join(target, '.claude-plugin/plugin.json')
  const manifest = JSON.parse(await readFile(path, 'utf8'))
  manifest.skills = []
  for (const item of await readdir(join(target, 'skills'), { withFileTypes: true })) {
    if (!item.isDirectory()) continue
    try { await readFile(join(target, 'skills', item.name, 'SKILL.md')); manifest.skills.push('./skills/' + item.name) }
    catch (error) { if (error.code !== 'ENOENT') throw error }
  }
  delete manifest.dependencies
  await writeFile(path, JSON.stringify(manifest, null, 2) + '\n')
}
