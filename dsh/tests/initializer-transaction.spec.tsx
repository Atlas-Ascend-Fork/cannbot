// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

// @vitest-environment node
import { expect, it } from 'vitest'
import { mkdir, mkdtemp, readFile, writeFile, access, readdir } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { initializeTransaction } from '../src/initializer-transaction.ts'
import type { WorkflowDescriptor } from '../src/content-types.ts'

async function fixture() {
  await mkdir('.acceptance-workflow-tests', { recursive: true })
  const root = await mkdtemp(resolve('.acceptance-workflow-tests/transaction-'))
  const workspace = join(root, 'workspace'), recovery = join(root, 'recovery'), resources = join(root, 'resources')
  await mkdir(join(workspace, '.dsh/skills/shared'), { recursive: true })
  await mkdir(join(workspace, '.dsh/agents'), { recursive: true })
  await mkdir(join(resources, '.claude-plugin'), { recursive: true })
  await writeFile(join(resources, 'agent.md'), '---\nname: reviewer\ndescription: review\n---\n')
  await writeFile(join(resources, '.claude-plugin/plugin.json'), JSON.stringify({ agents: ['./agent.md'] }))
  await writeFile(join(workspace, '.dsh/skills/shared/SKILL.md'), 'old shared skill')
  await writeFile(join(workspace, '.dsh/agents/reviewer.md'), 'old reviewer')
  await writeFile(join(workspace, 'AGENTS.md'), 'user instructions')
  await writeFile(join(workspace, 'user-code.cpp'), 'user code')
  const descriptor = { id: 'flow', skills: [{ name: 'shared' }, { name: 'new-skill' }] } as WorkflowDescriptor
  return { workspace, recovery, resources, descriptor }
}
it('restores shared Skills, agents and user instructions after a partial initialization failure', async () => {
  const f = await fixture()
  await expect(initializeTransaction(f.workspace, f.recovery, f.descriptor, f.resources, async () => {
    await writeFile(join(f.workspace, '.dsh/skills/shared/SKILL.md'), 'partial new skill')
    await mkdir(join(f.workspace, '.dsh/skills/new-skill'))
    await writeFile(join(f.workspace, '.dsh/skills/new-skill/SKILL.md'), 'partial new skill')
    await writeFile(join(f.workspace, '.dsh/agents/reviewer.md'), 'partial agent')
    await writeFile(join(f.workspace, 'AGENTS.md'), 'partial instructions')
    throw new Error('EACCES: cannot copy Skill')
  })).rejects.toThrow('已恢复')
  expect(await readFile(join(f.workspace, '.dsh/skills/shared/SKILL.md'), 'utf8')).toBe('old shared skill')
  expect(await readFile(join(f.workspace, '.dsh/agents/reviewer.md'), 'utf8')).toBe('old reviewer')
  expect(await readFile(join(f.workspace, 'AGENTS.md'), 'utf8')).toBe('user instructions')
  expect(await readFile(join(f.workspace, 'user-code.cpp'), 'utf8')).toBe('user code')
  await expect(access(join(f.workspace, '.dsh/skills/new-skill'))).rejects.toThrow()
  await expect(access(join(f.recovery, 'recovery.json'))).rejects.toThrow()
  expect(await readdir(f.recovery)).toEqual([])
})
it('commits successful initialization without rolling back new resources', async () => {
  const f = await fixture()
  await initializeTransaction(f.workspace, f.recovery, f.descriptor, f.resources, async () => {
    await writeFile(join(f.workspace, '.dsh/skills/shared/SKILL.md'), 'new shared skill')
  })
  expect(await readFile(join(f.workspace, '.dsh/skills/shared/SKILL.md'), 'utf8')).toBe('new shared skill')
  await expect(access(join(f.recovery, 'recovery.json'))).rejects.toThrow()
  expect(await readdir(f.recovery)).toEqual([])
})
it('recovers a previously interrupted initialization before invoking the next installer', async () => {
  const f = await fixture(), directory = join(f.recovery, 'snapshot-crashed')
  await mkdir(directory, { recursive: true })
  await writeFile(join(directory, '0'), 'old instructions before crash')
  await writeFile(join(f.recovery, 'recovery.json'), JSON.stringify({ workspace: f.workspace, directory, entries: [{ path: 'AGENTS.md', present: true, slot: '0' }] }))
  await writeFile(join(f.workspace, 'AGENTS.md'), 'incomplete instructions')
  await initializeTransaction(f.workspace, f.recovery, f.descriptor, f.resources, async () => {
    expect(await readFile(join(f.workspace, 'AGENTS.md'), 'utf8')).toBe('old instructions before crash')
  })
})
