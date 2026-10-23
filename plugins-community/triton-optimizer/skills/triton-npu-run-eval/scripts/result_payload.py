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

import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Optional, TypedDict, cast


class ResultPayload(TypedDict):
    return_code: int
    stdout: str
    stderr: str
    stalled: bool
    session_id: str | None


def make_result(
    *,
    return_code: int,
    stdout: str,
    stderr: str,
    stalled: bool = False,
    session_id: str | None = None,
) -> ResultPayload:
    return {
        "return_code": return_code,
        "stdout": stdout,
        "stderr": stderr,
        "stalled": stalled,
        "session_id": session_id,
    }


def dump_result_fields(result: ResultPayload) -> dict[str, object]:
    """Serialize a result payload to JSON-safe wire fields."""
    return {
        "return_code": int(result["return_code"]),
        "stdout": str(result["stdout"]),
        "stderr": str(result["stderr"]),
        "stalled": bool(result["stalled"]),
        "session_id": result["session_id"],
    }


def load_result(data: Mapping[str, object]) -> ResultPayload:
    """Rebuild a result payload from decoded wire fields."""
    return make_result(
        return_code=int(cast(int, data["return_code"])),
        stdout=str(data.get("stdout", "")),
        stderr=str(data.get("stderr", "")),
        stalled=bool(data.get("stalled", False)),
        session_id=cast(Optional[str], data.get("session_id")),
    )


def replace_result(result: ResultPayload, **overrides: object) -> ResultPayload:
    """Clone a result payload with selected fields replaced."""
    merged = dump_result_fields(result)
    merged.update(overrides)
    return load_result(merged)


def render_result(result: ResultPayload, skip_stdout: bool) -> None:
    stdout = result["stdout"]
    stderr = result["stderr"]
    if stdout and not skip_stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    if stderr:
        print(stderr, file=sys.stderr, end="" if stderr.endswith("\n") else "\n")


LONG_OUTPUT_CHARACTER_LIMIT = 20_000


def archive_long_failure_output(
    result: ResultPayload,
    *,
    workflow: str,
    character_limit: int = LONG_OUTPUT_CHARACTER_LIMIT,
) -> ResultPayload:
    """Archive oversized failed output and return a concise result payload."""
    if int(result["return_code"]) == 0 and not bool(result["stalled"]):
        return result
    stdout = str(result["stdout"])
    stderr = str(result["stderr"])
    character_count = len(stdout) + len(stderr)
    if character_count <= character_limit:
        return result

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=f"helix-{workflow}-",
            suffix="-output.log",
            delete=False,
        ) as output_file:
            output_path = Path(output_file.name).resolve()
            output_file.write("=== stdout ===\n")
            output_file.write(stdout)
            if stdout and not stdout.endswith(("\n", "\r")):
                output_file.write("\n")
            output_file.write("=== stderr ===\n")
            output_file.write(stderr)
            if stderr and not stderr.endswith(("\n", "\r")):
                output_file.write("\n")
    except OSError:
        return result

    return replace_result(
        result,
        stdout="",
        stderr=(
            f"Output is too long ({character_count} characters); "
            f"full {workflow} output saved to: {output_path}"
        ),
    )


_WARNING_PREFIX = "[WARNING]"


def differential_archive_path(operator_file: Path) -> Path:
    return operator_file.parent / f"{operator_file.stem}_result.pt"


def filter_result_payload(result: ResultPayload, *, verbose: bool) -> ResultPayload:
    if verbose:
        return result
    filtered_stdout = _filter_known_warning_lines(str(result["stdout"]))
    filtered_stderr = _filter_known_warning_lines(str(result["stderr"]))
    if filtered_stdout == result["stdout"] and filtered_stderr == result["stderr"]:
        return result
    return make_result(
        return_code=int(result["return_code"]),
        stdout=filtered_stdout,
        stderr=filtered_stderr,
        stalled=bool(result["stalled"]),
        session_id=result["session_id"],
    )


def _filter_known_warning_lines(text: str) -> str:
    return "".join(
        line
        for line in text.splitlines(keepends=True)
        if not line.rstrip("\r\n").startswith(_WARNING_PREFIX)
    )
