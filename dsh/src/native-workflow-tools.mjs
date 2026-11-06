import { defineTool } from '@deepseek-ai/dsh-tools'
import { access, realpath } from 'node:fs/promises'
import { isAbsolute, join, resolve } from 'node:path'
import { NativeWorkflow, within } from './native-workflow.mjs'
import { installGoalWorkflowResume } from './goal-workflow-resume.mjs'
import { PmProgress } from './pm-progress.mjs'

/** Register generic Python workflow scheduling tools when DSH's native loop is available. */
export function installNativeWorkflowTools(ctx, content) {
  ctx.inject(['tools', 'subagents', 'workingDirectory', 'sessionProjections', 'sessions', 'sessionQuery'], scoped => {
    const execution = new NativeWorkflow(scoped)
    const progress = new PmProgress(scoped)
    let goals
    scoped.on('dispose', () => execution.dispose())
    scoped.on('dispose', () => progress.dispose())
    async function start(args, agent, signal) {
      const workspace = await realpath(await scoped.workingDirectory.ensure(agent, signal))
      await content.prepare(workspace, args.workflow)
      const source = content.getSource()
      const plugin = source.catalog.plugins.find(item => item.id === args.workflow)
      if (!plugin) throw new Error('Unknown workflow package')
      const resources = await realpath(resolve(source.assets, plugin.resourceDirectory ?? plugin.id))
      const runner = join(resources, 'skills/workflow-orchestrator/scripts/orchestrator.py')
      await access(runner)
      const yaml = await realpath(isAbsolute(args.yaml) ? args.yaml : resolve(resources, args.yaml))
      if (!within(resources, yaml) && !within(workspace, yaml)) throw new Error('Workflow YAML must belong to the package or workspace')
      const cwd = resolve(workspace, args.workDir ?? '.')
      if (!within(workspace, cwd)) throw new Error('Workflow directory must be inside the session workspace')
      // Check the nearest existing ancestor so symlinked directories cannot escape the workspace.
      let ancestor = cwd
      while (true) {
        try {
          if (!within(workspace, await realpath(ancestor))) throw new Error('Workflow directory escapes the session workspace')
          break
        } catch (error) {
          if (error.code !== 'ENOENT') throw error
          ancestor = resolve(ancestor, '..')
        }
      }
      signal.throwIfAborted()
      return execution.start(agent, { runner, yaml, cwd, resources, prompt: args.prompt, workflow: args.workflow, goalId: goals?.get(agent)?.id })
    }
    scoped.inject(['goals'], goalScope => {
      goals = goalScope.goals
      goalScope.on('dispose', () => { goals = undefined })
      installGoalWorkflowResume(goalScope, execution, start)
    })
    const string = { type: 'string', required: true }
    const specs = [
      ['cannbot_workflow_run', {
        workflow: string, yaml: string, prompt: { type: 'string' }, workDir: { type: 'string' },
      }, 'Run or resume a YAML workflow from the selected CANNBot workflow package. Python owns scheduling, parallelism, retries and verdicts; nodes use the DSH native agent loop and inherit the session model. No CLI provider is needed. yaml is absolute or relative to package resources; workDir defaults to the session workspace. prompt is required for a new run.'],
      ['cannbot_workflow_status', { runId: string, waitMs: { type: 'number' } }, 'Read Python workflow state and log. Optionally wait up to 30000 ms. Awaiting approvals remain governed by the Python workflow approval scripts.'],
      ['cannbot_workflow_cancel', { runId: string }, 'Stop this session’s scheduler and native node agents. Start the same YAML and working directory again to recover through the Python resume logic.'],
    ]
    for (const [name, parameters, description] of specs) {
      scoped.tools.register(defineTool({ name, parameters, description,
        output: { schema: { type: 'object', properties: {}, additionalProperties: true },
          render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }],
        },
        async execute(args, exec) {
          if (!exec.agent) throw new Error('A live DSH session is required')
          if (name === 'cannbot_workflow_status') return execution.status(exec.agent, args.runId, args.waitMs)
          if (name === 'cannbot_workflow_cancel') return execution.cancel(exec.agent, args.runId)
          if (['provider', 'model'].some(key => key in args)) throw new Error('Workflow nodes inherit the DSH session model')
          return start(args, exec.agent, exec.signal)
        },
      }))
    }
  })
}
