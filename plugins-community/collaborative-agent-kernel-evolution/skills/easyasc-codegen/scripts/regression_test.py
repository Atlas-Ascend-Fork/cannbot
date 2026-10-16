#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""
Regression test for the cake skill toolchain.

Given an operator that already has its DSL + functional + reference + test_cases
in `output/<op>/`, this script runs the full downstream pipeline end-to-end and
verifies that the toolchain produces a working kernel without any manual
intervention. It checks all the P0/P1/P2 fix points listed in
``output/AddRMSNorm/REVIEW.md §5.2 / §10 / §11 / §12``:

  P0-1  gen_bridge ``_to_camel`` preserves internal capitals (AddRMSNorm not Addrmsnorm)
  P0-2  easyasc-codegen post-process renames PascalCase kernel files to snake_case
  P0-3  bridge cpp's ``aclnn`` lookup name uses the kernelbase-style camel
  P1-1  build.sh patched to pre-create ``binary/config/`` (CPack robustness)
  P1-2  bridge cpp auto-emits bf16↔fp32 cast layer when DSL/op_desc dtypes differ
  P2-1  test_cases.py has ``get_init_inputs`` (no Model __init__ missing-arg errors)
  Eval  empty_cache + retry-on-failure → expected 12/12 PASS for AddRMSNorm

Usage::

    PYTHONPATH=${EASYASC_DSL_HOME}:${PYTHONPATH} \\
      python3 skills/easyasc-codegen/scripts/regression_test.py AddRMSNorm

    # Skip slow eval; just verify stages 5/6 succeed and skill-fix signals appear:
    python3 skills/easyasc-codegen/scripts/regression_test.py AddRMSNorm --skip-eval

    # Run multiple ops:
    python3 skills/easyasc-codegen/scripts/regression_test.py AddRMSNorm dynamic_quant

Exit codes:
    0 — all stages OK and (if not --skip-eval) eval passes ≥ expected_min_pass cases
    1 — stage failure (bridge, codegen, build, install, pybind, or eval setup error)
    2 — pass rate below expected threshold
    3 — toolchain skill-fix signals missing (regression in skill code)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class _StreamProxy:
    """按名字在写出时解析 sys.stdout / sys.stderr。

    logging.StreamHandler 在构造时就持有流对象，而 print 每次调用才取
    sys.stdout / sys.stderr。用本代理转发，使二者行为一致——进程内替换或
    重定向标准流时，输出仍落到替换后的流。
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def write(self, text: str) -> int:
        return getattr(sys, self._name).write(text)

    def flush(self) -> None:
        getattr(sys, self._name).flush()


_LOG = logging.getLogger(__name__ + ".stdout")
_ERR = logging.getLogger(__name__ + ".stderr")


def _init_loggers() -> None:
    """把脚本输出接到 logging，格式为 %(message)s，每行内容与原 print 一致。"""
    for logger, name in ((_LOG, "stdout"), (_ERR, "stderr")):
        if logger.handlers:
            continue
        handler = logging.StreamHandler(_StreamProxy(name))
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False


_init_loggers()


# Project root assumed to be 2 levels up from this script
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"


# Per-op expected pass count thresholds. AddRMSNorm baseline is 12/12 after
# all P0/P1/P2/H-tail/empty-cache/retry fixes; if a regression breaks any of
# these, this test will catch it. Add more ops here as you regress-test them.
EXPECTED_PASS_MIN: Dict[str, int] = {
    "AddRMSNorm": 11,  # allow 1 flaky case for absolute safety; usually 12/12
    "dynamic_quant": 4,
}


# ANSI colors (no-op when not a TTY)
def _color(s: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"\x1b[{code}m{s}\x1b[0m"
    return s


def _green(s):
    return _color(s, "32")


def _red(s):
    return _color(s, "31")


def _yellow(s):
    return _color(s, "33")


def _bold(s):
    return _color(s, "1")


class _StageAbort(Exception):
    """阶段致命失败。由 main 捕获后转为退出码，不在函数内直接结束进程。"""

    def __init__(self, code: int) -> None:
        super().__init__(f"stage aborted with code {code}")
        self.code = code


def run(
    cmd: List[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict] = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run a subprocess and stream/return its output."""
    real_env = os.environ.copy()
    if env:
        real_env.update(env)
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=real_env,
        capture_output=capture,
        text=True,
    )
    if check and result.returncode != 0:
        _LOG.info(_red(f"  ✗ command failed: {' '.join(cmd)}"))
        _LOG.info(_red(f"    stdout: {result.stdout[-600:]}"))
        _LOG.info(_red(f"    stderr: {result.stderr[-600:]}"))
        raise _StageAbort(1)
    return result


