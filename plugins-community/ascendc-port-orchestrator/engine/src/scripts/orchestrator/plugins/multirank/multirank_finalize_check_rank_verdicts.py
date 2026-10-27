# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""multirank rank-verdicts finalize gate (multirank-scoped).

Extracted from finalize_checks_structural.py (module-size discipline): the
gate validates verification.json["multirank"] — structure (exactly world_size rank
entries per group), verdict⟺claim consistency (both directions), UNVERIFIED
probe evidence (full-group + per-case channels), and the coverage partition
(declared cases == folded ∪ unverified, disjoint).

Wiring note (Option-A plugin wiring): the gate is NOT registered in the core
finalize branch tables — it is registered ONLY through the multirank
plugin's extra_finalize_checks (plugins/multirank/__init__.py), which lazily
imports this module, so BOTH finalize branches (PASS and PARTIAL_PERSIST)
validate the multirank block without a core mode-branch (architecture_lint
CORE_MODE_LEAK / PLUGIN_NAME_BRANCH).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional


def _candidate_subdirs(workspace: Path, sub: str) -> list[Path]:
    """Candidate <sub> dirs across layouts: nest prj-*/<sub> (multirank C++ project
    under workspace/<op>/prj-<op>/) + legacy single-layer workspace/<sub>.
    Callers filter via is_dir()/exists() — legacy entries may not exist."""
    return [*workspace.glob(f"prj-*/{sub}"), workspace / sub]


def _workspace_is_multirank(workspace: Path) -> bool:
    """True when the durable state flags this port_a3 workspace `multirank`.

    The multirank extension is not a standalone mode: the workspace is
    detected as port_a3_to_a5 by the plugin registry, and every multirank
    gate scopes itself on this durable-state flag instead.
    """
    state_file = Path(workspace) / ".opgen_state.json"
    if not state_file.is_file():
        return False
    try:
        import json as _json

        return _json.loads(state_file.read_text()).get("multirank") is True
    except Exception:
        return False


def _multirank_unverified_evidence_error(unverified_cases: dict) -> Optional[str]:
    """Per-case UNVERIFIED evidence (same bar as the full-group placeholder):
    a case recorded unverified must carry objective probe evidence."""
    for cname, ph in unverified_cases.items():
        if not (
            isinstance(ph, dict)
            and ph.get("status") == "UNVERIFIED"
            and ph.get("reason")
            and ph.get("detail")
            and ph.get("probe")
        ):
            return (
                f"MULTIRANK_RANK_VERDICTS (UNVERIFIED evidence): case {cname!r} is "
                f"recorded under `unverified_cases` but lacks objective probe "
                f"evidence (status/reason/detail/probe). A self-reported "
                f"coverage gap cannot bypass verification — only a "
                f"probe-backed card shortage may."
            )
    return None


def _ws_coverage_partition_error(
    ws, declared, rank_verdicts, unverified, case_unv
) -> Optional[str]:
    """One world_size's covered/unverified partition check."""
    full_group = str(ws) in unverified
    if full_group and case_unv:
        return (
            f"MULTIRANK_RANK_VERDICTS (coverage partition): world_size={ws} "
            f"has BOTH a full-group UNVERIFIED placeholder and per-case "
            f"unverified entries {sorted(case_unv)} — the two channels "
            f"are mutually exclusive per group."
        )
    covered: set = set()
    if not full_group:
        for r in rank_verdicts.get(str(ws)) or []:
            if isinstance(r, dict):
                covered.update(r.get("cases") or [])
    overlap = covered & case_unv
    missing = declared - covered - case_unv - (declared if full_group else set())
    extra = (covered | case_unv) - declared
    if not (overlap or missing or extra):
        return None
    parts = []
    if overlap:
        parts.append(f"covered∩unverified={sorted(overlap)}")
    if missing:
        parts.append(f"never-accounted={sorted(missing)}")
    if extra:
        parts.append(f"not-declared={sorted(extra)}")
    return (
        f"MULTIRANK_RANK_VERDICTS (coverage partition): world_size={ws} "
        f"case coverage does not partition the declared campaign — "
        f"{'; '.join(parts)}. Every declared case must be folded "
        f"into the rank verdicts or recorded UNVERIFIED with probe "
        f"evidence; none may be dropped or double-counted."
    )


