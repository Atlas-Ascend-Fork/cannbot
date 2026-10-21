#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

"""Workflow orchestrator — 主循环。

python3 orchestrator.py --yaml <wf.yaml> --work-dir <dir> [--provider opencode]
                        [--prompt <p>] [--dry-run]

启动分流：
- $WORK_DIR/.workflow/status.json 不存在 → 必须 --prompt，委托 init_status.py 初始化后进主循环
- 已存在 → 恢复执行（传了 --prompt 则打警告）；先重置瞬态：running→pending、verifying→executed
  （瞬态是进程内的，编排器进程被杀后滞留会造成永久在飞 → 死锁）

主循环（事件驱动补位）：
- 常驻唯一 ThreadPoolExecutor（容量 = workflow yaml 的 max_parallel，启动时读取）。
  主线程独占调度与 status.json 写入：收割已完成 → 调 get_task.py 要新批次 → 串行预占
  （pending→running / executed→verifying，回复传空串）→ submit →
  wait(FIRST_COMPLETED)。
  任一任务完成即收割即补位，无批内 barrier：快任务验证 pass 后，只依赖它的下游立即
  拉起，不等同批慢任务。原始 stdout 存档到 .workflow/sessions/<task_id>.<phase>.<时间戳>.jsonl。
- 崩溃 = 一次失败：agent 进程退出码非零 → log crash 事件 → update_status 传 $CRASH
  （落 fail、retries+1、吃重试预算）→ 照常调度。预算内 get_task 下一轮自动重排重试
  （本次运行内自愈）；耗尽后由 on_exhaust 裁决（exit → [STUCK]；continue → 跳过
  该节点及其全部下游依赖；rollback → 排干在飞后回滚到 rollback_to 重做）。
  拉起级失败（provider 二进制缺失等 Popen OSError）→ 主循环异常 exit 2，
  任务留瞬态，重跑恢复，不吃预算。
- 排干守卫：终结信号（[ALL TASK FINISHED]/[STUCK]）到达时仍有在飞任务 → 停止派发，
  等在飞全部收尾并回收后重新裁决，杜绝孤儿 agent 进程。
- get_task 输出映射：batch → 派发；[ALL TASK FINISHED] 无 skipped → exit 0；
  带 skipped（耗尽+continue 的跳过任务清单）→ 报告跳过清单，exit 1；[STUCK] → exit 1；
  [] → 有在飞则等待；无在飞但有待审批任务则按固定间隔轮询（不计空轮、不退出，
  等人工审批到达）；其余无在飞则原地重置瞬态再试，连续 3 轮仍空 → exit 2。
- 单实例互斥：.workflow/orchestrator.lock（pid + 存活探测，陈旧锁自动接管）。
  所有 status.json 写入均为临时文件 + rename 原子替换，写半截崩溃不损坏旧文件。

--dry-run（UT 专用）：不拉起真 CLI，回复取 $WORK_DIR/.workflow/dry_replies.json：
{"task_id": ["回复", ...]}，FIFO、跨 execute/verify 按调用顺序消费；"$CRASH" 模拟进程
崩溃；"$SLEEP:<秒>" 模拟慢任务（睡眠后返回阶段默认回复）；verify 阶段的
"$VERDICT:pass"/"$VERDICT:fail[:原因]" 模拟 verifier 调 verdict 回调脚本（写裁决文件，
文本回复缺省模拟不合规的"通过/失败"，可用 "|文本" 覆盖）；未配置/耗尽的条目按阶段给默认回复
（execute→executed，verify→写 pass 裁决文件）；普通文本不产生裁决。
"""

import argparse
import atexit
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from abc import ABC, abstractmethod
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone

import yaml

