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
"""dispatch_parallel.py — 并行启动多个 route 子 CLI，每个 route 独立执行
.claude/references/algorithms/gene-fusion/route.md 的完整 pipeline。

用法:
  python3 dispatch_parallel.py --manifests route-1/.task_manifest.json route-2/.task_manifest.json --timeout 3600
"""

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# B5: 三条 route 的首条用户消息一字节相同——prompt cache 从第 1 token 命中，
# 消除"首消息只差 route 编号导致每条 route 全量写 ~40k cache_creation"的浪费
# （原首消息同时内插 route_id 与含 route-N 的绝对 manifest 路径）。route 身份/
# 差异全部放 .task_manifest.json 文件内，route 第一步读取自取 route_id。
ROUTE_PROMPT = "Read .task_manifest.json in your working directory and execute it."

# C1(修复 8 轮挂账的派发权限缺陷): --print 非交互模式无法弹窗授权, 不带权限
# 参数时 route 子 CLI 的工具调用全部被拒(R7/R9 D0 探针实证 3 route 零产物)。
# 以 allowlist 最小授权文件与 Bash 工具; 越权兜底仍由 PreToolUse guard(worker 模式)承担。
ROUTE_ALLOWED_TOOLS = "Read,Edit,Write,MultiEdit,Glob,Grep,Bash,TodoWrite"

# route 子 CLI 的模型：写死 "claude-sonnet-4-6" 会在只提供别的模型的网关/环境里直接失败。
# 默认跟随环境（TRITON_ROUTE_MODEL / CANNBOT_ROUTE_MODEL），都没设置就继承 claude 自身默认。
DEFAULT_ROUTE_MODEL = (
    os.environ.get("TRITON_ROUTE_MODEL") or os.environ.get("CANNBOT_ROUTE_MODEL") or ""
)

# B5: AGENTS.md 同样三 route 一字节相同（会进 system prompt，含 route_id 同样
# 从第 1 token 分叉缓存）。每次派发重写，覆盖旧版含 route_id 的残留文件。
AGENTS_MD_TEXT = """---
name: triton-route-worker
description: Route Worker for gene-fusion — 执行 .claude/references/algorithms/gene-fusion/route.md 完整 pipeline
mode: primary
temperature: 0.1
---

# Route Worker

你是 Gene-Fusion 的 Route Worker。你的完整规范在 `.claude/references/algorithms/gene-fusion/route.md`。

请读取你工作目录下的 `.task_manifest.json` 后按照规范执行；你的 route 身份
（route_id、基因组合、baseline_dir、超时等）与任务参数都在其中。
"""


def cache_prefix_fingerprint() -> dict:
    """B5 自检指纹：首消息与 AGENTS.md 的 md5（与 route 无关，天然全 route 相同）。"""
    return {
        "route_prompt_md5": hashlib.md5(ROUTE_PROMPT.encode(), usedforsecurity=False).hexdigest(),
        "agents_md_md5": hashlib.md5(AGENTS_MD_TEXT.encode(), usedforsecurity=False).hexdigest(),
    }


def parse_args():
    parser = argparse.ArgumentParser(description="dispatch_parallel.py — 并行启动多个 route 子 CLI")
    parser.add_argument("--manifests", nargs="+", required=True, help="task manifest 文件路径列表")
    parser.add_argument("--timeout", type=int, default=3600,
                        help="route 兜底超时（秒），默认 3600；被 route_type 分层或 manifest 显式声明覆盖")
    # A6 超时分层：elite 贴近父代、确定性高（短）；exploration 新基因调试量大（长）。
    # 依据：R6 整条 route 超时被杀作废、R1 route_timeout+开销 > worker timeout 必触发重派。
    parser.add_argument("--elite-route-timeout", type=int, default=2400,
                        help="route_type 含 elite 的超时（秒），默认 2400")
    parser.add_argument("--crossover-route-timeout", type=int, default=3600,
                        help="route_type 含 crossover 的超时（秒），默认 3600")
    parser.add_argument("--exploration-route-timeout", type=int, default=5400,
                        help="route_type 含 exploration 的超时（秒），默认 5400")
    # I2 启动错峰：三 route 同时 import torch_npu 会叠加 host 尖峰，按序错开启动
    parser.add_argument("--start-stagger", type=int, default=45,
                        help="相邻 route 启动间隔（秒），默认 45；0=关闭错峰")
    parser.add_argument("--dry-run", action="store_true",
                        help="只解析并打印每 route 的生效超时与启动延迟，不实际派发（A6/I2 验证通道）")
    parser.add_argument("--output", type=str, default=None, help="结果输出 JSON 文件路径，默认写入第一个 manifest 的 work_dir 同级")
    parser.add_argument("--model", type=str, default=DEFAULT_ROUTE_MODEL,
                        help="route 子 CLI 模型（默认取 TRITON_ROUTE_MODEL/CANNBOT_ROUTE_MODEL；"
                             "都未设置则继承 claude 自身默认）")
    return parser.parse_args()


