# Copyright 2026 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""CPU regressions for shared profiling-kernel and build-cleanup helpers."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest
from op_autoresearch.op.verifier.adapters.factory import get_dsl_adapter


_OP_ROOT = Path(__file__).resolve().parents[2] / "src/op_autoresearch/op"


def _load_source(relative_path):
    path = _OP_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(f"_test_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Pointer:
    def __init__(self, values):
        self.values = values
        self.writes = np.zeros(len(values), dtype=int)
        self.reads = np.zeros(len(values), dtype=int)

    def __add__(self, offsets):
        return self, offsets


@pytest.fixture
def memory_kernels(monkeypatch):
    """Interpret the JIT function bodies with masked CPU loads and stores."""
    triton = ModuleType("triton")
    language = ModuleType("triton.language")
    state = {"pid": 0}

    def jit(func):
        return func

    def cdiv(value, block):
        return (value + block - 1) // block

    def program_id(_axis):
        return state["pid"]

    triton.jit = jit
    triton.language = language
    language.constexpr = object
    language.int32 = np.int32
    language.arange = np.arange
    language.zeros = np.zeros
    language.cdiv = cdiv
    language.program_id = program_id

    def load(address, mask):
        pointer, offsets = address
        values = np.zeros(len(offsets), dtype=pointer.values.dtype)
        values[mask] = pointer.values[offsets[mask]]
        pointer.reads[offsets[mask]] += 1
        return values

    def store(address, values, mask):
        pointer, offsets = address
        pointer.values[offsets[mask]] = values[mask]
        pointer.writes[offsets[mask]] += 1

    language.load = load
    language.store = store
    monkeypatch.setitem(sys.modules, "triton", triton)
    monkeypatch.setitem(sys.modules, "triton.language", language)
    helper = _load_source("utils/triton_memory.py")
    monkeypatch.setitem(sys.modules, "op_autoresearch.op.utils.triton_memory", helper)
    return (
        state,
        _load_source("utils/triton_autotune_patch.py"),
        _load_source("verifier/l2_cache_clear.py"),
    )


@pytest.mark.parametrize("n_elements", [0, 1, 7, 8, 9, 49])
@pytest.mark.parametrize("copy", [False, True])
@pytest.mark.parametrize("dtype", [np.int32, np.float32])
def test_named_memory_kernels_cover_blocks_once(
    memory_kernels, n_elements, copy, dtype
):
    state, restore, clear = memory_kernels
    src = _Pointer(np.arange(n_elements, dtype=dtype) + 1)
    dst = _Pointer(np.full(n_elements + 2, -7, dtype=dtype))
    if copy:
        kernel = restore.op_autoresearch_restore_copy_kernel
        assert kernel.__name__ == restore.OP_AUTORESEARCH_RESTORE_COPY_KERNEL_NAME
        args = (dst, src, n_elements)
    else:
        kernel = clear.op_autoresearch_l2cache_clear_kernel
        assert kernel.__name__ == clear.L2_CACHE_CLEAR_KERNEL_NAME
        args = (dst, n_elements)

    for pid in range(3):
        state["pid"] = pid
        kernel(*args, block_size=8, core_num=3)

    expected = src.values if copy else np.zeros(n_elements, dtype=dtype)
    np.testing.assert_array_equal(dst.values[:n_elements], expected)
    np.testing.assert_array_equal(dst.writes[:n_elements], 1)
    np.testing.assert_array_equal(src.reads, int(copy))
    np.testing.assert_array_equal(dst.reads, 0)
    np.testing.assert_array_equal(dst.values[n_elements:], -7)
    np.testing.assert_array_equal(dst.writes[n_elements:], 0)


@pytest.mark.parametrize(
    "dsl,project_dir_name",
    [
        ("ascendc", "ascendc_op"),
        ("ascendc", "custom_op"),
        ("ascendc_catlass", "catlass_op"),
    ],
)
@pytest.mark.parametrize("keep_temp", ["0", "1"])
def test_cleanup_preserves_adapter_retention_policy(
    tmp_path, monkeypatch, dsl, project_dir_name, keep_temp
):
    adapter = get_dsl_adapter(dsl)
    if project_dir_name == "custom_op":
        adapter.prepare_config(
            {"ascendc_op_dir": project_dir_name, "arch": "ascend910b3"}
        )
    project = tmp_path / project_dir_name
    build = project / "build"
    build.mkdir(parents=True)
    (build / "compiled.o").write_bytes(b"build artifact")
    source = project / "CMakeLists.txt"
    source.write_text("project(toy)", encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("AR_KEEP_BATCH_VERIFY_TEMP", keep_temp)

    adapter.post_iteration_cleanup(str(tmp_path))
    adapter.post_iteration_cleanup(str(tmp_path))

    assert build.exists() is (dsl == "ascendc" and keep_temp == "1")
    assert source.read_text(encoding="utf-8") == "project(toy)"
    assert profile.read_text(encoding="utf-8") == "{}"
