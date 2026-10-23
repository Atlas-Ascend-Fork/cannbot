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
import importlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from cann_bench_native_replay import create_native_ref_operator
import npu_compare
from npu_compare_common import ArtifactCompareResult


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref-result", "--oracle-result", dest="ref_result", required=True)
    parser.add_argument("--new-result", required=True)
    parser.add_argument(
        "--accuracy-mode",
        choices=["npu-contract", "dtype-close", "cann-bench"],
        default=None,
    )
    parser.add_argument("--test-file", help=argparse.SUPPRESS)
    parser.add_argument("--ref-operator-file", help=argparse.SUPPRESS)
    args = parser.parse_args()
    native_ref_operator = None
    if args.accuracy_mode == "cann-bench" and args.test_file and args.ref_operator_file:
        native_ref_operator = create_native_ref_operator(
            Path(args.test_file), Path(args.ref_operator_file)
        )
    return compare_result_files(
        args.ref_result,
        args.new_result,
        accuracy_mode=args.accuracy_mode,
        native_ref_operator=native_ref_operator,
    )


def compare_result_payload_objects(
    ref_payload: object,
    new_payload: object,
    *,
    accuracy_mode: str | None = None,
    native_ref_operator: Any = None,
) -> int:
    result = npu_compare.compare_result_payloads(
        ref_payload,
        new_payload,
        accuracy_mode=accuracy_mode,
        native_ref_operator=native_ref_operator,
    )
    print(format_artifact_compare_result(result))
    return 0 if result.passed else 1


def _failed_case_lines(case_result_item: object) -> list[str]:
    lines = [case_result_item.message]
    diagnostics = case_result_item.diagnostics
    threshold_info = diagnostics.get("thresholds")
    if isinstance(threshold_info, Mapping):
        lines.append(f"  thresholds={dict(cast(Mapping[object, object], threshold_info))}")
    lines.append(f"  diagnostics={dict(diagnostics)}")
    return lines


def format_artifact_compare_result(result: ArtifactCompareResult) -> str:
    lines = [result.message]
    if not result.passed:
        for case_result_item in result.case_results:
            if not case_result_item.passed:
                lines.extend(_failed_case_lines(case_result_item))
    return "\n".join(lines)


def compare_result_files(
    ref_result: str | Path,
    new_result: str | Path,
    *,
    accuracy_mode: str | None = None,
    native_ref_operator: Any = None,
) -> int:
    return compare_result_payload_objects(
        load_result_payload(ref_result),
        load_result_payload(new_result),
        accuracy_mode=accuracy_mode,
        native_ref_operator=native_ref_operator,
    )


def load_result_payload(path: str | Path) -> object:
    torch_module = cast(Any, importlib.import_module("torch"))
    return torch_module.load(Path(path), map_location="cpu")


def find_case_result_payload(path: str | Path, case_id: str) -> object | None:
    return _find_case_result_payload(load_result_payload(path), case_id, label=str(Path(path)))


def load_case_result_payload(path: str | Path, case_id: str) -> object:
    payload = find_case_result_payload(path, case_id)
    if payload is not None:
        return payload
    available = ", ".join(_list_result_case_ids(load_result_payload(path), label=str(Path(path))))
    raise ValueError(
        f"Result payload '{Path(path)}' does not contain case '{case_id}'. Available case ids: {available}"
    )


def _find_case_result_payload(
    payload: object,
    case_id: str,
    *,
    label: str,
) -> object | None:
    compute, cases = _extract_payload_cases(payload, label=label)
    for case in cases:
        if case["id"] == case_id:
            return {
                "compute": compute,
                "cases": [
                    {
                        "id": case["id"],
                        "inputs": case["inputs"],
                        "result": case["result"],
                    }
                ],
            }
    return None


def _list_result_case_ids(payload: object, *, label: str) -> list[str]:
    _compute, cases = _extract_payload_cases(payload, label=label)
    return [cast(str, case["id"]) for case in cases]


def _extract_payload_cases(
    payload: object,
    *,
    label: str,
) -> tuple[bool, list[dict[str, object]]]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"Result payload '{label}' must be a dict with a 'cases' entry.")
    payload_map = cast(Mapping[str, object], payload)
    if "results" in payload_map:
        raise ValueError(
            f"Result payload '{label}' uses the legacy payload format. "
            "Expected {'compute': <bool>, 'cases': [...]} instead of {'results': [...]}."
        )
    raw_cases = payload_map.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError(f"Result payload '{label}' is missing required list field 'cases'.")
    raw_compute = payload_map.get("compute")
    compute = raw_compute if isinstance(raw_compute, bool) else True
    cases: list[dict[str, object]] = []
    for raw_case in cast(list[object], raw_cases):
        if not isinstance(raw_case, Mapping):
            raise ValueError(f"Result payload '{label}' contains a non-mapping case entry.")
        case_map = cast(Mapping[str, object], raw_case)
        case_id = case_map.get("id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"Result payload '{label}' contains a case without a valid string id.")
        if "inputs" not in case_map:
            raise ValueError(f"Result payload '{label}' case '{case_id}' is missing required field 'inputs'.")
        if "result" not in case_map:
            raise ValueError(f"Result payload '{label}' case '{case_id}' is missing required field 'result'.")
        cases.append(
            {
                "id": case_id,
                "inputs": case_map["inputs"],
                "result": case_map["result"],
            }
        )
    return compute, cases


if __name__ == "__main__":
    raise SystemExit(main())
