# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""O2.5 multirank reference provision (task-generated form).

The multirank input is the KernelBench-style task .py + same-stem sidecar
(single-card npubench format), statically converted at the CLI entry into
the internal spec.py (task_to_spec): the task's Model is the reference
implementation, get_input_groups(rank=..., world_size=...) is the single
input generator (the harness materializes nothing), and the sidecar's
cases declare their world_size. When the task sets NEEDS_EP_COMM, the
collector runs the reference as one subprocess per rank with a live HCCL
group (hcomm handle passed to forward as a trailing comm keyword).

The golden keeps the COLLECTED per-rank shares verbatim (inputs never
re-derived at verify time); the cache key covers the frozen task+sidecar
bytes via task_sha256. Provision is pure CPU here — the reference itself
executes on the candidate endpoint through the subprocess collector.
"""

from __future__ import annotations

import hashlib
import logging
import importlib.util
import json
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, Any, Optional

log = logging.getLogger(__name__)


class TaskCaseExpansion(NamedTuple):
    """_expand_case_records_task result: golden records, scoreable/skipped
    counts, case index, loud-failure report and the kernel input order.
    """

    records: "list | None"
    n_ok: int
    n_skipped: int
    case_idx: int
    error: "object | None"
    kernel_input_order: "list | None"


# The shared reference_provider helpers (backward_input_gen) live in the
# harness reference_provider/ tree next to the orchestrator package — same
# bootstrap as phase_o25_backward. This module now lives under
# plugins/multirank/, so resolve up to the orchestrator dir first.
_ORCH_DIR = Path(__file__).resolve().parents[2]  # .../orchestrator/
_RP_DIR = _ORCH_DIR.parent / "reference_provider"
if str(_RP_DIR) not in sys.path:
    sys.path.insert(0, str(_RP_DIR))

_VALID_VERDICTS = (
    "READY",  # golden/ per-case tree + model.py + ref_runnable.json produced
    "SPEC_MISSING",  # spec path absent / unreadable
    "SPEC_INVALID",  # spec fails the SPEC contract
    "COMPUTE_FAILED",  # shard/expected raised
    "REF_UNAVAILABLE",  # declared truth tier infeasible (endpoint missing / provider unwired)
)


@dataclass
class MultirankRefReport:
    verdict: str
    summary: str = ""
    op: str = ""
    world_sizes: list = field(default_factory=list)
    n_cases: int = 0
    n_ok: int = 0
    n_skipped: int = 0
    errors: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)


_DTYPE_BY_NAME = None


def case_slug(name: str) -> str:
    """`case0@ws8[randn]` → `case0_ws8_randn` — filesystem-safe case identity.

    Used as the per-case golden file stem (`golden/<slug>.pt`) and the
    per-case rank-log dir name (`.run/<slug>/`).
    """
    return re.sub(r"[^0-9A-Za-z_]+", "_", str(name)).strip("_")


def load_golden_manifest(workspace: Path) -> dict:
    """The provision-published golden index (`golden/manifest.json`).

    Returns the parsed manifest dict (with a `cases` list of per-case records:
    idx/name/case/world_size/profile/file/sha256), or {} when absent or
    unreadable — callers treat empty as "no provisioned campaign" and fail
    loud.
    """
    try:
        m = json.loads((Path(workspace) / "golden" / "manifest.json").read_text())
        return m if isinstance(m, dict) and m.get("cases") else {}
    except Exception:
        return {}


def _torch_dtype(name: str):
    global _DTYPE_BY_NAME
    import torch

    if _DTYPE_BY_NAME is None:
        _DTYPE_BY_NAME = {
            "float32": torch.float32,
            "float": torch.float32,
            "fp32": torch.float32,
            "float16": torch.float16,
            "half": torch.float16,
            "fp16": torch.float16,
            "bfloat16": torch.bfloat16,
            "bf16": torch.bfloat16,
            "float64": torch.float64,
            "double": torch.float64,
        }
    if name not in _DTYPE_BY_NAME:
        raise ValueError(
            f"unsupported dtype name {name!r} (known: {sorted(_DTYPE_BY_NAME)})"
        )
    return _DTYPE_BY_NAME[name]


def _state_declared_spec(state_file: Path) -> "Path | None":
    """The spec path declared in .opgen_state.json['spec'], if it exists."""
    try:
        stated = json.loads(state_file.read_text()).get("spec")
        if stated and Path(stated).is_file():
            return Path(stated)
    except (OSError, ValueError):
        pass
    return None


def resolve_spec_path(workspace: Path, op: str) -> Optional[Path]:
    """Locate the multirank op spec for this workspace.

    Order:
      1. `.opgen_state.json['spec']` (explicit absolute path written by
         `_cmd_multirank` — normally the canonical location itself).
      2. Canonical location `<op_workspace>/spec.py`. The cold-start
         reset is an allowlist-delete (state_patterns only), so the spec
         survives op-workspace cold-start in place, same as model.py.
    Returns None if none exist.
    """
    workspace = Path(workspace)
    state_file = workspace / ".opgen_state.json"
    if state_file.is_file():
        declared = _state_declared_spec(state_file)
        if declared is not None:
            return declared
    canonical = workspace / "spec.py"
    if canonical.is_file():
        return canonical
    return None


def _load_spec(spec_path: Path):
    # Read + compile the spec bytes directly — SourceFileLoader's timestamp-
    # based .pyc validation trusts a stale bytecode cache when the spec is
    # edited and re-loaded within the same mtime second, while the golden's
    # cache key (spec_hash) reads the NEW bytes. Loading the exact current
    # bytes keeps the two content-addressed views consistent.
    name = f"_spec_{abs(hash(str(spec_path)))}"
    mod = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(name, loader=None)
    )
    mod.__file__ = str(spec_path)
    try:
        code = compile(spec_path.read_bytes(), str(spec_path), "exec")
        exec(code, mod.__dict__)
    except Exception as e:
        raise ImportError(f"cannot load spec module from {spec_path}: {e}") from e
    return mod


def _is_positive_int(n: int) -> bool:
    return isinstance(n, int) and not isinstance(n, bool) and n >= 1


def declared_case_world_sizes(workspace: Path, op: str | None = None) -> list[int]:
    """Distinct case world_sizes declared in the multirank spec (sorted ascending).

    world_size is a per-case field — the verification campaign is
    case-controlled, so the spec is the single authoritative source. NOT a
    materialized copy in ref_runnable.json: that receipt is published by the
    O2.5 channel (publish_mode_reference) and carries only runnability fields
    (verdict / source_sha256 / probe result), never campaign data, so it has
    no world_sizes to read. Returns [] when the spec is absent/unreadable;
    callers treat empty as "no declared groups".
    """
    workspace = Path(workspace)
    try:
        spec_path = resolve_spec_path(workspace, op or workspace.name)
        if spec_path is None:
            return []
        mod = _load_spec(spec_path)
        spec = getattr(mod, "SPEC", {})
        cases = spec.get("cases") or []
        default_ws = spec.get("world_sizes")
        ws: set = set()
        for c in cases:
            if not isinstance(c, dict):
                continue
            cws = c.get("world_size", default_ws)
            if isinstance(cws, list):
                ws.update(
                    w
                    for w in cws
                    if isinstance(w, int) and not isinstance(w, bool) and w >= 1
                )
            elif isinstance(cws, int) and not isinstance(cws, bool) and cws >= 1:
                ws.add(cws)
        return sorted(ws)
    except Exception:
        return []


def _validate_spec_fields(spec, mod, errors) -> None:
    """Top-level SPEC field checks: op_name, top-level world_size
    rejection, inputs, optional module callables, input_constrain,
    truth tier. Appends to errors."""
    op_name = spec.get("op_name")
    if not isinstance(op_name, str) or not op_name:
        errors.append("SPEC['op_name'] must be a non-empty str")

    if "world_size" in spec:
        errors.append(
            "SPEC['world_size'] is not a valid top-level field — declare "
            "'world_size' inside each entry of SPEC['cases']"
        )

    inputs = spec.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        errors.append(
            "SPEC['inputs'] must be the sidecar's non-empty "
            "descriptor list (task-generated form)"
        )
    elif not any(isinstance(d, dict) and d.get("type") == "tensor" for d in inputs):
        errors.append(
            "SPEC['inputs'] must declare at least one "
            "tensor input (task-generated form)"
        )

    # Optional MODULE-LEVEL callables (how multirank_verify.py resolves them —
    # getattr on the spec module; fail-loud when present-but-broken):
    # perf_baseline  — non-fused NPU perf reference (verify --perf ratio)
    # t2_competitor  — composed stock CANN path run per case for the T2 parity
    #                  arm of the precision judge (absent → T2 N/A_ALL_T1)
    for opt in ("perf_baseline", "t2_competitor"):
        fn = getattr(mod, opt, None)
        if fn is not None and not callable(fn):
            errors.append(
                f"spec module attribute {opt!r} must be a callable "
                f"when declared; got {type(fn).__name__}"
            )

    # Optional constraint hook: input_constrain (inputs: dict) -> dict runs in
    # the FULL domain right after materialization — the sanctioned home for
    # constrained/derived inputs (quantized weights + scales, top-k indices)
    # that the random materializer cannot express. Contract: output must be a
    # SUPERSET of the declared inputs (free variables preserved), it must be a
    # rank-independent pure function (full-domain, commutes with slicing), and
    # the insertion order of its added keys defines the full-domain input
    # ordering. Absent → the pipeline behaves as if the hook did not exist.
    constrain = spec.get("input_constrain")
    if constrain is not None and not callable(constrain):
        errors.append(
            "SPEC['input_constrain'] must be a callable "
            "(inputs: dict) -> dict when declared; got "
            f"{type(constrain).__name__}"
        )

    # Optional truth-tier declaration: SPEC['truth'] names which golden
    # provider this spec targets. Absent → a3_live (the default). The
    # spec is the durable declaration point (the CLI --reference-source
    # flag must agree with it — same case-controlled principle as
    # world_size): a tier change is a spec-byte change, so the golden cache
    # key (_spec_content_hash) covers it with no extra mixing.
    truth = spec.get("truth")
    if truth is not None:
        _executable = ("a3_live", "npubench")
        if not isinstance(truth, str) or truth not in _executable:
            errors.append(
                "SPEC['truth'] must be one of "
                + "/".join(_executable)
                + f" when declared; got {truth!r}"
            )


def _case_world_sizes(c: dict, i: int, default_ws, errors) -> "set[int] | None":
    """One case's declared world sizes; None = invalid (error appended)."""
    cws = c.get("world_size", default_ws)
    if isinstance(cws, list):
        if not cws or not all(_is_positive_int(w) for w in cws):
            errors.append(
                f"SPEC['cases'][{i}]['world_size'] must be a "
                f"positive int or a non-empty list of positive ints; "
                f"got {cws!r}"
            )
            return None
        return set(cws)
    if _is_positive_int(cws if isinstance(cws, int) else 0):
        return {cws}
    if cws is None:
        errors.append(
            f"SPEC['cases'][{i}] declares no 'world_size' and the "
            f"spec has no top-level 'world_sizes' default — exactly one "
            f"of the two must provide it"
        )
    else:
        errors.append(
            f"SPEC['cases'][{i}]['world_size'] must be a positive "
            f"int or a non-empty list of positive ints; got {cws!r}"
        )
    return None


