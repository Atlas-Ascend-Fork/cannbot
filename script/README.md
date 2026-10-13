# CANNBot npm installer

This directory is the complete npm project for `@cannbot-plugin/cannbot`.

```bash
npx @cannbot-plugin/cannbot install ops-direct-invoke --tool opencode
npx @cannbot-plugin/cannbot install model-infer-optimize --tool codex
```

The package build reads plugin definitions from `../plugins-official/` and `../plugins-community/` and Skill sources from the `../vendor/cannbot-skills` submodule. `prepack` assembles the selected source trees into `dist/plugins/`, so npm users receive a self-contained package and never clone the source repository. Building a package requires an initialized submodule; package builds keep the checked-out revision rather than fetching master.

```bash
npm test
npm run build:plugins
npm pack --dry-run
npm run pack:smoke
npm publish --access public
```

`npm publish` runs the full test suite and installs the generated tarball through
its `cannbot` npm bin before publishing. Version `1.3.2` was released on 2026-08-31.

The npm package is a mixed-license distribution. The installer implementation
is MIT licensed. Assembled official plugins and bundled Skills retain the CANN
Open Software License Agreement Version 2.0 and any license notices included
with their content; see the package `LICENSE` overview and the license files in
each `dist/plugins/<plugin>/` directory.

All supported CLI clients use the same Node installer. Source `init.sh` scripts that use the shared entry point forward the selected plugin, source repository, tool, and target to the CLI, which links Skills to their declared source directories. Independent plugin installers retain their own behavior. npm installation copies the bundled Skills. Plugin-specific dependency repositories are declared in `plugin-install.json`.

See [the workflow installation and usage guide](docs/cannbot-workflows.md) for all supported commands and prompt examples.

Community plugins with a `plugin-sources.json` are also assembled into the package. To install ops-direct-invoke from its source directory:

```bash
node script/bin/cannbot.js install ops-direct-invoke --source "$PWD" --tool codex --target /absolute/project
```

`--override-skills /absolute/overrides` replaces selected existing repo-* Skills from same-named directories. Document templates are maintained under ops-direct-invoke/templates; workflow reference graphs live in workflows/ascendc and carry use_when metadata. Run scripts/generate_workflow_guide.py with --output in the work directory before selecting a template from the generated guide. The workflow entry and scheduler cannot be replaced through this option. See the ops-direct-invoke README for its task assembly rules and current public-interface limitations.

For source installations that declare shared Skills under `vendor/cannbot-skills`, each install initializes the submodule if needed and fetches the branch on its `origin` matching the current CANNBot branch. If that remote branch does not exist, or CANNBot has a detached HEAD, it uses `master`. Remote lookup or fetch errors fail the installation instead of triggering fallback. `--skills <SHA>` selects a commit (use a full SHA to fetch missing commits); `--skills <path>` links shared Skills from a local Git worktree root, resolving relative paths from the calling directory. Explicit overrides bypass branch selection. This preserves repository-local harness and plugin Skills. Default/SHA updates reject uncommitted submodule changes. Local overrides keep uncommitted content and never update the submodule. Packaged installs and plugins without shared dependencies reject `--skills`.

The client-specific `cannbot-plugin.json` records `source.revisions.cannbot` and `source.revisions["cannbot-skills"]` (selection, requested value, full commit, dirty flag, and local path when applicable). Automatic selection uses `selection: "latest-branch"` and records the actual selected branch in `requested`, including `master` after fallback. Reinstalling replaces the plugin record. These options and records apply to the shared installer; independent entry points such as `ascendc-port-orchestrator/init.sh` are not integrated. See [the shared-source guide](docs/cannbot-workflows.md#安装方式).

Updating the submodule may mark its Gitlink as changed in the CANNBot worktree. All source installations use live symlinks, including fixed-SHA installations: subsequent updates to a shared checkout affect earlier installations. Revision records describe installation-time commits, not frozen copies; dirty content is not reproduced by its commit alone. Use independent checkouts with `--skills <path>` for separate project versions.

`--plugin-dir` selects a specific plugin directory when its folder name differs from its manifest name. Relative paths resolve from `--source` for source installs, or the installer package root for packaged installs. The requested install ID must match the manifest; installed assets and registry records always use that ID.
