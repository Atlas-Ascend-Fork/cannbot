#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_ROOT="$(mktemp -d /tmp/ops-perf-state.XXXXXX)"

cleanup() {
    rm -rf "$TEST_ROOT"
}
trap cleanup EXIT

mkdir -p "$TEST_ROOT/code" "$TEST_ROOT/run/round1"
printf '%s\n' 'kernel-v1' > "$TEST_ROOT/code/kernel.cpp"
printf '%s\n' 'case_id,shape,dtype,level' 'a,"[1,16]",float16,L0' 'b,"[17,32]",float16,L0' > "$TEST_ROOT/cases.csv"

PREPARE="$PLUGIN_ROOT/scripts/prepare_case_sets.py"
TOOL="$PLUGIN_ROOT/scripts/workflow_state.py"
STATE="$TEST_ROOT/run/workflow-state.json"
MANIFEST="$TEST_ROOT/run/run-manifest.json"
REQUEST="$TEST_ROOT/optimization-request.json"

python3 "$PREPARE" create-request --request "$REQUEST" --operator-name test_op \
    --target-soc Ascend950 \
    --code-dir "$TEST_ROOT/code" --performance-cases "$TEST_ROOT/cases.csv" \
    --functional-mode reuse_performance --optimization-mode fixed_rounds --rounds 3 \
    --python-executable "$(command -v python3)" --cann-env-command inherit >/dev/null
python3 "$PREPARE" freeze --output-dir "$TEST_ROOT/run" --request "$REQUEST" >/dev/null
python3 "$TOOL" start --state "$STATE" --manifest "$MANIFEST" | grep -q '"status": "new"'
test -f "$TEST_ROOT/run/性能调优报告.md"
test ! -e "$TEST_ROOT/run/lessons"
test ! -e "$TEST_ROOT/run/report-progress.json"
test ! -e "$TEST_ROOT/run/multi-round-summary.json"

python3 "$TOOL" mark --state "$STATE" --stage prepare.acceptance --status in_progress \
    --message '开始功能验收' >/dev/null
python3 "$TOOL" progress --state "$STATE" --kind diagnosis --stage prepare.acceptance \
    --message '原始实现同条件复现，候选误差未恶化' --case-id b \
    --classification known_baseline_failure --evidence baseline-repro.json \
    --hypothesis 'baseline defect' --excluded-hypothesis 'candidate regression' \
    --next-action '以 conditional_pass 继续 round1' >/dev/null
printf '%s\n' '# acceptance' 'gate: conditional_pass' > "$TEST_ROOT/run/acceptance.md"
python3 "$TOOL" mark --state "$STATE" --stage prepare.acceptance --status complete \
    --message "功能验收 conditional_pass" --next-action "进入 round1" \
    --artifact "$TEST_ROOT/run/acceptance.md" >/dev/null
python3 "$TOOL" verify --state "$STATE" | grep -q '"status": "valid"'

python3 - "$STATE" <<'PY'
import json
from pathlib import Path
import sys

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
stage = state["stages"]["prepare.acceptance"]
assert stage["status"] == "complete"
assert stage["started_at"] < stage["completed_at"]
assert stage["elapsed_seconds"] >= 0
assert state["precision"]["policy"] == "persistent"
assert state["precision"]["known_baseline_failures"][0]["case_id"] == "b"
assert "candidate regression" in state["precision"]["excluded_hypotheses"]
PY
grep -q '既是执行现场，也是最终交付' "$TEST_ROOT/run/性能调优报告.md"
grep -q '优化目标：固定 3 轮' "$TEST_ROOT/run/性能调优报告.md"
grep -q '已验证目标 SoC：`Ascend950`' "$TEST_ROOT/run/性能调优报告.md"
grep -q '优化请求：`' "$TEST_ROOT/run/性能调优报告.md"
grep -q 'Python：' "$TEST_ROOT/run/性能调优报告.md"
grep -q 'CANN 环境：`inherit`' "$TEST_ROOT/run/性能调优报告.md"
grep -q '已证实基线失败：1' "$TEST_ROOT/run/性能调优报告.md"
grep -q 'conditional_pass' "$TEST_ROOT/run/性能调优报告.md"

