# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software; you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

"""Concurrent startup regression test for the orchestrator work-directory lock."""

from concurrent.futures import ThreadPoolExecutor
import tempfile
import threading
import unittest
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import orchestrator


class OrchestratorLockTest(unittest.TestCase):
    def test_concurrent_start_has_only_one_lock_owner(self):
        with tempfile.TemporaryDirectory(prefix="wo-lock-") as work_dir:
            barrier = threading.Barrier(2)
            original_flock = orchestrator.fcntl.flock

            def synchronized_flock(fd, operation):
                barrier.wait(timeout=5)
                return original_flock(fd, operation)

            with patch.object(orchestrator.fcntl, "flock", synchronized_flock):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    locks = list(pool.map(lambda _: orchestrator.acquire_lock(work_dir), range(2)))

            self.assertEqual(sum(lock is not None for lock in locks), 1)
            owner = next(lock for lock in locks if lock is not None)
            owner.close()
            self.assertTrue(Path(work_dir, ".workflow", "orchestrator.lock").exists())
            second_owner = orchestrator.acquire_lock(work_dir)
            self.assertIsNotNone(second_owner)
            second_owner.close()


if __name__ == "__main__":
    unittest.main()
