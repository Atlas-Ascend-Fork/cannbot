#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
"""黑盒执行前预检：在上设备前拦截 ACLNN 接口对接问题并给出修复建议。"""

import argparse
import ast
import csv
import logging
import os
import re
import shutil
import subprocess
import sys

LOG = logging.getLogger(__name__)


def api_names(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return sorted(
            {row["api_name"] for row in csv.DictReader(handle) if row.get("api_name")}
        )


def attr_keys(path):
    keys = set()
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            raw = (row.get("attributes") or "").strip()
            if not raw:
                continue
            try:
                keys |= set(ast.literal_eval(raw).keys())
            except (SyntaxError, ValueError) as exc:
                LOG.debug("跳过不可解析 attributes %r: %s", raw, exc)
    return sorted(keys)


def so_symbols(opp, optype):
    library = os.path.join(opp, "vendors", optype, "op_api", "lib", "libcust_opapi.so")
    if not os.path.isfile(library):
        return None
    nm = shutil.which("nm")
    if not nm:
        LOG.warning("找不到 nm 工具，跳过符号核对")
        return None
    result = subprocess.run(
        [nm, "-D", library], capture_output=True, text=True, check=False
    )
    return set(re.findall(r"\baclnn\w+", result.stdout))


def sig_under(include_root, api):
    """Return ``<api>GetWorkspaceSize``'s parameter string below an include root."""
    if not os.path.isdir(include_root):
        return None
    for root, _, files in os.walk(include_root):
        for filename in files:
            with open(
                os.path.join(root, filename), encoding="utf-8", errors="replace"
            ) as handle:
                text = handle.read()
            text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
            text = re.sub(r"//[^\n]*", "", text)
            match = re.search(
                re.escape(api) + r"GetWorkspaceSize\s*\((.*?)\)", text, re.S
            )
            if match:
                return match.group(1)
    return None


def header_sig(opp, optype, api):
    return sig_under(os.path.join(opp, "vendors", optype, "op_api", "include"), api)


def builtin_header_sig(opp, api):
    """Locate a CANN public ACLNN wrapper header, excluding all vendor trees."""
    toolkit = os.path.dirname(os.path.realpath(opp))
    candidates = [os.path.join(toolkit, "include", "aclnnop")]
    try:
        arches = sorted(name for name in os.listdir(toolkit) if name.endswith("-linux"))
    except OSError as exc:
        LOG.debug("无法枚举 toolkit 架构目录: %s", exc)
        arches = []
    candidates.extend(
        os.path.join(toolkit, arch, "include", "aclnnop") for arch in arches
    )
    for include_root in candidates:
        signature = sig_under(include_root, api)
        if signature is not None:
            return signature
    return None


def other_vendor_headers(opp, optype, api):
    vendors = os.path.join(opp, "vendors")
    try:
        names = sorted(os.listdir(vendors))
    except OSError as exc:
        LOG.debug("无法枚举 vendors 目录: %s", exc)
        return []
    matches = []
    for name in names:
        if name == optype:
            continue
        include_root = os.path.join(vendors, name, "op_api", "include")
        if sig_under(include_root, api) is not None:
            matches.append(name)
    return matches


def params_from_sig(signature):
    if signature is None:
        return None
    return set(re.findall(r"[\*\s](\w+)\s*(?:,|$)", signature))


def sig_tensor_param_count(signature):
    """签名里 aclTensor* / aclTensorList* 形参个数。"""
    return len(re.findall(r"acl(?:Tensor|TensorList)\s*\*", signature))


def csv_tensor_count(tensor_view_shapes):
    """CSV tensor_view_shapes 顶层元组里的 tensor 个数；解析失败返回 -1。"""
    try:
        value = ast.literal_eval(tensor_view_shapes)
    except (SyntaxError, ValueError) as exc:
        LOG.debug("无法解析 tensor_view_shapes %r: %s", tensor_view_shapes, exc)
        return -1
    return len(value) if isinstance(value, tuple) else -1


def param_types(signature):
    types = []
    for part in signature.split(","):
        match = re.search(r"(acl\w+|bool|u?int\d+_t|float|double|size_t)\b", part)
        types.append(match.group(1) if match else part.strip())
    return types


def is_valuedepend_tensor_variant(base_sig, tensor_sig):
    """base 与 ...Tensor 两签名恰好差一处 aclIntArray* <-> aclTensor* 时返回 True。"""
    left, right = param_types(base_sig), param_types(tensor_sig)
    if len(left) != len(right):
        return False
    diffs = [(x, y) for x, y in zip(left, right) if x != y]
    return len(diffs) == 1 and diffs[0] == ("aclIntArray", "aclTensor")


def dual_interface_violation(api, exec_syms, opp=None, optype=None):
    """判定 ValueDepend(OPTIONAL) 双接口是否构成 device-tensor 崩溃路径。"""
    if not api.endswith("Tensor"):
        return False
    base = api[: -len("Tensor")]
    if base == api or base not in exec_syms:
        return False
    if opp is not None and optype is not None:
        base_sig = header_sig(opp, optype, base)
        tensor_sig = header_sig(opp, optype, api)
        if base_sig and tensor_sig:
            return is_valuedepend_tensor_variant(base_sig, tensor_sig)
    return True


def public_apis(symbols):
    if not symbols:
        return set()
    raw = {name for name in symbols if not name.endswith("GetWorkspaceSize")}
    raw |= {
        name[: -len("GetWorkspaceSize")]
        for name in symbols
        if name.endswith("GetWorkspaceSize")
    }
    return raw


def _fail_dual_interface(api):
    base = api[: -len("Tensor")]
    LOG.error(
        "api_name '%s' 是 ValueDepend(OPTIONAL) 的 Tensor 双接口变体；"
        "请改用基接口 '%s'。",
        api,
        base,
    )
    return False


def _public_wrapper_signature(args, api, op_apis):
    signature = builtin_header_sig(args.opp, api)
    if signature is None:
        candidates = sorted(op_apis)
        LOG.error(
            "api_name '%s' 不在 vendor 符号或 CANN 公共接口中（候选：%s）",
            api,
            candidates[:4],
        )
        return None, False
    shadows = other_vendor_headers(args.opp, args.optype, api)
    if shadows:
        LOG.error(
            "CANN 公共 ACLNN wrapper '%s' 同时被其它 vendor 头文件定义：%s",
            api,
            shadows,
        )
        return None, False
    LOG.info(
        "api_name '%s' 使用 CANN 公共 ACLNN wrapper；必须由 smoke kernel-origin 门禁确认。",
        api,
    )
    return signature, True


def _validate_api_signatures(args, symbols, op_apis):
    api_sigs = {}
    condemned = set()
    ok = True
    if symbols is None:
        LOG.warning(
            "找不到 vendors/%s/op_api/lib/libcust_opapi.so，跳过符号/头文件核对",
            args.optype,
        )
    for api in api_names(args.csv):
        if symbols is not None and dual_interface_violation(
            api, symbols, args.opp, args.optype
        ):
            ok = _fail_dual_interface(api)
            condemned.add(api)
            continue
        if symbols is not None and api not in op_apis:
            signature, accepted = _public_wrapper_signature(args, api, op_apis)
            if not accepted:
                ok = False
                continue
            api_sigs[api] = signature
        elif symbols is not None:
            api_sigs[api] = header_sig(args.opp, args.optype, api)
        ok &= _validate_attributes(args, api, api_sigs.get(api))
    return api_sigs, condemned, ok


def _validate_attributes(args, api, signature):
    params = params_from_sig(signature)
    if not params:
        return True
    ok = True
    for key in attr_keys(args.csv):
        if key in params:
            continue
        candidates = [
            param for param in sorted(params) if param.lower().startswith(key.lower())
        ]
        hint = f"；是否应为 '{candidates[0]}'?" if candidates else ""
        LOG.error(
            "属性键 '%s' 不是 %s 的接口参数名（头文件参数：%s%s）",
            key,
            api,
            sorted(params),
            hint,
        )
        ok = False
    return ok


def _validate_tensor_counts(args, api_sigs, condemned):
    if not api_sigs or not os.path.isfile(args.csv):
        return True
    with open(args.csv, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            api = row.get("api_name")
            if not api or api in condemned or api not in api_sigs:
                continue
            signature = api_sigs[api]
            if not signature:
                continue
            tensor_count = csv_tensor_count(row.get("tensor_view_shapes") or "")
            param_count = sig_tensor_param_count(signature)
            if tensor_count > param_count:
                LOG.error(
                    "用例 '%s' 的 tensor 数 %d > %s 接口 tensor 形参数 %d。",
                    row.get("testcase_name"),
                    tensor_count,
                    api,
                    param_count,
                )
                return False
    return True


def _validate_csv_literals(path):
    """Validate CSV literals even when vendor symbols are unavailable."""
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            shapes = row.get("tensor_view_shapes")
            if shapes is not None and csv_tensor_count(shapes) < 0:
                LOG.error(
                    "用例 '%s' 的 tensor_view_shapes 必须是可解析的顶层元组。",
                    row.get("testcase_name"),
                )
                return False
            raw = (row.get("attributes") or "").strip()
            if not raw:
                continue
            try:
                attributes = ast.literal_eval(raw)
            except (SyntaxError, ValueError):
                LOG.error(
                    "用例 '%s' 的 attributes 无法解析。", row.get("testcase_name")
                )
                return False
            if not isinstance(attributes, dict):
                LOG.error(
                    "用例 '%s' 的 attributes 必须是字典。", row.get("testcase_name")
                )
                return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--optype", required=True)
    parser.add_argument("--opp", default=os.environ.get("ASCEND_OPP_PATH", ""))
    args = parser.parse_args(argv)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")

    if not _validate_csv_literals(args.csv):
        LOG.info("[preflight] 有不通过项，修复用例后重试")
        return 1

    symbols = so_symbols(args.opp, args.optype)
    op_apis = public_apis(symbols)
    api_sigs, condemned, ok = _validate_api_signatures(args, symbols, op_apis)
    ok &= _validate_tensor_counts(args, api_sigs, condemned)
    LOG.info("[preflight] PASS" if ok else "[preflight] 有不通过项，修复用例后重试")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