def _multirank_coverage_partition_error(
    world_sizes, declared_cases, rank_verdicts, unverified, unverified_cases
) -> Optional[str]:
    """Coverage partition: when the block self-describes its campaign via
    multirank.cases, every declared case must be accounted for exactly once —
    folded into the rank verdicts (entry `cases`) or recorded UNVERIFIED
    (full-group placeholder / per-case entry). A silently dropped case (or
    one counted in both channels) is a dishonest coverage report."""
    for ws in world_sizes:
        declared = {
            c.get("name")
            for c in declared_cases
            if isinstance(c, dict) and c.get("world_size") == ws
        }
        if not declared:
            continue
        case_unv = {
            n
            for n, ph in unverified_cases.items()
            if isinstance(ph, dict) and ph.get("world_size") == ws
        }
        err = _ws_coverage_partition_error(
            ws, declared, rank_verdicts, unverified, case_unv
        )
        if err is not None:
            return err
    return None


def _unverified_placeholder_error(ws, ph) -> Optional[str]:
    """The full-group UNVERIFIED placeholder must carry probe evidence."""
    if not (
        isinstance(ph, dict)
        and ph.get("status") == "UNVERIFIED"
        and ph.get("reason")
        and ph.get("detail")
        and ph.get("probe")
    ):
        return (
            f"MULTIRANK_RANK_VERDICTS (UNVERIFIED evidence): world_size={ws} "
            f"has no rank verdicts, but its `unverified` placeholder lacks "
            f"objective probe evidence (status/reason/detail/probe). A "
            f"self-reported coverage gap cannot bypass verification — only "
            f"a probe-backed card shortage may."
        )
    return None


def _rank_verdict_structure_error(
    world_sizes, rank_verdicts, unverified
) -> Optional[str]:
    """Invariants 2-3: every declared ws is a positive int and its group has
    exactly world_size classified PASS/FAIL rank entries (or a probe-backed
    UNVERIFIED placeholder)."""
    for ws in world_sizes:
        if not isinstance(ws, int) or isinstance(ws, bool) or ws < 1:
            return (
                f"MULTIRANK_RANK_VERDICTS (design §5 Layer 4a): declared world_size {ws!r} "
                f"is not a positive int."
            )
        ranks = rank_verdicts.get(str(ws))
        if ranks is None and str(ws) in unverified:
            # UNVERIFIED escape hatch: a declared
            # world_size the probe could not allocate cards for is recorded as
            # an UNVERIFIED placeholder. Accept it ONLY with objective probe
            # evidence — a placeholder without reason/detail/probe is a worker
            # self-report of "did not run", which must not bypass verification.
            ph_err = _unverified_placeholder_error(ws, unverified[str(ws)])
            if ph_err is not None:
                return ph_err
            continue
        n_ranks = len(ranks) if isinstance(ranks, list) else None
        if not isinstance(ranks, list) or n_ranks != ws:
            return (
                f"MULTIRANK_RANK_VERDICTS (design §3.2): world_size={ws} group has "
                f"{n_ranks} ranks. multirank_verify.py must emit exactly "
                f"world_size per-rank verdicts per group."
            )
        bad = []
        for r in ranks:
            if not (isinstance(r, dict) and r.get("status") in ("PASS", "FAIL")):
                bad.append(r)
        if bad:
            return (
                f"MULTIRANK_RANK_VERDICTS (design §3.2): world_size={ws}: {len(bad)} of "
                f"{ws} rank entrie(s) carry a non-PASS/FAIL status "
                f"({[r.get('status') if isinstance(r, dict) else type(r).__name__ for r in bad]}). "
                f"Per-rank verdicts must be the classified PASS/FAIL strings."
            )
    return None


