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
from typing import Any, cast

from shared.env import read_bool_env
from shared.managed_integrity import (
    append_evidence_batch,
    operator_sha256 as operator_artifact_sha256,
    validate_integrity,
)
from state_manage.state_machine import (
    PHASE_DEEP_ANALYSIS,
    PHASE_ROUND_ACTIVE,
    load_state,
    parse_round_number,
    require_rounds_dict,
    write_state,
)
from state_manage import retrieval_bridge

RECOMMENDATIONS_ENV = "HELIX_OPTIMIZE_RECOMMEND_PATTERNS"
BACKEND_SKILL_DIRS = (".codex", ".claude", ".agents", ".opencode", ".pi", ".openhands", ".trae")


def _workflow_language(state_path: Path) -> str:
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if not state_path.exists():
            return "triton"
        raise ValueError(f"invalid workflow state: {state_path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("workflow state must be an object")
    language = cast(dict[str, object], raw).get("language", "triton")
    if not isinstance(language, str) or not language.strip():
        raise ValueError("workflow state language must be a non-empty string")
    return language.strip().lower()


def knowledge_dir(state_path: Path) -> Path:
    skill_name = f"{_workflow_language(state_path)}-npu-optimize-knowledge"
    workspace = state_path.parent.parent
    for backend in BACKEND_SKILL_DIRS:
        candidate = workspace / backend / "skills" / skill_name
        if (candidate / "references" / "patterns").is_dir():
            return candidate
    repository_root = Path(__file__).resolve().parents[5]
    fallback = repository_root / "skills" / _workflow_language(state_path) / skill_name
    if (fallback / "references" / "patterns").is_dir():
        return fallback
    raise ValueError(f"staged {skill_name} skill is unavailable")


def _recommendations_enabled() -> bool:
    return read_bool_env(RECOMMENDATIONS_ENV)


def _recorded_recommendations(
    recommendations: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Slim entries for workflow state and the durable record: id + matched symptoms."""
    return [
        {
            "id": recommendation["id"],
            "matched_symptoms": recommendation["matched_symptoms"],
        }
        for recommendation in recommendations
    ]


def _skill_recommendations(
    state_path: Path,
    symptoms: list[str],
    history: dict[str, object],
    operator_path: Path,
    round_path: Path,
) -> list[dict[str, object]]:
    """Run the pattern-retrieval skill; any problem yields no recommendations.

    Mechanism-blind: one uniform invocation carries every input the skill
    may need (symptoms, history, operator source, round analysis, contract,
    pattern cards). The submission contract is primary: a missing skill or a
    retrieval failure never fails submit-deep-analysis and adds nothing to
    its output.
    """
    workspace = state_path.parent.parent.resolve()
    skill_dir = retrieval_bridge.find_staged_retrieval_skill(workspace)
    if skill_dir is None:
        return []
    try:
        knowledge = knowledge_dir(state_path)
        payload = retrieval_bridge.run_retrieval(
            skill_dir,
            symptoms=symptoms,
            exclude=sorted(history),
            code=operator_path,
            analysis=round_path / "perf-analysis.md",
            contract=knowledge / "references" / "symptom-contract.json",
        )
        return retrieval_bridge.map_results(payload)
    except ValueError:
        return []


def build_parser(*, prog_name: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog_name or Path(__file__).name)
    subparsers = parser.add_subparsers(dest="command", required=True)

    submit = subparsers.add_parser("submit-deep-analysis")
    submit.add_argument("--round-dir", required=True)
    submit.add_argument("--profile-manifest", required=True)
    submit.add_argument("--ir-manifest", required=True)
    submit.add_argument(
        "--symptom",
        action="append",
        required=True,
        help="Symptom ID from the staged knowledge skill; repeat up to five times.",
    )
    return parser


def _workflow_failure_guideline(message: str) -> str:
    if "workflow state is not available" in message or ".helix/state.json" in message:
        return (
            "Optimize workflow state is unavailable. Run the staged "
            "`triton-npu-optimize-state` skill's `start-round` subcommand first, then "
            "complete the required profile and IR analysis before retrying "
            "`submit-deep-analysis`."
        )
    if "requires workflow phase deep_analysis" in message:
        return (
            "This round is not waiting for deep analysis. Use `start-round` to open a "
            "deep-analysis round before submitting profile and IR manifests."
        )
    if "manifest" in message or "profiler output" in message or "IR artifact" in message:
        return (
            "Deep-analysis artifacts are incomplete or do not match this round. Run "
            "`profile-bench` and `capture-ir` for the same candidate and case, then "
            "retry `submit-deep-analysis` with both manifests."
        )
    if "candidate" in message or "benchmark identity" in message or "case_id" in message:
        return (
            "The submitted analysis does not match the active round candidate or benchmark. "
            "Repeat profiling and IR capture for the current candidate and selected case, "
            "then retry `submit-deep-analysis`."
        )
    if "workflow state" in message:
        return (
            "The temporary optimize workflow state is invalid. Stop this attempt and restart "
            "the optimize session so the runner-managed state can be rebuilt cleanly."
        )
    return (
        "Deep-analysis submission could not be applied. Repair the reported issue, rerun "
        "profile and IR analysis if needed, and retry `submit-deep-analysis`."
    )


def submit_deep_analysis(
    state_path: Path,
    round_dir: str,
    *,
    profile_manifest: Path,
    ir_manifest: Path,
    symptoms: list[str],
) -> dict[str, object]:
    payload = load_state(state_path)
    round_entry = _require_deep_analysis_round_entry(payload, round_dir)
    # Symptom validity is owned by the retrieval skill: its script validates
    # the IDs when recommendations run and reports problems through the
    # submit output, so the submission itself stays thin.
    normalized_symptoms = [item.strip() for item in symptoms]
    deep_entry, round_path, operator_path, operator_hash = _resolve_deep_analysis_candidate(
        state_path, round_entry, round_dir
    )
    profile, ir = _validated_deep_manifest_pair(
        state_path, round_path=round_path, operator_path=operator_path,
        operator_hash=operator_hash, profile_manifest=profile_manifest, ir_manifest=ir_manifest,
    )
    profile_case_id = str(profile["case_id"])
    recommendation_history, recommendations = _gather_pattern_recommendations(
        state_path, payload, normalized_symptoms, round_path, operator_path
    )
    profile_record, ir_record = _record_deep_analysis_evidence(
        state_path, round_dir, profile_manifest=profile_manifest, ir_manifest=ir_manifest,
        profile=profile, ir=ir, operator_path=operator_path,
    )
    _finalize_deep_analysis(
        state_path, payload, round_entry, deep_entry, round_path=round_path,
        symptoms=normalized_symptoms, recommendations=recommendations,
        recommendation_history=recommendation_history, profile=profile, ir=ir,
        profile_record=profile_record, ir_record=ir_record, case_id=profile_case_id,
    )
    return _deep_analysis_result(
        round_entry, round_dir=round_dir, case_id=profile_case_id,
        symptoms=normalized_symptoms, recommendations=recommendations,
    )


def _require_deep_analysis_round_entry(payload: dict[str, object], round_dir: str) -> dict[str, object]:
    if payload.get("phase") != PHASE_DEEP_ANALYSIS:
        raise ValueError("submit-deep-analysis requires workflow phase deep_analysis")
    round_number = parse_round_number(round_dir)
    if payload.get("current_round") != round_number:
        raise ValueError("submit-deep-analysis round does not match current workflow round")
    rounds = require_rounds_dict(payload)
    round_entry_obj = rounds.get(str(round_number))
    if not isinstance(round_entry_obj, dict):
        raise ValueError(f"missing workflow state entry for {round_dir}")
    return cast(dict[str, object], round_entry_obj)


def _resolve_deep_analysis_candidate(
    state_path: Path,
    round_entry: dict[str, object],
    round_dir: str,
) -> tuple[dict[str, object], Path, Path, str]:
    """Return the deep-analysis entry, round path, candidate path, and candidate hash."""
    if round_entry.get("status") != "deep_analysis_required":
        raise ValueError("submit-deep-analysis requires a pending deep-analysis round")
    deep_entry_obj = round_entry.get("deep_analysis")
    if not isinstance(deep_entry_obj, dict):
        raise ValueError("workflow state deep-analysis entry is missing")
    deep_entry = cast(dict[str, object], deep_entry_obj)
    workspace = state_path.parent.parent.resolve()
    round_path = (workspace / round_dir).resolve()
    if not round_path.is_dir():
        raise ValueError(f"round directory does not exist: {round_path}")
    operator_path = (workspace / str(deep_entry.get("operator_file"))).resolve()
    operator_hash = deep_entry.get("operator_sha256")
    if not operator_path.is_file() or not isinstance(operator_hash, str):
        raise ValueError("deep-analysis candidate snapshot is missing")
    if operator_artifact_sha256(operator_path) != operator_hash:
        raise ValueError("deep-analysis candidate changed after start-round")
    return deep_entry, round_path, operator_path, operator_hash


def _validated_deep_manifest_pair(
    state_path: Path,
    *,
    round_path: Path,
    operator_path: Path,
    operator_hash: str,
    profile_manifest: Path,
    ir_manifest: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    integrity = validate_integrity(state_path)
    bench_file = Path(str(integrity["bench_file"])).resolve()
    bench_sha256 = str(integrity["bench_sha256"])
    profile = _validate_deep_manifest(
        profile_manifest,
        artifact_root=round_path / "profile",
        expected_kind="profile",
        operator_path=operator_path,
        operator_sha256=operator_hash,
        bench_file=bench_file,
        bench_sha256=bench_sha256,
    )
    ir = _validate_deep_manifest(
        ir_manifest,
        artifact_root=round_path / "ir",
        expected_kind="ir",
        operator_path=operator_path,
        operator_sha256=operator_hash,
        bench_file=bench_file,
        bench_sha256=bench_sha256,
    )
    if str(profile["case_id"]) != str(ir["case_id"]):
        raise ValueError("profile and IR manifests must select the same case_id")
    return profile, ir


def _gather_pattern_recommendations(
    state_path: Path,
    payload: dict[str, object],
    normalized_symptoms: list[str],
    round_path: Path,
    operator_path: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Return the recommendation history and this submission's recommendations."""
    recommendation_history_obj = payload.get("pattern_recommendations", {})
    if not isinstance(recommendation_history_obj, dict):
        raise ValueError("workflow state pattern_recommendations must be an object")
    recommendation_history = cast(dict[str, object], recommendation_history_obj)
    _merge_completed_recommendation_history(
        round_path.parent, recommendation_history, exclude_round=round_path
    )
    if _recommendations_enabled():
        recommendations = _skill_recommendations(
            state_path,
            normalized_symptoms,
            recommendation_history,
            operator_path,
            round_path,
        )
    else:
        recommendations = []
    return recommendation_history, recommendations


def _record_deep_analysis_evidence(
    state_path: Path,
    round_dir: str,
    *,
    profile_manifest: Path,
    ir_manifest: Path,
    profile: dict[str, object],
    ir: dict[str, object],
    operator_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    records = append_evidence_batch(
        state_path,
        round_name=round_dir,
        records=[
            {
                "command": "profile-bench",
                "mode": "deep-analysis",
                "artifact_kind": "profile_manifest",
                "artifact_path": profile_manifest.resolve(),
                "operator_path": operator_path,
                "remote": profile["remote"],
                "metadata": {
                    "case_id": str(profile["case_id"]),
                    "artifact_dir": str(profile["artifact_dir"]),
                },
            },
            {
                "command": "capture-ir",
                "mode": "deep-analysis",
                "artifact_kind": "ir_manifest",
                "artifact_path": ir_manifest.resolve(),
                "operator_path": operator_path,
                "remote": ir["remote"],
                "metadata": {
                    "case_id": str(ir["case_id"]),
                    "artifact_dir": str(ir["artifact_dir"]),
                },
            },
        ],
    )
    profile_record = next(record for record in records if record["artifact_kind"] == "profile_manifest")
    ir_record = next(record for record in records if record["artifact_kind"] == "ir_manifest")
    return profile_record, ir_record


def _finalize_deep_analysis(
    state_path: Path,
    payload: dict[str, object],
    round_entry: dict[str, object],
    deep_entry: dict[str, object],
    *,
    round_path: Path,
    symptoms: list[str],
    recommendations: list[dict[str, object]],
    recommendation_history: dict[str, object],
    profile: dict[str, object],
    ir: dict[str, object],
    profile_record: dict[str, Any],
    ir_record: dict[str, Any],
    case_id: str,
) -> None:
    """Record the submission, advance workflow state, and persist the durable record."""
    deep_entry["profile_evidence"] = [
        {"record_id": profile_record["record_id"], "artifact_dir": str(profile["artifact_dir"])}
    ]
    deep_entry["ir_evidence"] = [
        {"record_id": ir_record["record_id"], "artifact_dir": str(ir["artifact_dir"])}
    ]
    deep_entry["selected_case_id"] = case_id
    recorded = _recorded_recommendations(recommendations) if _recommendations_enabled() else []
    deep_entry["symptoms"] = symptoms
    deep_entry["recommendations"] = recorded
    durable_record = {
        "symptoms": symptoms,
        "recommendations": recorded,
    }
    if recommendations:
        for recommendation in recommendations:
            recommendation_history[str(recommendation["id"])] = {
                "id": recommendation["id"],
                "matched_symptoms": recommendation["matched_symptoms"],
            }
    try:
        round_path.joinpath("deep-analysis.json").write_text(
            json.dumps(durable_record, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ValueError(f"deep-analysis durable record could not be written: {exc}") from exc
    payload["pattern_recommendations"] = recommendation_history
    round_entry["deep_analysis"] = deep_entry
    round_entry["status"] = "active"
    payload["phase"] = PHASE_ROUND_ACTIVE
    write_state(state_path, payload)


def _deep_analysis_result(
    round_entry: dict[str, object],
    *,
    round_dir: str,
    case_id: str,
    symptoms: list[str],
    recommendations: list[dict[str, object]],
) -> dict[str, object]:
    strategy_state = round_entry.get("strategy_state")
    scope_review_required = (
        isinstance(strategy_state, dict)
        and cast(dict[str, object], strategy_state).get("round_strategy") == "plateau_review"
    )
    return {
        "status": "active",
        "round": round_dir,
        "case_id": case_id,
        "scope_review_required": scope_review_required,
        "symptoms": symptoms,
        "pattern_recommendations": recommendations if _recommendations_enabled() else [],
    }


def _merge_completed_recommendation_history(
    workspace: Path, history: dict[str, object], *, exclude_round: Path
) -> None:
    """Recover recommendations from prior rounds' durable submissions.

    The current round's record is excluded: it is written before workflow
    state advances, so an interrupted submission (record written, state not
    advanced) is retried from scratch and never suppresses its own
    recommendations. Prior round records keep delivered recommendations from
    repeating after a workflow state rebuild.
    """
    for record_path in sorted(workspace.glob("opt-round-*/deep-analysis.json")):
        if record_path.parent.resolve() == exclude_round.resolve():
            continue
        try:
            raw = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        typed_raw = cast(dict[str, object], raw)
        recommendations = typed_raw.get("recommendations")
        if not isinstance(recommendations, list):
            continue
        for item in cast(list[object], recommendations):
            if not isinstance(item, dict):
                continue
            typed_item = cast(dict[str, object], item)
            identifier = typed_item.get("id")
            if isinstance(identifier, str) and identifier:
                history.setdefault(
                    identifier,
                    {
                        "id": identifier,
                        "matched_symptoms": typed_item.get("matched_symptoms", []),
                    },
                )


def _validate_ir_capture_layout(data: dict[str, object], artifact_dir: Path) -> None:
    """Validate an IR archive against the manifest's kernel-bundle records.

    New captures index every kernel variant in the manifest's ``kernels`` array;
    each record's declared paths must exist with the declared kind (directory or
    file). Manifests without ``kernels`` come from pre-bundle captures and are
    validated against the historical flat layout.
    """
    if "kernels" not in data:
        if not all(
            (artifact_dir / required_name).exists()
            for required_name in ("triton_dump", "bishengir_stages", "pass-order.json")
        ):
            raise ValueError("IR artifact is missing required capture files")
        return
    kernels_obj = data["kernels"]
    if not isinstance(kernels_obj, list) or not kernels_obj:
        raise ValueError("IR manifest kernels must be a non-empty array")
    kernels = cast(list[object], kernels_obj)
    for entry in kernels:
        if not isinstance(entry, dict):
            raise ValueError("IR manifest kernel records must be objects")
        record = cast(dict[str, object], entry)
        kernel_key = record.get("kernel_key")
        if not isinstance(kernel_key, str) or not kernel_key:
            raise ValueError("IR manifest kernel record is missing kernel_key")
        for field, must_be_dir in (
            ("triton_dump_dir", True),
            ("stage_dir", True),
            ("pass_order_file", False),
        ):
            raw_path = record.get(field)
            if not isinstance(raw_path, str) or not raw_path:
                raise ValueError(
                    f"IR manifest kernel '{kernel_key}' is missing {field}"
                )
            path = artifact_dir / raw_path
            exists = path.is_dir() if must_be_dir else path.is_file()
            if not exists:
                raise ValueError(
                    f"IR artifact is missing required capture files for kernel '{kernel_key}'"
                )


def _validate_deep_manifest(
    manifest_path: Path,
    *,
    artifact_root: Path,
    expected_kind: str,
    operator_path: Path,
    operator_sha256: str,
    bench_file: Path,
    bench_sha256: str,
) -> dict[str, object]:
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {expected_kind} manifest: {manifest_path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{expected_kind} manifest must be a JSON object")
    data = cast(dict[str, object], raw)
    required = ("case_id", "operator_file", "operator_sha256", "bench_file", "bench_sha256", "artifact_dir")
    if any(not isinstance(data.get(key), str) or not str(data[key]) for key in required):
        raise ValueError(f"{expected_kind} manifest is missing required identity fields")
    if not isinstance(data.get("remote"), bool):
        raise ValueError(f"{expected_kind} manifest remote must be a boolean")
    artifact_dir = Path(str(data["artifact_dir"])).expanduser().resolve()
    try:
        artifact_dir.relative_to(artifact_root.resolve())
    except ValueError as exc:
        raise ValueError(f"{expected_kind} artifact is outside the current round") from exc
    if artifact_dir != manifest_path.resolve().parent:
        raise ValueError(f"{expected_kind} manifest artifact_dir does not match its parent")
    if not artifact_dir.is_dir():
        raise ValueError(f"{expected_kind} artifact directory does not exist")
    if expected_kind == "profile" and not any(artifact_dir.glob("mindstudio_profiler_output/op_statistic_*.csv")):
        raise ValueError("profile artifact is missing profiler output")
    if expected_kind == "ir":
        _validate_ir_capture_layout(data, artifact_dir)
    if Path(str(data["operator_file"])).resolve() != operator_path:
        raise ValueError(f"{expected_kind} manifest operator_file does not match the round candidate")
    if data["operator_sha256"] != operator_sha256:
        raise ValueError(f"{expected_kind} manifest operator hash does not match the round candidate")
    if Path(str(data["bench_file"])).resolve() != bench_file or data["bench_sha256"] != bench_sha256:
        raise ValueError(f"{expected_kind} manifest benchmark identity does not match the canonical benchmark")
    return {
        "case_id": str(data["case_id"]),
        "artifact_dir": str(artifact_dir),
        "remote": data["remote"],
    }


def _print_failure(message: str) -> int:
    print(
        json.dumps(
            {
                "status": "fail",
                "issues": [message],
                "guideline": _workflow_failure_guideline(message),
            },
            ensure_ascii=True,
        )
    )
    return 1


def _success_guideline(round_name: str, *, scope_review_required: bool) -> str:
    if scope_review_required:
        return (
            f"Deep analysis for {round_name} is accepted. The round is now active "
            "but remains in plateau review: you must not edit the operator yet. "
            "Reassess the complete selected optimization scope, then use "
            "`set-current-round-state` to record `structural_change` or "
            "evidence-backed `focused_tuning` before editing."
        )
    return (
        f"Deep analysis for {round_name} is accepted. The round is now active; "
        "you may edit the candidate and continue with canonical validation."
    )


def main(argv: list[str] | None = None, *, prog_name: str | None = None) -> int:
    args = build_parser(prog_name=prog_name).parse_args(argv)
    round_dir = Path(args.round_dir).expanduser().resolve()
    profile_manifest = Path(args.profile_manifest).expanduser().resolve()
    ir_manifest = Path(args.ir_manifest).expanduser().resolve()
    try:
        state_path = round_dir.parent / ".helix" / "state.json"
        if not state_path.exists():
            raise RuntimeError("optimize workflow state is not available")
        workflow_result = submit_deep_analysis(
            state_path,
            round_dir.name,
            profile_manifest=profile_manifest,
            ir_manifest=ir_manifest,
            symptoms=list(args.symptom),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return _print_failure(str(exc))

    printed: dict[str, object] = {
        "status": "pass",
        "round": workflow_result["round"],
        "case_id": workflow_result["case_id"],
        "symptoms": workflow_result["symptoms"],
        "guideline": _success_guideline(
            round_dir.name,
            scope_review_required=workflow_result.get("scope_review_required") is True,
        ),
    }
    if workflow_result.get("pattern_recommendations"):
        printed["pattern_recommendations"] = workflow_result["pattern_recommendations"]
    print(json.dumps(printed, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
