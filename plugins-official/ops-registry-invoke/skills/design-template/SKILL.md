---
name: design-template
description: Use when rendering one bundled ACLNN operator design document from a caller-selected .md.templ file into a caller-provided output path; not for implementing kernels, creating executable tests, or authoring requirements.
disable-model-invocation: true
---

# Design Template

`$SKILL_ROOT` is the directory containing this `SKILL.md`; bundled templates live under `$SKILL_ROOT/templates`.

## Inputs

The calling task must provide:

1. The exact bundled template name. Reject names containing `/`, `..`, or a leading `.`. If the template is not one of the bundled files, report a missing bundled resource instead of resolving an arbitrary path.
2. Target output path.
3. A sibling locator mapping from each referenced document name to either a colocated path or an explicit path/identifier. When a referenced sibling or section is absent or ambiguous, mark the dependent fact `待补`, name the missing locator/section, and do not fabricate it.
4. Operator facts, requirement facts, and values for placeholders that the target template uses.
5. Runtime resources and resource locators, including paradigm resources, code templates, reference implementations, performance artifacts, platform limits, and API evidence. Resources may be files or caller-declared inline content. If absent, record that they are missing; never infer or invent a path.
6. The complete set of caller-authorized output paths. Cross-document repair is allowed only for paths explicitly listed by the caller.
7. A planned-reference list when a sibling document is intentionally produced later. For each such reference, record its owner/producing stage and the initial missing-fact marker.

## Render rules

1. Render only the requested target file, plus only the caller-authorized repair paths when an explicit repair contract requires them.
2. Select the matching template from the bundled allowlist:
   - `$SKILL_ROOT/templates/design/<NAME>.md.templ` for a top-level design document.
   - `$SKILL_ROOT/templates/DESIGN-BRANCH.md.templ` for one branch design document.
3. Replace only placeholders with caller-provided facts. Common meanings are:
   - `{OP}`: operator `snake_case` name; `{OP_UPPER}`: its `UPPER_SNAKE` form.
   - `{KEY}`: current tilingKey.
   - Branch design file locators: caller-provided values registered by `BranchCatalog.md`.
4. Treat `>` paragraphs and template comments as generation guidance, not output content. Remove all generation guidance before delivery.
5. Preserve required section headings and ordering. Replace examples, scaffold cells, `<fact>` markers, and unfilled placeholders with operator-specific facts, explicit `N/A`, or a missing-input reason.
6. Use sibling document name plus section title for cross-references; do not add directory paths. Planned forward references must follow rule 7 in Inputs and must not block unrelated sections.
7. Write only caller-authorized paths. Do not modify templates, workflows, inputs, or unauthorized documents.

## Acceptance

- Every authorized output exists, is non-empty, and is self-consistent for facts available in the declared input set.
- Every placeholder with a provided value is replaced; no fact is invented.
- No generation guidance, template comment, unfilled fact placeholder, or empty scaffold cell remains.
- Required sections remain present and ordered.
- Every cross-reference resolves through the sibling locator or is an explicitly owned planned reference with its owner and missing-fact marker.
- Runtime-provided resource references remain traceable to their declared source or are explicitly marked missing.
- When a required repair path is not authorized, report the blocker instead of editing it.
