#!/usr/bin/env python3
"""Automatic concurrency / core-limit sweep.

Flow:
  Phase 1 core tuning: search core limits (golden-section).
  Phase 2 concurrency tuning: fix the best core limit, enumerate --threads (default 1..8, skip failures).
  Phase 3 batch (optional): only when --batches is given.

Statistics policy (fixed):
  repeat=3 per config; each run uses CircleCount=5000/DebugFreq=1000 yielding 5 samples;
  per run, drop the first sample and the largest deviation, then average the rest;
  take the median of the 3 repeats. A run is valid only when test.sh returns 0 and the
  expected sample count is present; any invalid repeat invalidates the whole config.
  --tp99-limit with no feasible config clears the recommendation and exits non-zero.
  Multi-device --devices is executed sequentially (single-device is the recommended case).

Outputs:
  M<id>/sweep/logs/*.log
  M<id>/sweep/sweep_<ts>.csv
  M<id>/sweep/report_<ts>.md
"""

import argparse
import csv
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

AIC_OPS = {
    "MatMul", "MatMulV2", "BatchMatMul", "BatchMatMulV2", "Gemm",
    "Conv", "Conv2D", "Conv3D", "DepthwiseConv2D",
    "Conv2DBackpropInput", "Conv2DBackpropFilter",
}


# ============================================================
# onnx operator analysis
# ============================================================

def analyze_ops(model_id):
    from collections import Counter

    m = C.load_onnx(C.model_file(model_id))
    counter = Counter(n.op_type for n in m.graph.node)
    aic = sum(counter[o] for o in AIC_OPS)
    total = sum(counter.values())
    aiv = total - aic
    main = "AIV" if aiv >= aic else "AIC"
    return {"aic_ops": aic, "aiv_ops": aiv, "total": total, "main": main}


# ============================================================
# device occupancy check
# ============================================================

# 每 NPU 的 die 数（910B 单卡 2 die）；可用 SWEEP_DIES_PER_NPU 覆盖
DIES_PER_NPU = 2
# --skip-device-check 的运行时开关（由 main 设置）
SKIP_DEVICE_CHECK = False


def _row_ids(line):
    """从进程表数据行里取 (npu_id, chip_id)；不是数据行返回 None。

    兼容两种排布：
      `| 0 | 1 | 12345 | python | 1234 |`      （列间有竖线）
      `| 0       1        12345   python 1234 |`（整行一格，靠空格分列）
    """
    body = line.strip()
    if not body.startswith("|"):
        return None
    cells = [c.strip() for c in body.strip("|").split("|")]
    if len(cells) >= 2 and cells[0].isdigit() and cells[1].isdigit():
        return int(cells[0]), int(cells[1])
    if cells:
        parts = re.findall(r"\d+", cells[0])
        if len(parts) >= 2:
            return int(parts[0]), int(parts[1])
    parts = re.findall(r"\d+", body)
    if len(parts) >= 2:
        return int(parts[0]), int(parts[1])
    return None


def parse_process_table(text):
    """解析 `npu-smi info` 的进程表，返回 (占用集合, 是否找到表头, 数据行数, dies_per_npu)。

    仅解析表头（含 "Process id"/"进程"）之后的连续数据行，避免把版本头、
    温度表等无关行当占用。dies_per_npu 由观测到的最大 Chip 号 + 1 推断。
    """
    busy = set()
    chips = set()
    rows = 0
    header = False
    in_table = False
    for line in text.splitlines():
        if not in_table:
            if "Process id" in line or "进程" in line:
                in_table = True
                header = True
            continue
        ids = _row_ids(line)
        if ids:
            busy.add(ids)
            chips.add(ids[1])
            rows += 1
            continue
        if not line.strip() or set(line.strip()) <= set("+-="):
            continue
        in_table = False
    dies = (max(chips) + 1) if chips else None
    return busy, header, rows, dies


