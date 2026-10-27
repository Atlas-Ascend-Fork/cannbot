#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""multirank op build driver (build Layer 3b + 5c).

Builds the op_host three libraries (cust_op_proto / cust_optiling / cust_opapi),
then the op_kernel binary (Layer 5c), then py_ext (NpuExtension /
torch::Dispatcher import) against the staged install tree.

Flow:
  1. cmake -S <op> -B <op>/.build --preset=default -DASCEND_CANN_PACKAGE_PATH=<cann>
     (configure stage runs opbuild -> autogen aclnn_*.h/.cpp, then rename_aclnn
     -> aclnnInner*, both via op_host/CMakeLists.txt execute_process injected by
     multirank_msopgen_scaffold._patch_op_host_cmakelists).
  2. Back-fill the wrapper signatures from .build/autogen/aclnn_{op}.h (the
     scaffold's wrapper ships a TODO placeholder; multirank_build reads the real
     aclnnInner{op_pascal} param list so the public aclnn{op_pascal} symbol matches).
  3. cmake --build .build -jN --target cust_op_proto cust_optiling cust_opapi
     (op_host three-stage; links nnopbase/ascendcl/intf_pub via msopgen CMake).
  4. cmake --build .build -jN --target binary
     (op_kernel binary — the msopgen add_kernels_compile umbrella target defined
     in cmake/func.cmake. Runs ascendc_compile_kernel.py per op via the target
     dependency graph, producing <OpType>_<md5>.o + binary_info_config.json.
     Depends on cust_optiling / liboptiling.so from stage 3.)

Does NOT fork build_ascendc.py (that is the flat-kernel + pybind11 path; multirank is
the msopgen opc path). HCCL is pulled in transitively via nnopbase
(msopgen already links nnopbase/ascendcl/intf_pub to cust_optiling + cust_opapi).
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

CANN_DEFAULT = "/usr/local/Ascend/cann-8.5.1"
BINARY_TARGET = "binary"
_DEFAULT_COMPUTE_UNIT = "ascend910b"


# ---------------------------------------------------------------------------
# env / path resolution
# ---------------------------------------------------------------------------
def _detect_cann() -> Path:
    for env_name in (
        "ASCEND_CANN_PACKAGE_PATH",
        "ASCEND_INSTALL_PATH",
        "ASCEND_HOME_PATH",
    ):
        v = os.environ.get(env_name)
        if v:
            return Path(v).expanduser().resolve()
    for c in (
        Path("/usr/local/Ascend/cann-8.5.1"),
        Path("/usr/local/Ascend/ascend-toolkit/latest"),
    ):
        if c.exists():
            return c.resolve()
    return Path(CANN_DEFAULT)


def _merge_set_env_exports(env: dict, set_env: Path) -> None:
    """Pull in everything CANN's set_env.sh exports (LD_LIBRARY_PATH etc.,
    needed by the opbuild tool run at configure)."""
    out = subprocess.run(
        ["/bin/bash", "-c", f"source '{set_env}' && env"],
        capture_output=True,
        text=True,
    )
    for line in out.stdout.splitlines():
        if "=" in line and not line.startswith("_="):
            k, _, v = line.partition("=")
            if k not in ("PWD", "SHLVL", "OLDPWD"):
                env[k] = v


def _resolve_env(cann: Path) -> dict:
    """Build the cmake subprocess env: inherit + force ASCEND_CANN_PACKAGE_PATH
    + merge set_env.sh exports."""
    env = os.environ.copy()
    env["ASCEND_CANN_PACKAGE_PATH"] = str(cann)
    set_env = cann / "set_env.sh"
    if set_env.is_file():
        _merge_set_env_exports(env, set_env)
    return env


def _resolve_op_dir(op: str) -> Path:
    p = Path(op)
    if not p.is_dir():
        raise FileNotFoundError(f"op project dir not found: {op}")
    return p.resolve()


def _find_op_name(op_dir: Path) -> str:
    """Derive the snake op name from the project dir name (prj-<op>) —
    deterministic, no op_host/*.cpp glob assumption (run.py derives the name
    the same way)."""
    return op_dir.name.removeprefix("prj-")


def _pascal(snake: str) -> str:
    return "".join(w[:1].upper() + w[1:] for w in re.split(r"[_-]", snake))


# ---------------------------------------------------------------------------
# warning filter (default-on for kernel compile)
# ---------------------------------------------------------------------------
_HARNESS_FILTER = (
    Path(__file__).resolve().parent.parent
    / "op_template_gen"
    / "multirank_assets"
    / "scripts"
    / "filter_build_warnings.py"
)


