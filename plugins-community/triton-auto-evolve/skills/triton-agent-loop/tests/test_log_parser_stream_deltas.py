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
"""Offline CLI-format deltas and full assistant messages share one transcript."""

import importlib.util
import io
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/log_parser.py"
SPEC = importlib.util.spec_from_file_location("log_parser", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def feed(parser, event):
    parser.feed_line("[sub-agent stdout] " + json.dumps(event))


def stream(parser, event):
    feed(parser, {"type": "stream_event", "event": event})


@pytest.mark.parametrize("kind,label", [("text", "回复"), ("thinking", "思考")])
@pytest.mark.parametrize("assistant_order", ["before_stop", "after_stop", "absent"])
def test_nested_deltas_are_kept_once(kind, label, assistant_order):
    output = io.StringIO()
    parser = MODULE.StreamJsonReadableParser(output)
    stream(parser, {"type": "message_start", "message": {"id": "msg_1"}})
    stream(
        parser,
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": kind, kind: ""},
        },
    )
    for part in ("hello ", "world"):
        stream(
            parser,
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": kind + "_delta", kind: part},
            },
        )
    assistant = {
        "type": "assistant",
        "message": {"id": "msg_1", "content": [{"type": kind, kind: "hello world"}]},
    }
    if assistant_order == "before_stop":
        feed(parser, assistant)
    stream(parser, {"type": "message_stop"})
    if assistant_order == "after_stop":
        feed(parser, assistant)
    parser.flush()
    assert output.getvalue() == f"[{label}] hello world\n"


def test_streamed_thinking_text_and_completed_tool_keep_order():
    output = io.StringIO()
    parser = MODULE.StreamJsonReadableParser(output)
    stream(parser, {"type": "message_start", "message": {"id": "msg_2"}})
    for index, kind, text in [(0, "thinking", "plan"), (1, "text", "answer")]:
        stream(
            parser,
            {
                "type": "content_block_delta",
                "index": index,
                "delta": {"type": kind + "_delta", kind: text},
            },
        )
    feed(
        parser,
        {
            "type": "assistant",
            "message": {
                "id": "msg_2",
                "content": [
                    {"type": "thinking", "thinking": "plan"},
                    {"type": "text", "text": "answer"},
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "x.py"},
                    },
                ],
            },
        },
    )
    stream(parser, {"type": "message_stop"})
    assert (
        output.getvalue() == "[思考] plan\n[回复] answer\n[工具] Read: file_path=x.py\n"
    )


def test_identical_text_in_next_message_is_not_dropped():
    output = io.StringIO()
    parser = MODULE.StreamJsonReadableParser(output)
    stream(parser, {"type": "message_start", "message": {"id": "msg_3"}})
    stream(
        parser,
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "same"},
        },
    )
    stream(parser, {"type": "message_stop"})
    feed(
        parser,
        {
            "type": "assistant",
            "message": {"id": "msg_4", "content": [{"type": "text", "text": "same"}]},
        },
    )
    parser.flush()
    assert output.getvalue() == "[回复] same\n[回复] same\n"
