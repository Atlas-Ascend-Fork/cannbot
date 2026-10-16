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
Driver script for the easyasc-codegen skill.

Loads `output/{op_name}/{op_name}_dsl.py`, looks up the `{op_name}_custom`
kernel + the file's `build_codegen_inputs()` builder, and invokes
`OpExec(simulator=False, gen_only=True, out_dir=...)` to emit AscendC
sources into `output/{op_name}/easyasc_workspace/{op_name}_raw/`. After
that, optionally builds the project (`--build`) and softlinks the produced
`.run` into `output/{op_name}/{op_name}Custom/build_out/`. The
`{op_name}Custom/` directory is created here (was previously the bridge's
job — bridge now runs *after* codegen so it can read the autogen aclnn
header for ground-truth ordering).

Layout produced:

    output/{op_name}/
    ├── easyasc_workspace/
    │   └── {op_name}_raw/         ← isolated easyasc-codegen artifacts
    │       ├── op_host/, op_kernel/, ...
    │       ├── build.sh           ← patched for CPack robustness
    │       └── build_out/         ← only after --build
    │           ├── autogen/aclnn_*.h          ← bridge reads this
    │           └── custom_opp_*.run            ← softlink target
    └── {op_name}Custom/
        └── build_out/
            └── custom_opp_*.run  ← softlink → ../../easyasc_workspace/...

Usage:
    PYTHONPATH=${EASYASC_DSL_HOME}:${PYTHONPATH} python3 run_codegen.py <op_name>
        [--build] [--output-root output]

