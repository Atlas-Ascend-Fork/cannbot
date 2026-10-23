# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Remote workspace API for canonical benchmark, probe, and profile execution."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO, cast

from debug_device import maybe_print_visible_devices
from ascendc_runtime import ascendc_source_path, is_ascendc_operator
from env_registry import (
    HELIX_BENCH_DEFER_PARSE,
    HELIX_BENCH_OUTPUT_DIR,
    bench_defer_parse_enabled,
    bench_output_dir,
)
from perf_artifacts import PerfCaseRecord, perf_case_record_from_mapping
from profile_artifacts import validate_profile_dir
from remote_python_bundle import resolve_remote_python_bundle
from result_payload import ResultPayload, archive_long_failure_output, load_result
from run_bench_local_api import (
    _has_missing_planned_cases,  # pyright: ignore[reportPrivateUsage]  # shared within the skill scripts
    _perf_file_is_complete,  # pyright: ignore[reportPrivateUsage]  # shared within the skill scripts
    _resolve_perf_output_path,  # pyright: ignore[reportPrivateUsage]  # shared within the skill scripts
    _write_synthesized_perf,  # pyright: ignore[reportPrivateUsage]  # shared within the skill scripts
)
from run_bench_modes import collect_bench_copy_files, normalize_bench_mode
from run_runtime import (
    RemoteSpec,
    StagingInput,
    cleanup_remote_workspace,
    collect_staging_input_files,
    copy_directory_from_remote,
    copy_file_from_remote,
    copy_staging_files_to_remote,
    create_remote_workspace,
    result_succeeded,
    run_remote_command_buffered,
)
from worker_supervisor import SupervisedRun, run_remote_worker


