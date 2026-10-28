#!/usr/bin/env python3
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
"""Check finite, explicitly expanded schedule obligations and bound evidence.

This is not a solver, source extractor, hardware simulator or synchronization proof.
Program submission order is deliberately NOT a completion dependency. Branches are
explicit scenarios; omitted branches, tasks and semantics remain review obligations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import namedtuple
from pathlib import Path

from validate_source_isolation import snapshot

from cli_output import emit

POLICY = {"id": "schedule_contract_v1", "version": 1}
LEVELS = ("model", "lowering", "runtime")
LIMITATIONS = [
    "Declared finite scenarios only; task/edge/branch completeness requires source review.",
    "Submission order does not establish completion or hardware overlap.",
    "Blocking scalar/API issue semantics are not simulated; coverage_review must bind a blocking_issue_review.",
    "Static reserved capacity; no dynamic allocation packing or timing prediction.",
    "Evidence hashes establish identity, not truth of generated-code or runtime reviews.",
    "No universal hardware safety or performance proof; selection uses the frozen performance policy.",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    value = json.loads(Path(path).read_text())
    require(isinstance(value, dict), f"object required: {path}")
    return value


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_identity(path):
    path = Path(path).resolve()
    return {
        "path": str(path),
        "sha256": hashlib.sha256(json.dumps(snapshot(path), sort_keys=True).encode()).hexdigest(),
    }


def policy_enabled(manifest):
    configuration = manifest.get("configuration", {})
    value = configuration.get("schedule_policy")
    request = manifest.get("request", {})
    if isinstance(request, dict) and request.get("path"):
        request_path = Path(request["path"])
        require(request_path.is_file(), "frozen request missing; cannot establish schedule policy")
        require(request.get("sha256") == sha(request_path), "frozen request identity changed")
        frozen = load(request_path)
        require(
            ("schedule_policy" in frozen) == ("schedule_policy" in configuration)
            and frozen.get("schedule_policy") == value,
            "schedule policy differs from frozen request",
        )
    if "schedule_policy" not in configuration:
        return False
    require(
        isinstance(value, dict) and value == POLICY and type(value.get("version")) is int, "unsupported schedule_policy"
    )
    return True


def ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha(path)}


def verify_ref(value, dependencies):
    require(isinstance(value, dict) and isinstance(value.get("path"), str), "file reference needs path and sha256")
    path = Path(value["path"])
    require(path.is_absolute() and path.is_file(), f"evidence must be an absolute existing file: {path}")
    actual = ref(path)
    require(value == actual, f"stale evidence SHA or noncanonical reference: {path}")
    dependencies[str(path.resolve())] = actual["sha256"]
    return path.resolve()


def refs(values, dependencies, label):
    require(isinstance(values, list) and values, f"{label} requires evidence references")
    return [verify_ref(v, dependencies) for v in values]


def unique(rows, label):
    require(isinstance(rows, list), f"{label} must be an array")
    result = {}
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"], f"{label} needs id")
        require(row["id"] not in result, f"duplicate {label} id: {row['id']}")
        result[row["id"]] = row
    return result


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, f"{label} must be integer >= {minimum}")
    return value


def _add_edge(graph, a, b):
    graph[a].add(b)


def _check_buffers(buffers, capacities):
    reserved = {}
    for bid, b in buffers.items():
        size = integer(b.get("bytes"), f"{bid}.bytes", 1)
        depth = integer(b.get("depth"), f"{bid}.depth", 1)
        alignment = integer(b.get("alignment"), f"{bid}.alignment", 1)
        require(size % alignment == 0, f"unaligned allocation: {bid}")
        require(b.get("memory") in capacities, f"missing capacity: {bid}")
        reserved[b["memory"]] = reserved.get(b["memory"], 0) + size * depth
        require(isinstance(b.get("initial_generations"), list), f"{bid} needs initial_generations (possibly empty)")
        for gen in b["initial_generations"]:
            integer(gen, f"{bid}.initial_generation")
        views = unique(b.get("views"), f"{bid}.views")
        require(views, f"{bid} needs physical views")
        for v in views.values():
            offset = integer(v.get("offset"), "view offset")
            length = integer(v.get("bytes"), "view bytes", 1)
            require(offset + length <= size, f"view exceeds allocation: {bid}/{v['id']}")
        for field in ("initialization", "drain"):
            require(isinstance(b.get(field), str) and b[field], f"{bid} needs {field} responsibility")
    return reserved


def _check_capacity(capacities, reserved):
    for memory, size in reserved.items():
        require(size <= integer(capacities[memory], f"capacity {memory}", 1), f"capacity exceeded: {memory}: {size}")


def _check_programs(programs, tasks):
    ordered = []
    for pid, p in programs.items():
        order = p.get("submission_order")
        require(isinstance(order, list) and len(order) == len(set(order)), f"invalid submission_order: {pid}")
        for tid in order:
            require(tid in tasks and tasks[tid].get("program") == pid, f"program task mismatch: {tid}")
        ordered.extend(order)
    require(len(ordered) == len(tasks) and set(ordered) == set(tasks), "programs must submit every task exactly once")


def _check_tasks(tasks, buffers, branches, resources, dependencies):
    accesses = {}
    for tid, t in tasks.items():
        require(t.get("resource") in resources, f"unknown resource: {tid}")
        require(isinstance(t.get("coordinates"), dict), f"task needs query/tile/subtile coordinates: {tid}")
        require(set(t["coordinates"]) == {"query", "tile", "subtile"}, f"task coordinates incomplete: {tid}")
        refs(t.get("source"), dependencies, f"task {tid} source")
        require(
            isinstance(t.get("completion_event"), str) and t["completion_event"],
            f"task completion event required: {tid}",
        )
        require(
            isinstance(t.get("branches"), list) and t["branches"] and set(t["branches"]) <= set(branches),
            f"task branch predicate required: {tid}",
        )
        accesses[tid] = []
        for mode in ("reads", "writes"):
            require(isinstance(t.get(mode), list), f"task {tid} needs {mode}")
            for a in t[mode]:
                require(a.get("buffer") in buffers, f"unknown physical buffer: {tid}")
                b = buffers[a["buffer"]]
                views = {v["id"]: v for v in b["views"]}
                require(a.get("view") in views, f"unknown physical view: {tid}")
                gen = integer(a.get("generation"), "access generation")
                v = views[a["view"]]
                accesses[tid].append((mode, a["buffer"], gen, gen % b["depth"], v["offset"], v["offset"] + v["bytes"]))
    return accesses


def _check_edges(edges, tasks, dependencies):
    require(isinstance(edges, list), "edges must be array")
    for edge in edges:
        require(edge.get("kind") in ("data", "resource", "reuse"), "edge must distinguish data/resource/reuse")
        require(edge.get("from") in tasks and edge.get("to") in tasks, "edge endpoint missing")
        require(
            edge.get("from_phase") == "complete" and edge.get("to_phase") == "start",
            "dependency requires completion -> start",
        )
        refs(edge.get("source"), dependencies, "edge source")


def _check_branch_decl(c, tasks, branch, branch_id):
    require(isinstance(branch.get("predicate"), str) and branch["predicate"], "branch needs predicate")
    require(isinstance(branch.get("case_ids"), list) and branch["case_ids"], "branch needs case_ids")
    require(set(branch["case_ids"]) <= set(c["scope"]["case_ids"]), "branch case outside scope")
    active = {tid for tid, t in tasks.items() if branch_id in t["branches"]}
    require(active, f"branch without tasks: {branch_id}")
    return active


def _branch_graph(active, programs, edges):
    graph = {f"{t}:{p}": set() for t in active for p in ("submit", "start", "complete")}
    for t in active:
        _add_edge(graph, t + ":submit", t + ":start")
        _add_edge(graph, t + ":start", t + ":complete")
    for p in programs.values():
        order = [t for t in p["submission_order"] if t in active]
        for a, b in zip(order, order[1:]):
            _add_edge(graph, a + ":submit", b + ":submit")
    for e in edges:
        if e["from"] in active and e["to"] in active:
            _add_edge(graph, e["from"] + ":complete", e["to"] + ":start")
    return graph


def _event_endpoints(e, tasks, active, eid):
    endpoints = {}
    for kind in ("publishes", "waits"):
        require(isinstance(e.get(kind), list), f"event needs {kind}")
        endpoints[kind] = []
        for row in e[kind]:
            require(row.get("task") in tasks, f"event endpoint unknown: {eid}")
            integer(row.get("tokens"), "event tokens", 1)
            require(row.get("pipe") == tasks[row["task"]]["resource"], f"event pipe mismatch: {eid}")
            if row["task"] in active:
                endpoints[kind].append(row)
    return endpoints


def _check_branch_events(events, tasks, active, branch_id, graph, dependencies):
    event_generations = {}
    for eid, e in events.items():
        generation = integer(e.get("generation"), f"event {eid} generation")
        require(isinstance(e.get("hardware_id"), str) and e["hardware_id"], "event hardware_id required")
        initial = integer(e.get("initial_tokens"), "initial_tokens")
        require(e.get("drain_tokens") == 0, "events must drain to zero tokens")
        refs(e.get("source"), dependencies, "event protocol source")
        endpoints = _event_endpoints(e, tasks, active, eid)
        pubs, waits = endpoints["publishes"], endpoints["waits"]
        require(
            initial + sum(x["tokens"] for x in pubs) == sum(x["tokens"] for x in waits),
            f"event token imbalance in {branch_id}: {eid}",
        )
        # Counter events are interpreted conservatively as a join. Partial-token
        # wakeups must be split into distinct event generations in this schema.
        for pub in pubs:
            for wait in waits:
                _add_edge(graph, pub["task"] + ":complete", wait["task"] + ":start")
        key = (e["hardware_id"], generation)
        require(key not in event_generations, "duplicate hardware event generation")
        first_generation = min(
            other["generation"] for other in events.values() if other["hardware_id"] == e["hardware_id"]
        )
        require(
            initial == 0 or generation == first_generation,
            "initial tokens may only initialize the first hardware event generation",
        )
        if pubs or waits:
            event_generations[key] = (pubs, waits)
    return event_generations


def _check_acyclic(graph, branch_id):
    indegree = {n: 0 for n in graph}
    for targets in graph.values():
        for n in targets:
            indegree[n] += 1
    queue = [n for n, d in indegree.items() if d == 0]
    count = 0
    while queue:
        n = queue.pop()
        count += 1
        for other in graph[n]:
            indegree[other] -= 1
            if not indegree[other]:
                queue.append(other)
    require(count == len(graph), f"dependency/wait cycle: {branch_id}")


def _reachable(graph, reach_cache, start):
    if start not in reach_cache:
        seen, pending = set(), list(graph[start])
        while pending:
            n = pending.pop()
            if n not in seen:
                seen.add(n)
                pending.extend(graph[n])
        reach_cache[start] = seen
    return reach_cache[start]


def _before(graph, reach_cache, a, b):
    return b + ":start" in _reachable(graph, reach_cache, a + ":complete")


def _check_resource_order(programs, tasks, active, resources, graph, reach_cache):
    for program in programs.values():
        for rid in resources:
            fifo = [t for t in program["submission_order"] if t in active and tasks[t]["resource"] == rid]
            for earlier, later in zip(fifo, fifo[1:]):
                require(
                    _before(graph, reach_cache, earlier, later),
                    f"resource FIFO contradicts submission order: {earlier}/{later}",
                )
    for rid in resources:
        rt = [t for t in active if tasks[t]["resource"] == rid]
        require(
            resources[rid].get("mode") == "exclusive",
            "only explicitly exclusive resources supported; split independent pipes",
        )
        for i, a in enumerate(rt):
            for b in rt[i + 1:]:
                require(
                    _before(graph, reach_cache, a, b) or _before(graph, reach_cache, b, a),
                    f"resource ordering missing: {rid}: {a}/{b}",
                )


def _producer_writes(flat, tid, a, graph, reach_cache):
    return [
        (wt, wa)
        for wt, wa in flat
        if wa[0] == "writes" and wa[1:4] == a[1:4] and wt != tid and _before(graph, reach_cache, wt, tid)
    ]


def _check_read_coverage(flat, tid, a, buffers, graph, reach_cache):
    mode, bid, gen, slot, lo, hi = a
    if mode == "reads" and gen not in buffers[bid]["initial_generations"]:
        writes = _producer_writes(flat, tid, a, graph, reach_cache)
        intervals = sorted((max(lo, wa[4]), min(hi, wa[5])) for _, wa in writes if wa[4] < hi and lo < wa[5])
        covered = lo
        for begin, end in intervals:
            if begin <= covered:
                covered = max(covered, end)
        require(covered >= hi, f"data producer/coverage missing: {tid}/{bid}/generation {gen}")


def _check_coverage(flat, buffers, graph, reach_cache):
    for tid, a in flat:
        _check_read_coverage(flat, tid, a, buffers, graph, reach_cache)


def _alias_skip(ta, tb, a, b):
    return ta == tb or a[1] != b[1] or a[3] != b[3] or a[4] >= b[5] or b[4] >= a[5] or (a[0] == b[0] == "reads")


def _check_alias_order(flat, graph, reach_cache):
    for i, (ta, a) in enumerate(flat):
        for tb, b in flat[i + 1:]:
            if _alias_skip(ta, tb, a, b):
                continue
            if a[2] == b[2]:
                require(
                    _before(graph, reach_cache, ta, tb) or _before(graph, reach_cache, tb, ta),
                    f"unordered physical alias access: {ta}/{tb}",
                )
            else:
                earlier, later = (ta, tb) if a[2] < b[2] else (tb, ta)
                require(
                    _before(graph, reach_cache, earlier, later),
                    f"reuse before last reader/writer: {earlier}/{later}",
                )


def _require_reuse_consumption(waits, next_pubs, hardware, graph, reach_cache):
    for w in waits:
        for p in next_pubs:
            require(
                _before(graph, reach_cache, w["task"], p["task"]),
                f"event id reused before consumption: {hardware}",
            )


def _check_event_reuse(event_generations, graph, reach_cache):
    for (hardware, generation), (pubs, waits) in event_generations.items():
        later = [(g, p) for (h, g), (p, _) in event_generations.items() if h == hardware and g > generation]
        if later:
            _, next_pubs = min(later)
            _require_reuse_consumption(waits, next_pubs, hardware, graph, reach_cache)


BranchModel = namedtuple(
    "BranchModel",
    ("c", "tasks", "programs", "resources", "accesses", "edges", "events", "buffers", "dependencies"),
)


def _check_branch(model, branch_id, branch):
    c, tasks, programs, resources, accesses, edges, events, buffers, dependencies = model
    active = _check_branch_decl(c, tasks, branch, branch_id)
    graph = _branch_graph(active, programs, edges)
    event_generations = _check_branch_events(events, tasks, active, branch_id, graph, dependencies)
    _check_acyclic(graph, branch_id)
    reach_cache = {}
    _check_resource_order(programs, tasks, active, resources, graph, reach_cache)
    flat = [(t, a) for t in active for a in accesses[t]]
    _check_coverage(flat, buffers, graph, reach_cache)
    _check_alias_order(flat, graph, reach_cache)
    _check_event_reuse(event_generations, graph, reach_cache)


def check_model(c, dependencies):
    tasks = unique(c["tasks"], "tasks")
    buffers = unique(c["buffers"], "buffers")
    programs = unique(c["programs"], "programs")
    branches = unique(c["branches"], "branches")
    resources = unique(c["resources"], "resources")
    require(
        tasks and programs and branches and resources, "expanded tasks/programs/branches/resources must be nonempty"
    )
    capacities = c["capacities"]
    require(isinstance(capacities, dict), "capacities must be object")
    reserved = _check_buffers(buffers, capacities)
    _check_capacity(capacities, reserved)
    _check_programs(programs, tasks)
    accesses = _check_tasks(tasks, buffers, branches, resources, dependencies)
    edges = c["edges"]
    _check_edges(edges, tasks, dependencies)
    events = unique(c["events"], "events")
    model = BranchModel(c, tasks, programs, resources, accesses, edges, events, buffers, dependencies)
    for branch_id, branch in branches.items():
        _check_branch(model, branch_id, branch)
    require(
        set().union(*(set(b["case_ids"]) for b in branches.values())) == set(c["scope"]["case_ids"]),
        "branch coverage missing scope cases",
    )
    return {"tasks": len(tasks), "branches": len(branches), "reserved_bytes": reserved}


def _check_integration_gate(gate_path, targets, seen, manifest_path, dependencies):
    """Validate one integrated postprocess gate against actual runtime evidence."""
    from validate_postprocess_performance import validate as validate_postprocess
    from summarize_performance_effects import summary_dependency_paths

    gate = load(gate_path)
    soc = gate.get("target_soc")
    require(soc in targets and soc not in seen, "integration postprocess target coverage invalid")
    seen.add(soc)
    paths = {k: (Path(v["baseline"]["path"]), Path(v["candidate"]["path"])) for k, v in gate["collections"].items()}
    errors = gate["collections"].get("functional", {}).get("expected_errors")
    hosts = gate["collections"].get("functional", {}).get("host_checks")
    baseline_failures = gate["collections"].get("functional", {}).get("baseline_failures")
    actual = validate_postprocess(
        manifest_path,
        soc,
        paths,
        functional_errors=(
            tuple(Path(errors[side]["evidence"]["path"]) for side in ("baseline", "candidate")) if errors else None
        ),
        functional_host_checks=(
            tuple(Path(hosts[side]["evidence"]["path"]) for side in ("baseline", "candidate")) if hosts else None
        ),
        functional_baseline_failures=(
            tuple(
                Path(baseline_failures[side]["evidence"]["path"])
                for side in ("baseline", "candidate")
            )
            if baseline_failures else None
        ),
        effect_evidence={k: [Path(p) for p in v] for k, v in gate.get("effect_evidence", {}).items()},
        same_implementation={k: Path(v) for k, v in gate.get("same_implementation", {}).items()},
    )
    require(actual == gate and gate["decision"] == "pass", "integration postprocess gate stale or failed")
    runtime_sources = {v["path"]: v["sha256"] for v in targets[soc]["runtime"]["source_artifacts"]}
    for item in gate["collections"].values():
        require(
            runtime_sources.get(item["candidate"]["path"]) == item["candidate"]["sha256"],
            "integration postprocess candidate CSV absent from actual runtime evidence",
        )
        for side in ("baseline", "candidate"):
            dependencies[item[side]["path"]] = sha(item[side]["path"])
        for raw in summary_dependency_paths(item["summary"]):
            dependencies[str(Path(raw).resolve())] = sha(raw)


def check_integration(e, c, manifest, manifest_path, dependencies):
    """Join actual integrated source/build/load identity to original full gates."""
    from validate_execution_identity import validate_document, dependency_paths

    integration = e["integration"]
    require(
        c["scope"]["collection"] in ("performance_full", "generalization_full"),
        "integration schedule requires full frozen scope",
    )
    identity_path = verify_ref(integration.get("execution_identity"), dependencies)
    document = load(identity_path)
    require(
        Path(document.get("source", {}).get("path", "")).resolve() == Path(c["candidate_root"]).resolve(),
        "integration execution source differs from schedule candidate root",
    )
    # Existing validator checks the recorded source snapshot live, built/loaded
    # hashes, build receipts and runtime source evidence. The original run input
    # stays immutable; this explicit view validates the integrated source.
    validate_document({"configuration": manifest["configuration"], "inputs": {"code": document["source"]}}, document)
    for raw in dependency_paths(document):
        dependencies[str(Path(raw).resolve())] = sha(raw)
    gates = refs(integration.get("postprocess_gates"), dependencies, "integration postprocess gates")
    targets = {t["target_soc"]: t for t in document["targets"]}
    seen = set()
    for gate_path in gates:
        _check_integration_gate(gate_path, targets, seen, manifest_path, dependencies)
    require(seen == set(c["scope"]["target_socs"]), "integration postprocess gates missing target SoCs")
    return {
        "execution_identity": ref(identity_path),
        "postprocess_gates": [ref(p) for p in gates],
        "source": document["source"],
    }


def _report_dependencies(contract_path, manifest_path):
    return {
        str(contract_path): sha(contract_path),
        str(manifest_path): sha(manifest_path),
        str(Path(__file__).resolve()): sha(__file__),
    }


def _report_contract(c, manifest, dependencies):
    require(
        c.get("schema_version") == 1 and c.get("kind") == "schedule-contract", "schedule contract schema/kind invalid"
    )
    require(isinstance(c.get("scheme_id"), str) and c["scheme_id"], "scheme_id required")
    scope = c.get("scope", {})
    require(scope.get("target_socs") == manifest["configuration"].get("target_socs"), "schedule target_socs mismatch")
    require(
        isinstance(scope.get("case_ids"), list)
        and scope["case_ids"]
        and len(scope["case_ids"]) == len(set(scope["case_ids"])),
        "unique scope case_ids required",
    )
    require(isinstance(scope.get("description"), str) and scope["description"], "scope description required")
    collection_name = scope.get("collection")
    require(
        collection_name in ("performance_tuning", "performance_full", "generalization_full"),
        "scope requires a frozen performance collection",
    )
    collection = manifest.get("collections", {}).get(collection_name)
    require(isinstance(collection, dict), "scope collection absent from manifest")
    collection_path = verify_ref({"path": collection.get("path"), "sha256": collection.get("sha256")}, dependencies)
    from prepare_case_sets import case_ids_from_collection

    require(
        set(scope["case_ids"]) == case_ids_from_collection(collection),
        "schedule case_ids must cover the exact frozen collection",
    )
    request = manifest.get("request", {})
    if request.get("path"):
        dependencies[str(Path(request["path"]).resolve())] = sha(request["path"])
    return scope


def _report_identities(c, dependencies):
    identities = c.get("identities", {})
    for key in ("baseline", "model", "compiler", "workload"):
        verify_ref(identities.get(key), dependencies)
    if identities.get("reference") is None:
        require(
            "reference" in identities
            and isinstance(c.get("reference_absence_reason"), str)
            and c["reference_absence_reason"],
            "absent reference needs explicit reason",
        )
    else:
        verify_ref(identities["reference"], dependencies)
    return identities


def _report_candidate_root(c, candidate):
    require(
        isinstance(c.get("candidate_root"), str) and Path(c["candidate_root"]).is_absolute(),
        "candidate_root must be absolute",
    )
    candidate_root = Path(c["candidate_root"]).resolve()
    if candidate is not None:
        require(candidate_root == Path(candidate).resolve(), "schedule candidate identity mismatch")
    return candidate_root


def _report_applicability(c, dependencies):
    app = c.get("applicability", {})
    require(
        isinstance(app.get("required"), bool) and isinstance(app.get("reason"), str) and app["reason"],
        "applicability decision/reason required",
    )
    refs(app.get("evidence"), dependencies, "applicability")
    features = app.get("features", {})
    require(
        set(features) == {"cross_tile", "multi_engine", "async_reuse"}
        and all(isinstance(v, bool) for v in features.values()),
        "explicit applicability trigger facts required",
    )
    require(app["required"] or not any(features.values()), "false applicability contradicts trigger facts")
    return app


def _report_model(c):
    model = c.get("model", {})
    require(
        isinstance(model.get("version"), str)
        and model["version"]
        and isinstance(model.get("boundaries"), list)
        and model["boundaries"],
        "model version and explicit boundaries required",
    )
    return model


def _report_unknowns(c, dependencies):
    unknowns = c.get("unknowns")
    require(isinstance(unknowns, list), "unknowns array required")
    critical = []
    for item in unknowns:
        require(
            item.get("kind") in ("safety", "performance")
            and isinstance(item.get("question"), str)
            and item["question"],
            "unknown needs kind/question",
        )
        require(item.get("status") in ("open", "resolved"), "unknown status invalid")
        if item["status"] == "resolved":
            refs(item.get("evidence"), dependencies, "resolved unknown")
        elif item["kind"] == "safety":
            critical.append(item["question"])
    return unknowns, critical


def _report_review(c, dependencies):
    review = c.get("coverage_review", {})
    require(isinstance(review.get("complete"), bool), "coverage_review.complete boolean required")
    refs(review.get("evidence"), dependencies, "coverage review")
    refs(review.get("blocking_issue_review"), dependencies, "blocking issue/API review")
    return review


def _report_checked(c, app, dependencies):
    errors, checked = [], {}
    if app["required"]:
        try:
            checked = check_model(c, dependencies)
        except (ValueError, KeyError, TypeError) as error:
            errors.append(str(error))
    return errors, checked


def _report_evidence(
    evidence_path,
    status,
    contract_path,
    manifest_path,
    scope,
    identities,
    candidate_root,
    dependencies,
):
    require(status == "ready_for_implementation", "only reviewed model with resolved safety unknowns can advance")
    require(evidence_path is not None, "lowering/runtime evidence required")
    evidence_path = Path(evidence_path).resolve()
    dependencies[str(evidence_path)] = sha(evidence_path)
    e = load(evidence_path)
    require(e.get("schema_version") == 1 and e.get("contract") == ref(contract_path), "evidence contract SHA mismatch")
    require(e.get("manifest") == ref(manifest_path), "evidence manifest SHA mismatch")
    require(e.get("candidate") == source_identity(candidate_root), "candidate source SHA mismatch")
    require(e.get("scope") == scope, "evidence branch/case/SoC scope mismatch")
    require(e.get("compiler") == identities["compiler"], "compiler/build identity mismatch")
    # The source snapshot is checked live, and included in the saved report.
    lower = e.get("lowering", {})
    for key in ("generated_code", "build", "task_mapping", "event_mapping", "last_reader_review"):
        refs(lower.get(key), dependencies, f"lowering.{key}")
    require(lower.get("status") == "pass", "lowering review did not pass")
    return evidence_path, e, "lowering_verified"


def _runtime_expected(c, scope):
    branches = c.get("branches", [])
    expected = set()
    for branch in branches:
        for case in branch["case_ids"]:
            for soc in scope["target_socs"]:
                expected.add((case, soc, branch["id"]))
    if not branches:
        expected = {(case, soc, None) for case in scope["case_ids"] for soc in scope["target_socs"]}
    return expected


def _report_runtime(e, c, scope, dependencies):
    runtime = e.get("runtime", {})
    require(runtime.get("status") == "pass", "runtime acceptance did not pass")
    for key in ("load", "execution", "precision", "sequence_stress"):
        refs(runtime.get(key), dependencies, f"runtime.{key}")
    require(
        runtime.get("covered_branches") == [b["id"] for b in c.get("branches", [])], "runtime branch coverage mismatch"
    )
    coverage = runtime.get("coverage")
    require(isinstance(coverage, list), "runtime requires per-case/SoC/branch coverage")
    expected = _runtime_expected(c, scope)
    observed = set()
    for row in coverage:
        key = (row.get("case_id"), row.get("target_soc"), row.get("branch"))
        require(
            key in expected and key not in observed, "runtime coverage missing/duplicate/out-of-scope case/SoC/branch"
        )
        observed.add(key)
        refs(row.get("evidence"), dependencies, "runtime case/SoC/branch evidence")
    require(observed == expected, "runtime coverage missing case/SoC/branch")
    return "eligible"


def build_report(contract_path, manifest_path, level="model", evidence_path=None, candidate=None):
    require(level in LEVELS, "unknown evidence level")
    contract_path, manifest_path = Path(contract_path).resolve(), Path(manifest_path).resolve()
    c, manifest = load(contract_path), load(manifest_path)
    require(policy_enabled(manifest), "schedule checker requires explicit frozen schedule_policy")
    dependencies = _report_dependencies(contract_path, manifest_path)
    scope = _report_contract(c, manifest, dependencies)
    identities = _report_identities(c, dependencies)
    candidate_root = _report_candidate_root(c, candidate)
    app = _report_applicability(c, dependencies)
    model = _report_model(c)
    unknowns, critical = _report_unknowns(c, dependencies)
    review = _report_review(c, dependencies)
    errors, checked = _report_checked(c, app, dependencies)
    status = (
        "MODEL_REJECTED"
        if errors
        else "needs_probe" if critical else "ready_for_implementation" if review["complete"] else "MODEL_FEASIBLE"
    )
    e = None
    if level != "model":
        evidence_path, e, status = _report_evidence(
            evidence_path, status, contract_path, manifest_path, scope, identities, candidate_root, dependencies
        )
        if level == "runtime":
            status = _report_runtime(e, c, scope, dependencies)
    report = {
        "schema_version": 1,
        "kind": "schedule-check",
        "scheme_id": c["scheme_id"],
        "level": level,
        "status": status,
        "decision": "pass" if status in ("ready_for_implementation", "lowering_verified", "eligible") else "fail",
        "contract": ref(contract_path),
        "manifest": ref(manifest_path),
        "candidate_root": str(candidate_root),
        "evidence": ref(evidence_path) if evidence_path else None,
        "scope": scope,
        "dependencies": dependencies,
        "checked": checked,
        "errors": errors,
        "unknowns": unknowns,
        "limitations": LIMITATIONS + model["boundaries"],
    }
    if level != "model":
        report["candidate"] = source_identity(candidate_root)
        if level == "runtime" and "integration" in e:
            report["integration"] = check_integration(e, c, manifest, manifest_path, dependencies)
    return report


def verify_report(path, manifest_path, minimum="model", candidate=None):
    saved = load(path)
    require(saved.get("kind") == "schedule-check" and saved.get("level") in LEVELS, "schedule-check report required")
    require(LEVELS.index(saved["level"]) >= LEVELS.index(minimum), f"schedule requires {minimum} evidence")
    require(saved.get("manifest") == ref(manifest_path), "schedule report belongs to another manifest")
    evidence = saved.get("evidence")
    current = build_report(
        saved["contract"]["path"],
        manifest_path,
        saved["level"],
        evidence["path"] if evidence else None,
        candidate,
    )
    require(saved == current, "stale or misattributed schedule report")
    require(current["decision"] == "pass", f"schedule not ready: {current['status']}")
    return current


def validate_implementation_schedule(contract, result, manifest_path, candidate):
    manifest = load(manifest_path)
    if not policy_enabled(manifest):
        require(
            "schedule" not in contract and "schedule" not in result, "schedule fields require frozen schedule_policy"
        )
        return None
    deps = {}
    schedule = contract.get("schedule", {})
    cp = verify_ref(schedule.get("contract"), deps)
    mp = verify_ref(schedule.get("check"), deps)
    model = verify_report(mp, manifest_path, "model", candidate)
    require(
        model["contract"] == ref(cp) and model["scheme_id"] == contract["scheme_id"], "model schedule scheme mismatch"
    )
    rp = verify_ref(result.get("schedule", {}).get("check"), deps)
    runtime = verify_report(rp, manifest_path, "runtime", candidate)
    require(
        runtime["contract"] == ref(cp) and runtime["scheme_id"] == contract["scheme_id"],
        "runtime schedule scheme mismatch",
    )
    return {"model": ref(mp), "runtime": ref(rp), "report": runtime}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--level", choices=LEVELS, default="model")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--candidate", type=Path)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--out", type=Path)
    output.add_argument("--verify-existing", type=Path)
    args = parser.parse_args()
    try:
        report = build_report(args.contract, args.manifest, args.level, args.evidence, args.candidate)
        if args.verify_existing:
            require(load(args.verify_existing) == report, "stale or misattributed schedule report")
        else:
            from validate_implementation_conformance import atomic_write

            atomic_write(args.out, report)
        emit(json.dumps(report, ensure_ascii=False))
        return 0 if report["decision"] == "pass" else 1
    except (ValueError, OSError, KeyError, TypeError) as error:
        emit(json.dumps({"decision": "fail", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