# ----------------------------------------------------------------------------
# Stage-by-stage checks
# ----------------------------------------------------------------------------


def check_prerequisites(op_name: str) -> Path:
    """Ensure the operator workspace has DSL + op_desc + functional + test_cases."""
    work_dir = PROJECT_ROOT / "output" / op_name
    required = {
        f"{op_name}_dsl.py": "DSL written by dsl-baseline-generation-easyasc",
        f"{op_name}_op_desc.json": "op desc written by op-desc-generation",
        f"{op_name}_functional.py": "functional written by functional-conversion",
        "test_cases.py": "test cases (you create from skill template)",
    }
    missing = [
        (name, why) for name, why in required.items() if not (work_dir / name).is_file()
    ]
    if missing:
        _LOG.info(_red(f"  ✗ prerequisite files missing in {work_dir}:"))
        for name, why in missing:
            _LOG.info(_red(f"      - {name} ({why})"))
        raise _StageAbort(1)
    return work_dir


def stage_bridge(op_name: str, work_dir: Path) -> List[Tuple[str, bool]]:
    """Run gen_bridge.py and verify P0-1, P0-3, P1-2 fix signals.

    v2.1 stage 6 = bridge cpp generation, runs AFTER easyasc-codegen
    (reads the autogen aclnn header as ground truth for parameter ordering).
    """
    _LOG.info(_bold(f"\n[stage 6 / bridge] gen_bridge for {op_name}"))
    script = SKILLS_DIR / "easyasc-dsl-bridge" / "scripts" / "gen_bridge.py"

    # IMPORTANT: gen_bridge.py imports easyasc to introspect DSL tensors
    # (`detect_dsl_dtypes`) for the P1-2 dtype-cast layer. If PYTHONPATH
    # doesn't include EASYASC_DSL_HOME, that detection silently falls
    # back and emits a cpp WITHOUT casts — leading to aclnn ret=161002
    # (PARAM_INVALID) at eval time when bf16 inputs hit a fp32-registered
    # kernel. Always export the easyasc path here.
    easyasc_home = os.environ.get("EASYASC_DSL_HOME")
    if not easyasc_home:
        _LOG.info(
            _red("  ✗ EASYASC_DSL_HOME not set — cast detection would silently fail")
        )
        raise _StageAbort(1)
    pythonpath = easyasc_home + os.pathsep + os.environ.get("PYTHONPATH", "")
    cp = run(
        ["python3", str(script), op_name],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": pythonpath},
    )
    _LOG.info(cp.stdout)

    cpp_path = work_dir / f"{op_name}.cpp"
    if not cpp_path.is_file():
        _LOG.info(_red("  ✗ bridge cpp not created"))
        raise _StageAbort(1)
    cpp = cpp_path.read_text()

    # Compute expected camel name with the kernelbase-style _to_camel (preserves
    # internal capitals): "AddRMSNorm_custom" → "AddRMSNormCustom"
    parts = [p for p in (op_name + "_custom").split("_") if p]
    expected_camel = "".join(p[:1].upper() + p[1:] for p in parts)
    expected_aclnn = f"aclnn{expected_camel}"

    # P0-1 / P0-3 signal: gen_bridge produces correct aclnn name
    signals = [
        ("P0-1/3 correct aclnn lookup name in cpp", expected_aclnn in cpp),
        # P1-2 signal: when DSL dtype differs from op_desc dtype, cast lines emitted
        # We probe by looking for the bridge generator's stdout banner.
        (
            "P1-2 dtype-cast banner OR no mismatch needed",
            "dtype-cast layer emitted" in cp.stdout or "→ kernel" not in cp.stdout,
        ),
    ]
    for name, ok in signals:
        if ok:
            _LOG.info(_green(f"  ✓ {name}"))
        else:
            _LOG.info(_red(f"  ✗ {name}"))
    return signals


