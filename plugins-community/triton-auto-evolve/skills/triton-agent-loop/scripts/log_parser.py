#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Parse Claude Code CLI --output-format=stream-json into a human-readable log.

Adapted from the MCTS sub-agent launcher approach so that a running round can
be observed in real time without blocking on the sub-process.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

logger = logging.getLogger(__name__)


def _strip_prefix(line: str) -> str:
    for prefix in ("[sub-agent stdout] ", "[sub-agent stderr] "):
        if line.startswith(prefix):
            start = len(prefix)
            return line[start:]
    return line


def _try_json(data: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(data)
    except Exception:
        return None


def _format_tool_result(result: Any) -> str:
    if result is None:
        return "(无结果)"
    if isinstance(result, str):
        return result.strip()[:500]
    if isinstance(result, dict):
        if result.get("error"):
            return f"[错误] {result['error']}"
        if "output" in result:
            return str(result["output"]).strip()[:500]
        if "content" in result:
            return str(result["content"]).strip()[:500]
        return json.dumps(result, ensure_ascii=False)[:500]
    return str(result).strip()[:500]


def _tool_input_summary(name: str, inp: Any) -> str:
    if not inp:
        return ""
    if name == "Bash":
        cmd = inp.get("command", "") if isinstance(inp, dict) else ""
        desc = inp.get("description", "") if isinstance(inp, dict) else ""
        parts = []
        if desc:
            parts.append(desc)
        if cmd:
            parts.append(cmd)
        return " | ".join(parts)
    if name in ("Read", "Write", "Edit", "Glob", "Grep"):
        pairs = []
        for k, v in inp.items():
            if isinstance(v, str):
                pairs.append(f"{k}={v}")
            else:
                pairs.append(f"{k}={json.dumps(v, ensure_ascii=False)}")
        return " | ".join(pairs)
    pairs = []
    for k, v in inp.items():
        pairs.append(f"{k}={v}")
    return " | ".join(pairs)


class StreamJsonReadableParser:
    """Incremental parser for Claude Code CLI stream-json events.

    Writes a human-readable summary ([思考]/[回复]/[工具]/[结果]) to *out* as
    events arrive, so observers can tail the round log while the sub-agent is
    still running.
    """

    def __init__(self, out: TextIO) -> None:
        self.out = out
        self.thinking_buffer: List[str] = []
        self.text_buffer: List[str] = []
        self._stream_message_id: Optional[str] = None
        self._streamed_blocks: Dict[int, Dict[str, str]] = {}

    def feed_line(self, line: str) -> None:
        stripped = _strip_prefix(line).strip()
        if not stripped:
            return
        if stripped.startswith("#") or stripped.startswith("-"):
            return

        event = _try_json(stripped)
        if event is None:
            self.out.write(f"[原始] {stripped}\n")
            self.out.flush()
            return

        etype = event.get("type")

        if etype == "assistant":
            self._handle_assistant(event.get("message", {}))
            return

        if etype == "user":
            msg = event.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "tool_result":
                    self._write_result(block.get("content"))
            return

        if etype == "system":
            return

        if etype == "stream_event":
            self._handle_stream_event(event)

    def flush(self) -> None:
        self._flush_thinking()
        self._flush_text()

    def _handle_assistant(self, msg: Dict[str, Any]) -> None:
        for index, block in enumerate(msg.get("content", [])):
            btype = block.get("type")
            if btype == "tool_use":
                self._write_tool(block.get("name", ""), block.get("input", {}))
            elif btype in ("text", "thinking"):
                text = self._completed_block_suffix(msg, index, block)
                if text.strip():
                    buffer = (
                        self.text_buffer if btype == "text" else self.thinking_buffer
                    )
                    buffer.append(text)

    def _flush_thinking(self) -> None:
        if self.thinking_buffer:
            text = "".join(self.thinking_buffer).strip()
            if text:
                self.out.write(f"[思考] {text}\n")
                self.out.flush()
            self.thinking_buffer = []

    def _flush_text(self) -> None:
        if self.text_buffer:
            text = "".join(self.text_buffer).strip()
            if text:
                self.out.write(f"[回复] {text}\n")
                self.out.flush()
            self.text_buffer = []

    def _write_tool(self, name: str, inp: Any) -> None:
        self._flush_thinking()
        self._flush_text()
        self.out.write(f"[工具] {name}: {_tool_input_summary(name, inp)}\n")
        self.out.flush()

    def _write_result(self, result: Any) -> None:
        self._flush_thinking()
        self._flush_text()
        self.out.write(f"[结果] {_format_tool_result(result)}\n")
        self.out.flush()

    def _completed_block_suffix(
        self, msg: Dict[str, Any], index: int, block: Dict[str, Any]
    ) -> str:
        kind = block.get("type")
        text = block.get(kind, "")
        streamed = self._streamed_blocks.get(index, {})
        if msg.get("id") != self._stream_message_id or streamed.get("type") != kind:
            return text
        previous = streamed.get("text", "")
        start = len(previous)
        return text[start:] if text.startswith(previous) else text

    def _handle_stream_event(self, event: Dict[str, Any]) -> None:
        se = event.get("event", {})
        stype = se.get("type")

        if stype == "message_start":
            self._stream_message_id = se.get("message", {}).get("id")
            self._streamed_blocks = {}
        elif stype == "content_block_start":
            block = se.get("content_block", {})
            self._append_stream_block(
                se.get("index", 0),
                block.get("type", ""),
                block.get(block.get("type", ""), ""),
            )
        elif stype == "content_block_delta":
            delta = se.get("delta", {})
            dtype = delta.get("type")
            if dtype == "text_delta":
                self._append_stream_block(
                    se.get("index", 0), "text", delta.get("text", "")
                )
            elif dtype == "thinking_delta":
                self._append_stream_block(
                    se.get("index", 0), "thinking", delta.get("thinking", "")
                )
        elif stype == "thinking_delta":
            delta = se.get("thinking", "")
            if delta:
                self.thinking_buffer.append(delta)
        elif stype == "text":
            delta = se.get("text", "")
            if delta:
                self.text_buffer.append(delta)
        elif stype == "message_stop":
            self._flush_thinking()
            self._flush_text()

    def _append_stream_block(self, index: int, kind: str, text: str) -> None:
        if kind not in ("text", "thinking"):
            return
        block = self._streamed_blocks.setdefault(index, {"type": kind, "text": ""})
        block["text"] += text
        if text:
            buffer = self.text_buffer if kind == "text" else self.thinking_buffer
            buffer.append(text)


def parse_stream_json_log(raw_path: str, readable_path: str) -> None:
    if not raw_path or not readable_path:
        return
    if not Path(raw_path).exists():
        return
    os.makedirs(os.path.dirname(readable_path), exist_ok=True)
    with (
        open(raw_path, "r", encoding="utf-8") as f_in,
        open(readable_path, "w", encoding="utf-8") as f_out,
    ):
        parser = StreamJsonReadableParser(f_out)
        for line in f_in:
            parser.feed_line(line)
        parser.flush()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if len(sys.argv) < 3:
        logger.error("Usage: python log_parser.py <raw.log> <readable.log>")
        sys.exit(1)
    parse_stream_json_log(sys.argv[1], sys.argv[2])
    logger.info("Parsed %s -> %s", sys.argv[1], sys.argv[2])
