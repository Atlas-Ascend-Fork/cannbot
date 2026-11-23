// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

/**
 * 读取门户工作流卡片配置，直接运行归档脚本时无需安装 npm 依赖。
 *
 * 支持的子集（足够覆盖本仓所有 yaml）：
 *   · 注释（整行 / 行尾，`#` 在引号内不算）
 *   · 块状 map / 块状 sequence / 二者嵌套
 *   · 行内 flow：`[a, b]`、`{a: b}`
 *   · 单引号 / 双引号标量、数字、true/false/null/~
 *   · 块标量 `|` `|-` `>` `>-`（按行拼接，不保留折叠语义细节）
 *
 * 不支持：锚点/别名（&a、*a）、多文档（--- 分隔）、显式类型标签（!!str）、复杂 flow 嵌套。
 * 超出子集的语法会报错。
 */

const UNSUPPORTED = ['&', '*', '!!'];

function stripComment(line) {
  let quote = null;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (quote) {
      if (ch === quote) {
        // 单引号里的 '' 是转义的单引号
        if (quote === "'" && line[i + 1] === "'") {
          i += 1;
          continue;
        }
        quote = null;
      } else if (ch === '\\' && quote === '"') {
        i += 1;
      }
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      continue;
    }
    if (ch === '#' && (i === 0 || /\s/.test(line[i - 1]))) return line.slice(0, i);
  }
  return line;
}

/** 切行：保留空行（块标量要用），记录缩进与行号 */
function lex(text, label) {
  const out = [];
  const raw = String(text).replace(/^\uFEFF/, '').split(/\r?\n/);
  for (let n = 0; n < raw.length; n += 1) {
    const line = raw[n];
    if (!line.trim()) {
      out.push({ blank: true, ind: 0, text: '', line: n + 1 });
      continue;
    }
    const spaces = line.match(/^ */)[0].length;
    if (/^ *\t/.test(line)) {
      throw new Error(`${label}: 第 ${n + 1} 行用制表符缩进，YAML 只允许空格`);
    }
    const content = stripComment(line.slice(spaces)).replace(/\s+$/, '');
    if (!content) {
      out.push({ blank: true, ind: 0, text: '', line: n + 1 });
      continue;
    }
    if (UNSUPPORTED.some((p) => content.startsWith(p))) {
      throw new Error(`${label}: 第 ${n + 1} 行使用了内置解析器不支持的 YAML 语法（${content.slice(0, 12)}…）`);
    }
    out.push({ blank: false, ind: spaces, text: content, line: n + 1 });
  }
  return out;
}

/** 跳过空行 */
function skipBlank(L, i) {
  while (i < L.length && L[i].blank) i += 1;
  return i;
}

/** `key: value` 的冒号：引号外、且后面是空白或行尾（所以 https:// 不算） */
function mapColon(text) {
  let quote = null;
  let depth = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quote) {
      if (ch === quote) {
        if (quote === "'" && text[i + 1] === "'") {
          i += 1;
          continue;
        }
        quote = null;
      } else if (ch === '\\' && quote === '"') i += 1;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      continue;
    }
    if (ch === '[' || ch === '{') depth += 1;
    if (ch === ']' || ch === '}') depth -= 1;
    if (ch === ':' && depth === 0 && (i + 1 === text.length || /\s/.test(text[i + 1]))) return i;
  }
  return -1;
}

const isSeqLine = (text) => text === '-' || text.startsWith('- ');

