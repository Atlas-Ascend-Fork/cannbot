# Changelog

This file records notable changes to the CANNBot plugin orchestration and delivery repository.

## Unreleased

### Added

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

### Changed

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
