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


from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any
from typing import NamedTuple
from typing import TextIO
from typing import TypedDict
from typing import Union
from typing import cast


_MLIR_PRINT_OP_GENERIC_ENV = "HELIX_CAPTURE_IR_MLIR_PRINT_OP_GENERIC"


class ResultPayload(TypedDict):
    return_code: int
    stdout: str
    stderr: str
    stalled: bool
    session_id: str | None


class CaptureDetails(NamedTuple):
    dumped_ir_dir: str
    compile_command: list[str]


class CaptureDetailsList(list[CaptureDetails]):
    """Ordered capture entries with compatibility access for old callers."""

    @property
    def dumped_ir_dir(self) -> str:
        if len(self) != 1:
            raise AttributeError("dumped_ir_dir is only available for one capture entry")
        return self[0].dumped_ir_dir

    @property
    def compile_command(self) -> list[str]:
        if len(self) != 1:
            raise AttributeError("compile_command is only available for one capture entry")
        return self[0].compile_command


class _RemoteCaptureContext(NamedTuple):
    """Shared remote-capture plumbing: session spec, remote dirs, and output settings."""

    spec: Any
    remote_root: str
    remote_archive_dir: str
    remote_source_dir: str
    verbose: bool
    stderr: TextIO | None


def extract_capture_details(stdout: str) -> CaptureDetailsList:
    entries: list[dict[str, object]] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("Dumping intermediate results to "):
            entries.append(
                {
                    "dumped_ir_dir": stripped.removeprefix("Dumping intermediate results to ").strip(),
                    "compile_command": None,
                }
            )
        elif stripped.startswith("[DEBUG] cmd_list: "):
            raw_command = stripped.removeprefix("[DEBUG] cmd_list: ").strip()
            _attach_compile_command(entries, raw_command)

    complete = CaptureDetailsList(
        CaptureDetails(
            dumped_ir_dir=str(entry["dumped_ir_dir"]),
            compile_command=cast(list[str], entry["compile_command"]),
        )
        for entry in entries
        if entry["compile_command"] is not None
    )
    if not complete:
        raise RuntimeError(
            "Missing 'Dumping intermediate results to ...' / '[DEBUG] cmd_list: ...' pairs in command stdout."
        )
    dropped = len(entries) - len(complete)
    if dropped:
        print(f"Warning: dropped {dropped} kernel dump(s) with no matching compile command.", file=sys.stderr)
    return complete


def _attach_compile_command(entries: list[dict[str, object]], raw_command: str) -> None:
    for entry in reversed(entries):
        if entry["compile_command"] is None:
            entry["compile_command"] = _normalize_compile_command_tokens(shlex.split(raw_command))
            break


def rewrite_compile_command(
    command: list[str],
    *,
    archived_input: Path,
) -> list[str]:
    command = _normalize_compile_command_tokens(command)
    if len(command) < 2:
        raise RuntimeError(f"Unexpected compile command shape: {command}")
    compiler_input = _recorded_compiler_input(command)

    rewritten: list[str] = [command[0]]
    input_replaced = False
    index = 1
    while index < len(command):
        token = command[index]
        if token.startswith("--bishengir-print-ir-after="):
            index += 1
            continue
        if token == "--bishengir-print-ir-after":
            index += 2
            continue
        if token.startswith("--mlir-print-ir-tree-dir="):
            index += 1
            continue
        if token == "--mlir-print-ir-tree-dir":
            index += 2
            continue
        if token == "--mlir-print-ir-after-failure":
            index += 1
            continue
        if token == "--mlir-print-ir-after-all":
            index += 1
            continue
        if not input_replaced and token == compiler_input:
            rewritten.append(archived_input.as_posix())
            input_replaced = True
            index += 1
            continue
        rewritten.append(token)
        index += 1

    if not input_replaced:
        raise RuntimeError(f"Recorded compiler input was not found while rewriting command: {compiler_input}")

    rewritten.append("--mlir-print-ir-after-all")
    if _should_print_generic_ops() and "--mlir-print-op-generic" not in rewritten:
        rewritten.append("--mlir-print-op-generic")
    return rewritten


def _should_print_generic_ops() -> bool:
    return os.environ.get(_MLIR_PRINT_OP_GENERIC_ENV) == "1"


