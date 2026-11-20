# CONVENTIONS — naming, numbering, language

- **Entry files**: `book-9x0/entries/NNNN-<claim-shaped-slug>.md`. NNNN is book-local, never
  reused, never renumbered. Phase-1 mass harvest pre-allocates per-domain number blocks (see the
  plan's 2026-08-24 amendment); within a block, drafting order. The slug states the claim,
  lowercase, hyphenated, no topic-words ("notes", "misc", "overview" are banned in slugs).
- **Cross-references**: inside a book, `NNNN` suffices; in logs, plans, and anything that can be
  read from outside one book, write `910:NNNN` or `950:NNNN`. The bare form in a shared file is a
  form error the checker flags.
- **Board tokens** (the only accepted spellings): `910B1`, `910B2`, `910B2C`, `910B4`, `910_93`,
  `910C`, `950PR`, `950DT`, `family-claimed(unverified)`. New boards are added here first, then
  used, and `tools/check_entries.sh` is updated in the same change.
- **Upstream vocabulary map** (per upstream's declared truth source,
  `ops/npu-arch/references/npu-hardware-params.md`): ASCEND910B = DAV_2201 = `__NPU_ARCH__` 2201 =
  arch22 = Atlas A2 **and A3** = boards 910B1–B4, 910B2C, 910_93; ASCEND950 = DAV_3510 =
  `__DAV_C310__` = 3510 = arch35 = Atlas A5 = 950DT, 950PR. `regbase` and `SIMT` are 950-era
  PROGRAMMING MODELS, not chips — a passage using that vocabulary lands in book-950 by mechanism
  even if no chip is named. The word "910C" is not defined anywhere upstream; treat it
  as probably-`910_93`/A3 vocabulary, and never write `910C` in a BOARD line on upstream evidence
  alone — write the token the source actually names, or `family-claimed(unverified)`.
- **Claim-cards**: `harvest/claims/<source-skill>--NNN-<slug>.md`, numbered per source skill. The
  source skill's name in the filename is deliberate: `ls harvest/claims/` must show coverage and
  gaps per upstream skill at a glance.
- **Level maps**: each book declares its own `Lx` level map in its `book-9x0/README.md` (the 910
  book may start from the parent book's map; the 950 book must not inherit 910 levels blindly —
  regbase/SIMT-era architecture may need its own strata of failure).
- **Language**: all artifacts in English (matching the parent book and upstream SKILL.md
  conventions). Conversational reporting to the operator is separate and may be Chinese.
- **Dates**: absolute (`2026-08-24`), never relative. A date is a property of a past event; it has
  no re-derive command.
- **Upstream references**: always relative to `upstream/skills-dev-main/`, with line numbers.
  Upstream is read-only; nothing in `upstream/` is ever edited, and no artifact of ours lives there.
- **The parent repo `ascend910/` is out of bounds for writes.** Reading it (for form, for
  comparison) is fine; `kb/` must remain self-contained enough that deleting the parent
  repo would not invalidate a single entry here.

> 2026-08-24 addendum (C-950fin-009): the installed toolchain's reg-compute interface admits
> `__NPU_ARCH__` values beyond the upstream truth-source map — 1001, 2002, 5102, 3003, 3113 were
> observed in shipped headers/gates and are mapped NOWHERE upstream. "regbase ⇒ 950" is an
> assumption the toolkit does not make; never infer a board from an arch value outside the map.
>
> 2026-08-24 phase-2 update, measured on the bound installations (harvest/RUNS_20260824.md):
> **1001 now has an installed identity** — `platform_config/Ascend910B.ini` carries `NpuArch=1001`
> (previous-generation Ascend910; ub=256 KB, l1=1 MB, l0c=256 KB, l2=32 MB — the row that C-003's
> "typical" table and the 32 MB in 910-book statement B reproduce). **3003 and 3113 appear in the
> arch gate of `GetVecLen()`** (`kernel_operator_sys_var_intf.h`: enabled for `__NPU_ARCH__` ∈
> {3003, 3113, 3510}) — still mapped to no board; the rule stands: never infer a board from an
> arch value outside the map.
>
> 2026-08-25 close-out vocabulary correction (the one owed by the phase-2 triage:
> C-950fin-009 · C-950bp-011 · C-950td-026 · C-950bp-008/C-950fin-030 · C-910-005;
> measured facts in `harvest/RUNS_20260824.md`, register rows in `harvest/contradictions-950-*.md`
> and `harvest/TRIAGE_DOMAIN_ROWS_20260825.md`):
>
> - **The 2026-08-24 addendum's "mapped NOWHERE upstream" was too wide.** Upstream's declared
>   truth source (`npu-hardware-params.md:13-21`) does carry rows for DAV_1001 and DAV_2002
>   (alongside 2201/3002/3510 — C-950arch-001's reading). What remains mapped to no board
>   upstream: **3003, 3113, 5102**.
> - **Installed identities, measured**: 1001 = `Ascend910B.ini` (see the update above);
>   3505 = `Ascend035*.ini` ×3 on CANN 9.1.0, with **no DAV_3505 row upstream** (C-950arch-001);
>   the vendor's compile-time table (`asc/include/utils/base/sys_constants.h`) gates BT per
>   `__NPU_ARCH__`: 0 for {1001, 2002}, 1 KB for {2201, 3002, 3003, 3113}, 4 KB for {3510}.
> - **`DAV_5102`** (C-950td-026): defined nowhere; exactly two occurrences in the whole shelf,
>   both inside the gate constant `SMALL_SHAPE_BYTES_THRES_HOLD_DAV_5102_021 = 70000`. Under
>   950:0202's naming rule the digits would read "arch51", which no document mentions. Treat it
>   as a token inside a constant's name, never as a board or an architecture.
> - **`Atlas 350`** (C-950bp-011): a product name (1042 occurrences repo-wide) used as the
>   column head of the DAV_3510 conflict rules; the truth source maps Atlas **A5** = ASCEND950 =
>   DAV_3510 and has no "Atlas 350" row. Same handling as "910C": write the token the source
>   names; never write `Atlas 350` in a BOARD line.
> - **`dav310` path species** (C-950bp-008, C-950fin-030): four reference families keep
>   DAV_3510 templates under `templates/dav310/` (152 references) while two others spell
>   `dav3510`, and the usage guide instructs consumers to preserve the `dav310/` subdirectory.
>   Since DAV_2002 = ASCEND310P exists, the spelling invites a 310-family misreading. Rule:
>   copy such paths verbatim (they are load-bearing), and never infer a chip family from digits
>   inside a path.
> - **"910C" sharpened** (C-910-005, measured 2026-08-25): the installed 910 toolkit ships code
>   for the token (`ASCEND_910C` in `cce_params.py`, `is910C` tiling fields) but no
>   `Ascend910C*.ini` and no mapping row — present-but-unmapped. The BOARD-line rule above stands.