# Parallel candidates must not overwrite each other's stage records.
printf '%s\n' '# impl a' > "$TEST_ROOT/run/round1/impl-a.md"
printf '%s\n' '# impl b' > "$TEST_ROOT/run/round1/impl-b.md"
python3 "$TOOL" mark --state "$STATE" --stage round1.impl.a --status complete \
    --artifact "$TEST_ROOT/run/round1/impl-a.md" &
PID_A=$!
python3 "$TOOL" mark --state "$STATE" --stage round1.impl.b --status complete \
    --artifact "$TEST_ROOT/run/round1/impl-b.md" &
PID_B=$!
wait "$PID_A" "$PID_B"
python3 - "$STATE" <<'PY'
import json
from pathlib import Path
import sys

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
stages = state["stages"]
assert "round1.impl.a" in stages
assert "round1.impl.b" in stages
for name in ("round1.impl.a", "round1.impl.b"):
    record = stages[name]
    assert record["elapsed_seconds"] is None, f"{name} lacked in_progress mark; elapsed must stay unknown, not fake 0.0"
    assert "started_at" not in record
PY
grep -q '当前阶段：`阶段间歇`' "$TEST_ROOT/run/性能调优报告.md"
grep -q '| `round1.impl.a` | complete | - | .* | - | 1 |' "$TEST_ROOT/run/性能调优报告.md"

# Interactive waits are explicit, report-visible, and resolvable.
python3 "$TOOL" decision --state "$STATE" --awaiting --question '继续修复还是淘汰 candidate-a？' \
    --safe-restore-point round1.impl.a >/dev/null
grep -q '状态：等待人工' "$TEST_ROOT/run/性能调优报告.md"
python3 "$TOOL" decision --state "$STATE" --decision '淘汰 candidate-a，继续 candidate-b' >/dev/null
grep -q '淘汰 candidate-a' "$TEST_ROOT/run/性能调优报告.md"

# Intentional manifest updates must be synchronized; silent changes are stale.
python3 "$PREPARE" confirm-performance --manifest "$MANIFEST" --note 'operator reaffirmed set' >/dev/null
set +e
RESULT=$(python3 "$TOOL" start --state "$STATE" --manifest "$MANIFEST")
STATUS=$?
set -e
test "$STATUS" -eq 3
grep -q 'stale_inputs' <<< "$RESULT"
python3 "$TOOL" sync-manifest --state "$STATE" --message 'performance set confirmed' >/dev/null
python3 "$TOOL" start --state "$STATE" --manifest "$MANIFEST" | grep -q '"status": "resume"'

# Workflow changes require an impact audit and invalidate only declared stages.
set +e
RESULT=$(python3 "$TOOL" start --state "$STATE" --manifest "$MANIFEST" --workflow-version workflow-v4)
STATUS=$?
set -e
test "$STATUS" -eq 5
grep -q 'resume_with_workflow_change' <<< "$RESULT"
printf '%s\n' '# migration audit' 'Only round1.impl.a is affected.' > "$TEST_ROOT/run/migration.md"
python3 "$TOOL" migrate-workflow --state "$STATE" --audit "$TEST_ROOT/run/migration.md" \
    --workflow-version workflow-v4 --invalidate-stage round1.impl.a >/dev/null
set +e
RESULT=$(python3 "$TOOL" start --state "$STATE" --manifest "$MANIFEST" --workflow-version workflow-v4)
STATUS=$?
set -e
test "$STATUS" -eq 4
grep -q 'round1.impl.a' <<< "$RESULT"

# Modified completed evidence is detected and reflected in state/report.
printf '%s\n' '# changed' >> "$TEST_ROOT/run/round1/impl-b.md"
if python3 "$TOOL" verify --state "$STATE" >/dev/null; then
    echo "Modified checkpoint should fail verification" >&2
    exit 1
fi
grep -q 'invalid' "$STATE"

if python3 "$TOOL" finish --state "$STATE" --status failed --reason-code known_baseline_failure \
    --message '不得因原始失败终止' >/dev/null 2>&1; then
    echo "Known baseline failure must not terminate the workflow" >&2
    exit 1
fi
python3 "$TOOL" finish --state "$STATE" --status blocked --reason-code external_blocker \
    --message '测试终态：保留安全恢复点，等待外部资源' >/dev/null
grep -q '终态：`blocked`' "$TEST_ROOT/run/性能调优报告.md"

echo "Unified workflow state and live report: PASS"
