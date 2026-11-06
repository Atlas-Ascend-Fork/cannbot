#!/usr/bin/env python3
# ----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# ----------------------------------------------------------------------------------------------------------

"""
dashboard_parsers.py  —  op-dashboard 的数据发现与解析层

四部分：算子输出目录的自动发现（discover）、各类数据源的解析（op_desc /
evaluation / precision / msprof CSV / kernel / op_host / DSL）、UB buffer
尺寸推算，以及 op_graph 骨架构建。只读不写，不产生 HTML。
"""

import csv
import io
import json
import logging
import re
from pathlib import Path
from typing import NamedTuple

from dashboard_config import _tok

logger = logging.getLogger(__name__)


# ─── AUTO-DISCOVER ─────────────────────────────────────────────────────────────


def _pick_latest(candidates) -> "Path | None":
    """从候选路径列表中选取 mtime 最新的文件（忽略访问错误）。"""
    best, best_mtime = None, -1.0
    for cand in candidates:
        try:
            t = cand.stat().st_mtime
            if t > best_mtime:
                best, best_mtime = cand, t
        except Exception as e:
            logger.debug("无法读取候选文件 mtime，已跳过 %s: %s", cand, e)
    return best


def _is_msprof_fair_bench_run(eval_path: "Path") -> bool:
    """
    检测 evaluation_results.json 是否来自 msprof_fair_bench.py 的 ModelNew=Model 镜像跑法。
    这类跑法 speedup≈1.0，ref_time 无效，应跳过作为性能数据源。
    判断依据：文件所在目录名含 _ref_timing_ 或父目录含 ref_timing。
    """
    try:
        parts = eval_path.parts
        for part in parts:
            if "_ref_timing_" in part or part.endswith("_ref_timing"):
                return True
    except Exception as e:
        logger.debug("检测 ref_timing 路径失败，按非镜像跑处理 %s: %s", eval_path, e)
    return False


# Keywords that mark a markdown heading as describing a kernel's UB layout.
_MEM_GROUP_KEYWORDS = (
    "UB",
    "ub",
    "buffer",
    "Buffer",
    "内存",
    "空间",
    "kernel",
    "Kernel",
)

_SHAPE_DIM_NAMES = ("M", "N", "K", "B", "H", "S", "D", "C", "L")


def _is_shape_dim(name: str, value) -> bool:
    return isinstance(value, int) and name in _SHAPE_DIM_NAMES


def _is_case_summary_csv(path) -> bool:
    return "origin_data" not in path.parts and not path.name.startswith(
        "op_summary_reference_fn_"
    )


def _first_match(op_dir: Path, pattern: str):
    """rglob 的第一个匹配项（按字典序），没有则返回 None。"""
    for f in sorted(op_dir.rglob(pattern)):
        return f
    return None


def _is_cake2_csv(candidate) -> bool:
    """CAKE2 evaluate.py 产出的 op_summary_<case>.csv（排除 msprof 平铺格式与汇总表）。"""
    return (
        not candidate.name.startswith("op_summary_custom_fn_")
        and not candidate.name.startswith("op_summary_reference_fn_")
        and candidate.name != "multi_case_report.csv"
    )


def _has_paired_model_dirs(d: Path) -> bool:
    """profiling 目录下是否同时存在 Model_device* 与 ModelNew_device* 子目录。"""
    entries = list(d.iterdir())
    has_model = any(
        x.is_dir()
        and x.name.startswith("Model_device")
        and not x.name.startswith("ModelNew")
        for x in entries
    )
    has_modelnew = any(
        x.is_dir() and x.name.startswith("ModelNew_device") for x in entries
    )
    return has_model and has_modelnew


def _discover_eval(op_dir: Path, found: dict) -> None:
    """evaluation_results.json / results_precision.json：
    优先选 mtime 最新的，且跳过 msprof_fair_bench 镜像跑（_ref_timing_ 目录）。"""
    candidates = list(op_dir.rglob("evaluation_results.json")) + list(
        op_dir.rglob("results_precision.json")
    )
    real_evals = [f for f in candidates if not _is_msprof_fair_bench_run(f)]
    pick = _pick_latest(real_evals) or _pick_latest(candidates)
    if pick:
        found["eval"] = pick
        return
    txt_pick = _pick_latest(list(op_dir.rglob("evaluation_result*.txt")))
    if txt_pick:
        found["eval"] = txt_pick


def _discover_profiling(op_dir: Path, found: dict) -> None:
    """Standard profiling/ directory（直接在 op_dir 下）；没有时回退到
    TileLang / msprof_fair_bench 的 *_ref_timing_*/profiling/ 子目录。"""
    profiling = op_dir / "profiling"
    if profiling.is_dir():
        found["profiling_dir"] = profiling
        csv_path = profiling / "multi_case_report.csv"
        if csv_path.exists():
            found["multi_csv"] = csv_path
        report = profiling / "report.txt"
        if report.exists():
            found["report_txt"] = report
        return

    # 找最新的含有 Model_device* + ModelNew_device* 配对的 profiling 目录
    candidates = [
        d for d in op_dir.rglob("profiling") if d.is_dir() and _has_paired_model_dirs(d)
    ]
    if not candidates:
        return
    # 选 mtime 最新的 profiling 目录
    best = max(candidates, key=lambda p: p.stat().st_mtime)
    found["profiling_dir"] = best
    report = best / "report.txt"
    if report.exists():
        found["report_txt"] = report


def _discover_msprof_csvs(op_dir: Path, found: dict) -> None:
    """Flat msprof CSVs: op_summary_custom_fn_<case>.csv + op_summary_reference_fn_<case>.csv；
    都没有时再找 CAKE2 evaluate.py 格式的 op_summary_<case>.csv。"""
    if "multi_csv" not in found:
        custom_csvs = sorted(op_dir.rglob("op_summary_custom_fn_*.csv"))
        ref_csvs = sorted(op_dir.rglob("op_summary_reference_fn_*.csv"))
        if custom_csvs or ref_csvs:
            found["msprof_custom_csvs"] = custom_csvs
            found["msprof_ref_csvs"] = ref_csvs
    if "multi_csv" in found or "msprof_custom_csvs" in found:
        return

    # 路径不固定，优先在已找到的 profiling_dir 下 glob；
    # 若无 profiling_dir，则在 op_dir 全局 rglob，不假设固定层级。
    if found.get("profiling_dir"):
        search_iter = Path(found["profiling_dir"]).glob("op_summary_*.csv")
    else:
        search_iter = op_dir.rglob("op_summary_*.csv")
    cake2_csvs = sorted(f for f in search_iter if _is_cake2_csv(f))
    if cake2_csvs:
        found["msprof_cake2_csvs"] = cake2_csvs


def _discover_code_sources(op_dir: Path, found: dict) -> None:
    """op_host / kernel / dsl 源文件；kernel 找不到时回退 *_custom.cpp。"""
    for key, pattern in (("op_host", "op_host/*.cpp"), ("kernel", "op_kernel/*.cpp")):
        f = _first_match(op_dir, pattern)
        if f:
            found[key] = f
    if "kernel" not in found:
        f = _first_match(op_dir, "*_custom.cpp")
        if f:
            found["kernel"] = f
    f = _first_match(op_dir, "*_dsl.py")
    if f:
        found["dsl"] = f


def _pick_colocated(candidates: list, eval_path):
    """优先取与所选 eval 目录同级的候选（最相关），否则按 mtime 取最新。"""
    if not eval_path:
        return _pick_latest(candidates)
    eval_dir = Path(eval_path).parent
    colocated = [f for f in candidates if f.parent == eval_dir]
    return _pick_latest(colocated) or _pick_latest(candidates)


def _discover_test_cases(op_dir: Path, found: dict) -> None:
    """test_cases.csv / test_cases.py：优先与 eval 目录同级，否则取 mtime 最新。"""
    for key, name in (
        ("test_cases", "test_cases.csv"),
        ("test_cases_py", "test_cases.py"),
    ):
        candidates = list(op_dir.rglob(name))
        if candidates:
            found[key] = _pick_colocated(candidates, found.get("eval"))


def _discover_panel_files(op_dir: Path, found: dict) -> None:
    """algo_flow.json（panels/algo/ 优先，其次根目录），以及 TileLang standalone
    的 panels/perf/cann_result.json 与 panels/memory/analysis.md。"""
    panels_algo_flow = op_dir / "panels" / "algo" / "algo_flow.json"
    if panels_algo_flow.exists():
        found["algo_flow"] = panels_algo_flow
    else:
        for f in sorted(op_dir.glob("algo_flow.json")):
            found["algo_flow"] = f
            break
    for key, rel in (
        ("cann_result", ("panels", "perf", "cann_result.json")),
        ("memory_analysis_md", ("panels", "memory", "analysis.md")),
    ):
        path = op_dir.joinpath(*rel)
        if path.exists():
            found[key] = path


def discover(op_dir: Path) -> dict:
    found = {}
    for key, pattern in (
        ("op_desc", "*_op_desc.json"),
        ("precision", "precision_results.json"),
    ):
        f = _first_match(op_dir, pattern)
        if f:
            found[key] = f
    _discover_eval(op_dir, found)
    _discover_profiling(op_dir, found)
    _discover_msprof_csvs(op_dir, found)
    _discover_code_sources(op_dir, found)
    _discover_test_cases(op_dir, found)
    _discover_panel_files(op_dir, found)
    return found


# ─── PARSERS ──────────────────────────────────────────────────────────────────


def _read(path) -> str:
    return (
        Path(path).read_text(encoding="utf-8", errors="replace")
        if path and Path(path).exists()
        else ""
    )


def _json(path) -> dict:
    txt = _read(path)
    try:
        return json.loads(txt) if txt else {}
    except Exception:
        return {}


def _is_buffer_header(cols: list) -> bool:
    """Detect header row: contains 'buffer'/'buf'/'用途' keyword"""
    return any(
        "buffer" in c.lower()
        or "用途" in c.lower()
        or (c.lower() in ("buf", "buffer", "缓冲区", "名称", "name"))
        for c in cols
    )


def _ub_size_kb(size_str: str) -> float:
    """Parse size: "32 KB" or "32.0 KB" or "48 KB (49152×uint8)"."""
    m = re.search(r"([\d.]+)\s*KB", size_str, re.IGNORECASE)
    return float(m.group(1)) if m else 0.0


def _ub_position(name: str) -> str:
    """Infer position from name heuristics (for metadata only, not coloring)."""
    name_lower = name.lower()
    if any(x in name_lower for x in ("l1", "l0a", "l0b")):
        return "L1"
    if any(x in name_lower for x in ("int8", "fp16", "out", "res")):
        return "VECOUT"
    return "VECCALC"