def _find_filter_script(op_dir: Path):
    """Resolve filter_build_warnings.py: prefer the workspace copy (scaffold
    ships it at <op>/scripts/), fall back to the harness asset
    (op_template_gen/multirank_assets/scripts/ — ported by a parallel task, may not
    exist yet; when neither copy exists run_filtered runs unfiltered)."""
    ws_copy = op_dir / "scripts" / "filter_build_warnings.py"
    if ws_copy.is_file():
        return ws_copy
    if _HARNESS_FILTER.is_file():
        return _HARNESS_FILTER
    return None


def run_filtered(
    cmd,
    *,
    filter_script=None,
    filter_warnings: bool = True,
    check=True,
    env=None,
    cwd=None,
):
    """Run cmd; when filter_warnings and a filter script is present, pipe the

    process stdout+stderr through filter_build_warnings.py (suppress CANN
    system-header warnings + dedup; errors always pass through). Exit code is
    preserved — raises CalledProcessError on failure when check, identical to
    subprocess.run(check=True).
    """
    if not filter_warnings or filter_script is None:
        if filter_warnings and filter_script is None:
            log.warning("filter_build_warnings.py not found; running unfiltered")
        subprocess.run(cmd, check=check, env=env, cwd=cwd)
        return
    log.info(f"{' '.join(str(c) for c in cmd)} | python3 {filter_script} -")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd,
        env=env,
    )
    filter_proc = subprocess.Popen(
        [sys.executable, str(filter_script), "-"], stdin=proc.stdout
    )
    proc.stdout.close()
    filter_proc.communicate()
    status = proc.wait()
    if check and status != 0:
        raise subprocess.CalledProcessError(status, cmd)


# ---------------------------------------------------------------------------
# configure + wrapper back-fill + build
# ---------------------------------------------------------------------------
def configure(
    op_dir: Path, build_dir: Path, cann: Path, env: dict, dump: bool = False
) -> None:
    cmd = [
        "cmake",
        "-S",
        str(op_dir),
        "-B",
        str(build_dir),
        "--preset=default",
        f"-DASCEND_CANN_PACKAGE_PATH={cann}",
        f"-DCMAKE_INSTALL_PREFIX={op_dir / '.install'}",
    ]
    if dump:
        cmd.append("-DASCENDC_DUMP=ON")
    subprocess.run(cmd, check=True, env=env)


def _split_top_level(s: str, sep: str = ",") -> list[str]:
    """Split on sep at paren/angle/bracket depth 0 (handles fn-ptr params)."""
    parts, depth, cur = [], 0, []
    for c in s:
        if c in "(<[":
            depth += 1
            cur.append(c)
        elif c in ")>]":
            depth -= 1
            cur.append(c)
        elif c == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    if cur:
        parts.append("".join(cur))
    return parts


def _param_names(params: str) -> str:
    """Extract bare argument names from a C param list (drop types)."""
    names = []
    for p in _split_top_level(params):
        p = p.strip()
        if not p or p == "void":
            continue
        m = re.search(r"([A-Za-z_]\w*)\s*(\[[^\]]*\])?\s*$", p)
        if m:
            names.append(m.group(1))
    return ", ".join(names)


@dataclass
class WrapperTemplateCtx:
    """Substitution values for the generated op wrapper .cpp template."""

    op: str
    op_pascal: str
    gws_params: str
    gws_args: str
    opr_params: str
    opr_args: str


def _wrapper_cpp_filled(tpl: WrapperTemplateCtx) -> str:
    return f"""#include "aclnn_{tpl.op}.h"

// HCCL server-type weak hook (CANN runtime contract, MTE vs AICPU routing).
enum NnopbaseHcclServerType {{
    NNOPBASE_HCCL_SERVER_TYPE_AICPU = 0,
    NNOPBASE_HCCL_SERVER_TYPE_MTE,
    NNOPBASE_HCCL_SERVER_TYPE_END
}};
// weak CANN runtime hook declaration (server-type routing, see enum above)
extern "C" void __attribute__((weak)) NnopbaseSetHcclServerType(
    void *executor, NnopbaseHcclServerType sType);

#ifdef __cplusplus
extern "C" {{
#endif

// Auto back-filled from .build/autogen/aclnn_{tpl.op}.h by multirank_build.py (configure
// stage ran opbuild + rename_aclnn -> aclnnInner; the public aclnn symbol below
// forwards to it, injecting the HCCL server type before exec).
__attribute__((visibility("default")))
aclnnStatus aclnn{tpl.op_pascal}GetWorkspaceSize({tpl.gws_params})
{{
    return aclnnInner{tpl.op_pascal}GetWorkspaceSize({tpl.gws_args});
}}

__attribute__((visibility("default")))
aclnnStatus aclnn{tpl.op_pascal}({tpl.opr_params})
{{
    // MTE routing rationale: the AICPU hccl service is offline on this path and
    // the window-RDMA lane (GetHcclContext/HcclResource reuse) needs the MTE
    // server — high-level HCCL collectives (HcclAllReduce etc.) ride the AICPU
    // service and conflict, so pin the type before the Inner forward.
    if (NnopbaseSetHcclServerType) {{
        NnopbaseSetHcclServerType(executor, NNOPBASE_HCCL_SERVER_TYPE_MTE);
    }}
    return aclnnInner{tpl.op_pascal}({tpl.opr_args});
}}

#ifdef __cplusplus
}}
#endif
"""


