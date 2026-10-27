# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License).
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Unit tests for the build-warning filter state machine (filter_build_warnings._run_filter).

Pins the observable contract the build pipe relies on: keep-root warnings
pass (deduplicated by file:line:message), errors always pass, foreign-root
warnings are dropped, leading-context/note/continuation lines stay attached
to their block, and ordinary text passes through unchanged.
"""

from __future__ import annotations

import importlib.util
import io
import logging
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "op_template_gen"
    / "multirank_assets"
    / "scripts"
    / "filter_build_warnings.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "_filter_build_warnings_under_test", _SCRIPT
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_FILTER = _load_module()


def _run(text: str, keep_roots) -> str:
    """Run the filter on `text`, returning everything it logged."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    logger = _FILTER.log
    old_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        run_filter = getattr(_FILTER, "_run_filter")  # private helper driven directly
        run_filter(io.StringIO(text), keep_roots)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    return buf.getvalue()


def _sample_build_output(keep: Path) -> str:
    """A representative cmake/clang pipe: foreign warning + leading context,
    a keep warning (repeated twice more), an error, a note, ordinary text,
    and a foreign libc warning."""
    return (
        "In file included from /usr/local/Ascend/ascendc/foo.h:1,\n"
        f"                 from {keep}/op_host/op.cpp:2:\n"
        "/usr/local/Ascend/ascendc/foo.h:10:5: warning: unused variable 'x' [-Wunused-variable]\n"
        f"{keep}/op_host/op.cpp:3:9: warning: comparison of integer expressions of different signedness\n"
        f" {keep}/op_host/op.cpp:2:10: note: in expansion of macro 'CHECK'\n"
        f"{keep}/op_host/op.cpp:3:9: warning: comparison of integer expressions of different signedness\n"
        "/usr/include/bar.h:7:1: error: expected ';' before 'return'\n"
        f"{keep}/op_kernel/k.cpp:5:2: note: in expansion of macro 'M'\n"
        "Scanning dependencies of target cust_opapi\n"
        "/usr/include/stddef.h:9:1: warning: some libc-level warning\n"
        f"{keep}/op_host/op.cpp:3:9: warning: comparison of integer expressions of different signedness\n"
    )


def test_filter_contract(tmp_path):
    keep = tmp_path / "prj-demo_op"
    keep.mkdir()
    out = _run(_sample_build_output(keep), [str(keep)])

    # keep-root warning passes exactly once (dedup by file:line:message)
    assert out.count("comparison of integer expressions") == 1
    # its note/continuation lines stay attached to the emitted block
    assert "in expansion of macro 'CHECK'" in out
    # errors always pass, with their own trailing note attached
    assert "expected ';' before 'return'" in out
    assert "in expansion of macro 'M'" in out
    # foreign-root warnings are dropped entirely (with their leading context)
    assert "unused variable 'x'" not in out
    assert "some libc-level warning" not in out
    assert "In file included from /usr/local/Ascend" not in out
    # ordinary build text passes through
    assert "Scanning dependencies of target cust_opapi" in out


def test_dedup_is_per_file_line_message(tmp_path):
    keep = tmp_path / "k"
    keep.mkdir()
    text = (
        f"{keep}/a.cpp:1:1: warning: same message\n"
        f"{keep}/a.cpp:1:1: warning: same message\n"
        f"{keep}/a.cpp:2:1: warning: same message\n"
        f"{keep}/b.cpp:1:1: warning: same message\n"
    )
    out = _run(text, [str(keep)])
    assert out.count("same message") == 3  # a:1, a:2, b:1 — line/file vary


def test_errors_are_never_deduplicated(tmp_path):
    keep = tmp_path / "k"
    keep.mkdir()
    text = f"{keep}/a.cpp:1:1: error: boom\n{keep}/a.cpp:1:1: error: boom\n"
    out = _run(text, [str(keep)])
    assert out.count("error: boom") == 2


def test_foreign_error_still_passes(tmp_path):
    keep = tmp_path / "k"
    keep.mkdir()
    text = "/usr/include/x.h:1:1: error: foreign failure\n"
    out = _run(text, [str(keep)])
    assert "foreign failure" in out


def test_warning_block_continuation_lines_travel_with_block(tmp_path):
    keep = tmp_path / "k"
    keep.mkdir()
    text = (
        f"{keep}/a.cpp:1:1: warning: multi-line block\n"
        "  with an indented continuation detail\n"
        f"{keep}/a.cpp:2:1: warning: next block\n"
    )
    out = _run(text, [str(keep)])
    assert "multi-line block" in out
    assert "with an indented continuation detail" in out
    assert "next block" in out


def test_under_prefix_guard():
    under = getattr(_FILTER, "_under")  # private helper exercised directly
    # /a/op must NOT count as under /a/op_kernel (the os.sep guard)
    assert not under("/data/prj-x/op.cpp", "/data/prj-x/op_kern")
    assert under("/data/prj-x/op.cpp", "/data/prj-x")
    assert under("/data/prj-x", "/data/prj-x")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
