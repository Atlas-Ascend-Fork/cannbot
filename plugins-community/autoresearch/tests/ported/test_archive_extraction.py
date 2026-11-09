# Copyright 2026 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Archive validation must finish before either extraction branch writes."""

import io
import tarfile

import pytest
from op_autoresearch.core.worker.local_worker import (
    PackageExtractError,
    _extract_archive,
)


@pytest.fixture(params=["modern", "legacy"])
def extraction_mode(request, monkeypatch):
    if request.param == "modern" and not hasattr(tarfile, "data_filter"):
        pytest.skip("This Python does not provide tarfile.data_filter")
    if request.param == "legacy":
        if hasattr(tarfile, "fully_trusted_filter"):
            monkeypatch.setattr(
                tarfile.TarFile,
                "extraction_filter",
                staticmethod(tarfile.fully_trusted_filter),
            )
        monkeypatch.delattr(tarfile, "data_filter", raising=False)
    return request.param


def _write_archive(path, members):
    with tarfile.open(path, "w") as archive:
        for member, content in members:
            if member.isfile():
                member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            else:
                archive.addfile(member)


def _unsafe_member(kind, extract_dir):
    names = {
        "traversal": "../escaped.py",
        "absolute_outside": str(extract_dir.parent / "escaped.py"),
        "absolute_inside": str(extract_dir / "absolute.py"),
    }
    member = tarfile.TarInfo(names.get(kind, "unsafe"))
    member.type = {
        "symlink": tarfile.SYMTYPE,
        "hardlink": tarfile.LNKTYPE,
        "character_device": tarfile.CHRTYPE,
        "block_device": tarfile.BLKTYPE,
        "fifo": tarfile.FIFOTYPE,
    }.get(kind, tarfile.REGTYPE)
    member.linkname = "../escaped.py"
    return member


@pytest.mark.parametrize(
    "kind",
    [
        "traversal",
        "absolute_outside",
        "absolute_inside",
        "symlink",
        "hardlink",
        "character_device",
        "block_device",
        "fifo",
    ],
)
def test_rejects_unsafe_archive_before_writing(kind, extraction_mode, tmp_path):
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    archive_path = tmp_path / "package.tar"
    _write_archive(
        archive_path,
        [
            (tarfile.TarInfo("safe.py"), b"safe\n"),
            (_unsafe_member(kind, extract_dir), b"unsafe\n"),
        ],
    )

    with pytest.raises(PackageExtractError, match="Unsafe archive member rejected"):
        _extract_archive(str(archive_path), str(extract_dir))

    assert list(extract_dir.iterdir()) == []
    assert not (tmp_path / "escaped.py").exists()


def test_extracts_valid_archive(extraction_mode, tmp_path):
    archive_path = tmp_path / "package.tar"
    extract_dir = tmp_path / "extract"
    directory = tarfile.TarInfo("project")
    directory.type = tarfile.DIRTYPE
    directory.mode = 0o755
    _write_archive(
        archive_path,
        [(directory, b""), (tarfile.TarInfo("project/kernel.py"), b"pass\n")],
    )
    _extract_archive(str(archive_path), str(extract_dir))

    assert (extract_dir / "project" / "kernel.py").read_bytes() == b"pass\n"
