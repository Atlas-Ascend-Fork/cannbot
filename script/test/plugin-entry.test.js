// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import test from "node:test";
import * as entry from "../index.js";

test("OpenCode plugin preserves the legacy factory", async () => {
  assert.equal(typeof entry.CANNBotPlugin, "function");
  assert.deepEqual(await entry.CANNBotPlugin(), {});
  assert.equal(entry.default.server, entry.CANNBotPlugin);
});

test("OpenCode plugin exports a v2 definition", async () => {
  assert.equal(typeof entry.default, "object");
  assert.equal(entry.default.id, "cannbot");
  assert.equal(typeof entry.default.setup, "function");
  await entry.default.setup();
});
