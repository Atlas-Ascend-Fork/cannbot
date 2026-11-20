# book-950 — installation calibration record

本文件记录 `verified` 条目所依赖的安装环境取值，每个值都给出重新求得它的命令。
换一套环境复核这些条目时，按同样的命令重新取值，不要直接沿用下表的数字。

Installation provenance for the 950 verification environment: each value paired with the command
that re-derives it. Values below were derived on the bound installation, not pasted from documentation. Entries record board identity, conditions, readouts and the commands that re-derive them.

## Bound installation (2026-08-24)

| value | derived | re-derive command |
|---|---|---|
| host arch | x86_64 | `uname -m` |
| board | Ascend950PR, single card | `npu-smi info` |
| AI Core count | 28 | `npu-smi info -t common -i 0 \| grep 'Aicore Count'` |
| rated / observed idle AIC freq | 1650 MHz rated, **100 MHz at deep idle** (DVFS floor; a 16.5× confound if unwarmed) | `npu-smi info -t common -i 0 \| grep -i freq` |
| HBM | 131072 MB | `npu-smi info` (HBM-Usage column denominator) |
| toolkit pin | CANN **9.1.0**, package timestamp `20260730_231653901`, at `/workspace/Ascend/cann-9.1.0` | `cat /workspace/Ascend/cann-9.1.0/compiler/version.info` |
| second toolkit PRESENT, NOT BOUND | CANN 9.0.0-beta.2 (timestamp `20260328_213255003`) at `/home/developer/Ascend/` — never mixed into a run without an explicit per-run pin note | `cat /home/developer/Ascend/cann-9.0.0-beta.2/compiler/version.info` |
| driver / npu-smi | 25.7.rc1 / 25.7.rc1 | `cat /usr/local/Ascend/driver/version.info` |
| compiler | `bisheng` (and `ccec`) at `/workspace/Ascend/cann-9.1.0/bin/` | `which bisheng ccec` |
| arch token that WORKS | `-xasc --npu-arch=dav-3510` (bisheng ASC mode) | calibration build below |
| arch token, split behaviour (measured 2026-08-24) | `--cce-aicore-lang --cce-aicore-arch=dav-3510` ⇒ `bisheng: error: Unsupported CCE architecture: dav-3510`. Upstream's exact VF-preflight line `--cce-aicore-arch=dav-3510 --cce-aicore-only -c` ACCEPTS the arch token (compilation proceeds into headers) but the CLASSIC `kernel_operator.h` tree then fails on this pin at `kernel_log.h:287` ("decomposition declaration template not supported"), with and without `-std=c++17`. Scope: upstream aims that line at VF/regbase-style sources, which were not compiled here — this row does not establish their preflight broken, only that the classic-API path is closed under `--cce-aicore-only` on this pin | run both lines, read the errors |
| link libs | `-lascendcl -lruntime` from `/workspace/Ascend/cann-9.1.0/lib64` | `ls .../lib64/libascendcl.so .../lib64/libruntime.so` |

**Standing occupancy fact**: the card carries resident processes from other work (observed: two
`python` processes holding ~9 GB HBM at NPU-Util 0%). Correctness runs may proceed; TIMED runs
must record the full `npu-smi info` table pre/post and treat a busy co-tenant as voiding.

## Verified single-file build line (calibration, 2026-08-24)

```
$TK/bin/bisheng -xasc --npu-arch=dav-3510 -O2 -std=c++17 \
  -I$TK/include -I$TK/compiler/tikcpp/tikcfw{,/interface,/impl} \
  -I$TK/asc{,/include,/include/adv_api,/include/basic_api,/include/c_api,/include/utils} \
  -I$TK/asc/impl{,/adv_api,/basic_api,/c_api,/utils} \
  -L$TK/lib64 -lascendcl -lruntime  -o <bin> <single-source.cpp>
# TK=/workspace/Ascend/cann-9.1.0 ; kernel+host in ONE translation unit, <<<>>> launch.
# The CLASSIC AscendC API (TPipe/TQue/DataCopy/Adds from kernel_operator.h) compiles and runs
# on Ascend950PR under -xasc — measured here, not assumed.
```

## Instrument calibration record (RULES.md Art. 5 / plan step 1)

2026-08-24, Ascend950PR, NPU-Util 0% before and after:
- known-answer kernel `y = x + 1.0f` over 256 floats (TPipe/TQue, GM→UB→Adds→GM, 1 core):
  checker **CHECK PASS (256 elements)**, exit 0.
- poisoned variant (same source, `-DPOISON` ⇒ `y = x + 2.0f`), SAME checker:
  **CHECK FAIL (256 wrong of 256)**, exit 1.
- Aicore curFreq 100 MHz before AND after (untimed correctness run; timed runs must warm to
  plateau — from a 100 MHz floor the unwarmed error is up to 16.5× — and record pre/post,
  drift voids the run).

The instrument bleeds when poisoned. Build line, device selection, launch, synchronize,
readback, and checker plumbing are all proven on this installation.

## Direct-launch VF / UB facts on this installation (measured 2026-08-25, 950PR)

| fact | measured | where it is used |
|---|---|---|
| UB inside a `__simt_vf__` on direct launch needs the launch attribute | no attr → 507035 at the first UB access; `aclrtLaunchKernelAttr{ACL_RT_LAUNCH_KERNEL_ATTR_DYN_UBUF_SIZE, .value.dynUBufSize=N}` via `aclrtGetFuncBySymbol` + `aclrtLaunchKernelWithHostArgs` grants it; 4 KB → still 507035 (the value is consumed) | 950:0483 §4, 950:0314 §4.6, 950:0489 §4 (SIMT form) |
| grant ceiling | 221184 B = 216 KB accepted; 221216 and above refused at *submission*, rc 107000 (not the 507035 runtime abort) | 950:0238 (Arm A / grant) |
| `GetRuntimeUBSize()` | plain vector kernel: 253952 regardless of grant; VF-bearing kernel: exactly the grant (0, 4096, 65536, …, 221184) | 950:0238 |
| UB access bound in the VF regime | largest granted InitBuffer whose tail is touched: 229376 (= grant 221184 + 8192); 229408 refused 507035. Plain regime: 262144 / 262176 (950:0209 reproduced). Difference 32768 | 950:0238 Arm B |
| what the 507035 refusal keys on | the *accessed* address, not the allocation total: an extra 16 KB buffer allocated after the probed one and never touched moves no bound | 950:0238 fixture design |
| host-args ABI | 7 args (3 pointers + 4 × uint32) as a packed 40-B struct match the `<<<>>>` stub | all direct-launch probes |
| **scalar GM stores vs MTE3/VF GM stores on one 64-B line** | writes from the kernel body's scalar path and from `DataCopy`/VF to the SAME 64-byte GM line clobber each other (markers lost in 0/2 … 5/6 launches); on separate lines 8/8 and 100 % of probes. **Rule: scalar echo words never share a 64-B line with vector-written results** | every probe in harvest/RUNS_20260824.md from ub238c on |
| regbase `__VEC_SCOPE__` outer loop with trip count 1 | stores after the loop hold the registers' initial constants (both fp16 and fp32); trip count ≥ 2 correct — observed, not explained; keep timed loops ≥ 256 | 950:0489 §4 |
| `GetWarpSize()` | 32 (device echo; `GetThreadNum()` 512 under `LAUNCH_BOUND(512)`) | SIMT probes |
| VF / vector-scope loop induction variable | must be `uint16_t` (hard compiler error otherwise) | all regbase/VF sources |
