// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

import { lstatSync, mkdtempSync, readFileSync, realpathSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const start = "<!-- cannbot:tilelang-op-orchestrator:start -->";
const end = "<!-- cannbot:tilelang-op-orchestrator:end -->";

function readExisting(pluginRoot, destination) {
  let info;
  try {
    info = lstatSync(destination);
  } catch (error) {
    if (error.code === "ENOENT") return { content: "" };
    throw error;
  }
  const canonical = realpathSync(join(pluginRoot, "AGENTS.md"));
  if (info.isSymbolicLink()) {
    let source;
    try {
      source = realpathSync(destination);
    } catch {
      throw new Error(`Cannot merge instruction symlink: ${destination}`);
    }
    if (source === canonical) return { content: "" };
    throw new Error(`Cannot merge instruction symlink owned by another source: ${destination}`);
  }
  if (!info.isFile()) throw new Error(`Instruction entry must be a regular file: ${destination}`);
  if (realpathSync(destination) === canonical) return { sourceFile: true };
  return { content: readFileSync(destination, "utf8"), mode: info.mode & 0o777 };
}

function managedRange(current) {
  const first = current.indexOf(start);
  const last = current.indexOf(end);
  if (first === -1 && last === -1) return null;
  const unique = current.lastIndexOf(start) === first && current.lastIndexOf(end) === last;
  const startLine = first === 0 || current[first - 1] === "\n";
  const endLine = last > 0 && current[last - 1] === "\n";
  const afterStart = current.slice(first + start.length);
  const afterEnd = current.slice(last + end.length);
  if (first === -1 || last < first || !unique || !startLine || !endLine
      || !/^(?:\r?\n)/.test(afterStart) || !/^(?:\r?\n|$)/.test(afterEnd)) {
    throw new Error("Cannot merge TileLang managed block: markers must be unique, ordered and on separate lines");
  }
  const newline = afterEnd.startsWith("\r\n") ? 2 : afterEnd.startsWith("\n") ? 1 : 0;
  return { first, last: last + end.length + newline };
}

function mergeInstructions(current, incoming) {
  const block = `${start}\n${incoming}${incoming.endsWith("\n") ? "" : "\n"}${end}\n`;
  const range = managedRange(current);
  if (range) return current.slice(0, range.first) + block + current.slice(range.last);
  if (current === incoming) return block;
  if (/^---\r?\nname: tilelang-op-orchestrator\r?\n/.test(current)) {
    throw new Error("Cannot merge modified legacy TileLang instructions without managed block markers");
  }
  const separator = !current || current.endsWith("\n\n") ? "" : current.endsWith("\n") ? "\n" : "\n\n";
  return current + separator + block;
}

function renderInstructions(pluginRoot, sharedSkills) {
  let content = readFileSync(join(pluginRoot, "AGENTS.md"), "utf8");
  for (const [from, to] of [
    ["tilelang-ascend/", `${pluginRoot}/tilelang-ascend/`],
    ["../../ops/", `${sharedSkills}/`],
    ["(workflows/", `(${pluginRoot}/workflows/`],
    ["(references/", `(${pluginRoot}/references/`],
  ]) content = content.replaceAll(from, to);
  return content;
}

export function installInstructions(pluginRoot, destination, sharedSkills) {
  const existing = readExisting(pluginRoot, destination);
  if (existing.sourceFile) return;
  const updated = mergeInstructions(existing.content, renderInstructions(pluginRoot, sharedSkills));
  if (updated === existing.content) return;
  const temporary = mkdtempSync(join(dirname(destination), ".tilelang-instructions-"));
  try {
    const staged = join(temporary, "entry");
    writeFileSync(staged, updated, { mode: existing.mode });
    renameSync(staged, destination);
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
}
