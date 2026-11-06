# Third-party notices

CANNBot DSH contains the DSH adapter and installation code. Official workflow
resources are copied from the selected CANNBot source and its declared shared
Skills during source installation or workflow-package construction. This source
tree does not retain copies of those resources.
Each generated workflow package retains its CANN Open Software License Agreement
Version 2.0 and shared Skill license in resources/LICENSE and SKILLS_LICENSE.
Its workflow.json records the actual source revisions and content hashes.
Local uncommitted changes are included; revision identifiers alone do not identify
those changes. Published npm installations obtain resources from workflow packages.

Source-declared symlinks are materialized for portable installation. The upstream
bundler's model-invocation normalization is retained unless the plugin declares
preserveSkillInvocationPolicy. DSH entry Skill adapters are added for official
plugins whose primary instructions are AGENTS.md rather than a same-named Skill.
The original instructions, agents, scripts, hooks and templates are retained.

The palette and decorative C mark were developed for this plugin. DSH, Cordis,
Schemastery and DSH's UI libraries remain separately installed dependencies with
their original licenses. The build uses the official DSH client bundle preset;
this package contains no redistributed DSH desktop executable or server runtime.