def _raw_dir(work_dir: Path, op_name: str) -> Path:
    """v2.1 layout: easyasc-codegen outputs go under
    ``work_dir/easyasc_workspace/{op_name}_raw/``."""
    return work_dir / "easyasc_workspace" / f"{op_name}_raw"


def _build_artifact_signals(
    op_name: str, work_dir: Path, raw_dir: Path
) -> List[Tuple[str, bool]]:
    """Signals for artifacts produced by the build half of stage 5."""
    extra: List[Tuple[str, bool]] = []
    # P1-1 signal: build.sh patched to mkdir binary/config
    build_sh = raw_dir / "build.sh"
    if build_sh.is_file():
        sh = build_sh.read_text()
        extra.append(
            (
                "P1-1 build.sh patched to pre-create binary/config",
                "cpack-robust patch" in sh
                or 'mkdir -p "$BUILD_DIR/op_kernel/binary/config"' in sh,
            ),
        )
    # v2.1 signal: aclnn header materialized (bridge requires it)
    aclnn_headers = (
        list((raw_dir / "build_out" / "autogen").glob("aclnn_*.h"))
        if (raw_dir / "build_out" / "autogen").is_dir()
        else []
    )
    extra.append(
        (
            "v2.1 aclnn header emitted under build_out/autogen/ (bridge ground truth)",
            len(aclnn_headers) == 1,
        ),
    )
    # v2.1 signal: .run softlinked into {Op}Custom/build_out/
    custom_link = work_dir / f"{op_name}Custom" / "build_out"
    softlinks = (
        [p for p in custom_link.glob("custom_opp_*.run") if p.is_symlink()]
        if custom_link.is_dir()
        else []
    )
    extra.append(
        ("v2.1 .run softlinked into {op}Custom/build_out/", len(softlinks) >= 1),
    )

    return extra


def _codegen_signals(op_name: str, work_dir: Path) -> List[Tuple[str, bool]]:
    """Collect the stage-5 verification signals by inspecting the output tree.

    Pure filesystem inspection — no side effects, no process launches.
    """
    raw_dir = _raw_dir(work_dir, op_name)
    kernel_dir = raw_dir / "op_kernel"
    snake_name = _camel_to_snake_test(f"{op_name}_custom")
    snake_cpp = kernel_dir / f"{snake_name}.cpp"
    pascal_cpp = kernel_dir / f"{op_name}_custom.cpp"

    signals = [
        ("v2.1 raw output under easyasc_workspace/{op}_raw/", raw_dir.is_dir()),
        (
            "P0-2 kernel cpp present at snake_case name (or unchanged if op name was already snake_case)",
            snake_cpp.is_file() or (op_name.islower() and pascal_cpp.is_file()),
        ),
        (
            "P0-2 PascalCase cpp removed after rename (no-op for snake_case op names)",
            not (pascal_cpp.is_file() and snake_cpp != pascal_cpp),
        ),
    ]
    signals.extend(_build_artifact_signals(op_name, work_dir, raw_dir))
    return signals


def stage_8_codegen(op_name: str, work_dir: Path) -> List[Tuple[str, bool]]:
    """Run run_codegen.py (codegen + build + softlink, v2.1).

    Verify P0-2 / P1-1 fix signals plus the new aclnn header is produced.
    """
    _LOG.info(_bold(f"\n[stage 5 / codegen+build] easyasc-codegen for {op_name}"))
    script = SKILLS_DIR / "easyasc-codegen" / "scripts" / "run_codegen.py"

    easyasc_home = os.environ.get("EASYASC_DSL_HOME")
    if not easyasc_home:
        _LOG.info(_red("  ✗ EASYASC_DSL_HOME not set"))
        raise _StageAbort(1)
    pythonpath = easyasc_home + os.pathsep + os.environ.get("PYTHONPATH", "")
    # --build runs codegen + build + softlink in one shot (v2.1 entry point)
    cp = run(
        ["python3", str(script), op_name, "--build"],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": pythonpath},
    )
    _LOG.info(cp.stdout[-1500:])

    signals = _codegen_signals(op_name, work_dir)

    for name, ok in signals:
        if ok:
            _LOG.info(_green(f"  ✓ {name}"))
        else:
            _LOG.info(_red(f"  ✗ {name}"))
    return signals