def _full_pass_claim(prec: dict) -> tuple[bool, object, object]:
    """(is_full_pass, tier1_pass, total) from the precision claim.

    T2-wired runs (spec t2_competitor declared): a case that FAILED T1 but
    reached parity-or-better vs the competitor counts into
    tier1_pass_inclusive (P0cc), so the full-pass claim is keyed on the
    inclusive count when present; the strict count stays authoritative for
    pre-T2 archives (inclusive == tier1_pass there, so behavior is unchanged)."""
    pa = prec.get("pass_a") or {}
    t1, tot = pa.get("tier1_pass"), pa.get("total")
    counts_known = (
        isinstance(t1, int)
        and not isinstance(t1, bool)
        and isinstance(tot, int)
        and not isinstance(tot, bool)
        and tot > 0
    )
    t1i = pa.get("tier1_pass_inclusive")
    inclusive_known = (
        isinstance(t1i, int) and not isinstance(t1i, bool) and counts_known
    )
    if inclusive_known:
        return t1i == tot, t1, tot
    if counts_known:
        return t1 == tot, t1, tot
    return prec.get("status") in ("PASS", "PASS_WITHIN_TOLERANCE"), t1, tot


def _verdict_consistency_error(
    v, world_sizes, rank_verdicts, unverified
) -> Optional[str]:
    """Invariant 4, enforced BOTH ways.

    Verdict-consistency (matmul_allreduce kw-1 dishonest rank-verdict stencil,
    2026-08-12): design §3.2 "ALL rank PASS = PASS" is an implication between
    the rank verdicts and the precision claim, not a structural demand on every
    op — a requirement-class PARTIAL op honestly records FAIL ranks at the
    world_sizes whose cases failed T1 (probe-verified requirement-class
    judge-strictness cells; the runner's measured-FAIL path reconciles the
    counts).
      all-ranks-PASS verdict roll  <=>  the precision claim is a full pass.
    kw-1 wrote an all-PASS block alongside a 25/35 PARTIAL pass_a — that
    pair is logically impossible (a rank with any failing case has status
    FAIL) and is rejected here in BOTH directions."""
    all_pass = True
    for ws in world_sizes:
        if str(ws) in unverified:
            continue
        for r in rank_verdicts[str(ws)]:
            if r.get("status") != "PASS":
                all_pass = False
    prec = v.get("precision") or {}
    full_pass_claim, t1, tot = _full_pass_claim(prec)
    if all_pass and not full_pass_claim:
        return (
            f"MULTIRANK_RANK_VERDICTS (design §3.2 consistency): the rank-verdict roll claims "
            f"ALL-ranks-PASS at every world_size, but precision.pass_a is a "
            f"partial claim (tier1_pass={t1!r}, total={tot!r}, "
            f"status={prec.get('status')!r}). An all-PASS verdict roll with a "
            f"partial count claim is logically impossible — a rank with any "
            f"failing case has status FAIL. Record the honest per-rank "
            f"verdicts (FAIL at the world_sizes whose cases failed T1) from "
            f"the runner's measured output, not an all-PASS stencil."
        )
    if not all_pass and full_pass_claim:
        failing = {}
        for ws in world_sizes:
            if str(ws) in unverified:
                continue
            failed_ranks = [
                r.get("rank")
                for r in rank_verdicts[str(ws)]
                if r.get("status") != "PASS"
            ]
            if failed_ranks:
                failing[str(ws)] = failed_ranks
        return (
            f"MULTIRANK_RANK_VERDICTS (design §3.2 ALL-rank-PASS): the precision claim "
            f"is a full pass but {len(failing)} world_size group(s) contain "
            f"FAIL ranks {failing}. multirank verdict is PASS only if EVERY rank "
            f"PASSes — either the claim or the rank-verdict roll is dishonest."
        )
    return None


