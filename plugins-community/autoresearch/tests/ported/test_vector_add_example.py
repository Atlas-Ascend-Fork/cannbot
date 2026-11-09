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

"""CPU interpretation checks, not Triton Ascend compilation or NPU validation."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest


class _Tensor:
    def __init__(self, values):
        self.values = values
        self.reads = np.zeros(values.size, dtype=int)
        self.writes = np.zeros(values.size, dtype=int)

    def numel(self):
        return self.values.size


class _Block:
    def __init__(self, base, shape, strides, offsets, block_shape, order):
        assert strides == (1,)
        assert order == (0,)
        self.base = base
        self.indices = offsets[0] + np.arange(block_shape[0])
        self.valid = (self.indices >= 0) & (self.indices < shape[0])


def _load(block, boundary_check=()):
    assert boundary_check == (0,)
    indices = block.indices[block.valid]
    # Inactive lanes are unspecified for block loads without a padding option.
    values = np.full(block.indices.size, 71, dtype=block.base.values.dtype)
    values[block.valid] = block.base.values[indices]
    block.base.reads[indices] += 1
    return values


def _store(block, values, boundary_check=()):
    assert boundary_check == (0,)
    indices = block.indices[block.valid]
    block.base.values[indices] = values[block.valid]
    block.base.writes[indices] += 1


def _empty_like(tensor):
    return _Tensor(np.full_like(tensor.values, -37))


def _cdiv(value, divisor):
    return (value + divisor - 1) // divisor


def _next_power_of_2(value):
    assert value > 0
    return 1 << (value - 1).bit_length()


class _JitFunction:
    def __init__(self, function, state):
        self.function = function
        self.state = state

    def __getitem__(self, grid):
        def launch(*args, **kwargs):
            self.state["launches"].append((grid, kwargs.copy()))
            for pid in range(grid[0]):
                self.state["pid"] = pid
                self.function(*args, **kwargs)

        return launch


@pytest.fixture
def vector_add(monkeypatch):
    state = {"pid": 0, "launches": []}
    triton = ModuleType("triton")
    language = ModuleType("triton.language")
    torch = ModuleType("torch")

    def jit(function):
        return _JitFunction(function, state)

    def program_id(axis):
        assert axis == 0
        return state["pid"]

    triton.jit = jit
    triton.cdiv = _cdiv
    triton.next_power_of_2 = _next_power_of_2
    triton.language = language
    language.constexpr = object
    language.program_id = program_id
    language.make_block_ptr = _Block
    language.load = _load
    language.store = _store
    torch.nn = SimpleNamespace(Module=object)
    torch.empty_like = _empty_like
    for name, module in (
        ("torch", torch),
        ("torch_npu", ModuleType("torch_npu")),
        ("triton", triton),
        ("triton.language", language),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    path = Path(__file__).resolve().parents[2]
    path /= "ar_examples/triton_ascend/vector_add_kernel.py"
    spec = importlib.util.spec_from_file_location("_test_vector_add_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, state


def _inputs(size, dtype):
    positions = np.arange(size, dtype=np.int32)
    x = ((positions % 11 - 5) * 0.25).astype(dtype)
    y = ((positions % 7 - 3) * 0.5).astype(dtype)
    return _Tensor(x), _Tensor(y)


@pytest.mark.parametrize("size", [0, 1, 7, 8, 9, 16, 17, 49])
@pytest.mark.parametrize("dtype", [np.float16, np.float32, np.int32])
def test_kernel_checks_bounds_and_writes_each_element_once(vector_add, size, dtype):
    module, state = vector_add
    x, y = _inputs(size, dtype)
    original_x, original_y = x.values.copy(), y.values.copy()
    out = _Tensor(np.full(size + 3, -37, dtype=dtype))

    for pid in range(_cdiv(size, 8)):
        state["pid"] = pid
        module.vector_add_kernel.function(x, y, out, size, block_size=8)

    np.testing.assert_array_equal(out.values[:size], original_x + original_y)
    np.testing.assert_array_equal(out.writes[:size], 1)
    np.testing.assert_array_equal(out.values[size:], -37)
    np.testing.assert_array_equal(out.writes[size:], 0)
    np.testing.assert_array_equal(out.reads, 0)
    for tensor, original in ((x, original_x), (y, original_y)):
        np.testing.assert_array_equal(tensor.values, original)
        np.testing.assert_array_equal(tensor.reads, 1)
        np.testing.assert_array_equal(tensor.writes, 0)


@pytest.mark.parametrize(
    "size,block_size,programs",
    [
        (0, None, 0),
        (1, 1, 1),
        (7, 8, 1),
        (1023, 1024, 1),
        (1024, 1024, 1),
        (1025, 1024, 2),
        (2048, 1024, 2),
        (65536, 1024, 64),
        (65537, 1024, 65),
    ],
)
@pytest.mark.parametrize("dtype", [np.float16, np.float32, np.int32])
def test_forward_preserves_dtype_and_launches_only_needed_blocks(
    vector_add, size, block_size, programs, dtype
):
    module, state = vector_add
    x, y = _inputs(size, dtype)
    original_x, original_y = x.values.copy(), y.values.copy()

    out = module.ModelNew().forward(x, y)

    expected_launches = [((programs,), {"block_size": block_size})] if programs else []
    assert state["launches"] == expected_launches
    assert out is not x and out is not y
    assert out.values.dtype == dtype
    assert out.values.shape == x.values.shape
    np.testing.assert_array_equal(out.values, original_x + original_y)
    np.testing.assert_array_equal(out.writes, 1)
    np.testing.assert_array_equal(x.values, original_x)
    np.testing.assert_array_equal(y.values, original_y)


def test_forward_accepts_the_same_input_twice(vector_add):
    module, _state = vector_add
    x, _y = _inputs(1025, np.float32)
    original = x.values.copy()

    out = module.ModelNew().forward(x, x)

    np.testing.assert_array_equal(out.values, original + original)
    np.testing.assert_array_equal(x.values, original)
    np.testing.assert_array_equal(x.writes, 0)
    np.testing.assert_array_equal(x.reads, 2)
