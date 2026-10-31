# Changelog

This file records notable changes to the CANNBot plugin orchestration and delivery repository.

## Unreleased

### Fixed

- Restored the original TileLang AGENTS.md, role adapters and workflows directory verbatim. Migration now adapts only Skill source resolution and installation; no extra orchestration Skill or workflow rewrite is introduced.

- TileLang source installation now defaults to the plugin directory instead of the CANNBot repository root, preserving its AGENTS.md on repeated installs. Explicit project paths remain supported.

### Added

- `model-recommend-infer-optimize` now declares `dependencies: ["model-recommend-skills"]`, and the marketplace registers that
  Skills pack as a `git-subdir` source (`cannbot-skills` `community/model`) pinned to the same commit as the
  `vendor/cannbot-skills` submodule (`b4baf2a`). Claude Code marketplace installs therefore ship the 18 Skills
  through the dependency pack instead of ending up with an empty `skills/`; `npm run build:plugins` keeps
  bundling them into `dist/plugins/model-recommend-infer-optimize/skills/` as before.
- Migrated `tilelang-op-orchestrator` from cannbot-skills, preserving the independent Ascend910 / Ascend950 workflows, six role agents and SessionStart hook. The unified installer links thirteen shared Skills from `vendor/cannbot-skills`; npm builds bundle those Skills. The original AGENTS.md, role definitions and platform workflows are preserved; TileLang installation resolves the shared Skill sources and retains their original relative layout.
- Installers now prepare the knowledge base for use: both the unified installer and
  `triton-auto-evolve/init.sh` build the retrieval index (`search/okf.index.json`, ~50s,
  ~310MB) right after cloning `cannbot-knowledge`, instead of leaving the first query to
  pay for it (and instead of failing with "knowledge base root does not look ready" on
  the old code). Failures degrade to a warning and the next query retries;
  `CANNBOT_SKIP_KNOWLEDGE_INDEX=1` skips the step and `CANNBOT_REBUILD_KNOWLEDGE_INDEX=1`
  forces a rebuild.
- `triton-auto-evolve/init.sh` generates a project-level `config.json` after a
  project-level install (`target_mfu=60`, `max_rounds=2`), with `npu_idle` thresholds
  probed from the current machine and `npu_device_id` pinned to a free card when
  `npu-smi` answers (falling back to `TRITON_NPU_DEVICE_ID`, then to auto-selection).
  Without it the orchestrator fell back to `DEFAULT_CONFIG` (`max_rounds=10`,
  `npu_idle.hbm=10`), which marks every card busy on a shared machine and fails round 1.
- `triton-auto-evolve/init.sh` installs only `triton-auto-evolve` itself. It no longer
  provisions `triton-op-generator`: `--with-op-generator` now fails with a hint to run that
  plugin's own installer, and `--no-op-generator` is accepted as a no-op. The orchestration
  flow already reaches the same shared ops Skills, while co-installing costs a second
  knowledge clone and index (~310MB), grows the project instructions file from 18KB to
  97KB, and registers op-generator's PreToolUse baseline guard for every CLI in that
  project.



### Fixed

- `dispatch_parallel.py` hard-coded `--model claude-sonnet-4-6` in the CLI default, in
  `RouteRunCtx` and in `_launch_route`, so `gene-fusion` route workers failed outright on
  gateways that only serve other models. The default now comes from
  `TRITON_ROUTE_MODEL` / `CANNBOT_ROUTE_MODEL`, and when neither is set the `--model` flag
  is omitted so the CLI inherits its own default; the route prompt is still passed
  positionally after the optional model flag.
- `triton-op-generator/plugin-sources.json` and `triton-auto-evolve/plugin-sources.json`
  now declare `ops/triton-mfu-analyzer`. Both agents require that Skill for MFU
  measurement (`Phase 4` / metric_mode=mfu), but it was never installed, so agents
  reported "there's no triton-mfu-analyzer" and fell back to ad-hoc measurement tooling.
- `config_loader.py` normalises `target_mfu` to `target_speedup`, and `check_npu_idle.py`
  honours `TRITON_NPU_SMI_TIMEOUT` (default unchanged at 10s): on a busy machine
  `npu-smi info -m` can take over 20s, which made every device look unusable and aborted
  the round with `NpuIdleCheckError`.

### Changed

- `triton-auto-evolve/init.sh` defaults to the `claude` client, so `init.sh project` alone
  produces the Claude Code layout (`CLAUDE.md`, `.claude/`); `opencode`, `trae`, `cursor`
  and `copilot` remain available as an explicit second argument.