def _check_multirank_rank_verdicts(workspace: Path) -> Optional[str]:
    """multirank (multirank, design §5 Layer 4a): finalize gate validating the
    verification.json multi-rank rank-verdict contract.

    multirank archives MUST record their multi-rank verdict under `verification.json
    ["multirank"]`:
      {"multirank": {"world_sizes": [<int>, ...],
               "rank_verdicts": {"<ws>": [{"rank": r, "status": "PASS"}, ...], ...}}}
    (The key is `rank_verdicts`, matching this gate's name — NOT `groups`,
    which collides with the HCCL comm-group concept. The legacy single-ws
    shape {"world_size", "ranks"} and the interim "groups" spelling were
    dropped with the rename; every archive re-emits on its next verify.)

    Invariants (design §2.3: rank count = any positive int; §3.2:
    ALL rank PASS = PASS as a rank-verdicts↔claim implication):
      1. `multirank` object present — else multirank_verify.py did not emit multi-rank
         rank verdicts (route back to worker).
      2. Every declared world_size is an int >= 1.
      3. Every group has exactly world_size rank entries (per-case launches
         are folded back into the group shape), each carrying a classified
         "PASS"/"FAIL" status string.
      4. Verdict-consistency (kw-1 dishonest rank-verdict stencil incident):
         all-ranks-PASS across every group ⟺ the precision claim is a full
         pass (pass_a counts when present, else precision.status=="PASS").
         A PARTIAL op honestly records FAIL ranks at the world_sizes whose
         cases failed T1; an all-PASS stencil over partial counts (or FAIL
         ranks under a full-pass claim) is logically impossible and rejected.
      5. UNVERIFIED evidence (both channels): a full-group `unverified`
         placeholder or a per-case `unverified_cases` entry is accepted ONLY
         with objective probe evidence (status/reason/detail/probe) — a
         worker self-report of "did not run" must not bypass verification.
      6. Coverage partition (when `multirank.cases` declares the campaign): per
         world_size, the cases folded into the rank verdicts + the cases
         recorded UNVERIFIED must partition the declared cases — no declared
         case silently dropped, none double-counted, the full-group and
         per-case unverified channels mutually exclusive.

    Scoping mirrors _check_arch35_wrap_cheat: applies ONLY to multirank;
    single-rank modes have no multirank rank-verdict block.

    Returns None on pass (or out-of-scope / file-absent — other gates handle
    those); rationale string on any invariant violation.

    Fail-closed detection: detection errors are deliberately allowed to
    PROPAGATE — never swallowed into an out-of-scope None.
    `_run_plugin_extra_finalize_checks` converts a raised gate into a
    fail-closed finalize rejection, so an ambiguous detection can never be
    laundered into a gate skip (test_plugin_detection_fail_closed pins the
    explicit catch allowlist).
    """
    if not _workspace_is_multirank(workspace):
        return None
    vp = workspace / "verification.json"
    if not vp.is_file():
        return None  # VERIFICATION_FILE_MISSING handles absence
    try:
        v = json.loads(vp.read_text())
    except Exception:
        return None  # VERIFICATION_MALFORMED handles this
    multirank = v.get("multirank")
    if not isinstance(multirank, dict):
        return (
            "MULTIRANK_RANK_VERDICTS (design §5 Layer 4a): verification.json is missing the "
            "`multirank` rank-verdict object. multirank multirank_verify.py MUST emit "
            '{"multirank": {"world_sizes": [<int>...], "rank_verdicts": {"<ws>": '
            '[{"rank": r, "status": "PASS"}, ...]}}} aggregating the '
            "multi-rank run."
        )
    world_sizes = multirank.get("world_sizes")
    rank_verdicts = multirank.get("rank_verdicts")
    unverified = multirank.get("unverified") or {}
    unverified_cases = multirank.get("unverified_cases") or {}
    if (
        not isinstance(world_sizes, list)
        or not world_sizes
        or not isinstance(rank_verdicts, dict)
    ):
        return (
            f"MULTIRANK_RANK_VERDICTS (design §5 Layer 4a): multirank.world_sizes = "
            f"{world_sizes!r} is not a non-empty list (with a `rank_verdicts` "
            f"dict). multirank_verify.py must record the per-case world_size "
            f"rank verdicts it ran."
        )
    structure_err = _rank_verdict_structure_error(
        world_sizes, rank_verdicts, unverified
    )
    if structure_err is not None:
        return structure_err
    evidence_err = _multirank_unverified_evidence_error(unverified_cases)
    if evidence_err:
        return evidence_err
    declared_cases = multirank.get("cases")
    if isinstance(declared_cases, list) and declared_cases:
        partition_err = _multirank_coverage_partition_error(
            world_sizes, declared_cases, rank_verdicts, unverified, unverified_cases
        )
        if partition_err:
            return partition_err
    return _verdict_consistency_error(v, world_sizes, rank_verdicts, unverified)