def _validate_spec_cases(spec, errors) -> set:
    """SPEC cases / per-case world_size / world_sizes-default
    validation; returns the set of distinct declared world sizes."""
    cases = spec.get("cases")
    ws_set: set[int] = set()
    if not isinstance(cases, list) or not cases:
        errors.append(
            "SPEC['cases'] must be a non-empty list — each case may "
            "declare 'world_size' (int or list of ints); without it the "
            "top-level 'world_sizes' default applies"
        )
        return ws_set
    default_ws = spec.get("world_sizes")
    ws_default_valid = (
        isinstance(default_ws, list)
        and bool(default_ws)
        and all(_is_positive_int(w) for w in default_ws)
    )
    if default_ws is not None and not ws_default_valid:
        errors.append(
            "SPEC['world_sizes'] (global default) must be a non-empty "
            "list of positive ints"
        )
    for i, c in enumerate(cases):
        if not isinstance(c, dict):
            errors.append(f"SPEC['cases'][{i}] must be a dict")
            continue
        ws = _case_world_sizes(c, i, default_ws, errors)
        if ws:
            ws_set.update(ws)
    return ws_set


def _validate_spec(mod, op: str) -> tuple[Any, dict, list[int], list[str]]:
    """Validate the spec module against the SPEC contract.

    world_size is a PER-CASE field (each case declares the rank count it
    verifies at); there is no top-level world_size. Returns
    (spec_dict, sorted distinct world_sizes, errors). errors non-empty →
    SPEC_INVALID.
    """
    errors: list[str] = []
    spec = getattr(mod, "SPEC", None)
    if not isinstance(spec, dict):
        return {}, [], ["spec must define a `SPEC` dict"]

    _validate_spec_fields(spec, mod, errors)
    ws_set = _validate_spec_cases(spec, errors)
    return spec, sorted(ws_set), errors


