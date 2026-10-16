# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Reusable real-NPU verify helper for the CV easyasc-a2 examples.

WHY THIS EXISTS (do NOT modify the easyasc lib):
  easyasc's codegen emits an op_kernel/tensorutils.h that references a5-only
  symbols (PaddingMode, QF322F32_PRE, QF322FP8_PRE, QF322HIF8_PRE*,
  float8_e4m3_t, hifloat8_t) UNGUARDED. On a2 (ascend910b / CANN 8.5.0) those
  are undefined -> the `binary` kernel-compile target fails ("use of undeclared
  identifier ...") and no device binary is produced. The proven a2 fix (see
  output/quant_matmul/patch_tensorutils.py) wraps exactly those a5-only branches
  in `#ifdef __DAV_C310__`, leaving the a2 path identical.

  OpExec(simulator=False) regenerates tensorutils.h on every call, so we cannot
  patch-then-call. Instead this helper drives the device path in phases:
    1. gen_only=True  -> codegen the project + write input bins (no build).
    2. patch EVERY tensorutils.h under the out dir (idempotent).
    3. run the generated {out_dir}_kernel_script/b.sh (build) + r.sh (run).
    4. load output bins back as torch tensors.
"""
import os
import glob
import subprocess

import torch
from easyasc.torchplugin import OpExec


_PATCHES = [
    # (anchor, replacement); each idempotent via the marker check below.
    (
        "    DataCopyPad<T, PaddingMode::Normal>(dst, src, param, padparam);\n}",
        "#ifdef __DAV_C310__  // [a2-compat patch] PaddingMode is a5-only\n"
        "    DataCopyPad<T, PaddingMode::Normal>(dst, src, param, padparam);\n"
        "#else\n"
        "    DataCopyPad(dst, src, param, padparam);\n"
        "#endif\n}",
    ),
    (
        "    if constexpr(std::is_same<T, float>::value && std::is_same<T2, float>::value){\n"
        "        if (scaledQuant){ q = QF322F32_PRE; deqScalar = PackDeqScalar(scale, 0); }"
        "  // a5: scaled fp32 L0C -> fp32\n"
        "        else q = NoQuant;\n"
        "    }",
        "    if constexpr(std::is_same<T, float>::value && std::is_same<T2, float>::value){\n"
        "#ifdef __DAV_C310__  // [a2-compat patch] QF322F32_PRE is a5-only\n"
        "        if (scaledQuant){ q = QF322F32_PRE; deqScalar = PackDeqScalar(scale, 0); }"
        "  // a5: scaled fp32 L0C -> fp32\n"
        "        else q = NoQuant;\n"
        "#else\n"
        "        q = NoQuant;\n"
        "#endif\n"
        "    }",
    ),
    (
        "    }else if constexpr(std::is_same<T, float8_e4m3_t>::value && std::is_same<T2, float>::value){\n"
        "        q = QF322FP8_PRE; deqScalar = PackDeqScalar(scale, 0);            // a5: fp32 L0C -> fp8 e4m3\n"
        "    }else if constexpr(std::is_same<T, hifloat8_t>::value && std::is_same<T2, float>::value){\n"
        "        q = hif8Hybrid ? QF322HIF8_PRE_HYBRID : QF322HIF8_PRE;            // a5: fp32 L0C -> hif8\n"
        "        deqScalar = PackDeqScalar(scale, 0);                          "
        "   // (hybrid vs half-to-away rounding)\n"
        "    }else{",
        "#ifdef __DAV_C310__  // [a2-compat patch] fp8/hif8 types+enums are a5-only\n"
        "    }else if constexpr(std::is_same<T, float8_e4m3_t>::value && std::is_same<T2, float>::value){\n"
        "        q = QF322FP8_PRE; deqScalar = PackDeqScalar(scale, 0);            // a5: fp32 L0C -> fp8 e4m3\n"
        "    }else if constexpr(std::is_same<T, hifloat8_t>::value && std::is_same<T2, float>::value){\n"
        "        q = hif8Hybrid ? QF322HIF8_PRE_HYBRID : QF322HIF8_PRE;            // a5: fp32 L0C -> hif8\n"
        "        deqScalar = PackDeqScalar(scale, 0);                          "
        "   // (hybrid vs half-to-away rounding)\n"
        "#endif\n"
        "    }else{",
    ),
]


def _patch_one(path):
    with open(path) as f:
        src = f.read()
    if "// [a2-compat patch]" in src:
        return False
    n = 0
    for anchor, repl in _PATCHES:
        if anchor in src:
            src = src.replace(anchor, repl, 1)
            n += 1
    if n:
        with open(path, "w") as f:
            f.write(src)
    return n > 0


def _patch_all(out_dir):
    patched = []
    for root in (out_dir, f"{out_dir}_kernel_script"):
        for p in glob.glob(os.path.join(root, "**", "tensorutils.h"), recursive=True):
            if _patch_one(p):
                patched.append(p)
    return patched


_TORCH_DTYPE = {
    "half": torch.float16, "float": torch.float32, "int": torch.int32,
    "int32_t": torch.int32, "int8_t": torch.int8, "int16_t": torch.int16,
    "int64_t": torch.int64,
}


def device_run(kernel, args, shape_bindings, out_dir):
    """gen -> patch -> build -> run -> load output bins. Returns the first
    output GMTensor's torch result (single-output kernels)."""
    ex = OpExec(kernel, simulator=False, gen_only=True, out_dir=out_dir)
    ex(*args, shape_bindings=shape_bindings)

    patched = _patch_all(out_dir)
    print(f"[device_verify] patched tensorutils.h: {patched or 'none (already patched / not needed)'}")

    script_dir = f"{out_dir}_kernel_script"
    for s in ("b.sh", "r.sh"):
        sp = os.path.join(script_dir, s)
        log = os.path.abspath(os.path.join(script_dir, f"{s}.log"))
        with open(log, "w") as lf:
            r = subprocess.run(["/bin/bash", sp], stdout=lf, stderr=subprocess.STDOUT)
        if r.returncode != 0:
            raise RuntimeError(f"{s} failed (rc={r.returncode}); see {log}")

    # load output bins from {out_dir}_aclnn_test/output/output_<name>.bin
    out_gms = kernel._last_output_gmtensors
    bound = kernel._last_bound_args
    name_by_id = {id(v): k for k, v in bound.items()}
    out_root = os.path.join(f"{out_dir}_aclnn_test", "output")
    results = []
    for gm in out_gms:
        name = name_by_id[id(gm)]
        # resolve shape from bound Var values
        shape = []
        for d in gm.shape:
            shape.append(int(getattr(d, "value", d)))
        numel = 1
        for d in shape:
            numel *= d
        dt = _TORCH_DTYPE[gm.dtype.name]
        path = os.path.join(out_root, f"output_{name}.bin")
        t = torch.from_file(path, shared=False, size=numel, dtype=dt).clone()
        results.append(t.contiguous().view(*shape))
    return results[0] if len(results) == 1 else results
