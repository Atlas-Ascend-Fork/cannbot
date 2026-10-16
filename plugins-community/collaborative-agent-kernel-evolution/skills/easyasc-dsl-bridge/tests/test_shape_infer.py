# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Unit tests for gen_bridge.infer_output_shape_expr and ModelNew generation.

Run from the v2 repo root:

    pytest skills/easyasc-dsl-bridge/tests/test_shape_infer.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_THIS = Path(__file__).resolve()
_SCRIPTS = _THIS.parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import gen_bridge  # noqa: E402


# ---------- Pattern 1: full equality -------------------------------------


def test_pattern1_full_equality():
    out_decl = {"name": "y", "shape": [16, 1024]}
    in_decls = [{"name": "x", "shape": [16, 1024]}]
    inputs_dsl = [("x", "float32")]
    expr = gen_bridge.infer_output_shape_expr(out_decl, in_decls, inputs_dsl)
    assert expr == "x.sizes().vec()"


# ---------- Pattern 2: drop last dim -------------------------------------


def test_pattern2_drop_last_dim():
    out_decl = {"name": "scale", "shape": [16]}
    in_decls = [{"name": "x", "shape": [16, 1024]}]
    inputs_dsl = [("x", "float32")]
    expr = gen_bridge.infer_output_shape_expr(out_decl, in_decls, inputs_dsl)
    assert "x.sizes().begin()" in expr
    assert "x.sizes().end() - 1" in expr


# ---------- Pattern 3: matmul (M,K)@(K,N) -> (M,N) -----------------------


def test_pattern3_matmul_2d():
    out_decl = {"name": "y", "shape": [128, 512]}
    in_decls = [
        {"name": "x", "shape": [128, 256]},
        {"name": "weight", "shape": [256, 512]},
    ]
    inputs_dsl = [("x", "float16"), ("weight", "float16")]
    expr = gen_bridge.infer_output_shape_expr(out_decl, in_decls, inputs_dsl)
    assert "x.sizes().vec()" in expr
    assert "weight.size(-1)" in expr


def test_pattern3_matmul_with_batch():
    # (B,S,K) @ (K,N) -> (B,S,N)
    out_decl = {"name": "y", "shape": [4, 128, 512]}
    in_decls = [
        {"name": "x", "shape": [4, 128, 256]},
        {"name": "w", "shape": [256, 512]},
    ]
    inputs_dsl = [("x", "float16"), ("w", "float16")]
    expr = gen_bridge.infer_output_shape_expr(out_decl, in_decls, inputs_dsl)
    assert "x.sizes().vec()" in expr
    assert "w.size(-1)" in expr


# ---------- Pattern 6: transposed-weight matmul (nn.Linear) -------------


def test_pattern6_transposed_weight_matmul():
    # x @ weight.T : x=(M,K), weight=(N,K), out=(M,N)
    out_decl = {"name": "z", "shape": [32, 48]}
    in_decls = [
        {"name": "x", "shape": [32, 16]},
        {"name": "y", "shape": [48, 16]},
    ]
    inputs_dsl = [("x", "float32"), ("y", "float32")]
    expr = gen_bridge.infer_output_shape_expr(out_decl, in_decls, inputs_dsl)
    assert "x.sizes().vec()" in expr
    assert "y.size(-2)" in expr  # take y's N from index -2 (not -1)


def test_pattern6_transposed_weight_batched():
    # (B,S,K) @ (N,K).T -> (B,S,N)
    out_decl = {"name": "z", "shape": [4, 128, 512]}
    in_decls = [
        {"name": "x", "shape": [4, 128, 256]},
        {"name": "w", "shape": [512, 256]},
    ]
    inputs_dsl = [("x", "float16"), ("w", "float16")]
    expr = gen_bridge.infer_output_shape_expr(out_decl, in_decls, inputs_dsl)
    assert "x.sizes().vec()" in expr
    assert "w.size(-2)" in expr


# ---------- Pattern 4: batched matmul / QK^T ------------------------------


def test_pattern4_batched_matmul():
    # (B,H,S,K) @ (B,H,K,T) -> (B,H,S,T)
    out_decl = {"name": "y", "shape": [2, 8, 64, 128]}
    in_decls = [
        {"name": "q", "shape": [2, 8, 64, 32]},
        {"name": "k", "shape": [2, 8, 32, 128]},
    ]
    inputs_dsl = [("q", "float16"), ("k", "float16")]
    expr = gen_bridge.infer_output_shape_expr(out_decl, in_decls, inputs_dsl)
    # The expression should build from q's sizes and replace the last dim with k.size(-1).
    # (pattern 4 currently shares the lambda emission shape with pattern 3; the
    # important thing is that it does NOT raise.)
    assert "size(-1)" in expr