def _generate_model_py(op: str, spec: dict, input_order: list) -> str:
    """model.py for a task-generated spec: wraps the task's own Model at the
    single-process degenerate (rank=0, world_size=1)."""
    return f'''"""Canonical multirank reference for {op} (O2.5 generated — DO NOT EDIT).

Task-generated spec: the reference is the task's own Model (KernelBench
form), invoked at rank=0/world_size=1 — the single-process degenerate.
"""
import os
import sys

import torch.nn as nn

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from task import Model as _TaskModel  # noqa: E402
from task import get_init_inputs as _task_init  # noqa: E402
from task import get_input_groups as _task_inputs  # noqa: E402

_INPUT_ORDER = {input_order!r}


class Model(nn.Module):
    """multirank single-process reference for {op} (task-wrapped)."""

    def __init__(self):
        super().__init__()
        self._inner = _TaskModel(*_task_init(rank=0, world_size=1))

    def forward(self, *args):
        group = _task_inputs(rank=0, world_size=1)
        if len(group) != len(_INPUT_ORDER):
            raise ValueError(
                f"task input group has {{len(group)}} entries, "
                f"expected {{len(_INPUT_ORDER)}}")
        out = self._inner(*group)
        if isinstance(out, (tuple, list)):
            return out
        return (out,)


def get_init_inputs():
    return []
'''


def _write_golden_cases(torch, golden_dir, op, output_records) -> list:
    """One golden/<slug>.pt per expanded case — identity + full_inputs
    + canonical_outputs (derived form) or the stored per-rank shares
    (task-generated form). Rank shares are NOT duplicated in the derived
    form: multirank_verify shards the full tensors at launch. Each case
    group loads only its own file (fault isolation). Returns the
    manifest's cases list."""
    golden_cases = []
    for record in output_records:
        slug = case_slug(record["name"])
        if "full_inputs" in record:
            payload = {
                "op": op,
                "idx": record["idx"],
                "name": record["name"],
                "case": record["case"],
                "world_size": record["world_size"],
                "profile": record["profile"],
                "shape": record["shape"],
                "full_inputs": record["full_inputs"],
                "canonical_outputs": record["canonical_outputs"],
            }
        else:
            # task-generated: per-rank shares stored at collection time
            payload = {
                "op": op,
                "idx": record["idx"],
                "name": record["name"],
                "case": record["case"],
                "world_size": record["world_size"],
                "profile": record["profile"],
                "kernel_input_order": record["kernel_input_order"],
                "ranks": record["ranks"],
            }
        case_file = golden_dir / f"{slug}.pt"
        torch.save(payload, case_file)
        golden_cases.append(
            {
                "idx": record["idx"],
                "name": record["name"],
                "case": record["case"],
                "world_size": record["world_size"],
                "profile": record["profile"],
                "file": f"{slug}.pt",
                "sha256": hashlib.sha256(case_file.read_bytes()).hexdigest(),
            }
        )
    return golden_cases


def _canonical_case_views(output_records) -> tuple:
    """The canonical bundle's case views: input_cases (probe/edge
    inputs), dataset_cases (inputs + outputs) and the first
    task-generated record as the probe fallback (rank 0's stored share
    stands in for the full-domain view)."""
    input_cases = []
    dataset_cases = []
    probe_fallback = None
    for record in output_records:
        if "full_inputs" not in record:
            # task-generated: rank 0's stored share stands in for the
            # full-domain view the canonical bundle expects
            rank0 = record["ranks"].get("0", {})
            record = {
                **record,
                "full_inputs": rank0.get("inputs", {}),
                "canonical_outputs": rank0.get("outputs", {}),
            }
            if probe_fallback is None:
                probe_fallback = record
        identity = {
            # machine key (reconciliation/sorting) + human-readable name
            # (case{ci}@ws{ws}[{profile}] — logs and per-case reports
            # print THIS; idx stays for count reconciliation only)
            "idx": record.get("idx"),
            "name": record.get("name"),
            "case": record.get("case"),
            "world_size": record.get("world_size"),
            "profile": record.get("profile"),
        }
        input_cases.append(
            {
                **identity,
                "inputs": record["full_inputs"],
            }
        )
        dataset_cases.append(
            {
                **identity,
                "inputs": record["full_inputs"],
                "outputs": record["canonical_outputs"],
            }
        )
    return input_cases, dataset_cases, probe_fallback


