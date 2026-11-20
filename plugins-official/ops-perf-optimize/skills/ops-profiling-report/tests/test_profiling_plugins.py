# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Plugin selection and consolidation never need inactive tool instructions."""

import errno
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from types import SimpleNamespace

import pytest

import profile_report
import report_contract
from report_common import check_receipt, receipt, write_report_files


def configure_guided_tools(tmp_path, monkeypatch):
    entries = {}
    for name in ("first", "second"):
        guide = tmp_path / (name + ".md")
        guide.write_text("private guidance should only be read by the Agent")
        entries[name] = {"id": name, "guide": str(guide)}
    monkeypatch.setattr(report_contract, "_TOOLS", entries)
    monkeypatch.setattr(report_contract, "_BACKENDS", {})


def test_one_or_multiple_guided_tools_need_no_measurement_adapter(
    tmp_path, monkeypatch
):
    configure_guided_tools(tmp_path, monkeypatch)
    original = Path.read_text

    def read(path, *args, **kwargs):
        assert path.suffix != ".md", "preparation must not load unused instruction text"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    one = report_contract.prepare({"tools": ["first"]})
    assert one["provider"] == "first" and one["execution_mode"] == "skill"
    several = report_contract.prepare({"tools": ["first", "second"]})
    assert [b["provider"] for b in several["bindings"]] == ["first", "second"]


def test_default_registry_has_only_active_children(monkeypatch):
    assert set(report_contract._TOOLS) == {"msopprof", "msprof"}
    assert set(report_contract._BACKENDS) == {"msopprof", "msprof"}
    monkeypatch.setattr("shutil.which", lambda name: pytest.fail("inactive providers must not probe tools"))
    with pytest.raises(ValueError, match="inactive"):
        report_contract.backend({"provider": "npu-compute"})


def test_mother_keeps_distinct_protocols_and_carries_optimization_analysis(
    tmp_path, monkeypatch
):
    configure_guided_tools(tmp_path, monkeypatch)
    monkeypatch.setitem(report_contract._BACKENDS, "second", "external")
    monkeypatch.setitem(report_contract._MODULES, "external", SimpleNamespace(validate_report=lambda report: None))
    raw = tmp_path / "raw.csv"
    raw.write_text("fixture")
    reports = []
    for index, name in enumerate(("first", "second")):
        path = tmp_path / (name + ".json")
        path.write_text(
            json.dumps(
                {
                    "provider": name,
                    "case_id": "case",
                    "status": "diagnostic_valid",
                    "collection_root": {"device": str(raw.parent)} if index == 0 else str(tmp_path),
                    "identity": {"input": "same"},
                    "protocol": {"boundary": "kernel" if index == 0 else "application"},
                    "measurements": [
                        {
                            "kernel": "A",
                            "device": 0,
                            "duration_us": 10 + index,
                            "evidence": receipt(raw),
                            "line": 1,
                        }
                    ],
                    "evidence": [receipt(raw)],
                }
            )
        )
        reports.append(path)
    analysis = {
        "findings": ["两套计时边界不同，分别展示"],
        "recommendations": [
            {
                "change": "检查数据搬运是否可重叠",
                "basis": "需补充流水证据",
                "verify": "保持输入与缓存口径复测",
            }
        ],
    }
    result = profile_report.consolidate(reports, tmp_path, analysis)
    assert [child["validation"] for child in result["children"]] == ["receipts_only", "raw_verified"]
    assert len(result["measurements"]) == 2 and "total_us" not in result
    assert result["recommendations"] == analysis["recommendations"]
    assert (
        result["measurements"][0]["protocol"] != result["measurements"][1]["protocol"]
    )
    raw.write_text("tampered")
    with pytest.raises(ValueError, match="changed"):
        profile_report.consolidate(reports, tmp_path / "bad")


@pytest.mark.parametrize("filename", ["profile-report.json", "性能分析报告.md"])
def test_existing_report_file_preserves_directory(tmp_path, filename):
    existing = tmp_path / filename
    existing.write_text("previous report")
    os.utime(tmp_path, (1600000000, 1600000000))
    before = tmp_path.stat().st_mtime_ns
    with pytest.raises(FileExistsError) as error:
        write_report_files(tmp_path, {}, ["new report"])
    assert Path(error.value.filename) == existing
    assert existing.read_text() == "previous report"
    assert list(tmp_path.iterdir()) == [existing]
    assert tmp_path.stat().st_mtime_ns == before


