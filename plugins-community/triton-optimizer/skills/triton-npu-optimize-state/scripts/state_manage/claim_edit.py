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
import json
from pathlib import Path
from typing import cast

from shared.managed_integrity import active_state_path
from state_manage.claim_contract import (
    CLAIM_RESPONSE_REQUIRED,
    EDIT_CLAIM_ERROR_FALLBACK_GUIDELINE,
    EDIT_CLAIM_ERROR_GUIDELINES,
)
from state_manage.state_machine import (
    EDIT_CLAIM_SOURCE_KINDS,
    claim_edit as claim_edit_in_workflow_state,
)


def build_parser(*, prog_name: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog_name or Path(__file__).name)
    subparsers = parser.add_subparsers(dest="command", required=True)

    claim = subparsers.add_parser("claim-edit")
    claim.add_argument("--target", required=True)
    claim.add_argument("--source", required=True, choices=EDIT_CLAIM_SOURCE_KINDS)
    claim.add_argument("--pattern-path", action="append", default=[])
    claim.add_argument("--reason", required=True)
    return parser


def _failure_guideline(exc: Exception) -> str:
    """Map a claim-edit failure to an actionable guideline by error code."""
    code = getattr(exc, "code", None)
    return EDIT_CLAIM_ERROR_GUIDELINES.get(
        cast(str, code), EDIT_CLAIM_ERROR_FALLBACK_GUIDELINE
    )


def _normalized_pattern_paths(raw_values: list[str]) -> list[str]:
    pattern_paths: list[str] = []
    for value in raw_values:
        pattern_paths.extend(item.strip() for item in value.split(",") if item.strip())
    return pattern_paths


def _claim_edit_or_report(
    target: Path,
    *,
    source: str,
    reason: str,
    pattern_paths: list[str],
) -> dict[str, object] | None:
    """Run the workflow claim, printing a failure payload and returning None on error."""
    try:
        state_path = active_state_path(target)
        if state_path is None:
            raise RuntimeError("optimize workflow state is not available")
        return claim_edit_in_workflow_state(
            state_path,
            target,
            source_kind=source,
            reason=reason,
            pattern_paths=pattern_paths,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "issues": [str(exc)],
                    "guideline": _failure_guideline(exc),
                },
                ensure_ascii=True,
            )
        )
        return None


def main(argv: list[str] | None = None, *, prog_name: str | None = None) -> int:
    args = build_parser(prog_name=prog_name).parse_args(argv)
    target = Path(args.target).expanduser().resolve()
    pattern_paths = _normalized_pattern_paths(args.pattern_path)
    if args.source == "pattern" and not pattern_paths:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "issues": [
                        "pattern edit claim requires at least one --pattern-path "
                        "(the exact optimize-knowledge pattern markdown file)"
                    ],
                    "guideline": CLAIM_RESPONSE_REQUIRED,
                },
                ensure_ascii=True,
            )
        )
        return 1
    result = _claim_edit_or_report(
        target,
        source=args.source,
        reason=args.reason,
        pattern_paths=pattern_paths,
    )
    if result is None:
        return 1

    print(
        json.dumps(
            {
                "status": "pass",
                "guideline": (
                    "The claim is active. Operator edits for this round are now allowed. "
                    "If an edit hook asks you to claim again after a denial, pass the "
                    "same claim arguments and retry."
                ),
                **result,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
