#!/usr/bin/env python3
# -----------------------------------------------------------------------------------------------------------
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# This program is free software, you can redistribute it and/or modify it under the terms and conditions of
# CANN Open Software License Agreement Version 2.0 (the "License").
# Please refer to the License for details. You may not use this file except in compliance with the License.
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
# See LICENSE in the root of the software repository for the full text of the License.
# -----------------------------------------------------------------------------------------------------------

"""Render a verified Board/Simulation/unknown Chrome trace without changing its original bytes."""
import argparse
import collections
import copy
import hashlib
import html
import json
import math
from pathlib import Path
import shutil
import textwrap

from cli_output import emit


def merge(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def color(label):
    colors = {'MTE2': '#2b8bd3', 'MTE1': '#8260bd', 'MTE3': '#149c82',
              'CUBE': '#ed9132', 'FIXP': '#d4af2b', 'RVEC': '#c2579b',
              'SCALAR': '#7a8794', 'PUSHQ': '#5ba04a', 'FC': '#99a4ad'}
    return next((value for key, value in colors.items() if key in label), '#7a8794')


def read_trace(path):
    data = json.loads(path.read_text())
    events = data['traceEvents'] if isinstance(data, dict) else data
    names = {e['pid']: e['args']['name'].split(' (', 1)[0]
             for e in events if e.get('ph') == 'M' and e.get('name') == 'process_name'}
    # Group slots of a given pipeline together, retaining process/AIC/AIV identity.
    lanes = collections.defaultdict(list)
    skipped_zero = 0
    for event in events:
        if event.get('ph') != 'X' or event.get('pid') not in names:
            continue
        duration = float(event.get('dur', 0))
        if not math.isfinite(duration) or duration < 0:
            raise ValueError('Invalid instruction duration')
        if duration == 0:
            skipped_zero += 1
            continue
        if not math.isfinite(float(event['ts'])):
            raise ValueError('Invalid instruction timestamp')
        lanes[event['pid']].append(event)
    if not lanes:
        raise ValueError('No positive-duration instructions with process_name metadata')
    return data, events, names, lanes, skipped_zero


def core_ids(value):
    """Parse explicit core IDs; all/unknown cannot prove a concrete subset."""
    if value in ('all', 'unknown'):
        return None
    result = set()
    for part in value.split(','):
        bounds = part.split('-')
        if len(bounds) > 2 or any(not x.isdigit() for x in bounds):
            raise ValueError('Core range must be all, unknown, or IDs such as 0-2,5')
        first, last = int(bounds[0]), int(bounds[-1])
        if first > last or last - first > 10000:
            raise ValueError('Invalid core range')
        result.update(range(first, last + 1))
    return result


def provenance(args):
    recorded, reported = core_ids(args.recorded_cores), core_ids(args.reported_cores)
    if recorded is not None and reported is not None and not reported <= recorded:
        raise ValueError('Reported cores must be a subset of recorded cores')
    coverage = ('declared ID subset valid; trace coverage not audited' if recorded is not None and reported is not None
                else 'unknown: concrete recorded/reported subset not verified')
    return dict(source=args.source, tool=args.tool, tool_version=args.tool_version,
                soc=args.soc, model=args.model, case=args.case, kernel=args.kernel,
                recorded_cores=args.recorded_cores, reported_cores=args.reported_cores,
                scope=args.scope, output_status=args.output_status, core_coverage=coverage)


def provenance_text(info):
    return (f"{info['source']} | tool {info['tool']} {info['tool_version']} | "
            f"SoC {info['soc']} | model {info['model']} | case {info['case']} | kernel {info['kernel']}\n"
            f"recorded cores {info['recorded_cores']} | reported cores {info['reported_cores']} | "
            f"scope {info['scope']} | OUTPUT {info['output_status']} | {info['core_coverage']}")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--title', required=True, help='Operator, case and recorded core')
    parser.add_argument('--time-unit', choices=['us', 'ns', 'cycles'], required=True,
                        help='Verified unit of input ts/dur; values are not converted')
    parser.add_argument('--source', choices=['Board', 'Simulation', 'unknown'], default='Simulation',
                        help='Legacy default is Simulation; Board callers must explicitly declare Board')
    for field in ('tool', 'tool-version', 'soc', 'model', 'case', 'kernel',
                  'recorded-cores', 'reported-cores'):
        parser.add_argument('--' + field, default='unknown')
    parser.add_argument('--scope', choices=['full', 'cropped', 'unknown'], default='unknown')
    parser.add_argument('--output-status', choices=['PASS', 'FAIL', 'unknown'], default='unknown')
    return parser


def load_plot_modules(parser):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import plotly.graph_objects as go
    except ImportError as exc:
        parser.error(f'{exc}; use a Python environment with matplotlib and plotly')
    return plt, go


def compute_lane_stats(lanes, names, start, span):
    stats = []
    merged_lanes = {}
    mte2 = []
    for pid, lane in lanes.items():
        intervals = merge([(e['ts'], e['ts'] + e['dur']) for e in lane])
        merged_lanes[pid] = intervals
        busy = sum(b - a for a, b in intervals)
        gap = sum(intervals[i][0] - intervals[i - 1][1] for i in range(1, len(intervals)))
        stats.append(dict(pid=pid, pipeline=names[pid], instruction_count=len(lane),
                          busy_time=busy, share_percent=busy / span * 100,
                          internal_gap_time=None if 'SCALAR' in names[pid] else gap))
        if 'MTE2' in names[pid]:
            mte2.extend(e['ts'] for e in lane)
    return stats, merged_lanes, mte2


def build_summary(args, info, lanes, span, start, mte2, stats, skipped_zero):
    return dict(title=args.title, provenance=info, time_unit=args.time_unit, span=span,
                first_instruction_ts=start, head_time=min(mte2) - start if mte2 else None,
                instruction_count=sum(len(lane) for lane in lanes.values()),
                zero_duration_events_excluded=skipped_zero,
                source_trace=str(args.trace.resolve()),
                source_sha256=hashlib.sha256(args.trace.read_bytes()).hexdigest(),
                pipelines=stats)


def write_trace_outputs(args, data, summary):
    args.output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.trace, args.output / 'trace_original.json')
    normalized = copy.deepcopy(data)
    normalized_events = normalized['traceEvents'] if isinstance(normalized, dict) else normalized
    for e in normalized_events:
        if e.get('ph') == 'M' and e.get('name') == 'process_name':
            e['args']['name'] = e['args']['name'].split(' (', 1)[0].replace('SCALAR_LDST', 'SCALARLDST')
    normalized_events[:] = [e for e in normalized_events
                            if e.get('ph') != 'X' or e.get('dur', 0) > 0]
    (args.output / 'trace_normalized.json').write_text(json.dumps(normalized))
    (args.output / 'pipeline_stats.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False))


def render_static(args, plt, lanes, labels, merged_lanes, start, span, summary,
                  display_metadata, metadata_lines):
    plot_height = max(6, len(labels) * 0.28)
    footer_height = 0.35 + metadata_lines * 0.15
    fig, axis = plt.subplots(figsize=(16, plot_height + footer_height))
    for i, pid in enumerate(lanes):
        axis.broken_barh([(a - start, b - a) for a, b in merged_lanes[pid]],
                         (i - 0.35, 0.7), facecolors=color(labels[i]))
    axis.set_yticks(range(len(labels)), labels)
    axis.invert_yaxis()
    axis.set_xlim(0, span)
    axis.set_xlabel(f'{args.source} time relative to first instruction ({args.time_unit})')
    axis.set_title(f'{args.title} | span {span:.3f} {args.time_unit} | '
                   f'{summary["instruction_count"]:,} instructions')
    axis.grid(axis='x', alpha=0.2)
    fig.text(0.01, 0.01, display_metadata, fontsize=8, va='bottom', wrap=True)
    if args.output_status == 'FAIL':
        fig.text(0.5, 0.5, 'OUTPUT FAIL — diagnostic only', color='crimson',
                 fontsize=28, alpha=0.35, rotation=18, ha='center')
    fig.tight_layout(rect=(0, footer_height / (plot_height + footer_height), 1, 1))
    fig.savefig(args.output / 'pipeline.png', dpi=180)
    fig.savefig(args.output / 'pipeline.svg')
    plt.close(fig)


def render_interactive(args, go, lanes, names, start, labels, display_metadata):
    interactive = go.Figure()
    for pid, lane in lanes.items():
        interactive.add_trace(go.Bar(
            y=[str(pid)] * len(lane), x=[e['dur'] for e in lane],
            base=[e['ts'] - start for e in lane], orientation='h', name=names[pid],
            marker_color=color(names[pid]),
            customdata=[[names[pid], e['name'], e['ts'] - start,
                         str(e.get('args', {}).get('pc', ''))] for e in lane],
            hovertemplate='%{customdata[0]}<br>%{customdata[1]}<br>'
                          'Start %{customdata[2]:.6f}<br>Duration %{x:.6f}<br>'
                          'PC %{customdata[3]}<extra></extra>'))
    interactive.update_layout(
        title=html.escape(args.title) + "<br><sup>" + html.escape(display_metadata).replace("\n", "<br>") + "</sup>",
        height=max(750, len(labels) * 30),
        barmode='overlay', showlegend=False, template='plotly_white',
        xaxis=dict(title=f'{args.source} time ({args.time_unit})', rangeslider=dict(visible=True)),
        yaxis=dict(type='category', categoryorder='array',
                   categoryarray=[str(pid) for pid in lanes], autorange='reversed',
                   tickmode='array', tickvals=[str(pid) for pid in lanes], ticktext=labels))
    if args.output_status == 'FAIL':
        interactive.add_annotation(text='OUTPUT FAIL — diagnostic only', x=0.5, y=0.5,
                                   xref='paper', yref='paper', showarrow=False,
                                   font=dict(size=30, color='crimson'), opacity=0.5)
    interactive.write_html(args.output / 'timeline.html', include_plotlyjs=True,
                           config=dict(scrollZoom=True, displaylogo=False))


def write_report(args, stats, metadata_text, span):
    report = [f'# {args.title}', '', metadata_text, '', f'{args.source} 时间单位：{args.time_unit}；span：{span:.6f}。',
              '同流水区间已合并；internal gap 不含头尾空闲，SCALAR 不报气泡。',
              '各流水可同时工作，share 不能相加作为总利用率。', '',
              '| Pipeline | Instructions | Busy | Share % | Internal gap |',
              '|---|---:|---:|---:|---:|']
    for s in stats:
        gap = '—' if s['internal_gap_time'] is None else f'{s["internal_gap_time"]:.6f}'
        report.append(f'| {s["pipeline"]} | {s["instruction_count"]} | '
                      f'{s["busy_time"]:.6f} | {s["share_percent"]:.3f} | {gap} |')
    (args.output / 'pipeline_analysis.md').write_text('\n'.join(report) + '\n')


def write_index(args, metadata_text):
    title = html.escape(args.title)
    (args.output / 'index.html').write_text(
        '<!doctype html><meta charset="utf-8"><title>' + title + '</title>'
        '<style>body{font:16px system-ui;max-width:1600px;margin:32px auto;padding:0 20px}'
        'img{width:100%}</style><h1>' + title + '</h1>'
        '<p>' + html.escape(metadata_text).replace('\n', '<br>') + '</p>'
        '<p>Only recorded instructions are shown; missing records do not prove hardware idle. '
        'Simulation span, hardware latency and wall time are separate.</p>'
        '<p><a href="timeline.html">Interactive timeline</a> · '
        '<a href="trace_original.json">Original trace</a> · '
        '<a href="pipeline.svg">SVG</a> · '
        '<a href="pipeline_stats.json">Statistics</a> · '
        '<a href="pipeline_analysis.md">Analysis</a></p>'
        '<img src="pipeline.png" alt="Instruction pipeline with source, scope and output status">')


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        info = provenance(args)
    except ValueError as exc:
        parser.error(str(exc))
    metadata_text = provenance_text(info)
    display_metadata = '\n'.join(textwrap.fill(line, width=150)
                                 for line in metadata_text.splitlines())
    metadata_lines = display_metadata.count('\n') + 1
    generated_names = ('trace_original.json', 'trace_normalized.json', 'pipeline_stats.json',
                       'pipeline.png', 'pipeline.svg', 'timeline.html',
                       'pipeline_analysis.md', 'index.html')
    if any(args.trace.resolve() == (args.output / name).resolve() for name in generated_names):
        parser.error('Output must not overwrite the input trace')
    plt, go = load_plot_modules(parser)
    data, events, names, lanes, skipped_zero = read_trace(args.trace)
    start = min(e['ts'] for lane in lanes.values() for e in lane)
    end = max(e['ts'] + e['dur'] for lane in lanes.values() for e in lane)
    span = end - start
    stats, merged_lanes, mte2 = compute_lane_stats(lanes, names, start, span)
    summary = build_summary(args, info, lanes, span, start, mte2, stats, skipped_zero)
    write_trace_outputs(args, data, summary)
    labels = [names[pid] for pid in lanes]
    render_static(args, plt, lanes, labels, merged_lanes, start, span, summary,
                  display_metadata, metadata_lines)
    render_interactive(args, go, lanes, names, start, labels, display_metadata)
    write_report(args, stats, metadata_text, span)
    write_index(args, metadata_text)
    result = dict(output=str(args.output.resolve()), span=span, time_unit=args.time_unit,
                  provenance=info, instructions=summary['instruction_count'])
    emit(json.dumps(result))


if __name__ == '__main__':
    main()