def test_consolidation_hashes_the_bytes_it_parses(tmp_path, monkeypatch):
    configure_guided_tools(tmp_path, monkeypatch)
    source, replacement = tmp_path / "child.json", tmp_path / "replacement"
    for path, duration in ((source, 1), (replacement, 2)):
        path.write_text(json.dumps({"provider": "first", "status": "valid",
                                    "measurements": [{"duration_us": duration}]}))
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    original_open = Path.open

    @contextmanager
    def replace_after_close(path, *args, **kwargs):
        with original_open(path, *args, **kwargs) as stream:
            yield stream
        if path == source and replacement.exists():
            replacement.replace(path)

    monkeypatch.setattr(Path, "open", replace_after_close)
    result = profile_report.consolidate([source], tmp_path / "combined")
    assert not replacement.exists()
    assert result["children"][0]["report"] == {"path": str(source), "sha256": before}
    assert result["measurements"][0]["duration_us"] == 1


@pytest.mark.skipif(not hasattr(signal, "SIGXFSZ"), reason="requires POSIX file size limits")
def test_killed_report_writer_never_publishes_truncated_data(tmp_path):
    program = """
import resource, signal, sys
from pathlib import Path
from report_common import write_report_files
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_FSIZE, (4096, 4096))
signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
write_report_files(Path(sys.argv[1]), {"payload": "x" * 65536}, ["complete Markdown"])
"""
    process = subprocess.run([sys.executable, "-B", "-c", program, str(tmp_path)],
                             cwd=Path(profile_report.__file__).parent)
    assert process.returncode == -signal.SIGXFSZ
    assert not (tmp_path / "profile-report.json").exists()
    assert not (tmp_path / "性能分析报告.md").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX filesystem encoding")
def test_json_receipt_round_trips_filename_across_locales(tmp_path):
    source = tmp_path / "子报告.json"
    source.write_text('{"note": "原件"}', encoding="utf-8")
    program = """
import json, sys
from report_common import check_receipt, read_json_with_receipt
data, item = read_json_with_receipt(sys.argv[1])
check_receipt(item)
check_receipt(json.loads(sys.argv[2]))
print(json.dumps([data, item]))
"""
    result = subprocess.check_output([sys.executable, "-B", "-c", program, str(source),
                                      json.dumps(receipt(source))], cwd=Path(profile_report.__file__).parent,
                                     env={**os.environ, "LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"})
    data, item = json.loads(result)
    assert data == {"note": "原件"}
    assert check_receipt(item) == receipt(source)


@pytest.mark.skipif(sys.platform not in ("linux", "darwin"), reason="POSIX exclusive publish paths")
@pytest.mark.parametrize("allow_links", [True, False])
def test_concurrent_replacement_is_preserved(tmp_path, monkeypatch, allow_links):
    link = os.link
    markdown = tmp_path / "性能分析报告.md"

    def competing_writer(source, target):
        if target.name == "profile-report.json":
            assert markdown.read_text() == "ours\n"
            replacement = tmp_path / "replacement"
            replacement.write_text("other writer")
            replacement.replace(markdown)
            target.write_text("other JSON")
        if not allow_links:
            raise OSError(errno.EOPNOTSUPP, "hard links unavailable")
        link(source, target)

    monkeypatch.setattr(os, "link", competing_writer)
    with pytest.raises(FileExistsError):
        write_report_files(tmp_path, {}, ["ours"])
    assert markdown.read_text() == "other writer"
    assert (tmp_path / "profile-report.json").read_text() == "other JSON"


def test_receipt_uses_canonical_file_with_or_without_procfs(tmp_path, monkeypatch):
    target = tmp_path / "raw.csv"
    target.write_bytes(b"raw")
    link = tmp_path / "alias"
    link.symlink_to(target)
    expected = receipt(target)
    assert receipt(link) == expected and expected["path"] == str(target)
    readlink = os.readlink

    def without_procfs(path, *args, **kwargs):
        if str(path).startswith("/proc/self/fd/"):
            raise FileNotFoundError(path)
        return readlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "readlink", without_procfs)
    assert receipt(link) == expected