def _publish_canonical_bundle(
    *, workspace, candidate_dir, op, spec, input_cases, dataset_cases, probe_args
) -> None:
    """Hand the staged tree to the common publication authority.

    NEEDS_EP_COMM references run as live HCCL rank groups on the NPU
    endpoint (the subprocess collector); an in-orchestrator CPU probe
    would init NPU/HCCL without a process group and cannot represent
    the execution — the probe defers, the collection run itself is the
    runnability evidence.
    """
    from o25_mode_reference import publish_mode_reference

    # NEEDS_EP_COMM references run as live HCCL rank groups on the NPU
    # endpoint (the subprocess collector); an in-orchestrator CPU probe
    # would init NPU/HCCL without a process group and cannot represent
    # the execution — defer the probe, the collection run itself is the
    # runnability evidence.
    # multirank_verify.py is NOT staged: the canonical verifier executes in
    # place from the harness tree (multirank_runner._CANONICAL_VERIFY).
    private_filenames = ["spec.py", "model.py"]
    deferred_probe = None
    if spec.get("needs_ep_comm"):
        deferred_probe = (
            "NEEDS_EP_COMM reference: truth runs as live HCCL rank "
            "groups on the NPU endpoint (subprocess collector); an "
            "in-orchestrator CPU probe cannot represent it"
        )
    publish_mode_reference(
        workspace=workspace,
        candidate_dir=candidate_dir,
        op=op,
        mode="mc2",
        input_cases=input_cases,
        dataset_cases=dataset_cases,
        source_filename="model.py",
        probe_args=probe_args,
        private_filenames=tuple(private_filenames),
        deferred_probe=deferred_probe,
    )


def _seal_reference_bundle(
    workspace, golden_dir, spec_hash, kernel_input_order
) -> None:
    """Post-publish seal: backfill spec_hash + kernel_input_order into
    ref_runnable.json (keeps the idempotent-cache key effective), move
    the golden tree into the workspace (wholesale replace — a
    re-provision must not mix stale case files with fresh ones), and
    retire the pre-split monolith file."""
    # Backfill spec_hash into the canonical ref_runnable.json so the
    # idempotent-cache check (spec-content-hash key) stays effective.
    # kernel_input_order records the op's canonical kernel-side input
    # ordering (the shard return order, cross-checked across every
    # rank/world-size/case during expansion) — the authoritative answer
    # to "what does the kernel take", for diagnostics and tooling.
    try:
        _rj = json.loads((workspace / "ref_runnable.json").read_text())
        _rj["spec_hash"] = spec_hash
        _rj["kernel_input_order"] = list(kernel_input_order)
        (workspace / "ref_runnable.json").write_text(json.dumps(_rj, indent=2))
    except (OSError, ValueError, TypeError):
        pass
    # The golden tree lands after the canonical bundle: the publish
    # channel accepts flat filenames only, and every golden byte is a
    # repackaging of the canonically-published edge_dataset.pt (same
    # full_inputs + canonical_outputs), so the authority binding comes from
    # that bundle. The wholesale replace keeps a re-provision from mixing
    # stale case files with fresh ones.
    golden_dst = workspace / "golden"
    shutil.rmtree(golden_dst, ignore_errors=True)
    shutil.move(str(golden_dir), str(golden_dst))
    # Retired monolith: the pre-split multirank_reference_outputs.pt must not
    # survive a re-provision (a stale copy would shadow the golden/ tree
    # for any caller still defaulting to it).
    (workspace / "multirank_reference_outputs.pt").unlink(missing_ok=True)


_PUBLISHED_ARTIFACTS = [
    "spec.py",
    "model.py",
    "golden/",
    "input_gen.py",
    "edge_inputs.pt",
    "manifest.json",
    "edge_dataset.pt",
    "ref_runnable.json",
]


def _write_golden_manifest(golden_dir: Path, ctx, op: str, golden_cases) -> None:
    """golden/manifest.json — the campaign index consumed by multirank_runner."""
    from . import read_truth_tier

    (golden_dir / "manifest.json").write_text(
        json.dumps(
            {
                "op": op,
                "spec_hash": ctx.spec_hash,
                "truth_tier": read_truth_tier(ctx.workspace),
                "world_sizes": ctx.ws_set,
                "n_cases": len(golden_cases),
                "cases": golden_cases,
            },
            indent=2,
        )
    )


def _publish_multirank_reference(
    *,
    torch,
    output_records: list[dict],
    kernel_input_order: list[str],
    ctx: ProvisionCtx,
) -> list[str]:
    """Stage and publish MULTIRANK truth through the common authority."""
    workspace, op, spec = ctx.workspace, ctx.op, ctx.spec
    workspace.mkdir(parents=True, exist_ok=True)
    candidate_dir = Path(tempfile.mkdtemp(prefix=".mc2_reference.", dir=workspace))
    try:
        shutil.copyfile(ctx.spec_path, candidate_dir / "spec.py")
        (candidate_dir / "model.py").write_text(
            _generate_model_py(op, spec, list(spec.get("kernel_input_order") or []))
        )
        # multirank_verify.py is NOT staged: the canonical verifier executes in place
        # from the harness tree (multirank_runner._CANONICAL_VERIFY).
        # Per-case golden files: one golden/<slug>.pt per expanded case —
        # identity + full_inputs + canonical_outputs only. Rank shares are NOT
        # stored: multirank_verify derives this rank's inputs/outputs from the full
        # tensors via the spec's shard/expected at launch (the per-rank data is
        # a deterministic derive — storing it duplicated every rank's bytes).
        # Each case process group loads only its own file (fault isolation: a
        # corrupt case file kills that case alone).
        golden_dir = candidate_dir / "golden"
        golden_dir.mkdir()
        golden_cases = _write_golden_cases(torch, golden_dir, op, output_records)
        _write_golden_manifest(golden_dir, ctx, op, golden_cases)

        input_cases, dataset_cases, probe_fallback = _canonical_case_views(
            output_records
        )
        first = probe_fallback or output_records[0]
        probe_args = [first["full_inputs"][name] for name in ctx.input_names]

        _publish_canonical_bundle(
            workspace=workspace,
            candidate_dir=candidate_dir,
            op=op,
            spec=spec,
            input_cases=input_cases,
            dataset_cases=dataset_cases,
            probe_args=probe_args,
        )
        _seal_reference_bundle(workspace, golden_dir, ctx.spec_hash, kernel_input_order)
        return list(_PUBLISHED_ARTIFACTS)
    finally:
        shutil.rmtree(candidate_dir, ignore_errors=True)