from verdict_common import verdict_file_path, write_verdict_file

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
# G.PSL.02：now() 须显式传 tz；统一用 now(timezone.utc).astimezone() 按系统默认时区记录
CRASH = "$CRASH"
SLEEP_PREFIX = "$SLEEP:"
VERDICT_PREFIX = "$VERDICT:"
MAX_EMPTY_ROUNDS = 3
APPROVAL_POLL_SECONDS = 1  # 待审批轮询间隔：审批经文件信箱异步到达，固定间隔避免热自旋
TERMINAL_RESULTS = ("[ALL TASK FINISHED]", "[STUCK]")  # get_task 终结裁决的合法 result


class Provider(ABC):
    """无头调用 Coding Agent CLI；接入新 CLI（如 claude）= 继承本类 + 注册进 PROVIDERS。"""

    name = ""

    @abstractmethod
    def build_command(self, agent, prompt):
        """返回完整 argv；子进程以 cwd=work_dir 运行。"""


class OpenCodeProvider(Provider):
    name = "opencode"

    def build_command(self, agent, prompt):
        return ["opencode", "run", "--format", "json", "--agent", agent, prompt]


class CannbotProvider(OpenCodeProvider):
    name = "cannbot"

    def build_command(self, agent, prompt):
        return ["cannbot", "run", "--format", "json", "--agent", agent, prompt]


class ClaudeProvider(Provider):
    name = "claude"

    def build_command(self, agent, prompt):
        return [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--dangerously-skip-permissions",
            "--agent",
            agent,
        ]


class PiProvider(Provider):
    name = "pi"

    def build_command(self, agent, prompt):
        return ["pi", "-p", "--mode", "json", "--no-session", prompt]


class CodexProvider(Provider):
    name = "codex"

    def build_command(self, agent, prompt):
        # --skip-git-repo-check：work_dir 常非 git 仓库，不带此标志 codex 拒绝运行
        return [
            "codex",
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            prompt,
        ]


PROVIDERS = {
    p.name: p
    for p in (
        OpenCodeProvider(),
        CannbotProvider(),
        ClaudeProvider(),
        PiProvider(),
        CodexProvider(),
    )
}


def err(msg):
    print("[orchestrator] 错误: %s" % msg, file=sys.stderr)
    return 2


