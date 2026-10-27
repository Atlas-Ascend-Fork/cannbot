# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""Phase O1.7 — LLM-driven op classification (P0aaj/P0aak, 2026-05-07).

Replaces the bench-name-keyed `op_taxonomy.OP_TAGS` map (P0aai regression).
Per user direction: classification should be done by an LLM agent reading the
source, not a hardcoded Python dict + regex catalog. This module wraps the
headless backend skill call (aog-op-classify), parses the resulting
JSON, returns a structured dataclass for brief construction.

Architecture:
- Phase O1.7 runs after O1.5 (DET_POLICY classification) and before O2 (benchmark sync)
- Per-op cost: ~$0.05 + ~30s, cached after via source content SHA256
- Failure mode graceful: subprocess error → falls back to None, brief uses default-only KB
- No state-machine integration (classification is a Python pipeline step, not a state)

Subprocess layer is testable via monkeypatch — unit tests inject a fake backend.
"""

from __future__ import annotations
import logging

import hashlib
import json
import os  # noqa: F401
import subprocess  # noqa: F401 (retained for test monkeypatch compat + TimeoutExpired symbol)
from dataclasses import dataclass, field  # noqa: F401
from pathlib import Path
from typing import Optional

from backends import get_backend

# Funnel (backend-decoupling step 3): the claude skill invocation goes through the pluggable
# Backend, not a hardcoded `claude --print`. phase_o17's divergent shape (acceptEdits + plain-text
# output + prompt-via-stdin) is expressed via dispatch's permission_mode/output_format/stdin_prompt.
_backend = get_backend()


def _strip_backend_suffix(name: str) -> str:
    """Compatibility name retained; scoped workspaces use flat names."""
    return name


@dataclass
class OpClassification:
    op: str
    op_class_tags: list[str]
    kb_recommendations: list[dict]  # [{"path": str, "reason": str}, ...]
    rationale: str
    source_signatures_observed: list[str]
    source_sha256: str
    schema_version: int = 2
    error: Optional[str] = None  # populated on subprocess failure / parse error


_SKILL_NAME = "aog-op-classify"


def _empty_classification(
    workspace: Path, cur_sha: str, *, error: Optional[str] = None, rationale: str = ""
) -> OpClassification:
    """The empty-tags fallback result for a degraded/failed classify run."""
    return OpClassification(
        op=_strip_backend_suffix(workspace.name),
        op_class_tags=[],
        kb_recommendations=[],
        rationale=rationale,
        source_signatures_observed=[],
        source_sha256=cur_sha,
        error=error,
    )


_CACHE_FILENAME = "op_classification.json"
# P135.O17 (2026-05-18): sentinel written when claude CLI reports the skill
# is missing in this checkout. Caches the "skill unavailable" outcome so
# subsequent orchestrator restarts (e.g. --resume after pause) skip the
# 20-30s claude subprocess + $0.05-0.5 cost instead of re-discovering the
# same env limitation. Cleared by the next source-content change (via the
# same sha256 path the normal cache uses).
_SKILL_UNAVAILABLE_SENTINEL = "op_classification.skill_unavailable"


def _compute_source_sha256(workspace: Path) -> str:
    """SHA256 of concatenated source files (in the order SKILL.md §Step 1 lists)."""
    parts: list[bytes] = []
    candidates = [
        workspace / "model.py",
        workspace / "model_new_ascendc.py",
        workspace / "analysis.md",
    ]
    for sub in ("kernel", "."):
        d = workspace / sub
        if not d.exists() or not d.is_dir():
            continue
        for ext in ("*.h", "*.cpp", "*.py"):
            candidates.extend(sorted(d.glob(ext)))
    seen: set[Path] = set()
    for p in candidates:
        if p in seen or not p.exists() or not p.is_file():
            continue
        seen.add(p)
        skip_current_item = False
        try:
            parts.append(p.read_bytes()[:200_000])
        except Exception as error:
            logging.getLogger(__name__).debug(
                "Recoverable operation failed.", exc_info=error
            )
            skip_current_item = True
        if skip_current_item:
            continue
    return hashlib.sha256(b"\n".join(parts)).hexdigest()


def _read_cached(workspace: Path) -> Optional[OpClassification]:
    """Return cached classification if `op_classification.json` exists AND its
    `source_sha256` matches current source content.

    W15-followup (2026-05-12): when classification.json has source=cli_flag_port_a3
    (written by `_cmd_port_a3` from the orchestrator CLI flag), skip the SHA256
    check — the CLI flag IS the authoritative classification, no source-scan
    needed. Without this, phase_o17 re-runs the slow LLM classify skill even
    though _cmd_port_a3 already wrote the right answer.
    """
    cache = workspace / _CACHE_FILENAME
    if not cache.exists():
        return None
    try:
        data = json.loads(cache.read_text())
    except json.JSONDecodeError:
        return None
    # CLI-flag-authoritative shortcut
    if data.get("source") == "cli_flag_port_a3":
        return OpClassification(
            op=data.get("op", _strip_backend_suffix(workspace.name)),
            op_class_tags=data.get("op_class_tags", []),
            kb_recommendations=data.get("kb_recommendations", []),
            rationale=data.get("rationale", "CLI flag --port-a3-ops classification"),
            source_signatures_observed=data.get("source_signatures_observed", []),
            source_sha256=data.get("source_sha256", "cli_flag_port_a3"),
            schema_version=data.get("schema_version", 2),
        )
    cached_sha = data.get("source_sha256", "")
    current_sha = _compute_source_sha256(workspace)
    if cached_sha != current_sha:
        return None
    return OpClassification(
        op=data.get("op", _strip_backend_suffix(workspace.name)),
        op_class_tags=data.get("op_class_tags", []),
        kb_recommendations=data.get("kb_recommendations", []),
        rationale=data.get("rationale", ""),
        source_signatures_observed=data.get("source_signatures_observed", []),
        source_sha256=cached_sha,
        schema_version=data.get("schema_version", 2),
    )


def _write_unclassified_fallback(workspace: Path, cur_sha: str) -> OpClassification:
    """Deterministic sha-matched fallback for the O1.7 "exit-0-without-file" glitch.

    scan 2026-07-24 (main-assigned harness-gap #4; OL-282 vehicle-id family): when
    `aog-op-classify` exits 0 but writes no op_classification.json — because there is
    no benchmark source in scope to classify (for example an `--optimize` re-entry op
    lacking a <op>.py/<op>.json; surfaced on selective_scan_fwd_simd re-optimize) — the
    classifier narrates / asks a clarifying question instead of writing. The old code
    returned a bare error WITHOUT caching, so (a) every orchestrator resume re-invoked
    the flaky 120s LLM subprocess, and (b) downstream saw no file (mode/routing signal
    lost). This writes a deterministic sha-matched fallback (empty tags → brief uses
    default KB sections, the documented graceful mode; see module docstring §Failure
    mode) so the file always exists post-O1.7, re-runs on the SAME source read it cached
    (source_sha256 match → no re-invoke), and a real source change re-triggers classify.
    """
    rationale = (
        "O1.7 fallback: aog-op-classify exited 0 without writing "
        "op_classification.json (no benchmark source in scope to classify, e.g. "
        "an --optimize re-entry). Using default KB sections; a source "
        "change re-triggers classification."
    )
    try:
        (workspace / _CACHE_FILENAME).write_text(
            json.dumps(
                {
                    "op": _strip_backend_suffix(workspace.name),
                    "op_class_tags": [],
                    "kb_recommendations": [],
                    "rationale": rationale,
                    "source_signatures_observed": [],
                    "source_sha256": cur_sha,
                    "schema_version": 2,
                    "source": "o17_fallback_unclassified",
                },
                indent=2,
            )
        )
    except OSError:
        pass
    return _empty_classification(workspace, cur_sha, rationale=rationale)


def _invoke_claude_skill(
    workspace: Path, timeout: int = 900
) -> tuple[bool, str, str, bool]:
    """Run `/aog-op-classify <workspace>` via headless `claude --print`.

    Note: claude CLI does NOT support `--skill <name>` flag. Skills resolve via
    `/skill-name` syntax in the prompt body (per `claude --help` "Skills still
    resolve via /skill-name"). So we pipe `/<skill> <args>` as the prompt.

    Returns (ok, stdout, stderr, timed_out). ok=False indicates subprocess error
    or non-zero exit; timed_out=True marks a wall-clock timeout — the caller
    must NOT sha-pin that outcome (see classify()).

    Runs with bypassPermissions: headless `--print` has no interactive approval
    channel, so a restrictive permission mode would hang the first non-edit
    tool call until the subprocess timeout. Classification runs at a bounded
    effort: enough reasoning to read the source and map it onto op-class/KB
    knowledge, without spending a deep-reasoning budget.
    """
    prompt = f"/{_SKILL_NAME} {workspace}"
    env = _backend.dispatch(
        _SKILL_NAME,
        prompt,
        kind="skill",
        timeout=timeout,
        permission_mode="bypassPermissions",
        effort="medium",
        output_format=None,
        stdin_prompt=True,
    )
    raw = env.raw_envelope
    if raw.get("timed_out"):
        return False, "", f"timeout after {timeout}s", True
    if raw.get("not_found"):
        return False, "", f"claude CLI not found: {raw.get('stderr')}", False
    stdout = env.output_text or ""
    stderr = raw.get("stderr") or raw.get("reason") or ""
    if env.is_error:  # returncode != 0
        return False, stdout, stderr or f"exit {raw.get('returncode')}", False
    return True, stdout, stderr, False


def _try_existing_classification(
    workspace: Path, cur_sha: str, error_msg: str
) -> Optional[OpClassification]:
    """Helper: respect intrinsic op_class taxonomy across cache events.

    Per P135.O17c (2026-05-23 review): when the
    classify skill is unavailable (cached-sentinel) OR cached-error pins
    current sha, the cached short-circuit was returning empty op_class_tags.
    But `op_class` is the operator's INTRINSIC taxonomy — stable across
    kernel iterations of the SAME op. source_sha tracks regen-relevant
    changes, NOT taxonomy validity.

    This helper checks for an existing `op_classification.json` with
    non-empty tags BEFORE returning empty. If found, returns the stale-but-
    -valid classification with the cache-event message captured in `error`
    (transparency: downstream sees the fallback happened).

    Returns None if no usable classification exists (caller should return
    the original error OpClassification).
    """
    import json as _json

    cls_path = workspace / _CACHE_FILENAME
    if not cls_path.is_file():
        return None
    try:
        d = _json.loads(cls_path.read_text())
    except (OSError, _json.JSONDecodeError):
        return None
    tags = d.get("op_class_tags") or []
    if not tags:
        return None
    json_sha = (d.get("source_sha256") or "")[:8]
    return OpClassification(
        op=_strip_backend_suffix(workspace.name),
        op_class_tags=list(tags),
        kb_recommendations=list(d.get("kb_recommendations") or []),
        rationale=d.get("rationale", "") or "",
        source_signatures_observed=list(d.get("source_signatures_observed") or []),
        source_sha256=d.get("source_sha256", "") or "",
        error=(
            f"{error_msg} — reused intrinsic taxonomy from prior valid "
            f"classification (json sha={json_sha}.., current sha="
            f"{cur_sha[:8]}..); op_class is stable across kernel iters of "
            f"the same op"
        ),
    )


def _sentinel_short_circuit(workspace: Path, cur_sha: str) -> "OpClassification | None":
    """P135.O17 skill-unavailable sentinel — if a prior invocation already
    determined this checkout's claude CLI doesn't know /aog-op-classify, skip
    the subprocess. Sentinel is sha-pinned so a source-content change still
    re-tries (in case the skill was installed in between)."""
    sentinel = workspace / _SKILL_UNAVAILABLE_SENTINEL
    if not sentinel.exists():
        return None
    try:
        pinned_sha = sentinel.read_text().strip()
    except OSError:
        pinned_sha = ""
    if pinned_sha != cur_sha:
        return None
    # P135.O17c (2026-05-23 review): mirror the cached-error fallback —
    # check for existing valid op_classification.json BEFORE returning empty.
    # Same intrinsic-taxonomy reasoning as the cached-error path.
    stale = _try_existing_classification(
        workspace,
        cur_sha,
        "skill unavailable (cached sentinel — /aog-op-classify not installed in this checkout)",
    )
    if stale is not None:
        return stale
    return _empty_classification(
        workspace,
        cur_sha,
        error="skill unavailable (cached sentinel; brief will use default-only KB)",
    )


def _skill_missing_fallback(
    workspace: Path, cur_sha: str, stdout: str
) -> OpClassification:
    """Claude CLI exited 0 but the skill produced no output file. Cache the
    outcome so the next orchestrator restart short-circuits."""
    try:
        (workspace / _SKILL_UNAVAILABLE_SENTINEL).write_text(cur_sha)
    except OSError:
        pass
    return _empty_classification(
        workspace,
        cur_sha,
        error=(
            "skill exited 0 but op_classification.json not written or sha "
            f"mismatch; stdout_tail={stdout[-200:]!r}"
        ),
    )


def classify(
    workspace: Path, *, force: bool = False, timeout: int = 900
) -> OpClassification:
    """Run Phase O1.7 classification on a workspace.

    Args:
        workspace: path to workspace dir
        force: if True, ignore cache and re-run skill
        timeout: subprocess timeout in seconds — a hang fuse bounding the
            worst case so one stuck classify cannot stall the pipeline; NOT
            the expected duration of a healthy classification run.

    Returns:
        OpClassification (with error field populated on failure — never raises)
    """
    cur_sha = _compute_source_sha256(workspace)
    if not force:
        cached = _read_cached(workspace)
        if cached is not None:
            return cached
        # P135.O17 (2026-05-18): skill-unavailable sentinel (sha-pinned so a
        # source-content change still re-tries).
        short = _sentinel_short_circuit(workspace, cur_sha)
        if short is not None:
            return short

    # No cached-error short-circuit (multirank e2e finding #12, 2026-10-15):
    # failures are never recorded as a "same source failed before" marker.
    # Whether a failure is transient (infra hiccup) or deterministic is not
    # knowable from the error text — a mis-guessed transient failure would
    # pin the workspace into permanently degraded classification until
    # manual cleanup. Retrying costs one bounded classify call; the retry
    # path is the only way a transient failure self-heals. Legacy
    # op_classification.error/.sha256 files from older builds are ignored.

    ok, stdout, stderr, _ = _invoke_claude_skill(workspace, timeout=timeout)
    if not ok:
        # DEBT-134 (2026-05-26): on a first-invocation skill failure/timeout,
        # prefer a prior valid op_classification.json (non-empty tags) over an
        # empty-tags error — op_class is the operator's INTRINSIC taxonomy,
        # stable across kernel iters of the same op.
        # No error file/marker is written (finding #12): a failure is never
        # cached as a source property — the next invocation retries the
        # skill; transient failures self-heal and deterministic ones merely
        # cost one extra bounded call.
        stale = _try_existing_classification(
            workspace,
            cur_sha,
            f"skill subprocess failed (first invocation): {stderr[:120]}",
        )
        if stale is not None:
            return stale
        return _empty_classification(
            workspace, cur_sha, error=f"skill subprocess failed: {stderr[:400]}"
        )

    # Skill writes the JSON to workspace/op_classification.json directly; we just
    # re-read it. Sanity-check that the skill emitted the expected file.
    cached = _read_cached(workspace)
    if cached is not None:
        return cached
    # P135.O17 (2026-05-18): claude CLI exited 0 but the skill produced no
    # output file. The deterministic cause is "Unknown command: /<skill>" —
    # the skill is not installed/registered in this checkout.
    if "Unknown command" in stdout:
        return _skill_missing_fallback(workspace, cur_sha, stdout)
    # scan 2026-07-24 (O1.7-glitch fix, main-assigned #4; OL-282 vehicle-id family):
    # non-"Unknown command" exit-0-without-file = the classifier narrated / asked a
    # clarifying question instead of writing (no benchmark source in scope to classify
    # — for example an --optimize re-entry). Write a deterministic sha-matched fallback
    # (see _write_unclassified_fallback) so re-runs on the same source skip the flaky
    # 120s re-invoke + downstream always has a file; a source change re-triggers classify.
    # exit-0-without-(sha-matching)-file: before writing the deterministic
    # empty fallback, respect an existing non-empty classification (multirank
    # CLI-flag preseed, or a prior valid agent write whose sha scheme
    # predates the --classify-sha contract) — op_class is intrinsic to the
    # op; never clobber non-empty tags with an empty fallback.
    stale = _try_existing_classification(
        workspace,
        cur_sha,
        "skill exited 0 without a sha-matching op_classification.json",
    )
    if stale is not None:
        return stale
    return _write_unclassified_fallback(workspace, cur_sha)
