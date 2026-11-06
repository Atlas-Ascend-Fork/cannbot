---
name: workflow-orchestrator
description: Run a development workflow defined in workflow.yaml.
disable-model-invocation: true
---

# Workflow Orchestrator

`$SKILL_ROOT` = the absolute path of the directory containing this SKILL.md.
`$START_DIR` = the absolute startup directory of the current Agent session, recorded when this skill begins. It is the plugin project directory containing the model-adapter files.

## Running in the DSH plugin

When running inside DSH with `cannbot_workflow_run` available, follow this branch and its linked approval instructions; the CLI inputs and steps below apply only to other hosts.

1. Resolve the owning CANNBot workflow ID, YAML path, task prompt and working directory from the selected workflow and user request. Reuse values already supplied; ask only for required information that is missing. For a new run, omit `workDir` to use the tool’s default session workspace unless the user supplies a directory within that workspace. For a resumed run, reuse its original YAML and working directory.
2. Start or resume with `cannbot_workflow_run`, following its tool definition for parameters. No provider selection is required.
3. Keep the returned `runId` and poll `cannbot_workflow_status` with `waitMs: 10000`.
4. If any task in the returned `state.tasks` has `status: "awaiting_approval"`, follow [Human approval](#human-approval) using the returned `workDir`, then continue status polling. On a stop request call `cannbot_workflow_cancel`.
5. Report completion only after the workflow exits successfully. Include failed/skipped tasks and log diagnostics on failure. After a DSH restart, resume with the same YAML and directory and use the newly returned `runId`.

If this is a DSH session but these tools are unavailable, report that the CANNBot plugin must be enabled or updated. Do not substitute a CLI provider.

## Inputs

Four required inputs:

- `workflow.yaml` — path to the workflow definition file.
- `work_dir` — working directory; every workflow artifact and intermediate artifact is produced here.
- `provider` — the Coding Agent CLI used to execute the workflow's tasks.
- `prompt` — the prompt for this development task.

For a missing `work_dir`, suggest `$START_DIR/<task_or_project_name_in_snake_case>`. Use the task or project identifier from the prompt, convert word boundaries and separators to underscores, and use lowercase. Ask for an identifier only when needed to derive this directory. Preserve a user-supplied `work_dir`.

## Steps

For questions, use the environment's question tool when available; otherwise ask in chat and wait for the reply.

1. **Prepare input candidates.** First read the orchestrator's CLI help:

   ```bash
   python3 "$SKILL_ROOT/scripts/orchestrator.py" --help
   ```

   Use the values shown for `--provider` as the source of truth for provider options and validation. Proceed when the command succeeds and lists the accepted values. Preserve valid values the user has supplied. For missing inputs, propose values supported by the current task and session:
   - `workflow.yaml`: use the workflow file identified by the user or current plugin workflow; ask if no file is identified.
   - `work_dir`: use the task or project directory suggestion under Inputs.
   - `provider`: propose the actual CLI command name running the current Agent session when it appears in the help's accepted values. Match the current CLI itself rather than a protocol-compatible alternative. When the current session was started with CANNBot, use `cannbot` even though its agent protocol is compatible with OpenCode. Use session context to identify it; installed executables and configuration directories alone do not identify the running CLI. If the CLI is unknown or unsupported, ask the user to choose from the accepted values.
   - `prompt`: use the user's development request, preserving requirements and acceptance criteria; ask for any missing task requirements.
   Ask the user for unresolved values. Proposed values remain candidates until confirmed.
   Done when: all four concrete candidates are available and `provider` is accepted by the CLI help.
2. **Absolutize paths.** Run `realpath -m` on `workflow.yaml`, `work_dir`, and `$START_DIR` (`-m` allows the proposed `work_dir` to be absent).
   Done when: the three resulting paths are absolute and retain their intended locations.
3. **Confirm all four inputs.** Use a single question-tool call containing exactly four questions, one for each input. Populate the provider options from the CLI help output collected in Step 1, and validate any edited provider against that list. In each question body, display the complete current candidate value, including full paths and prompt text. For every option, use the actual value or a meaningful short form as the `label`; put the full value and its explanation in the `description`. Never use a generic label such as "Use this path" that conceals the value. Allow the user to edit each value directly. If a value is missing or invalid, ask only about that value and wait for the user's response. Reuse confirmations already given for these exact values during this run. Suggestions, preselected choices, and silence do not count as confirmation.
4. **Prepare Agent configuration.** Run the linker and require exit status 0 before starting tmux:

   ```bash
   python3 "$SKILL_ROOT/scripts/link_agent_config.py" \
     --start-dir "<start_dir>" \
     --work-dir "<work_dir>" >> "<work_dir>/orchestrator.log" 2>&1
   ```
   Done when: `work_dir` exists, the linker exits 0, and its redirected output is present in `<work_dir>/orchestrator.log`.
5. **Run the orchestrator** (blackbox — see below) in a detached tmux session, logging output to `<work_dir>/orchestrator.log` with the exit status appended.

   Session name `<session>`: `orchestrator-<slug>`, where `<slug>` is the basename of `work_dir` with every character outside `[A-Za-z0-9_-]` replaced by `-`. If `tmux has-session -t <session>` says the name is taken, append `-2`, `-3`, … until it is free.

   ```bash
   tmux new-session -d -s <session> \
     'python3 $SKILL_ROOT/scripts/orchestrator.py \
       --yaml "<workflow.yaml>" \
       --work-dir "<work_dir>" \
       --provider "<provider>" \
       --prompt "<prompt>" >> "<work_dir>/orchestrator.log" 2>&1; \
      echo "exit status: $?" >> "<work_dir>/orchestrator.log"'
   ```

   (Substitute `$SKILL_ROOT` and each `<...>` placeholder verbatim, **keeping the double quotes** — the inner shell parses the substituted command, and an unquoted prompt with spaces or `(` dies as a syntax error before the log redirect runs. Escape `"`, `` ` `` and `$` inside a substituted value.)

   Then enter the wait loop. Each round (~10s apart) does the following two things until `tmux has-session -t <session>` fails (session ended):

   1. Poll `tmux has-session -t <session>` (as above).
   2. Follow [Human approval](#human-approval) with `<work_dir>` to display progress and handle pending approvals.
   Done when: the session has ended, and the log (output + exit status) has been relayed to the user verbatim.

## Human approval

Use the running workflow’s working directory as `<work_dir>` throughout these steps.

1. Run `python3 "$SKILL_ROOT/scripts/poll_workflow.py" --work-dir "<work_dir>"`.
   Relay stdout **verbatim** as plain text, without added headers, code fences, rewording or JSON conversion. Relay the progress block even when unchanged.
2. For each `◉ 待审批 <task_id>「<title>」` entry, ask the user to choose **approve / redo / fail**, including the task ID, title, acceptance list and review hints. Use the environment’s question tool when available; otherwise ask in chat. Require a comment for redo; a reason for fail is optional. Handle multiple tasks one by one and wait for the user’s actual decision; keep unanswered questions pending without asking them again.
3. After the user answers, submit that decision:

   ```bash
   python3 "$SKILL_ROOT/scripts/approve_task.py" --work-dir "<work_dir>" --task-id "<task_id>" \
     --decision <approve|redo|fail> [--comment "<user comment>"] >> "<work_dir>/orchestrator.log" 2>&1
   ```

   If the command fails, relay its error output verbatim and return to the calling branch’s polling loop. A decision is submitted only when the command exits successfully; task completion is determined by subsequent workflow status. If no entries need a new decision, return to polling.

## Blackbox rule

orchestrator.py is a blackbox: invoke it with `--help` to discover accepted providers or with the launch command above to run the workflow. Judge it only by its output and exit code. Never read or edit its source.