def log_event(work_dir, **kv):
    kv = dict(
        kv,
        timestamp=datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
    )
    with open(os.path.join(work_dir, ".workflow", "log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(kv, ensure_ascii=False) + "\n")


def load_status(work_dir):
    with open(os.path.join(work_dir, ".workflow", "status.json"), encoding="utf-8") as f:
        return json.load(f)


def read_max_parallel(work_dir):
    """从 status.json 指向的 workflow yaml 读 max_parallel（常驻线程池容量）。"""
    try:
        wf = load_status(work_dir)["workflow"]
        with open(wf, encoding="utf-8") as f:
            return yaml.safe_load(f)["max_parallel"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError, yaml.YAMLError):
        return None


def save_status(work_dir, status):
    path = os.path.join(work_dir, ".workflow", "status.json")
    tmp = path + ".tmp"  # 原子写：写半截崩溃不损坏旧文件
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _close_lock_fd(lock_file):
    if not lock_file.closed:
        lock_file.close()


def acquire_lock(work_dir):
    """获取单实例非阻塞锁；内核会在进程退出时自动释放文件锁。"""
    lock = os.path.join(work_dir, ".workflow", "orchestrator.lock")
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    lock_file = open(lock, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(str(os.getpid()))
        lock_file.flush()
    except BlockingIOError:
        _close_lock_fd(lock_file)
        return None
    except BaseException:
        _close_lock_fd(lock_file)
        raise
    atexit.register(_close_lock_fd, lock_file)
    return lock_file


def reset_transient(work_dir):
    """瞬态重置（崩溃恢复 / [] 空轮自愈）：running→pending、verifying→executed。"""
    status = load_status(work_dir)
    hits = [t for t in status["tasks"].values() if t["status"] in ("running", "verifying")]
    if not hits:
        return 0
    for t in hits:
        t["status"] = "pending" if t["status"] == "running" else "executed"
    save_status(work_dir, status)
    log_event(work_dir, event="reset", tasks=len(hits))
    return len(hits)


def session_path(work_dir, task_id, phase):
    """会话存档路径；进程启动前创建，stdout 流式写入，监控可实时读到。"""
    d = os.path.join(work_dir, ".workflow", "sessions")
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y%m%dT%H%M%S")
    path = os.path.join(d, "%s.%s.%s.jsonl" % (task_id, phase, ts))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


WORKFLOW_DIR_NAME = ".workflow"  # 快照/恢复都要跳过的账本目录
CP = shutil.which("cp") or "cp"  # 绝对路径（G.EDV.05）；--reflink=auto 依赖 GNU cp


def copy_tree(src, dst):
    """把 src 下除 .workflow 外的顶层条目逐一 cp 到 dst（reflink=auto：CoW 零拷贝，不支持则退化）。"""
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name == WORKFLOW_DIR_NAME:
            continue
        subprocess.run([CP, "-a", "--reflink=auto", os.path.join(src, name), dst + "/"], check=True)


def clear_tree(path):
    """删除 path 下除 .workflow 外的全部顶层条目（回滚恢复 checkpoint 前清空现场）。"""
    for name in os.listdir(path):
        if name == WORKFLOW_DIR_NAME:
            continue
        p = os.path.join(path, name)
        if os.path.islink(p) or os.path.isfile(p):
            os.unlink(p)
        else:
            shutil.rmtree(p)


def dry_reply(dry_map, task_id, phase):
    seq = dry_map.get(task_id)
    default = VERDICT_PREFIX + "pass" if phase == "verify" else "executed"
    if isinstance(seq, list) and seq:
        r = str(seq.pop(0))
        if r.startswith(SLEEP_PREFIX):  # 模拟慢任务：睡眠后返回阶段默认回复
            try:
                time.sleep(float(r[len(SLEEP_PREFIX) :]))
            except (ValueError, OverflowError) as e:
                # 非法令牌属测试数据 bug，fail fast：静默降级默认回复会让 UT 假通过
                raise ValueError("非法 $SLEEP 令牌 %r: %s" % (r, e)) from e
            return default
        return r
    return default


def update(work_dir, task_id, reply):
    return subprocess.run(
        [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "update_status.py"),
            task_id,
            work_dir,
            reply,
        ],
        capture_output=True,
        text=True,
    )


def report(work_dir):
    status = load_status(work_dir)
    for tid, t in sorted(status["tasks"].items()):
        print("[orchestrator]   %s: %s (retries=%d)" % (tid, t["status"], t.get("retries", 0)))


def run_agent(entry, provider, work_dir, dry_map):
    """worker 线程体：返回 (内部阶段令牌, crashed)，stdout 仅存档；不碰 status.json。"""
    if dry_map is not None:
        reply = dry_reply(dry_map, entry["task_id"], entry["_phase"])
        if entry["_phase"] == "advice" and reply != CRASH:
            os.makedirs(os.path.dirname(entry["advice"]), exist_ok=True)
            with open(entry["advice"], "w", encoding="utf-8") as f:
                f.write(
                    "# Rollback Advice (SIMULATED / dry-run)\n\n"
                    "此文档由 dry-run 模拟生成，未执行真实失败分析。\n"
                )
            reply = "advice-written"
        elif entry["_phase"] == "verify" and reply.startswith(VERDICT_PREFIX):
            # 模拟 verifier 调 verdict 回调脚本：写裁决文件；文本回复缺省模拟不合规自然语言，
            # "|文本" 可显式覆盖（如 "$VERDICT:fail:原因|pass" 模拟裁决文件与文本矛盾）
            body, _, text = reply[len(VERDICT_PREFIX) :].partition("|")
            verdict, _, reason = body.partition(":")
            write_verdict_file(work_dir, entry["task_id"], verdict.strip(), reason.strip() or None)
            reply = text or ("通过" if verdict.strip() == "pass" else "失败")
        return reply, reply == CRASH
    path = session_path(work_dir, entry["task_id"], entry["_phase"])
    with (
        open(path, "wb") as f,
        subprocess.Popen(
            provider.build_command(entry["agent"], entry["prompt"]),
            cwd=work_dir,
            # opencode/cannbot 按 PWD 环境变量（而非实际 cwd）解析项目目录；
            # Popen(cwd=) 不会回写继承来的 PWD，子进程会落到父进程 cwd 所属项目
            env={**os.environ, "PWD": work_dir},
            stdout=f,
            stderr=subprocess.PIPE,
        ) as p,
    ):
        stderr = p.stderr.read().decode("utf-8", "replace")
        rc = p.wait()
    if rc != 0:  # 失败也存档：exit/stderr 追加在尾部，供排查基础设施故障
        with open(path, "a", encoding="utf-8") as f:
            f.write("\nexit=%d\n%s" % (rc, stderr))
        return None, True
    # stdout 仅存档；进程成功与否只看退出码，验证结论由裁决文件提供。
    return "executed" if entry["_phase"] == "execute" else "", False


def finish_advice(work_dir, entry, crashed=False, error=None):
    """记录 advice 执行失败；成功产物由下一轮 get_task 消费。"""
    status = load_status(work_dir)
    pending = status.get("advice_pending")
    if not pending or pending.get("task_id") != entry["task_id"]:
        raise ValueError("advice pending 与完成任务不一致: %s" % entry["task_id"])
    if crashed:
        error = error or "agent 进程崩溃"
    if not error:
        try:
            with open(pending["advice"], encoding="utf-8") as f:
                if not f.read().strip():
                    error = "advice 文件为空: %s" % pending["advice"]
        except (OSError, UnicodeError) as e:
            error = "advice 文件缺失或不可读: %s" % e
    if error:
        pending["error"] = error
        save_status(work_dir, status)
    log_event(
        work_dir,
        event="advice",
        task_id=entry["task_id"],
        result="error" if error else "ready",
        error=error,
    )


def consume_verdict_file(work_dir, task_id):
    """收割 verify 任务时读取裁决文件；合法返回 (verdict, reason|None)，否则 None。

    裁决文件是唯一验证依据；缺失/非法 → None，保持 verifying。
    """
    path = verdict_file_path(work_dir, task_id)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        data = None
    if not isinstance(data, dict) or data.get("verdict") not in ("pass", "fail"):
        return None
    reason = data.get("reason")
    if data["verdict"] != "fail" or not isinstance(reason, str) or not reason.strip():
        reason = None
    return data["verdict"], reason


def clear_verdict_file(work_dir, task_id):
    """派发 verify 前归档陈旧裁决文件；返回是否可安全派发。"""
    path = verdict_file_path(work_dir, task_id)
    try:
        if not os.path.exists(path):
            return True
        history = os.path.join(work_dir, ".workflow", "verdicts", "history")
        os.makedirs(history, exist_ok=True)
        encoded_id = os.path.splitext(os.path.basename(path))[0]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        archive = os.path.join(history, "%s.%s.json" % (encoded_id, stamp))
        os.replace(path, archive)
        return True
    except OSError:
        return False


def resolve_verdict_reply(work_dir, task_id):
    """仅使用有效裁决文件；缺失或非法时保持 verifying，等待重新验证。"""
    verdict = consume_verdict_file(work_dir, task_id)
    if not verdict:
        log_event(
            work_dir,
            event="verdict_missing",
            task_id=task_id,
            reason="裁决文件缺失或非法，需要重新验证",
        )
        return ""
    word, reason = verdict
    event = {"event": "verdict", "task_id": task_id, "verdict": word}
    if reason:
        event["reason"] = reason
    log_event(work_dir, **event)
    return word


def harvest_done(work_dir, inflight):
    """收割已完成的 future（主线程串行调用，status.json 唯一写入路径）。

    崩溃 = 一次失败：log crash 事件、update_status 传 $CRASH（落 fail、吃预算）；
    成功执行写 executed，成功验证仅消费裁决文件。单任务更新失败仅记录不停机。
    """
    for future in [x for x in inflight if x.done()]:
        entry = inflight.pop(future)
        if entry.get("_phase", entry.get("phase")) == "advice":
            try:
                _, crashed = future.result()
            except Exception as e:
                finish_advice(work_dir, entry, crashed=True, error=str(e))
            else:
                finish_advice(work_dir, entry, crashed=crashed)
            continue
        reply, crashed = future.result()
        if crashed:
            log_event(work_dir, event="crash", task_id=entry["task_id"])
            reply = CRASH
        elif entry.get("_phase") == "verify":
            reply = resolve_verdict_reply(work_dir, entry["task_id"])
        else:
            reply = "executed"
        rc = update(work_dir, entry["task_id"], reply).returncode
        if rc != 0:
            # 单任务更新失败不停机：可能因 agent 越权直改 status.json 等。
            # 记录后继续回收其余任务，交由下一轮调度重试/告警。
            err("状态更新失败: %s (reply=%r)，跳过并继续" % (entry["task_id"], reply[:200]))


def terminal_exit(work_dir, verdict):
    """终结裁决 → 退出码：全部 pass → 0；部分完成（有跳过）→ 1；STUCK → 1。"""
    skipped = verdict.get("skipped") or []
    reason = verdict.get("reason", "")
    if verdict["result"] == "[STUCK]":
        msg, event, code = (
            "工作流卡住: %s" % reason,
            dict(event="stuck", reason=reason),
            1,
        )
    elif skipped:
        msg, event, code = (
            "工作流部分完成（跳过: %s）" % ", ".join(skipped),
            dict(event="finish", result="partial", skipped=skipped),
            1,
        )
    else:
        msg, event, code = "工作流完成", dict(event="finish", result="ok"), 0
    print("[orchestrator] %s" % msg)
    report(work_dir)
    log_event(work_dir, **event)
    return code


class LoopContext:
    """主循环运行上下文与轮间状态；仅主线程读写（worker 只跑 run_agent）。"""

    def __init__(self, work_dir, provider, dry_map, executor):
        self.work_dir = work_dir
        self.provider = provider
        self.dry_map = dry_map
        self.executor = executor  # 常驻共享线程池
        self.inflight = {}  # future → 派发条目
        self.empty_rounds = 0  # 连续空轮计数（自愈 3 轮上限）


def ask_get_task(work_dir):
    """调 get_task.py 并解析校验输出：返回 (结果, 退出码)；退出码非 None 时循环应终止。

    合法性一次判尽（list 批次 / TERMINAL_RESULTS 终结 dict），下游不再重复校验。
    """
    proc = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, "get_task.py"), work_dir],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 2:
        sys.stderr.write(proc.stderr)
        return None, 2
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, err("get_task 输出无法解析: %r stderr=%r" % (proc.stdout, proc.stderr))
    if not (
        isinstance(out, list) or (isinstance(out, dict) and out.get("result") in TERMINAL_RESULTS)
    ):
        return None, err("get_task 输出无法解析: %r" % proc.stdout)
    return out, None