class RemoteBenchSession:
    """Reuse one remote root and worker bundle for sequential benchmark runs.

    Inputs stage flat into the root workspace so shared files transfer once.
    Each named run executes in its own snapshot directory below the root so
    same-named operator files and generated artifacts stay isolated.
    """

    def __init__(
        self,
        remote: str,
        remote_workdir: str | None,
        *,
        keep_remote_workdir: bool,
        verbose: bool,
        stderr: TextIO | None,
    ) -> None:
        self.remote = remote
        self.remote_workdir = remote_workdir
        self.keep_remote_workdir = keep_remote_workdir
        self.verbose = verbose
        self.stderr = stderr
        self.spec: RemoteSpec | None = None
        self.workspace: str | None = None
        self.runtime_bundle = resolve_remote_python_bundle([_worker_script()])
        self.staged: set[tuple[str, str]] = set()

    def start(self) -> "RemoteBenchSession":
        self.spec, self.workspace = create_remote_workspace(
            self.remote, self.remote_workdir, verbose=self.verbose, stderr=self.stderr
        )
        try:
            self._stage(
                [{"source": path, "target": path.name} for path in self.runtime_bundle],
                self.workspace,
            )
        except BaseException:
            self._dispose_workspace()
            raise
        return self

    def run(
        self,
        bench_file: Path,
        operator_file: Path,
        bench_mode: str,
        *,
        warmup_cap: int | None,
        repeats_cap: int | None,
        output: str | None,
        run_name: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> tuple[ResultPayload, Path | None]:
        if self.spec is None or self.workspace is None:
            raise RuntimeError("Remote benchmark session has not been started.")
        if (warmup_cap is None) != (repeats_cap is None):
            raise ValueError("Both execution limits are required together")
        maybe_print_visible_devices()
        bench_mode = normalize_bench_mode(bench_mode)
        perf_path = _resolve_perf_output_path(operator_file, output=output)
        records = _bench_staging_records(bench_file, operator_file, self.runtime_bundle)
        self._stage(records, self.workspace)
        execution_workspace = self.workspace
        if run_name is not None:
            execution_workspace = _run_directory(self.workspace, run_name)
            self._prepare_run_directory(run_name)
        run = run_remote_worker(
            self.spec,
            execution_workspace,
            _build_remote_bench_command(
                bench_file.name,
                operator_file.name,
                bench_mode,
                output_name=perf_path.name,
                warmup_cap=warmup_cap,
                repeats_cap=repeats_cap,
                verbose=self.verbose,
            ),
            extra_env=_bench_execution_env(bench_mode, extra_env),
            verbose=self.verbose,
            stderr=self.stderr,
        )
        result, resolved_perf_path = _collect_remote_bench_perf(
            self.spec,
            execution_workspace,
            run,
            bench_mode=bench_mode,
            perf_path=perf_path,
            verbose=self.verbose,
            stderr=self.stderr,
        )
        return archive_long_failure_output(result, workflow="run-bench"), resolved_perf_path

    def run_profile(
        self,
        bench_file: Path,
        operator_file: Path,
        *,
        case_id: str,
    ) -> tuple[ResultPayload, str | None]:
        """Profile one case remotely and return the pruned PROF_* directory name."""
        if self.spec is None or self.workspace is None:
            raise RuntimeError("Remote benchmark session has not been started.")
        records = _bench_staging_records(bench_file, operator_file, self.runtime_bundle)
        self._stage(records, self.workspace)
        run = run_remote_worker(
            self.spec,
            self.workspace,
            [
                "python3",
                _worker_script().name,
                "profile-artifact",
                "--bench-file",
                bench_file.name,
                "--operator-file",
                operator_file.name,
                "--case-id",
                case_id,
            ],
            verbose=self.verbose,
            stderr=self.stderr,
        )
        if run.final is None:
            return run.result, None
        result = load_result(cast(Mapping[str, object], run.final["result"]))
        if not result_succeeded(result):
            return result, None
        profile_name = run.final.get("profile_name")
        return result, None if profile_name is None else str(profile_name)

    def close(self) -> None:
        self._dispose_workspace()

    def _dispose_workspace(self) -> None:
        if self.spec is not None and self.workspace is not None and not self.keep_remote_workdir:
            cleanup_remote_workspace(self.spec, self.workspace, verbose=self.verbose, stderr=self.stderr)

    def _prepare_run_directory(self, run_name: str) -> None:
        if self.spec is None or self.workspace is None:
            raise RuntimeError("Remote benchmark session has not been started.")
        command = (
            f"rm -rf {run_name} && mkdir {run_name} && "
            f'for entry in *; do if [ -f "$entry" ]; then cp "$entry" {run_name}/; fi; done'
        )
        result = run_remote_command_buffered(
            self.spec, self.workspace, command, verbose=self.verbose, stderr=self.stderr
        )
        if not result_succeeded(result):
            raise RuntimeError(
                result["stderr"] or result["stdout"] or f"Failed to prepare remote run directory {run_name}."
            )

    def _stage(self, records: list[dict[str, object]], workspace: str) -> None:
        if self.spec is None:
            raise RuntimeError("Remote benchmark session has not been started.")
        pending: list[StagingInput] = []
        for record in records:
            key = _staging_key(record)
            if key not in self.staged:
                pending.append(cast(StagingInput, record))
        if pending:
            copy_staging_files_to_remote(
                self.spec, pending, workspace, verbose=self.verbose, stderr=self.stderr
            )
            self.staged.update(_staging_key(record) for record in pending)


def open_remote_bench_session(
    remote: str,
    remote_workdir: str | None,
    *,
    keep_remote_workdir: bool,
    verbose: bool,
    stderr: TextIO | None,
) -> RemoteBenchSession:
    """Open a reusable remote benchmark workspace for sequential runs."""
    return RemoteBenchSession(
        remote,
        remote_workdir,
        keep_remote_workdir=keep_remote_workdir,
        verbose=verbose,
        stderr=stderr,
    ).start()


def run_remote_bench_comparison(
    bench_file: Path,
    baseline_operator_file: Path,
    operator_file: Path,
    bench_mode: str,
    *,
    remote: str,
    remote_workdir: str | None,
    keep_remote_workdir: bool = False,
    verbose: bool = False,
    stderr: TextIO | None = None,
    output: str | None = None,
) -> tuple[tuple[ResultPayload, Path | None], tuple[ResultPayload, Path | None] | None, str]:
    """Run baseline and candidate benchmarks in one remote workspace."""
    session = open_remote_bench_session(
        remote,
        remote_workdir,
        keep_remote_workdir=keep_remote_workdir,
        verbose=verbose,
        stderr=stderr,
    )
    try:
        baseline = session.run(
            bench_file,
            baseline_operator_file,
            bench_mode,
            warmup_cap=None,
            repeats_cap=None,
            output=None,
            run_name="baseline",
        )
        if baseline[1] is None or int(baseline[0]["return_code"]) != 0:
            if session.workspace is None:
                raise RuntimeError("internal error: remote bench session has no workspace")
            return baseline, None, session.workspace
        candidate = session.run(
            bench_file,
            operator_file,
            bench_mode,
            warmup_cap=None,
            repeats_cap=None,
            output=output,
            run_name="candidate",
        )
        if session.workspace is None:
            raise RuntimeError("internal error: remote bench session has no workspace")
        return baseline, candidate, session.workspace
    finally:
        session.close()


def run_remote_bench(
    bench_file: Path,
    operator_file: Path,
    bench_mode: str,
    remote: str,
    remote_workdir: str | None,
    *,
    keep_remote_workdir: bool = False,
    verbose: bool = False,
    stderr: TextIO | None = None,
    output: str | None = None,
    warmup_cap: int | None = None,
    repeats_cap: int | None = None,
    extra_env: dict[str, str] | None = None,
) -> tuple[ResultPayload, Path | None, str]:
    session = open_remote_bench_session(
        remote,
        remote_workdir,
        keep_remote_workdir=keep_remote_workdir,
        verbose=verbose,
        stderr=stderr,
    )
    try:
        result, perf_path = session.run(
            bench_file,
            operator_file,
            bench_mode,
            warmup_cap=warmup_cap,
            repeats_cap=repeats_cap,
            output=output,
            extra_env=extra_env,
        )
        if session.workspace is None:
            raise RuntimeError("internal error: remote bench session has no workspace")
        return result, perf_path, session.workspace
    finally:
        session.close()


def run_remote_profile_bench(
    bench_file: Path,
    operator_file: Path,
    remote: str,
    remote_workdir: str | None,
    *,
    case_id: str | None = None,
    kernel_name: str | None = None,
    output_dir: Path | None = None,
    keep_remote_workdir: bool = False,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> tuple[ResultPayload, Path | None, str]:
    del kernel_name
    if case_id is None:
        raise ValueError("torch-npu-profiler benchmark profiling requires --case-id <id>.")
    session = open_remote_bench_session(
        remote,
        remote_workdir,
        keep_remote_workdir=keep_remote_workdir,
        verbose=verbose,
        stderr=stderr,
    )
    try:
        result, profile_name = session.run_profile(bench_file, operator_file, case_id=case_id)
        if session.spec is None or session.workspace is None:
            raise RuntimeError("internal error: remote bench session is not fully started")
        if not result_succeeded(result) or profile_name is None:
            return result, None, session.workspace
        local_profile_dir = operator_file.parent / profile_name
        if local_profile_dir.exists():
            raise FileExistsError(f"Local profile directory already exists: {local_profile_dir}")
        copy_directory_from_remote(
            session.spec, f"{session.workspace}/{profile_name}", local_profile_dir, verbose=verbose, stderr=stderr
        )
        validate_profile_dir(local_profile_dir)
        if output_dir is not None:
            output_dir = output_dir.expanduser().resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            target = output_dir / local_profile_dir.name
            if target.exists():
                raise FileExistsError(f"Profile directory already exists: {target}")
            shutil.move(str(local_profile_dir), str(target))
            local_profile_dir = target
        return result, local_profile_dir, session.workspace
    finally:
        session.close()


def _collect_remote_bench_perf(
    spec: RemoteSpec,
    remote_workspace: str,
    run: SupervisedRun,
    *,
    bench_mode: str,
    perf_path: Path,
    verbose: bool = False,
    stderr: TextIO | None = None,
) -> tuple[ResultPayload, Path | None]:
    """Pull the remote perf file and shape partial runs locally.

    A worker that died before its final line (or completed without reporting
    every planned case) still has usable partial records; those are combined
    with synthesized missing-case records at the local pull destination.
    Nothing is ever written back to the remote host.
    """
    captured_records: list[PerfCaseRecord] = [
        perf_case_record_from_mapping(record, bench_mode=bench_mode)
        for record in run.records
    ]
    worker_result = (
        run.result
        if run.final is None
        else load_result(cast(Mapping[str, object], run.final["result"]))
    )
    try:
        copy_file_from_remote(
            spec,
            f"{remote_workspace}/{perf_path.name}",
            perf_path,
            verbose=verbose,
            stderr=stderr,
        )
        pulled = True
    except RuntimeError:
        if result_succeeded(worker_result):
            raise
        pulled = False
    if run.final is None:
        if not captured_records and not run.planned_case_ids:
            return worker_result, None
        if not _perf_file_is_complete(run, perf_path):
            _write_synthesized_perf(perf_path, run, captured_records)
        return worker_result, perf_path
    if _has_missing_planned_cases(run, captured_records) and not _perf_file_is_complete(
        run, perf_path
    ):
        _write_synthesized_perf(perf_path, run, captured_records)
        return worker_result, perf_path
    return worker_result, perf_path if pulled else None


def _bench_execution_env(
    bench_mode: str,
    extra_env: dict[str, str] | None,
) -> dict[str, str] | None:
    if bench_mode == "perf-counter" or not bench_defer_parse_enabled():
        return dict(extra_env) if extra_env is not None else None
    # Deferred parsing runs inside the remote worker and buffers raw traces
    # between batch parses. An unset HELIX_BENCH_OUTPUT_DIR forwards nothing,
    # so the worker falls back to its own temporary run directory (created
    # under the system temp root and removed in the deferred pipeline's
    # finally, success or failure) — the same behavior as a local unset run.
    # The backpressure gate bounds unparsed trace bytes on that filesystem,
    # RAM-backed or not, so tmpfs placement degrades to throttling.
    env = {**(extra_env or {}), HELIX_BENCH_DEFER_PARSE: "1"}
    configured_root = bench_output_dir()
    if configured_root is not None:
        env[HELIX_BENCH_OUTPUT_DIR] = configured_root
    return env


def _build_remote_bench_command(
    bench_name: str,
    operator_name: str,
    bench_mode: str,
    *,
    output_name: str,
    warmup_cap: int | None = None,
    repeats_cap: int | None = None,
    verbose: bool = False,
) -> list[str]:
    command = [
        "python3",
        _worker_script().name,
        "run-bench",
        "--bench-file",
        bench_name,
        "--operator-file",
        operator_name,
        "--bench-mode",
        bench_mode,
        "--output",
        output_name,
    ]
    if warmup_cap is not None and repeats_cap is not None:
        command.extend(["--warmup-cap", str(warmup_cap), "--repeats-cap", str(repeats_cap)])
    if verbose:
        command.append("--verbose")
    return command


def _bench_staging_records(
    bench_file: Path,
    operator_file: Path,
    runtime_bundle: list[Path],
) -> list[dict[str, object]]:
    explicit: list[tuple[Path, str]] = [
        (bench_file, bench_file.name),
        (operator_file, operator_file.name),
    ]
    bench_json = bench_file.with_suffix(".json")
    if bench_json.exists():
        explicit.append((bench_json, bench_json.name))
    extra_files = [(path, path.name) for path in collect_bench_copy_files(bench_file.parent)]
    staged = collect_staging_input_files(
        (bench_file.parent, operator_file.parent),
        tuple(explicit),
        extra_files=tuple(extra_files) + _ascendc_remote_files(operator_file),
        excluded_names=tuple(path.name for path in runtime_bundle),
    )
    return [dict(record) for record in staged]


def _staging_key(record: Mapping[str, object]) -> tuple[str, str]:
    return (str(Path(str(record["source"])).resolve()), str(record["target"]))


def _run_directory(workspace: str, run_name: str) -> str:
    if not run_name or Path(run_name).name != run_name or run_name in {".", ".."}:
        raise ValueError(f"Invalid remote run directory name: {run_name}")
    return f"{workspace}/{run_name}"


def _worker_script() -> Path:
    return Path(__file__).resolve().with_name("run_bench_worker.py")


def _ascendc_remote_files(operator_file: Path) -> tuple[tuple[Path, str], ...]:
    if not is_ascendc_operator(operator_file):
        return ()
    return ((ascendc_source_path(operator_file), ascendc_source_path(operator_file).name),)
