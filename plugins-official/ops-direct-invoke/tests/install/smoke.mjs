// Copyright (c) 2026 CANNBot contributors
// SPDX-License-Identifier: MIT
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export function smokeDirectInvoke({ sandbox, target, consumer, executable, run }) {
  const directInput = join(sandbox, "direct-init.json");
  writeFileSync(directInput, JSON.stringify({ repo: "cannbench", platform: "ascend", chip: "Ascend950",
    preferences: { interaction: "confirm", autonomy: "仅已明确授权范围", review_points: [] } }));
  run(executable, ["install", "ops-direct-invoke", "--tool", "claude", "--target", target], consumer, {
    ...process.env,
    CANNBOT_DIRECT_INVOKE_CONFIG: directInput,
    CANNBOT_SKIP_OPMODEL_INSTALL: "1",
    HOME: join(sandbox, "home"),
    XDG_CACHE_HOME: join(sandbox, "cache"),
    CANNBOT_SKIP_DEPENDENCY_REPOS: "1",
  });
  const config = JSON.parse(readFileSync(join(target, ".cannbot/ops-direct-invoke.json"), "utf8"));
  const mainSkills = ["ops-direct-invoke", "ops-direct-invoke-maintain", "ops-direct-invoke-requirement", "ops-direct-invoke-repo-guide"];
  const actualSkills = readdirSync(join(target, ".claude/skills")).sort();
  if (JSON.stringify(actualSkills) !== JSON.stringify(mainSkills.sort())) throw new Error("direct workflow exposes unselected Skills");
  for (const path of [
    ...mainSkills.map((name) => join(target, ".claude/skills", name, "SKILL.md")),
    join(config.asset_root, "tools/generate_workflow_guide.py"),
    join(config.asset_root, "tools/assemble_workflow.py"),
    join(config.asset_root, "orchestrations/workflows/ascendc/basic.yaml"),
    join(config.asset_root, "skills/custom-skills/requirement/kirin/SKILL.md"),
    join(config.asset_root, "agents/ops-direct-invoke-verifier.md"),
    join(config.external_skills_root, "workflow-orchestrator/scripts/orchestrator.py"),
    join(config.external_skills_root, "cannbot-dsl-best-practice/SKILL.md"),
  ]) {
    if (!existsSync(path)) throw new Error(`packaged direct workflow is missing: ${path}`);
  }
  const performance = JSON.parse(readFileSync(config.performance_registry, "utf8")).plugins
    .find((plugin) => plugin.plugin === "ops-perf-optimize");
  if (!performance?.skills.length) throw new Error("isolated performance initialization is missing");
  for (const skill of performance.skills) {
    if (!existsSync(join(config.performance_root, skill, "SKILL.md"))) throw new Error(`missing performance Skill: ${skill}`);
  }
  const guide = join(sandbox, "workflow-guide.csv");
  run("python3", [join(config.asset_root, "tools/generate_workflow_guide.py"), "--output", guide], consumer);
  for (const template of ["basic", "perf-optimize", "op-dev-with-perf"]) {
    if (!readFileSync(guide, "utf8").includes(`ascendc/${template}.yaml`)) throw new Error(`${template} workflow missing from guide`);
    run("python3", [join(config.asset_root, "tools/run_workflow.py"), "--template", `ascendc/${template}.yaml`,
      "--work-dir", join(sandbox, "workflow-run", template), "--provider", "claude", "--prompt", "package workflow smoke test",
      "--harness-skill", join(config.external_skills_root, "workflow-orchestrator"), "--foreground", "--dry-run"], consumer);
  }
}