def dispatch_batch(ctx, batch):
    """预占任务状态并提交一批任务（主线程串行）；成功返回 None，否则返回退出码。"""
    # Advice remains pending in the ledger until its file is consumed. Repeated
    # dispatcher polls must not submit a second worker for that stable id.
    seen = {entry["task_id"] for entry in ctx.inflight.values()}
    unique_batch = []
    for entry in batch:
        if entry["task_id"] not in seen:
            unique_batch.append(entry)
            seen.add(entry["task_id"])
    batch = unique_batch
    status = load_status(ctx.work_dir)
    for entry in batch:
        if entry.get("phase") == "advice":
            entry["_phase"] = "advice"
            continue
        t = status["tasks"][entry["task_id"]]
        # 记阶段供 dry-run 默认回复与 session 存档：pending→execute、executed→verify
        entry["_phase"] = "verify" if t["status"] == "executed" else "execute"
        if entry["_phase"] == "verify":
            if not clear_verdict_file(ctx.work_dir, entry["task_id"]):
                return err("裁决文件归档失败: %s" % entry["task_id"])
    for entry in batch:
        if entry["_phase"] == "advice":
            continue
        if update(ctx.work_dir, entry["task_id"], "").returncode != 0:
            return err("任务状态预占失败: %s" % entry["task_id"])
    for entry in batch:
        ctx.inflight[
            ctx.executor.submit(run_agent, entry, ctx.provider, ctx.work_dir, ctx.dry_map)
        ] = entry
    return None


