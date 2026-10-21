# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

"""Blackbox tests for the workflow-orchestrator skill.

These tests exercise ``orchestrator.py`` only through its documented CLI in
``--dry-run`` mode (simulated agents), asserting on exit codes, stdout, and the
persisted artifacts (``status.json`` / ``log.jsonl``). ``OrchestratorTest``
drives the orchestrator only through this CLI — it stays a blackbox, its source
intentionally not read here. ``BuildPromptTest`` is the sole exception: a
whitebox unit test of the pure function ``get_task.build_prompt``.

Run from the skill root (or anywhere)::

    python3 -m unittest discover -s harness/workflow-orchestrator/tests

or directly::

    python3 harness/workflow-orchestrator/tests/test_orchestrator.py
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from dataclasses import dataclass
from unittest.mock import patch
from pathlib import Path

import yaml

SKILL_ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = SKILL_ROOT / "scripts" / "orchestrator.py"

sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import get_task  # noqa: E402  白盒：借用纯函数 build_prompt / validate_workflow
from verdict_common import verdict_file_path  # noqa: E402


def _node(node_id, **overrides):
    """A valid normal task node; overrides let a test break one field."""
    node = {
        "id": node_id,
        "task_type": "normal",
        "title": f"Task {node_id}",
        "goal": ["finish the task"],
        "approach": ["do the work"],
        "acceptance": ["true"],
        "out_of_scope": ["nothing"],
        "depends_on": [],
        "executor": "general-executor",
        "verifier": "general-verifier",
        "max_retries": 0,
        "on_exhaust": "exit",
    }
    node.update(overrides)
    return node


def _workflow_yaml(nodes, max_parallel=1, max_rollbacks=None):
    wf = {"workflow": "test", "max_parallel": max_parallel, "nodes": nodes}
    if max_rollbacks is not None:
        wf["max_rollbacks"] = max_rollbacks
    return yaml.safe_dump(wf, sort_keys=False)


@dataclass(frozen=True)
class WorkflowOptions:
    max_parallel: int = 1
    max_rollbacks: int | None = None


def _rollback_nodes():
    """Two-node workflow in which b rolls back to a."""
    return [
        _node("a"),
        _node("b", depends_on=["a"], on_exhaust="rollback", rollback_to="a"),
    ]


def run_orchestrator(
    nodes=None,
    yaml_text=None,
    dry_replies=None,
    options=None,
    pre_files=None,
):
    """Run orchestrator.py with --dry-run; return (exit_code, output, work_dir).

    pre_files: {相对路径: 内容}，运行前写入 work_dir（如子图 yaml、手工 status.json）。
    """
    options = options or WorkflowOptions()
    work_dir = tempfile.mkdtemp(prefix="wo-test-")
    wf_path = Path(work_dir) / "workflow.yaml"
    wf_path.write_text(
        yaml_text
        if yaml_text is not None
        else _workflow_yaml(nodes, options.max_parallel, options.max_rollbacks)
    )
    for rel, content in (pre_files or {}).items():
        p = Path(work_dir) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    if dry_replies is not None:
        wr = Path(work_dir) / ".workflow"
        wr.mkdir(parents=True, exist_ok=True)
        (wr / "dry_replies.json").write_text(json.dumps(dry_replies))
    proc = subprocess.run(
        [
            sys.executable,
            str(ORCHESTRATOR),
            "--yaml",
            str(wf_path),
            "--work-dir",
            work_dir,
            "--dry-run",
            "--prompt",
            "test",
        ],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr, work_dir


def read_status(work_dir):
    return json.loads((Path(work_dir) / ".workflow" / "status.json").read_text())


def read_log(work_dir):
    lines = (Path(work_dir) / ".workflow" / "log.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _run_orchestrator_dry(wf, work_dir):
    """以 --dry-run 运行编排器（work_dir 已就绪）；返回 (returncode, out)。"""
    proc = subprocess.run(
        [
            sys.executable,
            str(ORCHESTRATOR),
            "--yaml",
            str(wf),
            "--work-dir",
            work_dir,
            "--dry-run",
        ],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


class OrchestratorTest(unittest.TestCase):
    def setUp(self):
        self._work_dirs = []

    def tearDown(self):
        for d in self._work_dirs:
            shutil.rmtree(d, ignore_errors=True)

    def _run(self, **kwargs):
        code, out, work_dir = run_orchestrator(**kwargs)
        self._work_dirs.append(work_dir)
        return code, out, work_dir

    def _legacy_work_dir(self, nodes, tasks, seq=1, dry_replies=None):
        """构造「旧账本」work_dir：写 workflow.yaml + 手工 status.json，返回 (work_dir, wf, wr)。"""
        work_dir = tempfile.mkdtemp(prefix="wo-test-")
        self._work_dirs.append(work_dir)
        wf = Path(work_dir) / "workflow.yaml"
        wf.write_text(_workflow_yaml(nodes))
        wr = Path(work_dir) / ".workflow"
        wr.mkdir()
        (wr / "user_prompt.md").write_text("test\n")
        (wr / "status.json").write_text(
            json.dumps(
                {
                    "workflow": str(wf),
                    "work_dir": work_dir,
                    "user_prompt": str(wr / "user_prompt.md"),
                    "provider": "dry",
                    "seq": seq,
                    "rollbacks_used": 0,
                    "tasks": tasks,
                }
            )
        )
        (wr / "dry_replies.json").write_text(json.dumps(dry_replies or {}))
        return work_dir, wf, wr

    def _pending_advice_fixture(self):
        nodes = [
            _node("a"),
            _node("b", depends_on=["a"], on_exhaust="rollback", rollback_to="a"),
        ]
        wd, wf, wr = self._legacy_work_dir(
            nodes,
            {
                "a": {
                    "status": "pass",
                    "retries": 0,
                    "pass_seq": 1,
                    "checkpoint_seq": 0,
                },
                "b": {"status": "fail", "retries": 1},
            },
        )
        ckpt = wr / "checkpoints" / "a"
        ckpt.mkdir(parents=True)
        (ckpt / "workflow.yaml").write_text(wf.read_text())
        (ckpt / "marker.txt").write_text("baseline")
        (Path(wd) / "marker.txt").write_text("failed attempt")
        return wd, wf, wr

    def _poll_advice(self, wd):
        proc = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts/get_task.py"), wd],
            capture_output=True,
            text=True,
        )
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        return json.loads(proc.stdout)

    def test_advice_two_polls_archive_once_and_inline_content(self):
        wd, wf, wr = self._pending_advice_fixture()
        first = self._poll_advice(wd)
        self.assertEqual(first[0].get("phase"), "advice")
        self.assertEqual(set(read_status(wd)["tasks"]), {"a", "b"})
        self.assertIn("advice_pending", read_status(wd))
        history = wr / "history" / "b.to.a.1"
        self.assertEqual((history / "marker.txt").read_text(), "failed attempt")
        self.assertEqual((Path(wd) / "marker.txt").read_text(), "baseline")
        self.assertEqual(first, self._poll_advice(wd))
        self.assertEqual(len(list((wr / "history").iterdir())), 1)
        self.assertEqual(read_status(wd)["rollbacks_used"], 1)
        advice = wr / "advice" / "b.to.a.1.md"
        self.assertFalse(advice.exists())
        advice.write_text("Unique recovery instruction: preserve the seed.")
        second = self._poll_advice(wd)
        self.assertEqual(second[0]["task_id"], "a")
        self.assertIn("Unique recovery instruction", second[0]["prompt"])
        self.assertNotIn("advice_pending", read_status(wd))
        status = read_status(wd)
        status["tasks"]["a"].update(status="pass", pass_seq=2)
        (wr / "status.json").write_text(json.dumps(status))
        downstream = self._poll_advice(wd)
        self.assertEqual(downstream[0]["task_id"], "b")
        self.assertNotIn("Unique recovery instruction", downstream[0]["prompt"])

    def test_empty_advice_does_not_dispatch_redo(self):
        wd, wf, wr = self._pending_advice_fixture()
        first = self._poll_advice(wd)
        (wr / "advice" / "b.to.a.1.md").write_text("   ")
        self.assertEqual(first, self._poll_advice(wd))
        self.assertIn("advice_pending", read_status(wd))

    def test_orchestrator_stops_when_advice_output_missing(self):
        wd, wf, wr = self._pending_advice_fixture()
        with patch.object(
            get_task.orch, "run_agent", return_value=("advice-written", False)
        ) as run:
            result = get_task.orch.loop(wd, None, None)
        self.assertEqual(result, 1)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0]["phase"], "advice")
        self.assertIn("error", read_status(wd)["advice_pending"])
        self.assertEqual(read_status(wd)["rollbacks_used"], 1)

    def test_orchestrator_stops_after_advice_crash(self):
        wd, wf, wr = self._pending_advice_fixture()
        with patch.object(get_task.orch, "run_agent", return_value=(None, True)) as run:
            result = get_task.orch.loop(wd, None, None)
        self.assertEqual(result, 1)
        self.assertEqual(run.call_count, 1)
        self.assertIn("error", read_status(wd)["advice_pending"])

    def test_init_without_provider(self):
        wd = tempfile.mkdtemp(prefix="wo-test-")
        self._work_dirs.append(wd)
        wf = Path(wd) / "workflow.yaml"
        wf.write_text(_workflow_yaml([_node("a")]))
        proc = subprocess.run(
            [
                sys.executable,
                str(SKILL_ROOT / "scripts/init_status.py"),
                "--yaml",
                str(wf),
                "--work-dir",
                wd,
                "--prompt",
                "test",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("provider", read_status(wd))

    def test_happy_path_single_node(self):
        code, out, wd = self._run(nodes=[_node("setup")])
        self.assertEqual(code, 0, out)
        self.assertEqual(read_status(wd)["tasks"]["setup"]["status"], "pass")
        events = [e["event"] for e in read_log(wd)]
        self.assertIn("init", events)
        self.assertIn("finish", events)

    def test_status_ledger_fields(self):
        code, out, wd = self._run(nodes=[_node("setup")])
        self.assertEqual(code, 0, out)
        status = read_status(wd)
        self.assertNotIn("provider", status)
        self.assertEqual(status.get("rollbacks_used"), 0)
        self.assertGreaterEqual(status.get("seq", 0), 1)
        task = status["tasks"]["setup"]
        self.assertEqual(task.get("pass_seq"), 1)
        self.assertNotIn("advice", task)

    def test_checkpoint_snapshot_taken(self):
        nodes = [
            _node("setup"),
            _node(
                "rollback",
                depends_on=["setup"],
                on_exhaust="rollback",
                rollback_to="setup",
            ),
            _node("downstream", depends_on=["rollback"]),
        ]
        code, out, wd = self._run(nodes=nodes, pre_files={"hello.txt": "hi\n"})
        self.assertEqual(code, 0, out)
        ckpt = Path(wd) / ".workflow" / "checkpoints" / "setup"
        self.assertTrue((ckpt / "hello.txt").is_file())
        self.assertEqual((ckpt / "hello.txt").read_text(), "hi\n")
        self.assertFalse((ckpt / ".workflow").exists())  # .workflow 不进快照
        # 首次派发时还没有任何 pass，seq=0
        status = read_status(wd)
        self.assertEqual(status["tasks"]["setup"].get("checkpoint_seq"), 0)
        self.assertNotIn("checkpoint_seq", status["tasks"]["rollback"])
        self.assertNotIn("checkpoint_seq", status["tasks"]["downstream"])
        self.assertFalse((Path(wd) / ".workflow" / "checkpoints" / "rollback").exists())
        self.assertFalse(
            (Path(wd) / ".workflow" / "checkpoints" / "downstream").exists()
        )

    def test_dependency_chain_completes(self):
        nodes = [_node("a"), _node("b", depends_on=["a"])]
        code, out, wd = self._run(nodes=nodes)
        self.assertEqual(code, 0, out)
        tasks = read_status(wd)["tasks"]
        self.assertEqual(tasks["a"]["status"], "pass")
        self.assertEqual(tasks["b"]["status"], "pass")

    def test_independent_nodes_run_in_parallel(self):
        nodes = [_node("a"), _node("b")]
        code, out, wd = self._run(nodes=nodes, options=WorkflowOptions(max_parallel=2))
        self.assertEqual(code, 0, out)
        tasks = read_status(wd)["tasks"]
        self.assertEqual(tasks["a"]["status"], "pass")
        self.assertEqual(tasks["b"]["status"], "pass")

    def test_empty_nodes_rejected(self):
        code, out, _ = self._run(
            yaml_text="workflow: test\nmax_parallel: 1\nnodes: []\n"
        )
        self.assertEqual(code, 1, out)
        self.assertIn("没有任务节点", out)

    def test_missing_node_key_rejected(self):
        node = _node("t1")
        del node["approach"]
        code, out, _ = self._run(nodes=[node])
        self.assertEqual(code, 2, out)
        self.assertIn("approach", out)

    def test_invalid_task_type_rejected(self):
        code, out, _ = self._run(nodes=[_node("t1", task_type="bogus")])
        self.assertEqual(code, 2, out)
        self.assertIn("normal/subgraph", out)

    def test_retry_then_pass(self):
        node = _node("t1", max_retries=1)
        code, out, wd = self._run(
            nodes=[node],
            dry_replies={
                "t1": ["executed", "$VERDICT:fail", "executed", "$VERDICT:pass"]
            },
        )
        self.assertEqual(code, 0, out)
        task = read_status(wd)["tasks"]["t1"]
        self.assertEqual(task["status"], "pass")
        self.assertEqual(task["retries"], 1)

    def test_fail_exhausts_budget(self):
        node = _node("t1", max_retries=1)
        code, out, wd = self._run(
            nodes=[node],
            dry_replies={
                "t1": ["executed", "$VERDICT:fail", "executed", "$VERDICT:fail"]
            },
        )
        self.assertEqual(code, 1, out)
        task = read_status(wd)["tasks"]["t1"]
        self.assertEqual(task["status"], "fail")
        self.assertTrue(task["exhausted"])
        self.assertGreaterEqual(task["retries"], 1)

    def test_max_rollbacks_invalid_rejected(self):
        node = _node("t1")
        for bad in (-1, 1.5, "2", True):
            code, out, _ = self._run(
                yaml_text=_workflow_yaml([node], max_rollbacks=bad)
            )
            self.assertEqual(code, 2, out)
            self.assertIn("max_rollbacks", out)

    def test_rollback_without_rollback_to_rejected(self):
        code, out, _ = self._run(nodes=[_node("t1", on_exhaust="rollback")])
        self.assertEqual(code, 2, out)
        self.assertIn("rollback_to", out)

    def test_rollback_to_ignored_when_on_exhaust_not_rollback(self):
        # on_exhaust!=rollback：rollback_to 完全忽略，即使指向不存在的节点也照常跑完
        code, out, wd = self._run(
            nodes=[_node("t1", on_exhaust="exit", rollback_to="ghost")]
        )
        self.assertEqual(code, 0, out)
        self.assertEqual(read_status(wd)["tasks"]["t1"]["status"], "pass")

    def test_rollback_to_unknown_rejected(self):
        code, out, _ = self._run(
            nodes=[_node("t1", on_exhaust="rollback", rollback_to="ghost")]
        )
        self.assertEqual(code, 2, out)
        self.assertIn("rollback_to", out)

    def test_rollback_to_non_ancestor_rejected(self):
        nodes = [
            _node("a"),
            _node("b", depends_on=["a"]),
            _node("c", on_exhaust="rollback", rollback_to="b"),
        ]  # c 不依赖 b
        code, out, _ = self._run(nodes=nodes)
        self.assertEqual(code, 2, out)
        self.assertIn("上游", out)

    def test_rollback_to_subgraph_node_rejected(self):
        nodes = [
            _node("a"),
            {
                "id": "sg",
                "task_type": "subgraph",
                "file": "sub.yaml",
                "depends_on": ["a"],
            },
            _node("b", depends_on=["a"], on_exhaust="rollback", rollback_to="sg"),
        ]
        code, out, _ = self._run(nodes=nodes)
        self.assertEqual(code, 2, out)
        self.assertIn("subgraph", out)

    def test_rollback_budget_exhausted_stuck(self):
        nodes = _rollback_nodes()
        code, out, wd = self._run(
            nodes=nodes,
            options=WorkflowOptions(max_rollbacks=0),
            dry_replies={
                "a": ["executed", "$VERDICT:pass"],
                "b": ["executed", "$VERDICT:fail"],
            },
        )
        self.assertEqual(code, 1, out)
        self.assertIn("回滚预算耗尽", out)
        self.assertIn("工作流卡住", out)
        self.assertIn("rollbacks_used=0 >= max_rollbacks=0", out)
        self.assertNotIn("rollback_pending", read_status(wd))  # 预算耗尽路径不置标记

    def test_subgraph_child_rollback_to_outside_rejected(self):
        # 子图子节点的 rollback_to 在子图命名空间解析：引用父级节点 = 引用不存在
        sub = {"nodes": [_node("x", on_exhaust="rollback", rollback_to="a")]}
        nodes = [
            _node("a"),
            {
                "id": "sg",
                "task_type": "subgraph",
                "file": "sub.yaml",
                "depends_on": ["a"],
            },
        ]
        code, out, _ = self._run(
            nodes=nodes, pre_files={"sub.yaml": yaml.safe_dump(sub)}
        )
        self.assertEqual(code, 2, out)
        self.assertIn("rollback_to", out)

    def test_rollback_full_cycle(self):
        nodes = [
            _node("a"),
            _node("b", depends_on=["a"]),
            _node(
                "c",
                depends_on=["b"],
                max_retries=0,
                on_exhaust="rollback",
                rollback_to="a",
            ),
        ]
        replies = {
            "a": ["executed", "$VERDICT:pass", "executed", "$VERDICT:pass"],
            "b": ["executed", "$VERDICT:pass", "executed", "$VERDICT:pass"],
            "c": ["executed", "$VERDICT:fail", "executed", "$VERDICT:pass"],
        }
        code, out, wd = self._run(
            nodes=nodes, dry_replies=replies, pre_files={"seed.txt": "v1\n"}
        )
        self.assertEqual(code, 0, out)
        status = read_status(wd)
        self.assertEqual(status.get("rollbacks_used"), 1)
        self.assertNotIn("rollback_pending", status)
        for tid in ("a", "b", "c"):
            self.assertEqual(status["tasks"][tid]["status"], "pass")
            self.assertEqual(status["tasks"][tid]["retries"], 0)
        # advice 占位文件（dry）；Y=a 的 advice 字段 pass 后已清除
        self.assertTrue((Path(wd) / ".workflow" / "advice" / "c.to.a.1.md").is_file())
        self.assertNotIn("advice", status["tasks"]["a"])
        # 失败时间线产物已归档；seed.txt 在 checkpoint(a) 拍摄前已存在，恢复后仍在
        self.assertTrue(
            (Path(wd) / ".workflow" / "history" / "c.to.a.1" / "seed.txt").is_file()
        )
        self.assertTrue((Path(wd) / "seed.txt").is_file())
        # 重置时删旧 checkpoint，重跑时重拍
        self.assertTrue(
            (Path(wd) / ".workflow" / "checkpoints" / "a" / "seed.txt").is_file()
        )
        # 日志含 rollback 事件（带 history/advice 字段）
        rollbacks = [e for e in read_log(wd) if e["event"] == "rollback"]
        self.assertEqual(len(rollbacks), 1)
        self.assertEqual(rollbacks[0]["from"], "c")
        self.assertEqual(rollbacks[0]["to"], "a")
        self.assertIn("history", rollbacks[0])
        self.assertIn("advice", rollbacks[0])

    def test_rollback_drains_inflight(self):
        # b 快速失败触发回滚时 d 仍在执行 → 输出 [] 自然排干，d 收尾后才执行回滚
        nodes = [
            _node("a"),
            _node(
                "b",
                depends_on=["a"],
                max_retries=0,
                on_exhaust="rollback",
                rollback_to="a",
            ),
            _node("d", depends_on=["a"]),
        ]
        replies = {
            "a": ["executed", "$VERDICT:pass", "executed", "$VERDICT:pass"],
            "b": ["executed", "$VERDICT:fail", "executed", "$VERDICT:pass"],
            "d": [
                "$SLEEP:2",
                "executed",
                "$VERDICT:pass",
            ],  # 首轮 execute 慢；executed 态被重置后重做
        }
        code, out, wd = self._run(
            nodes=nodes, dry_replies=replies, options=WorkflowOptions(max_parallel=2)
        )
        self.assertEqual(code, 0, out)
        status = read_status(wd)
        self.assertEqual(status.get("rollbacks_used"), 1)
        for tid in ("a", "b", "d"):
            self.assertEqual(status["tasks"][tid]["status"], "pass")
        # d 首轮从未 pass（executed 态被重置）；d 不是 rollback 目标，不创建 checkpoint
        self.assertNotIn("checkpoint_seq", status["tasks"]["d"])

    def test_rollback_without_checkpoint_stuck(self):
        # 旧账本：a 无 checkpoint_seq → 回滚无法执行 → STUCK，rollback_pending 留账
        nodes = _rollback_nodes()
        tasks = {
            "a": {"status": "pass", "retries": 0},  # 旧账本：无 pass_seq/checkpoint_seq
            "b": {"status": "fail", "retries": 1, "exhausted": True},
        }
        work_dir, wf, _ = self._legacy_work_dir(nodes, tasks)
        code, out = _run_orchestrator_dry(wf, work_dir)
        self.assertEqual(code, 1, out)
        self.assertIn("checkpoint", out)
        self.assertIn("rollback_pending", read_status(work_dir))

    def test_subgraph_child_rollback(self):
        sub = {
            "nodes": [
                _node("x"),
                _node(
                    "y",
                    depends_on=["x"],
                    max_retries=0,
                    on_exhaust="rollback",
                    rollback_to="x",
                ),
            ]
        }
        nodes = [
            _node("pre"),
            {
                "id": "sg",
                "task_type": "subgraph",
                "file": "sub.yaml",
                "depends_on": ["pre"],
            },
        ]
        replies = {
            "pre": ["executed", "$VERDICT:pass"],
            "sg/x": ["executed", "$VERDICT:pass", "executed", "$VERDICT:pass"],
            "sg/y": ["executed", "$VERDICT:fail", "executed", "$VERDICT:pass"],
        }
        code, out, wd = self._run(
            nodes=nodes,
            dry_replies=replies,
            pre_files={"sub.yaml": yaml.safe_dump(sub)},
        )
        self.assertEqual(code, 0, out)
        status = read_status(wd)
        self.assertEqual(status.get("rollbacks_used"), 1)
        for tid in ("pre", "sg/x", "sg/y"):
            self.assertEqual(status["tasks"][tid]["status"], "pass")
        # 子图子任务的 checkpoint 按 sg/child 嵌套；advice/history 文件名 / 转写为 __
        self.assertTrue((Path(wd) / ".workflow" / "checkpoints" / "sg" / "x").is_dir())
        self.assertTrue(
            (Path(wd) / ".workflow" / "advice" / "sg__y.to.sg__x.1.md").is_file()
        )
        self.assertTrue(
            (Path(wd) / ".workflow" / "history" / "sg__y.to.sg__x.1").is_dir()
        )
        self.assertEqual(status.get("checkpoint_targets"), ["sg/x"])
        self.assertNotIn("checkpoint_seq", status["tasks"]["sg/y"])
        self.assertFalse((Path(wd) / ".workflow" / "checkpoints" / "sg" / "y").exists())
        # sg/x 的 checkpoint 是稳定基线，回滚后重跑不重拍
        self.assertEqual(status["tasks"]["sg/x"].get("checkpoint_seq"), 1)

    def test_node_id_with_slash_rejected(self):
        code, out, _ = self._run(nodes=[_node("a/b")])
        self.assertEqual(code, 2, out)
        self.assertIn("'/'", out)

    def test_rollback_resets_later_parallel_pass(self):
        # c 与 b 平行（都依赖 a）；c 在 checkpoint(a) 之后 pass → 回滚时一并重置重跑
        nodes = [
            _node("a"),
            _node(
                "b",
                depends_on=["a"],
                max_retries=0,
                on_exhaust="rollback",
                rollback_to="a",
            ),
            _node("c", depends_on=["a"]),
        ]
        replies = {
            "a": ["executed", "$VERDICT:pass", "executed", "$VERDICT:pass"],
            "b": [
                "$SLEEP:2",
                "$VERDICT:fail",
                "executed",
                "$VERDICT:pass",
            ],  # 首轮 execute 慢，让 c 先 pass
            "c": ["executed", "$VERDICT:pass", "executed", "$VERDICT:pass"],
        }
        code, out, wd = self._run(
            nodes=nodes, dry_replies=replies, options=WorkflowOptions(max_parallel=2)
        )
        self.assertEqual(code, 0, out)
        status = read_status(wd)
        self.assertEqual(status.get("rollbacks_used"), 1)
        for tid in ("a", "b", "c"):
            self.assertEqual(status["tasks"][tid]["status"], "pass")
        # c 被重置后第二轮重跑时仍不创建 checkpoint：它不是 rollback 目标
        self.assertNotIn("checkpoint_seq", status["tasks"]["c"])

    def test_rollback_resets_cross_subgraph_continue(self):
        # x2(continue 耗尽) 经子图节点 sg 才是 a 的传递下游 → 豁免失效，一并重置重跑
        sub = {"nodes": [_node("k")]}
        nodes = [
            _node("a"),
            {
                "id": "sg",
                "task_type": "subgraph",
                "file": "sub.yaml",
                "depends_on": ["a"],
            },
            _node("x2", depends_on=["sg"], max_retries=0, on_exhaust="continue"),
            _node(
                "x",
                depends_on=["a"],
                max_retries=0,
                on_exhaust="rollback",
                rollback_to="a",
            ),
        ]
        replies = {
            "a": ["executed", "$VERDICT:pass", "executed", "$VERDICT:pass"],
            "sg/k": ["executed", "$VERDICT:pass", "executed", "$VERDICT:pass"],
            "x": [
                "$SLEEP:2",
                "$VERDICT:fail",
                "executed",
                "$VERDICT:pass",
            ],  # 首轮 execute 慢，让 x2 先耗尽
            "x2": ["executed", "$VERDICT:fail", "executed", "$VERDICT:pass"],
        }
        code, out, wd = self._run(
            nodes=nodes,
            dry_replies=replies,
            options=WorkflowOptions(max_parallel=2),
            pre_files={"sub.yaml": yaml.safe_dump(sub)},
        )
        self.assertEqual(code, 0, out)
        status = read_status(wd)
        self.assertEqual(status.get("rollbacks_used"), 1)
        for tid in ("a", "sg/k", "x2", "x"):
            self.assertEqual(status["tasks"][tid]["status"], "pass")

    def test_rollback_pending_exit_exhausted_stuck_first(self):
        # rollback_pending 待执行时另一节点 exit 耗尽 → STUCK 优先，回滚不执行、标记留账
        nodes = [
            _node("a"),
            _node(
                "b",
                depends_on=["a"],
                max_retries=0,
                on_exhaust="rollback",
                rollback_to="a",
            ),
            _node("e", depends_on=["a"], max_retries=0, on_exhaust="exit"),
        ]
        tasks = {
            "a": {"status": "pass", "retries": 0},
            "b": {"status": "fail", "retries": 1, "exhausted": True},
            "e": {"status": "fail", "retries": 1, "exhausted": True},
        }
        work_dir, wf, _ = self._legacy_work_dir(nodes, tasks)
        code, out = _run_orchestrator_dry(wf, work_dir)
        self.assertEqual(code, 1, out)
        self.assertIn("工作流卡住", out)
        # 回滚未执行：rollbacks_used 仍为 0、b 保持 fail、标记留账供排查
        status = read_status(work_dir)
        self.assertEqual(status.get("rollbacks_used"), 0)
        self.assertIn("rollback_pending", status)
        self.assertEqual(status["tasks"]["b"]["status"], "fail")

    def test_second_rollback_trigger_free_redo(self):
        # 同轮第二个 rollback 触发不置标记不吃预算：回滚执行时一并重置（免费重做）
        nodes = [
            _node("a"),
            _node(
                "b",
                depends_on=["a"],
                max_retries=0,
                on_exhaust="rollback",
                rollback_to="a",
            ),
            _node(
                "c",
                depends_on=["a"],
                max_retries=0,
                on_exhaust="rollback",
                rollback_to="a",
            ),
        ]
        replies = {
            "a": ["executed", "$VERDICT:pass", "executed", "$VERDICT:pass"],
            "b": ["executed", "$VERDICT:fail", "executed", "$VERDICT:pass"],
            "c": ["executed", "$VERDICT:fail", "executed", "$VERDICT:pass"],
        }
        code, out, wd = self._run(
            nodes=nodes, dry_replies=replies, options=WorkflowOptions(max_parallel=2)
        )
        self.assertEqual(code, 0, out)
        status = read_status(wd)
        self.assertEqual(status.get("rollbacks_used"), 1)
        for tid in ("a", "b", "c"):
            self.assertEqual(status["tasks"][tid]["status"], "pass")

    def test_multiple_rollbacks_sequence(self):
        # max_rollbacks=2：同一节点两次耗尽触发两次回滚，history/advice 按序号区分
        nodes = _rollback_nodes()
        replies = {
            "a": [
                "executed",
                "$VERDICT:pass",
                "executed",
                "$VERDICT:pass",
                "executed",
                "$VERDICT:pass",
            ],
            "b": [
                "executed",
                "$VERDICT:fail",
                "executed",
                "$VERDICT:fail",
                "executed",
                "$VERDICT:pass",
            ],
        }
        code, out, wd = self._run(
            nodes=nodes, dry_replies=replies, options=WorkflowOptions(max_rollbacks=2)
        )
        self.assertEqual(code, 0, out)
        status = read_status(wd)
        self.assertEqual(status.get("rollbacks_used"), 2)
        for n in (1, 2):
            self.assertTrue(
                (Path(wd) / ".workflow" / "advice" / ("b.to.a.%d.md" % n)).is_file()
            )
            self.assertTrue(
                (Path(wd) / ".workflow" / "history" / ("b.to.a.%d" % n)).is_dir()
            )
        self.assertEqual(status["tasks"]["b"]["status"], "pass")

    def test_rollback_preserves_legacy_pass(self):
        # 旧账本 pass 任务（无 pass_seq）视为 pass_seq=0：≤ checkpoint_seq(回滚目标) 保持不动
        nodes = _rollback_nodes()
        tasks = {
            "a": {"status": "pass", "retries": 0, "checkpoint_seq": 0},  # 无 pass_seq
            "b": {"status": "fail", "retries": 1, "exhausted": True},
        }
        work_dir, wf, wr = self._legacy_work_dir(
            nodes, tasks, seq=0, dry_replies={"b": ["executed", "$VERDICT:pass"]}
        )
        # execute_rollback 要恢复 checkpoint(a)：真实快照含 work_dir 顶层条目（恢复后
        # clear_tree 删掉的 workflow.yaml 随之还原），这里手工对齐，只需 workflow.yaml
        ckpt_a = wr / "checkpoints" / "a"
        ckpt_a.mkdir(parents=True)
        (ckpt_a / "workflow.yaml").write_text(wf.read_text())
        code, out = _run_orchestrator_dry(wf, work_dir)
        self.assertEqual(code, 0, out)
        status = read_status(work_dir)
        self.assertEqual(status.get("rollbacks_used"), 1)
        # a 保持 pass 未被重做（若被重置重跑，a 的 pass 会让 seq 变成 2）
        self.assertEqual(status.get("seq"), 1)
        self.assertEqual(status["tasks"]["a"]["status"], "pass")
        self.assertEqual(status["tasks"]["b"]["status"], "pass")

    def test_repeated_rollback_keeps_same_target_checkpoint(self):
        """A second rollback to the same target must consume the original baseline."""
        work_dir = tempfile.mkdtemp(prefix="wo-test-")
        self._work_dirs.append(work_dir)
        root = Path(work_dir)
        wr = root / ".workflow"
        wr.mkdir()
        marker = root / "marker.txt"
        marker.write_text("baseline-a\n")
        ckpt = wr / "checkpoints" / "a"
        ckpt.mkdir(parents=True)
        (ckpt / "marker.txt").write_text("baseline-a\n")
        a = _node("a")
        b = _node("b", depends_on=["a"], on_exhaust="rollback", rollback_to="a")
        tasks = {
            "a": {"status": "pass", "retries": 0, "pass_seq": 1, "checkpoint_seq": 0},
            "b": {"status": "fail", "retries": 1, "exhausted": True},
        }
        status = {
            "provider": "dry",
            "seq": 1,
            "rollbacks_used": 0,
            "tasks": tasks,
            "rollback_pending": {"from": "b", "to": "a"},
        }
        status_path = wr / "status.json"
        status_path.write_text(json.dumps(status))
        graph = ([(a, "a", []), (b, "b", ["a"])], {"a": a, "b": b}, {})

        self.assertEqual(
            get_task.execute_rollback(work_dir, status, str(status_path), graph, tasks),
            0,
        )
        self.assertTrue((ckpt / "marker.txt").is_file())

        # Simulate the target's successful redo, then trigger the same rollback again.
        tasks["a"].update(status="pass", pass_seq=2)
        tasks["b"].update(status="fail", retries=1, exhausted=True)
        status["rollback_pending"] = {"from": "b", "to": "a"}
        marker.write_text("changed-after-first-rollback\n")
        self.assertEqual(
            get_task.execute_rollback(work_dir, status, str(status_path), graph, tasks),
            0,
        )
        self.assertEqual(marker.read_text(), "baseline-a\n")

    def test_distinct_rollback_targets_keep_independent_checkpoints(self):
        """Resetting for target a must retain target b's independent baseline."""
        work_dir = tempfile.mkdtemp(prefix="wo-test-")
        self._work_dirs.append(work_dir)
        root = Path(work_dir)
        wr = root / ".workflow"
        wr.mkdir()
        marker = root / "marker.txt"
        marker.write_text("baseline-a\n")
        for target, value in (("a", "baseline-a\n"), ("b", "baseline-b\n")):
            d = wr / "checkpoints" / target
            d.mkdir(parents=True)
            (d / "marker.txt").write_text(value)
        a = _node("a")
        b = _node("b", depends_on=["a"])
        c = _node("c", depends_on=["b"], on_exhaust="rollback", rollback_to="b")
        tasks = {
            "a": {"status": "pass", "retries": 0, "pass_seq": 1, "checkpoint_seq": 0},
            "b": {"status": "pass", "retries": 0, "pass_seq": 2, "checkpoint_seq": 1},
            "c": {"status": "fail", "retries": 1, "exhausted": True},
        }
        status = {
            "provider": "dry",
            "seq": 2,
            "rollbacks_used": 0,
            "tasks": tasks,
            "rollback_pending": {"from": "c", "to": "a"},
        }
        status_path = wr / "status.json"
        status_path.write_text(json.dumps(status))
        graph = (
            [(a, "a", []), (b, "b", ["a"]), (c, "c", ["b"])],
            {"a": a, "b": b, "c": c},
            {},
        )

        self.assertEqual(
            get_task.execute_rollback(work_dir, status, str(status_path), graph, tasks),
            0,
        )
        self.assertTrue((wr / "checkpoints" / "b" / "marker.txt").is_file())

        tasks["a"].update(status="pass", pass_seq=3)
        tasks["b"].update(status="pass", pass_seq=4)
        tasks["c"].update(status="fail", retries=1, exhausted=True)
        status["rollback_pending"] = {"from": "c", "to": "b"}
        marker.write_text("changed-before-second-target\n")
        self.assertEqual(
            get_task.execute_rollback(work_dir, status, str(status_path), graph, tasks),
            0,
        )
        self.assertEqual(marker.read_text(), "baseline-b\n")

    def test_rollback_preserves_preexisting_non_target_checkpoint(self):
        """Rollback must retain checkpoints and metadata for non-target tasks."""
        work_dir = tempfile.mkdtemp(prefix="wo-test-")
        self._work_dirs.append(work_dir)
        root = Path(work_dir)
        wr = root / ".workflow"
        wr.mkdir()
        for target, value in (("a", "baseline-a\n"), ("b", "baseline-b\n")):
            d = wr / "checkpoints" / target
            d.mkdir(parents=True)
            (d / "marker.txt").write_text(value)
        a = _node("a")
        b = _node("b", depends_on=["a"])
        c = _node("c", depends_on=["b"], on_exhaust="rollback", rollback_to="a")
        tasks = {
            "a": {"status": "pass", "retries": 0, "pass_seq": 1, "checkpoint_seq": 0},
            "b": {"status": "pass", "retries": 0, "pass_seq": 2, "checkpoint_seq": 1},
            "c": {"status": "fail", "retries": 1, "exhausted": True},
        }
        status = {
            "provider": "dry",
            "seq": 2,
            "rollbacks_used": 0,
            "tasks": tasks,
            "rollback_pending": {"from": "c", "to": "a"},
        }
        status_path = wr / "status.json"
        status_path.write_text(json.dumps(status))
        graph = (
            [(a, "a", []), (b, "b", ["a"]), (c, "c", ["b"])],
            {"a": a, "b": b, "c": c},
            {},
        )

        self.assertEqual(
            get_task.execute_rollback(work_dir, status, str(status_path), graph, tasks),
            0,
        )
        self.assertEqual(tasks["b"].get("checkpoint_seq"), 1)
        self.assertTrue((wr / "checkpoints" / "b" / "marker.txt").is_file())

    def test_child_rollback_target_uses_namespaced_checkpoint(self):
        """A bare child rollback_to resolves to and restores sg/x's checkpoint."""
        work_dir = tempfile.mkdtemp(prefix="wo-test-")
        self._work_dirs.append(work_dir)
        root = Path(work_dir)
        wr = root / ".workflow"
        wr.mkdir()
        marker = root / "marker.txt"
        marker.write_text("child-baseline\n")
        ckpt = wr / "checkpoints" / "sg" / "x"
        ckpt.mkdir(parents=True)
        (ckpt / "marker.txt").write_text("child-baseline\n")
        x = _node("x")
        y = _node("y", depends_on=["x"], on_exhaust="rollback", rollback_to="x")
        tasks = {
            "sg/x": {
                "status": "pass",
                "retries": 0,
                "pass_seq": 1,
                "checkpoint_seq": 0,
            },
            "sg/y": {"status": "fail", "retries": 1, "exhausted": True},
        }
        status = {
            "provider": "dry",
            "seq": 1,
            "rollbacks_used": 0,
            "tasks": tasks,
            "rollback_pending": {"from": "sg/y", "to": "sg/x"},
        }
        status_path = wr / "status.json"
        status_path.write_text(json.dumps(status))
        graph = (
            [(x, "sg/x", []), (y, "sg/y", ["sg/x"])],
            {"sg": {"id": "sg", "task_type": "subgraph", "depends_on": []}},
            {"sg": [x, y]},
        )

        self.assertEqual(
            get_task.execute_rollback(work_dir, status, str(status_path), graph, tasks),
            0,
        )
        self.assertTrue(ckpt.is_dir())
        marker.write_text("changed-child\n")
        tasks["sg/x"].update(status="pass", pass_seq=2)
        tasks["sg/y"].update(status="fail", retries=1, exhausted=True)
        status["rollback_pending"] = {"from": "sg/y", "to": "sg/x"}
        self.assertEqual(
            get_task.execute_rollback(work_dir, status, str(status_path), graph, tasks),
            0,
        )
        self.assertEqual(marker.read_text(), "child-baseline\n")

    def test_checkpoint_targets_ignore_non_rollback_nodes(self):
        nodes = [_node("a", on_exhaust="exit", rollback_to="ghost")]
        self.assertEqual(get_task.collect_checkpoint_targets(nodes, {}), set())

    def test_checkpoint_creation_is_idempotent(self):
        """Repeated task polls preserve the original rollback baseline."""
        with tempfile.TemporaryDirectory() as wd:
            root = Path(wd)
            workflow = root / ".workflow"
            workflow.mkdir()
            marker = root / "marker.txt"
            marker.write_text("baseline\n")
            status = {"seq": 4, "tasks": {"a": {"status": "pending", "retries": 0}}}
            status_path = workflow / "status.json"
            status_path.write_text(json.dumps(status))

            get_task.create_checkpoints(wd, status, str(status_path), ["a"], {"a"})
            marker.write_text("changed\n")
            get_task.create_checkpoints(wd, status, str(status_path), ["a"], {"a"})

            self.assertEqual(
                (workflow / "checkpoints" / "a" / "marker.txt").read_text(),
                "baseline\n",
            )
            self.assertEqual(status["tasks"]["a"]["checkpoint_seq"], 4)

    def test_get_task_creates_checkpoint_without_orchestrator(self):
        nodes = [
            _node("a"),
            _node("b", depends_on=["a"], on_exhaust="rollback", rollback_to="a"),
        ]
        wd, wf, wr = self._legacy_work_dir(
            nodes,
            {
                "a": {"status": "pending", "retries": 0},
                "b": {"status": "pending", "retries": 0},
            },
            seq=0,
        )
        marker = Path(wd) / "marker.txt"
        marker.write_text("original")
        first = self._poll_advice(wd)
        self.assertEqual(first[0]["task_id"], "a")
        checkpoint = wr / "checkpoints" / "a" / "marker.txt"
        self.assertEqual(checkpoint.read_text(), "original")
        self.assertEqual(read_status(wd)["tasks"]["a"]["checkpoint_seq"], 0)
        self.assertEqual(read_status(wd)["tasks"]["a"]["status"], "pending")
        marker.write_text("changed after polling")
        self.assertEqual(self._poll_advice(wd), first)
        self.assertEqual(checkpoint.read_text(), "original")
        self.assertFalse((wr / "checkpoints" / "b").exists())