def backfill_wrapper(op_dir: Path, build_dir: Path, op: str, op_pascal: str) -> bool:
    """Read .build/autogen/aclnn_{op}.h (post-rename -> aclnnInner), extract the

    exact GetWorkspaceSize/op signatures, rewrite wrapper/aclnn_{op}.cpp. Returns
    False if the autogen header is absent (rename_aclnn failed at configure).
    """
    h = build_dir / "autogen" / f"aclnn_{op}.h"
    if not h.is_file():
        return False
    txt = h.read_text(encoding="utf-8", errors="ignore")
    gws = re.search(
        rf"aclnnStatus\s+aclnnInner{re.escape(op_pascal)}GetWorkspaceSize\s*\(([^;]*)\)",
        txt,
    )
    opr = re.search(
        rf"aclnnStatus\s+aclnnInner{re.escape(op_pascal)}\s*\(([^;]*)\)", txt
    )
    if not gws or not opr:
        return False
    gws_params, opr_params = gws.group(1).strip(), opr.group(1).strip()
    wrapper = op_dir / "op_host" / "wrapper" / f"aclnn_{op}.cpp"
    wrapper.write_text(
        _wrapper_cpp_filled(
            WrapperTemplateCtx(
                op=op,
                op_pascal=op_pascal,
                gws_params=gws_params,
                gws_args=_param_names(gws_params),
                opr_params=opr_params,
                opr_args=_param_names(opr_params),
            )
        ),
        encoding="utf-8",
    )
    return True


def install_target(
    build_dir: Path,
    env: dict,
    jobs: int,
    filter_script=None,
    filter_warnings: bool = True,
) -> None:
    """Build kernel binary (target `binary`) then stage the complete op package

    via cmake --target install (op_tiling/lib + op_api/lib + kernel binary +
    npu_supported_ops under CMAKE_INSTALL_PREFIX). Mirrors build.sh: --target
    binary, then --target install.
    """
    for tgt in ("binary", "install"):
        run_filtered(
            ["cmake", "--build", str(build_dir), f"-j{jobs}", "--target", tgt],
            filter_script=filter_script,
            filter_warnings=filter_warnings,
            check=True,
            env=env,
        )


def find_artifacts(build_dir: Path) -> dict:
    """Locate the op_host .so via OUTPUT_NAME (Unix `lib` prefix + cust_op_proto/

    cust_optiling OUTPUT_NAME overrides; target name != file name — design §build
    probe).
    """
    out = {}
    for name in (
        "libcust_opsproto_rt2.0.so",
        "libcust_opmaster_rt2.0.so",
        "libcust_opapi.so",
    ):
        hits = list(build_dir.rglob(name))
        out[name] = hits[0] if hits else None
    return out


# ---------------------------------------------------------------------------
# kernel binary compile stage (Layer 5c)
# ---------------------------------------------------------------------------
def _read_compute_unit(build_dir: Path) -> str:
    """ASCEND_COMPUTE_UNIT from the cmake cache (CMakePresets default sets it)."""
    cache = build_dir / "CMakeCache.txt"
    if cache.is_file():
        for line in cache.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("ASCEND_COMPUTE_UNIT:"):
                return line.split("=", 1)[1].strip()
    return _DEFAULT_COMPUTE_UNIT