def has_awaiting_approval(work_dir):
    """status.json 中存在待审批任务；缺失/损坏/结构异常一律 False（落回空轮计数，不改现有行为）。"""
    try:
        tasks = load_status(work_dir)["tasks"]
        return any(t.get("status") == "awaiting_approval" for t in tasks.values())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def loop_step(ctx):
    """单轮调度：收割 → 问 get_task → 派发/自愈 → 等待任一完成。

    返回 None 表示继续下一轮，否则为进程退出码。
    """
    # ① 收割已完成
    harvest_done(ctx.work_dir, ctx.inflight)
    # ② 问 get_task 要裁决 / 新批次（每次收割后立即补位，无批内 barrier；
    #    输出合法性已由 ask_get_task 一次判尽）
    next_tasks, exit_code = ask_get_task(ctx.work_dir)
    if exit_code is not None:
        return exit_code
    if isinstance(next_tasks, dict):  # 终结裁决
        if ctx.inflight:
            # 排干：终结信号到达时仍有在飞 → 等收割后由下一轮 get_task 重裁决
            # （exhausted 标记粘滞且短路先于批次选择，裁决必然复现），不留孤儿进程
            wait(list(ctx.inflight), return_when=FIRST_COMPLETED)
            return None
        return terminal_exit(ctx.work_dir, next_tasks)
    if next_tasks:
        # 派发（预占 + submit）后直落 ③ 等待，省一次必然空批的 get_task 调用
        ctx.empty_rounds = 0
        exit_code = dispatch_batch(ctx, next_tasks)
        if exit_code is not None:
            return exit_code
    elif not ctx.inflight:
        if has_awaiting_approval(ctx.work_dir):
            # 待审批不算空轮：按固定间隔轮询等人工审批到达，不进自愈/退出计数
            ctx.empty_rounds = 0
            time.sleep(APPROVAL_POLL_SECONDS)
            return None
        # 空轮自愈（仅无在飞时）：任务滞留瞬态 → 重置再试，直接进下一轮不等待
        ctx.empty_rounds += 1
        if ctx.empty_rounds > MAX_EMPTY_ROUNDS:
            return err("连续 %d 轮无可派发任务" % MAX_EMPTY_ROUNDS)
        reset_transient(ctx.work_dir)
        return None
    # ③ 等任一完成 → 回 ①
    wait(list(ctx.inflight), return_when=FIRST_COMPLETED)
    return None


