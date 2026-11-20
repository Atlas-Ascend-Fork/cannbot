# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Network msprof fixture paths and synthetic executable."""
from pathlib import Path
from device_fixture import FAKE_TARGET

FIXTURE = Path(__file__).resolve().parent / "fixtures"
NAMES = ["aclnnAdd_AddAiCore_Add", "aclnnMul_MulAiCore_Mul", "aclnnExp_ExpAiCore_Exp"]


def fake_tool(root):
    path = root / "msprof"
    path.write_text('''#!/usr/bin/env python3
import csv, json, os, sys
from pathlib import Path
if '--help' in sys.argv:
 print('--output --task-time --ai-core --ascendcl --sys-lp --l2'); sys.exit(0)
root=Path(next(x.split('=',1)[1] for x in sys.argv if x.startswith('--output=')))
FAKE_TARGET_PLACEHOLDER
profile=root/'PROF_fixture'
(profile/'host').mkdir(parents=True)
(profile/f'device_{physical}').mkdir()
(profile/'mindstudio_profiler_output').mkdir()
(profile/'host/info.json').write_text(json.dumps({'pid':str(os.getpid())}))
with Path(FIXTURE_PATH).open() as f:
 reader=csv.DictReader(f); fields=reader.fieldnames; rows=list(reader)
if sys.argv[-1]=='candidate': rows=rows[:1]
else:
 last=dict(rows[0]); last['Task ID']='9'; last['Task Start Time(us)']='1794904812641613.636'; rows.append(last)
for row in rows: row['Device_id']=str(physical)
with (profile/'mindstudio_profiler_output/op_summary.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fields);w.writeheader();w.writerows(rows)
'''.replace('FAKE_TARGET_PLACEHOLDER', FAKE_TARGET).replace('FIXTURE_PATH', repr(str(FIXTURE / 'op_summary.csv'))))
    path.chmod(0o755)
    return path
