-- Copyright (c) 2026 Huawei Technologies Co., Ltd.
-- This program is free software, you can redistribute it and/or modify it under the terms and conditions of
-- CANN Open Software License Agreement Version 2.0 (the "License").
-- Please refer to the License for details. You may not use this file except in compliance with the License.
-- THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
-- INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
-- See LICENSE in the root of the software repository for the full text of the License.

on run args
    set labels to {}
    repeat with i from 1 to (count args) by 2
        set end of labels to item i of args
    end repeat
    repeat
        activate
        set choice to button returned of (display dialog "点击“同意并安装”表示您同意用户协议，并已阅读隐私政策和开源软件声明。" with title "CANNBot开发工作台" buttons {"取消", "查看文件", "同意并安装"} default button "查看文件" cancel button "取消")
        if choice is "同意并安装" then return
        set selection to choose from list labels with title "协议与声明" with prompt "选择需要阅读的文件"
        if selection is not false then
            repeat with i from 1 to count labels
                if item i of labels is (item 1 of selection) then
                    set docPath to item (i * 2) of args
                    -- Quick Look returns to this dialog when its read-only preview closes.
                    do shell script "/usr/bin/qlmanage -p " & quoted form of docPath
                    exit repeat
                end if
            end repeat
        end if
    end repeat
end run
