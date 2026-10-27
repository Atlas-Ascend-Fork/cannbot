# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Canonical publication for self-contained backward and multirank references.

Design note: publication here is deliberately lightweight — NO trusted-receipt
/ anti-tamper machinery (no StableArtifact snapshots, interpreter-bound
receipts, or inode-identity transactional rollback). This module exposes the
canonical public API and artifact schemas while inlining the essentials:

  - dataset identity: `reference_provider/case_gen.dataset_data_sha256` — the
    canonical tensor-data hash (torch-version independent: hashes tensor
    bytes, not torch.save file bytes).
  - runnability receipt: execute the staged model source bytes ONCE with the
    probe args on CPU and record verdict=RUNNABLE + the source sha256. No
    authority envelope, no interpreter binding, no snapshot validation.
  - publication: stage every artifact in `candidate_dir`, then `os.replace`
    each into the workspace (per-file atomic rename on the same filesystem —
    the candidate dir is created inside the workspace). No rollback
    machinery; a mid-bundle failure leaves the already-replaced files in
    place and the error propagates to the caller.

The five canonical O2.5 artifacts (input_gen.py / edge_inputs.pt /
manifest.json / edge_dataset.pt / ref_runnable.json) keep the source schemas,
so mode providers (phase_o25_backward, the multirank extension's
multirank_phase_o25) stay drop-in against
this channel.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import types
from collections.abc import Mapping, Sequence
from pathlib import Path

# reference_provider is a sibling package dir; ensure it's importable
# (case_gen lives there — same bootstrap as phase_o25_backward).
_ORCH_DIR = Path(__file__).resolve().parent
_RP_DIR = _ORCH_DIR.parent / "reference_provider"
if str(_RP_DIR) not in sys.path:
    sys.path.insert(0, str(_RP_DIR))


_CANONICAL_FILENAMES = (
    "input_gen.py",
    "edge_inputs.pt",
    "manifest.json",
    "edge_dataset.pt",
    "ref_runnable.json",
)


class LocalReferenceExecutionError(RuntimeError):
    """The exact active CPU reference failed during Model.forward."""


class LocalReferencePublicationError(RuntimeError):
    """The local receipt could not be prepared or published canonically."""


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _dataset_data_sha256(input_cases: Sequence[Mapping]) -> str:
    """Canonical dataset identity — same hash the source channel computed."""
    from case_gen import dataset_data_sha256

    return dataset_data_sha256([dict(case) for case in input_cases])


def _run_local_active_preflight(
    *,
    source_snapshot: bytes,
    source_display_path: Path,
    import_root: Path,
    positional_args: Sequence[object] = (),
    keyword_args: Mapping[str, object] | None = None,
) -> dict:
    """Execute the exact source bytes once and return a RUNNABLE receipt.

    Compiles and execs the staged model source (NOT the workspace copy — the
    snapshot bytes are what gets published), instantiates `Model`, and runs
    one forward pass with the probe args. A raise propagates to the caller
    (a reference that cannot execute is a publication failure, not a warning).
    The receipt records the source sha256 so consumers can bind the receipt
    to the exact published bytes; no environment-binding envelope is attached
    (execution results are recorded as measured, not as trusted proof).
    """
    import torch

    source_display_path = Path(source_display_path).resolve(strict=False)
    source_sha256 = hashlib.sha256(source_snapshot).hexdigest()

    inserted = str(import_root) not in sys.path
    if inserted:
        sys.path.insert(0, str(import_root))
    module = types.ModuleType(f"_o25_local_preflight_{source_sha256[:16]}")
    module.__file__ = str(source_display_path)
    try:
        exec(
            compile(source_snapshot, str(source_display_path), "exec"),
            module.__dict__,
        )
        model_type = getattr(module, "Model")
        model = model_type()
        forward = getattr(model, "forward", None)
        args = tuple(positional_args)
        kwargs = dict(keyword_args or {})
        output = (
            forward(*args, **kwargs) if callable(forward) else model(*args, **kwargs)
        )
    finally:
        if inserted:
            sys.path.remove(str(import_root))

    return {
        "schema_version": 1,
        "verdict": "RUNNABLE",
        "ref_call_path": "Model.forward (active, local CPU)",
        "source_path": str(source_display_path),
        "source_sha256": source_sha256,
        "probe_returncode": 0,
        "probe_result": {
            "ok": True,
            "error": None,
            "out_repr": repr(type(output).__name__),
            "source_sha256": source_sha256,
            "torch_version": str(torch.__version__),
            "device": "cpu",
        },
        "error": None,
        "recommendation": "PROCEED",
    }


