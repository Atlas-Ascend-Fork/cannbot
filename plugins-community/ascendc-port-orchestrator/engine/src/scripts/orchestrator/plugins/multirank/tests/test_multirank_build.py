# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Unit tests for multirank_build.py.

No real cmake/msopgen — pure helpers + wrapper back-fill verified against an
inline autogen-header fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent))

from ..patches import multirank_build as m  # noqa: E402


def test_split_top_level():
    assert getattr(m, "_split_top_level")("a, b, c") == ["a", " b", " c"]
    # comma inside parens must NOT split
    assert getattr(m, "_split_top_level")("a, f(int, x), c") == [
        "a",
        " f(int, x)",
        " c",
    ]


def test_param_names():
    assert (
        getattr(m, "_param_names")(
            "const aclTensor *x, uint64_t *workspaceSize, aclOpExecutor **executor"
        )
        == "x, workspaceSize, executor"
    )
    assert getattr(m, "_param_names")("void") == ""
    assert (
        getattr(m, "_param_names")(
            "void *workspace, uint64_t workspaceSize, aclOpExecutor *executor, aclrtStream stream"
        )
        == "workspace, workspaceSize, executor, stream"
    )


def test_backfill_wrapper_extracts_signature(tmp_path):
    op, op_pascal = "all_reduce", "AllReduce"
    autogen = tmp_path / ".build" / "autogen"
    autogen.mkdir(parents=True)
    (autogen / f"aclnn_{op}.h").write_text(
        "aclnnStatus aclnnInnerAllReduceGetWorkspaceSize(const aclTensor *x, "
        "uint64_t *workspaceSize, aclOpExecutor **executor);\n"
        "aclnnStatus aclnnInnerAllReduce(void *workspace, uint64_t workspaceSize, "
        "aclOpExecutor *executor, aclrtStream stream);\n",
        encoding="utf-8",
    )
    wrap = tmp_path / "op_host" / "wrapper" / f"aclnn_{op}.cpp"
    wrap.parent.mkdir(parents=True)
    wrap.write_text("placeholder", encoding="utf-8")

    ok = m.backfill_wrapper(tmp_path, tmp_path / ".build", op, op_pascal)
    assert ok is True
    r = wrap.read_text()
    # public symbol carries the autogen param list
    assert (
        "aclnnAllReduceGetWorkspaceSize(const aclTensor *x, uint64_t *workspaceSize, "
        "aclOpExecutor **executor)"
    ) in r
    # forwards to Inner with bare arg names
    assert "aclnnInnerAllReduceGetWorkspaceSize(x, workspaceSize, executor)" in r
    assert "aclnnInnerAllReduce(workspace, workspaceSize, executor, stream)" in r
    # HCCL server-type hook retained
    assert "NnopbaseSetHcclServerType(executor, NNOPBASE_HCCL_SERVER_TYPE_MTE)" in r


def test_backfill_wrapper_missing_autogen(tmp_path):
    # no .build/autogen/aclnn_<op>.h -> returns False (rename/opbuild did not run)
    assert (
        m.backfill_wrapper(tmp_path, tmp_path / ".build", "all_reduce", "AllReduce")
        is False
    )


def test_find_artifacts(tmp_path):
    bd = tmp_path / ".build" / "op_host"
    bd.mkdir(parents=True)
    for name in (
        "libcust_opapi.so",
        "libcust_opsproto_rt2.0.so",
        "libcust_opmaster_rt2.0.so",
    ):
        (bd / name).write_text("", encoding="utf-8")
    arts = m.find_artifacts(tmp_path / ".build")
    assert all(p is not None for p in arts.values())
    assert arts["libcust_opapi.so"].name == "libcust_opapi.so"


# ---------------------------------------------------------------------------
# install: cmake --target binary then --target install (kernel binary is NOT an
# auto-built install dep, so it must be built first — mirrors build.sh)
# ---------------------------------------------------------------------------
def test_install_target_invokes_binary_then_install(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    m.install_target(tmp_path / ".build", env={}, jobs=4)
    assert len(calls) == 2
    targets = [cmd[cmd.index("--target") + 1] for cmd in calls]
    assert targets == ["binary", "install"]
    for cmd in calls:
        assert cmd[0] == "cmake"
        assert "--build" in cmd
        assert str(tmp_path / ".build") in cmd
        assert "-j4" in cmd


def test_find_kernel_binary_locator(tmp_path):
    bd = tmp_path / ".build"
    op, unit = "mat_mul_all_reduce", "ascend910b"
    op_bin = bd / "op_kernel" / "binary" / unit / op
    op_bin.mkdir(parents=True)
    (op_bin / "MatMulAllReduce_deadbeef.o").write_text("", encoding="utf-8")
    (op_bin / "MatMulAllReduce_deadbeef.json").write_text("", encoding="utf-8")
    cfg = bd / "op_kernel" / "binary" / "config" / unit
    cfg.mkdir(parents=True)
    (cfg / "binary_info_config.json").write_text("", encoding="utf-8")
    npu = bd / "op_kernel" / "tbe" / "op_info_cfg" / "ai_core"
    npu.mkdir(parents=True)
    (npu / "npu_supported_ops.json").write_text("", encoding="utf-8")

    r = m.find_kernel_binary(bd, op, unit)
    assert r["obj"].name == "MatMulAllReduce_deadbeef.o"
    assert r["meta"].name == "MatMulAllReduce_deadbeef.json"
    assert r["binary_info_config"].name == "binary_info_config.json"
    assert r["npu_supported_ops"].name == "npu_supported_ops.json"


def test_find_kernel_binary_raises_on_zero(tmp_path):
    bd = tmp_path / ".build" / "op_kernel" / "binary" / "ascend910b" / "no_op"
    bd.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="kernel binary not found"):
        m.find_kernel_binary(tmp_path / ".build", "no_op", "ascend910b")