class _UbTableParser:
    """逐行扫描 analysis.md，从 markdown 表格中收集 UB buffer 声明。"""

    def __init__(self):
        self.buffers = []
        self.seen_names = set()  # 去重：同名 buffer 只保留一次
        self.in_buffer_table = False
        self.header_found = False
        self.current_group = ""  # 当前所属 kernel 组（如 "K1"/"K2"）

    def parse(self, txt: str) -> list:
        """扫描整段文本，返回收集到的 buffer 列表。"""
        for line in txt.splitlines():
            self._feed(line.strip())
        return self.buffers

    def _feed(self, s: str) -> None:
        if not s.startswith("|"):
            self._feed_text_line(s)
            return
        cols = [c.strip() for c in s.strip("|").split("|")]
        if self._consume_header(cols):
            return
        # Skip separator row (|---|---|)
        if all(re.match(r"^[-: ]+$", c) for c in cols if c.strip()):
            return
        if not self.in_buffer_table or len(cols) < 3:
            return
        self._add_buffer(cols)

    def _feed_text_line(self, s: str) -> None:
        """非表格行：若当前在 buffer 表中，退出该表，继续扫描下一个表。
        并尝试提取 kernel group label（如 K1/K2/K3/Kernel1）。"""
        if self.in_buffer_table:
            self.in_buffer_table = False
            self.header_found = False
        _grp_m = re.search(r"\b(K\d+|Kernel\s*\d+)\b", s, re.IGNORECASE)
        # 只在含 UB/buffer/内存 关键字时更新 group（避免误匹配公式里的 K1）
        _has_mem_keyword = any(kw in s for kw in _MEM_GROUP_KEYWORDS)
        if _grp_m is not None and _has_mem_keyword:
            self.current_group = _grp_m.group(1).upper().replace(" ", "")

    def _consume_header(self, cols: list) -> bool:
        """表头行只切换状态，不产生 buffer。"""
        if self.header_found or not _is_buffer_header(cols):
            return False
        self.header_found = True
        self.in_buffer_table = True
        return True

    def _add_buffer(self, cols: list) -> None:
        """把一行表格转成一条 buffer 记录。"""
        name = cols[0].strip()
        if not name or name.lower() in ("buffer", "buf", "name", "名称", "缓冲区"):
            return
        if name in self.seen_names:
            return  # 跨表格去重
        size_kb = _ub_size_kb(cols[2] if len(cols) > 2 else "")
        pos = _ub_position(name)
        # 用途描述：取第 2 列（index 1），去除 markdown 加粗等装饰
        purpose = (
            re.sub(r"\*\*([^*]+)\*\*", r"\1", cols[1].strip()) if len(cols) > 1 else ""
        )
        self.seen_names.add(name)
        self.buffers.append(
            {
                "name": name,
                "kind": "TBuf",
                "position": pos,
                "multiplier": 1,
                "size_kb": round(size_kb, 2),
                # 每个 buffer 独立配色（按全局序号从色板取，相邻 buffer 颜色不同）
                "color": _buf_color(len(self.buffers)),
                "label": f"{pos} TBuf",
                "kernel_group": self.current_group,
                "purpose": purpose,
            }
        )


def parse_ub_from_analysis_md(md_path) -> list:
    """
    从 panels/memory/analysis.md 的 markdown 表格提取 UB buffer 信息。
    支持格式（Claude 按 SPEC.md 生成）：
      **K1 UB（≈192 KB，利用率≈75%）**：
      | Buffer | 用途 | 大小 | 生命周期 |
      |--------|------|------|---------|
      | c_ub   | 暂存 GEMM int32 结果 | 32 KB (8192×int32) | AIV 开始 → Cast 前 |

    扫描整个 analysis.md：支持多个 buffer 表格（如 K1、K2 分别有自己的表格）。
    每个 buffer 携带 kernel_group 字段（如 "K1"/"K2"，单 kernel 时为 ""）。
    返回 [{name, kind, position, multiplier, size_kb, color, label, kernel_group}]
    """
    try:
        txt = _read(md_path)
        return _UbTableParser().parse(txt) if txt else []
    except Exception:
        return []


def parse_cann_result_json(path) -> dict:
    """
    解析 panels/perf/cann_result.json（TileLang standalone 真实 NPU kernel 计时结果）。
    格式：
      {"source": "tilelang_eval_adapter", "ref_time_us": 1279.8,
       "custom_time_us": 678.9, "speedup": 1.89, "notes": "..."}
    """
    try:
        data = _json(path)
        if not data:
            return {}
        return {
            "ref_time_us": float(data.get("ref_time_us", 0)),
            "custom_time_us": float(data.get("custom_time_us", 0)),
            "speedup": float(data.get("speedup", 0)),
            "source": data.get("source", "cann_standalone"),
            "notes": data.get("notes", ""),
        }
    except Exception:
        return {}


def parse_test_cases_csv(path) -> list:
    try:
        txt = _read(path)
        if not txt:
            return []
        lines = [line.strip() for line in txt.strip().splitlines() if line.strip()]
        if len(lines) < 2:
            return []
        sep = ";" if ";" in lines[0] else ","
        headers = [h.strip() for h in lines[0].split(sep)]
        cases = []
        for line in lines[1:]:
            parts = line.split(sep)
            row = {h: v.strip() for h, v in zip(headers, parts)}
            cases.append(row)
        return cases
    except Exception:
        return []


# case 片段中形如 "mat1_shape": [2048, 4096] 的整数数组字段
_SHAPE_FIELD_PAT = re.compile(
    r'"(mat1_shape|mat2_shape|input_shape|shape|shape1|shape2)"\s*:\s*\[([^\]]+)\]'
)
# _shape_label 的第三种结果：片段里没有任何可识别的 shape 字段，应走通用 fallback
_NO_SHAPE_FIELDS = object()


def _case_segment_shapes(segment: str) -> dict:
    """从一个 case 片段解析出 mat1_shape / shape1 / shape 等整数数组字段。"""
    shapes = {}
    for sm in _SHAPE_FIELD_PAT.finditer(segment):
        vals = [v.strip() for v in sm.group(2).split(",")]
        try:
            shapes[sm.group(1)] = [int(v) for v in vals if v]
        except ValueError:
            pass
    return shapes


def _matmul_pair_label(s1: list, s2: list) -> str:
    """shape1[..., M, K] × shape2[..., K, N] 的标签；非 Matmul 形态则并列显示两个 shape。"""
    if len(s1) < 2 or len(s2) < 2 or s1[-1] != s2[-2]:
        # Element-wise binary: show both shapes
        return f"{'×'.join(str(v) for v in s1)} / {'×'.join(str(v) for v in s2)}"
    if len(s1) == 2:
        return f"M={s1[0]} K={s1[1]} N={s2[1]}"
    batch = "×".join(str(v) for v in s1[:-2])
    return f"B={batch} M={s1[-2]} K={s1[-1]} N={s2[-1]}"


def _shape_label(shapes: dict):
    """shape 字段集合 → 展示用维度标签；字段齐全但不可用返回 None，无字段返回哨兵。"""
    if "mat1_shape" in shapes and "mat2_shape" in shapes:
        m1, m2 = shapes["mat1_shape"], shapes["mat2_shape"]
        if len(m1) >= 2 and len(m2) >= 2:
            return f"M={m1[0]} K={m1[1]} N={m2[1]}"
        return None
    if "mat1_shape" in shapes:
        return "×".join(str(v) for v in shapes["mat1_shape"])
    if "shape1" in shapes and "shape2" in shapes:
        return _matmul_pair_label(shapes["shape1"], shapes["shape2"])
    # shape1 / shape（Softmax、Gelu 等标准键）/ input_shape，按此优先级取第一个命中的
    for key in ("shape1", "shape", "input_shape"):
        if key in shapes:
            return "×".join(str(v) for v in shapes[key])
    return _NO_SHAPE_FIELDS


def _fallback_shape_label(segment: str):
    """通用 fallback：从 case 片段提取 "key": 整数 字段（排除 id/seed 等元信息）。"""
    _skip = {"id", "seed", "case_id", "rank"}
    _prio = ["N_orig", "N_expert", "D_in", "D_out", "K", "G", "M", "N", "H", "S", "B"]
    kv = {}
    for kvm in re.finditer(r'"(\w+)"\s*:\s*(\d+)', segment):
        k, v = kvm.group(1), int(kvm.group(2))
        if k.lower() not in _skip and k not in kv:
            kv[k] = v
    if not kv:
        return None
    # Priority order first, then remaining (up to 5 total)
    ordered = [(k, kv[k]) for k in _prio if k in kv]
    ordered += [(k, v) for k, v in kv.items() if k not in {k2 for k2, _ in ordered}]
    return " ".join(f"{k}={v}" for k, v in ordered[:5])


def parse_test_cases_py(path) -> dict:
    """
    从 test_cases.py 中提取 case_name → shape_str 映射。
    使用正则解析（不 exec），支持 mat1_shape/mat2_shape 字段。
    返回 {"case_name": "M=2048 K=4096 N=2048", ...}
    """
    txt = _read(path)
    if not txt:
        return {}
    result = {}
    # 找到每个 case dict 块：从 "name": "xxx" 开始，提取 mat1_shape/mat2_shape
    # 策略：按 "name": "..." 分割，然后在每段中找 mat1_shape/mat2_shape
    name_matches = list(re.finditer(r'"name"\s*:\s*"([^"]+)"', txt))
    for i, nm in enumerate(name_matches):
        # 搜索范围：到下一个 case 的 "name" 或文件末尾
        end_pos = name_matches[i + 1].start() if i + 1 < len(name_matches) else len(txt)
        start_pos = nm.start()
        segment = txt[start_pos:end_pos]
        label = _shape_label(_case_segment_shapes(segment))
        if label is _NO_SHAPE_FIELDS:
            label = _fallback_shape_label(segment)
        if label is not None:
            result[nm.group(1)] = label
    return result


def _row_shape(row: dict) -> str:
    """Shape cell of one report row: first varN_shape column, else `shape`."""
    for k, v in row.items():
        if re.match(r"var\d+_shape", k.strip()) or k.strip() == "shape":
            return v.strip().strip('"')
    return ""


def _multi_case_row(row: dict):
    """One parsed report row, or None when its numbers are unusable."""
    try:
        return {
            "case_id": int(row.get("case_id", 0) or 0),
            "shape": _row_shape(row),
            "passed": (row.get("passed", "") or "").lower() in ("true", "1", "yes"),
            "ref_time_us": float(row.get("ref_time_us", 0) or 0),
            "custom_time_us": float(row.get("custom_time_us", 0) or 0),
            "speedup": float(row.get("speedup", 0) or 0),
        }
    except (ValueError, TypeError):
        return None


def parse_multi_case_csv(path) -> list:
    """解析 multi_case_report.csv，返回 [{case_id, shape, passed, ref_us, custom_us, speedup}]"""
    txt = _read(path)
    if not txt:
        return []
    rows = []
    try:
        for row in csv.DictReader(io.StringIO(txt)):
            parsed = _multi_case_row(row)
            if parsed is not None:
                rows.append(parsed)
    except Exception as e:
        logger.debug("解析 multi_case_report.csv 失败，返回已解析行: %s", e)
    return rows


