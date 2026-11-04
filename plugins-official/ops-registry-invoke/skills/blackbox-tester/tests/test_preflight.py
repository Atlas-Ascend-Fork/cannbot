#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""preflight ValueDepend(OPTIONAL) 双接口 / value-depend-as-tensor 守卫回归测试。"""

import importlib.util
import os
import shutil
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_PREF = os.path.join(_HERE, "..", "preflight.py")
_spec = importlib.util.spec_from_file_location("preflight", _PREF)
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)

_INTARRAY_SIG = (
    "aclnnStatus aclnnSampleReduceGetWorkspaceSize(const aclTensor *x, "
    "const aclIntArray *axes, bool keepDims, const aclTensor *out, "
    "uint64_t *workspaceSize, aclOpExecutor **executor)"
)
_TENSOR_SIG = (
    "aclnnStatus aclnnSampleReduceTensorGetWorkspaceSize(const aclTensor *x, "
    "const aclTensor *axes, bool keepDims, const aclTensor *out, "
    "uint64_t *workspaceSize, aclOpExecutor **executor)"
)


def test_csv_tensor_count():
    assert pf.csv_tensor_count("((16,8),(1,),(16,))") == 3
    assert pf.csv_tensor_count("((15237427,),(1,),(1,))") == 3
    assert pf.csv_tensor_count("((16,8),(1,))") == 2
    assert pf.csv_tensor_count("garbage") == -1


def test_sig_tensor_param_count():
    assert pf.sig_tensor_param_count(_INTARRAY_SIG) == 2
    assert pf.sig_tensor_param_count(_TENSOR_SIG) == 3


def test_dual_interface_violation():
    exec_syms = {"aclnnSampleReduce", "aclnnSampleReduceTensor"}
    assert pf.dual_interface_violation("aclnnSampleReduceTensor", exec_syms) is True
    assert pf.dual_interface_violation("aclnnSampleReduce", exec_syms) is False
    assert pf.dual_interface_violation("aclnnSomeTensor", {"aclnnSomeTensor"}) is False


def _build_opp(tmp, optype, symbols, header):
    """Build a real stub vendor deployment when a local C toolchain is available."""
    library_dir = os.path.join(tmp, "vendors", optype, "op_api", "lib")
    include_dir = os.path.join(tmp, "vendors", optype, "op_api", "include")
    os.makedirs(library_dir, exist_ok=True)
    os.makedirs(include_dir, exist_ok=True)
    source = os.path.join(tmp, f"stub_{optype}.c")
    with open(source, "w", encoding="utf-8") as handle:
        for symbol in symbols:
            handle.write(f"int {symbol}(void){{return 0;}}\n")
    gcc = shutil.which("gcc")
    if not gcc:
        return tmp
    output = os.path.join(library_dir, "libcust_opapi.so")
    subprocess.run([gcc, "-shared", "-fPIC", "-o", output, source], check=True)
    with open(
        os.path.join(include_dir, f"aclnn_{optype.lower()}.h"), "w", encoding="utf-8"
    ) as handle:
        handle.write(header)
    return tmp


def _build_public_header(tmp, api, signature):
    include = os.path.join(tmp, "x86_64-linux", "include", "aclnnop")
    os.makedirs(include, exist_ok=True)
    with open(
        os.path.join(include, f"{api.lower()}.h"), "w", encoding="utf-8"
    ) as handle:
        handle.write(signature + ";\n")


_EN_SYMS = (
    "aclnnSampleReduce",
    "aclnnSampleReduceGetWorkspaceSize",
    "aclnnSampleReduceTensorGetWorkspaceSize",
)


def _csv(tmp, name, rows):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(
            "testcase_name,api_name,tensor_view_shapes,tensor_dtypes,attributes,output_tensor_indexes\n"
        )
        handle.writelines(rows)
    return path


