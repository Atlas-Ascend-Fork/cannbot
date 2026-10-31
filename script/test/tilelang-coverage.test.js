// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
// See script/LICENSE for the full license text.

import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

const workflow = resolve(import.meta.dirname, "../../plugins-official/tilelang-op-orchestrator/workflows/Ascend950");
const validator = join(workflow, "scripts/validate_optimization_search_coverage.py");
const examples = join(workflow, "workflows/optimization-search-coverage");

function run(t, fixture, args, mutate) {
  const directory = mkdtempSync(join(tmpdir(), "tilelang-coverage-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const data = JSON.parse(readFileSync(join(examples, fixture), "utf8"));
  mutate?.(data);
  const record = join(directory, "record.json");
  writeFileSync(record, JSON.stringify(data));
  const result = spawnSync("python3", [validator, record, ...args], { encoding: "utf8", timeout: 10000 });
  assert.ifError(result.error);
  return result;
}

for (const [fixture, args, status, stdout, stderr] of [
  ["optimization_search_coverage.example.json", [], 0, "VALID_RECORD", ""],
  ["optimization_search_coverage.example.json", ["--final"], 2, "", "SEARCH_INCOMPLETE: performance targets unmet for ['representative_case']; keep search open"],
  ["optimization_search_coverage.example.json", ["--final", "--allow-unmet-convergence"], 1, "", "INVALID: obligation O_ROUTE/representative_case: still PENDING at final gate"],
  ["optimization_search_coverage.final.example.json", [], 0, "VALID_RECORD", ""],
  ["optimization_search_coverage.final.example.json", ["--final"], 0, "TARGET_MET", ""],
  ["optimization_search_coverage.final.example.json", ["--final", "--allow-unmet-convergence"], 0, "TARGET_MET", ""],
]) {
  test(`TileLang coverage preserves ${fixture} ${args.join(" ") || "draft"} gate results`, (t) => {
    const result = run(t, fixture, args);
    assert.equal(result.status, status, result.stderr);
    assert.equal(result.stdout.trim(), stdout);
    assert.equal(result.stderr.trim(), stderr);
  });
}

for (const [name, mutate, message] of [
  ["inconsistent source density", (data) => { data.cases[0].source_window.density = 0.5; }, "INVALID: case representative_case: source density is inconsistent with consumed/span"],
  ["changed candidate identity", (data) => { data.candidate_events[1].identity.precision = "changed"; }, "INVALID: candidate C1: identity changed; allocate a new ID"],
  ["invalid measurement", (data) => { data.candidate_events[1].case_results[0].performance_measurement.kernel_time_us = 0; }, "INVALID: candidate C1/representative_case: invalid measured kernel_time_us"],
  ["untested boundary value", (data) => { data.obligations[1].boundary_plan[0].case_values.representative_case = 999; }, "INVALID: obligation O_TILE/B_FULL: no candidate tested FULL_CONTIGUOUS_UNIT=999 for representative_case"],
  ["untested interaction", (data) => { data.obligations[2].interaction_plan[0].writeback_kind = "SCALAR"; }, "INVALID: obligation O_INTERACTION/I_FULL_DIRECT_SCATTER: no candidate tested required combination for representative_case"],
]) {
  test(`TileLang coverage rejects ${name} with the original diagnostic`, (t) => {
    const result = run(t, "optimization_search_coverage.final.example.json", ["--final"], mutate);
    assert.equal(result.status, 1);
    assert.equal(result.stdout, "");
    assert.equal(result.stderr.trim(), message);
  });
}

function addPipelineObligation(data) {
  const obligation = {
    obligation_id: "O_PIPELINE",
    kind: "pipeline_realization",
    case_ids: ["representative_case"],
    status: "ACTIVE",
    candidate_ids: ["C1"],
    case_dispositions: structuredClone(data.obligations[0].case_dispositions),
    basis_candidate_id: "B0",
    pipeline_plan: {
      automatic: { status: "NOT_TRIED", candidate_ids: [] },
      manual: { status: "NOT_TRIED", candidate_ids: [] },
    },
  };
  data.obligations.push(obligation);
  data.cases[0].obligation_ids.push("O_PIPELINE");
  return obligation;
}

test("TileLang coverage preserves an admitted pipeline obligation when the target is met", (t) => {
  const result = run(t, "optimization_search_coverage.final.example.json", ["--final"], addPipelineObligation);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, "TARGET_MET\n");
  assert.equal(result.stderr, "");
});

for (const [name, mutate, message] of [
  ["unknown pipeline basis", (obligation) => { obligation.basis_candidate_id = "missing"; }, "INVALID: obligation O_PIPELINE: basis_candidate_id must be B0 or a candidate"],
  ["invalid automatic status", (obligation) => { obligation.pipeline_plan.automatic.status = "INVALID"; }, "INVALID: obligation O_PIPELINE: invalid automatic status"],
  ["unlinked pipeline trial", (obligation) => { obligation.pipeline_plan.automatic.candidate_ids = ["missing"]; }, "INVALID: obligation O_PIPELINE: automatic candidate not linked"],
  ["untested automatic realization", (obligation) => { obligation.pipeline_plan.automatic = { status: "COMPLETE", candidate_ids: ["C1"] }; }, "INVALID: obligation O_PIPELINE: automatic has no actually tested AUTOMATIC candidate for representative_case"],
  ["untested manual realization", (obligation) => { obligation.pipeline_plan.manual = { status: "TESTED", candidate_ids: ["C1"] }; }, "INVALID: obligation O_PIPELINE: manual has no actually tested MANUAL candidate for representative_case"],
]) {
  test(`TileLang coverage rejects ${name} with the original diagnostic`, (t) => {
    const result = run(t, "optimization_search_coverage.final.example.json", ["--final"], (data) => {
      mutate(addPipelineObligation(data));
    });
    assert.equal(result.status, 1);
    assert.equal(result.stdout, "");
    assert.equal(result.stderr, `${message}\n`);
  });
}

test("TileLang coverage functions meet the reported static requirements", () => {
  const check = `
import ast
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text()
lines = source.splitlines()
controls = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.Match)
def depth(node):
    return int(isinstance(node, controls)) + max((depth(child) for child in ast.iter_child_nodes(node)), default=0)
tree = ast.parse(source)
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef):
        body = node.body
        if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            body = body[1:]
        nbnc = sum(bool(line.strip()) and not line.lstrip().startswith("#") for line in lines[body[0].lineno - 1:node.end_lineno])
        assert nbnc <= 50, (node.name, nbnc)
        assert 1 + depth(node) <= 4, (node.name, 1 + depth(node))
    if isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
        clauses = len(node.generators) + sum(len(part.ifs) for part in node.generators)
        assert clauses <= 2, (node.lineno, clauses)
        for part in node.generators:
            assert part.iter.lineno == part.iter.end_lineno, part.iter.lineno
            assert all(condition.lineno == condition.end_lineno for condition in part.ifs), node.lineno
    if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple):
        assert len(node.value.elts) <= 5, node.lineno
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        assert node.func.id != "print", node.lineno
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        direct_stream_write = node.func.attr == "write" and ast.unparse(node.func.value) in {"sys.stdout", "sys.stderr"}
        assert not direct_stream_write, node.lineno
`;
  const result = spawnSync("python3", ["-c", check, validator], { encoding: "utf8", timeout: 10000 });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
});
