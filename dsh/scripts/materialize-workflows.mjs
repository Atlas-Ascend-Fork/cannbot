/** Copy the selected working tree and declared Skills into a fresh installation staging directory. */
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync, readdirSync, mkdirSync, rmSync, statSync, copyFileSync, realpathSync, lstatSync, readlinkSync, unlinkSync, renameSync } from 'node:fs'
import { createRequire } from 'node:module'
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
const localRequire = createRequire(import.meta.url)
const { parse } = (() => {
  try { return localRequire('yaml') }
  catch { return createRequire(realpathSync(localRequire.resolve('@deepseek-ai/dsh-skill-filesystem/package.json')))('yaml') }
})()

if (!process.argv[2] || !process.argv[3]) throw new Error('Usage: materialize-workflows.mjs <source> <fresh-output>');
const source = resolve(process.argv[2]);
const target = resolve(process.argv[3]);
if (!source || !target || existsSync(target)) throw new Error('An existing source and a fresh output directory are required');
const project = fileURLToPath(new URL('..', import.meta.url));
const known = JSON.parse(readFileSync(join(project, 'official-plugins.json'), 'utf8'));
const json = path => JSON.parse(readFileSync(path, 'utf8'));
const git = (root, ...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
const skillsSource = join(source, 'vendor/cannbot-skills');
const config = {
  repository:known.repository, commit:git(source,'rev-parse','HEAD'), skillsCommit:git(skillsSource,'rev-parse','HEAD'),
  plugins:readdirSync(join(source,'plugins-official'),{withFileTypes:true})
    .filter(item=>item.isDirectory()&&/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(item.name)
      &&(existsSync(join(source,'plugins-official',item.name,'.claude-plugin/plugin.json'))
        ||existsSync(join(source,'plugins-official',item.name,'skills',item.name,'SKILL.md'))))
    .map(item=>{
      const file=join(source,'plugins-official',item.name,'.claude-plugin/plugin.json');
      const manifest=existsSync(file)?json(file):{name:item.name};
      if(manifest.name!==item.name)throw new Error('Plugin directory and identity differ');
      return {id:item.name,title:known.plugins.find(old=>old.id===item.name)?.title??manifest.displayName??manifest.name};
    }),
};
config.plugins.sort((a,b)=>{ const rank=id=>{const n=known.plugins.findIndex(item=>item.id===id);return n<0?100000:n;};return rank(a.id)-rank(b.id)||a.id.localeCompare(b.id);});
if (!config.plugins.length) throw new Error('No official workflows discovered');
const within = (root, candidate) => { const path = relative(root,candidate); if(path==='..'||path.startsWith(`..${sep}`)||isAbsolute(path)) throw new Error('Resource escapes repository'); };
const links = new Map()
for (const root of [source, skillsSource]) {
  for (const row of execFileSync('git', ['ls-tree', '-r', '--full-tree', '-z', 'HEAD'], { cwd: root, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }).split('\0')) {
    if (!row.startsWith('120000 ')) continue
    const path = resolve(root, row.slice(row.indexOf('\t') + 1))
    links.set(path, resolve(dirname(path), execFileSync('git', ['show', `HEAD:${row.slice(row.indexOf('\t') + 1)}`], {cwd: root, encoding:'utf8'}).trim()))
  }
}
function materialPath(input) {
  let path = resolve(input)
  const visited = new Set()
  for (;;) {
    within(source, path)
    let replaced = false
    for (let cursor = path; cursor !== dirname(cursor); cursor = dirname(cursor)) {
      const link = existsSync(cursor) && lstatSync(cursor).isSymbolicLink()
        ? resolve(dirname(cursor), readlinkSync(cursor)) : links.get(cursor)
      if (link === undefined) continue
      if (visited.has(cursor)) throw new Error(`Symlink cycle: ${input}`)
      visited.add(cursor)
      path = resolve(link, relative(cursor, path))
      replaced = true
      break
    }
    if (!replaced) {
      if (!existsSync(path)) throw new Error(`Missing source resource: ${path}. Prepare the Skills declared by this source before installing.`)
      within(source, realpathSync(path)); return path
    }
  }
}
const ignored = new Set(['.git', '.gitignore', '.npmignore', '.agents', '.claude', '.codex', '.opencode', '.pi', 'node_modules', '__pycache__'])
function copyTree(input, output, ancestors = new Set()) {
  within(target, resolve(output))
  const path = materialPath(input)
  if (statSync(path).isDirectory()) {
    if (ancestors.has(path)) throw new Error(`Directory cycle: ${input}`)
    mkdirSync(output, { recursive: true })
    const next = new Set([...ancestors, path])
    for (const item of readdirSync(path).sort()) {
      if (ignored.has(item) || item.endsWith('.pyc')) continue
      copyTree(join(path, item), join(output, item), next)
    }
  } else {
    mkdirSync(dirname(output), { recursive: true })
    copyFileSync(path, output)
  }
}
function skillId(value) {
  if (typeof value !== 'string' || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value)) throw new Error(`Invalid Skill ID: ${value}`)
  return value
}
function skillInfo(path) {
  const content = readFileSync(path, 'utf8')
  const match = content.match(/^\uFEFF?---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/)
  if (!match) throw new Error(`Skill frontmatter is missing: ${path}`)
  const metadata = parse(match[1])
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(metadata.name) || typeof metadata.description !== 'string' || !metadata.description.trim()) throw new Error(`Invalid Skill identity: ${path}`)
  return metadata
}
function treeHash(root) {
  const hash = createHash('sha256')
  function visit(path) {
    if (statSync(path).isDirectory()) { for (const name of readdirSync(path).sort()) visit(join(path, name)); return }
    hash.update(relative(root, path).split(sep).join('/')); hash.update('\0'); hash.update(readFileSync(path)); hash.update('\0')
  }
  visit(root)
  return hash.digest('hex')
}