def _spec_content_hash(spec_path: Path) -> str:
    """sha256 (short) of the spec source file bytes.

    The golden is a pure function of the spec's `shard`/`expected`/SPEC code,
    so the cache key must include the spec CONTENT, not just the metadata fields
    (op/ws/n_cases/seed/profiles/dtypes). Editing expected() leaves all metadata
    unchanged — without this hash the cache hits on a stale golden and verify
    compares against the pre-edit truth. Scope: the resolved spec file only;
    sibling helper modules a spec might import are NOT hashed (specs are
    single-file by convention)."""
    return hashlib.sha256(spec_path.read_bytes()).hexdigest()[:16]


def _cached_reference_if_match(
    workspace: Path, op: str, ws_set: list[int], n_expected_cases: int, spec_hash: str
) -> Optional[MultirankRefReport]:
    """O2.5 idempotency: return a READY report
    from the cached golden/ tree + ref_runnable.json when the recorded spec
    content hash matches the current spec, else None (caller proceeds to full
    provision). spec_hash alone is the cache key: every other candidate field
    (op/ws/n_cases/seed/profiles/dtypes) is a deterministic derive of the spec
    source, so the content hash subsumes them all. The golden is deterministic
    (seed+idx per case) so a matching cache is bit-identical to a re-provision
    — re-running only wastes ~6min per resume. Missing/corrupt files (manifest
    absent, a case file wiped, or a stale pre-spec_hash ref_runnable.json)
    return None → full provision."""
    cache_runnable = workspace / "ref_runnable.json"
    if not cache_runnable.is_file():
        return None
    try:
        if json.loads(cache_runnable.read_text()).get("spec_hash") != spec_hash:
            return None
        manifest = load_golden_manifest(workspace)
        if not manifest or manifest.get("spec_hash") != spec_hash:
            return None
        # Depth defense: a cached golden from a DIFFERENT truth tier must
        # not satisfy the current declaration even when spec bytes match
        # (unreachable via the normal flow — the tier derives from the spec
        # — but a hand-edited state or a pre-tier legacy cache must miss).
        from . import read_truth_tier

        if manifest.get("truth_tier") != read_truth_tier(workspace):
            return None
        cases = manifest["cases"]
        golden_dir = workspace / "golden"
        if any(not (golden_dir / c["file"]).is_file() for c in cases):
            return None
    except Exception:
        return None
    return MultirankRefReport(
        verdict="READY",
        op=op,
        world_sizes=ws_set,
        summary=(
            f"multirank reference truth cached (spec content hash matches "
            f"current spec) — skip re-provision. {len(cases)} scoreable "
            f"cases, world_sizes={ws_set}"
        ),
        n_cases=n_expected_cases,
        n_ok=len(cases),
        n_skipped=0,
        artifacts=["golden/ (cached)", "ref_runnable.json (cached)"],
    )


def _write_cheap_reference_files(
    workspace: Path,
    spec_path: Path,
    op: str,
    spec: dict,
    *,
    only_if_missing: bool = False,
) -> list:
    """Write the op-agnostic reference artifacts (spec.py, model.py) —
    deterministic functions of the spec, no substitution. multirank_verify.py is
    deliberately absent: the canonical verifier runs from the harness tree
    (multirank_runner._CANONICAL_VERIFY), never staged. only_if_missing=True re-emits
    artifacts wiped by a workspace cleanup while golden stayed cached, without
    overwriting worker-touched copies (provision is idempotent on unchanged
    spec). Returns the list written."""
    workspace.mkdir(parents=True, exist_ok=True)
    written = []
    spec_dst = workspace / "spec.py"
    if spec_path.resolve() != spec_dst.resolve() and not (
        only_if_missing and spec_dst.exists()
    ):
        shutil.copyfile(spec_path, spec_dst)
        written.append("spec.py")
    model_dst = workspace / "model.py"
    if not (only_if_missing and model_dst.exists()):
        model_dst.write_text(
            _generate_model_py(op, spec, list(spec.get("kernel_input_order") or []))
        )
        written.append("model.py")
    return written


@dataclass
class TaskFailureCtx:
    """The fixed identity context per-case failures report against."""

    op: str
    ws_set: set


def _task_case_failure(ctx: TaskFailureCtx, verdict, summary, errors, order):
    """A loud per-case refusal as a TaskCaseExpansion carrying a
    MultirankRefReport."""
    return TaskCaseExpansion(
        None,
        0,
        0,
        0,
        MultirankRefReport(
            verdict=verdict,
            op=ctx.op,
            world_sizes=ctx.ws_set,
            summary=summary,
            errors=errors,
        ),
        order,
    )


def _cached_idle_lanes(lane_cache, endpoint, case_ws):
    """Per-world_size idle lanes, probed by the PARENT and cached (remote
    collector subprocesses cannot import npu_probe — lanes travel via
    MULTIRANK_LANES injection). Probe failure degrades to lanes=None: the
    collector warns and falls back to its legacy mask."""
    from . import multirank_endpoint as _ep

    if case_ws not in lane_cache:
        lane_cache[case_ws] = _ep.pick_idle_npu(endpoint, case_ws)
    return lane_cache[case_ws]