def _write_canonical_artifacts(
    candidate_dir: Path,
    op: str,
    mode: str,
    input_cases: Sequence[Mapping],
    dataset_cases: Sequence[Mapping],
) -> None:
    """Write the five canonical O2.5 artifacts into the staging dir."""
    import torch

    canonical_input_cases = [dict(case) for case in input_cases]
    data_sha256 = _dataset_data_sha256(canonical_input_cases)
    edge_inputs = {
        "op": op,
        "coverage_tier": "sign_off",
        "data_sha256": data_sha256,
        "cases": canonical_input_cases,
    }
    edge_inputs_path = candidate_dir / "edge_inputs.pt"
    torch.save(edge_inputs, edge_inputs_path)
    edge_inputs_sha256 = hashlib.sha256(edge_inputs_path.read_bytes()).hexdigest()

    manifest_cases = []
    for index, case in enumerate(canonical_input_cases):
        manifest_case = {
            "idx": case.get("idx", index),
            "name": case.get("name", f"case_{index}"),
        }
        if "shape" in case:
            manifest_case["shape"] = case["shape"]
        manifest_cases.append(manifest_case)
    (candidate_dir / "manifest.json").write_text(
        _canonical_json(
            {
                "op": op,
                "coverage_tier": "sign_off",
                "n_cases": len(canonical_input_cases),
                "data_sha256": data_sha256,
                "edge_inputs_pt_sha256": edge_inputs_sha256,
                "cases": manifest_cases,
            }
        )
    )
    torch.save(
        {
            "op": op,
            "coverage_tier": "sign_off",
            "data_sha256": data_sha256,
            "reference_source": f"{mode} canonical local active reference",
            "cases": [dict(case) for case in dataset_cases],
        },
        candidate_dir / "edge_dataset.pt",
    )
    (candidate_dir / "input_gen.py").write_text(
        '"""Canonical inputs are regenerated by the mode O2.5 provider."""\n'
        "raise SystemExit(\n"
        f"    'rerun the {mode} O2.5 provider to regenerate this bound dataset'\n"
        ")\n"
    )


def _deferred_probe_receipt(
    source_snapshot: bytes, workspace: Path, source_filename: str, deferred_probe: str
) -> dict:
    """The RUNNABLE receipt for a deferred probe (source-sha256 preserved)."""
    return {
        "schema_version": 1,
        "verdict": "RUNNABLE",
        "ref_call_path": "deferred to the mode's collection run",
        "source_path": str(workspace / source_filename),
        "source_sha256": hashlib.sha256(source_snapshot).hexdigest(),
        "probe_returncode": 0,
        "probe_deferred_reason": deferred_probe,
        "probe_result": None,
        "error": None,
        "recommendation": "PROCEED",
    }


def _publish_artifacts(candidate_dir: Path, workspace: Path, publication_names) -> None:
    """Replace every published filename into the workspace atomically
    (per-file os.replace, publication order preserved)."""
    workspace.mkdir(parents=True, exist_ok=True)
    for filename in publication_names:
        staged = candidate_dir / filename
        if not staged.is_file():
            raise LocalReferencePublicationError(
                f"staged artifact missing before publication: {filename}"
            )
        os.replace(staged, workspace / filename)