# Kernel-binary layout candidates (msopgen template generations):
#   legacy:     op_kernel/binary/<unit>/<snake_op>/
#   msopgen-26: op_kernel/ascendc_kernels/binary/<unit>/<snake_op>/
# (ascendc_kernels = the npu_op_kernel_library target name — the 26.x macro
# style nests the whole binary/tbe tree one level under the kernel target's
# dir; CANN 9.1.0 func.cmake:406/1149 + ascendc_compile_kernel.py:186.)
_KERNEL_BINARY_SUBDIRS = ("binary", "ascendc_kernels/binary")


def find_kernel_binary(
    build_dir: Path, op_name: str, compute_unit: str = _DEFAULT_COMPUTE_UNIT
) -> dict:
    """Locate the compiled kernel binary + its metadata. The per-op dir

    binary/<unit>/<snake_op>/ holds exactly one <PascalOp>_<md5>.{o,json} pair
    (legacy layout); the msopgen-26 macro style nests the same tree one level
    deeper under ascendc_kernels/. The candidate that yields the .o also
    anchors the companion paths (binary_info_config is legacy-only — 26.x
    does not generate it; npu_supported_ops sits at the kernel tree root's
    tbe/op_info_cfg/ai_core/ in both).
    """
    for sub in _KERNEL_BINARY_SUBDIRS:
        base = build_dir / "op_kernel" / sub
        op_bin_dir = base / compute_unit / op_name
        objs = sorted(op_bin_dir.glob("*.o")) if op_bin_dir.is_dir() else []
        if objs:
            break
    else:
        tried = [
            str(build_dir / "op_kernel" / s / compute_unit / op_name)
            for s in _KERNEL_BINARY_SUBDIRS
        ]
        raise FileNotFoundError(
            f"kernel binary not found: expected <PascalOp>_<md5>.o under one "
            f"of {tried} (cmake --target {BINARY_TARGET} did not produce it)"
        )
    if len(objs) > 1:
        raise RuntimeError(
            f"multiple kernel binaries under {op_bin_dir}: "
            f"{[o.name for o in objs]} (stale --no-clean collision; clean .build "
            f"and rebuild)"
        )
    return {
        "obj": objs[0],
        "meta": objs[0].with_suffix(".json"),
        "binary_info_config": base
        / "config"
        / compute_unit
        / "binary_info_config.json",
        "npu_supported_ops": base.parent
        / "tbe"
        / "op_info_cfg"
        / "ai_core"
        / "npu_supported_ops.json",
    }


# ---------------------------------------------------------------------------
# py_ext launch layer (cmake-installed op package -> build_ext Python extension)
# ---------------------------------------------------------------------------
def _opp_path(op_dir: Path) -> Path:
    """ASCEND_CUSTOM_OPP_PATH: cmake install lays op_api under
    packages/vendors/<vendor>/ (msopgen default vendor_name=customize).

    Keep-in-sync with multirank_runner._activate_opp_env (orchestrator/multirank_runner.py,
    ported by a follow-up task): the runner recomputes this same
    <op_project>/.install/packages/vendors/customize path to set
    ASCEND_CUSTOM_OPP_PATH at run time — setup_operator_env below only applies
    it to the build_ext subprocess env, it is never persisted."""
    return op_dir / ".install" / "packages" / "vendors" / "customize"


def setup_operator_env(op_dir: Path, env: dict) -> dict:
    """ASCEND_CUSTOM_OPP_PATH + LD_LIBRARY_PATH for py_ext build_ext (so setup.py

    finds op_api/include + op_api/lib, and the linker finds libcust_opapi.so).
    """
    opp = _opp_path(op_dir)
    e = env.copy()
    e["ASCEND_CUSTOM_OPP_PATH"] = str(opp)
    lib = str(opp / "op_api" / "lib")
    e["LD_LIBRARY_PATH"] = lib + ":" + e.get("LD_LIBRARY_PATH", "")
    return e


def build_ext(
    op_dir: Path, env: dict, filter_script=None, filter_warnings: bool = True
) -> None:
    """python setup.py build_ext --inplace -> py_ext/_C*.so. Requires op_host

    install first (libcust_opapi.so + aclnn_*.h under ASCEND_CUSTOM_OPP_PATH).
    NpuExtension compiles ext_{op}.cpp + links libcust_opapi.so (aclnn via dlsym).
    """
    py_ext = op_dir / "py_ext"
    run_filtered(
        [
            "python3",
            str(py_ext / "setup.py"),
            "build",
            "--build-base",
            str(op_dir / ".build_ext"),
            "build_ext",
            "--inplace",
        ],
        filter_script=filter_script,
        filter_warnings=filter_warnings,
        check=True,
        env=env,
        cwd=str(op_dir),
    )