function parseScalar(text, label, line) {
  const raw = text.trim();
  if (!raw) return null;
  // flow 序列/映射必须闭合：`tags: [a, b` 在 js-yaml 下会直接报错（构建失败），
  // 兜底解析器不能把它当成普通字符串放过
  if ((raw.startsWith('[') && !raw.endsWith(']')) || (raw.startsWith('{') && !raw.endsWith('}'))) {
    throw new Error(`${label}: 第 ${line} 行 flow 集合没有闭合：${raw.slice(0, 40)}`);
  }
  if (raw.startsWith('[') && raw.endsWith(']')) {
    return splitFlow(raw.slice(1, -1), label, line).map((part) => parseScalar(part, label, line));
  }
  if (raw.startsWith('{') && raw.endsWith('}')) {
    const obj = {};
    for (const part of splitFlow(raw.slice(1, -1), label, line)) {
      const colon = mapColon(part);
      if (colon < 0) throw new Error(`${label}: 第 ${line} 行 flow map 缺冒号：${part}`);
      obj[unquote(part.slice(0, colon).trim())] = parseScalar(part.slice(colon + 1), label, line);
    }
    return obj;
  }
  if (raw.startsWith('"') && raw.endsWith('"') && raw.length >= 2) {
    return raw
      .slice(1, -1)
      .replace(/\\n/g, '\n')
      .replace(/\\t/g, '\t')
      .replace(/\\"/g, '"')
      .replace(/\\\\/g, '\\');
  }
  if (raw.startsWith("'") && raw.endsWith("'") && raw.length >= 2) {
    return raw.slice(1, -1).replace(/''/g, "'");
  }
  if (raw === 'true' || raw === 'True' || raw === 'TRUE') return true;
  if (raw === 'false' || raw === 'False' || raw === 'FALSE') return false;
  if (raw === 'null' || raw === 'Null' || raw === 'NULL' || raw === '~') return null;
  if (/^-?\d+(\.\d+)?$/.test(raw)) return Number(raw);
  return raw;
}

function unquote(text) {
  const raw = text.trim();
  if (raw.length >= 2 && raw.startsWith("'") && raw.endsWith("'")) return raw.slice(1, -1).replace(/''/g, "'");
  if (raw.length >= 2 && raw.startsWith('"') && raw.endsWith('"')) return raw.slice(1, -1);
  return raw;
}

/** 按顶层逗号切 flow 内容（忽略引号与嵌套括号里的逗号） */
function splitFlow(text, label, line) {
  const parts = [];
  let quote = null;
  let depth = 0;
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quote) {
      if (ch === quote) {
        if (quote === "'" && text[i + 1] === "'") {
          i += 1;
          continue;
        }
        quote = null;
      } else if (ch === '\\' && quote === '"') i += 1;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      continue;
    }
    if (ch === '[' || ch === '{') depth += 1;
    if (ch === ']' || ch === '}') depth -= 1;
    if (ch === ',' && depth === 0) {
      parts.push(text.slice(start, i));
      start = i + 1;
    }
  }
  const tail = text.slice(start);
  if (tail.trim()) parts.push(tail);
  else if (text.trim() === '') return [];
  else throw new Error(`${label}: 第 ${line} 行 flow 序列有悬空逗号`);
  return parts.map((p) => p.trim());
}

const BLOCK_RE = /^[|>][+-]?$/;

/** 块标量：把后续更深缩进（或空行）的行按原样拼起来 */
function readBlockScalar(L, i, ind) {
  const lines = [];
  let j = i;
  let blockInd = null;
  while (j < L.length) {
    const cur = L[j];
    if (cur.blank) {
      lines.push('');
      j += 1;
      continue;
    }
    if (cur.ind <= ind) break;
    if (blockInd == null) blockInd = cur.ind;
    lines.push(cur.text.padStart(cur.text.length + Math.max(0, cur.ind - blockInd), ' '));
    j += 1;
  }
  // 去掉尾部空行（保留内容里的空行）
  while (lines.length && lines[lines.length - 1] === '') lines.pop();
  return [lines.join('\n'), j];
}

/** 解析一个块：map 或 sequence */
function parseBlock(L, i, label) {
  const start = skipBlank(L, i);
  if (start >= L.length) return [null, start];
  const ind = L[start].ind;
  if (L[start].text === '[]') return [[], start + 1];
  if (isSeqLine(L[start].text)) return parseSeq(L, start, ind, label);
  return parseMap(L, L[start], ind, label, start + 1);
}

