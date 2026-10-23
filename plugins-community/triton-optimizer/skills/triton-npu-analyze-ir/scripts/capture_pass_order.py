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
import hashlib
import json
import re
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any, Optional


_IR_DUMP_HEADER = re.compile(
    r"^// -----// IR Dump After (?P<name>.+) \((?P<pass_id>[^()]+)\) //----- //$"
)


class _IrBlockCollector:
    """Accumulates IR dump blocks from a replay stderr stream."""

    def __init__(self, stage_dir: Path) -> None:
        self.stage_dir = stage_dir
        self.created_paths: list[Path] = []
        self.partial_path: Path | None = None
        self.partial_stream: Any = None
        self.passes: list[dict[str, Any]] = []
        self.header: str | None = None
        self.pass_name: str | None = None
        self.pass_id: str | None = None
        self.block_digest = hashlib.sha256()

    def feed(self, line: str, diagnostics: deque[str]) -> None:
        stripped = line.rstrip("\n")
        match = _IR_DUMP_HEADER.match(stripped)
        if match:
            self.finalize_block()
            self.header = stripped
            self.pass_name = match.group("name")
            self.pass_id = match.group("pass_id")
            self.block_digest.update(line.encode("utf-8"))
            self.partial_path = self.stage_dir / f".capture-{len(self.passes) + 1:06d}.partial"
            self.partial_stream = self.partial_path.open("w", encoding="utf-8", newline="")
            self.partial_stream.write(line)
            return
        if self.header is None:
            diagnostics.append(line)
            return
        self.block_digest.update(line.encode("utf-8"))
        if self.partial_path is None or self.partial_stream is None:
            raise RuntimeError("Internal error: missing partial IR stage.")
        self.partial_stream.write(line)

    def finalize_block(self) -> None:
        if self.header is None:
            return
        if self.pass_name is None or self.pass_id is None:
            raise RuntimeError("Internal error: incomplete IR block header.")
        index = len(self.passes) + 1
        stage_path = self.stage_dir / f"{index:06d}_{_sanitize_stage_component(self.pass_id)}.mlir"
        if self.partial_path is None:
            raise RuntimeError("Internal error: missing partial IR stage.")
        if self.partial_stream is not None:
            self.partial_stream.close()
            self.partial_stream = None
        self.partial_path.replace(stage_path)
        self.created_paths.append(stage_path)
        self.passes.append(
            {
                "index": index,
                "header": self.header,
                "pass_name": self.pass_name,
                "pass_id": self.pass_id,
                "ir_sha256": self.block_digest.hexdigest(),
                "match": "sha256",
                "stage_paths": [stage_path.relative_to(self.stage_dir.parent).as_posix()],
            }
        )
        self.partial_path = None
        self.header = None
        self.pass_name = None
        self.pass_id = None
        self.block_digest = hashlib.sha256()

    def cleanup(self) -> None:
        if self.partial_stream is not None:
            self.partial_stream.close()
        if self.partial_path is not None:
            self.partial_path.unlink(missing_ok=True)
        for path in self.created_paths:
            path.unlink(missing_ok=True)


def capture_stages_and_pass_order(
    command: list[str],
    *,
    stage_dir: Path,
    output_path: Path,
    env: Optional[dict[str, str]] = None,
) -> Path:
    """Replay a compiler once, archiving stderr IR blocks and their order.

    The compiler's ``--mlir-print-ir-after-all`` output is a stream of complete
    module snapshots.  Keeping the stream parser here means local and remote
    capture use the same stage naming, digest, and failure behavior.
    """
    stage_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    stderr_stream = process.stderr
    if stderr_stream is None:
        raise RuntimeError("Unable to capture replay stderr for stage extraction.")

    diagnostics: deque[str] = deque(maxlen=20)
    collector = _IrBlockCollector(stage_dir)
    temporary_output: Path | None = None
    try:
        for line in stderr_stream:
            collector.feed(line, diagnostics)
        collector.finalize_block()
        return_code = process.wait()
        if return_code != 0:
            detail = "".join(diagnostics).strip()
            if detail:
                raise RuntimeError(f"Replay compile command failed:\n{detail}")
            raise RuntimeError("Replay compile command failed without compiler diagnostics.")
        if not collector.passes:
            raise RuntimeError("Replay completed without any parseable IR dump headers.")

        payload = {"schema_version": 1, "passes": collector.passes}
        temporary_output = output_path.with_name(f".{output_path.name}.partial")
        temporary_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary_output.replace(output_path)
        return output_path
    except Exception:
        collector.cleanup()
        if temporary_output is not None:
            temporary_output.unlink(missing_ok=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture BiSheng IR stages and pass order from replay stderr.")
    parser.add_argument("--stage-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        print("Expected a replay command after '--'.", file=sys.stderr)
        return 2
    try:
        output_path = capture_stages_and_pass_order(
            command,
            stage_dir=Path(args.stage_dir),
            output_path=Path(args.output),
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Pass order: {output_path}")
    return 0


def _sanitize_stage_component(value: str) -> str:
    sanitized = "".join(
        character if character.isalnum() or character in {".", "_", "-"} else "_"
        for character in value
    ).strip(".")
    return sanitized or "unknown-pass"


if __name__ == "__main__":
    raise SystemExit(main())
