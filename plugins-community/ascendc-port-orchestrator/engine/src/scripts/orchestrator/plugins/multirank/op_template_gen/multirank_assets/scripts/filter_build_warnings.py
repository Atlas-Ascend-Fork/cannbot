#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Filter and deduplicate compiler warnings via a path whitelist.

Piped between the compiler and stdout during AscendC op builds
(``multirank_build.run_filtered`` → ``cmake --build ... | python3
filter_build_warnings.py -``). A warning passes through iff its file path
falls under one of the keep roots; everything else (CANN headers, libc,
third-party such as catlass, autogen) is filtered. Errors always pass
through and are never deduplicated; the exit code is the upstream compile
exit code — filtering never masks a build failure.

Keep roots come from ``--keep PATH`` (repeatable) or, if none given,
default to this process's cwd. Under the standard build entry
(``cd prj-<op>/ && python3 run.py build``) the filter subprocess inherits
``prj-<op>`` as its cwd, so the project source dir is kept by default with
no explicit argument.
"""

import argparse
import logging
import os
import re
import sys

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def _real(path):
    """Normalize a path for prefix matching: expand $VARS, collapse symlinks
    via realpath, then normpath. Applied to BOTH keep roots and warning file
    paths so the two sides stay comparable."""
    return os.path.normpath(os.path.realpath(os.path.expandvars(path)))


def _under(path, root):
    """True iff ``path`` is ``root`` itself or a descendant. The ``+ os.sep``
    guard prevents /a/op from matching /a/op_kernel."""
    p, r = _real(path), _real(root)
    return p == r or p.startswith(r + os.sep)


def _resolve_keep(cli_keep):
    """Return the list of keep roots. Explicit ``--keep`` paths win; if none
    given, fall back to the process cwd (the standard build entry keeps cwd
    at ``prj-<op>``). Always returns at least one root."""
    if cli_keep:
        return [_real(p) for p in cli_keep]
    return [_real(os.getcwd())]


# Parser states for the line-block state machine.
IDLE = "idle"
WARNING = "warning"
ERROR = "error"

_WARNING_RE = re.compile(r"^(.+?):(\d+):(\d+)?\s*warning:\s*(.+)$")
_ERROR_RE = re.compile(r"^(.+?):(\d+):(\d+)?\s*error:\s*(.+)$")
_NOTE_RE = re.compile(r"^(.+?):(\d+):(\d+)?\s*note:\s*(.+)$")

# Leading context lines that appear BEFORE a warning/error header.
_LEADING_CONTEXT_RE = re.compile(
    r"^(?:In file included from |\s+from |"
    r".+?:\s*In\s+(?:function|lambda))"
)


class _WarningBlockFilter:
    """The warning/error block state machine (one pass over the lines).

    A warning block prints iff its file is under one of the keep roots;
    error blocks always print; warnings are deduplicated by
    (file, line, message). Ordinary build output and leading-context lines
    pass through unchanged.
    """

    def __init__(self, keep_roots):
        self.keep_roots = keep_roots
        self.seen_warnings: set = set()
        self.state = IDLE
        self.pending_lines: list[str] = []
        self.block_lines: list[str] = []
        self.warning_key = None
        self.header_just_seen = False

    @staticmethod
    def is_block_continuation(line, after_header):
        """True if the line continues the current warning/error block."""
        if not line or line[0] in " \t":
            return True
        if after_header:
            return True
        if line.lstrip().startswith("^"):
            return True
        return False

    def feed(self, line):
        w_match = _WARNING_RE.match(line)
        e_match = _ERROR_RE.match(line)
        n_match = _NOTE_RE.match(line)
        if w_match or e_match:
            self._handle_header(w_match, e_match, line)
        elif n_match:
            self._handle_note(line)
        elif _LEADING_CONTEXT_RE.match(line):
            self._handle_leading_context(line)
        else:
            self._handle_other(line)

    def flush_pending(self):
        for line in self.pending_lines:
            log.info(line)
        self.pending_lines.clear()

    def flush_block(self):
        if self.state == WARNING and self.warning_key is not None:
            if self.warning_key not in self.seen_warnings:
                self.seen_warnings.add(self.warning_key)
                if any(_under(self.warning_key[0], r) for r in self.keep_roots):
                    log.info("\n".join(self.block_lines))
        elif self.state == ERROR:
            log.info("\n".join(self.block_lines))
        self.block_lines.clear()
        self.warning_key = None
        self.state = IDLE

    def _handle_header(self, w_match, e_match, line):
        self.flush_block()
        if w_match:
            self.state = WARNING
            self.warning_key = (w_match.group(1), w_match.group(2), w_match.group(4))
            self.block_lines = self.pending_lines + [line]
            self.pending_lines = []
        else:
            self.state = ERROR
            self.block_lines = self.pending_lines + [line]
            self.pending_lines = []
        self.header_just_seen = True

    def _handle_note(self, line):
        # Note line continues the current block or is treated as text.
        if self.state in (WARNING, ERROR):
            self.block_lines.append(line)
            self.header_just_seen = True
        else:
            self.flush_pending()
            log.info(line)
            self.header_just_seen = False

    def _handle_leading_context(self, line):
        if self.state in (WARNING, ERROR):
            self.flush_block()
        self.pending_lines.append(line)
        self.header_just_seen = False

    def _handle_other(self, line):
        if self.is_block_continuation(line, self.header_just_seen):
            if self.state in (WARNING, ERROR):
                self.block_lines.append(line)
            else:
                # Standalone continuation line without an active block:
                # treat as ordinary text.
                self.flush_pending()
                log.info(line)
            self.header_just_seen = False
        else:
            # Ordinary text: end any active block first.
            if self.state in (WARNING, ERROR):
                self.flush_block()
            self.flush_pending()
            log.info(line)
            self.header_just_seen = False


def _run_filter(file_obj, keep_roots):
    """Run the warning block state machine on ``file_obj``."""
    machine = _WarningBlockFilter(keep_roots)
    try:
        for raw_line in file_obj:
            machine.feed(raw_line.rstrip("\n"))
        machine.flush_pending()
        machine.flush_block()
    finally:
        if file_obj is not sys.stdin:
            file_obj.close()


def main():
    ap = argparse.ArgumentParser(
        description="Filter/dedup compiler warnings via a path whitelist. "
        "A warning passes through iff its file is under a keep "
        "root (--keep PATH, repeatable); without --keep the "
        "process cwd is used. Errors always pass through."
    )
    ap.add_argument(
        "--keep",
        action="append",
        metavar="PATH",
        default=None,
        help="Project source root to KEEP (repeatable). When "
        "given, only warnings whose file is under a keep "
        "root are shown; otherwise the cwd is used.",
    )
    ap.add_argument(
        "input", nargs="?", default="-", help="input file ('-' or omitted = stdin)"
    )
    args = ap.parse_args()

    keep_roots = _resolve_keep(args.keep)
    if args.input == "-":
        _run_filter(sys.stdin, keep_roots)
    else:
        with open(args.input, "r") as file_obj:
            _run_filter(file_obj, keep_roots)


if __name__ == "__main__":
    main()
