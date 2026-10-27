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

"""Codex CLI backend plugin.

This is the harness adapter layer only. It deliberately does not translate the
canonical gates or reference-provider logic; those remain in orchestrator
Python. The first production use should be a small structured-output spike
before routing long-running op-gen workers through this backend.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from .base import (
    Backend,
    Envelope,
    TranscriptSkills,
    format_backend_agent,
    normalize_backend_envelope,
)
from .skill_context import load_skill_context

_CODEX_EXEC_MARKERS = ("codex exec", "codex  exec")
_OP_SLUG_RE = re.compile(
    r"\b([a-z][a-z0-9_]*)-(?:kw|pp|ko|fo|ar|da|bs|td|tt|tpo|cl)-\d+"
)


class CodexBackend(Backend):
    name = "codex"

    def __init__(self, codex_bin: str | None = None):
        self.codex_bin = codex_bin or os.environ.get("AOG_CODEX_BIN", "codex")

    def dispatch(
        self,
        target: str,
        prompt: str,
        *,
        kind: str = "agent",
        mode: str = "foreground",
        # effort accepted for cc-parity; codex resolves it from its own profile
        effort: Optional[str] = None,
        timeout: Optional[float] = None,
        silence_timeout: Optional[int] = None,
        sandbox_prefix: Optional[list] = None,
        extra_args: Optional[list] = None,
        cwd=None,
        output_file=None,
        tee_path=None,
        progress_callback=None,
        # session/settings accepted for cc-contract parity; codex ignores settings
        session: Optional[str] = None,
        settings: Optional[str] = None,
        permission_mode: str = "bypassPermissions",
        output_format: Optional[str] = "json",
        stdin_prompt: bool = False,
    ) -> Envelope:
        self._require_supported_dispatch(mode, sandbox_prefix)
        formatted = self._format_prompt(target, prompt, kind=kind)
        with tempfile.NamedTemporaryFile(
            prefix="aog-codex-last-", suffix=".txt", delete=False
        ) as tmp:
            last_path = tmp.name
        try:
            return self._run_exec(
                formatted,
                last_path,
                kind=kind,
                mode=mode,
                timeout=timeout,
                cwd=cwd,
                extra_args=extra_args,
                tee_path=tee_path,
            )
        except subprocess.TimeoutExpired:
            return self._exec_error_envelope({"timed_out": True, "cmd_kind": kind})
        except FileNotFoundError as e:
            return self._exec_error_envelope({"not_found": True, "stderr": str(e)})
        finally:
            try:
                Path(last_path).unlink()
            except OSError:
                pass

    def normalize(self, raw: Any) -> Envelope:
        return normalize_backend_envelope(raw, self.name)

    def format_agent(self, agent_def: dict) -> dict:
        return format_backend_agent(agent_def, self.name)

    def wire_safety(self, checkers: list) -> None:
        return None

    def resume(self, session_id: str, prompt: str) -> Envelope:
        formatted = self._format_prompt("resume", prompt, kind="resume")
        with tempfile.NamedTemporaryFile(
            prefix="aog-codex-resume-last-", suffix=".txt", delete=False
        ) as tmp:
            last_path = tmp.name
        try:
            cmd = [
                self.codex_bin,
                "exec",
                "resume",
                session_id,
                "--json",
                "-o",
                last_path,
                "-",
            ]
            completed = subprocess.run(
                cmd, input=formatted, capture_output=True, text=True
            )
            output_text = (
                Path(last_path).read_text(errors="replace")
                if Path(last_path).exists()
                else completed.stdout
            )
            return Envelope(
                is_error=completed.returncode != 0,
                output_text=output_text or "",
                raw_envelope={
                    "returncode": completed.returncode,
                    "stderr": completed.stderr or "",
                    "stdout": completed.stdout or "",
                    "cmd_kind": "resume",
                    "backend": self.name,
                },
            )
        except FileNotFoundError as e:
            return Envelope(
                is_error=True,
                output_text="",
                raw_envelope={"not_found": True, "stderr": str(e)},
            )
        finally:
            try:
                Path(last_path).unlink()
            except OSError:
                pass

    def transcript_skills(self, transcript_path) -> TranscriptSkills:
        """Report that Codex transcripts cannot prove tier-a skill invocation."""
        return TranscriptSkills(
            parseable=False,
            note="codex transcripts carry no skill-tool events — CBA route gate cannot prove tier-a USE",
        )

    def identify_cmd(self, cmd: str) -> bool:
        return any(marker in cmd for marker in _CODEX_EXEC_MARKERS)

    def parse_op_from_cmd(self, cmd: str) -> Optional[str]:
        m = _OP_SLUG_RE.search(cmd)
        return m.group(1) if m else None

    def _require_supported_dispatch(self, mode: str, sandbox_prefix) -> None:
        """Codex's dispatch surface today: no background mode, no bwrap prefix."""
        if mode == "background":
            raise NotImplementedError(
                "CodexBackend does not support background dispatch yet"
            )
        if sandbox_prefix:
            raise NotImplementedError(
                "CodexBackend does not support orchestrator bwrap sandbox_prefix yet"
            )

    def _exec_error_envelope(self, raw_extra: dict) -> Envelope:
        """A failed-exec envelope (timeout / missing CLI)."""
        return Envelope(
            is_error=True,
            output_text="",
            raw_envelope={"backend": self.name, **raw_extra},
        )

    def _run_exec(
        self, formatted, last_path, *, kind, mode, timeout, cwd, extra_args, tee_path
    ) -> Envelope:
        """Run the codex exec subprocess and collect (tee on success)."""
        cmd = self._build_exec_cmd(
            last_path,
            cwd=str(cwd) if cwd is not None else None,
            sandbox=os.environ.get("AOG_CODEX_SANDBOX"),
            extra_args=extra_args,
        )
        completed = subprocess.run(
            cmd,
            input=formatted,
            capture_output=True,
            text=True,
            timeout=int(timeout) if timeout else None,
        )
        if tee_path:
            Path(tee_path).parent.mkdir(parents=True, exist_ok=True)
            Path(tee_path).write_text(completed.stdout or "")
        return self._collect_exec_result(last_path, completed, kind=kind, mode=mode)

    def _collect_exec_result(
        self, last_path: str, completed, *, kind, mode
    ) -> Envelope:
        """The success envelope: the exec tool's last-message file wins over
        raw stdout (empty file falls back to stdout)."""
        output_text = ""
        last = Path(last_path)
        if last.exists():
            output_text = last.read_text(errors="replace")
        if not output_text:
            output_text = completed.stdout or ""
        return Envelope(
            is_error=completed.returncode != 0,
            output_text=output_text,
            raw_envelope={
                "returncode": completed.returncode,
                "stderr": completed.stderr or "",
                "stdout": completed.stdout or "",
                "cmd_kind": kind,
                "backend": self.name,
                "mode": mode,
            },
        )

    def _build_exec_cmd(
        self,
        last_message_path: str,
        *,
        cwd: str | None = None,
        sandbox: str | None = None,
        extra_args: Optional[list] = None,
    ) -> list:
        cmd = [self.codex_bin, "exec", "--json", "-o", last_message_path]
        if cwd:
            cmd += ["-C", cwd]
        if sandbox:
            cmd += ["--sandbox", sandbox]
        if extra_args:
            cmd += list(extra_args)
        cmd += ["-"]
        return cmd

    def _format_prompt(self, target: str, prompt: str, *, kind: str) -> str:
        skill_context = load_skill_context(target) if kind == "skill" else None
        skill_block = f"\n\n{skill_context}" if skill_context else ""
        return (
            f"You are running as the a5_ops harness backend target {target!r} "
            f"(kind={kind!r}) through Codex CLI.\n\n"
            "Follow the a5_ops orchestrator brief below. Return only the final "
            "worker/skill result text expected by the orchestrator."
            f"{skill_block}\n\n"
            "----- a5_ops prompt -----\n"
            f"{prompt}"
        )
