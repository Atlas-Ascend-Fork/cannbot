#!/usr/bin/env python3
"""Accuracy verification: compare inference outputs with golden/CPU onnxruntime reference.

Usage:
  python3 tools/verify.py <model_id> [--run] [--golden-source auto|user|ort]
                                    [--rtol R] [--atol A] [--ref-dir DIR] [--gate FILE]

Flow:
  1. Resolve golden from exactly two sources: manual (--golden-source user, --ref-dir) or
     framework-generated (--golden-source ort, model .cache/golden_ort); auto prefers manual.
     Manual mode never generates; ort mode never writes the manual reference directory.
  2. Resolve tested outputs from the framework: M<id>/output/output_<i>.bin plus output/.complete.
     --run-id rejects stale runs; --run cleans outputs, re-runs inference, and fails on non-zero RC.
  3. Compare per output: int/bool exact; float requires finite actual output and uses allclose
     (default rtol=atol=1e-3). Per-output thresholds come from the accuracy gate file
     (default M<id>/config/precision_gate.json, override with --gate); CLI --rtol/--atol only
     act as the fallback when the gate file or the output entry is absent.
  4. Write M<id>/output/verify_report.json (summary) and M<id>/output/verify_table.log
     (error bins + top 30 by abs/rel error); exit 0 on all PASS else 1.
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
import common as C  # noqa: E402


def _sorted_by_index(paths):
    def idx(p):
        try:
            return int(p.stem.split("_")[1])
        except (IndexError, ValueError):
            return -1

    return sorted(paths, key=idx)


def _user_files(ref_dir):
    if not ref_dir.exists():
        return None, None
    npy = _sorted_by_index(list(ref_dir.glob("output_*.npy")))
    bins = _sorted_by_index(list(ref_dir.glob("output_*.bin")))
    return npy, bins


def _generate_ort_golden(model_id):
    """Generate framework golden into a cache dir; never write the user reference dir."""
    import gen_golden

    gen_dir = C.model_dir(model_id) / ".cache" / "golden_ort"
    gen_dir.mkdir(parents=True, exist_ok=True)
    for p in list(gen_dir.glob("output_*.npy")) + list(gen_dir.glob("output_*.bin")):
        p.unlink()
    try:
        gen_golden.generate(model_id, gen_dir)
    except SystemExit as e:
        raise SystemExit(
            f"[ERROR] framework golden generation failed: {e}\n"
            f"        provide reference/output_<i>.npy|.bin and use --golden-source user."
        )
    npy, _ = _user_files(gen_dir)
    if not npy:
        raise SystemExit(f"[ERROR] output_*.npy still not found after generation: {gen_dir}")
    return "ort_npy", npy, gen_dir


def resolve_golden(model_id, ref_dir, source):
    user_dir = Path(ref_dir) if ref_dir else C.model_dir(model_id) / "reference"
    npy, bins = _user_files(user_dir)

    if source == "user":
        if npy:
            return "user_npy", npy, user_dir
        if bins:
            return "user_bin", bins, user_dir
        raise SystemExit(
            f"[ERROR] user golden not found ({user_dir}/output_<i>.npy|.bin); "
            f"cannot verify. Use --golden-source ort to generate framework golden."
        )

    if source == "ort":
        return _generate_ort_golden(model_id)

    # auto: prefer user golden, otherwise generate framework golden
    if npy:
        return "user_npy", npy, user_dir
    if bins:
        return "user_bin", bins, user_dir
    return _generate_ort_golden(model_id)


def load_expected(path, io_out, fallback_shape):
    if path.suffix == ".npy":
        arr = np.load(path)
    else:
        shape = io_out.get("shape", [])
        if shape is None or any(int(d) == -1 for d in shape):
            shape = fallback_shape
        arr = C.bytes_to_array(path.read_bytes(), io_out["dtype"], shape)
    if io_out["dtype"] in ("float16", "bfloat16"):
        # npy may be raw bf16/f16; normalize to float for comparison
        return C.normalize_for_compare(arr, io_out["dtype"])
    return arr


def load_actual_shapes(model_id):
    """Read actual output shapes dumped by the C++ runtime -> {index: [dims]}.

    io_config output shapes may contain -1 for dynamic dims; the runtime writes the real
    shapes to output/output_shapes.json, which is authoritative for interpreting output_i.bin.
    """
    p = C.output_dir(model_id) / "output_shapes.json"
    if not p.exists():
        return {}
    try:
        data = C.read_json(p)
    except Exception as e:  # noqa: BLE001
        print(f"[verify][WARN] failed to read {p}: {e}")
        return {}
    shapes = {}
    for item in data.get("outputs", []):
        idx = item.get("index")
        shape = item.get("shape")
        if idx is not None and shape is not None:
            shapes[int(idx)] = [int(d) for d in shape]
    return shapes


def load_precision_gate(model_id, explicit):
    """读取逐输出精度门禁（可选）。

    默认路径 M<id>/config/precision_gate.json；文件不存在且未显式指定时返回 (None, None)。
    结构：
      {
        "default": {"rtol": 1e-3, "atol": 1e-3},
        "outputs": {"<output name>": {"rtol": 1e-3, "atol": 0.5, "note": "用户确认的依据"}}
      }
    """
    path = Path(explicit) if explicit else (C.config_dir(model_id) / "precision_gate.json")
    if not path.exists():
        if explicit:
            raise SystemExit(f"[ERROR] precision gate not found: {path}")
        return None, None
    data = C.read_json(path)
    if not isinstance(data, dict):
        raise SystemExit(f"[ERROR] precision gate must be a JSON object: {path}")
    outputs = data.get("outputs") or {}
    if not isinstance(outputs, dict):
        raise SystemExit(f"[ERROR] precision gate 'outputs' must be an object: {path}")
    for name, entry in outputs.items():
        if not isinstance(entry, dict):
            raise SystemExit(f"[ERROR] precision gate entry for '{name}' must be an object: {path}")
    return path, data


def gate_threshold(gate, name, rtol, atol):
    """按输出名解析阈值：outputs[name] > default > CLI 回退值。"""
    if not gate:
        return rtol, atol
    entry = (gate.get("outputs") or {}).get(name) or {}
    default = gate.get("default") or {}
    r = entry.get("rtol", default.get("rtol", rtol))
    a = entry.get("atol", default.get("atol", atol))
    try:
        return float(r), float(a)
    except (TypeError, ValueError):
        raise SystemExit(f"[ERROR] precision gate threshold for '{name}' is not numeric: rtol={r!r} atol={a!r}")


def compare_one(expected, actual, dtype, rtol, atol):
    res = {"pass": False, "mismatch": None, "max_abs": None, "max_rel_eff": None,
           "expected_shape": list(np.shape(expected)), "actual_shape": list(np.shape(actual))}
    if list(np.shape(expected)) != list(np.shape(actual)):
        return res
    if dtype in ("int32", "int64", "bool"):
        mism = int(np.count_nonzero(expected != actual))
        res["mismatch"] = mism
        res["pass"] = (mism == 0)
        return res
    # float
    e = expected.astype(np.float64)
    a = actual.astype(np.float64)
    if e.size == 0:
        res["pass"] = True
        return res
    if not bool(np.all(np.isfinite(a))):
        res["non_finite_actual"] = int(np.count_nonzero(~np.isfinite(a)))
        return res
    if not bool(np.all(np.isfinite(e))):
        res["non_finite_expected"] = int(np.count_nonzero(~np.isfinite(e)))
        return res
    abs_err, rel_err = _err_arrays(expected, actual)
    res["max_abs"] = float(np.max(abs_err))
    # Keep consistent with the TOP table: max_rel ignores abs_err <= 1e-6
    eff = abs_err > 1e-6
    res["max_rel_eff"] = float(np.max(rel_err[eff])) if bool(np.any(eff)) else None
    res["pass"] = bool(np.allclose(e, a, rtol=rtol, atol=atol))
    return res


BIN_LABELS = [
    ("abs_err > 1e0", 1.0, None),
    ("1e0 >= abs_err > 1e-1", 1e-1, 1.0),
    ("1e-1 >= abs_err > 1e-3", 1e-3, 1e-1),
    ("1e-3 >= abs_err > 1e-6", 1e-6, 1e-3),
    ("1e-6 >= abs_err", None, 1e-6),
]


def _err_arrays(expected, actual):
    """Return (abs_err, rel_err) as 1D float64 arrays.

    Relative error is abs_err/|expected|; when expected==0: 0 if no error, else 100% (ratio 1.0).
    """
    e = expected.astype(np.float64)
    a = actual.astype(np.float64)
    abs_err = np.abs(e - a)
    with np.errstate(divide="ignore", invalid="ignore"):
        rel_err = abs_err / np.abs(e)
    rel_err = np.where(np.abs(e) == 0, np.where(abs_err == 0, 0.0, 1.0), rel_err)
    return abs_err, rel_err


def _bin_counts(abs_err):
    flat = abs_err.ravel()
    finite = flat[np.isfinite(flat)]
    total = int(finite.size)
    counts = []
    for label, lo, hi in BIN_LABELS:
        if lo is None:
            c = int(np.count_nonzero(finite <= hi))
        elif hi is None:
            c = int(np.count_nonzero(finite > lo))
        else:
            c = int(np.count_nonzero((finite > lo) & (finite <= hi)))
        pct = (100.0 * c / total) if total else 0.0
        counts.append((label, c, pct))
    return counts, total


def _fmt_pos(flat, shape):
    if len(shape) == 0:
        return f"flat {flat}"
    coord = np.unravel_index(int(flat), tuple(int(d) for d in shape))
    return "[" + ",".join(str(int(x)) for x in coord) + f"] (flat {flat})"


def _fmt_val(v):
    if isinstance(v, (np.floating, float)):
        return f"{float(v):.6g}"
    return str(v)


def _rel_pct(v):
    if v is None:
        return "n/a"
    v = float(v)
    if np.isnan(v):
        return "nan"
    if np.isinf(v):
        return "inf"
    return f"{v * 100:.4f}%"


def _fmt_abs(v):
    """Print max_abs with at most 8 decimals; tiny non-zero values show ~1e-8."""
    if v is None:
        return "n/a"
    v = float(v)
    if np.isnan(v):
        return "nan"
    if np.isinf(v):
        return "inf"
    if v == 0.0:
        return "0.00000000"
    if abs(v) < 1e-8:
        return "~0.00000001"
    return f"{v:.8f}"


def _top_rows(e_flat, a_flat, ab_flat, rl_flat, shape, order, dtype_label):
    rows = []
    for rank, flat in enumerate(order):
        ab = float(ab_flat[flat])
        if np.isnan(ab):
            abs_s = "nan"
        elif np.isinf(ab):
            abs_s = "inf"
        else:
            abs_s = f"{ab:.6e}"
        rows.append({
            "rank": rank + 1,
            "pos": _fmt_pos(flat, shape),
            "dtype": dtype_label,
            "exp": _fmt_val(e_flat[flat]),
            "act": _fmt_val(a_flat[flat]),
            "abs": abs_s,
            "rel": _rel_pct(float(rl_flat[flat])),
        })
    return rows


def detail_stats(expected, actual, dtype, top_n=30):
    """Per-element error stats: 5 absolute-error bins + top_n elements by abs/rel error."""
    if list(np.shape(expected)) != list(np.shape(actual)):
        return None
    shape = list(np.shape(expected))
    abs_err, rel_err = _err_arrays(expected, actual)
    bins, total = _bin_counts(abs_err)
    e_flat = expected.reshape(-1)
    a_flat = actual.reshape(-1)
    ab_flat = abs_err.reshape(-1)
    rl_flat = rel_err.reshape(-1)
    # TOP tables ignore negligible errors (abs_err <= 1e-6); bins still count all
    cand = np.flatnonzero(np.isfinite(ab_flat) & (ab_flat > 1e-6))
    if cand.size:
        order_abs = cand[np.argsort(-ab_flat[cand], kind="stable")[:top_n]]
        order_rel = cand[np.argsort(-rl_flat[cand], kind="stable")[:top_n]]
    else:
        order_abs = np.array([], dtype=int)
        order_rel = np.array([], dtype=int)
    return {
        "total": total,
        "bins": bins,
        "top_abs": _top_rows(e_flat, a_flat, ab_flat, rl_flat, shape, order_abs, dtype),
        "top_rel": _top_rows(e_flat, a_flat, ab_flat, rl_flat, shape, order_rel, dtype),
    }


def write_table_log(path, model_id, source, ref_dir, threshold, results, details,
                    expected_paths, actual_paths):
    col_pos, col_dtype, col_exp, col_act = 22, 7, 16, 16
    row_fmt = ("| {rank:>4} | {pos:<%d} | {dtype:<%d} | {exp:>%d} | {act:>%d} | "
               "{abs:>11} | {rel:>9} |" % (col_pos, col_dtype, col_exp, col_act))

    def fmt_row(rank, pos, dtype, exp, act, abs_s, rel_s):
        return row_fmt.format(rank=rank, pos=pos, dtype=dtype, exp=exp, act=act,
                              abs=abs_s, rel=rel_s)

    header = fmt_row("rank", "position", "dtype", "expected", "actual", "abs_err", "rel_err")
    W = len(header)
    eq = "=" * W

    def frame(text):
        s = "| " + str(text)
        if len(s) < W - 1:
            s += " " * (W - 1 - len(s))
        return s + "|"

    def trunc(s, n):
        s = str(s)
        return s if len(s) <= n else s[: n - 1] + "..."

    def row_line(r):
        return fmt_row(r["rank"], trunc(r["pos"], col_pos), trunc(r["dtype"], col_dtype),
                       trunc(r["exp"], col_exp), trunc(r["act"], col_act), r["abs"], r["rel"])

    lines = [eq, frame(f"ACCURACY VERIFY TABLE - M{model_id}".center(W - 4)), eq]
    for k, v in [
        ("model_id", model_id),
        ("golden_source", source),
        ("reference_dir", str(ref_dir)),
        ("threshold", f"rtol={threshold['rtol']} atol={threshold['atol']}"),
        ("report", str(C.output_dir(model_id) / "verify_report.json")),
    ]:
        lines.append(frame(f"{k:<14}: {v}"))
    lines.append(eq)

    for i, r in enumerate(results):
        d = details[i]
        lines.append(frame(f"OUTPUT[{i}] {r['name']} ({r['dtype']}) "
                           f"shape={r['actual_shape']} pass={r['pass']}"))
        lines.append(frame(f"expected      : {expected_paths[i]}"))
        lines.append(frame(f"actual        : {actual_paths[i]}"))
        if r["mismatch"] is not None:
            lines.append(frame(f"summary: mismatch={r['mismatch']} / total={d['total'] if d else '?'}"))
        elif r["max_abs"] is None:
            extra = ""
            if r.get("non_finite_actual"):
                extra = f" non_finite_actual={r['non_finite_actual']}"
            elif r.get("non_finite_expected"):
                extra = f" non_finite_expected={r['non_finite_expected']}"
            lines.append(frame(f"summary: shape mismatch or invalid reference{extra}"))
        else:
            lines.append(frame(f"summary: max_abs={r['max_abs']:.6e} "
                               f"max_rel={_rel_pct(r.get('max_rel_eff'))}"))
        if d is None:
            lines.append(frame("no element table (shape mismatch or non-finite data)"))
            lines.append(eq)
            continue
        lines.append(eq)
        lines.append(frame("ABSOLUTE ERROR DISTRIBUTION"))
        lines.append(eq)
        for label, c, pct in d["bins"]:
            lines.append(frame(f"{label:<24}| {c:>10} | {pct:>8.4f}%"))
        for title, rows in (("TOP 30 BY ABSOLUTE ERROR", d["top_abs"]),
                            ("TOP 30 BY RELATIVE ERROR", d["top_rel"])):
            lines.append(eq)
            lines.append(frame(title))
            lines.append(eq)
            if not rows:
                lines.append(frame("no element with abs_err > 1e-6"))
                lines.append(eq)
                continue
            lines.append(header)
            lines.append(eq)
            for row in rows:
                lines.append(row_line(row))
            lines.append(eq)
    path.write_text("\n".join(lines) + "\n")
    return path


def _clean_outputs(out_dir):
    if not out_dir.exists():
        return
    for p in out_dir.glob("output_*.bin"):
        p.unlink()
    for name in ("output_shapes.json", "output_shapes.json.tmp", ".complete", ".complete.tmp",
                 "verify_report.json", "verify_table.log"):
        p = out_dir / name
        if p.exists():
            p.unlink()


def _read_complete(path):
    data = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    return data


def run_inference(model_id):
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
    env = os.environ.copy()
    env["MODEL_ID"] = model_id
    env["PrintOutput"] = "True"
    env["THREAD_NUM"] = "1"
    env["GE_RUN_ID"] = run_id
    root = C.demo_root()
    out_dir = C.output_dir(model_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    _clean_outputs(out_dir)
    print(f"[verify] re-run inference: bash test.sh "
          f"(MODEL_ID={model_id}, PrintOutput=True, GE_RUN_ID={run_id})")
    cp = subprocess.run(["bash", str(root / "test.sh")], cwd=str(root), env=env, check=False)
    if cp.returncode != 0:
        raise SystemExit(f"[ERROR] inference failed (rc={cp.returncode}); skip verification")
    return run_id


def main():
    ap = argparse.ArgumentParser(description="GE_SESSION_DEMO accuracy verification")
    ap.add_argument("model_id")
    ap.add_argument("--run", action="store_true", help="re-run inference before verification")
    ap.add_argument("--golden-source", default="auto", choices=["auto", "user", "ort"])
    ap.add_argument("--rtol", type=float, default=1e-3)
    ap.add_argument("--atol", type=float, default=1e-3)
    ap.add_argument("--ref-dir", default=None)
    ap.add_argument("--run-id", default=None,
                    help="require output/.complete to contain this run id")
    ap.add_argument("--gate", default=None,
                    help="per-output precision gate JSON (default: M<id>/config/precision_gate.json)")
    args = ap.parse_args()

    model_id = C.normalize_model_id(args.model_id)
    io_path = C.config_dir(model_id) / "io_config.json"
    C.check_exists(io_path, "io_config.json (run prepare_input.py first)")
    io = C.read_json(io_path)
    io_outputs = io["outputs"]

    gate_path, gate = load_precision_gate(model_id, args.gate)
    print(f"[verify] model_id={model_id} fallback float threshold rtol={args.rtol} atol={args.atol}"
          f" (override with --rtol/--atol)")
    if gate_path:
        print(f"[verify] per-output precision gate: {C.rel_to_root(gate_path)} "
              f"({len(gate.get('outputs') or {})} 个输出自定义阈值)")
    else:
        print("[verify][WARN] 未找到 precision_gate.json —— 全部输出使用全局阈值，"
              "若某输出有已批准的差异化阈值，其精度门禁结论不可信")

    source, files, ref_dir = resolve_golden(model_id, args.ref_dir, args.golden_source)
    print(f"[verify] golden source: {source} ({ref_dir})")

    out_dir = C.output_dir(model_id)
    expected_run_id = args.run_id
    if args.run:
        expected_run_id = run_inference(model_id)

    complete_path = out_dir / ".complete"
    if not complete_path.exists():
        raise SystemExit(
            f"[ERROR] output/.complete missing: {complete_path}\n"
            f"        run inference with PrintOutput=True first, or add --run."
        )
    complete = _read_complete(complete_path)
    if expected_run_id and complete.get("run_id") != expected_run_id:
        raise SystemExit(
            f"[ERROR] stale output: .complete run_id={complete.get('run_id')!r} "
            f"!= expected={expected_run_id!r}"
        )
    if not expected_run_id:
        print(f"[verify][WARN] .complete run_id={complete.get('run_id')!r}; "
              f"freshness is not asserted (pass --run-id for strict checking)")

    actual_files = _sorted_by_index(list(out_dir.glob("output_*.bin"))) if out_dir.exists() else []
    if not actual_files:
        raise SystemExit(
            f"[ERROR] output dir is empty: {out_dir}\n"
            f"        run test.sh with PrintOutput=True first, or add --run."
        )

    if len(io_outputs) != len(files) or len(io_outputs) != len(actual_files):
        raise SystemExit(
            f"[ERROR] output count mismatch: io_config={len(io_outputs)} golden={len(files)} "
            f"actual={len(actual_files)}; check golden and outputs are complete."
        )

    actual_shapes = load_actual_shapes(model_id)
    if actual_shapes:
        print(f"[verify] actual output shapes (output_shapes.json): "
              f"{ {i: actual_shapes[i] for i in sorted(actual_shapes)} }")

    results = []
    details = []
    expected_paths = []
    actual_paths = []
    all_pass = True
    for i in range(len(io_outputs)):
        io_out = io_outputs[i]
        cfg_shape = [int(d) for d in io_out.get("shape", [])]
        actual_shape = actual_shapes.get(i)
        if actual_shape is None:
            if cfg_shape is not None and all(d != -1 for d in cfg_shape):
                actual_shape = cfg_shape
            else:
                raise SystemExit(
                    f"[ERROR] output[{i}] '{io_out['name']}' shape is dynamic {cfg_shape} and "
                    f"output/output_shapes.json is missing; run inference first (or add --run)."
                )
        if cfg_shape is not None and all(d != -1 for d in cfg_shape) and cfg_shape != actual_shape:
            print(f"[verify][WARN] output[{i}] '{io_out['name']}' io_config shape {cfg_shape} "
                  f"!= actual {actual_shape}; using the actual GE output shape")
        expected = load_expected(files[i], io_out, actual_shape)
        actual = C.bytes_to_array(actual_files[i].read_bytes(), io_out["dtype"], actual_shape)
        out_rtol, out_atol = gate_threshold(gate, io_out["name"], args.rtol, args.atol)
        r = compare_one(expected, actual, io_out["dtype"], out_rtol, out_atol)
        r.update(index=i, name=io_out["name"], dtype=io_out["dtype"],
                 rtol=out_rtol, atol=out_atol)
        results.append(r)
        details.append(detail_stats(expected, actual, io_out["dtype"]))
        expected_paths.append(str(Path(files[i]).resolve()))
        actual_paths.append(str(Path(actual_files[i]).resolve()))
        all_pass = all_pass and r["pass"]

    table_path = out_dir / "verify_table.log"
    report = {
        "model_id": model_id,
        "golden_source": source,
        "reference_dir": C.rel_to_root(ref_dir),
        "threshold": {"rtol": args.rtol, "atol": args.atol},
        "precision_gate": C.rel_to_root(gate_path) if gate_path else None,
        "outputs": results,
        "table_log": C.rel_to_root(table_path),
        "pass": all_pass,
    }
    C.write_json(out_dir / "verify_report.json", report)
    write_table_log(table_path, model_id, source, ref_dir, report["threshold"], results, details,
                    expected_paths, actual_paths)

    for r in results:
        if r["pass"]:
            detail = "exact" if r["mismatch"] is not None else \
                f"max_abs={_fmt_abs(r['max_abs'])} max_rel={_rel_pct(r.get('max_rel_eff'))}"
            print(f"  [PASS] output[{r['index']}] {r['name']} ({r['dtype']}) {detail}")
        else:
            detail = f"mismatch={r['mismatch']}" if r["mismatch"] is not None else \
                f"max_abs={_fmt_abs(r['max_abs'])} max_rel={_rel_pct(r.get('max_rel_eff'))}"
            print(f"  [FAIL] output[{r['index']}] {r['name']} ({r['dtype']}) {detail} "
                  f"expected_shape={r['expected_shape']} actual_shape={r['actual_shape']}")
    print(f"[verify] {'PASS' if all_pass else 'FAIL'}; compared data dir: {out_dir}/")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()