def resolve_route_timeout(
    manifest: dict, fallback: int, tier_timeouts: dict[str, int | None]
) -> int:
    """A6 超时分层解析：manifest 显式 route_timeout > route_type 分层 > 兜底。

    route_type 取 ``genetic_metadata.route_type``（如 elite / crossover /
    exploration / initial_exploration），顶层 ``route_type`` 兼容回退；
    分层键做子串匹配（initial_exploration 命中 exploration 层）。
    纯函数，便于无副作用的单测。
    """
    explicit = manifest.get("route_timeout")
    if explicit:
        return int(explicit)
    route_type = str(
        manifest.get("genetic_metadata", {}).get("route_type")
        or manifest.get("route_type", "")
    ).lower()
    for tier, tier_to in tier_timeouts.items():
        if tier_to and tier in route_type:
            return int(tier_to)
    return int(fallback)


def write_partial_result(partial_dir: Path | None, result: dict) -> None:
    """A2 流式收集：单 route 进程一结束即落盘 partial 结果。

    父/编排侧读 partial 即可先行记账，不再阻塞等最慢 route（H1 后编排侧
    直读本产物）。best-effort：写失败只告警，不阻塞派发主流程。
    """
    if partial_dir is None:
        return
    route_id = str(result.get("route_id") or "unknown")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in route_id)
    path = partial_dir / f"parallel_result_partial_{safe}.json"
    try:
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        logger.info("  [%s] A2 partial written: %s", route_id, path)
    except OSError as exc:
        logger.warning("  [%s] A2 partial write failed (non-fatal): %s", route_id, exc)


@dataclass
class RouteRunCtx:
    """Route run context passed through the dispatch helpers."""

    route_id: str
    manifest_path: Path
    work_dir: Path
    manifest: dict
    effective_timeout: int
    model: str = DEFAULT_ROUTE_MODEL


def _collect_route_success(proc, start_time, ctx: RouteRunCtx) -> dict:
    """Collect the route result on success."""
    stdout, stderr = proc.communicate(timeout=ctx.effective_timeout)
    elapsed = time.time() - start_time
    result = {
        "route_id": ctx.route_id,
        "manifest_path": str(ctx.manifest_path),
        "work_dir": str(ctx.work_dir),
        "status": "success" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "elapsed_seconds": round(elapsed, 1),
        "route_type": ctx.manifest.get("genetic_metadata", {}).get("route_type"),
        "timeout_effective": ctx.effective_timeout,
        "stderr": stderr.decode("utf-8", errors="replace")[:1000] if stderr else "",
    }
    round_result_path = ctx.work_dir / "round_result.json"
    if round_result_path.exists():
        result["round_result"] = json.loads(round_result_path.read_text())
    return result


