# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Private acquisition and raw-evidence adapter; loaded by report_contract."""

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import shutil
import subprocess

from npu_compute_report import (
    load_summary,
    positive,
    receipt,
    select_summary,
    timing,
)

PROTOCOL = {
    "profiler": "npu-compute",
    "sections": ["PipeUtilization"],
    "cache_control": "all",
    "metric": "Task Duration(us)",
    "statistic": "task_log_replay_median",
}


def require(value, message):
    if not value:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def run(command, cwd, log):
    with log.open("w") as stream:
        return subprocess.run(
            command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT
        ).returncode


def check_receipt(item):
    actual = receipt(item["path"])
    require(
        all(item[k] == actual[k] for k in ("path", "sha256")),
        "report dependency changed",
    )
    return actual


def published(log, label):
    values = re.findall(
        r"^npu-compute:\s*" + label + r"=\s*(.+?)\s*$", log, re.MULTILINE
    )
    require(
        len(values) == 1 and Path(values[0]).is_absolute(),
        f"expected one absolute {label} publication",
    )
    return Path(values[0]).resolve()


def validate_measurement(plan):
    require(
        plan.get("protocol") == PROTOCOL,
        "independent report protocol differs from registration",
    )
    require(
        Path(plan["tool"]["path"]).name == "npu-compute",
        "frozen npu-compute executable required",
    )
    for identity in plan["identities"].values():
        require(
            isinstance(identity.get("kernel_name"), str)
            and identity["kernel_name"]
            and type(identity.get("block_dim")) is int
            and identity["block_dim"] > 0,
            "exact reported Op Name and block dimension required",
        )


def validate_failure(attempt, log):
    require(
        not attempt.get("archive") and not re.search(r"npu-compute:\s*report=", log),
        "published report cannot be discarded as a failed attempt",
    )
    export = attempt["command"][attempt["command"].index("--export") + 1]
    require(
        not Path(export).exists(),
        "existing archive requires parsing/review, not recollection",
    )


def validate_publication(attempt, archive, summary, log, import_log, plan=None):
    values = re.findall(r"^npu-compute:\s*report=\s*(.+?)\s*$", log, re.MULTILINE)
    require(values == [str(archive)], "capture did not publish exactly this archive")
    require(
        str(archive) == attempt["command"][attempt["command"].index("--export") + 1],
        "archive differs from actual export argv",
    )
    imported = re.findall(
        r"^npu-compute:\s*unpacked=\s*(.+?)\s*$", import_log, re.MULTILINE
    )
    require(
        attempt.get("import_returncode") == 0
        and len(imported) == 1
        and Path(imported[0]).is_absolute()
        and summary.is_relative_to(Path(imported[0])),
        "summary not bound to successful import",
    )


def tool_skill(context=None):
    if context is not None:
        data = (
            json.loads(Path(context).read_text())
            if isinstance(context, (str, Path))
            else context
        )
        path = Path(data["tool_skill"]).resolve()
        require(
            (path / "SKILL.md").is_file(), "backend skill missing from report context"
        )
        return path
    candidates = [
        Path.cwd() / ".agents/skills/tool-npu-compute",
        Path.home() / ".agents/skills/tool-npu-compute",
        Path.home() / ".codex/skills/tool-npu-compute",
    ]
    candidates += [
        parent / "vendor/cannbot-skills/tools/tool-npu-compute"
        for parent in Path(__file__).resolve().parents
    ]
    for path in candidates:
        if (path / "SKILL.md").is_file():
            return path.resolve()
    raise ValueError(
        "tool-npu-compute skill unavailable; provide its location in report context"
    )


def prepare(context=None, *, executable=None):
    executable = executable if executable is not None else shutil.which("npu-compute")
    require(executable, "npu-compute is unavailable in the selected environment")
    skill = tool_skill(context)
    # Read-only capability discovery occurs only when this report entry is used.
    commands = []
    for option in ("--help", "--list-sections"):
        result = subprocess.run(
            [executable, option], capture_output=True, text=True, timeout=30
        )
        require(result.returncode == 0, f"npu-compute {option} failed: {result.stderr}")
        commands.append(result.stdout + result.stderr)
    require(
        "PipeUtilization" in commands[1] and "--cache-control" in commands[0],
        "required timing capability is unavailable",
    )
    return {
        "tool": receipt(executable),
        "protocol": dict(PROTOCOL),
        "report_context": {"tool_skill": str(skill)},
    }


def validate_screening(report):
    require(report.get("provider") == "npu-compute", "unexpected report provider")
    dependencies = [report["summary"], *[i["result"] for i in report["inspections"]]]
    for item in dependencies:
        check_receipt(item)
    raw = load_summary(report["summary"]["path"])[-1]
    duration = timing(raw)
    require(
        raw == report["op_info"]
        and {k: v for k, v in duration.items() if k != "use"}
        == {k: v for k, v in report["timing"].items() if k != "use"}
        and duration["rated_frequency_valid"]
        and positive(duration["duration_us"]),
        "screening timing/frequency differs from original summary",
    )
    return {
        "duration_us": duration["duration_us"],
        "frequency_mhz": duration["rated_frequency_mhz"],
        "dependencies": dependencies,
        "comparison_key": dict(PROTOCOL),
    }


