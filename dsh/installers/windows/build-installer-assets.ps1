# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.

param([string]$Source, [string]$Destination)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$logo = [Drawing.Image]::FromFile($Source)
try {
    foreach ($layout in @(@('header.bmp', 150, 57, 42), @('sidebar.bmp', 164, 314, 98))) {
        $canvas = New-Object Drawing.Bitmap($layout[1], $layout[2])
        $graphics = [Drawing.Graphics]::FromImage($canvas)
        try {
            $graphics.Clear([Drawing.Color]::White)
            $graphics.InterpolationMode = [Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $size = [int]$layout[3]
            $x = [int](($canvas.Width - $size) / 2)
            $y = if ($layout[0] -eq 'header.bmp') { [int](($canvas.Height - $size) / 2) } else { 76 }
            $graphics.DrawImage($logo, $x, $y, $size, $size)
            $canvas.Save((Join-Path $Destination $layout[0]), [Drawing.Imaging.ImageFormat]::Bmp)
        } finally { $graphics.Dispose(); $canvas.Dispose() }
    }
} finally { $logo.Dispose() }