class ResumeWorkflowGuardTest(unittest.TestCase):
    """resume 分支核对 status.json 的 workflow 与本次 --yaml，防止串工作流假成功。"""

    def setUp(self):
        self._work_dirs = []

    def tearDown(self):
        for d in self._work_dirs:
            shutil.rmtree(d, ignore_errors=True)

    def test_resume_same_yaml_ok(self):
        work_dir, wf = self._finished_work_dir(recorded="same")
        code, out = _run_orchestrator_dry(wf, work_dir)
        self.assertEqual(code, 0, out)

    def test_resume_different_yaml_fails(self):
        work_dir, wf = self._finished_work_dir(recorded="same")
        other = Path(work_dir) / "other.yaml"
        other.write_text(_workflow_yaml([_node("b")]))
        code, out = _run_orchestrator_dry(other, work_dir)
        self.assertEqual(code, 2, out)
        self.assertIn("另一个工作流", out)
        self.assertIn(str(wf), out)
        self.assertIn(str(other), out)
        # fail-fast：status.json 未被改动
        self.assertEqual(read_status(work_dir)["tasks"]["a"]["status"], "pass")

    def test_resume_missing_workflow_field_fails(self):
        work_dir, _ = self._finished_work_dir(recorded=None)
        code, out = _run_orchestrator_dry(Path(work_dir) / "workflow.yaml", work_dir)
        self.assertEqual(code, 2, out)
        self.assertIn("缺失 workflow 字段", out)

    def _finished_work_dir(self, recorded):
        """构造「已完成」work_dir：workflow.yaml + status.json（a 已 pass）。

        recorded="same" 时记录本目录的 workflow.yaml（正常 resume）；
        recorded=None 时省略 workflow 字段（旧版状态）。
        返回 (work_dir, wf)。
        """
        work_dir = tempfile.mkdtemp(prefix="wo-test-")
        self._work_dirs.append(work_dir)
        wf = Path(work_dir) / "workflow.yaml"
        wf.write_text(_workflow_yaml([_node("a")]))
        wr = Path(work_dir) / ".workflow"
        wr.mkdir()
        (wr / "user_prompt.md").write_text("test\n")
        status = {
            "work_dir": work_dir,
            "user_prompt": str(wr / "user_prompt.md"),
            "seq": 1,
            "rollbacks_used": 0,
            "tasks": {"a": {"status": "pass", "retries": 0}},
        }
        if recorded == "same":
            status["workflow"] = str(wf)
        elif recorded is not None:
            status["workflow"] = recorded
        (wr / "status.json").write_text(json.dumps(status))
        (wr / "dry_replies.json").write_text(json.dumps({}))
        return work_dir, wf


