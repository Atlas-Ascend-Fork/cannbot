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

"""Sanitize and verify portable experience deliveries. Private plans stay local.

Public evidence is a derived snapshot, with original and exported hashes kept
distinct. This module never follows a URL or an original path during extraction.
"""
import hashlib
import argparse
import json
from pathlib import Path
import re

import rough_bundle

HASH = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
PERSONAL = re.compile(r"/home/|/Users/|[A-Za-z]:[\\/]+Users[\\/]|\b[a-z]\d{8}\b", re.I)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check_public(text, forbidden=()):
    require(not PERSONAL.search(text), "public export contains personal path/identifier")
    require(
        not any(value and value in text for value in forbidden), "public export contains private project identifier"
    )
    require(not re.search(r"\]\((?:/|file://|[A-Za-z]:[\\/])", text),
            "public export contains an absolute local citation")
    rough_bundle.reject_secrets(text)


def redact(text, replacements):
    # Only token/path substitutions, not prose rewrites or changed measurements.
    for old, new in sorted(replacements.items(), key=lambda pair: -len(pair[0])):
        require(len(old) >= 3 and not any(c.isspace() for c in old) and
                re.search(r"[A-Za-z]", old) is not None, "redaction must identify a path or literal token")
        require(new and "\n" not in new and "\r" not in new, "invalid redaction token")
        text = text.replace(old, new)
    return text


def sanitize_entries(entries, replacements, forbidden=()):
    """Rebind SHA references in dependency order; never mutate original bytes.

    Selected sources must form an acyclic hash-reference graph. Binary/external
    identities not selected remain historical hashes, not verified dependencies.
    """
    rough_bundle.validate_entries(entries)
    by_hash = {entry["sha256"]: entry for entry in entries}
    rewritten, active = {}, set()

    def visit(digest):
        if digest in rewritten:
            return rewritten[digest]
        require(digest not in active, "cyclic hash references in export selection")
        active.add(digest)
        text = redact(by_hash[digest]["text"], replacements)
        dependencies = set(HASH.findall(text)) & by_hash.keys()
        for dependency in dependencies:
            visit(dependency)
        text = HASH.sub(lambda match: rewritten[match[0]][1] if match[0] in rewritten else match[0], text)
        check_public(text, forbidden)
        rewritten[digest] = (text, sha(text.encode()))
        active.remove(digest)
        return rewritten[digest]

    output = []
    for entry in entries:
        text, digest = visit(entry["sha256"])
        name = redact(entry["name"], replacements)
        rough_bundle.safe_name(name)
        check_public(name, forbidden)
        output.append({"name": name, "text": text, "bytes": len(text.encode()),
                       "sha256": digest, "original_sha256": entry["sha256"]})
    rough_bundle.validate_entries(output)
    return output