def device_occupied(device):
    """Check whether the target die is busy via the npu-smi process table.

    device 是全局 die 号（NPU0Chip0=0, NPU0Chip1=1, NPU1Chip0=2 …），
    映射为 (npu, chip) = divmod(device, dies_per_npu)。dies_per_npu 取值顺序：
    参数/`SWEEP_DIES_PER_NPU` -> 进程表观测值 -> 默认 2。

    查询失败、找不到进程表表头或解析不到数据行时按空闲处理并告警——
    误判 busy 会让 sweep 空等，比误判空闲更伤。可用 `--skip-device-check`
    或 `SWEEP_SKIP_DEVICE_CHECK=1` 强制跳过。
    """
    if SKIP_DEVICE_CHECK or os.environ.get("SWEEP_SKIP_DEVICE_CHECK") == "1":
        print(f"[sweep][WARN] device check skipped for {device}")
        return False
    try:
        proc = subprocess.run(["npu-smi", "info"], capture_output=True, text=True, timeout=30)
    except Exception as e:
        print(f"[sweep][WARN] npu-smi query failed ({e}); treat device {device} as free")
        return False
    if proc.returncode != 0:
        print(f"[sweep][WARN] npu-smi exit={proc.returncode}; treat device {device} as free")
        return False

    busy, header, rows, detected = parse_process_table(proc.stdout)
    if not header:
        print(f"[sweep][WARN] npu-smi 输出中未找到进程表表头；treat device {device} as free")
        return False
    if rows == 0:
        # 表头存在但没有数据行 = 当前无进程占用，属正常空闲，不告警
        return False

    env_dies = os.environ.get("SWEEP_DIES_PER_NPU")
    try:
        dies = int(env_dies) if env_dies else (detected or DIES_PER_NPU)
    except ValueError:
        dies = detected or DIES_PER_NPU
    if dies <= 0:
        dies = DIES_PER_NPU
    npu_id, chip_id = divmod(device, dies)
    return (npu_id, chip_id) in busy


def wait_device_free(device, timeout, poll):
    start = time.time()
    while device_occupied(device):
        if timeout <= 0 or time.time() - start > timeout:
            # 逐 config 反复等待只会把整轮拖成死等，直接终止并给出可操作提示
            raise SystemExit(
                "[sweep][ERROR] device %d 在 %ss 内未空闲，终止本轮 sweep。\n"
                "  确认卡确实空闲后用 --skip-device-check 跳过检查，或用 --device/--devices 换卡。"
                % (device, timeout))
        print(f"[sweep] device {device} busy, retry in {poll}s ...")
        time.sleep(poll)
    return True


# ============================================================
# single run and parsing
# ============================================================

def parse_log(path):
    text = Path(path).read_text(errors="ignore")
    avgs = [float(x) for x in re.findall(r"avg session run time=([\d.]+)ms", text)]
    tp99 = [float(x) for x in re.findall(r"TP99:([\d.]+)ms", text)]
    qps = [float(x) for x in re.findall(r"Qps=([\d.]+)", text)]
    return avgs, tp99, qps


def stable_avg(values):
    """Drop the first sample and the largest deviation, average the rest."""
    if not values:
        return None
    v = values[1:] if len(values) > 1 else values
    if len(v) >= 3:
        med = statistics.median(v)
        idx = max(range(len(v)), key=lambda i: abs(v[i] - med))
        v = [x for i, x in enumerate(v) if i != idx]
    return sum(v) / len(v)


