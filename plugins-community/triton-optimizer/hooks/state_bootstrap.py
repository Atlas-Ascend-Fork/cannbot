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

__all__ = [
    "BootstrapResult",
    "bootstrap_runtime_state",
    "prepare_compiler_source_context",
    "resolve_workspace",
]

from dataclasses import dataclass
import os
from pathlib import Path
import sys

from compiler_source import (
    CompilerSourceInfo,
    RunGit,
    prepare_compiler_source,
)
from workflow_state import recover_optimize_workflow_state

_SESSION_GUIDANCE_FILENAME = "session-guidance.md"


@dataclass(frozen=True)
class BootstrapResult:
    additional_context: str | None = None


def _load_session_guidance() -> str | None:
    guidance_path = Path(__file__).resolve().parent / _SESSION_GUIDANCE_FILENAME
    try:
        content = guidance_path.read_text(encoding="utf-8")
    except OSError as exc:  # noqa: BLE001 - hook must fail open
        print(
            f"helix claude plugin SessionStart cannot read session guidance: {exc}",
            file=sys.stderr,
        )
        return None
    stripped = content.strip()
    return stripped or None


def bootstrap_runtime_state(
    workspace: Path,
    *,
    compiler_source_enabled: bool | None = None,
    compiler_source_cache_dir: Path | None = None,
    run_git: RunGit | None = None,
) -> BootstrapResult:
    contexts: list[str] = []
    guidance = _load_session_guidance()
    if guidance is not None:
        contexts.append(guidance)
    runtime_dir = workspace / ".helix"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    recovery = recover_optimize_workflow_state(
        workspace,
        state_path=runtime_dir / "state.json",
    )
    if recovery.guidance is not None:
        contexts.append(recovery.guidance)

    compiler_context = prepare_compiler_source_context(
        compiler_source_enabled=compiler_source_enabled,
        compiler_source_cache_dir=compiler_source_cache_dir,
        run_git=run_git,
    )
    if compiler_context is not None:
        contexts.append(compiler_context)

    return BootstrapResult(_join_contexts(contexts))


def prepare_compiler_source_context(
    *,
    compiler_source_enabled: bool | None = None,
    compiler_source_cache_dir: Path | None = None,
    run_git: RunGit | None = None,
) -> str | None:
    if not _compiler_source_enabled(compiler_source_enabled):
        return None
    try:
        compiler_source = prepare_compiler_source(
            mode="auto",
            cache_dir=compiler_source_cache_dir,
            run_git=run_git,
        )
    except ValueError as exc:
        return (
            "Compiler source analysis is unavailable: "
            f"{exc}. Continue optimize work without compiler source unless the user fixes "
            "the checkout or network access."
        )
    if compiler_source is None:
        return None
    return _compiler_source_context(compiler_source)


def resolve_workspace(payload: dict[str, object]) -> Path | None:
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd).expanduser().resolve()
    return None


def _compiler_source_enabled(value: bool | None) -> bool:
    if value is not None:
        return value
    configured = os.environ.get("HELIX_CLAUDE_PLUGIN_COMPILER_SOURCE", "auto")
    return configured.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _compiler_source_context(compiler_source: CompilerSourceInfo) -> str:
    return "\n".join(
        [
            "Compiler source analysis is enabled.",
            f"Compiler source path: {compiler_source.path}",
            f"Compiler source commit: {compiler_source.commit}.",
            "Treat the compiler source checkout as read-only.",
            "Do not run git clone, git fetch, git pull, or modify files in the compiler source checkout.",
            "Use the bundled triton-npu-analyze-compiler-source skill only when compiler source evidence is needed.",
        ]
    )


def _join_contexts(contexts: list[str]) -> str | None:
    if not contexts:
        return None
    return "\n\n".join(contexts)
