# CANNBot managed plugins

This directory contains the official CANNBot plugin definitions and non-Skill files:

- `ops-direct-invoke`
- `model-infer-optimize`
- `hccl-op-generator`
- `triton-op-generator`

Each plugin declares the Skills it needs in `plugin-sources.json`. The actual Skill source is maintained in the `vendor/cannbot-skills` submodule and is not duplicated in this repository.

Each plugin's `init.sh` creates project Skill symlinks to the submodule. `npm --prefix script run build:plugins` instead copies the declared Skills into `script/dist/plugins/<plugin>/skills/` for a self-contained npm package.

Each `init.sh` is a thin source adapter for the shared Node installer. Optional dependency repositories are declared in `plugin-install.json`.

An official plugin's directory name is its plugin id: the directory name and the manifest `name` must agree, and the bundler rejects a plugin where they do not. Community plugins under `plugins-community/` are indexed by their manifest `name` instead, so their directory name is only a storage location. Each official plugin is assembled with a copy of `plugins/LICENSE`; a community plugin keeps whatever licence it ships with, and the community root has none.
