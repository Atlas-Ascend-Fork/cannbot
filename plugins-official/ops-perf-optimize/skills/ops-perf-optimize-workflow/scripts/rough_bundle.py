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

"""Portable UTF-8 evidence inside ordinary rough cards; never executes payloads.

pack consumes a local explicit allowlist. check/extract read only supplied cards.
The JSON envelope is payload, not a new repository shelf or knowledge label.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

ISO = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
PATTERNS = [re.compile(pattern, re.I) for pattern in (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?:token|passwd|password|secret|api_?key)\w*\s*[=:]\s*[\"']?[A-Za-z0-9+/_\-.]{16,}",
    r"(?:gh[pousr]_|glpat-|sk-proj-|sk-ant-|xox[baprs]-)[A-Za-z0-9_-]{16,}",
    r"authorization:\s*\S{16,}", r"\bbearer\s+[A-Za-z0-9._-]{20,}")]


def check_card(path):
    text = path.read_text(encoding="utf-8")
    require(text.startswith("---\n"), "missing rough frontmatter")
    front, body = text[4:].split("---\n", 1)
    fields = dict(line.split(": ", 1) for line in front.splitlines() if ": " in line)
    require(
        all(fields.get(k) for k in ("source", "time", "account", "submitted", "content_sha256")), "missing rough fields"
    )
    require(ISO.fullmatch(fields["time"]) and ISO.fullmatch(fields["submitted"]), "invalid rough timestamp")
    require(
        re.fullmatch(r"r-" + re.escape(fields["account"]) + r"-\d{4}\.md", path.name), "rough account/name mismatch"
    )
    require(sha(body.encode()) == fields["content_sha256"], "rough body checksum mismatch")


MARKER = "\n<!-- rough-bundle-v1 -->\n```json\n"
END = "\n```\n<!-- /rough-bundle-v1 -->\n"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def safe_name(value):
    require(isinstance(value, str) and value and "\\" not in value,
            "invalid relative payload path")
    p = PurePosixPath(value)
    require(not p.is_absolute() and all(x not in ("", ".", "..") for x in value.split("/")),
            "unsafe payload path")
    require(not any(ord(c) < 32 for c in value), "control character in payload path")
    return value


def reject_secrets(text):
    for line in text.splitlines():
        require(not any(p.search(line) for p in PATTERNS),
                "payload matches redline; review locally (content not printed)")


def pack(plan, output):
    """Plan is local-only: {account, time, title, sources:[path,name,sha256]}."""
    require(re.fullmatch(r"[a-z0-9_-]+", plan["account"]), "invalid account")
    require(ISO.fullmatch(plan["time"]), "invalid source time")
    require(output.name.startswith("r-" + plan["account"] + "-"), "card account mismatch")
    require(not output.exists(), "refuse to replace an existing card")
    entries = []
    for ref in plan["sources"]:
        path = Path(ref["path"])
        data = path.read_bytes()
        require(sha(data) == ref["sha256"], "source SHA mismatch")
        text = data.decode("utf-8")
        require("\x00" not in text, "binary payload is not supported")
        from experience_portability import check_public
        check_public(text)
        reject_secrets(text)
        entries.append({"name": safe_name(ref["name"]), "sha256": sha(data),
                        "bytes": len(data), "text": text,
                        **({"original_sha256": ref["original_sha256"]} if "original_sha256" in ref else {})})
    validate_entries(entries)
    payload = json.dumps({"schema_version": 1, "files": entries}, ensure_ascii=False, indent=2)
    body = ("# " + plan["title"] + "\n\n"
            "UTF-8 发布文本包；JSON text 解码后恢复发布副本字节，sha256 校验发布身份。\n"
            "脱敏条目的 original_sha256 仅标识私有原件，不代表原件可下载或与发布字节相同。\n"
            "包内 name 相对提取目录；出处令牌不会被提取器当成本地路径打开。\n"
            "此卡仅提供原料，不代表新设备观测或知识确立。可用标准 JSON 解析器读取 files，"
            "或使用性能工作流 scripts/rough_bundle.py check/extract。\n"
            + MARKER + payload + END)
    check_public(body)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = (f"---\nsource: portable-rough-bundle/v1\ntime: {plan['time']}\n"
              f"content_sha256: {sha(body.encode())}\naccount: {plan['account']}\n"
              f"submitted: {now}\n---\n")
    output.write_text(header + body, encoding="utf-8")
    check_card(output)


def validate_entries(entries):
    require(isinstance(entries, list) and entries, "empty evidence bundle")
    seen = set()
    for entry in entries:
        name = safe_name(entry["name"])
        require(name not in seen, "duplicate payload path")
        seen.add(name)
        data = entry["text"].encode("utf-8")
        require(len(data) == entry["bytes"] and sha(data) == entry["sha256"],
                "payload SHA/length mismatch")
        if "original_sha256" in entry:
            require(isinstance(entry["original_sha256"], str) and
                    re.fullmatch(r"[0-9a-f]{64}", entry["original_sha256"]),
                    "invalid original SHA")
        require("\x00" not in entry["text"], "binary payload is not supported")
        reject_secrets(entry["text"])
    return entries


def read_cards(cards):
    entries = []
    for card in cards:
        check_card(card)
        text = card.read_text(encoding="utf-8")
        require(text.count(MARKER) == 1 and text.endswith(END), "invalid bundle framing")
        payload = json.loads(text.split(MARKER, 1)[1][:-len(END)])
        require(payload["schema_version"] == 1, "unsupported bundle version")
        entries.extend(payload["files"])
    return validate_entries(entries)


def extract(cards, output):
    entries = read_cards(cards)  # validate the entire set before writing anything
    require(not output.exists(), "extraction directory must not exist")
    # Disallow symlink ancestors; do not follow a pre-existing route outside the target.
    require(not any(p.is_symlink() for p in [output, *output.parents]), "symlink output path")
    output.mkdir(parents=True)
    for entry in entries:
        p = output / entry["name"]
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("xb") as stream:
            stream.write(entry["text"].encode("utf-8"))
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pack")
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    for command in ("check", "extract"):
        p = sub.add_parser(command)
        p.add_argument("cards", type=Path, nargs="+")
        if command == "extract":
            p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "pack":
            pack(json.loads(args.plan.read_text()), args.out)
            entries = read_cards([args.out])
        elif args.command == "extract":
            entries = extract(args.cards, args.out)
        else:
            entries = read_cards(args.cards)
        print(json.dumps({"status": "pass", "files": len(entries),
                          "bytes": sum(x["bytes"] for x in entries)}))
    except (ValueError, OSError, KeyError, TypeError):
        # Source text/credentials may occur in decoding and parsing errors.
        print("bundle operation failed; check schema, hashes, paths and redline locally", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