def parse_evaluation_results_json(path) -> list:
    """
    解析 CAKE2 evaluate.py 生成的 evaluation_results.json 多-case 格式。

    Schema:
      {
        "operator": "FastGelu",
        "total_cases": 10, "passed_cases": 10,
        "geometric_mean_speedup": 1.69,
        "results": [
          {"case_id": 1, "case_name": "basic_1d", "status": "PASS",
           "speedup": 1.68, "ref_time_us": 6.46, "custom_time_us": 3.62,
           "precision": {"passed": true, "ratios": {"max_re": 1.0, "mean_re": 0.38, ...}}}
        ]
      }

    Returns [{case_id, name, shape, passed, ref_time_us, custom_time_us, speedup, precision}]
    Compatible with the multi_csv branch in collect_data().
    """
    data = _json(path)
    if not data or "results" not in data:
        return []
    rows = []
    for r in data.get("results", []):
        prec_raw = r.get("precision") or {}
        ratios = prec_raw.get("ratios") or {}
        # A status of PASS counts as passed; FAIL and ERROR do not.
        passed = str(r.get("status", "")).upper() == "PASS"
        raw_cid = r.get("case_id")
        try:
            case_id = int(raw_cid) if raw_cid not in (None, "") else 0
        except (TypeError, ValueError):
            case_id = 0
        rows.append(
            {
                "case_id": case_id,
                "name": r.get("case_name", f"case_{case_id}"),
                "shape": r.get("case_name", ""),  # use case_name as shape label
                "passed": passed,
                "ref_time_us": float(r.get("ref_time_us") or 0),
                "custom_time_us": float(r.get("custom_time_us") or 0),
                "speedup": float(r.get("speedup") or 0),
                "precision": {
                    "passed": prec_raw.get("passed", passed),
                    "max_re": ratios.get("max_re"),
                    "mean_re": ratios.get("mean_re"),
                    "rmse": ratios.get("rmse"),
                    "svec": ratios.get("svec"),
                },
            }
        )
    return rows


def parse_precision_json(path) -> dict:
    """解析 precision_results.json (v2 schema)，按 case_id 提取精度指标"""
    data = _json(path)
    if not data or "cases" not in data:
        return {}
    result = {}
    for case in data.get("cases", []):
        cid = case.get("id", 0)
        params = case.get("params", {})
        fwd = case.get("forward", {})
        # 找第一个有 ratios 的 component
        for comp_name, comp in fwd.items():
            ratios = comp.get("ratios", {})
            avg_vs_golden = comp.get("ans_vs_golden", {})
            result[cid] = {
                "passed": comp.get("passed", False),
                "max_re": ratios.get("max_re"),
                "mean_re": ratios.get("mean_re"),
                "rmse": ratios.get("rmse"),
                "svec": ratios.get("svec"),
                "ae_max": avg_vs_golden.get("ae_max"),
                "re_max": avg_vs_golden.get("re_max"),
                "mismatch_rate": avg_vs_golden.get("mismatch_rate"),
                "component": comp_name,
                "params": params,
            }
            break  # only first component
    return result


def parse_evaluation_txt(path) -> list:
    """
    解析 evaluation_result.txt 日志格式（非 JSON）。
    支持格式：
      INFO - [1/10] Test: small_basic  {'M': 32, ...}
      INFO -   Correctness: [PASS] match_rate=100.00% (1536/1536), max_diff=0.0, mean_diff=0.0
      INFO -   Performance: ref=0.0068ms, custom=0.0117ms, speedup=0.58x
    返回 [{id, name, shape, passed, precision, performance}]
    """
    txt = _read(path)
    if not txt or not any(s in txt for s in ("[PASS]", "[FAIL]", "Correctness:")):
        return []
    cases = []
    # Split on test case headers
    header_re = re.compile(
        r"\[(\d+)/\d+\]\s+Test:\s+(\w+)\s+(.*?)(?=\[\d+/\d+\]|$)", re.DOTALL
    )
    for m in header_re.finditer(txt):
        idx = int(m.group(1)) - 1
        name = m.group(2)
        block = m.group(3)
        # params dict → shape string
        p = re.search(r"\{([^}]+)\}", block)
        shape = p.group(0) if p else ""
        # correctness
        passed = bool(re.search(r"\[PASS\]", block))
        mr = re.search(r"match_rate=([\d.]+)%", block)
        mx = re.search(r"max_diff=([\d.e+\-]+)", block)
        mn = re.search(r"mean_diff=([\d.e+\-]+)", block)
        # performance
        ref_m = re.search(r"ref=([\d.]+)ms", block)
        cus_m = re.search(r"custom=([\d.]+)ms", block)
        spd_m = re.search(r"speedup=([\d.]+)x", block)
        cases.append(
            {
                "id": idx,
                "name": name,
                "shape": shape,
                "passed": passed,
                "precision": {
                    "passed": passed,
                    "match_rate": float(mr.group(1)) if mr else None,
                    "max_diff": float(mx.group(1)) if mx else None,
                    "mean_diff": float(mn.group(1)) if mn else None,
                },
                "performance": {
                    "ref_time_us": float(ref_m.group(1)) * 1000 if ref_m else 0,
                    "custom_time_us": float(cus_m.group(1)) * 1000 if cus_m else 0,
                    "speedup": float(spd_m.group(1)) if spd_m else 0,
                    "source": "msprof",
                }
                if ref_m
                else {},
            }
        )
    return cases


def _msprof_row_duration(row: dict, dur_col: str, name_col, target_op) -> float | None:
    """返回单行 msprof 记录的 Task Duration，行不适用时返回 None。"""
    raw_dur = row.get(dur_col, "").strip()
    if not raw_dur:
        return None
    try:
        dur = float(raw_dur)
    except ValueError:
        return None
    if (
        target_op
        and name_col
        and target_op.lower() not in row.get(name_col, "").strip().lower()
    ):
        return None
    return dur