function parseSeq(L, i, ind, label) {
  const arr = [];
  let j = i;
  while (true) {
    j = skipBlank(L, j);
    if (j >= L.length) break;
    const cur = L[j];
    if (cur.ind !== ind || !isSeqLine(cur.text)) break;

    const afterDash = cur.text.slice(1);
    const rest = afterDash.trim();
    const restCol = cur.ind + 1 + (afterDash.length - afterDash.trimStart().length);

    if (!rest) {
      // `-` 单独一行：值在下一层
      const sub = skipBlank(L, j + 1);
      if (sub < L.length && L[sub].ind > ind) {
        const [value, next] = parseBlock(L, sub, label);
        arr.push(value);
        j = next;
      } else {
        arr.push(null);
        j += 1;
      }
      continue;
    }

    if (BLOCK_RE.test(rest)) {
      const [text, next] = readBlockScalar(L, j + 1, restCol);
      arr.push(text);
      j = next;
      continue;
    }

    if (mapColon(rest) >= 0) {
      // `- key: value`：把这一行当成 restCol 处的 map 首行，后面的续行也归这个 map
      const virtual = { blank: false, ind: restCol, text: rest, line: cur.line };
      const [value, next] = parseMap(L, virtual, restCol, label, j + 1);
      arr.push(value);
      j = next;
      continue;
    }

    arr.push(parseScalar(rest, label, cur.line));
    j += 1;
  }
  return [arr, j];
}

/**
 * 解析一个 map。
 * @param head 首行（`- key: value` 场景下是虚拟行，不是 L 里的真实元素）
 * @param bodyStart 首行之后在 L 里的下标
 */
function parseMap(L, head, ind, label, bodyStart) {
  const obj = {};
  let j = bodyStart;

  const emit = (line, text) => {
    const colon = mapColon(text);
    if (colon < 0) throw new Error(`${label}: 第 ${line} 行不是合法的 key: value：${text}`);
    const key = unquote(text.slice(0, colon));
    if (key in obj) throw new Error(`${label}: 第 ${line} 行 key 重复：${key}`);
    const valueText = text.slice(colon + 1).trim();
    if (!valueText) {
      // 值在下一层（或空）
      const sub = skipBlank(L, j);
      if (sub < L.length && L[sub].ind > ind) {
        const [value, next] = parseBlock(L, sub, label);
        obj[key] = value;
        j = next;
      } else {
        obj[key] = null;
      }
      return;
    }
    if (BLOCK_RE.test(valueText)) {
      const [text2, next] = readBlockScalar(L, j, ind);
      obj[key] = text2;
      j = next;
      return;
    }
    obj[key] = parseScalar(valueText, label, line);
  };

  emit(head.line, head.text);

  while (true) {
    j = skipBlank(L, j);
    if (j >= L.length) break;
    const cur = L[j];
    if (cur.ind !== ind) {
      if (cur.ind > ind) {
        throw new Error(`${label}: 第 ${cur.line} 行缩进不一致（期望 ${ind} 空格，实际 ${cur.ind}）`);
      }
      break;
    }
    if (isSeqLine(cur.text)) break;
    // 先前进到下一行：emit 里的嵌套块解析从这里开始
    j += 1;
    emit(cur.line, cur.text);
  }

  return [obj, j];
}

/**
 * 解析 YAML 文本。
 * @param {string} text
 * @param {string} [label] 报错时用于定位（如文件名）
 */
export function parseYamlLite(text, label = '<yaml>') {
  const L = lex(text, label);
  const start = skipBlank(L, 0);
  if (start >= L.length) return null;
  const [value, end] = parseBlock(L, start, label);
  const rest = skipBlank(L, end);
  if (rest < L.length) {
    throw new Error(`${label}: 第 ${L[rest].line} 行之后还有无法归入结构的内容（缩进 ${L[rest].ind}）`);
  }
  return value;
}
