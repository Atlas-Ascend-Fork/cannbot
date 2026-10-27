# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""MultiRank extension plugin for port_a3_to_a5 migration.

This plugin is NOT a standalone mode. It is an extension loaded by
`PortA3Plugin` when a workspace is detected as a multi-rank
collective-communication + compute fusion case. It provides the multi-rank
capability stack (runner, golden provision, build chain, KB, safety nets) so
the core `port_a3_to_a5` mode can delegate without being invaded.

All runtime modules live alongside this file in `plugins/multirank/` and are
imported lazily so that importing the extension never requires them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..base import BasePlugin


# HCCL delegation attack surface. A worker may degrade the "communication" half
# of a fusion op into host-side torch.distributed / hcom / aclnn*Hcom* —
# delegating to the CANN collective runtime instead of authoring an AscendC
# collective kernel. Multi-rank analogue of the existing anti-CANN-delegation
# patterns.
MULTIRANK_FORBIDDEN: list[tuple[str, str]] = [
    # Collectives only — init_process_group / barrier / destroy_process_group
    # (process-group setup/sync, no data movement) are excluded.
    (
        r"\btorch\.distributed\.(all_reduce|all_gather|broadcast|"
        r"reduce_scatter|all_to_all[a-z_]*|send|recv|isend|irecv)\s*\(",
        "torch.distributed.<collective>() — HCCL/gloo delegation, not an AscendC "
        "collective kernel",
    ),
    (
        r"\bdist\.(all_reduce|all_gather|broadcast|reduce_scatter|all_to_all[a-z_]*)\s*\(",
        "dist.<collective>() — torch.distributed alias (HCCL/gloo delegation)",
    ),
    (
        r"\btorch\.distributed\.(ccl|get_rank|get_world_size|new_group)\b",
        "torch.distributed rank/world_size query — use the multirank rank shim, not "
        "torch.distributed",
    ),
    (
        r"\bhcom\.[A-Z][a-zA-Z_0-9]*\s*\(",
        "hcom.<Api>() — direct HCCL C-API delegation (CANN collective runtime)",
    ),
    (r"\bHcom[A-Z][a-zA-Z_0-9]*\s*\(", "Hcom<Api>() — HCCL delegation"),
    (
        r"\baclnn(AllReduce|AllGather|Broadcast|ReduceScatter|"
        r"AllToAll|Hcom)[a-zA-Z_0-9]*\s*\(",
        "aclnn<Collective> / aclnn*Hcom* — CANN collective built-in delegation",
    ),
    (
        r"\btorch_npu\.npu_[a-z_]*(all_reduce|all_gather|broadcast|reduce_scatter|"
        r"all_to_all)\s*\(",
        "torch_npu.npu_<collective>() — HCCL-backed delegation",
    ),
]


# Truth-tier vocabulary (module level: readers import these without the
# plugin class). Durable-state key + the tiers; see
# resolve_truth_source_tier for semantics.
TRUTH_TIER_STATE_KEY = "multirank_truth_source"
TIERS = ("a3_live", "npubench")


def read_truth_tier(workspace) -> str:
    """Effective truth tier from durable state (written by _cmd_multirank:

    SPEC['truth'] > npubench default). Absent/unreadable state or a value
    outside TIERS falls back to the default — the single reader every
    consumer (plugin method, provision, gates) shares.
    """
    state_file = Path(workspace) / ".opgen_state.json"
    try:
        import json as _json

        tier = _json.loads(state_file.read_text()).get(TRUTH_TIER_STATE_KEY)
    except Exception:
        tier = None
    return tier if tier in TIERS else "npubench"