def loop(work_dir, provider, dry_map):
    max_parallel = read_max_parallel(work_dir)
    if not isinstance(max_parallel, int) or isinstance(max_parallel, bool) or max_parallel < 1:
        return err("无法从 workflow yaml 读取合法的 max_parallel")

    # 常驻共享池 + 全部轮间状态聚合进 ctx（仅主线程读写）
    ctx = LoopContext(work_dir, provider, dry_map, ThreadPoolExecutor(max_workers=max_parallel))
    try:
        while True:
            exit_code = loop_step(ctx)
            if exit_code is not None:
                return exit_code
    finally:
        ctx.executor.shutdown()


def parse_args():
    parser = argparse.ArgumentParser(description="Workflow orchestrator")
    parser.add_argument("--yaml", required=True, help="path to the workflow definition file")
    parser.add_argument(
        "--work-dir", required=True, help="working directory for all workflow artifacts"
    )
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDERS),
        default=None,
        help="Coding Agent CLI used to execute the workflow's tasks",
    )
    parser.add_argument("--prompt", default=None, help="development task prompt (first run only)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="simulate agents from .workflow/dry_replies.json (UT only)",
    )
    return parser.parse_args()


def _resume_workflow(args, status_path):
    """Resume an in-flight workflow after checking the recorded yaml identity."""
    if args.prompt:
        print(
            "[orchestrator] 警告: 工作流已在执行中(%s 已存在)，"
            "--prompt 已被忽略，恢复执行时不应传递 prompt" % status_path,
            file=sys.stderr,
        )
    try:
        with open(status_path, encoding="utf-8") as f:
            recorded = json.load(f).get("workflow")
    except (OSError, json.JSONDecodeError) as e:
        return err("恢复失败: 无法读取 %s: %s" % (status_path, e))
    current = os.path.abspath(args.yaml)
    if recorded != current:
        return err(
            "该工作区已存在另一个工作流的状态: %s 记录 %s，本次 --yaml 为 %s；"
            "请删除 %s 目录或换一个干净工作区后重试"
            % (
                status_path,
                recorded or "<缺失 workflow 字段>",
                current,
                os.path.dirname(status_path),
            )
        )
    try:
        reset_transient(args.work_dir)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        return err("恢复失败: %s" % e)
    return 0