def test_preflight_rejects_crash_and_accepts_intarray(tmp_path):
    if shutil.which("gcc") is None:
        return
    opp = _build_opp(
        str(tmp_path),
        "SampleReduce",
        _EN_SYMS,
        _INTARRAY_SIG + ";\n" + _TENSOR_SIG + ";\n",
    )
    bad1 = _csv(
        str(tmp_path),
        "crash_tensor.csv",
        [
            "c1,aclnnSampleReduceTensor,\"((16,8),(1,),(16,))\",\"('float16','int32','float16')\",{},\"(2,)\"\n"
        ],
    )
    assert pf.main([bad1, "--optype", "SampleReduce", "--opp", opp]) == 1
    bad2 = _csv(
        str(tmp_path),
        "crash_intarray.csv",
        [
            "c1,aclnnSampleReduce,\"((15237427,),(1,),(1,))\",\"('float16','int32','float16')\",{},\"(2,)\"\n"
        ],
    )
    assert pf.main([bad2, "--optype", "SampleReduce", "--opp", opp]) == 1
    good = _csv(
        str(tmp_path),
        "good.csv",
        [
            'c1,aclnnSampleReduce,"((16,8),(16,))","(\'float16\',\'float16\')","{\'axes\':[0]}","(1,)"\n'
        ],
    )
    assert pf.main([good, "--optype", "SampleReduce", "--opp", opp]) == 0


def test_valuedepend_tensor_variant_signature():
    assert pf.is_valuedepend_tensor_variant(_INTARRAY_SIG, _TENSOR_SIG) is True
    left = "aclnnFooGetWorkspaceSize(const aclTensor *x, const aclTensor *out, uint64_t *ws, aclOpExecutor **e)"
    right = "aclnnFooTensorGetWorkspaceSize(const aclTensor *x, const aclTensor *y, const aclTensor *out, uint64_t *ws)"
    assert pf.is_valuedepend_tensor_variant(left, right) is False
    left = "aclnnBarGetWorkspaceSize(const aclTensor *x, bool k, const aclTensor *out, uint64_t *ws, aclOpExecutor **e)"
    right = (
        "aclnnBarTensorGetWorkspaceSize(const aclTensor *x, float k, "
        "const aclTensor *out, uint64_t *ws, aclOpExecutor **e)"
    )
    assert pf.is_valuedepend_tensor_variant(left, right) is False


def test_dual_interface_no_false_positive(tmp_path):
    if shutil.which("gcc") is None:
        return
    base = "aclnnFooGetWorkspaceSize(const aclTensor *x, const aclTensor *out, uint64_t *ws, aclOpExecutor **e)"
    tensor = (
        "aclnnFooTensorGetWorkspaceSize(const aclTensor *x, const aclTensor *y, "
        "const aclTensor *out, uint64_t *ws)"
    )
    symbols = (
        "aclnnFoo",
        "aclnnFooGetWorkspaceSize",
        "aclnnFooTensor",
        "aclnnFooTensorGetWorkspaceSize",
    )
    opp = _build_opp(str(tmp_path), "Foo", symbols, base + ";\n" + tensor + ";\n")
    case = _csv(
        str(tmp_path),
        "foo_ok.csv",
        [
            "c1,aclnnFooTensor,\"((8,),(8,),(8,))\",\"('float16','float16','float16')\",{},\"(2,)\"\n"
        ],
    )
    assert pf.main([case, "--optype", "Foo", "--opp", opp]) == 0


def test_preflight_accepts_public_wrapper_but_keeps_signature_guards(tmp_path):
    if shutil.which("gcc") is None:
        return
    opp = _build_opp(
        str(tmp_path / "opp"),
        "FooV2",
        ("aclnnFooV2", "aclnnFooV2GetWorkspaceSize"),
        "aclnnStatus aclnnFooV2GetWorkspaceSize(const aclTensor *x, const aclTensor *out, "
        "uint64_t *ws, aclOpExecutor **e);",
    )
    public_sig = (
        "aclnnStatus aclnnFooGetWorkspaceSize(const aclTensor *x, int64_t dim, "
        "const aclTensor *out, uint64_t *ws, aclOpExecutor **e)"
    )
    _build_public_header(str(tmp_path), "aclnnFoo", public_sig)
    good = _csv(
        str(tmp_path),
        "public_wrapper.csv",
        [
            'c1,aclnnFoo,"((8,),(8,))","(\'float16\',\'float16\')","{\'dim\':0}","(1,)"\n'
        ],
    )
    assert pf.main([good, "--optype", "FooV2", "--opp", opp]) == 0

    bad = _csv(
        str(tmp_path),
        "public_wrapper_bad_attr.csv",
        [
            'c1,aclnnFoo,"((8,),(8,))","(\'float16\',\'float16\')","{\'axis\':0}","(1,)"\n'
        ],
    )
    assert pf.main([bad, "--optype", "FooV2", "--opp", opp]) == 1