mkdirSync(target, { recursive: true })
const plugins = []
const sources = []
for (const plugin of config.plugins) {
  const upstream = join(source, 'plugins-official', plugin.id)
  const output = join(target, plugin.id)
  const sourceManifest = join(upstream, '.claude-plugin/plugin.json')
  const manifest = existsSync(sourceManifest) ? json(sourceManifest) : { name: plugin.id, description: plugin.title }
  const dependencyFile = join(upstream, 'plugin-install.json')
  const installation = existsSync(dependencyFile) ? json(dependencyFile) : {}
  const entrySkill = skillId(installation.entrySkill ?? plugin.id)
  copyTree(upstream, output)
  copyTree(join(source, 'plugins-official/LICENSE'), join(output, 'LICENSE'))
  copyTree(join(skillsSource, 'LICENSE'), join(output, 'SKILLS_LICENSE'))
  const definitionFile = join(upstream, 'plugin-sources.json')
  const definition = existsSync(definitionFile) ? json(definitionFile) : undefined
  if (definition) {
    for (const path of definition.skills) {
      const input = materialPath(resolve(source, definition.skillsRepository, path))
      const destination = join(output, 'skills', basename(input))
      if (!existsSync(join(input, 'SKILL.md'))) throw new Error(`Missing declared Skill: ${input}`)
      copyTree(input, destination)
      if (definition.preserveSkillInvocationPolicy !== true) {
        const skillFile = join(destination, 'SKILL.md')
        writeFileSync(skillFile, readFileSync(skillFile, 'utf8').replace(/^disable-model-invocation:\s*true\s*$/m, 'disable-model-invocation: false'))
      }
    }
  }
  if (plugin.id === 'ops-registry-invoke') {
    const dependencies = json(join(upstream, 'skills/ops-registry-invoke/skills.json'))
    for (const name of dependencies.skills.external.map(skillId)) copyTree(join(skillsSource, 'ops', name), join(output, 'skills', name))
    for (const name of [...dependencies.skills.native, ...dependencies.skills.external].map(skillId)) {
      if (!existsSync(join(output, 'skills', name, 'SKILL.md'))) throw new Error(`Unbundled registry workflow dependency: ${name}`)
    }
  }
  if (plugin.id === 'pypto-op-orchestrator') {
    const dependencyRoot = join(skillsSource, 'plugins-official/pypto-op-orchestrator')
    const assets = json(join(dependencyRoot, 'plugin-assets.json'))
    for (const name of assets.skills.names.map(skillId)) copyTree(join(skillsSource, assets.skills.dir, name), join(output, 'skills', name))
    copyTree(dependencyRoot, join(output, 'dependencies/cannbot-skills/pypto-op-orchestrator'))
  }
  const declaredEntry = (manifest.skills ?? []).map(path => resolve(output, path, 'SKILL.md')).find(path => {
    within(output, path)
    return existsSync(path) && skillInfo(path).name === entrySkill
  })
  if (installation.entrySkill && !declaredEntry) throw new Error(`Declared workflow entry is missing: ${entrySkill}`)
  const entryFile = declaredEntry ?? join(output, 'skills', plugin.id, 'SKILL.md')
  let generatedEntry = false
  if (!existsSync(entryFile)) {
    generatedEntry = true
    mkdirSync(dirname(entryFile), { recursive: true })
    const documents = ['AGENTS.md', 'README.md'].filter(path => existsSync(join(output, path)))
    writeFileSync(entryFile, `---\nname: ${plugin.id}\ndescription: ${JSON.stringify(manifest.description)}\n---\n\n# ${plugin.title}\n\n此入口加载随包的 CANNBot 官方插件 ${plugin.id}。\n先完整读取以下原始插件文档，再按其中的阶段、输入、执行与验收约定处理用户需求：\n\n${documents.map(path => `- [${path}](../../${path})`).join('\n')}\n\n脚本、角色和模板随原插件目录打包。使用安装包中的绝对路径读取资源，补齐原插件要求的运行环境后执行。\n`)
  }
  const skillNames = []
  // Custom initializers register their workspace Skills; only manifest entries are public here.
  const directories = installation.initializer ? manifest.skills ?? []
    : readdirSync(join(output, 'skills'), { withFileTypes: true }).filter(item => item.isDirectory()).map(item => 'skills/' + item.name)
  for (const directory of directories.sort()) {
    const path = resolve(output, directory, 'SKILL.md')
    within(output, path)
    if (!existsSync(path)) continue
    const metadata = skillInfo(path)
    skillNames.push(metadata.name)
    sources.push({ pluginId: plugin.id, originalName: metadata.name, path: relative(target, path).split(sep).join('/'), hash: treeHash(dirname(path)), entry: metadata.name === entrySkill })
  }
  if (!skillNames.includes(entrySkill)) throw new Error(`Workflow entry is not loadable: ${plugin.id}`)
  plugins.push({ ...plugin, version: manifest.version ?? config.commit, description: manifest.description, generatedEntry, skills: skillNames, runtimeDependencies: installation.dependencies ?? [] })
}
const exposedSkills = []
const winners = new Map()
for (const skill of sources) {
  const previous = winners.get(skill.originalName)
  if (!previous) {
    winners.set(skill.originalName, skill)
    skill.name = skill.originalName
    exposedSkills.push(skill)
  } else if (previous.hash === skill.hash) skill.name = previous.name
  else {
    skill.name = `${skill.pluginId}-${skill.originalName}`
    if (exposedSkills.some(item => item.name === skill.name)) throw new Error(`Duplicate public Skill name: ${skill.name}`)
    exposedSkills.push(skill)
  }
}
for (const plugin of plugins) {
  plugin.aliases = Object.fromEntries(sources.filter(skill => skill.pluginId === plugin.id && skill.name !== skill.originalName).map(skill => [skill.originalName, skill.name]))
}
const catalog = { generatedBy: 'cannbot-dsh-vendor', repository: config.repository, commit: config.commit, skillsRepository: 'https://gitcode.com/cann/cannbot-skills.git', skillsCommit: config.skillsCommit, plugins, exposedSkills, skillCopies: sources.length }
writeFileSync(join(target, 'catalog.json'), JSON.stringify(catalog, null, 2) + '\n')
console.log(JSON.stringify({plugins:catalog.plugins.length,skills:catalog.exposedSkills.length}));
