#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------
"""基线/标杆指纹：记录并校验「同口径」的物质基础。

用法：
  python3 tools/check_provenance.py <model_id> --write                 # 记录到 config/provenance.json
  python3 tools/check_provenance.py <model_id> --merge FILE            # 并入 baseline_metadata.json，同时写 config/provenance.json
  python3 tools/check_provenance.py <model_id> [--baseline FILE] [--declare F1,F2]
  python3 tools/check_provenance.py <model_id> --declare model_sha256  # 声明「本轮预期改动」后再比对

指纹分两类（这是与优化动作共存的关键）：
  frozen  ：input_sha256、golden_sha256 —— 非实验变量，任何变化都判口径漂移（exit 1）；
  declared：model_sha256、shape_config_sha256、io_config_sha256 —— 预期实验变量
            （换模型 / 改 shape / 改 io 配置本就是要做的优化动作），变化时必须用
            --declare 显式声明，输出可直接粘进报告的 before/after 记录。
退出码：0 通过；1 口径漂移（frozen 变化，或 declared 变化但未声明）；2 尚未建立基线指纹。
"""


import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

CHUNK = 1 << 20
SKIP_SUFFIX = {".log", ".tmp", ".pyc"}
# 非实验变量：变了就是换了题，不得再声称同口径
FROZEN_FIELDS = ("input_sha256", "golden_sha256")
# 预期实验变量：优化动作本身会改（换模型 / 改 shape / 改 io 配置），变化须显式声明
DECLARED_FIELDS = ("model_sha256", "shape_config_sha256", "io_config_sha256")
ALL_FIELDS = FROZEN_FIELDS + DECLARED_FIELDS


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(paths):
    """对一组文件做稳定聚合哈希：按相对路径排序后逐项计入 (相对路径, 文件哈希)。"""
    items = []
    for path in sorted(paths, key=lambda p: str(p)):
        if not path.is_file() or path.suffix in SKIP_SUFFIX:
            continue
        items.append("%s:%s" % (path.name, sha256_file(path)))
    if not items:
        return None
    return hashlib.sha256("\n".join(items).encode("utf-8")).hexdigest()


def collect(model_id):
    root = Path(C.model_dir(model_id))
    cfg = root / "config"
    result = {
        "model_sha256": sha256_tree((root / "model").glob("*")),
        "input_sha256": sha256_tree((root / "input_data").glob("*")),
        "golden_sha256": sha256_tree((root / "reference").glob("*")),
        "shape_config_sha256": sha256_file(cfg / "shape_config.json") if (cfg / "shape_config.json").exists() else None,
        "io_config_sha256": sha256_file(cfg / "io_config.json") if (cfg / "io_config.json").exists() else None,
    }
    return result


def load_recorded(path):
    data = C.read_json(path)
    if isinstance(data, dict) and "fingerprints" in data:
        data = data["fingerprints"]
    if not isinstance(data, dict):
        raise SystemExit("[ERROR] 指纹文件必须是对象，或含 fingerprints 段的对象：%s" % path)
    return data


def _resolve_merge_path(raw):
    path = Path(raw)
    if path.exists():
        return path
    # 允许写相对 GE_SESSION_DEMO 根的路径（如在任意 CWD 下写 ../data/<model>/baseline/...）
    candidate = Path(C.demo_root()) / raw
    if candidate.exists():
        return candidate
    raise SystemExit(
        "[ERROR] --merge 目标不存在：%s（也试过 %s）\n"
        "        路径相对当前目录；在 GE_SESSION_DEMO 下执行时数据目录通常是 "
        "../data/<model_name>/baseline/baseline_metadata.json" % (raw, candidate))


def _parse_declare(raw):
    if not raw:
        return set()
    fields = [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]
    unknown = [f for f in fields if f not in DECLARED_FIELDS]
    if unknown:
        raise SystemExit(
            "[ERROR] --declare 只接受预期实验变量 %s；%s 属于非实验变量，不允许声明变更"
            % (", ".join(DECLARED_FIELDS), ", ".join(unknown)))
    return set(fields)