def raw_sample(path, identity, plan):
    info = load_summary(path)[-1]
    require(
        info.get("Op Name") == identity["kernel_name"]
        and info.get("Block Dim") == identity["block_dim"],
        "raw target identity mismatch",
    )
    duration = info.get("Task Duration(us)")
    require(positive(duration), "raw Task Duration must be finite and positive")
    require(info.get("Device Id") == plan["logical_device"], "logical device mismatch")
    current, rated = info.get("Current Freq"), info.get("Rated Freq")
    frequency = plan.get("frequency_policy", "rated")
    require(frequency in ("rated", "record_only"), "unknown frequency policy")
    if frequency == "rated":
        require(
            positive(current)
            and positive(rated)
            and current == rated == plan["rated_frequency_mhz"],
            "frequency missing or different from frozen rated frequency",
        )
    pid = info.get("Pid")
    require(type(pid) is int and pid > 0, "raw process identity required")
    return duration, pid


def check_command(command, identity, plan=None):
    require(
        isinstance(command, list)
        and all(isinstance(x, str) for x in command)
        and command
        and Path(command[0]).name == "npu-compute"
        and "--" in command,
        "actual npu-compute argv with explicit program separator required",
    )
    divider = command.index("--")
    require(
        command[divider + 1 :] == identity["runner"],
        "runner argv changed after registration",
    )
    options = command[1:divider]
    require(len(options) % 2 == 0, "tool options must have explicit values")
    pairs = list(zip(options[::2], options[1::2]))
    require(
        len(pairs) == 3
        and dict(pairs).get("--section") == "PipeUtilization"
        and dict(pairs).get("--cache-control") == "all"
        and "--export" in dict(pairs),
        "actual sampling/cache protocol mismatch",
    )


def collect_attempt(plan, identity, slot, attempt_dir, context=None):
    archive = attempt_dir / "capture.npu-rep"
    command = [
        plan["tool"]["path"],
        "--section",
        "PipeUtilization",
        "--cache-control",
        "all",
        "--export",
        str(archive),
        "--",
        *identity["runner"],
    ]
    print(now(), "starting", slot, flush=True)
    started = now()
    log_path = attempt_dir / "run.log"
    code = run(command, identity["cwd"], log_path)
    attempt = {
        "schema_version": 1,
        **slot,
        "protocol": plan["protocol"],
        "physical_device": plan["physical_device"],
        "logical_device": plan["logical_device"],
        "environment": plan["environment"],
        "command": command,
        "returncode": code,
        "started_at": started,
        "ended_at": now(),
        "status": "needs_review",
        "run_log": receipt(log_path),
    }
    try:
        log = log_path.read_text(errors="replace")
        # An outer zero exit code cannot turn a missing report into success.
        if code or not re.search(r"^npu-compute:\s*report=", log, re.MULTILINE):
            if not archive.exists() and not re.search(r"npu-compute:\s*report=", log):
                attempt["status"] = "failed"
            raise ValueError("capture did not publish a successful report")
        require(
            published(log, "report") == archive and archive.is_file(),
            "archive publication mismatch",
        )
        attempt["archive"] = receipt(archive)
        import_attempt(plan, identity, attempt, attempt_dir)
        attempt["status"] = "valid"
    except (OSError, ValueError, KeyError) as error:
        attempt["error"] = str(error)
    attempt["ended_at"] = now()
    return attempt


def import_attempt(plan, identity, attempt, directory):
    unpack = directory / "unpacked"
    unpack.mkdir()
    import_log = directory / "import.log"
    command = [
        plan["tool"]["path"],
        "--import",
        attempt["archive"]["path"],
        "--export",
        str(unpack),
    ]
    code = run(command, identity["cwd"], import_log)
    attempt.update(
        import_command=command, import_returncode=code, import_log=receipt(import_log)
    )
    require(code == 0, "import failed; reparse this archive without recollection")
    root = published(import_log.read_text(errors="replace"), "unpacked")
    summary, _ = select_summary(root, identity["kernel_name"])
    attempt["summary"] = receipt(summary)
    validate_publication(
        attempt,
        Path(attempt["archive"]["path"]),
        summary,
        Path(attempt["run_log"]["path"]).read_text(errors="replace"),
        import_log.read_text(errors="replace"),
    )
    raw_sample(summary, identity, plan)


def recover_attempt(plan, identity, attempt, directory):
    """Recover timing from the retained archive; directory holds new import evidence."""
    attempt = dict(attempt)
    try:
        check_command(attempt["command"], identity)
        require(attempt["returncode"] == 0, "capture exited unsuccessfully")
        log = Path(check_receipt(attempt["run_log"])["path"]).read_text(
            errors="replace"
        )
        archive = published(log, "report")
        require(
            str(archive)
            == attempt["command"][attempt["command"].index("--export") + 1],
            "archive publication mismatch",
        )
        if attempt.get("archive"):
            require(
                check_receipt(attempt["archive"])["path"] == str(archive),
                "archive changed",
            )
        else:
            attempt["archive"] = receipt(archive)
        if attempt.get("summary"):
            summary = Path(check_receipt(attempt["summary"])["path"])
            import_log = Path(check_receipt(attempt["import_log"])["path"]).read_text(
                errors="replace"
            )
            validate_publication(attempt, archive, summary, log, import_log)
            raw_sample(summary, identity, plan)
        else:
            import_attempt(plan, identity, attempt, directory)
        attempt["status"] = "valid"
        attempt.pop("error", None)
    except (OSError, ValueError, KeyError) as error:
        attempt["error"] = str(error)
    return attempt
