#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""Build flash_attention_gen AscendC kernel."""

import os
import shutil
import subprocess
from pathlib import Path

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext

KERNEL_DIR = Path(__file__).resolve().parent


class PrebuiltBuildExt(build_ext):
    def build_extension(self, ext):
        source = KERNEL_DIR / "build" / self.get_ext_filename(ext.name)
        if not source.is_file():
            self.build_kernel()
        target = Path(self.get_ext_fullpath(ext.name))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    def build_kernel(self):
        cmake = shutil.which("cmake")
        if cmake is None:
            raise FileNotFoundError("CMake is required to build the AscendC kernel")
        executable = str(Path(cmake).resolve())
        configure = [
            executable,
            "-S",
            str(KERNEL_DIR),
            "-B",
            str(KERNEL_DIR / "build"),
            f"-DASCEND_CANN_PACKAGE_PATH={os.environ['ASCEND_HOME_PATH']}",
            f"-DTL_ROOT={os.environ['TL_ROOT']}",
            f"-DNPU_ARCH={os.environ.get('NPU_ARCH', 'dav-2201')}",
            "-DCMAKE_BUILD_TYPE=Release",
        ]
        subprocess.run(configure, check=True, shell=False)
        subprocess.run(
            [
                executable,
                "--build",
                str(KERNEL_DIR / "build"),
                "--parallel",
                os.environ.get("BUILD_JOBS", "4"),
            ],
            check=True,
            shell=False,
        )


setup(
    name="flash_attention_gen",
    version="0.1.0",
    description="Flash Attention AscendC kernel",
    ext_modules=[Extension("flash_attention_gen_ext", sources=[])],
    cmdclass={"build_ext": PrebuiltBuildExt},
    license="CANN-2.0",
    python_requires=">=3.8",
)
