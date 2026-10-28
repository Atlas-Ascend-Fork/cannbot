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
"""Workflow startup dependency preflight for ops-perf-optimize.

Run this AFTER the optimization request is confirmed and BEFORE
``prepare_case_sets.py freeze``.  Every dependency the workflow's scripts,
harnesses, build and device chain need is checked in one pass, so missing
pieces surface here instead of mid-run:

* plugin scripts (prepare_case_sets / workflow_state / summarize / validators)
* configured Python environment (torch / torch_npu / numpy / ml_dtypes)
* CANN environment (resolved ASCEND_HOME_PATH, version, msprof, atc, opapi
  library family, aclnnArgMax/aclnnMax warmup symbols — incomplete installs
  are detected the way ``collect_perf_application.inspect_cann_environment``
  does at collection time)
* TTK (import check + multi-copy version-drift warning)
* build toolchain (git repo, build.sh, cmake, g++, makeself)
* device (visible, initializable, busy state, HBM)

Exit code 0 when no FATAL check failed (warnings allowed), 1 otherwise.
The JSON report path is printed on stdout.
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cli_output import emit

PLUGIN_DIR = Path(__file__).resolve().parent
PLUGIN_SCRIPTS = (
    "dsl_evidence.py",
    "prepare_case_sets.py",
    "workflow_state.py",
    "summarize_performance_effects.py",
    "performance_effect_evidence.py",
    "validate_implementation_conformance.py",
    "validate_integration_safety.py",
    "validate_source_isolation.py",
    "build_performance_targets.py",
    "validate_postprocess_performance.py",
    "validate_execution_identity.py",
)
OPAPI_FAMILY = (
    "libopapi.so",
    "libopapi_math.so",
    "libopapi_nn.so",
    "libopapi_transformer.so",
    "libopapi_cv.so",
    "libopapi_ras.so",
    "libopapi_oam.so",
)
WARMUP_SYMBOLS = ("aclnnArgMaxGetWorkspaceSize", "aclnnMaxGetWorkspaceSize")
TTK_REPO_URL = "https://gitcode.com/cann/ops-test-kit.git"
DEFAULT_TTK_ROOT = Path("/tmp/ops-test-kit")
COMMON_TTK_ROOTS = (
    DEFAULT_TTK_ROOT,
    Path.home() / "codex" / "ops-test-kit",
    Path.home() / "opscode" / "ops-test-kit",
)
TTK_STANDARD_SKILLS = (
    "ttk-how-run-test",
    "ttk-how-write-case",
    "ttk-how-write-plugin",
    "ttk-how-diagnose",
)
# Skill discovery dirs per client (mirrors init.sh):
# opencode -> .opencode/skills, claude -> .claude/skills,
# codex -> .agents/skills, codearts -> .codeartsdoer/skills
SKILL_DIR_CANDIDATES = (
    Path.cwd() / ".opencode" / "skills",
    Path.cwd() / ".claude" / "skills",
    Path.cwd() / ".agents" / "skills",
    Path.cwd() / ".codeartsdoer" / "skills",
    Path.home() / ".config" / "opencode" / "skills",
    Path.home() / ".claude" / "skills",
    Path.home() / ".agents" / "skills",
    Path.home() / ".codeartsdoer" / "skills",
)
MIN_FREE_GB = 20


class Report:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    @property
    def status(self) -> str:
        if any(check["status"] == "fail" for check in self.checks):
            return "fail"
        if any(check["status"] == "warn" for check in self.checks):
            return "warn"
        return "pass"

    def summary(self) -> dict:
        return {
            "status": self.status,
            "fail_count": sum(1 for c in self.checks if c["status"] == "fail"),
            "warn_count": sum(1 for c in self.checks if c["status"] == "warn"),
            "checks": self.checks,
        }

    def add(self, name: str, group: str, status: str, detail: str, fix: str = "") -> None:
        if status not in ("ok", "warn", "fail", "skip"):
            raise ValueError(f"invalid check status: {status}")
        self.checks.append({
            "name": name, "group": group, "status": status,
            "detail": detail, "fix": fix,
        })
        marker = {"ok": "[OK]  ", "warn": "[WARN]", "fail": "[FAIL]", "skip": "[SKIP]"}[status]
        emit(f"{marker} {group}/{name}: {detail}" + (f"  (fix: {fix})" if fix and status != "ok" else ""))


def run_shell(command: str, timeout: int = 120) -> tuple[int, str]:
    process = subprocess.run(
        ["/bin/bash", "-c", command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (process.stdout + process.stderr).strip()
    return process.returncode, output


def check_plugin_scripts(report: Report) -> None:
    import ast

    for name in PLUGIN_SCRIPTS:
        path = PLUGIN_DIR / name
        if not path.is_file():
            report.add(name, "plugin-scripts", "fail", f"missing {path}", "restore the plugin installation")
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as error:
            report.add(name, "plugin-scripts", "fail", f"syntax error: {error}", f"fix {path}")
            continue
        code, output = run_shell(f"{shlex.quote(sys.executable)} {shlex.quote(str(path))} --help")
        if code not in (0, 2):
            report.add(name, "plugin-scripts", "fail", f"--help exited {code}: {output[:160]}", f"fix {path}")
        else:
            report.add(name, "plugin-scripts", "ok", "parses and executes")


def load_request(report: Report, request_path: Path) -> dict:
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        report.add("request", "request", "fail", f"cannot read {request_path}: {error}", "fix the request file")
        return {}
    if request.get("confirmation", {}).get("status") != "confirmed":
        report.add("request", "request", "fail", "confirmation.status is not 'confirmed'", "re-confirm the request")
    else:
        report.add("request", "request", "ok", "confirmed")
    return request


def check_python_env(report: Report, python_exe: str, cann_command: str) -> None:
    if not Path(python_exe).is_file():
        report.add("python", "python-env", "fail", f"executable not found: {python_exe}",
                   "install the confirmed Python environment")
        return
    code, version = run_shell(f"{shlex.quote(python_exe)} --version")
    if code != 0:
        report.add("python", "python-env", "fail", f"--version exited {code}", "fix the Python installation")
        return
    report.add("python", "python-env", "ok", version)

    probe = (
        "import torch, torch_npu, numpy; "
        "assert torch.npu.is_available(), 'npu not available'; "
        "print('torch', torch.__version__, '| torch_npu', torch_npu.__version__, "
        "'| numpy', numpy.__version__)"
    )
    code, output = run_shell(
        f"{cann_command} && {shlex.quote(python_exe)} -c {shlex.quote(probe)}", timeout=180
    )
    if code != 0:
        report.add("torch_npu", "python-env", "fail", f"import/init failed: {output[-240:]}",
                   "match torch_npu with the CANN version or fix the environment")
        return
    report.add("torch_npu", "python-env", "ok", output)

    code, output = run_shell(
        f"{cann_command} && {shlex.quote(python_exe)} -c 'import ml_dtypes' 2>&1", timeout=60
    )
    if code != 0:
        report.add("ml_dtypes", "python-env", "warn",
                   "ml_dtypes missing (needed by bf16 CPU goldens)", "pip install ml_dtypes")
    else:
        report.add("ml_dtypes", "python-env", "ok", "importable")


def _cann_version(ascend_home: Path) -> tuple[str, str]:
    version = timestamp = ""
    for candidate in (
        ascend_home / "version.info",
        ascend_home / "x86_64-linux" / "version.info",
        ascend_home / "compiler" / "version.info",
        ascend_home / "opp" / "version.info",
        ascend_home / "runtime" / "version.info",
    ):
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "Version" and not version:
                version = value.strip()
            elif key.strip() == "timestamp" and not timestamp:
                timestamp = value.strip()
        if version:
            break
    return version, timestamp


def _cann_tools(report: Report, cann_command: str, backend: str = "ascendc") -> None:
    for tool in (("msprof", "bisheng") if backend == "cannbot_dsl" else ("msprof", "atc")):
        code, output = run_shell(f"{cann_command} && command -v {tool}")
        if code != 0:
            report.add(tool, "cann", "fail", f"{tool} not on PATH after sourcing CANN",
                       "complete the CANN installation")
        else:
            report.add(tool, "cann", "ok", output)


def _opapi_libraries(ascend_home: Path) -> dict[str, str]:
    lib_dirs = [
        directory
        for directory in (ascend_home / "x86_64-linux" / "lib64", ascend_home / "lib64")
        if directory.is_dir()
    ]
    present: dict[str, str] = {}
    for name in OPAPI_FAMILY:
        for directory in lib_dirs:
            candidate = directory / name
            if candidate.exists():
                present[name] = str(candidate)
                break
    return present


def _warmup_symbol_found(libraries: list[str]) -> bool:
    for symbol in WARMUP_SYMBOLS:
        for library in libraries:
            code, output = run_shell(f"nm -D {shlex.quote(library)} 2>/dev/null | grep -m1 ' {symbol}$'")
            if code == 0 and output:
                return True
    return False


def check_cann(report: Report, cann_command: str, backend: str = "ascendc") -> dict:
    code, home = run_shell(f"{cann_command} && printf '%s' \"$ASCEND_HOME_PATH\"")
    if code != 0 or not home:
        report.add("cann-env", "cann", "fail", f"sourcing failed or ASCEND_HOME_PATH unset (exit {code})",
                   "fix the CANN setup command")
        return {}
    report.add("cann-env", "cann", "ok", home)
    ascend_home = Path(home)
    version, timestamp = _cann_version(ascend_home)
    if version:
        report.add("cann-version", "cann", "ok", f"{version} (build {timestamp or 'unknown'})")
    else:
        report.add("cann-version", "cann", "warn", "version.info not found under ASCEND_HOME_PATH")
    _cann_tools(report, cann_command, backend)
    present = _opapi_libraries(ascend_home)
    if not present:
        report.add("opapi-libs", "cann", "warn" if backend == "cannbot_dsl" else "fail",
                   "no opapi libraries under ASCEND_HOME_PATH (incomplete CANN/ops install)",
                   "install the missing CANN ops packages")
        return {"home": home, "version": version, "opapi": present}
    if _warmup_symbol_found(list(present.values())):
        report.add("warmup-symbols", "cann", "ok",
                   "aclnnArgMax/aclnnMax present (framework-ops warmup available)")
    else:
        report.add("warmup-symbols", "cann", "warn",
                   f"no aclnnArgMax/aclnnMax symbols in {sorted(present)} "
                   "(incomplete install: framework-ops warmup unavailable, "
                   "compiled warmup becomes the only fallback)",
                   "install the ops packages providing libopapi.so")
    report.add("opapi-libs", "cann", "ok", ", ".join(sorted(present)))
    return {"home": home, "version": version, "opapi": present}


def check_dsl(report: Report, request: dict, python_exe: str, cann_command: str,
              environment_path: Path) -> None:
    from workflow_backend import validate_backend
    try:
        validate_backend(request)
    except ValueError as error:
        report.add("dsl-config", "dsl", "fail", str(error), "fix the DSL request")
        return
    code_dir = Path(request["code_dir"])
    if not code_dir.is_dir() or not any(code_dir.rglob("*.py")):
        report.add("dsl-source", "dsl", "fail", "no Python source in code_dir")
        return
    report.add("dsl-source", "dsl", "ok", str(code_dir))
    # Run in the confirmed environment, not in preflight's own interpreter.
    command = (
        f"{cann_command} && {shlex.quote(python_exe)} "
        f"{shlex.quote(str(PLUGIN_DIR / 'dsl_evidence.py'))} environment "
        f"--out {shlex.quote(str(environment_path))}"
    )
    code, output = run_shell(command, timeout=180)
    if code != 0:
        report.add("dsl-package", "dsl", "fail", output[-400:], "install/match cannbot-dsl and its toolchain")
        return
    snapshot = json.loads(environment_path.read_text())
    report.add("dsl-package", "dsl", "ok", f"{snapshot['dsl_version']} at {snapshot['package_root']}")
    probe = "import cannbotdsl, pytest; print('DSL and pytest importable')"
    code, output = run_shell(
        f"{cann_command} && {shlex.quote(python_exe)} -c {shlex.quote(probe)}", timeout=120
    )
    report.add("dsl-import", "dsl", "ok" if code == 0 else "fail", output[-400:])
    report.add("ttk", "ttk", "skip", "DSL uses frozen original pytest/checker/golden; TTK is route-specific")
    if request["dsl"]["execution_mode"] == "aot":
        check_build(report, code_dir)
    else:
        report.add("build-entry", "build", "skip", "JIT builds from Python; CMake/build.sh not required")


def check_ttk(report: Report, python_exe: str, cann_command: str, ttk_root: Path | None) -> Path | None:
    candidates: list[Path] = []
    if ttk_root is not None:
        candidates.append(ttk_root)
    else:
        env_root = os.environ.get("TTK_ROOT")
        if env_root:
            candidates.append(Path(env_root))
        candidates.extend(root for root in COMMON_TTK_ROOTS if root.is_dir())
    candidates = [root for root in candidates if root.is_dir() and (root / "ttk").is_dir()]
    if not candidates:
        code, output = run_shell(
            f"git clone --depth=1 {shlex.quote(TTK_REPO_URL)} {shlex.quote(str(DEFAULT_TTK_ROOT))}",
            timeout=300,
        )
        if code == 0 and (DEFAULT_TTK_ROOT / "ttk").is_dir():
            report.add("ttk", "ttk", "ok", f"cloned {TTK_REPO_URL} -> {DEFAULT_TTK_ROOT}")
            candidates.append(DEFAULT_TTK_ROOT)
        else:
            report.add("ttk", "ttk", "fail", "no ops-test-kit found (tried --ttk-root, $TTK_ROOT, "
                       + ", ".join(str(r) for r in COMMON_TTK_ROOTS) + ") and auto-clone failed: "
                       + output[-200:],
                       "pass --ttk-root or install ops-test-kit")
            return None

    heads: dict[str, str] = {}
    for root in candidates:
        code, head = run_shell(f"git -C {shlex.quote(str(root))} log -1 --format='%h %ad' --date=short")
        heads[str(root)] = head if code == 0 else "unknown"
    if len(candidates) > 1 and len(set(heads.values())) > 1:
        report.add("ttk-drift", "ttk", "warn",
                   "multiple ops-test-kit copies with different HEADs: "
                   + "; ".join(f"{root}={head}" for root, head in heads.items())
                   + " — pick one explicitly with --ttk-root (mixed copies caused "
                   "silent golden/input-generation differences in the field)",
                   "pass --ttk-root with the copy the baseline used")
    chosen = candidates[0]
    code, output = run_shell(
        f"{cann_command} && cd {shlex.quote(str(chosen))} && {shlex.quote(python_exe)} -c "
        "'import ttk; print(\"ttk importable\")'", timeout=120
    )
    if code != 0:
        report.add("ttk-import", "ttk", "fail", f"import failed: {output[-200:]}",
                   "install ttk requirements into the configured Python")
    else:
        report.add("ttk-import", "ttk", "ok", f"{chosen} ({heads.get(str(chosen), '?')})")
    link_ttk_skills(report, chosen)
    return chosen


def _link_skills_into(dest: Path, source: Path) -> None:
    for name in TTK_STANDARD_SKILLS:
        src = source / name
        if not src.is_dir():
            continue
        target = dest / name
        if target.is_symlink() or target.exists():
            target.unlink()
        target.symlink_to(src)


def link_ttk_skills(report: Report, ttk_root: Path) -> None:
    """Symlink the standard TTK skills into the client skill discovery dir.

    The TTK repo ships 4 standard skills under $TTK/.claude/skills/; link them into
    whichever client is deployed (opencode/claude/codex/codearts, project- or
    global-level) so they load as standalone skills. Downstream TTK work reads
    these 4 skills directly.
    """
    ttk_skills_dir = ttk_root / ".claude" / "skills"
    if not ttk_skills_dir.is_dir():
        report.add("ttk-skills", "ttk", "warn",
                   f"{ttk_skills_dir} missing (ops-test-kit too old to ship standard skills)",
                   "update ops-test-kit to a version shipping .claude/skills/")
        return
    dests = [d for d in dict.fromkeys(SKILL_DIR_CANDIDATES) if d.is_dir()]
    if not dests:
        report.add("ttk-skills", "ttk", "warn",
                   "no client skill dir found (looked for .opencode/.claude/.agents/"
                   ".codeartsdoer skills dirs, project- and global-level)",
                   "run init.sh first, then link $TTK/.claude/skills/* into the "
                   "client's skills dir manually")
        return
    missing = [name for name in TTK_STANDARD_SKILLS if not (ttk_skills_dir / name).is_dir()]
    if missing:
        report.add("ttk-skills", "ttk", "warn",
                   f"{ttk_skills_dir} missing skills, skipped: {', '.join(missing)}")
    linked: list[str] = []
    for dest in dests:
        try:
            _link_skills_into(dest, ttk_skills_dir)
            linked.append(str(dest))
        except OSError as exc:
            report.add("ttk-skills", "ttk", "warn", f"symlink into {dest} failed: {exc}",
                       f"link {ttk_skills_dir}/* into {dest} manually")
    if linked:
        report.add("ttk-skills", "ttk", "ok",
                   f"linked {', '.join(n for n in TTK_STANDARD_SKILLS if n not in missing)} "
                   f"-> {'; '.join(linked)} (restart the client to load)")


def _build_entries(code_dir: Path) -> list[str]:
    roots = [code_dir]
    if not (code_dir / ".git").exists():
        for parent in code_dir.parents:
            roots.append(parent)
            if (parent / ".git").exists():
                break
        else:
            roots = [code_dir]  # Do not infer an unrelated archive parent.
    entries = []
    for root in roots:
        for name in ("build.sh", "CMakeLists.txt", "Makefile", "setup.py", "pyproject.toml"):
            if (root / name).is_file():
                entries.append(str(root / name))
    return entries


def _report_build_entry(report: Report, code_dir: Path) -> None:
    entries = _build_entries(code_dir)
    report.add(
        "build-entry", "build", "warn" if entries else "fail",
        "build entry candidates: " + ", ".join(entries) if entries
        else "no build entry found in code dir or enclosing repository",
        "verify the single-operator target and working directory; keep code_dir unchanged",
    )


def _check_build_tools(report: Report) -> None:
    for tool, fatal in (("cmake", True), ("g++", True), ("ccache", False)):
        code, output = run_shell(f"command -v {tool}")
        if code != 0:
            status = "fail" if fatal else "warn"
            report.add(tool, "build", status, f"{tool} not found",
                       f"install {tool}" + ("" if fatal else " (optional, speeds up builds)"))
        else:
            report.add(tool, "build", "ok", output)


def check_build(report: Report, code_dir: Path) -> None:
    if not code_dir.is_dir():
        report.add("code-dir", "build", "fail", f"code dir not found: {code_dir}", "fix the request")
        return
    report.add("code-dir", "build", "ok", str(code_dir))
    if not (code_dir / ".git").exists():
        report.add("git-repo", "build", "warn", "code dir is not a git repository "
                   "(worktree/archive extraction may still work)")
    else:
        report.add("git-repo", "build", "ok", "git repository")
    if (code_dir / "build.sh").is_file():
        report.add("build.sh", "build", "ok", "present")
    else:
        # An operator directory need not be the repository's build entrypoint.
        _report_build_entry(report, code_dir)
    _check_build_tools(report)


def check_device(report: Report, python_exe: str, cann_command: str, device: int) -> None:
    devices = glob.glob("/dev/davinci*")
    if not devices:
        report.add("device-nodes", "device", "fail", "no /dev/davinci* nodes", "check the driver")
        return
    report.add("device-nodes", "device", "ok", f"{len(devices)} nodes")
    probe = (
        f"import torch, torch_npu; "
        f"torch.npu.set_device({device}); "
        f"x = torch.randn(64, device='npu'); "
        f"free, total = torch.npu.mem_get_info(); "
        f"print('init ok; HBM free %.1f/%.1f GB' % (free/2**30, total/2**30))"
    )
    code, output = run_shell(
        f"{cann_command} && {shlex.quote(python_exe)} -c {shlex.quote(probe)}", timeout=180
    )
    if code == 0:
        report.add("device-init", "device", "ok", output)
        return
    if "507033" in output or "Operation not permitted" in output:
        report.add("device-init", "device", "warn",
                   "device busy (aclError 507033) — shared device; retry when free",
                   "wait for the current occupant or use another device")
    else:
        report.add("device-init", "device", "fail", f"init failed: {output[-240:]}",
                   "fix driver/runtime pairing or the device id")


def check_disk(report: Report, out_path: Path) -> None:
    code, output = run_shell(f"df -BG --output=avail {shlex.quote(str(out_path))} | tail -1")
    if code != 0:
        report.add("disk", "disk", "warn", "df failed")
        return
    try:
        free_gb = int(output.strip().rstrip("G"))
    except ValueError:
        report.add("disk", "disk", "warn", f"unparsed df output: {output.strip()}")
        return
    if free_gb < MIN_FREE_GB:
        report.add("disk", "disk", "warn",
                   f"only {free_gb} GB free at {out_path} (builds + PROF data need tens of GB)",
                   "free space or move the run directory")
    else:
        report.add("disk", "disk", "ok", f"{free_gb} GB free")


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ops-perf-optimize startup dependency preflight")
    parser.add_argument("--request", required=True, help="optimization-request.json path")
    parser.add_argument("--ttk-root", default=None, help="ops-test-kit root (default: $TTK_ROOT or common paths)")
    parser.add_argument("--device", type=int, default=0)
    parser.add_argument("--out", default=None, help="JSON report output path")
    parser.add_argument("--skip-device", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    return parser.parse_args()


def _run_preflight_checks(
    args: argparse.Namespace, report: Report, request: dict, request_path: Path
) -> tuple[str, str, Path, str, Path]:
    environments = request.get("environments", {})
    python_exe = environments.get("python", {}).get("executable", sys.executable)
    cann_command = environments.get("cann", {}).get("setup_command", "true")
    code_dir = Path(request.get("code_dir", ".")).resolve()
    if cann_command == "inherit":
        cann_command = "true"
    check_python_env(report, python_exe, cann_command)
    backend = request.get("backend", "ascendc")
    if backend not in ("ascendc", "cannbot_dsl"):
        report.add("backend", "request", "fail", f"unknown backend: {backend}")
    check_cann(report, cann_command, backend)
    environment_path = request_path.parent / "dsl-environment.json"
    if backend == "cannbot_dsl":
        check_dsl(report, request, python_exe, cann_command, environment_path)
    else:
        check_ttk(report, python_exe, cann_command, Path(args.ttk_root) if args.ttk_root else None)
        if not args.skip_build:
            check_build(report, code_dir)
    if not args.skip_device:
        check_device(report, python_exe, cann_command, args.device)
    check_disk(report, request_path.parent)
    return python_exe, cann_command, code_dir, backend, environment_path


def _summary_report(
    report: Report,
    started_at: str,
    request_path: Path,
    python_exe: str,
    cann_command: str,
    code_dir: Path,
    backend: str,
    environment_path: Path,
) -> dict:
    summary = report.summary()
    summary.update({
        "started_at": started_at,
        "completed_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "request": str(request_path),
        "python": python_exe,
        "cann_command": cann_command,
        "code_dir": str(code_dir),
        "backend": backend,
        "dsl_environment": {
            "path": str(environment_path),
            "sha256": hashlib.sha256(environment_path.read_bytes()).hexdigest(),
        } if backend == "cannbot_dsl" and environment_path.is_file() else None,
        "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest()
        if request_path.is_file() else "",
    })
    return summary


def main() -> int:
    args = _parse_arguments()

    started_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    request_path = Path(args.request).resolve()
    report = Report()
    emit(f"== ops-perf-optimize dependency preflight ==\nrequest: {request_path}")

    check_plugin_scripts(report)
    request = load_request(report, request_path)
    python_exe, cann_command, code_dir, backend, environment_path = _run_preflight_checks(
        args, report, request, request_path
    )
    summary = _summary_report(
        report, started_at, request_path, python_exe, cann_command, code_dir, backend, environment_path
    )

    out_path = Path(args.out) if args.out else request_path.parent / "preflight-report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    emit(f"\n== preflight: {summary['status'].upper()} "
          f"({summary['fail_count']} fail / {summary['warn_count']} warn) ==")
    emit(f"report: {out_path}")
    if summary["status"] == "fail":
        emit("fix the FAIL items (or re-confirm the request environments) before freeze", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
