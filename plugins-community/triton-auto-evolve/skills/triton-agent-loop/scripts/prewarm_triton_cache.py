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
"""prewarm_triton_cache.py — dispatch 前把上一轮最优 route 的 .triton_cache 预热进各新 route 工作区（优化项E2）。

Triton 缓存按源码+环境内容寻址：命中即跳过编译，不命中即回源编译并落新条目，
因此整目录合并拷贝是安全的——陈旧条目永远不会被误用，同名冲突按"保留已有"处理。

源（二选一）：
  --round-dir PATH   上一轮目录，自动选 best_speedup 最高的成功 route 的 .triton_cache
  --src-cache PATH   显式指定缓存目录（优先级更高）

目标（二选一，可组合）：
  --dest-round PATH  新一轮目录：对其下每个 route-*/ 工作区合并预热
  --dest-dir PATH... 显式指定一个或多个工作区目录

输出 JSON：{src, best_route, dests:[{dir, copied, skipped, conflicts, bytes}], total_copied, env_hint}
退出码：0 = 成功（含零拷贝）；2 = 源缺失/无目标工作区。纯标准库。

用法：
    python3 prewarm_triton_cache.py --round-dir opt-round-2 --dest-round opt-round-3
"""

import argparse
import filecmp
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bottleneck_card import pick_best_route  # noqa: E402


def merge_cache(src: Path, dst: Path) -> dict:
    """把 src 缓存树合并进 dst：缺失才拷贝，同名同内容跳过，同名异内容保留已有计冲突。"""
    copied = skipped = conflicts = 0
    bytes_copied = 0
    if not dst.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.is_file():
            try:
                same = filecmp.cmp(path, target, shallow=False)
            except OSError:
                same = False
            if same:
                skipped += 1
            else:
                # 内容寻址下正常不会发生（不同内容必有不同哈希目录名）；
                # 保留已有条目，宁可回源编译也不冒用错缓存的风险。
                conflicts += 1
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        copied += 1
        bytes_copied += path.stat().st_size
    return {"copied": copied, "skipped": skipped, "conflicts": conflicts, "bytes": bytes_copied}


def resolve_src(args: argparse.Namespace, op_dir: Path) -> tuple[Path | None, str | None]:
    """解析预热源缓存目录，返回 (路径, best_route 名或 None)。"""
    if args.src_cache:
        p = Path(args.src_cache)
        return (p if p.is_dir() else None), None
    if not args.round_dir:
        return None, None
    round_dir = Path(args.round_dir)
    if not round_dir.is_dir():
        return None, None
    route_id, rr = pick_best_route(round_dir)
    if route_id:
        cache = round_dir / route_id / ".triton_cache"
        if cache.is_dir():
            return cache, route_id
    # 兜底：任一 route 有缓存就用（无缓存也应能继续，返回 None 由调用方告警）
    for route_dir in sorted(round_dir.glob("route-*")):
        cache = route_dir / ".triton_cache"
        if cache.is_dir():
            return cache, route_dir.name
    return None, route_id


def resolve_dests(args: argparse.Namespace) -> list[Path]:
    dests: list[Path] = []
    if args.dest_dir:
        dests.extend(Path(d) for d in args.dest_dir)
    if args.dest_round:
        dests.extend(sorted(Path(args.dest_round).glob("route-*")))
    seen: set[str] = set()
    unique = []
    for d in dests:
        key = str(d.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser(description="上一轮最优 route 的 .triton_cache -> 新 route 工作区（E2）")
    parser.add_argument("--round-dir", default=None, help="上一轮目录（自动选最优 route 的缓存）")
    parser.add_argument("--src-cache", default=None, help="显式缓存目录（优先于 --round-dir）")
    parser.add_argument("--dest-round", default=None, help="新一轮目录（对其下 route-*/ 逐一预热）")
    parser.add_argument("--dest-dir", nargs="*", default=None, help="显式工作区目录列表")
    args = parser.parse_args()

    src, best_route = resolve_src(args, Path(args.round_dir).parent if args.round_dir else Path())
    dests = resolve_dests(args)

    result: dict = {
        "src": str(src) if src else None,
        "best_route": best_route,
        "dests": [],
        "total_copied": 0,
        "env_hint": None,
    }

    if src is None:
        result["error"] = "no source cache found (check --round-dir/--src-cache)"
        sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return 2
    if not dests:
        result["error"] = "no destination workspaces (check --dest-round/--dest-dir)"
        sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return 2

    for dest in dests:
        stats = merge_cache(src, dest / ".triton_cache")
        stats["dir"] = str(dest)
        result["dests"].append(stats)
        result["total_copied"] += stats["copied"]
    result["env_hint"] = f"TRITON_CACHE_DIR={Path(dests[0].resolve() / '.triton_cache')}"

    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
