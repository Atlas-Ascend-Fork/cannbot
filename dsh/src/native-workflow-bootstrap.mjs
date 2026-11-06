/** Plugin-owned Python bootstrap. Paths and prompts travel as argv, never interpolated code. */
export const pythonBootstrap = String.raw`
import concurrent.futures
import json
import os
import sys
import threading
import uuid

# Import the installed workflow's shared scheduler, including its sibling modules.
script = os.path.abspath(sys.argv.pop(1))
sys.path.insert(0, os.path.dirname(script))
sys.argv[0] = script
import orchestrator

# Use the unchanged CLI parser for ordinary YAML/workspace/prompt arguments.
args = orchestrator.parse_args()
if args.provider is not None:
    raise SystemExit("The plugin supplies its execution callback; do not pass a CLI provider")

class PipeExecutor:
    def __init__(self, output):
        self.output = output
        self.lock = threading.Lock()
        self.pending = {}
        threading.Thread(target=self._receive, daemon=True).start()

    def _receive(self):
        try:
            for line in sys.stdin:
                response = json.loads(line)
                with self.lock:
                    future = self.pending.pop(response['id'], None)
                if future is not None:
                    future.set_result(response)
        finally:
            # Host loss releases the Python scheduler even while awaiting approval.
            os._exit(2)

    def execute(self, entry, work_dir, path):
        request_id = str(uuid.uuid4())
        future = concurrent.futures.Future()
        with self.lock:
            self.pending[request_id] = future
            self.output.write(json.dumps({'id': request_id, 'taskId': entry['task_id'],
                                         'role': entry['agent'], 'phase': entry['_phase'],
                                         'prompt': entry['prompt'], 'workDir': work_dir}) + '\n')
            self.output.flush()
        response = future.result()
        with open(path, 'w', encoding='utf-8') as output:
            json.dump(response, output, ensure_ascii=False)
        return ('executed' if entry['_phase'] == 'execute' else ''), not response.get('ok', False)

# Preserve one protocol descriptor; scheduler/subprocess logs all go to stderr.
protocol = os.fdopen(os.dup(sys.stdout.fileno()), 'w', encoding='utf-8')
os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
sys.stdout = sys.stderr
executor = PipeExecutor(protocol)
sys.exit(orchestrator.main(task_executor=executor.execute, args=args))
`
