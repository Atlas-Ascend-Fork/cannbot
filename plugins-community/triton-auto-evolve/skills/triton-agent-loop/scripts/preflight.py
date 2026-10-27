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
"""preflight.py — 正式派发前 30 秒冒烟预检（优化项A3-脚本）。

① 模型 id 预检：发一个 ≤10 token 请求验证模型 id 可用，防止 unrecognized_model
   之类错误在 route 跑到超时才暴露（R8）。
② 可选吞吐探测（--probe-throughput）：小请求测量 tok/s，作为网关基线参考（非门控）。

输出 JSON：{model_ok, model, tok_s, latency_s, error}
退出码：0 = 可派发；2 = 不可派发（CLI 缺失 / 模型不可用 / 超时 / 空响应）。

用法：
    python3 preflight.py [--model claude-sonnet-4-6] [--timeout 30]
                         [--probe-throughput] [--probe-tokens 64] [--out preflight.json]

与 dispatch_parallel.py 采用同一调用形态（claude --print --output-format json），
因此本脚本通过即代表 route 子 CLI 可启动。纯标准库。
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# 与 dispatch_parallel.py 保持一致的默认模型 id。
DEFAULT_MODEL = "claude-sonnet-4-6"


def run_claude(prompt: str, model: str | None, timeout: float) -> tuple[dict | None, str | None, float]:
    """运行一次 claude --print，返回 (响应 JSON, 错误信息, 耗时秒)。两者互斥（响应可能为 None）。

    model=None 时不带 --model 参数——与 worker 命令模板（裸 claude -p）同形态，
    由 claude 自身 settings 解析模型；这是派发前预检（A3）最忠实的探测方式。
    """
    cmd = ["claude", "--print", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return None, "claude CLI not found in PATH", time.time() - start
    except subprocess.TimeoutExpired:
        return None, f"claude request exceeded {timeout:g}s timeout", time.time() - start
    elapsed = time.time() - start
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-300:]
        return None, f"claude exit {proc.returncode}: {tail}", elapsed
    try:
        return json.loads(proc.stdout), None, elapsed
    except ValueError:
        return None, f"non-JSON output: {proc.stdout[:200]}", elapsed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="派发前 30 秒冒烟预检（A3-脚本）")
    parser.add_argument("--model", default=None,
                        help="待验证模型 id（缺省不带 --model，与 worker 命令模板同形态，"
                             f"由 claude settings 解析；显式探测可传如 {DEFAULT_MODEL}）")
    parser.add_argument("--timeout", type=float, default=30.0, help="单次请求超时秒数（默认 30）")
    parser.add_argument("--attempts", type=int, default=2,
                        help="瞬时故障重试次数（默认 2 次；全部失败才判不可派发）")
    parser.add_argument("--probe-throughput", action="store_true",
                        help="预检通过后追加一次小吞吐探测（记录 tok/s，非门控）")
    parser.add_argument("--probe-tokens", type=int, default=64,
                        help="吞吐探测期望产出的近似 token 数（默认 64）")
    parser.add_argument("--out", default=None, help="可选：结果 JSON 落盘路径（缺省仅 stdout）")
    return parser.parse_args()


def _check_model(model: str | None, timeout: float, attempts: int) -> tuple[bool, str | None, float]:
    """Check the model id with a ≤10 token request; returns (model_ok, error, elapsed)."""
    data = error = None
    elapsed = 0.0
    for attempt in range(max(attempts, 1)):
        data, error, elapsed = run_claude("Reply with exactly one word: ok", model, timeout)
        if error is None:
            break
        if attempt + 1 < max(attempts, 1):
            time.sleep(5)
    if error is not None:
        return False, error, elapsed
    text = str(data.get("result") or "").strip()
    if data.get("is_error"):
        return False, f"model returned error: {text[:200]}", elapsed
    if not text:
        return False, f"empty response (subtype={data.get('subtype', '?')})", elapsed
    return True, None, elapsed


def main() -> int:
    args = _parse_args()

    model_ok, error, elapsed = _check_model(args.model, args.timeout, args.attempts)

    result: dict = {
        "model_ok": model_ok,
        "model": args.model,
        "tok_s": None,
        "latency_s": round(elapsed, 2),
        "error": error,
    }

    # ② 可选吞吐探测：只记录参考值，不影响退出码。
    if model_ok and args.probe_throughput:
        pdata, perr, pelapsed = run_claude(
            f"Count from 1 to {max(args.probe_tokens, 8)}, comma separated, digits only, no other text.",
            args.model,
            args.timeout,
        )
        if perr is not None or not pdata:
            result["error"] = f"throughput probe failed (non-fatal): {perr}"
        else:
            out_tokens = (pdata.get("usage") or {}).get("output_tokens") or 0
            if out_tokens > 0 and pelapsed > 0:
                result["tok_s"] = round(out_tokens / pelapsed, 1)

    if args.out:
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")
    sys.stdout.buffer.write((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return 0 if model_ok else 2


if __name__ == "__main__":
    sys.exit(main())