class BuildPromptTest(unittest.TestCase):
    """get_task.build_prompt 的白盒单测（纯函数；orchestrator 本体仍是黑盒）。"""

    NODE = {
        "id": "a",
        "title": "t",
        "goal": ["g"],
        "approach": ["ap"],
        "acceptance": ["ac"],
        "out_of_scope": ["o"],
    }

    def test_execute_prompt_includes_advice(self):
        with tempfile.TemporaryDirectory() as wd:
            advice = Path(wd) / "advice.md"
            advice.write_text("Investigate the original failure before retrying.")
            p = get_task.build_prompt(
                self.NODE,
                "execute",
                wd,
                "/up",
                get_task.PromptContext(advice=str(advice)),
            )
            self.assertIn("Rollback-Advice:", p)
            self.assertIn(advice.read_text(), p)

    def test_execute_prompt_includes_latest_verdict_failure_reason(self):
        with tempfile.TemporaryDirectory() as wd:
            verdict = Path(verdict_file_path(wd, "a"))
            verdict.parent.mkdir(parents=True)
            verdict.write_text(json.dumps({"verdict": "fail", "reason": "报告未生成"}))
            reason = get_task.read_verdict_failure_reason(wd, "a")
            p = get_task.build_prompt(
                self.NODE,
                "execute",
                wd,
                "/up",
                get_task.PromptContext(failure_reason=reason),
            )
            self.assertIn("Previous-Verification-Failure:", p)
            self.assertIn("报告未生成", p)

    def test_verify_prompt_omits_verdict_failure_reason(self):
        p = get_task.build_prompt(
            self.NODE,
            "verify",
            "/wd",
            "/up",
            get_task.PromptContext(failure_reason="报告未生成"),
        )
        self.assertNotIn("Previous-Verification-Failure", p)

    def test_missing_or_non_fail_verdict_has_no_failure_reason(self):
        with tempfile.TemporaryDirectory() as wd:
            self.assertIsNone(get_task.read_verdict_failure_reason(wd, "a"))
            verdict = Path(verdict_file_path(wd, "a"))
            verdict.parent.mkdir(parents=True)
            verdict.write_text(json.dumps({"verdict": "pass"}))
            self.assertIsNone(get_task.read_verdict_failure_reason(wd, "a"))
            verdict.write_text("not json")
            self.assertIsNone(get_task.read_verdict_failure_reason(wd, "a"))

    def test_verify_prompt_omits_advice(self):
        p = get_task.build_prompt(
            self.NODE,
            "verify",
            "/wd",
            "/up",
            get_task.PromptContext(advice="/wd/.workflow/advice/x.md"),
        )
        self.assertNotIn("Rollback-Advice", p)

    def test_prompt_without_advice_unchanged(self):
        p = get_task.build_prompt(self.NODE, "execute", "/wd", "/up")
        self.assertNotIn("Rollback-Advice", p)

    def test_execute_prompt_includes_system_prompt(self):
        p = get_task.build_prompt(
            self.NODE,
            "execute",
            "/wd",
            "/up",
            get_task.PromptContext(system_prompt="全局指令"),
        )
        self.assertIn("$SYSTEM_PROMPT=全局指令", p)
        self.assertIn("$WORK_DIR=/wd", p)

    def test_verify_prompt_includes_system_prompt(self):
        p = get_task.build_prompt(
            self.NODE,
            "verify",
            "/wd",
            "/up",
            get_task.PromptContext(system_prompt="全局指令"),
        )
        self.assertIn("$SYSTEM_PROMPT=全局指令", p)

    def test_verify_prompt_embeds_verdict_commands(self):
        p = get_task.build_prompt(self.NODE, "verify", "/wd", "/up")
        scripts = get_task.orch.SCRIPTS_DIR
        self.assertIn(
            'python3 "%s" --work-dir "/wd" --task-id "a"'
            % (scripts + "/verdict_pass.py"),
            p,
        )
        self.assertIn(
            'python3 "%s" --work-dir "/wd" --task-id "a"'
            ' --reason "<why acceptance fails>"' % (scripts + "/verdict_fail.py"),
            p,
        )
        self.assertIn("The verdict file is required; a text reply is not a verdict.", p)
        self.assertNotIn("After verifying, reply with only", p)

    def test_verify_prompt_uses_namespaced_task_id(self):
        p = get_task.build_prompt(
            self.NODE, "verify", "/wd", "/up", get_task.PromptContext(task_id="sub/a")
        )
        self.assertIn('--task-id "sub/a"', p)

    def test_execute_prompt_has_no_verdict_commands(self):
        p = get_task.build_prompt(self.NODE, "execute", "/wd", "/up")
        self.assertNotIn("verdict_", p)
        self.assertNotIn("reply with only", p)

    def test_prompt_without_system_prompt_unchanged(self):
        p = get_task.build_prompt(self.NODE, "execute", "/wd", "/up")
        self.assertNotIn("$SYSTEM_PROMPT=", p)
        self.assertTrue(p.startswith("$WORK_DIR=/wd"))