class MultiRankPlugin(BasePlugin):
    name = "multirank"

    cli_flag = None  # Not a standalone mode; used only as an extension.

    # Re-exported on the class for protocol-visible introspection.
    TRUTH_TIER_STATE_KEY = TRUTH_TIER_STATE_KEY

    TIERS = TIERS

    # Durable-state key carrying the declared truth tier; values = TIERS below.
    TRUTH_TIER_STATE_KEY = "multirank_truth_source"

    TIERS = TIERS

    def check_op_host_completeness(self, workspace: Path) -> Optional[str]:
        """PB-33 N/A — multirank's op_host is the msopgen opc internal deliverable
        (OpDef + TilingFunc + aclnn wrapper), NOT a port_a3-style op_host/
        archive mirror. The archive deliverable (model_new_ascendc.py + .so) is
        enforced by _check_universal_entrypoints (OL-160).
        """
        return None

    def detect(self, workspace: Path) -> bool:
        """Extension plugin never claims a workspace on its own.

        Detection is owned by `PortA3Plugin.is_multirank_workspace()`.
        """
        return False

    def extra_finalize_checks(self):
        """Multirank rank-verdicts + namespace gates.

        These checks are registered by `PortA3Plugin` when it detects a
        multirank workspace, so they run as part of the port_a3_to_a5 finalize
        path without modifying the core finalize pipeline.
        """

        def _rank_verdicts_gate(ws, vj):
            from . import multirank_finalize_check_rank_verdicts

            return getattr(
                multirank_finalize_check_rank_verdicts, "_check_multirank_rank_verdicts"
            )(ws)

        def _namespace_gate(ws, vj):
            from . import multirank_finalize_check_rank_verdicts

            return getattr(
                multirank_finalize_check_rank_verdicts, "_check_multirank_namespace"
            )(ws)

        def _perf_integrity_gate(ws, vj):
            # The perf waiver path applies to NPU tiers only (where a
            # measurement was expected).
            spec_path = ws / "spec.py"
            if not spec_path.is_file():
                return None
            try:
                from . import multirank_phase_o25

                mod = getattr(multirank_phase_o25, "_load_spec")(spec_path)
                spec = getattr(mod, "SPEC", {})
            except Exception:
                return None
            if not isinstance(spec, dict) or not spec.get("perf_baseline"):
                return None
            perf = ((vj or {}).get("performance")) or {}
            ratio = perf.get("ratio")
            has_ratio = isinstance(ratio, (int, float)) and ratio > 0
            if has_ratio or (ws / ".perf_waiver").is_file():
                return None
            return (
                "spec declares perf_baseline but verification.json.performance "
                "carries no measured ratio and no .perf_waiver is on record — "
                "re-run the perf campaign (verify --perf) or record an "
                "explicit owner waiver in workspace .perf_waiver before "
                "finalize"
            )

        return [
            ("multirank_rank_verdicts_consistency", _rank_verdicts_gate),
            ("multirank_namespace_violation", _namespace_gate),
            ("multirank_perf_integrity", _perf_integrity_gate),
        ]

    def finalize_perf_capture(self, workspace: Path, op: str) -> Optional[dict]:
        """Multirank finalize perf: the multi-rank multirank_runner --perf pass."""
        # A perf A/B baseline must be an NPU-executed reference
        # (npubench/a3_live) — enforced by the tier resolver refusing
        # everything else before a campaign can start.
        from . import multirank_runner

        method = "multirank_runner --perf multi-NPU per-case A/B"
        mr_res = multirank_runner.run_all_groups(
            multirank_runner.CampaignContext(workspace=workspace, op=op, perf=True),
            None,
        )
        if mr_res.runner_error:
            return self._mr_runner_error_result(mr_res.runner_error, method)
        unverified = self._mr_unverified_result(workspace, mr_res, method)
        if unverified is not None:
            return unverified
        perf = mr_res.perf or {}
        ratio = perf.get("ratio")
        if ratio is None:
            return {
                "status": "N/A",
                "reason": (
                    "multirank: spec declares no perf_baseline (or the "
                    "baseline measurement failed) — perf is honestly N/A"
                ),
                "na_kind": "UNMEASURABLE_BY_DESIGN",
                "method": method,
            }
        result = {
            key: value
            for key, value in perf.items()
            if key not in ("trusted_receipt", "execution_report")
        }
        result["method"] = method
        if not result.get("status"):
            threshold = self.ko_escalation_threshold()
            result["status"] = (
                "PASS"
                if ratio >= 1.0
                else "PASS_WITHIN_TOLERANCE"
                if ratio >= threshold
                else "BELOW_THRESHOLD"
            )
        return result

    def forbidden_patterns(self) -> list[tuple[str, str]]:
        return list(MULTIRANK_FORBIDDEN)

    def kernel_author_constraints_block(self) -> Optional[str]:
        return """**Constraints (state up-front — scanner/gate enforce; avoids the write→scan→fix token cost):**
- Communication MUST live inside the kernel (window RDMA / memory semantics);
  NO host-side HCCL delegation (`torch.distributed.*` / `hcom.*` / `aclnn*Hcom*` /
  `torch_npu.npu_*collective*` — scan gate rejects).
- Qualify every AscendC symbol (`AscendC::DataCopy`, not `using namespace AscendC`
  — MULTIRANK_NAMESPACE_VIOLATION gate rejects).
- `spec.py` and `specs/` are REFERENCE fixtures, READ-ONLY — never Edit
  either. They encode the golden computation (incl. dtype/bitwidth choices such
  as fp32-vs-fp64 for quant/gmm); the baseline `specs/<op>.py` is re-staged
  over the provision copy on every provision, so any Edit is silently lost AND
  corrupts the precision baseline. Spec changes are owner-authored; if a task
  conflicts with the spec, surface it in your handoff (→ orchestrator: <the
  conflict>); do NOT "fix" the spec to match your kernel."""

    def kernel_cpp_dirs(self) -> tuple[str, ...]:
        return ("op_host", "op_kernel")

    def kernel_logic_files(self) -> tuple[str, ...]:
        return ("model_new_ascendc.py",)

    def ko_brief_phase_block(
        self, handoff_str: str = "", directive_str: str = ""
    ) -> Optional[str]:
        return f"""# PHASES (aog-kernel-optimizer — multirank backend){handoff_str}

**SCOPE — you optimize PERF via the canonical multirank entry points (run.py).**

A. **KB Manifest LOAD** — load (kb-root paths start at the plugin's kb/;
   the MC case is an official CANN doc under the plugin's docs/references/):
   - `src/scripts/orchestrator/plugins/multirank/docs/multirank_communication.md` P-P110/P-P111/P-P112
   - the target hardware spec doc
        (compute/comm dual-pipeline overlap principle)

B. **Read verification.json + perf data** (multirank perf is measured by multirank_runner
   `--perf`, flowing into verification.json.performance).

C. **Apply tuning** in `workspace/{{op}}/prj-{{op}}/op_kernel/<op>.h + <op>.cpp`
   (NEST layout). Each iter:
   1. Edit ONE axis
   2. `cd workspace/{{op}}/prj-{{op}} && python3 run.py build`
   3. `python3 run.py verify` (multirank_runner multi-card; ALL-rank PASS = PASS)
   4. `python3 run.py verify --perf` for the perf ratio
   5. msprof if perf metric ambiguous
   6. Compare against baseline → KEEP or REVERT

D. **Exit** when perf ≥ band or iter_cap exhausted with PLATEAU.

If precision regresses on ANY iter → REVERT immediately + log in
optimization_log.md. Do NOT use deploy_to_a5.sh / benchmark.py (single-card,
wrong for multirank)."""

    def kw_brief_fixed_layout_block(self) -> Optional[str]:
        return """# FIXED OUTPUT LAYOUT (Multirank: nest — C++ project under prj-<op>/)

**Directory structure (MANDATED)**: NEST layout — the msopgen C++
project lives at `workspace/{op}/prj-{op}/`; reference + convention files stay
at the `workspace/{op}/` root. Build install tree at
`workspace/{op}/prj-{op}/.install/`. All scratch (temp scripts, logs, probes)
goes under `workspace/{op}/prj-{op}/.tmp/` (never litter the op root).
`multirank_runner` probes `workspace/{op}/prj-{op}/.install` for `ASCEND_CUSTOM_OPP_PATH`.

`workspace/{op}/` root files (reference + convention):
  CLAUDE.md                 # convention entity (commands/products/constraints + python entrypoints); auto-loaded by CC
  model_new_ascendc.py      # canonical name (OL-160); loads _C.so via glob("prj-*/py_ext/_C*.so")
  model.py                  # orchestrator-provided (DO NOT modify)
  spec.py / golden/ / ref_runnable.json   # reference (provision: per-case golden tree)
  verification.json / knowledge_update.md / PROGRESS.md
  (the multi-rank verifier multirank_verify.py lives in the harness tree — multirank_runner
   executes it in place; never staged here, never worker-editable)

`workspace/{op}/prj-{op}/` files (msopgen C++ project + build):
  run.py                  # unified entry: build | verify | provision (thin, calls harness)
  op_kernel/
    <op>.h                  # kernel + INLINED HCCL tools
    <op>.cpp                # extern "C" __global__ __aicore__; KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_MIX_AIC_1_2); GetHcclContext<HCCL_GROUP_ID_0>
  op_host/
    <op>_tiling.h           # TilingData struct — Mc2InitTiling + Mc2CcTiling first 2 fields
    <op>_tiling.cpp         # TilingFunc + SetHcommCfg: FIXED HCCL resource-request profile
    <op>_def.cpp            # OpDef: this->MULTIRANK().HcclGroup({"group"}); AICore().SetTiling(<TilingFunc>)
  py_ext/
    ext_<op>.cpp            # torch::Dispatcher skeleton (aclnn{Op} via EXEC_NPU_CMD; worker authors per actual signature)
    __init__.py / setup.py / pytorch_npu_helper.hpp
  scripts/
    rename_aclnn_autogen.py   # aclnn->aclnnInner rename (scaffold-shipped; filter_build_warnings.py is harness-shared)
  cmake/ + CMakeLists.txt + CMakePresets.json + build.sh + framework/   # msopgen-generated, DO NOT modify

Hard rules:
- NEST layout: C++ project under `prj-{op}/`, reference/convention at root (mandated).
- `model_new_ascendc.py` at root, canonical (OL-160); `model_new_multirank.py` FORBIDDEN.
- NO external util directory.
- NO `op_kernel/arch35/` (port_a3 deliverable) / NO flat `kernel/` (single-card layout).
- HCCL linked transitively via nnopbase (msopgen CMakeLists); no separate HCCL step, do NOT vendor libhccl.so.
- TilingData first 2 fields MUST be Mc2InitTiling + Mc2CcTiling.
- ko / fo / probe iter editors MUST preserve every file kw produced.
"""

    def kw_brief_phase_block(
        self,
        *,
        op: str = "",
        workspace=None,
        iter_cap_remaining: int = 0,
        directive_text=None,
        handoff_from_prior_agent=None,
        env=None,
    ):
        """Multirank kernel-worker brief for PortA3Plugin to inject."""
        return f"""# Multirank compute-communication fusion kernel-worker

ONE AscendC kernel fusing compute + collective communication across NPUs
(world_size ≥ 1 — ws=1 is a legal degenerate path) — not a compute kernel
that calls a host-side collective.

**Read FIRST (binding):**
- `workspace/{{op}}/CLAUDE.md` — build/verify/provision conventions
  (auto-loaded; binding).
- `workspace/{{op}}/.source_arch22/` — the staged arch22 migration source
  (ops-nn snapshot, read-only; state `port_a3_source`). **This IS the
  structural authority for the port**: preserve the A3 source's algorithm,
  dataflow, block partition, pipelining, and in-kernel communication
  structure — whatever communication pattern and implementation route the
  source actually uses. Prefer keeping the source's API usage and the
  dataflow it forms; edit only the parts you identify as needing
  migration. Code that carries over cleanly is carried (same
  rule as the op_host CARRY-verbatim recipe); a translation unit that
  needs adaptation is re-emitted with the SAME structure, not redesigned.
  Adapt point-by-point for hardware differences only: includes, core-type
  conditionals, instruction/API availability, sync primitives, and the
  mapping of the A3 communication mechanism onto its A5-side path
  (P-P110 HCCL resource reuse). Swapping the source's implementation
  route for a different A5 idiom is an explicit migration decision that
  must be justified in the handoff BEFORE authoring — never a default.

**Phase A — KB LOAD** (grep-load; kb-root paths start at the plugin's kb/,
the MC case is an official CANN doc and lives under the plugin's
docs/references/ tree):
- `src/scripts/orchestrator/plugins/multirank/docs/sync_fundamentals.md` — MANDATORY.
- `src/scripts/orchestrator/plugins/multirank/docs/multirank_communication.md`
- Compute half: consult the OKF knowledge cards (knowledge-query) the
- brief loads for API usage and patterns. Init
  position is YOUR choice — do NOT assume a single fixed init.

**Phase A.5 — scaffold** (ONCE, before authoring): if `prj-{{op}}/` does NOT
exist, generate the msopgen template first — never re-run over an existing
`prj-{{op}}/` (the scaffold refuses to overwrite a worker-authored project):

`{self._scaffold_command(op, workspace)}`

(one `--input` / `--output` flag per kernel-signature entry, form
`name:dtype`; attrs default to group/rank_size/rank_id; `--out` is this op
workspace root. The scaffold fixes the HCCL resource-request profile —
`HCCL_CMD_ALLTOALLV` + `SetCommEngine(4)` — not configurable.)

{self._migration_knowledge_block(op, workspace)}

**Phase B — author** the kernel (`prj-{{op}}/op_kernel/<op>.h` + `<op>.cpp` +
root `model_new_ascendc.py`) via the CLAUDE.md entrypoints only. Tiling
registration 3-piece consistency → **OL-268**. HCCL tooling: inline the
`multirank/templates/` headers per P-P110/P-P111/P-P112.

**A-class fixed set (mandatory)**: HCCL integration + TilingData
header contract per `multirank_communication.md` P-P110 (InitV2 non-mandatory).
**The A-class fixed set and the KB locked items bind over every other note.**
Both the compute half and the communication structure follow the port
source (see the Read FIRST block); the free zone is limited to A5
hardware-mapping details (HCCL resource-reuse integration, event/sync
scheduling).

**Phase C — verify** MULTI-RANK via `multirank_runner` (single-process self-verify
FORBIDDEN — tests only the compute half, false PASS). ALL-rank PASS = PASS.

**Phase D — knowledge_update.md** (≥100 bytes: multirank fusion approach + pitfalls).

{self.kernel_author_constraints_block()}

Precision STUCK ≥4 iters → `@aog-precision-probe`. Perf below band →
`@aog-kernel-optimizer`. all-rank PASS + det PASS + perf ≥ band +
`knowledge_update.md` written → `→ orchestrator: done — <summary>`."""

    def pp_brief_phase_block(
        self, *, handoff_str: str = "", iter_cap: int = 0
    ) -> Optional[str]:
        return f"""# PHASES (aog-precision-probe — multirank backend){handoff_str}

A. **KB Manifest LOAD** — load (paths relative to the plugin's kb/ root):
   - `src/scripts/orchestrator/plugins/multirank/docs/sync_fundamentals.md`
   - `src/scripts/orchestrator/plugins/multirank/docs/multirank_communication.md` P-P110/P-P111/P-P112

B. **Read worker's verification.json + architecture.md + analysis.md +
   PROGRESS.md** to understand residual signature.

C. **Multirank-specific bisection** — MULTI-RANK reproduction is mandatory.
   Single-process self-verify (HCCL-null kernel) is FORBIDDEN.

   Build + verify via the canonical multirank entry points:
   - `cd workspace/{{op}}/prj-{{op}} && python3 run.py build`
   - `python3 run.py verify` (multirank_runner multi-process; lanes auto-picked
     per case; opp env auto-injected; ALL-rank PASS = PASS)
   - `python3 run.py verify --run-only` (diagnostic: output shape/nan/mean,
     skip golden compare)

   Do NOT use deploy_to_a5.sh / verification_ascendc.py (single-card, wrong for
   multirank).

D. **Classify** — write probe_report.md AND emit probe_result.json. Multirank-specific:
   - `bug` subclass `multirank-multicore-race` -> multi-core window write/read coherence
     gap (A-P61.5/.6); needs sync/coherence fix, NOT a numerical change
   - `bug` subclass `multirank-comm-flagid` -> CrossRankSync flagId back-to-back (P-P111)
   - `bug` subclass `multirank-reduce-precision` -> collective sum not fp32-promoted (P-P52)
   - `convention` -> single-rank probe artifact (re-run multi-rank)

E. **Exit** — write probe_report.md AND probe_result.json (standard op-gen
   probe contract; `deferred` verdict for infra-blocked runs).
"""

    def provision_reference(self, op: str, workspace: Path, state: dict):
        """O2.5 reference provision for multirank workspace.

        Delegated from PortA3Plugin via fsm_phase_o25_dispatch.
        """
        from . import multirank_phase_o25

        return multirank_phase_o25.provision(op, workspace, state)

    def resolve_truth_source_tier(self, workspace: Path) -> str:
        """Pick the multirank truth tier for this workspace.

        1. `a3_live` (default) — the source-side real C++ op, run on the
           OLD machine via the existing a3_live flow (repository build.sh
           in-container build + aclnn/wrapper execution); the model wraps it
           into the standard py interface for the harness to drive. CLI
           spelling: `--reference-source a3_live`.
        2. `npubench` — the multirank analogue of the single-card npubench
           reference path: the spec's `expected` (authored from the user's
           description, per the design guide) IS the reference
           implementation, and it executes on the A5 machine through the
           SAME multi-card launcher as the candidate (N processes per case,
           npu_probe card allocation) — reference and candidate share one
           environment, so both precision and the existing --perf A/B flow
           (multirank_runner --perf, reference as the baseline) apply
           unchanged. No source machine is needed. `expected` may freely
           use torch_npu `npu_*` NPU-only ops (they exist ONLY on NPU).
           CLI spelling: `--reference-source npubench`.

        The declaration comes from durable state (`multirank_truth_source`);
        provisioning fail-closes on a declared-but-missing reference instead
        of silently degrading tiers.
        """
        return read_truth_tier(workspace)

    def run_verification(self, workspace: Path, op: str):
        """O5 multi-rank verification.

        Delegated from PortA3Plugin via phase_o5.
        """
        from . import multirank_runner

        return multirank_runner.run_all_groups(
            multirank_runner.CampaignContext(workspace=workspace, op=op)
        )

    def should_run_phase_o5_perf_capture(self) -> bool:
        return True

    def verifier_canonical_filenames(self) -> tuple[str, ...]:
        return ("model_new_ascendc.py", "model.py")

    def verify_files(self) -> tuple[str, ...]:
        return ("multirank_verify.py",)

    def _migration_knowledge_block(self, op: str, workspace) -> str:
        """Shared single-card migration knowledge, injected into the
        multirank kw brief (design: "reuse + extend the port KB").

        Three pieces reused from the single-card port path:
        - the migration-level guide routing (`_migration_level_block` verbatim:
          reads op_classification, decides the L tier, lists the MUST-READ
          guides — missing signals degrade safely to L1 = the base guides);
        - the L-tier OL/EC/PB anchor lists (same IDs the single-card Phase
          A.1.5 cites — the worker self-classifies and cites what it loaded);
        - the cube-class routing (multirank flavor: no single-card
          architecture gate applies here, so this is a KB routing directive,
          not a gate threat — but a matmul-bearing fusion op organized as
          pure-VEC wastes the AIC half exactly the same way).
        """
        level_block = ""
        if workspace is not None:
            try:
                from briefs.kw_brief_pa3_phases import _migration_level_block

                level_block = _migration_level_block(op, workspace)
            except Exception:
                level_block = ""
        return f"""{level_block}

**L-tier OL/EC/PB anchors** — self-classify the port effort into
L1/L2/L3 (per the migration level above + the spec's compute semantics;
record the judgment + which trigger fired in knowledge_update.md), then
load and cite the corresponding anchors:
- L1: OL-142, EC-47, EC-48, EC-49, PB-29, PB-30, PB-31
- L2: above + OL-143, OL-144, OL-145 (if MX-format), OL-146, OL-147
      (if math-fn), OL-148 (if bounded-output), OL-152, P-P95, P-P96
- L3: L1 set + OL-150, OL-151, OL-152, PB-32

**Cube-class routing** — if the fused op's compute half contains matmul /
gmm-class cube work, the AIC half of the MIX is the point of the fusion:
organize
AIC(cube)/AIV(vector) per its scaffold BEFORE authoring; a pure-VEC
implementation of a cube-bearing op wastes the AIC half and will not hit
the perf band."""

    def _mr_runner_error_result(self, runner_error: str, method: str) -> dict:
        """Map a campaign runner_error to the perf-capture result."""
        import phase_o5 as _p5

        if _p5.classify_runner_error(runner_error) == "infra":
            return {
                "status": "PAUSE_RESOURCE",
                "reason": runner_error,
                "method": method,
            }
        return {
            "status": "N/A",
            "error": runner_error,
            "reason": runner_error,
            "na_kind": "MEASUREMENT_FAILED",
            "method": method,
        }

    def _mr_unverified_result(self, workspace, mr_res, method: str) -> "dict | None":
        """PAUSE_RESOURCE when card-shortage ws groups lack a coverage waiver."""
        import fsm_finalize_coverage

        if not mr_res.unverified_world_sizes:
            return None
        if fsm_finalize_coverage.coverage_accept_satisfied(
            workspace, mr_res.unverified_world_sizes
        ):
            return None
        det_parts = []
        for k, v in sorted(
            mr_res.unverified_world_sizes.items(), key=lambda kv: int(kv[0])
        ):
            det_parts.append(f"ws={k}: {v.get('detail', '')}")
        det = "; ".join(det_parts)
        return {
            "status": "PAUSE_RESOURCE",
            "reason": (
                f"multirank perf campaign: card-shortage world_sizes unverified — {det}"
            ),
            "method": method,
            "unverified_world_sizes": mr_res.unverified_world_sizes,
        }

    def _scaffold_command(self, op: str, workspace) -> str:
        """The worker-runnable scaffold CLI line for this op workspace."""
        plugin_root = Path(__file__).resolve().parents[6]
        script = (
            plugin_root / "engine/src/scripts/orchestrator/plugins/multirank/"
            "op_template_gen/multirank_msopgen_scaffold.py"
        )
        pascal = (
            "".join(part.capitalize() for part in op.split("_")) if op else "<OpName>"
        )
        out = workspace if workspace else "<workspace>"
        return (
            f"python3 {script} {pascal} "
            "--input <name>:<dtype> ... --output <name>:<dtype> ... "
            f"--out {out}"
        )


_INSTANCE = MultiRankPlugin()


def get_plugin_instance():
    return _INSTANCE


# Self-register at import time
from .. import register_plugin  # noqa: E402

register_plugin(_INSTANCE)