def _init_workflow(args, status_path):
    """Initialize a fresh workflow via init_status.py; a prompt is required."""
    if not args.prompt:
        print(
            "[orchestrator] 错误: 工作流未初始化(%s 不存在)，"
            "首次运行必须提供 --prompt" % status_path,
            file=sys.stderr,
        )
        return 1
    print("[orchestrator] 初始化工作流: %s" % status_path)
    return subprocess.run(
        [
            sys.executable,
            os.path.join(SCRIPTS_DIR, "init_status.py"),
            "--yaml",
            args.yaml,
            "--work-dir",
            args.work_dir,
            "--prompt",
            args.prompt,
        ]
    ).returncode


def prepare_workflow(args):
    """Initialize or resume the workflow, returning its preparation exit code."""
    status_path = os.path.join(args.work_dir, ".workflow", "status.json")

    if os.path.exists(status_path):
        return _resume_workflow(args, status_path)
    return _init_workflow(args, status_path)


def main():
    args = parse_args()
    if not args.dry_run and not args.provider:
        return err("必须提供 --provider（或用 --dry-run 模拟）")
    if acquire_lock(args.work_dir) is None:
        return err("另一个 orchestrator 实例正在运行（.workflow/orchestrator.lock），拒绝双跑")
    rc = prepare_workflow(args)
    if rc != 0:
        return rc

    dry_map = None
    if args.dry_run:
        path = os.path.join(args.work_dir, ".workflow", "dry_replies.json")
        try:
            with open(path, encoding="utf-8") as f:
                dry_map = json.load(f)
        except (OSError, json.JSONDecodeError):
            dry_map = {}
    try:
        return loop(args.work_dir, PROVIDERS.get(args.provider), dry_map)
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as e:
        # JSONDecodeError ⊂ ValueError，不重复捕获；CalledProcessError = copy_tree 的 cp 失败
        return err("主循环异常: %s" % e)


if __name__ == "__main__":
    sys.exit(main())
