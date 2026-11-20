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

"""Evidence-linked experience extraction and review gate. No device execution.

Structural checks cannot establish causal truth or reviewer independence; an
independent content review is a separate input, bound to exact artifact bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

LEGACY_POLICY = {"id": "evidence_lessons_v1", "version": 1}
POLICY = {"id": "evidence_lessons_v2", "version": 2}
DIMENSIONS = ("conditions", "changes_costs", "evidence_reasoning", "decisions",
              "reproduction", "coverage_synthesis", "readability")
PLACEHOLDERS = {"todo", "tbd", "n/a", "待补", "待完善", "同上", "见附件", "unknown"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def file_ref(path):
    p = Path(path).resolve()
    return {"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def check_ref(ref):
    require(isinstance(ref, dict) and isinstance(ref.get("path"), str), "invalid file reference")
    p = Path(ref["path"])
    require(p.is_absolute() and p.is_file(), f"evidence is not an absolute file: {p}")
    require(file_ref(p)["sha256"] == ref.get("sha256"), f"evidence SHA mismatch: {p}")
    return p


def text(value, label):
    require(isinstance(value, str) and value.strip() and value.strip().lower() not in PLACEHOLDERS,
            f"missing substantive {label}")
    return value


def texts(value, label):
    require(isinstance(value, list) and bool(value), f"missing {label}")
    for item in value:
        text(item, label)


def validate_policy(value):
    require(isinstance(value, dict) and value in (LEGACY_POLICY, POLICY) and type(value.get("version")) is int,
            f"unsupported experience_policy: {value!r}")
    return value


def enabled(manifest):
    config = manifest.get("configuration", manifest)
    if "experience_policy" not in config:
        return False
    validate_policy(config["experience_policy"])
    return True


def pointer(document, value):
    require(isinstance(value, str) and (not value or value.startswith("/")), "invalid JSON pointer")
    node = document
    for part in value.split("/")[1:]:
        require(re.search(r"~(?:[^01]|$)", part) is None, "invalid JSON pointer escape")
        key = part.replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(node, list):
                require(re.fullmatch(r"0|[1-9][0-9]*", key) is not None,
                        "invalid JSON pointer array index")
            node = node[int(key)] if isinstance(node, list) else node[key]
        except (KeyError, IndexError, ValueError, TypeError) as error:
            raise ValueError(f"unresolved JSON pointer {value}") from error
    return node


def anchors(items, sources):
    require(isinstance(items, list) and items, "claim lacks evidence anchors")
    for item in items:
        require(isinstance(item, dict) and item.get("source") in sources, "unknown evidence source")
        path = Path(sources[item["source"]]["path"])
        require(("pointer" in item) != ("lines" in item), "anchor needs one pointer or line interval")
        if "pointer" in item:
            pointer(load(path), item["pointer"])
        else:
            span = item["lines"]
            require(isinstance(span, list) and len(span) == 2 and
                    all(type(i) is int for i in span), "invalid evidence line interval")
            require(1 <= span[0] <= span[1] <= len(path.read_text().splitlines()),
                    "evidence line interval out of bounds")


def expected_rounds(manifest_path):
    """Read the existing round ledger, never rewrite or hash mutable whole state."""
    p = Path(manifest_path).resolve().parent / "workflow-state.json"
    state = load(p)
    require(state.get("manifest", {}).get("sha256") == file_ref(manifest_path)["sha256"],
            "workflow state belongs to another manifest")
    found = {}
    for stage, entry in state.get("stages", {}).items():
        if not re.fullmatch(r"(?:gen\.)?round[1-9][0-9]*\.complete", stage):
            continue
        require(entry.get("status") == "complete", f"unfinished experience round: {stage}")
        refs = [r for r in entry.get("artifacts", []) if Path(r["path"]).name == "selection.json"]
        require(len(refs) == 1, f"round {stage} needs one recorded selection.json")
        check_ref(refs[0])
        found[stage] = refs[0]
    return found


def selection_outcome(selection):
    search = selection.get("search", {})
    outcome = search.get("outcome")
    if outcome in ("implementation_failed", "screened", "no_candidate"):
        require(selection.get("candidate_accepted") is not True, "failed candidate marked accepted")
        return outcome
    require(isinstance(selection.get("candidate_accepted"), bool), "selection lacks candidate_accepted")
    return "accepted" if selection["candidate_accepted"] else "rejected"


def validate_bundle(bundle_path, manifest_path):
    bundle_path, manifest_path = Path(bundle_path).resolve(), Path(manifest_path).resolve()
    b = load(bundle_path)
    require(type(b.get("schema_version")) is int and b["schema_version"] == 1, "unsupported experience bundle schema")
    require(check_ref(b.get("manifest")) == manifest_path, "experience manifest mismatch")
    text(b.get("producer"), "producer identity")
    context = b.get("context", {})
    for key in ("platform", "toolchain", "measurement", "time"):
        text(context.get(key), f"context.{key}")
    sources = b.get("sources")
    require(isinstance(sources, dict) and sources, "missing experience sources")
    dependencies = [str(bundle_path), str(manifest_path)]
    for name, ref in sources.items():
        text(name, "source id")
        dependencies.append(str(check_ref(ref)))
    expected = expected_rounds(manifest_path)
    rounds = b.get("rounds")
    require(isinstance(rounds, list), "rounds must be a list")
    ids = [r.get("stage") for r in rounds]
    require(len(ids) == len(set(ids)) and set(ids) == set(expected), "experience round coverage mismatch")
    for r in rounds:
        ref = sources.get(r.get("selection_source"), {})
        require(ref.get("path") == expected[r["stage"]]["path"] and
                ref.get("sha256") == expected[r["stage"]]["sha256"], "wrong round selection identity")
        selection = load(ref["path"])
        require(r.get("outcome") == selection_outcome(selection), "round outcome contradicts selection")
        performance = r.get("performance")
        original = selection.get("search", {}).get("effect_summary")
        if r["outcome"] in ("implementation_failed", "screened", "no_candidate"):
            require(performance is None, "unmeasured round cannot claim a performance ratio")
        elif original:
            require(isinstance(performance, dict), "measured round lacks candidate performance")
            source = sources.get(performance.get("source"), {})
            require(source.get("path") == original.get("path") and source.get("sha256") == original.get("sha256"),
                    "candidate performance must use the selection's actual candidate summary")
            summary = load(source["path"])
            actual = summary.get("effective_geomean_speedup")
            number = performance.get("geomean_speedup")
            require(type(number) in (int, float) and math.isfinite(number) and number > 0 and
                    type(actual) in (int, float) and math.isclose(number, actual, rel_tol=1e-12),
                    "performance ratio does not match source summary")
            require(type(performance.get("case_count")) is int and performance["case_count"] > 0 and
                    performance["case_count"] == summary.get("total_case_count"), "performance scope count mismatch")
            text(performance.get("comparison"), "performance comparison identity")
        else:
            require(performance is None, "unbound performance claim; supply selection.search.effect_summary")
            text(r.get("performance_unavailable_reason"), "performance evidence limitation")
    lessons = b.get("lessons")
    require(isinstance(lessons, list), "lessons must be a list")
    lesson_ids, covered = [], set()
    for lesson in lessons:
        lid = text(lesson.get("id"), "lesson id")
        lesson_ids.append(lid)
        text(lesson.get("title"), f"{lid}.title")
        stages = lesson.get("rounds")
        require(isinstance(stages, list) and stages and set(stages) <= set(expected), "lesson refers to unknown rounds")
        covered.update(stages)
        for key in ("problem", "change", "benefit", "cost", "decision", "retry_condition", "falsification"):
            text(lesson.get(key), f"{lid}.{key}")
        for key in ("applies_when", "does_not_apply", "invariants"):
            texts(lesson.get(key), f"{lid}.{key}")
        observations = lesson.get("observations")
        require(isinstance(observations, list) and observations, "lesson needs observed facts")
        for observation in observations:
            text(observation.get("statement"), "observation")
            anchors(observation.get("evidence"), sources)
        reasoning = lesson.get("reasoning", {})
        require(
            reasoning.get("status") in ("supported", "hypothesis", "unknown"), "reasoning needs an epistemic status"
        )
        text(reasoning.get("statement"), "reasoning statement")
        text(reasoning.get("unproven"), "reasoning limitation")
        anchors(reasoning.get("evidence"), sources)
        reproduction = lesson.get("reproduction", {})
        texts(reproduction.get("offline_steps"), "offline reproduction steps")
        text(reproduction.get("expected"), "expected observations")
        text(reproduction.get("requires_device"), "device-only validation boundary")
    require(len(lesson_ids) == len(set(lesson_ids)), "duplicate lesson ids")
    require(covered == set(expected), "some attempted rounds have no lessons")
    if not expected:
        text(b.get("no_attempt_reason"), "no-attempt explanation")
    texts(b.get("synthesis"), "cross-round synthesis")
    texts(b.get("limitations"), "global limitations")
    return b, list(dict.fromkeys(dependencies))


def render(b):
    """One structured source for prose and evidence, not a second manual summary."""
    out = ["# 性能优化经验原料", "", "这是有证据范围的经验原料，不代表独立硬件复跑或已确立知识。", ""]
    for key, label in (("platform", "平台"), ("toolchain", "工具链"), ("measurement", "测量口径"), ("time", "时间")):
        out += [f"- {label}：{b['context'][key]}"]
    out += ["", "## 实验结果", "", "| 轮次 | 处置 | 候选实测 |", "|---|---|---|"]
    for r in b["rounds"]:
        p = r.get("performance")
        result = f"{p['geomean_speedup']:.12g}×；{p['case_count']}例；{p['comparison']}" if p else "无可比候选实测"
        out += [f"| {r['stage']} | {r['outcome']} | {result} |"]
    for r in b["rounds"]:
        if r.get("performance_unavailable_reason"):
            out += ["", f"{r['stage']} 实测缺项：{r['performance_unavailable_reason']}"]
    if not b["rounds"]:
        out += ["", f"无完成尝试的原因：{b['no_attempt_reason']}"]

    def cite(items):
        parts = []
        for a in items:
            suffix = a.get("pointer") if "pointer" in a else f"L{a['lines'][0]}–L{a['lines'][1]}"
            parts.append(f"[{a['source']}]({b['sources'][a['source']]['path']}) `{suffix}`")
        return "；".join(parts)
    labels = {"problem": "问题", "change": "具体改法", "benefit": "减少的工作", "cost": "新增成本",
              "decision": "使用决策", "retry_condition": "重试前提", "falsification": "可观察的推翻条件"}
    for lesson in b["lessons"]:
        out += ["", f"## {lesson['id']}：{lesson['title']}", "", f"对应轮次：{', '.join(lesson['rounds'])}", ""]
        for key in ("problem", "change", "benefit", "cost"):
            out += [f"**{labels[key]}**：{lesson[key]}", ""]
        for key, label in (("applies_when", "适用前提"), ("does_not_apply", "不可直接推广的边界"), ("invariants", "保留的不变量")):
            out += [f"**{label}**", ""] + [f"- {v}" for v in lesson[key]] + [""]
        out += ["**事实与证据**", ""]
        for observation in lesson["observations"]:
            out += [f"- {observation['statement']}（{cite(observation['evidence'])}）"]
        reasoning = lesson["reasoning"]
        out += ["", f"**归因状态：{reasoning['status']}**。{reasoning['statement']}", "",
                f"尚未证明：{reasoning['unproven']}（{cite(reasoning['evidence'])}）", ""]
        for key in ("decision", "retry_condition", "falsification"):
            out += [f"**{labels[key]}**：{lesson[key]}", ""]
        reproduction = lesson["reproduction"]
        out += ["**离线复核**", ""] + [f"{i}. {v}" for i, v in enumerate(reproduction["offline_steps"], 1)]
        out += ["", f"预期：{reproduction['expected']}", "", f"仍需设备：{reproduction['requires_device']}"]
    out += ["", "## 跨轮经验", ""] + [f"- {v}" for v in b["synthesis"]]
    out += ["", "## 证据限制", ""] + [f"- {v}" for v in b["limitations"]]
    out += ["", "## 原始证据索引", ""]
    for name, ref in b["sources"].items():
        out += [f"- {name}：[原件]({ref['path']})；SHA256 `{ref['sha256']}`"]
    return "\n".join(out) + "\n"


def validate_review(review_path, bundle_path, material_path, b):
    review = load(review_path)
    require(type(review.get("schema_version")) is int and review["schema_version"] == 1,
            "unsupported experience review schema")
    require(review.get("bundle") == file_ref(bundle_path), "review belongs to different bundle bytes")
    require(review.get("material") == file_ref(material_path), "review belongs to different material bytes")
    reviewer = text(review.get("reviewer"), "reviewer identity")
    require(reviewer != b["producer"], "experience author cannot supply the independent review")
    text(review.get("method"), "independent review method and limits")
    require(review.get("critical_errors") == [], "critical experience errors remain")
    dimensions = review.get("dimensions", {})
    require(set(dimensions) == set(DIMENSIONS), "incomplete semantic rubric")
    total = 0
    for name, entry in dimensions.items():
        score = entry.get("score")
        require(type(score) is int and 3 <= score <= 4, f"semantic dimension {name} below 3/4")
        text(entry.get("reason"), f"{name} review reason")
        anchors(entry.get("evidence"), {**b["sources"], "material": file_ref(material_path)})
        total += score
    require(total / 28 * 100 >= 85, "semantic total below 85/100")
    probes = review.get("reader_tests")
    require(isinstance(probes, list) and len(probes) >= 4, "insufficient reader decision tests")
    categories, coverage, ids, points = set(), set(), set(), 0
    for probe in probes:
        pid = text(probe.get("id"), "reader test id")
        require(pid not in ids, "duplicate reader test id")
        ids.add(pid)
        require(probe.get("category") in ("apply", "reject", "retry", "uncertainty"), "invalid reader test category")
        categories.add(probe["category"])
        text(probe.get("question"), "reader question")
        text(probe.get("answer"), "reader answer")
        require(type(probe.get("score")) is int and 0 <= probe["score"] <= 2, "invalid reader score")
        require(probe.get("dangerous") is False, "dangerous reader recommendation")
        points += probe["score"]
        require(isinstance(probe.get("lesson_ids"), list) and
                (probe["lesson_ids"] or not b["lessons"]), "reader test lacks lesson coverage")
        coverage.update(probe["lesson_ids"])
        anchors(probe.get("evidence"), {**b["sources"], "material": file_ref(material_path)})
    require(categories == {"apply", "reject", "retry", "uncertainty"}, "reader tests lack decision diversity")
    require(coverage == {lesson["id"] for lesson in b["lessons"]}, "reader tests do not cover all lessons")
    require(points / (2 * len(probes)) >= 0.875, "reader decision score below 87.5%")
    return {"semantic_score": total / 28 * 100, "reader_score": points,
            "reader_max": 2 * len(probes), "reviewer": reviewer}


def validate_export(record_path, material_path, review_path, *, bundle=None, portable=False):
    record = load(record_path)
    require(record.get("experience_material") == file_ref(material_path),
            "reflux export belongs to different material bytes")
    require(record.get("experience_review") == file_ref(review_path),
            "reflux export belongs to different review bytes")
    card = check_ref(record.get("card"))
    dependencies = [str(Path(record_path).resolve()), str(card)]
    if portable:
        require(isinstance(record.get("portable_delivery"), dict), "reflux requires portable_delivery evidence")
        delivery = check_ref(record["portable_delivery"])
        from experience_portability import validate_delivery
        dependencies.extend(validate_delivery(delivery, bundle, material_path))
        contract = load(delivery)
        require((Path(contract["root"]) / contract["material_file"]).resolve() == card.resolve(),
                "reflux card differs from verified portable material")
    else:
        require(card.read_bytes().endswith(Path(material_path).read_bytes()),
                "reflux card must retain the complete reviewed material verbatim")
    return dependencies


def validate(bundle_path, manifest_path, *, material_path=None, review_path=None, reflux_path=None):
    b, dependencies = validate_bundle(bundle_path, manifest_path)
    result = {"status": "structure_pass", "round_count": len(b["rounds"]), "lesson_count": len(b["lessons"])}
    if material_path is not None:
        require(
            Path(material_path).read_text(encoding="utf-8") == render(b),
            "material differs from checked experience bundle",
        )
        dependencies.append(str(Path(material_path).resolve()))
    if review_path is not None:
        require(material_path is not None, "review requires the actual material")
        result.update(validate_review(review_path, bundle_path, material_path, b))
        dependencies.append(str(Path(review_path).resolve()))
        result["status"] = "pass"
    if reflux_path is not None:
        require(result["status"] == "pass", "reflux export requires an independent reviewed material")
        portable = load(manifest_path)["configuration"].get("experience_policy") == POLICY
        dependencies.extend(validate_export(reflux_path, material_path, review_path, bundle=b, portable=portable))
        result["portable_export_verified"] = portable
        result["public_semantic_review"] = "not_inherited_from_local_review" if portable else "not_checked"
        result["export_verified"] = True
    result["dependencies"] = [file_ref(p) for p in dependencies]
    result["limitations"] = (
        "File/field/coverage checks do not establish causal truth or independent hardware replication; "
        "semantic judgments remain the named reviewer's evidence-bound assessment."
    )
    return result


def integration_artifacts(files, manifest_path):
    if not enabled(load(manifest_path)):
        return []
    names = ("experience-lessons.json", "experience-material.md", "experience-review.json", "knowledge-reflux.json")
    require(
        all(n in files for n in names),
        "integration requires experience lessons, rendered material, independent review and knowledge-reflux record",
    )
    result = validate(files[names[0]], manifest_path, material_path=files[names[1]],
                      review_path=files[names[2]], reflux_path=files[names[3]])
    return [r["path"] for r in result["dependencies"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "render"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--material", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--reflux", type=Path, help="Bind the actual archived raw card to reviewed material")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "render":
            bundle, dependencies = validate_bundle(args.bundle, args.manifest)
            output = render(bundle)
        else:
            result = validate(args.bundle, args.manifest, material_path=args.material, review_path=args.review,
                              reflux_path=args.reflux)
            dependencies = [ref["path"] for ref in result["dependencies"]]
            output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        protected = {Path(p).resolve() for p in dependencies}
        protected.add(args.manifest.resolve().parent / "workflow-state.json")
        require(args.out.resolve() not in protected, "output would overwrite input")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
        print(json.dumps({"status": "written", "output": str(args.out.resolve())}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