def find_py_ext_so(op_dir: Path):
    """py_ext/_C*.so produced by build_ext --inplace (loaded by __init__.py)."""
    hits = list((op_dir / "py_ext").glob("_C*.so"))
    return hits[0] if hits else None


@dataclass
class BuildOptions:
    """Build-affecting switches for build() — defaults are the shipped
    behavior; override per keyword at the call site.
    """

    jobs: int = 8
    clean: bool = True
    with_py_ext: bool = True
    with_kernel_binary: bool = True
    filter_warnings: bool = True
    dump: bool = False


def build(op: str, options: "BuildOptions | None" = None) -> dict:
    if options is None:
        options = BuildOptions()
    cann = _detect_cann()
    env = _resolve_env(cann)
    op_dir = _resolve_op_dir(op)
    filter_script = _find_filter_script(op_dir)
    op_name = _find_op_name(op_dir)
    op_pascal = _pascal(op_name)
    build_dir = op_dir / ".build"
    if options.clean and build_dir.exists():
        shutil.rmtree(build_dir)
    configure(op_dir, build_dir, cann, env, dump=options.dump)
    if not backfill_wrapper(op_dir, build_dir, op_name, op_pascal):
        log.error(
            f"[multirank_build] WARNING: wrapper back-fill skipped — autogen aclnn_"
            f"{op_name}.h not found (opbuild/rename may have failed at configure)"
        )
    install_target(build_dir, env, options.jobs, filter_script, options.filter_warnings)
    compute_unit = _read_compute_unit(build_dir)
    result = {
        "op": op_name,
        "op_pascal": op_pascal,
        "build_dir": build_dir,
        "artifacts": find_artifacts(build_dir),
        "kernel_binary": find_kernel_binary(build_dir, op_name, compute_unit),
    }
    if options.with_py_ext:
        ext_env = setup_operator_env(op_dir, env)
        build_ext(op_dir, ext_env, filter_script, options.filter_warnings)
        result["py_ext_so"] = find_py_ext_so(op_dir)
    return result


def _build_args():
    """Parse the CLI contract."""
    ap = argparse.ArgumentParser(
        description="multirank op build driver (op_host + kernel binary + py_ext)"
    )
    ap.add_argument("op", help="op project dir (multirank_msopgen_scaffold output)")
    ap.add_argument("-j", "--jobs", type=int, default=8)
    ap.add_argument(
        "--no-kernel-binary",
        action="store_true",
        help="Skip the op_kernel binary stage (also skips py_ext — a "
        "py_ext without a kernel binary is not runnable)",
    )
    ap.add_argument(
        "--no-py-ext",
        action="store_true",
        help="Skip op_host install + py_ext build_ext (op_host + kernel binary only)",
    )
    ap.add_argument(
        "--no-filter-warnings",
        action="store_true",
        help="Disable build warning filter (show raw CANN system-header warnings)",
    )
    ap.add_argument(
        "--dump",
        action="store_true",
        help="Enable ASCENDC_DUMP (-DASCENDC_DUMP=1) for this build — "
        "kernel debug prints ON. Never use for gate/perf verdicts "
        "(dump perturbs precision and adds overhead).",
    )
    return ap.parse_args()


def _log_build_result(r: dict, with_kernel_binary: bool, with_py_ext: bool) -> bool:
    """Print the build artifacts; returns the overall ok flag."""
    log.info(f"[multirank_build] built {r['op_pascal']} in {r['build_dir']}")
    for name, p in r["artifacts"].items():
        log.info(f"  {name}: {p}")
    if "kernel_binary" in r:
        log.info(f"  kernel binary: {r['kernel_binary']['obj']}")
    if "py_ext_so" in r:
        log.info(f"  py_ext .so: {r['py_ext_so']}")
    ok = all(r["artifacts"].values())
    if with_kernel_binary:
        ok = ok and "kernel_binary" in r and r["kernel_binary"]["obj"].is_file()
    if with_py_ext:
        ok = ok and r.get("py_ext_so") is not None
    return ok


def main() -> int:
    args = _build_args()
    with_kernel_binary = not args.no_kernel_binary
    with_py_ext = not args.no_py_ext and with_kernel_binary
    r = build(
        args.op,
        BuildOptions(
            jobs=args.jobs,
            with_py_ext=with_py_ext,
            with_kernel_binary=with_kernel_binary,
            filter_warnings=not args.no_filter_warnings,
            dump=args.dump,
        ),
    )
    return 0 if _log_build_result(r, with_kernel_binary, with_py_ext) else 1


if __name__ == "__main__":
    sys.exit(main())