def validate_delivery(contract_path, bundle, material_path):
    """Integration gate; contract is local/private, payload files are publishable.

    Contract fields: root, files(name->SHA), cards, replacements, forbidden_literals,
    source_entries(source ID->entry name), material_file, unavailable, review_scope.
    A source can be a regular file (entry name = file name) or a text-bundle entry.
    """
    contract_path = Path(contract_path)
    contract = json.loads(contract_path.read_text())
    require(contract.get("schema_version") == 1, "unsupported portable delivery schema")
    root = Path(contract["root"]).resolve()
    require(root.is_dir(), "portable delivery root missing")
    require(not contract_path.resolve().is_relative_to(root), "private delivery contract must stay outside public root")
    files = contract["files"]
    require(isinstance(files, dict) and files, "portable delivery files missing")
    forbidden = contract.get("forbidden_literals", [])
    replacements = contract["replacements"]
    resolved = {}
    for name, digest in files.items():
        rough_bundle.safe_name(name)
        path = root / name
        require(path.resolve().is_relative_to(root) and path.is_file(), "portable file missing or outside root")
        data = path.read_bytes()
        require(sha(data) == digest, "portable file SHA mismatch")
        check_public(data.decode("utf-8"), forbidden)
        resolved[name] = path
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    require(actual == set(files), "public root contains undeclared files")
    cards = contract.get("cards", [])
    require(len(cards) == len(set(cards)) and set(cards) <= files.keys(), "unknown or duplicate payload card")
    entries = rough_bundle.read_cards([resolved[name] for name in cards]) if cards else []
    entries += [{"name": name, "text": path.read_text(), "sha256": files[name], "bytes": path.stat().st_size}
                for name, path in resolved.items() if name not in cards]
    # read_text normalizes CRLF: identity verification always uses read_bytes.
    for entry in entries:
        if entry["name"] in resolved and entry["name"] not in cards:
            entry["text"] = resolved[entry["name"]].read_bytes().decode("utf-8")
    rough_bundle.validate_entries(entries)
    by_name = {entry["name"]: entry for entry in entries}
    rebinding = {}
    for entry in entries:
        check_public(entry["text"], forbidden)
        if "original_sha256" in entry:
            old = entry["original_sha256"]
            digest = entry["sha256"]
            require(rebinding.setdefault(old, digest) == digest, "conflicting sanitized source identities")
    mapping = contract["source_entries"]
    require(set(mapping) == set(bundle["sources"]), "portable delivery must cover every direct source")
    for key, original in bundle["sources"].items():
        digest = by_name[mapping[key]]["sha256"]
        old = original["sha256"]
        require(old not in rebinding or rebinding[old] == digest, "conflicting direct source identities")
        rebinding[old] = digest
    # Prove each public direct source is exactly the declared redaction of its
    # original, with hash references rebound to available derived snapshots.
    for key, original in bundle["sources"].items():
        entry = by_name[mapping[key]]
        data = Path(original["path"]).read_bytes()
        require(sha(data) == original["sha256"], "original source SHA mismatch")
        expected = HASH.sub(lambda m: rebinding.get(m[0], m[0]), redact(data.decode(), replacements))
        require(expected == entry["text"], "public source differs beyond declared redaction")
        require(
            entry.get("original_sha256", original["sha256"]) == original["sha256"], "original source lineage mismatch"
        )
    # Full reviewed prose survives, with only private tokens, hashes and evidence
    # links relocated. Its old semantic score is explicitly local-review-only.
    expected = redact(Path(material_path).read_bytes().decode(), replacements)
    expected = HASH.sub(lambda m: rebinding.get(m[0], m[0]), expected)
    for old, new in contract.get("links", {}).items():
        require(new in resolved, "public evidence link is outside declared files")
        expected = expected.replace("](" + old + ")", "](" + new + ")")
    public_material = resolved.get(contract["material_file"])
    require(public_material is not None, "public material is outside declared files")
    require(public_material.read_text().endswith(expected), "public material loses or changes reviewed experience")
    require(
        contract.get("review_scope") == "local_review_not_reused_as_public_review",
        "public export cannot inherit old semantic score",
    )
    require(isinstance(contract.get("unavailable"), list), "explicit unavailable dependencies required")
    return [str(contract_path.resolve()), *map(str, resolved.values())]


def sanitize_plan(plan, output):
    """Explicit selected-source plan; output contains no private substitution map."""
    require(not output.exists(), "sanitized output directory must not exist")
    require(not any(p.is_symlink() for p in [output, *output.parents]), "symlink output path")
    entries = []
    for source in plan["sources"]:
        data = Path(source["path"]).read_bytes()
        require(sha(data) == source["sha256"], "source SHA mismatch before sanitization")
        entries.append({"name": source["name"], "sha256": source["sha256"],
                        "bytes": len(data), "text": data.decode("utf-8")})
    public = sanitize_entries(entries, plan["replacements"], plan.get("forbidden_literals", []))
    require("sanitization-lineage.json" not in {entry["name"] for entry in public}, "reserved lineage name")
    output.mkdir(parents=True)
    lineage = []
    for entry in public:
        p = output / entry["name"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(entry["text"].encode())
        lineage.append({k: v for k, v in entry.items() if k != "text"})
    (output / "sanitization-lineage.json").write_text(json.dumps(lineage, ensure_ascii=False, indent=2) + "\n")
    return public


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sanitize")
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("check-delivery")
    p.add_argument("--contract", type=Path, required=True)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--material", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "sanitize":
            entries = sanitize_plan(json.loads(args.plan.read_text()), args.out)
            print(json.dumps({"status": "pass", "files": len(entries)}))
        else:
            dependencies = validate_delivery(args.contract, json.loads(args.bundle.read_text()), args.material)
            print(json.dumps({"status": "pass", "files": len(dependencies) - 1,
                              "scope": "portable source coverage and declared redaction; not a new semantic review"}))
    except (ValueError, OSError, KeyError, TypeError):
        # Errors from decoding sources can contain private text. Never echo them.
        raise SystemExit("portable export failed; inspect the private plan, hashes and redactions locally") from None