class ValidateSystemPromptTest(unittest.TestCase):
    """validate_workflow 白盒校验顶层可选键 system_prompt。"""

    BASE = {
        "workflow": "wf",
        "max_parallel": 1,
        "nodes": [
            {
                "id": "a",
                "task_type": "normal",
                "title": "t",
                "goal": ["g"],
                "approach": ["ap"],
                "acceptance": ["ac"],
                "out_of_scope": ["o"],
                "depends_on": [],
                "executor": "e",
                "verifier": "v",
                "max_retries": 0,
                "on_exhaust": "exit",
            }
        ],
    }

    def test_absent_ok(self):
        self.assertIsNone(get_task.validate_workflow(self.BASE))

    def test_non_empty_str_ok(self):
        self.assertIsNone(
            get_task.validate_workflow(dict(self.BASE, system_prompt="全局指令"))
        )

    def test_invalid_rejected(self):
        for bad in (123, ["x"], "", "   "):
            err = get_task.validate_workflow(dict(self.BASE, system_prompt=bad))
            self.assertIsNotNone(err, "system_prompt=%r 应校验失败" % (bad,))


class VerdictFileTest(unittest.TestCase):
    """verdict 裁决文件消费（黑盒 dry-run）。

    $VERDICT 令牌模拟 verifier 调脚本写裁决文件；编排器以裁决文件为权威，不使用文本兜底。
    """

    @staticmethod
    def _events(wd, name):
        return [e for e in read_log(wd) if e.get("event") == name]

    def test_verdict_file_pass_with_non_compliant_text(self):
        code, out, wd = self._run(
            nodes=[_node("t1")], dry_replies={"t1": ["executed", "$VERDICT:pass"]}
        )
        self.assertEqual(code, 0, out)
        self.assertEqual(read_status(wd)["tasks"]["t1"]["status"], "pass")
        verdicts = self._events(wd, "verdict")
        self.assertEqual(len(verdicts), 1)
        self.assertEqual(verdicts[0]["verdict"], "pass")
        self.assertFalse(self._events(wd, "reset"))  # 一次验证即过，无重验证
        self.assertTrue(Path(verdict_file_path(wd, "t1")).exists())  # 保留裁决文件

    def test_verdict_file_fail_with_reason(self):
        code, out, wd = self._run(
            nodes=[_node("t1")],  # max_retries=0 → fail 即耗尽 → on_exhaust=exit
            dry_replies={"t1": ["executed", "$VERDICT:fail:报告未生成"]},
        )
        self.assertEqual(code, 1, out)
        task = read_status(wd)["tasks"]["t1"]
        self.assertEqual(task["status"], "fail")
        self.assertTrue(task["exhausted"])
        verdicts = self._events(wd, "verdict")
        self.assertEqual(len(verdicts), 1)
        self.assertEqual(verdicts[0]["verdict"], "fail")
        self.assertEqual(verdicts[0]["reason"], "报告未生成")

    def test_missing_verdict_triggers_reverification(self):
        code, out, wd = self._run(
            nodes=[_node("t1")], dry_replies={"t1": ["executed", "通过"]}
        )
        # 缺失裁决 → 滞留 verifying → reset 自愈重验证（dry 默认写 pass 裁决）。
        self.assertEqual(code, 0, out)
        self.assertEqual(read_status(wd)["tasks"]["t1"]["status"], "pass")
        self.assertTrue(self._events(wd, "reset"))
        self.assertEqual(len(self._events(wd, "verdict")), 1)

    def test_stale_verdict_file_cleared_on_dispatch(self):
        code, out, wd = self._run(
            nodes=[_node("t1")],
            pre_files={
                os.path.relpath(
                    verdict_file_path("/", "t1"), "/"
                ): '{"verdict": "fail"}\n'
            },
        )
        # 陈旧裁决文件先归档；dry 默认生成新的 pass 裁决。
        self.assertEqual(code, 0, out)
        self.assertEqual(read_status(wd)["tasks"]["t1"]["status"], "pass")
        self.assertEqual(
            json.loads(Path(verdict_file_path(wd, "t1")).read_text())["verdict"], "pass"
        )
        history = Path(wd) / ".workflow" / "verdicts" / "history"
        archived = list(history.glob("t1.*.json"))
        self.assertEqual(len(archived), 1)
        self.assertRegex(
            archived[0].name, r"^t1\.20[0-9]{6}T[0-9]{6}\.[0-9]{6}Z\.json$"
        )
        self.assertEqual(len(self._events(wd, "verdict")), 1)

    def test_verdict_archive_failure_stops_dispatch(self):
        code, out, wd = self._run(
            nodes=[_node("t1")],
            pre_files={
                os.path.relpath(
                    verdict_file_path("/", "t1"), "/"
                ): '{"verdict": "fail"}\n',
                ".workflow/verdicts/history": "not a directory\n",
            },
        )
        self.assertEqual(code, 2, out)
        self.assertIn("裁决文件归档失败", out)
        self.assertEqual(read_status(wd)["tasks"]["t1"]["status"], "executed")

    def test_invalid_verdict_token_fails_fast(self):
        code, out, _ = self._run(
            nodes=[_node("t1")], dry_replies={"t1": ["executed", "$VERDICT:bogus"]}
        )
        # 非法 verdict 令牌属测试数据 bug，fail fast（与非法 $SLEEP 令牌同款语义）
        self.assertEqual(code, 2, out)
        self.assertIn("非法 verdict", out)

    def test_verdict_file_wins_over_contradictory_text(self):
        code, out, wd = self._run(
            nodes=[_node("t1")],
            dry_replies={"t1": ["executed", "$VERDICT:fail:报告缺失|pass"]},
        )
        # 文本谎称 pass，裁决文件为 fail：忽略文本，只消费裁决文件。
        self.assertEqual(code, 1, out)
        self.assertEqual(read_status(wd)["tasks"]["t1"]["status"], "fail")
        verdicts = self._events(wd, "verdict")
        self.assertEqual(len(verdicts), 1)
        self.assertEqual(verdicts[0]["verdict"], "fail")
        self.assertEqual(verdicts[0]["reason"], "报告缺失")
        self.assertNotIn("warning", verdicts[0])

    def _run(self, **kwargs):
        code, out, wd = run_orchestrator(**kwargs)
        self._work_dirs.append(wd)
        return code, out, wd

    def setUp(self):
        self._work_dirs = []

    def tearDown(self):
        for d in self._work_dirs:
            shutil.rmtree(d, ignore_errors=True)


