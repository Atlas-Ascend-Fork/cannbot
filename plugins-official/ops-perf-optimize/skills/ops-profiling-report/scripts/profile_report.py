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

"""Consolidate specialist reports without importing tool usage or parsing raw formats."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import report_contract
from report_common import check_receipt, positive, read_json_with_receipt, require, roofline, write_report_files


def observed_alignment(request, inventory, index):
    """Expand only unambiguous runtime names observed in both captures."""
    case, src, dst = request["case_id"], request["runtime"], request["detail"]
    require(inventory is not None and src != dst, "alignment needs a source inventory and a different detail tool")
    require(isinstance(request.get("basis"), str) and request["basis"].strip(), "alignment needs a basis")
    require(len({(g["device"], g["pid"]) for g in inventory["kernels"]}) <= 1,
            "scope runtime-name alignment to one process and device")
    candidates = []
    for group in inventory["kernels"]:
        aliases = group.get("runtime_names", {})
        name = next(iter(aliases)) if len(aliases) == 1 else None
        detail = index.get((case, dst, name), [])
        scopes = {(r["specialist_report"]["path"], r.get("pid"), r.get("device")) for r in detail}
        matched = (name and aliases[name]["launches"] == group["launches"] and len(scopes) == 1
                   and group["device"] is not None and detail[0].get("device") == group["device"])
        candidates.append((group["name"], name if matched else None, aliases))
    uses = Counter(alias for _, _, aliases in candidates for alias in aliases)
    rows = []
    for original, name, aliases in candidates:
        target = name if name and uses[name] == 1 else None
        row = {"case_id": case, "names": {src: original, dst: target}, "basis": request["basis"]}
        if target:
            path, line = aliases[target]["first"]
            row["via"] = {"path": str(Path(inventory["collection_root"]) / path), "line": line}
        rows.append(row)
    return rows


def align_kernels(rows, measurements, inventory):
    """Resolve the agent's original names against the supplied captures."""
    index = defaultdict(list)
    for row in measurements:
        index[row["case_id"], row["provider"], row["kernel"]].append(row)
    observed = isinstance(rows, dict)
    if observed:
        rows = observed_alignment(rows, inventory, index)
    require(isinstance(rows, list), "kernel_alignment needs an observation request or a list of rows")
    result, assigned = [], set()
    for row in rows:
        require(isinstance(row, dict), "expected an alignment row")
        case, names, basis = row["case_id"], row["names"], row["basis"]
        require(isinstance(case, str) and case.strip(), "alignment needs a case ID")
        require(isinstance(names, dict) and len(names) >= 2 and any(names.values())
                and isinstance(basis, str) and basis.strip(), "alignment needs names and a basis")
        sources = {}
        for provider, name in names.items():
            if name is None:
                continue
            require(isinstance(name, str) and name, "use an original report name or null")
            key = (case, provider, name)
            if all(value is not None for value in names.values()):
                require(key not in assigned, f"ambiguous one-to-one alignment for {provider}: {name}")
                assigned.add(key)
            matches = index.get(key, [])
            require(matches and len({(r["specialist_report"]["path"], r.get("pid"), r.get("device"))
                                     for r in matches}) == 1,
                    f"alignment name missing or ambiguous in {case}/{provider}: {name}")
            first = matches[0]
            sources[provider] = {"launches": len(matches), "report": first["specialist_report"],
                                 "first": {"source": first["evidence"], "line": first["line"]}}
        entry = {"case_id": case, "names": names, "basis": basis, "sources": sources}
        if observed and "via" in row:
            entry["via"] = row["via"]
        result.append(entry)
    return result