def publish_mode_reference(
    *,
    workspace: Path,
    candidate_dir: Path,
    op: str,
    mode: str,
    input_cases: Sequence[Mapping],
    dataset_cases: Sequence[Mapping],
    source_filename: str,
    probe_args: Sequence[object],
    private_filenames: Sequence[str],
    deferred_probe: "str | None" = None,
) -> None:
    """Publish one mode-private truth and the canonical O2.5 artifacts.

    Stages the mode-private source files (already in `candidate_dir`) plus the
    five canonical artifacts, executes the local active preflight against the
    staged source bytes, then replaces every published filename into the
    workspace atomically (per-file `os.replace`, publication order preserved).

    ``deferred_probe`` (reason string) skips the in-orchestrator CPU preflight:
    for references whose execution context this process cannot reproduce
    (e.g. NEEDS_EP_COMM — live HCCL rank groups on the NPU endpoint, already
    exercised by the collection run). The receipt keeps verdict=RUNNABLE with
    ``probe_deferred_reason`` recorded instead of a probe result; the
    source-sha256 binding is preserved.
    """
    if not input_cases or len(input_cases) != len(dataset_cases):
        raise ValueError(
            "mode reference requires equal non-empty input and dataset cases"
        )
    candidate_dir = Path(candidate_dir)
    workspace = Path(workspace)
    source_path = candidate_dir / source_filename
    source_snapshot = source_path.read_bytes()

    _write_canonical_artifacts(candidate_dir, op, mode, input_cases, dataset_cases)

    if deferred_probe is None:
        receipt = _run_local_active_preflight(
            source_snapshot=source_snapshot,
            source_display_path=workspace / source_filename,
            import_root=candidate_dir,
            positional_args=probe_args,
        )
    else:
        receipt = _deferred_probe_receipt(
            source_snapshot, workspace, source_filename, deferred_probe
        )
    (candidate_dir / "ref_runnable.json").write_text(_canonical_json(receipt))

    publication_names = tuple(
        dict.fromkeys((*private_filenames, *_CANONICAL_FILENAMES))
    )
    _publish_artifacts(candidate_dir, workspace, publication_names)


def publish_local_cpu_reference_receipt(
    *,
    workspace: Path,
    source_filename: str = "model.py",
) -> None:
    """Execute the active CPU model and publish its authority receipt.

    Re-runs the runnability preflight against the WORKSPACE copy of the model
    (the currently active reference — e.g. after a worker edited it) with the
    first edge_inputs.pt case's inputs as keyword args, then replaces
    ref_runnable.json in place.
    """
    workspace = Path(workspace)
    source_path = workspace / source_filename
    try:
        source_snapshot = source_path.read_bytes()
        import torch

        inputs_payload = torch.load(
            workspace / "edge_inputs.pt", map_location="cpu", weights_only=False
        )
        if not isinstance(inputs_payload, Mapping):
            raise TypeError("edge_inputs.pt root must be a mapping")
        cases = inputs_payload.get("cases")
        if not isinstance(cases, (list, tuple)) or not cases:
            raise TypeError("edge_inputs.pt requires a non-empty cases list")
        first_case = cases[0]
        if not isinstance(first_case, Mapping):
            raise TypeError("edge_inputs.pt case 0 must be a mapping")
        keyword_args = first_case.get("inputs")
        if not isinstance(keyword_args, Mapping):
            raise TypeError("edge_inputs.pt case 0 inputs must be a mapping")
    except Exception as exc:
        raise LocalReferencePublicationError(
            f"cannot prepare local active preflight: {exc}"
        ) from exc

    try:
        receipt = _run_local_active_preflight(
            source_snapshot=source_snapshot,
            source_display_path=source_path,
            import_root=workspace,
            keyword_args=keyword_args,
        )
    except Exception as exc:
        raise LocalReferenceExecutionError(
            f"active Model.forward failed: {exc}"
        ) from exc
    candidate_dir = Path(tempfile.mkdtemp(prefix=".o25_local_receipt.", dir=workspace))
    try:
        (candidate_dir / "ref_runnable.json").write_text(_canonical_json(receipt))
        staged = candidate_dir / "ref_runnable.json"
        try:
            os.replace(staged, workspace / "ref_runnable.json")
        except Exception as exc:
            raise LocalReferencePublicationError(
                f"canonical local receipt publication failed: {exc}"
            ) from exc
    finally:
        shutil.rmtree(candidate_dir, ignore_errors=True)