def _launch_task_collect(torch, scratch, case_info, launch_kwargs):
    """Save this case's task payload and run the collector once; returns the
    loaded result dict. case_info is (case_idx, case_name, case_ws, ci)."""
    case_idx, case_name, case_ws, ci = case_info
    in_file = scratch / f"in_{case_idx}.pt"
    out_file = scratch / f"out_{case_idx}.pt"
    task_payload = {
        "idx": case_idx,
        "name": case_name,
        "case": ci,
        "world_size": case_ws,
        "mode": "task",
    }
    from . import multirank_endpoint as _ep

    torch.save(task_payload, in_file)
    _ep.run_collector(
        _ep.CollectorLaunch(
            out_file=out_file,
            in_file=in_file,
            **launch_kwargs,
        )
    )
    return torch.load(out_file, weights_only=False)


def _task_case_record(case_info, case_keys, per_rank) -> dict:
    """One golden record: the collector's per-rank inputs/outputs stored
    verbatim (no derive-at-verify — the generator may be arbitrary Python,
    so golden keeps what it measured). case_info is
    (case_idx, case_name, case_ws, ci)."""
    case_idx, case_name, case_ws, ci = case_info
    return {
        "idx": case_idx,
        "name": case_name,
        "case": ci,
        "profile": "task",
        "world_size": case_ws,
        "kernel_input_order": case_keys,
        "ranks": {
            str(r): {
                "inputs": {k: v.clone() for k, v in rd["inputs"].items()},
                "outputs": {k: v.clone() for k, v in rd["outputs"].items()},
            }
            for r, rd in per_rank.items()
        },
    }


class _TaskCaseLaunch(NamedTuple):
    """The per-case launch inputs: collected resources + case descriptors."""

    torch: object
    scratch: object
    case_info: tuple
    launch_kwargs: dict


def _launch_task_case(launch: _TaskCaseLaunch, fail_ctx, order):
    """Launch + collect one case; (result, None) or (None, failure_report)."""
    case_name = launch.case_info[1]
    try:
        return (
            _launch_task_collect(
                launch.torch, launch.scratch, launch.case_info, launch.launch_kwargs
            ),
            None,
        )
    except Exception as e:
        return None, _task_case_failure(
            fail_ctx,
            "COMPUTE_FAILED",
            (
                f"npubench task collection failed ({case_name}): "
                f"{e!r}; full rank logs kept at {launch.scratch.resolve()}"
            ),
            [f"collector error: {e!r}"],
            order,
        )


def _validate_task_case_result(fail_ctx, case_name, result, case_ws, order):
    """Shape-check one case's collected result.

    Returns (case_keys, None), or (None, failure_report) when the case's key
    order drifts across cases or the rank count mismatches world_size."""
    per_rank = result["per_rank"]
    case_keys = list(result["kernel_input_order"])
    if order and case_keys != order:
        return None, _task_case_failure(
            fail_ctx,
            "SPEC_INVALID",
            (
                f"task inputs returned inconsistent key orders across "
                f"cases ({case_name}): {case_keys} vs {order}"
            ),
            ["task input key-order inconsistency"],
            order,
        )
    if len(per_rank) != case_ws:
        return None, _task_case_failure(
            fail_ctx,
            "COMPUTE_FAILED",
            (
                f"collector returned {len(per_rank)} rank entries for "
                f"world_size={case_ws} ({case_name})"
            ),
            ["collector rank count mismatch"],
            order,
        )
    return case_keys, None


def _rank_outputs_all_finite(torch, per_rank) -> bool:
    """Every rank's every output tensor finite (skip non-finite cases)."""
    return not any(
        not torch.isfinite(t).all()
        for rd in per_rank.values()
        for t in rd["outputs"].values()
    )


def _warn_probe_fallback(case_ws, lane_err, lanes) -> None:
    """Log the collector's legacy-mask fallback when the probe fails."""
    if lanes is None:
        log.error(
            f"[o25] WARNING: idle-card probe for ws={case_ws} "
            f"failed ({lane_err}); collector falls back to its "
            f"legacy mask"
        )


def _task_case_launch_kwargs(endpoint, spec_path, wrapper_path, lanes) -> dict:
    """The per-case launch kwargs the collector subprocess consumes."""
    return dict(
        endpoint=endpoint,
        spec_path=spec_path,
        wrapper_path=wrapper_path,
        lanes=lanes,
    )


