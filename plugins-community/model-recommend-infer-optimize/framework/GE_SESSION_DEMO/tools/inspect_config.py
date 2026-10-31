#!/usr/bin/env python3
"""Configuration inspection tool.

Usage:
  python3 tools/inspect_config.py <model_id> [--ignore-warning] [--fix] [--gen-input]

Behavior:
  - Print a full human-readable report and save txt + json to M<id>/report/.
  - Issues are marked [WARNING]; with warnings the process exits 2 (stop further steps)
    unless --ignore-warning (exit 0).
  - Fatal errors (missing/unreadable files) exit 1.
  - Cross-checks model.onnx inputs and outputs against model_config for count/order/name/dtype/
    shape/dynamic metadata, so stale configs are reported.
  - By default report + fix suggestions only; --fix reruns prepare_input.py to regenerate
    io_config/batch_list, passing --gen-input when --gen-input is also given.
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402


def prod(xs):
    n = 1
    for x in xs:
        n *= int(x)
    return n


def main():
    ap = argparse.ArgumentParser(description="Configuration inspection")
    ap.add_argument("model_id")
    ap.add_argument("--ignore-warning", action="store_true")
    ap.add_argument("--fix", action="store_true", help="rerun prepare_input.py after issues are found")
    ap.add_argument("--gen-input", action="store_true",
                    help="with --fix, pass --gen-input to prepare_input.py (auto-generate missing inputs)")
    args = ap.parse_args()

    model_id = C.normalize_model_id(args.model_id)
    mc_p = C.config_dir(model_id) / "model_config.json"
    sc_p = C.config_dir(model_id) / "shape_config.json"
    io_p = C.config_dir(model_id) / "io_config.json"
    bl_p = C.input_data_dir(model_id) / "batch_list.json"

    report_dir = C.model_dir(model_id) / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    fatal = []
    for p, name in [(mc_p, "model_config.json"), (sc_p, "shape_config.json"),
                    (io_p, "io_config.json"), (bl_p, "batch_list.json")]:
        if not p.exists():
            fatal.append(f"missing {name}: {p}")
    if fatal:
        for f in fatal:
            print(f"[ERROR] {f}")
        print("[inspect] fatal error, exit 1")
        sys.exit(1)

    mc = C.read_json(mc_p)
    sc = C.read_json(sc_p)
    io = C.read_json(io_p)
    bl = C.read_json(bl_p)

    checks = []

    def add(status, name, detail=""):
        checks.append({"status": status, "name": name, "detail": detail})

    # summary
    print(f"=== M{model_id} config report ===")
    print(f"[summary] model_id={io.get('model_id')} framework={io.get('framework')} "
          f"shape_mode={io.get('shape_mode')} pass_input_shape={io.get('pass_input_shape')} "
          f"batch_size={io.get('batch_size')}")

    io_in = io.get("inputs", [])
    io_out = io.get("outputs", [])
    mc_in = mc.get("inputs", [])
    mc_out = mc.get("outputs", [])

    # inputs
    print(f"[inputs] total {len(io_in)}")
    print("  idx  name  onnx_dtype  io_dtype  runtime_shape  parser_shape  hint")
    for i, e in enumerate(io_in[:50]):
        print(f"  {e.get('index')}  {e.get('name')}  {mc_in[i].get('dtype') if i < len(mc_in) else '?'}"
              f"  {e.get('dtype')}  {e.get('runtime_shape')}  {e.get('parser_shape')}  {e.get('hint_shape')}")
    if len(io_in) > 50:
        print(f"  ... ({len(io_in)-50} more, see JSON report)")

    # outputs
    print(f"[outputs] total {len(io_out)}")
    for e in io_out:
        print(f"  {e.get('index')}  {e.get('name')}  {e.get('dtype')}  {e.get('shape')}  {e.get('size_bytes')}")
    print(f"[batch_list] {len(bl)} items, total size={sum(int(x.get('size',0)) for x in bl)} bytes")

    # 1. input order/name/dtype
    if len(io_in) != len(mc_in):
        add("WARNING", "io.inputs count differs from model_config.inputs",
            f"io={len(io_in)} model={len(mc_in)}")
    else:
        mismatch = [i for i, (a, b) in enumerate(zip(io_in, mc_in))
                    if a.get("name") != b.get("name") or a.get("dtype") != b.get("dtype")]
        add("OK" if not mismatch else "WARNING",
            "io.inputs matches model_config input order/name/dtype",
            "" if not mismatch else f"mismatch indexes: {mismatch}")

    # 2. batch_list order
    if len(bl) != len(io_in):
        add("WARNING", "batch_list length differs from io.inputs", f"{len(bl)} vs {len(io_in)}")
    else:
        bad = [i for i, (b, e) in enumerate(zip(bl, io_in)) if b.get("ori_name") != e.get("name")]
        add("OK" if not bad else "WARNING", "batch_list order matches io.inputs",
            "" if not bad else f"order mismatch indexes: {bad}")

        # 3. dim/size
        size_bad = []
        for i, (b, e) in enumerate(zip(bl, io_in)):
            dim = b.get("dim", [])
            if dim != e.get("runtime_shape"):
                size_bad.append(f"[{i}] {b.get('ori_name')} dim {dim} != runtime {e.get('runtime_shape')}")
            expect = prod(dim) * int(e.get("elem_bytes", 0))
            if int(b.get("size", 0)) != expect:
                size_bad.append(f"[{i}] {b.get('ori_name')} size {b.get('size')} != {expect}")
        add("OK" if not size_bad else "WARNING", "batch_list dim/size matches io",
            "" if not size_bad else "; ".join(size_bad[:5]))

    # 4. output size (dynamic outputs carry -1 / null size_bytes; GE decides at runtime)
    out_bad = []
    dyn_out = []
    for j, e in enumerate(io_out):
        shape = e.get("shape", [])
        if any(int(d) == -1 for d in shape) or e.get("size_bytes") is None:
            dyn_out.append(e.get("name"))
            continue
        expect = prod(shape) * int(e.get("elem_bytes", 0))
        if int(e.get("size_bytes", 0)) != expect:
            out_bad.append(f"[{j}] {e.get('name')} size {e.get('size_bytes')} != {expect}")
    detail = "; ".join(out_bad)
    if dyn_out:
        detail = (detail + "; " if detail else "") + f"dynamic outputs use runtime shape: {dyn_out}"
    add("OK" if not out_bad else "WARNING", "io.outputs size_bytes is self-consistent", detail)

    # 5. shape_config validity
    mode = sc.get("mode")
    if mode not in ("all_static", "all_dynamic", "custom"):
        add("WARNING", "shape_config.mode is valid", f"invalid mode={mode}")
    else:
        in_names = {e.get("name") for e in io_in}
        out_names = {e.get("name") for e in io_out}
        bad_ov = [k for k in sc.get("overrides", {}) if k not in in_names]
        bad_out = [k for k in sc.get("output_overrides", {}) if k not in out_names]
        add("OK" if not bad_ov and not bad_out else "WARNING",
            "shape_config overrides/output_overrides keys exist",
            "" if not bad_ov and not bad_out else f"unknown input keys={bad_ov} unknown output keys={bad_out}")

    # 6. paths exist
    mf = C.demo_root() / io.get("model_file", "")
    blp = C.demo_root() / io.get("batch_list", "")
    add("OK" if mf.exists() else "WARNING", "model_file path is readable", str(mf))
    add("OK" if blp.exists() else "WARNING", "batch_list path is readable", str(blp))

    # 7. dtype validity
    dtypes = {e.get("dtype") for e in io_in + io_out}
    bad_dt = sorted(d for d in dtypes if not C.is_supported_dtype(d))
    add("OK" if not bad_dt else "WARNING", "all dtypes are supported",
        "" if not bad_dt else f"unsupported: {bad_dt} (supported: {list(C.SUPPORTED_DTYPES)})")

    # 8. re-read onnx for cross-check (stale config detection)
    try:
        model = C.load_onnx(mf)
        m_inputs, m_outputs = C.build_input_output_info(model)

        def compare_meta(kind, onnx_items, cfg_items):
            bad = []
            if len(onnx_items) != len(cfg_items):
                bad.append(f"{kind} count onnx={len(onnx_items)} "
                           f"model_config={len(cfg_items)}")
                return bad
            for i, (a, b) in enumerate(zip(onnx_items, cfg_items)):
                for key in ("name", "dtype", "onnx_shape", "dynamic_dims", "symbolic"):
                    if a.get(key) != b.get(key):
                        bad.append(f"[{i}] {key}: onnx={a.get(key)} config={b.get(key)}")
            return bad

        input_bad = compare_meta("input", m_inputs, mc_in)
        output_bad = compare_meta("output", m_outputs, mc_out)
        add("OK" if not input_bad else "WARNING",
            "model.onnx inputs match model_config (shape/dtype not stale)",
            "" if not input_bad else "; ".join(input_bad[:5]))
        add("OK" if not output_bad else "WARNING",
            "model.onnx outputs match model_config (shape/dtype not stale)",
            "" if not output_bad else "; ".join(output_bad[:5]))
    except Exception as e:
        add("WARNING", "model.onnx cross-check", f"read failed: {e}")

    # 9. batch_list value key sampling
    sample_bad = []
    for e in bl[:3]:
        keys = [k for k in e if k.endswith("_val") or k.endswith("_bits")]
        if not keys:
            sample_bad.append(f"{e.get('ori_name')} has no value key")
    add("OK" if not sample_bad else "WARNING", "batch_list value key sampling", "; ".join(sample_bad))

    # print check results
    warnings = [c for c in checks if c["status"] == "WARNING"]
    print("[checks]")
    for c in checks:
        mark = "[OK]     " if c["status"] == "OK" else "[WARNING]"
        print(f"  {mark} {c['name']}" + (f" —— {c['detail']}" if c["detail"] else ""))
    print(f"[conclusion] passed {len(checks)-len(warnings)}, warnings {len(warnings)} -> "
          f"{'PASS' if not warnings else 'WARN'}")

    result = {
        "model_id": model_id,
        "pass": not warnings,
        "checks": checks,
        "warnings": [c["name"] for c in warnings],
    }
    txt_path = report_dir / f"inspect_report_{ts}.txt"
    json_path = report_dir / f"inspect_report_{ts}.json"
    C.write_json(json_path, result)
    with open(txt_path, "w") as f:
        f.write(f"=== M{model_id} config report ({ts}) ===\n")
        f.write(f"pass={result['pass']} warnings={result['warnings']}\n")
        for c in checks:
            f.write(f"[{c['status']}] {c['name']}" + (f" —— {c['detail']}" if c["detail"] else "") + "\n")
    print(f"[inspect] JSON saved to {json_path} (not printed here; for downstream pipelines)")
    print(f"[inspect] TXT  saved to {txt_path}")

    if warnings and args.fix:
        print("[inspect] --fix: rerun prepare_input.py to regenerate io_config/batch_list ...")
        cmd = [sys.executable, str(Path(__file__).parent / "prepare_input.py"), model_id]
        if args.gen_input:
            cmd.append("--gen-input")
        subprocess.run(cmd, check=False)

    if warnings and not args.ignore_warning:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()