// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT

import { createInterface, cursorTo, emitKeypressEvents, moveCursor } from "node:readline";
import { PassThrough } from "node:stream";

async function lineQuestion(prompt, input, output) {
  const terminal = createInterface({ input, output });
  try {
    return await new Promise((resolve, reject) => {
      const cancel = () => reject(new Error("初始化已取消，未保存本次选择。"));
      terminal.once("SIGINT", cancel);
      terminal.once("close", cancel);
      terminal.question(prompt, resolve);
    });
  } finally {
    terminal.close();
  }
}

export class QuestionnaireScreen {
  constructor(output = process.stdout) {
    this.output = output;
    this.answers = [];
    this.body = "";
    if (process.env.TERM !== "dumb") {
      this.input = new PassThrough();
      this.display = createInterface({ input: this.input, output, terminal: true });
    }
  }

  content(body) {
    return [...this.answers, body].filter(Boolean).join("\n");
  }

  show(body) {
    this.body = body;
    if (this.display) {
      this.display.setPrompt(this.content(body));
      this.display.prompt();
    }
  }

  answer(prompt, value) {
    const line = `${prompt.replace(/[？?]$/, "：")}${value}`;
    this.answers.push(line);
    if (this.display) this.show("");
    else this.output.write(line + "\n");
  }

  close() {
    this.output.write("\n");
    this.display?.close();
    this.input?.destroy();
  }
}

async function readKeys(input, handle) {
  const wasRaw = Boolean(input.isRaw);
  const wasFlowing = input.readableFlowing;
  let onKey;
  let onEnd;
  try {
    return await new Promise((resolve, reject) => {
      onEnd = () => reject(new Error("初始化已取消，未保存本次选择。"));
      onKey = (text, key = {}) => {
        if (key.ctrl && (key.name === "c" || key.name === "d")) return onEnd();
        handle(text, key, (value) => { input.removeListener("keypress", onKey); resolve(value); });
      };
      emitKeypressEvents(input);
      input.on("keypress", onKey);
      input.once("end", onEnd);
      input.setRawMode(true);
      input.resume();
    });
  } finally {
    input.removeListener("keypress", onKey);
    input.removeListener("end", onEnd);
    input.setRawMode(wasRaw);
    if (wasFlowing !== true) input.pause();
  }
}

export async function textQuestion(prompt, { input = process.stdin, output = process.stdout, screen, initial = "" } = {}) {
  if (!screen?.display) return lineQuestion(`${prompt}\n> `, input, output);
  const display = screen.display;
  let finish;
  let rows;
  const result = readKeys(input, (text, key, resolve) => {
    finish = resolve;
    if (key.name === "return" || key.name === "enter") {
      display.write(null, { ctrl: true, name: "e" });
      rows = display.getCursorPos().rows;
    }
    display.write(text, key);
  });
  display.question(`${screen.content(prompt)}\n> `, (value) => {
    // Readline's Enter clears its row tracking and moves down one line. Return
    // to the frame's top before drawing the next question or answer summary.
    moveCursor(output, 0, -(rows + 1));
    cursorTo(output, 0);
    finish(value);
  });
  // Offer a previous value as editable input instead of asking from a blank line.
  if (initial) display.write(initial);
  return result;
}

export async function selectChoice(prompt, labels, { input = process.stdin, output = process.stdout, initial = 0, screen } = {}) {
  if (process.env.TERM === "dumb") {
    return lineQuestion(`${prompt}\n${labels.map((label, index) => `${index + 1}. ${label}`).join("\n")}\n请输入数字：`, input, output);
  }
  // Readline renders wrapped Chinese labels and handles terminal resizing. Its
  // input stays separate so arrow keys select options instead of editing text.
  const displayInput = screen ? null : new PassThrough();
  const display = screen?.display ?? createInterface({ input: displayInput, output, terminal: true });
  const show = (body) => {
    if (screen) screen.show(body);
    else { display.setPrompt(body); display.prompt(); }
  };
  let selected = initial;
  let message = "↑/↓ 移动，数字跳转，回车确认，Ctrl+C 取消";
  const render = () => {
    const options = labels.map((label, index) => index === selected
      ? `\x1b[1;32m❯ ${index + 1}. ${label}\x1b[0m` : `  ${index + 1}. ${label}`);
    show([prompt, ...options, message].join("\n"));
  };
  try {
    const result = readKeys(input, (text, key, resolve) => {
        if (key.name === "return" || key.name === "enter") {
          show(`${prompt.replace(/[？?]$/, "：")}\x1b[1;32m${labels[selected]}\x1b[0m`);
          return resolve(String(selected + 1));
        }
        if (key.name === "up") selected = (selected + labels.length - 1) % labels.length;
        else if (key.name === "down") selected = (selected + 1) % labels.length;
        else if (/^[1-9]$/.test(text ?? "") && Number(text) <= labels.length) selected = Number(text) - 1;
        else {
          message = `输入无效，请用 ↑/↓ 或数字 1–${labels.length} 选择，再按回车。`;
          render();
          return;
        }
        message = "↑/↓ 移动，数字跳转，回车确认，Ctrl+C 取消";
        render();
    });
    render();
    return await result;
  } finally {
    if (!screen) {
      output.write("\n");
      display.close();
      displayInput.destroy();
    }
  }
}