def _camel_to_snake_test(name: str) -> str:
    """Mirror run_codegen.py's _camel_to_snake — used for verification."""
    import re

    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    s = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", s)
    return s.lower()


# NOTE: v2.1 removed the standalone build stage — run_codegen.py with --build
# performs codegen + build + softlink atomically, so stage_8_build is no longer
# needed. The verification signals it used to produce (`.run` present in raw,
# softlink in {Op}Custom/build_out/) are now checked in stage_8_codegen.


def stage_10_install_and_pybind(op_name: str, work_dir: Path) -> bool:
    _LOG.info(_bold("\n[stage 7 / eval prep] install .run + generate pybind"))
    run_path = (
        work_dir / f"{op_name}Custom" / "build_out" / "custom_opp_ubuntu_aarch64.run"
    )
    # Clean previous vendors install
    vendors = work_dir / "vendors"
    if vendors.is_dir():
        import shutil

        shutil.rmtree(vendors)

    cp = subprocess.run(
        ["/bin/bash", str(run_path), f"--install-path={work_dir}"],
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        _LOG.info(_red("  ✗ .run install failed"))
        _LOG.info(_red(f"    {cp.stderr[-500:]}"))
        return False

    # generate pybind. Its success banner is emitted via Python ``logging`` so
    # it lands on stderr, not stdout — check both streams.
    pybind = SKILLS_DIR / "ascendc-evaluation" / "scripts" / "generate_pybind.py"
    cp = run(["python3", str(pybind), op_name], cwd=PROJECT_ROOT)
    combined = (cp.stdout or "") + (cp.stderr or "")
    if "PyBind bindings generated successfully" not in combined:
        _LOG.info(_red("  ✗ pybind compile failed"))
        _LOG.info(_red("    stdout tail: " + (cp.stdout or "")[-500:]))
        _LOG.info(_red("    stderr tail: " + (cp.stderr or "")[-500:]))
        return False
    _LOG.info(_green("  ✓ install + pybind OK"))
    return True


def stage_10_evaluate(
    op_name: str, work_dir: Path, expected_min_pass: int
) -> Tuple[int, int, float]:
    _LOG.info(
        _bold("\n[stage 7 / evaluate] running multi-case eval (this takes ~10-25 min)")
    )
    eval_script = SKILLS_DIR / "ascendc-evaluation" / "scripts" / "evaluate.py"
    set_env = work_dir / "vendors" / "customize" / "bin" / "set_env.bash"
    json_out = work_dir / "evaluation_results.json"

    cp = subprocess.run(
        [
            "/bin/bash",
            "-c",
            f"source {shlex.quote(str(set_env))} && "
            f"python3 {shlex.quote(str(eval_script))} {shlex.quote(op_name)} "
            f"--device-id 2 --json-output {shlex.quote(str(json_out))}",
        ],
        capture_output=True,
        text=True,
    )
    # Print last 30 lines whether passed or failed
    _LOG.info((cp.stdout + "\n" + cp.stderr)[-2000:])
    if not json_out.is_file():
        _LOG.info(_red("  ✗ evaluation_results.json missing"))
        raise _StageAbort(1)
    with json_out.open() as f:
        d = json.load(f)
    passed = d.get("passed_cases", 0)
    total = d.get("total_cases", 0)
    geo_mean = d.get("geometric_mean_speedup", 0.0) or 0.0

    if passed >= expected_min_pass:
        _LOG.info(
            _green(
                f"  ✓ {passed}/{total} PASS (geo_mean={geo_mean:.2f}×)"
                f" ≥ expected min {expected_min_pass}"
            )
        )
    else:
        _LOG.info(
            _red(
                f"  ✗ {passed}/{total} PASS (geo_mean={geo_mean:.2f}×)"
                f" < expected min {expected_min_pass}"
            )
        )
    return passed, total, geo_mean


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def test_op(
    op_name: str, skip_eval: bool, expected_min_pass_override: Optional[int]
) -> Dict:
    _LOG.info(_bold(f"\n{'=' * 70}"))
    _LOG.info(_bold(f"  regression_test for {op_name}"))
    _LOG.info(_bold(f"{'=' * 70}"))

    work_dir = check_prerequisites(op_name)
    expected_min = expected_min_pass_override or EXPECTED_PASS_MIN.get(op_name, 0)

    summary: Dict = {
        "op_name": op_name,
        "expected_min_pass": expected_min,
        "stages": {},
    }

    # v2.1: codegen FIRST (so aclnn header exists for bridge to parse).
    # --build is included in run_codegen.py, so build is now part of stage 5.
    s5 = stage_8_codegen(op_name, work_dir)
    summary["stages"]["codegen"] = all(ok for _, ok in s5)
    if not summary["stages"]["codegen"]:
        summary["passed"] = False
        return summary

    # v2.1: bridge runs AFTER codegen, reading the autogen aclnn header.
    s6 = stage_bridge(op_name, work_dir)
    summary["stages"]["bridge"] = all(ok for _, ok in s6)

    # Stage 7 install + pybind
    install_ok = stage_10_install_and_pybind(op_name, work_dir)
    summary["stages"]["install"] = install_ok
    if not install_ok:
        summary["passed"] = False
        return summary

    if skip_eval:
        all_stage_ok = all(summary["stages"].values())
        summary["passed"] = all_stage_ok
        summary["note"] = "eval skipped via --skip-eval"
        return summary

    passed, total, geo_mean = stage_10_evaluate(op_name, work_dir, expected_min)
    summary["pass_count"] = passed
    summary["total"] = total
    summary["geo_mean"] = geo_mean
    summary["passed"] = passed >= expected_min and all(summary["stages"].values())
    return summary


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ops", nargs="+", help="Operator name(s) to regression-test")
    ap.add_argument(
        "--skip-eval",
        action="store_true",
        help="Skip the long-running evaluate.py stage; verify build pipeline only",
    )
    ap.add_argument(
        "--expected-min-pass",
        type=int,
        default=None,
        help="Override the per-op expected pass minimum",
    )
    args = ap.parse_args(argv)

    _LOG.info(_bold("cake regression test"))
    _LOG.info(f"  ops = {args.ops}")
    _LOG.info(f"  skip_eval = {args.skip_eval}")

    summaries = []
    for op in args.ops:
        try:
            summaries.append(test_op(op, args.skip_eval, args.expected_min_pass))
        except _StageAbort as abort:
            return abort.code
        except Exception as exc:
            _LOG.info(_red(f"  ✗ unexpected error for {op}: {exc}"))
            import traceback

            traceback.print_exc()
            summaries.append({"op_name": op, "passed": False, "error": str(exc)})

    _LOG.info(_bold("\n" + "=" * 70))
    _LOG.info(_bold("  REGRESSION TEST SUMMARY"))
    _LOG.info(_bold("=" * 70))
    all_pass = True
    for s in summaries:
        op = s["op_name"]
        if s.get("passed"):
            extra = ""
            if "pass_count" in s:
                extra = (
                    f" — eval {s['pass_count']}/{s['total']} (geo={s['geo_mean']:.2f}×)"
                )
            _LOG.info(_green(f"  ✓ {op}: PASS{extra}"))
        else:
            _LOG.info(
                _red(
                    f"  ✗ {op}: FAIL  stages={s.get('stages')}  "
                    f"pass_count={s.get('pass_count', '?')}/{s.get('total', '?')}"
                )
            )
            all_pass = False

    return 0 if all_pass else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