def _expand_case_records_task(
    torch, spec, cases, ws_set, op, *, workspace, spec_path, endpoint, wrapper_path=None
):
    """Expand task-generated cases into golden records via the subprocess
    collector's task mode: per case, the task's own get_input_groups/
    Model run on the candidate endpoint (multiprocess + HCCL when the task
    declares NEEDS_EP_COMM); the collected per-rank inputs/outputs are
    stored verbatim (no derive-at-verify — the generator may be arbitrary
    Python, so golden keeps what it measured).

    Returns the (records, n_ok, n_skipped, case_idx, error, order) tuple
    the provision flow expects.
    """
    fail_ctx = TaskFailureCtx(op=op, ws_set=ws_set)
    outputs_records: list[dict] = []
    n_ok = n_skipped = case_idx = 0
    kernel_input_order: list[str] = []
    scratch = Path(tempfile.mkdtemp(prefix=".npu_bench_task.", dir=workspace))
    lane_cache: dict[int, tuple] = {}
    success = False
    try:
        for ci, binding in enumerate(cases):
            case_ws = int(binding.get("world_size", 1))
            case_idx += 1
            case_name = f"{binding.get('name', f'case{ci}')}@ws{case_ws}"
            lanes, lane_err = _cached_idle_lanes(lane_cache, endpoint, case_ws)
            _warn_probe_fallback(case_ws, lane_err, lanes)
            case_info = (case_idx, case_name, case_ws, ci)
            launch_kwargs = _task_case_launch_kwargs(
                endpoint, spec_path, wrapper_path, lanes
            )
            result, launch_err = _launch_task_case(
                _TaskCaseLaunch(
                    torch=torch,
                    scratch=scratch,
                    case_info=case_info,
                    launch_kwargs=launch_kwargs,
                ),
                fail_ctx,
                kernel_input_order,
            )
            if launch_err is not None:
                return launch_err
            case_keys, shape_err = _validate_task_case_result(
                fail_ctx, case_name, result, case_ws, kernel_input_order
            )
            if shape_err is not None:
                return shape_err
            if not kernel_input_order:
                kernel_input_order = case_keys
            per_rank = result["per_rank"]
            if not _rank_outputs_all_finite(torch, per_rank):
                n_skipped += 1
                continue

            n_ok += 1
            outputs_records.append(_task_case_record(case_info, case_keys, per_rank))
        success = True
        return TaskCaseExpansion(
            outputs_records, n_ok, n_skipped, case_idx, None, kernel_input_order
        )
    finally:
        # Success only: wipe the scratch. Failure returns above (and any
        # escaping exception) keep it — the rank logs stay on disk for
        # post-mortem and the failure report names the directory.
        if success:
            shutil.rmtree(scratch, ignore_errors=True)


def _refusal(op: str, verdict: str, summary: str, errors=None, **extra):
    """A loud provision refusal report (verdict + summary + errors)."""
    return MultirankRefReport(
        verdict=verdict, op=op, summary=summary, errors=errors or [], **extra
    )


@dataclass
class ProvisionCtx:
    """Everything provision_multirank_reference resolves before it can run."""

    workspace: Path
    op: str
    spec_path: Path
    spec: dict
    ws_set: set
    task_form: bool
    tier: str
    env: object
    spec_hash: str
    cached: "MultirankRefReport | None"

    @property
    def input_names(self):
        """The kernel's input name list (task form: the canonical order)."""
        if self.task_form:
            return self.spec.get("kernel_input_order")
        return self.spec["inputs"]


def _load_validated_spec(workspace: Path, op: str):
    """(spec, ws_set, spec_path, refusal) — the spec module loaded and
    validated, or the load/validate refusal."""
    spec_path = resolve_spec_path(workspace, op)
    if spec_path is None:
        return (
            None,
            None,
            None,
            _refusal(
                op,
                "SPEC_MISSING",
                f"no multirank op spec found for {op}: looked for "
                f".opgen_state.json['spec'] and workspace/{op}/spec.py",
                errors=[f"spec missing for op {op}"],
            ),
        )
    try:
        mod = _load_spec(spec_path)
    except Exception as e:
        return (
            None,
            None,
            None,
            _refusal(
                op,
                "SPEC_INVALID",
                f"failed to import spec: {e!r}",
                [f"import error: {e!r}"],
            ),
        )
    spec, ws_set, errors = _validate_spec(mod, op)
    if errors:
        return (
            None,
            None,
            None,
            _refusal(
                op, "SPEC_INVALID", "spec does not satisfy the SPEC contract", errors
            ),
        )
    return spec, ws_set, spec_path, None


def _load_provision_ctx(workspace: Path, op: str):
    """Resolve + validate the spec, gate the truth tier, check the idempotent
    cache. Returns (ctx, None) ready to run, or (None, refusal_report)."""
    spec, ws_set, spec_path, refusal = _load_validated_spec(workspace, op)
    if refusal is not None:
        return None, refusal

    # Truth-tier feasibility (fail-closed, BEFORE the idempotent cache): a
    # declared tier must bind to a resolvable endpoint and a wired
    # provider — never a silent degradation to another tier. Tier
    # comes from durable state (single reader shared with the plugin).
    from . import read_truth_tier
    from . import multirank_endpoint as _ep

    tier = read_truth_tier(workspace)
    env = _ep.load_env_or_none()
    tier_errors = _ep.tier_feasibility_errors(tier, env)
    if tier_errors:
        return None, _refusal(
            op,
            "REF_UNAVAILABLE",
            f"declared truth tier {tier!r} is not satisfiable in this "
            f"environment — refusing to silently degrade the golden",
            tier_errors,
        )

    # Idempotency: skip the ~6min golden re-provision when the cached
    # artifacts match the current spec. The key is the spec content hash:
    # editing shard/expected must invalidate the cache, else verify compares
    # against a stale golden. The truth tier needs no separate mixing —
    # SPEC['truth'] is the single declaration point, so a tier change IS a
    # spec-byte change.
    spec_hash = _spec_content_hash(spec_path)
    cached = _cached_reference_if_match(
        workspace, op, ws_set, len(spec["cases"]), spec_hash
    )
    ctx = ProvisionCtx(
        workspace=workspace,
        op=op,
        spec_path=spec_path,
        spec=spec,
        ws_set=ws_set,
        task_form=(spec.get("input_mode") == "task_generated"),
        tier=tier,
        env=env,
        spec_hash=spec_hash,
        cached=cached,
    )
    return ctx, None