a2/a5 gate (mirrors fm-easyasc): the workspace's codegen_status.json carries an
immutable ``target_device`` (set by init_workspace.sh). Only ``a2`` (ascend910b)
supports real AscendC codegen on this host. For ``a5`` this driver REFUSES —
the a5 path is simulator-only (the DSL file's ``__main__`` self-check) and ends
``report-only`` (no .run, no aclnn header, so the downstream bridge cannot run).
If codegen_status.json is absent, target defaults to ``a2`` (backward compatible).

Exit codes:
    0  — codegen succeeded; expected output files exist
    2  — DSL file or required entry points missing, or target_device=a5 (refused)
    3  — kernel function name does not match {op_name}_custom
    4  — codegen ran but expected output files are not present
    5  — --build was requested but build.sh failed
"""

import argparse
import importlib.util
import json
import logging
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


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


class _CodegenAbort(Exception):
    """致命错误。由入口捕获后打印并转为退出码，不在函数内直接结束进程。"""

    def __init__(self, code: int, msg: str) -> None:
        super().__init__(msg)
        self.code = code


def _die(code, msg):
    """中止本次运行。原实现直接 sys.exit，现改为抛出由入口统一处理。"""
    raise _CodegenAbort(code, msg)


def _camel_to_snake(name: str) -> str:
    """Mirror AscendC build harness's ``optype_snake_ex``
    (``cmake/util/ascendc_impl_build.py:302``).

    Insert underscore before each capital that follows a lowercase / digit, AND
    between consecutive capitals followed by a lowercase (so "AddRMSNorm" splits
    into ``Add_RMS_Norm``). Then lowercase everything.

    Used to translate easyasc's PascalCase kernel filename
    (e.g. ``AddRMSNorm_custom.cpp``) into the snake_case form the AscendC
    compile harness expects (``add_rms_norm_custom.cpp``).

        >>> _camel_to_snake("AddRMSNorm_custom")
        'add_rms_norm_custom'
        >>> _camel_to_snake("DynamicQuantCustom")
        'dynamic_quant_custom'
        >>> _camel_to_snake("dynamic_quant_custom")
        'dynamic_quant_custom'
        >>> _camel_to_snake("FooBar")
        'foo_bar'
    """
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    s = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", s)
    return s.lower()


def _ensure_cpack_robust_build_sh(build_sh_path: Path):
    """Patch the generated ``build.sh`` so CPack does not crash on a missing
    ``build_out/op_kernel/binary/config/`` directory.

    Background: easyasc's emitted ``build.sh`` invokes ``cmake --target binary``
    (which generates the kernel ``.o``/.json files into ``build_out/op_kernel/
    binary/ascend910b/`` and ``binary/config/``), then ``cmake --target package``
    which runs CPack. CPack's install step has a hard-coded ``file INSTALL`` for
    ``binary/config/`` — if the binary target failed *and was retried in a
    half-cooked state*, the config subdirectory may not exist yet and CPack
    aborts with::

        CMake Error at .../cmake_install.cmake (file):
          file INSTALL cannot find ".../build_out/op_kernel/binary/config":
          No such file or directory.

    This typically happens after fixing a kernel-compile error and rerunning
    ``bash build.sh`` from a partially populated ``build_out/`` (see
    ``output/AddRMSNorm/REVIEW.md §5.2 #3``).

    The fix is a one-liner ``mkdir -p`` injected right before the ``package``
    target. Idempotent if applied twice.
    """
    if not build_sh_path.is_file():
        return
    text = build_sh_path.read_text()
    sentinel = "# [easyasc-codegen] cpack-robust patch"
    if sentinel in text:
        return  # already patched
    # Locate the line that builds the `package` (or `$target`) target. There
    # are two occurrences in the upstream build.sh (cross-compile and native
    # branches); patch both. Pattern: `cmake --build "$BUILD_DIR" --target $target` etc.
    inject = (
        f"\n  {sentinel}: pre-create binary/config so CPack install step succeeds even on partial builds\n"
        f'  mkdir -p "$BUILD_DIR/op_kernel/binary/config"\n'
    )
    # Insert before each occurrence of `cmake --build "$BUILD_DIR" --target $target`.
    needle = 'cmake --build "$BUILD_DIR" --target $target'
    if needle not in text:
        # different upstream form — try the literal `package` target
        needle = 'cmake --build "$BUILD_DIR" --target package'
    if needle in text:
        text = text.replace(needle, inject.lstrip("\n") + "  " + needle)
        build_sh_path.write_text(text)
        _LOG.info(
            "[easyasc-codegen] patched build.sh to mkdir binary/config before package target"
        )


def _rename_kernel_files_to_snake_case(op_kernel_dir: Path, kernel_func_name: str):
    """Rename easyasc-codegen's PascalCase kernel files to snake_case in-place.

    Why this exists: easyasc-codegen emits the kernel cpp using the literal
    Python kernel function name (e.g. ``AddRMSNorm_custom.cpp``), but the
    AscendC compile harness — invoked by the generated ``build.sh`` — derives
    the expected filename from the registered op_type using a CamelCase →
    snake_case conversion (``AddRMSNormCustom`` → ``add_rms_norm_custom``).
    When the kernel function name contains internal capitals (RMS, CV etc.)
    the two names diverge and ``ascendc_compile_kernel.py`` errors with
    ``[ERROR] operator: <snake> source file does not found``.

    This helper post-processes ``op_kernel/`` so the generated project is
    self-consistent. Op-host files keep their PascalCase names (that's the
    AscendC convention for op_type cpp filenames).

    For names that don't have internal capitals (e.g.
    ``dynamic_quant_custom``), this is a no-op — the snake-cased form equals
    the original.

    Renames:
      - ``{kernel_func_name}.cpp``       → ``{snake_name}.cpp``
      - ``{kernel_func_name}_cube.h``    → ``{snake_name}_cube.h``
      - ``{kernel_func_name}_vec.h``     → ``{snake_name}_vec.h``

    Then patches inside the renamed ``.cpp`` and helper ``.h`` files:
      - ``#include "{kernel_func_name}_cube.h"`` → snake form
      - ``#include "{kernel_func_name}_vec.h"``  → snake form
      - ``void {kernel_func_name}(...)``          → ``void {snake_name}(...)``
      - calls to ``{kernel_func_name}_cube(...)`` / ``_vec(...)`` → snake form
    """
    snake_name = _camel_to_snake(kernel_func_name)
    if snake_name == kernel_func_name:
        return snake_name  # nothing to do

    # 1) rename files
    for suffix in (".cpp", "_cube.h", "_vec.h"):
        src = op_kernel_dir / f"{kernel_func_name}{suffix}"
        dst = op_kernel_dir / f"{snake_name}{suffix}"
        if src.exists():
            src.rename(dst)

    # 2) patch cpp internals
    cpp_path = op_kernel_dir / f"{snake_name}.cpp"
    if cpp_path.exists():
        t = cpp_path.read_text()
        t = t.replace(f'"{kernel_func_name}_cube.h"', f'"{snake_name}_cube.h"')
        t = t.replace(f'"{kernel_func_name}_vec.h"', f'"{snake_name}_vec.h"')
        t = re.sub(
            rf"\bvoid {re.escape(kernel_func_name)}\(",
            f"void {snake_name}(",
            t,
        )
        t = t.replace(f"{kernel_func_name}_cube(", f"{snake_name}_cube(")
        t = t.replace(f"{kernel_func_name}_vec(", f"{snake_name}_vec(")
        cpp_path.write_text(t)

    # 3) patch helper headers' function symbols
    for h_suffix in ("_cube", "_vec"):
        h_path = op_kernel_dir / f"{snake_name}{h_suffix}.h"
        if h_path.exists():
            t = h_path.read_text()
            t = t.replace(
                f"{kernel_func_name}{h_suffix}(",
                f"{snake_name}{h_suffix}(",
            )
            h_path.write_text(t)

    _LOG.info(
        f"[easyasc-codegen] renamed PascalCase kernel files → snake_case "
        f"({kernel_func_name} → {snake_name})"
    )
    return snake_name


def _load_dsl_module(dsl_path: Path):
    spec = importlib.util.spec_from_file_location("op_dsl_module", dsl_path)
    if spec is None or spec.loader is None:
        _die(2, f"failed to spec-load {dsl_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_build(out_dir: Path) -> None:
    """Run `bash build.sh` inside out_dir with CANN env sourced.

    Aborts with code 5 on failure (build is opt-in via --build; if requested,
    a failed build is fatal so the caller doesn't miss the breakage).
    """
    ascend_home = os.environ.get("ASCEND_HOME_PATH")
    if not ascend_home:
        _die(
            5,
            "--build requested but ASCEND_HOME_PATH is not set; "
            "source /usr/local/Ascend/cann-*/bin/setenv.bash first",
        )
    setenv = Path(ascend_home) / "bin" / "setenv.bash"
    if not setenv.is_file():
        _die(5, f"--build requested but {setenv} does not exist")

    _LOG.info(f"[easyasc-codegen] running build.sh in {out_dir}")
    # Source setenv.bash then run build.sh in a single bash invocation.
    cmd = (
        f"source {shlex.quote(str(setenv))} && "
        f"cd {shlex.quote(str(out_dir))} && /bin/bash build.sh"
    )
    ret = subprocess.call(["/bin/bash", "-c", cmd])
    if ret != 0:
        _die(5, f"build.sh failed in {out_dir} with exit code {ret}")
    _LOG.info("[easyasc-codegen] build.sh OK")


def _softlink_run(out_dir: Path, custom_build_out: Path) -> None:
    """Find `out_dir/build_out/custom_opp_*.run` and softlink it into
    `custom_build_out/`. Idempotent: removes any prior symlink at the
    destination before relinking."""
    src_glob = list((out_dir / "build_out").glob("custom_opp_*.run"))
    if not src_glob:
        _die(
            4,
            f"no custom_opp_*.run found in {out_dir / 'build_out'}; "
            f"did build.sh actually produce the installer?",
        )
    if len(src_glob) > 1:
        _ERR.info(
            f"[easyasc-codegen] WARNING: multiple .run files found, picking {src_glob[0].name}"
        )
    src = src_glob[0].resolve()
    custom_build_out.mkdir(parents=True, exist_ok=True)
    dst = custom_build_out / src.name
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    dst.symlink_to(src)
    _LOG.info(f"[easyasc-codegen] softlink: {dst} → {src}")


def build_arg_parser() -> argparse.ArgumentParser:
    """命令行参数定义。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("op_name", help="Operator name, e.g. 'softmax' or 'layer_norm'")
    ap.add_argument(
        "--output-root",
        default="output",
        help="Root directory under which {op_name}/ lives (default: output)",
    )
    ap.add_argument(
        "--build",
        action="store_true",
        help="Also run `bash build.sh` and softlink the resulting .run into "
        "{op_name}Custom/build_out/. Requires ASCEND_HOME_PATH to be set.",
    )
    return ap


def enforce_a2_only_gate(workspace_dir: Path) -> Path:
    """a2/a5 门禁：真实 AscendC codegen 只在 a2 上做。返回 status 文件路径。

    target_device 由 init_workspace.sh 写入 codegen_status.json 且不可变；
    文件缺失时按 a2 处理（向后兼容）。a5 为仅仿真/仅报告，此处直接终止。
    """
    # a2/a5 gate: real AscendC codegen is a2-only. Read the immutable
    # target_device from codegen_status.json (seeded by init_workspace.sh);
    # default a2 when the status file is absent (backward compatible).
    target_device = "a2"
    status_path = workspace_dir / "codegen_status.json"
    if status_path.is_file():
        try:
            target_device = (
                json.loads(status_path.read_text()).get("target_device", "a2") or "a2"
            )
        except (ValueError, OSError):
            target_device = "a2"
    if target_device == "a5":
        # a5 is simulator-only / report-only: refuse real codegen, record the
        # terminal state so the agent skips the bridge + evaluation stages.
        try:
            status = (
                json.loads(status_path.read_text()) if status_path.is_file() else {}
            )
            status["next_step"] = "report-only"
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(json.dumps(status, indent=2))
        except (ValueError, OSError):
            pass
        _die(
            2,
            "target_device=a5 — AscendC codegen is a2-only on this host. "
            "The a5 path is simulator-only (run the DSL file's __main__ "
            "self-check) and ends report-only; the bridge/evaluation stages "
            "are skipped.",
        )
    return status_path


def load_and_validate_dsl(dsl_path: Path, op_name: str):
    """导入 DSL 模块并校验其导出，返回 (kernel, op_args)。"""
    expected_kernel = f"{op_name}_custom"
    _LOG.info(f"[easyasc-codegen] loading DSL: {dsl_path}")
    module = _load_dsl_module(dsl_path)

    if not hasattr(module, expected_kernel):
        _die(
            3,
            f"DSL module has no kernel named '{expected_kernel}'. "
            f"cake requires the kernel function to be named "
            f"`{op_name}_custom` so its codegen-derived AscendC op_type "
            f"matches CAKE's pybind wrapper. Rename the kernel and re-run "
            f"dsl-baseline-generation-easyasc.",
        )

    if not hasattr(module, "build_codegen_inputs"):
        _die(
            2,
            "DSL module is missing the required `build_codegen_inputs()` "
            "function. dsl-baseline-generation-easyasc must emit this "
            "module-level builder so the codegen driver knows how to "
            "construct the OpExec arguments.",
        )

    kernel = getattr(module, expected_kernel)
    op_args = module.build_codegen_inputs()

    if not isinstance(op_args, tuple):
        _die(
            2,
            f"build_codegen_inputs() must return a tuple, got {type(op_args).__name__}",
        )
    return kernel, op_args, expected_kernel


def build_and_collect(out_dir: Path, custom_build_out: Path, do_build: bool):
    """按需执行 build.sh，并回收 .run 包与 aclnn 头路径，返回 (run_pkg, aclnn_h)。"""
    aclnn_h = None
    run_pkg = None
    if do_build:
        _run_build(out_dir)
        _softlink_run(out_dir, custom_build_out)
        run_glob = list((out_dir / "build_out").glob("custom_opp_*.run"))
        run_pkg = str(run_glob[0].resolve()) if run_glob else None
        # Also surface the aclnn header path so the next stage (bridge) can
        # locate it without re-globbing.
        aclnn_h = next((out_dir / "build_out" / "autogen").glob("aclnn_*.h"), None)
        if aclnn_h is not None:
            _LOG.info(f"[easyasc-codegen] aclnn_header = {aclnn_h.resolve()}")
        else:
            _ERR.info(
                "[easyasc-codegen] WARNING: build_out/autogen/aclnn_*.h not found; "
                "stage 6 (bridge) will fail to read the ordering"
            )
    else:
        _LOG.info(
            f"[easyasc-codegen] next: re-run with --build, "
            f"or manually: source ${{ASCEND_HOME_PATH}}/bin/setenv.bash "
            f"&& cd {out_dir} && bash build.sh"
        )
    return run_pkg, aclnn_h


def record_terminal_status(
    status_path: Path, out_dir: Path, run_pkg, aclnn_h, do_build: bool
) -> None:
    """把终态写回 codegen_status.json，供 a2/a5 分支与后续阶段读取。"""
    # Record terminal state in codegen_status.json (single source of truth for
    # the a2/a5 branch). next_step=bridge tells the agent to proceed to stage 6
    # once the build produced the aclnn header.
    if status_path.is_file():
        try:
            status = json.loads(status_path.read_text())
            status["ascendc_generated"] = True
            status["raw_dir"] = str(out_dir.resolve())
            if run_pkg:
                status["run_package"] = run_pkg
            if aclnn_h is not None:
                status["aclnn_header"] = str(aclnn_h.resolve())
            status["next_step"] = (
                "bridge" if (do_build and aclnn_h is not None) else "build"
            )
            status_path.write_text(json.dumps(status, indent=2))
        except (ValueError, OSError):
            pass


def generate_ascendc_project(
    kernel, op_args, out_dir: Path, expected_kernel: str
) -> None:
    """运行 OpExec 生成 AscendC 工程，校验产物并做重命名与 build.sh 加固。

    OpExec 在运行期解析——easyasc 需经 PYTHONPATH 可导入。
    """
    # Resolve OpExec at runtime — easyasc must be importable via PYTHONPATH.
    try:
        from easyasc.torchplugin import OpExec  # type: ignore
    except ImportError as exc:
        _die(
            2,
            f"failed to import easyasc: {exc}. Ensure "
            f"PYTHONPATH includes ${{EASYASC_DSL_HOME}} and that "
            f"${{EASYASC_DSL_HOME}}/easyasc/ exists (run "
            f"bash ${{EASYASC_DSL_HOME}}/agent/scripts/init.sh if not).",
        )

    out_dir_abs = str(out_dir.resolve())
    _LOG.info(
        f"[easyasc-codegen] running OpExec(simulator=False, gen_only=True, out_dir={out_dir_abs})"
    )

    op = OpExec(kernel, out_dir=out_dir_abs, simulator=False, gen_only=True)
    op(*op_args)

    op_kernel_dir = out_dir / "op_kernel"
    op_host_dir = out_dir / "op_host"

    # Sanity: codegen should have written op_kernel/{expected_kernel}.cpp BEFORE
    # we run the snake-case rename. (op_host uses CamelCase op_type filenames,
    # which is the AscendC convention and stays untouched.)
    pre_rename_kernel_cpp = op_kernel_dir / f"{expected_kernel}.cpp"
    pre_rename_host_cpp = op_host_dir / f"{expected_kernel}.cpp"
    pre_missing = [
        str(p) for p in (pre_rename_kernel_cpp, pre_rename_host_cpp) if not p.is_file()
    ]
    if pre_missing:
        _die(
            4,
            "codegen ran but expected files are missing:\n  "
            + "\n  ".join(pre_missing)
            + f"\nList what's actually in {out_dir}:\n  "
            + "\n  ".join(sorted(str(p) for p in out_dir.rglob("*") if p.is_file())),
        )

    # Post-process: rename PascalCase kernel files to snake_case so the AscendC
    # compile harness can find them. No-op for snake_case-named kernels.
    snake_name = _rename_kernel_files_to_snake_case(op_kernel_dir, expected_kernel)

    # Post-process: harden build.sh so CPack doesn't crash on missing
    # binary/config dir during partial-rebuild scenarios.
    _ensure_cpack_robust_build_sh(out_dir / "build.sh")

    # Final sanity: the renamed kernel cpp must exist (or, if no rename was
    # needed, the original).
    final_kernel_cpp = op_kernel_dir / f"{snake_name}.cpp"
    if not final_kernel_cpp.is_file():
        _die(
            4,
            "post-rename kernel cpp missing:\n  "
            + str(final_kernel_cpp)
            + f"\nList what's actually in {op_kernel_dir}:\n  "
            + "\n  ".join(sorted(str(p) for p in op_kernel_dir.iterdir())),
        )


def main():
    args = build_arg_parser().parse_args()

    op_name = args.op_name
    op_dir = Path(args.output_root) / op_name
    dsl_path = op_dir / f"{op_name}_dsl.py"
    workspace_dir = op_dir / "easyasc_workspace"
    out_dir = workspace_dir / f"{op_name}_raw"
    custom_build_out = op_dir / f"{op_name}Custom" / "build_out"

    status_path = enforce_a2_only_gate(workspace_dir)

    if not dsl_path.is_file():
        _die(2, f"DSL file not found: {dsl_path}")

    kernel, op_args, expected_kernel = load_and_validate_dsl(dsl_path, op_name)

    # Ensure parent dir for codegen output exists; clear stale output to keep
    # codegen deterministic. Don't touch siblings (e.g. {op_name}Custom/).
    if out_dir.exists():
        import shutil

        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    generate_ascendc_project(kernel, op_args, out_dir, expected_kernel)

    _LOG.info(f"[easyasc-codegen] OK — generated AscendC project at {out_dir}")

    # Always pre-create {op_name}Custom/build_out/ (used by stage 6 bridge as
    # the eval expected location, even when --build is skipped — bridge needs
    # somewhere to point during sanity pybind compile).
    custom_build_out.mkdir(parents=True, exist_ok=True)

    run_pkg, aclnn_h = build_and_collect(out_dir, custom_build_out, args.build)

    record_terminal_status(status_path, out_dir, run_pkg, aclnn_h, args.build)


if __name__ == "__main__":
    try:
        main()
    except _CodegenAbort as abort:
        _ERR.info(f"[easyasc-codegen] ERROR: {abort}")
        sys.exit(abort.code)