def _text_without_comments(text: str, *, cpp: bool) -> str:
    """Line-preserving comment removal for the namespace scan.

    The gate judges CODE, not prose: a guidance comment can legitimately
    CONTAIN the forbidden phrase while telling the reader not to use it — the
    multirank/templates header's own "No `using namespace AscendC`" line does, and
    the template mandates a verbatim copy, so without comment stripping every
    conformant workspace tripped the gate on the template's own text. Lines
    are replaced (not deleted) so violation line numbers stay true to the
    original file."""
    _single_line_block = re.compile(r"/\*.*?\*/")
    lines_out: list[str] = []
    in_block = False
    for raw in text.splitlines():
        line = raw
        if in_block:
            if "*/" in line:
                in_block = False
                line = line.split("*/", 1)[1]
            else:
                lines_out.append("")
                continue
        if cpp:
            line = _single_line_block.sub("", line)
            if "/*" in line and "*/" not in line:
                in_block = True
                line = line.split("/*", 1)[0]
        marker = "//" if cpp else "#"
        idx = line.find(marker)
        if idx != -1:
            line = line[:idx]
        lines_out.append(line)
    return "\n".join(lines_out)


def _check_multirank_namespace(workspace: Path) -> Optional[str]:
    """multirank (multirank): finalize gate rejecting `using namespace AscendC` in
    kernel/host files. multirank requires explicit `AscendC::` qualification — the
    multirank/templates/ headers are authored that way, and a blanket using-namespace
    pollutes the global namespace, undermining the `namespace mc2_sync`
    discipline the sync helpers rely on (and hiding qualification mistakes).

    Scans op_kernel/ + kernel/ *.h/*.cpp (nest prj-*/op_kernel and legacy
    flat layouts) + model_new_ascendc.py + pybind11.cpp.
    Scoped to multirank (single-rank modes are unaffected). Returns None on
    pass / out-of-scope; rationale string on violation. Detection errors
    propagate (same fail-closed discipline as _check_multirank_rank_verdicts).
    """
    import re as _re

    if not _workspace_is_multirank(workspace):
        return None
    _pat = _re.compile(r"\busing\s+namespace\s+AscendC\b")
    targets: list[Path] = []
    for d in (
        *_candidate_subdirs(workspace, "op_kernel"),
        *_candidate_subdirs(workspace, "kernel"),
    ):
        if d.is_dir():
            targets += list(d.glob("*.h")) + list(d.glob("*.cpp"))
    for name in ("model_new_ascendc.py", "pybind11.cpp"):
        p = workspace / name
        if p.is_file():
            targets.append(p)
    for f in targets:
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        scan_text = _text_without_comments(
            text, cpp=f.suffix in {".h", ".hpp", ".cpp", ".cc", ".cxx"}
        )
        m = _pat.search(scan_text)
        if m:
            lineno = scan_text.count("\n", 0, m.start()) + 1
            return (
                f"MULTIRANK_NAMESPACE_VIOLATION: `{m.group(0).strip()}` found in "
                f"{f.relative_to(workspace)}:{lineno}. multirank kernels MUST use "
                "explicit `AscendC::` qualification — `using namespace AscendC` "
                "is forbidden (pollutes the global namespace and undermines the "
                "`namespace mc2_sync` discipline the mc2/templates/ headers rely "
                "on). Remove the using-namespace and qualify each AscendC symbol."
            )
    return None