def write_manifest(
    archive_dir: Path,
    *,
    bench_file: Path,
    operator_file: Path,
    rendered_command: list[str],
    remote: bool,
    dumped_ir_dir: str,
    original_compile_command: list[str],
    replay_compile_command: list[str],
    archived_input: Path,
    resolved_case: dict[str, object] | None = None,
    case_id: str,
    kernel_records: list[dict[str, object]] | None = None,
) -> Path:
    manifest_path = archive_dir / "capture-manifest.json"
    kernels = kernel_records or [
        {
            "kernel_key": "default",
            "triton_dump_dir": _archive_relative_path(archive_dir, archived_input.parent),
            "stage_dir": _archive_relative_path(archive_dir, archive_dir / "bishengir_stages"),
            "pass_order_file": _archive_relative_path(archive_dir, archive_dir / "pass-order.json"),
            "archived_input": _archive_relative_path(archive_dir, archived_input),
            "original_compile_command": original_compile_command,
            "replay_compile_command": replay_compile_command,
            "dumped_ir_dir": dumped_ir_dir,
        }
    ]
    first_kernel = kernels[0]
    payload = {
        "bench_file": bench_file.resolve().as_posix(),
        "bench_sha256": _sha256_file(bench_file),
        "operator_file": operator_file.resolve().as_posix(),
        "operator_sha256": _sha256_file(operator_file),
        "case_id": case_id,
        "artifact_dir": archive_dir.resolve().as_posix(),
        "rendered_command": rendered_command,
        "remote": remote,
        "dumped_ir_dir": dumped_ir_dir,
        "original_compile_command": original_compile_command,
        "replay_compile_command": replay_compile_command,
        "archived_input": archived_input.as_posix(),
        "pass_order_file": _manifest_path_value(archive_dir, first_kernel.get("pass_order_file")),
        "kernel_count": len(kernels),
        "kernels": kernels,
        "resolved_case": resolved_case
        or {"status": "unavailable", "reason": "Capture predates resolved-case metadata."},
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _archive_relative_path(archive_dir: Path, path: Path | PurePosixPath) -> str:
    if isinstance(path, Path):
        return path.resolve().relative_to(archive_dir.resolve()).as_posix()
    return path.relative_to(PurePosixPath(archive_dir.as_posix())).as_posix()


def _manifest_path_value(archive_dir: Path, value: object) -> str:
    if not isinstance(value, str):
        return (archive_dir / "pass-order.json").as_posix()
    path = Path(value)
    if path.is_absolute():
        return path.as_posix()
    return (archive_dir / path).as_posix()


def resolve_case_metadata(bench_file: Path, case_id: str | None) -> dict[str, object]:
    """Archive shape and launch facts exposed by the selected benchmark case."""
    try:
        with _TemporaryImportPath(bench_file.parent):
            module = _load_bench_module(bench_file)
            build_cases = getattr(module, "build_bench_cases", None)
            raw_cases = build_cases() if callable(build_cases) else None
    except Exception as exc:
        return {
            "case_id": case_id,
            "status": "unavailable",
            "reason": f"Could not resolve case metadata: {type(exc).__name__}: {exc}",
        }
    selected = _select_case(raw_cases, case_id)
    if selected is None:
        return {
            "case_id": case_id,
            "status": "unavailable",
            "reason": "Selected case is not available from build_bench_cases.",
        }
    return {
        "case_id": selected.get("id"), "status": "available",
        "case_data": _json_safe(dict(selected)),
        "resolved_shape": _metadata_subset(
            selected, ("shape", "shapes", "m", "n", "k", "batch", "seq", "size", "dtype", "dtypes")
        ),
        "launch_metadata": _metadata_subset(selected, ("grid", "num_warps", "num_stages", "block", "blocks", "launch")),
    }


class _TemporaryImportPath:
    def __init__(self, path: Path) -> None:
        self.path = str(path.resolve())
        self.added = False

    def __enter__(self) -> None:
        if self.path not in sys.path:
            sys.path.insert(0, self.path)
            self.added = True

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if self.added and self.path in sys.path:
            sys.path.remove(self.path)


def _load_bench_module(bench_file: Path) -> object:
    spec = importlib.util.spec_from_file_location(f"capture_ir_bench_{bench_file.stem}", bench_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load benchmark module: {bench_file}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclass/typing decorators resolve the module via sys.modules.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _select_case(raw_cases: object, case_id: str | None) -> Mapping[object, object] | None:
    if not isinstance(raw_cases, (list, tuple)):
        return None
    for item in cast(Union[list[object], tuple[object, ...]], raw_cases):
        if not isinstance(item, Mapping):
            continue
        candidate = cast(Mapping[object, object], item)
        if case_id is None or candidate.get("id") == case_id:
            return candidate
    return None


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {str(key): _json_safe(item) for key, item in mapping.items()}
    if isinstance(value, (list, tuple)):
        items = cast(Union[list[object], tuple[object, ...]], value)
        return [_json_safe(item) for item in items]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _metadata_subset(case: Mapping[object, object], keys: tuple[str, ...]) -> dict[str, object]:
    return {str(key): _json_safe(value) for key, value in case.items() if str(key).lower() in keys}


def _capture_ir_hint(archive_dir: Path) -> str:
    return (
        "Hint: use the bundled `inspect_ir.py` helper with "
        f"`--ir-dir {archive_dir}` to inspect this archive first; "
        "choose a bundle under kernels/<kernel-key>/, then inspect the artifacts "
        "named by capture-manifest.json directly."
    )


def capture_local_archive(
    *,
    bench_file: Path,
    operator_file: Path,
    archive_dir: Path,
    case_id: str | None = None,
) -> Path:
    normalized_case_id = _require_case_id(case_id)
    archive_dir = _allocate_archive_dir(archive_dir, normalized_case_id)
    _prepare_empty_archive_dir(archive_dir)
    try:
        command = build_execution_command(
            bench_file=bench_file,
            operator_file=operator_file,
            case_id=normalized_case_id,
        )
        resolved_case = resolve_case_metadata(bench_file, normalized_case_id)
        result = _run_local_command(command, cwd=bench_file.parent)
        if int(str(result["return_code"])) != 0:
            raise RuntimeError(str(result["stderr"]) or str(result["stdout"]) or "Command failed.")

        details_list = extract_capture_details(str(result["stdout"]))
        bundle_specs = _bundle_paths(archive_dir, details_list)
        kernel_records: list[dict[str, object]] = []
        for details, (_key, _triton_dump_dir, _stage_dir, _pass_order_file) in zip(details_list, bundle_specs):
            bundle_root = _stage_dir.parent
            kernel_records.append(_archive_kernel_locally(archive_dir, details, bundle_root=bundle_root))
        first = kernel_records[0]
        return write_manifest(
            archive_dir,
            bench_file=bench_file,
            operator_file=operator_file,
            rendered_command=command,
            remote=False,
            dumped_ir_dir=str(first["dumped_ir_dir"]),
            original_compile_command=cast(list[str], first["original_compile_command"]),
            replay_compile_command=cast(list[str], first["replay_compile_command"]),
            archived_input=archive_dir / str(first["archived_input"]),
            resolved_case=resolved_case,
            case_id=normalized_case_id,
            kernel_records=kernel_records,
        )
    except Exception:
        shutil.rmtree(archive_dir, ignore_errors=True)
        raise


def capture_remote_archive(
    *,
    bench_file: Path,
    operator_file: Path,
    archive_dir: Path,
    remote: str,
    remote_workdir: str | None,
    keep_remote_workdir: bool,
    case_id: str | None = None,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> tuple[Path, str]:
    normalized_case_id = _require_case_id(case_id)
    archive_dir = _allocate_archive_dir(archive_dir, normalized_case_id)
    _prepare_archive_destination(archive_dir)
    spec, remote_root = create_remote_workspace(remote, remote_workdir, verbose=verbose, stderr=stderr)
    ctx = _RemoteCaptureContext(
        spec=spec, remote_root=remote_root,
        remote_archive_dir=f"{remote_root}/archive", remote_source_dir=f"{remote_root}/workspace",
        verbose=verbose, stderr=stderr,
    )
    remote_source_dir = ctx.remote_source_dir
    command = build_execution_command(
        bench_file=Path(bench_file.name),
        operator_file=Path(operator_file.name),
        python_executable="python3",
        case_id=normalized_case_id,
    )
    resolved_case = resolve_case_metadata(bench_file, normalized_case_id)
    try:
        _prepare_remote_workspace(ctx, bench_file, operator_file)
        kernel_records = _capture_remote_records(ctx, command, archive_dir)
        manifest_path = _write_remote_manifest(
            archive_dir,
            bench_file=bench_file,
            operator_file=operator_file,
            command=command,
            kernel_records=kernel_records,
            resolved_case=resolved_case,
            case_id=normalized_case_id,
        )
        return manifest_path, remote_root
    except Exception:
        shutil.rmtree(archive_dir, ignore_errors=True)
        raise
    finally:
        if not keep_remote_workdir:
            cleanup_remote_workspace(spec, remote_root, verbose=verbose, stderr=stderr)


def _capture_remote_records(
    ctx: _RemoteCaptureContext,
    command: list[str],
    archive_dir: Path,
) -> list[dict[str, object]]:
    """Run the debug capture remotely, archive every kernel, and fetch the archive."""
    run_result = _run_remote_debug_command(
        ctx.spec,
        ctx.remote_source_dir,
        command,
        verbose=ctx.verbose,
        stderr=ctx.stderr,
    )
    if int(str(run_result["return_code"])) != 0:
        raise RuntimeError(str(run_result["stderr"]) or str(run_result["stdout"]) or "Remote command failed.")

    details_list = extract_capture_details(str(run_result["stdout"]))
    remote_records = _archive_remote_kernels(ctx, details_list)
    copy_directory_from_remote(
        ctx.spec,
        f"{ctx.remote_root}/archive",
        archive_dir,
        verbose=ctx.verbose,
        stderr=ctx.stderr,
    )
    return _localize_remote_records(archive_dir, remote_records)


def _prepare_remote_workspace(
    ctx: _RemoteCaptureContext,
    bench_file: Path,
    operator_file: Path,
) -> None:
    run_remote_command_buffered(
        ctx.spec,
        ctx.remote_root,
        f"mkdir -p {shlex.quote(ctx.remote_source_dir)} {shlex.quote(ctx.remote_archive_dir)}",
        verbose=ctx.verbose,
        stderr=ctx.stderr,
    )
    _stage_required_files(
        ctx.spec,
        bench_file=bench_file,
        operator_file=operator_file,
        remote_source_dir=ctx.remote_source_dir,
        verbose=ctx.verbose,
        stderr=ctx.stderr,
    )


def _archive_remote_kernels(
    ctx: _RemoteCaptureContext,
    details_list: CaptureDetailsList,
) -> list[dict[str, object]]:
    bundle_specs = _bundle_paths(Path(ctx.remote_archive_dir), details_list)
    remote_records: list[dict[str, object]] = []
    for details, (key, remote_dump_dir, remote_stage_dir, remote_pass_order_file) in zip(
        details_list, bundle_specs
    ):
        remote_records.append(
            _archive_remote_kernel(
                ctx,
                details,
                key=key,
                remote_dump_dir=remote_dump_dir,
                remote_stage_dir=remote_stage_dir,
                remote_pass_order_file=remote_pass_order_file,
            )
        )
    return remote_records


def _write_remote_manifest(
    archive_dir: Path,
    *,
    bench_file: Path,
    operator_file: Path,
    command: list[str],
    kernel_records: list[dict[str, object]],
    resolved_case: dict[str, object] | None,
    case_id: str,
) -> Path:
    first = kernel_records[0]
    return write_manifest(
        archive_dir,
        bench_file=bench_file,
        operator_file=operator_file,
        rendered_command=command,
        remote=True,
        dumped_ir_dir=str(first["dumped_ir_dir"]),
        original_compile_command=cast(list[str], first["original_compile_command"]),
        replay_compile_command=cast(list[str], first["replay_compile_command"]),
        archived_input=archive_dir / str(first["archived_input"]),
        resolved_case=resolved_case,
        case_id=case_id,
        kernel_records=kernel_records,
    )


def _archive_remote_kernel(
    ctx: _RemoteCaptureContext,
    details: CaptureDetails,
    *,
    key: str,
    remote_dump_dir: Path,
    remote_stage_dir: Path,
    remote_pass_order_file: Path,
) -> dict[str, object]:
    remote_dump_dir_text = str(PurePosixPath(remote_dump_dir.as_posix()))
    remote_stage_dir_text = str(PurePosixPath(remote_stage_dir.as_posix()))
    remote_pass_order_text = str(PurePosixPath(remote_pass_order_file.as_posix()))
    compiler_input = _recorded_compiler_input(details.compile_command)
    remote_input = PurePosixPath(remote_dump_dir_text) / Path(compiler_input).name
    replay_command = rewrite_compile_command(
        details.compile_command,
        archived_input=Path(str(remote_input)),
    )
    _copy_remote_dump(ctx, key, remote_dump_dir.parent, remote_dump_dir_text, details.dumped_ir_dir)
    _replay_remote_pass_order(
        ctx, replay_command, key, remote_stage_dir_text, remote_pass_order_text
    )
    return {
        "kernel_key": key,
        "triton_dump_dir": _archive_relative_path(Path(ctx.remote_archive_dir), remote_dump_dir),
        "stage_dir": _archive_relative_path(Path(ctx.remote_archive_dir), remote_stage_dir),
        "pass_order_file": _archive_relative_path(Path(ctx.remote_archive_dir), remote_pass_order_file),
        "archived_input": _archive_relative_path(Path(ctx.remote_archive_dir), remote_input),
        "dumped_ir_dir": details.dumped_ir_dir,
        "original_compile_command": details.compile_command,
        "replay_compile_command": replay_command,
    }


def _copy_remote_dump(
    ctx: _RemoteCaptureContext,
    key: str,
    remote_bundle_dir: Path,
    remote_dump_dir_text: str,
    dumped_ir_dir: str,
) -> None:
    remote_copy_command = (
        f"mkdir -p {shlex.quote(str(remote_bundle_dir))} && "
        f"rm -rf {shlex.quote(remote_dump_dir_text)} && "
        f"mkdir -p {shlex.quote(remote_dump_dir_text)} && "
        f"cp -R {shlex.quote(dumped_ir_dir)}/. {shlex.quote(remote_dump_dir_text)}/"
    )
    copy_result = run_remote_command_buffered(
        ctx.spec,
        ctx.remote_root,
        remote_copy_command,
        verbose=ctx.verbose,
        stderr=ctx.stderr,
    )
    if int(copy_result["return_code"]) != 0:
        raise RuntimeError(
            str(copy_result["stderr"])
            or str(copy_result["stdout"])
            or f"Failed to archive remote Triton dump for kernel {key}."
        )


def _replay_remote_pass_order(
    ctx: _RemoteCaptureContext,
    replay_command: list[str],
    key: str,
    remote_stage_dir_text: str,
    remote_pass_order_text: str,
) -> None:
    pass_order_command = _build_remote_pass_order_command(
        replay_command,
        ctx.remote_archive_dir,
        ctx.remote_source_dir,
        remote_stage_dir=remote_stage_dir_text,
        remote_output_file=remote_pass_order_text,
    )
    pass_order_result = run_remote_command_buffered(
        ctx.spec,
        ctx.remote_root,
        pass_order_command,
        verbose=ctx.verbose,
        stderr=ctx.stderr,
    )
    if int(pass_order_result["return_code"]) != 0:
        raise RuntimeError(
            _format_failed_command_message(
                f"Failed to replay remote compile command for kernel {key}",
                pass_order_command,
                stdout=str(pass_order_result["stdout"]),
                stderr=str(pass_order_result["stderr"]),
            )
        )


def _localize_remote_records(
    archive_dir: Path, remote_records: list[dict[str, object]]
) -> list[dict[str, object]]:
    kernel_records: list[dict[str, object]] = []
    for record in remote_records:
        local_dump_dir = archive_dir / str(record["triton_dump_dir"])
        local_stage_dir = archive_dir / str(record["stage_dir"])
        local_pass_order_file = archive_dir / str(record["pass_order_file"])
        local_archived_input = _resolve_archived_input(
            local_dump_dir,
            cast(list[str], record["original_compile_command"]),
        )
        kernel_records.append(
            {
                **record,
                "triton_dump_dir": _archive_relative_path(archive_dir, local_dump_dir),
                "stage_dir": _archive_relative_path(archive_dir, local_stage_dir),
                "pass_order_file": _archive_relative_path(archive_dir, local_pass_order_file),
                "archived_input": _archive_relative_path(archive_dir, local_archived_input),
            }
        )
    return kernel_records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture Triton Ascend IR into an IR directory.",
        allow_abbrev=False,
    )
    parser.add_argument("--ir-dir", required=True)
    parser.add_argument("--bench-file", required=True)
    parser.add_argument("--operator-file", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--remote")
    parser.add_argument("--remote-workdir")
    parser.add_argument("--keep-remote-workdir", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    archive_parent = Path(args.ir_dir).expanduser().resolve()
    bench_file = _resolve_existing_path(args.bench_file, "Bench file")
    operator_file = _resolve_existing_path(args.operator_file, "Operator file")
    try:
        if args.remote:
            manifest_path, remote_workspace = capture_remote_archive(
                bench_file=bench_file,
                operator_file=operator_file,
                archive_dir=archive_parent,
                remote=args.remote,
                remote_workdir=args.remote_workdir,
                keep_remote_workdir=args.keep_remote_workdir,
                case_id=args.case_id,
                verbose=args.verbose,
                stderr=sys.stderr,
            )
            print(f"IR archive: {manifest_path.parent}")
            print(f"Capture manifest: {manifest_path}")
            print(_capture_ir_hint(manifest_path.parent))
            if args.keep_remote_workdir:
                print(f"Remote workspace: {remote_workspace}")
            return 0

        manifest_path = capture_local_archive(
            bench_file=bench_file,
            operator_file=operator_file,
            archive_dir=archive_parent,
            case_id=args.case_id,
        )
        print(f"IR archive: {manifest_path.parent}")
        print(f"Capture manifest: {manifest_path}")
        print(_capture_ir_hint(manifest_path.parent))
        return 0
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _prepare_empty_archive_dir(archive_dir: Path) -> None:
    if archive_dir.exists():
        shutil.rmtree(archive_dir)
    archive_dir.mkdir(parents=True)


def _prepare_archive_destination(archive_dir: Path) -> None:
    if archive_dir.exists():
        shutil.rmtree(archive_dir)
    archive_dir.parent.mkdir(parents=True, exist_ok=True)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sanitize_case_id(case_id: str) -> str:
    sanitized = "".join(
        character if character.isalnum() or character in {".", "_", "-"} else "_"
        for character in case_id.strip()
    ).strip(".")
    if not sanitized:
        raise ValueError("--case-id must contain a usable path component")
    return sanitized


def _require_case_id(case_id: str | None) -> str:
    if case_id is None or not case_id.strip():
        raise ValueError("capture_ir.py requires --case-id <id>")
    return case_id.strip()


def _allocate_archive_dir(parent_dir: Path, case_id: str) -> Path:
    parent = parent_dir.expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / f"{_utc_timestamp()}-{_sanitize_case_id(case_id)}"
    if target.exists():
        shutil.rmtree(target)
    return target


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _resolve_existing_path(raw_path: str, label: str) -> Path:
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"{label} path does not exist: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"{label} path is not a file: {path}")
    return path


def _run_local_command(command: list[str], *, cwd: Path) -> ResultPayload:
    env = dict(os.environ)
    env["TRITON_DEBUG"] = "1"
    env["TRITON_ALWAYS_COMPILE"] = "1"
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stalled": False,
        "session_id": None,
    }


def _capture_stages_and_pass_order(command: list[str], *, stage_dir: Path, output_path: Path) -> Path:
    module = _load_capture_pass_order_module()
    return module.capture_stages_and_pass_order(
        command,
        stage_dir=stage_dir,
        output_path=output_path,
        env=_replay_environment(command),
    )


def _normalize_compile_command_tokens(tokens: list[str]) -> list[str]:
    normalized: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        prefix = _space_separated_option_prefix(token)
        if prefix is not None:
            value = token.split("=", 1)[1]
            merged: list[str] = [value] if value else []
            index += 1
            while index < len(tokens) and _should_merge_space_separated_option_value(prefix, tokens[index]):
                merged.append(tokens[index])
                index += 1
            normalized.append(f"{prefix}{' '.join(merged)}")
            continue
        normalized.append(token)
        index += 1
    return normalized


def _space_separated_option_prefix(token: str) -> str | None:
    for prefix in (
        "--append-bisheng-options=",
        "--discrete-mask-access-conversion=",
        "--triton-to-unstructure=",
        "--triton-to-linalg=",
    ):
        if token.startswith(prefix):
            return prefix
    return None


def _should_merge_space_separated_option_value(prefix: str, token: str) -> bool:
    if token.startswith("-"):
        return False
    if prefix == "--append-bisheng-options=":
        return True
    return _looks_like_inline_option_assignment(token)


def _looks_like_inline_option_assignment(token: str) -> bool:
    name, separator, _value = token.partition("=")
    return bool(separator) and bool(name) and all(character.isalnum() or character in "._-" for character in name)


def _recorded_compiler_input(command: list[str]) -> str:
    for token in command[1:]:
        if token.startswith("-"):
            continue
        if token.endswith(".ttadapter.mlir"):
            return token
        if token.endswith(".ttir.mlir"):
            return token
    raise RuntimeError(
        "Recorded compile command has no supported MLIR input; expected a .ttadapter.mlir or .ttir.mlir argument: "
        f"{command}"
    )


def build_execution_command(
    *,
    bench_file: Path,
    operator_file: Path,
    python_executable: str | None = None,
    case_id: str | None = None,
) -> list[str]:
    operator_arg = operator_file.name
    if bench_file.parent != operator_file.parent:
        operator_arg = os.path.relpath(operator_file, bench_file.parent)
    interpreter = sys.executable if python_executable is None else python_executable
    helper_script = _run_bench_execution_script_path() if python_executable is None else Path("run_bench_execution.py")
    return [
        interpreter,
        str(helper_script),
        "exec-one",
        "--bench-file",
        bench_file.name,
        "--operator-file",
        operator_arg,
        *([] if case_id is None else ["--case-id", case_id]),
    ]


def _resolve_archived_input(triton_dump_dir: Path, command: list[str]) -> Path:
    compiler_input_name = Path(_recorded_compiler_input(command)).name
    matches = sorted(triton_dump_dir.rglob(compiler_input_name))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Expected exactly one compiler input named {compiler_input_name} under "
            f"{triton_dump_dir}, found {len(matches)}."
        )
    return matches[0]


def _kernel_key(dumped_ir_dir: str) -> str:
    name = Path(dumped_ir_dir.rstrip("/\\")).name
    sanitized = "".join(
        character if character.isalnum() or character in {".", "_", "-"} else "_"
        for character in name
    ).strip(".")
    return sanitized or "kernel"


def _bundle_paths(archive_dir: Path, details_list: CaptureDetailsList) -> list[tuple[str, Path, Path, Path]]:
    records: list[tuple[str, Path, Path, Path]] = []
    seen: set[str] = set()
    for details in details_list:
        key = _kernel_key(details.dumped_ir_dir)
        if key in seen:
            raise RuntimeError(f"Duplicate kernel key '{key}' from dump directory: {details.dumped_ir_dir}")
        seen.add(key)
        root = archive_dir / "kernels" / key
        records.append((key, root / "triton_dump", root / "bishengir_stages", root / "pass-order.json"))
    return records


def _archive_kernel_locally(
    archive_dir: Path,
    details: CaptureDetails,
    *,
    bundle_root: Path,
) -> dict[str, object]:
    bundle_root.mkdir(parents=True, exist_ok=True)
    triton_dump_dir = bundle_root / "triton_dump"
    stage_dir = bundle_root / "bishengir_stages"
    pass_order_file = bundle_root / "pass-order.json"
    shutil.copytree(Path(details.dumped_ir_dir), triton_dump_dir)
    archived_input = _resolve_archived_input(triton_dump_dir, details.compile_command)
    replay_command = rewrite_compile_command(
        details.compile_command,
        archived_input=archived_input,
    )
    _capture_stages_and_pass_order(replay_command, stage_dir=stage_dir, output_path=pass_order_file)
    return {
        "kernel_key": _kernel_key(details.dumped_ir_dir),
        "triton_dump_dir": _archive_relative_path(archive_dir, triton_dump_dir),
        "stage_dir": _archive_relative_path(archive_dir, stage_dir),
        "pass_order_file": _archive_relative_path(archive_dir, pass_order_file),
        "archived_input": _archive_relative_path(archive_dir, archived_input),
        "dumped_ir_dir": details.dumped_ir_dir,
        "original_compile_command": details.compile_command,
        "replay_compile_command": replay_command,
    }


def _stage_required_files(
    spec: Any,
    *,
    bench_file: Path,
    operator_file: Path,
    remote_source_dir: str,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> None:
    if bench_file.name == operator_file.name and bench_file.resolve() != operator_file.resolve():
        raise RuntimeError(
            f"Remote staging would collide on basename '{bench_file.name}': {bench_file} vs {operator_file}"
        )
    copy_file_to_remote(
        spec,
        bench_file.resolve(),
        f"{remote_source_dir}/{bench_file.name}",
        verbose=verbose,
        stderr=stderr,
    )
    copy_file_to_remote(
        spec,
        operator_file.resolve(),
        f"{remote_source_dir}/{operator_file.name}",
        verbose=verbose,
        stderr=stderr,
    )
    for helper_path in _run_bench_execution_bundle_paths():
        copy_file_to_remote(
            spec,
            helper_path,
            f"{remote_source_dir}/{helper_path.name}",
            verbose=verbose,
            stderr=stderr,
        )
    for record in _RUNTIME_HELPERS["collect_staging_input_files"](
        (bench_file.parent, operator_file.parent),
        excluded_paths=(bench_file, operator_file),
    ):
        copy_file_to_remote(
            spec,
            Path(str(record["source"])),
            f"{remote_source_dir}/{record['target']}",
            verbose=verbose,
            stderr=stderr,
        )
    pass_order_script = _capture_pass_order_script_path()
    copy_file_to_remote(
        spec,
        pass_order_script,
        f"{remote_source_dir}/{pass_order_script.name}",
        verbose=verbose,
        stderr=stderr,
    )


def _find_common_skill_script(skill_name: str, script_name: str) -> Path:
    """Find a script inside a common skill directory.

    The skills directory layout differs between the repository source tree and
    the flat staging workspace used at runtime:

      Repo:    <root>/common/<skill_name>/scripts/<script_name>
      Staging: <root>/<skill_name>/scripts/<script_name>   (no "common" group)

    This helper checks both layouts so the script works in either environment.
    """
    script_file = Path(__file__).resolve()
    flat = script_file.parents[2] / skill_name / "scripts" / script_name
    if flat.is_file():
        return flat
    repo = script_file.parents[3] / "common" / skill_name / "scripts" / script_name
    if repo.is_file():
        return repo
    raise FileNotFoundError(
        f"Cannot find {skill_name}/scripts/{script_name} — "
        f"tried flat={flat} and repo={repo}"
    )


def _run_bench_execution_script_path() -> Path:
    return _find_common_skill_script("triton-npu-run-eval", "run_bench_execution.py")


def _capture_pass_order_script_path() -> Path:
    return Path(__file__).resolve().with_name("capture_pass_order.py")


def _run_bench_execution_bundle_paths() -> list[Path]:
    bundle_module = _load_run_eval_script_module("remote_python_bundle.py")
    return list(bundle_module.resolve_remote_python_bundle([_run_bench_execution_script_path()]))


def _load_run_eval_script_module(script_name: str) -> Any:
    script_path = _find_common_skill_script("triton-npu-run-eval", script_name)
    spec = importlib.util.spec_from_file_location(f"capture_ir_{script_path.stem}", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load run-eval helper: {script_path}")
    module = importlib.util.module_from_spec(spec)
    script_dir = str(script_path.parent)
    added_path = False
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
        added_path = True
    previous_module = sys.modules.get(spec.name)
    # Register before exec: dataclass/typing decorators resolve the module via sys.modules.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous_module is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous_module
        if added_path:
            sys.path.remove(script_dir)
    return module


def _run_remote_debug_command(
    spec: Any,
    remote_source_dir: str,
    command: list[str],
    *,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> ResultPayload:
    remote_command = "export TRITON_DEBUG=1 TRITON_ALWAYS_COMPILE=1 && " + _shell_join_command(command)
    return run_remote_command_buffered(
        spec,
        remote_source_dir,
        remote_command,
        verbose=verbose,
        stderr=stderr,
    )


def _replay_environment(command: list[str]) -> dict[str, str]:
    env = dict(os.environ)
    compiler_dir = os.path.dirname(command[0])
    if compiler_dir:
        env["PATH"] = compiler_dir + os.pathsep + env.get("PATH", "")
    return env


def _build_remote_pass_order_command(
    command: list[str],
    remote_archive_dir: str,
    remote_source_dir: str,
    remote_stage_dir: str | None = None,
    remote_output_file: str | None = None,
) -> str:
    compiler_dir = os.path.dirname(command[0])
    path_prefix = ""
    if compiler_dir:
        path_prefix = f"export PATH={shlex.quote(compiler_dir)}:\"$PATH\" && "
    stage_dir = remote_stage_dir or f"{remote_archive_dir}/bishengir_stages"
    output_file = remote_output_file or f"{remote_archive_dir}/pass-order.json"
    return (
        f"mkdir -p {shlex.quote(stage_dir)} && "
        f"{path_prefix}python3 {shlex.quote(remote_source_dir)}/capture_pass_order.py "
        f"--stage-dir {shlex.quote(stage_dir)} "
        f"--output {shlex.quote(output_file)} -- "
        f"{_shell_join_command(command)}"
    )


def _load_capture_pass_order_module() -> Any:
    script_path = _capture_pass_order_script_path()
    spec = importlib.util.spec_from_file_location("capture_ir_pass_order", script_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load pass-order helper: {script_path}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclass/typing decorators resolve the module via sys.modules.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _shell_join_command(command: list[str]) -> str:
    rendered: list[str] = []
    for token in command:
        if token.startswith("--append-bisheng-options="):
            value = token.split("=", 1)[1]
            rendered.append(f"--append-bisheng-options={shlex.quote(value)}")
            continue
        rendered.append(shlex.quote(token))
    return " ".join(rendered)


def _format_failed_command_message(
    title: str,
    command: str,
    *,
    stdout: str,
    stderr: str,
) -> str:
    parts = [f"{title}: {command}"]
    if stdout.strip():
        parts.append(f"stdout:\n{stdout.rstrip()}")
    if stderr.strip():
        parts.append(f"stderr:\n{stderr.rstrip()}")
    return "\n".join(parts)


def _load_runtime_helpers() -> dict[str, Any]:
    module = _load_run_eval_script_module("run_runtime.py")
    return {
        "create_remote_workspace": module.create_remote_workspace,
        "cleanup_remote_workspace": module.cleanup_remote_workspace,
        "copy_file_to_remote": module.copy_file_to_remote,
        "collect_staging_input_files": module.collect_staging_input_files,
        "copy_directory_from_remote": module.copy_directory_from_remote,
        "run_remote_command_buffered": module.run_remote_command_buffered,
    }


_RUNTIME_HELPERS = _load_runtime_helpers()
create_remote_workspace = _RUNTIME_HELPERS["create_remote_workspace"]
cleanup_remote_workspace = _RUNTIME_HELPERS["cleanup_remote_workspace"]
copy_file_to_remote = _RUNTIME_HELPERS["copy_file_to_remote"]
copy_directory_from_remote = _RUNTIME_HELPERS["copy_directory_from_remote"]
run_remote_command_buffered = _RUNTIME_HELPERS["run_remote_command_buffered"]


if __name__ == "__main__":
    raise SystemExit(main())