def test_find_kernel_binary_raises_on_multiple(tmp_path):
    bd = tmp_path / ".build" / "op_kernel" / "binary" / "ascend910b" / "op"
    bd.mkdir(parents=True)
    (bd / "Op_aaaa.o").write_text("", encoding="utf-8")
    (bd / "Op_bbbb.o").write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="multiple kernel binaries"):
        m.find_kernel_binary(tmp_path / ".build", "op", "ascend910b")


def test_build_flow_uses_install_target(monkeypatch, tmp_path):
    op_dir = tmp_path / "proj" / "my_op"
    (op_dir / "op_host").mkdir(parents=True)
    (op_dir / "op_host" / "my_op.cpp").write_text("", encoding="utf-8")
    bd = op_dir / ".build"
    record = []

    def rec(name):
        def _f(*a, **k):
            record.append(name)

        return _f

    monkeypatch.setattr(m, "_detect_cann", lambda: tmp_path / "cann")
    monkeypatch.setattr(m, "_resolve_env", lambda cann: {})
    monkeypatch.setattr(m, "configure", rec("configure"))
    monkeypatch.setattr(
        m, "backfill_wrapper", lambda *a, **k: record.append("backfill_wrapper") or True
    )
    monkeypatch.setattr(m, "install_target", rec("install_target"))
    monkeypatch.setattr(m, "_read_compute_unit", lambda b: "ascend910b")
    monkeypatch.setattr(m, "find_artifacts", lambda b: {})
    monkeypatch.setattr(
        m,
        "find_kernel_binary",
        lambda *a, **k: (
            record.append("find_kernel_binary")
            or {
                "obj": bd / "o.o",
                "meta": bd / "o.json",
                "binary_info_config": bd / "c.json",
                "npu_supported_ops": bd / "n.json",
            }
        ),
    )
    monkeypatch.setattr(m, "setup_operator_env", lambda *a, **k: {})
    monkeypatch.setattr(m, "build_ext", rec("build_ext"))
    monkeypatch.setattr(
        m,
        "find_py_ext_so",
        lambda *a, **k: record.append("find_py_ext_so") or bd / "_C.so",
    )

    m.build(str(op_dir))
    assert record == [
        "configure",
        "backfill_wrapper",
        "install_target",
        "find_kernel_binary",
        "build_ext",
        "find_py_ext_so",
    ]


def test_no_kernel_binary_implies_no_py_ext(monkeypatch, tmp_path):
    captured = {}

    def fake_build(op, options=None):
        captured.update(vars(options or m.BuildOptions()))
        return {"op": "x", "op_pascal": "X", "build_dir": tmp_path, "artifacts": {}}

    monkeypatch.setattr(m, "build", fake_build)
    monkeypatch.setattr(
        sys, "argv", ["multirank_build.py", str(tmp_path), "--no-kernel-binary"]
    )
    rc = m.main()
    assert captured["with_kernel_binary"] is False
    assert captured["with_py_ext"] is False
    assert rc == 0


def test_no_py_ext_keeps_kernel_binary(monkeypatch, tmp_path):
    captured = {}
    obj = tmp_path / "o.o"
    obj.write_text("", encoding="utf-8")

    def fake_build(op, options=None):
        captured.update(vars(options or m.BuildOptions()))
        return {
            "op": "x",
            "op_pascal": "X",
            "build_dir": tmp_path,
            "artifacts": {},
            "kernel_binary": {"obj": obj},
        }

    monkeypatch.setattr(m, "build", fake_build)
    monkeypatch.setattr(
        sys, "argv", ["multirank_build.py", str(tmp_path), "--no-py-ext"]
    )
    rc = m.main()
    assert captured["with_kernel_binary"] is True
    assert captured["with_py_ext"] is False
    assert rc == 0
