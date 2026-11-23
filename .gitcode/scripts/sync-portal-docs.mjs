// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

// 在 CANNBot 内容仓运行；组合构建只需要挂载 .gitcode/portal。
import { existsSync, mkdirSync, readFileSync, readdirSync, unlinkSync, writeFileSync } from 'node:fs';
import { join, posix } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseYamlLite } from './lib/portal-yaml.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
const portal = join(root, '.gitcode/portal');
const output = join(portal, 'docs/workflows');
const route = '/docs/workflows/';
const cards = parseYamlLite(readFileSync(join(portal, 'home/workflows.yaml'), 'utf8')).cards;
const official = readdirSync(join(root, 'plugins-official'), { withFileTypes: true })
  .filter(entry => entry.isDirectory()).map(entry => entry.name).sort();
const byId = new Map(cards.map(card => [card.id, card]));
const orderedIds = [...new Set([...cards.map(card => card.id), ...official])];
const pages = new Map([['script/docs/cannbot-workflows.md', 'index']]);
const groups = new Map();
function addItem(group, text, id) {
  if (!groups.has(group)) groups.set(group, []);
  groups.get(group).push({ text, link: route + id + '.html' });
}
addItem('入门', '工作流安装与使用', 'index');
for (const id of orderedIds.filter(id => official.includes(id))) {
  const dir = 'plugins-official/' + id;
  const files = readdirSync(join(root, dir));
  const name = files.find(name => name.toLowerCase() === 'quickstart.md') ?? 'README.md';
  pages.set(dir + '/' + name, id);
  const card = byId.get(id);
  addItem(card?.category ?? '其他工作流', card?.title ?? id, id);
}
addItem('算子领域', '算子系统测试', 'ascendc-st-design');

// 保留代码示例。在门户已归档的相对链接指向站内页面，其余链接回到插件目录中的原文件。
function archive(source) {
  const content = readFileSync(join(root, source), 'utf8');
  let fence = '';
  return content.split('\n').map(line => {
    const marker = /^ {0,3}(`{3,}|~{3,})/.exec(line)?.[1];
    if (marker) {
      if (!fence) fence = marker;
      else if (marker.startsWith(fence)) fence = '';
      return line;
    }
    if (fence) return line;
    return line.replace(/\]\(([^\s)]+)\)/g, (match, url) => {
      if (/^(?:[a-z][\w+.-]*:|#|\/)/i.test(url)) return match;
      const [, file, suffix] = /^([^?#]*)(.*)$/.exec(url);
      const target = posix.join(posix.dirname(source), file);
      const page = pages.get(target);
      const href = page ? route + page + '.html' : 'https://gitcode.com/cann/cannbot/blob/master/' + target;
      return '](' + href + suffix + ')';
    });
  }).join('\n').trimEnd() + '\n';
}

const generated = '<!-- 来源文件：';
mkdirSync(output, { recursive: true });
const current = new Set();
for (const [source, id] of pages) {
  const name = id + '.md';
  current.add(name);
  writeFileSync(join(output, name), generated + source + ' -->\n\n' + archive(source));
}
for (const name of readdirSync(output)) {
  if (name.endsWith('.md') && !current.has(name) && readFileSync(join(output, name), 'utf8').startsWith(generated)) {
    unlinkSync(join(output, name));
  }
}
const sidebar = [
  `# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------`,
  '',
  '# 由 .gitcode/scripts/sync-portal-docs.mjs 根据工作流归档生成。',
  "'/docs/':",
];
for (const [group, items] of groups) {
  sidebar.push('  - text: ' + JSON.stringify(group), '    items:');
  for (const { text, link } of items) {
    if (!existsSync(join(portal, link.slice(1).replace(/\.html$/, '.md')))) throw Error('缺少文档 ' + link);
    sidebar.push('      - text: ' + JSON.stringify(text), '        link: ' + link);
  }
}
writeFileSync(join(portal, 'sidebar.yaml'), sidebar.join('\n') + '\n');
