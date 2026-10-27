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
"""await_file.py — 阻塞等待一个文件出现（最多 --timeout 秒），供 route 派发后的循环等待使用。

headless `-p` 会话在回合结束（输出不带工具调用的文本）时立即退出，且 Bash 工具单次调用
超时上限约 10 分钟——因此"后台启动 dispatch + 单次前台阻塞到 5400s"不可行，
"后台派发后结束回合等待通知"更不可行（会话退出连带杀死全部子进程，冒烟 #1/#2 实证）。

正确模式（round.md §6.2）：
    1) setsid nohup 后台启动 dispatch 脚本（记住其 PID）；
    2) 循环调用本脚本：每次最多等 --timeout 秒（须 < 480s，留足工具超时余量），
       输出 JSON 恒为 exit 0，"done": false 时**立即再次调用本脚本**（工具调用链
       保持会话存活），直到 "done": true 才进入收集阶段；
    3) 全程禁止在 done=true 之前输出任何回合结束文本。

可选 --pid：监视派发进程；若文件未出现而该 PID 已死亡，立即返回
"dispatch_exited": true（避免对已崩溃的派发干等到超时）。

输出 JSON：{done, waited_s, exists, json_ok, dispatch_alive, action, error}
退出码：0 = 正常（含未完成，看 action 续等）；2 = 参数错误。纯标准库。
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

MAX_TIMEOUT_S = 480.0  # Bash 工具调用上限 600s，预留余量


@dataclass
class EmitSpec:
    """Payload for the JSON result emitted by the await loop."""

    done: bool
    exists: bool
    json_ok: bool
    dispatch_alive: bool | None
    action: str
    error: str | None = None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # 进程存在但属其他用户


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="阻塞等待文件出现（循环调用保持会话存活）")
    parser.add_argument("--path", required=True, help="待等待的文件路径")
    parser.add_argument("--timeout", type=float, default=480.0,
                        help=f"本次调用最长等待秒数（默认 480，上限 {MAX_TIMEOUT_S:g}）")
    parser.add_argument("--interval", type=float, default=10.0, help="轮询间隔秒数（默认 10）")
    parser.add_argument("--pid", type=int, default=None,
                        help="可选：派发进程 PID；文件未出现且该进程死亡时立即返回")
    parser.add_argument("--require-json", action="store_true",
                        help="文件出现后还需能解析为 JSON 才算 done（如 parallel_result.json）")
    return parser.parse_args()


def _json_ready(target: Path, require_json: bool) -> bool:
    """Return True if the target is a valid JSON (or JSON not required)."""
    if not require_json:
        return True
    try:
        json.loads(target.read_text(encoding="utf-8"))
        return True
    except (ValueError, OSError):
        return False


def main() -> int:
    args = _parse_args()

    if args.timeout > MAX_TIMEOUT_S:
        sys.stdout.buffer.write((json.dumps({"done": False, "exists": False, "json_ok": False, "dispatch_alive": None,
                          "action": "fix args and retry",
                          "error": f"--timeout {args.timeout:g}s exceeds {MAX_TIMEOUT_S:g}s "
                                   f"tool-call budget"}, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return 2
    if args.interval <= 0:
        sys.stdout.buffer.write((json.dumps({"done": False, "exists": False, "json_ok": False, "dispatch_alive": None,
                                     "action": "fix args and retry",
                                     "error": "--interval must be positive"},
                                    ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return 2

    target = Path(args.path)
    start = time.time()

    def emit(spec: EmitSpec) -> int:
        sys.stdout.buffer.write((json.dumps({
            "done": spec.done, "waited_s": round(time.time() - start, 1), "exists": spec.exists,
            "json_ok": spec.json_ok, "dispatch_alive": spec.dispatch_alive, "action": spec.action, "error": spec.error,
        }, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        return 0

    while True:
        if target.is_file() and _json_ready(target, args.require_json):
            return emit(EmitSpec(True, True, True, None, "target ready - proceed to collection phase"))
        if args.pid is not None and not pid_alive(args.pid):
            if target.is_file():
                return emit(EmitSpec(True, True, False, False, "target ready - proceed to collection phase"))
            # setsid 在部分环境会 fork，$! 可能是已退出的包装进程而非 dispatch 本体，
            # 先验证再定性：读 dispatch 日志 / ps 确认；若 dispatch 仍在跑，去掉 --pid 继续等。
            time.sleep(30)
            if target.is_file():
                return emit(EmitSpec(True, True, False, False, "target ready - proceed to collection phase"))
            return emit(EmitSpec(False, target.is_file(), False, False,
                        "PID dead and no target - verify via dispatch log and `ps aux | grep dispatch_parallel`: "
                        "if dispatch actually exited, investigate and re-dispatch; "
                        "if it is still running (e.g. setsid forked so $! was the wrapper), "
                        "re-call this script WITHOUT --pid and keep waiting",
                        "monitored PID is gone before target appeared (may be a setsid wrapper false positive)"))
        if time.time() - start >= args.timeout:
            return emit(EmitSpec(False, target.is_file(), False,
                        pid_alive(args.pid) if args.pid is not None else None,
                        "PENDING - call this script again immediately (do not end the turn)"))
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