def _expand_tier_cases(torch, ctx: ProvisionCtx):
    """Run the tier-selected expansion campaign (a3_live source endpoint with
    the pre-handoff wrapper / default candidate endpoint)."""
    from . import multirank_endpoint as _ep

    if ctx.tier == "a3_live":
        # The source-side campaign: inputs still come from the task's
        # generator; the executed body is the staged source operator via
        # its pre-handoff wrapper (contract: run(rank_inputs, rank,
        # world_size and optional comm, returning a dict; authored around
        # workspace/<op>/.source_arch22/ — the same single-card stage).
        wrapper_path = ctx.workspace / "wrapper.py"
        if not wrapper_path.is_file():
            return None, _refusal(
                ctx.op,
                "REF_UNAVAILABLE",
                f"a3_live requires the pre-handoff source-operator "
                f"wrapper at {wrapper_path} (contract: run("
                f"rank_inputs, rank, world_size, comm=None) -> dict, "
                f"authored around the staged .source_arch22/ tree)",
                ["a3_live wrapper missing"],
                world_sizes=ctx.ws_set,
            )
        endpoint = _ep.resolve_endpoint(ctx.env, "source")
        kw = {"wrapper_path": wrapper_path}
    else:
        endpoint = _ep.resolve_endpoint(ctx.env, "candidate")
        kw = {}
    return (
        _expand_case_records_task(
            torch,
            ctx.spec,
            ctx.spec["cases"],
            ctx.ws_set,
            ctx.op,
            workspace=ctx.workspace,
            spec_path=ctx.spec_path,
            endpoint=endpoint,
            **kw,
        ),
        None,
    )


def _cached_hit_report(ctx: ProvisionCtx) -> MultirankRefReport:
    """Cache hit: re-emit any cheap artifacts a cleanup wiped, keep the verdict."""
    re_emitted = _write_cheap_reference_files(
        ctx.workspace, ctx.spec_path, ctx.op, ctx.spec, only_if_missing=True
    )
    if re_emitted:
        ctx.cached.summary += f" | re-emitted missing: {', '.join(re_emitted)}"
    return ctx.cached


def _finish_provision(torch, ctx: ProvisionCtx, expanded) -> MultirankRefReport:
    """Score the expansion outcome and publish — the READY/COMPUTE_FAILED report."""
    outputs_records, n_ok, n_skipped, case_idx, expand_err, kernel_input_order = (
        expanded
    )
    if expand_err is not None:
        return expand_err
    if n_ok == 0:
        return _refusal(
            ctx.op,
            "COMPUTE_FAILED",
            f"all {n_skipped} cases produced non-finite/failed reference "
            f"— nothing scoreable",
            n_cases=case_idx,
            n_ok=0,
            n_skipped=n_skipped,
            world_sizes=ctx.ws_set,
        )
    try:
        artifacts = _publish_multirank_reference(
            torch=torch,
            output_records=outputs_records,
            kernel_input_order=kernel_input_order,
            ctx=ctx,
        )
    except Exception as exc:
        return _refusal(
            ctx.op,
            "COMPUTE_FAILED",
            f"canonical MULTIRANK publication failed: {exc}",
            [f"canonical publication error: {exc}"],
            world_sizes=ctx.ws_set,
            n_cases=case_idx,
            n_ok=n_ok,
            n_skipped=n_skipped,
        )
    return MultirankRefReport(
        verdict="READY",
        op=ctx.op,
        world_sizes=ctx.ws_set,
        summary=(
            f"multirank reference truth produced self-contained: {n_ok} scoreable / "
            f"{n_skipped} skipped / {case_idx} total cases; world_sizes={ctx.ws_set}"
        ),
        n_cases=case_idx,
        n_ok=n_ok,
        n_skipped=n_skipped,
        artifacts=artifacts,
    )


def provision_multirank_reference(
    workspace: Path,
    *,
    op: str | None = None,
) -> MultirankRefReport:
    """Produce the self-contained multirank multi-rank reference truth.

    Steps:
      1. Resolve + load + validate the multirank op spec.
      2. For each (case × ws × profile): materialize FULL inputs (deterministic
         randn + edge profile), then run every rank's `shard`/`expected` as a
         provision-time validation (non-finite → skip) — the per-rank tensors
         themselves are NOT stored (multirank_verify re-derives them from the full
         inputs at launch; they are a deterministic derive).
      3. Emit workspace artifacts: spec.py (copied), model.py (canonical
         OL-160 single-process reference), golden/<case>.pt per expanded case
         (identity + full_inputs + canonical_outputs) + golden/manifest.json
         (the campaign index, consumed by multirank_runner), ref_runnable.json
         (verdict=RUNNABLE, self-contained — NO SSH). multirank_verify.py is NOT
         emitted — the canonical verifier executes in place from the harness
         tree (multirank_runner._CANONICAL_VERIFY).
      4. READY iff ≥1 scoreable case.

    Pure CPU. No NPU/HCCL/CANN/SSH. The worker verifies its fusion kernel vs
    this truth on real NPU via multirank_runner (Layer 4c/5).
    """
    import torch

    workspace = Path(workspace)
    ctx, refusal = _load_provision_ctx(workspace, op or workspace.name)
    if refusal is not None:
        return refusal
    if ctx.cached is not None:
        return _cached_hit_report(ctx)
    if not ctx.task_form:
        return _refusal(
            ctx.op,
            "SPEC_INVALID",
            "the derived spec.py form (shard/expected) is retired — "
            "multirank input is the KernelBench-style task .py + "
            "sidecar, statically converted at the CLI entry",
            ["derived spec form retired"],
            world_sizes=ctx.ws_set,
        )
    expanded, refusal = _expand_tier_cases(torch, ctx)
    if refusal is not None:
        return refusal
    return _finish_provision(torch, ctx, expanded)


def format_block_message(op: str, rep: MultirankRefReport) -> str:
    lines = [
        "=" * 72,
        f"multirank Phase O2.5 BLOCK — op: {op}  verdict: {rep.verdict}",
        "=" * 72,
        rep.summary or "",
    ]
    for e in rep.errors:
        lines.append(f"  - {e}")
    if rep.verdict in ("SPEC_MISSING", "SPEC_INVALID"):
        lines.append("")
        lines.append(
            "The multirank op spec must live at workspace/<op>/spec.py (or be "
            "named in .opgen_state.json['spec']) and define a `SPEC` "
            "dict (op_name / world_size / inputs / shard / expected). See "
            "multirank_phase_o25.py module docstring for the convention."
        )
    lines.append("=" * 72)
    return "\n".join(lines)