class RunAgentEnvTest(unittest.TestCase):
    """run_agent 子进程环境的白盒单测：opencode/cannbot 按 PWD 环境变量
    （而非实际 cwd）解析项目目录，Popen(cwd=) 不回写继承的 PWD，
    因此 run_agent 必须显式把 PWD 置为 work_dir。"""

    def test_run_agent_exports_pwd_matching_work_dir(self):
        import orchestrator as orch  # 白盒：直接调 worker 线程体

        captured = {}

        class FakePopen:
            def __init__(self, cmd, cwd=None, env=None, stdout=None, stderr=None):
                captured["cmd"] = cmd
                captured["cwd"] = cwd
                captured["env"] = env
                self.stderr = io.BytesIO(b"")

            def __enter__(self):
                return self

            @staticmethod
            def __exit__(*args):
                return False

            @staticmethod
            def wait():
                return 0

        provider = types.SimpleNamespace(build_command=lambda agent, prompt: ["true"])
        entry = {"task_id": "t1", "_phase": "execute", "agent": "a", "prompt": "p"}
        with tempfile.TemporaryDirectory() as wd:
            with patch.object(orch.subprocess, "Popen", FakePopen):
                reply, crashed = orch.run_agent(entry, provider, wd, None)
            self.assertFalse(crashed)
            self.assertEqual(reply, "executed")
            self.assertEqual(captured["cwd"], wd)
            self.assertEqual(captured["env"]["PWD"], wd)


if __name__ == "__main__":
    unittest.main()
