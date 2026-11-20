# book-910 — installation calibration record

Installation provenance for the 910 verification environment: each value paired with the command
that re-derives it. Values below were derived on the bound installation, not pasted from documentation. Entries record board identity, conditions, readouts and the commands that re-derive them.

## Bound installation (2026-08-24)

| value | derived | re-derive command |
|---|---|---|
| host arch | aarch64 | `uname -m` |
| board | 910B2 (8 dies on the host; each job sees its allocation via `ASCEND_RT_VISIBLE_DEVICES`) | `npu-smi info` |
| AI Core count | 24 per die | `npu-smi info -t common -i <die> \| grep 'Aicore Count'` |
| rated / observed idle AIC freq | 1800 MHz rated, 800 MHz at idle (DVFS floor) | `npu-smi info -t common -i <die> \| grep -i freq` |
| HBM per die | 65536 MB | `npu-smi info` (HBM-Usage column denominator) |
| toolkit pin | CANN **9.1.0**, package timestamp `20260730_231653901` | `cat /usr/local/Ascend/cann-9.1.0/compiler/version.info` |
| driver / npu-smi | 25.5.1 / 25.5.1 | `cat /usr/local/Ascend/driver/version.info` |
| compiler | `bisheng` (and `ccec`) at `/usr/local/Ascend/cann-9.1.0/bin/` | `which bisheng ccec` |
| arch tokens | SOC map ships `"dav-2201" "2201" "Ascend910B1"`; kernel arch flags `--cce-aicore-arch=dav-c220-vec` (AIV) and `--cce-aicore-arch=dav-c220-cube` (AIC) | `grep -rh "dav-c220\|Ascend910B" /usr/local/Ascend/ascend-toolkit/latest/compiler/tikcpp/ascendc_kernel_cmake/ \| sort -u` |
| link libs | `-lascendcl -lruntime` from `/usr/local/Ascend/ascend-toolkit/latest/lib64` | `ls .../lib64/libascendcl.so .../lib64/libruntime.so` |

**NOTE on the pin**: the parent 910 lineage was measured against CANN 9.0.0-beta.2; THIS book's
verification lane is CANN 9.1.0 (that is what the bound machine carries). Every entry promoted
here says 9.1.0 in its INDEX; a claim that needs the older toolkit stays unverified and says so.

## Verified single-file build line (calibration, 2026-08-24)

```
bisheng --cce-aicore-lang --cce-aicore-arch=dav-c220-vec -O2 -std=c++17 \
  -I$TK/include -I$TK/aarch64-linux/include \
  -I$TK/compiler/tikcpp/tikcfw{,/interface,/impl} -I$TK/aarch64-linux/tikcpp/tikcfw{,/interface,/impl} \
  -I$TK/asc{,/include,/include/adv_api,/include/basic_api,/include/c_api,/include/utils} \
  -I$TK/asc/impl{,/adv_api,/basic_api,/c_api,/utils} \
  (same asc set under $TK/aarch64-linux/) \
  -L$TK/lib64 -L$TK/aarch64-linux/lib64 -lascendcl -lruntime  -o <bin> <single-source.cpp>
# TK=/usr/local/Ascend/ascend-toolkit/latest ; kernel+host in ONE translation unit, <<<>>> launch
```

## Instrument calibration record (RULES.md Art. 5 / plan step 1)

2026-08-24, die 0 (bus 0000:C1:00.0), AICore 0% on all 8 dies before and after:
- known-answer kernel `y = x + 1.0f` over 256 floats (TPipe/TQue, GM→UB→Adds→GM, 1 AIV core):
  checker **CHECK PASS (256 elements)**, exit 0.
- poisoned variant (same source, `-DPOISON` ⇒ `y = x + 2.0f`), SAME checker:
  **CHECK FAIL (256 wrong of 256)**, exit 1.
- Aicore curFreq 800 MHz before AND after (untimed correctness run; timed runs must warm to
  plateau and record pre/post, drift voids the run).

The instrument bleeds when poisoned. Build line, device selection, launch, synchronize,
readback, and checker plumbing are all proven on this installation.