def parse_flat_msprof_csv_pairs(
    custom_csvs: list, ref_csvs: list, op_name: str
) -> list:
    """
    从平铺的 op_summary_custom_fn_<case>.csv + op_summary_reference_fn_<case>.csv 配对提取时延。
    自动按 case 名称配对，提取 median(Task Duration) 跳过 warmup 行。
    返回 [{case_name, ref_time_us, custom_time_us, speedup}]
    """

    def _extract_durations(csv_path: Path, target_op: str = None) -> list:
        """提取目标 op 的 Task Duration(us) 列表。
        过滤策略：若给定 target_op，只保留名称含 target_op 的行；
        否则按算子名过滤掉明显的 L2 flush/warmup（通过分位数：超过 p75 的 10 倍视为异常）。
        """
        txt = _read(csv_path)
        if not txt:
            return []
        durs = []
        try:
            reader = csv.DictReader(io.StringIO(txt))
            dur_col = next(
                (k for k in (reader.fieldnames or []) if "Duration" in k), None
            )
            name_col = next(
                (
                    k
                    for k in (reader.fieldnames or [])
                    if k.strip() in ("Op Name", "OP Type", "Name")
                ),
                None,
            )
            if not dur_col:
                return []
            for row in reader:
                dur = _msprof_row_duration(row, dur_col, name_col, target_op)
                if dur is not None:
                    durs.append(dur)
        except Exception as e:
            logger.debug("提取 Task Duration 失败 %s: %s", csv_path, e)
        if not durs:
            return durs
        # Remove outliers: rows > 20× median (catches L2 flush, large warmup)
        med = sorted(durs)[len(durs) // 2]
        threshold = max(med * 20, 200.0)
        return [d for d in durs if d <= threshold]

    def _median(lst):
        return sorted(lst)[len(lst) // 2] if lst else 0.0

    # Build {case_name: csv_path} mappings
    def _case_name(p: Path, prefix: str) -> str:
        prefix_length = len(prefix)
        return p.stem[prefix_length:]  # e.g. "op_summary_custom_fn_" → "small_basic"

    custom_map = {_case_name(f, "op_summary_custom_fn_"): f for f in custom_csvs}
    ref_map = {_case_name(f, "op_summary_reference_fn_"): f for f in ref_csvs}
    all_cases = sorted(set(custom_map) | set(ref_map))

    results, unpaired = [], []
    for case_name in all_cases:
        has_custom = case_name in custom_map
        has_ref = case_name in ref_map
        if has_custom and has_ref:
            cus_durs = _extract_durations(custom_map[case_name], op_name)
            ref_durs = _extract_durations(ref_map[case_name])
            cus_us = _median(cus_durs[1:] or cus_durs)
            ref_us = _median(ref_durs[1:] or ref_durs)
            results.append(
                {
                    "case_name": case_name,
                    "ref_time_us": ref_us,
                    "custom_time_us": cus_us,
                    "speedup": round(ref_us / cus_us, 2) if cus_us > 0 else 0,
                }
            )
        else:
            unpaired.append(
                case_name + ("(custom_only)" if has_custom else "(ref_only)")
            )
    if unpaired:
        # Store unpaired info so collect_data can add to diagnostics
        results.append({"_unpaired": unpaired})
    return results


# Fields shown in the Perf tab op_summary detail panel (user-configurable)
# 根据算子类型（Task Type）动态选择显示字段
OP_SUMMARY_FIELDS_BY_TYPE = {
    "vector": [
        "OP Type",
        "OP State",
        "Task Type",
        "Task Duration(us)",
        "Block Dim",
        "Input Shapes",
        "Input Data Types",
        "Input Formats",
        "Output Shapes",
        "Output Data Types",
        "Output Formats",
        "aiv_time(us)",
        "aiv_total_cycles",
        "aiv_vec_time(us)",
        "aiv_vec_ratio",
        "aiv_scalar_time(us)",
        "aiv_scalar_ratio",
        "aiv_mte2_time(us)",
        "aiv_mte2_ratio",
        "aiv_mte3_time(us)",
        "aiv_mte3_ratio",
        "aiv_icache_miss_rate",
    ],
    "cube": [
        "OP Type",
        "OP State",
        "Task Type",
        "Task Duration(us)",
        "Block Dim",
        "Input Shapes",
        "Input Data Types",
        "Input Formats",
        "Output Shapes",
        "Output Data Types",
        "Output Formats",
        "aicore_time(us)",
        "aic_total_cycles",
        "aic_mac_time(us)",
        "aic_mac_ratio",
        "aic_scalar_time(us)",
        "aic_scalar_ratio",
        "aic_mte1_time(us)",
        "aic_mte1_ratio",
        "aic_mte2_time(us)",
        "aic_mte2_ratio",
        "aic_fixpipe_time(us)",
        "aic_fixpipe_ratio",
        "aic_icache_miss_rate",
        "cube_utilization(%)",
    ],
}

# 向后兼容：默认显示所有字段（用于未指定类型时的降级处理）
# 展开为显式循环：去重并保序，避免循环变量泄漏到模块作用域（被内层函数局部变量遮蔽）


def _all_op_summary_fields() -> list:
    seen = {}
    for _type_fields in OP_SUMMARY_FIELDS_BY_TYPE.values():
        for _field in _type_fields:
            seen[_field] = None  # dict 保序去重
    return list(seen)


OP_SUMMARY_DISPLAY_FIELDS = _all_op_summary_fields()
_OP_SUM_STRING_FIELDS = {
    "Input Shapes",
    "Input Data Types",
    "Input Formats",
    "Output Shapes",
    "Output Data Types",
    "Block Dim",
    "Mix Block Dim",
    "OP Type",
    "Op Name",
    "Task Type",
}


class _SummaryAcc(NamedTuple):
    """op_summary 明细的聚合中间结果：数值字段求和/计数，字符串字段取首值。"""

    sums: dict
    counts: dict
    strings: dict


def _row_matches_op(row: dict, op_col, op_name: str) -> bool:
    """行是否属于目标算子；未给出列名或算子名时视为匹配。"""
    if not op_col or not op_name:
        return True
    return op_name.lower() in row.get(op_col, "").strip().lower()


def _fields_for_task_type(task_type: str) -> list:
    """根据 Task Type 选择字段列表。"""
    if "AI_VECTOR" in task_type:
        return OP_SUMMARY_FIELDS_BY_TYPE.get("vector", OP_SUMMARY_DISPLAY_FIELDS)
    if "AIC" in task_type or "AI_CORE" in task_type:
        return OP_SUMMARY_FIELDS_BY_TYPE.get("cube", OP_SUMMARY_DISPLAY_FIELDS)
    return OP_SUMMARY_DISPLAY_FIELDS


def _detect_display_fields(txt: str, op_name: str) -> list:
    """先读取 CSV 检测 Task Type，再据此选择展示字段列表。"""
    detected_task_type = None
    try:
        reader = csv.DictReader(io.StringIO(txt))
        raw_headers = list(reader.fieldnames or [])
        hmap = {h.strip(): h for h in raw_headers}
        task_type_col = hmap.get("Task Type")
        # 从匹配的行中获取 Task Type
        op_col = next((h for h in raw_headers if h.strip() in ("Op Name",)), None)
        for row in reader:
            if not _row_matches_op(row, op_col, op_name):
                continue
            if task_type_col:
                detected_task_type = row.get(task_type_col, "").strip()
                break
    except Exception:
        return OP_SUMMARY_DISPLAY_FIELDS
    return (
        _fields_for_task_type(detected_task_type)
        if detected_task_type
        else OP_SUMMARY_DISPLAY_FIELDS
    )


def _accumulate_field(acc: _SummaryAcc, field: str, val_str: str) -> None:
    """把一个字段值并入聚合结果：字符串字段取首个非空值，数值字段累加。"""
    if field in _OP_SUM_STRING_FIELDS:
        acc.strings.setdefault(field, val_str.strip('"'))
        return
    try:
        val = float(val_str)
    except ValueError:
        acc.strings.setdefault(field, val_str)
        return
    acc.sums[field] = acc.sums.get(field, 0.0) + val
    acc.counts[field] = acc.counts.get(field, 0) + 1


def _accumulate_row(
    acc: _SummaryAcc, row: dict, active_fields: list, hmap: dict
) -> None:
    """把一行 CSV 中的所有关注字段并入聚合结果。"""
    for field in active_fields:
        h_orig = hmap.get(field)
        if h_orig is None:
            continue
        val_str = row.get(h_orig, "").strip()
        if val_str:
            _accumulate_field(acc, field, val_str)


def parse_op_summary_detail(
    csv_path: Path, op_name: str, display_fields: list = None
) -> dict:
    """
    从 op_summary_custom_fn_<case>.csv 提取目标算子的关键性能字段（取匹配行均值）。
    - 数值字段：取所有匹配行的均值（跳过 warmup 首行）
    - 字符串字段（Input Shapes / Input Data Types / Block Dim）：取首个非空值
    - 根据 Task Type 自动选择合适的字段列表（vector/cube）
    """
    txt = _read(csv_path)
    if not txt:
        return {}

    # 如果没有指定 display_fields，尝试从 CSV 中检测 Task Type 来选择合适的字段列表
    if display_fields is None:
        display_fields = _detect_display_fields(txt, op_name)

    active_fields = display_fields or OP_SUMMARY_DISPLAY_FIELDS
    acc = _SummaryAcc(sums={}, counts={}, strings={})
    try:
        reader = csv.DictReader(io.StringIO(txt))
        raw_headers = list(reader.fieldnames or [])
        # Strip whitespace from headers for lookup
        hmap = {h.strip(): h for h in raw_headers}
        # Filter: Op Name must contain op_name
        op_col = next((h for h in raw_headers if h.strip() in ("Op Name",)), None)
        for row in reader:
            if _row_matches_op(row, op_col, op_name):
                _accumulate_row(acc, row, active_fields, hmap)
    except Exception as e:
        logger.debug("解析 op_summary 明细失败，返回已聚合字段: %s", e)

    result = dict(acc.strings)
    for field, total in acc.sums.items():
        cnt = acc.counts[field]
        result[field] = round(total / cnt, 4) if cnt > 0 else 0.0
    return result


def parse_profiling_report_txt(path) -> dict:
    """解析 profiling/report.txt（单 case）"""
    txt = _read(path)
    result = {}
    m = re.search(r"Reference time\s*:\s*([\d.]+)\s*us", txt)
    if m:
        result["ref_time_us"] = float(m.group(1))
    m = re.search(r"Custom time\s*:\s*([\d.]+)\s*us", txt)
    if m:
        result["custom_time_us"] = float(m.group(1))
    m = re.search(r"Speedup\s*:\s*([\d.]+)x", txt)
    if m:
        result["speedup"] = float(m.group(1))
    return result


def pair_profiling_dirs(profiling_dir: Path) -> list:
    """
    按时间戳排序，将 Model_* 与 ModelNew_* 两两配对。
    返回 [(model_dir, modelnew_dir), ...] 按时间戳从旧到新。
    """
    if not profiling_dir or not Path(profiling_dir).is_dir():
        return []
    pdir = Path(profiling_dir)

    def _is_model_dir(d) -> bool:
        return (
            d.is_dir()
            and d.name.startswith("Model_device")
            and not d.name.startswith("ModelNew")
        )

    models = sorted([d for d in pdir.iterdir() if _is_model_dir(d)])
    modelnews = sorted(
        [
            d
            for d in pdir.iterdir()
            if d.is_dir() and d.name.startswith("ModelNew_device")
        ]
    )
    pairs = list(zip(models, modelnews))
    return pairs


def _sum_duration_column(csv_file: Path) -> float:
    """Total of the Duration column in one op_summary CSV, 0.0 when unusable."""
    txt = csv_file.read_text(encoding="utf-8", errors="replace")
    lines = [
        line for line in txt.splitlines() if line.strip() and not line.startswith("#")
    ]
    if not lines:
        return 0.0
    rows = csv.reader(lines)
    headers = [h.strip() for h in next(rows)]
    dur_col = next((i for i, h in enumerate(headers) if "Duration" in h), None)
    if dur_col is None:
        return 0.0
    total = 0.0
    for parts in rows:
        if len(parts) <= dur_col:
            continue
        try:
            total += float(parts[dur_col].strip())
        except ValueError:
            pass
    return total


def extract_profiling_time(prof_dir: Path) -> float:
    """从 profiling dir 的 op_summary CSV 提取总 task duration (us)"""
    if not prof_dir or not prof_dir.is_dir():
        return 0.0
    for csv_file in sorted(prof_dir.rglob("op_summary*.csv")):
        try:
            total = _sum_duration_column(csv_file)
        except Exception as e:
            logger.debug(
                "读取 profiling op_summary CSV 失败，已跳过 %s: %s", csv_file, e
            )
            continue
        if total > 0:
            return total
    return 0.0


def _dsl_header_comments(txt: str) -> list:
    """Leading comment block of a DSL file, as plain text lines."""
    algo_lines, in_comment = [], False
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("#"):
            in_comment = True
            c = s.lstrip("# ").strip()
            if c:
                algo_lines.append(c)
        elif in_comment and algo_lines:
            break
    return algo_lines


def _dsl_compute_steps(txt: str) -> list:
    """Comment lines found inside `with tl.compute():` blocks."""
    compute_steps = []
    in_compute = False
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("with tl.compute():"):
            in_compute = True
            continue
        if not in_compute:
            continue
        dedented = bool(s) and not line.startswith((" ", "\t"))
        if s.startswith("with ") or dedented:
            in_compute = False
            continue
        # Pick up comment lines inside compute block
        if s.startswith("# ") and s[2:].strip():
            compute_steps.append(s[2:].strip())
    return compute_steps


def parse_dsl(path) -> dict:
    txt = _read(path)
    if not txt:
        return {}
    return {
        "header_comments": _dsl_header_comments(txt)[:20],
        "compute_steps": _dsl_compute_steps(txt),
    }


# 搬运类 / dispatch 类 / 跨核同步类 API，不属于计算逻辑，扫描时跳过
_SKIP_APIS = {
    "DataCopy",
    "DataCopyPad",
    "DeQue",
    "AllocTensor",
    "EnQue",
    "FreeTensor",
    "Get",
    "SetGlobalBuffer",
    "InitBuffer",
    "set_atomic_none",
    # dispatch/loop-control（属于任务分配，不是计算逻辑）
    "GetBlockIdx",
    "GetBlockNum",
    "GetSubBlockIdx",
    "GetSubBlockNum",
    # CV cross-core sync（属于流水线协同，不是计算逻辑）
    "CrossCoreSetFlag",
    "CrossCoreWaitFlag",
}

# 已知 AscendC compute API 列表（用于支持 using namespace AscendC; 无前缀调用）
# Use a list (not set) so iteration order is deterministic and matches source order.
_KNOWN_APIS = [
    "Muls",
    "Adds",
    "Mul",
    "Add",
    "Sub",
    "Div",
    "Exp",
    "Log",
    "Sqrt",
    "Rec",
    "Abs",
    "Neg",
    "Max",
    "Min",
    "Relu",
    "Sigmoid",
    "Tanh",
    "Cast",
    "ReduceSum",
    "ReduceMax",
    "ReduceMean",
    "ArgMax",
    "Transpose",
    "Broadcast",
    "Gather",
    "Scatter",
    "Matmul",
    "BatchMatmul",
    "Softmax",
    "LayerNorm",
    "Copy",
    "SetValue",
    "Concat",
    "Split",
]

# Compute*() / Process() 方法头（支持 Compute1/Compute2/ComputeRem 等拆分写法）
_COMPUTE_HEADER_RE = re.compile(
    r"(?:__aicore__\s+inline\s+)?void\s+(Compute\w*|Process)\s*\([^)]*\)"
)


def _brace_body(txt: str, header_end: int) -> str | None:
    """从 header_end 后找到第一个 '{', 然后用括号深度计数提取完整函数体。
    正确处理函数内嵌套的 if/for/while 块，避免正则在第一个 '}' 处截断。"""
    start = txt.find("{", header_end)
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(txt)):
        if txt[i] == "{":
            depth += 1
            continue
        if txt[i] != "}":
            continue
        depth -= 1
        if depth == 0:
            body_start = start + 1
            return txt[body_start:i]
    return None


def _paren_args(txt: str, paren_pos: int) -> str:
    """从 '(' 处起，用括号深度计数提取配对括号内的参数字符串（不含外层括号）。
    修复 ([^;]*) 贪婪匹配跨行代码的问题（如 GetBlockNum() 后紧跟 { ... ; }）。"""
    depth = 0
    for i in range(paren_pos, len(txt)):
        if txt[i] == "(":
            depth += 1
            continue
        if txt[i] != ")":
            continue
        depth -= 1
        if depth == 0:
            args_start = paren_pos + 1
            return txt[args_start:i]
    args_start = paren_pos + 1
    return txt[args_start:]  # unbalanced — return remainder


def _compute_method_bodies(kernel_txt: str) -> str | None:
    """合并所有 Compute*() / Process() 方法体，没有命中则返回 None。"""
    bodies = []
    for m in _COMPUTE_HEADER_RE.finditer(kernel_txt):
        body = _brace_body(kernel_txt, m.end())
        if body:
            bodies.append(body)
    return "\n".join(bodies) if bodies else None


def _call_entry(compute_body: str, call_m, api_name: str) -> tuple:
    """把一次调用整理成 (起始位置, API 名, 前 4 个实参)。"""
    args_txt = _paren_args(compute_body, call_m.end() - 1)
    return call_m.start(), api_name, [a.strip() for a in args_txt.split(",")][:4]


def _scan_prefixed_calls(compute_body: str, seen_apis: set) -> list:
    """匹配带前缀的调用 AscendC::XXX(...)。
    用 _paren_args 替代 ([^;]*) 以精确提取平衡括号内的参数，避免捕获闭合括号或跨行代码。"""
    found = []
    for call_m in re.finditer(r"AscendC::(\w+)\s*\(", compute_body):
        api_name = call_m.group(1)
        if api_name in _SKIP_APIS:
            continue
        seen_apis.add(api_name)
        found.append(_call_entry(compute_body, call_m, api_name))
    return found


def _scan_bare_calls(compute_body: str, seen_apis: set) -> list:
    """扫描无前缀的已知 API（支持混用 AscendC::Foo 与 Bar，以及 using namespace）。
    避免误匹配：要求函数名在已知列表中，且前面不是 :: 或 . 成员访问。每个 API 只记录一次出现。"""
    found = []
    for api_name in _KNOWN_APIS:
        if api_name in _SKIP_APIS or api_name in seen_apis:
            continue
        call_m = re.search(rf"(?<![:\.\w]){re.escape(api_name)}\s*\(", compute_body)
        if not call_m:
            continue
        found.append(_call_entry(compute_body, call_m, api_name))
        seen_apis.add(api_name)
    return found


def extract_kernel_compute_apis(kernel_txt: str) -> list:
    """
    从 kernel 源码的 Compute() 方法体中直接提取 AscendC API 调用序列。

    对显式前缀调用（如 `AscendC::Foo(...)`）不依赖任何预设 API 列表，AscendC 升级后会自动适配；
    对无前缀调用（如 `Foo(...)`，通常来自 `using namespace AscendC;`）会回退到 `_KNOWN_APIS`
    做名称匹配，因此可能无法覆盖未来新增但未同步进列表的 API。
    返回格式: [{"api": "Muls", "args": ["expLocal", "xLocal", "-1.702f", "tileSize"]}]
    """
    if not kernel_txt:
        return []

    compute_body = _compute_method_bodies(kernel_txt)
    if compute_body is None:
        return []

    # Collect all calls with their source position so we can merge and sort by appearance.
    seen_apis: set[str] = set()
    calls = _scan_prefixed_calls(compute_body, seen_apis)
    calls += _scan_bare_calls(compute_body, seen_apis)

    # Sort by source position so algo_flow reflects actual Compute() call order
    return [{"api": n, "args": a} for _, n, a in sorted(calls, key=lambda x: x[0])]


# rhs 以这些前缀开头时直接对应的 AscendC API
_API_PREFIXES = (
    ("exp(", "Exp"),
    ("sqrt(", "Sqrt"),
    ("tanh(", "Tanh"),
    ("ln(", "Ln"),
    ("log(", "Ln"),
    ("reducemax(", "ReduceMax"),
    ("reducemin(", "ReduceMin"),
    ("reducesum(", "ReduceSum"),
    ("max(", "Maxs"),
    ("min(", "Mins"),
)
# 整段描述中出现这些词时对应的 AscendC API
_API_PATTERNS = (
    (r"\bmuls\b", "Muls"),
    (r"\badds\b", "Adds"),
    (r"\bdivs?\b", "Div"),
    (r"\bsubs\b", "Sub"),
    (r"\bmaxs\b|\bvmax\b", "Maxs"),
    (r"\bmins\b|\bvmin\b", "Mins"),
    (r"\breducesum\b", "ReduceSum"),
    (r"\breducemax\b", "ReduceMax"),
    (r"\breducemin\b", "ReduceMin"),
    (r"\bexp\b", "Exp"),
)
# 最外层运算符到 AscendC API 的优先级顺序
_OPERATOR_APIS = (("/", "Div"), ("+", "Adds"), ("-", "Sub"), ("*", "Muls"))


def _top_level_operators(rhs: str) -> set:
    """扫描 rhs 中位于括号外层的四则运算符，不被 exp() 等子式误导。"""
    found = set()
    depth = 0
    for i, c in enumerate(rhs):
        if c == "(":
            depth += 1
            continue
        if c == ")":
            depth -= 1
            continue
        if depth != 0:
            continue
        # 负号只有在前一个字符不是数字时才算减法（排除 -1.0 这类字面量）
        if c == "-" and (i == 0 or rhs[i - 1] in "0123456789"):
            continue
        if c in "+-*/":
            found.add(c)
    return found


def _infer_api_from_desc(desc: str) -> str:
    """从步骤描述推断 AscendC API 名（fallback，用于 DSL/注释来源）。
    识别最外层运算符，不被 exp() 子式误导。"""
    m = re.search(r"=\s*(.+)$", desc)
    rhs = m.group(1).strip() if m else desc

    ops = _top_level_operators(rhs)
    for op, api in _OPERATOR_APIS:
        if op in ops:
            return api

    rhs_l = rhs.lower().lstrip()
    for prefix, api in _API_PREFIXES:
        if rhs_l.startswith(prefix):
            return api

    for pat, api in _API_PATTERNS:
        if re.search(pat, desc, re.I):
            return api
    return "Compute"


def _make_api_formula(api: str, raw_desc: str) -> str:
    """生成 AscendC API 调用形式的 formula（fallback 路径）。"""
    floats = re.findall(r"-?\d+\.\d+", raw_desc)
    scalar = floats[0] if floats else ""
    if not scalar:
        ints = re.findall(r"\b\d{2,}\b", raw_desc)
        scalar = ints[0] if ints else ""
    t = {
        "Muls": f"tmp = Muls(x, {scalar})" if scalar else "tmp = Muls(x, α)",
        "Exp": "e   = Exp(tmp)",
        "Adds": f"d   = Adds(e, {scalar})" if scalar else "d   = Adds(e, 1)",
        "Div": "y   = Div(x, d)",
        "Sub": "tmp = Sub(a, b)",
        "Add": "out = Add(a, b)",
        "Mul": "out = Mul(a, b)",
        "Maxs": f"out = Maxs(x, {scalar})" if scalar else "out = Maxs(x, 0)",
        "Mins": f"out = Mins(x, {scalar})" if scalar else "out = Mins(x, 0)",
        "ReduceSum": "s = ReduceSum(x, work)",
        "ReduceMax": "m = ReduceMax(x, work)",
        "ReduceMin": "m = ReduceMin(x, work)",
        "Sqrt": "out = Sqrt(x)",
        "Tanh": "out = Tanh(x)",
        "Ln": "out = Ln(x)",
        "Compute": "out = Compute(x)",
    }
    return t.get(api, f"out = {api}(x)")


def _api_call_scalar(args: list) -> str:
    """从单个 call 的实参里取第一个浮点常量，没有则返回空串。"""
    for arg in args:
        # 去掉 f 后缀，匹配浮点或多位整数
        fm = re.search(r"-?\d+\.\d+", arg.strip().rstrip("f"))
        if fm:
            return fm.group(0)
    return ""


def _api_call_var(s: str) -> str:
    """清理变量名：去 this-> 前缀与 Local/Buf/_ub 后缀，使其简洁。"""
    s = re.sub(r"\bthis->", "", s).strip().rstrip("f").strip()  # 仅去前缀，保留字段名
    s = re.sub(r"(?i)(local|buf|_ub|_tensor|local_)$", "", s.strip())
    return s.strip() or "tmp"


def _api_call_formula(api: str, args: list, scalar: str) -> str:
    """按实参个数与标量常量拼出该调用的展示公式。"""
    dst = _api_call_var(args[0]) if len(args) > 0 else "out"
    src = _api_call_var(args[1]) if len(args) > 1 else "x"
    src2 = _api_call_var(args[2]) if len(args) > 2 else ""
    if scalar:
        return f"{dst} = {api}({src}, {scalar})"
    # 二元无标量 API（Div, Add, Sub, Mul）：显示两个操作数
    _binary = {"Div", "Add", "Sub", "Mul", "ReduceSum", "ReduceMax", "ReduceMin"}
    # src2 是否为有效的第二操作数（排除 tiling 控制参数等非数据操作数）
    _src2_is_loop_param = src2.lower() in (
        "tilesize",
        "innerloops",
        "tailcount",
        "count",
        "size",
    )
    _has_second_operand = bool(src2) and src2 != src and not _src2_is_loop_param
    if api in _binary and _has_second_operand:
        return f"{dst} = {api}({src}, {src2})"
    return f"{dst} = {api}({src})"


def _build_nodes_from_api_calls(api_calls: list, dsl_steps: list) -> list:
    """
    从 extract_kernel_compute_apis() 的结果构建 nodes（主路径）。
    formula 直接来自真实 AscendC 调用参数，最可靠。
    """
    # _NO_SCALAR_APIS: 这些 API 不接受标量参数
    _no_scalar = {
        "Exp",
        "Sqrt",
        "Tanh",
        "Ln",
        "Log",
        "ReduceSum",
        "ReduceMax",
        "ReduceMin",
        "Div",
        "Add",
        "Sub",
        "Mul",
        "DataCopy",
        "DataCopyPad",
    }

    nodes = []
    for call in api_calls[:8]:
        api = call.get("api", "Compute")
        args = call.get("args", [])
        # 仅从当前 call 的 args 提取常量（不跨 call 引用）
        scalar = "" if api in _no_scalar else _api_call_scalar(args)
        nodes.append(
            {
                "api": api,
                "formula": _api_call_formula(api, args, scalar),
                "in_tmpl": "{N}",
                "out_tmpl": "{N}",
            }
        )
    return nodes


def _is_dsl_compute_step(step: str) -> bool:
    """DSL compute_steps 中真正表示计算的行（排除分隔线与纯搬运）。"""
    return (
        not re.match(r"^-{3,}$", step)
        and not re.match(r"^(COPYOUT|COPYIN)", step, re.I)
        and "=" in step
        and len(step) > 5
    )


def _kernel_formula_steps(kernel_txt: str) -> list:
    """来源 3: kernel step 注释公式行，按步骤号排序并去重。"""
    step_re = re.compile(r"//\s*step\s*(\d+)\s*[:\-]\s*(.+)", re.IGNORECASE)
    step_map = {}
    for m in step_re.finditer(kernel_txt):
        n, desc = int(m.group(1)), m.group(2).strip()
        if n not in step_map:
            step_map[n] = desc
    return [step_map[n] for n in sorted(step_map)]


def _pass_comment_titles(kernel_data: dict) -> list:
    """来源 4: pass_comments 标题（fallback）。"""
    titles = []
    for c in kernel_data.get("pass_comments", []):
        m = re.match(r"Step\s*\d+\s*:\s*(.+?)(?:\s*[—–]\s*.+)?$", c, re.IGNORECASE)
        if m:
            titles.append(m.group(1).strip())
    return titles


def _fallback_steps(dsl_steps: list, formula_steps: list, pass_titles: list) -> tuple:
    """Fallback：从 DSL/注释推断，返回 (步骤列表, 来源标识)；都没有时步骤列表为空。"""
    if dsl_steps:
        return dsl_steps, "dsl"
    if formula_steps:
        return formula_steps, "kernel_comments"
    if pass_titles:
        return pass_titles, "pass_titles"
    return [], ""


def _nodes_from_steps(raw_steps: list) -> list:
    """Fallback 路径下构建 nodes（来源：DSL/注释推断）。"""
    nodes = []
    for desc in raw_steps[:8]:
        api = _infer_api_from_desc(desc)
        nodes.append(
            {
                "api": api,
                "formula": _make_api_formula(api, desc),
                "in_tmpl": "{N}",
                "out_tmpl": "{N}",
            }
        )
    return nodes


def _algo_io_meta(op_desc: dict) -> dict:
    """── 从 op_desc 推导真实 IO 元信息（避免硬编码 float32/单维度） ──"""
    shape_info = (op_desc or {}).get("shape_info", {})
    inp_shapes = shape_info.get("input_shapes", [])
    out_shapes = shape_info.get("output_shapes", [])
    first_in = inp_shapes[0] if inp_shapes else {}
    first_out = out_shapes[0] if out_shapes else {}
    ndim = len(first_in.get("shape", [])) or 1
    svars = [f"S{i}" for i in range(ndim)] if ndim > 1 else ["N"]
    tmpl = "{" + ",".join(svars) + "}"
    return {
        "shape_vars": svars,
        "inp_name": first_in.get("name", "x"),
        "inp_tmpl": tmpl,
        "inp_dtype": first_in.get("dtype", "float32"),
        "out_name": first_out.get("name", "y"),
        "out_tmpl": tmpl,
        "out_dtype": first_out.get("dtype", "float32"),
    }


# ── 硬件单元元数据 ──
_UNIT_META = {
    "vector": {
        "id": "vector",
        "label": "Vector Core  Compute",
        "bg": "#f5f0ff",
        "accent": "#8250df",
    },
    "cube": {
        "id": "cube",
        "label": "Cube Core  MAC",
        "bg": "#fffbf0",
        "accent": "#bf8700",
    },
}


def auto_build_algo_flow(
    op_name: str,
    dsl_data: dict,
    kernel_data: dict,
    op_type: str = "vector",
    op_desc: dict = None,
) -> dict:
    """
    三层优先级构建 algo_flow.json：
    1. 直接从 kernel Compute() 提取 AscendC API 调用（最可靠，不依赖预设列表）
    2. 从 DSL compute_steps 推断（含数学运算符，适合 API 名映射）
    3. Fallback：从 pass_comments 提取标题

    algo_flow.json 增加 api_list 字段，记录实际调用的 AscendC 函数，自描述、可审计。
    op_desc 若提供，则用于填充真实 shape_vars / IO dtype，否则退化为 ["N"] / float32。
    """
    kernel_txt = kernel_data.get("_txt", "")

    # ══ 来源 1：直接从 kernel Compute() 提取 AscendC::XXX() 调用（最可靠）══
    # 不依赖预设 API 列表，AscendC 升级自动适应
    kernel_api_calls = extract_kernel_compute_apis(kernel_txt)
    # ── 来源 2: DSL compute_steps（含运算符，适合推断 API 名）──
    dsl_steps = [
        s for s in dsl_data.get("compute_steps", []) if _is_dsl_compute_step(s)
    ]

    # ══ 优先使用直接提取的 API 调用构建节点 ══
    use_source = "kernel_api"
    if kernel_api_calls:
        nodes = _build_nodes_from_api_calls(kernel_api_calls, dsl_steps)
    else:
        raw_steps, use_source = _fallback_steps(
            dsl_steps,
            _kernel_formula_steps(kernel_txt),
            _pass_comment_titles(kernel_data),
        )
        if not raw_steps:
            return {}
        nodes = _nodes_from_steps(raw_steps)

    if not nodes:
        return {}

    unit_meta = _UNIT_META.get(op_type, _UNIT_META["vector"])
    # ── 组装合规 algo_flow，包含 api_list 供审计 ──
    return {
        "op_name": op_name,
        "description": f"Auto-extracted ({use_source}, {len(nodes)} ops)",
        "_auto": True,
        **_algo_io_meta(op_desc),
        # 实际调用的 AscendC API，可审计、不依赖预设列表
        "api_list": list(
            dict.fromkeys(n["api"] for n in nodes if n["api"] != "Compute")
        ),
        "units": [
            {
                "id": unit_meta["id"],
                "label": unit_meta["label"],
                "bg": unit_meta["bg"],
                "accent": unit_meta["accent"],
                "nodes": nodes,
            }
        ],
    }


# 匹配多种 step/pass/phase 注释格式（大小写不敏感），包括：
#   // Step N: desc              // Pass N: desc        // Phase N: desc
#   // ---- Step N: desc ----   // ── Step N: desc ──  // Phase N (ctx): desc
#   // A5: Step N - desc        // Stage N: desc
_STEP_COMMENT_PAT = re.compile(
    r"^[ \t]*//\s*"  # 行首注释，允许任意缩进（重复步骤号通过 seen 去重）
    r"[-\u2500-\u257F=\s]*"  # 可选前置装饰符（ASCII/Unicode box-drawing）
    r"(?:A5:\s*)?"  # 可选 A5: 前缀
    r"(?:Pass|Step|Phase|Stage)\s*"  # 关键字
    r"(\d+)"  # 步骤编号
    r"(?:\s*[\(\uff08][^\uff09)]*[\)\uff09])?"  # 可选括号内上下文，如 (AIC+AIV)
    r"\s*[-:：\u2500-\u257F\s]+"  # 分隔符（冒号/横线/空格组合）
    r"([\w\u4e00-\u9fff].{1,})",  # 描述文本（字母/汉字开头，至少2字符）
    re.IGNORECASE,
)
_STEP_CONT_PAT = re.compile(r"^\s*//\s*(?!step\s*\d|pass\s*\d)(.+)", re.IGNORECASE)
# TQue/TBuf 声明中的位置枚举——支持可选 AscendC:: 前缀与 QuePosition 别名
_TPOS = r"(?:(?:AscendC::)?(?:TPosition|QuePosition))"
_SHAPE_DIM_NAMES = ["M", "N", "K", "D", "E"]


def _parse_kernel_buffers(txt: str, buffer_num: int) -> list:
    """收集 kernel 中声明的 TQue / TBuf。"""
    buffers = []
    # TQue with BUFFER_NUM variable
    for m in re.finditer(
        rf"(?:AscendC::)?TQue<{_TPOS}::(\w+),\s*BUFFER_NUM>\s*(\w+)\s*;", txt
    ):
        buffers.append(
            {
                "name": m.group(2),
                "kind": "TQue",
                "position": m.group(1),
                "multiplier": buffer_num,
            }
        )
    # TQue with literal integer (CAKE2 format: TQue<..., 1> inQueue;)
    for m in re.finditer(
        rf"(?:AscendC::)?TQue<{_TPOS}::(\w+),\s*(\d+)>\s*(\w+)\s*;", txt
    ):
        buffers.append(
            {
                "name": m.group(3),
                "kind": "TQue",
                "position": m.group(1),
                "multiplier": int(m.group(2)),
            }
        )
    # TBuf
    for m in re.finditer(rf"(?:AscendC::)?TBuf<{_TPOS}::(\w+)>\s*(\w+)\s*;", txt):
        buffers.append(
            {
                "name": m.group(2),
                "kind": "TBuf",
                "position": m.group(1),
                "multiplier": 1,
            }
        )
    return buffers


def _step_comment_detail(lines: list, i: int) -> str:
    """尝试读取紧随的解释行（最多 1 行）。"""
    if i + 1 >= len(lines):
        return ""
    cm = _STEP_CONT_PAT.match(lines[i + 1])
    return cm.group(1).strip() if cm else ""


def _parse_pass_comments(txt: str) -> list:
    """从 kernel 注释中提取 Step/Pass/Phase 流程说明，按步骤号去重。"""
    pass_comments = []
    seen_step_nums = set()
    lines = txt.splitlines()
    for i, line in enumerate(lines):
        m = _STEP_COMMENT_PAT.match(line)
        if not m:
            continue
        step_num = m.group(1)
        if step_num in seen_step_nums:
            continue
        seen_step_nums.add(step_num)
        # Strip trailing decorators (ASCII dashes, Unicode box-drawing, spaces)
        title = re.sub(r"[\s\-\u2500-\u257F]+$", "", m.group(2)).strip()
        detail = _step_comment_detail(lines, i)
        # 组合：标题 + 解释（用空格分隔，保持单行显示）
        full = (
            f"Step {step_num}: {title} — {detail}"
            if detail
            else f"Step {step_num}: {title}"
        )
        if len(full) > 5:
            pass_comments.append(full)
    return pass_comments


def _parse_shape_typedefs(txt: str, consts: dict) -> None:
    """Pass 2: template shape typedefs  using L1Shape = GemmShape<128, 256, 512>"""
    for m in re.finditer(r"using\s+(\w+)\s*=\s*\w*Shape\s*<\s*([\d,\s]+)\s*>", txt):
        tname = m.group(1)
        vals = [int(x.strip()) for x in m.group(2).split(",")]
        for i, v in enumerate(vals[: len(_SHAPE_DIM_NAMES)]):
            # Store as both "L1Shape_N" and "L1Shape::N" for resolution
            consts[f"{tname}_{_SHAPE_DIM_NAMES[i]}"] = v
            consts[f"{tname}::{_SHAPE_DIM_NAMES[i]}"] = v


def _parse_kernel_constants(txt: str) -> dict:
    """── Constant extraction ──"""
    consts = {}
    # Pass 1: constexpr declarations whose value is a plain integer literal
    for m in re.finditer(r"constexpr\s+\w+\s+(\w+)\s*=\s*(\d+)\s*;", txt):
        consts[m.group(1)] = int(m.group(2))
    _parse_shape_typedefs(txt, consts)
    # Pass 3: compound constexpr (evaluate using known constants, multi-pass)
    for _ in range(3):
        _resolve_compound_constants(txt, consts)
    return consts


def _resolve_compound_constants(txt: str, consts: dict) -> None:
    """用已知常量求值尚未解析的 constexpr 表达式。"""
    for m in re.finditer(r"constexpr\s+\w+\s+(\w+)\s*=\s*([^;{]+?)\s*;", txt):
        name, expr = m.group(1), m.group(2).strip()
        if name in consts:
            continue
        val = _eval_size_expr(expr, consts)
        if val > 0:
            consts[name] = val


def parse_kernel_cpp(path) -> dict:
    txt = _read(path)
    if not txt:
        return {}
    m = re.search(r"BUFFER_NUM\s*=\s*(\d+)", txt)
    buffer_num = int(m.group(1)) if m else 1
    return {
        "buffer_num": buffer_num,
        "buffers": _parse_kernel_buffers(txt, buffer_num),
        "tiling_params": list(dict.fromkeys(re.findall(r"tiling_data\.(\w+)", txt))),
        "pass_comments": _parse_pass_comments(txt)[:20],
        "constants": _parse_kernel_constants(txt),
        "_txt": txt,
    }


def _extract_tiling_body(txt: str) -> str:
    """提取 TilingFunc 完整函数体（括号深度计数，避免被内层 if/for 截断）。"""
    sig_match = re.search(r"ge::graphStatus\s+\w*TilingFunc\w*\s*\([^)]*\)\s*\{", txt)
    if not sig_match:
        return ""
    start = sig_match.end() - 1
    depth = 0
    for i in range(start, len(txt)):
        if txt[i] == "{":
            depth += 1
        elif txt[i] == "}":
            depth -= 1
            if depth == 0:
                body_start = start + 1
                return txt[body_start:i]
    return ""


def _collect_tiling_locals(tiling_body: str, consts: dict) -> None:
    """Record local uint assignments in the tiling body.

    Values may be literals or references to constants already known. Two passes
    resolve forward dependencies between them.
    """
    for _ in range(2):
        _resolve_tiling_locals_once(tiling_body, consts)


def _resolve_tiling_locals_once(tiling_body: str, consts: dict) -> None:
    """One resolution pass over the local uint assignments."""
    for m in re.finditer(r"uint\d+_t\s+(\w+)\s*=\s*([^;]+);", tiling_body):
        var, rhs = m.group(1), m.group(2).strip()
        if var in consts:
            continue
        if re.fullmatch(r"\d+", rhs):
            consts[var] = int(rhs)
            continue
        if rhs in consts:
            # A constant assigned from another known constant inherits its value.
            consts[var] = consts[rhs]


def _collect_tiling_setters(tiling_body: str, consts: dict) -> None:
    """Map tiling setter field names onto known constant values.

    This lets the kernel side resolve expressions such as a tile size multiplied
    by an element width.
    """
    for m in re.finditer(r"tiling\.set_(\w+)\s*\(\s*([^)]+?)\s*\)", tiling_body):
        field, expr = m.group(1), m.group(2).strip()
        if expr in consts:
            consts[field] = consts[expr]
        elif re.fullmatch(r"\d+", expr):
            consts[field] = int(expr)


def parse_op_host_cpp(path) -> dict:
    """从 op_host/*.cpp 提取 constexpr/const/局部变量 tile 常量（L1_M/L1_N/L1_K/WORKSPACE_STAGES/BLOCK_DIM/tileSize 等）。

    额外解析 tiling.set_<field>(<expr>) 调用，将 tiling 结构体字段名
    （如 tileSize、nUsed）也加入常量表。这样 kernel 的 InitBuffer 表达式
    "tileSize * sizeof(float)" 就能用 op_host 的 TILE_SIZE 常量正确求值，
    避免因名称不匹配导致的 UB 溢出误报。
    """
    txt = _read(path)
    if not txt:
        return {"constants": {}, "tiling_body": ""}
    consts = {}
    # constexpr 常量
    for m in re.finditer(r"constexpr\s+\w+\s+(\w+)\s*=\s*(\d+)\s*;", txt):
        consts[m.group(1)] = int(m.group(2))
    # const 常量（CAKE2 格式：const uint32_t BLOCK_DIM = 16;）
    for m in re.finditer(r"const\s+\w+\s+(\w+)\s*=\s*(\d+)\s*;", txt):
        consts[m.group(1)] = int(m.group(2))
    # 提取 TilingFunc 函数体
    tiling_body = _extract_tiling_body(txt)
    if tiling_body:
        _collect_tiling_locals(tiling_body, consts)
        _collect_tiling_setters(tiling_body, consts)
    return {"constants": consts, "tiling_body": tiling_body}


# sizeof lookup for InitBuffer expression evaluation
_SIZEOF = {
    "char": 1,
    "int8_t": 1,
    "uint8_t": 1,
    "int8": 1,
    "short": 2,
    "int16_t": 2,
    "uint16_t": 2,
    "int16": 2,
    "half": 2,
    "float16_t": 2,
    "__fp16": 2,
    "int": 4,
    "int32_t": 4,
    "uint32_t": 4,
    "int32": 4,
    "float": 4,
    "float32_t": 4,
    "double": 8,
    "int64_t": 8,
    "float64_t": 8,
    # Template type aliases
    "ElementA": 1,
    "ElementB": 1,
    "ElementC": 4,
    "ElementD": 2,
}


def _eval_size_expr(expr: str, consts: dict) -> int:
    """Evaluate simple InitBuffer size expression like 'tileElements * sizeof(float)'."""
    # Replace sizeof(type) → integer
    expr2 = re.sub(
        r"sizeof\s*\(\s*(\w+)\s*\)", lambda m: str(_SIZEOF.get(m.group(1), 4)), expr
    )
    # Replace TYPE::MEMBER constants first (longest key first to avoid partial match)
    for k, v in sorted(consts.items(), key=lambda x: -len(x[0])):
        if "::" in k:
            expr2 = expr2.replace(k, str(v))
    # Replace simple identifier constants
    for k, v in sorted(consts.items(), key=lambda x: -len(x[0])):
        if "::" not in k:
            expr2 = re.sub(r"\b" + re.escape(k) + r"\b", str(v), expr2)
    # Only evaluate pure arithmetic
    try:
        if re.fullmatch(r"[\d\s\*\+\-\/\(\)]+", expr2.strip()):
            return int(eval(expr2))
    except Exception as e:
        logger.debug("size 表达式求值失败，返回 0 (%r): %s", expr, e)
    return 0


def _absorb_assignments(
    pattern: str, kernel_txt: str, ext: dict, flags: int = 0
) -> None:
    """Add every assignment matching `pattern` whose value can be evaluated."""
    for m in re.finditer(pattern, kernel_txt, flags):
        var, rhs = m.group(1), m.group(2).strip()
        if var in ext:
            continue
        v = _eval_size_expr(rhs, ext)
        if v > 0:
            ext[var] = v


def parse_kernel_init_buffers(kernel_txt: str, consts: dict) -> dict:
    """
    解析 pipe.InitBuffer() 调用，返回 {buf_name: size_bytes}。
    支持两种形式：
      pipe.InitBuffer(bufName, count, sizeExpr);  — TQue（count 是整数字面量）
      pipe.InitBuffer(bufName, sizeExpr);          — TBuf

    在求值 sizeExpr 前，按以下三类扩展常量表（两轮前向引用）：
      1. 带类型前缀的局部变量声明：uint32_t x = expr;
      2. constexpr 类成员常量：static constexpr uint32_t CHUNK_M = L1Shape::M / VEC_NUM;
      3. 成员变量赋值（无类型前缀）：computeLength = CHUNK_M * L1Shape::N;
    """
    # 扩展常量表：先复制 consts，再追加 kernel 中可求值的常量/变量
    ext = dict(consts)
    # Pass 1a: 带类型前缀的局部变量声明（uint32_t x = expr; / int x = expr;）
    _absorb_assignments(
        r"\b(?:uint\d+_t|int|size_t)\s+(\w+)\s*=\s*([^;]+);", kernel_txt, ext
    )
    # Pass 1b: constexpr 类成员常量（static constexpr uint32_t CHUNK_M = L1Shape::M / VEC_NUM;）
    _absorb_assignments(
        r"\bconstexpr\s+\w[\w:]*\s+(\w+)\s*=\s*([^;]+);", kernel_txt, ext
    )
    # Pass 1c（两轮）: 成员变量赋值，无类型前缀（computeLength = CHUNK_M * L1Shape::N;）
    # 只匹配行首缩进后的 identifier = arithmetic_expr; 形式，避免匹配 if/for 等控制结构
    for _ in range(2):
        _absorb_assignments(
            r"^\s+(\w+)\s*=\s*([^=;{}\n][^;\n]*);", kernel_txt, ext, flags=re.MULTILINE
        )

    sizes = {}
    # TQue form: 3 args, 2nd is integer literal
    for m in re.finditer(
        r"pipe\.InitBuffer\s*\(\s*(\w+)\s*,\s*(\d+)\s*,\s*([^;]+?)\s*\)\s*;", kernel_txt
    ):
        buf, size_expr = m.group(1), m.group(3).strip()
        sizes[buf] = _eval_size_expr(size_expr, ext)
    # TBuf form: 2 args, 2nd is NOT an integer literal alone
    for m in re.finditer(
        r"pipe\.InitBuffer\s*\(\s*(\w+)\s*,\s*([^,;]+?)\s*\)\s*;", kernel_txt
    ):
        buf, size_expr = m.group(1), m.group(2).strip()
        if buf not in sizes and not re.fullmatch(r"\d+", size_expr):
            sizes[buf] = _eval_size_expr(size_expr, ext)
    return sizes


def compact_shape(shape_str: str, shape_vars=None) -> str:
    """Convert shape dict string to compact 'M=32 K=64 N=48' format."""
    kv = {}
    for m in re.finditer(r"'(\w+)':\s*(\d+)", str(shape_str)):
        kv[m.group(1)] = m.group(2)
    if not kv:
        return str(shape_str)
    if shape_vars:
        parts = [f"{k}={kv.get(k, '')}" for k in shape_vars if k in kv]
        extras = [f"{k}={v}" for k, v in kv.items() if k not in shape_vars]
        return " ".join(parts + extras[:2])
    return " ".join(f"{k}={v}" for k, v in list(kv.items())[:6])


# ─── UB BUFFER SIZES ──────────────────────────────────────────────────────────


def _parse_shape_dims(shape_str: str) -> dict:
    """从 shape 字符串解析命名维度：优先 dict 字面量，其次 NAME=数字 紧凑形式。"""
    kv = {
        m.group(1): int(m.group(2)) for m in re.finditer(r"'(\w+)':\s*(\d+)", shape_str)
    }
    if kv:
        return kv
    # Fall back to the compact form, where each dimension is named and
    # separated by spaces rather than quoted as a dict.
    return {
        m.group(1): int(m.group(2))
        for m in re.finditer(r"\b([A-Z]\w*)\s*=\s*(\d+)", shape_str)
    }


def _tile_balance_pct(total_tiles: int, aic_cores: int) -> int:
    """核间负载均衡率：整除为 100，否则按向上取整后的核占用折算。"""
    if total_tiles == 0:
        return 0
    if total_tiles % aic_cores == 0:
        return 100
    ceil_t = (total_tiles + aic_cores - 1) // aic_cores
    return round(total_tiles / (ceil_t * aic_cores) * 100)


def _case_tiling_row(
    case: dict, kv: dict, dim_str: str, tile_sizes: tuple, aic_cores: int
) -> dict:
    """对单个 case 计算 AIC tile 数、尾块标志与负载均衡率。"""
    l1_m, l1_n, l1_k = tile_sizes
    m_dim, n_dim, k_dim = kv.get("M", 0), kv.get("N", 0), kv.get("K", 0)
    tiles_m = ((m_dim + l1_m - 1) // l1_m) if l1_m and m_dim else None
    tiles_n = (n_dim + l1_n - 1) // l1_n
    tiles_k = ((k_dim + l1_k - 1) // l1_k) if l1_k and k_dim else None
    total_tiles = (tiles_m or 1) * tiles_n

    tail_m = bool(l1_m and m_dim and m_dim % l1_m != 0)
    tail_n = bool(n_dim % l1_n != 0)
    tail_k = bool(l1_k and k_dim and k_dim % l1_k != 0)

    return {
        "case_id": case.get("id", 0),
        "case_name": case.get("name", f"Case {case.get('id', 0)}"),
        "dim_str": dim_str,
        "M": m_dim,
        "N": n_dim,
        "K": k_dim,
        "tiles_m": tiles_m,
        "tiles_n": tiles_n,
        "tiles_k": tiles_k,
        "total_tiles": total_tiles,
        "tail_m": tail_m,
        "tail_n": tail_n,
        "tail_k": tail_k,
        "has_tail": tail_m or tail_n or tail_k,
        "tiles_per_core": round(total_tiles / aic_cores, 2),
        "balance_pct": _tile_balance_pct(total_tiles, aic_cores),
    }


def compute_tiling_analysis(
    cases: list, tiling_consts: dict, aic_cores: int = 32
) -> list:
    """
    对每个 test case 计算 tiling 指标：
    - 从 shape 字符串提取 M/K/N（支持 dict 格式 {'M':32,'K':64,'N':48,...}）
    - 计算 AIC tile 数、有无尾块、每核分配、负载均衡率
    返回 [{case_id, case_name, dims, tiles, tail, tiles_per_core, balance_pct}, ...]
    """
    # Resolve tile constants with fallbacks
    l1_m = (
        tiling_consts.get("L1_M")
        or tiling_consts.get("L1Shape_M")
        or tiling_consts.get("tile_m")
    )
    l1_n = (
        tiling_consts.get("L1_N")
        or tiling_consts.get("L1Shape_N")
        or tiling_consts.get("tile_n")
    )
    l1_k = (
        tiling_consts.get("L1_K")
        or tiling_consts.get("L1Shape_K")
        or tiling_consts.get("tile_k")
    )

    results = []
    for c in cases:
        kv = _parse_shape_dims(str(c.get("shape", "")))
        # Build dim string from available shape dims
        dim_parts = [(k, v) for k, v in kv.items() if _is_shape_dim(k, v)]
        dim_str = (
            "×".join(str(v) for _, v in dim_parts)
            if dim_parts
            else c.get("shape_compact", "")
        )
        # Only compute tile analysis when we have primary tile dims
        if l1_n and kv.get("N", 0):
            results.append(
                _case_tiling_row(c, kv, dim_str, (l1_m, l1_n, l1_k), aic_cores)
            )
    return results


DTYPE_BYTES = {
    "float32": 4,
    "float16": 2,
    "bfloat16": 2,
    "float": 4,
    "half": 2,
    "int8": 1,
    "int16": 2,
    "int32": 4,
}
POSITION_COLORS = {
    "VECIN": _tok("colors.pos_vecin", "#0969da"),
    "VECOUT": _tok("colors.pos_vecout", "#1a7f37"),
    "VECCALC": _tok("colors.pos_veccalc", "#cf222e"),
    "L1": _tok("colors.pos_l1", "#8250df"),
    "L0A": "#bf8700",
}

# 每个 buffer 独立配色色板（16色，感知均匀、明暗双主题均可读）
# 冷暖交替，相邻 buffer 对比明显
_BUF_PALETTE = [
    "#0969da",  # 0  蓝
    "#e36209",  # 1  橙
    "#1a7f37",  # 2  绿
    "#cf222e",  # 3  红
    "#8250df",  # 4  紫
    "#0e8a8a",  # 5  青
    "#bf8700",  # 6  琥珀
    "#c4432b",  # 7  砖红
    "#0550ae",  # 8  深蓝
    "#2da44e",  # 9  亮绿
    "#953800",  # 10 深橙
    "#6639ba",  # 11 深紫
    "#1b7a8a",  # 12 深青
    "#d4a017",  # 13 金
    "#b35cad",  # 14 粉紫
    "#3d7a3d",  # 15 橄榄绿
]


def _buf_color(idx: int) -> str:
    """按 buffer 序号取色板颜色，循环使用。"""
    return _BUF_PALETTE[idx % len(_BUF_PALETTE)]


def compute_ub_buffers(kernel_data, tile_length, dtype_bytes, init_sizes=None):
    """
    计算 UB buffer 大小列表。
    优先使用 init_sizes（从 InitBuffer 表达式求值），fallback 到 tile_length × dtype_bytes。
    每个 buffer 从 _BUF_PALETTE 按序号取色，保证视觉可区分。
    """
    result = []
    for idx, buf in enumerate(kernel_data.get("buffers", [])):
        pos = buf["position"]
        mul = buf["multiplier"]
        if init_sizes and buf["name"] in init_sizes and init_sizes[buf["name"]] > 0:
            size_kb = init_sizes[buf["name"]] / 1024.0
        else:
            size_kb = mul * tile_length * dtype_bytes / 1024.0
        result.append(
            {
                "name": buf["name"],
                "kind": buf["kind"],
                "position": pos,
                "multiplier": mul,
                "size_kb": round(size_kb, 2),
                "color": _buf_color(idx),
                "label": f"{pos} {buf['kind']}{'×' + str(mul) if mul > 1 else ''}",
                "kernel_group": buf.get("kernel_group", ""),
            }
        )
    return result


# ─── OP GRAPH (工业级计算流图骨架) ─────────────────────────────────────────────
# ⚠️  gen_dashboard.py 是纯汇总器，不做算子语义推断。
# 计算单元（units）必须来自外部 algo_flow.json（由 Claude 阅读算子源码生成）。
# 若未提供 algo_flow.json，units 为空，Tab 1 显示引导提示。
# 详见：subskills/algo_flowchart.md


def _graph_shape_vars(inp_shape: list) -> list:
    """Use actual symbolic names from shape (e.g. ["M","K"]) if they are strings,
    otherwise fall back to generic var names."""
    if inp_shape and all(isinstance(s, str) for s in inp_shape):
        return list(inp_shape)  # e.g. ["M", "K"] from op_desc
    ndim = len(inp_shape)
    if ndim == 1:
        return ["N"]
    if ndim == 2:
        return ["N", "C"]
    if ndim == 3:
        return ["B", "N", "C"]
    return [f"D{i}" for i in range(ndim)]


def _shape_tmpl(shape: list, shape_vars: list) -> str:
    """把一个 shape 渲染成 "{M}, {K}" 形式的模板串。"""
    return ", ".join(
        "{" + (shape_vars[i] if i < len(shape_vars) else f"D{i}") + "}"
        for i, _ in enumerate(shape)
    )


def _graph_shape_case(case: dict, shape_vars: list):
    """把一个 test case 的 shape 转成 shape_cases 条目；无法解析时返回 None。"""
    shape_str = str(case.get("shape", ""))
    label_prefix = case.get("name") or f"Case {case.get('id', 0)}"
    # Try 1: parse dict-format string → extract values by key (e.g. {'M':32,'K':64,'N':48,...})
    kv = {m.group(1): m.group(2) for m in re.finditer(r"'(\w+)':\s*(\d+)", shape_str)}
    if kv and all(v in kv for v in shape_vars):
        vals = [kv[v] for v in shape_vars]
        return {
            "label": f"{label_prefix}: {' × '.join(vals)}",
            "vars": dict(zip(shape_vars, vals)),
        }
    # Try 2: use actual dims regardless of ndim mismatch (supports 1D/2D/3D/4D test cases)
    nums = re.findall(r"\d+", shape_str)
    if not nums:
        return None
    # Map to shape_vars for first min(n, len(shape_vars)) dims, extend with S{i} for extras
    actual_vars = [
        shape_vars[i] if i < len(shape_vars) else f"S{i}" for i in range(len(nums))
    ]
    return {
        "label": f"{label_prefix}: {' × '.join(nums)}",
        "vars": dict(zip(actual_vars, nums)),
    }


def _io_entry(s: dict, idx: int, shape_vars: list, is_output: bool = False) -> dict:
    """Multi-IO arrays (v2) 中的一项。"""
    return {
        "name": s.get("name", "y" if is_output else f"x{idx}"),
        "dtype": s.get("dtype", ""),
        "tmpl": _shape_tmpl(s.get("shape", []), shape_vars),
    }


def build_op_graph(input_shapes, output_shapes, cases):
    """
    构建 op_graph 骨架：IO 字段 + shape_cases，units 始终为空。
    计算单元由 algo_flow.json 注入，不在此处推断。
    """
    inp_shape = input_shapes[0].get("shape", []) if input_shapes else []
    shape_vars = _graph_shape_vars(inp_shape)
    out_shape = output_shapes[0].get("shape", inp_shape) if output_shapes else inp_shape

    shape_cases = []
    for c in cases:
        entry = _graph_shape_case(c, shape_vars)
        if entry:
            shape_cases.append(entry)
    if not shape_cases and inp_shape:
        shape_cases = [
            {
                "label": "Default",
                "vars": dict(zip(shape_vars, [str(s) for s in inp_shape])),
            }
        ]

    return {
        "units": [],  # 由 algo_flow.json 注入
        "needs_algo_flow": True,  # JS 用于显示引导提示
        "shape_vars": shape_vars,
        "shape_cases": shape_cases,
        # legacy single-IO fields (backward compat)
        "inp_name": input_shapes[0].get("name", "x") if input_shapes else "x",
        "out_name": output_shapes[0].get("name", "y") if output_shapes else "y",
        "inp_tmpl": _shape_tmpl(inp_shape, shape_vars),
        "out_tmpl": _shape_tmpl(out_shape, shape_vars),
        "inp_dtype": input_shapes[0].get("dtype", "") if input_shapes else "",
        "out_dtype": output_shapes[0].get("dtype", "") if output_shapes else "",
        # v2 multi-IO arrays
        "inputs": [
            _io_entry(s, i, shape_vars, False) for i, s in enumerate(input_shapes)
        ],
        "outputs": [
            _io_entry(s, i, shape_vars, True) for i, s in enumerate(output_shapes)
        ],
    }