def consolidate(reports, out, analysis=None):
    out = Path(out).resolve()
    children, measurements, invocations, limitations = [], [], [], []
    assessment = analysis or {}
    require(isinstance(assessment, dict), "analysis must be an object")
    alignment = assessment.get("kernel_alignment")
    inventory = None
    for source in reports:
        child, bound = read_json_with_receipt(source)
        if alignment is not None:
            require(all(c["report"] != bound for c in children), "duplicate specialist report in alignment")
        provider = child.get("provider")
        adapter = report_contract.report_adapter(provider)
        if not isinstance(child.get("measurements"), list):
            raise ValueError("specialist report needs normalized measurements")
        dependencies = list(child.get("evidence", []))
        dependencies.extend(row["evidence"] for row in child["measurements"] if row.get("evidence"))
        for path, digest in {(item["path"], item["sha256"]) for item in dependencies}:
            check_receipt({"path": path, "sha256": digest})
        validation = "receipts_only"
        if adapter is not None:
            check_output = getattr(adapter, "check_report_output", None)
            if check_output:
                check_output(child, out)
            verifier = getattr(adapter, "validate_report", None)
            if verifier:
                verifier(child)
                validation = "raw_verified"
        if isinstance(alignment, dict) and (child.get("case_id"), provider) == (
            alignment["case_id"],
            alignment["runtime"],
        ):
            require(inventory is None, "multiple runtime-name reports for the same case")
            overview = getattr(report_contract.backend(child), "overview", None)
            require(overview is not None, f"{provider} has no runtime-name inventory")
            inventory = overview(child)
        for row in child["measurements"]:
            measurements.append(
                {
                    **row,
                    "provider": provider,
                    "case_id": child.get("case_id"),
                    "identity": child.get("identity", {}),
                    "protocol": child.get("protocol", {}),
                    "specialist_report": bound,
                }
            )
        children.append(
            {
                "provider": provider,
                "report": bound,
                "status": child.get("status"),
                "validation": validation,
                "conditions": child.get("conditions", {}),
                "observations": child.get("observations", []),
            }
        )
        if child.get("invocation"):
            invocations.append({**child["invocation"], "provider": provider,
                                "case_id": child.get("case_id"), "identity": child.get("identity", {}),
                                "protocol": child.get("protocol", {}), "specialist_report": bound})
        limitations.extend(child.get("limitations", []))
        if child.get("status") not in ("diagnostic_valid", "valid"):
            limitations.append(
                f"{provider}: specialist report is {child.get('status')}"
            )
        conditions = child.get("conditions", {})
        for condition in ("npu_ownership",):
            supplied = conditions.get(condition)
            if not supplied or (
                isinstance(supplied, dict) and supplied.get("verified") is not True
            ):
                limitations.append(f"{provider}: {condition} evidence not supplied")
    if any(
        not isinstance(assessment.get(key, []), list)
        for key in ("findings", "recommendations")
    ):
        raise ValueError("findings/recommendations must be lists")
    result = {
        "schema_version": 1,
        "kind": "consolidated_profile_report",
        "status": (
            "valid"
            if measurements
            and all(
                child["status"] in ("diagnostic_valid", "valid") for child in children
            )
            and all(positive(r.get("duration_us")) for r in measurements)
            else "incomplete"
        ),
        "performance_eligible": False,
        "children": children,
        "measurements": measurements,
        "invocations": invocations,
        "findings": assessment.get("findings", []),
        "recommendations": assessment.get("recommendations", []),
        "limitations": list(dict.fromkeys(str(value) for value in limitations)),
        "aggregation": "sum within each selected invocation; keep tool protocols and launches separate",
    }
    if "kernel_alignment" in assessment:
        result["kernel_alignment"] = align_kernels(alignment, measurements, inventory)
    lines = ["# 性能分析报告", ""]
    if invocations:
        lines += ["| 工具 | case | 目标 launch 数 | Σkernel (us) |", "|---|---|---:|---:|"]
        lines += [
            f"| {r['provider']} | {r['case_id']} | {len(r['records'])} | {r['duration_us']} |" for r in invocations
        ]
        lines.append("")
    lines += [
        "| 工具 | case / kernel | 应用 device | 报告 device | 耗时(us) |",
        "|---|---|---:|---:|---:|",
    ]
    for row in measurements:
        label = str(row.get("kernel", "unknown")).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {row['provider']} | {row.get('case_id')} / {label} | "
            f"{row.get('application_device', '—')} | {row.get('device')} | {row.get('duration_us')} |"
        )
    if result.get("kernel_alignment"):
        rows = result["kernel_alignment"]
        providers = list(dict.fromkeys(p for row in rows for p in row["names"]))
        lines += ["", "## Kernel 对照", "", "| " + " | ".join(["用例", *providers, "对齐依据"]) + " |",
                  "|" + "---|" * (len(providers) + 2)]
        for row in rows:
            cells = [row["case_id"]]
            for provider in providers:
                source = row["sources"].get(provider)
                if source:
                    raw = source["first"]
                    cells.append(
                        f"[{row['names'][provider]} ×{source['launches']}](<{raw['source']['path']}>) L{raw['line']}"
                    )
                else:
                    cells.append("—")
            basis = row["basis"]
            if "via" in row:
                basis += f" · [任务原件](<{row['via']['path']}>) L{row['via']['line']}"
            cells.append(basis)
            lines.append("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in cells) + " |")
    for title, values in [
        ("分析", result["findings"]),
        ("设计与优化建议", result["recommendations"]),
        ("证据边界", result["limitations"]),
    ]:
        if values:
            lines.extend(["", "## " + title, ""])
            lines.extend(
                "- "
                + (
                    value
                    if isinstance(value, str)
                    else json.dumps(value, ensure_ascii=False)
                )
                for value in values
            )
    lines.extend(["", "专项报告："])
    lines.extend(
        f"- [{child['provider']}]({child['report']['path']})" for child in children
    )
    for child in children:
        if child["conditions"]:
            lines.append(f"- {child['provider']} 采集条件：" + json.dumps(child["conditions"], ensure_ascii=False))
    write_report_files(out, result, lines)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        action="append",
        required=True,
        help="one or more specialist report JSON files",
    )
    parser.add_argument(
        "--analysis",
        type=Path,
        help="Agent's evidence-based findings and design/optimization recommendations",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        analysis = json.loads(args.analysis.read_bytes()) if args.analysis else None
        result = consolidate(args.report, args.out, analysis)
    except (OSError, ValueError, KeyError) as error:
        print(json.dumps({"status": "failed", "reason": str(error)}))
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                "report": str(args.out.resolve() / "profile-report.json"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