# ---------- Pattern 5: explicit shape_expr --------------------------------


def test_pattern5_shape_expr_full():
    out_decl = {"name": "y", "shape": [-1], "shape_expr": "input0.shape"}
    in_decls = [{"name": "x", "shape": [16, 1024]}]
    inputs_dsl = [("x", "float32")]
    expr = gen_bridge.infer_output_shape_expr(out_decl, in_decls, inputs_dsl)
    assert expr == "x.sizes().vec()"


def test_pattern5_shape_expr_drop_last():
    out_decl = {"name": "y", "shape": [-1], "shape_expr": "input0.shape[:-1]"}
    in_decls = [{"name": "x", "shape": [16, 1024]}]
    inputs_dsl = [("x", "float32")]
    expr = gen_bridge.infer_output_shape_expr(out_decl, in_decls, inputs_dsl)
    assert "x.sizes().begin()" in expr
    assert "x.sizes().end() + (-1)" in expr


def test_pattern5_shape_expr_concat_matmul():
    out_decl = {
        "name": "y",
        "shape": [-1, -1],
        "shape_expr": "input0.shape[:-1] + input1.shape[-1:]",
    }
    in_decls = [
        {"name": "x", "shape": [128, 256]},
        {"name": "w", "shape": [256, 512]},
    ]
    inputs_dsl = [("x", "float16"), ("w", "float16")]
    expr = gen_bridge.infer_output_shape_expr(out_decl, in_decls, inputs_dsl)
    # Concatenation lambda must reference both x and w.
    assert "x.sizes()" in expr
    assert "w.sizes()" in expr
    assert "insert" in expr  # lambda concat path


# ---------- Failure path -------------------------------------------------


def test_unsupported_shape_raises():
    # Output of shape [1] when inputs are [16,1024] and [256,512] — doesn't match any pattern.
    out_decl = {"name": "y", "shape": [1]}
    in_decls = [
        {"name": "x", "shape": [16, 1024]},
        {"name": "w", "shape": [256, 512]},
    ]
    inputs_dsl = [("x", "float32"), ("w", "float32")]
    with pytest.raises(ValueError):
        gen_bridge.infer_output_shape_expr(out_decl, in_decls, inputs_dsl)


# ---------- ModelNew generator ------------------------------------------


def test_modelnew_single_input_single_output():
    out = gen_bridge.generate_modelnew_skeleton(
        op_name="sigmoid",
        inputs=[("x", "float32")],
        outputs=[("y", "float32")],
    )
    assert "import torch_npu" in out
    assert "import custom_ops_lib" in out
    assert "def module_fn(x: torch.Tensor) -> torch.Tensor:" in out
    assert "return custom_ops_lib.sigmoid_custom(x)" in out
    assert "class ModelNew(nn.Module):" in out
    assert "def __init__(self):" in out


def test_modelnew_multi_input():
    out = gen_bridge.generate_modelnew_skeleton(
        op_name="matmul",
        inputs=[("x", "float16"), ("w", "float16")],
        outputs=[("y", "float16")],
    )
    assert "def module_fn(x: torch.Tensor, w: torch.Tensor)" in out
    assert "custom_ops_lib.matmul_custom(x, w)" in out


def test_modelnew_multi_output_returns_tuple():
    out = gen_bridge.generate_modelnew_skeleton(
        op_name="dynamic_quant",
        inputs=[("x", "bfloat16")],
        outputs=[("y", "int8"), ("scale", "float32")],
    )
    # Tuple return type for multi-output (kept as plain `tuple` annotation to
    # avoid pulling in a `typing` import in the generated file).
    assert "-> tuple:" in out


def test_modelnew_requires_inputs():
    with pytest.raises(ValueError):
        gen_bridge.generate_modelnew_skeleton(
            op_name="noop", inputs=[], outputs=[("y", "float32")]
        )


def test_modelnew_requires_outputs():
    with pytest.raises(ValueError):
        gen_bridge.generate_modelnew_skeleton(
            op_name="noop", inputs=[("x", "float32")], outputs=[]
        )