def main():
    ap = argparse.ArgumentParser(description="baseline/golden provenance fingerprints")
    ap.add_argument("model_id")
    ap.add_argument("--write", action="store_true", help="记录当前指纹到 config/provenance.json")
    ap.add_argument("--baseline", default=None,
                    help="对比/写入指定指纹文件（默认 config/provenance.json；也可指向 baseline_metadata.json）")
    ap.add_argument("--merge", default=None, metavar="FILE",
                    help="把当前指纹并入指定 JSON 的 fingerprints 段（保留其余字段），同时写 config/provenance.json")
    ap.add_argument("--declare", default=None, metavar="F1,F2",
                    help="声明本轮预期改动的实验变量（%s），声明后才允许判通过" % ",".join(DECLARED_FIELDS))
    args = ap.parse_args()

    model_id = C.normalize_model_id(args.model_id)
    root = Path(C.model_dir(model_id))
    record_path = root / "config" / "provenance.json"
    target = Path(args.baseline) if args.baseline else record_path
    current = collect(model_id)
    missing = [name for name, value in current.items() if value is None]
    if missing:
        print("[provenance][WARN] 以下指纹缺失（对应目录/文件不存在）：%s" % ", ".join(missing))

    if args.write:
        target.parent.mkdir(parents=True, exist_ok=True)
        C.write_json(target, current)
        print("[provenance] wrote %s" % C.rel_to_root(target))
        for name, value in current.items():
            print("  %-22s %s" % (name, value or "—"))
        return 0

    if args.merge:
        merge_path = _resolve_merge_path(args.merge)
        payload = C.read_json(merge_path)
        if not isinstance(payload, dict):
            raise SystemExit("[ERROR] --merge 目标必须是 JSON 对象：%s" % merge_path)
        payload["fingerprints"] = current
        C.write_json(merge_path, payload)
        # 同步写一份记录，保证后续无参比对有基线（否则 merge 路径与复查路径脱节）
        record_path.parent.mkdir(parents=True, exist_ok=True)
        C.write_json(record_path, current)
        print("[provenance] 已把 fingerprints 合并进 %s（其余字段保留）" % C.rel_to_root(merge_path))
        print("[provenance] 同时写入基线记录 %s —— 后续可直接无参比对" % C.rel_to_root(record_path))
        return 0

    if not target.exists():
        print("[provenance][ERROR] 尚未建立基线指纹：%s" % C.rel_to_root(target))
        print("        先运行 --write 或 --merge 记录基线；没有基线就无法判断是否同口径，"
              "此处不再静默通过。")
        return 2

    recorded = load_recorded(target)
    declared = _parse_declare(args.declare)
    frozen_diffs = []
    declared_diffs = []
    for name in ALL_FIELDS:
        before = recorded.get(name)
        now = current.get(name)
        if before == now:
            continue
        (frozen_diffs if name in FROZEN_FIELDS else declared_diffs).append((name, before, now))

    if frozen_diffs:
        print("[provenance] FAIL 非实验变量发生变化，已不是同一口径：")
        for name, before, now in frozen_diffs:
            print("  %-22s baseline=%s now=%s" % (name, before or "—", now or "—"))
        print("  frozen 域（%s）只允许「重建基线」，不允许用 --declare 声明变更。"
              % ", ".join(FROZEN_FIELDS))
        return 1

    unacknowledged = [d for d in declared_diffs if d[0] not in declared]
    if unacknowledged:
        print("[provenance] FAIL 以下预期实验变量发生变化但未声明：")
        for name, before, now in unacknowledged:
            print("  %-22s baseline=%s now=%s" % (name, before or "—", now or "—"))
        print("  若属于本轮优化动作，用 --declare %s 声明后重跑，并把下列记录写进报告："
              % ",".join(d[0] for d in unacknowledged))
        return 1

    if declared_diffs:
        print("[provenance] OK 非实验变量未变；以下实验变量已声明变更（请粘贴进报告）：")
        for name, before, now in declared_diffs:
            print("  declared_change: %-22s %s -> %s" % (name, (before or "—")[:12], (now or "—")[:12]))
        return 0

    print("[provenance] OK 指纹与基线一致（输入/标杆/模型/配置均未变）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