def _launch_route(work_dir: Path, model: str = DEFAULT_ROUTE_MODEL) -> subprocess.Popen:
    """Launch the route sub CLI (--allowedTools 白名单授权, 见 ROUTE_ALLOWED_TOOLS 注记)."""
    command = ["claude", "--print", "--output-format", "json",
               "--allowedTools", ROUTE_ALLOWED_TOOLS]
    if model:
        command += ["--model", model]
    command.append(ROUTE_PROMPT)
    return subprocess.Popen(
        command,
        cwd=str(work_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env={**os.environ, "CLAUDE_CODE_WORK_DIR": str(work_dir)},
    )


def _prepare_route_workspace(
    manifest_path: Path, timeout: int, tier_timeouts: dict[str, int | None],
) -> tuple[dict, str, Path, int]:
    """Read the manifest and prepare the route workspace; returns (manifest, route_id, work_dir, effective_timeout)."""
    manifest = json.loads(manifest_path.read_text())
    route_id = manifest.get("route_id", manifest_path.parent.name)
    work_dir = Path(manifest.get("work_dir", manifest_path.parent))
    effective_timeout = resolve_route_timeout(manifest, timeout, tier_timeouts)
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / ".task_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    (work_dir / "AGENTS.md").write_text(AGENTS_MD_TEXT)
    return manifest, route_id, work_dir, effective_timeout


def _run_route_once(ctx: RouteRunCtx, partial_dir: Path | None) -> dict:
    """Launch one route and collect its result (success/timeout/error)."""
    start_time = time.time()
    try:
        proc = _launch_route(ctx.work_dir, ctx.model)

        try:
            result = _collect_route_success(proc, start_time, ctx)
            write_partial_result(partial_dir, result)
            return result

        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            result = {
                "route_id": ctx.route_id, "manifest_path": str(ctx.manifest_path),
                "work_dir": str(ctx.work_dir), "status": "timeout",
                "elapsed_seconds": round(time.time() - start_time, 1),
                "route_type": ctx.manifest.get("genetic_metadata", {}).get("route_type"),
                "timeout_effective": ctx.effective_timeout,
                "error": f"Route exceeded timeout of {ctx.effective_timeout}s",
                "pid": proc.pid,
            }
            write_partial_result(partial_dir, result)
            return result

    except Exception as e:
        result = {
            "route_id": ctx.route_id, "manifest_path": str(ctx.manifest_path),
            "work_dir": str(ctx.work_dir), "status": "error", "error": str(e),
        }
        write_partial_result(partial_dir, result)
        return result


def run_single_route(
    manifest_path: str,
    timeout: int,
    tier_timeouts: dict[str, int | None] | None = None,
    start_delay: float = 0.0,
    partial_dir: Path | None = None,
    model: str = DEFAULT_ROUTE_MODEL,
) -> dict:
    """启动单个 route 子 CLI 并等待其完成。"""
    manifest_path = Path(manifest_path).resolve()
    if not manifest_path.exists():
        result = {
            "route_id": None, "manifest_path": str(manifest_path), "status": "error",
            "error": "manifest not found",
        }
        write_partial_result(partial_dir, result)
        return result

    manifest, route_id, work_dir, effective_timeout = _prepare_route_workspace(
        manifest_path, timeout, tier_timeouts or {}
    )

    if start_delay > 0:
        # I2: 错峰启动——manifest 序号靠后者延迟启动，抹平同时 import torch_npu 的 host 尖峰
        logger.info(
            "[dispatch_parallel] [%s] start in %.0fs (I2 stagger, timeout=%ss)",
            route_id, start_delay, effective_timeout,
        )
        time.sleep(start_delay)

    ctx = RouteRunCtx(
        route_id=route_id, manifest_path=manifest_path, work_dir=work_dir,
        manifest=manifest, effective_timeout=effective_timeout, model=model,
    )
    return _run_route_once(ctx, partial_dir)


def _dry_run_preview(manifests: list[Path], timeout: int, tier_timeouts: dict, start_stagger: float) -> None:
    """Print the per-route timeout and start delay without dispatching."""
    for idx, m in enumerate(manifests):
        try:
            manifest = json.loads(m.read_text())
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("[dry-run] %s: manifest unreadable (%s)", m, e)
            continue
        to = resolve_route_timeout(manifest, timeout, tier_timeouts)
        rt = manifest.get("genetic_metadata", {}).get("route_type")
        logger.info(
            "[dry-run] %s: route_type=%s timeout=%ss start_delay=%ss",
            m.parent.name, rt, to, idx * start_stagger,
        )


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    manifests = [Path(m).resolve() for m in args.manifests]
    tier_timeouts = {
        "elite": args.elite_route_timeout,
        "crossover": args.crossover_route_timeout,
        "exploration": args.exploration_route_timeout,
    }
    if not manifests:
        logger.error("Error: No manifests provided")
        sys.exit(1)

    if args.dry_run:
        _dry_run_preview(manifests, args.timeout, tier_timeouts, args.start_stagger)
        return

    logger.info(
        "[dispatch_parallel] Starting %d routes in parallel "
        "(fallback timeout=%ss, A6 tiers=%s)",
        len(manifests), args.timeout, tier_timeouts,
    )

    # A2: 先算输出路径——单 route 结束即写 partial 到同目录（流式收集）
    output_path = Path(args.output) if args.output else Path(manifests[0]).parent.parent / "parallel_result.json"
    partial_dir = output_path.parent
    results = {}
    with ThreadPoolExecutor(max_workers=len(manifests)) as executor:
        futures = {
            executor.submit(
                run_single_route, str(m), args.timeout, tier_timeouts,
                idx * args.start_stagger, partial_dir, args.model,
            ): str(m)
            for idx, m in enumerate(manifests)
        }
        for future in as_completed(futures):
            result = future.result()
            manifest = futures[future]
            route_id = result.get("route_id", "unknown")
            status = result.get("status", "error")
            results[route_id] = result
            logger.info("  [%s] %s", route_id, status)

    # 写入结果（A2: partial 已在各 route 结束时流式落盘，此为全量汇总）
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))

    success_count = sum(1 for r in results.values() if r["status"] == "success")
    logger.info("[dispatch_parallel] Done: %d/%d routes succeeded", success_count, len(manifests))
    logger.info("  Result written to: %s", output_path)


if __name__ == "__main__":
    main()