- Added the `model-recommend-infer-optimize` community plugin: end-to-end inference optimization for recommendation / search / ranking / vision-encoder models on Ascend NPU. The primary agent drives entries 0-14 (environment baseline → model analysis → single-card baseline → concurrency and core policy → precision gate → performance analysis) and then a one-action-per-round optimization loop gated by both precision and performance, dispatching four subagents (runner / analyzer / implementer / reviewer). Its eighteen atomic Skills live in the `cannbot-skills` repository under `community/model/` and are pulled through `plugin-sources.json`; the plugin itself keeps the orchestration assets and bundles the GE_SESSION_DEMO framework under `framework/` (upstream Apache-2.0, LICENSE/NOTICE shipped, exempted in `OAT.xml`), which is copied to the project root at install time for the onnx path — pytorch / HuggingFace inputs stay on the model's own script plus `torch_npu` and are documented as experimental.
- Added the `ops-direct-invoke-flash` plugin (migrated from the cannbot-skills repository): end-to-end construction of a brand-new Ascend C kernel from a CPU function, a mathematical formula, a code fragment, or a text description, covering environment probing, definition and design documents, incremental implementation, on-device NPU verification, and wrap-up documentation; `AscendC::Reg` code is generated natively when the target is Ascend950 / `dav-3510`. The entry Skill `ops-direct-invoke-flash` ships inside the plugin with its own hooks, references, scripts, and the `add`/`mul`/`sqrt` reference operators; `ascendc-st-design` and `ascendc-whitebox-design` are sourced from `vendor/cannbot-skills` via `plugin-sources.json`, which sets `preserveSkillInvocationPolicy` so the bundler leaves the entry Skill's `disable-model-invocation: true` intact and an npm install behaves like a source install. The three reference operators moved from the plugin root to `skills/ops-direct-invoke-flash/operators/` so they remain reachable through `${CLAUDE_SKILL_DIR}` after installation; `AGENTS.md` gained a `name` and is declared in `agents`, so it installs as the `direct-invoke-flash` primary agent alongside the `ops-direct-invoke-flash-reviewer` subagent. The plugin's self-contained 322-line `init.sh` is replaced by the shared thin source adapter: the cursor/copilot/codearts targets and global-level installation are no longer offered, and installs are recorded in the shared `cannbot-plugin.json` registry instead of the per-tool `cannbot-manifest.json` the old installer wrote. The shared installer splices `AGENTS.md` into a marker block instead of symlinking it as the project instruction file, which left the old fixed `parents[3]` lookup in `validate_test_gate.py` unable to find any config once installed, silently forcing `harness.test_gate` to `off`; the validator now locates its own `<!-- cannbot:ops-direct-invoke-flash:start -->` block wherever it sits in the file (the installer appends it after existing content, and other plugins splice their own), accepts `CLAUDE.md` as well as `AGENTS.md`, and resolves the config file — not merely its directory — as the nearest one actually declaring `harness.test_gate` at or above `--operator-doc-dir`, falling back to its own plugin directory. The upward search stops at the project root (`.git`/`.cannbot`) so a user-level config cannot supply the switch, and ignores the operator doc directory, which the workflow writes into. A resolution miss is now a gate failure (`config_not_found`, exit 1) instead of a silent `off`, and the file the setting came from is printed.
- Added the `ops-perf-optimize` plugin (migrated from the cannbot-skills repository): end-to-end AscendC operator performance tuning through the five-stage workflow (baseline evaluation, preparation, diagnostic analysis, implementation verification, post-processing), with project extraction and restoration, precision gates, generalization tuning, and per-case regression protection. Its nine workflow Skills ship inside the plugin; seventeen shared AscendC Skills plus the `knowledge-query` Skill are sourced from `vendor/cannbot-skills` via `plugin-sources.json`. The cannbot-knowledge knowledge base, `asc-devkit`, and `cann-samples` are declared in `plugin-install.json` and cloned under `.cannbot/dependencies/ops-perf-optimize/` (asc-devkit/cann-samples exposed at the project root); scheme design (analysis) and scheme implementation consume KB cards through the `KB_ROOT` dispatch-envelope field — citing `kb_cards` doc-ids in the analysis report and `scheme-conformance.json`, degrading to `kb_unavailable` when the knowledge base is absent; the installer replaces the previous self-contained `init.sh`.
- Added the `triton-op-generator` plugin (migrated from the cannbot-skills repository): Triton-Ascend operator generation and optimization in Phase 0-7 direct-execution mode. Its eight triton Skills plus `knowledge-query`/`ops-knowledge-ingest` are sourced from `vendor/cannbot-skills` via `plugin-sources.json`; the cannbot-knowledge knowledge base is auto-cloned at install time via `plugin-install.json`; the baseline guard hook uses the standard `hooks/hooks.json` layout; all knowledge cards are served from cannbot-knowledge.
- Added the `pypto-op-orchestrator` plugin for PyPTO operator development: the 7-stage
  state machine (plan → golden → design → verify-prep → per-module implementation →
  final E2E → performance tuning) is orchestrated as two harness workflows
  (`pypto-op-develop.yaml` for generation plus tuning, `pypto-op-tune.yaml` for
  tuning only) in the node-as-agent style, with `general-executor`/`general-verifier`
  protocol shells and stage behaviour carried by node fields. The plugin ships no
  PyPTO Skills, role agents, or hooks itself; `plugin-install.json` declares the
  [cannbot-skills](https://gitcode.com/cann/cannbot-skills) repository as a dependency
  with an `assets` mapping, and the installer clones it at install time and links the
  declared Skills/hooks/AGENTS.md into the target project (relative symlinks, tracking
  `master`). The installer gained the dependency-asset mechanism for this:
  `assets` on `plugin-install.json` dependencies, the dependency repository's
  `plugin-assets.json` manifest (inline keys override), and `resolvePluginDir` now
  accepts a plugin without a local `skills/` directory when it declares such assets.
  The harness orchestrator also fixes subprocess `PWD` propagation so providers that
  resolve the project directory from `PWD` work when the orchestrator is started from
  another directory.
- Added the `hccl-op-generator` plugin for HCCL AICPU standard communication operator development, with four Agent state-machine workflow, from the cannbot-hccl repository. Corresponding Skills are contributed to the [cannbot-skills](https://gitcode.com/cann/cannbot-skills) repository under `communication/`.
- Community plugin channel: `plugins-community/` is recognised by the bundler and the
  installer, and a community plugin is indexed by its manifest `name`, so its directory
  name is only a storage location. `plugins-official/` keeps the rule that the directory
  name is the plugin id.
- Agent and workflow bodies have `skills/<name>/` references rewritten to the installed
  Skill path, matched only against Skill names that resolved, so prose is not altered.
- A Skill name claimed by two plugins is refused only when the resolved sources differ;
  two plugins resolving the same Skill from the same place install as before.
- Community plugin `cake` (CAKE2, Collaborative Ascend Kernel Evolution): 19 Skills and
  3 agents for AscendC operator generation and evaluation, at
  `plugins-community/collaborative-agent-kernel-evolution/`. The content is the copy
  published in `cann/cannbot-skills`; registration files (`plugin-sources.json`,
  `init.sh`, `.codex-plugin/plugin.json`, marketplace entry, `OAT.xml` filteritem) are
  new here. The remaining Skills of the TileLang, EasyAsc and CV routes follow separately.
- Third-party attribution for cake: 40 files obtained from `just-it/ascendopgenagent`
  (commit `d530e7b`, offered under Apache-2.0) now record that provenance and a
  modification notice instead of a CANN-2.0 header. The notice states where the content
  came from rather than who holds copyright in it, because that repository declares no
  copyright holder and is not the origin of the Triton-derived DSL it documents; `LICENSE-APACHE` ships with the
  plugin, `README.OpenSource` records the component, and `OAT.xml` exempts those paths
  from the CANN-2.0 header policy. `skills/reference-generation/references/hardtanh.py`
  The torch_npu path block in `skills/ascendc-evaluation/scripts/template/CppExtension/
  setup.py` is registered against the Ascend samples (Apache-2.0). The notices lead with Huawei's
  modification claim so the repository's header rule still matches, and state the
  acquisition route rather than asserting who holds copyright upstream.
- `skills/ascendc-evaluation/scripts/template/CppExtension/csrc/pytorch_npu_helper.hpp`
  has its upstream BSD-3-Clause notice restored and is registered as third-party. The
  notice had been replaced with a CANN-2.0 header, while a second copy of the same file
  elsewhere in this plugin family retains BSD-3-Clause and is registered under it. The
  composition scan did not report this file.
- `skills/cake-docs-search/scripts/*` record that they share origin with
  `ops/ascendc-docs-search` in `cann/cannbot-skills`, which this plugin vendors as
  `vendor/cannbot-skills`, first published in CAKE2 on 2026-03-24.
- `skills/reference-generation/references/hardtanh.py` is removed from this change.
  It adapted a Stanford KernelBench task, and the step 4 bullet in that skill's
  `SKILL.md` which pointed at it is removed with it; `linear_softplus.py` remains as
  the reference example for that step.

### Fixed

- A clean install could leave `knowledge-query` installed but unusable, so agents ran on
  the skeleton path while the knowledge base sat unused in the project. The retrieval
  index is built lazily on first query, but that auto-build — and the rebuild after the
  index goes stale — was gated by a stricter rule than root discovery uses, so
  `cannbot-knowledge` checkouts provisioned by `plugin-install.json` (which carry only
  `ops/` + `index.md`) were rejected with "does not look ready". The fix lives in
  `cannbot-skills` (`knowledge-query`: three readiness checks now share one trust rule);
  the `vendor/cannbot-skills` gitlink will be bumped to the merged commit in a follow-up,
  and this entry records the user-visible behaviour change. `triton-op-generator`'s
  quickstart now states that the index is built lazily on first query rather than at
  install time, so the one-off ~50s cost is not mistaken for a hang.

### Fixed

- `triton-auto-evolve`'s `init.sh` resolved the shared Skills from the
  `vendor/cannbot-skills` gitlink, so a fresh clone installed whatever commit the gitlink
  pinned instead of the current branch: users got stale Skills and a stale
  `knowledge-query` even after the Skills repository had moved. It now resolves the shared
  checkout the way the unified installer does — explicit `--skills <path|SHA>` first,
  otherwise the latest commit of the same-named remote branch (falling back to `master`),
  failing loudly instead of silently installing the pinned revision — and prints the
  resolved revision so staleness is visible at install time.

### Changed

- The `model-recommend-infer-optimize` installer now merges `settings.json` hooks by JSON instead of skipping them when the file already exists, splices its instruction file into a marker block with a backup instead of overwriting `AGENTS.md` / `CLAUDE.md`, quotes hook command paths, and fails the health check when hooks are not actually registered.
- The installer now copies a plugin's `framework/` directory along with `workflows/`, `agents/` and `hooks/`. Plugins that ship runtime assets outside those well-known directories previously lost them on `cannbot install`; the bundled `GE_SESSION_DEMO` framework of `model-recommend-infer-optimize` is the first consumer.
- Renamed the official plugin directory `plugins/` to `plugins-official/`, aligning with the `cannbot-skills` repository layout and pairing with `plugins-community/`; updated the marketplace sources, installer discovery paths, bundling, tests, and documentation accordingly. The npm package layout (`dist/plugins/`) and the installed layout (`.cannbot/plugins/`) are unchanged.
- A plugin may set `preserveSkillInvocationPolicy` in `plugin-sources.json` to keep the
  `disable-model-invocation` value each of its Skills was authored with. Without it the
  bundler rewrites the value as before.
- Community plugins are not stamped with a plugin-root licence; each keeps the licence it
  ships with, and `plugins-community/` carries none.

### Removed

- Removed the test-oriented `ascendc-st-design` plugin from `plugins-official/` and its marketplace entry. The `ascendc-st-design` Skill remains available in `cannbot-skills` and is still bundled by `ops-direct-invoke`.

## 1.3.2 - 2026-08-31

### Changed

- Switched plugin homepage URLs to the canonical production HTTPS endpoint.

## 1.3.1 - 2026-08-31

### Changed

- Aligned plugin homepage URLs with the production HTTP endpoint.
- Added the static CANNBot plugin portal and aligned its operator test page with `ascendc-st-design`.

## 1.3.0 - 2026-08-31

### Added

- Added repository-level CANN Open Software License 2.0 metadata and OAT compliance configuration.
- Added a Claude Code marketplace catalog for the three official plugins.
- Added Git text normalization and binary file rules.
- Added per-plugin license delivery and npm package installation smoke tests.
- Added the `ascendc-st-design` plugin for L0/L1/L2 system test design.

### Changed

- Standardized repository metadata on the official URL, `https://gitcode.com/cann/cannbot`.
- Unified npm and source installations behind the same Node.js installer.
- Added plugin-level `init.sh` adapters for source installations.
- Made source installation initialize the Skill submodule only when required.
- Renamed `npm/` to `script/` and `plugin-official/` to `plugins/`.
- Added the repository architecture, directory responsibilities, and release flow to the root README.
- Made plugin instructions and installation records coexist across multiple installed plugins.
- Renamed the internal CLI entry point to `cannbot.js`.

## 1.2.2 - 2026-08-21

### Changed

- Moved npm tooling into its own directory.
- Enabled shallow initialization of the Skill submodule.

## 1.2.1 - 2026-08-21

### Changed

- Established `cannbot-skills` as the single Skill source through a pinned Git submodule.
- Added build-time plugin assembly for npm packages.

## 1.2.0 - 2026-08-21

### Changed

- Made published official plugins self-contained so npm users do not clone the Skill repository.

## 1.1.0 - 2026-08-21

### Added

- Added packaged official plugins and native plugin initialization support.

## 1.0.0 - 2026-08-19

### Added

- Published the cross-client installer as `@cannbot-plugin/cannbot`.
