#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Golden lock for the scoped arch22 to arch35 worker prompt.

These hashes pin the reviewed input-provenance prompt for representative input
variations. Intentional contract edits must update the fixture and re-run the
source/target truth-boundary assertions.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile

import pytest


class _StubEnv:
    port_a3_source = "/home/x/workspace/cann/ops-nn/matmul/mat_mul_v3"
    host = "a5host.example"
    container = "npu_dev3"
    target = "a5"

    def __getattr__(self, name):  # any other env.X → harmless string
        return ""


def _ws(tags):
    d = pathlib.Path(tempfile.mkdtemp()) / "ws"
    d.mkdir(parents=True, exist_ok=True)
    if tags is not None:
        (d / "op_classification.json").write_text(json.dumps({"op_class_tags": tags}))
    return d


# (op, op_class_tags, iter_cap_remaining) -> sha256(output)
# Re-pinned 2026-09-17 (去双轨模式, bb167473): 未配置外部仓时迁移卡引用不再回退插件内
# 旧知识，`kb_ref_display` 的 fail-loud 标记文案改为「cannbot-knowledge 未安装、配置无效
# 或未收录」。
# Re-pinned 2026-09-17 (外部知识仓适配, OKF v0.2): 迁移卡片的 KB 指针改经
# `external_kb.kb_ref_display` 输出，brief 文本随外部仓配置与否变化；本表 pin 的是
# **未配置外部仓**的确定性形态。测试经 `no_external_kb` fixture 显式隔离，保证在配置了
# CANNBOT_KNOWLEDGE_ROOT 的机器上也复现同一形态。配置模式的解析行为由
# test_kw_brief_decomposition_modules.py 的 external-repo 模式测试覆盖。
# Re-pinned 2026-10-26 (port 契约表述对齐): A5 kernel 方法论句从「designed via math +
# hardware adaptation」改为「re-emits the A3 source's algorithm and structure with
# arch35 hardware adaptation (Phase A.1-1 authoring contract)」——与 port 契约的
# preserve-structure 语义对齐；diff 审查确认全文本仅此一处差异（abs 用例逐字节 diff）。
_GOLDEN = [
    ("mat_mul_v3", ["a3_to_a5_port", "CUBE_MIX"], 3,
     "20b2d92ef40304ae214a8a20d6c3fc7addb097178586fc51726bb44f751804bc"),
    ("some_vec_op", ["a3_to_a5_port"], 3,
     "56549d29e9b07274526595fc80cdb96ca14e8096ded7531d02a9d930fe08dc70"),
    ("flash_attention_score", ["a3_to_a5_port", "FA_CLASS"], 2,
     "2f66d83c5bdc6267bee82365a6cc6c70ddc0a3e467ac5f010f0469bc54ae2a4c"),
    ("abs", ["a3_to_a5_port"], 1,
     "fdb2759bd9f566aefa5e694bf0bdfb69dc962ea79602fae248d66236d156bb73"),
]


@pytest.mark.parametrize("op,tags,iter_cap,expected_sha", _GOLDEN)
def test_port_a3_phase_brief_byte_identical(op, tags, iter_cap, expected_sha, no_external_kb):
    from briefs.kw_brief import _port_a3_phase_instructions_block  # type: ignore

    out = _port_a3_phase_instructions_block(
        op=op, workspace=_ws(tags), iter_cap_remaining=iter_cap, env=_StubEnv()
    )
    got = hashlib.sha256(out.encode()).hexdigest()
    assert got == expected_sha, (
        f"port_a3 phase brief changed for op={op!r} tags={tags} iter_cap={iter_cap}: "
        f"len={len(out)} sha={got} != reviewed golden {expected_sha}."
    )
