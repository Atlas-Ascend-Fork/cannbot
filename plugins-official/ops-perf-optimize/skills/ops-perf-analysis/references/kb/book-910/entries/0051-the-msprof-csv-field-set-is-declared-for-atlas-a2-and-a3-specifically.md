```
ID:        0051-the-msprof-csv-field-set-is-declared-for-atlas-a2-and-a3-specifically
LABEL:     knowledge
LEVEL:     L7 (verification)
STRATUM:   harvested — drafted from one upstream origin; nothing measured here
BOARD:     family-claimed(unverified)
SOURCE:    ops/ops-profiling/references/csv_fields_reference.md:3 — "数据来源: MindStudio 8.3.0 官方文档。适用于 Atlas A2/A3 训练系列产品和推理系列产品"; ops/ascendc-performance-analysis/references/metrics_reference.md:349 — "#### PipeUtilization.csv 关键字段（Atlas A2/A3）"
INDEX:     none — nothing measured; see SOURCE.
OVERTURN:  an msprof collection on a named DAV_2201 board produces a PipeUtilization.csv whose column names differ from the documented set, or omits fields the documentation lists.
```

# 0051 · The msprof CSV field set is declared for Atlas A2 and A3 specifically

## 1 · Claim
Upstream asserts that its msprof CSV field reference is sourced from MindStudio 8.3.0
documentation and applies to Atlas A2/A3 training and inference products. Upstream asserts a
specific A2/A3 field set for PipeUtilization.csv: `aic_time(us)`, `aic_total_cycles`,
`aiv_time(us)`, `aiv_total_cycles`, `aic_cube_ratio`, `aic_mte2_ratio`, `aiv_vec_ratio`,
`aiv_mte2_time(us)`, `aiv_mte3_time(us)`, `aic_fixpipe_ratio`. Upstream marks at least two items as
A2/A3-only: the Mix Block Dim column and the active-bandwidth section. Not established here.

## 2 · The wrong branch this removes
Every threshold in every diagnosis rule this book carries — the bound-routing gates, the bank
conflict gates, the utilisation ladders — is expressed as a comparison against a named CSV field.
An agent that cannot name the fields its part actually produces cannot evaluate any of them, and
the failure is quiet in a specific way: a parsing script that looks up a missing column and gets
nothing will report a ratio of zero, which reads as "this pipe is idle" rather than as "this field
does not exist". A pipe reported idle is excluded from the bottleneck search, so a missing field
does not raise an error — it removes a candidate.

That is the failure species this book tracks: a check that reads only the lines it expects. The
defence is to enumerate the columns actually present before evaluating any threshold against them,
which is what §4 does.

The second branch is scoping. This is one of the few upstream documents that names both an
architecture scope AND a tool version. Most thresholds elsewhere name neither (0053). A consuming
agent should read this document's discipline as the standard and treat unscoped threshold tables as
weaker, not as equally authoritative.

## 3 · Ground / Source
`ops/ops-profiling/references/csv_fields_reference.md:3`, the document's provenance line:
"数据来源: MindStudio 8.3.0 官方文档。适用于 Atlas A2/A3 训练系列产品和推理系列产品。"
— a tool version AND an architecture scope in one sentence, which no other threshold document in
scope manages.

A2/A3-specific items in that file: line 32, "| Mix Block Dim | 混合算子从核 blockDim（非 Mix 算子
显示 N/A） | 仅 A2/A3 |"; line 77, "### 活跃带宽（仅 A2/A3）"; line 208, "### Atlas A2/A3" heading
over the L2Cache.csv field table.

The field list, `ops/ascendc-performance-analysis/references/metrics_reference.md` §6.4, heading at
line 349 "#### PipeUtilization.csv 关键字段（Atlas A2/A3）", table at lines 351-362, ten fields as
quoted in §1.

The file-level map, same file lines 341-347: ArithmeticUtilization.csv (`aic_cube_ratio`,
`aiv_vec_ratio`, `aic_cube_fops`, `aiv_vec_fops`), PipeUtilization.csv, L2Cache.csv (`hit_rate`),
Memory.csv (`gm_to_ub`, `ub_to_gm`), OpBasicInfo.csv (`block_dim`, `task_duration`).

The trace PID mapping, same file lines 54-64, with an explicit warning at line 66 that this book
adopts: "**注意**：PID 与单元名的映射从 trace 文件中的元数据事件 (`ph==\"M\"`,
`name==\"process_name\"`) 中动态提取，不同版本可能有差异。" — upstream itself says the mapping is
version-dependent and must be read from the file rather than assumed. That is the same discipline
as §4 below and is upstream's, not this book's.

Both files are the same repo: one origin. MindStudio 8.3.0's own documentation would be an
independent origin and was not consulted.

## 4 · Procedure
Proposed, runnable later; not run. This procedure is a prerequisite for every other entry in this
book that names a CSV field, and should be run once before any of them.

1. Name the die; occupancy before and after; no substitution. Record the installed MindStudio and
   CANN versions — the claim is version-scoped and a result without a version is not comparable.
2. Run `msprof op --output=... ./trivial_kernel` on a minimal kernel that exercises Cube, Vector,
   MTE2 and MTE3, so every documented field has a chance to be populated.
3. Enumerate the actual column headers of every produced CSV. Diff against the documented set,
   reporting BOTH directions: documented-but-absent, and present-but-undocumented. The second
   direction is the one an agent working from documentation alone never sees.
4. Extract the trace PID→unit mapping from the metadata events rather than from the documented
   table, and diff those too.
5. For each documented field that IS present, record whether it is populated (non-zero somewhere in
   the run) or constant-zero. A present-but-always-zero field is functionally missing and produces
   exactly the silent-idle failure of §2.

## 5 · Checker — acceptance declared before the run
Verdict variables `missing_fields`, `extra_fields`, `dead_fields` (present but constant-zero).
PASS iff `missing_fields` is empty and `dead_fields` is empty.
`extra_fields` is reported and does not fail the check — an undocumented column is a gap in the
documentation, not in the tool.
The positive fixture this checker must find, run before any real diff: feed the enumerator a CSV
with a column deliberately renamed and confirm it reports that column as missing. **An enumerator
that returns "no missing fields" on a file it never opened, or on a file with a renamed column, is
the blind species this entry exists to defend against, and its clean verdicts would be worthless.**
The fixture is a positive the instrument must FIND, not a clean file it must pass.
Exit code is not the verdict; msprof exits zero on a collection that produced empty CSVs.

## 6 · Evidence
NOT YET RUN — no readout exists. Nothing in this file is a measurement.

## 7 · Scope limits — what this entry does NOT establish
Nothing measured here; no board touched. "Atlas A2/A3" is two product lines spanning six parts, not
a board. The claim is pinned to MindStudio 8.3.0 and this book has no installation bound
(`book-910/CALIBRATION.md` carries no installation), so nothing here is established for any other tool
version — and upstream itself warns the trace mapping varies by version. This entry does not
establish what any field *means*, only that it is documented to exist; the semantics of
`aiv_vec_ratio` (cycles? time?) are not settled by a column list. It does not establish which
fields exist on 950-family parts, and it must not be read as implying they differ.