def test_preflight_rejects_public_wrapper_shadowed_by_other_vendor(tmp_path):
    if shutil.which("gcc") is None:
        return
    sig_v2 = (
        "aclnnStatus aclnnFooV2GetWorkspaceSize(const aclTensor *x, const aclTensor *out, "
        "uint64_t *ws, aclOpExecutor **e);"
    )
    opp = _build_opp(
        str(tmp_path / "opp"),
        "FooV2",
        ("aclnnFooV2", "aclnnFooV2GetWorkspaceSize"),
        sig_v2,
    )
    public_sig = (
        "aclnnStatus aclnnFooGetWorkspaceSize(const aclTensor *x, int64_t dim, "
        "const aclTensor *out, uint64_t *ws, aclOpExecutor **e)"
    )
    _build_public_header(str(tmp_path), "aclnnFoo", public_sig)
    _build_opp(
        str(tmp_path / "opp"),
        "StaleFoo",
        ("aclnnFoo", "aclnnFooGetWorkspaceSize"),
        public_sig + ";",
    )
    case = _csv(
        str(tmp_path),
        "shadowed.csv",
        [
            'c1,aclnnFoo,"((8,),(8,))","(\'float16\',\'float16\')","{\'dim\':0}","(1,)"\n'
        ],
    )
    assert pf.main([case, "--optype", "FooV2", "--opp", opp]) == 1


def test_attributes_are_checked_against_their_own_api(tmp_path, monkeypatch):
    import csv

    path = tmp_path / "multi_api.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["api_name", "attributes"])
        writer.writeheader()
        writer.writerows(
            [
                {"api_name": "aclnnFoo", "attributes": "{'alpha': 1}"},
                {"api_name": "aclnnBar", "attributes": "{'beta': 2}"},
            ]
        )
    include = tmp_path / "vendors" / "Multi" / "op_api" / "include"
    include.mkdir(parents=True)
    (include / "aclnn_multi.h").write_text(
        "aclnnStatus aclnnFooGetWorkspaceSize(int64_t alpha, aclOpExecutor **executor);\n"
        "aclnnStatus aclnnBarGetWorkspaceSize(int64_t beta, aclOpExecutor **executor);\n",
        encoding="utf-8",
    )
    # The deployed symbol table is the only device installation boundary.
    monkeypatch.setattr(pf, "so_symbols", lambda opp, optype: {"aclnnFoo", "aclnnBar"})
    assert pf.main([str(path), "--optype", "Multi", "--opp", str(tmp_path)]) == 0
    assert pf.attr_keys(str(path)) == ["alpha", "beta"]


def test_wrong_attribute_on_the_same_api_is_still_rejected(tmp_path, monkeypatch):
    import csv

    path = tmp_path / "bad_attr.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["api_name", "attributes"])
        writer.writeheader()
        writer.writerow({"api_name": "aclnnFoo", "attributes": "{'beta': 1}"})
    include = tmp_path / "vendors" / "Multi" / "op_api" / "include"
    include.mkdir(parents=True)
    (include / "aclnn_multi.h").write_text(
        "aclnnStatus aclnnFooGetWorkspaceSize(int64_t alpha, aclOpExecutor **executor);\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pf, "so_symbols", lambda opp, optype: {"aclnnFoo"})
    assert pf.main([str(path), "--optype", "Multi", "--opp", str(tmp_path)]) == 1
