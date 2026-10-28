#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""CPU observations and independent replay phases; never restore device tensors.

Intentionally narrow: callers supply already-copied CPU tensors, then run their
original verifier. Device storage, offsets, strides and aliases stay caller-owned.
"""
import hashlib
from pathlib import Path

PHASES = ('preparation', 'target_execution', 'output_validation', 'db_persistence',
          'user_exit', 'record', 'report', 'visualization')
STATUSES = {'PASS', 'FAIL', 'blocked', 'notrun', 'unknown'}


def save_cpu_observations(path, tensors):
    """Save independently owned CPU views (typed and raw may share input storage).

    No implicit .cpu(): transfer success/RC must be established by the caller.
    torch imported lazily, without importing torch_npu or invoking a device API.
    """
    import torch
    path = Path(path)
    observations = {}
    for name, tensor in tensors.items():
        if not isinstance(name, str) or not isinstance(tensor, torch.Tensor):
            raise TypeError('Observations must be named tensors')
        if tensor.device.type != 'cpu' or tensor.layout != torch.strided:
            raise ValueError('Only already-copied strided CPU observations supported')
        observations[name] = tensor.detach().clone()
    with path.open('xb') as handle:
        torch.save(observations, handle)
    return dict(path=str(path.resolve()), bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                names=list(observations), device_restore=False)


def preserve_truth_then_verify(save_truth, verifier):
    """Persist truth first; propagate the original save/verifier exception unchanged."""
    receipt = save_truth()
    verifier()
    return receipt


def phase_summary(phases):
    """Preserve phase receipts, including original RC and exception information.

    All eight explicit PASS statuses are necessary for normal success. RC0 alone
    cannot imply target/output success; any nonzero RC makes that phase FAIL.
    Additional callback counters/evidence are retained rather than normalized away.
    """
    unknown = set(phases) - set(PHASES)
    if unknown:
        raise ValueError(f'Unknown phases: {sorted(unknown)}')
    result = {}
    for name in PHASES:
        receipt = dict(phases.get(name, {'status': 'unknown'}))
        if receipt.get('status') not in STATUSES:
            raise ValueError(f'{name}: invalid status')
        rc = receipt.get('returncode')
        if rc is not None and (isinstance(rc, bool) or not isinstance(rc, int)):
            raise ValueError(f'{name}: returncode must be an original integer')
        if rc is not None and rc != 0:
            receipt['status'] = 'FAIL'
        result[name] = receipt
    status = ('PASS' if all(r['status'] == 'PASS' for r in result.values()) else
              'FAIL' if any(r['status'] == 'FAIL' for r in result.values()) else 'unknown')
    return dict(schema_version=1, status=status, phases=result)