def run_once(root, model_id, thread, core, device, circle, debug_freq,
             log_path, keep_cache, batch=None):
    env = os.environ.copy()
    env["MODEL_ID"] = model_id
    env["THREAD_NUM"] = str(thread)
    env["CORE_NUM"] = core
    env["START_DEVICE"] = str(device)
    env["CircleCount"] = str(circle)
    env["DebugFreq"] = str(debug_freq)
    env["PrintOutput"] = "False"
    env["KEEP_KERNEL_META"] = "True" if keep_cache else "False"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as f:
        cp = subprocess.run(["bash", str(root / "test.sh")], cwd=str(root), env=env,
                            stdout=f, stderr=subprocess.STDOUT, check=False)
    avgs, tp99, qps = parse_log(log_path)
    expected_n = max(1, (circle * thread) // debug_freq)
    status = "ok" if cp.returncode == 0 and len(avgs) >= expected_n else "failed"
    return {
        "avg": stable_avg(avgs),
        "tp99": stable_avg(tp99),
        "qps": stable_avg(qps),
        "n_avg": len(avgs),
        "rc": cp.returncode,
        "expected_n": expected_n,
        "status": status,
    }


def aggregate(reps, expected_repeat=None):
    if expected_repeat is not None and len(reps) != expected_repeat:
        return {"avg": None, "tp99": None, "qps": None, "status": "failed"}
    if not reps or any(r.get("status") != "ok" for r in reps):
        return {"avg": None, "tp99": None, "qps": None, "status": "failed"}
    got = [r for r in reps if r.get("avg") is not None]
    if not got:
        return {"avg": None, "tp99": None, "qps": None, "status": "failed"}
    return {
        "avg": statistics.median([r["avg"] for r in got]),
        "tp99": statistics.median([r["tp99"] for r in got if r["tp99"] is not None]) if any(r["tp99"] is not None for r in got) else None,
        "qps": statistics.median([r["qps"] for r in got if r["qps"] is not None]) if any(r["qps"] is not None for r in got) else None,
        "status": "ok",
    }


# ============================================================
# config evaluation
# ============================================================

class Sweep:
    def __init__(self, args):
        self.args = args
        self.root = C.demo_root()
        self.model_id = C.normalize_model_id(args.model_id)
        self.sweep_dir = C.model_dir(self.model_id) / "sweep"
        self.log_dir = self.sweep_dir / "logs"
        self.records = []          # aggregated record per config
        self.repeat_rows = []      # per-repeat details
        self.skipped = []
        self._cache = {}

    def _clear_cache(self):
        import shutil
        km = C.model_dir(self.model_id) / ".cache" / "run" / "kernel_meta"
        if km.exists():
            shutil.rmtree(km, ignore_errors=True)
        fr = km.parent / "fusion_result.json"
        if fr.exists():
            fr.unlink()

    def config_key(self, device, thread, core, batch):
        return (device, thread, core, batch)

    def evaluate(self, thread, core, device, batch=None, phase=""):
        key = self.config_key(device, thread, core, batch)
        if key in self._cache:
            return self._cache[key]
        tag = f"{phase}_t{thread}_c{core.replace('|','-')}_b{batch}_{device}"
        if not wait_device_free(device, self.args.wait_timeout, self.args.poll):
            self.skipped.append((tag, "device busy timeout"))
            rec = {"phase": phase, "thread": thread, "core": core, "batch": batch,
                   "device": device, "avg": None, "tp99": None, "qps": None, "status": "busy"}
            self._cache[key] = rec
            return rec
        # config changed -> clear compile cache; repeats of the same config reuse it
        self._clear_cache()
        reps = []
        for r in range(self.args.repeat):
            log = self.log_dir / f"{tag}_rep{r}.log"
            print(f"[sweep] run {tag} rep{r+1}/{self.args.repeat} ...")
            res = run_once(self.root, self.model_id, thread, core, device,
                           self.args.circle, self.args.debug_freq, log,
                           keep_cache=(r > 0), batch=batch)
            reps.append(res)
            self.repeat_rows.append({
                "phase": phase, "thread": thread, "core": core, "batch": batch,
                "device": device, "repeat": r,
                "avg_ms": res["avg"], "tp99_ms": res["tp99"], "qps": res["qps"],
                "n": res["n_avg"], "rc": res["rc"], "status": res["status"],
            })
        agg = aggregate(reps, expected_repeat=self.args.repeat)
        rec = {"phase": phase, "thread": thread, "core": core, "batch": batch,
               "device": device, **agg}
        self._cache[key] = rec
        self.records.append(rec)
        print(f"[sweep] {tag}: avg={agg['avg']} tp99={agg['tp99']} qps={agg['qps']} {agg['status']}")
        return rec

    # ---------------- Phase 1: core tuning ----------------
    def phase_cores(self, device):
        a = self.args
        aic_max, aiv_max = 24, 48
        aiv_lo, aic_lo = 6, 6
        analysis = analyze_ops(self.model_id)
        print(f"[sweep] onnx ops: AIC={analysis['aic_ops']} AIV={analysis['aiv_ops']} "
              f"main={analysis['main']}")
        budget = [a.core_budget]
        evaluated = []

        def evalfn(aic, aiv):
            if budget[0] <= 0:
                return None
            budget[0] -= 1
            r = self.evaluate(a.threads[0], f"{aic}|{aiv}", device, phase="core")
            if r and r.get("avg") is not None:
                evaluated.append({"aic": aic, "aiv": aiv, **r})
            return r

        # tune AIV (fixed AIC=aic_max) with golden-section
        lo, hi = aiv_lo, aiv_max
        while hi - lo > 2 and budget[0] > 0:
            m1 = int(lo + 0.382 * (hi - lo))
            m2 = int(lo + 0.618 * (hi - lo))
            r1 = evalfn(aic_max, m1)
            r2 = evalfn(aic_max, m2)
            if r1 is None or r2 is None:
                break
            if r1["avg"] is not None and (r2["avg"] is None or r1["avg"] < r2["avg"]):
                hi = m2
            else:
                lo = m1
        for aiv in range(max(aiv_lo, lo), min(aiv_max, hi) + 1):
            evalfn(aic_max, aiv)

        if not evaluated:
            raise SystemExit("[sweep][ERROR] no valid core configuration; aborting")
        best = min(evaluated, key=lambda r: r["avg"])

        # fine-tune AIC (fixed best AIV)
        best_aic = best["aic"]
        for aic in range(aic_lo, aic_max + 1, 2):
            if budget[0] <= 0:
                break
            r = evalfn(aic, best["aiv"])
            if r and r["avg"] is not None and (best["avg"] is None or r["avg"] < best["avg"]):
                best = {"aic": aic, "aiv": best["aiv"], **r}
                best_aic = aic
        print(f"[sweep] core tuning result: {best_aic}|{best['aiv']} avg={best['avg']}")
        return f"{best_aic}|{best['aiv']}"

    # ---------------- Phase 2: concurrency tuning ----------------
    def phase_threads(self, device, core):
        best = None
        for t in self.args.threads:
            r = self.evaluate(t, core, device, phase="thread")
            if r["status"] != "ok":
                self.skipped.append((f"thread={t}", r["status"]))
                continue
            if best is None or (r["qps"] or 0) > (best["qps"] or 0):
                best = r
        return best

    # ---------------- Phase 3: batch (optional) ----------------
    def phase_batch(self, device, core, thread, batches):
        sc_path = C.config_dir(self.model_id) / "shape_config.json"
        io_path = C.config_dir(self.model_id) / "io_config.json"
        bl_path = C.input_data_dir(self.model_id) / "batch_list.json"
        snapshot = {p: p.read_bytes() for p in (sc_path, io_path, bl_path) if p.exists()}
        sc = C.read_json(sc_path)
        try:
            for b in batches:
                sc["batch_size"] = b
                C.write_json(sc_path, sc)
                cp = subprocess.run(
                    [sys.executable, str(Path(__file__).parent / "prepare_input.py"),
                     self.model_id], check=False)
                if cp.returncode != 0:
                    raise SystemExit(
                        f"[sweep][ERROR] prepare_input.py failed for batch={b}")
                self.evaluate(thread, core, device, batch=b, phase="batch")
        finally:
            for p, data in snapshot.items():
                p.write_bytes(data)

    # ---------------- report ----------------
    def write_csv(self, ts):
        path = self.sweep_dir / f"sweep_{ts}.csv"
        self.sweep_dir.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["kind", "phase", "thread", "core", "batch", "device", "repeat",
                        "avg_ms", "tp99_ms", "qps", "n", "status"])
            for r in self.repeat_rows:
                w.writerow(["repeat", r["phase"], r["thread"], r["core"], r["batch"],
                            r["device"], r["repeat"], r["avg_ms"], r["tp99_ms"],
                            r["qps"], r["n"], r["status"]])
            for r in self.records:
                w.writerow(["agg", r["phase"], r["thread"], r["core"], r["batch"],
                            r["device"], "", r["avg"], r["tp99"], r["qps"], "", r["status"]])
        return path

    def write_md(self, ts, best):
        path = self.sweep_dir / f"report_{ts}.md"
        if best is None:
            best_line = "- best: none (no configuration satisfied the constraints)"
        else:
            best_line = (f"- best: QPS={best.get('qps')} avg={best.get('avg')}ms "
                         f"tp99={best.get('tp99')}ms core={best.get('core')} "
                         f"thread={best.get('thread')}")
        lines = [
            f"# Sweep report M{self.model_id} ({ts})",
            "",
            f"- repeat={self.args.repeat} circle={self.args.circle} debug_freq={self.args.debug_freq}",
            f"- device(s)={self.args.devices or self.args.device}",
            best_line,
            "",
            "## aggregated config results",
            "",
            "| phase | thread | core | batch | avg(ms) | tp99(ms) | qps | status |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for r in self.records:
            lines.append(f"| {r['phase']} | {r['thread']} | {r['core']} | {r['batch']} | "
                         f"{r['avg']} | {r['tp99']} | {r['qps']} | {r['status']} |")
        if self.skipped:
            lines += ["", "## skipped/failed", ""]
            for tag, why in self.skipped:
                lines.append(f"- {tag}: {why}")
        Path(path).write_text("\n".join(lines) + "\n")
        return path


def main():
    ap = argparse.ArgumentParser(description="Automatic concurrency / core-limit sweep")
    ap.add_argument("model_id")
    ap.add_argument("--threads", default="1,2,3,4,5,6,7,8")
    ap.add_argument("--device", type=int, default=0, help="single device")
    ap.add_argument("--devices", default=None,
                    help="devices to scan sequentially, e.g. 8,9,10 (single device recommended)")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--circle", type=int, default=5000)
    ap.add_argument("--debug-freq", type=int, default=1000)
    ap.add_argument("--core-budget", type=int, default=24)
    ap.add_argument("--batches", default=None, help="comma-separated batch list (optional)")
    ap.add_argument("--tp99-limit", type=float, default=None)
    ap.add_argument("--wait-timeout", type=int, default=600)
    ap.add_argument("--poll", type=int, default=30)
    ap.add_argument("--phase", default="all", choices=["all", "cores", "threads", "batch"])
    ap.add_argument("--quick", action="store_true", help="quick smoke: repeat=1 circle=300 debug=100")
    ap.add_argument("--skip-device-check", action="store_true",
                    help="skip the npu-smi busy check (use when device_occupied misjudges)")
    args = ap.parse_args()

    global SKIP_DEVICE_CHECK
    SKIP_DEVICE_CHECK = bool(args.skip_device_check)

    if args.quick:
        args.repeat, args.circle, args.debug_freq = 1, 300, 100

    args.threads = [int(x) for x in args.threads.split(",") if x.strip()]
    batches = [int(x) for x in args.batches.split(",")] if args.batches else []
    devices = [int(x) for x in args.devices.split(",")] if args.devices else [args.device]

    if args.repeat < 1 or args.circle < 1 or args.debug_freq < 1:
        raise SystemExit("[sweep][ERROR] repeat/circle/debug-freq must be >= 1")
    if not args.threads or any(t < 1 for t in args.threads):
        raise SystemExit("[sweep][ERROR] --threads must contain positive integers")

    if len(devices) > 1:
        print(f"[sweep][WARN] multi-device is sequential (single-device recommended): {devices}")

    s = Sweep(args)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    cores = {}
    for dev in devices:
        if args.phase in ("all", "cores"):
            cores[dev] = s.phase_cores(dev)
        else:
            cores[dev] = None

    if args.phase in ("all", "threads", "batch"):
        def worker(dev):
            core = cores.get(dev) or f"24|48"
            best = s.phase_threads(dev, core) if args.phase in ("all", "threads") else None
            if args.phase in ("all", "batch") and batches:
                t = best["thread"] if best else 1
                s.phase_batch(dev, core, t, batches)
            if args.phase == "batch":
                batch_recs = [r for r in s.records
                              if r.get("phase") == "batch" and r.get("device") == dev
                              and r.get("status") == "ok"]
                best = max(batch_recs, key=lambda r: r["qps"] or 0) if batch_recs else None
            return best

        bests = [worker(dev) for dev in devices]
        valid = [b for b in bests if b]
        if not valid:
            print("[sweep][ERROR] all devices failed, no usable result")
            sys.exit(1)
        best = max(valid, key=lambda r: r["qps"] or 0)
    else:
        # cores-only phase: evaluate the best core per device with default concurrency
        best = None
        for dev in devices:
            r = s._cache.get((dev, args.threads[0], cores[dev], None))
            if r and (best is None or (r["qps"] or 0) > (best["qps"] or 0)):
                best = r
        if best is None:
            raise SystemExit("[sweep][ERROR] no valid core configuration; aborting")

    # apply tp99 limit
    tp99_failed = False
    if args.tp99_limit is not None:
        ok = [r for r in s.records
              if r.get("status") == "ok" and r.get("avg") is not None
              and (r.get("tp99") or 1e9) <= args.tp99_limit]
        if ok:
            best = max(ok, key=lambda r: r["qps"] or 0)
        else:
            print(f"[sweep][ERROR] no config satisfies tp99<={args.tp99_limit}")
            best = None
            tp99_failed = True

    csv_path = s.write_csv(ts)
    md_path = s.write_md(ts, best)
    print(f"[sweep] CSV: {csv_path}")
    print(f"[sweep] report: {md_path}")
    if tp99_failed:
        sys.exit(2)
    if best is None:
        print("[sweep][ERROR] no usable best configuration")
        sys.exit(1)
    print(f"[sweep] best: thread={best.get('thread')} core={best.get('core')} "
          f"qps={best.get('qps')} avg={best.get('avg')} tp99={best.get('tp99')}")


if __name__ == "__main__":
    main()