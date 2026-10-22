#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Opportunistically discover same-operator reference implementations (opt-in).

NOTE: most operators have NO comparable reference. The universal performance anchor is the
operator's intrinsic-minimum-cost roofline (workflow-contract §4.2), which needs no external
implementation. Run this ONLY when a sibling/competitor/same-op reference is known or strongly
suspected; a "not found" result is not a workflow blocker. Scans two sources:

1. CANN install: registered aclnn symbols `aclnn<CamelCaseOp>*` in libopapi*.so — a production
   reference the workflow can measure via torch_npu / aclnn on the same cases.
2. Repo / adjacent dirs: sibling operator directories whose name matches the operator (e.g.
   <op>, <op>_v2, <op>_v3, official/self-dev variants) — candidate reference implementations.

Emits reference-candidates.json. This only *surfaces* candidates; the main agent decides which to
measure and freeze as REFERENCE_PERF. It never fabricates numbers.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from cli_output import emit


def camel_case(op: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[_\-]+", op) if part)


def scan_cann_aclnn(op: str, cann_home: Path) -> list[dict]:
    """Return aclnn<CamelCaseOp>* symbols found in libopapi*.so under the CANN install."""
    camel = camel_case(op)
    needle = f"aclnn{camel}"
    lib_dir = cann_home / "x86_64-linux" / "lib64"
    if not lib_dir.is_dir():
        # fall back to any lib64 under cann_home
        matches = list(cann_home.glob("**/lib64"))
        lib_dir = matches[0] if matches else cann_home
    nm = shutil.which("nm")
    if nm is None:
        return []
    found: dict[str, list[str]] = {}
    for lib in sorted(lib_dir.glob("libopapi*.so")):
        try:
            out = subprocess.run(
                [nm, "-D", str(lib)], capture_output=True, text=True, timeout=60
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        syms = sorted({m for m in re.findall(rf"aclnn{re.escape(camel)}[A-Za-z0-9]*", out)})
        if syms:
            found[str(lib)] = syms
    return [
        {"kind": "cann_aclnn", "library": lib, "symbols": syms, "aclnn_prefix": needle}
        for lib, syms in found.items()
    ]


def scan_sibling_dirs(op: str, search_root: Path, self_dir: Path | None) -> list[dict]:
    """Return sibling directories whose name matches the operator (variants included)."""
    token = op.lower()
    candidates: list[dict] = []
    seen: set[str] = set()
    for path in search_root.rglob(f"*{token}*"):
        if not path.is_dir():
            continue
        name = path.name.lower()
        # match <op>, <op>_v2, <op>_norope, official/self-dev variants; skip build/cache dirs
        if token not in name:
            continue
        if any(seg in path.parts for seg in (".git", "build", "__pycache__", "node_modules")):
            continue
        rp = str(path.resolve())
        if self_dir and rp == str(self_dir.resolve()):
            continue  # skip the operator under optimization itself
        if rp in seen:
            continue
        seen.add(rp)
        has_kernel = any(path.rglob("*op_kernel*")) or any(path.glob("**/*.cpp"))
        candidates.append({"kind": "sibling_dir", "path": rp, "has_kernel_sources": bool(has_kernel)})
    return candidates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--operator", required=True, help="operator name, e.g. mla_prolog")
    ap.add_argument("--cann-home", type=Path, default=Path(os.environ.get("ASCEND_HOME_PATH", "")))
    ap.add_argument("--search-root", type=Path, action="append", default=None,
                    help="dir(s) to scan for sibling implementations (repeatable)")
    ap.add_argument("--self-dir", type=Path, help="the operator dir under optimization (excluded from siblings)")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    cann_candidates: list[dict] = []
    if args.cann_home and Path(args.cann_home).is_dir():
        cann_candidates = scan_cann_aclnn(args.operator, Path(args.cann_home))

    sibling_candidates: list[dict] = []
    for root in (args.search_root or []):
        if Path(root).is_dir():
            sibling_candidates.extend(scan_sibling_dirs(args.operator, Path(root), args.self_dir))

    report = {
        "operator": args.operator,
        "aclnn_prefix": f"aclnn{camel_case(args.operator)}",
        "cann_home": str(args.cann_home) if args.cann_home else None,
        "cann_references": cann_candidates,
        "sibling_references": sibling_candidates,
        "any_reference_found": bool(cann_candidates or sibling_candidates),
        "note": (
            "Candidates only — the workflow must measure one on the frozen cases and freeze it as "
            "REFERENCE_PERF (or record why none is measurable). No numbers are fabricated here."
        ),
    }
    args.out.resolve().write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    emit(json.dumps({
        "status": "discovered" if report["any_reference_found"] else "none_found",
        "cann_references": len(cann_candidates),
        "sibling_references": len(sibling_candidates),
        "out": str(args.out.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
